// SPDX-License-Identifier: MIT
//! One config session (spec 8.2): `INFO`, `CFG_READ` until total, edit with unknown fields kept,
//! `CFG_BEGIN(base_seq)`, the chunks, `CFG_COMMIT`. A stale `seq` re-reads and gives the diff.

use std::fmt;
use std::io::{Read, Write};
use std::ops::RangeInclusive;
use std::time::Duration;

use obs_core::document::{self, Document, Rejected, WriteRefused};
use obs_core::protocol::{Info, Message, CFG_DATA_MAX, RESULT_OK, RESULT_STALE_SEQ, UUID_LEN};
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

/// One `OBS_ITEM` as the pad sent it: the 16 UUID bytes and the name bytes, unchecked.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObsItem {
    pub uuid: [u8; UUID_LEN],
    pub name: Vec<u8>,
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

    /// `OBS_LIST` from index 0 until the `total` of the first `OBS_ITEM`. Each reply must answer the
    /// list and index asked and keep that `total` (trust boundary): a list that changed mid-read
    /// is refused, and the caller asks again.
    pub fn obs_list(&mut self, list: u8) -> Result<Vec<ObsItem>, SessionError> {
        let mut items = Vec::new();
        let mut total = None;
        let mut index = 0u16;
        while total.is_none_or(|total| index < total) {
            let Message::ObsItem { list: got, index: at, total: count, uuid, name } =
                self.link.ask(&Message::ObsList { list, index })?
            else {
                return Err(SessionError::BadReply("OBS_LIST answered without OBS_ITEM"));
            };
            if (got, at) != (list, index) || *total.get_or_insert(count) != count {
                return Err(SessionError::BadReply("OBS_ITEM does not continue the list"));
            }
            if index < count {
                items.push(ObsItem { uuid, name });
            }
            index = index.saturating_add(1);
        }
        Ok(items)
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

pub(crate) fn schemas(info: &Info) -> RangeInclusive<u64> {
    u64::from(info.schema_min)..=u64::from(info.schema_max)
}

#[cfg(test)]
mod tests {
    use super::*;
    use obs_core::protocol::{self, Pulled, Size, LIST_SCENES};
    use obs_core::LinkRx;
    use std::cell::RefCell;
    use std::io::{self, ErrorKind};
    use std::rc::Rc;

    fn info() -> Info {
        Info {
            proto: 2,
            obs_password_set: false,
            wifi_psk_set: false,
            schema_min: 1,
            schema_max: 1,
            max_doc_bytes: 16384,
            keys: 9,
            buttons: 4,
            knobs: 3,
            main_display: Size { width: 320, height: 480 },
            strip_display: Size { width: 142, height: 428 },
            capabilities: 0,
            board_rev: 1,
            git_hash: [0; 4],
            unique_id: [0; 6],
            fw_version: "0.2.0".into(),
        }
    }

    /// A pad that answers `INFO_GET`, and `OBS_LIST` with `item(list, index)`.
    struct ListPad {
        item: fn(u8, u16) -> Message,
        asked: Rc<RefCell<Vec<u16>>>,
        rx: LinkRx,
        pending: Vec<u8>,
    }

    impl ListPad {
        /// The pad, and the indexes it was asked for.
        fn new(item: fn(u8, u16) -> Message) -> (Self, Rc<RefCell<Vec<u16>>>) {
            let asked = Rc::new(RefCell::new(Vec::new()));
            (Self { item, asked: Rc::clone(&asked), rx: LinkRx::default(), pending: Vec::new() }, asked)
        }
    }

    impl Write for ListPad {
        fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
            self.rx.push(buf);
            while let Some(Pulled::Frame(frame)) = self.rx.pull() {
                let reply = match Message::decode(&frame) {
                    Some(Message::InfoGet) => Message::Info(info()),
                    Some(Message::ObsList { list, index }) => {
                        self.asked.borrow_mut().push(index);
                        (self.item)(list, index)
                    }
                    other => panic!("the session sent {other:?}"),
                };
                let frame = reply.encode(frame.id).expect("reply encodes");
                self.pending.extend(protocol::encode(&frame).expect("reply fits"));
            }
            Ok(buf.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl Read for ListPad {
        fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
            if self.pending.is_empty() {
                return Err(ErrorKind::TimedOut.into());
            }
            let got = self.pending.len().min(buf.len());
            buf[..got].copy_from_slice(&self.pending[..got]);
            self.pending.drain(..got);
            Ok(got)
        }
    }

    fn item(list: u8, index: u16, total: u16) -> Message {
        Message::ObsItem { list, index, total, uuid: [1; UUID_LEN], name: format!("Scene {index}").into_bytes() }
    }

    #[test]
    fn obs_list_asks_each_index_until_the_total() {
        let (pad, asked) = ListPad::new(|list, index| item(list, index, 3));
        let items = Session::start(pad).expect("session").obs_list(LIST_SCENES).expect("list");
        assert_eq!(
            items.iter().map(|item| item.name.as_slice()).collect::<Vec<_>>(),
            [b"Scene 0", b"Scene 1", b"Scene 2"]
        );
        assert_eq!(*asked.borrow(), [0, 1, 2]);
    }

    #[test]
    fn an_empty_list_is_one_request() {
        let (pad, asked) = ListPad::new(|list, index| item(list, index, 0));
        assert_eq!(Session::start(pad).expect("session").obs_list(LIST_SCENES).expect("list"), []);
        assert_eq!(*asked.borrow(), [0]);
    }

    #[test]
    fn a_list_that_changes_mid_read_is_refused() {
        let (pad, _) = ListPad::new(|list, index| item(list, index, 3 + index));
        let listed = Session::start(pad).expect("session").obs_list(LIST_SCENES);
        assert!(matches!(listed, Err(SessionError::BadReply(_))));
    }

    #[test]
    fn an_item_for_another_index_or_list_is_refused() {
        for answer in [|list, _| item(list, 7, 9), |_, index| item(LIST_SCENES + 1, index, 9)] {
            let (pad, _) = ListPad::new(answer);
            let listed = Session::start(pad).expect("session").obs_list(LIST_SCENES);
            assert!(matches!(listed, Err(SessionError::BadReply(_))));
        }
    }
}
