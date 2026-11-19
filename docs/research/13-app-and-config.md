# 13. The Linux Tauri app and bidirectional configuration

Research only, 2026-11-18. This file is the only file written. An earlier pass was interrupted. This
pass kept its first and second findings (re-checked where noted) and finished the design.

Confidence tags: **verified** (read or run today in a primary source), **likely** (reasoned from a
verified fact, or taken from a sibling report and not re-read), **unverified**. Keys such as `[L1]`
point into the Sources list. No hardware was used. No size in this report comes from a drawing, and
none is a mechanical size, so nothing needs a MEASURE tag.

## Recommendation

Keep the framed USB CDC-ACM link and raise it to protocol version 2: add a request id, typed
replies, and a chunked transfer of one configuration document. The document is compact JSON with a
`schema` number and a `seq` number. The device stores it in two flash slots and validates it on
commit. The app does read, edit and write with an optimistic check on `seq`. The OBS password never
leaves the PC. The app keeps it in the desktop keyring and hands the device only the salt-bound
secret, once per OBS start (report 05).

Build the app the way `macropad-greycode/configurator` is built: a Rust core with no Tauri, a thin
Tauri 2 shell, and a plain HTML and ES-module UI with no build step. Add a device simulator. It is
the firmware's own C core, built with gcc, behind a pseudo-terminal, so the app and the firmware
test against each other in `just test` without hardware.

Next action: the owner answers open question 1 (OBS authentication on or off). It decides whether
the app must keep running in the tray.

Install for the Tauri window, once, as the owner:

```bash
sudo pacman -S --needed webkit2gtk-4.1 xdotool libayatana-appindicator
```

`webkit2gtk-4.1` is required. `xdotool` is on Tauri's Arch list (it ships `libxdo.so`).
`libayatana-appindicator` is needed only for the tray icon. Everything else on Tauri's list is
already present. (verified on this machine, `[T1]` `[L6]`)

## What exists and what holds up

1. **The app today is an OBS bridge, not a configurator.** `app/src-tauri/src/session.rs` (688
   lines) holds the `obws` socket and turns pad events into OBS calls. The seven commands are
   `get_state`, `set_connection`, `set_key`, `select_input`, `set_profile`, `connect`, `disconnect`
   (`main.rs:21-66`). None reads a config from the device. (verified, `[L1]`)
2. **The config lives in a file on the PC.** `host/src/config.rs` parses TOML with
   `deny_unknown_fields`, holds `[KeyAction; 9]`, refuses a file that is not `0600`, and saves by
   temp file, `sync_all` and rename (`:150-171`). `KeyAction` has seven variants: Scene, Mute,
   Transition, Stream, Record, ProfileNext, ProfilePrev (`keymap.rs:14-24`). (verified, `[L2]`)
3. **Protocol v1 cannot carry a config.** A frame holds at most 240 payload bytes. There is no
   request id, no reply type and no chunking. The parser buffer is 256 bytes and the transmit queue
   1024 bytes (`firmware/link.h:12`, `:37-45`). The shared vectors file and the CRC-16/MODBUS framing
   are worth keeping. (verified, `[L3]`)
4. **The device path is hard-coded.** `pad.rs:27` opens `/dev/macropad-obs`, a udev symlink from
   `app/udev/70-macropad-obs.rules`. Two pads collide on it, and the USB serial string is the
   constant `"obs"` (`firmware/src/usb_descriptors.c:45`). (verified, `[L1]` `[L3]`)
5. **The sibling configurator is the structure to copy.** `macropad-greycode/configurator/` splits a
   core crate with no Tauri (`document.rs`, `session.rs`, `atomic.rs`), a Tauri 2 shell with six
   commands and bundling off, and a no-build HTML and ES-module UI whose model is tested with
   `node --test`. Its README already names `webkit2gtk-4.1` as the one missing package. Save refuses
   when the file changed on disk since it was opened. That is the same optimistic check this report
   puts on the device. (verified, `[P1]`)
6. **The other two sibling projects add two ideas.** `macropad-nyxilab/host` talks to a vendor HID
   interface (64-byte reports, usage page `0xFF4E`) through `/dev/hidrawN` and matches the udev rule
   on the interface string (`host/udev/70-nyxilab-macropad.rules`). `macropad/firmware/sim` drives
   the firmware core on the PC and renders the display to PNG. (verified, `[P2]` `[P3]`)

Reuse: the CRC framing, the vectors-file discipline, the atomic-save code, the `Secret` type that
never prints, and the `obws` dependency (for OBS pickers, see below). Drop: `session.rs` as the
main loop, `Core::on_pad`, the TOML file as the source of truth, and the fixed symlink.

## The configuration model

One document describes the whole pad. It lives on the device. The app holds a copy only while
editing, and as an export file.

```json
{
  "schema": 1,
  "seq": 17,
  "name": "Desk pad",
  "obs": { "url": "ws://192.168.7.2:4455", "auth": "app" },
  "net": { "pad": "192.168.7.1/24", "lease": "192.168.7.2" },
  "keys":    [ {"do": "scene", "uuid": "…", "label": "Cam"} ],
  "buttons": [ {"do": "record_toggle"} ],
  "knobs":   [ {"input": {"uuid": "…", "label": "Mic"}, "step_db": 1.0, "push": {"do": "mute_toggle"}} ],
  "pages":   [ {"name": "Main", "keys": ["…9 actions…"]} ],
  "main_display":  { "layout": "scenes_grid", "status_bar": ["rec", "live", "obs_link"] },
  "strip_display": { "layout": "knobs3", "fields": ["name", "level", "mute"] },
  "ui": { "brightness": 80, "dim_after_s": 300 }
}
```

1. **OBS URL and authentication.** `obs.url` is `ws://host:port`. The app refuses `wss://` because
   obs-websocket has no TLS (report 05). `obs.auth` is `none` or `app`. There is no password field,
   in the document or in any frame. With `app`, the device asks the app for the salt-bound secret
   when it sees a new salt in `Hello`. The secret lives in device RAM only, never in flash. (likely,
   from report 05 `[R5]`)
2. **Network.** With the USB network link of reports 03 and 04, the pad runs the DHCP server and
   leases one address to the PC. So `net` holds the pad address and the leased address, and
   `obs.url` defaults to the leased address. The TinyUSB example's `192.168.7.0/24` may collide
   with the owner's LAN, so the subnet must be editable. (likely, from report 03 `[R3]`)
3. **Mapping.** Nine keys per page, four small buttons, three knobs (turn, push). One tagged action
   type serves all of them: `scene`, `mute_toggle`, `record_toggle`, `stream_toggle`, `transition`,
   `source_visibility`, `hotkey`, `page`, `none`. Scenes and inputs are stored by UUID with a label.
   UUIDs survive a rename. obs-websocket 5.4.0 is the floor for UUIDs (report 05). The label is what
   the display shows when OBS is not connected. (likely, `[R5]`)
4. **Displays.** The document chooses a layout by name and fills its fields from a fixed list. It
   does not describe pixels. The firmware owns drawing (report 14). This keeps the schema small and
   makes the live preview exact (see below).
5. **Pages.** Pages change only the nine keys. Buttons and knobs stay fixed, so a knob never changes
   meaning under the owner's hand. (proposal)

Text format. Compared:

| Format | For | Against |
|---|---|---|
| JSON (recommended) | The firmware already needs a streaming JSON reader for OBS (report 05). `serde_json` on the PC. The export file is the same bytes | Larger than binary. Not stored with comments |
| CBOR | Compact, typed | A second parser on the device. Not readable as an export |
| Fixed C struct | Simplest firmware | Every schema change breaks old files. Padding and layout bugs |
| TOML (today) | Comments, readable | No TOML parser on the device |

A cap of 16 KiB covers 9 keys x 8 pages plus 7 controls with 48-byte labels, with room to spare.
(arithmetic: 79 actions x about 120 bytes is about 9.5 kB)

## Transport between app and device

| Option | For | Against |
|---|---|---|
| A. CDC-ACM, protocol v2 (recommended) | Already exists in C and Rust, with shared vectors. Byte stream, so a 16 KiB document is about 80 frames. Works beside CDC-NCM in one composite device (reports 03, 04) | Needs a udev rule for access. ModemManager may touch the port |
| B. Vendor HID (as in nyxilab) | No tty, no ModemManager. hidraw access by udev `uaccess` | 64-byte reports, so the framing is rewritten. One more interface and two endpoints beside NCM |
| C. HTTP or a WebSocket on the pad over the USB network | The app could use plain HTTP | The pad becomes a server on a network interface. The firewall step of report 03 grows. Config fails exactly when the network is broken, which is when it is needed |
| D. A file on a USB mass-storage drive | No app needed to edit | No read-modify-write check. No live preview. A third USB class |

Option A also stays usable when the network link is down, which is the moment the owner needs to fix
the URL. (likely)

### Protocol v2 sketch

Header: `SOF 0xA5`, `version 0x02`, `type`, `id` (u8, echoed in the reply), `length` (u16, 0..240),
payload, CRC-16/MODBUS. v1 frames are refused with a NOTICE, not parsed. The header change, the C
parser, the Rust parser, `firmware/test/vectors.txt` and `docs/protocol.md` change in one commit, as
the repo rule demands. (`CLAUDE.md`, verified)

| Direction | Type | Payload |
|---|---|---|
| app to pad | `INFO_GET` | empty |
| pad to app | `INFO` | proto, firmware version string, git hash, board revision, unique id, schema min and max, max document bytes, counts (keys 9, buttons 4, knobs 3), display sizes, capability bits |
| app to pad | `CFG_READ` | `u16 offset`, `u8 len` |
| pad to app | `CFG_DATA` | `u32 seq`, `u16 total`, `u16 offset`, bytes |
| app to pad | `CFG_BEGIN` | `u32 base_seq`, `u16 total`, `u32 crc32`, `u8 flags` (bit0: try only, do not store) |
| app to pad | `CFG_CHUNK` | `u16 offset`, bytes |
| app to pad | `CFG_COMMIT` | empty |
| pad to app | `RESULT` | `u8 code` (ok, busy, stale seq, bad crc, too big, invalid), `u32 new_seq`, path of the first bad field, up to 48 bytes |
| app to pad | `FACTORY_RESET` | `u32` magic, so one bit flip cannot erase the config |
| app to pad | `BOOTSEL` | magic. Reboots into the ROM loader for a UF2 update |
| pad to app | `AUTH_NEED` | the 44-byte salt and the OBS version from `Hello` |
| app to pad | `AUTH_SECRET` | the 44-byte salt-bound secret. Not the password |
| pad to app | `STATUS` | OBS link state, last close code, counters. Sent on change |
| pad to app | `INPUT` | key, button or knob event, for the app's "press to select" |

Every request gets exactly one `RESULT` or data reply with the same `id`. The app waits 1 s, then
retries the same request. `CFG_CHUNK` is idempotent by offset, so a retry is safe. (proposal)

`AUTH_SECRET` is a new carve-out of the rule "No OBS password in a CDC frame". The secret is not the
password, but report 05 says it "equals the password in power until the salt changes". Flag for the
owner: the rule's wording holds; its spirit is arguable. (verified wording, `CLAUDE.md`; `[R5]`)

## Read-modify-write and schema versions

1. The app reads `INFO`. If the firmware's schema max is above the app's, the app opens the config
   read-only and says "update the app". If it is below, the app writes the oldest schema the
   firmware takes, or refuses.
2. The app reads the document and its `seq`, and keeps the raw JSON value. Edits change only the
   fields the user touched. Unknown fields stay, so an older app does not drop a newer field.
3. The app validates with its own rules, for fast feedback. Then it writes with `CFG_BEGIN
   base_seq`. The device refuses with "stale seq" if the stored `seq` changed (another app window,
   a factory reset). The app re-reads and shows what changed. This is the greycode "file changed on
   disk" check moved to the device. (`[P1]`, verified)
4. The device validates again on commit. It is the trust boundary and the only check that cannot be
   skipped. One shared file of valid and invalid documents (`firmware/test/config_vectors/`) runs in
   both the C and the Rust tests, as `vectors.txt` does for frames.
5. Migrations live in the app's Rust core only, as one function per schema step. The firmware reads
   one schema. (proposal)

## Atomic storage on device flash

Pico SDK 2.3: sector 4096 bytes, page 256 bytes, `flash_range_erase`, `flash_range_program`,
`flash_safe_execute` (runs the callback with interrupts off, and parks the other core). Flash is
mapped at `0x10000000`, so the stored document can be parsed in place. (verified, `[S1]`)

1. Two slots, A and B, each 16 KiB plus a 4 KiB header sector, at the top of the 16 MB flash, away
   from the firmware image. (proposal)
2. A header holds magic, schema, `seq`, length and CRC-32 of the body. The header is programmed
   last. An erased or torn header fails its CRC.
3. Commit writes the slot that does not hold the current document: erase, program the body,
   program the header, read back and check the CRC. Then it switches to it in RAM.
4. At boot, the valid slot with the higher `seq` wins. If neither is valid, the firmware uses the
   defaults compiled in and shows "factory config" on the strip display.
5. Erasing a sector stalls code that runs from flash. W25Q128JV sector erase is typically 45 ms,
   at most 400 ms (datasheet, likely `[S2]`). So commit happens only on `CFG_COMMIT`, never per
   keystroke, and the display freezes for under 2 s. Endurance is 100,000 erase cycles per sector,
   far above any editing rate. (likely, `[S2]`)
6. The host-built test models NOR flash: erase sets `0xFF`, programming only clears bits. It cuts
   power after every program call and checks that boot always finds the old or the new document,
   never a mix. (proposal)

## Factory reset

Two routes. From the app: `FACTORY_RESET` with its magic, behind a confirm dialog that offers an
export first. On the pad: hold the first and last small button while plugging in. Both erase both
slot headers. The firmware then runs on compiled-in defaults. The defaults are generated from
`board.toml` so the counts cannot drift. (proposal)

## Version and capability report

`INFO` is the first exchange of every session. The app shows firmware version, git hash, board
revision and unique id on its Device page. Capability bits gate UI features: USB network present,
OBS client present, on-device preview, `BOOTSEL`. The unique id becomes the USB serial string.
The Pico SDK has `pico_unique_id` for this. (verified it exists, `[S1]`; likely that it reads the
flash id on RP2040 and the OTP chip id on RP2350)

## Live preview of display layouts

1. **Exact preview in the app (recommended).** The firmware's UI core is plain C with no SDK
   headers (report 14). The app's Rust core builds it with the `cc` crate and calls
   `ui_render(document, sample_state, framebuffer)`. The UI shows the RGB565 buffer on a canvas,
   at 1:1 and zoomed. The pixels are the firmware's pixels. `macropad-nyxilab/tools/ui_sim` and
   `macropad/firmware/sim` did the same for PNGs. (verified for the sibling pattern, `[P2]` `[P3]`)
2. **Try on the device.** `CFG_BEGIN` with the "try only" flag loads the draft into RAM and draws
   it, without storing. The pad goes back to the stored document after 30 s or on `CFG_READ`.
   This shows real colours and viewing angle. (proposal)
3. Rejected: a second renderer in JavaScript. It drifts from the firmware.

## Export and import

Export writes the document as pretty JSON with `schema`, a `exported_from` block (firmware version,
unique id, date) and no secrets. Import parses it, runs the app's migrations and validation, and
opens it as an unsaved draft. The user then writes it. Atomic file save reuses greycode's
`atomic.rs` (temp file, fsync, rename). (verified for the pattern, `[P1]`)

## Device discovery and udev

1. Discovery lists ports with `serialport::available_ports()`, which uses libudev by default, and
   keeps USB ports with the pad's VID, PID and interface. Each pad is named by its serial string.
   (verified that `libudev` is the crate's default feature, `[S3]`; likely for the USB fields)
2. `ttyACM*` gets group `uucp` (`/usr/lib/udev/rules.d/50-udev-default.rules:47`) and the user is
   not in it. `/etc/udev/rules.d/` is empty. The rule is required and is not installed. (verified,
   `[L5]`)
3. ModemManager 1.24.2 is installed but inactive. Its default "strict" filter does not probe a tty
   unless it looks like a modem, and TinyUSB's `TUD_CDC_DESCRIPTOR` sets protocol "none", not AT.
   Add `ID_MM_DEVICE_IGNORE` anyway, for the day it is turned on. (verified for the package, the
   service state and the descriptor, `[L5]` `[S4]`; likely for the filter result, `[M1]`)
4. Proposed rule, one file, installed with sudo once:

   ```text
   SUBSYSTEM=="tty", ATTRS{idVendor}=="1209", ATTRS{idProduct}=="4f42", \
     TAG+="uaccess", ENV{ID_MM_DEVICE_IGNORE}="1", SYMLINK+="macropad-obs-$attr{serial}"
   ```

   The app should not depend on the symlink. It is for the shell.
5. `https://pid.codes/1209/4F42/` returns 404 today, so PID `0x4F42` is likely not allocated.
   (verified 404, `[U1]`)
6. The simulator path: an env var `MACROPAD_OBS_PORT=/dev/pts/N` makes the app skip discovery.

## What the app does once the device talks to OBS

1. **Configure** the pad. The main job.
2. **Hand over the OBS secret** once per OBS start, if OBS auth is on. The app reads the password
   from the desktop keyring (Secret Service), computes the salt-bound secret, sends `AUTH_SECRET`.
   For this the app must be running when OBS starts: a tray icon and an XDG autostart entry. If
   the owner turns OBS auth off, this whole duty goes away. (likely, `[R5]`)
3. **Offer OBS pickers.** The app opens its own short `obws` session to list scenes, inputs and
   hotkeys with their UUIDs, so the user picks from a list. `obws` 0.15.0 is already a dependency.
   (verified dependency, `[L1]`)
4. **Diagnose.** Show the pad's `STATUS`: link state, last close code, OBS version, counters.
   Show "the PC firewall drops port 4455" when the pad reports a TCP timeout (report 03).
5. **Update firmware.** `BOOTSEL`, then copy the UF2 to the ROM drive. (proposal)

It no longer turns key presses into OBS calls. That is the firmware's job now.

## UI structure

One window, as greycode. A top bar with the device picker, a state chip ("In sync", "Unsaved
changes", "Changed on device", "Disconnected"), and Read and Write buttons. A left list of pages:

| Page | Content |
|---|---|
| Pad | A drawing of the pad as in the owner's sketch: big display and strip on top, the 3x3 keys, the row of 4 buttons, 3 knobs on the right. Click a control, or press it on the pad, to edit it in the side panel. Page tabs for the nine keys |
| Displays | Layout and fields for each display, with the exact preview and "Try on pad" |
| OBS | URL, auth mode, "Store password in keyring", "Test connection" (from the app and from the pad) |
| Network | Pad subnet and leased address, with the firewall command to copy |
| Device | Firmware, capability list, unique id, firmware update, factory reset, export and import |

`model.js` (layout, validation messages, list helpers) has no DOM and is tested with `node --test`,
as in greycode. Node 26 is installed. Every edit goes to the Rust core through a Tauri command; the
core is the only owner of the document. Device events reach the UI through a Tauri event. (verified
for the greycode pattern, `[P1]`; likely for Tauri event delivery, `[T2]`)

## Testing without hardware

1. **Device simulator `padsim`.** A host program, built with gcc and ASan, that links the same
   firmware C core: `link.c`, the config codec and validator, the flash store over a NOR model in a
   file, and the UI core. It opens a pseudo-terminal with `openpty` and prints its path. The app
   core opens that path like a real port. Scripted key and knob events come from stdin. (proposal)
2. **Contract tests** in the app's Rust core spawn `padsim` and run: INFO, read, write, stale-seq
   refusal, try-only revert, factory reset, power cut during commit, oversized document, a v1
   frame. These run in `just test` because they need only gcc and cargo. The Tauri shell stays out
   of `just test`, as today. (verified that `just test` does not build `app/src-tauri`, `CLAUDE.md`)
3. **Shared vectors.** Frame vectors and config vectors run in both the C and the Rust tests.
4. **Fake OBS.** For the auth handover and the pickers, a small obs-websocket 5 server stub
   (report 15). Node 26 has a WebSocket client built in. A server stub needs a crate or a package.
   (likely, `[R6]`)
5. **UI.** `node --test` for `model.js`. The window itself is checked by hand once webkit2gtk-4.1
   is installed. Under Wayland on this AMD GPU no WebKit workaround is expected. (unverified)

## Conflicts with repo rules

1. "No OBS password in a CDC frame": held. `AUTH_SECRET` carries a password-equivalent secret
   bound to one OBS run. The owner decides whether that is acceptable (open question 1).
2. "Protocol changes update ... together": v2 changes all four files. No conflict.
3. `host/config.rs` refuses a TOML file that is not `0600`. Under this design the PC file is only an
   export with no secret, so that check moves to nothing. Flag, not a conflict.

## Sources

- `[L1]` `app/src-tauri/src/main.rs`, `session.rs`, `pad.rs`, `Cargo.toml` (obws 0.15.0,
  serialport 4.7, tauri 2), `tauri.conf.json`, `app/udev/70-macropad-obs.rules`. Read today.
- `[L2]` `host/src/config.rs`, `host/src/keymap.rs`. Read today.
- `[L3]` `firmware/link.h`, `firmware/src/usb_descriptors.c:40-45`, `docs/protocol.md`,
  `firmware/test/vectors.txt`. Read today.
- `[L5]` `/usr/lib/udev/rules.d/50-udev-default.rules:47`, `/etc/udev/rules.d/`, `id -nG`,
  `pacman -Q modemmanager` (1.24.2-2.1), `systemctl is-active ModemManager` (inactive),
  `/usr/lib/udev/rules.d/77-mm-*.rules`. Run today.
- `[L6]` `pacman -Q` and `pacman -Si` for webkit2gtk-4.1 (extra, 2.54.2-1, not installed), xdotool
  (extra, not installed), libayatana-appindicator (extra, 0.6.1-1, not installed), base-devel,
  curl, wget, file, openssl, appmenu-gtk-module, librsvg (installed). `pkg-config`: gtk+-3.0 3.24.52,
  libsoup-3.0 3.8.1, libudev 262. Run today.
- `[P1]` `/home/worxbend/Projects/macropad-greycode/configurator/README.md`, `core/src/*.rs`,
  `src-tauri/src/main.rs`. Read today.
- `[P2]` `/home/worxbend/Projects/macropad-nyxilab/host/src/protocol.rs`, `device.rs`,
  `host/udev/70-nyxilab-macropad.rules`, `tools/ui_sim/`. Read today.
- `[P3]` `/home/worxbend/Projects/macropad/firmware/README.md` (Simulator section), `sim/src/`.
  Read today.
- `[S1]` Pico SDK in `~/.platformio/packages/framework-arduinopico/pico-sdk/`:
  `src/rp2_common/pico_flash/include/pico/flash.h`, `hardware_flash`, `pico_unique_id`. Read today.
- `[S2]` Winbond W25Q128JV datasheet, AC characteristics (tSE) and endurance,
  https://www.winbond.com/hq/product/code-storage-flash-memory/serial-nor-flash/ . Not re-read today.
- `[S3]` `~/.cargo/registry/src/*/serialport-4.10.1/Cargo.toml:41` (`default = ["libudev"]`).
- `[S4]` `pico-sdk/lib/tinyusb/src/device/usbd.h:233-237` (`CDC_COMM_PROTOCOL_NONE`). Read today.
- `[S5]` `libappindicator-sys-0.9.0/src/lib.rs:14-20` (loads `libayatana-appindicator3.so.1`, then
  `libappindicator3.so.1`, at run time). Read today.
- `[T1]` Tauri 2 prerequisites, Arch list, https://v2.tauri.app/start/prerequisites/ . Read today.
- `[T2]` Tauri 2 events and channels, https://v2.tauri.app/develop/calling-frontend/ . Not read today.
- `[M1]` ModemManager port and device detection, filter policies,
  https://modemmanager.org/docs/modemmanager/port-and-device-detection/ . Read today: default
  "strict" since 1.20.
- `[U1]` https://pid.codes/1209/4F42/ returned HTTP 404 today.
- `[R3]` `docs/research/03-connectivity.md` (address plan, DHCP server, firewall).
- `[R5]` `docs/research/05-obs-websocket.md` (auth, salt per server start, UUIDs, no `wss`).
- `[R6]` `docs/research/15-verification-strategy.md` (Node 26, no Python websockets).

## Open questions

1. Is OBS authentication on? If yes, the app must run at every OBS start (tray plus autostart), and
   the owner must accept a salt-bound secret in a CDC frame. If no, the pad is fully on its own.
2. Should the PID be registered at pid.codes, or does the pad use a test PID while private?
3. Is a desktop keyring (GNOME Keyring or KWallet with Secret Service) running in the owner's
   session? The app stores the OBS password there.
4. Should pages also remap the four small buttons, or only the nine keys?
5. Is an on-pad edit (for example, hold a key to assign the current scene) wanted? It makes the
   device a second writer, and the `seq` check then matters in practice.
6. Which OBS actions beyond the seven of today are needed for the buttons (replay buffer, virtual
   camera, studio mode, screenshot)?
7. Should firmware update from the app be in the first release, or is a manual UF2 copy enough?
