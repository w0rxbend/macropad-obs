// SPDX-License-Identifier: MIT
//! One task owns the OBS client and the CDC bridge. The password is not framed.

use std::collections::VecDeque;
use std::net::{IpAddr, SocketAddr, ToSocketAddrs};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use futures_util::StreamExt;
use obws::client::{ConnectConfig, DEFAULT_BROADCAST_CAPACITY, DEFAULT_CONNECT_TIMEOUT};
use obws::events::{Event, OutputState};
use obws::requests::inputs::{InputId, Volume};
use obws::Client;
use obs_core::{
    connect_target, default_config_path, load, output_is_on, parse, round_db, save, Bridge, Config,
    ConfigError, Core, Effect, EventBurst, InputState, KeyAction, ObsRequest, ObsSnapshot, PadEvent, Port,
};
use tokio::sync::{mpsc, oneshot};

use crate::logbuf::Log;
use crate::pad::{self, PadMsg};

pub enum Cmd {
    GetState(oneshot::Sender<UiState>),
    SetConnection {
        url: String,
        password: String,
        allow_non_loopback: bool,
        reply: oneshot::Sender<Result<(), String>>,
    },
    SetKey {
        index: u8,
        action: String,
        reply: oneshot::Sender<Result<(), String>>,
    },
    SelectInput {
        name: String,
        reply: oneshot::Sender<Result<(), String>>,
    },
    SetProfile {
        name: String,
        reply: oneshot::Sender<Result<(), String>>,
    },
    Connect(oneshot::Sender<Result<(), String>>),
    Disconnect(oneshot::Sender<Result<(), String>>),
}

#[derive(serde::Serialize)]
pub struct InputView {
    pub name: String,
    pub muted: bool,
    pub db: i8,
}

#[derive(serde::Serialize)]
pub struct SlotView {
    pub occupied: bool,
    pub program: bool,
    pub name: String,
}

#[derive(serde::Serialize)]
pub struct UiState {
    pub url: String,
    pub password_set: bool,
    pub allow_non_loopback: bool,
    pub connected: bool,
    pub scenes: Vec<String>,
    pub inputs: Vec<InputView>,
    pub profile: String,
    pub profiles: Vec<String>,
    pub keys: Vec<String>,
    pub slots: Vec<SlotView>,
    pub page: u8,
    pub page_count: u8,
    pub latency_ms: Option<u64>,
    pub notice: Option<String>,
}

struct ChanPort {
    inbound: Arc<Mutex<VecDeque<u8>>>,
    tx: std::sync::mpsc::Sender<Vec<u8>>,
}

impl Port for ChanPort {
    fn read(&mut self, dst: &mut [u8]) -> usize {
        let mut queue = self.inbound.lock().expect("cdc queue");
        let n = dst.len().min(queue.len());
        for byte in dst.iter_mut().take(n) {
            *byte = queue.pop_front().unwrap_or(0);
        }
        n
    }

    fn write(&mut self, src: &[u8]) -> usize {
        if self.tx.send(src.to_vec()).is_err() {
            return 0;
        }
        src.len()
    }
}

pub fn start() -> mpsc::Sender<Cmd> {
    let (tx, rx) = mpsc::channel(16);
    tauri::async_runtime::spawn(run(rx));
    tx
}

async fn run(mut cmds: mpsc::Receiver<Cmd>) {
    let mut log = Log::open();
    let path = default_config_path();
    let mut config = match load(&path) {
        Ok(config) => config,
        Err(ConfigError::Missing) => fallback_config(),
        Err(err) => {
            log.info(&format!("config load failed: {err}"));
            fallback_config()
        }
    };
    log.set_secret(config.obs.password.reveal());
    let mut core = Core::new(config.clone());
    let inbound = Arc::new(Mutex::new(VecDeque::new()));
    let (mut pad_rx, pad_tx) = pad::spawn();
    let mut bridge = Bridge::new(ChanPort { inbound: Arc::clone(&inbound), tx: pad_tx });
    let mut client: Option<Client> = None;
    let (obs_tx, mut obs_rx) = mpsc::channel(32);
    let mut forward: Option<tauri::async_runtime::JoinHandle<()>> = None;
    let mut generation = 0u64;
    let mut burst = EventBurst::default();
    let mut connected = false;
    let mut acked = false;
    let mut hello_at: Option<Instant> = None;
    let mut hello_logged = false;
    let mut latency = None;
    let mut last_hb = 0u64;

    loop {
        let tick = tokio::time::sleep(Duration::from_millis(20));
        tokio::pin!(tick);
        tokio::select! {
            cmd = cmds.recv() => {
                let Some(cmd) = cmd else { break };
                handle_cmd(
                    cmd, &mut config, &mut core, &mut client, &obs_tx, &mut forward, &mut generation,
                    &mut bridge, &mut connected, &mut burst, &mut log, &path, latency,
                ).await;
            }
            msg = pad_rx.recv() => {
                match msg {
                    Some(PadMsg::Opened) => {
                        hello_at = Some(Instant::now());
                        hello_logged = false;
                        acked = false;
                        log.info("cdc open");
                    }
                    Some(PadMsg::Closed) => {
                        acked = false;
                        hello_at = None;
                        log.info("cdc closed");
                    }
                    Some(PadMsg::Bytes(bytes)) => {
                        if let Ok(mut queue) = inbound.lock() {
                            queue.extend(bytes);
                        }
                        for event in bridge.poll_pad() {
                            on_pad(event, &mut core, &mut bridge, &mut acked, &mut last_hb, &mut latency, client.as_ref(), &log).await;
                        }
                    }
                    None => break,
                }
            }
            event = obs_rx.recv() => {
                match event {
                    Some(ObsNote::Event(event)) => {
                        if let Some(obs) = client.as_ref() {
                            on_obs(event, obs, &mut core, &mut bridge, &mut burst, &log).await;
                        }
                    }
                    Some(ObsNote::Closed { gen }) if gen == generation => {
                        drop_obs(&mut client, &mut forward, &mut connected, &mut bridge, &config, &log);
                    }
                    Some(_) | None => {}
                }
            }
            _ = &mut tick => {
                let now = now_ms();
                if acked && now.saturating_sub(last_hb) >= 1000 {
                    bridge.heartbeat();
                    last_hb = now;
                }
                for effect in core.poll(now) {
                    apply_one(&effect, client.as_ref(), &mut bridge, &mut latency, Instant::now(), &log).await;
                }
                if burst.poll(now) {
                    push_view(&mut bridge, &core);
                }
                if let Some(opened) = hello_at {
                    if !acked && !hello_logged && opened.elapsed() >= Duration::from_secs(2) {
                        log.info("no HELLO within 2s");
                        hello_logged = true;
                    }
                }
            }
        }
    }
}

async fn handle_cmd(
    cmd: Cmd,
    config: &mut Config,
    core: &mut Core,
    client: &mut Option<Client>,
    obs_tx: &mpsc::Sender<ObsNote>,
    forward: &mut Option<tauri::async_runtime::JoinHandle<()>>,
    generation: &mut u64,
    bridge: &mut Bridge<ChanPort>,
    connected: &mut bool,
    burst: &mut EventBurst,
    log: &mut Log,
    path: &std::path::Path,
    latency: Option<u64>,
) {
    match cmd {
        Cmd::GetState(reply) => {
            let _ = reply.send(ui_state(config, core, *connected, latency));
        }
        Cmd::SetConnection { url, password, allow_non_loopback, reply } => {
            let result = write_connection(config, core, path, &url, &password, allow_non_loopback);
            if result.is_ok() {
                log.set_secret(config.obs.password.reveal());
                log.info("config saved");
            }
            let _ = reply.send(result);
        }
        Cmd::SetKey { index, action, reply } => {
            let result = (|| {
                let action = parse_action(&action)?;
                let mut next = config.clone();
                let slot = usize::from(index);
                if slot >= next.keys.len() {
                    return Err("key index".into());
                }
                next.keys[slot] = action;
                save(path, &next).map_err(|err| err.to_string())?;
                core.set_key(index, action).map_err(|err| format!("{err:?}"))?;
                *config = next;
                Ok(())
            })();
            let _ = reply.send(result);
        }
        Cmd::SelectInput { name, reply } => {
            let _ = reply.send(core.select_input(&name).map_err(|err| format!("{err:?}")));
        }
        Cmd::SetProfile { name, reply } => {
            let result = match client.as_ref() {
                Some(obs) => obs.profiles().set_current(&name).await.map_err(|err| log.scrub(&err.to_string())),
                None => Err("obs down".into()),
            };
            let _ = reply.send(result);
        }
        Cmd::Connect(reply) => {
            let result = connect_obs(
                config, core, client, obs_tx, forward, generation, bridge, connected, burst, log,
            ).await;
            let _ = reply.send(result);
        }
        Cmd::Disconnect(reply) => {
            drop_obs(client, forward, connected, bridge, config, log);
            let _ = reply.send(Ok(()));
        }
    }
}

fn write_connection(
    config: &mut Config,
    _core: &mut Core,
    path: &std::path::Path,
    url: &str,
    password: &str,
    allow_non_loopback: bool,
) -> Result<(), String> {
    let mut text = format!(
        "[obs]\nurl = {}\npassword = {}\nallow_non_loopback = {}\n\n",
        toml_basic(url),
        toml_basic(password),
        allow_non_loopback,
    );
    for action in &config.keys {
        text.push_str(&format!("[[key]]\naction = \"{}\"\n", action_name(*action)));
    }
    let next = parse(&text).map_err(|err| err.to_string())?;
    save(path, &next).map_err(|err| err.to_string())?;
    *config = next;
    Ok(())
}

async fn connect_obs(
    config: &Config,
    core: &mut Core,
    client: &mut Option<Client>,
    obs_tx: &mpsc::Sender<ObsNote>,
    forward: &mut Option<tauri::async_runtime::JoinHandle<()>>,
    generation: &mut u64,
    bridge: &mut Bridge<ChanPort>,
    connected: &mut bool,
    burst: &mut EventBurst,
    log: &Log,
) -> Result<(), String> {
    bridge.bind(1, config.obs.port, &config.obs.host);
    log.info("obs connecting");
    let addrs = resolve(&config.obs.host, config.obs.port).map_err(|err| log.scrub(&err))?;
    let addr = connect_target(config, &addrs).map_err(|err| err.to_string())?;
    let reveal = config.obs.password.reveal();
    let password = if reveal.is_empty() { None } else { Some(reveal.to_string()) };
    let host = match addr.ip() {
        IpAddr::V6(ip) => format!("[{ip}]"),
        IpAddr::V4(ip) => ip.to_string(),
    };
    let opened = Client::connect_with_config(ConnectConfig {
        host,
        port: addr.port(),
        password,
        event_subscriptions: None,
        tls: config.obs.url.starts_with("wss://"),
        broadcast_capacity: DEFAULT_BROADCAST_CAPACITY,
        connect_timeout: DEFAULT_CONNECT_TIMEOUT,
        dangerous: None,
    })
    .await;
    let obs = match opened {
        Ok(obs) => obs,
        Err(err) => {
            let state = if matches!(err, obws::error::Error::Handshake(_)) { 2 } else { 0 };
            bridge.bind(state, config.obs.port, &config.obs.host);
            let text = log.scrub(&err.to_string());
            log.info(&format!("obs connect failed: {text}"));
            return Err(text);
        }
    };
    let snap = match read_snapshot(&obs).await {
        Ok(snap) => snap,
        Err(err) => {
            bridge.bind(0, config.obs.port, &config.obs.host);
            log.info(&format!("obs read failed: {err}"));
            return Err(err);
        }
    };
    core.apply_snapshot(snap);
    let stream = obs.events().map_err(|err| log.scrub(&err.to_string()))?;
    *generation = generation.wrapping_add(1);
    if let Some(task) = forward.take() {
        task.abort();
    }
    *forward = Some(spawn_events(stream, obs_tx.clone(), *generation));
    *client = Some(obs);
    *connected = true;
    burst.push(now_ms());
    let state = if config.obs.allow_non_loopback { 4 } else { 3 };
    bridge.bind(state, config.obs.port, &config.obs.host);
    push_view(bridge, core);
    log.info("obs connected");
    Ok(())
}

fn drop_obs(
    client: &mut Option<Client>,
    forward: &mut Option<tauri::async_runtime::JoinHandle<()>>,
    connected: &mut bool,
    bridge: &mut Bridge<ChanPort>,
    config: &Config,
    log: &Log,
) {
    if let Some(task) = forward.take() {
        task.abort();
    }
    let was = client.is_some() || *connected;
    *client = None;
    *connected = false;
    bridge.bind(0, config.obs.port, &config.obs.host);
    if was {
        log.info("obs closed");
    }
}

enum ObsNote {
    Event(Event),
    Closed { gen: u64 },
}

fn spawn_events(
    mut stream: obws::events::EventStream,
    tx: mpsc::Sender<ObsNote>,
    gen: u64,
) -> tauri::async_runtime::JoinHandle<()> {
    tauri::async_runtime::spawn(async move {
        while let Some(event) = stream.next().await {
            if tx.send(ObsNote::Event(event)).await.is_err() {
                return;
            }
        }
        let _ = tx.send(ObsNote::Closed { gen }).await;
    })
}

async fn on_pad(
    event: PadEvent,
    core: &mut Core,
    bridge: &mut Bridge<ChanPort>,
    acked: &mut bool,
    last_hb: &mut u64,
    latency: &mut Option<u64>,
    client: Option<&Client>,
    log: &Log,
) {
    if let PadEvent::Hello { proto, .. } = event {
        if proto != 1 {
            log.info(&format!("pad proto {proto} refused"));
            return;
        }
        if !*acked && bridge.hello_ack() {
            *acked = true;
            *last_hb = now_ms();
            log.info("hello ack");
        }
        return;
    }
    let started = Instant::now();
    let effects = core.on_pad(event);
    for effect in &effects {
        apply_one(effect, client, bridge, latency, started, log).await;
    }
    for effect in core.poll(now_ms()) {
        apply_one(&effect, client, bridge, latency, started, log).await;
    }
    push_view(bridge, core);
}

async fn on_obs(
    event: Event,
    client: &Client,
    core: &mut Core,
    bridge: &mut Bridge<ChanPort>,
    burst: &mut EventBurst,
    log: &Log,
) {
    let mut snap = core.snapshot().clone();
    let mut refresh_scenes = false;
    let mut refresh_inputs = false;
    match event {
        Event::CurrentProgramSceneChanged { id } => snap.program = Some(id.name),
        Event::SceneListChanged { mut scenes } => {
            scenes.sort_by_key(|scene| scene.index);
            snap.scenes = scenes.into_iter().map(|scene| scene.name).collect();
        }
        Event::InputMuteStateChanged { id, muted } => {
            if let Some(input) = snap.inputs.iter_mut().find(|input| input.name == id.name) {
                input.muted = muted;
            }
        }
        Event::InputVolumeChanged { id, db, .. } => {
            if let Some(input) = snap.inputs.iter_mut().find(|input| input.name == id.name) {
                input.db = round_db(db);
            }
        }
        Event::StreamStateChanged { state, .. } => snap.streaming = output_is_on(state_name(state)),
        Event::RecordStateChanged { state, .. } => snap.recording = output_is_on(state_name(state)),
        Event::StudioModeStateChanged { enabled } => snap.studio = enabled,
        Event::CurrentProfileChanged { .. } => {
            refresh_scenes = true;
            refresh_inputs = true;
        }
        Event::InputCreated { .. } | Event::InputRemoved { .. } | Event::InputNameChanged { .. } => {
            refresh_inputs = true;
        }
        _ => return,
    }
    if refresh_scenes {
        if let Ok(fresh) = read_scenes(client).await {
            snap.scenes = fresh.0;
            snap.program = fresh.1;
        }
    }
    if refresh_inputs {
        if let Ok(inputs) = read_inputs(client).await {
            snap.inputs = inputs;
        }
    }
    if refresh_scenes {
        if let Ok(profiles) = client.profiles().list().await {
            snap.profile = profiles.current;
            snap.profiles = profiles.profiles;
        }
    }
    core.apply_snapshot(snap);
    burst.push(now_ms());
    let _ = bridge;
    let _ = log;
}

async fn apply_one(
    effect: &Effect,
    client: Option<&Client>,
    bridge: &mut Bridge<ChanPort>,
    latency: &mut Option<u64>,
    started: Instant,
    log: &Log,
) {
    match effect {
        Effect::Notice(text) => {
            bridge.notice(text);
        }
        Effect::Obs(request) => {
            if let Some(obs) = client {
                if let Err(err) = obs_request(obs, request).await {
                    log.info(&format!("obs request failed: {}", log.scrub(&err.to_string())));
                }
            }
            *latency = Some(u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX));
        }
    }
}

async fn obs_request(client: &Client, request: &ObsRequest) -> obws::error::Result<()> {
    match request {
        ObsRequest::SetProgramScene { name } => client.scenes().set_current_program_scene(name.as_str()).await,
        ObsRequest::SetProfile { name } => client.profiles().set_current(name).await,
        ObsRequest::SetMute { name, muted } => {
            client.inputs().set_muted(InputId::Name(name), *muted).await
        }
        ObsRequest::SetVolumeDb { name, db } => {
            client.inputs().set_volume(InputId::Name(name), Volume::Db(f32::from(*db))).await
        }
        ObsRequest::StartStream => client.streaming().start().await,
        ObsRequest::StopStream => client.streaming().stop().await,
        ObsRequest::StartRecord => client.recording().start().await,
        ObsRequest::StopRecord => {
            client.recording().stop().await?;
            Ok(())
        }
        ObsRequest::Transition => client.transitions().trigger().await,
    }
}

async fn read_snapshot(client: &Client) -> Result<ObsSnapshot, String> {
    let (scenes, program) = read_scenes(client).await?;
    let profiles = client.profiles().list().await.map_err(|err| err.to_string())?;
    let current = client.profiles().current().await.map_err(|err| err.to_string())?;
    let _stream = client.streaming().status().await.map_err(|err| err.to_string())?;
    let _record = client.recording().status().await.map_err(|err| err.to_string())?;
    let studio = client.ui().studio_mode_enabled().await.map_err(|err| err.to_string())?;
    let inputs = read_inputs(client).await?;
    Ok(ObsSnapshot {
        scenes,
        program,
        profile: current,
        profiles: profiles.profiles,
        inputs,
        streaming: false,
        recording: false,
        studio,
    })
}

async fn read_scenes(client: &Client) -> Result<(Vec<String>, Option<String>), String> {
    let mut listed = client.scenes().list().await.map_err(|err| err.to_string())?;
    listed.scenes.sort_by_key(|scene| scene.index);
    let names = listed.scenes.into_iter().map(|scene| scene.id.name).collect();
    let current = client.scenes().current_program_scene().await.map_err(|err| err.to_string())?;
    Ok((names, Some(current.id.name)))
}

async fn read_inputs(client: &Client) -> Result<Vec<InputState>, String> {
    let listed = client.inputs().list(None).await.map_err(|err| err.to_string())?;
    let mut kept = Vec::new();
    for input in listed {
        let name = input.id.name;
        let muted = client.inputs().muted(InputId::Name(&name)).await.map_err(|err| err.to_string())?;
        let volume = match client.inputs().volume(InputId::Name(&name)).await {
            Ok(volume) => volume,
            Err(_) => continue,
        };
        kept.push(InputState { name, muted, db: round_db(f64::from(volume.db)) });
        if kept.len() == 32 {
            break;
        }
    }
    Ok(kept)
}

fn push_view(bridge: &mut Bridge<ChanPort>, core: &Core) {
    let view = core.page_view();
    bridge.page(&view);
    if let Some(name) = core.selected() {
        if let Some(input) = core.snapshot().inputs.iter().find(|input| input.name == name) {
            bridge.input(input.db, input.muted, &input.name);
        }
    }
    let profile = core.snapshot().profile.clone();
    if !profile.is_empty() {
        bridge.profile(&profile);
    }
}

fn ui_state(config: &Config, core: &Core, connected: bool, latency_ms: Option<u64>) -> UiState {
    let view = core.page_view();
    let snap = core.snapshot();
    UiState {
        url: config.obs.url.clone(),
        password_set: !config.obs.password.reveal().is_empty(),
        allow_non_loopback: config.obs.allow_non_loopback,
        connected,
        scenes: snap.scenes.clone(),
        inputs: snap.inputs.iter().map(|input| InputView {
            name: input.name.clone(),
            muted: input.muted,
            db: input.db,
        }).collect(),
        profile: snap.profile.clone(),
        profiles: snap.profiles.clone(),
        keys: core.keys().iter().copied().map(action_name).map(str::to_string).collect(),
        slots: view.slots.iter().map(|slot| SlotView {
            occupied: slot.occupied,
            program: slot.program,
            name: slot.name.clone(),
        }).collect(),
        page: view.page,
        page_count: view.page_count,
        latency_ms,
        notice: view.notice.clone(),
    }
}

fn state_name(state: OutputState) -> &'static str {
    match state {
        OutputState::Starting => "OBS_WEBSOCKET_OUTPUT_STARTING",
        OutputState::Started => "OBS_WEBSOCKET_OUTPUT_STARTED",
        OutputState::Stopping => "OBS_WEBSOCKET_OUTPUT_STOPPING",
        OutputState::Stopped => "OBS_WEBSOCKET_OUTPUT_STOPPED",
        OutputState::Reconnecting => "OBS_WEBSOCKET_OUTPUT_RECONNECTING",
        OutputState::Reconnected => "OBS_WEBSOCKET_OUTPUT_RECONNECTED",
        OutputState::Paused => "OBS_WEBSOCKET_OUTPUT_PAUSED",
        OutputState::Resumed => "OBS_WEBSOCKET_OUTPUT_RESUMED",
        OutputState::Unknown | _ => "",
    }
}

fn parse_action(text: &str) -> Result<KeyAction, String> {
    match text {
        "scene" => Ok(KeyAction::Scene),
        "mute" => Ok(KeyAction::Mute),
        "transition" => Ok(KeyAction::Transition),
        "stream" => Ok(KeyAction::Stream),
        "record" => Ok(KeyAction::Record),
        "profile_next" => Ok(KeyAction::ProfileNext),
        "profile_prev" => Ok(KeyAction::ProfilePrev),
        _ => Err("unknown action".into()),
    }
}

fn action_name(action: KeyAction) -> &'static str {
    match action {
        KeyAction::Scene => "scene",
        KeyAction::Mute => "mute",
        KeyAction::Transition => "transition",
        KeyAction::Stream => "stream",
        KeyAction::Record => "record",
        KeyAction::ProfileNext => "profile_next",
        KeyAction::ProfilePrev => "profile_prev",
    }
}

fn toml_basic(text: &str) -> String {
    format!("\"{}\"", text.replace('\\', "\\\\").replace('"', "\\\""))
}

fn resolve(host: &str, port: u16) -> Result<Vec<SocketAddr>, String> {
    (host, port).to_socket_addrs().map(|iter| iter.collect()).map_err(|err| err.to_string())
}

fn fallback_config() -> Config {
    parse(include_str!("../../../host/config.example.toml")).expect("example config")
}

fn now_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| u64::try_from(d.as_millis()).unwrap_or(u64::MAX)).unwrap_or(0)
}


