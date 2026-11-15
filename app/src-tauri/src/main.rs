// SPDX-License-Identifier: MIT

mod logbuf;
mod pad;
mod session;

use session::Cmd;
use tauri::State;
use tokio::sync::{mpsc, oneshot};

struct Shell {
    tx: mpsc::Sender<Cmd>,
}

async fn ask<T>(shell: &State<'_, Shell>, cmd: Cmd, rx: oneshot::Receiver<T>) -> Result<T, String> {
    shell.tx.send(cmd).await.map_err(|_| "session down".to_string())?;
    rx.await.map_err(|_| "session dropped".to_string())
}

#[tauri::command]
async fn get_state(shell: State<'_, Shell>) -> Result<session::UiState, String> {
    let (tx, rx) = oneshot::channel();
    ask(&shell, Cmd::GetState(tx), rx).await
}

#[tauri::command]
async fn set_connection(
    shell: State<'_, Shell>,
    url: String,
    password: String,
    allow_non_loopback: bool,
) -> Result<(), String> {
    let (tx, rx) = oneshot::channel();
    ask(&shell, Cmd::SetConnection { url, password, allow_non_loopback, reply: tx }, rx).await?
}

#[tauri::command]
async fn set_key(shell: State<'_, Shell>, index: u8, action: String) -> Result<(), String> {
    let (tx, rx) = oneshot::channel();
    ask(&shell, Cmd::SetKey { index, action, reply: tx }, rx).await?
}

#[tauri::command]
async fn select_input(shell: State<'_, Shell>, name: String) -> Result<(), String> {
    let (tx, rx) = oneshot::channel();
    ask(&shell, Cmd::SelectInput { name, reply: tx }, rx).await?
}

#[tauri::command]
async fn set_profile(shell: State<'_, Shell>, name: String) -> Result<(), String> {
    let (tx, rx) = oneshot::channel();
    ask(&shell, Cmd::SetProfile { name, reply: tx }, rx).await?
}

#[tauri::command]
async fn connect(shell: State<'_, Shell>) -> Result<(), String> {
    let (tx, rx) = oneshot::channel();
    ask(&shell, Cmd::Connect(tx), rx).await?
}

#[tauri::command]
async fn disconnect(shell: State<'_, Shell>) -> Result<(), String> {
    let (tx, rx) = oneshot::channel();
    ask(&shell, Cmd::Disconnect(tx), rx).await?
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            app.manage(Shell { tx: session::start() });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_state,
            set_connection,
            set_key,
            select_input,
            set_profile,
            connect,
            disconnect
        ])
        .run(tauri::generate_context!())
        .expect("tauri");
}
