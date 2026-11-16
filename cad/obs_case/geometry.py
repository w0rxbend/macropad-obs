# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Wedge case solids.

The key plane is one face at face_tilt_deg. Keys and the glass are flush on
that plane. One dish rises above it. The base bottom is flat on the desk.

Face frame, before the tilt: origin at the outer front-left corner, +x
right, +y toward the USB edge, z = 0 on the key plane, negative z into the
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

# Quintic corner of the 95.2 by 157.2 box. The first three controls on a side
# are colinear, so curvature is zero where the curve meets the straight.
# Distances from the corner, along that side. corner_radius is not this.
CORNER_HANDLES_MM = (10.935, 6.561, 2.187)
BORDER_MM = 3.0
TOP_CHAMFER_MM = 0.5
BASE_CHAMFER_MM = 1.7
DISH_FLOOR_X = (14.95, 70.35)
DISH_FLOOR_Y = (18.85, 147.61)
WELL_DEPTH_MM = 0.7
PLAIN_BAND_MM = 1.6
GROOVE_COUNT = 36
GROOVE_DEPTH_MM = 0.35
GROOVE_PAST_MM = 0.2  # the V runs past the cylinder so the cut does not kiss it
POINTER_MM = (0.9, 0.4, 2.0, 6.0)  # width, depth, inner radius, outer radius

_BUILD_NOTES: list[str] = []


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

    _BUILD_NOTES.clear()
    board = board or load_board()
    case = board["case"]
    span_x, span_y = _spans(board)
    top = _top(board, span_x, span_y)
    glass = _glass(board, span_x, span_y)
    knob = _knob(board)
    place = Pos(0, 0, case["face_front_z"]) * Rot(case["face_tilt_deg"], 0, 0)
    base = _base(board, place * _skin(span_x, span_y, case["plate_web"]))
    for note in _BUILD_NOTES:
        print(note)
    return {
        "top": place * top,
        "base": base,
        "glass": place * glass,
        "knob": place * knob,
    }


def _keep(solid, step: str, build):
    """Run one later cut. On failure the last solid that built is the result."""
    try:
        return build()
    except Exception as error:
        _BUILD_NOTES.append(f"{step} kept the previous solid: {type(error).__name__}: {error}")
        return solid


def _skin(span_x: float, span_y: float, thickness: float):
    from build123d import Box, Pos

    return Pos(span_x / 2, span_y / 2, -thickness / 2) * Box(span_x, span_y, thickness)


def _toward(corner: tuple[float, float], point: tuple[float, float], distance: float) -> tuple[float, float]:
    # Sides of this box are parallel to the axes, so the run is one coordinate.
    length = abs(point[0] - corner[0]) + abs(point[1] - corner[1])
    step = distance / length
    return corner[0] + (point[0] - corner[0]) * step, corner[1] + (point[1] - corner[1]) * step


def _corner_curve(before: tuple[float, float], corner: tuple[float, float], after: tuple[float, float]):
    from build123d import Bezier

    far, mid, near = CORNER_HANDLES_MM
    return Bezier(
        _toward(corner, before, far),
        _toward(corner, before, mid),
        _toward(corner, before, near),
        _toward(corner, after, near),
        _toward(corner, after, mid),
        _toward(corner, after, far),
    )


def _outline(span_x: float, span_y: float, inset: float):
    """Quintic-Bezier plan of the box, inset on each side. Not an OCCT offset."""
    from build123d import Line, make_face

    x0, y0 = inset, inset
    x1, y1 = span_x - inset, span_y - inset
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    curves = [
        _corner_curve(corners[index - 1], corner, corners[(index + 1) % 4])
        for index, corner in enumerate(corners)
    ]
    edges = []
    for index, curve in enumerate(curves):
        following = curves[(index + 1) % 4]
        edges.append(curve)
        edges.append(Line(curve @ 1, following @ 0))
    return make_face(edges)


def _rounded(span_x: float, span_y: float, thickness: float):
    from build123d import extrude

    return extrude(_outline(span_x, span_y, 0.0), amount=-thickness)


def _cut(solid, x: float, y: float, width: float, height: float, depth: float):
    """Cut a rectangular opening through the plate from the key plane."""
    from build123d import Box, Pos

    tool = Pos(x + width / 2, y + height / 2, -depth / 2) * Box(width, height, depth + 0.4)
    return solid - tool


def _top(board: dict, span_x: float, span_y: float):
    case = board["case"]
    # The 1.5 mm web stays the floor. z = 0 is still the key plane.
    floor = _rounded(span_x, span_y, case["plate_web"])
    border = _border(span_x, span_y)
    border = _keep(border, "top chamfer", lambda: _chamfer_highest(border, TOP_CHAMFER_MM))
    border = _keep(border, "knob border", lambda: border - _knob_cylinder(board, BORDER_MM + 0.4, BORDER_MM / 2))
    plate = floor + border
    plate = _keep(plate, "dish", lambda: plate - _dish())
    grow = _grow(case)
    for key_x in board["pcb"]["key_x"]:
        for key_y in board["pcb"]["key_y"]:
            plate = _cut(
                plate,
                key_x + grow - MX_CUT_MM / 2,
                key_y + grow - MX_CUT_MM / 2,
                MX_CUT_MM,
                MX_CUT_MM,
                case["plate_web"],
            )
    pocket_x, pocket_y = _pocket_origin(board, grow)
    pocket_w, pocket_h = case["pocket_plan"]
    plate = _cut(plate, pocket_x, pocket_y, pocket_w, pocket_h, case["pocket_depth"])
    knob_x, knob_y = board["pcb"]["knob"]
    pocket = case["encoder_pocket"][0]
    plate = _cut(plate, knob_x + grow - pocket / 2, knob_y + grow - pocket / 2, pocket, pocket, case["plate_web"])
    plate = _keep(plate, "knob well", lambda: plate - _knob_well(board))
    return plate


def _border(span_x: float, span_y: float):
    from build123d import extrude

    return extrude(_outline(span_x, span_y, 0.0), amount=BORDER_MM)


def _chamfer_highest(solid, length: float):
    from build123d import Axis, chamfer

    edges = list(solid.edges().group_by(Axis.Z)[-1])
    if not edges:
        raise RuntimeError("no top edges")
    return chamfer(edges, length, angle=45)


def _knob_centre(board: dict) -> tuple[float, float]:
    grow = _grow(board["case"])
    knob_x, knob_y = board["pcb"]["knob"]
    return knob_x + grow, knob_y + grow


def _knob_cylinder(board: dict, height: float, centre_z: float):
    from build123d import Cylinder, Pos

    centre_x, centre_y = _knob_centre(board)
    radius = board["case"]["knob_diameter"] / 2
    return Pos(centre_x, centre_y, centre_z) * Cylinder(radius, height)


def _knob_well(board: dict):
    # 0.7 mm below the key plane, opening upward. Not a 23.1 mm well.
    from build123d import Cylinder, Pos

    centre_x, centre_y = _knob_centre(board)
    radius = board["case"]["knob_diameter"] / 2
    height = WELL_DEPTH_MM + 0.2
    return Pos(centre_x, centre_y, -WELL_DEPTH_MM / 2 + 0.1) * Cylinder(radius, height)


def _dish():
    """One pocket. Sharp rectangular floor, walls open at 45° along the face normal."""
    from build123d import Pos, Rectangle, extrude

    x0, x1 = DISH_FLOOR_X
    y0, y1 = DISH_FLOOR_Y
    floor = Pos((x0 + x1) / 2, (y0 + y1) / 2) * Rectangle(x1 - x0, y1 - y0)
    # The extra height is above the border, so the rim on the solid stays at BORDER_MM.
    return extrude(floor, amount=BORDER_MM + 0.4, taper=-45)


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

    case = board["case"]
    centre_x, centre_y = _knob_centre(board)
    radius = case["knob_diameter"] / 2
    foot = case["knob_lift"]
    body = Pos(0, 0, foot + KNOB_HEIGHT_MM / 2) * Cylinder(radius, KNOB_HEIGHT_MM)
    body = _keep(body, "knob grooves", lambda: body - _knob_grooves(radius, foot))
    body = _keep(body, "knob pointer", lambda: body - _knob_pointer(foot))
    return Pos(centre_x, centre_y, 0) * body


def _knob_grooves(radius: float, foot: float):
    """36 straight 90° V cuts in one band. Ends are square, as a turned band would be."""
    from build123d import Polygon, Pos, Rot, extrude

    depth, past = GROOVE_DEPTH_MM, GROOVE_PAST_MM
    start = foot + PLAIN_BAND_MM
    height = KNOB_HEIGHT_MM - 2 * PLAIN_BAND_MM
    vee = Polygon(
        (radius - depth, 0),
        (radius + past, -(depth + past)),
        (radius + past, depth + past),
    )
    groove = Pos(0, 0, start) * extrude(vee, amount=height)
    step = 360 / GROOVE_COUNT
    # Half a step off, so a land and not a groove lines up with the pointer.
    grooves = [Rot(0, 0, (index + 0.5) * step) * groove for index in range(GROOVE_COUNT)]
    cutter = grooves[0]
    for extra in grooves[1:]:
        cutter += extra
    return cutter


def _knob_pointer(foot: float):
    from build123d import Pos, Rectangle, extrude

    width, depth, inner, outer = POINTER_MM
    top = foot + KNOB_HEIGHT_MM
    line = Pos(0, (inner + outer) / 2) * Rectangle(width, outer - inner)
    return Pos(0, 0, top - depth) * extrude(line, amount=depth + 0.2)


def _base(board: dict, skin):
    """Wedge under the skin. Bottom is z = 0. Walls and floor stay."""
    case = board["case"]
    pcb = board["pcb"]
    span_x = skin.bounding_box().size.X
    # The tilted skin's horizontal footprint is shorter than the face length.
    face_y = _spans(board)[1]
    blank = _wedge_blank(board, span_x, face_y)
    base = blank - skin
    grow = _grow(case)
    cavity = _cavity(board, grow)
    base = base - cavity
    base = _usb_slot(base, board, grow)
    tilt = case["face_tilt_deg"]
    for name in ("boot", "reset"):
        base = _floor_hole(base, pcb[name][0] + grow, pcb[name][1] + grow, BUTTON_HOLE_MM, case, tilt)
    for hole_x, hole_y in pcb["holes"]:
        base = _floor_hole(base, hole_x + grow, hole_y + grow, SCREW_HOLE_MM, case, tilt)
    base = _keep(base, "base chamfer", lambda: _chamfer_underside(base, BASE_CHAMFER_MM))
    return base


def _chamfer_underside(solid, length: float):
    """45° on the desk-frame bottom edge only. Hole circles on that face stay."""
    from build123d import GeomType, chamfer

    edges = []
    for edge in solid.edges():
        if edge.center().Z > 0.05:
            continue
        if edge.geom_type == GeomType.CIRCLE:
            continue
        edges.append(edge)
    if not edges:
        raise RuntimeError("no underside edges")
    return chamfer(edges, length, angle=45)


def _wedge_blank(board: dict, span_x: float, face_y: float):
    """Material from the top face down to the desk, before the skin is removed."""
    from build123d import Box, Pos, Rot, extrude

    case = board["case"]
    tilt = case["face_tilt_deg"]
    # A deep extrusion of the face, then keep only z >= 0.
    deep = _skin_box(span_x, face_y, 80.0)
    placed = Pos(0, 0, case["face_front_z"]) * Rot(tilt, 0, 0) * deep
    floor = Pos(span_x / 2, face_y / 2, 40.0) * Box(span_x + 40, face_y + 40, 80.0)
    wedge = placed & floor
    # Same corner family as the plate, on the gap-inset box. Vertical in the desk frame.
    inset = extrude(_outline(span_x, face_y, case["shadow_gap"]), amount=60.0)
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

    from build123d import Cylinder, Pos, Rot

    radians = math.radians(tilt)
    # Point on the top face. The floor hole uses that plan position.
    desk_y = face_y * math.cos(radians)
    tool = Pos(face_x, desk_y, case["floor"] / 2) * Rot(0, 0, 0) * Cylinder(diameter / 2, case["floor"] + 0.4)
    return base - tool
