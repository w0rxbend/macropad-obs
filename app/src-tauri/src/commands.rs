// SPDX-License-Identifier: MIT
//! The window's commands. Each locks the one `Connection` and makes one call into `app_core`. A
//! failure reaches the UI as the rejected value, one `Failure` line, and goes to the log; nothing
//! here panics. `(async)` runs the blocking serial calls off the main thread.

use std::path::Path;
use std::sync::{Mutex, MutexGuard, PoisonError};

use app_core::discover::UsbPort;
use app_core::forms::{self, Layout, Mapping, Network, ObsList, Reference, Secrets};
use app_core::{Config, Connection, Credential, Failure, NetworkPage, NetworkSaved, PadInfo, Saved, Status};
use serde_json::Value;
use serialport::SerialPort;
use tauri::ipc::Response;
use tauri::State;

use crate::logbuf::Log;

/// What every command shares: the pad connection, one command at a time, and the log.
pub struct Shared {
    connection: Mutex<Connection<Box<dyn SerialPort>>>,
    log: Log,
}

impl Shared {
    pub fn new(log: Log) -> Self {
        Self { connection: Mutex::new(Connection::new()), log }
    }

    /// The connection. A command that panicked mid-call left no half-made state that matters: the
    /// next call starts a new request.
    fn connection(&self) -> MutexGuard<'_, Connection<Box<dyn SerialPort>>> {
        self.connection.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// `outcome` as it is, with a failure logged under `command`. A `Failure` holds no secret.
    fn logged<T>(&self, command: &str, outcome: Result<T, Failure>) -> Result<T, Failure> {
        if let Err(failure) = &outcome {
            self.log.info(&format!("{command}: {failure}"));
        }
        outcome
    }
}

#[tauri::command(async)]
pub fn list_pads(shared: State<'_, Shared>) -> Result<Vec<UsbPort>, Failure> {
    shared.logged("list_pads", app_core::pads())
}

#[tauri::command(async)]
pub fn connect(shared: State<'_, Shared>, serial: Option<String>) -> Result<PadInfo, Failure> {
    shared.logged("connect", shared.connection().connect(serial.as_deref()))
}

#[tauri::command(async)]
pub fn disconnect(shared: State<'_, Shared>) -> Result<(), Failure> {
    shared.connection().disconnect();
    Ok(())
}

#[tauri::command(async)]
pub fn pad_info(shared: State<'_, Shared>) -> Result<PadInfo, Failure> {
    shared.logged("pad_info", shared.connection().info())
}

#[tauri::command(async)]
pub fn read_config(shared: State<'_, Shared>) -> Result<Config, Failure> {
    shared.logged("read_config", shared.connection().read())
}

#[tauri::command(async)]
pub fn write_config(shared: State<'_, Shared>, document: Value) -> Result<Saved, Failure> {
    shared.logged("write_config", shared.connection().write(document))
}

#[tauri::command(async)]
pub fn set_credential(shared: State<'_, Shared>, credential: Credential, secret: String) -> Result<PadInfo, Failure> {
    shared.logged("set_credential", shared.connection().set_credential(credential, secret))
}

#[tauri::command(async)]
pub fn clear_credentials(shared: State<'_, Shared>) -> Result<PadInfo, Failure> {
    shared.logged("clear_credentials", shared.connection().clear_credentials())
}

#[tauri::command(async)]
pub fn pad_status(shared: State<'_, Shared>) -> Result<Option<Status>, Failure> {
    shared.logged("pad_status", shared.connection().status())
}

#[tauri::command(async)]
pub fn export_config(shared: State<'_, Shared>) -> Result<String, Failure> {
    shared.logged("export_config", shared.connection().export())
}

#[tauri::command(async)]
pub fn read_mapping(shared: State<'_, Shared>) -> Result<Mapping, Failure> {
    shared.logged("read_mapping", shared.connection().read_mapping())
}

#[tauri::command(async)]
pub fn write_mapping(shared: State<'_, Shared>, mapping: Mapping) -> Result<Saved, Failure> {
    shared.logged("write_mapping", shared.connection().write_mapping(&mapping))
}

#[tauri::command(async)]
pub fn obs_list(shared: State<'_, Shared>, list: ObsList) -> Result<Vec<Reference>, Failure> {
    shared.logged("obs_list", shared.connection().obs_list(list))
}

/// The URL field's rule as the user types; no pad needed, so nothing is logged.
#[tauri::command]
pub fn check_url(url: String) -> Result<(), Failure> {
    forms::check_url(&url)
}

#[tauri::command(async)]
pub fn read_layout(shared: State<'_, Shared>) -> Result<Layout, Failure> {
    shared.logged("read_layout", shared.connection().read_layout())
}

#[tauri::command(async)]
pub fn write_layout(shared: State<'_, Shared>, layout: Layout) -> Result<Saved, Failure> {
    shared.logged("write_layout", shared.connection().write_layout(&layout))
}

/// Both panels as one binary answer, the main frame then the strip frame, each big-endian RGB565
/// row by row (`app_core::preview`). It runs as the user edits, so a refused layout is not logged.
#[tauri::command(async)]
pub fn preview(shared: State<'_, Shared>, layout: Layout) -> Result<Response, Failure> {
    let frames = shared.connection().preview(&layout)?;
    Ok(Response::new([frames.main, frames.strip].concat()))
}

#[tauri::command(async)]
pub fn read_network(shared: State<'_, Shared>) -> Result<NetworkPage, Failure> {
    shared.logged("read_network", shared.connection().read_network())
}

/// `secrets` is emptied and zeroed by the call, and dropped with it.
#[tauri::command(async)]
pub fn write_network(shared: State<'_, Shared>, network: Network, mut secrets: Secrets) -> Result<NetworkSaved, Failure> {
    shared.logged("write_network", shared.connection().write_network(&network, &mut secrets))
}

#[tauri::command(async)]
pub fn update_firmware(shared: State<'_, Shared>, image: String) -> Result<PadInfo, Failure> {
    shared.logged("update_firmware", shared.connection().update(Path::new(&image)))
}
