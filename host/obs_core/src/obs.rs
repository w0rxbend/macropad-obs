// SPDX-License-Identifier: MIT
//! Snapshot and requests. This module does no I/O.
//! Stream and record are on only for STARTED and RECONNECTED.
//! `outputActive` is not the on bit. obws 0.15 status structs have no `outputState`.

use serde::{Deserialize, Serialize};

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

/// obs-websocket `outputState` strings. Missing state is off.
pub fn output_is_on(state: &str) -> bool {
    state == "OBS_WEBSOCKET_OUTPUT_STARTED" || state == "OBS_WEBSOCKET_OUTPUT_RECONNECTED"
}

/// First OBS event arms `now + 50`. Later events do not move the deadline.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct EventBurst {
    deadline: Option<u64>,
}

impl EventBurst {
    pub fn push(&mut self, now_ms: u64) {
        if self.deadline.is_none() {
            self.deadline = Some(now_ms.saturating_add(50));
        }
    }

    pub fn poll(&mut self, now_ms: u64) -> bool {
        let Some(deadline) = self.deadline else {
            return false;
        };
        if now_ms < deadline {
            return false;
        }
        self.deadline = None;
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn output_on_is_only_started_and_reconnected() {
        assert!(output_is_on("OBS_WEBSOCKET_OUTPUT_STARTED"));
        assert!(output_is_on("OBS_WEBSOCKET_OUTPUT_RECONNECTED"));
        for state in [
            "OBS_WEBSOCKET_OUTPUT_STARTING",
            "OBS_WEBSOCKET_OUTPUT_STOPPING",
            "OBS_WEBSOCKET_OUTPUT_STOPPED",
            "OBS_WEBSOCKET_OUTPUT_RECONNECTING",
            "OBS_WEBSOCKET_OUTPUT_PAUSED",
            "OBS_WEBSOCKET_OUTPUT_RESUMED",
            "outputActive",
            "true",
            "",
        ] {
            assert!(!output_is_on(state), "{state}");
        }
    }

    #[test]
    fn burst_does_not_reset_the_deadline() {
        let mut burst = EventBurst::default();
        burst.push(1000);
        burst.push(1040);
        assert!(!burst.poll(1049));
        assert!(burst.poll(1050));
        assert!(!burst.poll(1051));
    }
}
