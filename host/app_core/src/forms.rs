// SPDX-License-Identifier: MIT
//! The mapping editor's rules (task 3.7): the form the window edits, how it goes back into the
//! document with unknown members kept, the URL rule, and the OBS picker from `OBS_LIST`. The
//! window only draws what these give. Field rules: `docs/config.md`.

use obs_core::document::is_private_ws_url;
use obs_core::protocol::{LIST_INPUTS, LIST_SCENES, UUID_LEN};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::connection::Failure;
use crate::session::ObsItem;

/// The most bytes of a `label` (`docs/config.md`).
const LABEL_MAX: usize = 48;
/// The actions of a key or button that act on an OBS reference.
const REFERENCED: &[&str] = &["scene", "toggle_mute"];
/// A knob's push: its `toggle_mute` acts on the knob's own input, so only `scene` has one.
const PUSH_REFERENCED: &[&str] = &["scene"];
const URL_RULE: &str =
    "the URL is ws://<private IPv4>[:port]: no wss, host name, loopback, public address, user, path or query";

/// The list a picker shows. No action names a transition: `transition` runs the current one.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ObsList {
    Scenes,
    Inputs,
}

impl ObsList {
    /// The `list` byte of `OBS_LIST`.
    pub fn code(self) -> u8 {
        match self {
            Self::Scenes => LIST_SCENES,
            Self::Inputs => LIST_INPUTS,
        }
    }
}

/// An OBS reference, as the document holds it and as a picker offers it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Reference {
    pub uuid: String,
    pub label: String,
}

/// A key's, a button's or a push's action, in the document's shape: `do`, then `uuid` and
/// `label` when it has a target.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Action {
    #[serde(rename = "do")]
    pub act: String,
    #[serde(flatten)]
    pub target: Option<Reference>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Knob {
    pub input: Option<Reference>,
    pub step_db: f64,
    pub push: Action,
}

/// What the mapping editor edits.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Mapping {
    pub url: String,
    pub keys: Vec<Action>,
    pub buttons: Vec<Action>,
    pub knobs: Vec<Knob>,
}

/// The mapping of a document read from the pad. The pad's bytes are a trust boundary: a document
/// without these fields is refused, not guessed at.
pub fn mapping(document: &Value) -> Result<Mapping, Failure> {
    let read = || -> Option<Mapping> {
        Some(Mapping {
            url: document["obs"]["url"].as_str()?.to_owned(),
            keys: Vec::deserialize(&document["keys"]).ok()?,
            buttons: Vec::deserialize(&document["buttons"]).ok()?,
            knobs: Vec::deserialize(&document["knobs"]).ok()?,
        })
    };
    read().ok_or_else(|| Failure("the pad holds no mapping to edit".to_owned()))
}

/// `document` with `mapping` in it. Every other member, and every member of an entry the form
/// does not own, stays as it was; a target an action does not use is dropped. The validator runs
/// on the write, not here.
pub fn apply(document: &Value, mapping: &Mapping) -> Result<Value, Failure> {
    let mut edited = document.clone();
    let root = edited.as_object_mut().ok_or_else(|| Failure("the pad holds no document to edit".to_owned()))?;
    object_at(root, "obs").insert("url".to_owned(), Value::from(mapping.url.as_str()));
    merge_list(root, "keys", &mapping.keys, |entry, key| merge_action(entry, key, REFERENCED));
    merge_list(root, "buttons", &mapping.buttons, |entry, button| merge_action(entry, button, REFERENCED));
    merge_list(root, "knobs", &mapping.knobs, merge_knob);
    Ok(edited)
}

/// The URL field's rule, the same function the validator runs (spec 8.2).
pub fn check_url(url: &str) -> Result<(), Failure> {
    if is_private_ws_url(url) {
        Ok(())
    } else {
        Err(Failure(URL_RULE.to_owned()))
    }
}

/// A picker's choices, in the pad's order. An item with the all-zero UUID (OBS gave one that is
/// not in text form) cannot be referenced and is left out. A name becomes a label of at most
/// `LABEL_MAX` bytes, cut on a character boundary; bytes that are not UTF-8 show as U+FFFD.
pub fn choices(items: &[ObsItem]) -> Vec<Reference> {
    items
        .iter()
        .filter(|item| item.uuid != [0; UUID_LEN])
        .map(|item| Reference { uuid: uuid_text(&item.uuid), label: label(&item.name) })
        .collect()
}

/// The 8-4-4-4-12 text form, lowercase, as OBS writes it.
fn uuid_text(bytes: &[u8; UUID_LEN]) -> String {
    let mut text = String::with_capacity(36);
    for (index, byte) in bytes.iter().enumerate() {
        if matches!(index, 4 | 6 | 8 | 10) {
            text.push('-');
        }
        text.push_str(&format!("{byte:02x}"));
    }
    text
}

fn label(name: &[u8]) -> String {
    let text = String::from_utf8_lossy(name);
    let mut end = text.len().min(LABEL_MAX);
    while !text.is_char_boundary(end) {
        end -= 1;
    }
    text[..end].to_owned()
}

/// `slot` as an object; anything else in it is replaced by an empty one.
fn as_object(slot: &mut Value) -> &mut Map<String, Value> {
    if !slot.is_object() {
        *slot = Value::Object(Map::new());
    }
    slot.as_object_mut().expect("made an object above")
}

fn object_at<'a>(parent: &'a mut Map<String, Value>, name: &str) -> &'a mut Map<String, Value> {
    as_object(parent.entry(name).or_insert(Value::Null))
}

/// The list `name` cut or grown to `forms.len()`, each entry merged with its form.
fn merge_list<T>(root: &mut Map<String, Value>, name: &str, forms: &[T], merge: impl Fn(&mut Map<String, Value>, &T)) {
    let slot = root.entry(name).or_insert(Value::Null);
    if !slot.is_array() {
        *slot = Value::Array(Vec::new());
    }
    let list = slot.as_array_mut().expect("made an array above");
    list.resize(forms.len(), Value::Null);
    for (entry, form) in list.iter_mut().zip(forms) {
        merge(as_object(entry), form);
    }
}

/// `do`, and the target only when `act` is one of `referenced`.
fn merge_action(entry: &mut Map<String, Value>, action: &Action, referenced: &[&str]) {
    entry.remove("uuid");
    entry.remove("label");
    entry.insert("do".to_owned(), Value::from(action.act.as_str()));
    if let Some(target) = action.target.as_ref().filter(|_| referenced.contains(&action.act.as_str())) {
        entry.insert("uuid".to_owned(), Value::from(target.uuid.as_str()));
        entry.insert("label".to_owned(), Value::from(target.label.as_str()));
    }
}

/// `input` and `step_db` are written only when they change, so an untouched knob keeps its bytes
/// (`1` stays `1`, not `1.0`) and the unknown members of its input.
fn merge_knob(entry: &mut Map<String, Value>, knob: &Knob) {
    let input = entry.get("input").and_then(|input| Reference::deserialize(input).ok());
    if input != knob.input {
        let reference = knob.input.as_ref().map(|input| serde_json::json!({"uuid": input.uuid, "label": input.label}));
        entry.insert("input".to_owned(), reference.unwrap_or(Value::Null));
    }
    if entry.get("step_db").and_then(Value::as_f64) != Some(knob.step_db) {
        entry.insert("step_db".to_owned(), Value::from(knob.step_db));
    }
    merge_action(object_at(entry, "push"), &knob.push, PUSH_REFERENCED);
}

#[cfg(test)]
mod tests {
    use super::*;
    use obs_core::document::Document;
    use serde_json::json;

    const FULL: &str = include_str!("../../../firmware/test/config_vectors/valid_full.json");
    const UNKNOWN: &str = include_str!("../../../firmware/test/config_vectors/valid_unknown_fields.json");

    fn doc(text: &str) -> Value {
        serde_json::from_str(text).expect("vector is JSON")
    }

    fn valid(document: &Value) -> bool {
        Document::parse(document.to_string().as_bytes(), 1..=1).is_ok()
    }

    #[test]
    fn the_mapping_reads_url_keys_buttons_and_knobs() {
        let form = mapping(&doc(FULL)).expect("mapping");
        assert_eq!(form.url, "ws://192.168.1.20:4455");
        assert_eq!((form.keys.len(), form.buttons.len(), form.knobs.len()), (9, 4, 3));
        let cam = Reference { uuid: "0b0e6b1c-7f0a-4a55-9a43-000000000001".into(), label: "Cam".into() };
        assert_eq!(form.keys[0], Action { act: "scene".into(), target: Some(cam) });
        assert_eq!(form.buttons[0], Action { act: "toggle_record".into(), target: None });
        assert_eq!(form.knobs[1].step_db, 2.5);
        assert_eq!(form.knobs[2].input, None);
    }

    #[test]
    fn an_untouched_mapping_gives_back_the_same_document_unknown_members_included() {
        for text in [FULL, UNKNOWN] {
            let read = doc(text);
            assert_eq!(apply(&read, &mapping(&read).expect("mapping")).expect("apply"), read);
        }
    }

    #[test]
    fn one_key_and_the_url_change_and_nothing_else() {
        let read = doc(UNKNOWN);
        let mut form = mapping(&read).expect("mapping");
        form.url = "ws://10.0.0.7:4456".into();
        form.keys[8] = Action {
            act: "scene".into(),
            target: Some(Reference { uuid: "00000007-0000-4000-8000-000000000000".into(), label: "Scene 007".into() }),
        };
        let edited = apply(&read, &form).expect("apply");
        let mut want = read.clone();
        want["obs"]["url"] = json!("ws://10.0.0.7:4456");
        want["keys"][8] = json!({"do": "scene", "uuid": "00000007-0000-4000-8000-000000000000", "label": "Scene 007"});
        assert_eq!(edited, want);
        assert!(valid(&edited));
    }

    #[test]
    fn a_new_action_keeps_the_entry_s_unknown_members() {
        let read = doc(UNKNOWN);
        let mut form = mapping(&read).expect("mapping");
        form.keys[0].act = "toggle_record".into();
        let edited = apply(&read, &form).expect("apply");
        assert_eq!(edited["keys"][0], json!({"do": "toggle_record", "colour": "#C8102E"}));
    }

    #[test]
    fn an_action_without_a_target_drops_the_one_the_form_still_holds() {
        let read = doc(FULL);
        let mut form = mapping(&read).expect("mapping");
        let mic = form.keys[4].target.clone();
        form.buttons[3] = Action { act: "transition".into(), target: mic.clone() };
        form.knobs[0].push = Action { act: "toggle_mute".into(), target: mic.clone() };
        form.knobs[1].push = Action { act: "scene".into(), target: mic };
        let edited = apply(&read, &form).expect("apply");
        assert_eq!(edited["buttons"][3], json!({"do": "transition"}));
        assert_eq!(edited["knobs"][0]["push"], json!({"do": "toggle_mute"}), "a push mute acts on its own input");
        assert_eq!(edited["knobs"][1]["push"]["uuid"], json!("0b0e6b1c-7f0a-4a55-9a43-000000000010"));
        assert!(valid(&edited));
    }

    #[test]
    fn a_knob_input_and_step_change_only_when_edited() {
        let read = doc(UNKNOWN);
        let mut form = mapping(&read).expect("mapping");
        form.knobs[2].input = form.knobs[1].input.clone();
        form.knobs[0].step_db = 0.5;
        form.knobs[1].input = None;
        let edited = apply(&read, &form).expect("apply");
        assert_eq!(edited["knobs"][2]["input"], read["knobs"][1]["input"]);
        assert_eq!(edited["knobs"][1]["input"], Value::Null);
        assert_eq!(edited["knobs"][0]["step_db"], json!(0.5));
        assert_eq!(edited["knobs"][1]["step_db"], json!(2.5));
        assert!(valid(&edited));
    }

    #[test]
    fn a_form_with_a_wrong_count_is_written_as_it_is_and_the_validator_refuses_it() {
        let read = doc(FULL);
        let mut form = mapping(&read).expect("mapping");
        form.keys.pop();
        let edited = apply(&read, &form).expect("apply");
        assert_eq!(edited["keys"].as_array().map(Vec::len), Some(8));
        assert!(!valid(&edited));
    }

    #[test]
    fn a_pad_with_no_document_or_no_mapping_gives_a_failure() {
        assert!(mapping(&Value::Null).is_err());
        assert!(mapping(&json!({"obs": {"url": "ws://10.0.0.2"}, "keys": []})).is_err());
        let form = mapping(&doc(FULL)).expect("mapping");
        assert!(apply(&Value::Null, &form).is_err());
    }

    #[test]
    fn the_url_rule_takes_a_private_ws_address_and_nothing_else() {
        for good in ["ws://192.168.1.20:4455", "ws://10.0.0.2", "ws://172.16.0.1:1"] {
            assert_eq!(check_url(good), Ok(()), "{good}");
        }
        let bad = [
            "",
            "wss://192.168.1.20:4455",
            "ws://127.0.0.1:4455",
            "ws://8.8.8.8:4455",
            "ws://obs.local:4455",
            "ws://a@192.168.1.20",
            "ws://192.168.1.20/path",
            "ws://192.168.1.20?q",
            "ws://192.168.1.20:0",
        ];
        for url in bad {
            assert!(check_url(url).is_err(), "{url}");
        }
    }

    fn scene(index: u16) -> ObsItem {
        let mut uuid = [0; UUID_LEN];
        uuid[2..4].copy_from_slice(&index.to_be_bytes());
        uuid[6] = 0x40;
        uuid[8] = 0x80;
        ObsItem { uuid, name: format!("Scene {index:03}").into_bytes() }
    }

    #[test]
    fn criterion_8_the_picker_takes_500_scenes_in_order() {
        let items: Vec<ObsItem> = (0..500).map(scene).collect();
        let picked = choices(&items);
        assert_eq!(picked.len(), 500);
        assert_eq!(
            picked[0],
            Reference { uuid: "00000000-0000-4000-8000-000000000000".into(), label: "Scene 000".into() }
        );
        assert_eq!(picked[499].uuid, "000001f3-0000-4000-8000-000000000000");
        assert_eq!(picked[499].label, "Scene 499");
        assert!(picked.iter().all(valid_reference));
    }

    fn valid_reference(choice: &Reference) -> bool {
        let mut document = doc(FULL);
        document["keys"][0] = json!({"do": "scene", "uuid": choice.uuid, "label": choice.label});
        valid(&document)
    }

    #[test]
    fn a_name_becomes_a_label_of_48_bytes_cut_on_a_character_boundary() {
        let long = ObsItem { uuid: scene(1).uuid, name: "й".repeat(30).into_bytes() };
        let broken = ObsItem { uuid: scene(2).uuid, name: vec![b'A', 0xFF, b'B'] };
        let picked = choices(&[long, broken]);
        assert_eq!(picked[0].label, "й".repeat(24));
        assert_eq!(picked[1].label, "A\u{FFFD}B");
    }

    #[test]
    fn an_item_with_the_zero_uuid_is_not_offered() {
        let unnamed = ObsItem { uuid: [0; UUID_LEN], name: b"Scene x".to_vec() };
        assert_eq!(choices(&[unnamed, scene(3)]).len(), 1);
    }
}
