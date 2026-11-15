// SPDX-License-Identifier: MIT
// GPIO map for macropad-obs. Numbers come from board.toml.
// tools/check_pins.py is the check. GP0 and GP1 are UART0 test pads and are not named here.
#pragma once

#define PIN_KEY_0 2
#define PIN_KEY_1 3
#define PIN_KEY_2 4
#define PIN_KEY_3 5
#define PIN_KEY_4 6
#define PIN_KEY_5 7
#define PIN_KEY_6 8
#define PIN_KEY_7 9
#define PIN_KEY_8 10
#define PIN_KEY_COUNT 9

#define PIN_KNOB_A 12
#define PIN_KNOB_B 13
#define PIN_KNOB_PUSH 11
#define PIN_KNOB_PULSES_PER_DETENT 4

#define PIN_DISP_SCK 18
#define PIN_DISP_MOSI 19
#define PIN_DISP_CS 17
#define PIN_DISP_DC 20
#define PIN_DISP_RESET 21
#define PIN_DISP_BL 22

#define USB_VID 0x1209
#define USB_PID 0x4F42
