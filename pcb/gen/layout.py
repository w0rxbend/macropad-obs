# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Builds the unrouted KiCad board: rules, outline, parts, nets, zones and hole keep-outs. Runs inside the
KiCad container (needs pcbnew).

Parts come in as `BoardPart`s, already in KiCad coordinates (`kicad_xy`); place.py makes them from board.toml,
and the outline with the antenna cut. The planes, the antenna keep-out and the locked copper come from
route.py (task 5.8) through `add_planes`, `add_copper_keepout` and `write_locked_copper`.

Copied from macropad-greycode pcb/gen (decision D5). Greycode's RP2040 pieces are gone: the QFN-56 paste
windows, the placement self-checks, the plane islands, the fiducials, and the silk.py and models.py calls.
`box_mm` and `circle_meets_rect` moved here from greycode's route.py; this board's route.py is pure Python.
"""

from __future__ import annotations

import json
import math
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import pcbnew

import route
import schematic
from place import kicad_xy, outline_path
from router import BACK, FRONT, Pad, Rules, Track, Via

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = tomllib.loads((REPO_ROOT / "board.toml").read_text())
PCB = SPEC["pcb"]
WIDTH, DEPTH = PCB["width"], PCB["depth"]
TOP, BOTTOM = "top", "bottom"
GND = "GND"
STOCK_FOOTPRINTS = Path("/usr/share/kicad/footprints")
PROJECT_FOOTPRINTS = REPO_ROOT / "pcb" / "lib"
SILK_EDGE_CLEARANCE = 0.2

# JLCPCB 4-layer capability with margin: 0.09 mm track/space and 0.3 mm drill are their limits.
TRACK_WIDTH = 0.15
CLEARANCE = 0.15
VIA_DIAMETER = 0.6
VIA_DRILL = 0.3
EDGE_CLEARANCE = 0.3
# Copper layer of each inner plane (spec R09: inner GND and power planes).
GROUND_LAYER = pcbnew.In2_Cu
POWER_LAYER = pcbnew.In1_Cu
ROUTING_RULES = Rules(track_width=TRACK_WIDTH, clearance=CLEARANCE, via_diameter=VIA_DIAMETER,
                      via_drill=VIA_DRILL, edge_clearance=EDGE_CLEARANCE)
# The board-wide limits kicad-cli's DRC checks against, as they are written into macropad-obs.kicad_pro.
# KiCad 9 keeps the design rules in the project file, not in the board file.
DRC_RULES = {
    "min_track_width": 0.127,
    "min_clearance": 0.127,
    "min_via_diameter": 0.45,
    "min_through_hole_diameter": 0.3,
    "min_copper_edge_clearance": EDGE_CLEARANCE,
    "min_hole_clearance": 0.2,
    "min_hole_to_hole": 0.25,
}
DEFAULT_NET_CLASS = {"track_width": TRACK_WIDTH, "clearance": CLEARANCE, "via_diameter": VIA_DIAMETER,
                     "via_drill": VIA_DRILL}
# No paste aperture anywhere comes closer than this to a via's drilled hole.
PASTE_TO_VIA_DRILL = 0.15
COPPER_LAYERS = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
_ROUTER_LAYERS = {FRONT: pcbnew.F_Cu, BACK: pcbnew.B_Cu}
# Value of the mounting-hole parts: their own keep-out does not count against them.
HOLE_VALUE = "M2"


class BoardPart(Protocol):
    """What the board needs of a circuit's part."""
    ref: str
    value: str
    footprint: str             # "library:name"
    lcsc: str                  # empty: not in the BOM
    nets: Mapping[str, str]    # pad number -> net; a pad left out is open
    x: float                   # KiCad coordinates, mm (kicad_xy)
    y: float
    rotation: float            # degrees, as seen from the top
    side: str                  # TOP or BOTTOM
    machine_assembled: bool


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def point(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def pad_xy(pad: pcbnew.PAD) -> tuple[float, float]:
    position = pad.GetPosition()
    return pcbnew.ToMM(position.x), pcbnew.ToMM(position.y)


def box_mm(box: pcbnew.BOX2I) -> tuple[float, float, float, float]:
    return tuple(pcbnew.ToMM(v) for v in (box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom()))


def circle_meets_rect(x: float, y: float, radius: float, rect: tuple) -> bool:
    left, top, right, bottom = rect
    return math.dist((x, y), (min(max(x, left), right), min(max(y, top), bottom))) < radius


def _load_footprint(name: str) -> pcbnew.FOOTPRINT:
    library, footprint_name = name.split(":")
    root = PROJECT_FOOTPRINTS if library == schematic.PROJECT else STOCK_FOOTPRINTS
    footprint = pcbnew.FootprintLoad(str(root / f"{library}.pretty"), footprint_name)
    assert footprint is not None, f"footprint not found: {name}"
    footprint.SetFPID(pcbnew.LIB_ID(library, footprint_name))  # with its library, as the schematic names it
    return footprint


def _net(board: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    return _board_net(board, schematic.board_net_name(name))


def _board_net(board: pcbnew.BOARD, board_name: str) -> pcbnew.NETINFO_ITEM:
    existing = board.FindNet(board_name)
    if existing is not None:
        return existing
    net = pcbnew.NETINFO_ITEM(board, board_name)
    board.Add(net)
    return net


def _place(board: pcbnew.BOARD, part: BoardPart, open_pin_nets: Mapping[str, str]) -> pcbnew.FOOTPRINT:
    footprint = _load_footprint(part.footprint)
    board.Add(footprint)  # pcbnew crashes when it flips a footprint that has no board
    footprint.SetReference(part.ref)
    footprint.SetPath(pcbnew.KIID_PATH(f"/{schematic.symbol_uuid(part.ref)}"))  # pairs it with its schematic symbol
    footprint.SetValue(part.value)
    footprint.SetPosition(point(part.x, part.y))
    if part.side == BOTTOM:
        # A top-bottom flip mirrors Y; the extra half turn makes it the X mirror you see from the top.
        footprint.Flip(footprint.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        footprint.SetOrientationDegrees(part.rotation + 180)
    else:
        footprint.SetOrientationDegrees(part.rotation)
    if part.lcsc:
        footprint.SetField("LCSC", part.lcsc)
        footprint.GetFieldByName("LCSC").SetVisible(False)
    footprint.Value().SetVisible(False)
    _remove_silkscreen_off_the_board(footprint)
    if not part.machine_assembled:
        footprint.SetExcludedFromPosFiles(True)
    _connect(board, footprint, part, open_pin_nets)
    return footprint


def _antenna_cut_box() -> tuple[float, float, float, float]:
    """board.toml [antenna] board_cut as (left, top, right, bottom), KiCad coordinates."""
    left, front, width, depth = SPEC["antenna"]["board_cut"]
    return left, DEPTH - (front + depth), left + width, DEPTH - front


def _remove_silkscreen_off_the_board(footprint: pcbnew.FOOTPRINT) -> None:
    """The USB receptacle hangs over the edge and its outline with it, and the module's antenna end sits in the
    antenna cut; the fab house would clip those lines."""
    cut_left, _, _, cut_bottom = _antenna_cut_box()
    for item in list(footprint.GraphicalItems()):
        if item.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            continue
        left, top, right, bottom = box_mm(item.GetBoundingBox())
        inside = (left >= SILK_EDGE_CLEARANCE and top >= SILK_EDGE_CLEARANCE
                  and right <= WIDTH - SILK_EDGE_CLEARANCE and bottom <= DEPTH - SILK_EDGE_CLEARANCE)
        in_cut = right > cut_left - SILK_EDGE_CLEARANCE and top < cut_bottom + SILK_EDGE_CLEARANCE
        if not inside or in_cut:
            footprint.Remove(item)


def _connect(board: pcbnew.BOARD, footprint: pcbnew.FOOTPRINT, part: BoardPart,
             open_pin_nets: Mapping[str, str]) -> None:
    """Nets from the circuit. An open pin gets the one-pad net KiCad's netlist names for it, so the board
    carries exactly the nets of the schematic."""
    pad_numbers = {pad.GetNumber() for pad in footprint.Pads()}
    unknown = set(part.nets) - pad_numbers
    assert not unknown, f"{part.ref}: no such pads {sorted(unknown)}"
    for pad in footprint.Pads():
        net_name = part.nets.get(pad.GetNumber(), schematic.NO_NET)
        open_net = open_pin_nets.get(f"{part.ref}.{pad.GetNumber()}")
        if net_name != schematic.NO_NET:
            pad.SetNet(_net(board, net_name))
        elif open_net is not None:
            pad.SetNet(_board_net(board, open_net))


def _outline(board: pcbnew.BOARD) -> None:
    """place.outline_path, then each board.toml [pcb] board_slots rectangle cut through the board."""
    for kind, *points in outline_path():
        if kind == "arc":
            shape = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
            shape.SetArcGeometry(*(point(*p) for p in points))
        else:
            shape = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
            shape.SetStart(point(*points[0]))
            shape.SetEnd(point(*points[1]))
        _add_edge(board, shape)
    for left, front, width, depth in PCB["board_slots"]:
        slot = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECT)
        slot.SetStart(point(*kicad_xy(left, front + depth)))
        slot.SetEnd(point(*kicad_xy(left + width, front)))
        _add_edge(board, slot)


def _add_edge(board: pcbnew.BOARD, shape: pcbnew.PCB_SHAPE) -> None:
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(mm(0.1))
    board.Add(shape)


def _zone(board: pcbnew.BOARD, net_name: str, layer: int, rectangles: list[tuple], priority: int = 0) -> None:
    """One zone over the union of the rectangles (left, top, right, bottom)."""
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNet(_net(board, net_name))
    zone.SetAssignedPriority(priority)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)  # hand-soldered pins must not sink the heat
    zone.SetThermalReliefGap(mm(0.25))
    zone.SetThermalReliefSpokeWidth(mm(0.4))
    zone.SetMinThickness(mm(0.2))
    zone.SetLocalClearance(mm(0.2))
    union = pcbnew.SHAPE_POLY_SET()
    for left, top, right, bottom in rectangles:
        union.NewOutline()
        for x, y in ((left, top), (right, top), (right, bottom), (left, bottom)):
            union.Append(mm(x), mm(y))
    union.Simplify()
    assert union.OutlineCount() == 1, f"{net_name} zone: the rectangles do not form one piece"
    # Copied point by point: handing the union itself to the zone makes pcbnew free it twice.
    merged = union.Outline(0)
    outline = zone.Outline()
    outline.NewOutline()
    for index in range(merged.PointCount()):
        corner = merged.CPoint(index)
        outline.Append(corner.x, corner.y)
    board.Add(zone)


def _circle_rule_area(board: pcbnew.BOARD, layers: tuple[int, ...], x: float, y: float, radius: float) -> None:
    """No copper pour, no track and no via inside the circle on these layers."""
    # The polygon's flats sit on the circle, so the polygon holds the whole circle.
    reach = radius / math.cos(math.pi / 32)
    angles = [math.radians(step * 360 / 32) for step in range(32)]
    _rule_area(board, layers, [(x + reach * math.cos(angle), y + reach * math.sin(angle)) for angle in angles])


def add_copper_keepout(board: pcbnew.BOARD, rect: tuple) -> None:
    """No copper pour, no track and no via inside the rectangle (left, top, right, bottom) on any copper layer."""
    left, top, right, bottom = rect
    _rule_area(board, COPPER_LAYERS, [(left, top), (right, top), (right, bottom), (left, bottom)])


def _rule_area(board: pcbnew.BOARD, layers: tuple[int, ...], corners: list[tuple[float, float]]) -> None:
    area = pcbnew.ZONE(board)
    area.SetIsRuleArea(True)
    layer_set = pcbnew.LSET()
    for layer in layers:
        layer_set.AddLayer(layer)
    area.SetLayerSet(layer_set)
    area.SetDoNotAllowCopperPour(True)
    area.SetDoNotAllowTracks(True)
    area.SetDoNotAllowVias(True)
    area.SetDoNotAllowPads(False)
    area.SetDoNotAllowFootprints(False)
    outline = area.Outline()
    outline.NewOutline()
    for x, y in corners:
        outline.Append(mm(x), mm(y))
    board.Add(area)


def add_hole_keepouts(board: pcbnew.BOARD) -> None:
    """board.toml hole_keepout_diameter round every M2 hole on all four copper layers."""
    for x, y in hole_centres():
        _circle_rule_area(board, COPPER_LAYERS, x, y, PCB["hole_keepout_diameter"] / 2)


def add_encoder_post_keepouts(board: pcbnew.BOARD) -> None:
    """board.toml [bottom_plate] encoder_post_keepout round each encoder post, on B.Cu: the post meets that face."""
    plate = SPEC["bottom_plate"]
    for x, y in plate["encoder_posts"]["at"]:
        _circle_rule_area(board, (pcbnew.B_Cu,), *kicad_xy(x, y), plate["encoder_post_keepout"] / 2)


def hole_centres() -> list[tuple[float, float]]:
    return [kicad_xy(x, y) for x, y in PCB["holes"]]


def _whole_board() -> list[tuple]:
    return [(0.0, 0.0, WIDTH, DEPTH)]


def add_planes(board: pcbnew.BOARD, planes: tuple[route.Plane, ...]) -> None:
    for plane in planes:
        layer = {route.GROUND_PLANE: GROUND_LAYER, route.POWER_PLANE: POWER_LAYER}[plane.layer]
        _zone(board, plane.net, layer, list(plane.rects), plane.priority)


def router_obstacles(board: pcbnew.BOARD) -> tuple[list[Pad], list[tuple]]:
    """Every copper pad as the router sees it ("U1.5", net, box, outer layers), and every unplated drill."""
    pads, holes = [], []
    for footprint in sorted(board.GetFootprints(), key=lambda fp: fp.GetReference()):
        for pad in footprint.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                x, y = pad_xy(pad)
                radius = pcbnew.ToMM(max(pad.GetDrillSize().x, pad.GetDrillSize().y)) / 2
                holes.append((x - radius, y - radius, x + radius, y + radius))
            elif pad.IsOnCopperLayer():
                layers = tuple(layer for layer, kicad in _ROUTER_LAYERS.items() if pad.IsOnLayer(kicad))
                net = schematic.circuit_net_name(pad.GetNetname())
                pads.append(Pad(f"{footprint.GetReference()}.{pad.GetNumber()}", net, box_mm(pad.GetBoundingBox()), layers))
    return pads, holes


def write_locked_copper(board: pcbnew.BOARD, tracks: list[Track], vias: list[Via], rules: Rules) -> None:
    """The router's tracks and through vias on the board, each locked so later routing keeps it."""
    for track in tracks:
        segment = pcbnew.PCB_TRACK(board)
        segment.SetStart(point(*track.start))
        segment.SetEnd(point(*track.end))
        segment.SetWidth(mm(track.width))
        segment.SetLayer(_ROUTER_LAYERS[track.layer])
        segment.SetNet(_net(board, track.net))
        segment.SetLocked(True)
        board.Add(segment)
    for via in vias:
        barrel = pcbnew.PCB_VIA(board)
        barrel.SetViaType(pcbnew.VIATYPE_THROUGH)
        barrel.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        barrel.SetPosition(point(via.x, via.y))
        barrel.SetWidth(pcbnew.F_Cu, mm(rules.via_diameter))
        barrel.SetDrill(mm(rules.via_drill))
        barrel.SetNet(_net(board, via.net))
        barrel.SetLocked(True)
        board.Add(barrel)


def add_outer_ground_pours(board: pcbnew.BOARD) -> None:
    _zone(board, GND, pcbnew.F_Cu, _whole_board())
    _zone(board, GND, pcbnew.B_Cu, _whole_board())


def _rules(board: pcbnew.BOARD) -> None:
    """The same rules on the board in memory, for the DRC runs on boards saved without the project file."""
    settings = board.GetDesignSettings()
    settings.SetBoardThickness(mm(PCB["thickness"]))
    settings.m_TrackMinWidth = mm(DRC_RULES["min_track_width"])
    settings.m_MinClearance = mm(DRC_RULES["min_clearance"])
    settings.m_ViasMinSize = mm(DRC_RULES["min_via_diameter"])
    settings.m_MinThroughDrill = mm(DRC_RULES["min_through_hole_diameter"])
    settings.m_CopperEdgeClearance = mm(DRC_RULES["min_copper_edge_clearance"])
    settings.m_HoleClearance = mm(DRC_RULES["min_hole_clearance"])
    settings.m_HoleToHoleMin = mm(DRC_RULES["min_hole_to_hole"])
    settings.m_TentViasFront = True
    settings.m_TentViasBack = True
    default_class = settings.m_NetSettings.GetDefaultNetclass()
    default_class.SetTrackWidth(mm(TRACK_WIDTH))
    default_class.SetClearance(mm(CLEARANCE))
    default_class.SetViaDiameter(mm(VIA_DIAMETER))
    default_class.SetViaDrill(mm(VIA_DRILL))


def write_project_rules(project_path: Path, rules: Mapping[str, float] = DRC_RULES) -> None:
    """Writes the design rules into the KiCad project file, where kicad-cli's DRC reads them. Saving the board
    from Python does not write this file, so a missing one is started from a minimal skeleton."""
    if project_path.exists():
        project = json.loads(project_path.read_text())
    else:
        project = {"board": {"design_settings": {"rules": {}}},
                   "net_settings": {"classes": [{"name": "Default"}], "meta": {"version": 3}},
                   "meta": {"filename": project_path.name, "version": 1}}
    project["board"]["design_settings"]["rules"].update(rules)
    (default_class,) = [c for c in project["net_settings"]["classes"] if c["name"] == "Default"]
    default_class.update(DEFAULT_NET_CLASS)
    project_path.write_text(json.dumps(project, indent=2, sort_keys=True) + "\n")


def check_hole_keepouts(board: pcbnew.BOARD) -> None:
    """board.toml: no copper or parts on either face inside hole_keepout_diameter. Pads and courtyards here;
    the rule areas keep tracks, vias and pours out, and DRC checks those."""
    radius = PCB["hole_keepout_diameter"] / 2
    for x, y in hole_centres():
        for footprint in board.GetFootprints():
            if footprint.GetValue() == HOLE_VALUE:
                continue
            for pad in footprint.Pads():
                if pad.IsOnCopperLayer():
                    assert not circle_meets_rect(x, y, radius, box_mm(pad.GetBoundingBox())), \
                        f"{footprint.GetReference()} pad {pad.GetNumber()} inside the keep-out of the hole at ({x}, {y})"
            footprint.BuildCourtyardCaches()
            for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                courtyard = footprint.GetCourtyard(layer)
                if courtyard.OutlineCount():
                    assert not courtyard.Collide(point(x, y), mm(radius)), \
                        f"{footprint.GetReference()} courtyard inside the keep-out of the hole at ({x}, {y})"


def _courtyards(footprint: pcbnew.FOOTPRINT) -> dict[int, pcbnew.SHAPE_POLY_SET]:
    """Courtyard per face. A through-hole part's leads cross the board, so its courtyard holds on both faces."""
    footprint.BuildCourtyardCaches()
    found = {layer: footprint.GetCourtyard(layer) for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd)}
    found = {layer: shape for layer, shape in found.items() if shape.OutlineCount()}
    if footprint.GetAttributes() & pcbnew.FP_THROUGH_HOLE and len(found) == 1:
        (shape,) = found.values()
        found = {pcbnew.F_CrtYd: shape, pcbnew.B_CrtYd: shape}
    return found


def check_courtyards_apart(board: pcbnew.BOARD) -> None:
    """No two courtyards on one face overlap."""
    footprints = [(footprint.GetReference(), _courtyards(footprint)) for footprint in board.GetFootprints()]
    for index, (ref, courtyards) in enumerate(footprints):
        for other_ref, other_courtyards in footprints[index + 1:]:
            for layer in courtyards.keys() & other_courtyards.keys():
                if not courtyards[layer].BBox().Intersects(other_courtyards[layer].BBox()):
                    continue
                overlap = pcbnew.SHAPE_POLY_SET(courtyards[layer])
                overlap.BooleanIntersection(other_courtyards[layer])
                first, second = sorted((ref, other_ref))
                assert overlap.Area() == 0, f"{first} and {second} courtyards overlap on {pcbnew.LayerName(layer)}"


def check_paste_clear_of_vias(board: pcbnew.BOARD) -> None:
    """Board-wide: no solder-paste aperture comes within PASTE_TO_VIA_DRILL of a via's hole, and every via is
    covered by solder mask on the top face."""
    vias = [track for track in board.GetTracks() if track.GetClass() == "PCB_VIA"]
    for via in vias:
        assert via.IsTented(pcbnew.F_Mask), f"via at {pad_xy(via)} is not tented on the top face"
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            for layer in (pcbnew.F_Paste, pcbnew.B_Paste):
                if not pad.IsOnLayer(layer):
                    continue
                margin = pad.GetSolderPasteMargin(layer)
                left, top, right, bottom = box_mm(pad.GetBoundingBox())
                aperture = (left - pcbnew.ToMM(margin.x), top - pcbnew.ToMM(margin.y),
                            right + pcbnew.ToMM(margin.x), bottom + pcbnew.ToMM(margin.y))
                for via in vias:
                    reach = pcbnew.ToMM(via.GetDrillValue()) / 2 + PASTE_TO_VIA_DRILL
                    assert not circle_meets_rect(*pad_xy(via), reach, aperture), (
                        f"{footprint.GetReference()}: paste aperture at {pad_xy(pad)} is within "
                        f"{PASTE_TO_VIA_DRILL} mm of the via hole at {pad_xy(via)}")


def build_board(board_path: Path, parts: tuple[BoardPart, ...], open_pin_nets: Mapping[str, str]) -> pcbnew.BOARD:
    """open_pin_nets: "U1.14" -> the net name KiCad's schematic netlist gives that unconnected pin."""
    board = pcbnew.NewBoard(str(board_path))
    board.SetCopperLayerCount(PCB["layers"])
    _rules(board)
    _outline(board)
    for part in parts:
        _place(board, part, open_pin_nets)
    check_hole_keepouts(board)
    check_courtyards_apart(board)
    add_hole_keepouts(board)
    return board
