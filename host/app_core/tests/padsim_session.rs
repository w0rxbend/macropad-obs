// SPDX-License-Identifier: MIT
//! The config session against padsim: `INFO`, read until total, write with `base_seq`, and the
//! diff on `stale_seq` (spec 8.2 flow, task 3.2). Run by `just test` (`test-host` builds padsim).

mod common;

use app_core::{Change, Document, Info, Session, Stored, Written};
use common::{minimal_document, Padsim, Scratch};
use serde_json::{json, Value};

const NEW_URL: &str = "ws://192.168.1.20:4455";

fn parse(info: &Info, json: &Value) -> Document {
    let schemas = u64::from(info.schema_min)..=u64::from(info.schema_max);
    Document::parse(json.to_string().as_bytes(), schemas).expect("the test document is valid")
}

/// Writes `json` as the first document of an empty pad and checks it is stored as seq 1.
fn seed<P: std::io::Read + std::io::Write>(session: &mut Session<P>, json: &Value) {
    assert_eq!(session.read().expect("read"), Stored { seq: 0, bytes: Vec::new() }, "a fresh pad holds nothing");
    let doc = parse(session.info(), json);
    assert_eq!(session.write(&doc).expect("write"), Written::Saved { seq: 1 });
}

#[test]
fn info_comes_first_and_names_the_pad() {
    let scratch = Scratch::new("info");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let session = Session::start(pad.port()).expect("INFO");
    let info = session.info();
    assert_eq!((info.keys, info.buttons, info.knobs), (9, 4, 3));
    assert!(info.schema_min <= info.schema_max);
    drop(session);
    pad.finish();
}

#[test]
fn round_trip_keeps_unknown_fields() {
    let scratch = Scratch::new("round-trip");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut session = Session::start(pad.port()).expect("INFO");
    let mut stored = minimal_document();
    stored["x_app_note"] = json!({"kept": "by the round trip", "list": [1, 2, 3]});
    stored["obs"]["x_tag"] = json!("nested unknown");
    seed(&mut session, &stored);

    let read = session.read().expect("read");
    assert_eq!(read.seq, 1);
    assert!(read.bytes.len() > obs_core::protocol::CFG_DATA_MAX, "the read takes more than one CFG_DATA");
    let doc = read
        .edit(session.info(), |doc| {
            doc["keys"][0] = json!({"do": "scene", "uuid": "S_B", "label": "Screen"});
            doc["obs"]["url"] = json!(NEW_URL);
        })
        .expect("the edit is valid");
    assert_eq!(doc.seq(), 1, "the edit carries the read seq as base_seq");
    assert_eq!(session.write(&doc).expect("write"), Written::Saved { seq: 2 });

    let back = session.read().expect("read");
    assert_eq!(back.seq, 2);
    assert_eq!(back.bytes, doc.to_bytes(), "the pad stores the bytes the app wrote");
    let back: Value = serde_json::from_slice(&back.bytes).expect("JSON");
    assert_eq!(back["x_app_note"], stored["x_app_note"], "an unknown member is kept");
    assert_eq!(back["obs"]["x_tag"], stored["obs"]["x_tag"], "a nested unknown member is kept");
    assert_eq!(back["obs"]["url"], json!(NEW_URL));
    assert_eq!(back["keys"][1], json!({"do": "none"}), "the other keys are as they were");
    drop(session);
    pad.finish();
}

#[test]
fn a_stale_write_changes_nothing_and_shows_the_diff() {
    let scratch = Scratch::new("stale");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut session = Session::start(pad.port()).expect("INFO");
    seed(&mut session, &minimal_document());
    let first = session.read().expect("read");

    let other = first.edit(session.info(), |doc| doc["obs"]["url"] = json!(NEW_URL)).expect("valid");
    assert_eq!(session.write(&other).expect("write"), Written::Saved { seq: 2 }, "another writer commits first");

    let mine = first.edit(session.info(), |doc| doc["keys"][3] = json!({"do": "toggle_record"})).expect("valid");
    let Written::Stale { pad: now, changes } = session.write(&mine).expect("write") else {
        panic!("a write on seq 1 after seq 2 is stale");
    };
    assert_eq!(now, Stored { seq: 2, bytes: other.to_bytes() }, "the stale result carries the re-read");
    assert_eq!(
        changes,
        [
            Change { path: "keys[3].do".into(), pad: Some(json!("none")), app: Some(json!("toggle_record")) },
            Change { path: "obs.url".into(), pad: Some(json!(NEW_URL)), app: Some(json!("ws://10.0.0.2")) },
        ],
        "the diff names each differing leaf and leaves seq out"
    );
    assert_eq!(session.read().expect("read"), now, "the stale write changed nothing");
    drop(session);
    pad.finish();
}
