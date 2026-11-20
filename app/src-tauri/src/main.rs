// SPDX-License-Identifier: MIT

mod commands;
mod logbuf;

use tauri::Manager;

fn main() {
    let ran = tauri::Builder::default()
        .setup(|app| {
            app.manage(commands::Shared::new(logbuf::Log::open()));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::list_pads,
            commands::connect,
            commands::disconnect,
            commands::pad_info,
            commands::read_config,
            commands::write_config,
            commands::set_credential,
            commands::clear_credentials,
            commands::pad_status,
            commands::export_config,
        ])
        .run(tauri::generate_context!());
    if let Err(err) = ran {
        eprintln!("macropad-obs: {err}");
        std::process::exit(1);
    }
}
