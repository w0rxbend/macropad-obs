// SPDX-License-Identifier: MIT
//! Spec 13 criteria 4 and 4c, end to end: this crate's codec drives padsim over its pty, and
//! padsim drives `tools/fake_obs.py` over TCP. Run by `just test` (`test-host` builds padsim).

mod common;

use common::{edited, minimal_document, seed, FakeObs, Pad, Scratch, WriteResult};
use obs_core::protocol::{RESULT_OK, RESULT_STALE_SEQ};
use serde_json::{json, Value};

const NEW_URL: &str = "ws://192.168.1.20:4455";

/// Criterion 4: read, change one key mapping and the URL, write; the next read gives the change
/// with `seq + 1`; a write on the old `seq` gets `stale_seq` and changes nothing.
#[test]
fn criterion_4_read_edit_write_and_stale() {
    let scratch = Scratch::new("criterion-4");
    let mut pad = Pad::start(&scratch.path("pad.nor"), None);
    let info = pad.info();
    let mut stored = minimal_document();
    stored["x_app_note"] = json!({"kept": "by the round trip"}); // a member no rule names
    seed(&mut pad, &info, &stored);

    let (seq, read) = pad.read_document();
    assert_eq!(seq, 1);
    let doc = edited(&info, &read, seq, |doc| {
        doc["keys"][0] = json!({"do": "scene", "uuid": "S_B", "label": "Screen"});
        doc["obs"]["url"] = json!(NEW_URL);
    });
    assert_eq!(pad.write_document(&info, &doc), WriteResult { code: RESULT_OK, seq: 2, path: String::new() });

    let (seq, read) = pad.read_document();
    assert_eq!(seq, 2, "the second read gives seq + 1");
    assert_eq!(read, doc.to_bytes(), "the second read gives the written bytes");
    let back: Value = serde_json::from_slice(&read).expect("JSON");
    assert_eq!(back["keys"][0], json!({"do": "scene", "uuid": "S_B", "label": "Screen"}));
    assert_eq!(back["obs"]["url"], json!(NEW_URL));
    assert_eq!(back["keys"][1], json!({"do": "none"}), "the other keys are as they were");
    assert_eq!(back["x_app_note"], stored["x_app_note"], "the unknown member is kept");

    let stale = edited(&info, &read, 1, |doc| doc["keys"][0] = json!({"do": "toggle_record"}));
    let refused = pad.write_document(&info, &stale);
    assert_eq!((refused.code, refused.seq), (RESULT_STALE_SEQ, 2), "a write on seq 1 gets stale_seq");
    assert_eq!(pad.read_document(), (2, doc.to_bytes()), "the stale write changed nothing");
    pad.finish();
}

const BEFORE_WRITE: [&str; 3] = [
    r#"{"requestType":"ToggleStream"}"#,
    r#"{"requestType":"SetInputVolume","requestData":{"inputUuid":"U_A","inputVolumeDb":-5}}"#,
    r#"{"requestType":"ToggleInputMute","requestData":{"inputUuid":"U_A"}}"#,
];

/// Spec 13 criterion 4c, word for word.
const AFTER_WRITE: [&str; 3] = [
    r#"{"requestType":"ToggleRecord"}"#,
    r#"{"requestType":"SetInputVolume","requestData":{"inputUuid":"U_B","inputVolumeDb":-18}}"#,
    r#"{"requestType":"ToggleInputMute","requestData":{"inputUuid":"U_B"}}"#,
];

/// One press of button 1, one clockwise detent and one push of knob 0, each settled before the
/// next. Returns the request lines they added to the log.
fn press_turn_push(pad: &mut Pad, obs: &FakeObs) -> Vec<String> {
    pad.wait_idle();
    let mark = obs.requests_settled(0).len();
    for (count, event) in ["button 1", "knob 0 1", "knob 0 push"].into_iter().enumerate() {
        pad.command(event);
        pad.wait_idle();
        obs.requests_settled(mark + count + 1);
    }
    obs.requests_settled(mark + 3).split_off(mark)
}

/// Criterion 4c: the app remaps button 1 and knob 0, writes, and the same three events then give
/// exactly the new requests. Before the write they give the old ones (G3).
#[test]
fn criterion_4c_input_remap_round_trip() {
    let scratch = Scratch::new("criterion-4c");
    let obs = FakeObs::start(scratch.path("requests.log"));
    let mut pad = Pad::start(&scratch.path("pad.nor"), Some(obs.port));
    let info = pad.info();
    pad.wait_obs_up();
    let mut old = minimal_document();
    old["buttons"][1] = json!({"do": "toggle_stream"});
    old["knobs"][0] = json!({"input": {"uuid": "U_A", "label": "Mic"}, "step_db": 1, "push": {"do": "toggle_mute"}});
    seed(&mut pad, &info, &old);

    assert_eq!(press_turn_push(&mut pad, &obs), BEFORE_WRITE, "the old map gives the old requests");

    let (seq, read) = pad.read_document();
    let doc = edited(&info, &read, seq, |doc| {
        doc["buttons"][1] = json!({"do": "toggle_record"});
        doc["knobs"][0] =
            json!({"input": {"uuid": "U_B", "label": "Desktop"}, "step_db": 2, "push": {"do": "toggle_mute"}});
    });
    let mark = obs.requests_settled(0).len();
    assert_eq!(pad.write_document(&info, &doc), WriteResult { code: RESULT_OK, seq: seq + 1, path: String::new() });

    assert_eq!(press_turn_push(&mut pad, &obs), AFTER_WRITE, "criterion 4c request log");
    let since_write = obs.requests_settled(mark).split_off(mark);
    let named_u_a: Vec<_> = since_write.iter().filter(|line| line.contains("\"U_A\"")).collect();
    assert!(named_u_a.is_empty(), "no request after the write names U_A: {named_u_a:#?}");
    pad.finish();
}
