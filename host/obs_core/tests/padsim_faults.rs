// SPDX-License-Identifier: MIT
//! Spec 13 criteria 5, 8 and 9, end to end: power cuts during `CFG_COMMIT`, a 500-scene OBS, and
//! the strip line of each failure. This crate's codec drives padsim over its pty, and padsim
//! drives `tools/fake_obs.py` over TCP. Run by `just test` (`test-host` builds padsim).

mod common;

use std::net::TcpListener;
use std::path::Path;
use std::thread;
use std::time::{Duration, Instant};

use common::{edited, minimal_document, seed, FakeObs, Pad, Scratch, WriteResult, TIMEOUT};
use obs_core::document::Document;
use obs_core::protocol::{Info, Message, Secret, CREDENTIAL_OBS_PASSWORD, CRED_OK, LIST_SCENES, RESULT_OK, UUID_LEN};
use serde_json::json;

const KILLS: u32 = 50;
/// A commit programs the body, then the header (`firmware/core/store.c`).
const PROGRAM_CALLS_PER_COMMIT: u32 = 2;
/// A run finishes up to this many commits less one, then dies in the next.
const COMMITS_PER_RUN: u32 = 3;

/// The stored `seq` and bytes, as `CFG_READ` serves them.
type Stored = (u32, Vec<u8>);

/// The next document of the run: key 0 carries the write's number, so each one is new.
fn generation(info: &Info, (seq, bytes): &Stored, number: u32) -> Document {
    edited(info, bytes, *seq, |doc| doc["keys"][0] = json!({"do": "toggle_record", "label": format!("gen {number}")}))
}

/// Boots the image and checks the pad runs the old or the new document. Returns what it serves.
fn boot_check(pad: &mut Pad, dir: &Path, old: &Stored, new: Option<&Stored>, kill: u32) -> Stored {
    let booted = pad.read_document();
    assert!(
        &booted == old || Some(&booted) == new,
        "after {kill} kills the pad serves seq {}: neither the old seq {} nor the new one",
        booted.0,
        old.0
    );
    assert_eq!(pad.strip_line(dir), "", "after {kill} kills the pad runs the document, not its factory defaults");
    booted
}

/// Criterion 5: 50 kills, each when a flash program call of `CFG_COMMIT` begins (the body or the
/// header, of the first, second or third commit of a run). Every next boot runs the old or the
/// new document.
#[test]
fn criterion_5_cut_during_commit_boots_old_or_new() {
    let scratch = Scratch::new("criterion-5");
    let nor = scratch.path("pad.nor");
    let dir = scratch.path("");
    let mut pad = Pad::start(&nor, None);
    let info = pad.info();
    seed(&mut pad, &info, &minimal_document());
    let mut old = pad.read_document();
    pad.finish();

    let mut new = None;
    let mut written = 0;
    for kill in 0..KILLS {
        let cut = 1 + kill % (PROGRAM_CALLS_PER_COMMIT * COMMITS_PER_RUN);
        let mut pad = Pad::start_with(&nor, None, Some(cut));
        let mut current = boot_check(&mut pad, &dir, &old, new.as_ref(), kill);
        loop {
            written += 1;
            let doc = generation(&info, &current, written);
            let next = (current.0 + 1, doc.to_bytes());
            let Some(result) = pad.write_document_or_cut(&info, &doc) else {
                (old, new) = (current, Some(next));
                break;
            };
            assert_eq!(result, WriteResult { code: RESULT_OK, seq: next.0, path: String::new() });
            current = next;
        }
        pad.wait_killed();
    }

    let mut pad = Pad::start(&nor, None);
    boot_check(&mut pad, &dir, &old, new.as_ref(), KILLS);
    pad.finish();
}

const SCENES: u16 = 500;

/// The 16 UUID bytes of `OBS_ITEM`, in the order of the text form.
fn uuid_bytes(text: &str) -> [u8; UUID_LEN] {
    let hex: String = text.chars().filter(|c| *c != '-').collect();
    let mut bytes = [0; UUID_LEN];
    for (index, byte) in bytes.iter_mut().enumerate() {
        *byte = u8::from_str_radix(&hex[2 * index..2 * index + 2], 16).expect("hex UUID");
    }
    bytes
}

/// Criterion 8: `fake_obs.py --scenes 500` (a 75 kB `GetSceneList` reply, throttled so it arrives
/// in pieces) loads with no reset, and all 500 come back over `OBS_LIST` in OBS order.
#[test]
fn criterion_8_500_scenes_load_and_list() {
    let scratch = Scratch::new("criterion-8");
    let flags = ["--scenes", "500", "--throttle-bytes-per-s", "250000"];
    let obs = FakeObs::start_with(scratch.path("requests.log"), &flags);
    let mut pad = Pad::start(&scratch.path("pad.nor"), Some(obs.port));
    pad.wait_obs_up();
    pad.wait_idle();

    for index in 0..SCENES {
        let Message::ObsItem { list, index: at, total, uuid, name } =
            pad.ask(&Message::ObsList { list: LIST_SCENES, index })
        else {
            panic!("OBS_LIST gives OBS_ITEM");
        };
        assert_eq!((list, at, total), (LIST_SCENES, index, SCENES), "scene {index}");
        // `with_scene_collection` in tools/fake_obs.py names them.
        assert_eq!(uuid, uuid_bytes(&format!("{index:08x}-0000-4000-8000-000000000000")), "scene {index}");
        let full = format!("{:-<64}", format!("Scene {index:03} "));
        let name = String::from_utf8(name).expect("the name is UTF-8");
        assert!(name.starts_with(&format!("Scene {index:03} ")) && full.starts_with(&name), "scene {index}: {name:?}");
    }
    assert_eq!(pad.info().schema_min, 1, "the pad still answers INFO");
    pad.finish();
}

const POLL: Duration = Duration::from_millis(20);

/// The strip line once it is `want`, or the last one seen when `TIMEOUT` runs out first.
fn line_within_timeout(pad: &mut Pad, dir: &Path, want: &str) -> String {
    let deadline = Instant::now() + TIMEOUT;
    loop {
        pad.wait_idle();
        let line = pad.strip_line(dir);
        if line == want || Instant::now() >= deadline {
            return line;
        }
        thread::sleep(POLL);
    }
}

/// Criterion 9, the pad's own failures: `wifi` events for bad key, no AP and no SSID, and the
/// factory defaults of a pad with no document. No SSID comes last: the pad then takes no event
/// until an SSID is set.
#[test]
fn criterion_9_wifi_and_factory_strip_lines() {
    let scratch = Scratch::new("criterion-9-wifi");
    let dir = scratch.path("");
    let mut pad = Pad::start(&scratch.path("pad.nor"), None);
    let expect = |pad: &mut Pad, want: &str, after: &str| {
        assert_eq!(line_within_timeout(pad, &dir, want), want, "{after}");
    };
    expect(&mut pad, "Factory config", "no document");
    for (event, want) in [("bad_key", "Wrong Wi-Fi key"), ("no_ap", "Wi-Fi not found"), ("up", "Factory config")] {
        pad.command(&format!("wifi {event}"));
        expect(&mut pad, want, event);
    }
    let info = pad.info();
    seed(&mut pad, &info, &minimal_document());
    expect(&mut pad, "", "a stored document leaves the line empty");
    pad.command("wifi no_ssid");
    expect(&mut pad, "Wi-Fi not set", "no_ssid");
    pad.finish();
}

/// A loopback port with no listener.
fn closed_port() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").expect("a free loopback port");
    listener.local_addr().expect("its address").port()
}

#[test]
fn criterion_9_obs_unreachable_strip_line() {
    let scratch = Scratch::new("criterion-9-unreachable");
    let mut pad = Pad::start(&scratch.path("pad.nor"), Some(closed_port()));
    assert_eq!(line_within_timeout(&mut pad, &scratch.path(""), "OBS unreachable"), "OBS unreachable");
    pad.finish();
}

#[test]
fn criterion_9_obs_too_old_strip_line() {
    let scratch = Scratch::new("criterion-9-too-old");
    let obs = FakeObs::start_with(scratch.path("requests.log"), &["--obs-websocket-version", "5.3.0"]);
    let mut pad = Pad::start(&scratch.path("pad.nor"), Some(obs.port));
    let want = "OBS too old, need 30.1";
    assert_eq!(line_within_timeout(&mut pad, &scratch.path(""), want), want);
    pad.finish();
}

/// A test string on both ends, never a real password.
const PAD_PASSWORD: &str = "pad-test-password";
const OBS_PASSWORD: &str = "obs-test-password";

/// A stored password OBS refuses gives the bad-password line; no stored password gives its own.
#[test]
fn criterion_9_bad_obs_password_strip_lines() {
    let scratch = Scratch::new("criterion-9-password");
    let nor = scratch.path("pad.nor");
    let dir = scratch.path("");
    let obs = FakeObs::start_with(scratch.path("requests.log"), &["--password", OBS_PASSWORD]);

    let mut pad = Pad::start(&nor, Some(obs.port));
    let unset = "OBS password not set";
    assert_eq!(line_within_timeout(&mut pad, &dir, unset), unset);
    let set = Message::SetCredential { kind: CREDENTIAL_OBS_PASSWORD, secret: Secret(PAD_PASSWORD.into()) };
    assert_eq!(pad.ask(&set), Message::CredStatus { code: CRED_OK });
    pad.finish();

    let mut pad = Pad::start(&nor, Some(obs.port));
    let wrong = "Wrong OBS password";
    assert_eq!(line_within_timeout(&mut pad, &dir, wrong), wrong);
    pad.finish();
}
