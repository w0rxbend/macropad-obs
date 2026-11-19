// SPDX-License-Identifier: MIT
//! CDC frames. Same bytes as `firmware/link.c`. BIND has no password field.

use serde::{Deserialize, Serialize};

pub const USB_VID: u16 = 0x1209;
pub const USB_PID: u16 = 0x4F42;

pub const SOF: u8 = 0xA5;
pub const VERSION: u8 = 0x01;
pub const MAX_PAYLOAD: usize = 240;

pub const HELLO: u8 = 0x01;
pub const KEY: u8 = 0x02;
pub const KNOB: u8 = 0x03;
pub const PAGE: u8 = 0x04;
pub const HELLO_ACK: u8 = 0x10;
pub const HEARTBEAT: u8 = 0x11;
pub const BIND: u8 = 0x12;
pub const PROFILE: u8 = 0x13;
pub const PAGE_VIEW: u8 = 0x14;
pub const INPUT: u8 = 0x15;
pub const NOTICE: u8 = 0x16;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Frame {
    pub kind: u8,
    pub payload: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum PadEvent {
    Hello { proto: u8, keys: u8, features: u16 },
    Key { index: u8, down: bool },
    Knob { detents: i8 },
    Page { delta: i8 },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SlotView {
    pub occupied: bool,
    pub program: bool,
    pub name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PageView {
    pub page: u8,
    pub page_count: u8,
    pub studio: bool,
    pub streaming: bool,
    pub recording: bool,
    pub slots: Vec<SlotView>,
    pub notice: Option<String>,
}

#[derive(Default)]
pub struct Link {
    buf: Vec<u8>,
    acked: bool,
    unknown: u32,
    rejected: u32,
}

impl Link {
    pub fn session_reset(&mut self) {
        self.buf.clear();
        self.acked = false;
    }

    pub fn acked(&self) -> bool {
        self.acked
    }

    pub fn unknown_count(&self) -> u32 {
        self.unknown
    }

    pub fn rejected_count(&self) -> u32 {
        self.rejected
    }

    pub fn feed(&mut self, data: &[u8]) -> Vec<Frame> {
        self.buf.extend_from_slice(data);
        let mut frames = Vec::new();
        loop {
            if self.buf.first().copied() != Some(SOF) {
                if self.buf.is_empty() {
                    break;
                }
                self.buf.remove(0);
                continue;
            }
            if self.buf.len() < 5 {
                break;
            }
            if self.buf[1] != VERSION {
                self.buf.remove(0);
                continue;
            }
            let length = usize::from(u16::from_le_bytes([self.buf[3], self.buf[4]]));
            if length > MAX_PAYLOAD {
                self.buf.remove(0);
                continue;
            }
            let total = 5 + length + 2;
            if self.buf.len() < total {
                break;
            }
            let got = u16::from_le_bytes([self.buf[total - 2], self.buf[total - 1]]);
            if got != crc16_modbus(&self.buf[1..5 + length]) {
                self.buf.remove(0);
                continue;
            }
            let kind = self.buf[2];
            if is_host(kind) && !self.acked && kind != HELLO_ACK {
                self.rejected += 1;
                self.buf.drain(..total);
                continue;
            }
            if !is_known(kind) {
                self.unknown += 1;
                self.buf.drain(..total);
                continue;
            }
            if kind == HELLO_ACK {
                self.acked = true;
            }
            let payload = self.buf[5..5 + length].to_vec();
            self.buf.drain(..total);
            frames.push(Frame { kind, payload });
        }
        frames
    }
}

pub fn crc16_modbus(data: &[u8]) -> u16 {
    let mut crc = 0xFFFFu16;
    for byte in data {
        crc ^= u16::from(*byte);
        for _ in 0..8 {
            if crc & 1 == 1 {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    crc
}

pub fn encode(kind: u8, payload: &[u8]) -> Option<Vec<u8>> {
    if payload.len() > MAX_PAYLOAD {
        return None;
    }
    let length = u16::try_from(payload.len()).ok()?;
    let mut out = Vec::with_capacity(7 + payload.len());
    out.push(SOF);
    out.push(VERSION);
    out.push(kind);
    out.extend_from_slice(&length.to_le_bytes());
    out.extend_from_slice(payload);
    let crc = crc16_modbus(&out[1..]);
    out.extend_from_slice(&crc.to_le_bytes());
    Some(out)
}

pub fn pad_event(frame: &Frame) -> Option<PadEvent> {
    let p = &frame.payload;
    match frame.kind {
        HELLO if p.len() == 4 => {
            Some(PadEvent::Hello { proto: p[0], keys: p[1], features: u16::from_le_bytes([p[2], p[3]]) })
        }
        KEY if p.len() == 2 => Some(PadEvent::Key { index: p[0], down: p[1] != 0 }),
        KNOB if p.len() == 1 => Some(PadEvent::Knob { detents: p[0] as i8 }),
        PAGE if p.len() == 1 => Some(PadEvent::Page { delta: p[0] as i8 }),
        _ => None,
    }
}

pub fn encode_bind(state: u8, port: u16, host: &str) -> Option<Vec<u8>> {
    let bytes = host.as_bytes();
    if bytes.is_empty() || bytes.len() > 48 || !bytes.iter().all(|b| (0x20..=0x7E).contains(b)) {
        return None;
    }
    let mut payload = Vec::with_capacity(4 + bytes.len());
    payload.push(state);
    payload.extend_from_slice(&port.to_le_bytes());
    payload.push(u8::try_from(bytes.len()).ok()?);
    payload.extend_from_slice(bytes);
    encode(BIND, &payload)
}

pub fn encode_page(view: &PageView) -> Option<Vec<u8>> {
    if view.slots.len() != 9 {
        return None;
    }
    let mut payload = vec![view.page, view.page_count, view_flags(view)];
    for slot in &view.slots {
        let name = ascii_field(&slot.name, 16);
        let mut flags = 0u8;
        if slot.occupied {
            flags |= 1;
        }
        if slot.program {
            flags |= 2;
        }
        payload.push(flags);
        payload.push(u8::try_from(name.len()).ok()?);
        payload.extend_from_slice(name.as_bytes());
    }
    encode(PAGE_VIEW, &payload)
}

pub fn encode_hello_ack(proto: u8) -> Option<Vec<u8>> {
    encode(HELLO_ACK, &[proto])
}

pub fn ascii_field(raw: &str, max_bytes: usize) -> String {
    let mut text = String::new();
    for ch in raw.chars() {
        if (' '..='~').contains(&ch) {
            text.push(ch);
        } else {
            text.push('?');
        }
    }
    if text.len() <= max_bytes {
        return text;
    }
    if max_bytes == 0 {
        return String::new();
    }
    let mut cut = text;
    cut.truncate(max_bytes - 1);
    cut.push('.');
    cut
}

fn view_flags(view: &PageView) -> u8 {
    let mut flags = 0u8;
    if view.studio {
        flags |= 1;
    }
    if view.streaming {
        flags |= 2;
    }
    if view.recording {
        flags |= 4;
    }
    flags
}

fn is_host(kind: u8) -> bool {
    (HELLO_ACK..=NOTICE).contains(&kind)
}

fn is_known(kind: u8) -> bool {
    (HELLO..=PAGE).contains(&kind) || is_host(kind)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn load_vector(name: &str) -> Vec<u8> {
        let text = include_str!("../../firmware/test/vectors.txt");
        for line in text.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let mut parts = line.split_whitespace();
            if parts.next() != Some(name) {
                continue;
            }
            return parts.map(|hex| u8::from_str_radix(hex, 16).expect("vector hex")).collect();
        }
        panic!("missing vector {name}");
    }

    #[test]
    fn crc_check_value_and_key_vector() {
        assert_eq!(crc16_modbus(b"123456789"), 0x4B37);
        let raw = load_vector("key_3_down");
        assert_eq!(raw, vec![0xA5, 0x01, 0x02, 0x02, 0x00, 0x03, 0x01, 0xB8, 0x82]);
        assert_eq!(encode(KEY, &[0x03, 0x01]).unwrap(), raw);
        let mut link = Link::default();
        let frames = link.feed(&raw);
        assert_eq!(frames.len(), 1);
        assert_eq!(pad_event(&frames[0]), Some(PadEvent::Key { index: 3, down: true }));
    }

    #[test]
    fn bind_vector_has_no_secret() {
        let raw = load_vector("bind_loopback");
        let encoded = encode_bind(3, 4455, "127.0.0.1").unwrap();
        assert_eq!(encoded, raw);
        let secret = b"replace-me";
        assert!(!encoded.windows(secret.len()).any(|w| w == secret));
        assert!(!encoded.windows(8).any(|w| w == b"password"));
    }

    #[test]
    fn page_view_rejected_until_hello_ack_and_again_after_reset() {
        let page = load_vector("page_view_empty");
        let ack = load_vector("hello_ack");
        let mut link = Link::default();
        link.session_reset();
        assert!(link.feed(&page).is_empty());
        assert!(!link.acked());
        assert_eq!(link.rejected_count(), 1);
        let frames = link.feed(&ack);
        assert_eq!(frames[0].kind, HELLO_ACK);
        assert!(link.acked());
        assert_eq!(link.feed(&page)[0].kind, PAGE_VIEW);
        link.session_reset();
        assert!(!link.acked());
        assert!(link.feed(&page).is_empty());
    }

    #[test]
    fn bad_crc_resyncs_onto_the_next_key() {
        let mut buf = load_vector("key_bad_crc");
        buf.extend(load_vector("key_3_down"));
        let frames = Link::default().feed(&buf);
        assert_eq!(pad_event(&frames[0]), Some(PadEvent::Key { index: 3, down: true }));
    }

    #[test]
    fn unknown_good_frame_does_not_clear_ack() {
        let ack = encode(HELLO_ACK, &[0x01]).unwrap();
        let unknown = encode(0x7F, &[0x00]).unwrap();
        let mut link = Link::default();
        assert_eq!(link.feed(&ack).len(), 1);
        assert!(link.feed(&unknown).is_empty());
        assert_eq!(link.unknown_count(), 1);
        assert!(link.acked());
    }

    #[test]
    fn shared_vectors_roundtrip() {
        assert_eq!(encode(HELLO, &[0x01, 0x09, 0x00, 0x00]).unwrap(), load_vector("hello"));
        assert_eq!(encode(HELLO_ACK, &[0x01]).unwrap(), load_vector("hello_ack"));
        assert_eq!(encode(HEARTBEAT, &[]).unwrap(), load_vector("heartbeat"));
        let mut payload = vec![0x00, 0x01, 0x00];
        payload.extend(std::iter::repeat(0).take(18));
        assert_eq!(encode(PAGE_VIEW, &payload).unwrap(), load_vector("page_view_empty"));
    }
}
