#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail if board.toml breaks a pin rule, or if pins.h or the Rust USB ids disagree with it.

`check_pins.py --write` generates pins.h from board.toml. No argument checks and writes nothing.
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS_H = "firmware/esp32s3/main/pins.h"
PROTOCOL_RS = "host/obs_core/src/protocol.rs"
UDEV_RULES = "app/udev/70-macropad-obs.rules"
# ESP32-S3 strapping pins and the one net each may carry ("" = left open). Source:
# docs/spec/spec-v2.md section 7 pin budget; docs/research/18-esp32s3-wifi-delta.md section 2.
STRAPPING = {"IO0": "BOOT", "IO3": "", "IO45": "", "IO46": ""}
UDEV_RULE = 'SUBSYSTEM=="tty", ATTRS{idVendor}=="1209", ATTRS{idProduct}=="4f42", TAG+="uaccess", SYMLINK+="macropad-obs"'
# The ESP32-S3 ROM download port that the pad becomes after BOOTLOADER: Espressif 303a:1001
# (docs/research/18-esp32s3-wifi-delta.md section 8). No symlink: it is not the pad's CDC port.
UDEV_ROM_RULE = 'SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", ATTRS{idProduct}=="1001", TAG+="uaccess"'


def rust_u16(text: str, name: str) -> int:
    match = re.search(rf"{name}:\s*u16\s*=\s*(0x[0-9A-Fa-f]+|\d+)", text)
    if match is None:
        raise SystemExit(f"missing {name} in protocol.rs")
    return int(match.group(1), 0)


def duplicate_errors(gpio: dict[str, int]) -> list[str]:
    nets_on: dict[int, list[str]] = {}
    for net, pin in gpio.items():
        nets_on.setdefault(pin, []).append(net)
    return [f"IO{pin} carries {' and '.join(sorted(nets))}" for pin, nets in sorted(nets_on.items()) if len(nets) > 1]


def strapping_errors(gpio: dict[str, int]) -> list[str]:
    errors = []
    for net, pin in sorted(gpio.items(), key=lambda net_pin: net_pin[1]):
        allowed = STRAPPING.get(f"IO{pin}", net)
        if allowed == "":
            errors.append(f"IO{pin} is a strapping pin and must stay open, not carry {net}")
        elif allowed != net:
            errors.append(f"IO{pin} is a strapping pin for {allowed} only, not {net}")
    return errors


def pin_errors(board: dict) -> list[str]:
    """Every pin rule that the [gpio] and [strapping] tables of board break."""
    errors = duplicate_errors(board["gpio"]) + strapping_errors(board["gpio"])
    if board["strapping"] != STRAPPING:
        errors.append(f"[strapping] must be {STRAPPING!r}, is {board['strapping']!r}")
    return errors


def render_pins_h(board: dict) -> str:
    usb = board["board"]["usb"]
    by_pin = sorted(board["gpio"].items(), key=lambda net_pin: net_pin[1])
    lines = [
        "// SPDX-License-Identifier: MIT",
        "// GPIO map for macropad-obs on the ESP32-S3-WROOM-1-N16R2.",
        "// Generated from board.toml by `python3 tools/check_pins.py --write`. Do not edit.",
        "// IO3, IO45 and IO46 are strapping pins and stay open.",
        "#pragma once",
        "",
        *(f"#define PIN_{net} {pin}" for net, pin in by_pin),
        "",
        "// pid.codes PID is pending: not submitted yet.",
        f"#define USB_VID 0x{usb['vid']:04X}",
        f"#define USB_PID 0x{usb['pid']:04X}",
        "",
        "// Power cap, board.toml [power] (power.c). The backlight cap is MEASURE until S.3.",
        *(f"#define POWER_{key.upper()} {value}" for key, value in board["power"].items()),
    ]
    return "\n".join(lines) + "\n"


def binding_errors(board: dict, pins_h: str, protocol_rs: str) -> list[str]:
    """Every place where a source file disagrees with board."""
    usb = (board["board"]["usb"]["vid"], board["board"]["usb"]["pid"])
    rust_usb = (rust_u16(protocol_rs, "USB_VID"), rust_u16(protocol_rs, "USB_PID"))
    errors = []
    if pins_h != render_pins_h(board):
        errors.append(f"{PINS_H} is not what board.toml generates: run tools/check_pins.py --write")
    if rust_usb != usb:
        errors.append(f"protocol.rs USB: board.toml {usb!r}, source {rust_usb!r}")
    return errors


def main(arguments: list[str]) -> int:
    board = tomllib.loads((ROOT / "board.toml").read_text(encoding="utf-8"))
    errors = pin_errors(board)
    if arguments == ["--write"] and not errors:
        (ROOT / PINS_H).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / PINS_H).write_text(render_pins_h(board), encoding="utf-8")
    elif arguments:
        errors.append("usage: check_pins.py [--write]; --write needs a board.toml that passes the pin rules")
    pins_h = (ROOT / PINS_H).read_text(encoding="utf-8")
    protocol_rs = (ROOT / PROTOCOL_RS).read_text(encoding="utf-8")
    errors += binding_errors(board, pins_h, protocol_rs)
    udev = (ROOT / UDEV_RULES).read_text(encoding="utf-8").strip()
    if udev != f"{UDEV_RULE}\n{UDEV_ROM_RULE}":
        errors.append(f"udev rule {udev!r}")
    print("\n".join(errors) or f"check_pins: {len(board['gpio'])} nets, pins.h and protocol.rs match board.toml")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
