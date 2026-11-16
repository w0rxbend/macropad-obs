# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Mechanical KiCad board and PCBWay files.

Copper is not routed. Passives whose netlist position is (0, 0) are omitted
from the silkscreen. Their BOM rows stay, with that origin, until a layout
pass moves them. This module imports pcbnew and runs only inside
kicad/kicad:9.0.9.
"""

from __future__ import annotations

import csv
import math
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD_PATH = ROOT / "pcb" / "kicad" / "macropad-obs.kicad_pcb"
FAB = ROOT / "pcb" / "fab"


def write_board() -> None:
    import pcbnew

    board_toml = tomllib.loads((ROOT / "board.toml").read_text())
    _write_tables(board_toml)
    board = pcbnew.BOARD()
    _outline(board, pcbnew, board_toml["pcb"])
    _holes(board, pcbnew, board_toml["pcb"])
    _silk(board, pcbnew, board_toml)
    BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    board.SetFileName(str(BOARD_PATH))
    pcbnew.SaveBoard(str(BOARD_PATH), board)
    gerbers = FAB / "gerbers"
    _plot(board, pcbnew, gerbers)
    _drill(board, pcbnew, gerbers)
    _prefix_empty_stem(gerbers)
    print(f"wrote {BOARD_PATH}")


def _write_tables(board_toml: dict) -> None:
    from circuit import build
    from fab import BOM_HEADER, CPL_HEADER, HAND_HEADER, bom_rows, cpl_rows, hand_rows

    board = build(board_toml)
    FAB.mkdir(parents=True, exist_ok=True)
    _csv(FAB / "bom-pcbway.csv", BOM_HEADER, bom_rows(board))
    _csv(FAB / "cpl-pcbway.csv", CPL_HEADER, cpl_rows(board))
    _csv(FAB / "hand.csv", HAND_HEADER, hand_rows(board))


def _csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def _mm(pcbnew, value: float) -> int:
    return pcbnew.FromMM(value)


def _point(pcbnew, x: float, y: float):
    return pcbnew.VECTOR2I(_mm(pcbnew, x), _mm(pcbnew, y))


def _add_segment(board, pcbnew, layer, x1, y1, x2, y2) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetLayer(layer)
    shape.SetStart(_point(pcbnew, x1, y1))
    shape.SetEnd(_point(pcbnew, x2, y2))
    shape.SetWidth(_mm(pcbnew, 0.1))
    board.Add(shape)


def _outline(board, pcbnew, pcb: dict) -> None:
    points = _rounded_loop(pcb["width"], pcb["depth"], pcb["corner_radius"])
    for start, end in zip(points, points[1:] + points[:1]):
        _add_segment(board, pcbnew, pcbnew.Edge_Cuts, start[0], start[1], end[0], end[1])


def _rounded_loop(width: float, depth: float, radius: float, steps: int = 6) -> list[tuple[float, float]]:
    corners = (
        (radius, radius, math.pi, math.pi / 2),
        (width - radius, radius, math.pi / 2, 0.0),
        (width - radius, depth - radius, 0.0, -math.pi / 2),
        (radius, depth - radius, -math.pi / 2, -math.pi),
    )
    points = []
    for cx, cy, start, end in corners:
        sweep = end - start
        for step in range(steps + 1):
            angle = start + sweep * step / steps
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


def _holes(board, pcbnew, pcb: dict) -> None:
    for index, (x, y) in enumerate(pcb["holes"], start=1):
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference(f"H{index}")
        footprint.SetPosition(_point(pcbnew, x, y))
        board.Add(footprint)
        pad = pcbnew.PAD(footprint)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        size = _point(pcbnew, pcb["hole_diameter"], pcb["hole_diameter"])
        pad.SetDrillSize(size)
        pad.SetSize(size)
        pad.SetPosition(_point(pcbnew, x, y))
        try:
            pad.SetLayerSet(pad.UnplatedHoleMask())
        except AttributeError:
            pad.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
        footprint.Add(pad)


def _silk(board, pcbnew, board_toml: dict) -> None:
    pcb = board_toml["pcb"]
    layer = pcbnew.F_SilkS
    ox, oy = pcb["display_origin"]
    width, height = pcb["display_size"]
    _rect(board, pcbnew, layer, ox, oy, width, height)
    for key_x in pcb["key_x"]:
        for key_y in pcb["key_y"]:
            _rect(board, pcbnew, layer, key_x - 7, key_y - 7, 14, 14)
    knob_x, knob_y = pcb["knob"]
    _rect(board, pcbnew, layer, knob_x - 6, knob_y - 6, 12, 12)
    text = pcbnew.PCB_TEXT(board)
    text.SetText("macropad-obs")
    text.SetLayer(layer)
    text.SetPosition(_point(pcbnew, 44, 8))
    text.SetTextSize(_point(pcbnew, 1.2, 1.2))
    text.SetTextThickness(_mm(pcbnew, 0.15))
    board.Add(text)


def _rect(board, pcbnew, layer, x: float, y: float, width: float, height: float) -> None:
    corners = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    for start, end in zip(corners, corners[1:] + corners[:1]):
        _add_segment(board, pcbnew, layer, start[0], start[1], end[0], end[1])


def _plot(board, pcbnew, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        old.unlink()
    plotter = pcbnew.PLOT_CONTROLLER(board)
    options = plotter.GetPlotOptions()
    options.SetOutputDirectory(str(folder))
    options.SetPlotFrameRef(False)
    options.SetDrillMarksType(pcbnew.DRILL_MARKS_NO_DRILL_SHAPE)
    layers = (
        (pcbnew.F_Cu, "F_Cu"),
        (pcbnew.B_Cu, "B_Cu"),
        (pcbnew.F_SilkS, "F_SilkS"),
        (pcbnew.B_SilkS, "B_SilkS"),
        (pcbnew.F_Mask, "F_Mask"),
        (pcbnew.B_Mask, "B_Mask"),
        (pcbnew.Edge_Cuts, "Edge_Cuts"),
    )
    for layer, name in layers:
        plotter.SetLayer(layer)
        plotter.OpenPlotfile(name, pcbnew.PLOT_FORMAT_GERBER, name)
        plotter.PlotLayer()
    plotter.ClosePlot()


def _prefix_empty_stem(folder: Path) -> None:
    """KiCad names files from the board stem. An empty stem yields '-F_Cu.gbr'."""
    for path in folder.iterdir():
        if path.name.startswith("-"):
            path.rename(folder / f"macropad-obs{path.name}")


def _drill(board, pcbnew, folder: Path) -> None:
    writer = pcbnew.EXCELLON_WRITER(board)
    writer.SetOptions(False, False, pcbnew.VECTOR2I(0, 0), False)
    writer.SetFormat(True)
    writer.CreateDrillandMapFilesSet(str(folder), True, False)
