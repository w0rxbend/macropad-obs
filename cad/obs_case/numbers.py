# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Desk-frame numbers. Importing this module does not import build123d."""

from __future__ import annotations

import math
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_board() -> dict:
    return tomllib.loads((ROOT / "board.toml").read_text())


def metrics(board: dict) -> dict:
    case = board["case"]
    pcb = board["pcb"]
    grow = case["wall"] + case["pcb_clearance"]
    span_x = pcb["width"] + 2 * grow
    span_y = pcb["depth"] + 2 * grow
    tilt_deg = case["face_tilt_deg"]
    tilt = math.radians(tilt_deg)
    rise = span_y * math.sin(tilt)
    desk = span_y * math.cos(tilt)
    usb_n = case["plate_above_pcb"] + pcb["thickness"] + pcb["usb_centre_from_pcb"]
    usb_s = grow + pcb["depth"]
    usb_z = case["face_front_z"] + usb_s * math.sin(tilt) - usb_n * math.cos(tilt)
    front_n = case["plate_above_pcb"] + pcb["thickness"]
    front_z = case["face_front_z"] + grow * math.sin(tilt) - front_n * math.cos(tilt)
    knob_x, knob_y = pcb["knob"]
    key_x = pcb["key_x"][2]
    key_y = pcb["key_y"][1]
    knob_gap = math.hypot(knob_x - key_x, knob_y - key_y)
    glass_tilt = tilt_deg
    key_tilt = tilt_deg
    flush = case["pocket_depth"] - 2.35
    return {
        "grow": grow,
        "span_x": span_x,
        "span_y": span_y,
        "tilt_deg": tilt_deg,
        "glass_tilt": glass_tilt,
        "key_tilt": key_tilt,
        "rise": rise,
        "desk": desk,
        "back_z": case["face_front_z"] + rise,
        "usb_z": usb_z,
        "front_z": front_z,
        "knob_gap": knob_gap,
        "flush": flush,
        "window": tuple(pcb["display_size"]),
        "pocket": (case["pocket_plan"][0], case["pocket_plan"][1], case["pocket_depth"]),
        "coplanar": glass_tilt == key_tilt == tilt_deg,
    }


def check(board: dict | None = None) -> list[str]:
    board = board or load_board()
    got = metrics(board)
    case = board["case"]
    pcb = board["pcb"]
    problems = []

    def near(name: str, value: float, expect: float, tol: float) -> None:
        if abs(value - expect) > tol:
            problems.append(f"{name}: {value:.4f} expected {expect:.4f}")

    near("tilt", got["tilt_deg"], 8.0, 0.05)
    near("window normal vs keys", abs(got["glass_tilt"] - got["key_tilt"]), 0.0, 0.05)
    near("tft flush", got["flush"], 0.0, 0.05)
    near("span x", got["span_x"], 95.2, 0.01)
    near("span y", got["span_y"], 157.2, 0.01)
    near("rise", got["rise"], 21.88, 0.01)
    near("desk", got["desk"], 155.67, 0.01)
    near("back z", got["back_z"], 33.88, 0.01)
    near("usb z", got["usb_z"], 25.26, 0.01)
    near("front pcb z", got["front_z"], 5.97, 0.01)
    if got["window"] != (42.72, 60.26):
        problems.append(f"window outline {got['window']}")
    if got["pocket"] != (43.22, 60.76, 2.35):
        problems.append(f"pocket {got['pocket']}")
    if got["window"] == got["pocket"][:2]:
        problems.append("window used the pocket size")
    knob_r = case["knob_diameter"] / 2
    if got["knob_gap"] <= knob_r + case["keycap"] / 2:
        problems.append("knob hits a keycap")
    if got["knob_gap"] <= knob_r + case["switch_housing"] / 2:
        problems.append("knob hits a switch housing")
    body = case["encoder_body"][0]
    pocket = case["encoder_pocket"][0]
    if body > pocket:
        problems.append("encoder body does not fit the pocket")
    if not got["coplanar"]:
        problems.append("glass is not coplanar with the keys")
    if pcb["mx_rotation_deg"] != 0:
        problems.append("mx rotation")
    if tuple(pcb["key_x"]) != (20.00, 39.05, 58.10):
        problems.append("key_x")
    if tuple(pcb["knob"]) != (79.6, 42.95):
        problems.append("knob")
    if tuple(pcb["display_origin"]) != (22.64, 82.0):
        problems.append("glass origin")
    text = (ROOT / "board.toml").read_text()
    for tag in (
        "pulses_per_detent",
        "fpc_edge",
        "bushing_hole",
        "encoder_pocket",
        "knob_lift",
        "keycap",
        "switch_housing",
        "encoder_body",
        "tact_body_mm",
    ):
        line = next(item for item in text.splitlines() if item.strip().startswith(tag))
        if "MEASURE" not in line:
            problems.append(f"{tag} lost its MEASURE tag")
    header = (ROOT / "firmware" / "st7789.h").read_text()
    if "MADCTL" not in header or "MEASURE" not in header:
        problems.append("MADCTL MEASURE")
    return problems
