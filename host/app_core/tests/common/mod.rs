// SPDX-License-Identifier: MIT
//! padsim (the whole firmware core on a pseudo-terminal) as the pad an `app_core` session talks to.
//! `just padsim-build` writes `.build/padsim`; `PADSIM` names another build.
// Each test binary uses its own part of this module.
#![allow(dead_code)]

use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use serde_json::Value;
use serialport::TTYPort;

const TIMEOUT: Duration = Duration::from_secs(10);
const READ_TIMEOUT: Duration = Duration::from_millis(20);

pub fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// `firmware/test/config_vectors/valid_minimal.json` as JSON: `seq` 0, every action `none`.
pub fn minimal_document() -> Value {
    let path = repo_root().join("firmware/test/config_vectors/valid_minimal.json");
    serde_json::from_slice(&fs::read(&path).expect("valid_minimal.json reads")).expect("valid_minimal.json is JSON")
}

/// A fresh directory under the system temp dir, removed on drop.
pub struct Scratch(PathBuf);

impl Scratch {
    pub fn new(name: &str) -> Self {
        let dir = std::env::temp_dir().join(format!("app-core-{}-{name}", std::process::id()));
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

/// One padsim process with its flash in `nor`.
pub struct Padsim {
    child: Child,
    stdin: Option<ChildStdin>,
    pty: String,
}

impl Padsim {
    pub fn start(nor: &Path) -> Self {
        Self::start_with(nor, &[])
    }

    /// With OBS at `127.0.0.1:obs_port` (padsim's `--obs`).
    pub fn start_with_obs(nor: &Path, obs_port: u16) -> Self {
        Self::start_with(nor, &["--obs".to_owned(), format!("127.0.0.1:{obs_port}")])
    }

    fn start_with(nor: &Path, flags: &[String]) -> Self {
        let padsim = std::env::var_os("PADSIM").map_or_else(|| repo_root().join(".build/padsim"), PathBuf::from);
        assert!(padsim.is_file(), "no padsim at {}: run `just padsim-build`", padsim.display());
        let mut child = Command::new(&padsim)
            .arg("--nor")
            .arg(nor)
            .args(flags)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .expect("padsim starts");
        let stdin = child.stdin.take();
        let mut stdout = BufReader::new(child.stdout.take().expect("padsim stdout"));
        let mut first = String::new();
        stdout.read_line(&mut first).expect("padsim line");
        // Later lines are drained, so padsim never writes into a closed pipe.
        thread::spawn(move || stdout.lines().map_while(Result::ok).for_each(drop));
        let pty =
            first.trim_end().strip_prefix("pty ").unwrap_or_else(|| panic!("first line names the pty: {first:?}"));
        Self { pty: pty.to_owned(), child, stdin }
    }

    /// The pty as the serial port the app opens. A pty has no DTR line, so this skips the DTR
    /// step of `discover::open` and keeps its settings.
    pub fn port(&self) -> TTYPort {
        serialport::new(&self.pty, 115_200).timeout(READ_TIMEOUT).open_native().expect("the pty opens as a serial port")
    }

    /// One stdin command (`firmware/padsim/main.c`).
    pub fn command(&mut self, text: &str) {
        let stdin = self.stdin.as_mut().expect("padsim stdin is open");
        writeln!(stdin, "{text}").and_then(|()| stdin.flush()).expect("padsim takes a command");
    }

    /// Ends padsim through end of stdin. It must exit 0 with no sanitizer report.
    pub fn finish(mut self) {
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

impl Drop for Padsim {
    fn drop(&mut self) {
        if matches!(self.child.try_wait(), Ok(None)) {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}

/// `tools/fake_obs.py` on a free loopback port, with `flags` such as `--scenes 500`.
pub struct FakeObs {
    child: Child,
    pub port: u16,
}

impl FakeObs {
    pub fn start(log: &Path, flags: &[&str]) -> Self {
        let mut child = Command::new("python3")
            .arg(repo_root().join("tools/fake_obs.py"))
            .arg("--log")
            .arg(log)
            .args(flags)
            .stdout(Stdio::piped())
            .spawn()
            .expect("python3 runs tools/fake_obs.py");
        let mut stdout = BufReader::new(child.stdout.take().expect("fake_obs stdout"));
        let mut first = String::new();
        stdout.read_line(&mut first).expect("fake_obs line");
        thread::spawn(move || stdout.lines().map_while(Result::ok).for_each(drop));
        let port = first.trim_end().strip_prefix("listening ").and_then(|port| port.parse().ok());
        let port = port.unwrap_or_else(|| panic!("fake_obs first line names its port: {first:?}"));
        Self { child, port }
    }
}

impl Drop for FakeObs {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
