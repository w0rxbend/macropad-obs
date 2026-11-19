# Architecture B: lowest risk

Research only, 2026-11-18. Angle: the smallest step from what already works, the fewest unproven
parts, everything testable without hardware. Tags: **verified** (read or run in a primary source),
**likely**, **unverified**. Report numbers point into `docs/research/`.

## Recommendation

Build on an **RP2040** board ported from the `macropad-greycode` generator. The firmware speaks
obs-websocket 5 itself: it dials the stored URL, does the handshake, sends `Identify`, owns every
request and event. In release 1 the TCP bytes travel through a **byte relay** in the app over a
second CDC-ACM port. The OBS password stays in the app. Per connection, the app answers the
device's `Hello` challenge with the one-time auth string. The repo rule "No OBS password in a CDC
frame" holds as written. USB networking (CDC-NCM + lwIP) is release 2. It is firmware only, behind
the same byte-stream seam, on the same board, and it ships only after a dev-board spike passes.

Next action: the owner answers two blocking questions. May sibling code be copied under MIT and
CERN-OHL-S-2.0? Is "the app runs in the tray while the pad is used" acceptable for release 1?

Why this is the lowest-risk reading of the owner's words:

1. **No network unknown on the critical path.** NCM needs NetworkManager to bring the link up, a
   sudo firewall rule (ufw input DROP on this PC), and stable ACM + NCM composite. None of it was
   observed on hardware (report 03, "Not checked"). The relay needs none of it: no lwIP, no DHCP, no
   firewall rule, and OBS may sit on any host the PC reaches (report 03, option d2, likely).
2. **No rule change.** Report 16 shows a stored salt-bound secret dies at each OBS restart, so the
   pad either stores the password (rule change) or needs the app (verified, report 16 finding 1).
   With the relay the app is present at every connect anyway. It can answer the per-connection
   challenge, which is weaker than even the salt-bound secret: replaying it is useless once that
   session closes, because the challenge is new per session (`WebSocketServer.cpp:254`, verified in
   report 05).
3. **The board is the proven board.** greycode is RP2040 + W25Q128 (`board.toml:8`, verified). Its
   generator rebuilt byte-identical in KiCad 9.0.9, and with Freerouting the board gave 0 DRC
   violations in KiCad 9 and 10 (report 09, verified). RP2040 `C2040` and W25Q128 `C97521` are
   already on the repo's checked LCSC list. RP2040 has no core-regulator inductor and no QFN-80
   fan-out (report 04, "Risks of the first choice").
4. **The hardware does not depend on the network decision.** Relay and NCM both ride the one USB
   cable. RP2040 built ACM + NCM + HID + lwIP into 56 kB text and 34 kB bss (report 04 `[X1]`,
   verified build only). Release 2 needs no new board.

Where this departs from earlier reports: report 04 picks RP2350B for margin; report 03 puts NCM
first; report 13 hands over a salt-bound secret; report 16 stores the password. Each is a sound
next step. None is the smallest proven one.

## Decisions

| Topic | Decision | Evidence |
| --- | --- | --- |
| MCU | RP2040 QFN-56, W25Q128JVSIQ, 12 MHz crystal, AP2112K, greycode USB-C/ESD/fuse block with the enable pin tied to VIN | reports 04, 10; greycode `board.toml` (verified) |
| Pins | 4x4 matrix 8, encoder A/B 6, two SPI buses 8 (SCK, MOSI, CS, DC each), shared RESET 1, backlight PWM 2: 25 of 30. No debug UART (logs on CDC) | report 04 pin budget (verified), report 08 |
| Reach OBS | Release 1: app byte relay on CDC-ACM port 1. Release 2: CDC-NCM + lwIP `NO_SYS`, pad runs the DHCP server, no router and no DNS option | report 03 (d2) and (b) |
| Auth | Release 1: pad sends `{salt, challenge}` to the app, app returns `base64(sha256(base64(sha256(pw+salt))+challenge))`. Pad holds it in RAM for one `Identify`, then zeroes it. Auth off in OBS also works | report 05 section 2 (verified) |
| Firmware | C11 on Pico SDK 2.3 + TinyUSB 0.18 with two CDC-ACM interfaces (`cdc_dual_ports` example, `CFG_TUD_CDC 2`, verified in the local SDK). SDK-free `firmware/core/` | report 04 |
| Config transport | Protocol v2 framed CDC-ACM on port 0: SOF, version 2, type, request id, u16 length, payload <= 240, CRC-16/MODBUS. Chunked document read and write, `seq` check, commit | report 13 |
| Schema | One JSON document, `schema` + `seq`, cap 16 KiB, scenes and inputs by UUID plus a label, displays by named layout and widget list. Same bytes as export | reports 13, 14 |
| Storage | Two 4 KiB-aligned 16 KiB slots at the top of flash, each with header (magic, schema, seq, length, CRC-32). Boot picks the newest valid slot, else factory defaults | report 13 |
| Display | Two SPI buses, 16-line band buffers by DMA, no frame buffer (about 20 kB), 4 bpp Latin + Cyrillic fonts from `lv_font_conv`. Widget redraw on change only | report 14 |
| Update | UF2 from the boot ROM. App sends `REBOOT_BOOTSEL`, pad calls `reset_usb_boot`, app copies the UF2 to the drive. Physical BOOTSEL button as fallback. Config slots sit above the image and survive | report 04 (UF2 in ROM, verified) |

The device needs about 105 kB of 264 kB RAM in release 1: band buffers 20 kB, stream JSON reader
state 580 B (report 04 `[X2]`, verified by test), config 16 kB, USB and link 8 kB, stack and the
rest estimated (likely). Release 2 adds about 34 kB of lwIP and USB state (report 04 `[X1]`).

RP2040 SPI tops out at 62.5 Mb/s. At `clk_peri` 125 MHz an even divider gives 31.25 MHz for a
40 MHz request: a full 320x480 frame is about 79 ms (arithmetic, likely). Band redraw of a 104x104
key cell is about 5.5 ms. That is enough for a pad that redraws cells, not video.

## Module split

| Module | Responsibility | Depends on | Built on the host |
| --- | --- | --- | --- |
| `core/link` | v2 frame codec, pull-style feed, no silent drops | none | yes, ASan, shared vectors |
| `core/input` | 4x4 scan, debounce (16-bit mask), 3 quadrature decoders | none | yes |
| `core/ws` | WebSocket client framing, SHA-1, base64, masking | `net` seam | yes, against a fake OBS |
| `core/json` | streaming reader, fixed-field capture (LwJSON-class) | none | yes, fuzzed |
| `core/obs` | Hello, auth request, Identify, state, requests, events, reconnect | ws, json | yes |
| `core/config` | document parse and validate, slot select, defaults | json | yes, fuzzed |
| `core/ui` | widget model, band renderer, fonts | config, obs state | yes, golden PNG frames |
| `port/rp2040` | TinyUSB dual ACM, SPI DMA, GPIO, flash, `net` seam over relay (R1) or lwIP (R2) | Pico SDK | no (ARM build only) |
| `host/obs_core` | v2 codec, config document types, relay, auth responder | none | yes, `cargo test` |
| `app/src-tauri` | thin Tauri 2 shell, keyring, obws pickers, editor, firmware update, tray | `obs_core` | core yes, window needs webkit2gtk-4.1 |
| `tools/padsim` | `core/*` built with gcc behind a PTY pair | core | yes |

The `net` seam is four calls: connect, send, receive, close. The relay, lwIP and a POSIX socket each
implement it. So `just test` runs the firmware core through padsim, the Rust relay and a stdlib fake
OBS server in one process tree. Report 15 ran such a fake server through a full handshake (likely,
not re-run here).

## The app at runtime

1. Finds pads by USB serial (from the flash unique ID). The udev rule adds `uaccess` and
   `ID_MM_DEVICE_IGNORE` and links each port by interface number (report 13).
2. Configuration: read the document, edit, write with `seq`, commit. The pad rejects a stale `seq`.
3. OBS pickers: the app's own short obws session lists scenes and inputs. The same keyring password
   serves it.
4. Relay: on `TCP_OPEN{host, port}` from the pad, open TCP and copy `TCP_DATA` both ways until
   `TCP_CLOSE`. The pad picks the host from its stored URL. The app never parses OBS traffic.
5. Auth: on `AUTH_CHALLENGE{salt, challenge}` answer `AUTH_RESPONSE{string}`. The password lives in
   Secret Service (KWallet shim present, report 16) or comes from the user once.
6. Firmware update and diagnostics (link state, last close code, counters).

## What is reused

From this repo: the `board.toml` + `check_pins.py` process (add a duplicate-GPIO check), the CRC
framing and vectors discipline, `input.c` debounce and quadrature, `config.rs` file safety and the
`Secret` type, `logbuf.rs`, `pad.rs` reopen loop, the `bridge.rs` `MemPort` seam, `cad` export
read-back, the test harness (report 02). From siblings, if the owner allows it: greycode PCB
generator, `MX_Hotswap` footprint and configurator split; nyxilab two-panel pattern and 3MF, GLB and
FreeCAD exporters; macropad coupons, CNC drawings and laser DXF (report 01). Replaced: display path,
`usb.c`, `main.c`, app session and UI, PCB generator, case geometry.

## Build order

1. Contracts: `board.toml` v2, `docs/protocol.md` v2, `vectors.txt`, config schema. Owner signs off.
2. Host-only firmware core plus padsim, the Rust v2 codec and relay, the fake OBS server. End-to-end
   test in `just test`. No hardware.
3. PCB placement and route spike on the ported generator (RP2040, matrix, 3 EC11, 4 tact, two FPC).
   Gate: KiCad DRC 0 violations, 0 unconnected.
4. ARM port build with the toolchain in `~/.platformio` (report 04 `[X1]`). Bench on any RP2040 dev
   board with both panels on jumper wires, against a throwaway OBS.
5. App shell (after the owner installs webkit2gtk-4.1), case print, PCB order, bring-up, CNC.
6. Release 2: NCM spike on the same dev board, then the owner decides the password rule text.

## Top risks and early retirement

1. **Owner rejects "app runs while the pad is used".** Retire at step 1 by asking. Fallback is
   release 2 on the same board, plus a rule change (report 16 Text 1).
2. **The board does not route** (two FPC connectors, 25 GPIO on QFN-56). Retire at step 3, before
   any firmware port. Escape: RP2350B, at the cost of the proven block.
3. **Display tails and controllers.** Contact face (FH12 vs FH12A), NV3007 init, SPI clock. Retire at
   step 4 with bought panels on a dev board before the PCB order (reports 06, 07).
4. **Relay throughput and back-pressure.** A 75 kB scene list over CDC with today's `usb.c` loss
   (report 02). Retire at step 2 with padsim tests that throttle the host side.
5. **Unlicensed sibling code.** Retire at step 1 by asking. Otherwise rewrite the generator (slow).

## Not checked

No hardware. Dual ACM was not compiled for RP2040. The relay latency and the RAM total are
estimates. The pin budget leaves 5 spare GPIO. A sixth panel line, such as a TE pin, eats into it.
