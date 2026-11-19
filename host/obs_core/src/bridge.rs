// SPDX-License-Identifier: MIT
//! In-memory CDC port. No `serialport` and no websocket.

use crate::protocol::{
    encode, encode_bind, encode_hello_ack, encode_page, pad_event, Link, PadEvent, PageView, HEARTBEAT, INPUT, NOTICE,
    PROFILE,
};

pub trait Port {
    fn read(&mut self, dst: &mut [u8]) -> usize;
    fn write(&mut self, src: &[u8]) -> usize;
}

#[derive(Debug, Default)]
pub struct MemPort {
    inbound: Vec<u8>,
    cursor: usize,
    pub outbound: Vec<u8>,
}

impl MemPort {
    pub fn push_in(&mut self, bytes: &[u8]) {
        self.inbound.extend_from_slice(bytes);
    }
}

impl Port for MemPort {
    fn read(&mut self, dst: &mut [u8]) -> usize {
        let rest = self.inbound.len().saturating_sub(self.cursor);
        let n = rest.min(dst.len());
        dst[..n].copy_from_slice(&self.inbound[self.cursor..self.cursor + n]);
        self.cursor += n;
        n
    }

    fn write(&mut self, src: &[u8]) -> usize {
        self.outbound.extend_from_slice(src);
        src.len()
    }
}

pub struct Bridge<P: Port> {
    port: P,
    link: Link,
    sent_ack: bool,
}

impl<P: Port> Bridge<P> {
    pub fn new(port: P) -> Self {
        Self { port, link: Link::default(), sent_ack: false }
    }

    pub fn port(&self) -> &P {
        &self.port
    }

    pub fn poll_pad(&mut self) -> Vec<PadEvent> {
        let mut buf = [0u8; 64];
        let mut events = Vec::new();
        loop {
            let n = self.port.read(&mut buf);
            if n == 0 {
                break;
            }
            for frame in self.link.feed(&buf[..n]) {
                if let Some(event) = pad_event(&frame) {
                    events.push(event);
                }
            }
        }
        events
    }

    pub fn hello_ack(&mut self) -> bool {
        self.write_host(encode_hello_ack(1))
    }

    pub fn heartbeat(&mut self) -> bool {
        self.write_host(encode(HEARTBEAT, &[]))
    }

    pub fn bind(&mut self, state: u8, port: u16, host: &str) -> bool {
        self.write_host(encode_bind(state, port, host))
    }

    pub fn page(&mut self, view: &PageView) -> bool {
        self.write_host(encode_page(view))
    }

    pub fn profile(&mut self, name: &str) -> bool {
        self.write_host(text_frame(PROFILE, name, 24))
    }

    pub fn input(&mut self, db: i8, muted: bool, name: &str) -> bool {
        let name = crate::protocol::ascii_field(name, 24);
        let mut payload = vec![db as u8, u8::from(muted), u8::try_from(name.len()).unwrap_or(0)];
        payload.extend_from_slice(name.as_bytes());
        self.write_host(encode(INPUT, &payload))
    }

    pub fn notice(&mut self, text: &str) -> bool {
        self.write_host(text_frame(NOTICE, text, 32))
    }

    fn write_host(&mut self, frame: Option<Vec<u8>>) -> bool {
        let Some(bytes) = frame else {
            return false;
        };
        if !self.sent_ack && bytes.get(2) != Some(&crate::protocol::HELLO_ACK) {
            return false;
        }
        if bytes.get(2) == Some(&crate::protocol::HELLO_ACK) {
            self.sent_ack = true;
        }
        self.port.write(&bytes) == bytes.len()
    }
}

fn text_frame(kind: u8, text: &str, max: usize) -> Option<Vec<u8>> {
    let text = crate::protocol::ascii_field(text, max);
    if text.is_empty() && kind == PROFILE {
        return None;
    }
    let mut payload = vec![u8::try_from(text.len()).ok()?];
    payload.extend_from_slice(text.as_bytes());
    encode(kind, &payload)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::{encode, PageView, SlotView, KEY};

    fn empty_page() -> PageView {
        PageView {
            page: 0,
            page_count: 1,
            studio: false,
            streaming: false,
            recording: false,
            slots: (0..9).map(|_| SlotView { occupied: false, program: false, name: String::new() }).collect(),
            notice: None,
        }
    }

    #[test]
    fn page_before_ack_writes_nothing_and_password_stays_out() {
        let mut bridge = Bridge::new(MemPort::default());
        assert!(!bridge.page(&empty_page()));
        assert!(bridge.port().outbound.is_empty());
        assert!(bridge.hello_ack());
        assert!(bridge.bind(3, 4455, "127.0.0.1"));
        let out = &bridge.port().outbound;
        assert!(!out.windows(10).any(|w| w == b"replace-me"));
        assert!(!out.windows(8).any(|w| w == b"password"));
        let key = encode(KEY, &[3, 1]).unwrap();
        bridge.port.push_in(&key);
        assert_eq!(bridge.poll_pad(), vec![PadEvent::Key { index: 3, down: true }]);
    }

    #[test]
    fn inbound_page_view_before_ack_is_not_a_pad_event() {
        let page = encode(
            crate::protocol::PAGE_VIEW,
            &[0, 1, 0].into_iter().chain(std::iter::repeat(0u8).take(18)).collect::<Vec<_>>(),
        )
        .unwrap();
        let mut bridge = Bridge::new(MemPort::default());
        bridge.port.push_in(&page);
        assert!(bridge.poll_pad().is_empty());
    }
}
