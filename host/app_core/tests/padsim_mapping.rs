// SPDX-License-Identifier: MIT
//! The mapping editor's commands (task 3.7) against padsim: the OBS picker over `OBS_LIST`
//! (criterion 8, with `tools/fake_obs.py --scenes 500`), and a mapping edit the pad's own
//! validator takes.

mod common;

use std::thread;
use std::time::{Duration, Instant};

use app_core::forms::{Action, ObsList, Reference};
use app_core::{Config, Connection, Saved};
use common::{minimal_document, FakeObs, Padsim, Scratch};
use obs_core::protocol::OBS_UP;
use serde_json::{json, Value};

const TIMEOUT: Duration = Duration::from_secs(10);
const POLL: Duration = Duration::from_millis(50);
const SCENES: usize = 500;

/// Criterion 8: all 500 scenes of the pad's OBS session reach the picker, in OBS order, each a
/// reference the document takes.
#[test]
fn criterion_8_the_picker_lists_500_scenes() {
    let scratch = Scratch::new("mapping-500");
    let flags = ["--scenes", "500", "--throttle-bytes-per-s", "250000"];
    let obs = FakeObs::start(&scratch.path("requests.log"), &flags);
    let pad = Padsim::start_with_obs(&scratch.path("pad.nor"), obs.port);
    let mut connection = Connection::new();
    connection.attach(pad.port()).expect("INFO");

    let deadline = Instant::now() + TIMEOUT;
    while connection.status().expect("status").map(|status| status.obs_state) != Some(OBS_UP) {
        assert!(Instant::now() < deadline, "the pad's OBS session is up within {TIMEOUT:?}");
    }
    // `Identified` comes before the scene list is read; the list may also change mid-read.
    let scenes = loop {
        match connection.obs_list(ObsList::Scenes) {
            Ok(scenes) if scenes.len() == SCENES => break scenes,
            _ => assert!(Instant::now() < deadline, "500 scenes within {TIMEOUT:?}"),
        }
        thread::sleep(POLL);
    };
    for (index, scene) in scenes.iter().enumerate() {
        // `with_scene_collection` in tools/fake_obs.py names them.
        assert_eq!(scene.uuid, format!("{index:08x}-0000-4000-8000-000000000000"), "scene {index}");
        assert!(scene.label.starts_with(&format!("Scene {index:03} ")), "scene {index}: {:?}", scene.label);
        assert!(scene.label.len() <= 48, "scene {index}: a label holds 48 bytes at most");
    }
    assert_eq!(connection.read().expect("the pad still answers").seq, 0);
    pad.finish();
}

#[test]
fn with_no_obs_the_picker_is_empty() {
    let scratch = Scratch::new("mapping-no-obs");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = Connection::new();
    connection.attach(pad.port()).expect("INFO");
    assert_eq!(connection.obs_list(ObsList::Inputs).expect("list"), []);
    pad.finish();
}

/// Criterion 4, the mapping part: one key and the URL change, the pad's validator takes the
/// write, and a second read returns exactly that.
#[test]
fn a_mapping_edit_is_written_and_read_back() {
    let scratch = Scratch::new("mapping-edit");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = Connection::new();
    connection.attach(pad.port()).expect("INFO");
    assert!(connection.read_mapping().is_err(), "a fresh pad holds no mapping");
    assert_eq!(connection.write(minimal_document()).expect("seed"), Saved::Saved { seq: 1 });

    let mut mapping = connection.read_mapping().expect("mapping");
    mapping.url = "ws://192.168.1.20:4455".into();
    let cam = Reference { uuid: "0b0e6b1c-7f0a-4a55-9a43-1f2d3c4b5a69".into(), label: "Cam".into() };
    mapping.keys[0] = Action { act: "scene".into(), target: Some(cam) };
    assert_eq!(connection.write_mapping(&mapping).expect("write"), Saved::Saved { seq: 2 });

    let mut want = minimal_document();
    want["seq"] = json!(1);
    want["obs"]["url"] = json!("ws://192.168.1.20:4455");
    want["keys"][0] = json!({"do": "scene", "uuid": "0b0e6b1c-7f0a-4a55-9a43-1f2d3c4b5a69", "label": "Cam"});
    assert_eq!(connection.read().expect("read"), Config { seq: 2, document: want });
    assert_eq!(connection.read_mapping().expect("mapping"), mapping);
    pad.finish();
}

#[test]
fn a_mapping_the_pad_refuses_names_the_bad_path_and_stores_nothing() {
    let scratch = Scratch::new("mapping-refused");
    let pad = Padsim::start(&scratch.path("pad.nor"));
    let mut connection = Connection::new();
    connection.attach(pad.port()).expect("INFO");
    connection.read().expect("read");
    connection.write(minimal_document()).expect("seed");
    let mut mapping = connection.read_mapping().expect("mapping");
    mapping.url = "ws://127.0.0.1:4455".into();
    let refused = connection.write_mapping(&mapping).expect_err("loopback");
    assert_eq!(refused.to_string(), "invalid value at `obs.url`");
    assert_eq!(connection.read().expect("read").document["obs"]["url"], Value::from("ws://10.0.0.2"));
    pad.finish();
}
