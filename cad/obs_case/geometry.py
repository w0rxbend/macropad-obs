# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Wedge case solids.

The top face is one plane at face_tilt_deg. Keys, the knob, and the glass
are flush on that face. The base bottom is flat on the desk.

Face frame, before the tilt: origin at the outer front-left corner, +x
right, +y toward the USB edge, z = 0 on the top face, negative z into the
case. build123d is imported only when a build is asked for.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# plate_web from board.toml is the key-plate thickness. The glass is thicker
# than that web, so it is its own solid and hangs below the plate.
MX_CUT_MM = 14.0
GLASS_THICK_MM = 2.25  # datasheet typical. The pocket depth is the maximum.
ACTIVE_MM = (36.72, 48.96)
USB_SLOT_MM = (14.0, 7.0)  # MEASURE: plug body, not a datasheet of this case
BUTTON_HOLE_MM = 4.0
SCREW_HOLE_MM = 3.4
KNOB_HEIGHT_MM = 16.0


def load_board() -> dict:
    return tomllib.loads((ROOT / "board.toml").read_text())


def _grow(case: dict) -> float:
    return case["wall"] + case["pcb_clearance"]


def _spans(board: dict) -> tuple[float, float]:
    grow = _grow(board["case"])
    pcb = board["pcb"]
    return pcb["width"] + 2 * grow, pcb["depth"] + 2 * grow


def build_parts(board: dict | None = None) -> dict:
    """Named solids in the desk frame. Keys are top, base, glass, and knob."""
    from build123d import Pos, Rot

    board = board or load_board()
    case = board["case"]
    span_x, span_y = _spans(board)
    top = _top(board, span_x, span_y)
    glass = _glass(board, span_x, span_y)
    knob = _knob(board)
    place = Pos(0, 0, case["face_front_z"]) * Rot(case["face_tilt_deg"], 0, 0)
    base = _base(board, place * _skin(span_x, span_y, case["plate_web"]))
    return {
        "top": place * top,
        "base": base,
        "glass": place * glass,
        "knob": place * knob,
    }


def _skin(span_x: float, span_y: float, thickness: float):
    from build123d import Box, Pos

    return Pos(span_x / 2, span_y / 2, -thickness / 2) * Box(span_x, span_y, thickness)


def _rounded(span_x: float, span_y: float, radius: float, thickness: float):
    from build123d import BuildPart, BuildSketch, Locations, Plane, RectangleRounded, extrude

    with BuildPart() as part:
        with BuildSketch(Plane.XY):
            with Locations((span_x / 2, span_y / 2)):
                RectangleRounded(span_x, span_y, radius)
        extrude(amount=-thickness)
    return part.part


def _cut(solid, x: float, y: float, width: float, height: float, depth: float):
    """Cut a rectangular opening through the plate from the top face."""
    from build123d import Box, Pos

    tool = Pos(x + width / 2, y + height / 2, -depth / 2) * Box(width, height, depth + 0.4)
    return solid - tool


def _top(board: dict, span_x: float, span_y: float):
    case = board["case"]
    plate = _rounded(span_x, span_y, min(case["corner_radius"], 10.0), case["plate_web"])
    grow = _grow(case)
    for key_x in board["pcb"]["key_x"]:
        for key_y in board["pcb"]["key_y"]:
            plate = _cut(plate, key_x + grow - MX_CUT_MM / 2, key_y + grow - MX_CUT_MM / 2, MX_CUT_MM, MX_CUT_MM, case["plate_web"])
    pocket_x, pocket_y = _pocket_origin(board, grow)
    pocket_w, pocket_h = case["pocket_plan"]
    plate = _cut(plate, pocket_x, pocket_y, pocket_w, pocket_h, case["plate_web"])
    knob_x, knob_y = board["pcb"]["knob"]
    pocket = case["encoder_pocket"][0]
    plate = _cut(plate, knob_x + grow - pocket / 2, knob_y + grow - pocket / 2, pocket, pocket, case["plate_web"])
    return plate


def _pocket_origin(board: dict, grow: float) -> tuple[float, float]:
    glass_x, glass_y = board["pcb"]["display_origin"]
    glass_w, glass_h = board["pcb"]["display_size"]
    pocket_w, pocket_h = board["case"]["pocket_plan"]
    return glass_x + grow - (pocket_w - glass_w) / 2, glass_y + grow - (pocket_h - glass_h) / 2


def _glass(board: dict, span_x: float, span_y: float):
    from build123d import Box, Pos

    del span_x, span_y
    grow = _grow(board["case"])
    origin_x, origin_y = board["pcb"]["display_origin"]
    width, height = board["pcb"]["display_size"]
    return Pos(origin_x + grow + width / 2, origin_y + grow + height / 2, -GLASS_THICK_MM / 2) * Box(
        width, height, GLASS_THICK_MM
    )


def _knob(board: dict):
    from build123d import Cylinder, Pos

    grow = _grow(board["case"])
    knob_x, knob_y = board["pcb"]["knob"]
    radius = board["case"]["knob_diameter"] / 2
    return Pos(knob_x + grow, knob_y + grow, KNOB_HEIGHT_MM / 2) * Cylinder(radius, KNOB_HEIGHT_MM)


def _base(board: dict, skin):
    """Wedge under the skin. Bottom is z = 0. Walls and floor stay."""
    case = board["case"]
    pcb = board["pcb"]
    span_x = skin.bounding_box().size.X
    # The tilted skin's horizontal footprint is shorter than the face length.
    face_y = _spans(board)[1]
    desk_y = face_y  # generous; the intersection with the skin extrusion trims it
    tilt = case["face_tilt_deg"]
    blank = _wedge_blank(board, span_x, desk_y)
    base = blank - skin
    grow = _grow(case)
    cavity = _cavity(board, grow)
    base = base - cavity
    base = _usb_slot(base, board, grow)
    for name in ("boot", "reset"):
        base = _floor_hole(base, pcb[name][0] + grow, pcb[name][1] + grow, BUTTON_HOLE_MM, case, tilt)
    for hole_x, hole_y in pcb["holes"]:
        base = _floor_hole(base, hole_x + grow, hole_y + grow, SCREW_HOLE_MM, case, tilt)
    return base


def _wedge_blank(board: dict, span_x: float, face_y: float):
    """Material from the top face down to the desk, before the skin is removed."""
    from build123d import Box, Pos, Rot

    case = board["case"]
    tilt = case["face_tilt_deg"]
    # A deep extrusion of the face, then keep only z >= 0.
    deep = _skin_box(span_x, face_y, 80.0)
    placed = Pos(0, 0, case["face_front_z"]) * Rot(tilt, 0, 0) * deep
    floor = Pos(span_x / 2, face_y / 2, 40.0) * Box(span_x + 40, face_y + 40, 80.0)
    wedge = placed & floor
    # Inset the outer wall by the shadow gap so the top plate overhangs.
    gap = case["shadow_gap"]
    inset = Pos(span_x / 2, face_y / 2, 30.0) * Box(span_x - 2 * gap, face_y - 2 * gap, 60.0)
    return wedge & inset


def _skin_box(span_x: float, span_y: float, thickness: float):
    from build123d import Box, Pos

    return Pos(span_x / 2, span_y / 2, -thickness / 2) * Box(span_x, span_y, thickness)


def _cavity(board: dict, grow: float):
    """PCB bay. Starts just under the top face and stops at the floor."""
    from build123d import Box, Pos, Rot

    case = board["case"]
    pcb = board["pcb"]
    span_x, span_y = _spans(board)
    wall = case["wall"]
    # Inner opening in the face frame, from just under the plate web to deep.
    width = pcb["width"] + 2 * case["pcb_clearance"]
    depth = pcb["depth"] + 2 * case["pcb_clearance"]
    local = Pos(grow - case["pcb_clearance"] + width / 2, grow - case["pcb_clearance"] + depth / 2, -40) * Box(
        width, depth, 70
    )
    placed = Pos(0, 0, case["face_front_z"]) * Rot(case["face_tilt_deg"], 0, 0) * local
    floor_block = Pos(span_x / 2, span_y / 2, case["floor"] / 2) * Box(span_x, span_y, case["floor"])
    # Keep the floor by not subtracting it: cut the cavity above the floor only.
    above = Pos(span_x / 2, span_y / 2, case["floor"] + 40) * Box(span_x + 10, span_y + 10, 80)
    del wall
    return (placed & above) - floor_block


def _usb_slot(base, board: dict, grow: float):
    from build123d import Box, Pos, Rot

    case = board["case"]
    pcb = board["pcb"]
    span_y = _spans(board)[1]
    width, height = USB_SLOT_MM
    # Centre the slot on the USB mouth, on the back edge, in the face frame,
    # then tilt it with the case so the opening follows the back face.
    local_x = pcb["usb_x"] + grow
    local = Pos(local_x, span_y, -case["plate_above_pcb"]) * Box(width, 16.0, height)
    placed = Pos(0, 0, case["face_front_z"]) * Rot(case["face_tilt_deg"], 0, 0) * local
    return base - placed


def _floor_hole(base, face_x: float, face_y: float, diameter: float, case: dict, tilt: float):
    """Vertical hole through the flat floor under a face-frame point."""
    import math

    from build123d import Pos, Rot, Cylinder

    radians = math.radians(tilt)
    # Point on the top face. The floor hole uses that plan position.
    desk_y = face_y * math.cos(radians)
    tool = Pos(face_x, desk_y, case["floor"] / 2) * Rot(0, 0, 0) * Cylinder(diameter / 2, case["floor"] + 0.4)
    return base - tool
