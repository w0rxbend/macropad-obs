// SPDX-License-Identifier: MIT
//! The display preview (spec 13 criterion 4b, R13 "Live preview"): the firmware's own `fw-ui` C,
//! built by `build.rs` through `cc`, draws a document and a sample OBS state into the two frames
//! the pad shows. The frames are padsim's dump format: visible pixels, row by row, big-endian
//! RGB565. A preview shows the pad with Wi-Fi up and OBS up and current; REC and LIVE count 0 s.

use std::ffi::{c_char, c_int, CString};
use std::fmt;

use obs_core::document::Document;
use serde_json::Value;

/// `main_display`: 320 x 480 pixels, 2 bytes each.
pub const MAIN_BYTES: usize = 320 * 480 * 2;
/// `strip_display`: 142 x 428 pixels, 2 bytes each.
pub const STRIP_BYTES: usize = 142 * 428 * 2;

/// The longest UUID config takes, and the cut of a scene or input name (`obs_state.h`).
const UUID_MAX: usize = 36;
const NAME_MAX: usize = 48;

// The return values of `preview_render` (`preview.c`).
const PREVIEW_OK: c_int = 0;
const PREVIEW_REFUSED: c_int = 1;

/// Both panels, each as padsim's `dump` writes it.
#[derive(Clone, PartialEq, Eq)]
pub struct Frames {
    pub main: Vec<u8>,
    pub strip: Vec<u8>,
}

impl fmt::Debug for Frames {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Frames {{ main: {} B, strip: {} B }}", self.main.len(), self.strip.len())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PreviewError {
    /// The sample state is not the shape of `tools/fixtures/ui_state.json`: the member at fault.
    BadState(&'static str),
    /// The `fw-ui` core refused a document the validator passed.
    Refused,
    /// The C side could not get its working memory, or drew outside a panel.
    Internal(c_int),
}

impl fmt::Display for PreviewError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::BadState(member) => write!(f, "the sample OBS state has no valid `{member}`"),
            Self::Refused => f.write_str("the display core refused the layout"),
            Self::Internal(code) => write!(f, "the preview failed inside the display core (code {code})"),
        }
    }
}

impl std::error::Error for PreviewError {}

/// One scene or input as `obs_state.c` keeps it from an OBS reply.
#[derive(Debug, Clone)]
struct Item {
    uuid: CString,
    name: CString,
    muted: bool,
    volume_db: f32,
}

/// What OBS shows in a preview, in the form `tools/fake_obs.py` serves: the same file gives the
/// pad and the preview the same state.
#[derive(Debug, Clone)]
pub struct SampleState {
    scenes: Vec<Item>,
    inputs: Vec<Item>,
    program: CString,
    preview: CString,
    studio_mode: bool,
    recording: bool,
    streaming: bool,
}

impl SampleState {
    /// Reads the `ui_state.json` form: `currentProgramSceneUuid`, `currentPreviewSceneUuid`
    /// (string or null), `studioModeEnabled`, `scenes` of `sceneName` and `sceneUuid`, `inputs` of
    /// `inputName`, `inputUuid`, `inputMuted` and `inputVolumeDb`, `recordActive` and `streamActive`.
    /// A UUID config would refuse reads as none, so that scene or input is left out, as on the pad.
    pub fn from_json(bytes: &[u8]) -> Result<Self, PreviewError> {
        let json: Value = serde_json::from_slice(bytes).map_err(|_| PreviewError::BadState("the root object"))?;
        let preview = match &json["currentPreviewSceneUuid"] {
            Value::Null => "",
            value => value.as_str().ok_or(PreviewError::BadState("currentPreviewSceneUuid"))?,
        };
        Ok(Self {
            scenes: items(&json, "scenes", "sceneUuid", "sceneName", false)?,
            inputs: items(&json, "inputs", "inputUuid", "inputName", true)?,
            program: obs_uuid(text(&json, "currentProgramSceneUuid")?),
            preview: obs_uuid(preview),
            studio_mode: flag(&json, "studioModeEnabled")?,
            recording: flag(&json, "recordActive")?,
            streaming: flag(&json, "streamActive")?,
        })
    }
}

fn text<'a>(json: &'a Value, member: &'static str) -> Result<&'a str, PreviewError> {
    json[member].as_str().ok_or(PreviewError::BadState(member))
}

fn flag(json: &Value, member: &'static str) -> Result<bool, PreviewError> {
    json[member].as_bool().ok_or(PreviewError::BadState(member))
}

fn items(
    json: &Value,
    list: &'static str,
    uuid: &'static str,
    name: &'static str,
    audio: bool,
) -> Result<Vec<Item>, PreviewError> {
    let entries = json[list].as_array().ok_or(PreviewError::BadState(list))?;
    let mut kept = Vec::with_capacity(entries.len());
    for entry in entries {
        let (muted, volume_db) = if audio {
            let volume = entry["inputVolumeDb"].as_f64().ok_or(PreviewError::BadState("inputVolumeDb"))?;
            // The pad reads the number with strtof; a dB value has far fewer digits than an f32.
            (flag(entry, "inputMuted")?, volume as f32)
        } else {
            (false, 0.0)
        };
        let uuid = obs_uuid(text(entry, uuid)?);
        if !uuid.as_bytes().is_empty() {
            kept.push(Item { uuid, name: obs_name(text(entry, name)?), muted, volume_db });
        }
    }
    Ok(kept)
}

/// The UUID, or none for one config refuses: 1..=36 bytes, each 0x21..=0x7E (`obs_state.c`).
fn obs_uuid(uuid: &str) -> CString {
    let valid = (1..=UUID_MAX).contains(&uuid.len()) && uuid.bytes().all(|byte| (0x21..=0x7E).contains(&byte));
    CString::new(if valid { uuid } else { "" }).expect("a valid UUID has no NUL byte")
}

/// The name cut to `NAME_MAX` bytes, never inside a character; a NUL byte ends it (`obs_state.c`).
fn obs_name(name: &str) -> CString {
    let name = name.split('\0').next().unwrap_or_default();
    let mut len = name.len().min(NAME_MAX);
    while !name.is_char_boundary(len) {
        len -= 1;
    }
    CString::new(&name[..len]).expect("the name stops before its first NUL byte")
}

#[repr(C)]
struct CItem {
    uuid: *const c_char,
    name: *const c_char,
    muted: bool,
    volume_db: f32,
}

#[repr(C)]
struct CObs {
    scenes: *const CItem,
    scene_count: usize,
    inputs: *const CItem,
    input_count: usize,
    program: *const c_char,
    preview: *const c_char,
    studio_mode: bool,
    recording: bool,
    streaming: bool,
}

extern "C" {
    fn preview_render(doc: *const u8, len: usize, sample: *const CObs, main_rgb: *mut u8, strip_rgb: *mut u8) -> c_int;
}

fn c_items(items: &[Item]) -> Vec<CItem> {
    let c_item = |item: &Item| CItem {
        uuid: item.uuid.as_ptr(),
        name: item.name.as_ptr(),
        muted: item.muted,
        volume_db: item.volume_db,
    };
    items.iter().map(c_item).collect()
}

/// Both frames as the pad draws `doc` while OBS holds `state`.
pub fn render(doc: &Document, state: &SampleState) -> Result<Frames, PreviewError> {
    let bytes = doc.to_bytes();
    let (scenes, inputs) = (c_items(&state.scenes), c_items(&state.inputs));
    let sample = CObs {
        scenes: scenes.as_ptr(),
        scene_count: scenes.len(),
        inputs: inputs.as_ptr(),
        input_count: inputs.len(),
        program: state.program.as_ptr(),
        preview: state.preview.as_ptr(),
        studio_mode: state.studio_mode,
        recording: state.recording,
        streaming: state.streaming,
    };
    let mut frames = Frames { main: vec![0; MAIN_BYTES], strip: vec![0; STRIP_BYTES] };
    // SAFETY: every pointer is live for the call: `bytes`, the item vectors and the CStrings they
    // point into outlive it, and each frame holds the byte count `preview_render` writes. The C
    // side keeps no pointer after it returns.
    let code = unsafe {
        preview_render(bytes.as_ptr(), bytes.len(), &sample, frames.main.as_mut_ptr(), frames.strip.as_mut_ptr())
    };
    match code {
        PREVIEW_OK => Ok(frames),
        PREVIEW_REFUSED => Err(PreviewError::Refused),
        _ => Err(PreviewError::Internal(code)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const STATE: &str = r#"{"currentProgramSceneUuid":"S_A","currentPreviewSceneUuid":null,
        "studioModeEnabled":false,"scenes":[{"sceneName":"Camera","sceneUuid":"S_A"},
        {"sceneName":"Bad","sceneUuid":"has space"}],
        "inputs":[{"inputMuted":true,"inputName":"Mic","inputUuid":"U_A","inputVolumeDb":-6}],
        "recordActive":true,"streamActive":false}"#;

    #[test]
    fn a_uuid_config_refuses_is_left_out() {
        let state = SampleState::from_json(STATE.as_bytes()).expect("valid");
        assert_eq!(state.scenes.len(), 1);
        assert_eq!(state.preview.as_bytes(), b"", "null preview reads as none");
        assert!(state.recording && !state.streaming && state.inputs[0].muted);
    }

    #[test]
    fn a_missing_member_is_named() {
        let err = SampleState::from_json(br#"{"currentProgramSceneUuid":"S_A"}"#).expect_err("incomplete");
        assert_eq!(err, PreviewError::BadState("scenes"));
        assert_eq!(SampleState::from_json(b"[1]").expect_err("not an object"), PreviewError::BadState("scenes"));
    }

    #[test]
    fn a_name_is_cut_at_a_whole_character() {
        let long = "\u{0436}".repeat(30); // 60 bytes of 2-byte characters
        assert_eq!(obs_name(&long).as_bytes().len(), NAME_MAX);
        let odd = format!("a{long}");
        assert_eq!(obs_name(&odd).as_bytes().len(), NAME_MAX - 1, "never inside a character");
        assert_eq!(obs_name("Mic\0tail").as_bytes(), b"Mic");
    }
}
