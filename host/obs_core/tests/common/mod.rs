// SPDX-License-Identifier: MIT
//! The end-to-end harness: padsim (the whole firmware core on a pseudo-terminal) and
//! `tools/fake_obs.py`, driven through this crate's codec as the app drives a pad (spec 13).
//!
//! `just padsim-build` writes `.build/padsim`; `PADSIM` names another build. Standard library only:
//! a thread per pipe turns each blocking read into a channel the test can wait on with a deadline.

// Each test binary compiles this module and uses only part of it.
#![allow(dead_code)]

use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, ExitStatus, Stdio};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::thread;
use std::time::{Duration, Instant};

use obs_core::document::{self, Document};
use obs_core::protocol::{self, Frame, Info, Message, Pulled, INPUT, OBS_UP, RESULT_OK, STATUS};
use obs_core::LinkRx;
use serde_json::Value;

pub const TIMEOUT: Duration = Duration::from_secs(10);
/// How long the request log must stay unchanged before a test reads it as complete.
const LOG_QUIET: Duration = Duration::from_millis(400);
const LOG_POLL: Duration = Duration::from_millis(10);
/// Linux `O_NOCTTY` (asm-generic `fcntl.h`): opening the pty must not make it our terminal.
const O_NOCTTY: i32 = 0o400;
/// The signal `--cut-after` kills padsim with (`firmware/padsim/nor_file.c`).
const SIGKILL: i32 = 9;

pub fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// `firmware/test/config_vectors/valid_minimal.json` as JSON: every action `none`, no widget.
pub fn minimal_document() -> Value {
    let path = repo_root().join("firmware/test/config_vectors/valid_minimal.json");
    serde_json::from_slice(&fs::read(&path).expect("valid_minimal.json reads")).expect("valid_minimal.json is JSON")
}

/// A fresh directory under the system temp dir, removed on drop.
pub struct Scratch(PathBuf);

impl Scratch {
    pub fn new(name: &str) -> Self {
        let dir = std::env::temp_dir().join(format!("padsim-e2e-{}-{name}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).expect("scratch directory");
        Self(dir)
    }

    pub fn path(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

/// Lines of a child pipe, read on their own thread.
fn line_channel(pipe: impl Read + Send + 'static) -> Receiver<String> {
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        for line in BufReader::new(pipe).lines() {
            let Ok(line) = line else { break };
            if tx.send(line).is_err() {
                break;
            }
        }
    });
    rx
}

fn next_line(lines: &Receiver<String>, what: &str) -> String {
    lines.recv_timeout(TIMEOUT).unwrap_or_else(|_| panic!("{what}: no line within {TIMEOUT:?}"))
}

/// Kills a child that a test left running because it panicked. A finished child is not touched.
fn reap(child: &mut Child) {
    if matches!(child.try_wait(), Ok(None)) {
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// `tools/fake_obs.py` on a free loopback port with its request log in a file.
pub struct FakeObs {
    child: Child,
    pub port: u16,
    log: PathBuf,
}

impl FakeObs {
    pub fn start(log: PathBuf) -> Self {
        Self::start_with(log, &[])
    }

    /// With more `tools/fake_obs.py` flags, such as `--scenes 500`.
    pub fn start_with(log: PathBuf, flags: &[&str]) -> Self {
        let mut child = Command::new("python3")
            .arg(repo_root().join("tools/fake_obs.py"))
            .arg("--log")
            .arg(&log)
            .args(flags)
            .stdout(Stdio::piped())
            .spawn()
            .expect("python3 runs tools/fake_obs.py");
        let lines = line_channel(child.stdout.take().expect("fake_obs stdout"));
        let first = next_line(&lines, "fake_obs");
        let port = first.strip_prefix("listening ").and_then(|port| port.parse().ok());
        let port = port.unwrap_or_else(|| panic!("fake_obs first line names its port: {first:?}"));
        Self { child, port, log }
    }

    /// Every request line logged so far.
    pub fn requests(&self) -> Vec<String> {
        fs::read_to_string(&self.log).expect("request log reads").lines().map(str::to_owned).collect()
    }

    /// The log once it holds at least `count` lines and has then stayed unchanged for `LOG_QUIET`,
    /// so a request that arrives late is in it.
    pub fn requests_settled(&self, count: usize) -> Vec<String> {
        let deadline = Instant::now() + TIMEOUT;
        let mut seen = self.requests();
        let mut stable_since = Instant::now();
        loop {
            thread::sleep(LOG_POLL);
            let now = self.requests();
            if now != seen {
                seen = now;
                stable_since = Instant::now();
            } else if seen.len() >= count && stable_since.elapsed() >= LOG_QUIET {
                return seen;
            }
            assert!(Instant::now() < deadline, "request log holds {} of {count} lines: {seen:#?}", seen.len());
        }
    }
}

impl Drop for FakeObs {
    fn drop(&mut self) {
        reap(&mut self.child);
    }
}

/// The `RESULT` that ends a write.
#[derive(Debug, PartialEq, Eq)]
pub struct WriteResult {
    pub code: u8,
    pub seq: u32,
    pub path: String,
}

/// One padsim process: its stdin commands, its stdout lines and the CDC link on its pty.
pub struct Pad {
    child: Child,
    stdin: Option<ChildStdin>,
    lines: Receiver<String>,
    link: File,
    bytes: Receiver<Vec<u8>>,
    rx: LinkRx,
    next_id: u8,
    last_status: Option<(u8, u8)>,
}

impl Pad {
    pub fn start(nor: &Path, obs_port: Option<u16>) -> Self {
        Self::start_with(nor, obs_port, None)
    }

    /// `cut_after`: padsim's `--cut-after N`, SIGKILL when flash program call N begins.
    pub fn start_with(nor: &Path, obs_port: Option<u16>, cut_after: Option<u32>) -> Self {
        let padsim = std::env::var_os("PADSIM").map_or_else(|| repo_root().join(".build/padsim"), PathBuf::from);
        assert!(padsim.is_file(), "no padsim at {}: run `just padsim-build`", padsim.display());
        let mut command = Command::new(&padsim);
        command.arg("--nor").arg(nor);
        if let Some(port) = obs_port {
            command.arg("--obs").arg(format!("127.0.0.1:{port}"));
        }
        if let Some(call) = cut_after {
            command.arg("--cut-after").arg(call.to_string());
        }
        let mut child =
            command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().expect("padsim starts");
        let stdin = child.stdin.take();
        let lines = line_channel(child.stdout.take().expect("padsim stdout"));
        let first = next_line(&lines, "padsim");
        let pty = first.strip_prefix("pty ").unwrap_or_else(|| panic!("first line names the pty: {first:?}"));
        // padsim holds the slave open in raw mode, so the line discipline passes every byte.
        let link = OpenOptions::new().read(true).write(true).custom_flags(O_NOCTTY).open(pty).expect("pty opens");
        let bytes = byte_channel(link.try_clone().expect("pty clones"));
        Self { child, stdin, lines, link, bytes, rx: LinkRx::default(), next_id: 1, last_status: None }
    }

    /// One stdin command (`firmware/padsim/main.c`).
    pub fn command(&mut self, text: &str) {
        let stdin = self.stdin.as_mut().expect("padsim stdin is open");
        writeln!(stdin, "{text}").and_then(|()| stdin.flush()).expect("padsim takes a command");
    }

    pub fn wait_idle(&mut self) {
        self.command("wait-idle");
        let line = next_line(&self.lines, "wait-idle");
        assert_eq!(line, "idle", "wait-idle answers idle");
    }

    fn frame(&mut self, deadline: Instant) -> Frame {
        self.try_frame(deadline).expect("padsim is alive")
    }

    /// The next frame from the pad, or None once padsim has closed the pty. A STATUS frame also
    /// updates `last_status`.
    fn try_frame(&mut self, deadline: Instant) -> Option<Frame> {
        loop {
            match self.rx.pull() {
                Some(Pulled::Frame(frame)) => {
                    if frame.kind == STATUS {
                        if let Some(Message::Status { obs_state, wifi_state, .. }) = Message::decode(&frame) {
                            self.last_status = Some((obs_state, wifi_state));
                        }
                    }
                    return Some(frame);
                }
                Some(Pulled::Reply(reply)) => panic!("the pad sent a frame the codec refuses: {reply:?}"),
                None => {}
            }
            let left = deadline.saturating_duration_since(Instant::now());
            match self.bytes.recv_timeout(left) {
                Ok(bytes) => self.rx.push(&bytes),
                Err(RecvTimeoutError::Disconnected) => return None,
                Err(RecvTimeoutError::Timeout) => panic!("the pad sent no whole frame within {TIMEOUT:?}"),
            }
        }
    }

    /// Sends one message and returns the pad's reply to it. STATUS and INPUT frames are skipped.
    pub fn ask(&mut self, message: &Message) -> Message {
        self.try_ask(message).unwrap_or_else(|| panic!("padsim ended before it answered {message:?}"))
    }

    /// `ask`, or None when padsim ends before it answers.
    fn try_ask(&mut self, message: &Message) -> Option<Message> {
        let id = self.next_id;
        self.next_id = self.next_id % u8::MAX + 1;
        let frame = message.encode(id).unwrap_or_else(|| panic!("the codec encodes {message:?}"));
        // A pty whose master is closed refuses the write: padsim has ended.
        self.link.write_all(&protocol::encode(&frame).expect("frame fits")).ok()?;
        let deadline = Instant::now() + TIMEOUT;
        loop {
            let reply = self.try_frame(deadline)?;
            if reply.id == id && reply.kind != STATUS && reply.kind != INPUT {
                return Some(
                    Message::decode(&reply).unwrap_or_else(|| panic!("the codec decodes the reply {reply:?}")),
                );
            }
        }
    }

    pub fn info(&mut self) -> Info {
        match self.ask(&Message::InfoGet) {
            Message::Info(info) => info,
            other => panic!("INFO_GET gives INFO, not {other:?}"),
        }
    }

    pub fn wait_obs_up(&mut self) {
        let deadline = Instant::now() + TIMEOUT;
        while self.last_status.map(|(obs, _)| obs) != Some(OBS_UP) {
            self.frame(deadline);
        }
    }

    /// `CFG_READ` until `total`: the stored `seq` and the document bytes.
    pub fn read_document(&mut self) -> (u32, Vec<u8>) {
        let mut doc = Vec::new();
        loop {
            let offset = u16::try_from(doc.len()).expect("a document fits u16");
            let len = u8::try_from(protocol::CFG_DATA_MAX).expect("CFG_DATA_MAX fits u8");
            let Message::CfgData { seq, total, offset: at, bytes } = self.ask(&Message::CfgRead { offset, len }) else {
                panic!("CFG_READ gives CFG_DATA");
            };
            assert_eq!(at, offset, "CFG_DATA answers the offset asked");
            doc.extend(bytes);
            if doc.len() >= usize::from(total) {
                assert_eq!(doc.len(), usize::from(total), "CFG_DATA gives no byte past total");
                return (seq, doc);
            }
        }
    }

    /// `CFG_BEGIN`, the chunks, `CFG_COMMIT`, as `document::write_messages` builds them. Stops at
    /// the first `RESULT` that is not ok and returns it; else returns the commit's.
    pub fn write_document(&mut self, info: &Info, doc: &Document) -> WriteResult {
        self.write_document_or_cut(info, doc).expect("padsim ended during CFG_COMMIT")
    }

    /// `write_document`, or None when padsim ends during `CFG_COMMIT`, as a `--cut-after` kill
    /// does. padsim ending on any earlier message fails the test.
    pub fn write_document_or_cut(&mut self, info: &Info, doc: &Document) -> Option<WriteResult> {
        let messages = document::write_messages(info, doc).expect("the app may write this pad");
        for message in &messages {
            let is_commit = matches!(message, Message::CfgCommit);
            let Some(reply) = self.try_ask(message) else {
                assert!(is_commit, "padsim ended on {message:?}, before CFG_COMMIT");
                return None;
            };
            let Message::Result { code, seq, path } = reply else {
                panic!("{message:?} gives RESULT");
            };
            if code != RESULT_OK || is_commit {
                return Some(WriteResult { code, seq, path });
            }
        }
        unreachable!("write_messages ends with CFG_COMMIT")
    }

    /// `dump DIR`: writes the panel frames to `dir` and returns the strip line padsim names.
    pub fn strip_line(&mut self, dir: &Path) -> String {
        self.command(&format!("dump {}", dir.display()));
        let reply = next_line(&self.lines, "dump");
        let (head, line) = reply.split_once(" line=").unwrap_or_else(|| panic!("dump names the line: {reply:?}"));
        assert_eq!(head, format!("dumped {} bad_windows=0", dir.display()), "dump reply");
        line.to_owned()
    }

    /// Waits for padsim to die by SIGKILL, as `--cut-after` kills it.
    pub fn wait_killed(mut self) {
        let status = self.wait_exit();
        assert_eq!(status.signal(), Some(SIGKILL), "padsim was killed by SIGKILL, not {status}");
    }

    fn wait_exit(&mut self) -> ExitStatus {
        let deadline = Instant::now() + TIMEOUT;
        loop {
            if let Some(status) = self.child.try_wait().expect("padsim wait") {
                return status;
            }
            assert!(Instant::now() < deadline, "padsim ends within {TIMEOUT:?}");
            thread::sleep(LOG_POLL);
        }
    }

    /// Ends padsim through end of stdin. It must exit 0 with no sanitizer report.
    pub fn finish(mut self) {
        drop(self.stdin.take());
        let status = self.wait_exit();
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

/// Bytes from the pty, read on their own thread. The thread ends when padsim closes the master.
fn byte_channel(mut link: File) -> Receiver<Vec<u8>> {
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let mut buf = [0u8; 4096];
        while let Ok(got @ 1..) = link.read(&mut buf) {
            if tx.send(buf[..got].to_vec()).is_err() {
                break;
            }
        }
    });
    rx
}

/// The app's read-modify-write: `edit` changes the JSON it read, the result carries the read `seq`
/// as its own `seq` (the `base_seq` of the write, `docs/config.md`), and passes the validator.
pub fn edited(info: &Info, read: &[u8], read_seq: u32, edit: impl FnOnce(&mut Value)) -> Document {
    let schemas = u64::from(info.schema_min)..=u64::from(info.schema_max);
    Document::parse(read, schemas.clone()).expect("the pad serves a valid document");
    let mut json: Value = serde_json::from_slice(read).expect("the document is JSON");
    edit(&mut json);
    json["seq"] = Value::from(read_seq);
    Document::parse(json.to_string().as_bytes(), schemas).expect("the edited document is valid")
}

/// Writes `json` as the first document of an empty pad (base seq 0) and checks it is stored as seq 1.
pub fn seed(pad: &mut Pad, info: &Info, json: &Value) {
    let schemas = u64::from(info.schema_min)..=u64::from(info.schema_max);
    let doc = Document::parse(json.to_string().as_bytes(), schemas).expect("the seed document is valid");
    assert_eq!(pad.read_document(), (0, Vec::new()), "a fresh pad serves no document");
    assert_eq!(pad.write_document(info, &doc), WriteResult { code: RESULT_OK, seq: 1, path: String::new() });
}
