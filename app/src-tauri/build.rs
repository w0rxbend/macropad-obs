// SPDX-License-Identifier: MIT

use tauri_build::{AppManifest, Attributes};

/// Tauri generates `allow-<command>` only for the names listed here, and
/// `capabilities/default.json` grants them. Keep the list equal to `generate_handler!` in
/// `src/main.rs`.
const COMMANDS: &[&str] = &[
    "list_pads",
    "connect",
    "disconnect",
    "pad_info",
    "read_config",
    "write_config",
    "set_credential",
    "clear_credentials",
    "pad_status",
    "export_config",
    "read_mapping",
    "write_mapping",
    "obs_list",
    "check_url",
    "read_layout",
    "write_layout",
    "preview",
    "read_network",
    "write_network",
    "update_firmware",
];

fn main() -> tauri_build::Result<()> {
    tauri_build::try_build(Attributes::new().app_manifest(AppManifest::new().commands(COMMANDS)))
}
