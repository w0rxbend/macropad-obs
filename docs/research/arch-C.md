# Architecture C: the product a careful hardware company would ship

Research and specification only, 2026-11-18. Angle: a robust product in a CNC metal case. Plug it in
and it works. Nothing on the host that a distro update or a firewall can quietly break. More
engineering is acceptable. Facts point to the report that holds the source and tag (`R03` =
`docs/research/03-connectivity.md`, and so on). Three facts were checked for this file and are
marked **verified here**. Nothing was built or run.

## Recommendation

1. **MCU.** RP2350B (QFN-80, stepping A4) with the W25Q128JVSIQ, Pico SDK 2.3, C. No radio. (R04)
2. **Path to OBS: the firmware is the OBS client, the PC only carries bytes.** USB composite device
   with two CDC-ACM ports: port 0 carries configuration, port 1 carries the OBS stream. A small user
   service on the PC, `obs-link`, opens TCP to the host and port in the pad's URL and copies bytes.
   The firmware does the WebSocket upgrade, the authentication, the requests and the events. This is
   option (d2) of R03, promoted to the first choice.
3. **Authentication.** The pad stores the OBS password, write-only, in its own flash sector. The
   relay and the app never see it. They see only the challenge reply. **This needs the rule change
   below.**
4. **Configuration.** Protocol v2 on port 0: one chunked JSON document, `seq` check, two flash
   slots (R13). The pad lists scenes and inputs for the editor, so the app holds no secret (R16
   finding 6).
5. **Firmware update from the app,** into A/B flash partitions with the RP2350 boot ROM's
   try-before-you-buy. The ROM UF2 drive stays as the unbrickable fallback.

Next action: the owner approves the rule text, and the relay reading of "firmware on the device
should be communicating with this websocket OBS url" (see "Owner decisions"). Then run the
dev-board spike in "Build order", step 1.

## Why the relay, and not USB networking or Wi-Fi

The owner wrote "firmware on the device should be communicating with this websocket OBS url". All
three options keep the OBS client in the firmware. They differ in what the host must get right.

| | (C) CDC relay (chosen) | (A) USB CDC-NCM + lwIP | Wi-Fi (ESP32-S3-WROOM-1U) |
| --- | --- | --- | --- |
| Host setup | udev rule + user unit, one package install | udev rule + firewall rule per distro + NetworkManager must bring the link up | Wi-Fi credentials + LAN firewall rule |
| Firewall | none: relay dials `127.0.0.1` | ufw/firewalld rule for the pad's address (R03, verified ufw DROP here) | open 4455 to the LAN |
| OBS on another PC | yes, the relay dials any host the PC reaches | no, needs NAT on the host (R03) | yes |
| Metal case | no effect | no effect | needs an external antenna (R03 `[H1]`) |
| Pad needs a PC process at run time | yes, `obs-link` | no | no |
| Subnet collision, MAC, DHCP server | none | must be designed (R03 open question 5) | LAN does it |
| Firmware network code | none: byte stream over CDC | lwIP + NCM + DHCP server, about 300 lines glue (R03 estimate) | Wi-Fi stack, provisioning |
| USB power | about 310 mA (R10) | same | about 615 mA linear, over 500 mA (R10) |

Reasons for (C):

1. **Fewest host-specific failure points.** NCM depends on NetworkManager behaviour that no report
   observed (R03 "Not checked" 1) and on a firewall rule whose form differs by distro. The relay
   needs only things the pad needs anyway: a udev rule for port access (R13, required today), and
   a user unit.
2. **It starts by itself.** udev can start a user unit when the device appears:
   `ENV{SYSTEMD_USER_WANTS}` "may be used to activate arbitrary units when a specific device becomes
   available" (verified here, `man systemd.device`; systemd's own `99-systemd.rules` uses it for
   `smartcard.target`). So the app need not be open, and no tray or autostart entry is needed.
3. **OBS on another PC works,** which a product must expect. NCM cannot do it without NAT.
4. **The hardware is the same for (A) and (C).** NCM can come later as a firmware-only feature on
   the same board, behind the same byte-stream seam (R03 design item 5). The PCB decision does not
   wait for the spike.
5. **Wi-Fi loses on the case.** A CNC aluminium case blocks a module antenna (R03 `[H1]`), and a
   radio breaks the USB power budget on a linear regulator (R10).

Cost: the pad needs `obs-link` running. If it is not, the strip display says "PC link service not
running" and the app's Device page offers to start it. That is a clear, local, fixable state, not a
silent network failure.

## Firmware

Two layers. The core is C11 with no SDK headers and builds with gcc and ASan in `just test` (R04).

| Module (core) | Job | Source |
| --- | --- | --- |
| `link` | v2 frame codec, CRC-16, pull API, credit-based back-pressure | adapt `firmware/link.c` (R02) |
| `stream` | byte-stream seam: open, send, receive, close; over port 1 frames | new (R03 item 5) |
| `ws` | RFC 6455 client: upgrade, masking, fragments, ping on idle | new |
| `crypto` | SHA-1, SHA-256, base64 | new, test vector in R05 section 3 |
| `json` | streaming reader, capture-then-decide, 9+ levels | LwJSON v1.10.1, MIT (R04 `[X2]`) |
| `obs` | Hello/Identify, mask 1118 (+65536 on demand), one request in flight, close codes 4009/4010/4011, code 207, collection switch | new (R05) |
| `actions` | keys, pages, buttons, knobs to OBS requests | port of `host` `keymap`, `paging`, `volume` with the two bugs fixed (R02) |
| `config` | JSON document codec and validator, the trust boundary | new (R13) |
| `store` | two config slots, credential sector, NOR model in tests | new (R13) |
| `input` | 4x4 matrix debounce; quadrature table for 3 encoders | adapt `firmware/input.c` (R02, R08) |
| `ui` | widget list, band renderer, fonts with Cyrillic | new (R14) |

The port layer (`firmware/port/rp2350/`) holds TinyUSB descriptors (two CDC interfaces, serial
string from the unique id), USB write with back-pressure (fixes R02 risks 1 to 3), SPI DMA for two
panels on two buses (pins allow it, R04), the encoder sampler on PIO or a 1 kHz timer, flash access
through `flash_safe_execute`, and the watchdog. Core 0 runs USB, OBS and input. Core 1 runs the
renderer. TinyUSB ships a two-port CDC example with `CFG_TUD_CDC 2` (verified here,
`lib/tinyusb/examples/device/cdc_dual_ports/src/tusb_config.h:94` in the local SDK 2.3.0).

Robustness a shipped product needs: watchdog with a reset-reason counter in `STATUS`; a boot-loop
guard that falls back to the other firmware partition; defaults compiled from `board.toml` when
both config slots are bad; one display line for every failure state (no OBS, bad password, OBS
too old, PC service missing).

On the host, `padsim` links the whole core behind two pseudo-terminals, one per port. With a stdlib
Python fake OBS (R15) and the real `obs-link`, the full chain runs in `just test` with no hardware.

## Configuration transport and schema

Port 0, protocol v2, as R13 specifies: `id` byte echoed in every reply, `INFO`, `CFG_READ`,
`CFG_BEGIN` with `base_seq`, `CFG_CHUNK`, `CFG_COMMIT`, `RESULT` with the first bad field,
`FACTORY_RESET`, `STATUS`, `INPUT`. Changes to R13:

1. Drop `AUTH_NEED` and `AUTH_SECRET`. Add `SET_CREDENTIAL` (app to pad, write-only) and
   `CLEAR_CREDENTIALS`. `INFO` and the document show only `obs_password_set: true|false`.
2. Add `OBS_LIST` (scenes, inputs, transitions; the pad answers in chunks from its own session),
   so the app needs no `obws` and no keyring.
3. Add `FW_BEGIN`, `FW_CHUNK`, `FW_COMMIT` for updates.
4. Text in frames and in the document is UTF-8, not printable ASCII (R05 section 10).

Port 1 uses the same frame codec with `STREAM_OPEN host port`, `STREAM_DATA`, `STREAM_CREDIT`,
`STREAM_CLOSE reason`. One codec, one vectors file, the four-file rule applies to both ports.

The schema is R13's document (`schema`, `seq`, `obs.url`, `keys`, `buttons`, `knobs`, `pages`,
`main_display`, `strip_display`, `ui`), minus `obs.auth` and `net`. Scenes and inputs are stored by
UUID with a label; obs-websocket 5.4.0 is the floor (R05). Cap 16 KiB.

## Rule change needed

`CLAUDE.md` says "No OBS password in a CDC frame." This design breaks its letter in one frame.
Replace it with R16 Text 1, unchanged:

> The OBS password and any Wi-Fi passphrase cross the CDC link only in `SET_CREDENTIAL`, app to
> device. No device-to-host frame, log line, display, readback or test vector carries a secret or a
> value derived from one. The device stores secrets in their own flash sector and erases it on
> `CLEAR_CREDENTIALS`, on the clear key combination, and before a host-requested BOOTSEL.

Add one sentence for the update path: "An update image without a valid project signature erases
the credential sector before it boots." Without it, any user process could push firmware that reads
the password. With it, official releases keep the password and test builds cost one re-entry.

The relay adds no secret on the wire: it forwards only `base64(sha256(secret + challenge))`, which
is bound to one connection (R05 section 3). Use the random 16-character password OBS generates
(R16 finding 4).

## What runs on the PC

1. **`obs-link`**: a Rust binary with no GUI, about 200 lines (estimate). A systemd user unit,
   started by udev per pad. It dials only what the pad asks for and refuses public addresses unless
   the owner allows them. It logs connect and close, never payload.
2. **The Tauri app**: configuration only. Rust core with no Tauri, thin Tauri 2 shell, no-build UI,
   as in `macropad-greycode/configurator` (R13). Pages: Pad, Displays (exact preview from the
   firmware's `ui` core built with `cc`), OBS (URL, password write, test from the pad), Device
   (version, update, factory reset, export and import). Closed in normal use.
3. **One package** installs both, the udev rule (`uaccess`, `ID_MM_DEVICE_IGNORE`, per-serial
   symlink, `SYSTEMD_USER_WANTS`) and the user unit. That is the only root step.

## Storage and firmware update

W25Q128JVSIQ, 16 MB, laid out by an RP2350 partition table: two firmware partitions (A/B), two 16
KiB config slots with headers programmed last (R13), one credential sector, one font and asset
region. The boot ROM has `pick_ab_partition` and `explicit_buy` (verified here,
`pico/bootrom.h:51,60` in the local SDK). An update writes the inactive partition over port 0,
checks a SHA-256 and the signature, and reboots on trial. The new image calls `explicit_buy` only
after USB enumerates and the config loads. Otherwise the ROM boots the old image. Holding BOOTSEL
still gives the ROM UF2 drive. Secure boot stays off for the prototype; the A4 stepping keeps it
possible for a CNC unit (R16).

## Reuse from this repo

Keep: `board.toml` as source of truth plus `check_pins.py` (add a duplicate-GPIO check), the frame
codec and shared vectors, debounce and quadrature, the C test harness, `config.rs` URL parsing and
atomic save, the `Secret` type and `logbuf.rs`, `cad/obs_case/export.py` read-back. Replace:
display path, `usb.c`, `main.c`, `session.rs` and the UI, the PCB generator (port greycode's, R01,
R09), the case geometry (R11). Delete `.grok/workflows/` once the owner agrees (R02).

## Build order

1. **Spike, one week, Pimoroni Pico Plus 2 (RP2350B) plus display breakouts.** Two CDC ports, a
   prototype `obs-link`, the WebSocket handshake to a throwaway real OBS, and udev starting the user
   unit. Bench both panels for read-ID, SPI clock and the tail's contact face.
2. **Contracts.** New `board.toml`, protocol v2 for both ports in the four files, config vectors,
   rule text in `CLAUDE.md`.
3. **Core on the host, test first.** `link`, `stream`, `crypto`, `ws`, `json`, `obs` against the fake
   OBS; then `config`, `store` with power-cut tests, `actions`, `input`, `ui` with golden frames.
   `padsim`, `obs-link` and the app core join `just test`.
4. **PCB.** Placement-only spike with QFN-80, both FPC connectors and the matrix; then locked
   critical copper plus Freerouting, DRC in Docker (R09).
5. **Case and hardware.** Printed case from the same build123d source, boards ordered, bring-up per
   R15's checklist, then the CNC and laser files (R11, R12).

## Top risks and how each is retired early

| Risk | Retired by |
| --- | --- |
| Display parts: tail contact face, 40-pin connector, NV3007 retail part and clock unknown (R06, R07) | Buy both panels and breakouts first; bench them in spike step 1, before the connector footprint |
| QFN-80 and 40-pin FPC escape do not route (R09) | Placement-only spike in build step 4, before any other PCB work |
| udev does not start the user unit in some sessions | Spike step 1. Fallback: the app starts `obs-link`, and an XDG autostart entry |
| Unbounded OBS messages break the parser or RAM (R05 section 6) | Fuzz `json` and `obs` under ASan with 500-scene and 500-input fixtures; one live-OBS run in the spike |
| ESD into a metal case, metal knobs and FPC lines | Bond the case to USB shield ground, TVS on exposed lines, IEC 61000-4-2 test on the printed prototype with a foil-lined case (likely; values unverified) |

## Owner decisions

1. Rule Text 1 plus the signed-update sentence, or keep the rule and accept the app at every OBS
   start (R05 option A)?
2. Is a PC service that forwards bytes an acceptable reading of "firmware on the device should be
   communicating with this websocket OBS url"? If not, design (A) on the same board, with one sudo
   firewall step.
3. May sibling code be copied under MIT and CERN-OHL-S-2.0 (R01)?
4. May the locked LCSC list drop C2040 and C596730, since neither part is used here (R04, R06)?

## Not checked

No hardware, no build of this design, no live OBS. `SYSTEMD_USER_WANTS` for a tty with `uaccess` was
read in the man page, not run. The `obs-link` and firmware line counts are estimates. The ESD
values are not from a datasheet.
