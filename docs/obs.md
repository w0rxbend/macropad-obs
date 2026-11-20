# OBS client

The pad is the obs-websocket 5 client (D1 = W, `docs/spec/decisions-v2.md`). It joins Wi-Fi, dials
OBS over TCP and holds the session itself. No PC process is in the path at run time (spec 1 item 3,
`docs/spec/spec-v2.md`). The app only writes the URL, the SSID and the secrets (`docs/config.md`,
`docs/protocol.md`).

All of it is C11 in `firmware/core/` with no ESP-IDF header (spec 5). `just test` runs it under
ASan/UBSan against `tools/fake_obs.py` (justfile `test-firmware`). Nothing here has run against a
real OBS or over a real radio (pending 4.8, H.3, H.4).

## Layers

| Layer | File | What it does |
| --- | --- | --- |
| Wi-Fi | `firmware/core/wifi.c` | Station states `no_ssid`, `connecting`, `bad_key`, `no_ap`, `up` (spec 8.2 `STATUS`); retry backoff; one strip line per failure. The port (`firmware/esp32s3/main/wifi_port.c`) owns the radio |
| Stream | `firmware/core/stream.h` | open, send, receive, close over TCP: lwIP on the pad (`firmware/esp32s3/main/stream_lwip.c`), POSIX in padsim and the tests (`firmware/test/posix_stream.c`) |
| WebSocket | `firmware/core/ws.c` | RFC 6455 client: upgrade, masked frames, fragments, close codes. A ping after 5 s of silence; 2 unanswered pings mean the link is lost, since obs-websocket never pings (`firmware/core/ws.h`, R05) |
| Handshake | `firmware/core/obs.c` | Hello, version floor, auth, Identify, Identified, reconnect |
| State | `firmware/core/obs_state.c` | Replies and events into one state; one request in flight |
| Actions | `firmware/core/actions.c` | Key, button and knob events into requests |
| Reader | `firmware/core/json.c` over LwJSON v1.10.1 (`firmware/core/third_party/lwjson/`) | Streaming JSON reader: a 500-scene reply is read in bounded RAM (spec 8.3; `firmware/test/fixtures/`) |

## Handshake

Source: `firmware/core/obs.h`, spec 8.3, R05 (`docs/research/05-obs-websocket.md`).

- Plain `ws://` only. No TLS on the pad (spec 12 "Never").
- The floor is obs-websocket 5.4.0, the first with UUIDs (OBS 30.1, spec 4 item 3). An older or
  missing version stops the client with `OBS too old, need 30.1`.
- `rpcVersion` 1. Identify subscribes 1118: Config 2, Scenes 4, Inputs 8, Transitions 16, Outputs
  64, Ui 1024. Meters (65536) go on by `Reidentify` only while a widget shows a meter, and off again
  when none does (`firmware/core/obs_state.h`; `layout_shows_meter` in
  `firmware/esp32s3/main/main.c` and `firmware/padsim/main.c`).
- Auth: `base64(sha256(base64(sha256(password + salt)) + challenge))` (spec 8.3), SHA-256 and
  base64 in `firmware/core/crypto.c`. The password comes from the `cred` partition
  (`firmware/esp32s3/main/cred_nvs.c`) and never leaves the pad (R1, `CLAUDE.md`).
- With `obs.auth_mode` `none` the port passes no password to the client (`start_obs` in
  `firmware/esp32s3/main/main.c`). If OBS asks for auth and the client holds no password, it stops
  with `OBS password not set`.

## Reconnect

Source: `firmware/core/obs.c` `RETRY_WAITS_MS`, `firmware/core/obs.h`.

- A failed try waits 0.5 s, 1 s, 2 s, then 2 s each time. The waits start again after `Identified`.
  The 2 s cap is chosen to keep criterion 3 (OBS restart to reconnect within 5 s, spec 13) with
  room for the handshake. Measured on hardware: no (pending 4.8, H.4).
- Close 4009 (wrong password), 4010 (RPC version) and 4011 (session invalidated) stop the client
  with no retry (spec 8.3). A new URL or password applies once the client is idle or stopped
  (task 4.7 status, `tasks/todo.md`).

## Session state

Source: `firmware/core/obs_state.h`, `firmware/core/obs_state.c`.

After each `Identified` the pad reads, one request at a time, in this order: `GetSceneList`,
`GetStudioModeEnabled`, `GetInputList`, `GetStreamStatus`, `GetRecordStatus`, then `GetInputMute`
and `GetInputVolume` for each of the 3 knob inputs. A reply is matched by `requestId`; a late reply
to an older request is dropped. A reply that has not come in 5 s frees the slot and the read goes out
again (`OBS_REQUEST_TIMEOUT_MS`).

Events it applies: `CurrentProgramSceneChanged`, `CurrentPreviewSceneChanged`, `SceneNameChanged`,
`SceneListChanged`, `SceneCreated`, `SceneRemoved`, `StudioModeStateChanged`, `InputCreated`,
`InputRemoved`, `InputNameChanged`, `InputMuteStateChanged`, `InputVolumeChanged`,
`StreamStateChanged`, `RecordStateChanged`, `CurrentSceneCollectionChanging`,
`CurrentSceneCollectionChanged`, `InputVolumeMeters`.

Limits (`firmware/core/obs_state.h`):

- 512 scenes and 256 audio inputs; past that the list keeps its first items and sets a `capped`
  flag. Criterion 8 (500 scenes) is covered by the 500-item fixtures in `firmware/test/fixtures/`.
- Names are cut at 48 bytes on a whole UTF-8 character, the config label cap (`docs/config.md`).
- Only the 3 knob inputs have their mute and volume read.
- An output is on for `outputState` STARTED, RESUMED or RECONNECTED; streaming means on and not
  reconnecting, recording means on and not paused (`obs_output_is_on`).

The pad's own lists go to the app as `OBS_LIST`/`OBS_ITEM` (`docs/protocol.md`). The transitions
list is empty: `obs_state` does not read transitions yet (`firmware/core/device.h`).

## Requests the pad sends

Source: `firmware/core/actions.c`, `firmware/core/actions.h`, `docs/config.md` "An action".

| Input | Request |
| --- | --- |
| `scene` | `SetCurrentProgramScene` with `sceneUuid` |
| `toggle_mute` | `ToggleInputMute` with `inputUuid`; on a knob push, the knob's own input |
| `toggle_record` | `ToggleRecord` |
| `toggle_stream` | `ToggleStream` |
| `transition` | `TriggerStudioModeTransition`, only while studio mode is on; else nothing |
| knob turn | `SetInputVolume` with `inputUuid` and an absolute `inputVolumeDb` |

A key, button or knob push acts on press. A knob turn sends its first detent at once; the other
detents of a 30 ms window go as one sum when the window closes, clamped to -100..26 dB. A knob with
no input, or with no volume known yet, sends nothing. Criterion 4c checks the exact request JSON
end to end in padsim (`host/obs_core/tests/padsim_e2e.rs`).

## Strip lines

Each failure has one fixed ASCII line on the strip (criterion 9). No line carries a secret, an SSID
byte or a value derived from one (R1).

| State | Line | Source |
| --- | --- | --- |
| no SSID | `Wi-Fi not set` | `firmware/core/wifi.c` |
| bad Wi-Fi key | `Wrong Wi-Fi key` | `firmware/core/wifi.c` |
| no AP | `Wi-Fi not found` | `firmware/core/wifi.c` |
| OBS unreachable | `OBS unreachable` | `firmware/core/obs.c` |
| no password stored | `OBS password not set` | `firmware/core/obs.c` |
| close 4009 | `Wrong OBS password` | `firmware/core/obs.c` |
| obs-websocket below 5.4.0 | `OBS too old, need 30.1` | `firmware/core/obs.c` |
| close 4010 or wrong `rpcVersion` | `OBS refused protocol` | `firmware/core/obs.c` |
| close 4011 | `OBS closed session` | `firmware/core/obs.c` |
| no document | `Factory config` | `firmware/core/store.c` |
| stored `schema` below min | `Factory config, update config` | `firmware/core/store.c` |

## Not proven

- Against a real OBS: the manual run on a throwaway OBS on port 4456 has not happened (spec 11
  "manual" row; pending H.9).
- Over Wi-Fi: association, RSSI through the back-wall insert and reconnect after an AP restart
  (pending S.3, 4.8, H.4, H.10).
- Latency: criterion 2, `INPUT` to `CurrentProgramSceneChanged` under 100 ms (pending H.3).
- Strip update within 200 ms of an OBS change: criterion 6 (pending H.6).
- Plain `ws://` on a shared LAN exposes the session; accepted for a home LAN (spec 14).
