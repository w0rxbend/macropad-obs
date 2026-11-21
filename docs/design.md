# macropad-obs design

The design as built, 2026-11-20. The contract is `docs/spec/spec-v2.md` (approved 2026-11-18) with
the owner's answers in `docs/spec/decisions-v2.md`, which win where they differ. This page says what
the tree holds today and where each fact comes from. Sizes that come from no datasheet stay MEASURE.
No hardware exists: nothing here has been built as a board, printed, milled or flashed onto a chip.

The v1 design (a USB-only pad with a PC bridge) is retired; git history keeps it.

## What it is

An OBS Studio control pad (spec 1, spec 2):

- a 3.5 inch 320x480 panel (Focus E35GH-I-RW300-N, ST7796U) and a 2.79 inch 142x428 strip
  (Wisevision N279, NV3007, by quote: D4);
- 9 MX keys in Kailh hot-swap sockets on a 4x4 diode matrix, 4 Omron B3F-1060 buttons, 3 Alps
  EC11E18244AU push encoders (spec 6);
- an ESP32-S3-WROOM-1-N16R2 module that joins Wi-Fi and is the obs-websocket 5 client itself
  (D1 = W, D7);
- one USB-C cable (GCT USB4216-03-A) for power and for configuration from a Linux Tauri app
  (spec 1 item 4, "USB-C" decision).

Body 97.4 x 173.5 mm, PCB 91.6 x 167.7 mm, 4 layers (spec 7; `board.toml` `[body]`, `[pcb]`). The
top view keeps the sketch's order: big panel top left, strip top right, keys under the big panel,
buttons under the keys, knobs under the strip (spec 2 row 16; `docs/spec/layout-v2.toml`,
`docs/images/layout-v2.png`).

## Sources of truth

| Fact | Lives in | Checked by |
| --- | --- | --- |
| Pins, mechanics, power cap | `board.toml` | `tools/check_pins.py` binds `firmware/esp32s3/main/pins.h` and `host/obs_core/src/protocol.rs` to it (`CLAUDE.md`) |
| Layout geometry | `docs/spec/layout-v2.toml` feeds `board.toml` | `tools/check_numbers.py` (`board.toml` header) |
| Board-order gate | the MEASURE tags on gated `board.toml` entries | `tools/check_measure.py` via `just gate` (spec 9 step 6) |
| CDC frames | `docs/protocol.md` | the four protocol files change together (R3, `CLAUDE.md`); `firmware/test/vectors.txt` in C and Rust |
| Config document | `docs/config.md` | the four config files change together (R3); `firmware/test/config_vectors/` in C and Rust |
| Flash layout | `firmware/esp32s3/partitions.csv` | `tools/check_partitions.py`, and against the built table in `just firmware` |

## System

```
OBS (ws://<LAN IPv4>:4455) <-- TCP over 2.4 GHz Wi-Fi --> pad (ESP32-S3)
pad <-- USB CDC frames (docs/protocol.md) --> Tauri app: config, URL, SSID, secrets, firmware
```

Source: spec 5. At run time no PC process sits between the pad and OBS (D1). The app is needed only
to configure the pad.

## Firmware

Two layers (spec 5, spec 10):

- **Core**, `firmware/core/`: C11, no ESP-IDF header, no heap after init, every fallible call returns
  a checked status. `just test` builds each module with gcc `-Wall -Wextra -Werror
  -fsanitize=address,undefined` and runs its test (justfile `test-firmware`).
- **Port**, `firmware/esp32s3/`: ESP-IDF v6.1.1 in Docker (`espressif/idf:v6.1.1`, approved in
  G-docker). The core links as the `fw_core` component (`firmware/esp32s3/components/fw_core/`).

| Core module | File | Role |
| --- | --- | --- |
| link | `firmware/core/link.c`, `link_tx.c` | v2 frame codec, pull feed, no frame dropped silently (spec 8.1) |
| device | `firmware/core/device.c` | the CDC request handlers: `INFO`, config flow, credentials, `OBS_LIST`, reset and bootloader |
| config | `firmware/core/config.c` | document validator (`docs/config.md`) |
| store | `firmware/core/store.c` | two raw slots `cfg_a`/`cfg_b`, header last; a power cut leaves the old or the new document (criterion 5, NOR model `firmware/test/nor_model.c`) |
| wifi | `firmware/core/wifi.c` | station state machine and strip lines (`docs/obs.md`) |
| crypto, ws, json | `firmware/core/crypto.c`, `ws.c`, `json.c` | SHA-1, SHA-256, base64; RFC 6455 client; streaming JSON on LwJSON v1.10.1 (G-deps) |
| obs, obs_state | `firmware/core/obs.c`, `obs_state.c` | obs-websocket 5 client (`docs/obs.md`) |
| input | `firmware/core/input.c` | matrix debounce, quadrature decode, the clear key combination |
| actions | `firmware/core/actions.c` | inputs to OBS requests (`docs/obs.md`) |
| ui, render, panels | `firmware/core/ui.c`, `render.c`, `panels.c` | widget model, band renderer with 4 bpp Noto fonts, both panels' init tables as data |

| Port file | Role |
| --- | --- |
| `firmware/esp32s3/main/main.c` | one app task on core 1, task watchdog 10 s, power cap, boot log (task 4.7 status) |
| `firmware/esp32s3/main/usb_port.c`, `boot_dl.c` | one CDC-ACM port on esp_tinyusb; `BOOTLOADER` into ROM download after the `cred` erase (spec 8.2) |
| `firmware/esp32s3/main/wifi_port.c`, `stream_lwip.c` | `esp_wifi` STA with `WIFI_STORAGE_RAM`; lwIP socket stream (spec 10) |
| `firmware/esp32s3/main/cred_nvs.c`, `store_flash.c` | plain NVS `cred` partition; raw config slots |
| `firmware/esp32s3/main/input_port.c` | matrix scan on a 1 ms timer; PCNT units 0-2 for the encoders |
| `firmware/esp32s3/main/lcd_port.c`, `backlight.c` | two `esp_lcd` SPI IO handles on SPI2; LEDC backlights |
| `firmware/esp32s3/main/power.c`, `settings.c`, `cc_sense.c` | backlight cap and the CC 1.5 A lift; SSID, URL and brightness from the document |

`just firmware` builds the merged image `.build/esp32s3/macropad-obs-merged.bin` (bootloader at 0x0,
table at 0x8000, app at 0x10000; justfile). The 2026-11-20 build: image 1,040,608 bytes, DIRAM
93,058 bytes free (`idf.py size` output of that run).

Partitions (`firmware/esp32s3/partitions.csv`, spec 10): `nvs` (IDF default, no secret), `factory`
app 4 MB, `cred` (plain NVS, secrets only, erased whole), `cfg_a` and `cfg_b` (raw, 64 KB each).

**padsim** (`firmware/padsim/`) runs the whole core on the PC: CDC on a pty, OBS over TCP to
`tools/fake_obs.py`, flash in a file, panels as RGB565 dumps. The host tests drive it end to end:
criteria 4 and 4c in `host/obs_core/tests/padsim_e2e.rs`, 5, 8 and 9 in
`host/obs_core/tests/padsim_faults.rs`, 4b in `host/app_core/tests/criterion_4b.rs`, and the
host side of 12 in `host/app_core/tests/padsim_provision.rs`.

Provisional values in the port, each MEASURE or pending:

- SPI clock 13.3 MHz (80 MHz / 6) until the S.3 bench (task 4.6 status; criterion 7). Pending S.3.
- Panel init tables unverified on glass (`lcd_port.c` warns at boot). Pending S.3.
- Backlight cap 600 permille, from report 18 arithmetic, not a measured current (`board.toml`
  `[power]`, MEASURE). Pending S.3, H.8.
- Matrix row settle 30 µs and the encoder clockwise sign (task 4.5 status, MEASURE). Pending 4.8.

## Host and app

| Part | Path | State |
| --- | --- | --- |
| `obs_core` | `host/obs_core/` | v2 codec and document types, same vectors as the C side; `Secret` for the password and Wi-Fi key (spec 10) |
| `app_core` | `host/app_core/` | the app without a window: find the pad, read and write the document, provision secrets, preview the panels with the firmware's own C renderer, firmware update with `espflash` as a library (`host/app_core/src/lib.rs`) |
| Tauri shell | `app/src-tauri/` | builds (`just app`, `just app-check`); twenty commands in `app/src-tauri/src/commands.rs`, registered in `app/src-tauri/src/main.rs`, each one call into `app_core` (tasks 3.6 to 3.8) |
| UI | `app/ui/` | no-build ES modules, rules in `host/app_core/src/forms.rs`: the mapping editor (`mapping.js`, task 3.7); the layout editor with the preview (`display.js`), the SSID with the write-only passphrase and password (`wifi.js`), and the update from `just firmware`'s image (`update.js`, task 3.8) |
| udev | `app/udev/70-macropad-obs.rules` | app port 1209:4f42 and ROM port 303a:1001, `TAG+="uaccess"` |

VID `0x1209` PID `0x4F42` is not registered with pid.codes (README).

## Security

Source: spec 12, D2, D8, rule R1 in `CLAUDE.md`.

- The OBS password and the Wi-Fi passphrase cross USB only in `SET_CREDENTIAL`, app to pad. No
  pad-to-app frame, log line, display, readback or test vector carries a secret or a value derived
  from one. `INFO` carries only `obs_password_set` and `wifi_psk_set` (`docs/protocol.md`).
- The pad keeps them in plain text in the `cred` partition (D8: no eFuse burn, no flash encryption,
  no secure boot). Anyone who holds the pad can read them with esptool in ROM download. The owner's
  mitigation: a password used only for this OBS, a guest SSID if wanted (spec 12).
- `cred` is erased whole on `CLEAR_CREDENTIALS`, `FACTORY_RESET`, the clear key combination (B1 + B4
  held 5 s from power-on) and before `BOOTLOADER` (spec 8.2).
- The Wi-Fi driver keeps the PSK in RAM only: `esp_wifi_set_storage(WIFI_STORAGE_RAM)` before
  `esp_wifi_set_config` (spec 10; `firmware/esp32s3/main/wifi_port.c`).
- Plain `ws://` on the LAN; no TLS on the pad (spec 12 "Never").

Not proven without hardware: the raw dumps of `nvs` and `cred` and the UART log holding no secret
(pending 4.8).

## PCB

Source: `pcb/gen/`, justfile `pcb`, tasks 5.1 to 5.12.

- Generated from code: greycode's generator, copied under CERN-OHL-S-2.0 (D5), reads `board.toml`.
  KiCad 9.0.9 in Docker for ERC, placement, critical copper and DRC; Freerouting 2.5.0 fetched by
  sha256 routes the free nets; KiCad 10.0.7-full exports the board STEP.
- 4 copper layers, inner GND and power planes (spec 2 row 1).
- The 2026-11-20 run of `just pcb`: ERC clean; routed DRC at error severity 0 violations,
  0 unconnected, 0 parity, 4 copper layers; the fab set is byte-repeatable with 48 BOM findings
  (unverified LCSC numbers, no MPN) listed.
- Provisional: both FPC footprints (J3, J4) are `PLACEHOLDER_*` until the panels are calipered, so
  the fab set and the STEP land in ignored `pcb/.build/`; the committed fab set (pcb/fab, not
  written yet) waits for task 5.12. Pending
  S.3, 5.3b, 5.12.
- LCSC cells stay `UNVERIFIED` (rule R2). No SK6812 (`CLAUDE.md`).
- Not orderable: `just gate` exits 1 with 18 open MEASURE tags (FPC centres, tail slot, carrier
  heights, knob bore, USB overhang, module stack, antenna feed side, regulator height and others).

## Case

Source: `cad/build.py`, `cad/obs_case/`, tasks 6.1 to 6.10.

- One build123d 0.13.0 source (`cad/.venv`), style A: flat slab, chamfered edges, bead blast, black
  anodise, laser-engraved ticks (D3). Two variants, `print` and `cnc`.
- A non-metal back-wall insert at x 56.0 to 87.6 is the window for the module's PCB antenna (D7;
  spec 7). Espressif's 15 mm clearance to the housing is not met (deck about 7.6 mm above, walls 4.6
  and 9.0 aside, spec 7 arithmetic); RF through the insert is unproven. Pending S.3, H.10, H.11.
- Exports in `cad/exports/`: STEP, BREP, IGES, STL, 3MF, GLB, DXF, SVG, PDF, each read back by
  `just cad`. The FCStd is not built: it needs FreeCAD, not approved (`cad/build.py` `fcstd`).
- `just cad fit` checks the case against the board STEP: 0 problems on the 2026-11-20 run; DSA
  keycap seat not checked (MEASURE).
- Display stack: panel face at z 5.6, foam 0.5 mm squeezed to 0.4, carrier heights from a calipered
  panel (spec 7 revision 3; `board.toml` `[stack]`, `[display_carrier]`, MEASURE).
- Fastening (`board.toml` `[screws]`, `cad/obs_case/screws.py`; open question 3 answered M2): six
  ISO 10642 M2 x 12 countersunk screws from below, through the plate, the standoffs and the PCB,
  into 5.0 mm bosses that hang from the deck and clamp the board. Each boss joins its nearest walls
  with R 1.2 fillets. The cnc shell is tapped M2 x 4.0 (drill 1.6 x 5.0); the print shell takes an
  M2 x 3.0 heat-set insert in a 3.2 x 4.0 pocket (MEASURE on the `insert-boss` coupon). The boss
  wall round the tap drill is 1.7 mm, a named thin wall: the boss cannot grow past the PCB hole
  keep-out it lands on.

## Not proven until hardware

From spec 14, still open on 2026-11-20: Wi-Fi range through the insert, the ROM port after
`BOOTLOADER`, two `esp_lcd` IO handles on one SPI host, IDF RAM at run time, SPI above 15 MHz,
backlight and CPU currents, encoders, matrix settle, buck heat, case air, laser marks, and every
MEASURE. Bring-up is `docs/bringup.md`; results go to the hardware record of Phase 8
(`tasks/todo.md`).
