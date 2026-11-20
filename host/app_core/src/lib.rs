// SPDX-License-Identifier: MIT
//! The app's core without a window: find the pad, then read and write its config document over
//! the CDC link, provision its secrets (spec 8.2), preview its displays with the firmware's C
//! (criterion 4b), and update its firmware (criterion 14). The Tauri commands are thin calls into
//! this crate.

mod connection;
mod diff;
pub mod discover;
mod link;
pub mod preview;
mod provision;
mod session;
pub mod update;

pub use connection::{pads, Config, Connection, Failure, PadInfo, Saved};
pub use diff::Change;
pub use link::LinkError;
pub use obs_core::document::{Document, Rejected, WriteRefused};
pub use obs_core::protocol::{Info, Secret};
pub use provision::{export, Credential, Status};
pub use session::{Session, SessionError, Stored, Written};
