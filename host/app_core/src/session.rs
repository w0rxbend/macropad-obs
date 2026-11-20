// SPDX-License-Identifier: MIT
//! One config session (spec 8.2): `INFO`, `CFG_READ` until total, edit with unknown fields kept,
//! `CFG_BEGIN(base_seq)`, the chunks, `CFG_COMMIT`. A stale `seq` re-reads and gives the diff.

use std::fmt;
use std::io::{Read, Write};
use std::ops::RangeInclusive;
use std::time::Duration;

use obs_core::document::{self, Document, Rejected, WriteRefused};
use obs_core::protocol::{Info, Message, CFG_DATA_MAX, RESULT_OK, RESULT_STALE_SEQ};
use serde_json::Value;

use crate::diff::{changes, Change};
use crate::link::{Link, LinkError};
use crate::provision::Status;

/// `CFG_DATA_MAX` as the `len` of a `CFG_READ`.
const READ_LEN: u8 = CFG_DATA_MAX as u8;

#[derive(Debug)]
pub enum SessionError {
    Link(LinkError),
    /// The app writes nothing to this pad (schema age or size).
    Refused(WriteRefused),
    /// The pad refused the write with a `RESULT` code other than ok or stale: the first bad path.
    Rejected {
        code: u8,
        path: String,
    },
    /// A reply of the wrong type, or a `CFG_DATA` that breaks the read (trust boundary).
    BadReply(&'static str),
    /// A credential refused with this `CRED_*` code, by the pad or by the app's check before
    /// sending.
    CredentialRefused {
        code: u8,
    },
}

impl fmt::Display for SessionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Link(err) => err.fmt(f),
            Self::Refused(why) => why.fmt(f),
            Self::Rejected { code, path } => write!(f, "the pad refused the write (code {code}) at `{path}`"),
            Self::BadReply(what) => write!(f, "the pad broke the protocol: {what}"),
            Self::CredentialRefused { code } => write!(f, "the credential was refused (code {code})"),
        }
    }
}

impl std::error::Error for SessionError {}

impl From<LinkError> for SessionError {
    fn from(err: LinkError) -> Self {
        Self::Link(err)
    }
}

impl From<WriteRefused> for SessionError {
    fn from(why: WriteRefused) -> Self {
        Self::Refused(why)
    }
}

/// The document the pad holds, as it served it. An empty pad has `seq` 0 and no byte.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Stored {
    pub seq: u32,
    pub bytes: Vec<u8>,
}

impl Stored {
    /// The read-modify-write: `change` edits the JSON as read, unknown members included. The
    /// result carries this `seq`, the `base_seq` of its write, and passes the validator.
    pub fn edit(&self, info: &Info, change: impl FnOnce(&mut Value)) -> Result<Document, Rejected> {
        let not_an_object = || Rejected::Invalid { path: String::new() };
        let mut json: Value = serde_json::from_slice(&self.bytes).map_err(|_| not_an_object())?;
        if !json.is_object() {
            return Err(not_an_object());
        }
        change(&mut json);
        json["seq"] = Value::from(self.seq);
        Document::parse(json.to_string().as_bytes(), schemas(info))
    }
}

/// How a write ended.
#[derive(Debug, Clone, PartialEq)]
pub enum Written {
    Saved {
        seq: u32,
    },
    /// Another write came first. `pad` is the re-read; `changes` are the leaves where it differs
    /// from the document the app tried to write, `seq` left out.
    Stale {
        pad: Stored,
        changes: Vec<Change>,
    },
}

/// A session with one pad. `INFO` is asked once, at the start.
pub struct Session<P> {
    link: Link<P>,
    info: Info,
}

impl<P: Read + Write> Session<P> {
    pub fn start(port: P) -> Result<Self, SessionError> {
        let mut link = Link::new(port);
        let info = ask_info(&mut link)?;
        Ok(Self { link, info })
    }

    pub fn info(&self) -> &Info {
        &self.info
    }

    /// Asks `INFO` again, after a step that changes it (a credential set or cleared).
    pub(crate) fn reload_info(&mut self) -> Result<(), SessionError> {
        self.info = ask_info(&mut self.link)?;
        Ok(())
    }

    pub(crate) fn ask(&mut self, message: &Message) -> Result<Message, LinkError> {
        self.link.ask(message)
    }

    /// Reads what the pad sends unasked for `wait`, so `status` catches up.
    pub fn listen(&mut self, wait: Duration) -> Result<(), SessionError> {
        Ok(self.link.listen(wait)?)
    }

    /// The last `STATUS` the pad sent, seen during any request or `listen`.
    pub fn status(&self) -> Option<&Status> {
        self.link.status()
    }

    /// `CFG_READ` until `total`. Each `CFG_DATA` must answer the offset asked, keep `seq` and
    /// `total`, and stay inside both `total` and the pad's `max_doc_bytes`.
    pub fn read(&mut self) -> Result<Stored, SessionError> {
        let (seq, total, mut bytes) = self.read_at(0)?;
        if total > self.info.max_doc_bytes {
            return Err(SessionError::BadReply("CFG_DATA total past max_doc_bytes"));
        }
        let total = usize::from(total);
        while bytes.len() < total {
            let offset = u16::try_from(bytes.len()).expect("below total, a u16");
            let (more_seq, more_total, chunk) = self.read_at(offset)?;
            if (more_seq, usize::from(more_total)) != (seq, total) || chunk.is_empty() {
                return Err(SessionError::BadReply("CFG_DATA does not continue the read"));
            }
            bytes.extend(chunk);
        }
        if bytes.len() > total {
            return Err(SessionError::BadReply("CFG_DATA past total"));
        }
        Ok(Stored { seq, bytes })
    }

    /// One `CFG_READ` at `offset`: the reply's `seq`, `total` and bytes.
    fn read_at(&mut self, offset: u16) -> Result<(u32, u16, Vec<u8>), SessionError> {
        match self.link.ask(&Message::CfgRead { offset, len: READ_LEN })? {
            Message::CfgData { seq, total, offset: at, bytes } if at == offset => Ok((seq, total, bytes)),
            Message::CfgData { .. } => Err(SessionError::BadReply("CFG_DATA answers another offset")),
            _ => Err(SessionError::BadReply("CFG_READ answered without CFG_DATA")),
        }
    }

    /// Writes `doc` on its own `seq` as `base_seq`. The schema-age rule runs first, so a refusal
    /// sends nothing. `stale_seq` re-reads and diffs instead of failing.
    pub fn write(&mut self, doc: &Document) -> Result<Written, SessionError> {
        for message in document::write_messages(&self.info, doc)? {
            let Message::Result { code, seq, path } = self.link.ask(&message)? else {
                return Err(SessionError::BadReply("a write step answered without RESULT"));
            };
            match code {
                RESULT_OK if matches!(message, Message::CfgCommit) => return Ok(Written::Saved { seq }),
                RESULT_OK => {}
                RESULT_STALE_SEQ => return self.stale(doc),
                _ => return Err(SessionError::Rejected { code, path }),
            }
        }
        Err(SessionError::BadReply("the write ended without a commit RESULT"))
    }

    fn stale(&mut self, mine: &Document) -> Result<Written, SessionError> {
        let pad = self.read()?;
        // Bytes that are not JSON (an empty pad, a torn store) diff as null: one change at the root.
        let theirs = serde_json::from_slice(&pad.bytes).unwrap_or(Value::Null);
        let mine: Value = serde_json::from_slice(&mine.to_bytes()).expect("a Document serialises to JSON");
        let changes = changes(&theirs, &mine).into_iter().filter(|change| change.path != "seq").collect();
        Ok(Written::Stale { pad, changes })
    }
}

fn ask_info<P: Read + Write>(link: &mut Link<P>) -> Result<Info, SessionError> {
    match link.ask(&Message::InfoGet)? {
        Message::Info(info) => Ok(info),
        _ => Err(SessionError::BadReply("INFO_GET answered without INFO")),
    }
}

fn schemas(info: &Info) -> RangeInclusive<u64> {
    u64::from(info.schema_min)..=u64::from(info.schema_max)
}
