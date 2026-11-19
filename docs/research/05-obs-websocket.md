# 05. obs-websocket 5 for a device-side client

Checked on 2026-11-18 against obs-websocket 5.7.6 (commit `e28f849`), the version pinned by OBS
Studio 33.0.0 and 33.0.1. Each fact carries a source key (`S1` to `S14`) and one of: verified,
likely, unverified. Trimmed from the earlier 29 kB draft. Kept facts were checked again today.

## Recommendation

Next action: the owner answers open question 1 (the password rule). It decides the design.

1. **Transport.** Plain `ws://`, JSON, `rpcVersion` 1. The server has no TLS, so refuse `wss://`
   in the app. Require obs-websocket 5.4.0 (OBS 30.1) so UUIDs are the only key.
2. **Authentication.** The app gives the device `base64(sha256(password + salt))`, never the
   password. The rule "No OBS password in a CDC frame" then holds. Cost: the secret dies when OBS
   restarts, so the app must answer once per OBS launch.
3. **Parsing.** Never buffer a whole message. No message size is bounded. Stream the bytes, keep a
   fixed set of fields, skip the rest.
4. **Subscriptions.** `eventSubscriptions` = 1118. Add 65536 with `Reidentify` only while meters
   are drawn.
5. **Reconnect.** No session resume. Read the full state again after `Identified`. Never replay a
   command. Stop on close codes 4009, 4010 and 4011.

The working reading (firmware talks to OBS, app only configures) is practical at protocol level.
The device needs SHA-256, SHA-1, base64, a WebSocket client and a streaming JSON reader.

## 1. Connection

| Item | Value | Source |
|---|---|---|
| Default port | 4455 | S4 `Config.h:38`, verified |
| Enabled by default | No. `ServerEnabled = false`. The owner turns it on in OBS | S4 `Config.h:37`, verified |
| Bind address | All interfaces. No bind-address setting exists | S1 `:108`, S4, verified |
| IPv6 and IPv4 | One dual-stack IPv6 listener. Falls back to IPv4 if that fails | S1 `:108-111`, verified. S9 `endpoint.hpp:510-521`, likely |
| IPv4 only | Only with the OBS flag `--websocket_ipv4_only` | S4 `Config.cpp:108`, verified |
| `wss` | Not supported. Server type is `websocketpp::config::asio`, the non-TLS transport | S1 `WebSocketServer.h:93`, verified |
| Path, Origin, Host | Not checked. `onValidate` always returns true | S1 `:204-216`, verified |
| Subprotocol | `obswebsocket.json` (default) or `obswebsocket.msgpack` | S1 `:210`, `:240-245`, verified |
| Compression | None. `permessage-deflate` is disabled in the websocketpp core config | S9 `core.hpp:275`, likely |
| Ping | The server never sends one. The client must mask its frames | S1 (no ping call), S11, verified |

"Likely" on websocketpp rows: read in 0.8.2. The copy inside the OBS build was not checked.

OBS shows its connect string as `obsws://<ip>:<port>/<password>` (S5 `ConnectInfo.cpp:76`,
verified). The app must strip the password before anything goes into a CDC frame.

## 2. Handshake

The server speaks first. Keys arrive in sorted order (section 6).

```json
{"d":{"authentication":{"challenge":"<44>","salt":"<44>"},"obsStudioVersion":"33.0.1","obsWebSocketVersion":"5.7.6","rpcVersion":1},"op":0}
{"op":1,"d":{"rpcVersion":1,"authentication":"<44>","eventSubscriptions":1118}}
{"d":{"negotiatedRpcVersion":1},"op":2}
```

1. `Hello` (op 0), 219 bytes. `authentication` is absent when OBS has authentication off.
   `obsStudioVersion` exists from 5.6.0. Gate on `obsWebSocketVersion` here, not with `GetVersion`.
2. `Identify` (op 1), 119 bytes. `rpcVersion` must be 1, else close 4010. A wrong `authentication`
   closes 4009. Omitted `eventSubscriptions` means all non-high-volume events.
3. `Identified` (op 2), 39 bytes.
4. `Reidentify` (op 3) changes only `eventSubscriptions`. The reply is another `Identified`.

Source: S1 `:247-262`, S2 `:59-65`, `:99-187`, S7. Verified.

## 3. Authentication

```text
secret = base64( sha256( password + salt ) )        44 ASCII chars
auth   = base64( sha256( secret   + challenge ) )   44 ASCII chars, sent in Identify
```

Salt and challenge are base64 of 32 random bytes. They are hashed as the 44-character strings,
not as decoded bytes (S3 `Crypto.cpp:30-70`, verified).

**The salt is stable for one run of the server. It changes on every server start.**

1. Salt and secret are made once, in `WebSocketServer::Start()` (S1 `:85-86`, verified).
2. Each connection gets a new challenge and the same salt (S1 `:253-258`, verified).
3. `Start()` has two callers: plugin load, and the settings dialog when the enable box, the port
   or the password changes (S6 `obs-websocket.cpp:130`, S5 `SettingsDialog.cpp:198-221`, verified).

So the app can hand the device the secret. It works until OBS restarts. The device sees a stale
secret before it fails: `Hello` carries the salt. On a new salt the device does not guess. It
sends the salt to the app over CDC and waits for a new secret.

| Option | Password in a CDC frame | Works with the app closed | Risk |
|---|---|---|---|
| A. Salt-bound secret from the app (recommended) | No | Until OBS restarts | The app or a tray helper runs once per OBS launch |
| B. Password stored on the device | Yes. Breaks the rule | Always | Password sits in device flash |
| C. Authentication off in OBS | No | Always | Port 4455 is open on every interface |
| D. App computes each `auth` | No | Never | The app is needed for every connection |

The secret equals the password in power until the salt changes. Treat it as a credential.

Test vector, recomputed today (S12):

```text
password   supersecretpassword
salt       lM1GncleQOaCu9lT1yeUZhFYnqhsLLP1G5lAGo3ixaI=
challenge  +IxH4CnCiqpX1rM9scsNynZzbOe4KhDeYcTNS3PDaeY=
secret     H1IfVz1pSREUQzbFTVnX/Tyb+gMhMik5x7yUBCY0PTs=
auth       1Ct943GAT+6YQUUX47Ia/ncufilbe6+oD6lY+5kaCu4=
```

The `Identify` example in the protocol document (`Dj6c...`) does not match its own `Hello`
example. Do not use that pair (S7 `protocol.md:206`, S12, verified).

## 4. Event subscriptions

The mask selects categories, not single events (S8 `EventSubscription.h`, verified).

- Take: Config 2, Scenes 4, Inputs 8, Transitions 16, Outputs 64, Ui 1024. Sum **1118**.
- On demand: InputVolumeMeters 65536. Sum **66654**.
- Leave off: General 1, Filters 32, SceneItems 128, MediaInputs 256, Vendors 512, Canvases 2048.

The mask is coarse. Unwanted events still arrive, and three are unbounded (section 5, last row).

## 5. Minimal request and event set

Sizes are bytes of JSON for one message with a 4-character `requestId`. "N" is the name length
in UTF-8 bytes. No name length limit exists in obs-websocket. Fields are from S7 `protocol.json`
(verified). Sizes are from the local model S12 (likely on a live socket).

| Feature | Request or event | Fields used | Worst-case size |
|---|---|---|---|
| Handshake | `Hello`, `Identify`, `Identified` | `obsWebSocketVersion`, `authentication.salt`, `.challenge` | 219, 119, 39 |
| Meters on, off | `Reidentify` | `eventSubscriptions` | 41 sent |
| Scene list, program, preview | `GetSceneList` | `currentProgramSceneUuid`, `currentPreviewSceneUuid`, `scenes[].sceneUuid`, `scenes[].sceneName` | Unbounded. 322 + 2N + scenes x (85 + N). 100 scenes: 11.2 kB. 500 scenes, 64-byte names: 74.8 kB |
| Scene list changed | `SceneListChanged` | None. Mark stale, send `GetSceneList` | Unbounded |
| Program, preview changed | `CurrentProgramSceneChanged`, `CurrentPreviewSceneChanged` | `sceneUuid`, `sceneName` | 151 + N |
| Scene renamed | `SceneNameChanged` | `sceneUuid`, `sceneName` | 159 + 2N |
| Switch scene | `SetCurrentProgramScene`, `SetCurrentPreviewScene` | `sceneUuid` | 139 sent, 115 back |
| Studio mode | `GetStudioModeEnabled`, `SetStudioModeEnabled`, `StudioModeStateChanged` | `studioModeEnabled` | 156 |
| Transition | `TriggerStudioModeTransition`, `GetCurrentSceneTransition`, `CurrentSceneTransitionChanged` | `transitionName`, `transitionDuration` | 77 sent. Reply 363 + N plus `transitionSettings`, an open object |
| Input list | `GetInputList` | `inputs[].inputUuid`, `.inputName`, `.inputKindCaps` (bit 1 = audio) | Unbounded. 134 + inputs x (130 + N + 2 x kind). 100 inputs: 19 kB. 500: 95 kB |
| Volume in dB | `GetInputVolume`, `SetInputVolume`, `InputVolumeChanged` | `inputUuid`, `inputVolumeDb` (-100 to 26, silence reads -100) | 154 sent, 197 back, event 216 + N |
| Mute | `GetInputMute`, `SetInputMute`, `InputMuteStateChanged` | `inputUuid`, `inputMuted` | 148 sent, 141 back, event 165 + N |
| Input renamed, removed | `InputNameChanged`, `InputRemoved` | `inputUuid`, `inputName` | 159 + 2N, 137 + N |
| Stream | `GetStreamStatus`, `StartStream`, `StopStream`, `StreamStateChanged` | `outputActive`, `outputReconnecting`, `outputState` | 62 sent, 356 back, event 149 |
| Record | `GetRecordStatus`, `StartRecord`, `StopRecord`, `ToggleRecordPause`, `RecordStateChanged` | `outputActive`, `outputPaused`, `outputState` | 67 sent, 253 back, event 161 + file path |
| Meters | `InputVolumeMeters` | `inputs[].inputUuid`, `inputs[].inputLevelsMul[ch][1]` | Unbounded. 92 + inputs x (87 + N + 62 x channels). 10 stereo inputs: 2.4 kB, 20 per second |
| Collection switch | `CurrentSceneCollectionChanging`, `CurrentSceneCollectionChanged` | Event type only | 114 + N |
| Must skip | `InputCreated`, `InputSettingsChanged`, `SceneListChanged` | None | Unbounded. Whole settings objects or lists |

1. `GetInputList` returns no volume and no mute (S8 `Obs_ArrayHelper.cpp:203-229`, verified). Ask
   per input, and only for the three knob inputs.
2. A UUID field wins over a name field (S10 `Request.cpp:231-246`, verified).
3. `outputActive` in the state events is true only for STARTED, RESUMED and RECONNECTED (S8
   `EventHandler_Outputs.cpp:22-39`, verified). Use `outputState` to tell paused from stopped.
4. Start on a running output returns 500, Stop on a stopped one returns 501, and nothing changes
   (S10, verified). Start and Stop are safe to send twice. Toggle is not.
5. Read order after `Identified`: `GetSceneList`, `GetStudioModeEnabled`,
   `GetCurrentSceneTransition`, `GetStreamStatus`, `GetRecordStatus`, then volume and mute for
   each knob. That is 11 requests and under 3 kB of replies plus the scene list.

## 6. Message sizes and a small microcontroller

**No bound.** Scene count, input count and name length belong to the user. One message is one
frame, so 500 scenes arrive as one 55 to 75 kB text frame (S9 `hybi13.hpp:630-671`, S12, likely).

**Key order.** The server builds messages with `nlohmann::json`, which sorts keys (S8 `Json.h:26`,
S12 run today, verified). So `"d"` comes before `"op"`, and `eventData` comes before `eventType`.
The device learns what a message is only after its data has gone by. JSON promises no order, so
build for that case: capture first, decide last.

Parser rules:

1. Feed TCP bytes straight into a streaming JSON reader. Server frames are unmasked.
2. Match key paths against the "fields used" column. Copy matches into a small scratch record.
3. Skip everything else at any depth with a depth counter only.
4. For `scenes[]` and `inputs[]`, take one element at a time. Compare its UUID with the bound
   ones, update that slot, drop the element.
5. At the end of the message, read `op` and the type from the scratch record. Apply or discard.

Client state is then fixed in size: a UUID and a cut label per bound scene or input. RAM outside
the TCP/IP stack is about 1 kB (unverified estimate).

| Option | For | Against |
|---|---|---|
| Streaming JSON reader (recommended) | Constant RAM. Text fixtures shared by C and Rust tests | Meter values are 17-digit decimals |
| Whole message in a buffer | Any small JSON library works | No safe buffer size exists |
| MessagePack subprotocol | Lengths come first, floats are short | Binary fixtures. Not measured here |

Names are UTF-8. The CDC rule "Text is printable ASCII" in `docs/protocol.md` would turn every
non-Latin scene name into `?`.

**Ordering.** Each incoming message runs on a thread pool (S1 `:347-352`, verified). Replies can
arrive out of order and events interleave. Keep one request in flight and match its `requestId`.
While a knob turns, hold only the latest dB value and send it when the previous reply arrives.

## 7. Volume meters

One `InputVolumeMeters` event every 50 ms, fixed (S8 `Obs_VolumeMeter.h:79`, S7 `protocol.md:2125`,
verified). No request changes the rate. No server-side filter exists.

1. The array holds every active input with audio, not only the three on the knobs (S8
   `Obs_VolumeMeter.cpp:249-262`, verified).
2. Each channel is `[magnitude x volume, peak x volume, input peak]`, linear (S8
   `Obs_VolumeMeter.cpp:86-89`, verified). Use index 1, take the largest channel, convert with
   20 x log10.
3. An inactive input leaves the array. Let a missing meter fall to zero.
4. Ten stereo inputs cost 2.4 kB per event, 49 kB per second. Thirty 8-channel inputs cost
   18 kB per event (S12, likely).
5. OBS runs the meter thread only while a client holds bit 16 (S8 `EventHandler.cpp:73-96`,
   verified). Drop the bit with `Reidentify` when meters are not drawn.

## 8. Reconnect behaviour

There is no session resume and no event replay. A new connection gets a new challenge.

| Close code | Meaning | Device action |
|---|---|---|
| 1001 | OBS exits or the server stops | Retry with backoff. Expect a new salt |
| 1006, TCP reset | Link lost | Retry with backoff |
| 4009 | Authentication failed | Stop. Ask the app for a secret |
| 4010 | RPC version not supported | Stop. Show "firmware too old" |
| 4011 | Kicked from the OBS session list | Stop. "You must not automatically reconnect" |

Codes: S10 `WebSocketCloseCode.h`, S1 `:147`, `:177`, S7 `protocol.md:752`. Verified.

1. **Liveness.** The server never pings. Send a ping when the link is idle and drop it after
   missed pongs. The intervals are a design choice.
2. **Not ready.** Request code 207 means OBS is starting, switching collection or closing
   (5.3.0+). No events flow in that state (S2 `:212-219`, `:359`, verified). Wait and ask again.
3. **Collection switch.** On `CurrentSceneCollectionChanging` stop all requests. The protocol
   document calls requests during the switch undefined behaviour that can crash OBS (S7
   `protocol.md:1637`, verified). On `...Changed` read the full state again.
4. **No replay.** A lost reply does not prove the command did not run. Read the state and let the
   user press again. Prefer Start and Stop, chosen from the displayed state, over Toggle.

## 9. OBS 28 to OBS 33

`rpcVersion` is 1 in every release. Every request and event in section 5 exists since 5.0.0
except `InputSettingsChanged`. Pairs are the `plugins/obs-websocket` submodule pin (S13, verified).
The version column is the pin of the **last patch** of each OBS line, not of the `.0` release.
The `.0` releases differ: 29.1.0 ships 5.2.2, 30.0.0 ships 5.3.3, 30.2.0 ships 5.5.1, 31.0.0 ships
5.5.4, 32.1.0 ships 5.7.2 (S13, rechecked in Verification). None of these changes the 5.4.0 floor.

| OBS | obs-websocket | Change that touches this client |
|---|---|---|
| 28.0 to 28.1 | 5.0.2 | Baseline. Names only, no UUIDs |
| 29.0, 29.1 | 5.1.0, 5.2.3 | None for this client |
| 30.0 | 5.3.4 | Code 207 NotReady |
| 30.1 | 5.4.2 | UUIDs on scenes, inputs, transitions. `InputSettingsChanged` |
| 30.2, 31.0 | 5.5.2, 5.5.6 | `RecordFileChanged` in Outputs |
| 31.1, 32.0 | 5.6.2, 5.6.3 | `Hello.obsStudioVersion`. `inputKindCaps` in `GetInputList` |
| 32.1, 32.2 | 5.7.3, 5.7.4 | Canvases: optional `canvasUuid`, subscription bit 11 |
| 33.0 | 5.7.6 | Current |

The owner's machine has OBS 33.0.1 (S14, verified), so a floor of 5.4.0 costs nothing there.

## 10. Conflicts with repo rules

1. **"No OBS password in a CDC frame."** Option A keeps the rule but needs the app once per OBS
   launch. Only B or C reconnects with the app closed after an OBS restart, and B breaks the rule.
   The owner decides. This report does not pick B.
2. **"Text is printable ASCII"** in `docs/protocol.md`. OBS names are UTF-8.
3. **Protocol change rule.** A salt request and a secret reply are new CDC messages. They land in
   the C parser, the Rust parser, the vectors file and `docs/protocol.md` together.

## Not checked

1. Nothing was run against a live OBS. Nothing listens on 4455 on this machine (S14). Sizes and
   key order come from source reading and a local model. Risk: sizes off by a few bytes.
2. The websocketpp version inside the OBS Flatpak build.
3. MessagePack sizes, and any JSON library for the firmware. Those belong to report 04.

## Sources

Source files are at tag 5.7.6 of <https://github.com/obsproject/obs-websocket>, under `src/`.

- S1. `websocketserver/WebSocketServer.cpp`, `WebSocketServer.h`
- S2. `websocketserver/WebSocketServer_Protocol.cpp`, `rpc/WebSocketSession.h`
- S3. `utils/Crypto.cpp`
- S4. `Config.h`, `Config.cpp`
- S5. `forms/SettingsDialog.cpp`, `forms/ConnectInfo.cpp`
- S6. `obs-websocket.cpp`
- S7. `docs/generated/protocol.md` and `protocol.json` (repo root, same tag):
  <https://github.com/obsproject/obs-websocket/blob/5.7.6/docs/generated/protocol.md>
- S8. `utils/Obs_ArrayHelper.cpp`, `utils/Obs_VolumeMeter.cpp`, `Obs_VolumeMeter.h`, `utils/Json.h`,
  `eventhandler/EventHandler.cpp`, `EventHandler_Outputs.cpp`, `types/EventSubscription.h`
- S9. websocketpp 0.8.2, `transport/asio/endpoint.hpp`, `config/core.hpp`, `processors/hybi13.hpp`:
  <https://github.com/zaphoyd/websocketpp/tree/0.8.2/websocketpp>
- S10. `requesthandler/rpc/Request.cpp`, `RequestHandler_Inputs.cpp`, `_Stream.cpp`, `_Record.cpp`,
  `types/RequestStatus.h`, `websocketserver/types/WebSocketCloseCode.h`
- S11. RFC 6455 section 5.1 (client frames are masked): <https://www.rfc-editor.org/rfc/rfc6455.txt>
- S12. Local model, run today, not kept. Python `hashlib` for the vector. Python `json` with
  sorted keys for sizes. A C++ check of key order with `/usr/include/nlohmann/json.hpp`.
- S13. OBS Studio submodule pins for tags 28.0.0 to 33.0.1, read from
  `https://api.github.com/repos/obsproject/obs-studio/contents/plugins/obs-websocket?ref=<tag>`
  and resolved with `git describe` in the obs-websocket clone.
- S14. This machine: `flatpak info com.obsproject.Studio` (33.0.1), `ss -ltn` (no 4455),
  `sysctl net.ipv6.bindv6only` (0). The OBS password was not read.

## Open questions

1. Does the owner accept that the app or a tray helper runs once per OBS launch (option A)? If
   not: amend the password rule (B), or turn OBS authentication off and firewall 4455 (C)?
2. Who lists scenes and inputs for the mapping editor: the app on its own short OBS connection,
   or the device? The first keeps `GetInputList` off the device.
3. Is OBS 30.1 an acceptable minimum, so UUIDs are the only key?
4. Are meters wanted on the narrow display, or only dB and mute? Meters are the only steady
   traffic. Which scripts must the displays draw?
5. Will the owner enable the WebSocket server in OBS so the handshake, sizes and the test vector
   can be checked on a live socket?

## Verification

Skeptic pass, 2026-11-18. Fresh clone of obs-websocket at tag `5.7.6` (resolves to `e28f849`), in a
scratch directory outside the repo. Every row was opened in that source, not taken from the
report's citation. Result: the protocol facts hold. One table was imprecise and is now corrected.

| # | Claim | Source opened | Result |
|---|---|---|---|
| 1 | No TLS; server type is the non-TLS `websocketpp::config::asio` | `src/websocketserver/WebSocketServer.h:93` | Verified |
| 2 | Port 4455, server off by default, IPv4-only only via `--websocket_ipv4_only` | `src/Config.h:37-39`, `src/Config.cpp:108-111` | Verified. `Ipv4Only` is set only by the command-line flag |
| 3 | Salt and secret made once per `Start()`; new challenge per connection, same salt | `WebSocketServer.cpp:85-86`, `:247-258`; `SettingsDialog.cpp:198-221` | Verified. Settings restart fires on enable, port, or password change (password only if auth is on) |
| 4 | `secret = b64(sha256(password+salt))`, `auth = b64(sha256(secret+challenge))`, strings hashed as base64 text | `src/utils/Crypto.cpp:30-70` | Verified |
| 5 | Test vector `H1If...`, `1Ct9...`; protocol.md example `Dj6c...` does not match | Python `hashlib` run today; `docs/generated/protocol.md:88,94-95,206` | Verified. The doc names `supersecretpassword` and its own salt and challenge, yet gives `Dj6c...` |
| 6 | Mask bits; 1118 = 2+4+8+16+64+1024; meters bit 16; omitted mask = `All` (no high-volume bits) | `src/eventhandler/types/EventSubscription.h`, `rpc/WebSocketSession.h:108` | Verified |
| 7 | Meter thread exists only while a client holds bit 16; `Reidentify` re-counts it; 50 ms period | `EventHandler.cpp:73-96`, `WebSocketServer_Protocol.cpp` Reidentify case, `Obs_VolumeMeter.h:79`, protocol.md:2125 | Verified |
| 8 | Close codes 4009, 4010, 4011 ("must not automatically reconnect"); server stop sends 1001 | `WebSocketCloseCode.h:135-159`, `WebSocketServer.cpp:147,177` | Verified |
| 9 | Keys sorted: `using json = nlohmann::json` (std::map) | `src/utils/Json.h:26` | Verified for the type. Byte order on a live socket not observed |
| 10 | Messages run on a thread pool, so replies can reorder | `WebSocketServer.cpp:347-352` | Verified |
| 11 | UUIDs on scenes, inputs, transitions from 5.4.0; absent in 5.3.4; `InputSettingsChanged` from 5.4.0 | `git show 5.4.0:` and `5.3.4:` of `Obs_ArrayHelper.cpp`, `EventHandler_Scenes.cpp` | Verified |
| 12 | `obsStudioVersion` in `Hello` and `inputKindCaps` from 5.6.0; code 207 from 5.3.0 | `git show 5.5.6:`/`5.6.0:`; `RequestStatus.h:108-118`; `git grep NotReady 5.3.0` | Verified |
| 13 | OBS to obs-websocket pins | GitHub contents API for `plugins/obs-websocket` at OBS tags, then `git describe` | **Corrected.** Table lists last-patch pins. `.0` pins differ (see section 9 note). 30.1.0 ships 5.4.2 and 33.0.0/33.0.1 ship 5.7.6, as stated |
| 14 | Start on running = 500, Stop on stopped = 501; `outputActive` false for PAUSED and RECONNECTING | `RequestHandler_Stream.cpp:103,124`, `_Record.cpp:93,116`, `EventHandler_Outputs.cpp:22-39` | Verified |
| 15 | Volume dB range -100 to 26 | `RequestHandler_Inputs.cpp:506,520,545` | Verified |
| 16 | Server answers client pings; no compression | websocketpp 0.8.2 `impl/connection_impl.hpp:1957-1969`, `config/core.hpp:275` | Likely. Read upstream 0.8.2, not the copy in the OBS build |

### Recommendation against the owner's requirements

The owner wrote: "firmware on the device should be communicating with this websocket OBS url" and
the app should "pass websocket url". The recommendation keeps that: the device connects to OBS
itself; the app passes the URL and, under option A, the salt-bound secret. It does not deliver a
pad that reconnects alone after an OBS restart when OBS authentication is on. That gap is real
(check 3: every `Start()` makes a new salt) and is correctly put to the owner as open question 1.
Report 16 recommends option B instead; the two reports disagree, and the owner must pick.

Not checked: a live OBS socket, the websocketpp copy in the OBS Flatpak, and message sizes in
section 5 (still from the local model, likely).
