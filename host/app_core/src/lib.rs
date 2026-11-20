// SPDX-License-Identifier: MIT
//! The app's core without a window: find the pad, then read and write its config document over
//! the CDC link (spec 8.2). The Tauri commands are thin calls into this crate.

mod diff;
pub mod discover;
mod link;
mod session;

pub use diff::Change;
pub use link::LinkError;
pub use obs_core::document::{Document, Rejected, WriteRefused};
pub use obs_core::protocol::Info;
pub use session::{Session, SessionError, Stored, Written};
