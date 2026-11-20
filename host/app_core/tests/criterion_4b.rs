// SPDX-License-Identifier: MIT
//! Criterion 4b (spec 13), task 3.4: the display layout round trip. padsim runs against
//! `tools/fake_obs.py` serving `tools/fixtures/ui_state.json`. The app core edits one `text`
//! widget and one `strip` widget, renders its preview from the same document and the same state
//! file, writes, and the padsim dumps equal the preview byte for byte. An overlapping layout gets
//! `RESULT invalid` from the pad itself and leaves the frames as they were. Run by `just test`.

mod common;

use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{self, Receiver};
use std::thread;
use std::time::{Duration, Instant};

use app_core::preview::{self, Frames, SampleState, MAIN_BYTES, STRIP_BYTES};
use app_core::{Document, Rejected, Session, Stored, Written};
use common::{minimal_document, repo_root, Scratch};
use obs_core::protocol::{self, Message, Pulled, OBS_UP, RESULT_INVALID, RESULT_OK};
use obs_core::LinkRx;
use serde_json::{json, Value};
use serialport::TTYPort;

const TIMEOUT: Duration = Duration::from_secs(10);
const READ_TIMEOUT: Duration = Duration::from_millis(20);
const MAIN_WIDTH: usize = 320;
const STRIP_WIDTH: usize = 142;

/// The `text` widget the test edits: `main_display.widgets[1]`.
const TEXT_RECT: Rect = Rect { x: 0, y: 40, w: 320, h: 40 };
/// The knob 1 `strip` widget the test edits: `strip_display.widgets[1]`.
const STRIP_RECT: Rect = Rect { x: 0, y: 142, w: 142, h: 140 };

#[derive(Clone, Copy, Debug)]
struct Rect {
    x: usize,
    y: usize,
    w: usize,
    h: usize,
}

impl Rect {
    fn holds(&self, x: usize, y: usize) -> bool {
        (self.x..self.x + self.w).contains(&x) && (self.y..self.y + self.h).contains(&y)
    }

    fn widget(&self, kind: &str) -> Value {
        json!({"kind": kind, "x": self.x, "y": self.y, "w": self.w, "h": self.h})
    }
}

fn with(mut widget: Value, fields: Value) -> Value {
    for (name, value) in fields.as_object().expect("fields are an object") {
        widget[name] = value.clone();
    }
    widget
}

/// Mappings that name the fixture's scenes and inputs, and a layout with every widget kind but
/// `meter` (it needs live levels, which fake_obs never sends).
fn layout_document() -> Value {
    let mut doc = minimal_document();
    doc["keys"][0] = json!({"do": "scene", "uuid": "S_A", "label": "Cam"});
    doc["keys"][1] = json!({"do": "scene", "uuid": "S_B", "label": "Scr"});
    doc["keys"][2] = json!({"do": "toggle_mute", "uuid": "U_C", "label": "Mus"});
    doc["buttons"][0] = json!({"do": "toggle_record"});
    for (knob, uuid) in ["U_A", "U_B", "U_C"].into_iter().enumerate() {
        doc["knobs"][knob] =
            json!({"input": {"uuid": uuid, "label": uuid}, "step_db": 1, "push": {"do": "toggle_mute"}});
    }
    doc["main_display"]["widgets"] = json!([
        with(Rect { x: 0, y: 0, w: 320, h: 40 }.widget("status"), json!({"fields": ["link", "rec", "live"]})),
        with(TEXT_RECT.widget("text"), json!({"text": "Hello"})),
        with(Rect { x: 0, y: 80, w: 96, h: 96 }.widget("key"), json!({"key": 0})),
        with(Rect { x: 112, y: 80, w: 96, h: 96 }.widget("key"), json!({"key": 1})),
        with(Rect { x: 224, y: 80, w: 96, h: 96 }.widget("key"), json!({"key": 2})),
        with(Rect { x: 0, y: 192, w: 320, h: 48 }.widget("scene_line"), json!({"scene": "program", "size": "large"})),
        with(Rect { x: 0, y: 240, w: 320, h: 32 }.widget("scene_line"), json!({"scene": "preview", "size": "small"})),
        with(Rect { x: 0, y: 440, w: 160, h: 40 }.widget("legend"), json!({"button": 0})),
    ]);
    doc["strip_display"]["widgets"] = json!([
        with(Rect { x: 0, y: 0, w: 142, h: 140 }.widget("strip"), json!({"knob": 0, "parts": ["name", "db", "fader"]})),
        with(STRIP_RECT.widget("strip"), json!({"knob": 1, "parts": ["name", "db", "fader", "push"]})),
        with(Rect { x: 0, y: 284, w: 142, h: 140 }.widget("strip"), json!({"knob": 2, "parts": ["name", "fader"]})),
    ]);
    doc
}

fn sample_state() -> SampleState {
    let path = repo_root().join("tools/fixtures/ui_state.json");
    SampleState::from_json(&fs::read(&path).expect("ui_state.json reads")).expect("ui_state.json is a sample state")
}

fn line_channel(pipe: impl Read + Send + 'static) -> Receiver<String> {
    let (sender, lines) = mpsc::channel();
    thread::spawn(move || {
        for line in BufReader::new(pipe).lines().map_while(Result::ok) {
            if sender.send(line).is_err() {
                break;
            }
        }
    });
    lines
}

fn next_line(lines: &Receiver<String>, what: &str) -> String {
    lines.recv_timeout(TIMEOUT).unwrap_or_else(|_| panic!("{what} gives a line within {TIMEOUT:?}"))
}

fn reap(child: &mut Child) {
    if matches!(child.try_wait(), Ok(None)) {
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// `tools/fake_obs.py` with its default state file, `tools/fixtures/ui_state.json`.
struct FakeObs {
    child: Child,
    port: u16,
}

impl FakeObs {
    fn start(log: &Path) -> Self {
        let mut child = Command::new("python3")
            .arg(repo_root().join("tools/fake_obs.py"))
            .arg("--log")
            .arg(log)
            .stdout(Stdio::piped())
            .spawn()
            .expect("python3 runs tools/fake_obs.py");
        let first = next_line(&line_channel(child.stdout.take().expect("fake_obs stdout")), "fake_obs");
        let port = first.strip_prefix("listening ").and_then(|port| port.parse().ok());
        let port = port.unwrap_or_else(|| panic!("fake_obs first line names its port: {first:?}"));
        Self { child, port }
    }
}

impl Drop for FakeObs {
    fn drop(&mut self) {
        reap(&mut self.child);
    }
}

/// padsim on fake_obs: its stdin commands, its stdout lines and the pty the app opens.
struct Pad {
    child: Child,
    stdin: Option<ChildStdin>,
    lines: Receiver<String>,
    pty: String,
}

impl Pad {
    fn start(nor: &Path, obs_port: u16) -> Self {
        let padsim = std::env::var_os("PADSIM").map_or_else(|| repo_root().join(".build/padsim"), PathBuf::from);
        assert!(padsim.is_file(), "no padsim at {}: run `just padsim-build`", padsim.display());
        let mut child = Command::new(&padsim)
            .arg("--nor")
            .arg(nor)
            .arg("--obs")
            .arg(format!("127.0.0.1:{obs_port}"))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .expect("padsim starts");
        let stdin = child.stdin.take();
        let lines = line_channel(child.stdout.take().expect("padsim stdout"));
        let first = next_line(&lines, "padsim");
        let pty = first.strip_prefix("pty ").unwrap_or_else(|| panic!("first line names the pty: {first:?}"));
        Self { pty: pty.to_owned(), child, stdin, lines }
    }

    fn port(&self) -> TTYPort {
        serialport::new(&self.pty, 115_200).timeout(READ_TIMEOUT).open_native().expect("the pty opens as a serial port")
    }

    fn command(&mut self, text: &str) {
        let stdin = self.stdin.as_mut().expect("padsim stdin is open");
        writeln!(stdin, "{text}").and_then(|()| stdin.flush()).expect("padsim takes a command");
    }

    fn wait_idle(&mut self) {
        self.command("wait-idle");
        assert_eq!(next_line(&self.lines, "wait-idle"), "idle");
    }

    /// `wait-idle`, then `dump`: both panel frames as padsim's panel RAM holds them.
    fn frames(&mut self, dir: &Path) -> Frames {
        self.wait_idle();
        fs::create_dir_all(dir).expect("dump directory");
        self.command(&format!("dump {}", dir.display()));
        let reply = next_line(&self.lines, "dump");
        assert!(reply.starts_with(&format!("dumped {} bad_windows=0 ", dir.display())), "dump reply: {reply:?}");
        let read = |name: &str| fs::read(dir.join(name)).expect("dump file reads");
        Frames { main: read("main.rgb565"), strip: read("strip.rgb565") }
    }

    fn finish(mut self) {
        drop(self.stdin.take());
        let deadline = Instant::now() + TIMEOUT;
        let status = loop {
            if let Some(status) = self.child.try_wait().expect("padsim wait") {
                break status;
            }
            assert!(Instant::now() < deadline, "padsim ends within {TIMEOUT:?} of end of stdin");
            thread::sleep(Duration::from_millis(10));
        };
        let mut errors = String::new();
        self.child.stderr.take().expect("padsim stderr").read_to_string(&mut errors).expect("stderr reads");
        assert!(status.success(), "padsim exits 0, not {status}: {errors}");
        assert!(!errors.contains("Sanitizer") && !errors.contains("runtime error"), "sanitizers: {errors}");
    }
}

impl Drop for Pad {
    fn drop(&mut self) {
        reap(&mut self.child);
    }
}

fn wait_obs_up<P: Read + Write>(session: &mut Session<P>) {
    let deadline = Instant::now() + TIMEOUT;
    while session.status().map(|status| status.obs_state) != Some(OBS_UP) {
        assert!(Instant::now() < deadline, "padsim reaches fake_obs within {TIMEOUT:?}");
        session.listen(Duration::from_millis(50)).expect("listen");
    }
}

/// The pixels where two frames of one panel differ, as (x, y).
fn changed(before: &[u8], after: &[u8], width: usize) -> Vec<(usize, usize)> {
    assert_eq!(before.len(), after.len());
    let pixels = before.chunks_exact(2).zip(after.chunks_exact(2));
    pixels.enumerate().filter(|(_, (old, new))| old != new).map(|(at, _)| (at % width, at / width)).collect()
}

fn assert_inside(pixels: &[(usize, usize)], rect: Rect, panel: &str) {
    assert!(!pixels.is_empty(), "the edit changes {panel} pixels");
    let outside: Vec<_> = pixels.iter().filter(|(x, y)| !rect.holds(*x, *y)).take(5).collect();
    assert!(outside.is_empty(), "{panel} pixels changed outside {rect:?}: {outside:?}");
}

/// One stored write sent frame by frame, without the app's validator, so the pad's own check is
/// the one that answers. Returns the first `RESULT` that is not ok, or the commit's.
fn write_raw(port: &mut TTYPort, bytes: &[u8], base_seq: u32) -> (u8, String) {
    let mut chunks = bytes.chunks(protocol::CFG_CHUNK_MAX).enumerate();
    let total = u16::try_from(bytes.len()).expect("fits u16");
    let mut messages = vec![Message::CfgBegin { base_seq, total, crc32: crc32(bytes), try_only: false }];
    messages.extend(chunks.by_ref().map(|(index, chunk)| Message::CfgChunk {
        offset: u16::try_from(index * protocol::CFG_CHUNK_MAX).expect("fits u16"),
        bytes: chunk.to_vec(),
    }));
    messages.push(Message::CfgCommit);
    let mut rx = LinkRx::default();
    for (id, message) in (1u8..).zip(&messages) {
        let frame = message.encode(id).expect("the codec encodes it");
        port.write_all(&protocol::encode(&frame).expect("frame fits")).expect("pty write");
        let Message::Result { code, path, .. } = reply_to(port, &mut rx, id) else {
            panic!("{message:?} gives RESULT");
        };
        if code != RESULT_OK || matches!(message, Message::CfgCommit) {
            return (code, path);
        }
    }
    unreachable!("the messages end with CFG_COMMIT")
}

fn reply_to(port: &mut TTYPort, rx: &mut LinkRx, id: u8) -> Message {
    let deadline = Instant::now() + TIMEOUT;
    let mut buffer = [0u8; 256];
    loop {
        while let Some(pulled) = rx.pull() {
            if let Pulled::Frame(frame) = pulled {
                if frame.id == id && frame.kind == protocol::RESULT {
                    return Message::decode(&frame).expect("RESULT decodes");
                }
            }
        }
        assert!(Instant::now() < deadline, "the pad answers within {TIMEOUT:?}");
        match port.read(&mut buffer) {
            Ok(got) => rx.push(&buffer[..got]),
            Err(err) if err.kind() == std::io::ErrorKind::TimedOut => {}
            Err(err) => panic!("pty read: {err}"),
        }
    }
}

/// CRC-32 (IEEE, reflected), as `CFG_BEGIN` carries it (`docs/protocol.md`).
fn crc32(bytes: &[u8]) -> u32 {
    !bytes.iter().fold(u32::MAX, |crc, &byte| {
        (0..8).fold(crc ^ u32::from(byte), |crc, _| if crc & 1 == 1 { (crc >> 1) ^ 0xEDB8_8320 } else { crc >> 1 })
    })
}

#[test]
fn criterion_4b_display_layout_round_trip() {
    let scratch = Scratch::new("criterion-4b");
    let obs = FakeObs::start(&scratch.path("requests.log"));
    let mut pad = Pad::start(&scratch.path("pad.nor"), obs.port);
    let mut port = pad.port();
    let mut session = Session::start(&mut port).expect("INFO");
    let info = session.info().clone();
    let schemas = u64::from(info.schema_min)..=u64::from(info.schema_max);
    let state = sample_state();

    assert_eq!(session.read().expect("read"), Stored { seq: 0, bytes: Vec::new() }, "a fresh pad holds nothing");
    let seeded = Document::parse(layout_document().to_string().as_bytes(), schemas.clone()).expect("valid layout");
    assert_eq!(session.write(&seeded).expect("write"), Written::Saved { seq: 1 });
    wait_obs_up(&mut session);
    let before = pad.frames(&scratch.path("before"));
    assert_eq!(before.main.len(), MAIN_BYTES, "main.rgb565 is 320 x 480 x 2 bytes");
    assert_eq!(before.strip.len(), STRIP_BYTES, "strip.rgb565 is 142 x 428 x 2 bytes");
    assert!(preview::render(&seeded, &state).expect("preview") == before, "the stored layout previews as drawn");

    let read = session.read().expect("read");
    let edited = read
        .edit(&info, |doc| {
            doc["main_display"]["widgets"][1]["text"] = json!("Test 1");
            doc["strip_display"]["widgets"][1]["parts"] = json!(["name", "db", "push"]);
        })
        .expect("the edit is valid");
    let shown = preview::render(&edited, &state).expect("preview");
    assert_eq!(session.write(&edited).expect("write"), Written::Saved { seq: 2 }, "RESULT ok");
    let after = pad.frames(&scratch.path("after"));
    assert!(after.main == shown.main, "main.rgb565 equals the preview byte for byte");
    assert!(after.strip == shown.strip, "strip.rgb565 equals the preview byte for byte");
    assert_inside(&changed(&before.main, &after.main, MAIN_WIDTH), TEXT_RECT, "main");
    assert_inside(&changed(&before.strip, &after.strip, STRIP_WIDTH), STRIP_RECT, "strip");

    let mut overlap: Value = serde_json::from_slice(&edited.to_bytes()).expect("JSON");
    overlap["seq"] = json!(2);
    overlap["main_display"]["widgets"][2] = with(Rect { x: 0, y: 60, w: 96, h: 96 }.widget("key"), json!({"key": 0}));
    let overlap = overlap.to_string().into_bytes();
    let second = "main_display.widgets[2]";
    assert_eq!(
        Document::parse(&overlap, schemas).expect_err("the app refuses it too"),
        Rejected::Invalid { path: second.into() },
        "the app names the same widget"
    );
    drop(session);
    assert_eq!(write_raw(&mut port, &overlap, 2), (RESULT_INVALID, second.to_owned()), "the pad refuses it");
    assert!(pad.frames(&scratch.path("refused")) == after, "the refused write leaves both frames as they were");
    drop(port);
    pad.finish();
}
