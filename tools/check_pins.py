#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail if pins.h or the Rust USB ids disagree with board.toml."""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def define(text: str, name: str) -> int:
    match = re.search(rf"#define\s+{name}\s+(0x[0-9A-Fa-f]+|\d+)", text)
    if match is None:
        raise SystemExit(f"missing #define {name}")
    return int(match.group(1), 0)


def rust_u16(text: str, name: str) -> int:
    match = re.search(rf"{name}:\s*u16\s*=\s*(0x[0-9A-Fa-f]+|\d+)", text)
    if match is None:
        raise SystemExit(f"missing {name} in protocol.rs")
    return int(match.group(1), 0)


def main() -> int:
    board = tomllib.loads((ROOT / "board.toml").read_text())
    pins = (ROOT / "firmware" / "pins.h").read_text()
    rust = (ROOT / "host" / "src" / "protocol.rs").read_text()
    cmake = (ROOT / "firmware" / "CMakeLists.txt").read_text()
    udev = (ROOT / "app" / "udev" / "70-macropad-obs.rules").read_text().strip()
    keys = board["keys"]["gpio"]
    knob = board["knob"]
    disp = board["display"]
    usb = board["board"]["usb"]
    named = [define(pins, f"PIN_KEY_{n}") for n in range(9)]
    named += [
        define(pins, "PIN_KNOB_A"),
        define(pins, "PIN_KNOB_B"),
        define(pins, "PIN_KNOB_PUSH"),
        define(pins, "PIN_DISP_SCK"),
        define(pins, "PIN_DISP_MOSI"),
        define(pins, "PIN_DISP_CS"),
        define(pins, "PIN_DISP_DC"),
        define(pins, "PIN_DISP_RESET"),
        define(pins, "PIN_DISP_BL"),
    ]
    expect = {
        "key GPIOs": (keys, [define(pins, f"PIN_KEY_{n}") for n in range(9)]),
        "knob A/B/push": (
            [knob["gpio_a"], knob["gpio_b"], knob["gpio_push"]],
            [define(pins, "PIN_KNOB_A"), define(pins, "PIN_KNOB_B"), define(pins, "PIN_KNOB_PUSH")],
        ),
        "pulses": (knob["pulses_per_detent"], define(pins, "PIN_KNOB_PULSES_PER_DETENT")),
        "display": (
            [disp["gpio_sck"], disp["gpio_mosi"], disp["gpio_cs"], disp["gpio_dc"], disp["gpio_reset"], disp["gpio_bl"]],
            [
                define(pins, "PIN_DISP_SCK"),
                define(pins, "PIN_DISP_MOSI"),
                define(pins, "PIN_DISP_CS"),
                define(pins, "PIN_DISP_DC"),
                define(pins, "PIN_DISP_RESET"),
                define(pins, "PIN_DISP_BL"),
            ],
        ),
        "pins.h USB": ((usb["vid"], usb["pid"]), (define(pins, "USB_VID"), define(pins, "USB_PID"))),
        "protocol.rs USB": ((usb["vid"], usb["pid"]), (rust_u16(rust, "USB_VID"), rust_u16(rust, "USB_PID"))),
    }
    bad = [f"{what}: board.toml {want!r}, source {got!r}" for what, (want, got) in expect.items() if want != got]
    if 0 in named or 1 in named:
        bad.append("GP0/GP1 are UART test pads and must not be named in pins.h")
    for needle in ("PICO_BOOTSEL_VIA_DOUBLE_RESET=1", "PICO_BOOTSEL_VIA_DOUBLE_RESET_TIMEOUT_MS=500"):
        if needle not in cmake:
            bad.append(f"CMakeLists.txt missing {needle}")
    rule = 'SUBSYSTEM=="tty", ATTRS{idVendor}=="1209", ATTRS{idProduct}=="4f42", TAG+="uaccess", SYMLINK+="macropad-obs"'
    if udev != rule or "plugdev" in udev or "MODE" in udev:
        bad.append(f"udev rule {udev!r}")
    print("\n".join(bad) or f"check_pins: {len(expect)} checks match board.toml")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
