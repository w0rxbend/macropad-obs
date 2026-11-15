// SPDX-License-Identifier: MIT
//! State log. Info lines are scrubbed before they hit disk.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

const LIMIT: u64 = 1_000_000;

pub struct Log {
    path: PathBuf,
    secret: String,
}

impl Log {
    pub fn open() -> Self {
        let dir = state_dir();
        let _ = fs::create_dir_all(&dir);
        #[cfg(unix)]
        if let Ok(meta) = fs::metadata(&dir) {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = meta.permissions();
            perms.set_mode(0o700);
            let _ = fs::set_permissions(&dir, perms);
        }
        Self { path: dir.join("app.log"), secret: String::new() }
    }

    pub fn set_secret(&mut self, secret: &str) {
        self.secret = secret.to_string();
    }

    pub fn info(&self, line: &str) {
        let clean = self.scrub(line);
        self.rotate();
        if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&self.path) {
            let _ = writeln!(file, "{clean}");
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let mut perms = file.metadata().map(|meta| meta.permissions()).unwrap_or_else(|_| {
                    std::fs::Permissions::from_mode(0o600)
                });
                perms.set_mode(0o600);
                let _ = file.set_permissions(perms);
            }
        }
    }

    pub fn scrub(&self, line: &str) -> String {
        if self.secret.is_empty() {
            return line.to_string();
        }
        line.replace(&self.secret, "***")
    }

    fn rotate(&self) {
        let Ok(meta) = fs::metadata(&self.path) else {
            return;
        };
        if meta.len() < LIMIT {
            return;
        }
        let aged = |index: u8| PathBuf::from(format!("{}.{index}", self.path.display()));
        let _ = fs::remove_file(aged(2));
        if aged(1).exists() {
            let _ = fs::rename(aged(1), aged(2));
        }
        let _ = fs::rename(&self.path, aged(1));
    }
}

fn state_dir() -> PathBuf {
    if let Some(xdg) = std::env::var_os("XDG_STATE_HOME") {
        return Path::new(&xdg).join("macropad-obs");
    }
    let home = std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    home.join(".local/state/macropad-obs")
}
