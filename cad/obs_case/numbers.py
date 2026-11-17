# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Desk-frame numbers. Importing this module does not import build123d."""

from __future__ import annotations

import math
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# One ISO 10642 M2x10 at every hole. The head seat is this far below the PCB
# top along the face normal, so the tip stops after M2_THREAD_MM in the standoff.
# A head on the outer skin cannot be one length: the back mouth is much farther.
M2_LENGTH_MM = 10.0
M2_THREAD_MM = 3.0
M2_CLEARANCE_MM = 2.4
M2_TAP_MM = 1.6
M2_TAP_DEPTH_MM = 3.5
M2_DRILL_POINT_MM = 0.48  # 118 degree point on the 1.6 mm tap drill
BOSS_DIAMETER_MM = 4.6  # neck inside the keep-out, up to the PCB
BOSS_ROOT_MM = 8.0  # below the head seat, so the 5 mm access leaves a wall
STANDOFF_DIAMETER_MM = 4.0
COUNTERSINK_DIAMETER_MM = 4.0
COUNTERSINK_RECESS_MM = 1.1
COUNTERSINK_SEAT_MM = 0.8  # 90 degrees, dia 4.0 down to the 2.4 clearance
ACCESS_DIAMETER_MM = 5.0
FOOT_DIAMETER_MM = 8.4  # MEASURE, 8 mm bumper
FOOT_DEPTH_MM = 0.6
FOOT_EDGE_MM = 8.0
FOOT_SPAN_MM = 44.0
USB_OPENING_MM = (14.0, 7.0)  # MEASURE, clears a 12.4 x 6.5 plug
USB_RECEPTACLE_MM = (8.94, 7.35, 3.26)  # width, length, height. MEASURE
USB_LEAD_MM = (18.0, 9.2, 2.2)  # wider mouth, same axis. Depth stays outside the tunnel.
USB_TUNNEL_MM = 10.0
SCOOP_RADIUS_MM = 6.0
SCOOP_DEPTH_MM = 1.0  # bite past the shadow-gap wall. Leaves the 3.2 mm cavity wall.
SCOOP_LENGTH_MM = 56.0
SCOOP_Z_MM = 9.0  # desk frame. The cylinder stays above the 2.4 mm floor.
GROOVE_COUNT = 36
GROOVE_DEPTH_MM = 0.7
GROOVE_HALF_MM = 0.65  # at the 22 mm cylinder. A 90 degree V at this depth erases the lands.
GROOVE_PAST_MM = 0.2  # the flute runs past the cylinder so the cut does not kiss it
MIN_THREAD_MM = 2.0
MIN_WALL_MM = 1.0
MIN_SKIN_MM = 1.0  # metal left under the key plane past the screw tip


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


def screw_plan(board: dict) -> list[dict]:
    """Face-frame seat for each M2. ``mouth`` is where the axis meets the desk."""
    case = board["case"]
    pcb = board["pcb"]
    grow = case["wall"] + case["pcb_clearance"]
    tilt = math.radians(case["face_tilt_deg"])
    pcb_top = -case["plate_above_pcb"]
    seat = pcb_top - (M2_LENGTH_MM - M2_THREAD_MM)
    rows = []
    for hole_x, hole_y in pcb["holes"]:
        y = hole_y + grow
        mouth = -(case["face_front_z"] + y * math.sin(tilt)) / math.cos(tilt)
        rows.append(
            {
                "x": hole_x + grow,
                "y": y,
                "mouth": mouth,
                "seat": seat,
                "tip": seat + M2_LENGTH_MM,
                "pcb_top": pcb_top,
                "pcb_bottom": pcb_top - pcb["thickness"],
            }
        )
    return rows


def foot_plan(board: dict) -> list[tuple[float, float]]:
    """Desk-frame centres. The pockets are vertical, because the base is flat."""
    case = board["case"]
    pcb = board["pcb"]
    grow = case["wall"] + case["pcb_clearance"]
    span_x = pcb["width"] + 2 * grow
    span_y = pcb["depth"] + 2 * grow
    desk = span_y * math.cos(math.radians(case["face_tilt_deg"]))
    middle = span_x / 2
    xs = (middle - FOOT_SPAN_MM / 2, middle + FOOT_SPAN_MM / 2)
    ys = (FOOT_EDGE_MM, desk - FOOT_EDGE_MM)
    return [(x, y) for y in ys for x in xs]


def _mouth_desk(row: dict, tilt: float) -> tuple[float, float]:
    return (row["x"], row["y"] * math.cos(tilt) - row["mouth"] * math.sin(tilt))


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
    problems.extend(_fastener_problems(board))
    return problems


def _fastener_problems(board: dict) -> list[str]:
    case = board["case"]
    pcb = board["pcb"]
    problems = []
    keepout = pcb["hole_keepout_diameter"]
    if BOSS_DIAMETER_MM >= keepout or STANDOFF_DIAMETER_MM >= keepout:
        problems.append("boss or standoff leaves the keep-out")
    boss_wall = (BOSS_DIAMETER_MM - M2_CLEARANCE_MM) / 2
    root_wall = (BOSS_ROOT_MM - ACCESS_DIAMETER_MM) / 2
    standoff_wall = (STANDOFF_DIAMETER_MM - M2_TAP_MM) / 2
    if min(boss_wall, root_wall, standoff_wall) < MIN_WALL_MM:
        problems.append(f"fastener wall {boss_wall:.2f} / {root_wall:.2f} / {standoff_wall:.2f}")
    if len(pcb["holes"]) != 4:
        problems.append("screw count")
    tilt = math.radians(case["face_tilt_deg"])
    need = FOOT_DIAMETER_MM / 2 + ACCESS_DIAMETER_MM / 2 + 1.0
    feet = foot_plan(board)
    for row in screw_plan(board):
        engagement = row["tip"] - row["pcb_top"]
        skin = -row["tip"]
        if engagement < MIN_THREAD_MM or skin < MIN_SKIN_MM:
            problems.append(f"screw at y {row['y']:.1f} engagement {engagement:.2f} skin {skin:.2f}")
        if row["seat"] <= row["mouth"]:
            problems.append("screw seat is outside the case")
        mouth = _mouth_desk(row, tilt)
        for foot in feet:
            gap = math.hypot(mouth[0] - foot[0], mouth[1] - foot[1])
            if gap < need:
                problems.append(f"foot hits a screw access ({gap:.2f})")
    opening_w, opening_h = USB_OPENING_MM
    plug_w, plug_h = 12.4, 6.5
    if opening_w <= plug_w or opening_h <= plug_h:
        problems.append("usb opening does not clear the plug")
    problems.extend(_silhouette_problems(board))
    return problems


def _silhouette_problems(board: dict) -> list[str]:
    """Scoops, the USB mouth, and the dial lands. No solids."""
    case = board["case"]
    pcb = board["pcb"]
    problems = []
    grow = case["wall"] + case["pcb_clearance"]
    span_y = pcb["depth"] + 2 * grow
    cavity_x = case["wall"]
    reach = case["shadow_gap"] + SCOOP_DEPTH_MM
    # Both long sides match. The cavity starts at x = wall.
    side_wall = cavity_x - reach
    if side_wall < MIN_WALL_MM:
        problems.append(f"scoop leaves {side_wall:.2f} mm of side wall")
    if SCOOP_Z_MM - SCOOP_RADIUS_MM <= case["floor"]:
        problems.append("scoop breaks the floor")
    desk = span_y * math.cos(math.radians(case["face_tilt_deg"]))
    centre_y = desk * 0.52
    half = SCOOP_LENGTH_MM / 2
    for foot_x, foot_y in foot_plan(board):
        if abs(foot_y - centre_y) < half + FOOT_DIAMETER_MM / 2:
            problems.append(f"scoop hits a foot at y {foot_y:.1f}")
        if foot_x - FOOT_DIAMETER_MM / 2 < reach:
            problems.append("scoop hits a foot in x")
    boss_x = min(hole[0] for hole in pcb["holes"]) + grow - BOSS_ROOT_MM / 2
    if boss_x - reach < MIN_WALL_MM:
        problems.append(f"scoop meets a boss ({boss_x - reach:.2f} mm)")
    lead_w, lead_h, lead_d = USB_LEAD_MM
    opening_w, opening_h = USB_OPENING_MM
    if lead_w <= opening_w or lead_h <= opening_h or lead_d >= USB_TUNNEL_MM or lead_d <= 0:
        problems.append("usb lead-in is not a shallow mouth")
    centre_z = -(case["plate_above_pcb"] + pcb["thickness"] + pcb["usb_centre_from_pcb"])
    if centre_z + lead_h / 2 >= -case["plate_web"]:
        problems.append("usb lead-in opens the plate")
    pitch = 2 * math.pi * (case["knob_diameter"] / 2) / GROOVE_COUNT
    if GROOVE_DEPTH_MM <= 0 or 2 * GROOVE_HALF_MM + 0.4 >= pitch:
        problems.append("knob flutes erase the lands")
    return problems
