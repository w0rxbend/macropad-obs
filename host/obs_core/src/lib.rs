// SPDX-License-Identifier: MIT
//! The app's half of the pad contracts: the CDC frame codec and the config document. The pad
//! maps inputs to OBS requests itself (`firmware/core/actions.c`).

mod config;
pub mod document;
pub mod protocol;

pub use config::{connect_target, default_config_path, load, parse, save, Config, ConfigError, KeyAction, Secret};
pub use protocol::{LinkRx, PadEvent, PageView, USB_PID, USB_VID};
