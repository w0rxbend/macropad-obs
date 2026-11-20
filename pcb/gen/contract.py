# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The board against board.toml, read independently of layout.py's placement code. Needs pcbnew.

    build.py contract

Checks the outline, the layer count and thickness, and every M2 hole with its keep-out. Prints one
line per group. The part positions and GPIO nets join as groups once the circuit lands (tasks 5.4 to 5.6).

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


def _xy(vector: pcbnew.VECTOR2I) -> tuple[float, float]:
    return pcbnew.ToMM(vector.x), pcbnew.ToMM(vector.y)


def _spec_xy(x: float, y: float) -> tuple[float, float]:
    """board.toml (front-left origin, y towards the back edge) -> KiCad (back-left origin, y towards the front).
    Written out here again on purpose: this check does not trust layout.kicad_xy."""
    return x, PCB["depth"] - y


def _near(actual: tuple[float, float], expected: tuple[float, float], what: str) -> None:
    assert math.dist(actual, expected) < TOLERANCE, f"{what} is at {actual}, board.toml says {expected}"


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
    arcs = [item for item in edges if item.GetShape() == pcbnew.SHAPE_T_ARC]
    assert len(arcs) == 4, f"{len(arcs)} rounded corners"
    for arc in arcs:
        radius = pcbnew.ToMM(arc.GetRadius())
        assert abs(radius - PCB["corner_radius"]) < TOLERANCE, f"corner radius {radius}"
    assert board.GetCopperLayerCount() == PCB["layers"], f"{board.GetCopperLayerCount()} copper layers"
    thickness = pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness())
    assert abs(thickness - PCB["thickness"]) < TOLERANCE, f"board thickness {thickness}"
    return f"outline {PCB['width']} x {PCB['depth']} mm, r {PCB['corner_radius']}, {PCB['layers']} layers"


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


CHECKS = (check_outline, check_holes)


def check(board: pcbnew.BOARD) -> None:
    for step in CHECKS:
        print(f"contract: {step(board)}")
    print(f"contract: {len(CHECKS)} groups match board.toml")
