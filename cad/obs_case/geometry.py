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

from .numbers import (
    ACCESS_DIAMETER_MM,
    BORE_CLEARANCE_MM,
    BOSS_DIAMETER_MM,
    BOSS_ROOT_MM,
    BUSHING_DIAMETER_MM,
    BUSHING_POCKET_EXTRA_MM,
    BUSHING_ROOM_MM,
    BUSHING_TOP_ABOVE_PCB_MM,
    COUNTERSINK_DIAMETER_MM,
    COUNTERSINK_RECESS_MM,
    COUNTERSINK_SEAT_MM,
    FOOT_DEPTH_MM,
    FOOT_DIAMETER_MM,
    GROOVE_COUNT,
    GROOVE_DEPTH_MM,
    GROOVE_HALF_MM,
    GROOVE_PAST_MM,
    KNOB_CAP_MM,
    KNOB_FLAT_MARGIN_MM,
    M2_CLEARANCE_MM,
    M2_DRILL_POINT_MM,
    M2_TAP_DEPTH_MM,
    M2_TAP_MM,
    POINTER_DOWN_MM,
    POINTER_INNER_MM,
    POINTER_WIDTH_MM,
    SCOOP_DEPTH_MM,
    SCOOP_LENGTH_MM,
    SCOOP_RADIUS_MM,
    SCOOP_Z_MM,
    SETSCREW_FROM_TOP_MM,
    SETSCREW_HOLE_MM,
    SHAFT_DIAMETER_MM,
    SHAFT_END_ABOVE_PCB_MM,
    SHAFT_FLAT_LENGTH_MM,
    SHAFT_FLAT_MM,
    STANDOFF_DIAMETER_MM,
    USB_LEAD_MM,
    USB_OPENING_MM,
    USB_RECEPTACLE_MM,
    USB_TUNNEL_MM,
    foot_plan,
    screw_plan,
)

ROOT = Path(__file__).resolve().parents[2]

# plate_web from board.toml is the key-plate thickness. The glass is thicker
# than that web, so it is its own solid and hangs below the plate.
MX_CUT_MM = 14.0
GLASS_THICK_MM = 2.25  # datasheet typical. The pocket depth is the maximum.
ACTIVE_MM = (36.72, 48.96)
BUTTON_HOLE_MM = 4.0
# Quintic corner of the 95.2 by 157.2 box. The first three controls on a side
# are colinear, so curvature is zero where the curve meets the straight.
# Distances from the corner, along that side. corner_radius is not this.
CORNER_HANDLES_MM = (10.935, 6.561, 2.187)
BORDER_MM = 1.2  # lip above the key plane. 3 mm sank the glass into a tray.
TOP_CHAMFER_MM = 0.8
BASE_CHAMFER_MM = 1.7
DISH_FLOOR_X = (14.95, 70.35)
DISH_FLOOR_Y = (18.85, 147.61)
WELL_RADIUS_MM = 11.9  # 0.9 mm ring. 12.2 would cut the nearest cap.
WELL_DEPTH_MM = 0.7
WELL_CUTTER_ABOVE_MM = 0.2
PLAIN_BAND_MM = 1.6
KNOB_CHAMFER_MM = 0.5  # both rims. Stays inside the plain bands.
KEYCAP_MM = (18.0, 18.0, 8.0)  # plan, plan, height. Bottom sits on the key plane.
CAP_CORNER_MM = 2.0
CAP_DRAFT_DEG = 8.0
# Spherical dish. Radius 8.5 at 3.0 mm deep stays inside the drafted top.
CAP_DISH_RADIUS_MM = 8.5
CAP_DISH_DEPTH_MM = 3.0
# Moat in the deck, wider than the cap, so each key has a shadow line.
KEY_REVEAL_MM = 0.45
KEY_REVEAL_SIDE_MM = 18.5
KEY_REVEAL_RADIUS_MM = 1.2
ACTIVE_RECESS_MM = 0.6

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
    """Named solids in the desk frame. Reference parts sit on the PCB, they are not cut."""
    from build123d import Pos, Rot

    _BUILD_NOTES.clear()
    board = board or load_board()
    case = board["case"]
    span_x, span_y = _spans(board)
    top = _top(board, span_x, span_y)
    glass = _glass(board, span_x, span_y)
    knob = _knob(board)
    keycaps = _keycaps(board)
    place = Pos(0, 0, case["face_front_z"]) * Rot(case["face_tilt_deg"], 0, 0)
    base = _base(board, place * _skin(span_x, span_y, case["plate_web"]))
    for note in _BUILD_NOTES:
        print(note)
    return {
        "top": place * top,
        "base": base,
        "glass": place * glass,
        "knob": place * knob,
        "keycaps": place * keycaps,
        "screws": place * _screws(board),
        "pcb": place * _pcb(board),
        "usb": place * _usb_jack(board),
        "encoder": place * _encoder(board),
        "switches": place * _switches(board),
        "display": place * _display(board),
    }


CLEAR_PAIRS = (
    ("screws", "base"),
    ("screws", "top"),
    ("screws", "pcb"),
    ("screws", "switches"),
    ("usb", "base"),
    ("usb", "pcb"),
    ("encoder", "base"),
    ("encoder", "top"),
    ("switches", "base"),
    ("switches", "top"),
    ("pcb", "base"),
    ("pcb", "top"),
    ("display", "glass"),
    ("display", "top"),
)


def fit_problems(parts: dict) -> list[str]:
    """Volumes that must stay clear. A shared face is dust, not a hit."""
    problems = []
    for left_name, right_name in CLEAR_PAIRS:
        hit = parts[left_name].intersect(parts[right_name])
        volume = 0.0 if hit is None else sum(item.volume for item in hit)
        if volume > 0.05:
            problems.append(f"{left_name} x {right_name} {volume:.2f} mm3")
    return problems


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
            centre_x, centre_y = key_x + grow, key_y + grow
            plate = _keep(
                plate,
                "key reveal",
                lambda plate=plate, centre_x=centre_x, centre_y=centre_y: plate - _key_reveal(centre_x, centre_y),
            )
    pocket_x, pocket_y = _pocket_origin(board, grow)
    pocket_w, pocket_h = case["pocket_plan"]
    plate = _cut(plate, pocket_x, pocket_y, pocket_w, pocket_h, case["pocket_depth"])
    knob_x, knob_y = board["pcb"]["knob"]
    pocket = case["encoder_pocket"][0]
    plate = _cut(plate, knob_x + grow - pocket / 2, knob_y + grow - pocket / 2, pocket, pocket, case["plate_web"])
    plate = plate - _knob_well(board)
    return _standoffs(plate, board)


def _border(span_x: float, span_y: float):
    from build123d import extrude

    return extrude(_outline(span_x, span_y, 0.0), amount=BORDER_MM)


def _chamfer_highest(solid, length: float):
    return _chamfer_z(solid, length, -1, "no top edges")


def _chamfer_lowest(solid, length: float):
    return _chamfer_z(solid, length, 0, "no bottom edges")


def _chamfer_z(solid, length: float, band: int, empty: str):
    from build123d import Axis, chamfer

    edges = list(solid.edges().group_by(Axis.Z)[band])
    if not edges:
        raise RuntimeError(empty)
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
    # From the top of the lip. Radius stays 11.9 so the cut misses the nearest cap.
    from build123d import Cylinder, Pos

    centre_x, centre_y = _knob_centre(board)
    floor_z = BORDER_MM - WELL_DEPTH_MM
    height = WELL_DEPTH_MM + WELL_CUTTER_ABOVE_MM
    return Pos(centre_x, centre_y, floor_z + height / 2) * Cylinder(WELL_RADIUS_MM, height)


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


def _key_reveal(centre_x: float, centre_y: float):
    """0.45 mm pocket. The 1.5 mm web keeps more than 1 mm under the floor."""
    from build123d import Axis, Box, Pos, fillet

    height = KEY_REVEAL_MM + 0.5
    block = Pos(centre_x, centre_y, 0.25 - KEY_REVEAL_MM / 2) * Box(KEY_REVEAL_SIDE_MM, KEY_REVEAL_SIDE_MM, height)
    return fillet(block.edges().filter_by(Axis.Z), KEY_REVEAL_RADIUS_MM)


def _one_keycap(side: float, height: float):
    """18 mm base, drafted, with one spherical dish and a rim."""
    from build123d import Pos, Rectangle, Sphere, extrude, fillet

    sketch = fillet(Rectangle(side, side).vertices(), CAP_CORNER_MM)
    # Positive taper shrinks along +Z in this build123d. The 18 mm base stays on the plate.
    body = Pos(side / 2, side / 2, 0) * extrude(sketch, amount=height, taper=CAP_DRAFT_DEG)
    # Centre is one radius above the dish floor, so the cut is CAP_DISH_DEPTH_MM.
    centre_z = height - CAP_DISH_DEPTH_MM + CAP_DISH_RADIUS_MM
    scoop = Pos(side / 2, side / 2, centre_z) * Sphere(CAP_DISH_RADIUS_MM)
    return body - scoop


def _keycaps(board: dict):
    """Nine caps, not fused. Pitch is 19.05 mm, so the 18 mm caps do not touch.

    Not cut out of the top. Outer caps overhang the dish floor by 0.35 mm.
    """
    from build123d import Compound, Pos

    side, _, height = KEYCAP_MM
    grow = _grow(board["case"])
    cap = _one_keycap(side, height)
    caps = []
    for key_x in board["pcb"]["key_x"]:
        for key_y in board["pcb"]["key_y"]:
            caps.append(Pos(key_x + grow - side / 2, key_y + grow - side / 2, 0) * cap)
    return Compound(caps)


def _active_box(board: dict, grow: float):
    """Active area centered in the glass. The datasheet does not give an offset."""
    origin_x, origin_y = board["pcb"]["display_origin"]
    width, height = board["pcb"]["display_size"]
    active_w, active_h = board["display"]["active_mm"]
    return (
        origin_x + grow + (width - active_w) / 2,
        origin_y + grow + (height - active_h) / 2,
        active_w,
        active_h,
    )


def _glass(board: dict, span_x: float, span_y: float):
    from build123d import Box, Pos

    del span_x, span_y
    grow = _grow(board["case"])
    origin_x, origin_y = board["pcb"]["display_origin"]
    width, height = board["pcb"]["display_size"]
    glass = Pos(origin_x + grow + width / 2, origin_y + grow + height / 2, -GLASS_THICK_MM / 2) * Box(
        width, height, GLASS_THICK_MM
    )
    left, near, active_w, active_h = _active_box(board, grow)
    # Floor at -ACTIVE_RECESS_MM. Centering the box on z = recess/2 only nicks the face.
    floor = -ACTIVE_RECESS_MM
    over = 0.2
    recess = Pos(left + active_w / 2, near + active_h / 2, (floor + over) / 2) * Box(
        active_w, active_h, over - floor
    )
    return glass - recess


def _display(board: dict):
    """Black active area, just below the glass face, so the bezel stays visible."""
    from build123d import Box, Pos

    left, near, active_w, active_h = _active_box(board, _grow(board["case"]))
    thickness = 0.12
    top = -0.04
    return Pos(left + active_w / 2, near + active_h / 2, top - thickness / 2) * Box(active_w, active_h, thickness)


def _knob_height(board: dict) -> float:
    """Cap sits KNOB_CAP_MM above the shaft end. A 16 mm blank left the shaft proud."""
    case = board["case"]
    shaft_end = -case["plate_above_pcb"] + SHAFT_END_ABOVE_PCB_MM
    return shaft_end + KNOB_CAP_MM - case["knob_lift"]


def _knob(board: dict):
    from build123d import Cylinder, Pos

    case = board["case"]
    centre_x, centre_y = _knob_centre(board)
    radius = case["knob_diameter"] / 2
    foot = case["knob_lift"]
    height = _knob_height(board)
    body = Pos(0, 0, foot + height / 2) * Cylinder(radius, height)
    body = _chamfer_highest(body, KNOB_CHAMFER_MM)
    body = _chamfer_lowest(body, KNOB_CHAMFER_MM)
    body = body - _knob_seat(board, foot)
    body = _keep(body, "knob grooves", lambda: body - _knob_grooves(radius, foot, height))
    body = body - _knob_pointer(foot, height, radius)
    body = body - _knob_setscrew(foot, height, radius)
    return Pos(centre_x, centre_y, 0) * body


def _knob_seat(board: dict, foot: float):
    """Bushing pocket, round bore, then a D over the shaft flat. The flat faces +y."""
    case = board["case"]
    pcb_top = -case["plate_above_pcb"]
    shaft_end = pcb_top + SHAFT_END_ABOVE_PCB_MM
    bushing_top = pcb_top + BUSHING_TOP_ABOVE_PCB_MM
    roof = bushing_top + BUSHING_ROOM_MM
    bore = SHAFT_DIAMETER_MM + BORE_CLEARANCE_MM
    flat = SHAFT_FLAT_MM + BORE_CLEARANCE_MM
    d_start = shaft_end - SHAFT_FLAT_LENGTH_MM + KNOB_FLAT_MARGIN_MM
    pocket_r = (BUSHING_DIAMETER_MM + BUSHING_POCKET_EXTRA_MM) / 2
    pocket = _face_cylinder(0, 0, foot - 0.4, roof, pocket_r)
    round_bore = _face_cylinder(0, 0, foot - 0.2, d_start, bore / 2)
    return pocket + round_bore + _d_solid(bore, flat, d_start, shaft_end)


def _knob_grooves(radius: float, foot: float, height: float):
    """36 flutes in one band. Width is fixed at the cylinder so the lands stay."""
    from build123d import Polygon, Pos, Rot, extrude

    depth, past, half = GROOVE_DEPTH_MM, GROOVE_PAST_MM, GROOVE_HALF_MM
    start = foot + PLAIN_BAND_MM
    band = height - 2 * PLAIN_BAND_MM
    outer = radius + past
    outer_half = half * (depth + past) / depth
    vee = Polygon(
        (radius - depth, 0),
        (outer, -outer_half),
        (outer, outer_half),
    )
    groove = Pos(0, 0, start) * extrude(vee, amount=band)
    step = 360 / GROOVE_COUNT
    # Half a step off, so a land and not a groove lines up with the pointer.
    grooves = [Rot(0, 0, (index + 0.5) * step) * groove for index in range(GROOVE_COUNT)]
    cutter = grooves[0]
    for extra in grooves[1:]:
        cutter += extra
    return cutter


def _knob_pointer(foot: float, height: float, radius: float):
    """Index on the flat side. It breaks the top rim, so the hero shows it."""
    from build123d import Box, Pos

    top = foot + height
    length = radius + 0.4 - POINTER_INNER_MM
    centre_y = POINTER_INNER_MM + length / 2
    return Pos(0, centre_y, top - POINTER_DOWN_MM / 2 + 0.1) * Box(
        POINTER_WIDTH_MM, length, POINTER_DOWN_MM + 0.2
    )


def _knob_setscrew(foot: float, height: float, radius: float):
    """M3 radial hole onto the flat. One side only, below the index."""
    from build123d import Cylinder, Pos, Rot

    bore_r = (SHAFT_DIAMETER_MM + BORE_CLEARANCE_MM) / 2
    outer = radius + 0.3
    inner = bore_r - 0.2
    length = outer - inner
    centre_y = (outer + inner) / 2
    centre_z = foot + height - SETSCREW_FROM_TOP_MM
    hole = Rot(90, 0, 0) * Cylinder(SETSCREW_HOLE_MM / 2, length)
    return Pos(0, centre_y, centre_z) * hole


def _d_solid(diameter: float, across: float, z0: float, z1: float):
    """D extrusion. The flat is +y, same side as the index and the set screw."""
    from build123d import Circle, Pos, Rectangle, extrude

    radius = diameter / 2
    flat_offset = across - radius
    keep = Pos(0, (flat_offset - radius) / 2) * Rectangle(diameter, flat_offset + radius)
    return Pos(0, 0, z0) * extrude(Circle(radius) & keep, amount=z1 - z0)


def _base(board: dict, skin):
    """Wedge under the skin. Bottom is z = 0. Walls and floor stay."""
    case = board["case"]
    span_x = skin.bounding_box().size.X
    # The tilted skin's horizontal footprint is shorter than the face length.
    face_y = _spans(board)[1]
    blank = _wedge_blank(board, span_x, face_y)
    base = blank - skin
    grow = _grow(case)
    cavity = _cavity(board, grow)
    base = base - cavity
    base = _usb_slot(base, board, grow)
    base = _keep(base, "base chamfer", lambda: _chamfer_underside(base, BASE_CHAMFER_MM))
    base = _keep(base, "side scoops", lambda: base - _side_scoops(board, span_x, face_y))
    base = _fasten_base(base, board)
    return base


def _side_scoops(board: dict, span_x: float, face_y: float):
    """One finger scoop on each long side. Desk frame, after the underside chamfer."""
    import math

    from build123d import Cylinder, Pos, Rot

    case = board["case"]
    desk = face_y * math.cos(math.radians(case["face_tilt_deg"]))
    gap = case["shadow_gap"]
    radius = SCOOP_RADIUS_MM
    left_x = gap - radius + SCOOP_DEPTH_MM
    right_x = span_x - gap + radius - SCOOP_DEPTH_MM
    cutter = Rot(90, 0, 0) * Cylinder(radius, SCOOP_LENGTH_MM)
    centre_y = desk * 0.52
    return Pos(left_x, centre_y, SCOOP_Z_MM) * cutter + Pos(right_x, centre_y, SCOOP_Z_MM) * cutter


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
    """Bay from the floor to the plate. A stop at the PCB top leaves metal on the threads."""
    from build123d import Box, Pos, Rot

    case = board["case"]
    pcb = board["pcb"]
    span_x, span_y = _spans(board)
    width = pcb["width"] + 2 * case["pcb_clearance"]
    depth = pcb["depth"] + 2 * case["pcb_clearance"]
    # 0.2 mm into the skin cut, so the bay meets the lid and no sliver remains.
    top = -case["plate_web"] + 0.2
    bottom = -80.0
    local = Pos(
        grow - case["pcb_clearance"] + width / 2,
        grow - case["pcb_clearance"] + depth / 2,
        (top + bottom) / 2,
    ) * Box(width, depth, top - bottom)
    placed = Pos(0, 0, case["face_front_z"]) * Rot(case["face_tilt_deg"], 0, 0) * local
    floor_block = Pos(span_x / 2, span_y / 2, case["floor"] / 2) * Box(span_x, span_y, case["floor"])
    above = Pos(span_x / 2, span_y / 2, case["floor"] + 40) * Box(span_x + 10, span_y + 10, 80)
    return (placed & above) - floor_block


def _usb_slot(base, board: dict, grow: float):
    """Stadium on the receptacle axis. The old slot was centred on the plate."""
    case = board["case"]
    pcb = board["pcb"]
    span_y = _spans(board)[1]
    width, height = USB_OPENING_MM
    lead_w, lead_h, lead_d = USB_LEAD_MM
    centre_z = -(case["plate_above_pcb"] + pcb["thickness"] + pcb["usb_centre_from_pcb"])
    x = pcb["usb_x"] + grow
    mouth_y = span_y + 0.6
    tunnel = _slot_along_y(x, mouth_y, centre_z, width, height, USB_TUNNEL_MM)
    lead = _slot_along_y(x, mouth_y, centre_z, lead_w, lead_h, lead_d)
    return base - _on_face(board, tunnel + lead)


def _face_cylinder(x: float, y: float, z0: float, z1: float, radius: float):
    from build123d import Cylinder, Pos

    low, high = (z0, z1) if z0 <= z1 else (z1, z0)
    if high - low <= 0:
        raise RuntimeError("empty cylinder")
    return Pos(x, y, (low + high) / 2) * Cylinder(radius, high - low)


def _on_face(board: dict, solid):
    from build123d import Pos, Rot

    case = board["case"]
    return Pos(0, 0, case["face_front_z"]) * Rot(case["face_tilt_deg"], 0, 0) * solid


def _slot_along_y(x: float, y: float, z: float, width: float, height: float, depth: float):
    """Outer end at y. Plane.XZ extrudes toward -y, so position the solid after the extrude."""
    from build123d import Plane, Pos, SlotOverall, extrude

    solid = extrude(Plane.XZ * SlotOverall(width, height), amount=depth)
    return Pos(x, y, z) * solid


def _standoffs(plate, board: dict):
    """4 mm standoffs down to the PCB. The tap drill stops 1 mm under the key plane."""
    case = board["case"]
    pcb_top = -case["plate_above_pcb"]
    height = -case["plate_web"] - pcb_top + 0.2
    drill = M2_TAP_DEPTH_MM + M2_DRILL_POINT_MM
    for row in screw_plan(board):
        plate = plate + _face_cylinder(row["x"], row["y"], pcb_top, pcb_top + height, STANDOFF_DIAMETER_MM / 2)
        plate = plate - _face_cylinder(row["x"], row["y"], pcb_top - 0.2, pcb_top + drill, M2_TAP_MM / 2)
    return plate


def _fasten_base(base, board: dict):
    """Bosses, access bores, and button holes along the face normal. Feet stay vertical."""
    from build123d import Cylinder, Pos

    case = board["case"]
    grow = _grow(case)
    for row in screw_plan(board):
        root = _face_cylinder(row["x"], row["y"], row["mouth"] - 0.4, row["seat"] + 0.2, BOSS_ROOT_MM / 2)
        neck = _face_cylinder(row["x"], row["y"], row["seat"] - 0.2, row["pcb_bottom"], BOSS_DIAMETER_MM / 2)
        base = base + _on_face(board, root)
        base = base + _on_face(board, neck)
        base = base - _on_face(board, _screw_bore(row))
    for name in ("boot", "reset"):
        x = board["pcb"][name][0] + grow
        y = board["pcb"][name][1] + grow
        mouth = _mouth_z(board, y)
        bore = _face_cylinder(x, y, mouth - 0.4, -case["plate_above_pcb"] - board["pcb"]["thickness"], BUTTON_HOLE_MM / 2)
        base = base - _on_face(board, bore)
    for foot_x, foot_y in foot_plan(board):
        pocket = Pos(foot_x, foot_y, FOOT_DEPTH_MM / 2) * Cylinder(FOOT_DIAMETER_MM / 2, FOOT_DEPTH_MM + 0.4)
        base = base - pocket
    return base


def _mouth_z(board: dict, y: float) -> float:
    import math

    case = board["case"]
    tilt = math.radians(case["face_tilt_deg"])
    return -(case["face_front_z"] + y * math.sin(tilt)) / math.cos(tilt)


def _screw_bore(row: dict):
    """5 mm access up to the seat, then the 90 degree countersink, then the clearance."""
    from build123d import Cone, Pos

    access = _face_cylinder(row["x"], row["y"], row["mouth"] - 0.4, row["seat"], ACCESS_DIAMETER_MM / 2)
    recess = _face_cylinder(
        row["x"],
        row["y"],
        row["seat"],
        row["seat"] + COUNTERSINK_RECESS_MM,
        COUNTERSINK_DIAMETER_MM / 2,
    )
    seat_z = row["seat"] + COUNTERSINK_RECESS_MM + COUNTERSINK_SEAT_MM / 2
    cone = Pos(row["x"], row["y"], seat_z) * Cone(
        COUNTERSINK_DIAMETER_MM / 2, M2_CLEARANCE_MM / 2, COUNTERSINK_SEAT_MM
    )
    clearance = _face_cylinder(
        row["x"],
        row["y"],
        row["seat"] + COUNTERSINK_RECESS_MM + COUNTERSINK_SEAT_MM,
        row["pcb_bottom"] + 0.05,
        M2_CLEARANCE_MM / 2,
    )
    return access + recess + cone + clearance


def _screws(board: dict):
    """M2x10 drawn clear of the metal. The thread is under the tap drill, so it does not clash."""
    from build123d import Compound, Cone, Pos

    screws = []
    for row in screw_plan(board):
        head_height = 1.2
        head = Pos(row["x"], row["y"], row["seat"] + 0.08 + head_height / 2) * Cone(1.85, 0.95, head_height)
        shank = _face_cylinder(row["x"], row["y"], row["seat"] + 0.08 + head_height, row["pcb_top"], 0.95)
        thread = _face_cylinder(row["x"], row["y"], row["pcb_top"], row["tip"], M2_TAP_MM / 2 - 0.05)
        screws.append(head + shank + thread)
    return Compound(screws)


def _pcb(board: dict):
    """Board envelope. Corners are square, which is larger than the 2 mm radius."""
    from build123d import Box, Pos

    case = board["case"]
    pcb = board["pcb"]
    grow = _grow(case)
    top = -case["plate_above_pcb"]
    body = Pos(grow + pcb["width"] / 2, grow + pcb["depth"] / 2, top - pcb["thickness"] / 2) * Box(
        pcb["width"], pcb["depth"], pcb["thickness"]
    )
    for row in screw_plan(board):
        body = body - _face_cylinder(
            row["x"], row["y"], top - pcb["thickness"] - 0.2, top + 0.2, pcb["hole_diameter"] / 2
        )
    return body


def _usb_jack(board: dict):
    """Receptacle envelope on the PCB bottom. The mouth is 0.5 mm past the board."""
    from build123d import Box, Pos

    case = board["case"]
    pcb = board["pcb"]
    grow = _grow(case)
    width, length, height = USB_RECEPTACLE_MM
    mouth_y = grow + pcb["depth"] + pcb["usb_mouth_overhang"]
    # The 3.26 mm body centred 1.6 mm off the face would enter the board by 0.03 mm.
    pcb_bottom = -(case["plate_above_pcb"] + pcb["thickness"])
    return Pos(pcb["usb_x"] + grow, mouth_y - length / 2, pcb_bottom - height / 2) * Box(width, length, height)


def _switches(board: dict):
    """MX bodies in the open gap under the plate. The 15.6 mm plan is MEASURE."""
    from build123d import Box, Compound, Pos

    case = board["case"]
    pcb = board["pcb"]
    grow = _grow(case)
    side = case["switch_housing"]
    height = case["plate_above_pcb"] - case["plate_web"]
    pcb_top = -case["plate_above_pcb"]
    bodies = [
        Pos(key_x + grow, key_y + grow, pcb_top + height / 2) * Box(side, side, height)
        for key_x in pcb["key_x"]
        for key_y in pcb["key_y"]
    ]
    return Compound(bodies)


def _encoder(board: dict):
    """EC11 body, the 7 mm bushing, and the D shaft the knob seats on."""
    from build123d import Box, Pos

    case = board["case"]
    pcb = board["pcb"]
    grow = _grow(case)
    body_x, body_y, body_z = case["encoder_body"]
    pcb_top = -case["plate_above_pcb"]
    knob_x, knob_y = pcb["knob"]
    x, y = knob_x + grow, knob_y + grow
    body = Pos(x, y, pcb_top + body_z / 2) * Box(body_x, body_y, body_z)
    bushing_top = pcb_top + BUSHING_TOP_ABOVE_PCB_MM
    shaft_end = pcb_top + SHAFT_END_ABOVE_PCB_MM
    flat_start = shaft_end - SHAFT_FLAT_LENGTH_MM
    bushing = _face_cylinder(x, y, pcb_top + body_z, bushing_top, BUSHING_DIAMETER_MM / 2)
    round_shaft = _face_cylinder(x, y, bushing_top, flat_start, SHAFT_DIAMETER_MM / 2)
    flat = Pos(x, y, 0) * _d_solid(SHAFT_DIAMETER_MM, SHAFT_FLAT_MM, flat_start, shaft_end)
    return body + bushing + round_shaft + flat
