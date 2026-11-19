# Architecture A: the pad is the OBS client

Research and specification only, 2026-11-18. Angle: literal fidelity. The device talks to the OBS
WebSocket by itself; the app only configures it. Each fact points to the report that holds its
source and tag (`R03` = `docs/research/03-connectivity.md`, and so on). Nothing here was built or
run.

## Recommendation

Build a standalone pad. Once configured, it works with the app closed, across OBS restarts and PC
reboots.

1. **MCU.** RP2350B (QFN-80) with the W25Q128JVSIQ, on Pico SDK 2.3 in C. (R04: ACM + NCM + lwIP +
   DHCP server + TCP connect built for RP2350B, 53 kB text, verified build only)
2. **Path to OBS.** One USB cable, one composite device: CDC-ACM for configuration, CDC-NCM with
   lwIP (`NO_SYS`) and a device-side DHCP server for the network. The firmware dials
   `ws://<host-lease>:4455`. No radio. (R03, verified in source; not run on hardware)
3. **Authentication.** The pad stores the OBS password, write-only, in its own flash sector. **This
   needs a rule change** (below). The salt-bound secret dies at every OBS start (R05
   `WebSocketServer.cpp:85-86`, verified). So it cannot give a pad that works alone.
4. **Configuration.** Framed CDC-ACM protocol v2 carries one JSON document, chunked, with an
   optimistic `seq` check. It is read back in full, edited, and written back (R13).
5. **The app holds no secret and no OBS session.** It asks the pad for scene and input lists. The
   pad fetches them from OBS and streams them up over CDC. The app needs no `obws` and no keyring
   (R16 finding 6).

Next action: the owner approves the rule text in "Rule change" and one sudo step at install (the
firewall rule). Then run the dev-board spike in "Build order", step 1.

## Why this shape

The owner wrote "firmware on the device should be communicating with this websocket OBS url" and
"tauri application that can configure this device, to pass websocket url". Read literally, the
firmware holds the session and the app passes settings. Three facts decide the rest:

- obs-websocket binds `[::]:4455` on every interface, does not filter clients, and has no TLS (R03,
  R05, verified). So the pad can reach OBS over a USB network link, and needs no TLS stack.
- A metal CNC case blocks a module antenna (R03 `[H1]`, verified). The cable is already there for
  power and configuration.
- Only a stored password or auth off lets the pad log in alone after OBS restarts (R16 finding 1).
  OBS generates a 16-character random password on first load, about 95 bits (R16 `[O2]`,
  verified). This keeps the stored-password risk small.

Options rejected for this angle: the logic bridge (the app holds the socket, so the firmware never
talks to OBS); the byte relay over a second CDC port (the app must run, so the pad is not
standalone; kept as the fallback behind the transport seam); Wi-Fi on ESP32-S3 (a second secret,
an antenna through a metal case, a 615 mA USB budget, R10); Ethernet (a second cable to reach the
PC at the other end of the first).

## Firmware

Three layers. Only the bottom one includes SDK headers.

| Module | Job | Host-tested |
| --- | --- | --- |
| `core/link` | v2 framing, CRC-16/MODBUS, request id, chunking, pull API (fixes the lost-head and cap-drop defects, R02) | yes, shared `vectors.txt` |
| `core/cfg` | JSON config codec and validator, defaults generated from `board.toml` | yes, shared `config_vectors/` |
| `core/store` | two 16 KiB config slots plus a credential sector, CRC-32 headers, header written last | yes, NOR-flash model with power cut after each program call |
| `core/ws` | WebSocket client: upgrade, SHA-1 accept, masking, ping, close codes | yes, fake transport with short reads |
| `core/json` | streaming reader, fixed-field capture, depth of 12 or more (LwJSON, MIT; R04 `[X2]`: 580 B for an 88.6 kB reply) | yes |
| `core/obs` | Hello/Identify, SHA-256 + base64 auth, mask 1118 (+65536 while meters show), one request in flight, full re-read after `Identified`, stop on 4009/4010/4011 (R05) | yes, against the 50-line stdlib fake OBS (R15) |
| `core/actions` | keymap, pages, volume step, Start/Stop chosen from shown state; port of `host/` logic minus its RESUMED bug (R02) | yes |
| `core/input` | 4x4 diode matrix scan (9 MX + 4 tact + 3 pushes), debounce, 3 quadrature decoders | yes, kept from `input.c` |
| `core/ui` | widget model, band renderer into 16-line buffers, 4 bpp Latin + Cyrillic fonts (R14) | yes, golden frames to PNG |
| `port/rp2350` | TinyUSB descriptors (CDC driver ahead of NCM, R03), lwIP TCP behind the connect/send/receive/close seam, DHCP server with no router or DNS option, MAC and USB serial from the unique id, SPI DMA to two panels on two buses, flash ops via `flash_safe_execute` | no, hardware |

The same `core/` built with gcc, ASan and UBSan becomes `padsim`. It is a PTY device with a POSIX
socket behind the transport seam. The app's Rust tests and a real OBS on the PC can both drive it
before any board exists. `just test` stays gcc, cargo and python3.

## Configuration link (protocol v2)

Header: `0xA5`, version 2, type, id (u8, echoed), length (u16, up to 240), payload, CRC-16. v1 frames
get a NOTICE. Messages follow R13: `INFO_GET`/`INFO`, `CFG_READ`/`CFG_DATA`,
`CFG_BEGIN`/`CFG_CHUNK`/`CFG_COMMIT`/`RESULT`, `FACTORY_RESET`, `BOOTSEL`, `STATUS`, `INPUT`. This
design changes two things:

- **Removed:** `AUTH_NEED` and `AUTH_SECRET`.
- **Added:** `SET_CREDENTIAL` (app to pad; the pad answers with a status byte only),
  `CLEAR_CREDENTIALS`, and `OBS_LIST` with `OBS_ITEM`. `OBS_LIST` asks for scenes, inputs or
  hotkeys. The pad sends one `OBS_ITEM` per element (uuid, name, kind caps) as the stream reader
  yields it, so it never buffers the whole list.

`docs/protocol.md`, `firmware/link.c`, `host/src/protocol.rs` and `firmware/test/vectors.txt` change
in one commit. Text fields become UTF-8, replacing "printable ASCII" (R05 section 10).

Document (compact JSON, cap 16 KiB, `schema` + `seq`): `obs.url`, `obs.password_set` (read-only,
boolean), `net.pad`/`net.lease` (an editable subnet; the default must avoid 192.168.7.0/24, R03),
9 keys x pages, 4 buttons, 3 knobs (input uuid, step dB, push action), and two display sections that
name a layout and pick fields (R13, R14). Scenes and inputs are stored by UUID plus label. The
floor is obs-websocket 5.4.0 (OBS 30.1) (R05). The device validates on commit. It is the trust
boundary.

URL rule, replacing `host/src/config.rs:215`: accept `ws://` only. A loopback host means "the PC at
the other end of the cable" and maps to the lease. Refuse `wss://`, userinfo, path and query. A
non-host address is stored, and the strip display shows "unreachable over USB" (R03, R16).

## Rule change needed

"No OBS password in a CDC frame" conflicts with a pad that logs in alone. This architecture needs
R16's Text 1 in `CLAUDE.md`, verbatim:

> The OBS password and any Wi-Fi passphrase cross the CDC link only in `SET_CREDENTIAL`, app to
> device. No device-to-host frame, log line, display, readback or test vector carries a secret or a
> value derived from one. The device stores secrets in their own flash sector and erases it on
> `CLEAR_CREDENTIALS`, on the clear key combination, and before a host-requested BOOTSEL.

Accepted risk: anyone holding the pad can read its flash. RP2350 secure boot is not planned for the
prototype. Specify stepping A4 or later so the lock-down stays possible on the CNC unit (R16).

## The app at runtime

The app is a Tauri 2 shell over a Rust core with no Tauri, and a no-build HTML/ES-module UI
(greycode pattern, R13). Its jobs:

1. Discover pads by VID, PID and serial.
2. Read, edit and write the document, with stale-seq handling.
3. Pick scenes, inputs and hotkeys via `OBS_LIST`.
4. Take the password once (split an `obsws://` string, write it with `SET_CREDENTIAL`, drop it).
5. Preview the displays with the firmware's own `core/ui`, linked through `cc`, and "try on pad".
6. Diagnose from `STATUS`. On a pad TCP timeout, show the exact ufw command.
7. Export and import with no secret.
8. Update firmware.

No tray, no autostart, no keyring. The pad never needs the app after setup.

## Storage and firmware update

- **Flash layout.** Top of the 16 MB: two config slots (16 KiB body plus a 4 KiB header each) and
  one 4 KiB credential sector. The higher valid `seq` wins at boot. With no valid slot, the pad
  runs on compiled-in defaults and the strip shows "factory config". An erase stalls code running
  from flash for up to 400 ms, so a commit happens only on `CFG_COMMIT` (R13, W25Q128JV tSE likely).
- **Firmware update.** The app sends `BOOTSEL` with a magic number. The pad erases the credential
  sector, then reboots to the ROM UF2 drive, and the app copies the UF2. Ship no SDK reset interface
  that skips the wipe (R16). Cost: the user enters the password again after each update.

## Reuse from this repo

Keep: `board.toml` + `check_pins.py`, with a duplicate-GPIO check added; the frame codec and the
shared-vector discipline; the debounce and quadrature code; the `Secret` type and `logbuf.rs`; the
atomic save; the CAD export read-back; the test harness.

Port, then retire on the host: `obs_core` logic into `core/actions`.

Replace: the display path, `usb.c`, `main.c`, `app/` session and UI, `pcb/gen` (take the
macropad-greycode generator and the Freerouting split, R09), and the case geometry. About 1,800 of
7,055 lines carry over (R02, estimate).

## Build order

1. **Spike, about one afternoon, on a Pico 2 dev board.** Run the ACM + NCM image. Check that
   NetworkManager brings the link up with no default route. Then send `Hello` from OBS before and
   after the ufw rule. Retires risk 1.
2. **Contract first.** Write the new `board.toml` tables (two displays, matrix, three encoders), the
   v2 protocol, the config schema, and both vector files.
3. **Host-only core, in parallel slices.** `link`, `cfg` + `store`, `ws` + `json` + `obs`, `input`,
   `ui`. Each is gated by ASan tests. Then `padsim`, and an end-to-end run against a throwaway real
   OBS on port 4456.
4. **App core and UI against `padsim`.** The Tauri window comes after `webkit2gtk-4.1` is installed.
5. **PCB.** Placement-only spike (QFN-80 escape, 40-pin FPC, core-regulator loop), then the routed
   board, then DRC.
6. **Case.** Print first, then CNC + laser. Then hardware bring-up.

## Top risks and how each is retired early

1. **The NCM link or the composite device misbehaves on the host.** Step 1 spike. Fallback: the byte
   relay behind the same seam, with no PCB change.
2. **The owner rejects the stored password.** Ask before step 2. Then only option C (auth off plus
   a firewall) keeps the pad standalone. Otherwise the app runs at every OBS start, which is
   architecture B, not this one.
3. **Unbounded OBS messages exhaust RAM.** Streaming reader plus fuzzing in step 3. Test with a
   synthetic 500-scene list in `padsim`.
4. **The firewall step.** ufw drops 4455 by default (R03, verified). The app detects the timeout and
   prints a rule limited to the pad's address. This is tested in the spike.
5. **OBS on another PC is wanted.** NCM reaches only the host. Ask the owner now. A "yes" adds a
   radio or Ethernet, and that decision must come before the PCB.

Not checked: no hardware, no NM plug-in, no live OBS, no ARM build of this split. Every size here is
inherited from the reports.
