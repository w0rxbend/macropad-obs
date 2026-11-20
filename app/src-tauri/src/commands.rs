// SPDX-License-Identifier: MIT
//! The window's commands. Each locks the one `Connection` and makes one call into `app_core`. A
//! failure reaches the UI as the rejected value, one `Failure` line, and goes to the log; nothing
//! here panics. `(async)` runs the blocking serial calls off the main thread.

use std::sync::{Mutex, MutexGuard, PoisonError};

use app_core::discover::UsbPort;
use app_core::forms::{self, Mapping, ObsList, Reference};
use app_core::{Config, Connection, Credential, Failure, PadInfo, Saved, Status};
use serde_json::Value;
use serialport::SerialPort;
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
