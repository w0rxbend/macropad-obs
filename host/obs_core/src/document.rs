// SPDX-License-Identifier: MIT
//! The config document: validator, migrations and the schema-age rule of the write.
//! Rules, check order and paths: `docs/config.md`. `firmware/core/config.c` runs the same rules and
//! `firmware/test/config_vectors/` holds both to them (R3).

use std::fmt;
use std::ops::RangeInclusive;

use serde_json::{Map, Value};

use crate::protocol::{Info, Message, CFG_CHUNK_MAX};

/// The schema this app reads and writes.
pub const SCHEMA: u64 = 1;
pub const MAX_BYTES: usize = 16384;

const KEYS: usize = 9;
const BUTTONS: usize = 4;
const KNOBS: usize = 3;
const WIDGETS_MAX: usize = 16;
const WIDGET_SIDE_MIN: u64 = 24;
const UUID_MAX: usize = 36;
const LABEL_MAX: usize = 48;
const SSID_MAX: usize = 32;
const TEXT_MAX: usize = 32;
const STEP_DB_MAX: f64 = 6.0;
const BRIGHTNESS_MAX: u64 = 100;

const ACTIONS: &[&str] = &["none", "scene", "toggle_mute", "toggle_record", "toggle_stream", "transition"];
const AUTH_MODES: &[&str] = &["stored", "none"];
const STATUS_FIELDS: &[&str] = &["link", "rec", "live"];
const STRIP_PARTS: &[&str] = &["name", "db", "fader", "meter", "push"];
const SCENES: &[&str] = &["program", "preview"];
const SIZES: &[&str] = &["small", "large"];

#[derive(Clone, Copy)]
struct Panel {
    name: &'static str,
    width: u64,
    height: u64,
}

const MAIN_DISPLAY: Panel = Panel { name: "main_display", width: 320, height: 480 };
const STRIP_DISPLAY: Panel = Panel { name: "strip_display", width: 142, height: 428 };

/// Why the pad refuses a document: `RESULT too_big` or `RESULT invalid` with the first bad path.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Rejected {
    TooBig,
    /// `path` is empty for bytes that are not one JSON object.
    Invalid {
        path: String,
    },
}

/// A document that passed every rule. It keeps the whole JSON value, unknown members included.
#[derive(Debug, Clone, PartialEq)]
pub struct Document {
    json: Value,
}

impl Document {
    /// Runs the rules in the order of `docs/config.md` and stops at the first failure.
    /// `schemas` is the pad's `INFO` `schema_min..=schema_max`.
    pub fn parse(bytes: &[u8], schemas: RangeInclusive<u64>) -> Result<Self, Rejected> {
        if bytes.len() > MAX_BYTES {
            return Err(Rejected::TooBig);
        }
        let not_an_object = || Rejected::Invalid { path: String::new() };
        let json: Value = serde_json::from_slice(bytes).map_err(|_| not_an_object())?;
        let root = Scope { obj: Some(json.as_object().ok_or_else(not_an_object)?), path: String::new() };
        check_document(&root, schemas).map_err(|path| Rejected::Invalid { path })?;
        Ok(Self { json })
    }

    pub fn seq(&self) -> u32 {
        let seq = self.json["seq"].as_u64().and_then(|seq| u32::try_from(seq).ok());
        seq.expect("parse admits only a u32 seq")
    }

    pub fn schema(&self) -> u64 {
        self.json["schema"].as_u64().expect("parse admits only an integer schema")
    }

    /// Compact JSON with members in sorted order.
    pub fn to_bytes(&self) -> Vec<u8> {
        self.json.to_string().into_bytes()
    }
}

/// Why the app writes nothing to this pad (spec 8.2).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WriteRefused {
    /// The pad's `schema_max` is below `SCHEMA`. There is no downgrade migration.
    UpdateFirmware,
    /// The pad's `schema_max` is above `SCHEMA`: the app opens the document read-only.
    UpdateApp,
    /// The serialised document is above `MAX_BYTES`.
    TooBig,
}

impl fmt::Display for WriteRefused {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::UpdateFirmware => "update firmware",
            Self::UpdateApp => "update the app",
            Self::TooBig => "document too big",
        })
    }
}

/// The messages of one stored write: `CFG_BEGIN` with the document's `seq` as `base_seq`, the
/// chunks, then `CFG_COMMIT`. The schema-age rule runs first, so a refusal builds no message.
pub fn write_messages(info: &Info, doc: &Document) -> Result<Vec<Message>, WriteRefused> {
    let pad_max = u64::from(info.schema_max);
    if pad_max < SCHEMA {
        return Err(WriteRefused::UpdateFirmware);
    }
    if pad_max > SCHEMA {
        return Err(WriteRefused::UpdateApp);
    }
    let bytes = doc.to_bytes();
    if bytes.len() > MAX_BYTES {
        return Err(WriteRefused::TooBig);
    }
    let total = u16::try_from(bytes.len()).map_err(|_| WriteRefused::TooBig)?;
    let mut messages = vec![Message::CfgBegin { base_seq: doc.seq(), total, crc32: crc32(&bytes), try_only: false }];
    for (index, chunk) in bytes.chunks(CFG_CHUNK_MAX).enumerate() {
        let offset = u16::try_from(index * CFG_CHUNK_MAX).map_err(|_| WriteRefused::TooBig)?;
        messages.push(Message::CfgChunk { offset, bytes: chunk.to_vec() });
    }
    messages.push(Message::CfgCommit);
    Ok(messages)
}

/// One schema step, run in the app only. `run` changes what the step needs and leaves `seq` and
/// unknown members alone; `migrate` then sets `schema` to `from + 1`.
#[derive(Clone, Copy)]
pub struct Migration {
    pub from: u64,
    pub run: fn(&mut Map<String, Value>),
}

/// Schema 1 is the first schema: the app ships no step yet.
pub const MIGRATIONS: &[Migration] = &[];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MigrateError {
    NotAnObject,
    NoSchema,
    /// The document is newer than `SCHEMA`. There is no downgrade migration.
    Newer,
    /// No step starts at this schema.
    NoStep(u64),
}

/// Brings a stored document up to `SCHEMA`, one step at a time. The result still needs
/// `Document::parse`.
pub fn migrate(stored: &[u8], steps: &[Migration]) -> Result<Vec<u8>, MigrateError> {
    let mut json: Value = serde_json::from_slice(stored).map_err(|_| MigrateError::NotAnObject)?;
    let doc = json.as_object_mut().ok_or(MigrateError::NotAnObject)?;
    loop {
        let schema = doc.get("schema").and_then(Value::as_u64).ok_or(MigrateError::NoSchema)?;
        if schema == SCHEMA {
            return Ok(json.to_string().into_bytes());
        }
        if schema > SCHEMA {
            return Err(MigrateError::Newer);
        }
        let step = steps.iter().find(|step| step.from == schema).ok_or(MigrateError::NoStep(schema))?;
        (step.run)(doc);
        doc.insert("schema".into(), Value::from(schema + 1));
    }
}

/// CRC-32 (IEEE 802.3, reflected, as zlib): `CFG_BEGIN` carries it for the whole document.
fn crc32(data: &[u8]) -> u32 {
    let mut crc = !0u32;
    for byte in data {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            crc = if crc & 1 == 1 { (crc >> 1) ^ 0xEDB8_8320 } else { crc >> 1 };
        }
    }
    !crc
}

/// The first bad path, or `Ok`.
type Check = Result<(), String>;

/// One JSON object and its path. `obj` is `None` for a list entry that is not an object: every
/// field of it then reads as missing, so the entry reports its first field's path.
struct Scope<'a> {
    obj: Option<&'a Map<String, Value>>,
    path: String,
}

impl<'a> Scope<'a> {
    fn at(&self, name: &str) -> String {
        if self.path.is_empty() {
            name.to_string()
        } else {
            format!("{}.{name}", self.path)
        }
    }

    fn get(&self, name: &str) -> Option<&'a Value> {
        self.obj.and_then(|obj| obj.get(name))
    }

    /// A missing field, a wrong type and a bad value all give the field's own path.
    fn field<T>(&self, name: &str, read: impl FnOnce(&'a Value) -> Option<T>) -> Result<T, String> {
        self.get(name).and_then(read).ok_or_else(|| self.at(name))
    }

    fn object(&self, name: &str) -> Result<Scope<'a>, String> {
        let obj = self.field(name, Value::as_object)?;
        Ok(Scope { obj: Some(obj), path: self.at(name) })
    }

    /// A JSON number with no fraction and no exponent, inside `range`.
    fn integer(&self, name: &str, range: RangeInclusive<u64>) -> Result<u64, String> {
        self.field(name, |value| value.as_u64().filter(|number| range.contains(number)))
    }

    fn string(&self, name: &str, max_bytes: usize) -> Result<&'a str, String> {
        self.field(name, |value| value.as_str().filter(|text| text.len() <= max_bytes))
    }

    fn one_of(&self, name: &str, allowed: &[&str]) -> Result<&'a str, String> {
        self.field(name, |value| value.as_str().filter(|text| allowed.contains(text)))
    }

    fn array(&self, name: &str, count: RangeInclusive<usize>) -> Result<&'a [Value], String> {
        self.field(name, |value| value.as_array().filter(|items| count.contains(&items.len())).map(Vec::as_slice))
    }

    fn list(&self, name: &str, count: RangeInclusive<usize>) -> Result<Vec<Scope<'a>>, String> {
        let items = self.array(name, count)?;
        let path = self.at(name);
        Ok(items
            .iter()
            .enumerate()
            .map(|(index, item)| Scope { obj: item.as_object(), path: format!("{path}[{index}]") })
            .collect())
    }

    /// A list of names from `allowed`, none twice. A bad entry gives its own path.
    fn distinct(&self, name: &str, allowed: &[&str], count: RangeInclusive<usize>) -> Check {
        let items = self.array(name, count)?;
        for (index, item) in items.iter().enumerate() {
            let fresh = item.as_str().is_some_and(|text| allowed.contains(&text)) && !items[..index].contains(item);
            if !fresh {
                return Err(format!("{}[{index}]", self.at(name)));
            }
        }
        Ok(())
    }
}

fn check_document(root: &Scope, schemas: RangeInclusive<u64>) -> Check {
    root.integer("schema", schemas)?;
    root.integer("seq", 0..=u64::from(u32::MAX))?;
    let obs = root.object("obs")?;
    obs.field("url", |value| value.as_str().filter(|url| is_private_ws_url(url)))?;
    obs.one_of("auth_mode", AUTH_MODES)?;
    root.object("wifi")?.string("ssid", SSID_MAX)?;
    for key in root.list("keys", KEYS..=KEYS)? {
        check_list_action(&key)?;
    }
    for button in root.list("buttons", BUTTONS..=BUTTONS)? {
        check_list_action(&button)?;
    }
    for knob in root.list("knobs", KNOBS..=KNOBS)? {
        check_knob(&knob)?;
    }
    check_display(&root.object(MAIN_DISPLAY.name)?, MAIN_DISPLAY)?;
    check_display(&root.object(STRIP_DISPLAY.name)?, STRIP_DISPLAY)?;
    root.object("ui")?.integer("brightness", 0..=BRIGHTNESS_MAX)?;
    Ok(())
}

/// `ws://<private IPv4>[:port]` and nothing else.
fn is_private_ws_url(url: &str) -> bool {
    let Some(authority) = url.strip_prefix("ws://") else {
        return false;
    };
    let (host, port) = match authority.split_once(':') {
        Some((host, port)) => (host, Some(port)),
        None => (authority, None),
    };
    // std's parser takes exactly four decimal octets 0..255 and refuses a leading zero.
    let private = host.parse::<std::net::Ipv4Addr>().is_ok_and(|address| address.is_private());
    private && port.map_or(true, is_port)
}

/// 1..65535 in decimal digits, no sign and no leading zero.
fn is_port(text: &str) -> bool {
    let digits = !text.is_empty() && text.bytes().all(|byte| byte.is_ascii_digit()) && !text.starts_with('0');
    digits && text.parse::<u16>().is_ok()
}

/// An entry of `keys` or `buttons`.
fn check_list_action(action: &Scope) -> Check {
    match action.one_of("do", ACTIONS)? {
        "scene" | "toggle_mute" => check_reference(action),
        _ => Ok(()),
    }
}

/// A knob's `push`: its `toggle_mute` acts on the knob's own input and carries no reference.
fn check_push(push: &Scope) -> Check {
    match push.one_of("do", ACTIONS)? {
        "scene" => check_reference(push),
        _ => Ok(()),
    }
}

/// An OBS reference: `uuid` of 1..36 bytes in `0x21`-`0x7E`, and `label`.
fn check_reference(reference: &Scope) -> Check {
    let printable = |text: &&str| !text.is_empty() && text.bytes().all(|byte| (0x21..=0x7E).contains(&byte));
    reference.field("uuid", |value| value.as_str().filter(|text| text.len() <= UUID_MAX).filter(printable))?;
    reference.string("label", LABEL_MAX)?;
    Ok(())
}

fn check_knob(knob: &Scope) -> Check {
    if !knob.get("input").is_some_and(Value::is_null) {
        check_reference(&knob.object("input")?)?;
    }
    knob.field("step_db", |value| value.as_f64().filter(|step| *step > 0.0 && *step <= STEP_DB_MAX))?;
    check_push(&knob.object("push")?)
}

#[derive(Clone, Copy)]
enum Kind {
    Status,
    Key,
    Legend,
    SceneLine,
    Strip,
    Text,
}

const KINDS: &[(&str, Kind)] = &[
    ("status", Kind::Status),
    ("key", Kind::Key),
    ("legend", Kind::Legend),
    ("scene_line", Kind::SceneLine),
    ("strip", Kind::Strip),
    ("text", Kind::Text),
];

/// The argument that rule 3 allows once per display.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Slot {
    Key(u64),
    Button(u64),
    Knob(u64),
}

#[derive(Clone, Copy)]
struct Rect {
    x: u64,
    y: u64,
    w: u64,
    h: u64,
}

impl Rect {
    /// Sharing an edge is not an overlap.
    fn overlaps(&self, other: &Rect) -> bool {
        let across = self.x < other.x.saturating_add(other.w) && other.x < self.x.saturating_add(self.w);
        let down = self.y < other.y.saturating_add(other.h) && other.y < self.y.saturating_add(self.h);
        across && down
    }
}

struct Placed {
    rect: Rect,
    slot: Option<Slot>,
}

impl Placed {
    /// Rules 3 and 4 against a widget placed before this one.
    fn clashes(&self, earlier: &Placed) -> bool {
        (self.slot.is_some() && self.slot == earlier.slot) || self.rect.overlaps(&earlier.rect)
    }
}

fn check_display(display: &Scope, panel: Panel) -> Check {
    let mut placed: Vec<Placed> = Vec::with_capacity(WIDGETS_MAX);
    for widget in display.list("widgets", 0..=WIDGETS_MAX)? {
        let current = check_widget(&widget, panel)?;
        if placed.iter().any(|earlier| current.clashes(earlier)) {
            return Err(widget.path);
        }
        placed.push(current);
    }
    Ok(())
}

fn check_widget(widget: &Scope, panel: Panel) -> Result<Placed, String> {
    let kind = widget.field("kind", |value| {
        let name = value.as_str()?;
        KINDS.iter().find(|(known, _)| *known == name).map(|(_, kind)| *kind)
    })?;
    let rect = check_rect(widget, panel)?;
    let slot = check_kind_fields(widget, kind)?;
    Ok(Placed { rect, slot })
}

/// Rule 1 on `w` and `h`, then rule 2 on the widget.
fn check_rect(widget: &Scope, panel: Panel) -> Result<Rect, String> {
    let rect = Rect {
        x: widget.integer("x", 0..=u64::MAX)?,
        y: widget.integer("y", 0..=u64::MAX)?,
        w: widget.integer("w", WIDGET_SIDE_MIN..=u64::MAX)?,
        h: widget.integer("h", WIDGET_SIDE_MIN..=u64::MAX)?,
    };
    let inside = rect.x.saturating_add(rect.w) <= panel.width && rect.y.saturating_add(rect.h) <= panel.height;
    if inside {
        Ok(rect)
    } else {
        Err(widget.path.clone())
    }
}

fn check_kind_fields(widget: &Scope, kind: Kind) -> Result<Option<Slot>, String> {
    match kind {
        Kind::Status => widget.distinct("fields", STATUS_FIELDS, 1..=STATUS_FIELDS.len()).map(|()| None),
        Kind::Key => widget.integer("key", 0..=KEYS as u64 - 1).map(|key| Some(Slot::Key(key))),
        Kind::Legend => widget.integer("button", 0..=BUTTONS as u64 - 1).map(|button| Some(Slot::Button(button))),
        Kind::SceneLine => {
            widget.one_of("scene", SCENES)?;
            widget.one_of("size", SIZES).map(|_| None)
        }
        Kind::Strip => {
            let knob = widget.integer("knob", 0..=KNOBS as u64 - 1)?;
            widget.distinct("parts", STRIP_PARTS, 1..=STRIP_PARTS.len()).map(|()| Some(Slot::Knob(knob)))
        }
        Kind::Text => widget.string("text", TEXT_MAX).map(|_| None),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::Size;
    use std::path::{Path, PathBuf};

    const PAD_SCHEMAS: RangeInclusive<u64> = 1..=1;

    fn vector_dir() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../firmware/test/config_vectors")
    }

    fn vector(name: &str) -> Vec<u8> {
        std::fs::read(vector_dir().join(name)).unwrap_or_else(|err| panic!("{name}: {err}"))
    }

    /// `(file, expected)` for each line of `verdicts.txt`. `Ok(())` is `valid`.
    fn verdicts() -> Vec<(String, Result<(), Rejected>)> {
        let table = std::fs::read_to_string(vector_dir().join("verdicts.txt")).unwrap();
        table
            .lines()
            .filter(|line| !line.trim().is_empty() && !line.starts_with('#'))
            .map(|line| {
                let words: Vec<&str> = line.split_whitespace().collect();
                let expected = match words[1..] {
                    ["valid"] => Ok(()),
                    ["too_big"] => Err(Rejected::TooBig),
                    ["invalid"] => Err(Rejected::Invalid { path: String::new() }),
                    ["invalid", path] => Err(Rejected::Invalid { path: path.to_string() }),
                    _ => panic!("bad verdict line: {line}"),
                };
                (words[0].to_string(), expected)
            })
            .collect()
    }

    fn valid_full() -> Document {
        Document::parse(&vector("valid_full.json"), PAD_SCHEMAS).unwrap()
    }

    fn info(schema_min: u16, schema_max: u16) -> Info {
        Info {
            proto: 2,
            obs_password_set: false,
            wifi_psk_set: false,
            schema_min,
            schema_max,
            max_doc_bytes: MAX_BYTES as u16,
            keys: KEYS as u8,
            buttons: BUTTONS as u8,
            knobs: KNOBS as u8,
            main_display: Size { width: 320, height: 480 },
            strip_display: Size { width: 142, height: 428 },
            capabilities: 0,
            board_rev: 1,
            git_hash: [0; 4],
            unique_id: [0; 6],
            fw_version: "test".into(),
        }
    }

    #[test]
    fn every_vector_gives_its_verdict_and_path() {
        let verdicts = verdicts();
        let mut failures = Vec::new();
        for (name, expected) in &verdicts {
            let got = Document::parse(&vector(name), PAD_SCHEMAS).map(drop);
            if &got != expected {
                failures.push(format!("{name}: expected {expected:?}, got {got:?}"));
            }
        }
        assert!(failures.is_empty(), "{}", failures.join("\n"));
        assert!(!verdicts.is_empty());
    }

    #[test]
    fn verdicts_list_every_vector_file_once() {
        let mut listed: Vec<String> = verdicts().into_iter().map(|(name, _)| name).collect();
        listed.sort();
        let mut files: Vec<String> = std::fs::read_dir(vector_dir())
            .unwrap()
            .map(|entry| entry.unwrap().file_name().into_string().unwrap())
            .filter(|name| name != "verdicts.txt")
            .collect();
        files.sort();
        assert_eq!(listed, files);
    }

    #[test]
    fn the_cap_is_16_kib() {
        assert_eq!(vector("valid_16384_bytes.json").len(), MAX_BYTES);
        assert_eq!(vector("too_big_16385_bytes.json").len(), MAX_BYTES + 1);
    }

    #[test]
    fn the_schema_range_comes_from_the_pad() {
        let schema_2 = String::from_utf8(vector("schema_too_new.json")).unwrap();
        assert!(Document::parse(schema_2.as_bytes(), 1..=2).is_ok());
        assert_eq!(
            Document::parse(&vector("valid_full.json"), 2..=2),
            Err(Rejected::Invalid { path: "schema".into() })
        );
    }

    #[test]
    fn unknown_members_survive_a_round_trip() {
        let doc = Document::parse(&vector("valid_unknown_fields.json"), PAD_SCHEMAS).unwrap();
        let again = Document::parse(&doc.to_bytes(), PAD_SCHEMAS).unwrap();
        assert_eq!(again, doc);
        let json: Value = serde_json::from_slice(&again.to_bytes()).unwrap();
        assert_eq!(json["name"], "Desk pad");
        assert_eq!(json["ui"]["dim_after_s"], 300);
        assert_eq!(json["keys"][0]["colour"], "#C8102E");
        assert_eq!(json["main_display"]["preset"], "mirror");
    }

    /// A made-up step from schema 0, which never shipped: its `ui.backlight` became `ui.brightness`.
    fn rename_backlight(doc: &mut Map<String, Value>) {
        if let Some(ui) = doc.get_mut("ui").and_then(Value::as_object_mut) {
            if let Some(level) = ui.remove("backlight") {
                ui.insert("brightness".into(), level);
            }
        }
    }

    #[test]
    fn a_document_one_step_old_migrates_validates_and_keeps_seq_and_unknown_members() {
        let mut old: Value = serde_json::from_slice(&vector("valid_unknown_fields.json")).unwrap();
        old["schema"] = Value::from(SCHEMA - 1);
        let ui = old["ui"].as_object_mut().unwrap();
        let level = ui.remove("brightness").unwrap();
        ui.insert("backlight".into(), level);
        let old = old.to_string().into_bytes();
        assert!(Document::parse(&old, PAD_SCHEMAS).is_err());

        let steps = [Migration { from: SCHEMA - 1, run: rename_backlight }];
        let doc = Document::parse(&migrate(&old, &steps).unwrap(), PAD_SCHEMAS).unwrap();
        assert_eq!(doc.schema(), SCHEMA);
        assert_eq!(doc.seq(), 17);
        let json: Value = serde_json::from_slice(&doc.to_bytes()).unwrap();
        assert_eq!(json["schema"], SCHEMA);
        assert_eq!(json["ui"]["brightness"], 80);
        assert_eq!(json["ui"]["dim_after_s"], 300);
        assert_eq!(json["name"], "Desk pad");
    }

    #[test]
    fn migrate_refuses_what_it_cannot_step() {
        let current = vector("valid_full.json");
        let unchanged: Value = serde_json::from_slice(&migrate(&current, MIGRATIONS).unwrap()).unwrap();
        assert_eq!(unchanged, serde_json::from_slice::<Value>(&current).unwrap());
        assert_eq!(migrate(&vector("schema_too_old.json"), MIGRATIONS), Err(MigrateError::NoStep(0)));
        assert_eq!(migrate(&vector("schema_too_new.json"), MIGRATIONS), Err(MigrateError::Newer));
        assert_eq!(migrate(&vector("schema_missing.json"), MIGRATIONS), Err(MigrateError::NoSchema));
        assert_eq!(migrate(&vector("root_is_a_list.json"), MIGRATIONS), Err(MigrateError::NotAnObject));
    }

    #[test]
    fn a_pad_older_than_the_app_gets_no_write() {
        let refused = write_messages(&info(0, 0), &valid_full());
        assert_eq!(refused, Err(WriteRefused::UpdateFirmware));
        assert_eq!(refused.unwrap_err().to_string(), "update firmware");
    }

    #[test]
    fn a_pad_newer_than_the_app_is_read_only() {
        let refused = write_messages(&info(1, 2), &valid_full());
        assert_eq!(refused, Err(WriteRefused::UpdateApp));
        assert_eq!(refused.unwrap_err().to_string(), "update the app");
    }

    #[test]
    fn a_write_is_begin_chunks_commit() {
        let doc = valid_full();
        let bytes = doc.to_bytes();
        let messages = write_messages(&info(1, 1), &doc).unwrap();
        let begin =
            Message::CfgBegin { base_seq: 17, total: bytes.len() as u16, crc32: crc32(&bytes), try_only: false };
        assert_eq!(messages.first(), Some(&begin));
        assert_eq!(messages.last(), Some(&Message::CfgCommit));
        let mut joined = Vec::new();
        for message in &messages[1..messages.len() - 1] {
            let Message::CfgChunk { offset, bytes: chunk } = message else { panic!("{message:?}") };
            assert_eq!(usize::from(*offset), joined.len());
            assert!(chunk.len() <= CFG_CHUNK_MAX);
            joined.extend_from_slice(chunk);
        }
        assert_eq!(joined, bytes);
    }

    #[test]
    fn crc32_matches_the_protocol_check_values() {
        assert_eq!(crc32(b"123456789"), 0xCBF4_3926);
        assert_eq!(crc32(br#"{"schema":1,"seq":7}"#), 0xCA7A_E782);
    }
}
