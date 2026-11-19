# 18. ESP32-S3 with Wi-Fi: what changes against spec v2

Research only, 2026-11-18. This file is the only file written. Owner decision D1 = W and D2 = "pad
stores it" (`docs/spec/decisions-v2.md`) are final. This report says what spec v2 must change to
match them. No hardware was used and no ESP-IDF build was run.

Tags: **verified** (read today in a primary source, or reused from a report that verified it),
**likely** (reasoned from a verified fact), **unverified**. **MEASURE** marks a size not read in a
datasheet drawing. Keys such as `[E2]` point into the Sources list. `R04` = `docs/research/04-...md`.

## Recommendation

1. **Module: ESP32-S3-WROOM-1U-N16R2.** U.FL connector, 16 MB flash, 2 MB quad PSRAM, -40 to 85 °C.
   The firmware draws in 16-line bands, so no frame buffer and no octal PSRAM is needed.
2. **Antenna: U.FL pigtail to an RP-SMA bulkhead jack in the back wall**, plus a 2.4 GHz dipole of at
   most 2.33 dBi. No window in the metal case.
3. **Power: TLV62569 buck** (R10) for 3.3 V; backlights stay on 5 V sinks. Peak VBUS about 510 mA,
   so the firmware caps backlight duty while Wi-Fi is up.
4. **One USB CDC-ACM port** on the native USB (esp_tinyusb). It carries config, the Wi-Fi SSID and
   key, the OBS URL and password. Secrets are write-only.
5. **Secrets in an NVS partition with NVS encryption, HMAC scheme.** No flash encryption, no secure
   boot. The pad stays reflashable over USB. Physical access still reads the secrets.
6. **ESP-IDF v6.1.1 in C.** The SDK-free core keeps its WebSocket client, stream JSON reader and
   SHA-256. `just test` does not change.
7. **Flashing: ROM download mode over USB, driven by the `espflash` Rust library inside the app.**
   No UF2.

Next action: the owner approves the antenna hole in the back wall (it changes the D3 look). Then
`contracts` rewrites spec sections listed at the end.

## 1. Module choice

| Variant | Flash | PSRAM | Pins lost | Ambient | Fit |
| --- | --- | --- | --- | --- | --- |
| WROOM-1U-N16R2 | 16 MB quad | 2 MB quad | 0 | -40 to 85 °C | **pick** |
| WROOM-1U-N16R8 | 16 MB quad | 8 MB octal | IO35, IO36, IO37 | -40 to 65 °C (85 °C with PSRAM ECC, 1/16 less PSRAM) | works, hotter limit |
| WROOM-1U-N8R8 | 8 MB quad | 8 MB octal | IO35 to IO37 | -40 to 65 °C | no gain |
| WROOM-1U-N16 | 16 MB quad | none | 0 | -40 to 85 °C | works, no headroom |

Source: `[E2]` tables 1-2 and 3-1 note b (verified). Module 18.0 x 19.2 x 3.2 mm `[E2]` table 1-2
(verified).

Why no frame buffer.

1. Frames: big 320 x 480 x 2 = 307,200 B; strip 142 x 428 x 2 = 121,552 B (arithmetic, verified).
   Chip SRAM is 512 KB `[E1]` (verified), shared with Wi-Fi and lwIP.
2. Spec section 9 `fw-ui` is a 16-line band renderer. Bands: 320 x 16 x 2 = 10,240 B; 142 x 16 x 2
   = 4,544 B; double-buffered about 30 KB of internal DMA RAM (arithmetic). No PSRAM needed.
3. 2 MB PSRAM costs no pins and keeps 85 °C. It is room for a later full frame or images. (likely)
4. Inside a closed black case with a buck and two sinks, 65 °C is a thin margin. Case air
   temperature is MEASURE.

The spike runs on ESP32-S3-DevKitC-1U-N16R8 (the R2 dev kits are EOL) `[E7]` (verified). Spec v2
frees IO35 to IO37 as spares on the N16R2; the N16R8 is not a board option.

## 2. Pin budget and pin table

The module has 36 GPIO pads: IO0 to IO21, IO35 to IO48 (IO43/IO44 are TXD0/RXD0) `[E2]` table 3-1
(verified). Rules used:

- Strapping: IO0 (weak pull-up, BOOT), IO3 (floating, JTAG source), IO45 (weak pull-down, VDD_SPI),
  IO46 (weak pull-down, boot mode / ROM print) `[E2]` table 4-1 (verified). Keep IO3/45/46 off.
- Power-up glitches: IO1 to IO17 glitch low 60 µs (IO15/16 as XTAL_32K_P/N); IO18 low and high;
  IO19/IO20 pull-down plus two high glitches over 3.2/2 ms `[E1]` table 2-2 (verified). IO21, IO38
  to IO48 are glitch-free (verified). Backlight enables
  go on non-glitching pins with 100 kΩ pull-downs (R10).
- SPI2 IO_MUX pins: IO12 CLK, IO11 MOSI, IO10 CS0 `[E2]` table 3-1 (verified). Other CS and DC go
  through the GPIO matrix. (likely fine at panel speeds)
- PCNT: 4 units, 2 channels each, glitch filter per unit `[E1]` 4.2.1.12 (verified). One unit per
  encoder, any GPIO through the matrix. (likely)
- LEDC: up to 8 PWM channels `[E1]` (verified).
- ADC1 is on IO1 to IO10 `[E2]` table 3-1 (verified).

| Pin | Net | Dir | Note |
| --- | --- | --- | --- |
| IO0 | BOOT | in | button to GND, 10 k pull-up, no large C (R10) |
| EN | RESET | in | 10 k / 1 µF, button to GND (R10) |
| IO19 | USB_D- | io | 22 Ω footprint (R10) |
| IO20 | USB_D+ | io | 22 Ω footprint |
| IO43 | UART0_TX | out | debug JST pin 3, 499 Ω (R10) |
| IO44 | UART0_RX | in | debug JST pin 1 |
| IO4, IO5, IO6, IO7 | ROW0..3 | out | matrix drive, open-drain style; low glitch harmless |
| IO15, IO16, IO17, IO18 | COL0..3 | in | 4.7 k pull-ups (R10). IO15/16 free: no 32 kHz crystal |
| IO8, IO9 | ENC1_A, ENC1_B | in | RC filter (R10), PCNT unit 0 |
| IO38, IO39 | ENC2_A, ENC2_B | in | PCNT unit 1. IO39 to IO42 are pad JTAG only if eFuse selects it |
| IO40, IO41 | ENC3_A, ENC3_B | in | PCNT unit 2 |
| IO12 | LCD_SCK | out | SPI2 IO_MUX |
| IO11 | LCD_MOSI | out | SPI2 IO_MUX |
| IO10 | LCD_CS_BIG | out | SPI2 CS0 |
| IO13 | LCD_CS_STRIP | out | matrix |
| IO14 | LCD_DC | out | shared |
| IO21 | LCD_RESET | out | shared, no glitch |
| IO47 | BL_BIG_PWM | out | LEDC, BCR421 enable, 100 k pull-down |
| IO48 | BL_STRIP_PWM | out | LEDC, 100 k pull-down |
| IO42 | STRIP_TE | in | optional; big panel has no TE (R10) |
| IO1, IO2 | CC1_SENSE, CC2_SENSE | in | required, ADC1, 100 k (lifts the cap on 1.5 A) |
| IO3, IO45, IO46 | — | — | strapping, no connection |
| IO35, IO36, IO37 | — | — | spare (N16R2) |

Count: 5 fixed + 25 assigned = 30 of 36. Spare: IO35 to IO37; 3 strapping. No MISO: the RAMRD
bench runs on the dev board. (arithmetic, from the verified pin list)

USB endpoints: CDC-ACM uses 2 IN; the S3 allows 5 IN counting EP0 (R04, verified). With NCM gone, a
HID keyboard (1 IN) fits beside ACM. (verified count)

## 3. Antenna through the anodised 6061 case

Facts.

1. WROOM-1U has a first-generation connector compatible with Hirose U.FL, I-PEX MHF I, Amphenol
   AMC. No antenna ships with it. Use 2.4 GHz, 50 Ω, max gain 2.33 dBi. Certified with the monopole
   TFPD05H08750011; "an external antenna of a different type or gain" may need extra testing, such
   as EMC `[E2]` 10.2 (verified). A dipole on a pigtail is another type: accepted risk for a one-off.
2. A PCB antenna needs "at least 15 mm" clearance to the housing in all directions and must not be
   fully covered by metal (R03 `[H1]` `[H5]`, verified). Anodise is an oxide skin on aluminium; the
   wall still shields. (likely)

| Option | Case impact | Verdict |
| --- | --- | --- |
| A. U.FL to RP-SMA bulkhead on the back wall, external dipole | one D-hole about 6.5 mm (MEASURE), PCB back-edge notch | **pick** |
| B. Flexible FPC antenna behind a non-metal window | plastic window plus 15 mm air in all directions; inside height is only 11.6 mm (deck underside 6.0 to plate -5.6, spec 7) | reject for CNC |
| B-print | FPC antenna stuck inside the printed case | allowed for the print prototype only |

Layout impact of A (all MEASURE until a bulkhead and pigtail are in hand).

1. **Place** the jack in the back wall at about x 70 to 80, behind the strip display (its top edge
   is y 161.27, PCB back edge y 167.7). That keeps it 25 mm or more from the USB at x 45.8, and clear
   of the (88.3, 166) hole keep-out.
2. **Height.** Centre the jack near the PCB mid-plane, z about -0.8. A nut about 8 mm across spans
   z -4.8 to +3.2, inside the -5.6 to 6.0 cavity. It must not reach y < 162.5 (display pockets).
3. **PCB notch** about 10 x 5 mm at the back edge under the jack, so the jack body passes the board
   plane and the pigtail drops to the bottom face.
4. **Module** on the bottom face (spec rule: all SMT on the bottom), near the back. It is 3.2 mm
   tall `[E2]` against `bottom_side.max_part_height = 2.5` and a 4.0 mm gap. U.FL receptacle 1.25
   +/- 0.15 mm high, 2.60 x 2.60, mating post 2.00 `[E2]` fig 10-3 (verified); mated plug height
   MEASURE (Hirose U.FL-LP not read). Fix: a pocket of 3.2 + mated height - 4.0 in the bottom plate,
   or 5.5 mm standoffs. Pick at `contracts`.
5. **Ground.** The jack body bonds to the case, which spec 14 already bonds to the USB shield.
6. **Style D3.** A dipole on the back changes the slab look. A short stubby dipole folds flat.

## 4. Power

Loads `[E2]` table 6-4, 6-6 (verified) and R10 allowances:

| Load | Rail | mA | Conf. |
| --- | --- | --- | --- |
| Module, Wi-Fi TX peak (802.11b 1 Mbps 20.5 dBm, 100 % duty) | 3.3 V | 355 | verified |
| Module, TX 802.11n HT20 MCS7 17.5 dBm | 3.3 V | 286 | verified |
| Module, RX | 3.3 V | 95 to 97 | verified |
| Module, 240 MHz, radio off (CPU, peripherals on during TX) | 3.3 V | 33 to 108 | verified |
| Panel logic | 3.3 V | 30 | unverified allowance (R10) |
| Pull-ups | 3.3 V | 0 to 9 | arithmetic |
| Big backlight | 5 V | 120 | likely (R06) |
| Strip backlight | 5 V | 100 | verified (R07) |

VBUS current, buck at 90 % (assumption; TLV62569 states "up to 95 %", R10 `[P2]` verified):

| Case | 3.3 V | VBUS |
| --- | --- | --- |
| TX peak, backlights full | 394 mA | 394 x 3.3 / 0.9 / 5.0 = 289, + 220 = **509 mA** |
| TX peak, backlights capped to 80 % | 394 mA | 289 + 176 = **465 mA** |
| RX steady, backlights full | 139 mA | 102 + 220 = 322 mA |
| TX peak at VBUS 4.4 V, full | 394 mA | 328 + 220 = 548 mA |
| LDO instead (AP2112K) | 394 mA | 614 mA; 0.67 W in SOT-25 (R10) |

Arithmetic, from the rows above. The 394 mA sum excludes the CPU: table 6-4 is RF-mode current,
RX with "peripherals disabled and CPU idle", and in-package PSRAM may draw more (6.4.2, verified).
With the CPU at 108 mA (table 6-6 Typ2): 502 mA on 3.3 V, VBUS 588 full, 544 at 80 %, about 60 %
cap for 500 (likely). Size the cap from the spike's measured 3V3 current. USB 2.0 allows 500 mA after configuration, 100 mA before (R10
`[U2]`, verified).

Design.

1. **Buck, not LDO.** TI TLV62569DBV: 2 A, 2.5 to 5.5 V in, SOT-23-5, 2.2 µH, 4.7 µF in, 10 µF out,
   0.6 V feedback (R10 `[P2]`, verified). Espressif asks "no less than 500 mA" on 3V3, 22 µF + 0.1 µF
   at the module pin (R10 `[E2]`, verified).
2. **VBUS bypass** stays at 10 µF or less (USB 2.0, R10); the 22 µF sits after the buck.
3. **Fuse** PPTC about 0.75 A hold (R10, unverified part).
4. **Firmware cap.** Backlights and Wi-Fi stay off until USB is configured. While Wi-Fi is on, total
   backlight PWM stays at 80 % or less. If no host enumerates in 2 s (a charger), run anyway at the
   same cap. The 2 s and 80 % are mine. (design)
5. **Required:** CC sense on IO1/IO2; a 1.5 A source lifts the cap (R10 `[U1]`, verified threshold).
6. **Measure** peak and 100 ms average 3V3 current at the module on the dev board (shunt, or kit fed
   on 3V3: its LDO makes VBUS equal 3V3 current, `[E7]` verified). Real VBUS in PCB bring-up.

## 5. Provisioning over USB

Transport: esp_tinyusb 3.0.1 (2026-11-13) CDC-ACM on the USB OTG peripheral `[E6]` (verified). When
TinyUSB runs, the USB-Serial/JTAG console is gone; logs go to UART0 (R04, verified). One CDC port
replaces spec's two. The v2 frame codec (spec 8.1) is unchanged.

Changes to spec 8.2:

1. `SET_CREDENTIAL{kind, bytes}`: kind 1 = OBS password, kind 2 = Wi-Fi passphrase (8 to 63 ASCII or
   64 hex, WPA2/WPA3 personal; likely). Reply: status byte only.
2. `CLEAR_CREDENTIALS{mask}`: erases one or both.
3. Document gains `wifi.ssid` (not secret, read back). `obs.url` becomes `ws://<private IPv4>[:port]`;
   refuse loopback (it means the pad itself), public addresses, `wss://`, userinfo, path, query.
   Host names via mDNS [later].
4. `INFO` gains `wifi_psk_set`; `STATUS` gains Wi-Fi state (`no_ssid`, `connecting`, `bad_key`,
   `no_ap`, `up`), RSSI and the pad's IP. No secret, length or hash.
5. `WIFI_SCAN` / `WIFI_AP` (SSID, RSSI, auth) [later]. R1: the user types the SSID.
6. `BOOTSEL` becomes `BOOTLOADER` (magic): erase credentials, then enter ROM download (section 8).
7. **Factory reset:** `FACTORY_RESET` (magic) and the clear key combination erase the credential
   partition with `nvs_flash_erase_partition`, then the config slots. A key erase alone may leave the
   old entry in flash until page reuse. (likely)

App: a Wi-Fi page (SSID field, write-only key field cleared after write, status line), the password
field as today. The app stores no secret (R16). App-side `Secret` type and log redaction stay.

## 6. Secret storage

| Option | Reflash over USB | Protects against | Cost | Verdict |
| --- | --- | --- | --- | --- |
| Plain NVS | yes | nothing | none | no |
| **NVS encryption, HMAC scheme** | yes | flash dump (esptool `read-flash`, desoldered chip) | one eFuse key block burned (irreversible) | **pick** |
| Flash encryption, development mode | yes, plaintext re-encrypted on boot | code read-out | NVS not covered; disable only once per chip | no gain |
| Flash encryption release + Secure Boot v2 | signed images only; ROM USB-OTG stack off; download mode "Secure" by default | hostile firmware, read-out | signing key, pre-encrypted or OTA updates | no for a hobby pad |

Sources: `[E3]` `[E4]` `[E5]` (verified).

1. HMAC scheme: XTS keys derived at run time from an eFuse key with purpose `HMAC_UP`; "secure
   storage on ESP32-S3 without enabling flash encryption". Set `CONFIG_NVS_SEC_KEY_PROTECT_USING_HMAC`
   and `CONFIG_NVS_SEC_HMAC_EFUSE_KEY_ID` explicitly (default -1). The auto key burn happens in
   `nvs_flash_init()`, which handles only the default partition. A custom `cred` needs
   `nvs_sec_provider_register_hmac`, `nvs_flash_read_security_cfg_v2` (or `_generate_keys_v2`) and
   `nvs_flash_secure_init_partition` `[E4]` (verified). With `CONFIG_NVS_ENCRYPTION` set, the first
   boot burns OTP with no prompt, so it stays off until D8; the owner pre-burns with
   `idf.py efuse-burn-key BLOCK_KEYn key.bin HMAC_UP` `[E4]` (verified).
2. Limit: any firmware on the chip can use the HMAC peripheral. Someone who flashes their own image
   through the BOOT button can decrypt the NVS. (likely) That matches the accepted physical-access
   risk (spec assumption 5, R16).
3. Flash encryption does not cover NVS: "NVS partitions ... cannot be encrypted" by it `[E3]`
   (verified).
4. Secure Boot v2: RSA-3072, up to 3 key digests, default download mode becomes Secure `[E5]`
   (verified). No secure boot: it needs signed images and a kept signing key, and Secure mode allows
   flash write only, no stub. The ROM USB-OTG stack it disables is not the one the app uses: ROM
   download runs on USB-Serial/JTAG, the internal PHY default `[E10]` usb-otg-console (verified).
5. Wi-Fi driver copy: `esp_wifi_set_storage` defaults to `WIFI_STORAGE_FLASH`, which stores SSID and
   passphrase in the default NVS `[E13]` (verified). Call it with `WIFI_STORAGE_RAM` after
   `esp_wifi_init`, before `esp_wifi_set_config`, and load the PSK from `cred` each boot.

Partitions: `nvs` (IDF), `cred` (encrypted NVS, secrets only), `cfg_a`/`cfg_b` (raw, the spec's
two-slot store and NOR model unchanged), `nvs_keys` not needed. (design)

## 7. Firmware stack

| Piece | Choice | Source | Conf. |
| --- | --- | --- | --- |
| SDK | ESP-IDF v6.1.1, 2026-11-16 | `[E8]` | verified |
| Docker | `espressif/idf:v6.1.1`, 4.2 GB, not local | R04 `[E10]` | verified |
| TCP | lwIP BSD sockets behind the spec's `stream` seam | R04 | likely |
| WebSocket | core RFC 6455 client (host-tested). `esp_websocket_client` 1.8.0 exists, not used | `[E6]` | verified version |
| JSON | core stream reader, LwJSON v1.10.1. `espressif/cjson` 1.7.19 is a tree parser | R04 `[X2]`, `[E6]` | verified |
| SHA-1/256, base64 | core's own (NIST vectors). Mbed TLS 4 / PSA is IDF 6's crypto interface; not needed | R04 `[E8]` | verified |
| Big panel | `esp_lcd` SPI panel IO; `espressif/esp_lcd_st7796` 1.5.0 supports SPI on esp32s3 | `[E6]` | verified |
| Strip panel | no NV3007 component found in the registry; LVGL v9.4+ has one (R07) | `[E6]`, R07 | verified search, likely none |
| Wi-Fi | `esp_wifi` STA, 2.4 GHz only | R03 `[H2]` | verified |
| Encoders | PCNT counts fed to the core decoder | `[E1]` | likely |

Display plan: use `esp_lcd_panel_io_spi` only (one SPI host, one IO handle per CS, DC by the
driver; likely). Keep both init tables as data in the core, so tests check the bytes. Skip the
ST7796 component; one path for both panels. SPI mode 3 is a plain setting on the S3; the RP2350
PL022 CS-pulse risk goes away. (likely)

SPI clock steps change: 80 MHz / n gives 40, 26.7, 20, 16, 13.3 MHz. IDF rounds to "the nearest
hardware-compatible number", not down, so request exact 80/n values and log
`spi_device_get_actual_freq()`. "Only the first Device attached to the bus can use the CS0 pin":
attach the big panel first (IO10) `[E14]` (verified). Full big frame, data only: 154 ms at 16, 123 at 20, 92 at 26.7, 61 at 40 MHz.
(arithmetic)

Host tests: the core has no IDF headers. `just test` stays gcc `-fsanitize=address,undefined`,
cargo, python3. padsim drops `obs-link`: its `stream` seam opens a POSIX TCP socket to
`fake_obs.py`. IDF's own `linux` target is "experimental" and a "preview" `[E9]` (verified): not
used.

## 8. Flashing

1. ROM download: GPIO0 low at reset, GPIO46 low or floating `[E10]` (verified). Over USB the ROM
   uses the USB-Serial/JTAG on the internal PHY. (likely)
2. From firmware (`BOOTLOADER`): (1) erase `cred`; (2) `tud_disconnect`, deinit esp_tinyusb, reset
   and gate the USB OTG module; (3) clear `RTC_CNTL_SW_HW_USB_PHY_SEL`, `RTC_CNTL_SW_USB_PHY_SEL`,
   `RTC_CNTL_USB_PAD_ENABLE`, then set `USB_SERIAL_JTAG_USB_PAD_ENABLE`; (4) set
   `RTC_CNTL_FORCE_DOWNLOAD_BOOT` in `RTC_CNTL_OPTION1_REG`; (5) `esp_restart()`. The bit is at
   `rtc_cntl_reg.h:3212` `[E11]`. Used by the IDF ROM console (`usb_console.c` 256-262) and by
   Arduino-ESP32 (`usb_switch_to_cdc_jtag`, `usb_persist_restart`) `[E15]` (verified); on the
   TinyUSB path it needs the PHY switch above. Expect 303a:1001 (espflash
   `USB_SERIAL_JTAG_PID = 0x1001`, verified).
3. Tools: `esptool` (Python) or `espflash` 4.7.0, a Rust library and CLI, MIT or Apache-2.0,
   supports ESP32-S3 `[E12]` (verified). The Tauri core links `espflash` as a library: no Python.
4. App flow: `BOOTLOADER` -> pad wipes credentials -> ROM port appears (VID 303a, PID 1001, likely)
   -> espflash writes bootloader, partition table, app (or one merged image) -> hard reset -> new git
   hash in `INFO`. The udev rule adds the ROM VID/PID with `uaccess`.
5. Recovery: BOOT + RESET buttons through the plate pinholes stay.
6. UF2: not native; Espressif's TinyUF2 port is not needed. (unverified, not read)

## Spec sections that must change

1. **Header, section 1 item 3, row 12, D1, D2:** record W and "stored"; drop relay and NCM text;
   drop `relay_answer` and R1-alt.
2. **Row 7:** encoders on PCNT. **Row 11:** URL is a LAN `ws://` IPv4. **Row 11b:** `BOOTLOADER` +
   espflash, not UF2.
3. **D4:** spike kit = ESP32-S3-DevKitC-1U-N16R8, a 2.33 dBi RP-SMA dipole, a U.FL to RP-SMA bulkhead
   pigtail; remove RP2350B board.
4. **Section 4:** item 2 (radio fitted), item 5 (ROM download, not UF2), item 6.
5. **Section 5:** new diagram: OBS <- Wi-Fi TCP <- pad (ESP32-S3: TinyUSB one CDC | SPI2 one bus |
   PCNT | LEDC | NVS | esp_wifi); Tauri app <- one CDC port. No `obs-link`. Drop the "two SPI buses",
   "UART pins" graft stays.
6. **Section 6 parts:** MCU -> WROOM-1U-N16R2; delete W25Q128JVSIQ, crystal, core inductor, SWD;
   AP2112K -> TLV62569 + 2.2 µH; fuse 0.75 A; add U.FL-RP-SMA pigtail and dipole; debug JST is UART.
7. **Section 7:** replace the pin budget with the table above; module 3.2 mm vs 2.5 mm max part
   height (plate pocket or taller standoffs); PCB back-edge notch; `radio` line; `mcu_zone` contents.
8. **Section 8.2:** `SET_CREDENTIAL` kind, `CLEAR_CREDENTIALS` mask, `wifi.ssid`, `INFO`/`STATUS`
   fields, `BOOTLOADER`, URL rule. **Section 8.3:** replace port 1 with direct TCP over Wi-Fi; keep
   the RFC 6455 and obs-websocket rules.
9. **Section 9:** delete `fw-ncm`, `obs-link`; `fw-stream` = TCP seam; add `fw-wifi` (core state
   machine, backoff); `fw-port-rp2350` -> `fw-port-esp32s3`; `app` gains Wi-Fi page and espflash.
   Spike items: CDC enumerates; association time; Hello/Identify over Wi-Fi; VBUS peak mA; RSSI
   through the RP-SMA in a metal box.
10. **Section 10:** ESP-IDF v6.1.1 (Docker 4.2 GB, ask first); `just firmware` changes.
11. **Section 11:** delete `fw-ncm`, `obs-link` rows; padsim without relay; bring-up: no 1.1 V, no
    JEDEC, UART boot log, Wi-Fi up, VBUS peak.
12. **Section 12:** R1 = R16 Text 1 (adds the Wi-Fi passphrase, "download mode" for BOOTSEL); R2
    LCSC: `C97521` unused too; R4 says ESP-IDF, not Pico SDK; "Ask first" adds eFuse burns.
13. **Section 13:** 2 (Wi-Fi transport), 3 (also re-associate after an AP restart), 7 (S3 SPI steps),
    9 (Wi-Fi failure lines), 12 (Wi-Fi key too), 14 (espflash flow); add: VBUS peak at most 500 mA
    with TX and capped backlights.
14. **Section 14:** drop PL022, udev unit, QFN-80 rows; add RF range through the bulkhead, VBUS
    budget, module height, NV3007 init by hand.
15. **Section 15:** D1 closed; add: 2.4 GHz network present? static IP for the OBS PC? antenna look?

## Not checked

- No build, no hardware, no RF test. Range through the RP-SMA in a closed case is unknown.
- Hirose U.FL mated height, RP-SMA bulkhead sizes, pigtail length: all MEASURE.
- Current at reduced TX power; IDF RAM use with Wi-Fi up.
- ROM download over USB after `FORCE_DOWNLOAD_BOOT`, and its VID/PID.
- Whether `esp_lcd` shares one SPI host across two panel IO handles without issues.

Risk: the 500 mA budget rests on a firmware cap and two allowances. The antenna hole and notch sit
in a tight back corner. Both need the dev-board and coupon checks before the board order.

## Sources

Espressif, read today:

- `[E1]` ESP32-S3 Series datasheet v2.2, table 2-2, 4.2.1.12, SRAM:
  <https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf>
- `[E2]` ESP32-S3-WROOM-1/1U datasheet v1.8, tables 1-2, 3-1, 4-1, 6-4, 6-6, section 10.2:
  <https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf>
- `[E3]` Flash encryption: <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/security/flash-encryption.html>
- `[E4]` NVS encryption: <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/storage/nvs_encryption.html>
- `[E5]` Secure Boot v2: <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/security/secure-boot-v2.html>
- `[E6]` Component registry API, versions and targets: `espressif/esp_tinyusb` 3.0.1,
  `esp_websocket_client` 1.8.0, `esp_lcd_st7796` 1.5.0, `cjson` 1.7.19~2; search `nv3007` empty:
  <https://components.espressif.com/api/components/espressif/esp_lcd_st7796>
- `[E7]` DevKitC-1 v1.1 user guide, ordering table:
  <https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html>
- `[E8]` Releases: <https://api.github.com/repos/espressif/esp-idf/releases> (v6.1.1, 2026-11-16)
- `[E9]` Host apps: <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/host-apps.html>
- `[E10]` Boot mode: <https://docs.espressif.com/projects/esptool/en/latest/esp32s3/advanced-topics/boot-mode-selection.html>;
  USB OTG console: <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/usb-otg-console.html>
- `[E11]` <https://raw.githubusercontent.com/espressif/esp-idf/v6.1.1/components/soc/esp32s3/register/soc/rtc_cntl_reg.h>
- `[E13]` esp_wifi API v6.1.1: <https://docs.espressif.com/projects/esp-idf/en/v6.1.1/esp32s3/api-reference/network/esp_wifi.html>
- `[E14]` SPI master v6.1.1: <https://docs.espressif.com/projects/esp-idf/en/v6.1.1/esp32s3/api-reference/peripherals/spi_master.html>
- `[E15]` <https://raw.githubusercontent.com/espressif/esp-idf/v6.1.1/components/esp_usb_cdc_rom_console/usb_console.c>,
  <https://raw.githubusercontent.com/espressif/arduino-esp32/master/cores/esp32/esp32-hal-tinyusb.c>
- `[E12]` espflash: <https://crates.io/api/v1/crates/espflash>, <https://github.com/esp-rs/espflash>

Repo: `docs/spec/decisions-v2.md`, `docs/spec/spec-v2.md`, `docs/spec/layout-v2.toml`,
`docs/research/03-connectivity.md` (`[H1]` `[H2]` `[H5]`), `04-mcu-and-firmware-stack.md`,
`07-long-display.md`, `10-electrical-design.md` (`[P2]` `[U1]` `[U2]`), `16-security.md`.
