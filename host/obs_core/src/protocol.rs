// SPDX-License-Identifier: MIT
//! CDC frame codec, protocol v2. Same bytes as `firmware/core/link.c`. Wire format: `docs/protocol.md`.

use std::fmt;

use serde::{Deserialize, Serialize};

pub const USB_VID: u16 = 0x1209;
pub const USB_PID: u16 = 0x4F42;

pub const SOF: u8 = 0xA5;
pub const VERSION: u8 = 0x02;
pub const HEADER_LEN: usize = 6;
pub const CRC_LEN: usize = 2;
pub const MAX_PAYLOAD: usize = 240;
pub const MAX_FRAME: usize = HEADER_LEN + MAX_PAYLOAD + CRC_LEN;

/// Pad-to-app types have bit 7 set. The frame codec sends `NOTICE` and `RESULT` by itself.
pub const INFO_GET: u8 = 0x01;
pub const CFG_READ: u8 = 0x02;
pub const CFG_BEGIN: u8 = 0x03;
pub const CFG_CHUNK: u8 = 0x04;
pub const CFG_COMMIT: u8 = 0x05;
pub const SET_CREDENTIAL: u8 = 0x06;
pub const CLEAR_CREDENTIALS: u8 = 0x07;
pub const OBS_LIST: u8 = 0x08;
pub const FACTORY_RESET: u8 = 0x09;
pub const BOOTLOADER: u8 = 0x0A;
pub const NOTICE: u8 = 0x80;
pub const RESULT: u8 = 0x81;
pub const INFO: u8 = 0x82;
pub const CFG_DATA: u8 = 0x83;
pub const CRED_STATUS: u8 = 0x84;
pub const STATUS: u8 = 0x85;
pub const OBS_ITEM: u8 = 0x86;
pub const INPUT: u8 = 0x87;

/// Largest byte run of `CFG_CHUNK` and `CFG_DATA`: the payload cap less their fixed fields.
pub const CFG_CHUNK_MAX: usize = MAX_PAYLOAD - 2;
pub const CFG_DATA_MAX: usize = MAX_PAYLOAD - 8;
pub const PATH_MAX: usize = 48;
pub const FW_VERSION_MAX: usize = 32;
/// Longest secret of `SET_CREDENTIAL`: the payload cap less the kind byte (spec 8.2).
pub const CREDENTIAL_MAX: usize = MAX_PAYLOAD - 1;
pub const WIFI_PASSPHRASE_MIN: usize = 8;
pub const WIFI_PSK_HEX_LEN: usize = 64;
pub const UUID_LEN: usize = 16;
/// ASCII "WIPE" and "BOOT" on the wire. `FACTORY_RESET` and `BOOTLOADER` carry nothing else.
pub const FACTORY_RESET_MAGIC: u32 = 0x4550_4957;
pub const BOOTLOADER_MAGIC: u32 = 0x544F_4F42;

const INFO_OBS_PASSWORD_SET: u8 = 0x01;
const INFO_WIFI_PSK_SET: u8 = 0x02;
const CFG_BEGIN_TRY_ONLY: u8 = 0x01;

/// First payload byte of `RESULT` (spec 8.2).
pub const RESULT_OK: u8 = 0;
pub const RESULT_BUSY: u8 = 1;
pub const RESULT_STALE_SEQ: u8 = 2;
pub const RESULT_BAD_CRC: u8 = 3;
pub const RESULT_TOO_BIG: u8 = 4;
pub const RESULT_INVALID: u8 = 5;

/// First payload byte of `SET_CREDENTIAL` (spec 8.2).
pub const CREDENTIAL_OBS_PASSWORD: u8 = 1;
pub const CREDENTIAL_WIFI_PASSPHRASE: u8 = 2;

/// The one payload byte of `CRED_STATUS` (spec 8.2).
pub const CRED_OK: u8 = 0;
pub const CRED_BAD_KIND: u8 = 1;
pub const CRED_BAD_LEN: u8 = 2;
pub const CRED_BAD_VALUE: u8 = 3;
pub const CRED_STORE_FAIL: u8 = 4;

/// `STATUS` OBS state. Idle: not trying, no Wi-Fi or no URL.
pub const OBS_IDLE: u8 = 0;
pub const OBS_CONNECTING: u8 = 1;
pub const OBS_REFUSED: u8 = 2;
pub const OBS_AUTH_FAILED: u8 = 3;
pub const OBS_UP: u8 = 4;

/// `STATUS` Wi-Fi state (spec 8.2).
pub const WIFI_NO_SSID: u8 = 0;
pub const WIFI_CONNECTING: u8 = 1;
pub const WIFI_BAD_KEY: u8 = 2;
pub const WIFI_NO_AP: u8 = 3;
pub const WIFI_UP: u8 = 4;

/// Which OBS list an `OBS_LIST` request and its `OBS_ITEM` reply are about.
pub const LIST_SCENES: u8 = 1;
pub const LIST_INPUTS: u8 = 2;
pub const LIST_TRANSITIONS: u8 = 3;

/// Which control an `INPUT` event comes from.
pub const INPUT_KEY: u8 = 1;
pub const INPUT_BUTTON: u8 = 2;
pub const INPUT_KNOB_PUSH: u8 = 3;
pub const INPUT_KNOB_TURN: u8 = 4;

const VERSION_AT: usize = 1;
const TYPE_AT: usize = 2;
const ID_AT: usize = 3;
const LENGTH_AT: usize = 4;
const V2_ONLY: &[u8] = b"protocol v2 only";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Frame {
    pub kind: u8,
    pub id: u8,
    pub payload: Vec<u8>,
}

/// One step of the pull parser.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Pulled {
    /// A frame that passed its CRC.
    Frame(Frame),
    /// A frame was refused. This is the reply the receiver must send.
    Reply(Frame),
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
pub struct LinkRx {
    buf: Vec<u8>,
}

impl LinkRx {
    pub fn push(&mut self, data: &[u8]) {
        self.buf.extend_from_slice(data);
    }

    /// Takes the next frame or reply out of the buffer. `None` means no whole frame is buffered.
    /// A version other than 2 gets `NOTICE`, a length above 240 gets `RESULT` too_big, a bad CRC
    /// gets `RESULT` bad_crc. Each refusal drops the SOF byte only and scans on.
    pub fn pull(&mut self) -> Option<Pulled> {
        let sof = self.buf.iter().position(|byte| *byte == SOF).unwrap_or(self.buf.len());
        self.buf.drain(..sof);
        if *self.buf.get(VERSION_AT)? != VERSION {
            return Some(self.refuse(Frame { kind: NOTICE, id: 0, payload: V2_ONLY.to_vec() }));
        }
        if self.buf.len() < HEADER_LEN {
            return None;
        }
        let id = self.buf[ID_AT];
        let length = usize::from(u16::from_le_bytes([self.buf[LENGTH_AT], self.buf[LENGTH_AT + 1]]));
        if length > MAX_PAYLOAD {
            return Some(self.refuse(result(id, RESULT_TOO_BIG)));
        }
        let crc_at = HEADER_LEN + length;
        let stored = self.buf.get(crc_at..crc_at + CRC_LEN)?;
        if u16::from_le_bytes([stored[0], stored[1]]) != crc16_modbus(&self.buf[VERSION_AT..crc_at]) {
            return Some(self.refuse(result(id, RESULT_BAD_CRC)));
        }
        let frame = Frame { kind: self.buf[TYPE_AT], id, payload: self.buf[HEADER_LEN..crc_at].to_vec() };
        self.buf.drain(..crc_at + CRC_LEN);
        Some(Pulled::Frame(frame))
    }

    fn refuse(&mut self, reply: Frame) -> Pulled {
        self.buf.remove(0);
        Pulled::Reply(reply)
    }
}

/// A `RESULT` from the codec stores nothing: seq 0 and no path follow the code byte.
fn result(id: u8, code: u8) -> Frame {
    Frame { kind: RESULT, id, payload: vec![code, 0, 0, 0, 0] }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Size {
    pub width: u16,
    pub height: u16,
}

/// The two credential fields are one bit each on the wire: set or not set, nothing else (R1).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Info {
    pub proto: u8,
    pub obs_password_set: bool,
    pub wifi_psk_set: bool,
    pub schema_min: u16,
    pub schema_max: u16,
    pub max_doc_bytes: u16,
    pub keys: u8,
    pub buttons: u8,
    pub knobs: u8,
    pub main_display: Size,
    pub strip_display: Size,
    pub capabilities: u32,
    pub board_rev: u8,
    pub git_hash: [u8; 4],
    pub unique_id: [u8; 6],
    /// Printable ASCII, 0..=`FW_VERSION_MAX` bytes.
    pub fw_version: String,
}

/// A credential on its way to the pad. `Debug` prints no byte of it: no log line carries a
/// secret (R1).
#[derive(Clone, PartialEq, Eq)]
pub struct Secret(pub Vec<u8>);

impl fmt::Debug for Secret {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("Secret(hidden)")
    }
}

/// One typed message of spec 8.2. Same rules as `link_msg_decode` in `firmware/core/link.c`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Message {
    InfoGet,
    /// `len` is 1..=`CFG_DATA_MAX`.
    CfgRead {
        offset: u16,
        len: u8,
    },
    CfgBegin {
        base_seq: u32,
        total: u16,
        crc32: u32,
        try_only: bool,
    },
    /// `bytes` is 1..=`CFG_CHUNK_MAX` long.
    CfgChunk {
        offset: u16,
        bytes: Vec<u8>,
    },
    CfgCommit,
    /// `code` is a `RESULT_*` value. `path` is printable ASCII, 0..=`PATH_MAX` bytes.
    Result {
        code: u8,
        seq: u32,
        path: String,
    },
    Info(Info),
    CfgData {
        seq: u32,
        total: u16,
        offset: u16,
        bytes: Vec<u8>,
    },
    /// `kind` is a `CREDENTIAL_*` value. `secret` is 1..=`CREDENTIAL_MAX` bytes.
    SetCredential {
        kind: u8,
        secret: Secret,
    },
    ClearCredentials,
    /// `list` is a `LIST_*` value.
    ObsList {
        list: u8,
        index: u16,
    },
    /// The codec checks the magic. The message has no field.
    FactoryReset,
    Bootloader,
    /// `code` is a `CRED_*` value.
    CredStatus {
        code: u8,
    },
    /// `rssi_dbm` is 0 and `ip` is 0.0.0.0 unless Wi-Fi is up. `ip` is IPv4 in network order.
    Status {
        obs_state: u8,
        wifi_state: u8,
        rssi_dbm: i8,
        ip: [u8; 4],
    },
    /// `total` 0: no item, nil UUID, no name. `name` is UTF-8 from OBS, not checked here.
    ObsItem {
        list: u8,
        index: u16,
        total: u16,
        uuid: [u8; UUID_LEN],
        name: Vec<u8>,
    },
    /// `value` is 1 down, 0 up. For `INPUT_KNOB_TURN` it is the detents, never 0.
    Input {
        source: u8,
        index: u8,
        value: i8,
    },
}

impl Message {
    /// Reads the payload of a frame that `LinkRx::pull` delivered. `None` for an unknown type and
    /// for a payload that breaks the type's rules. Trust boundary: every length and range is
    /// checked here.
    pub fn decode(frame: &Frame) -> Option<Self> {
        let mut reader = Reader(&frame.payload);
        let message = match frame.kind {
            INFO_GET => Self::InfoGet,
            CFG_READ => {
                let (offset, len) = (reader.u16()?, reader.u8()?);
                (1..=CFG_DATA_MAX).contains(&usize::from(len)).then_some(Self::CfgRead { offset, len })?
            }
            CFG_BEGIN => {
                let (base_seq, total, crc32, flags) = (reader.u32()?, reader.u16()?, reader.u32()?, reader.u8()?);
                let try_only = flag_bits(flags, CFG_BEGIN_TRY_ONLY)? != 0;
                Self::CfgBegin { base_seq, total, crc32, try_only }
            }
            CFG_CHUNK => {
                let (offset, bytes) = (reader.u16()?, reader.rest().to_vec());
                (!bytes.is_empty()).then_some(Self::CfgChunk { offset, bytes })?
            }
            CFG_COMMIT => Self::CfgCommit,
            RESULT => {
                let (code, seq) = (reader.u8().filter(|code| *code <= RESULT_INVALID)?, reader.u32()?);
                Self::Result { code, seq, path: reader.text(PATH_MAX)? }
            }
            INFO => Self::Info(Info::read(&mut reader)?),
            CFG_DATA => {
                let (seq, total, offset) = (reader.u32()?, reader.u16()?, reader.u16()?);
                Self::CfgData { seq, total, offset, bytes: reader.rest().to_vec() }
            }
            SET_CREDENTIAL => {
                let accepted = credential_status(frame) == CRED_OK;
                let (kind, secret) = (reader.u8()?, Secret(reader.rest().to_vec()));
                accepted.then_some(Self::SetCredential { kind, secret })?
            }
            CLEAR_CREDENTIALS => Self::ClearCredentials,
            OBS_LIST => Self::ObsList { list: reader.obs_list()?, index: reader.u16()? },
            FACTORY_RESET => (reader.u32()? == FACTORY_RESET_MAGIC).then_some(Self::FactoryReset)?,
            BOOTLOADER => (reader.u32()? == BOOTLOADER_MAGIC).then_some(Self::Bootloader)?,
            CRED_STATUS => Self::CredStatus { code: reader.u8().filter(|code| *code <= CRED_STORE_FAIL)? },
            STATUS => {
                let obs_state = reader.u8().filter(|state| *state <= OBS_UP)?;
                let wifi_state = reader.u8().filter(|state| *state <= WIFI_UP)?;
                Self::Status { obs_state, wifi_state, rssi_dbm: reader.i8()?, ip: reader.array()? }
            }
            OBS_ITEM => {
                let (list, index, total, uuid) = (reader.obs_list()?, reader.u16()?, reader.u16()?, reader.array()?);
                Self::ObsItem { list, index, total, uuid, name: reader.rest().to_vec() }
            }
            INPUT => {
                let (source, index, value) = (reader.u8()?, reader.u8()?, reader.i8()?);
                input_value_fits(source, value).then_some(Self::Input { source, index, value })?
            }
            _ => return None,
        };
        reader.0.is_empty().then_some(message)
    }

    /// Writes the message as a frame with the given id. `None` for what `decode` would refuse.
    pub fn encode(&self, id: u8) -> Option<Frame> {
        let mut payload = Vec::new();
        let kind = match self {
            Self::InfoGet => INFO_GET,
            Self::CfgRead { offset, len } => {
                payload.extend(offset.to_le_bytes());
                payload.push(*len);
                CFG_READ
            }
            Self::CfgBegin { base_seq, total, crc32, try_only } => {
                payload.extend(base_seq.to_le_bytes());
                payload.extend(total.to_le_bytes());
                payload.extend(crc32.to_le_bytes());
                payload.push(if *try_only { CFG_BEGIN_TRY_ONLY } else { 0 });
                CFG_BEGIN
            }
            Self::CfgChunk { offset, bytes } => {
                payload.extend(offset.to_le_bytes());
                payload.extend(bytes);
                CFG_CHUNK
            }
            Self::CfgCommit => CFG_COMMIT,
            Self::Result { code, seq, path } => {
                payload.push(*code);
                payload.extend(seq.to_le_bytes());
                payload.extend(path.as_bytes());
                RESULT
            }
            Self::Info(info) => {
                info.write(&mut payload);
                INFO
            }
            Self::CfgData { seq, total, offset, bytes } => {
                payload.extend(seq.to_le_bytes());
                payload.extend(total.to_le_bytes());
                payload.extend(offset.to_le_bytes());
                payload.extend(bytes);
                CFG_DATA
            }
            Self::SetCredential { kind, secret } => {
                payload.push(*kind);
                payload.extend(&secret.0);
                SET_CREDENTIAL
            }
            Self::ClearCredentials => CLEAR_CREDENTIALS,
            Self::ObsList { list, index } => {
                payload.push(*list);
                payload.extend(index.to_le_bytes());
                OBS_LIST
            }
            Self::FactoryReset => {
                payload.extend(FACTORY_RESET_MAGIC.to_le_bytes());
                FACTORY_RESET
            }
            Self::Bootloader => {
                payload.extend(BOOTLOADER_MAGIC.to_le_bytes());
                BOOTLOADER
            }
            Self::CredStatus { code } => {
                payload.push(*code);
                CRED_STATUS
            }
            Self::Status { obs_state, wifi_state, rssi_dbm, ip } => {
                payload.extend([*obs_state, *wifi_state]);
                payload.extend(rssi_dbm.to_le_bytes());
                payload.extend(ip);
                STATUS
            }
            Self::ObsItem { list, index, total, uuid, name } => {
                payload.push(*list);
                payload.extend(index.to_le_bytes());
                payload.extend(total.to_le_bytes());
                payload.extend(uuid);
                payload.extend(name);
                OBS_ITEM
            }
            Self::Input { source, index, value } => {
                payload.extend([*source, *index]);
                payload.extend(value.to_le_bytes());
                INPUT
            }
        };
        let frame = Frame { kind, id, payload };
        // The rules live in `decode` only: what was written must read back as `self`.
        (frame.payload.len() <= MAX_PAYLOAD && Self::decode(&frame).as_ref() == Some(self)).then_some(frame)
    }
}

impl Info {
    fn read(reader: &mut Reader) -> Option<Self> {
        let proto = reader.u8()?;
        let flags = flag_bits(reader.u8()?, INFO_OBS_PASSWORD_SET | INFO_WIFI_PSK_SET)?;
        Some(Self {
            proto,
            obs_password_set: flags & INFO_OBS_PASSWORD_SET != 0,
            wifi_psk_set: flags & INFO_WIFI_PSK_SET != 0,
            schema_min: reader.u16()?,
            schema_max: reader.u16()?,
            max_doc_bytes: reader.u16()?,
            keys: reader.u8()?,
            buttons: reader.u8()?,
            knobs: reader.u8()?,
            main_display: reader.size()?,
            strip_display: reader.size()?,
            capabilities: reader.u32()?,
            board_rev: reader.u8()?,
            git_hash: reader.array()?,
            unique_id: reader.array()?,
            fw_version: reader.text(FW_VERSION_MAX)?,
        })
    }

    fn write(&self, out: &mut Vec<u8>) {
        let obs_bit = if self.obs_password_set { INFO_OBS_PASSWORD_SET } else { 0 };
        let wifi_bit = if self.wifi_psk_set { INFO_WIFI_PSK_SET } else { 0 };
        out.extend([self.proto, obs_bit | wifi_bit]);
        out.extend(self.schema_min.to_le_bytes());
        out.extend(self.schema_max.to_le_bytes());
        out.extend(self.max_doc_bytes.to_le_bytes());
        out.extend([self.keys, self.buttons, self.knobs]);
        for size in [self.main_display, self.strip_display] {
            out.extend(size.width.to_le_bytes());
            out.extend(size.height.to_le_bytes());
        }
        out.extend(self.capabilities.to_le_bytes());
        out.push(self.board_rev);
        out.extend(self.git_hash);
        out.extend(self.unique_id);
        out.extend(self.fw_version.as_bytes());
    }
}

/// The status the pad answers to a `SET_CREDENTIAL` or `CLEAR_CREDENTIALS` frame, before it stores
/// or erases anything (spec 8.2). Call it for those two types only. It never gives `CRED_STORE_FAIL`:
/// only the store knows that. Same rules as `link_credential_check` in `firmware/core/link.c`.
pub fn credential_status(frame: &Frame) -> u8 {
    if frame.payload.len() > MAX_PAYLOAD {
        return CRED_BAD_LEN;
    }
    if frame.kind == CLEAR_CREDENTIALS {
        return if frame.payload.is_empty() { CRED_OK } else { CRED_BAD_LEN };
    }
    let Some((kind, secret)) = frame.payload.split_first() else {
        return CRED_BAD_LEN;
    };
    match (*kind, secret.len()) {
        (CREDENTIAL_OBS_PASSWORD | CREDENTIAL_WIFI_PASSPHRASE, 0) => CRED_BAD_LEN,
        (CREDENTIAL_OBS_PASSWORD, _) => CRED_OK,
        (CREDENTIAL_WIFI_PASSPHRASE, _) => wifi_passphrase_status(secret),
        _ => CRED_BAD_KIND,
    }
}

fn wifi_passphrase_status(text: &[u8]) -> u8 {
    let allowed = match text.len() {
        WIFI_PASSPHRASE_MIN..WIFI_PSK_HEX_LEN => printable(text),
        WIFI_PSK_HEX_LEN => text.iter().all(u8::is_ascii_hexdigit),
        _ => return CRED_BAD_LEN,
    };
    if allowed {
        CRED_OK
    } else {
        CRED_BAD_VALUE
    }
}

fn printable(text: &[u8]) -> bool {
    text.iter().all(|byte| (0x20..=0x7E).contains(byte))
}

/// A key, a button and a knob push are down (1) or up (0). A turn has at least one detent.
fn input_value_fits(source: u8, value: i8) -> bool {
    match source {
        INPUT_KEY | INPUT_BUTTON | INPUT_KNOB_PUSH => matches!(value, 0 | 1),
        INPUT_KNOB_TURN => value != 0,
        _ => false,
    }
}

/// `None` when a bit outside `known` is set: a reserved flag is refused, not ignored.
fn flag_bits(flags: u8, known: u8) -> Option<u8> {
    (flags & !known == 0).then_some(flags)
}

/// Payload cursor. Every read is `None` past the end.
struct Reader<'a>(&'a [u8]);

impl<'a> Reader<'a> {
    fn array<const N: usize>(&mut self) -> Option<[u8; N]> {
        let (head, tail) = self.0.split_first_chunk::<N>()?;
        self.0 = tail;
        Some(*head)
    }

    fn u8(&mut self) -> Option<u8> {
        self.array().map(|[byte]| byte)
    }

    fn i8(&mut self) -> Option<i8> {
        self.array().map(i8::from_le_bytes)
    }

    fn obs_list(&mut self) -> Option<u8> {
        self.u8().filter(|list| (LIST_SCENES..=LIST_TRANSITIONS).contains(list))
    }

    fn u16(&mut self) -> Option<u16> {
        self.array().map(u16::from_le_bytes)
    }

    fn u32(&mut self) -> Option<u32> {
        self.array().map(u32::from_le_bytes)
    }

    fn size(&mut self) -> Option<Size> {
        Some(Size { width: self.u16()?, height: self.u16()? })
    }

    fn rest(&mut self) -> &'a [u8] {
        std::mem::take(&mut self.0)
    }

    /// The rest of the payload as printable ASCII of at most `max_bytes`.
    fn text(&mut self, max_bytes: usize) -> Option<String> {
        let rest = self.rest();
        (rest.len() <= max_bytes && printable(rest)).then(|| rest.iter().copied().map(char::from).collect())
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

/// `None` when the payload is above the 240-byte cap.
pub fn encode(frame: &Frame) -> Option<Vec<u8>> {
    if frame.payload.len() > MAX_PAYLOAD {
        return None;
    }
    let length = u16::try_from(frame.payload.len()).ok()?;
    let mut out = Vec::with_capacity(HEADER_LEN + frame.payload.len() + CRC_LEN);
    out.extend_from_slice(&[SOF, VERSION, frame.kind, frame.id]);
    out.extend_from_slice(&length.to_le_bytes());
    out.extend_from_slice(&frame.payload);
    let crc = crc16_modbus(&out[VERSION_AT..]);
    out.extend_from_slice(&crc.to_le_bytes());
    Some(out)
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

#[cfg(test)]
mod tests {
    use super::*;

    const READ_LEN: usize = 64;

    fn vectors() -> Vec<(String, Vec<u8>)> {
        let text = include_str!("../../../firmware/test/vectors.txt");
        let lines = text.lines().map(str::trim).filter(|line| !line.is_empty() && !line.starts_with('#'));
        lines
            .map(|line| {
                let mut parts = line.split_whitespace();
                let name = parts.next().expect("vector name").to_string();
                (name, parts.map(|hex| u8::from_str_radix(hex, 16).expect("vector hex")).collect())
            })
            .collect()
    }

    fn vector(name: &str) -> Vec<u8> {
        let found = vectors().into_iter().find(|(vector_name, _)| vector_name == name);
        found.unwrap_or_else(|| panic!("missing vector {name}")).1
    }

    /// What the codec must hand back for a vector: the frame itself, or the reply to a refused one.
    fn answer(name: &str, bytes: &[u8]) -> Vec<u8> {
        match name.strip_prefix("refuse_") {
            Some(case) => vector(&format!("reply_{case}")),
            None => bytes.to_vec(),
        }
    }

    /// Feeds `input` in reads of `read_len`. Every frame and every reply comes back encoded again.
    fn pump(input: &[u8], read_len: usize) -> Vec<u8> {
        let mut rx = LinkRx::default();
        let mut seen = Vec::new();
        for read in input.chunks(read_len) {
            rx.push(read);
            while let Some(pulled) = rx.pull() {
                let (Pulled::Frame(frame) | Pulled::Reply(frame)) = pulled;
                seen.extend(encode(&frame).expect("pulled frame encodes"));
            }
        }
        seen
    }

    fn filled_frame(length: usize) -> Frame {
        Frame { kind: 0x7F, id: 0x33, payload: (0..length).map(|i| (i * 7 + 1) as u8).collect() }
    }

    #[test]
    fn crc_check_value() {
        assert_eq!(crc16_modbus(b"123456789"), 0x4B37);
    }

    #[test]
    fn good_vector_gives_type_id_and_payload() {
        let mut rx = LinkRx::default();
        rx.push(&vector("payload_3"));
        let want = Frame { kind: 0x7F, id: 0x09, payload: vec![1, 2, 3] };
        assert_eq!(rx.pull(), Some(Pulled::Frame(want)));
        assert_eq!(rx.pull(), None);
    }

    #[test]
    fn every_vector_decodes_alone() {
        for (name, bytes) in vectors() {
            let mut rx = LinkRx::default();
            rx.push(&bytes);
            let pulled = rx.pull().unwrap_or_else(|| panic!("{name}: nothing pulled"));
            assert_eq!(matches!(pulled, Pulled::Reply(_)), name.starts_with("refuse_"), "{name}");
            let (Pulled::Frame(frame) | Pulled::Reply(frame)) = pulled;
            assert_eq!(encode(&frame), Some(answer(&name, &bytes)), "{name}");
            assert_eq!(rx.pull(), None, "{name}");
        }
    }

    #[test]
    fn refusals_carry_the_type_and_code() {
        let refusal = |name: &str| {
            let mut rx = LinkRx::default();
            rx.push(&vector(name));
            rx.pull()
        };
        let result = |id, code| Frame { kind: RESULT, id, payload: vec![code, 0, 0, 0, 0] };
        assert_eq!(refusal("refuse_too_big"), Some(Pulled::Reply(result(0x07, RESULT_TOO_BIG))));
        assert_eq!(refusal("refuse_bad_crc"), Some(Pulled::Reply(result(0x09, RESULT_BAD_CRC))));
        let notice = Frame { kind: NOTICE, id: 0, payload: b"protocol v2 only".to_vec() };
        assert_eq!(refusal("refuse_v1_key"), Some(Pulled::Reply(notice)));
    }

    #[test]
    fn all_vectors_at_all_64_read_alignments_and_one_byte_at_a_time() {
        let all = vectors();
        let stream: Vec<u8> = all.iter().flat_map(|(_, bytes)| bytes.clone()).collect();
        let want: Vec<u8> = all.iter().flat_map(|(name, bytes)| answer(name, bytes)).collect();
        for lead in 0..READ_LEN {
            let mut input = vec![0u8; lead];
            input.extend(&stream);
            assert_eq!(pump(&input, READ_LEN), want, "lead {lead}");
        }
        assert_eq!(pump(&stream, 1), want);
    }

    /// docs/research/02-repo-inventory.md: the v1 parser lost the head of a 247-byte frame with
    /// traffic behind it at 54 of 64 read alignments.
    #[test]
    fn the_247_byte_and_the_largest_frame_keep_their_heads() {
        for payload_len in [239, MAX_PAYLOAD] {
            let mut want = encode(&filled_frame(payload_len)).expect("big frame encodes");
            assert_eq!(want.len(), HEADER_LEN + payload_len + CRC_LEN);
            want.extend(vector("empty_payload").repeat(40));
            for lead in 0..READ_LEN {
                let mut input = vec![0u8; lead];
                input.extend(&want);
                assert_eq!(pump(&input, READ_LEN), want, "payload {payload_len} lead {lead}");
            }
        }
        assert_eq!(MAX_FRAME, 248);
    }

    #[test]
    fn cut_frame_is_answered_and_the_next_frame_survives() {
        let next = vector("empty_payload");
        let mut input = vector("payload_3")[..HEADER_LEN + 1].to_vec();
        input.extend(&next);
        let mut want = vector("reply_bad_crc");
        want.extend(&next);
        assert_eq!(pump(&input, READ_LEN), want);
    }

    #[test]
    fn encode_refuses_a_payload_above_the_cap() {
        assert_eq!(encode(&filled_frame(MAX_PAYLOAD + 1)), None);
    }

    const DOCUMENT: &[u8] = br#"{"schema":1,"seq":7}"#;

    fn frame(name: &str) -> Frame {
        let mut rx = LinkRx::default();
        rx.push(&vector(name));
        match rx.pull() {
            Some(Pulled::Frame(frame) | Pulled::Reply(frame)) => frame,
            None => panic!("{name}: not a whole frame"),
        }
    }

    fn message(name: &str) -> Message {
        Message::decode(&frame(name)).unwrap_or_else(|| panic!("{name}: message refused"))
    }

    fn info() -> Info {
        Info {
            proto: VERSION,
            obs_password_set: true,
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
            git_hash: [0x00, 0xC0, 0xFF, 0xEE],
            unique_id: [0x02, 0x00, 0x00, 0x00, 0x00, 0x01],
            fw_version: "0.2.0".to_string(),
        }
    }

    fn result(code: u8, seq: u32, path: &str) -> Message {
        Message::Result { code, seq, path: path.to_string() }
    }

    #[test]
    fn every_msg_vector_decodes_and_encodes_back() {
        let typed: Vec<_> = vectors().into_iter().filter(|(name, _)| name.starts_with("msg_")).collect();
        assert_eq!(typed.len(), 25);
        for (name, bytes) in typed {
            let pulled = frame(&name);
            let again = message(&name).encode(pulled.id).unwrap_or_else(|| panic!("{name}: no encode"));
            assert_eq!(encode(&again), Some(bytes), "{name}");
        }
    }

    #[test]
    fn every_bad_vector_is_refused_by_the_typed_decoder() {
        let bad: Vec<_> = vectors().into_iter().filter(|(name, _)| name.starts_with("bad_")).collect();
        assert_eq!(bad.len(), 35);
        for (name, _) in bad {
            assert_eq!(Message::decode(&frame(&name)), None, "{name}");
        }
    }

    #[test]
    fn an_unknown_type_is_refused() {
        assert_eq!(Message::decode(&frame("payload_3")), None);
    }

    #[test]
    fn request_vectors_carry_these_fields() {
        assert_eq!(message("msg_info_get"), Message::InfoGet);
        assert_eq!(frame("msg_info_get").id, 0x10);
        assert_eq!(message("msg_cfg_read"), Message::CfgRead { offset: 0, len: 232 });
        let begin = |try_only| Message::CfgBegin { base_seq: 7, total: 20, crc32: 0xCA7A_E782, try_only };
        assert_eq!(message("msg_cfg_begin"), begin(false));
        assert_eq!(message("msg_cfg_begin_try"), begin(true));
        assert_eq!(message("msg_cfg_chunk"), Message::CfgChunk { offset: 0, bytes: DOCUMENT.to_vec() });
        assert_eq!(message("msg_cfg_commit"), Message::CfgCommit);
    }

    #[test]
    fn info_vector_carries_these_fields() {
        assert_eq!(message("msg_info"), Message::Info(info()));
        let wifi_only = Info { obs_password_set: false, wifi_psk_set: true, ..info() };
        assert_eq!(message("msg_info_wifi_psk"), Message::Info(wifi_only));
    }

    /// Acceptance of task 1.7: a stored credential moves one bit of `INFO` and nothing else.
    #[test]
    fn info_carries_each_credential_as_one_bit() {
        let payload = |obs_password_set, wifi_psk_set| {
            let info = Info { obs_password_set, wifi_psk_set, ..info() };
            Message::Info(info).encode(1).expect("info encodes").payload
        };
        let bits_changed = |a: &[u8], b: &[u8]| {
            assert_eq!(a.len(), b.len());
            a.iter().zip(b).map(|(x, y)| (x ^ y).count_ones()).sum::<u32>()
        };
        let unset = payload(false, false);
        assert_eq!(bits_changed(&unset, &payload(true, false)), 1);
        assert_eq!(bits_changed(&unset, &payload(false, true)), 1);
        assert_eq!(bits_changed(&payload(true, false), &payload(false, true)), 2);
    }

    #[test]
    fn reply_vectors_carry_these_fields() {
        let data = Message::CfgData { seq: 7, total: 20, offset: 0, bytes: DOCUMENT.to_vec() };
        assert_eq!(message("msg_cfg_data"), data);
        let empty = Message::CfgData { seq: 0, total: 0, offset: 0, bytes: Vec::new() };
        assert_eq!(message("msg_cfg_data_empty"), empty);
        assert_eq!(message("msg_result_ok"), result(RESULT_OK, 8, ""));
        assert_eq!(message("msg_result_busy"), result(RESULT_BUSY, 0, ""));
        assert_eq!(message("msg_result_stale_seq"), result(RESULT_STALE_SEQ, 9, ""));
        assert_eq!(message("reply_bad_crc"), result(RESULT_BAD_CRC, 0, ""));
        assert_eq!(message("reply_too_big"), result(RESULT_TOO_BIG, 0, ""));
        assert_eq!(message("msg_result_invalid"), result(RESULT_INVALID, 7, "obs.url"));
    }

    /// Spec 8.2: one reject vector per rule. The typed decoder takes a credential frame only when ok.
    #[test]
    fn every_cred_vector_gets_the_status_in_its_name() {
        let names = [
            ("ok_", CRED_OK),
            ("bad_kind_", CRED_BAD_KIND),
            ("bad_len_", CRED_BAD_LEN),
            ("bad_value_", CRED_BAD_VALUE),
        ];
        let cred: Vec<_> = vectors().into_iter().filter(|(name, _)| name.starts_with("cred_")).collect();
        assert_eq!(cred.len(), 15);
        for (name, bytes) in cred {
            let case = &name["cred_".len()..];
            let named = names.iter().find(|(prefix, _)| case.starts_with(prefix));
            let want = named.unwrap_or_else(|| panic!("{name}: no status in the name")).1;
            let pulled = frame(&name);
            assert_eq!(credential_status(&pulled), want, "{name}");
            let decoded = Message::decode(&pulled);
            assert_eq!(decoded.is_some(), want == CRED_OK, "{name}");
            if let Some(message) = decoded {
                assert_eq!(message.encode(pulled.id).and_then(|again| encode(&again)), Some(bytes), "{name}");
            }
        }
    }

    fn set_credential(kind: u8, secret: &[u8]) -> Message {
        Message::SetCredential { kind, secret: Secret(secret.to_vec()) }
    }

    #[test]
    fn credential_vectors_carry_these_fields() {
        assert_eq!(message("cred_ok_obs"), set_credential(CREDENTIAL_OBS_PASSWORD, b"dummy-obs-password"));
        assert_eq!(message("cred_ok_wifi_8"), set_credential(CREDENTIAL_WIFI_PASSPHRASE, b"dummy-pw"));
        assert_eq!(message("cred_ok_clear"), Message::ClearCredentials);
    }

    /// Spec 8.2: 239 is the payload cap less the kind byte. A 240-byte password has no frame (8.1).
    #[test]
    fn an_obs_password_stops_at_239_bytes() {
        assert_eq!(CREDENTIAL_MAX, 239);
        assert_eq!(message("cred_ok_obs_239"), set_credential(CREDENTIAL_OBS_PASSWORD, &[b'p'; CREDENTIAL_MAX]));
        assert_eq!(set_credential(CREDENTIAL_OBS_PASSWORD, &[b'p'; CREDENTIAL_MAX + 1]).encode(1), None);
        let too_big = Frame { kind: RESULT, id: 0x4F, payload: vec![RESULT_TOO_BIG, 0, 0, 0, 0] };
        assert_eq!(frame("refuse_cred_240"), too_big);
    }

    /// R1: no log line carries a secret. `{:?}` of a credential message prints no byte of it.
    #[test]
    fn debug_output_hides_the_secret() {
        let printed = format!("{:?}", message("cred_ok_obs"));
        assert_eq!(printed, "SetCredential { kind: 1, secret: Secret(hidden) }");
    }

    /// Spec 8.2: a 32-bit magic each, so no single flipped bit erases the pad.
    #[test]
    fn a_wrong_magic_is_refused() {
        for (name, kind, magic) in
            [("msg_factory_reset", FACTORY_RESET, b"WIPE"), ("msg_bootloader", BOOTLOADER, b"BOOT")]
        {
            let good = frame(name);
            assert_eq!((good.kind, good.payload.as_slice()), (kind, magic.as_slice()), "{name}");
            for bit in 0..32 {
                let mut flipped = good.clone();
                flipped.payload[bit / 8] ^= 1 << (bit % 8);
                assert_eq!(Message::decode(&flipped), None, "{name} bit {bit}");
            }
        }
        assert_eq!(message("msg_factory_reset"), Message::FactoryReset);
        assert_eq!(message("msg_bootloader"), Message::Bootloader);
    }

    const UUID: [u8; UUID_LEN] =
        [0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF];

    #[test]
    fn status_and_list_vectors_carry_these_fields() {
        assert_eq!(message("msg_cred_status_ok"), Message::CredStatus { code: CRED_OK });
        assert_eq!(message("msg_cred_status_store_fail"), Message::CredStatus { code: CRED_STORE_FAIL });
        let up = Message::Status { obs_state: OBS_UP, wifi_state: WIFI_UP, rssi_dbm: -52, ip: [192, 168, 1, 50] };
        assert_eq!(message("msg_status_up"), up);
        let no_ssid = Message::Status { obs_state: OBS_IDLE, wifi_state: WIFI_NO_SSID, rssi_dbm: 0, ip: [0; 4] };
        assert_eq!(message("msg_status_no_ssid"), no_ssid);
        assert_eq!(message("msg_obs_list"), Message::ObsList { list: LIST_SCENES, index: 0 });
        let name = "Caméra".as_bytes().to_vec();
        let scene = Message::ObsItem { list: LIST_SCENES, index: 0, total: 2, uuid: UUID, name };
        assert_eq!(message("msg_obs_item"), scene);
        let none =
            Message::ObsItem { list: LIST_TRANSITIONS, index: 0, total: 0, uuid: [0; UUID_LEN], name: Vec::new() };
        assert_eq!(message("msg_obs_item_none"), none);
        assert_eq!(message("msg_input_key"), Message::Input { source: INPUT_KEY, index: 4, value: 1 });
        assert_eq!(message("msg_input_turn"), Message::Input { source: INPUT_KNOB_TURN, index: 2, value: -1 });
    }

    /// R1: every pad-to-app type the typed codec knows, a vector of it, the fixed payload bytes, and
    /// what feeds the one byte run that may follow them (`None`: nothing may follow). `NOTICE` is
    /// the codec's own fixed text and has no fields.
    const PAD_TYPES: [(u8, &str, usize, Option<&str>); 7] = [
        (RESULT, "msg_result_invalid", 5, Some("path of the first bad config field")),
        (INFO, "msg_info", 34, Some("firmware version text")),
        (CFG_DATA, "msg_cfg_data", 8, Some("config document bytes: the cfg slot, never `cred`")),
        (CRED_STATUS, "msg_cred_status_ok", 1, None),
        (STATUS, "msg_status_up", 7, None),
        (OBS_ITEM, "msg_obs_item", 21, Some("name of an OBS scene, input or transition")),
        (INPUT, "msg_input_key", 3, None),
    ];

    /// A pad-to-app type that is not in `PAD_TYPES` must not exist: a new one fails here until it
    /// is listed and its fields are judged against R1.
    #[test]
    fn the_pad_to_app_types_are_a_closed_list() {
        let unlisted = (0x80..=0xFFu8).filter(|kind| PAD_TYPES.iter().all(|(listed, ..)| listed != kind));
        for kind in unlisted {
            for length in 0..=MAX_PAYLOAD {
                let zeros = Frame { kind, id: 1, payload: vec![0; length] };
                assert_eq!(Message::decode(&zeros), None, "type {kind:#04x} length {length}");
            }
            for (_, sample, ..) in PAD_TYPES {
                let relabelled = Frame { kind, ..frame(sample) };
                assert_eq!(Message::decode(&relabelled), None, "type {kind:#04x} as {sample}");
            }
        }
    }

    /// No listed type has room for a field the table does not name.
    #[test]
    fn each_pad_to_app_type_has_only_its_named_bytes() {
        for (kind, sample, fixed_len, run) in PAD_TYPES {
            let whole = frame(sample);
            assert_eq!((whole.kind, whole.kind & 0x80), (kind, 0x80), "{sample}");
            assert!(Message::decode(&whole).is_some(), "{sample}");
            assert_eq!(whole.payload.len() > fixed_len, run.is_some(), "{sample}");
            let cut = |length: usize| Frame { payload: whole.payload[..length].to_vec(), ..whole.clone() };
            assert!(Message::decode(&cut(fixed_len)).is_some(), "{sample}");
            assert_eq!(Message::decode(&cut(fixed_len - 1)), None, "{sample}");
            if run.is_none() {
                let mut longer = whole.clone();
                longer.payload.push(0);
                assert_eq!(Message::decode(&longer), None, "{sample}");
            }
        }
    }

    /// R1 names two exceptions: bytes that look like a hash or an opaque run, and are neither a
    /// credential nor made from one. The `INFO` git hash is the caller's four bytes whatever the
    /// two credential bits say. The `CFG_DATA` bytes are the caller's document bytes and nothing
    /// else: that message has no credential input at all.
    #[test]
    fn the_git_hash_and_the_document_bytes_are_not_fed_by_a_credential() {
        const GIT_HASH_AT: usize = 24;
        const DOCUMENT_AT: usize = 8;
        for (obs_password_set, wifi_psk_set) in [(false, false), (true, false), (false, true), (true, true)] {
            let info = Info { obs_password_set, wifi_psk_set, ..info() };
            let payload = Message::Info(info).encode(1).expect("info encodes").payload;
            assert_eq!(payload[GIT_HASH_AT..GIT_HASH_AT + 4], self::info().git_hash);
        }
        let data = Message::CfgData { seq: 7, total: 20, offset: 0, bytes: DOCUMENT.to_vec() };
        let payload = data.encode(1).expect("data encodes").payload;
        assert_eq!(&payload[DOCUMENT_AT..], DOCUMENT);
    }

    /// The one answer to a credential is one status byte. It is the same byte for an 8-byte, a
    /// 63-byte and a 239-byte secret, so it gives away no value, no length and no hash.
    #[test]
    fn the_credential_reply_is_the_same_for_every_accepted_secret() {
        let accepted = ["cred_ok_obs", "cred_ok_obs_239", "cred_ok_wifi_8", "cred_ok_wifi_63", "cred_ok_wifi_hex64"];
        for name in accepted {
            let request = frame(name);
            assert_eq!(request.kind & 0x80, 0, "{name}");
            let reply = Message::CredStatus { code: credential_status(&request) }.encode(1).expect("status encodes");
            assert_eq!(reply.payload, [CRED_OK], "{name}");
        }
    }

    #[test]
    fn chunk_and_data_sizes_stop_at_the_payload_cap() {
        assert_eq!((CFG_CHUNK_MAX, CFG_DATA_MAX), (238, 232));
        let chunk = |len| Message::CfgChunk { offset: 0, bytes: vec![0; len] }.encode(1);
        assert_eq!(chunk(CFG_CHUNK_MAX).map(|frame| frame.payload.len()), Some(MAX_PAYLOAD));
        assert_eq!(chunk(CFG_CHUNK_MAX + 1), None);
        let data = |len| Message::CfgData { seq: 0, total: 0, offset: 0, bytes: vec![0; len] }.encode(1);
        assert_eq!(data(CFG_DATA_MAX).map(|frame| frame.payload.len()), Some(MAX_PAYLOAD));
        assert_eq!(data(CFG_DATA_MAX + 1), None);
    }

    #[test]
    fn encode_refuses_what_decode_refuses() {
        assert_eq!(Message::CfgRead { offset: 0, len: 0 }.encode(1), None);
        assert_eq!(Message::CfgRead { offset: 0, len: 233 }.encode(1), None);
        assert_eq!(Message::CfgChunk { offset: 0, bytes: Vec::new() }.encode(1), None);
        assert_eq!(result(RESULT_INVALID + 1, 0, "").encode(1), None);
        assert!(result(RESULT_INVALID, 0, &"p".repeat(PATH_MAX)).encode(1).is_some());
        assert_eq!(result(RESULT_INVALID, 0, &"p".repeat(PATH_MAX + 1)).encode(1), None);
        assert_eq!(result(RESULT_INVALID, 0, "a\nb").encode(1), None);
        assert_eq!(Message::Info(Info { fw_version: "v".repeat(FW_VERSION_MAX + 1), ..info() }).encode(1), None);
        assert_eq!(set_credential(CREDENTIAL_WIFI_PASSPHRASE, b"dummy-p").encode(1), None);
        assert_eq!(Message::CredStatus { code: CRED_STORE_FAIL + 1 }.encode(1), None);
        let status = |wifi_state| Message::Status { obs_state: OBS_IDLE, wifi_state, rssi_dbm: 0, ip: [0; 4] };
        assert!(status(WIFI_UP).encode(1).is_some());
        assert_eq!(status(WIFI_UP + 1).encode(1), None);
        assert_eq!(Message::ObsList { list: 0, index: 0 }.encode(1), None);
        assert_eq!(Message::Input { source: INPUT_KNOB_TURN, index: 0, value: 0 }.encode(1), None);
    }
}
