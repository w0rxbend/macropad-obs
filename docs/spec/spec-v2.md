# Spec v2: macropad-obs rebuild

**Approved by the owner, 2026-11-18** (`docs/spec/decisions-v2.md`, "Spec": plan and build).
Revision 2026-11-18, both rounds of answers applied. `R03` = `docs/research/03-connectivity.md`,
`R18` = `docs/research/18-esp32s3-wifi-delta.md`, `G1` = `docs/research/gap-1.md`, etc. Facts keep
their tags; non-datasheet sizes are MEASURE. Scope: R1 = release 1, [later] = option to trim.

Next action: the owner does D6; spike step 1 and `contracts` start.

## 1. Objective

1. Build an OBS Studio control pad that matches the owner's sketch (`docs/images/sketch.jpg`).
2. It has a 3.5 inch display, a tall narrow display, 3x3 MX keys, 4 small tact buttons, 3 push encoders.
3. The firmware is the obs-websocket 5 client. An ESP32-S3 module dials OBS over Wi-Fi and holds
   the session, requests and events itself. No PC process runs at run time (D1 = W).
4. A Linux Tauri app reads, edits and writes back the config over USB: URL, SSID, secrets (write).
5. The board is 4-layer and routed; the case prints first, then is milled and laser-marked.

## 2. Requirement trace

| # | Owner's words or answer | How the design meets it |
| --- | --- | --- |
| 1 | "4layers or more PCB" | 4-layer 1.6 mm, inner GND and power planes, signals on F.Cu and B.Cu, routed from code, KiCad DRC (R09, R10). Criterion 10 |
| 2 | "3x3 keys matrics, MX switches" | 9 five-pin MX switches in Kailh CPG151101S11-1 hot-swap sockets, 19.05 mm pitch, on a 4x4 diode matrix (R08) |
| 3 | "2 displays one bigger and one longer" | Big: Focus E35GH-I-RW300-N, 3.5 in 320x480 (R06). Long: Wisevision N279, 2.79 in 142x428 strip (R07); by quote (D4) |
| 4 | Big display 3.2 to 3.5 in, about 57 mm wide | 3.5 in, module 54.46 mm wide against a 57.15 mm key block (R06, verified) |
| 5 | Narrow display shows the three knobs: source name, level, mute | Strip layout, one row per knob: name, level bar and dB, mute (R14). Criterion 6 |
| 6 | "one tray of buttons", 6x6 tactile, round black plunger in the picture, small; 4 buttons | 4 Omron B3F-1060 (round black plunger, 7.0 mm) at 12.7 mm pitch under the keys (R08). Plunger confirm: section 15 |
| 7 | Three round controls are rotary knobs with push | 3 Alps EC11E18244AU, pushes in the matrix, A/B on 6 filtered GPIO counted by PCNT (R08, R18) |
| 8 | "all the export format for 3d cad case" | Case: STEP AP214 (master), AP242, BREP, IGES, STL, 3MF, GLB, DXF, SVG, PDF, FCStd. Plus the assembled PCB STEP and part envelopes for the owner's own CAD. All read back (R11, R09). Criterion 11 |
| 9 | "prototype that will be printed and then CNC, and laser engraving to be stalish" | One build123d source, `print` and `cnc` variants; laser legend sheets DXF/SVG/PDF with a check; style A (D3; R11, R12, R17) |
| 10 | "linux tauri application that can configure this device" | Tauri 2 shell over a Tauri-free Rust core (R13). Builds and opens on this machine after D6. Criterion 13 |
| 11 | "to pass websocket url" | `obs.url` (LAN `ws://` IPv4) in the config document, written with `CFG_BEGIN/CHUNK/COMMIT`. Criteria 4, 13 |
| 11b | "and firmware" (second reading: the app updates the firmware) | `app` sends `BOOTLOADER`, the pad enters ROM download, the app's `espflash` library writes the image (R18 section 8). Criterion 14 |
| 12 | "firmware on the device should be communicating with this websocket OBS url" | Met in full (D1 = W). The firmware joins Wi-Fi, opens TCP to the URL, does the upgrade, auth, Identify, requests and events. No PC process in the path |
| 13 | "bidirectional configuration" | `CFG_READ` returns the whole document; the app edits it and writes it back with a `seq` check (R13). Criteria 4, 13 |
| 14 | "mapping buttons" | 9 keys, 4 buttons, 3 knobs (turn and push) map to OBS actions by UUID plus label. Criterion 4c |
| 15 | "configuring the outputs on the displays" | Two widget layouts in the document, previewed by the firmware's own C renderer (R13, R14). Criterion 4b |
| 16 | Sketch order: big top left, narrow top right, keys under big, button row under keys, knobs under narrow | `docs/spec/layout-v2.toml` keeps that order; approved (D3) |

## 3. Decisions taken

Source: `docs/spec/decisions-v2.md` (owner, 2026-11-18, final).

| Id | Answer | What it fixes in this spec |
| --- | --- | --- |
| D1 | **W: Wi-Fi.** ESP32-S3 module, external antenna; the firmware dials OBS itself | ESP32-S3 module (WROOM-1-N16R2 by D7), buck, Wi-Fi provisioning (R18). `obs-link`, NCM and the RP2350B are gone |
| D2 | **The pad stores the OBS password**, write-only | Rule R1 (section 12). R1-alt and `relay_answer` are dropped |
| D3 | **`layout-v2` and style A approved**: flat slab, chamfered edges, bead blast, black anodise, laser-engraved ticks | `layout-v2.toml` rev 2c, `docs/images/layout-v2.png`. Body 97.4 x 173.5 mm |
| D4 | Not asked; default taken: Wisevision N279 by quote | Spike kit below |
| D5 | **Reuse and Freerouting allowed** | Copy the greycode PCB generator and `MX_Hotswap`, the nyxilab 3MF/GLB/FCStd exporters, the macropad coupons, CNC drawings and laser DXF, relicensed MIT (code) and CERN-OHL-S-2.0 (`pcb/`, `cad/`). Freerouting 2.5.0 fetched by sha256, never committed |
| D7 | **Non-metal back-wall insert**, internal antenna behind it, own clearance check | WROOM-1-N16R2 PCB antenna at the back edge, board cut, insert (sections 6, 7, 14) |
| D8 | **No eFuse burn**: OBS password and Wi-Fi key in plain NVS, readable with esptool; D2 stands | `cred` is plain NVS; the `no_store` path is gone; threat stated in section 12 |
| USB-C | **Socket with SMT shell tabs** | GCT USB4216-03-A (section 6, 7) |
| Spec | **Approved: plan and build** | This revision |

Spike kit (D4 default, about USD 100, unverified): an ESP32-S3-DevKitC-1 with the PCB antenna (variant
unverified; R18 `[E7]` read the -1U), a printed slab mock-up with the insert, one E35GH-I-RW300-N (USD
40.35, R06), FPC breakouts, one N279 by quote (MOQ 1). Then 5 JLCPCB boards, Standard PCBA, SMT
bottom, TH by hand: USD 230 to 340; one 6061 case: USD 130 to 380 (R12, no live quote).

Still open:

- **D6. Install, owner action, once.** `sudo pacman -S --needed webkit2gtk-4.1 xdotool` (142 MiB;
  https://v2.tauri.app/start/prerequisites/, verified in G2); the udev rule (`ttyACM*` plus ROM port
  303a:1001, likely, R18); one ufw rule for the LAN subnet, which covers OBS, the throwaway OBS and
  the spike's DevKitC: `sudo ufw allow proto tcp from <LAN-subnet> to any port 4455,4456` (forms in
  `man ufw`, verified; input DROP, R03 `[L1]` verified). Before D6 the app is proven by `just
  app-check` and padsim.

## 4. Assumptions

1. "3x3 keys matrics" is a 3x3 grid on a 4x4 diode matrix; hot-swap sockets are wanted (R08).
2. A 2.4 GHz WPA2/WPA3-personal network reaches the pad; the S3 has no 5 GHz (R03 `[H2]`, verified).
3. OBS is 30.1 or later (obs-websocket 5.4.0, the first with UUIDs) (R05).
4. Scene and input names are UTF-8. Strip `level` is the fader dB; live meters are opt-in (R05, R14).
5. Not a USB keyboard (HID [later]); ROM download updates over USB (A/B and OTA [later]); BOOT and
   RESET buttons stay; physical access is outside the threat model: the holder reads the secrets (D8).
6. "pass websocket url and firmware" has two readings: firmware that talks to the URL (row 12), or
   the app also flashing firmware (row 11b). Both are built.
7. 9 keys are enough: key pages are [later] unless the owner says otherwise (section 15).
8. OBS listens on the LAN at a stable private IPv4, and the pad has a DHCP reservation (section 15).

## 5. Recommended architecture

ESP32-S3 on Wi-Fi (D1 = W, R18). Kept: ROM-mode updates, spike and panel bench first, URL rules,
GPIO check, TE and UART pins, ESD bonding, watchdog, one strip line per failure.

```
 OBS (ws://<LAN IPv4>:4455) <-TCP over Wi-Fi (2.4 GHz, PCB antenna behind the insert)-+
 Pad ESP32-S3-WROOM-1: esp_wifi STA | lwIP sockets | TinyUSB one CDC | SPI2 one bus, 2 CS
   | PCNT x3 | LEDC x2 | plain NVS `cred` | raw `cfg_a`/`cfg_b` | watchdog
   core C11, host-tested: wifi -> stream -> ws -> obs -> actions <- input (4x4 matrix, 3 encoders)
                          link -> config <-> store (2 slots) ; link -> credentials (write-only)
                          obs state + config -> ui -> big panel (ST7796U), strip (NV3007)
 Tauri app (config, URL, SSID, secrets, espflash) <-CDC frames- one USB-C cable (power + config)
```

The core has no ESP-IDF headers; `stream` opens a TCP socket (lwIP on the pad, POSIX in padsim).

## 6. Parts

LCSC numbers stay UNVERIFIED (rule R2). Status is for facts, not stock.

| Part | Role | Status |
| --- | --- | --- |
| ESP32-S3-WROOM-1-N16R2, 18.0 x 25.5 x 3.1 mm | MCU + Wi-Fi, 16 MB flash, 2 MB quad PSRAM, on-module PCB antenna, -40 to 85 °C; same pins as the 1U | verified (WROOM-1/1U datasheet v1.8 table 1-1, fig 3-1, 10-1; read 2026-11-18) |
| TI TLV62569DBV, 2.2 µH, 4.7 µF in, 10 µF out, 22 µF + 0.1 µF at the module | 3.3 V buck, 2 A | verified (R10 `[P2]`); inductor part unverified |
| BCR421UW6 x2 on 5 V | backlight sinks 120/100 mA | likely (R10) |
| GCT USB4216-03-A (16 pin, 4 SMT shell tabs, 2 x 0.65 pegs, 8.94 x 6.50 x 3.16); TPD2E2U06 or USBLC6-2SC6; PPTC about 0.75 A hold | USB-C (5.1 k per CC), ESD, fuse | USB4216 verified (GCT drawing rev A2, 2025-07-28, https://gct.co/Files/Drawings/USB4216.pdf); TI verified; ST likely; fuse unverified |
| Back-wall insert, black PC or POM, x 56.0 to 87.6, full wall height, floor tongue | non-metal window for the PCB antenna (D7) | design; material, fixing and fit MEASURE in `cad` |
| Focus E35GH-I-RW300-N | big panel, 3.5 in 320x480 IPS, ST7796U, 40-pin 0.5 mm, 54.46 x 82.94 x 2.15 | verified; tail offset and contact face MEASURE (R06) |
| Wisevision N279-1428KIWIG01-C10 | strip, 2.79 in 142x428 IPS, NV3007, 10-pin 0.5 mm, 24.38 x 69.43 x 2.1 | drawing verified; supply by quote (R07) |
| Hirose FH12-40S-0.5SH(55) and FH12-10S-0.5SH(55) class | FPC connectors, bottom face | unverified (Hirose 403); FH12 vs FH12A MEASURE |
| MX 5-pin switches in Kailh CPG151101S11-1, 9 off | keys, 14.0 mm plate hole | socket likely; hole verified; coupon MEASURE (R08) |
| Omron B3F-1060, 4 off (B3F-1050 square stem as alternate) | small buttons, 6x6 TH, round 3.5 mm plunger top, 7.0 mm high | verified (R08) |
| Alps EC11E18244AU, 3 off | push encoders, 2 edges per detent | verified (R08) |
| BAT54 SOD-123 x16, 4.7 k pull-ups; 3.3 k/10 k/10 nF x6 | matrix diodes; encoder RC filter | verified (R08, R10); RC values arithmetic |
| JST SM03B-SRSS-TB | debug UART0 (IO43/IO44), 499 Ω series | verified JST (R10); height not checked |
| DSA keycaps, acrylic lenses 1.0 mm, 0.5 mm black foam | caps, lenses, foam frames | unverified; foam part not picked |

Removed with the RP2350B: W25Q128JVSIQ, 12 MHz crystal, core inductor, SWD, AP2112K (614 mA from
VBUS at TX peak, R18 section 4). Removed by D7: RP-SMA jack, U.FL pigtail, dipole, U.FL plate pocket.
B3F-1060 cap: press-on printed cap or machined floating cap with a
flange under the deck (R08 item 4; fit MEASURE). Rejected: SK6812 (repo rule), 20-pin FH12 C596730
(no tail fits), WROOM-1U-N16R8 for the board (65 °C limit, takes IO35-37), WROOM-1U-N16R2 (its U.FL
antenna needs a wall hole, D7), GCT USB4105 and HRO TYPE-C-31-M-12 (TH shell stakes under the carrier).

## 7. Layout, stack and pin budget

Geometry: `docs/spec/layout-v2.toml` rev 2c, `docs/images/layout-v2.png` (approved, D3). Body 97.4 x
173.5, PCB 91.6 x 167.7, 6 holes (M2 from `board.toml`; M2 vs M2.5 open, section 15), FPC connectors
on the bottom face. The top view keeps the sketch's order; the drawing shows the bottom-face parts
dashed, the antenna board cut and the insert.

**Rev 2c (D7, USB-C):** `[mcu]` WROOM-1-N16R2 [60.6, 142.2, 18.0, 25.5], bottom face, antenna end
flush with the back edge; 3.1 tall in the 4.0 gap, no plate pocket. `[antenna]` keep-out from the
ESP32-S3 Hardware Design Guidelines, figure "Keepout Zone for ESP32-S3 Module's Antenna"
(https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html,
read 2026-11-18, verified): 6 mm antenna area at the board edge, no board under it, at most 2 of
board beyond the feed side, at least 15 clear beyond the far side. Board cut [58.6, 161.7, 33.0,
6.0] runs off the right edge; webs 0.28 behind the narrow carrier, 0.60 beside the big one; the
(88.3, 166) hole goes. On the bottom face the module is mirrored, so the feed is on the left in the
top view (MEASURE against the footprint). Insert [56.0, 168.1, 31.6, 2.5], full wall height, with a
tongue in the plate's `antenna_relief` [58.6, 161.7, 33.4, 6.4]. The guide also asks "at least 15
mm" to the housing "in all directions"; here (arithmetic) the deck is about 7.6 above, metal wall
4.6 left and 9.0 right, the narrow panel 0.4 ahead: not met (section 14). `[usb]` GCT USB4216: four
SMT shell pads, the rear pair at y 162.68 on the bottom face under the big carrier (allowed, no
slot); 0.65 pegs at y 163.30, 0.63 clear of the carrier; shell 1.0 past the PCB edge (MEASURE).
`[regulator]` zone [24.0, 148.0, 12.0, 8.0]. `swd` becomes `debug_uart`, at (16.0, 155.3).

**Revision 3 (in `contracts`, before CAD):** add `[stack]`, `[foam_frame]`, `[display_carrier]`,
`[pcb] top_keepout` (text in G5). z above the PCB top face: deck_top 8.0; lens_top 7.93;
lens_recess_floor 6.8; deck_underside 6.0; **panel_face 5.6** (R11's 5.5 gives 0 % foam squeeze);
mx_plate_top 5.0, ec11_body_top 4.5, b3f_body_top 3.4 (datasheets); pocket_skirt_bottom 2.0;
pcb_bottom -1.6; bottom_plate_inside -5.6 (MEASURE).

- **Foam frame:** 0.5 mm, installed 0.4 (20 % squeeze; Rogers: above 25 % speeds relaxation, G5).
  Outer edge = module outline, inner = lens opening. Narrow far-edge strip 1.00 mm (MEASURE).
- **Display carriers:** printed rings on the PCB top face, clearance 0.15, wall 2.0. Big outer
  [3.30, 79.15, 54.70, 83.20], height 3.45. Narrow outer [63.66, 91.69, 24.68, 69.73], height 3.50.
  Height = panel_face - calipered panel (MEASURE; narrow 2.1 +/- 0.1 swings squeeze 0 to 40 %).
- **Top-face keep-out:** under each carrier, no part, THT lead, hole, hole keep-out, slot or test
  pad; within 1.0 mm outside each pocket, top parts under 2.0 mm. Met now by the USB4216 SMT shell.

These tables replace `board.toml` `[pcb]`, `[case]` (with `[body]`, `[stack]`, `[foam_frame]`,
`[display_carrier]`, `[window]`, `[bottom_plate]`), `[display]`, `[keys]`, `[knob]`, and add
`[mcu]`, `[antenna]`, `[regulator]`. `[ui_mirror]` legend cells (x 0, 83, 166, 249, w 71) are
current. The back-left drill leaves a 0.6 mm web; JLCPCB gives no PTH/NPTH-to-edge minimum (read
2026-11-18): move them in or get a written OK (section 9 gate).

**Pin budget** (36 GPIO pads, IO0-21 and IO35-48; R18 section 2 from `[E1]` `[E2]`, verified):

| Pins | Net | Note |
| --- | --- | --- |
| IO0, EN | BOOT, RESET | buttons to GND under the plate pinholes; 10 k pull-up; EN 10 k / 1 µF |
| IO19, IO20 | USB D-, D+ | native USB, 22 Ω footprints |
| IO43, IO44 | UART0 TX, RX | debug JST, boot log |
| IO4-IO7 | ROW0-3 | matrix drive; power-up low glitch harmless |
| IO15-IO18 | COL0-3 | 4.7 k pull-ups; no 32 kHz crystal |
| IO8/9, IO38/39, IO40/41 | ENC1-3 A/B | RC filter, PCNT units 0-2 |
| IO12, IO11, IO10 | LCD SCK, MOSI, CS_BIG | SPI2 IO_MUX pins |
| IO13, IO14, IO21 | CS_STRIP, DC, RESET | GPIO matrix; DC and RESET shared |
| IO47, IO48 | BL_BIG, BL_STRIP PWM | LEDC, 100 k pull-downs (no power-up glitch) |
| IO42 | STRIP_TE | optional; big panel has no TE |
| IO1, IO2 | CC1/CC2 sense | required, ADC1, 100 k; a 1.5 A advert lifts the backlight cap |
| IO3, IO45, IO46 | none | strapping pins, left open |
| IO35-IO37 | spare | free on N16R2; N16R8 is not a board option |

Used 30 of 36; spare IO35-IO37. No MISO on the board: ID reads run on the dev kit; bring-up checks
a drawn pattern. `board.toml` gets the numbers and a strapping allow-list: IO0 only on BOOT (button
to GND, 10 k pull-up, no large C); IO3, IO45, IO46 NC. `check_pins.py` rejects any other net on a
strapping pin, and duplicates; one pass vector (this table) and one fail vector per rule.

## 8. Interfaces

**8.1 Frame codec (USB CDC).** `0xA5`, version `0x02`, type, id (u8, echoed in the reply), length
(u16, 0..240), payload, CRC-16/MODBUS. v1 frames get a `NOTICE`, not a parse. The feed API is
pull-style: no frame is dropped silently; an oversize frame gets `RESULT too_big`. USB writes block
on back-pressure. One CDC-ACM port on esp_tinyusb 3.0.1; logs go to UART0 (R18 `[E6]`, verified).

**8.2 App to device over USB (configuration and provisioning).**

- `INFO_GET`/`INFO`: proto, fw version, git hash, board rev, unique id, schema min/max, max doc
  bytes, counts, display sizes, capability bits, `obs_password_set`, `wifi_psk_set`.
- `CFG_READ`/`CFG_DATA` by offset with `seq`. `CFG_BEGIN` (`base_seq`, total, CRC-32, flag bit 0 =
  try only, RAM, 30 s), `CFG_CHUNK` (offset, idempotent), `CFG_COMMIT`/`RESULT` (validate, write the
  other slot, header last; ok, busy, stale_seq, bad_crc, too_big, invalid; new `seq`; first bad path).
- `SET_CREDENTIAL{kind u8, bytes}`: the bytes are the rest of the payload. The pad checks them
  before it stores anything (trust boundary); a refused write leaves the stored value as it was.
  - kind 1 = OBS password: 1..239 opaque bytes. 239 is the 240-byte payload cap of 8.1 less the kind
    byte (arithmetic).
  - kind 2 = Wi-Fi passphrase: 8..63 bytes, each `0x20`-`0x7E`, or exactly 64 hex digits (the raw
    PSK). Sources: IEEE Std 802.11-2016 Annex J.4.1 (cited, not re-read here); IDF
    `wifi_sta_config_t.password` is `uint8_t[64]` (`esp_wifi_types_generic.h`, v5.5 line 553, read
    2026-11-19), so 64 is the most the driver holds.
  - Reply: one status byte and nothing else. 0 `ok`; 1 `bad_kind` (kind not 1 or 2); 2 `bad_len`
    (empty payload, no bytes after the kind, or a kind 2 length outside 8..64); 3 `bad_value` (a
    kind 2 byte outside the allowed set); 4 `store_fail` (the NVS write failed).
- `CLEAR_CREDENTIALS`: no payload. It erases both secrets with
  `nvs_flash_erase_partition("cred")`, the same erase as `FACTORY_RESET` and `BOOTLOADER` below.
  There is no one-credential clear and no mask (R18 item 2 had one; dropped in review, 2026-11-19):
  a partition erase takes both, and a key erase can leave the cleared bytes in flash, which the
  `cred` dump check of section 11 forbids. To run with no OBS password, set `obs.auth_mode` to
  `none`. Reply: one status byte and nothing else, with the `SET_CREDENTIAL` codes. 0 `ok`;
  2 `bad_len` (any payload byte; nothing is erased); 4 `store_fail` (the erase failed).
- `STATUS` on change: OBS state, Wi-Fi state (`no_ssid`, `connecting`, `bad_key`, `no_ap`, `up`),
  RSSI, the pad's IP. No secret, length or hash. `OBS_LIST`/`OBS_ITEM`: scenes, inputs, transitions
  from the pad's own session. `INPUT` for "press to select". `WIFI_SCAN` [later]; R1 types the SSID.
- `FACTORY_RESET`, `BOOTLOADER`: 32-bit magic each. Both erase `cred` first with
  `nvs_flash_erase_partition` (a key erase can leave the entry until page reuse, likely).
  `FACTORY_RESET` then erases both cfg slots, as does B1 + B4 held 5 s from power-on (the clear key
  combination). `BOOTLOADER` then (R18 section 8): `tud_disconnect`, deinit esp_tinyusb; reset and
  gate USB OTG; clear `RTC_CNTL_SW_HW_USB_PHY_SEL`, `RTC_CNTL_SW_USB_PHY_SEL`,
  `RTC_CNTL_USB_PAD_ENABLE`; set `USB_SERIAL_JTAG_USB_PAD_ENABLE`, `RTC_CNTL_FORCE_DOWNLOAD_BOOT`;
  `esp_restart()` (as Arduino-ESP32, verified). Expect 303a:1001.

Flow: `INFO` -> `CFG_READ` until total -> edit (unknown fields kept) -> `CFG_BEGIN(base_seq)` ->
`CFG_CHUNK`... -> `CFG_COMMIT` -> `RESULT`. Stale `seq`: re-read, show the diff. One reply per id;
retry after 1 s.

Document: compact UTF-8 JSON, cap 16 KiB: `schema`, `seq`, `obs.url`, `obs.auth_mode` (`stored` |
`none`), `wifi.ssid` (read back), `keys`, `buttons`, `knobs` (input UUID, step dB, push action),
`main_display`, `strip_display`, `ui`. OBS references are UUID plus label. The pad validates on
commit (trust boundary). The pad accepts exactly the `schema` values from `INFO` min to max. A
document whose `schema` is missing, is not an integer, or lies outside that range gets
`RESULT invalid` with path `schema`, and nothing is stored. At boot, a stored document with a
good slot header and a `schema` below the pad's min (new firmware over an old document, criterion
14) is not loaded and not erased. The pad runs as it does with no document, shows the factory strip
line with the words `update config`, and `CFG_READ` still serves the stored bytes as they are, with
their `schema` and `seq`. The app migrates them and commits with that `seq` as `base_seq`
(review 2026-11-19, proposal). The app opens the document
read-only when the pad's schema max is above its own. When the pad's schema max is below the app's
current schema, the app writes nothing and says `update firmware`: there is no downgrade migration
(R13 item 1 offers "the oldest schema the firmware takes, or refuses"; refuse is taken). Migrations
run in the app only, one function
per schema step; the pad reads one schema (R13 "Read-modify-write and schema versions" items 1 and
5, proposals taken as the contract). Exports carry no secret. `docs/config.md` fixes layout names (R13, R14
differ) and the try-only revert. URL: `ws://<private IPv4>[:port]` only; refuse loopback, public,
`wss://`, userinfo, path, query. mDNS [later].

**8.3 Device to OBS over Wi-Fi.** `esp_wifi` STA, 2.4 GHz; lwIP TCP behind `stream`; backoff
reconnect after an AP or OBS restart. RFC 6455 (client masking, ping on idle, close codes) and
obs-websocket 5 (R05, verified in 5.7.6 source): plain `ws://`, JSON, `rpcVersion` 1, floor 5.4.0;
auth `base64(sha256(base64(sha256(password + salt)) + challenge))`; `Identify` with
`eventSubscriptions` 1118, plus 65536 (meters) by `Reidentify` only while a meter shows; one request
in flight; full re-read after `Identified`; no retry on 4009/4010/4011; a streaming JSON reader
(out-of-order replies; 500 scenes is one 55 to 75 kB frame). The four-file rule covers the CDC
codec.

## 9. Capability map

| Module id | Responsibility | Depends on | Scope |
| --- | --- | --- | --- |
| `contracts` | `board.toml`, layout-v2 rev 3, `docs/protocol.md` v2, `docs/config.md`, vectors, rule texts | owner decisions | R1 |
| `fw-link` | v2 codec, pull feed | contracts | R1 |
| `fw-crypto`, `fw-json` | SHA-1, SHA-256, base64; streaming reader (LwJSON v1.10.1, MIT) | — | R1 |
| `fw-stream`, `fw-ws` | open/send/receive/close TCP seam; RFC 6455 client | fw-crypto | R1 |
| `fw-wifi` | core Wi-Fi state machine: states, backoff, strip lines; no IDF headers | contracts | R1 |
| `fw-obs` | Hello/Identify/auth, state, requests, events, reconnect | fw-ws, fw-json, fw-crypto | R1 |
| `fw-config`, `fw-store` | document codec and validator; two raw slots, NOR model; credential store seam | fw-json, contracts | R1 |
| `fw-input` | 4x4 matrix debounce, 3 quadrature decoders fed by counts | contracts | R1 |
| `fw-actions` | inputs to OBS requests; port of `host` keymap/volume (paging later) | fw-obs, fw-config, fw-input | R1 |
| `fw-ui` | widget model, 16-line band renderer, both panels' init tables as data, 4 bpp fonts (Latin R1) | fw-config, fw-obs | R1 |
| `padsim` | whole core on one PTY plus a POSIX TCP stream, panel model, stdin events | all `fw-*` core | R1 |
| `host-core` | Rust v2 codec, document types, migrations | contracts | R1 |
| `app-shell` | fix the 3 known build defects of today's `app/src-tauri` (G2) | — | R1, first |
| `app` | Tauri-free Rust core, Tauri 2 shell, no-build UI, preview via `fw-ui` through `cc`, Wi-Fi page, `espflash` update | host-core, fw-ui, app-shell | R1 |
| `fw-port-esp32s3` | ESP-IDF v6.1.1: esp_tinyusb CDC, esp_wifi, lwIP, `esp_lcd` SPI IO, PCNT, LEDC, NVS, watchdog | all `fw-*` core | R1 |
| `pcb` | greycode generator port, locked critical copper, Freerouting, DRC, STEP | contracts | R1 |
| `cad` | build123d print/cnc case, back-wall insert, plate relief, exports with read-back, coupons, laser sheets | contracts, pcb | R1 |
| `fab` | JLCPCB file set and CNC pack (PCBWay set later) | pcb, cad | R1 |

Later options, off until asked: key pages, Cyrillic, HID, OTA or A/B, `WIFI_SCAN`, mDNS, PCBWay set,
IEC 61000-4-2 test, 24 h soak (R1 runs R15's 8 h), libFuzzer (R1 keeps ASan corpus tests).

Build order:

1. **Spike, two days at most, on the DevKitC-1.** Each item gives yes/no plus a value: CDC
   enumerates (`lsusb -v`); association time (s); Hello/Identify over Wi-Fi against a throwaway OBS
   on 4456 (ms); peak and 100 ms average 3V3 current at the module, TX and both backlights on (mA;
   shunt in 3V3 or kit fed on its 3V3 pin, since the kit's LDO hides the buck ratio, `[E7]`
   verified); RSSI and Hello/Identify in the slab mock-up (deck and walls taped in aluminium, insert
   bare) against open air at the same spot (dBm, D7 clearance check); `BOOTLOADER` to ROM port
   (VID/PID); each panel's ID read, dev kit only (bytes); highest clean SPI step, exact 80 MHz / n,
   `spi_device_get_actual_freq()` logged; tail contact face; tail offset x (caliper). The kit's RGB
   LED data is GPIO38 (v1.1) or GPIO48 (v1.0) (`[E7]`, verified): move that net to IO42 (TE unused
   here); log the kit revision. **Exit:** a narrow panel in hand with a read pin table and calipered
   outline; until then its pocket and FPC footprint stay open.
2. `contracts`; `app-shell` in parallel.
3. `fw-link`, `fw-crypto`, `fw-json`, `fw-input`, `fw-wifi`, `host-core` in parallel; then
   `fw-stream`, `fw-ws`, `fw-obs`, `fw-config`, `fw-store`; then `fw-actions`, `fw-ui`; then `padsim`.
4. `app` core against `padsim`. `pcb` placement-only spike starts in parallel at step 2.
5. `pcb` route and DRC; `fw-port-esp32s3` on the dev kit; `cad` print variant.
6. **Board-order gate:** `tools/check_measure.py` lists every MEASURE tag on a `[fpc.*]`,
   `board_slots`, `key_ribs`, `holes`, `[display_carrier]`, `[knobs]`, `[mcu]`, `[antenna]`,
   `[usb]`, `[regulator]` or `antenna_relief` entry and exits 1 if any is open. Today: FPC centres,
   bar tail slot x, FH12 vs FH12A, big tail path (24.5 in the layout vs about 22 by arithmetic),
   hot-swap pads vs key ribs, EC11 lugs vs the E2 hole, 0.6 back-left web, antenna feed side, module
   stack (0.9 to the plate), USB shell overhang, insert fit, inductor height. No board order while it
   exits 1. Then boards, print case, bring-up, `cad` cnc, `fab`.

## 10. Tech stack, commands, style

Stack: C11 on ESP-IDF v6.1.1 (R18 `[E8]` verified), esp_tinyusb 3.0.1; core WebSocket, SHA, base64;
LwJSON v1.10.1. Rust stable (`host/`); Tauri 2; `espflash` 4.7.0 as a library (MIT or Apache-2.0, S3
supported, R18 `[E12]` verified). KiCad 9.0.9 in Docker for generator and DRC, `kicad/kicad:10.0.7`
for STEP. Freerouting 2.5.0 by sha256 (D5). build123d 0.13.0 in `cad/.venv`. Python 3 stdlib. No
ESP-IDF here (R04, verified): Docker `espressif/idf:v6.1.1`, 4.2 GB, "Ask first" (R04 `[E10]`).
IDF's `linux` target is a preview, not used (R18 `[E9]`).

```
just test        # gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined on firmware/core,
                 # cargo in host/, check_pins, pure-python TOML number and MEASURE checks, padsim e2e
just firmware    # idf.py build in espressif/idf:v6.1.1 (after approval); writes a merged image
just flash       # espflash: bootloader, partition table, app over the ROM USB port
just pcb         # Docker kicad/kicad:9.0.9: generate, route, DRC, fab outputs; 10.0.7: STEP
just cad         # cad/.venv: build, export, read back, write manifest
just app         # cargo build in app/src-tauri on the host; needs D6
just app-check   # no sudo: image FROM local kicad/kicad:10.0.7 + Tauri's Debian -dev list,
                 # cargo build, xvfb-run: window "macropad-obs" visible within 10 s, alive 5 s
```

Partitions: `nvs` (IDF default, no secret), `cred` (plain NVS, its own partition, D8),
`cfg_a`/`cfg_b` (raw, two slots). `cred` opens with `nvs_flash_init_partition("cred")`
(https://docs.espressif.com/projects/esp-idf/en/v6.1.1/esp32s3/api-reference/storage/nvs_flash.html,
verified); `CONFIG_NVS_ENCRYPTION` stays off and no image burns a key. Call
`esp_wifi_set_storage(WIFI_STORAGE_RAM)` after `esp_wifi_init`, before `esp_wifi_set_config`, and
load the PSK from `cred` each boot; the default `WIFI_STORAGE_FLASH` puts it in plain `nvs`
(https://docs.espressif.com/projects/esp-idf/en/v6.1.1/esp32s3/api-reference/network/esp_wifi.html,
verified). No flash encryption. No secure boot: it needs signed images and a kept signing key, and
makes ROM download Secure (flash write only, no stub); the ROM USB-OTG stack it disables is not the
app's path (R18 `[E5]` `[E10]`, verified).

Style: C, fixed-width types, no heap after init in the core, every fallible call returns a checked
status (`link_status_t link_pull(link_rx_t *rx, link_frame_t *out)`). Rust: `cargo fmt`, clippy
clean, `Secret` for password and Wi-Fi key, no `unwrap` outside tests.

## 11. Testing strategy and definition of done

Core code is proven on the host (R15); the port on the dev kit.

| Module | Done when |
| --- | --- |
| `contracts` | `check_pins.py` binds `board.toml` to `pins.h` and `protocol.rs`, rejects a duplicate GPIO, any net on IO3/IO45/IO46 and any net but BOOT on IO0 (pass and fail vectors); vectors parse in C and Rust; a `numbers` test checks panel_face, carrier heights, foam squeeze 10 to 25 %, no keep-out under a carrier |
| `fw-link` | every `vectors.txt` frame decodes; split at all 64 read alignments; oversize and bad CRC answered, never dropped |
| `fw-crypto`, `fw-json` | NIST SHA-1/SHA-256 vectors and the R05 auth example; 500-scene and 500-input fixtures in bounded RAM under ASan |
| `fw-ws`, `fw-stream` | fake transport with 1-byte reads, fragments, ping, close |
| `fw-wifi` | every state and backoff step on a fake event feed; each failure maps to its strip line; no secret in any line |
| `fw-obs` | handshake, auth on and off, 4009/4010/4011, reconnect, against `tools/fake_obs.py` |
| `fw-config`, `fw-store` | every `config_vectors/` file gets the same verdict in C and Rust; NOR model, power cut after every program call: old or new, never a mix; credential never in `CFG_DATA`; a stored `schema` below min is kept and served by `CFG_READ`; clear leaves no secret byte in the `cred` model; URL rule rejects loopback, public, `wss://` |
| `fw-input`, `fw-actions` | ghosting, debounce, quadrature at 2 turns/s with bounce; B1 + B4 for 5 s at power-on clears, 4.9 s does not; each mapped action gives the expected request JSON |
| `fw-ui` | golden PNG frames for both displays and the three mock-ups (R14) match byte for byte; init tables match the vectors; page changes redraw only changed tiles |
| `padsim` | runs app-core -> padsim -> TCP -> fake OBS, incl. a 75 kB reply throttled; panel model with window and offset; `dump`, `wait-idle`, `key`/`button`/`knob` on stdin |
| `app-shell` | `build.rs` declares the commands via `AppManifest::commands`; `main.rs` imports `tauri::Manager`; icons are RGBA |
| `app` | core tests against padsim; round trip keeps unknown fields; export has no secret; key fields cleared after write; criteria 4b, 4c pass; `just app-check` exits 0; after D6 criteria 13 and 14 pass |
| `fw-port-esp32s3` | CDC enumerates; Wi-Fi associates and re-associates after an AP restart; both panels draw; 8 h soak with no reset (R15); watchdog test; after a Wi-Fi join a raw dump of `nvs` holds no PSK or password byte; after `CLEAR_CREDENTIALS`, the clear key combination or `BOOTLOADER`, a dump of `cred` holds none either; big panel attached to SPI2 first (CS0 on IO10); `spi_device_get_actual_freq()` logged |
| `pcb` | KiCad DRC at error severity: 0 violations, 0 unconnected, 0 parity; ERC clean; byte-repeatable; `check_measure.py` exits 0 |
| `cad` | every export reads back (solid count exact, B-rep volume 1e-4, mesh 0.1 %, watertight); no interference with the PCB, module or insert solids; no metal in the antenna board cut; laser sheets below |
| `cad` laser | each DXF opens in one tool other than OCCT (`ezdxf` audit or Inkscape) with 0 errors; strokes >= 0.2 mm; text cap height >= 2.0 mm; outline 1:1 with the deck outline within 0.05 mm |
| `fab` | JLCPCB set: Gerber/drill/BOM/CPL all accepted with 0 unmatched BOM lines and CPL rotations checked against the STEP; CNC pack has STEP, PDF drawing with tolerances, DXF |
| bring-up | R15 checklist in order, stop at first fail: no rail short; at 5 V, 100 mA limit, 3V3 = 3.3 V +/- 3 %; UART0 boot log; ROM port appears with BOOT held; CDC enumerates; each panel draws the test pattern; every key, button, knob reports `INPUT`; Wi-Fi up; VBUS peak under 500 mA; on a charger (no host) Wi-Fi up after 2 s at the cap |
| manual | once, owner's OBS closed: throwaway OBS on 4456 (R15); the 4b layout on both real panels matches the preview by eye |

## 12. Boundaries

**Always:** `board.toml` is the truth; four protocol files change together; non-datasheet sizes are
MEASURE; `just test` before a commit; no secret in logs, displays, readback, vectors, exports.
**Never:** SK6812; a secret in a device-to-host frame; `wss://` or TLS on the pad; a silent fallback
to a plain-text password file; a frame dropped without a reply; pushing or committing unasked;
burning any eFuse (D8; USB_PHY_SEL, for one, moves the PHY to OTG for good: `[E10]` usb-otg-console,
verified).

**Ask first:** a new dependency (LwJSON, rtree, `espflash`); `espressif/idf:v6.1.1`, `ubuntu:24.04`
or any non-local image; the `app-check` apt packages; deleting `.grok/workflows/`; licence texts and
holder in `LICENSE*`; a pid.codes PID; flash encryption or secure boot; editing
the sibling repos (never); rule-text changes.

**Security (D8, plain NVS).** The OBS password and the Wi-Fi key sit in plain text in the `cred`
partition. Anyone who holds the pad can put it in ROM download (BOOT held at reset, which erases
nothing) and read both with `esptool read_flash`, then join the Wi-Fi and drive OBS. No eFuse is
burnt, so nothing stops that. What still holds: R1 (the app never reads a secret back over USB), the
erase on clear and before `BOOTLOADER`, and no secret in `nvs`, logs, displays, readback or exports.
The owner's mitigation: a password used only for this OBS, and a guest SSID for the pad if wanted.

Settled (D5): copying from the sibling repos named in section 3 and fetching Freerouting 2.5.0 by
sha256 are allowed; copied files carry MIT or CERN-OHL-S-2.0 headers.

Repo rules that change (`CLAUDE.md` is edited in `contracts`, not here):

- **R1 (D2, replaces "No OBS password in a CDC frame.").** Exact text (R16 Text 1, with "partition"
  and "download mode" for the ESP32-S3):
  > The OBS password and any Wi-Fi passphrase cross the CDC link only in `SET_CREDENTIAL`, app to
  > device. No device-to-host frame, log line, display, readback or test vector carries a secret or a
  > value derived from one. The device stores secrets in their own flash partition and erases it on
  > `CLEAR_CREDENTIALS`, on the clear key combination, and before a host-requested download mode.
- **R2 (LCSC).** "LCSC cells stay `UNVERIFIED`." RP2040 C2040, W25Q128JVSIQ C97521 and FH12-20S
  C596730 are not used.
- **R3 (protocol and config).** "Protocol changes update `firmware/core/link.c`,
  `host/obs_core/src/protocol.rs`, `firmware/test/vectors.txt` and `docs/protocol.md` together. Config
  schema changes update `firmware/core/config.c`, `host/obs_core/src/document.rs`,
  `firmware/test/config_vectors/` and `docs/config.md` together."
- **R4 (just test).** "`just test` is gcc ASan/UBSan, `cargo` in `host/`, and python3. It runs padsim
  end to end against a fake OBS. It does not build `app/src-tauri`, does not import KiCad or
  ESP-IDF, and does not need `cad/.venv`."
- **R5 (source of truth).** Add: "`docs/spec/layout-v2.toml` feeds `board.toml`; no board order while
  `tools/check_measure.py` exits 1."
- **R6 (check_pins).** "`tools/check_pins.py` binds `firmware/esp32s3/main/pins.h` and
  `host/obs_core/src/protocol.rs` to it." (pins.h path is design, fixed in `contracts`.)

## 13. Success criteria

1. `just test` exits 0, includes padsim end to end and 4b, 4c; under 60 s on this machine.
2. On Wi-Fi, OBS 30.1+ on the LAN: `INPUT` frame to `CurrentProgramSceneChanged` under 100 ms.
3. After an OBS restart the pad reconnects within 5 s, after an AP restart within 30 s, app closed.
4. The app reads the document, changes one key mapping and the URL, writes it; a second read returns
   the change with `seq + 1`; a stale write gets `stale_seq`.
   - **4b. Display layout round trip (padsim, `fake_obs.py` serving `ui_state.json`).** The app core
     changes one `text` widget in `main_display` to `Test 1` (`Тест 1` if Cyrillic ships) and drops
     `fader` from the knob 1 `strip` widget in `strip_display`, renders its preview from the same
     state, writes, gets `RESULT ok`. After `wait-idle` the padsim dumps equal the preview byte for
     byte: `main.rgb565` 307,200 B (320x480), `strip.rgb565` 121,552 B (142x428), big-endian RGB565.
     Every changed pixel lies inside the two edited widgets. A write with two overlapping widgets
     gets `RESULT invalid` with the second widget's path, and the frames stay unchanged (G3).
   - **4c. Input remap round trip (padsim).** The app sets button 1 to `toggle_record`, knob 0 to
     input `U_B`, step 2 dB, push `toggle_mute`, writes. One press of button 1, one clockwise detent
     and one push of knob 0 make `fake_obs.py` log exactly, in order (`requestId` ignored):
     `{"requestType":"ToggleRecord"}`, `{"requestType":"SetInputVolume","requestData":{"inputUuid":"U_B","inputVolumeDb":-18}}`
     (`U_B` starts at -20 dB), `{"requestType":"ToggleInputMute","requestData":{"inputUuid":"U_B"}}`.
     No request names `U_A`; the same events before the write give the old requests (G3).
5. Unplug during `CFG_COMMIT` 50 times: the pad always boots with the old or the new document.
6. The strip shows name, level and mute for 3 inputs, and updates within 200 ms of a change in OBS.
7. The big display redraws one 96x96 key cell in 17 ms or less and the full screen in T_full or
   less, first CASET byte to last RAMWR byte, DMA, RGB565, SPI mode 3, at f_bus = the fastest S3
   step that passed (80 MHz / n requested exactly, actual logged). T_full = data time x 1.05: 194 ms
   at 13.3 MHz, 161 at 16, 129 at 20, 97 at 26.7, 64 at 40 (arithmetic). Until a step above the 15
   MHz rating passes (66 ns write cycle, G4), f_bus = 13.3 MHz.
8. A 500-scene OBS collection loads with no reset and lists in the app's picker.
9. Each failure (no SSID, bad Wi-Fi key, no AP, OBS unreachable, bad password, OBS too old, factory)
   has a strip line.
10. KiCad DRC: 0 violations, 0 unconnected, 4 copper layers, every net routed.
11. All case exports read back. The manifest also holds the assembled PCB STEP (KiCad 10: panels,
    switches, encoders, buttons, connectors, module) and one envelope STEP per bought part,
    each read back with its solid count (`kicad-cli` exits 0 with missing models, R09; MX, EC11 from
    `cad` envelopes). The printed case fits with no sanding; one shop's quote form accepts the CNC
    pack.
12. No byte of the OBS password or the Wi-Fi key appears in any device-to-host USB frame, in any
    host-to-device frame other than the `SET_CREDENTIAL` payload (R1), in logs or exports, or in a
    raw dump of `nvs`; `cred` holds them in plain (D8) until erased.
13. After D6: `just app` exits 0, the window opens, the app finds the pad without a fixed path,
    reads, edits one key, one `main_display` widget, the URL and the SSID, writes; after an app
    restart a read shows `seq + 1` and the panel the edit. Before D6: `just app-check` only.
14. Firmware from the app: `BOOTLOADER`, ROM port within 10 s, `espflash` writes, hard reset; the
    pad re-enumerates with the new git hash in `INFO` within 30 s. Credentials are gone after it.
15. VBUS peak stays at or under 500 mA with Wi-Fi TX and backlights at the firmware cap. 465 mA at
    80 % excludes the CPU (up to 108 mA, `[E2]` table 6-6 Typ2, verified): with it, 544 mA, so about
    60 % (R18 section 4, arithmetic). Set the cap from the spike's 3V3 current. No enumeration in 2 s
    means a charger: join Wi-Fi anyway at the same cap. A 1.5 A CC advert lifts it.

## 14. Risks and what stays unproven until hardware

| Risk | Retired by |
| --- | --- |
| Tail contact face, FH12 vs FH12A; NV3007 init by hand (no IDF component, R18 `[E6]`); narrow panel supply (N279 by quote) | panel bench and exit condition in spike step 1, before FPC footprints |
| ST7796U above its 15 MHz write rating | bench: each S3 step from 16 MHz up, 1000 pseudo-random full frames, RAMRD read-back on the dev kit, zero mismatches, 3.3 V IOVCC, real FPC length. Fastest pass is f_bus |
| VBUS over 500 mA: TX 355 mA + CPU up to 108 mA on 3.3 V, 220 mA backlights (R18, verified loads) | cap from the spike's 3V3 current; backlights and Wi-Fi off until USB configures, or 2 s with no enumeration (a charger), then the same cap; CC sense lifts it on 1.5 A; real VBUS in bring-up |
| Weak RF: the insert opens the back, but metal is closer than Espressif's 15 mm (deck about 7.6 above, wall 4.6 and 9.0 aside, narrow panel 0.4 ahead) | spike RSSI in the taped mock-up vs open air, then the print case, then the CNC case; a failed check goes back to the owner (the RP-SMA hole was D7's other option) |
| Module 3.1 in the 4.0 gap (0.9 left); 0.28 web behind the narrow carrier; USB shell 1.0 past the edge | stack check in `cad`; print coupon with the module, a bought USB4216 and the owner's cables |
| Secrets in plain NVS (D8): whoever holds the pad reads them | accepted by the owner; section 12 |
| Plain `ws://` on a shared LAN exposes the session (R16) | random OBS password; auth challenge never carries the password; accepted for a home LAN |
| Unbounded OBS messages exhaust RAM | streaming reader, 500-item fixtures, throttled padsim |
| ESD through metal case, knobs, FPC; foam squeeze 0 to 40 % with panel tolerance | case bonded to USB shield, TVS (values unverified), IEC test [later]; carrier height from a calipered panel |

Unproven until hardware: Wi-Fi range through the insert, ROM port after `BOOTLOADER`, two `esp_lcd`
IO handles on one SPI host, IDF RAM, SPI above 15 MHz, backlight and CPU currents, encoders, matrix
settle, buck heat, case air, laser, MEASUREs.

## 15. Open questions

1. D6 in section 3. Fixed LAN address for the OBS PC and a DHCP reservation for the pad? 2.4 GHz
   where the pad sits? Insert colour against the black anodise (default black)?
2. Plunger: round black B3F-1060 (7.0 mm, default), -1020 (5.0 mm) or square -1050? Sets cap and
   deck (R08).
3. Screws: M2 or M2.5, how many, which heat-set insert (R11)? Blocks the hole table.
4. Display: 350 cd/m2 enough; meters or fader dB; REC/LIVE time or clock; Cyrillic; 9 keys or key
   pages (button 4)? In-app firmware update (row 11b) wanted? If not, criterion 14 drops.
5. Printer bed (longest part about 170 mm); country (import tax); logo to engrave; keycap colour;
   is the repo public? If so, CI runs `app-check` on `ubuntu-24.04` (Tauri's Debian list).
