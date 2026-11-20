// SPDX-License-Identifier: MIT
//! OBS keymap core. The shell does the websocket and the serial port.

mod config;
pub mod document;
mod keymap;
mod paging;
mod profile;
pub mod protocol;
mod volume;

pub use config::{connect_target, default_config_path, load, parse, save, Config, ConfigError, KeyAction, Secret};
pub use protocol::{LinkRx, PadEvent, PageView, USB_PID, USB_VID};
pub use volume::round_db;

use keymap::{scene_count, scene_slot, INPUT_CAP, KEYS, PROFILE_CAP, SCENE_CAP};
use paging::{build_page, page_count, step_page, PageFlags};
use profile::wrap_index;
use volume::{clamp_db, VolumeGate};

use serde::{Deserialize, Serialize};

// The OBS snapshot, requests and effects of `Core`. The firmware keeps the OBS state now
// (`firmware/core/obs_state.c`); these go with `Core` in task 2.12.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InputState {
    pub name: String,
    pub muted: bool,
    pub db: i8,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ObsSnapshot {
    pub scenes: Vec<String>,
    pub program: Option<String>,
    pub profile: String,
    pub profiles: Vec<String>,
    pub inputs: Vec<InputState>,
    pub streaming: bool,
    pub recording: bool,
    pub studio: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum ObsRequest {
    SetProgramScene { name: String },
    SetProfile { name: String },
    SetMute { name: String, muted: bool },
    SetVolumeDb { name: String, db: i8 },
    StartStream,
    StopStream,
    StartRecord,
    StopRecord,
    Transition,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Effect {
    Obs(ObsRequest),
    Notice(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CoreError {
    Index,
    SceneKeys,
    UnknownInput,
}

pub struct Core {
    config: Config,
    snap: ObsSnapshot,
    page: usize,
    selected: Option<String>,
    volume: VolumeGate,
    capped: bool,
}

impl Core {
    pub fn new(config: Config) -> Self {
        Self {
            config,
            snap: ObsSnapshot::default(),
            page: 0,
            selected: None,
            volume: VolumeGate::default(),
            capped: false,
        }
    }

    pub fn snapshot(&self) -> &ObsSnapshot {
        &self.snap
    }

    pub fn keys(&self) -> &[KeyAction; KEYS] {
        &self.config.keys
    }

    pub fn selected(&self) -> Option<&str> {
        self.selected.as_deref()
    }

    pub fn config(&self) -> &Config {
        &self.config
    }

    pub fn apply_snapshot(&mut self, mut snap: ObsSnapshot) {
        self.capped = trim(&mut snap);
        let keep = self.selected.as_ref().filter(|name| snap.inputs.iter().any(|input| input.name == **name)).cloned();
        self.selected = keep.or_else(|| snap.inputs.first().map(|input| input.name.clone()));
        self.snap = snap;
        self.volume.on_snapshot();
        let pages = page_count(self.snap.scenes.len(), scene_count(&self.config.keys));
        if self.page >= pages {
            self.page = 0;
        }
    }

    pub fn on_pad(&mut self, event: PadEvent) -> Vec<Effect> {
        match event {
            PadEvent::Hello { .. } => Vec::new(),
            PadEvent::Key { down: false, .. } => Vec::new(),
            PadEvent::Key { index, down: true } => self.key_down(index),
            PadEvent::Knob { detents } => self.knob(detents),
            PadEvent::Page { delta } => {
                let pages = page_count(self.snap.scenes.len(), scene_count(&self.config.keys));
                self.page = step_page(self.page, delta, pages);
                Vec::new()
            }
        }
    }

    pub fn poll(&mut self, now_ms: u64) -> Vec<Effect> {
        let Some(db) = self.volume.poll(now_ms) else {
            return Vec::new();
        };
        self.volume_effect(db).into_iter().collect()
    }

    pub fn page_view(&self) -> PageView {
        let notice = if self.capped { Some("capped".to_string()) } else { None };
        build_page(
            &self.config.keys,
            &self.snap.scenes,
            self.snap.program.as_deref(),
            self.page,
            PageFlags { studio: self.snap.studio, streaming: self.snap.streaming, recording: self.snap.recording },
            notice,
        )
    }

    pub fn select_input(&mut self, name: &str) -> Result<(), CoreError> {
        if !self.snap.inputs.iter().any(|input| input.name == name) {
            return Err(CoreError::UnknownInput);
        }
        self.selected = Some(name.to_string());
        Ok(())
    }

    pub fn set_key(&mut self, index: u8, action: KeyAction) -> Result<(), CoreError> {
        let slot = usize::from(index);
        if slot >= KEYS {
            return Err(CoreError::Index);
        }
        let mut keys = self.config.keys;
        keys[slot] = action;
        if scene_count(&keys) == 0 {
            return Err(CoreError::SceneKeys);
        }
        self.config.keys = keys;
        Ok(())
    }

    fn key_down(&mut self, index: u8) -> Vec<Effect> {
        let slot = usize::from(index);
        if slot >= KEYS {
            return Vec::new();
        }
        match self.config.keys[slot] {
            KeyAction::Scene => self.scene_press(index),
            KeyAction::Mute => self.mute_press(),
            KeyAction::Transition => self.transition_press(),
            KeyAction::Stream => self.stream_press(),
            KeyAction::Record => self.record_press(),
            KeyAction::ProfileNext => self.profile_press(1),
            KeyAction::ProfilePrev => self.profile_press(-1),
        }
    }

    fn scene_press(&mut self, index: u8) -> Vec<Effect> {
        let Some(slot) = scene_slot(&self.config.keys, index) else {
            return Vec::new();
        };
        let ordinal = self.page * scene_count(&self.config.keys) + slot;
        let Some(name) = self.snap.scenes.get(ordinal).cloned() else {
            return Vec::new();
        };
        vec![Effect::Obs(ObsRequest::SetProgramScene { name })]
    }

    fn mute_press(&mut self) -> Vec<Effect> {
        let Some(name) = self.selected.clone() else {
            return Vec::new();
        };
        let Some(input) = self.snap.inputs.iter_mut().find(|input| input.name == name) else {
            return Vec::new();
        };
        input.muted = !input.muted;
        let muted = input.muted;
        vec![Effect::Obs(ObsRequest::SetMute { name, muted })]
    }

    fn transition_press(&mut self) -> Vec<Effect> {
        if self.snap.studio {
            vec![Effect::Obs(ObsRequest::Transition)]
        } else {
            vec![Effect::Notice("studio off".to_string())]
        }
    }

    fn stream_press(&mut self) -> Vec<Effect> {
        self.snap.streaming = !self.snap.streaming;
        let request = if self.snap.streaming { ObsRequest::StartStream } else { ObsRequest::StopStream };
        vec![Effect::Obs(request)]
    }

    fn record_press(&mut self) -> Vec<Effect> {
        self.snap.recording = !self.snap.recording;
        let request = if self.snap.recording { ObsRequest::StartRecord } else { ObsRequest::StopRecord };
        vec![Effect::Obs(request)]
    }

    fn profile_press(&mut self, delta: i8) -> Vec<Effect> {
        let current = self.snap.profiles.iter().position(|name| name == &self.snap.profile);
        let Some(index) = wrap_index(self.snap.profiles.len(), current, delta) else {
            return Vec::new();
        };
        let name = self.snap.profiles[index].clone();
        self.snap.profile = name.clone();
        vec![Effect::Obs(ObsRequest::SetProfile { name })]
    }

    fn knob(&mut self, detents: i8) -> Vec<Effect> {
        let Some(base) = self.selected_db() else {
            return Vec::new();
        };
        let Some(db) = self.volume.detent(detents, base) else {
            return Vec::new();
        };
        self.volume_effect(db).into_iter().collect()
    }

    fn selected_db(&self) -> Option<i8> {
        let name = self.selected.as_deref()?;
        self.snap.inputs.iter().find(|input| input.name == name).map(|input| input.db)
    }

    fn volume_effect(&self, db: i8) -> Option<Effect> {
        let name = self.selected.clone()?;
        Some(Effect::Obs(ObsRequest::SetVolumeDb { name, db: clamp_db(i32::from(db)) }))
    }
}

fn trim(snap: &mut ObsSnapshot) -> bool {
    let mut capped = false;
    if snap.scenes.len() > SCENE_CAP {
        snap.scenes.truncate(SCENE_CAP);
        capped = true;
    }
    if snap.inputs.len() > INPUT_CAP {
        snap.inputs.truncate(INPUT_CAP);
        capped = true;
    }
    if snap.profiles.len() > PROFILE_CAP {
        snap.profiles.truncate(PROFILE_CAP);
        capped = true;
    }
    capped
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::PadEvent;

    fn config() -> Config {
        parse(
            r#"
            [obs]
            url = "ws://127.0.0.1:4455"
            password = "replace-me"
            allow_non_loopback = false
            [[key]]
            action = "scene"
            [[key]]
            action = "scene"
            [[key]]
            action = "scene"
            [[key]]
            action = "mute"
            [[key]]
            action = "transition"
            [[key]]
            action = "stream"
            [[key]]
            action = "record"
            [[key]]
            action = "profile_next"
            [[key]]
            action = "profile_prev"
            "#,
        )
        .unwrap()
    }

    fn snap() -> ObsSnapshot {
        ObsSnapshot {
            scenes: vec!["A".into(), "B".into()],
            program: Some("A".into()),
            profile: "Main".into(),
            profiles: vec!["Main".into(), "Alt".into()],
            inputs: vec![InputState { name: "Mic".into(), muted: false, db: 0 }],
            streaming: false,
            recording: false,
            studio: true,
        }
    }

    #[test]
    fn volume_window_ignores_snapshot_until_it_closes() {
        let mut core = Core::new(config());
        core.apply_snapshot(snap());
        core.poll(0);
        let first = core.on_pad(PadEvent::Knob { detents: 1 });
        assert_eq!(first, vec![Effect::Obs(ObsRequest::SetVolumeDb { name: "Mic".into(), db: 1 })]);
        assert!(core.on_pad(PadEvent::Knob { detents: 2 }).is_empty());
        let mut moved = snap();
        moved.inputs[0].db = 10;
        core.apply_snapshot(moved);
        assert_eq!(core.poll(30), vec![Effect::Obs(ObsRequest::SetVolumeDb { name: "Mic".into(), db: 3 })]);
        let mut later = snap();
        later.inputs[0].db = 10;
        core.apply_snapshot(later);
        assert_eq!(
            core.on_pad(PadEvent::Knob { detents: 1 }),
            vec![Effect::Obs(ObsRequest::SetVolumeDb { name: "Mic".into(), db: 11 })]
        );
    }

    #[test]
    fn studio_off_mute_profile_page_and_zero_scene_keys() {
        let mut core = Core::new(config());
        let mut off = snap();
        off.studio = false;
        core.apply_snapshot(off);
        assert_eq!(core.on_pad(PadEvent::Key { index: 4, down: true }), vec![Effect::Notice("studio off".into())]);
        assert!(core.on_pad(PadEvent::Key { index: 4, down: false }).is_empty());
        assert_eq!(
            core.on_pad(PadEvent::Key { index: 3, down: true }),
            vec![Effect::Obs(ObsRequest::SetMute { name: "Mic".into(), muted: true })]
        );
        assert_eq!(
            core.on_pad(PadEvent::Key { index: 3, down: true }),
            vec![Effect::Obs(ObsRequest::SetMute { name: "Mic".into(), muted: false })]
        );
        assert_eq!(
            core.on_pad(PadEvent::Key { index: 8, down: true }),
            vec![Effect::Obs(ObsRequest::SetProfile { name: "Alt".into() })]
        );
        assert_eq!(
            core.on_pad(PadEvent::Key { index: 8, down: true }),
            vec![Effect::Obs(ObsRequest::SetProfile { name: "Main".into() })]
        );
        core.snap.scenes.extend(["C".into(), "D".into()]);
        core.on_pad(PadEvent::Page { delta: 1 });
        assert_eq!(core.page_view().page, 1);
        core.on_pad(PadEvent::Page { delta: 1 });
        assert_eq!(core.page_view().page, 0);
        assert!(core.set_key(0, KeyAction::Mute).is_ok());
        assert!(core.set_key(1, KeyAction::Mute).is_ok());
        assert_eq!(core.set_key(2, KeyAction::Mute), Err(CoreError::SceneKeys));
        let mut empty = snap();
        empty.inputs.clear();
        core.apply_snapshot(empty);
        assert!(core.on_pad(PadEvent::Knob { detents: 1 }).is_empty());
    }

    #[test]
    fn caps_keep_prefix_and_notice_once_per_view() {
        let mut core = Core::new(config());
        let mut wide = snap();
        wide.scenes = (0..70).map(|n| format!("s{n}")).collect();
        wide.inputs = (0..40).map(|n| InputState { name: format!("i{n}"), muted: false, db: 0 }).collect();
        core.apply_snapshot(wide);
        assert_eq!(core.snapshot().scenes.len(), 64);
        assert_eq!(core.snapshot().inputs.len(), 32);
        assert_eq!(core.snapshot().scenes[0], "s0");
        assert_eq!(core.page_view().notice.as_deref(), Some("capped"));
    }

    #[test]
    fn clamp_and_stream_toggle() {
        let mut core = Core::new(config());
        let mut loud = snap();
        loud.inputs[0].db = 26;
        core.apply_snapshot(loud);
        assert_eq!(
            core.on_pad(PadEvent::Knob { detents: 4 }),
            vec![Effect::Obs(ObsRequest::SetVolumeDb { name: "Mic".into(), db: 26 })]
        );
        assert_eq!(core.on_pad(PadEvent::Key { index: 5, down: true }), vec![Effect::Obs(ObsRequest::StartStream)]);
        assert_eq!(core.on_pad(PadEvent::Key { index: 5, down: true }), vec![Effect::Obs(ObsRequest::StopStream)]);
        assert_eq!(core.on_pad(PadEvent::Hello { proto: 1, keys: 9, features: 0 }), Vec::<Effect>::new());
    }
}
