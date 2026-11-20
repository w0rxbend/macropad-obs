// SPDX-License-Identifier: MIT
//! XDG config. The password stays in this file. Frames never carry it.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::net::{Ipv6Addr, SocketAddr};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::keymap::scene_count;

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Secret(String);

impl Secret {
    pub fn reveal(&self) -> &str {
        &self.0
    }
}

impl std::fmt::Debug for Secret {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("***")
    }
}

impl std::fmt::Display for Secret {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("***")
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum KeyAction {
    Scene,
    Mute,
    Transition,
    Stream,
    Record,
    ProfileNext,
    ProfilePrev,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObsSettings {
    pub url: String,
    pub host: String,
    pub port: u16,
    pub password: Secret,
    pub allow_non_loopback: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    pub obs: ObsSettings,
    pub keys: [KeyAction; 9],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConfigError {
    Parse(String),
    Url,
    SceneKeys,
    KeyCount,
    Missing,
    Perms,
    Address,
    Io(String),
}

impl std::fmt::Display for ConfigError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Parse(text) => write!(f, "config parse: {text}"),
            Self::Url => write!(f, "obs url"),
            Self::SceneKeys => write!(f, "scene key count is 0"),
            Self::KeyCount => write!(f, "key count"),
            Self::Missing => write!(f, "config missing"),
            Self::Perms => write!(f, "config permissions"),
            Self::Address => write!(f, "connect address"),
            Self::Io(text) => write!(f, "config io: {text}"),
        }
    }
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct FileConfig {
    obs: ObsFile,
    key: Vec<KeyFile>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ObsFile {
    url: String,
    password: Secret,
    allow_non_loopback: bool,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct KeyFile {
    action: KeyAction,
}

pub fn parse(text: &str) -> Result<Config, ConfigError> {
    let file: FileConfig = toml::from_str(text).map_err(|err| ConfigError::Parse(err.to_string()))?;
    if file.key.len() != 9 {
        return Err(ConfigError::KeyCount);
    }
    let mut keys = [KeyAction::Scene; 9];
    for (slot, key) in keys.iter_mut().zip(file.key) {
        *slot = key.action;
    }
    if scene_count(&keys) == 0 {
        return Err(ConfigError::SceneKeys);
    }
    let (host, port) = split_url(&file.obs.url)?;
    Ok(Config {
        obs: ObsSettings {
            url: file.obs.url,
            host,
            port,
            password: file.obs.password,
            allow_non_loopback: file.obs.allow_non_loopback,
        },
        keys,
    })
}

pub fn load(path: &Path) -> Result<Config, ConfigError> {
    ensure_private_dir(path)?;
    let meta = match fs::metadata(path) {
        Ok(meta) => meta,
        Err(err) if err.kind() == io::ErrorKind::NotFound => return Err(ConfigError::Missing),
        Err(err) => return Err(io_err(err)),
    };
    if !meta.is_file() || meta.permissions().mode() & 0o077 != 0 {
        return Err(ConfigError::Perms);
    }
    let text = fs::read_to_string(path).map_err(io_err)?;
    parse(&text)
}

pub fn save(path: &Path, config: &Config) -> Result<(), ConfigError> {
    ensure_private_dir(path)?;
    let body = toml::to_string(&to_file(config)).map_err(|err| ConfigError::Parse(err.to_string()))?;
    let tmp = temp_path(path)?;
    let mut file = OpenOptions::new().write(true).create(true).truncate(true).mode(0o600).open(&tmp).map_err(io_err)?;
    let mut perms = file.metadata().map_err(io_err)?.permissions();
    perms.set_mode(0o600);
    file.set_permissions(perms).map_err(io_err)?;
    file.write_all(body.as_bytes()).map_err(io_err)?;
    file.sync_all().map_err(io_err)?;
    drop(file);
    fs::rename(&tmp, path).map_err(io_err)?;
    if let Some(dir) = path.parent() {
        if let Ok(dir_file) = File::open(dir) {
            let _ = dir_file.sync_all();
        }
    }
    let mode = fs::metadata(path).map_err(io_err)?.permissions().mode();
    if mode & 0o777 != 0o600 {
        return Err(ConfigError::Perms);
    }
    Ok(())
}

pub fn connect_target(config: &Config, addrs: &[SocketAddr]) -> Result<SocketAddr, ConfigError> {
    if addrs.is_empty() {
        return Err(ConfigError::Address);
    }
    if config.obs.allow_non_loopback {
        return Ok(addrs[0]);
    }
    if addrs.iter().all(is_strict_loopback) {
        Ok(addrs[0])
    } else {
        Err(ConfigError::Address)
    }
}

pub fn default_config_path() -> PathBuf {
    if let Some(home) = std::env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(home).join("macropad-obs/config.toml");
    }
    let home = std::env::var_os("HOME").unwrap_or_default();
    PathBuf::from(home).join(".config/macropad-obs/config.toml")
}

fn to_file(config: &Config) -> FileConfig {
    FileConfig {
        obs: ObsFile {
            url: config.obs.url.clone(),
            password: config.obs.password.clone(),
            allow_non_loopback: config.obs.allow_non_loopback,
        },
        key: config.keys.iter().map(|action| KeyFile { action: *action }).collect(),
    }
}

fn split_url(url: &str) -> Result<(String, u16), ConfigError> {
    let Some(rest) = url.strip_prefix("wss://").or_else(|| url.strip_prefix("ws://")) else {
        return Err(ConfigError::Url);
    };
    if rest.contains('@') || rest.contains('/') || rest.contains('?') || rest.contains('#') {
        return Err(ConfigError::Url);
    }
    let (host, port_text) = if let Some(body) = rest.strip_prefix('[') {
        let Some((host, port_text)) = body.split_once("]:") else {
            return Err(ConfigError::Url);
        };
        (host, port_text)
    } else {
        let Some((host, port_text)) = rest.rsplit_once(':') else {
            return Err(ConfigError::Url);
        };
        if host.is_empty() || host.contains(':') {
            return Err(ConfigError::Url);
        }
        (host, port_text)
    };
    if host.is_empty() || port_text.is_empty() || !port_text.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(ConfigError::Url);
    }
    let port: u16 = port_text.parse().map_err(|_| ConfigError::Url)?;
    if port == 0 {
        return Err(ConfigError::Url);
    }
    Ok((host.to_string(), port))
}

fn is_strict_loopback(addr: &SocketAddr) -> bool {
    match addr {
        SocketAddr::V4(v4) => v4.ip().octets()[0] == 127,
        SocketAddr::V6(v6) => {
            let ip = v6.ip();
            ip.to_ipv4_mapped().is_none() && *ip == Ipv6Addr::LOCALHOST
        }
    }
}

fn ensure_private_dir(path: &Path) -> Result<(), ConfigError> {
    let Some(dir) = path.parent() else {
        return Err(ConfigError::Io("config path has no directory".into()));
    };
    if dir.as_os_str().is_empty() {
        return Err(ConfigError::Io("config path has no directory".into()));
    }
    if !dir.exists() {
        if let Some(parent) = dir.parent() {
            if !parent.as_os_str().is_empty() && !parent.exists() {
                fs::create_dir_all(parent).map_err(io_err)?;
            }
        }
        fs::create_dir(dir).map_err(io_err)?;
        let mut perms = fs::metadata(dir).map_err(io_err)?.permissions();
        perms.set_mode(0o700);
        fs::set_permissions(dir, perms).map_err(io_err)?;
    }
    let meta = fs::metadata(dir).map_err(io_err)?;
    if !meta.is_dir() || meta.permissions().mode() & 0o077 != 0 {
        return Err(ConfigError::Perms);
    }
    Ok(())
}

fn temp_path(path: &Path) -> Result<PathBuf, ConfigError> {
    let name = path.file_name().ok_or_else(|| ConfigError::Io("config path has no file name".into()))?;
    let mut tmp_name = name.to_os_string();
    tmp_name.push(".tmp");
    Ok(path.with_file_name(tmp_name))
}

fn io_err(err: io::Error) -> ConfigError {
    ConfigError::Io(err.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static N: AtomicU64 = AtomicU64::new(0);

    fn scratch() -> PathBuf {
        let n = N.fetch_add(1, Ordering::Relaxed);
        let dir = std::env::temp_dir().join(format!("macropad-obs-{}-{}", std::process::id(), n));
        fs::create_dir(&dir).unwrap();
        dir
    }

    fn sample_text() -> String {
        let mut text = String::from(
            "[obs]\nurl = \"ws://127.0.0.1:4455\"\npassword = \"replace-me\"\nallow_non_loopback = false\n",
        );
        for _ in 0..9 {
            text.push_str("\n[[key]]\naction = \"scene\"\n");
        }
        text
    }

    #[test]
    fn parse_rules_and_secret_redaction() {
        let config = parse(&sample_text()).unwrap();
        assert_eq!(config.obs.host, "127.0.0.1");
        assert_eq!(config.obs.port, 4455);
        assert_eq!(format!("{:?}", config.obs.password), "***");
        assert_eq!(config.obs.password.to_string(), "***");
        assert_eq!(config.obs.password.reveal(), "replace-me");
        assert!(
            parse("obs = { url = \"ws://127.0.0.1:4455\", password = \"x\", allow_non_loopback = false }\n").is_err()
        );
        assert!(parse(&sample_text().replace("ws://", "http://")).is_err());
        assert!(parse(&sample_text().replace("ws://127.0.0.1:4455", "ws://a@127.0.0.1:4455")).is_err());
        assert!(parse(&sample_text().replace(":4455", "")).is_err());
        let mut remote = sample_text();
        remote = remote.replace("allow_non_loopback = false", "allow_non_loopback = true");
        assert!(parse(&remote).is_ok(), "obs-websocket has no TLS, so a remote ws:// URL is allowed");
        remote = remote.replace("ws://", "wss://");
        assert!(parse(&remote).is_ok());
        let mut keys = sample_text();
        keys = keys.replace("action = \"scene\"", "action = \"mute\"");
        assert_eq!(parse(&keys).unwrap_err(), ConfigError::SceneKeys);
        assert!(parse(&format!("{}\nextra = 1\n", sample_text())).is_err());
    }

    #[test]
    fn connect_target_rejects_mapped_and_mixed_lists() {
        let config = parse(&sample_text()).unwrap();
        let loopback: SocketAddr = "127.0.0.1:4455".parse().unwrap();
        let also: SocketAddr = "127.1.2.3:4455".parse().unwrap();
        let v6: SocketAddr = "[::1]:4455".parse().unwrap();
        let mapped: SocketAddr = "[::ffff:127.0.0.1]:4455".parse().unwrap();
        let remote: SocketAddr = "10.0.0.1:4455".parse().unwrap();
        assert_eq!(connect_target(&config, &[loopback, also]).unwrap(), loopback);
        assert_eq!(connect_target(&config, &[v6]).unwrap(), v6);
        assert_eq!(connect_target(&config, &[loopback, remote]), Err(ConfigError::Address));
        assert_eq!(connect_target(&config, &[mapped]), Err(ConfigError::Address));
        assert_eq!(connect_target(&config, &[]), Err(ConfigError::Address));
        let mut remote_text = sample_text().replace("ws://", "wss://");
        remote_text = remote_text.replace("allow_non_loopback = false", "allow_non_loopback = true");
        let open = parse(&remote_text).unwrap();
        assert_eq!(connect_target(&open, &[remote, loopback]).unwrap(), remote);
    }

    #[test]
    fn load_creates_0700_and_refuses_group_bits() {
        let root = scratch();
        let dir = root.join("macropad-obs");
        let path = dir.join("config.toml");
        assert_eq!(load(&path).unwrap_err(), ConfigError::Missing);
        let mode = fs::metadata(&dir).unwrap().permissions().mode();
        assert_eq!(mode & 0o777, 0o700);

        fs::write(&path, sample_text()).unwrap();
        let mut loose = fs::metadata(&path).unwrap().permissions();
        loose.set_mode(0o644);
        fs::set_permissions(&path, loose).unwrap();
        assert_eq!(load(&path).unwrap_err(), ConfigError::Perms);

        let mut tight = fs::metadata(&path).unwrap().permissions();
        tight.set_mode(0o600);
        fs::set_permissions(&path, tight).unwrap();
        assert_eq!(load(&path).unwrap().obs.port, 4455);

        let mut dir_loose = fs::metadata(&dir).unwrap().permissions();
        dir_loose.set_mode(0o755);
        fs::set_permissions(&dir, dir_loose).unwrap();
        assert_eq!(load(&path).unwrap_err(), ConfigError::Perms);
        let mut dir_tight = fs::metadata(&dir).unwrap().permissions();
        dir_tight.set_mode(0o700);
        fs::set_permissions(&dir, dir_tight).unwrap();

        let mut config = load(&path).unwrap();
        config.obs.password = Secret("next-secret".into());
        save(&path, &config).unwrap();
        let saved = fs::metadata(&path).unwrap().permissions().mode();
        assert_eq!(saved & 0o777, 0o600);
        let text = fs::read_to_string(&path).unwrap();
        assert!(text.contains("next-secret"));
        assert_eq!(load(&path).unwrap().obs.password.reveal(), "next-secret");
        let _ = fs::remove_dir_all(&root);
    }
}
