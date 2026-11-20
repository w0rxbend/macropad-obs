// SPDX-License-Identifier: MIT
//! The display and Wi-Fi pages' commands (task 3.8) against padsim: the secret fields never fill
//! from a read and are empty after a write, whatever its outcome; a layout edit previews, writes
//! and reads back; an overlap previews as `invalid` and writes nothing.

mod common;

use app_core::forms::{Network, Secrets};
use app_core::preview::{MAIN_BYTES, STRIP_BYTES};
use app_core::{Connection, Saved};
use common::{minimal_document, Padsim, Scratch};
use serde_json::{json, Value};

const PASSPHRASE: &str = "correct horse battery";
const PASSWORD: &str = "hunter22-obs";

fn secrets(wifi_passphrase: &str, obs_password: &str) -> Secrets {
    serde_json::from_value(json!({"wifi_passphrase": wifi_passphrase, "obs_password": obs_password})).expect("form")
}

/// Every string member anywhere in `json`, to look for a secret in what the window gets.
fn strings(json: &Value) -> Vec<String> {
    match json {
        Value::String(text) => vec![text.clone()],
        Value::Array(items) => items.iter().flat_map(strings).collect(),
        Value::Object(members) => {
            members.iter().flat_map(|(name, item)| [vec![name.clone()], strings(item)].concat()).collect()
        }
        _ => Vec::new(),
    }
}

fn holds_a_secret(json: &Value) -> bool {
    strings(json).iter().any(|text| text.contains(PASSPHRASE) || text.contains(PASSWORD))
}

fn seeded(pad: &Padsim) -> Connection<serialport::TTYPort> {
    let mut connection = Connection::new();
    connection.attach(pad.port()).expect("INFO");
    connection.read().expect("read");
    assert_eq!(connection.write(minimal_document()).expect("seed"), Saved::Saved { seq: 1 });
    connection
}

#[test]
fn secret_fields_never_fill_from_a_read_and_are_empty_after_a_write() {
    let scratch = Scratch::new("pages-secrets");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = seeded(&pad);

    let page = serde_json::to_value(connection.read_network().expect("read")).expect("page serialises");
    assert_eq!(page, json!({"ssid": "", "auth_mode": "none", "wifi_psk_set": false, "obs_password_set": false}));

    let network = Network { ssid: "studio".into(), auth_mode: "stored".into() };
    let mut form = secrets(PASSPHRASE, PASSWORD);
    let saved = connection.write_network(&network, &mut form).expect("write");
    assert!(form.is_empty(), "the form is empty after the write");
    let saved = serde_json::to_value(saved).expect("answer serialises");
    assert_eq!(saved["saved"], json!({"outcome": "saved", "seq": 2}));
    assert_eq!(
        saved["page"],
        json!({"ssid": "studio", "auth_mode": "stored", "wifi_psk_set": true, "obs_password_set": true})
    );
    assert!(!holds_a_secret(&saved));

    let read = serde_json::to_value(connection.read_network().expect("read")).expect("page serialises");
    assert_eq!(read, saved["page"], "a read gives the flags, never a secret");
    assert!(!holds_a_secret(&serde_json::to_value(connection.read().expect("read")).expect("config")));
    assert!(!connection.export().expect("export").contains(PASSWORD));
    pad.finish();
}

#[test]
fn empty_secret_fields_leave_the_pad_s_secrets_as_they_are() {
    let scratch = Scratch::new("pages-keep");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = seeded(&pad);
    let network = Network { ssid: "studio".into(), auth_mode: "stored".into() };
    connection.write_network(&network, &mut secrets("", PASSWORD)).expect("password only");
    let page = connection.write_network(&network, &mut secrets("", "")).expect("no secret").page;
    assert!(page.obs_password_set && !page.wifi_psk_set);
    pad.finish();
}

#[test]
fn a_refused_document_sends_no_secret_and_still_empties_the_form() {
    let scratch = Scratch::new("pages-refused");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = seeded(&pad);
    let long = Network { ssid: "s".repeat(33), auth_mode: "stored".into() };
    let mut form = secrets(PASSPHRASE, PASSWORD);
    let refused = connection.write_network(&long, &mut form).expect_err("33-byte SSID");
    assert_eq!(refused.to_string(), "invalid value at `wifi.ssid`");
    assert!(form.is_empty());
    let info = connection.info().expect("INFO");
    assert!(!info.wifi_psk_set && !info.obs_password_set, "nothing was sent");
    pad.finish();
}

#[test]
fn a_refused_secret_empties_the_form_and_sends_nothing_after_it() {
    let scratch = Scratch::new("pages-bad-secret");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = seeded(&pad);
    let network = Network { ssid: "studio".into(), auth_mode: "stored".into() };
    let mut form = secrets("short", PASSWORD);
    assert!(connection.write_network(&network, &mut form).is_err(), "a 5-byte passphrase is refused");
    assert!(form.is_empty());
    assert!(!connection.info().expect("INFO").obs_password_set, "the password after it was not sent");
    pad.finish();
}

/// A fresh pad holds no document: both pages start from the built-in one, and a first write
/// goes on `seq` 0.
#[test]
fn a_fresh_pad_gives_both_pages_and_takes_a_first_layout() {
    let scratch = Scratch::new("pages-fresh");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = Connection::new();
    connection.attach(pad.port()).expect("INFO");
    let page = serde_json::to_value(connection.read_network().expect("network page")).expect("page serialises");
    assert_eq!(page, json!({"ssid": "", "auth_mode": "none", "wifi_psk_set": false, "obs_password_set": false}));
    let mut layout = connection.read_layout().expect("layout");
    layout.main_display.push(json!({"kind": "text", "x": 0, "y": 0, "w": 320, "h": 40, "text": "Test 1"}));
    connection.preview(&layout).expect("preview");
    assert_eq!(connection.write_layout(&layout).expect("write"), Saved::Saved { seq: 1 });
    assert_eq!(connection.read_layout().expect("layout"), layout);
    pad.finish();
}

#[test]
fn a_layout_edit_previews_writes_and_reads_back() {
    let scratch = Scratch::new("pages-layout");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = seeded(&pad);
    let mut layout = connection.read_layout().expect("layout");
    assert!(layout.main_display.is_empty() && layout.strip_display.is_empty());

    let blank = connection.preview(&layout).expect("preview");
    layout.main_display.push(json!({"kind": "text", "x": 0, "y": 0, "w": 320, "h": 40, "text": "Test 1"}));
    let drawn = connection.preview(&layout).expect("preview");
    assert_eq!((drawn.main.len(), drawn.strip.len()), (MAIN_BYTES, STRIP_BYTES));
    assert_ne!(drawn.main, blank.main, "the text widget is drawn");
    assert_eq!(drawn.strip, blank.strip, "the strip did not change");
    assert_eq!(connection.read().expect("read").seq, 1, "a preview writes nothing");

    assert_eq!(connection.write_layout(&layout).expect("write"), Saved::Saved { seq: 2 });
    assert_eq!(connection.read_layout().expect("layout"), layout);
    pad.finish();
}

#[test]
fn an_overlap_previews_as_invalid_and_writes_nothing() {
    let scratch = Scratch::new("pages-overlap");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = seeded(&pad);
    let mut layout = connection.read_layout().expect("layout");
    layout.main_display.push(json!({"kind": "text", "x": 0, "y": 0, "w": 100, "h": 40, "text": "a"}));
    layout.main_display.push(json!({"kind": "text", "x": 50, "y": 20, "w": 100, "h": 40, "text": "b"}));
    let refused = connection.preview(&layout).expect_err("overlap");
    assert_eq!(refused.to_string(), "invalid value at `main_display.widgets[1]`");
    assert!(connection.write_layout(&layout).is_err());
    assert_eq!(connection.read().expect("read").seq, 1);
    pad.finish();
}
