# 04. Microcontroller and firmware stack

Research only, 2026-11-18. This file is the only file written. An earlier pass was interrupted. This
pass re-read its load-bearing facts, re-ran its build, and changed the order of the two choices (see
"What changed from the earlier draft"). Confidence tags: **verified** (read or run in this pass in the
primary source), **likely** (reasoned from a verified fact, or carried from the earlier pass and not
re-read), **unverified**. Keys such as `[R2]` point into the Sources list. Sizes are from datasheet
tables, except the RM2 outline: its datasheet calls it "approximate", so it is tagged MEASURE (see
"Verification"). No hardware was used.

## Recommendation

**First choice: RP2350B with the Pico SDK 2.3 in C.** Flash is the W25Q128JVSIQ. USB is one TinyUSB
composite device: CDC-ACM for configuration and CDC-NCM for the network. lwIP runs without an RTOS.
The OBS client (WebSocket, streaming JSON, SHA-256) lives in a C core with no SDK headers, and
`just test` keeps building that core with gcc and ASan.

**Second choice: ESP32-S3-WROOM-1-N16R8 with ESP-IDF v6.1 in C and the same core.** Take it if the
owner wants Wi-Fi. For Wi-Fi inside a metal case it is the only part compared here with an antenna
connector, on the WROOM-1U variant.

Next action: the owner answers open question 1 (must Wi-Fi ever work?). "The cable is enough"
confirms the first choice. "Yes" selects the second.

Five findings carry the order.

1. **The first choice builds on this machine today.** CDC-ACM, CDC-NCM, a HID keyboard, lwIP, a DHCP
   server and an outbound TCP connection link into one image for RP2350B, RP2350A and RP2040. The SDK
   and the compiler were already in `~/.platformio`. Nothing for ESP-IDF is installed, and its image
   is a 4.2 GB pull. (verified, build only, `[X1]` `[E10]`)
2. **The owner's reusable work is all on Raspberry Pi chips.** Report 01 rebuilds on the
   `macropad-greycode` PCB generator (RP2040 with a W25Q128 flash) and on the two-display firmware of
   `macropad-nyxilab` (RP2350, a main and a bar panel on two SPI buses). `macropad` adds a generated
   RP2354A board with the regulator-inductor rules coded as checks. (verified in files, `[L3]`;
   likely for the generator, report 01)
3. **RP2350B has the margin in pins and endpoints.** 48 GPIO against 24 to 26 needed, and USB
   endpoints 0 to 15 in each direction (32 in all). The ESP32-S3 module leaves 4 to 6 pins. CDC-ACM plus CDC-NCM uses all five of its IN
   endpoints, so a keyboard interface cannot sit beside them. (verified, `[R2]` `[L1]` `[E1]` `[E2]`)
4. **The network code that ESP-IDF adds is not needed in the port layer.** Report 03 puts the seam at
   a TCP byte stream. Report 05 requires a streaming JSON reader. So the WebSocket client and the JSON
   reader belong in the core on either chip. Measured today: a stream reader takes an 88.6 kB
   `GetInputList` reply in 580 bytes of state; a cJSON tree of the same reply needs 190 kB on a
   32-bit target. (verified by test, `[X2]`)
5. **No Raspberry Pi chip has a radio.** Wi-Fi on the first choice needs the RM2 module: 4 USD, 4
   GPIO, on-board antenna only. That is the price of the first choice and the reason for the second.
   (verified, `[R5]` `[R8]`)

The working reading holds on both choices. The firmware can talk to OBS by itself. It needs a network
path (report 03) and a secret on the device (report 05).

## What changed from the earlier draft

The earlier draft put the ESP32-S3 first. Its part and framework facts were re-read and are kept,
with the corrections below. Its order is not kept.

1. **Order.** The draft did not use reports 03, 05 and 07. Report 03 recommends USB networking with
   no radio and warns that a metal case blocks a module antenna. Reports 05 and 07 remove the two
   needs that favoured the ESP32-S3: a ready WebSocket and JSON stack, and PSRAM for frame buffers.
2. **JSON.** The draft vendored cJSON for parsing. cJSON builds a tree. Report 05 shows no message
   size is bounded. The core now takes a stream reader.
3. **Corrections.** The Pico 2 W datasheet promises availability to January 2028; only the product
   page says 2040 `[R4]` `[R8]`. "RP2040 is out" was too strong: it can run this design without a
   frame buffer, and it loses on margin (see "Why the other Raspberry Pi parts lose"). The claim
   "builds with no install" needs one qualifier: the first build clones picotool from GitHub and
   compiles it `[X1]`.
4. **Experiment.** Redone from scratch, extended with a HID interface and an RP2350B board file.

## The owner's words that drive this topic

- "firmware on the device should be communicating with this websocket OBS url"
- "linux tauri application that can configure this device, to pass websocket url"
- "bidirectional configuration, mapping buttons, configuring the outputs on the displays"
- "3x3 keys matrics, MX switches, also 2 displays one bigger and one longer, also one tray of buttons"

The owner's answers add three encoders with push, four tact buttons, and a big display of about 3.2
to 3.5 inch.

## What the firmware must do

| Need | Fact | Source | Conf. |
| --- | --- | --- | --- |
| Reach OBS | Plain `ws://`, default port 4455, every interface, no TLS | report 03, report 05 | likely (not re-read) |
| Log in | `base64(sha256(base64(sha256(password + salt)) + challenge))`. Also SHA-1 for the upgrade reply | report 05 | likely (not re-read) |
| Parse | JSON text frames. No message size is bounded: 500 inputs give a 107 kB reply | report 05 | likely (not re-read) |
| Draw, big panel | 320 x 480 x 2 = 307,200 bytes. Sent whole: 61 ms at 40 MHz, 39 ms at 62.5 MHz, 31 ms at 80 MHz | arithmetic | verified |
| Draw, long panel | 142 x 428 x 2 = 121,552 bytes, 4-wire SPI | report 07 | likely (not re-read) |

Both frames together are 428,752 bytes.

## Pin budget

The design needs 24 to 26 GPIO.

| Function | Pins |
| --- | --- |
| 4 x 4 matrix: 9 MX keys, 4 tact buttons, 3 encoder pushes | 8 |
| 3 encoders, A and B | 6 |
| SPI clock and data, shared by both panels | 2 |
| 2 chip selects, 1 DC and 1 RESET (both shared), 2 backlight PWM | 6 |
| 2 tearing-effect inputs, optional | 0 to 2 |
| Debug UART | 2 |

| Part | GPIO | Taken before this design | Left | Spare |
| --- | --- | --- | --- | --- |
| RP2350B | 48 | 0. USB, SWD and flash have their own pins | 48 | 22 to 24 |
| RP2350B with RM2 and PSRAM fitted | 48 | 4 for the radio, 1 for the PSRAM chip select | 43 | 17 to 19 |
| RP2040, RP2350A | 30 | 0 | 30 | 4 to 6 |
| Pico 2 W as a module | 26 exposed | 0 | 26 | 0 to 2 |
| ESP32-S3-WROOM-1-N16R8 | 36 pads | 3 for octal PSRAM (IO35 to IO37), 2 for USB (IO19, IO20), 1 for BOOT (IO0) | 30 | 4 to 6 |
| ESP32-S3-WROOM-1-N16R2 | 36 pads | 2 for USB, 1 for BOOT | 33 | 7 to 9 |

Sources: `[R1]` section 1; `[R2]` table 1; `[R4]`; `[R5]` and `[L1]` `boards/pico2_w.h` (power-on,
shared data, clock, chip select); `[E2]` table 3-1 and note b. (all verified)

Two notes on the ESP32-S3 row.

1. Three of its 30 pins are strapping pins: IO3, IO45 and IO46. They are free after reset and must be
   quiet at reset. (verified, `[E2]` table 4-1)
2. When the firmware runs TinyUSB, the built-in USB debug port is gone, because both controllers
   share one PHY. Debug is then UART logs, or JTAG on IO39 to IO42, which takes 4 of the spare pins.
   (verified, `[E4]` `[E2]`)

On RP2350B the spare pins also pay for a second SPI bus (2 more pins). `macropad-nyxilab` gives each
panel its own bus. A shared bus makes a 20 Hz meter on the long panel wait behind a 39 ms frame on
the big one. (verified for the two buses, `[L3]`; likely for the wait)

## Parts compared

| | RP2040 | RP2350A / RP2350B | Pico 2 W module | RM2, added to an RP chip | ESP32-S3-WROOM-1-N16R8 |
| --- | --- | --- | --- | --- | --- |
| Core | 2 x Cortex-M0+, 133 MHz | 2 x Cortex-M33, 150 MHz | as RP2350A | | 2 x Xtensa LX7, 240 MHz |
| GPIO | 30 | 30 / 48 | 26 | costs 4 | 30 usable of 36 |
| RAM | 264 kB | 520 kB | 520 kB | | 512 kB |
| Flash | external, to 16 MB | external, to 16 MB. RP2354A/B: 2 MB inside | 4 MB | | 16 MB inside |
| PSRAM | none | optional, QSPI chip select 1 on GPIO 0, 8, 19 or 47 | none | | 8 MB octal inside |
| SPI master | 62.5 Mb/s (datasheet text) | 70.5 Mb/s (datasheet text; its own divide-by-2 rule gives 75) | same | | 80 MHz on SPI2 |
| USB | full-speed device, endpoints 0 to 15 in and out (32) | same | micro-USB socket on the module | | full-speed device, endpoint 0 plus 6, at most 5 IN counting endpoint 0 |
| ACM + NCM composite | built today, with HID | built today, with HID | as RP2350A | | fits with no IN endpoint left. Not built |
| Radio | none | none | 2.4 GHz Wi-Fi 4 | 2.4 GHz Wi-Fi 4, on-board antenna | 2.4 GHz Wi-Fi 4. 1U variant: antenna connector |
| Size | QFN-56, 7 x 7 mm | QFN-60 7 x 7, QFN-80 10 x 10, 0.4 mm pitch | 21 x 51 mm | about 14.5 x 16.5 x 2.55 mm, MEASURE | 18.0 x 25.5 x 3.1 mm. 1U: 18.0 x 19.2 x 3.2 mm |
| Flash without a debugger | UF2 drive in ROM | UF2 drive in ROM, A/B slots | same | | ROM loader over USB, GPIO0 low at reset |
| Price, one unit | not read today | 1.10 / 1.20 USD. RP2354: 0.20 more | not read today | 4 USD | 3.4 to 6.4 USD (unverified, earlier pass, shop pages) |
| In production until | January 2041 | January 2045 | 2028 (datasheet) or 2040 (product page) | January 2036 | 2033: 12 years from 2021-01-01, for the chip |

Sources: `[R1]` `[R2]` `[R4]` `[R5]` `[R6]` `[R8]` `[E1]` `[E2]` `[E9]` `[E11]` `[L1]` `[X1]`.
(verified unless tagged)

Why the other Raspberry Pi parts lose.

1. **RP2040.** 264 kB cannot hold one 320 x 480 frame (307 kB). It leaves 4 to 6 pins, and 0 to 2
   with the RM2. RP2350B costs 1.20 USD.
2. **RP2350A.** The same chip with 30 GPIO: 4 to 6 spare, 0 to 2 with the RM2. It saves 0.10 USD.
3. **Pico 2 W as a module.** 26 GPIO, 4 MB of flash, and its own micro-USB socket on a 21 x 51 mm
   board that the case would have to reach.

More facts that decide between the two choices.

1. **RP2350 stepping.** Erratum E9 (weak pull-downs) affects stepping A2. Raspberry Pi "ceased
   production of A2", and "A4 is a drop-in replacement". The datasheet lists the fix under stepping
   A3. (verified, `[R2]` appendix C.2.1 and D.5.1, `[R6]`)
2. **RP2350 core supply.** The on-chip regulator wants a polarity-marked 3.3 uH inductor,
   AOTA-B201610S3R3-101-T, placed in one orientation. `macropad/pcb/gen/layout.py` already checks the
   dot and adds the keep-outs. (verified, `[R2]` section 6.3.8, `[R3]`, `[L3]`)
3. **RM2.** "RM2 is exclusively designed for Raspberry Pi microcontrollers", and its driver licence
   allows use "solely with" Raspberry Pi chips. (verified, `[R5]` 1.3.2, `[L1]` `LICENSE.RP`)
4. **ESP32-S3 temperature and current.** N16R8 is rated to 65 °C ambient, N16R2 to 85 °C. With
   PSRAM ECC on, R8 parts reach 85 °C and lose 1/16 of the PSRAM. Wi-Fi
   transmit peaks at 355 mA. (verified, `[E2]`)
5. **ESP32-S3 extras.** Four pulse counters for the three encoders, eight LED PWM channels, an 8080
   LCD port to 40 MHz. (verified, `[E1]`)

Assembly.

- RP2040 is LCSC `C2040` and the flash is `C97521`. Both are on the repo's checked list. (verified,
  `CLAUDE.md`)
- RP2350A and RP2350B: "available via JLCPCB". (verified, `[R7]`, 2025-02-18. Stock today: unverified.
  The LCSC number stays UNVERIFIED under the repo rule.)
- ESP32-S3-WROOM-1-N16R8: JLCPCB lists it as an Extended part. (likely, `[C5]`, a shop page. The LCSC
  number stays UNVERIFIED.)
- PCBWay offers turn-key and consigned assembly and states "we can assemble 0.25mm fine pitch parts".
  QFN-80 is 0.4 mm pitch. (verified for the statement, `[C5]`; part stock unverified)
- `macropad/pcb/fab/` holds JLCPCB and PCBWay BOM and placement files for an RP2354A board. (verified
  that the files exist, `[L3]`; whether a board was ordered is unverified)
- RM2 stock at either house: unverified.

Nothing better was found. Considered and rejected without a datasheet read (unverified): ESP32-C6
and ESP32-C5 (no USB device controller for a composite device), ESP32-P4 (no radio, larger package),
STM32 and nRF52840 (no Wi-Fi, no reuse), a W5500 Ethernet chip (an RJ45 jack on the case, see report
03), and a Linux board such as Pi Zero 2 W (boot time, SD card).

## Frameworks compared

| | Pico SDK 2.3 (C) | ESP-IDF 6.1 (C) | Embassy on RP2350 (Rust) | esp-hal on ESP32-S3 (Rust) | Zephyr 4.5 |
| --- | --- | --- | --- | --- | --- |
| Licence | BSD-3-Clause | Apache-2.0 (likely) | MIT or Apache-2.0 (likely) | MIT or Apache-2.0 | Apache-2.0 (likely) |
| TCP/IP | lwIP 2.2.1 | lwIP, Espressif fork (likely) | embassy-net 0.9.1 | embassy-net | own stack (likely) |
| WebSocket client | none in the SDK. Lives in the core | `esp_websocket_client` 1.8.0, not needed | `embedded-websocket` 0.9.5, `edge-ws` 0.8.0 | same crates | client library |
| JSON | none in the SDK. Stream reader in the core | `espressif/cjson` 1.7.19, a tree parser | `serde-json-core` 0.7.0 | same | not checked |
| ACM + NCM composite | TinyUSB 0.18.0. Built today | `esp_tinyusb` 3.0.1. Both are in its default descriptor. Not built | `embassy-usb` 0.6.0 has `cdc_acm`, `cdc_ncm`, `hid` | USB OTG is "unstable" | classes exist (likely) |
| Wi-Fi | cyw43 driver for the RM2 | in tree | `cyw43` 0.7.0 | `esp-radio` 0.18.0, "unstable" | binary blobs (likely) |
| Docker | repo `Dockerfile` on `ubuntu:24.04`. Never run. Base image not local | `espressif/idf:v6.1.1`, 4.2 GB, not local | none needed | forked compiler by `espup` | not checked |
| Flash without a debugger | UF2 | esptool over the ROM loader | UF2 | ROM loader | per board |
| Host tests | C core with gcc and ASan | same core. The `linux` target is "experimental" | `cargo test`. Could share `obs_core` | `cargo test` | `native_sim` (likely) |
| Built on this machine | yes, today | no | the owner's `macropad` UF2 (HID only) | no | no |

Sources: `[L1]` `[E3]` `[E5]` `[E6]` `[E8]` `[E10]` `[E12]` `[C1]` `[C2]` `[C3]` `[L3]`. (verified
unless tagged; versions read today)

1. **Pico SDK in C: chosen.** It matches the repo's rules as written: a C parser in `firmware/link.c`,
   and firmware logic built with gcc and ASan. The same core moves to ESP-IDF unchanged if the second
   choice is taken.
2. **ESP-IDF in C: second.** It carries the Wi-Fi path, an `esp_netif` with a DHCP server on USB NCM
   (the `sta2eth` example), and settings encrypted with an eFuse HMAC key without flash encryption.
   (verified, `[E7]` `[E3]`) In ESP-IDF 6 the built-in `json` component is gone, `wifi_provisioning`
   is now `network_provisioning`, and Mbed TLS 4 makes PSA Crypto the interface. (verified, `[E8]`)
3. **Embassy on RP2350: sound, not chosen.** The owner's `macropad` ships an `embassy-rp` 0.10
   firmware, and the Rust target is installed here. It could share `obs_core` with the app. It would
   also replace the C parser that `CLAUDE.md` names, and it has no path to the second choice. This is
   open question 5, not a silent pick. (verified, `[L3]` `[L2]` `[C1]`)
4. **esp-hal: rejected.** "You will need to use a fork of the Rust compiler" for Xtensa. USB OTG and
   Wi-Fi are marked unstable. (verified, `[E12]`)
5. **Zephyr: rejected.** It covers both chips, but it brings devicetree, `west` and Wi-Fi blobs for
   one board. No part of this project needs that portability. (likely)

## How the code is split, and how it is tested

1. `firmware/core/`: C11, no SDK headers. The link codec, the matrix and encoder logic, the WebSocket
   client, the OBS session, the config codec and the screen model.
2. The core holds its own SHA-256, SHA-1 and base64. They run a few times per connection. OBS has no
   TLS, so no TLS library is linked.
3. The core reads JSON with a stream reader. LwJSON v1.10.1 (MIT) is the candidate from report 05. Its
   parser stack must hold at least 9 levels for a `GetInputList` reply: a depth of 8 failed in the
   test, 12 passed. (verified, `[X2]`)
4. The port layer is small, one per SDK: TCP connect, send, receive and close (the seam from report
   03), read pins, push pixels, load and save settings, USB serial bytes.
5. `just test` stays gcc, cargo and python3. A POSIX socket behind the same seam lets the whole OBS
   client run on Linux against a real OBS before any board exists.

This split makes the MCU decision cheap to reverse in firmware. The PCB is the part that is not.

## Experiments run in this pass

Both ran in scratch directories outside the repo. The scratch files are temporary.

**`[X1]` Composite USB network build.** A Pico SDK project of about 290 lines: one configuration
with CDC-ACM, CDC-NCM and a HID keyboard; lwIP with `NO_SYS 1`; TinyUSB's `dhserver.c` leasing one
address with no router and no DNS option; a MAC address from the flash unique ID; and a `tcp_connect`
to port 4455 on the lease that sends a WebSocket upgrade request. It uses five IN endpoints besides
endpoint 0. The ESP32-S3 allows four. Built with the local Pico SDK 2.3.0, `arm-none-eabi-gcc` 16.1.0
and Ninja, `MinSizeRel`.

| `PICO_BOARD` | Chip | text | bss |
| --- | --- | --- | --- |
| `pimoroni_pico_plus2_rp2350` | RP2350B, 16 MB flash, PSRAM select on GPIO 47 | 53,032 B | 33,020 B |
| `pico2` | RP2350A | 53,012 B | 33,020 B |
| `pico` | RP2040 | 56,496 B | 33,664 B |

Each image links `cdcd_open`, `netd_open`, `hidd_open`, `dhserv_init` and `tcp_connect`. `picotool`
2.3.0 from `~/.platformio` turned the `pico2` and `pico` ELF files into UF2 files and read them back
as `rp2350-arm-s` and `rp2040`. (verified, build only)

Three things a repeat needs to know. Link `pico_lwip`, `pico_lwip_arch` and `tinyusb_device`, and add
`lib/tinyusb/lib/networking/dhserver.c`. Set `SYS_LIGHTWEIGHT_PROT 0` when one main loop makes every
lwIP call. The first build clones picotool from GitHub and compiles it into the build directory, so
a Docker image should carry picotool. (verified, `[L1]` `tools/Findpicotool.cmake:47`)

What it does not show: the device never enumerated, took no address and reached no OBS.

**`[X2]` JSON readers under the repo's flags.** LwJSON v1.10.1 and cJSON v1.7.19 both compile clean
with `gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined` and run clean. The input is a
synthetic `GetInputList` reply in the server's key order, fed to the stream reader one byte at a time.

| Inputs | Message | Stream reader state (32-bit build) | cJSON tree, peak heap (32-bit build) |
| --- | --- | --- | --- |
| 10 | 1,900 B | 580 B | 4,261 B |
| 100 | 17,830 B | 580 B | 38,461 B |
| 500 | 88,630 B | 580 B | 190,461 B |

The reader was configured for 12 stack levels, 32-byte keys and 64-byte strings. The tree is 2.1
times the message, and the message must also sit in RAM. On a 520 kB chip one large reply would take
more than half of memory. The stream reader found all 500 UUIDs and audio flags. (verified by run;
the reply is a model, not a capture)

## The two network paths

Report 03 owns this subject and recommends USB networking. This table shows only what each MCU adds.

| | Wi-Fi | USB network (CDC-NCM) |
| --- | --- | --- |
| Extra secret on the pad | Wi-Fi passphrase | none |
| OBS on another PC | reachable | not reachable unless the PC routes |
| Metal case | blocks a module antenna | no effect |
| First choice, RP2350B | needs the RM2. No antenna connector | TinyUSB NCM plus lwIP, built today |
| Second choice, ESP32-S3 | built in. WROOM-1U takes an external antenna | `esp_tinyusb` NCM plus an `esp_netif`, not built |

The host firewall blocks port 4455 on either path until one rule is added. (likely, report 03)

## First choice: design notes for `board.toml` and the PCB

1. **MCU and flash.** RP2350B, QFN-80, with the W25Q128JVSIQ. That keeps LCSC `C97521` in use and
   leaves room for stored images. RP2354B (2 MB inside, no flash chip) is the variant with fewer
   parts, and `macropad` used its QFN-60 sibling.
2. **Core supply.** Port the inductor placement, dot check and keep-outs from `macropad/pcb/gen`.
3. **USB.** CDC-ACM plus CDC-NCM in one configuration. A HID keyboard interface fits if the owner
   wants one. BOOTSEL and RUN buttons stay, as in today's `[boot]` table.
4. **Inputs and panels.** Matrix rows on pull-ups, never pull-downs: safe on any stepping. One SPI bus
   per panel if the layout allows.
5. **Two footprints, not fitted at first.** The RM2 at a board edge (4 GPIO; outline MEASURE, the
   datasheet gives only approximate sizes) and a QSPI PSRAM on chip
   select 1 (GPIO 0, 8, 19 or 47, with an external pull-up on its select). `[R2]`

Risks of the first choice.

1. No Wi-Fi without the RM2, and the RM2 has only an on-board antenna. A metal case blocks it.
2. More support parts than a module: a 0.4 mm QFN-80, a crystal, a flash chip, an inductor with an
   orientation. The generator from `macropad` covers QFN-60; the QFN-80 fan-out is new.
3. We write the WebSocket client and the settings store, and Wi-Fi onboarding if the RM2 is fitted.
   The client can be tested on the host; the store is not designed yet.
4. 520 kB of RAM holds one full 320 x 480 frame (307 kB) beside the 33 kB of USB and network state
   in the spike. It does not hold both frames (429 kB). Draw in strips, as `macropad-nyxilab` does,
   or fit the PSRAM.
5. The link is built, not run. Report 03's spike on a dev board is still the first hardware step.

## Second choice: design notes

1. Put nothing on IO35 to IO37. Then N16R8, N16R2 and N8R2 fit one footprint. (verified, `[E2]`)
2. Use the direct SPI2 pins: clock IO12, data IO11, first chip select IO10. (verified, `[E3]`)
3. IO0 is the BOOT button and EN is the reset button. IO46 must be low or floating at reset. Nothing
   may pull IO45 high at reset. (verified for IO0 and IO46, `[E9]`; likely for IO45, `[E2]` table 4-1)
4. Bring UART0 (IO43, IO44) to test pads for logs.
5. Let the antenna end hang over a board edge, or use the WROOM-1U and an external antenna in a metal
   case. (likely, report 03)

Its risks: nothing was built here; no IN endpoint is left for a keyboard beside ACM and NCM (a vendor
interface in place of ACM would free one, and would change the configuration transport); 4 to 6
spare pins; a new toolchain; none of the owner's PCB generator blocks apply.

## Repo rules that meet this choice

Flagged, not decided.

1. **The locked LCSC list.** The first choice keeps `C97521` and stops using `C2040`. RP2350B, its
   crystal and its inductor need numbers. `macropad/pcb/fab/bom-jlcpcb.csv` has candidates. Its crystal
   `C20625731` and inductor `C42411119` are the two that Raspberry Pi links in `[R7]`. Under this
   repo's rule they stay UNVERIFIED until the owner extends the list.
2. **"No OBS password in a CDC frame."** The device must hold a secret to log in by itself. Report 05
   keeps the rule with a salted secret. Neither chip protects a stored secret from a person who holds
   the pad, unless secure boot is also set up. (likely)
3. **`board.toml` says `mcu = "RP2040"`.** That line changes to RP2350B. The `flash` line stays. The
   `tools/check_pins.py` binding to `firmware/pins.h` holds as it is.
4. **"`just test` is gcc ASan, `cargo` in `host/`, and python3."** It holds. The core and LwJSON
   compile under the recipe's flags today.
5. **Licences.** Pico SDK is BSD-3-Clause; TinyUSB and LwJSON are MIT. They sit beside MIT firmware
   without conflict. The cyw43 driver for the RM2 is not MIT: it is licensed for Raspberry Pi chips
   only, which this design satisfies. lwIP carries a BSD-style licence. (verified, `[L1]` `[C4]`)

The four-file protocol rule and "No SK6812" are not touched by this choice.

## Not checked

- No hardware. The composite device never enumerated. NetworkManager and the firewall step are
  report 03's spike.
- No ESP-IDF build. CDC-ACM plus NCM on an ESP32-S3 rests on the descriptor source and the endpoint
  count.
- No Docker build. Running a container was denied in this session, and `ubuntu:24.04` and
  `espressif/idf` are not local.
- Prices and stock today for RP2350B, RP2040, the RM2 and the ESP32-S3 module at JLCPCB and PCBWay.
- The 3.3 V regulator and the USB power budget with two backlights, with or without a radio.
- Zephyr's USB classes, blobs and `native_sim`: carried from the earlier pass. Only its version and
  its WebSocket client were re-read.
- That WROOM-1 and WROOM-1U share one land pattern. (likely)
- The W25Q128JVSIQ behind the RP2350 boot ROM. (likely: the repo already pairs it with RP2040, and a
  16 MB RP2350B board file is in the SDK)

Risk: the first choice has a build behind it and no board. The second has documents behind it and no
build. If the owner wants Wi-Fi in a metal case and the first choice is already on a PCB, the board
must change.

## Sources

Raspberry Pi, read in this pass (PDF text by `pdftotext`):

- `[R1]` RP2040 datasheet, sections 1 and 4.4, appendix C:
  <https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf>
- `[R2]` RP2350 datasheet, release 8: table 1, pin tables in 1.2, bootrom 5.5, regulator 6.3.8,
  SPI 12.3, appendix C.2.1 and D.5.1: <https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf>
- `[R3]` Hardware design with RP2350, release 3, build 2026-08-20:
  <https://datasheets.raspberrypi.com/rp2350/hardware-design-with-rp2350.pdf>
- `[R4]` Pico 2 W datasheet, release 2, build 2026-07-03, appendix A:
  <https://datasheets.raspberrypi.com/picow/pico-2-w-datasheet.pdf>
- `[R5]` Radio Module 2 datasheet, release 7, build 2026-02-20:
  <https://datasheets.raspberrypi.com/rm2/rm2-datasheet.pdf>
- `[R6]` Prices and the A4 stepping, 2025-07-29: <https://www.raspberrypi.com/news/rp2350-a4/>
- `[R7]` JLCPCB availability, 2025-02-18:
  <https://www.raspberrypi.com/news/rp2350-now-available-at-jlcpcb/>
- `[R8]` Product pages: <https://www.raspberrypi.com/products/rp2350/>,
  <https://www.raspberrypi.com/products/radio-module-2/>,
  <https://www.raspberrypi.com/products/raspberry-pi-pico-2/>
- `[R9]` Pico SDK releases (2.3.1, 2026-09-04): <https://github.com/raspberrypi/pico-sdk/releases>

Espressif, read in this pass:

- `[E1]` ESP32-S3 series datasheet v2.2, sections 4.2.1.5, 4.2.1.7 and 4.2.1.12:
  <https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf>
- `[E2]` ESP32-S3-WROOM-1 and 1U datasheet v1.8, ordering tables, table 3-1, table 4-1, current table:
  <https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf>
- `[E3]` ESP-IDF v6.1.1 guides:
  <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/host-apps.html>,
  <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/spi_master.html>,
  <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/usb-serial-jtag-console.html>,
  <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/storage/nvs_encryption.html>
- `[E4]` USB device stack: <https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_device.html>
- `[E5]` `esp_tinyusb` 3.0.1, `usb_descriptors.c`, `Kconfig`, `CHANGELOG.md`, `idf_component.yml`:
  <https://github.com/espressif/esp-usb/tree/master/device/esp_tinyusb>
- `[E6]` WebSocket client:
  <https://docs.espressif.com/projects/esp-protocols/esp_websocket_client/docs/latest/index.html>
- `[E7]` NCM interface example:
  <https://github.com/espressif/esp-idf/blob/v6.1.1/examples/network/sta2eth/main/usb_ncm_iface.c>
- `[E8]` 6.0 migration guides, `protocols.rst`, `provisioning.rst`, `security.rst`:
  <https://github.com/espressif/esp-idf/tree/v6.1.1/docs/en/migration-guides/release-6.x/6.0>
- `[E9]` Boot mode:
  <https://docs.espressif.com/projects/esptool/en/latest/esp32s3/advanced-topics/boot-mode-selection.html>
- `[E10]` Versions and sizes: <https://api.github.com/repos/espressif/esp-idf/releases> (v6.1.1,
  2026-11-16), <https://components.espressif.com/> (component versions),
  <https://hub.docker.com/r/espressif/idf/tags> (v6.1.1, 4.2 GB for amd64)
- `[E11]` Longevity: <https://www.espressif.com/en/products/longevity-commitment>
- `[E12]` Rust: <https://docs.espressif.com/projects/rust/book/getting-started/toolchain.html>,
  <https://github.com/esp-rs/esp-hal/blob/main/esp-hal/README.md>

Other projects, read in this pass:

- `[C1]` Crate versions from the sparse index: <https://index.crates.io/>
- `[C2]` Embassy: <https://github.com/embassy-rs/embassy/tree/main/embassy-usb/src/class>,
  <https://github.com/embassy-rs/embassy/tree/main/examples/rp235x/src/bin>
- `[C3]` Zephyr v4.5.0, 2026-10-28: <https://github.com/zephyrproject-rtos/zephyr/releases>,
  <https://docs.zephyrproject.org/latest/services/connectivity/networking/api/websocket.html>
- `[C4]` LwJSON v1.10.1 (MIT): <https://github.com/MaJerle/lwjson>. cJSON v1.7.19 (MIT):
  <https://github.com/DaveGamble/cJSON>
- `[C5]` Shop and capability pages (weak evidence):
  <https://jlcpcb.com/partdetail/3198300-ESP32_S3_WROOM_1N16R8/C2913202>,
  <https://www.pcbway.com/assembly-capabilities.html>

This machine:

- `[L1]` `~/.platformio/packages/framework-arduinopico/pico-sdk/` (Pico SDK 2.3.0; upstream latest is
  2.3.1 `[R9]`): `pico_sdk_version.cmake`, `LICENSE.TXT`, `lib/tinyusb/src/tusb_option.h` (0.18.0),
  `lib/lwip/src/include/lwip/init.h` (2.2.1), `lib/lwip/COPYING`, `lib/lwip/src/apps/` (no WebSocket),
  `lib/cyw43-driver/LICENSE.RP`, `lib/tinyusb/hw/bsp/rp2040/family.cmake`,
  `lib/tinyusb/lib/networking/dhserver.c`, `tools/Findpicotool.cmake`,
  `src/rp2350/hardware_structs/include/hardware/structs/usb_dpram.h:23`,
  `src/boards/include/boards/pico2_w.h`, `pimoroni_pico_plus2_rp2350.h`
- `[L2]` `~/.platformio/packages/toolchain-rp2040-earlephilhower/` (`arm-none-eabi-gcc` 16.1.0),
  `tool-picotool-rp2040-earlephilhower/` (picotool 2.3.0), `rustup target list --installed`
  (`thumbv8m.main-none-eabihf`), `docker images` (no `espressif/idf`, no `ubuntu`)
- `[L3]` The owner's earlier projects, read only: `/home/worxbend/Projects/macropad/pcb/gen/circuit.py`,
  `layout.py`, `schematic.py`, `pcb/fab/`, `firmware/fw/Cargo.toml`, `firmware/dist/macropad.uf2`;
  `/home/worxbend/Projects/macropad-greycode/board.toml`;
  `/home/worxbend/Projects/macropad-nyxilab/rotary/firmware/platformio.ini`, `include/config.h`
- `[L4]` This repo: `board.toml`, `CLAUDE.md`, `justfile`, `firmware/Dockerfile`,
  `firmware/CMakeLists.txt`, `docs/research/01-prior-art.md`, `02-repo-inventory.md`,
  `03-connectivity.md`, `05-obs-websocket.md`, `07-long-display.md`

Experiments:

- `[X1]` Composite USB network build, described above. `cmake -G Ninja -DPICO_BOARD=<board>
  -DCMAKE_BUILD_TYPE=MinSizeRel` with `PICO_SDK_PATH` and `PICO_TOOLCHAIN_PATH` set to the `[L1]` and
  `[L2]` paths; `arm-none-eabi-size`, `arm-none-eabi-nm`, `picotool uf2 convert`, `picotool info`.
- `[X2]` JSON test, described above. gcc 64-bit with ASan and UBSan for correctness; `gcc -m32` for
  the sizes.

## Open questions

Blocking the MCU decision:

1. Must Wi-Fi ever work, or is the USB cable enough? And is the CNC case metal? "Wi-Fi in a metal
   case" selects the second choice with the WROOM-1U.
2. Should the pad also be a USB keyboard, as `macropad` is? "Yes" rules out CDC-ACM plus CDC-NCM on
   the ESP32-S3.
3. How does the secret reach the pad, given "No OBS password in a CDC frame"? Report 05 lists the
   ways.
4. May the LCSC list gain RP2350B, its crystal and its inductor?

Not blocking:

5. Does the firmware stay C? This report says yes, because `CLAUDE.md` names a C parser. Embassy on
   RP2350 is the alternative and would share `obs_core` with the app.
6. RP2350B with the 16 MB flash, or RP2354B with 2 MB inside and one part fewer?
7. One SPI bus for both panels, or one each?
8. May the build pull `ubuntu:24.04` for the repo's `Dockerfile`, or `espressif/idf:v6.1.1` (4.2 GB)
   for the second choice?
9. JLCPCB or PCBWay? RM2 stock at either is unknown.

## Verification

Skeptic pass, 2026-11-18. Each claim was checked in a primary source opened in this pass (PDFs by
`curl` and `pdftotext`, source files, local SDK files). Verdict: **corrected**. The recommendation
holds. No correction changes the part, the framework or the order.

| # | Claim | Source opened | Result |
| --- | --- | --- | --- |
| 1 | RP2350B: QFN-80, 10 x 10 mm, 48 GPIO, 520 kB SRAM | `[R2]` release 8 (build 01/10/2026), table 1, section 1.2.1.2, figure 149 | verified. Figure 149 adds pitch e = 0.400 BSC, body 10 BSC, ePad 3.40 x 3.40 mm |
| 2 | RP2350/RP2040 USB has "16 endpoints" | `[R2]` USB features list; `[R1]` same list | corrected: "up to 32 endpoints (Endpoints 0 to 15 in both in and out directions)". The margin claim is stronger, not weaker |
| 3 | ESP32-S3 USB: EP0 plus 6, at most 5 IN counting EP0; ACM + NCM leaves no IN endpoint; ACM + NCM + HID does not fit | ESP32-S3 TRM, USB OTG features: "Six additional endpoints", "Maximum of five IN endpoints concurrently active at any time (including EP0 IN)" | verified. ACM uses 2 IN, NCM 2 IN, HID 1 IN: 4 fits, 5 does not |
| 4 | `esp_tinyusb` 3.0.1 has CDC and NCM in its default descriptor | `esp-usb` master `device/esp_tinyusb/usb_descriptors.c`, `idf_component.yml` | verified (`ITF_NUM_CDC`, `ITF_NUM_NET`, version 3.0.1) |
| 5 | ESP32-S3-WROOM-1: 36 GPIO pads, IO35 to IO37 taken by octal PSRAM, N16R8 rated -40 to 65 °C, 18.0 x 25.5 mm | `[E2]` v1.8, tables 1-1, 1-2, 3-1 note b | verified, with two additions: PSRAM ECC raises R8 to 85 °C at 1/16 less PSRAM; WROOM-1U is 18.0 x 19.2 mm, so the "one land pattern" item stays likely |
| 6 | PSRAM chip select 1 on GPIO 0, 8, 19 or 47 | `[R2]` GPIO function table (QMI CS1n) | verified |
| 7 | Erratum E9 affects A2 only, fixed in A3 | `[R2]` appendix C.2.1 and D.5.1 | verified. Pull-ups work on A2; an 8.2 kΩ or stronger pull-down also works |
| 8 | Core regulator wants the polarity-marked 3.3 uH AOTA-B201610S3R3-101-T | `[R2]` section 6.3.8 | verified |
| 9 | RM2: 4 GPIO, on-board antenna only, Raspberry Pi chips only, production to January 2036, 14.5 x 16.5 x 2.55 mm | `[R5]` release 7, table 1, sections 1.3.2, 1.3.4, 2.2 | verified for the pins (23, 24, 25, 29), antenna, exclusivity and lifetime. Size corrected to MEASURE: the datasheet says "approximate dimensions" |
| 10 | SPI master peak: RP2040 62.5 Mb/s, RP2350 70.5 Mb/s; ESP32-S3 80 MHz on SPI2 IO_MUX pins IO10/11/12 | `[R1]` and `[R2]` section 12.3.4.4; ESP-IDF stable `spi_master` page | the numbers are in the datasheets, but each datasheet's own rule (master ratio 2, clk_peri 150 MHz) gives 75 Mb/s for RP2350. Tagged "datasheet text". Not load-bearing: the panel controller limit binds first. ESP32-S3 pins verified; the 80 MHz figure on that page is stated for ESP32 IO_MUX, so likely for S3 |
| 11 | Lifetimes: RP2040 to January 2041, RP2350 to January 2045, Pico 2 W to January 2028, ESP32-S3 12 years from 2021-01-01 | RP2040 and RP2350 product brief PDFs; `[R4]`; `[E11]` | verified. The product web pages were behind a bot check and were not read |
| 12 | Local stack: Pico SDK 2.3.0, TinyUSB 0.18.0, lwIP 2.2.1, `dhserver.c`, `arm-none-eabi-gcc` 16.1.0, RP2350B board file with PSRAM CS 47 and 16 MB flash; upstream ESP-IDF v6.1.1 (2026-11-16), Pico SDK 2.3.1 (2026-09-04) | `[L1]` `[L2]` files; GitHub releases API | verified |
| 13 | obs-websocket auth is `base64(sha256(base64(sha256(password + salt)) + challenge))` | obs-websocket `docs/generated/protocol.md` | verified |
| 14 | `macropad-nyxilab` exists | `ls /home/worxbend/Projects` | verified. The owner's "nixylab" is this folder spelled "nyxilab" |

Not re-checked by the skeptic: `[X1]` and `[X2]` were not re-run (their scratch files are gone), so
the image sizes and the JSON memory figures rest on the researcher's run. Prices were not checked.

Against the owner's requirements and the sketch:

1. Inputs. 9 MX keys, 4 tact buttons and 3 encoder pushes are 16 switches in a 4 x 4 matrix, plus
   6 encoder pins. The pin budget covers them on all parts; RP2350B has the largest margin. Holds.
2. Two displays. One 320 x 480 frame (307 kB) fits RP2350's 520 kB; both frames (429 kB) do not.
   Strip drawing or the PSRAM footprint covers it. Holds.
3. "firmware on the device should be communicating with this websocket OBS url". Holds on USB NCM
   only when OBS runs on the PC the pad is plugged into, or that PC routes. A URL such as
   `ws://127.0.0.1:4455` typed in the app means the host, not the pad: the firmware must map it to
   the host side of the USB link. This is a gap for report 03 and the app, not for the MCU choice.
4. Tauri bidirectional configuration over CDC-ACM. Holds; ACM sits beside NCM on every part checked.
5. "No OBS password in a CDC frame" still conflicts with a pad that logs in by itself. Flagged above
   (rule 2, open question 3); not decided here.

Recommendation after the check: unchanged. RP2350B (QFN-80, 0.4 mm pitch) with the W25Q128JVSIQ and
Pico SDK 2.3 in C; TinyUSB CDC-ACM + CDC-NCM; lwIP `NO_SYS`; WebSocket client and stream JSON reader
in an SDK-free C core. ESP32-S3-WROOM-1(U)-N16R8 with ESP-IDF v6.1 only if Wi-Fi must work, and then
without a HID interface beside ACM + NCM.
