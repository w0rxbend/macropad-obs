// SPDX-License-Identifier: MIT
//! The connection the window's commands share (task 3.6), against padsim: attach, read, write with
//! the read's `seq`, the stale diff, credentials and export, each answer a value the UI can show.

mod common;

use app_core::{Change, Config, Connection, Credential, Saved};
use common::{minimal_document, Padsim, Scratch};
use serde_json::{json, Value};

const NEW_URL: &str = "ws://192.168.1.20:4455";

/// `minimal_document` written as the first document of the pad behind `connection`.
fn seed<P: std::io::Read + std::io::Write>(connection: &mut Connection<P>) -> Value {
    let doc = minimal_document();
    assert_eq!(connection.read().expect("read"), Config { seq: 0, document: Value::Null }, "a fresh pad");
    assert_eq!(connection.write(doc.clone()).expect("write"), Saved::Saved { seq: 1 });
    doc
}

#[test]
fn attach_answers_with_the_pad_info() {
    let scratch = Scratch::new("conn-info");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = Connection::new();
    let info = connection.attach(pad.port()).expect("INFO");
    assert_eq!((info.keys, info.buttons, info.knobs), (9, 4, 3));
    assert!(!info.obs_password_set && !info.wifi_psk_set);
    assert_eq!(info.git_hash.len(), 8, "four bytes as hex");
    assert_eq!(connection.info().expect("info"), info);
    connection.disconnect();
    assert!(connection.info().is_err(), "no pad after disconnect");
    pad.finish();
}

#[test]
fn a_write_keeps_unknown_fields_and_takes_the_read_seq() {
    let scratch = Scratch::new("conn-round-trip");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = Connection::new();
    connection.attach(pad.port()).expect("INFO");
    seed(&mut connection);

    let mut doc = connection.read().expect("read").document;
    doc["x_app_note"] = json!({"kept": true});
    doc["obs"]["url"] = json!(NEW_URL);
    doc["seq"] = json!(77);
    assert_eq!(connection.write(doc.clone()).expect("write"), Saved::Saved { seq: 2 }, "seq 77 is not the base");

    let back = connection.read().expect("read");
    assert_eq!(back.seq, 2);
    assert_eq!(back.document["x_app_note"], json!({"kept": true}));
    assert_eq!(back.document["obs"]["url"], json!(NEW_URL));
    drop(connection);
    pad.finish();
}

#[test]
fn a_refused_document_is_a_failure_and_writes_nothing() {
    let scratch = Scratch::new("conn-refused");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = Connection::new();
    connection.attach(pad.port()).expect("INFO");
    assert!(connection.write(minimal_document()).is_err(), "no write before a read");
    let mut doc = seed(&mut connection);

    for url in ["ws://127.0.0.1:4455", "ws://8.8.8.8", "wss://192.168.1.2"] {
        doc["obs"]["url"] = json!(url);
        let failure = connection.write(doc.clone()).expect_err("the URL rule refuses it");
        assert!(failure.to_string().contains("obs.url"), "{url}: {failure}");
    }
    assert!(connection.write(json!([1, 2])).is_err(), "not an object");
    assert_eq!(connection.read().expect("read").seq, 1, "nothing was stored");
    drop(connection);
    pad.finish();
}

#[test]
fn a_stale_write_shows_the_diff_and_takes_the_re_read() {
    let scratch = Scratch::new("conn-stale");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let port = pad.port();
    // Another writer on the same pad (the pty opens once), used while `mine` is idle.
    let second = port.try_clone_native().expect("a second handle on the pty");
    let mut mine = Connection::new();
    mine.attach(port).expect("INFO");
    let mut doc = seed(&mut mine);
    mine.read().expect("read");

    let mut other = Connection::new();
    other.attach(second).expect("INFO");
    let mut theirs = other.read().expect("read").document;
    theirs["obs"]["url"] = json!(NEW_URL);
    assert_eq!(other.write(theirs).expect("write"), Saved::Saved { seq: 2 });
    drop(other);

    doc["keys"][3] = json!({"do": "toggle_record"});
    let Saved::Stale { pad: now, changes } = mine.write(doc.clone()).expect("write") else {
        panic!("a write on seq 1 after seq 2 is stale");
    };
    assert_eq!(now.seq, 2);
    assert_eq!(now.document["obs"]["url"], json!(NEW_URL));
    assert_eq!(
        changes,
        [
            Change { path: "keys[3].do".into(), pad: Some(json!("none")), app: Some(json!("toggle_record")) },
            Change { path: "obs.url".into(), pad: Some(json!(NEW_URL)), app: Some(json!("ws://10.0.0.2")) },
        ]
    );
    assert_eq!(mine.write(doc).expect("write"), Saved::Saved { seq: 3 }, "the next write is on the re-read");
    drop(mine);
    pad.finish();
}

#[test]
fn credentials_set_and_clear_through_info_flags() {
    let scratch = Scratch::new("conn-cred");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = Connection::new();
    connection.attach(pad.port()).expect("INFO");

    let info = connection.set_credential(Credential::ObsPassword, "Zq7!Xv#9Lm@2Pp".into()).expect("set");
    assert!(info.obs_password_set && !info.wifi_psk_set);
    let failure = connection.set_credential(Credential::WifiPassphrase, "short".into()).expect_err("8..64");
    assert!(!failure.to_string().contains("short"), "a failure never carries the secret: {failure}");
    let info = connection.clear_credentials().expect("clear");
    assert!(!info.obs_password_set && !info.wifi_psk_set);
    drop(connection);
    pad.finish();
}

#[test]
fn export_needs_a_read_and_holds_the_document() {
    let scratch = Scratch::new("conn-export");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = Connection::new();
    connection.attach(pad.port()).expect("INFO");
    assert!(connection.export().is_err(), "nothing read yet");
    let doc = seed(&mut connection);
    connection.read().expect("read");
    let text = connection.export().expect("export");
    let exported: Value = serde_json::from_str(&text).expect("JSON");
    assert_eq!(exported["obs"], doc["obs"]);
    assert!(connection.status().is_ok(), "status reads unasked frames");
    drop(connection);
    pad.finish();
}

#[test]
fn every_command_without_a_pad_is_a_failure() {
    let mut connection = Connection::<std::io::Cursor<Vec<u8>>>::new();
    assert!(connection.info().is_err());
    assert!(connection.read().is_err());
    assert!(connection.write(minimal_document()).is_err());
    assert!(connection.set_credential(Credential::ObsPassword, "secret".into()).is_err());
    assert!(connection.clear_credentials().is_err());
    assert!(connection.status().is_err());
    assert!(connection.export().is_err());
}
