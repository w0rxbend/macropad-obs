# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The board against board.toml, read independently of layout.py's placement code. Needs pcbnew.

    build.py contract

Checks the outline with the antenna cut and the tail slots, the layer count and thickness, every M2 hole
with its keep-out, the parts board.toml places, no copper in the antenna cut, nothing on the top face
under a display carrier, and no tall top part beside a pocket (spec-v2 section 7). Prints one line per group.

Copied from macropad-greycode pcb/gen (decision D5). Greycode's key, knob, OLED, USB, LED and RP2040
groups are gone: they read greycode's circuit and board.toml.
"""

from __future__ import annotations

import math
import tomllib
from pathlib import Path

import pcbnew

SPEC = tomllib.loads((Path(__file__).resolve().parents[2] / "board.toml").read_text())
PCB = SPEC["pcb"]
TOLERANCE = 0.01  # mm
SAMPLE_STEP = 0.5  # mm, between the points tested for board under the antenna area
# Spec-v2 section 7: "within 1.0 mm outside each pocket, top parts under 2.0 mm".
SKIRT_WIDTH = 1.0
# Height above the PCB top face of each footprint that may stand on the top face ([stack]).
TOP_PART_HEIGHT = {
    "SW_TH_Tactile_Omron_B3F-100x": SPEC["stack"]["b3f_body_top"],
    "RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm": SPEC["stack"]["ec11_body_top"],
    "MX_Hotswap": SPEC["stack"]["mx_plate_top"],  # the switch on top of the bottom-face socket
}
MX_SOCKET = "MX_Hotswap"


def _xy(vector: pcbnew.VECTOR2I) -> tuple[float, float]:
    return pcbnew.ToMM(vector.x), pcbnew.ToMM(vector.y)


def _spec_xy(x: float, y: float) -> tuple[float, float]:
    """board.toml (front-left origin, y towards the back edge) -> KiCad (back-left origin, y towards the front).
    Written out here again on purpose: this check does not trust layout.kicad_xy."""
    return x, PCB["depth"] - y


def _spec_box(rect: list[float]) -> tuple[float, float, float, float]:
    """board.toml [x, y, w, h] -> (left, top, right, bottom) in KiCad coordinates."""
    x, y, width, depth = rect
    return x, PCB["depth"] - (y + depth), x + width, PCB["depth"] - y


def _box(box: pcbnew.BOX2I) -> tuple[float, float, float, float]:
    return tuple(pcbnew.ToMM(v) for v in (box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom()))


def _grown(box: tuple, margin: float) -> tuple[float, float, float, float]:
    left, top, right, bottom = box
    return left - margin, top - margin, right + margin, bottom + margin


def _boxes_meet(a: tuple, b: tuple) -> bool:
    """Overlap with area; edges that only touch do not meet."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _circle_meets(x: float, y: float, radius: float, box: tuple) -> bool:
    left, top, right, bottom = box
    return math.dist((x, y), (min(max(x, left), right), min(max(y, top), bottom))) < radius


def _centre(box: tuple) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _near(actual: tuple[float, float], expected: tuple[float, float], what: str) -> None:
    assert math.dist(actual, expected) < TOLERANCE, f"{what} is at {actual}, board.toml says {expected}"


def _same_points(found: list[tuple[float, float]], wanted: list[tuple[float, float]], what: str) -> None:
    assert len(found) == len(wanted), f"{len(found)} {what}s, board.toml has {len(wanted)}"
    for point in wanted:
        assert any(math.dist(point, other) < TOLERANCE for other in found), f"no {what} at {point}; found {found}"


def _board_polygon(board: pcbnew.BOARD) -> pcbnew.SHAPE_POLY_SET:
    outlines = pcbnew.SHAPE_POLY_SET()
    assert board.GetBoardPolygonOutlines(outlines), "the board outline is not one closed shape"
    return outlines


def _on_board(outlines: pcbnew.SHAPE_POLY_SET, x: float, y: float) -> bool:
    return outlines.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))


def _name(footprint: pcbnew.FOOTPRINT) -> str:
    return str(footprint.GetFPID().GetLibItemName())


def _footprints(board: pcbnew.BOARD, name: str) -> list[pcbnew.FOOTPRINT]:
    return [footprint for footprint in board.GetFootprints() if _name(footprint) == name]


def _courtyard_box(footprint: pcbnew.FOOTPRINT, layer: int) -> tuple | None:
    footprint.BuildCourtyardCaches()
    courtyard = footprint.GetCourtyard(layer)
    return _box(courtyard.BBox()) if courtyard.OutlineCount() else None


def check_outline(board: pcbnew.BOARD) -> str:
    edges = [item for item in board.GetDrawings() if item.GetLayer() == pcbnew.Edge_Cuts]
    assert edges, "no board outline"
    box = edges[0].GetBoundingBox()
    for item in edges[1:]:
        box.Merge(item.GetBoundingBox())
    # The outline's line width pads the box by half a stroke on each side.
    half = pcbnew.ToMM(edges[0].GetWidth()) / 2
    left, top = pcbnew.ToMM(box.GetLeft()) + half, pcbnew.ToMM(box.GetTop()) + half
    right, bottom = pcbnew.ToMM(box.GetRight()) - half, pcbnew.ToMM(box.GetBottom()) - half
    _near((left, top), (0.0, 0.0), "outline corner")
    _near((right, bottom), (PCB["width"], PCB["depth"]), "outline corner")
    radii = [pcbnew.ToMM(item.GetRadius()) for item in edges if item.GetShape() == pcbnew.SHAPE_T_ARC]
    corners = [radius for radius in radii if abs(radius - PCB["corner_radius"]) < TOLERANCE]
    # The fourth corner, back right, lies in the antenna board cut.
    assert len(corners) == 3, f"{len(corners)} board corners of r {PCB['corner_radius']}, arcs {radii}"
    _check_slots(board)
    assert board.GetCopperLayerCount() == PCB["layers"], f"{board.GetCopperLayerCount()} copper layers"
    thickness = pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness())
    assert abs(thickness - PCB["thickness"]) < TOLERANCE, f"board thickness {thickness}"
    return (f"outline {PCB['width']} x {PCB['depth']} mm, r {PCB['corner_radius']}, {len(PCB['board_slots'])} slots, "
            f"{PCB['layers']} layers")


def _check_slots(board: pcbnew.BOARD) -> None:
    """Each board_slots rectangle is a hole through the board, and the board runs up to its edges."""
    outlines = _board_polygon(board)
    for rect in PCB["board_slots"]:
        left, top, right, bottom = _spec_box(rect)
        middle_x, middle_y = _centre((left, top, right, bottom))
        assert not _on_board(outlines, middle_x, middle_y), f"no slot at {rect}"
        for x, y in ((left - 0.1, middle_y), (right + 0.1, middle_y), (middle_x, top - 0.1), (middle_x, bottom + 0.1)):
            assert _on_board(outlines, x, y), f"slot {rect} is larger than board.toml says: ({x}, {y}) is cut"


def check_holes(board: pcbnew.BOARD) -> str:
    drilled = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH and abs(
                    pcbnew.ToMM(pad.GetDrillSize().x) - PCB["hole_diameter"]) < TOLERANCE:
                drilled.append(_xy(pad.GetPosition()))
    wanted = [_spec_xy(x, y) for x, y in PCB["holes"]]
    assert len(drilled) == len(wanted), f"{len(drilled)} holes of {PCB['hole_diameter']} mm, board.toml has {len(wanted)}"
    for hole in wanted:
        assert any(math.dist(hole, found) < TOLERANCE for found in drilled), f"no M2 hole at {hole}"
    # The keep-out: one rule area per hole on all copper layers, no copper allowed inside.
    areas = [zone for zone in board.Zones() if zone.GetIsRuleArea() and zone.GetDoNotAllowTracks()
             and zone.GetDoNotAllowVias() and zone.GetDoNotAllowCopperPour()
             and all(zone.IsOnLayer(layer) for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu))]
    radius = PCB["hole_keepout_diameter"] / 2
    for x, y in wanted:
        covering = [area for area in areas
                    if all(area.Outline().Contains(pcbnew.VECTOR2I(pcbnew.FromMM(x + radius * math.cos(a)),
                                                                   pcbnew.FromMM(y + radius * math.sin(a))))
                           for a in (k * math.pi / 8 for k in range(16)))]
        assert covering, f"no {PCB['hole_keepout_diameter']} mm keep-out round the hole at ({x}, {y})"
    return f"{len(wanted)} M2 holes of {PCB['hole_diameter']} mm, each with a {PCB['hole_keepout_diameter']} mm keep-out"


def check_positions(board: pcbnew.BOARD) -> str:
    """Each part board.toml places, read from its own pads or outline, and its face."""
    keys = [_xy(pad.GetPosition()) for footprint in _footprints(board, MX_SOCKET) for pad in footprint.Pads()
            if abs(pcbnew.ToMM(pad.GetDrillSize().x) - 4.0) < TOLERANCE]  # the switch's centre post
    _same_points(keys, [_spec_xy(x, y) for y in SPEC["keys"]["y"] for x in SPEC["keys"]["x"]], "key")
    knobs = []
    for footprint in _footprints(board, "RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm"):
        lugs = [_xy(pad.GetPosition()) for pad in footprint.Pads() if pad.GetNumber() == "MP"]
        knobs.append(((lugs[0][0] + lugs[1][0]) / 2, (lugs[0][1] + lugs[1][1]) / 2))
    _same_points(knobs, [_spec_xy(SPEC["knobs"]["x"], y) for y in SPEC["knobs"]["y"]], "knob shaft")
    buttons = []
    for footprint in _footprints(board, "SW_TH_Tactile_Omron_B3F-100x"):
        pins = [_xy(pad.GetPosition()) for pad in footprint.Pads()]
        buttons.append((sum(x for x, _ in pins) / len(pins), sum(y for _, y in pins) / len(pins)))
    _same_points(buttons, [_spec_xy(x, SPEC["buttons"]["y"]) for x in SPEC["buttons"]["x"]], "button")
    bottom = _check_module(board) + _check_usb(board) + _check_bottom_centres(board)
    flipped = [footprint.GetReference() for footprint in bottom + _footprints(board, MX_SOCKET)
               if not footprint.IsFlipped()]
    assert not flipped, f"{flipped} are not on the bottom face"
    top = [footprint for footprint in board.GetFootprints() if _name(footprint) in TOP_PART_HEIGHT
           and _name(footprint) != MX_SOCKET]
    flipped = [footprint.GetReference() for footprint in top if footprint.IsFlipped()]
    assert not flipped, f"{flipped} are not on the top face"
    return (f"{len(keys)} keys, {len(knobs)} knobs, {len(buttons)} buttons on top; module, USB, tails, BOOT, RESET "
            f"and debug on the bottom")


def _check_module(board: pcbnew.BOARD) -> list[pcbnew.FOOTPRINT]:
    """[mcu] outline = the module's fabrication outline."""
    (module,) = _footprints(board, "ESP32-S3-WROOM-1")
    lines = [item for item in module.GraphicalItems()
             if item.GetClass() == "PCB_SHAPE" and item.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab)]
    box = lines[0].GetBoundingBox()
    for item in lines[1:]:
        box.Merge(item.GetBoundingBox())
    outline = _grown(_box(box), -pcbnew.ToMM(lines[0].GetWidth()) / 2)
    wanted = _spec_box(SPEC["mcu"]["outline"])
    assert all(abs(a - b) < TOLERANCE for a, b in zip(outline, wanted)), f"module outline {outline}, board.toml {wanted}"
    return [module]


def _check_usb(board: pcbnew.BOARD) -> list[pcbnew.FOOTPRINT]:
    """[usb] shell_pads and peg_holes."""
    (jack,) = _footprints(board, "USB_C_Receptacle_GCT_USB4216-03-A")
    shell = [_xy(pad.GetPosition()) for pad in jack.Pads() if pad.GetNumber() == "S1"]
    _same_points(shell, [_spec_xy(x, y) for x, y, _, _ in SPEC["usb"]["shell_pads"]], "USB shell pad")
    pegs = [_xy(pad.GetPosition()) for pad in jack.Pads() if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    _same_points(pegs, [_spec_xy(x, y) for x, y in SPEC["usb"]["peg_holes"]["at"]], "USB peg hole")
    return [jack]


def _check_bottom_centres(board: pcbnew.BOARD) -> list[pcbnew.FOOTPRINT]:
    """The tails at [fpc.*] centre, BOOT, RESET and the debug JST at their [bottom_side] points: courtyard centres."""
    side = SPEC["bottom_side"]
    groups = [
        ("PLACEHOLDER_FPC_FH12-40S", [SPEC["fpc"]["big"]["centre"]], "big tail connector"),
        ("PLACEHOLDER_FPC_FH12-10S", [SPEC["fpc"]["narrow"]["centre"]], "narrow tail connector"),
        ("SW_Push_1P1T_XKB_TS-1187A", [side["boot"], side["reset"]], "BOOT or RESET switch"),
        ("JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal", [side["debug_uart"]["at"]], "debug connector"),
    ]
    placed = []
    for name, points, what in groups:
        footprints = _footprints(board, name)
        centres = [_centre(_courtyard_box(footprint, pcbnew.B_CrtYd) or _courtyard_box(footprint, pcbnew.F_CrtYd))
                   for footprint in footprints]
        _same_points(centres, [_spec_xy(x, y) for x, y in points], what)
        placed += footprints
    return placed


def check_antenna(board: pcbnew.BOARD) -> str:
    """[antenna]: no board under the antenna area, and no copper in the board cut (pads, tracks, vias, pours)."""
    outlines = _board_polygon(board)
    left, top, right, bottom = _spec_box(SPEC["antenna"]["area"])
    columns, rows = round((right - left) / SAMPLE_STEP), round((bottom - top) / SAMPLE_STEP)
    for i in range(columns + 1):
        for j in range(rows + 1):
            x, y = left + i * SAMPLE_STEP, top + j * SAMPLE_STEP
            assert not _on_board(outlines, x, y), f"board under the antenna area at ({x}, {y})"
    inside = copper_in(board, _spec_box(SPEC["antenna"]["board_cut"]))
    assert not inside, f"{', '.join(inside)} in the antenna board cut"
    return f"no board under the {SPEC['antenna']['area'][2]} x {SPEC['antenna']['area'][3]} antenna area, no copper in the cut"


def copper_in(board: pcbnew.BOARD, box: tuple) -> list[str]:
    """Each pad, track, via or filled pour whose copper meets the box (left, top, right, bottom) with area."""
    found = [f"{footprint.GetReference()} pad {pad.GetNumber()}" for footprint in board.GetFootprints()
             for pad in footprint.Pads() if pad.IsOnCopperLayer() and _boxes_meet(_box(pad.GetBoundingBox()), box)]
    found += [f"{track.GetClass()} at {_xy(track.GetStart())}" for track in board.GetTracks()
              if _boxes_meet(_box(track.GetBoundingBox()), box)]
    window = pcbnew.SHAPE_POLY_SET()
    window.NewOutline()
    left, top, right, bottom = box
    for x, y in ((left, top), (right, top), (right, bottom), (left, bottom)):
        window.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    for zone in board.Zones():
        for layer in zone.GetLayerSet().CuStack():
            if zone.GetIsRuleArea() or not zone.HasFilledPolysForLayer(layer):
                continue
            overlap = pcbnew.SHAPE_POLY_SET(zone.GetFilledPolysList(layer))
            overlap.BooleanIntersection(window)
            if overlap.Area() > 0:
                found.append(f"{zone.GetNetname()} pour on {pcbnew.LayerName(layer)}")
    return found


def _top_parts(board: pcbnew.BOARD) -> list[tuple[pcbnew.FOOTPRINT, str, tuple]]:
    """(footprint, what, box) of each body on the top face: top-face courtyards, and the MX switch that plugs
    into each bottom-face socket ([keys] housing, square on the socket's centre)."""
    found = []
    for footprint in board.GetFootprints():
        ref = footprint.GetReference()
        if _name(footprint) == MX_SOCKET:
            x, y = _xy(footprint.GetPosition())
            half = SPEC["keys"]["housing"] / 2
            found.append((footprint, f"{ref} switch", (x - half, y - half, x + half, y + half)))
            continue
        layer = pcbnew.B_CrtYd if footprint.IsFlipped() else pcbnew.F_CrtYd
        on_top = not footprint.IsFlipped() or footprint.GetAttributes() & pcbnew.FP_THROUGH_HOLE
        box = _courtyard_box(footprint, layer) if on_top else None
        if box is not None:
            found.append((footprint, ref, box))
    return found


def _holes_through(board: pcbnew.BOARD) -> list[tuple[str, tuple]]:
    """(what, box) of each hole or lead through the top face. A plated hole tented on the top face is a via, which
    may sit under a carrier (board.toml [display_carrier])."""
    found = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            plated_via = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and not pad.IsOnLayer(pcbnew.F_Mask)
            if pad.HasHole() and not plated_via:
                found.append((f"{footprint.GetReference()} hole at {_xy(pad.GetPosition())}", _box(pad.GetBoundingBox())))
    return found


def check_carriers(board: pcbnew.BOARD) -> str:
    """[display_carrier]: under each carrier's outer rectangle no top part, no hole or lead, no hole keep-out, no slot."""
    carriers = {f"{name} carrier": _spec_box(SPEC["display_carrier"][name]["outer"]) for name in ("big", "narrow")}
    slots = [(f"slot {rect}", _spec_box(rect)) for rect in PCB["board_slots"]]
    items = [(what, box) for _, what, box in _top_parts(board)] + _holes_through(board) + slots
    for carrier, outer in carriers.items():
        for what, box in items:
            assert not _boxes_meet(box, outer), f"{what} is under the {carrier}"
        for x, y in PCB["holes"]:
            assert not _circle_meets(*_spec_xy(x, y), PCB["hole_keepout_diameter"] / 2, outer), \
                f"the keep-out of the hole at ({x}, {y}) is under the {carrier}"
    return f"nothing on the top face under the {len(carriers)} display carriers"


def check_pocket_skirt(board: pcbnew.BOARD) -> str:
    """Spec-v2 section 7: within SKIRT_WIDTH outside each pocket (with its tail notch), top parts stay under
    [stack] pocket_skirt_bottom."""
    limit = SPEC["stack"]["pocket_skirt_bottom"]
    pockets = {f"{name} pocket": [_spec_box(SPEC[f"{name}_display"][key]) for key in ("pocket", "pocket_tail_notch")]
               for name in ("big", "narrow")}
    for footprint, what, box in _top_parts(board):
        height = TOP_PART_HEIGHT.get(_name(footprint))
        assert height is not None, f"{what}: no [stack] height for top-face footprint {_name(footprint)}"
        if height < limit:
            continue
        for pocket, rects in pockets.items():
            for rect in rects:
                assert not _boxes_meet(box, _grown(rect, SKIRT_WIDTH)), \
                    f"{what} ({height} mm tall) is within {SKIRT_WIDTH} mm of the {pocket}"
    return f"no top part of {limit} mm or more within {SKIRT_WIDTH} mm of a pocket"


CHECKS = (check_outline, check_holes, check_positions, check_antenna, check_carriers, check_pocket_skirt)


def check(board: pcbnew.BOARD) -> None:
    for step in CHECKS:
        print(f"contract: {step(board)}")
    print(f"contract: {len(CHECKS)} groups match board.toml")
