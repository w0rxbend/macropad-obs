// SPDX-License-Identifier: MIT
//! What the window's commands call (task 3.6): at most one open pad, the document last read from
//! it, and serialisable answers. The Tauri crate only locks this and forwards, so every rule here
//! runs in `just test`.

use std::fmt;
use std::io::{Read, Write};
use std::mem;
use std::time::Duration;

use obs_core::document::{Document, Rejected};
use obs_core::protocol::{Info, Secret};
use serde::Serialize;
use serde_json::Value;
use serialport::SerialPort;

use crate::diff::Change;
use crate::discover::{self, DiscoverError, UsbPort};
use crate::provision::{self, wipe, Credential, Status};
use crate::session::{schemas, Session, SessionError, Stored, Written};

/// How long `status` reads what the pad sends unasked before it answers.
const STATUS_LISTEN: Duration = Duration::from_millis(50);

/// A command that failed, as one line for the UI. No variant of the errors it comes from carries
/// a secret byte.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(transparent)]
pub struct Failure(String);

impl fmt::Display for Failure {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Failure {}

impl From<SessionError> for Failure {
    fn from(err: SessionError) -> Self {
        Self(err.to_string())
    }
}

impl From<DiscoverError> for Failure {
    fn from(err: DiscoverError) -> Self {
        Self(err.to_string())
    }
}

impl From<Rejected> for Failure {
    fn from(why: Rejected) -> Self {
        Self(match why {
            Rejected::TooBig => "document too big".to_owned(),
            Rejected::Invalid { path } if path.is_empty() => "the document is not one JSON object".to_owned(),
            Rejected::Invalid { path } => format!("invalid value at `{path}`"),
        })
    }
}

/// The `INFO` fields the window shows, the byte arrays as lowercase hex.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PadInfo {
    pub fw_version: String,
    pub git_hash: String,
    pub board_rev: u8,
    pub unique_id: String,
    pub schema_min: u16,
    pub schema_max: u16,
    pub keys: u8,
    pub buttons: u8,
    pub knobs: u8,
    pub obs_password_set: bool,
    pub wifi_psk_set: bool,
}

impl From<&Info> for PadInfo {
    fn from(info: &Info) -> Self {
        Self {
            fw_version: info.fw_version.clone(),
            git_hash: hex(&info.git_hash),
            board_rev: info.board_rev,
            unique_id: hex(&info.unique_id),
            schema_min: info.schema_min,
            schema_max: info.schema_max,
            keys: info.keys,
            buttons: info.buttons,
            knobs: info.knobs,
            obs_password_set: info.obs_password_set,
            wifi_psk_set: info.wifi_psk_set,
        }
    }
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// The stored document as JSON. An empty pad, or bytes that are not JSON (a torn store), give
/// `null`, as the stale diff reads them; the next write replaces them on the same `seq`.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Config {
    pub seq: u32,
    pub document: Value,
}

impl From<&Stored> for Config {
    fn from(stored: &Stored) -> Self {
        Self { seq: stored.seq, document: serde_json::from_slice(&stored.bytes).unwrap_or(Value::Null) }
    }
}

/// How a write ended. `Stale` carries the re-read, which the next write is based on.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(tag = "outcome", rename_all = "snake_case")]
pub enum Saved {
    Saved { seq: u32 },
    Stale { pad: Config, changes: Vec<Change> },
}

struct Open<P> {
    session: Session<P>,
    /// The last document read or written: the base of the next write and of the export.
    stored: Option<Stored>,
}

/// One pad or none. Each method is one window command.
pub struct Connection<P> {
    open: Option<Open<P>>,
}

impl<P> Default for Connection<P> {
    fn default() -> Self {
        Self { open: None }
    }
}

/// The pad-VID/PID USB serial ports, for the picker.
pub fn pads() -> Result<Vec<UsbPort>, Failure> {
    Ok(discover::pads(&discover::usb_ports()?))
}

impl Connection<Box<dyn SerialPort>> {
    /// Opens the pad with `serial`, or the only pad when `serial` is `None`.
    pub fn connect(&mut self, serial: Option<&str>) -> Result<PadInfo, Failure> {
        let port = discover::pick(&discover::usb_ports()?, serial)?;
        self.disconnect();
        self.attach(discover::open(&port)?)
    }
}

impl<P: Read + Write> Connection<P> {
    pub fn new() -> Self {
        Self::default()
    }

    /// Starts a session on `port` in place of any open one.
    pub fn attach(&mut self, port: P) -> Result<PadInfo, Failure> {
        self.disconnect();
        self.open = Some(Open { session: Session::start(port)?, stored: None });
        self.info()
    }

    pub fn disconnect(&mut self) {
        self.open = None;
    }

    pub fn info(&self) -> Result<PadInfo, Failure> {
        Ok(PadInfo::from(self.opened()?.session.info()))
    }

    pub fn read(&mut self) -> Result<Config, Failure> {
        let open = self.opened_mut()?;
        let stored = open.session.read()?;
        let config = Config::from(&stored);
        open.stored = Some(stored);
        Ok(config)
    }

    /// Writes `document` as the whole new document, on the `seq` of the last read whatever `seq`
    /// it carries. The validator runs first, so a refused document sends nothing.
    pub fn write(&mut self, document: Value) -> Result<Saved, Failure> {
        let open = self.opened_mut()?;
        let base = open.stored.as_ref().ok_or_else(not_read)?;
        let doc = based_on(base, open.session.info(), document)?;
        match open.session.write(&doc)? {
            Written::Saved { seq } => {
                open.stored = Some(Stored { seq, bytes: doc.to_bytes() });
                Ok(Saved::Saved { seq })
            }
            Written::Stale { pad, changes } => {
                let config = Config::from(&pad);
                open.stored = Some(pad);
                Ok(Saved::Stale { pad: config, changes })
            }
        }
    }

    /// Sends `secret` and zeroes its bytes whatever the outcome; answers the new `INFO` flags.
    pub fn set_credential(&mut self, credential: Credential, secret: String) -> Result<PadInfo, Failure> {
        let mut field = Secret(secret.into_bytes());
        let sent = match self.opened_mut() {
            Ok(open) => open.session.set_credential(credential, &mut field).map_err(Failure::from),
            Err(failure) => Err(failure),
        };
        wipe(mem::take(&mut field.0));
        sent.and_then(|()| self.info())
    }

    pub fn clear_credentials(&mut self) -> Result<PadInfo, Failure> {
        self.opened_mut()?.session.clear_credentials()?;
        self.info()
    }

    /// The last `STATUS` the pad sent, after reading what it sent since the last command.
    pub fn status(&mut self) -> Result<Option<Status>, Failure> {
        let session = &mut self.opened_mut()?.session;
        session.listen(STATUS_LISTEN)?;
        Ok(session.status().copied())
    }

    /// The last document read or written as pretty JSON, which holds no secret (spec 8.2).
    pub fn export(&self) -> Result<String, Failure> {
        let stored = self.opened()?.stored.as_ref().ok_or_else(not_read)?;
        let bytes = provision::export(stored)?;
        String::from_utf8(bytes).map_err(|_| Failure("the export is not UTF-8".to_owned()))
    }

    fn opened(&self) -> Result<&Open<P>, Failure> {
        self.open.as_ref().ok_or_else(no_pad)
    }

    fn opened_mut(&mut self) -> Result<&mut Open<P>, Failure> {
        self.open.as_mut().ok_or_else(no_pad)
    }
}

fn no_pad() -> Failure {
    Failure("no pad connected".to_owned())
}

fn not_read() -> Failure {
    Failure("read the config first".to_owned())
}

/// `document` with `base`'s `seq`, through the validator for the pad's schema range.
fn based_on(base: &Stored, info: &Info, mut document: Value) -> Result<Document, Rejected> {
    let Some(members) = document.as_object_mut() else {
        return Err(Rejected::Invalid { path: String::new() });
    };
    members.insert("seq".to_owned(), Value::from(base.seq));
    Document::parse(document.to_string().as_bytes(), schemas(info))
}
