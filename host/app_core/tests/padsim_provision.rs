// SPDX-License-Identifier: MIT
//! Provisioning and export against padsim (spec 8.2, task 3.3): `SET_CREDENTIAL` from a `Secret`
//! that is cleared after the write, `CLEAR_CREDENTIALS`, the Wi-Fi `STATUS`, and an export with no
//! secret. A tap records the link in both directions for criterion 12, host side.

mod common;

use std::cell::RefCell;
use std::io::{Read, Write};
use std::rc::Rc;
use std::time::{Duration, Instant};

use app_core::{export, Credential, Document, Secret, Session, SessionError, Status, Written};
use common::{frames, minimal_document, Capture, Padsim, Scratch, Tap};
use obs_core::protocol::{
    self, CREDENTIAL_OBS_PASSWORD, CREDENTIAL_WIFI_PASSPHRASE, CRED_BAD_LEN, CRED_BAD_VALUE, SET_CREDENTIAL,
    WIFI_BAD_KEY, WIFI_UP,
};
use serde_json::{json, Value};

// No 4-byte run of either occurs in a document, a fixed INFO field or a frame header.
const OBS_PASSWORD: &[u8] = b"Zq7!Xv#9Lm@2Pp";
const WIFI_PSK: &[u8] = b"Kj4$Rt8&Wn5*Hy";
// The shortest run of secret bytes the capture check looks for (as `firmware/test/test_store.c`).
const SECRET_RUN: usize = 4;
const STATUS_WAIT: Duration = Duration::from_secs(5);

fn holds_secret_run(bytes: &[u8]) -> bool {
    [OBS_PASSWORD, WIFI_PSK]
        .iter()
        .any(|secret| secret.windows(SECRET_RUN).any(|run| bytes.windows(SECRET_RUN).any(|at| at == run)))
}

fn wait_for_wifi<P: Read + Write>(session: &mut Session<P>, wifi_state: u8) -> Status {
    let deadline = Instant::now() + STATUS_WAIT;
    loop {
        session.listen(Duration::from_millis(50)).expect("the link reads");
        match session.status() {
            Some(status) if status.wifi_state == wifi_state => return *status,
            _ => assert!(Instant::now() < deadline, "no STATUS with Wi-Fi state {wifi_state}"),
        }
    }
}

fn seed<P: Read + Write>(session: &mut Session<P>) {
    let mut json = minimal_document();
    json["wifi"]["ssid"] = json!("studio");
    json["obs"]["auth_mode"] = json!("stored");
    let schemas = u64::from(session.info().schema_min)..=u64::from(session.info().schema_max);
    let doc = Document::parse(json.to_string().as_bytes(), schemas).expect("the test document is valid");
    assert_eq!(session.write(&doc).expect("write"), Written::Saved { seq: 1 });
}

#[test]
fn credentials_cross_the_link_only_in_set_credential() {
    let scratch = Scratch::new("provision");
    let mut pad = Padsim::start(&scratch.path("pad.nor"));
    let capture = Rc::new(RefCell::new(Capture::default()));
    let mut session = Session::start(Tap { port: pad.port(), capture: Rc::clone(&capture) }).expect("INFO");
    assert!(!session.info().obs_password_set && !session.info().wifi_psk_set, "a fresh pad holds no secret");
    seed(&mut session);

    let mut field = Secret(OBS_PASSWORD.to_vec());
    session.set_credential(Credential::ObsPassword, &mut field).expect("the pad stores the password");
    assert!(field.0.is_empty(), "the field is cleared after the write");
    let mut field = Secret(WIFI_PSK.to_vec());
    session.set_credential(Credential::WifiPassphrase, &mut field).expect("the pad stores the passphrase");
    assert!(field.0.is_empty(), "the field is cleared after the write");
    assert!(session.info().obs_password_set && session.info().wifi_psk_set, "INFO shows both set");

    let exported = export(&session.read().expect("read")).expect("the stored document exports");
    let exported_json: Value = serde_json::from_slice(&exported).expect("the export is JSON");
    assert_eq!(exported_json["wifi"]["ssid"], json!("studio"), "the export is the stored document");
    assert!(!holds_secret_run(&exported), "the export has no secret");

    pad.command("wifi bad_key");
    assert_eq!(
        wait_for_wifi(&mut session, WIFI_BAD_KEY),
        Status { obs_state: 0, wifi_state: 2, rssi_dbm: 0, ip: [0; 4] }
    );
    pad.command("wifi up");
    let up = wait_for_wifi(&mut session, WIFI_UP);
    assert_eq!((up.rssi_dbm, up.ip), (-50, [127, 0, 0, 1]), "padsim's fake radio");

    session.clear_credentials().expect("the pad erases both");
    assert!(!session.info().obs_password_set && !session.info().wifi_psk_set, "INFO shows both cleared");
    drop(session);
    pad.finish();

    let capture = capture.borrow();
    assert!(!holds_secret_run(&capture.to_app), "no device-to-host byte holds a secret run");
    let mut carried = Vec::new();
    for frame in frames(&capture.to_pad) {
        if frame.kind == SET_CREDENTIAL {
            carried.push(frame.payload);
        } else {
            let bytes = protocol::encode(&frame).expect("frame fits");
            assert!(!holds_secret_run(&bytes), "a host-to-device 0x{:02X} frame holds a secret run", frame.kind);
        }
    }
    assert_eq!(
        carried,
        [
            [&[CREDENTIAL_OBS_PASSWORD][..], OBS_PASSWORD].concat(),
            [&[CREDENTIAL_WIFI_PASSPHRASE][..], WIFI_PSK].concat()
        ],
        "each secret went once, in its SET_CREDENTIAL payload"
    );
    frames(&capture.to_app);
}

#[test]
fn a_refused_credential_is_cleared_and_never_sent() {
    let scratch = Scratch::new("refused");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let capture = Rc::new(RefCell::new(Capture::default()));
    let mut session = Session::start(Tap { port: pad.port(), capture: Rc::clone(&capture) }).expect("INFO");

    for (secret, code) in
        [(&b"Kj4$Rt8"[..], CRED_BAD_LEN), (&b"Kj4$Rt8&\x7f"[..], CRED_BAD_VALUE), (&b""[..], CRED_BAD_LEN)]
    {
        let mut field = Secret(secret.to_vec());
        let refused = session.set_credential(Credential::WifiPassphrase, &mut field);
        assert!(
            matches!(refused, Err(SessionError::CredentialRefused { code: got }) if got == code),
            "{secret:?} gets code {code}"
        );
        assert!(field.0.is_empty(), "the field is cleared after a refusal too");
    }
    assert!(!session.info().wifi_psk_set);
    drop(session);
    pad.finish();
    let sent = frames(&capture.borrow().to_pad);
    assert!(sent.iter().all(|frame| frame.kind != SET_CREDENTIAL), "the app checks before it sends");
}

#[test]
fn an_empty_pad_has_nothing_to_export() {
    let empty = app_core::Stored { seq: 0, bytes: Vec::new() };
    assert!(export(&empty).is_err());
}
