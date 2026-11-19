// SPDX-License-Identifier: MIT

use tauri_build::{AppManifest, Attributes};

/// Tauri generates `allow-<command>` only for the names listed here, and
/// `capabilities/default.json` grants them. Keep the list equal to `generate_handler!` in
/// `src/main.rs`.
const COMMANDS: &[&str] =
    &["get_state", "set_connection", "set_key", "select_input", "set_profile", "connect", "disconnect"];

fn main() -> tauri_build::Result<()> {
    tauri_build::try_build(Attributes::new().app_manifest(AppManifest::new().commands(COMMANDS)))
}
