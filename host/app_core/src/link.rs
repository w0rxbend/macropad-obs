// SPDX-License-Identifier: MIT
//! Request and reply over the CDC link (spec 8.2): one reply per id, retry after 1 s.

use std::fmt;
use std::io::{self, ErrorKind, Read, Write};
use std::time::{Duration, Instant};

use obs_core::protocol::{self, Message, Pulled, INPUT, STATUS};
use obs_core::LinkRx;

/// How long one attempt waits for its reply before the same frame goes again.
pub const REPLY_WAIT: Duration = Duration::from_secs(1);
/// Sends of one request, the first included.
pub const ATTEMPTS: u32 = 3;

#[derive(Debug)]
pub enum LinkError {
    Io(io::Error),
    /// No reply after `ATTEMPTS` sends.
    Timeout,
    /// The codec refuses the message: a field out of its range. The caller broke its contract.
    Unencodable,
    /// A frame with the request's id that breaks its type's rules (trust boundary).
    BadReply {
        kind: u8,
    },
}

impl fmt::Display for LinkError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(err) => write!(f, "pad link: {err}"),
            Self::Timeout => write!(f, "the pad did not answer after {ATTEMPTS} tries"),
            Self::Unencodable => f.write_str("the app built a message the codec refuses"),
            Self::BadReply { kind } => write!(f, "the pad sent a malformed reply of type 0x{kind:02X}"),
        }
    }
}

impl std::error::Error for LinkError {}

impl From<io::Error> for LinkError {
    fn from(err: io::Error) -> Self {
        Self::Io(err)
    }
}

/// The app's end of the link. `port` reads with a short timeout, as `discover::open` sets it.
pub struct Link<P> {
    port: P,
    rx: LinkRx,
    next_id: u8,
}

impl<P: Read + Write> Link<P> {
    pub fn new(port: P) -> Self {
        Self { port, rx: LinkRx::default(), next_id: 1 }
    }

    /// Sends `message` and returns the pad's reply to it. Frames with another id, `STATUS` and
    /// `INPUT` are passed over. A commit is sent once and waits all attempts long: a second commit
    /// after a lost reply would not repeat the first.
    pub fn ask(&mut self, message: &Message) -> Result<Message, LinkError> {
        let id = self.take_id();
        let frame = message.encode(id).ok_or(LinkError::Unencodable)?;
        let bytes = protocol::encode(&frame).ok_or(LinkError::Unencodable)?;
        let (sends, wait) =
            if matches!(message, Message::CfgCommit) { (1, REPLY_WAIT * ATTEMPTS) } else { (ATTEMPTS, REPLY_WAIT) };
        for _ in 0..sends {
            self.port.write_all(&bytes)?;
            self.port.flush()?;
            if let Some(reply) = self.reply(id, Instant::now() + wait)? {
                return Ok(reply);
            }
        }
        Err(LinkError::Timeout)
    }

    /// Ids run 1..=255, so a late reply to an earlier request never matches the next one at once.
    fn take_id(&mut self) -> u8 {
        let id = self.next_id;
        self.next_id = self.next_id % u8::MAX + 1;
        id
    }

    /// The reply with `id`, or `None` once `deadline` passes.
    fn reply(&mut self, id: u8, deadline: Instant) -> Result<Option<Message>, LinkError> {
        loop {
            // A frame the codec refuses (`Pulled::Reply`) is a damaged reply: the retry asks again.
            while let Some(pulled) = self.rx.pull() {
                let Pulled::Frame(frame) = pulled else { continue };
                if frame.id == id && frame.kind != STATUS && frame.kind != INPUT {
                    return Message::decode(&frame).map(Some).ok_or(LinkError::BadReply { kind: frame.kind });
                }
            }
            if Instant::now() >= deadline {
                return Ok(None);
            }
            self.fill()?;
        }
    }

    /// Buffers what the port gives within its read timeout.
    fn fill(&mut self) -> Result<(), LinkError> {
        let mut buf = [0u8; 512];
        match self.port.read(&mut buf) {
            Ok(got) => {
                self.rx.push(&buf[..got]);
                Ok(())
            }
            Err(err) if matches!(err.kind(), ErrorKind::TimedOut | ErrorKind::WouldBlock | ErrorKind::Interrupted) => {
                Ok(())
            }
            Err(err) => Err(err.into()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use obs_core::protocol::{Frame, RESULT, RESULT_OK};
    use std::collections::VecDeque;

    /// A port that answers each write with the next canned reply bytes, or with silence.
    struct Scripted {
        replies: VecDeque<Option<Vec<u8>>>,
        pending: Vec<u8>,
        writes: usize,
    }

    impl Scripted {
        fn new(replies: Vec<Option<Vec<u8>>>) -> Self {
            Self { replies: replies.into(), pending: Vec::new(), writes: 0 }
        }
    }

    impl Write for Scripted {
        fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
            self.writes += 1;
            if let Some(Some(reply)) = self.replies.pop_front() {
                self.pending.extend(reply);
            }
            Ok(buf.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl Read for Scripted {
        fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
            if self.pending.is_empty() {
                std::thread::sleep(Duration::from_millis(5));
                return Err(ErrorKind::TimedOut.into());
            }
            let got = self.pending.len().min(buf.len());
            buf[..got].copy_from_slice(&self.pending[..got]);
            self.pending.drain(..got);
            Ok(got)
        }
    }

    fn wire(kind: u8, id: u8, payload: Vec<u8>) -> Vec<u8> {
        protocol::encode(&Frame { kind, id, payload }).expect("frame fits")
    }

    fn ok_result(id: u8) -> Vec<u8> {
        wire(RESULT, id, vec![RESULT_OK, 7, 0, 0, 0])
    }

    #[test]
    fn a_reply_with_another_id_or_a_status_frame_is_passed_over() {
        let status = wire(STATUS, 1, vec![0, 0, 0, 0, 0, 0, 0]);
        let reply = [status, ok_result(9), ok_result(1)].concat();
        let mut link = Link::new(Scripted::new(vec![Some(reply)]));
        let got = link.ask(&Message::CfgCommit).expect("reply");
        assert_eq!(got, Message::Result { code: RESULT_OK, seq: 7, path: String::new() });
    }

    #[test]
    fn silence_resends_the_same_frame_after_one_wait() {
        let mut link = Link::new(Scripted::new(vec![None, Some(ok_result(1))]));
        let started = Instant::now();
        let got = link.ask(&Message::CfgChunk { offset: 0, bytes: vec![b'{'] }).expect("reply to the second send");
        assert_eq!(got, Message::Result { code: RESULT_OK, seq: 7, path: String::new() });
        assert!(started.elapsed() >= REPLY_WAIT, "the second send waits out the first");
        assert_eq!(link.port.writes, 2);
    }

    #[test]
    fn a_commit_is_never_sent_twice() {
        let mut link = Link::new(Scripted::new(vec![None, None, None]));
        assert!(matches!(link.ask(&Message::CfgCommit), Err(LinkError::Timeout)));
        assert_eq!(link.port.writes, 1);
    }

    #[test]
    fn a_malformed_reply_with_the_id_is_an_error() {
        let mut link = Link::new(Scripted::new(vec![Some(wire(RESULT, 1, vec![RESULT_OK]))]));
        assert!(matches!(link.ask(&Message::InfoGet), Err(LinkError::BadReply { kind: RESULT })));
    }
}
