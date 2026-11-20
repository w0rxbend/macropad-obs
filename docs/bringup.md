# Bring-up

The first assembled board, checked in order. Stop at the first fail, write down the value, and take
it to the owner. Every result goes into the hardware record, docs/hardware.md, with the value, the
method and the date (Phase 8 of `tasks/todo.md`; task H.2 creates the file). Nothing below has been
run: no board exists (pending H.1, H.2).

Order and pass values: the spec 11 bring-up row (`docs/spec/spec-v2.md`), which adapts the R15
checklist (`docs/research/15-verification-strategy.md`, "Bring-up checklist for the first hardware")
to the ESP32-S3. R15's own list still names the steps of the dropped MCU (BOOTSEL drive, UF2, SWD,
CDC-NCM); the spec row replaces them.

## Before you start

- A board that passed `just gate` exit 0 on the commit ordered (task H.1). Today `just gate` exits 1
  with 18 open MEASURE tags (README status), so no board exists to bring up.
- A bench supply with a current limit, a multimeter, a 3.3 V USB-UART adapter for the debug JST
  (`board.toml` `[gpio]` UART0 TX IO43, RX IO44; spec 6: JST SM03B-SRSS-TB, 499 Ω series), and a USB
  power meter or a VBUS shunt.
- The udev rule installed once (`app/udev/70-macropad-obs.rules`; README "udev"): the app port
  1209:4f42 and the ROM port 303a:1001.
- An image from `just firmware`: `.build/esp32s3/macropad-obs-merged.bin` (justfile `firmware`).

## Checklist

| # | Step | Pass | Source |
| --- | --- | --- | --- |
| 1 | Unpowered: ohmmeter VBUS to GND and 3V3 to GND | no short on either rail | spec 11 bring-up row |
| 2 | Bench 5 V on VBUS, 100 mA limit; measure 3V3 at the module | 3.3 V +/- 3 % (3.201 to 3.399 V, arithmetic); the supply does not sit at its limit | spec 11 bring-up row |
| 3 | UART0 on the debug JST, power up | the ROM boot log prints | spec 11 bring-up row; spec 7 pin budget (IO43/IO44 boot log); `firmware/esp32s3/sdkconfig.defaults` `CONFIG_ESP_CONSOLE_UART_DEFAULT=y` (IDF default baud rate, not set here) |
| 4 | Hold BOOT (IO0), tap RESET (EN), USB to the PC | `lsusb` lists 303a:1001 (ROM port) | spec 11 bring-up row; spec 8.2 `BOOTLOADER` ("Expect 303a:1001") |
| 5 | `just flash /dev/ttyACM0` (the ROM port's tty), then RESET | `lsusb` lists 1209:4f42, one CDC-ACM port; the UART log prints the boot line of `firmware/esp32s3/main/main.c` (project, version, link protocol, reset reason) and the free-RAM line | spec 11 bring-up row; justfile `flash`; spec 8.1 |
| 6 | Each panel draws the test pattern | both panels show it, no shifted or torn band | spec 11 bring-up row |
| 7 | Press every key, button and knob push; turn each knob both ways | each reports one `INPUT` frame with the right `source` and `index` (`docs/protocol.md` "INPUT") | spec 11 bring-up row |
| 8 | Write the SSID in the document and the passphrase with `SET_CREDENTIAL` | `STATUS` Wi-Fi state `up`, with RSSI and the pad's IP | spec 11 bring-up row; spec 8.2 `STATUS` |
| 9 | USB power meter in VBUS, Wi-Fi TX and both backlights at the firmware cap | VBUS peak at or under 500 mA | spec 11 bring-up row; spec 13 criterion 15 |
| 10 | Power from a charger, no host | Wi-Fi `up` after the 2 s enumeration wait, backlights at the cap | spec 11 bring-up row; `board.toml` `[power]` `enumeration_wait_ms = 2000` |

## Gaps the tree has today

Each one blocks or weakens a step above. None is fixed here.

- Step 6: no test-pattern image is in the tree (`grep -rni pattern firmware/` finds no such mode).
  The panel init tables are unverified until S.3: `firmware/esp32s3/main/lcd_port.c` logs
  "init table unverified until S.3" for each panel. Pending S.3, H.2.
- Step 7: no host tool reads `INPUT` frames from a real port. The app's press-to-select is task 3.7,
  not done. Pending 3.7 or a script over `host/obs_core/src/protocol.rs`.
- Step 8: the app pages that write the SSID and the secrets are task 3.8, not done. Pending 3.8.
- Step 9: the backlight cap is `board.toml` `[power]` `backlight_cap_permille = 600`, MEASURE: report
  18 arithmetic, not a measured 3V3 current. Pending S.3, then H.8.
- f_bus: the SPI clock is the provisional 13.3 MHz (80 MHz / 6) until S.3 (task 4.6 status;
  `firmware/esp32s3/main/lcd_port.c` logs the requested and actual clock). Pending S.3, H.7.

## After the checklist

The criteria that need the board come after a clean pass, each in its own task card:
criterion 2 (H.3), 3 (H.4, 4.8), 5 (H.5), 6 (H.6), 7 (H.7), 15 (H.8), the manual row (H.9), and the
case fit and RF checks (H.10, H.11). The dev kit acceptance (4.8) can run before any board: it needs
only the DevKitC-1 (pending 4.8).
