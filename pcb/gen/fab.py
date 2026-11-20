# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Assembly files from the routed board: JLCPCB bill of materials and component placement list, and the checks
that they agree with the board, the Gerbers and the drill file.

Gerbers and drill files come from kicad-cli (`just pcb`). Runs inside the KiCad container.

Copied from macropad-greycode pcb/gen (decision D5). The parts come in as `FabPart`s instead of
greycode's circuit module. An LCSC cell that is not a JLCPCB number (UNVERIFIED) fails `check_outputs`.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Protocol

import pcbnew

import schematic

FAB_DIR = Path(__file__).resolve().parents[1] / "fab"
# The board's SHA-256 when the order files were last written. test_order_files.py (task 5.10) compares it.
BOARD_HASH_PATH = FAB_DIR / "board-sha256.txt"
BOM_COLUMNS = ["Comment", "Designator", "Footprint", "LCSC Part #", "Manufacturer", "Manufacturer Part #"]


class FabPart(Protocol):
    """What the order files need of a circuit's part."""
    ref: str
    value: str
    footprint: str                         # "library:name"
    lcsc: str
    manufacturer_part: tuple[str, str]     # manufacturer, part number
    machine_assembled: bool


def _bom_lines(parts: tuple[FabPart, ...]) -> list[tuple[FabPart, list[str]]]:
    """One line per distinct machine-placed part: a sample part and every reference that uses it.
    Hand-soldered parts are not listed here."""
    refs_by_part: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    sample: dict[tuple[str, str, str], FabPart] = {}
    for part in parts:
        if part.machine_assembled:
            key = (part.value, _package(part), part.lcsc)
            refs_by_part[key].append(part.ref)
            sample.setdefault(key, part)
    return [(sample[key], refs_by_part[key]) for key in sorted(refs_by_part)]


def _package(part: FabPart) -> str:
    return part.footprint.split(":")[1]


def write_bom(parts: tuple[FabPart, ...], path: Path) -> None:
    with path.open("w", newline="") as bom_file:
        writer = csv.writer(bom_file)
        writer.writerow(BOM_COLUMNS)
        for part, refs in _bom_lines(parts):
            writer.writerow([part.value, ",".join(refs), _package(part), part.lcsc, *part.manufacturer_part])


def _body_centre(footprint: pcbnew.FOOTPRINT) -> tuple[float, float]:
    """Centre of the part body, drawn on the fabrication layer: where the pick-and-place nozzle holds the part.

    Not the centre of the SMD pads: a USB receptacle's SMD pads can sit in one row behind its body. Not the
    footprint origin either: the hot-swap socket's origin is the switch centre. A footprint with no body
    outline falls back to the centre of its pads.
    """
    fab_layers = (pcbnew.F_Fab, pcbnew.B_Fab)
    boxes = [item.GetBoundingBox() for item in footprint.GraphicalItems()
             if item.GetLayer() in fab_layers and item.GetClass() == "PCB_SHAPE"]
    if not boxes:
        boxes = [pad.GetBoundingBox() for pad in footprint.Pads()]
    left = min(pcbnew.ToMM(box.GetLeft()) for box in boxes)
    right = max(pcbnew.ToMM(box.GetRight()) for box in boxes)
    top = min(pcbnew.ToMM(box.GetTop()) for box in boxes)
    bottom = max(pcbnew.ToMM(box.GetBottom()) for box in boxes)
    return (left + right) / 2, (top + bottom) / 2


def _placed_footprints(board: pcbnew.BOARD, parts: tuple[FabPart, ...]) -> list[pcbnew.FOOTPRINT]:
    machine_assembled = {part.ref for part in parts if part.machine_assembled}
    return sorted((fp for fp in board.GetFootprints() if fp.GetReference() in machine_assembled),
                  key=lambda fp: fp.GetReference())


def _side(footprint: pcbnew.FOOTPRINT) -> str:
    return "Bottom" if footprint.IsFlipped() else "Top"


def _rotation(footprint: pcbnew.FOOTPRINT) -> str:
    """KiCad's rotation, unchanged on both faces. Check it in the assembler's preview."""
    return f"{footprint.GetOrientationDegrees() % 360:.0f}"


def write_placement(board: pcbnew.BOARD, parts: tuple[FabPart, ...], path: Path) -> None:
    rows = []
    for footprint in _placed_footprints(board, parts):
        x, y = _body_centre(footprint)
        # KiCad's Y axis points down; JLCPCB's placement file wants Y up.
        rows.append([footprint.GetReference(), f"{x:.3f}mm", f"{-y:.3f}mm", _side(footprint), _rotation(footprint)])
    with path.open("w", newline="") as placement_file:
        writer = csv.writer(placement_file)
        writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        writer.writerows(rows)


GERBER_SUFFIXES = ("F_Cu.gtl", "In1_Cu.g1", "In2_Cu.g2", "B_Cu.gbl", "F_Paste.gtp", "B_Paste.gbp",
                   "F_Silkscreen.gto", "B_Silkscreen.gbo", "F_Mask.gts", "B_Mask.gbs", "Edge_Cuts.gm1")


def _drill_hits_by_diameter(drill_path: Path) -> dict[str, int]:
    """Excellon file -> hole count per tool diameter ("0.300")."""
    diameter_of_tool: dict[str, str] = {}
    hits: dict[str, int] = defaultdict(int)
    current = ""
    for line in drill_path.read_text().splitlines():
        tool = re.fullmatch(r"(T\d+)(?:C([\d.]+))?", line)
        if tool and tool.group(2):
            diameter_of_tool[tool.group(1)] = tool.group(2)
        elif tool:
            current = diameter_of_tool[tool.group(1)]
        elif line.startswith("X") and "G85" not in line:
            hits[current] += 1
    return dict(hits)


def check_outputs(board: pcbnew.BOARD, parts: tuple[FabPart, ...]) -> None:
    """The files in pcb/fab/ agree with the board and with each other. Run after the Gerber export."""
    gerber_dir = FAB_DIR / "gerbers"
    board_written = Path(board.GetFileName()).stat().st_mtime
    for suffix in GERBER_SUFFIXES:
        gerber = gerber_dir / f"{schematic.PROJECT}-{suffix}"
        assert gerber.is_file() and gerber.stat().st_size > 0, f"missing or empty {gerber}"
        assert gerber.stat().st_mtime >= board_written, f"{gerber.name} is older than the board"

    via_drills = {f"{pcbnew.ToMM(track.GetDrillValue()):.3f}" for track in board.GetTracks()
                  if track.GetClass() == "PCB_VIA"}
    assert len(via_drills) == 1, f"vias with different drills: {via_drills}"
    via_count = sum(track.GetClass() == "PCB_VIA" for track in board.GetTracks())
    drilled = _drill_hits_by_diameter(gerber_dir / f"{schematic.PROJECT}-PTH.drl").get(via_drills.pop(), 0)
    assert drilled == via_count, f"{via_count} vias on the board, {drilled} in the drill file"
    npth = sum(_drill_hits_by_diameter(gerber_dir / f"{schematic.PROJECT}-NPTH.drl").values())
    board_npth = sum(pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH for fp in board.GetFootprints() for pad in fp.Pads())
    assert npth == board_npth, f"{board_npth} unplated holes on the board, {npth} in the drill file"

    machine_assembled = {part.ref for part in parts if part.machine_assembled}
    bom_rows = _read_csv("bom-jlcpcb.csv")
    placement_rows = _read_csv("cpl-jlcpcb.csv")
    placed = [row["Designator"] for row in placement_rows]
    listed = [ref for row in bom_rows for ref in row["Designator"].split(",")]
    assert sorted(listed) == sorted(placed) == sorted(machine_assembled), "BOM, placement list and circuit differ"
    assert len(placed) == len(set(placed)), "a part is placed twice"
    assert {row["Layer"] for row in placement_rows} <= {"Top", "Bottom"}, "side is not Top or Bottom"
    unnumbered = [row["Comment"] for row in bom_rows if not re.fullmatch(r"C\d+", row["LCSC Part #"])]
    assert not unnumbered, f"no JLCPCB part number for {unnumbered}"
    no_mpn = [row["Comment"] for row in bom_rows if not (row["Manufacturer"] and row["Manufacturer Part #"])]
    assert not no_mpn, f"no manufacturer part number for {no_mpn}"
    value = {part.ref: part.value for part in parts}
    for row in bom_rows:
        for ref in row["Designator"].split(","):
            footprint = board.FindFootprintByReference(ref)
            assert footprint.GetValue() == value[ref] == row["Comment"], f"{ref}: value differs from the board"
            assert footprint.GetFieldText("LCSC") == row["LCSC Part #"], f"{ref}: LCSC number differs from the board"
    _check_placement_on_parts(board, placement_rows, lambda y: -y)
    for row in placement_rows:
        footprint = board.FindFootprintByReference(row["Designator"])
        assert row["Layer"] == _side(footprint) and row["Rotation"] == _rotation(footprint), \
            f"{row['Designator']}: side or rotation differs from the board"


def _read_csv(name: str) -> list[dict[str, str]]:
    with (FAB_DIR / name).open() as csv_file:
        return list(csv.DictReader(csv_file))


def board_hash(board_path: Path) -> str:
    return hashlib.sha256(board_path.read_bytes()).hexdigest()


def _check_placement_on_parts(board: pcbnew.BOARD, placement_rows: list[dict[str, str]], to_kicad_y) -> None:
    """Every placement point lies inside its own part's courtyard, so the nozzle lands on the part."""
    for row in placement_rows:
        footprint = board.FindFootprintByReference(row["Designator"])
        footprint.BuildCourtyardCaches()
        x, y = float(row["Mid X"].removesuffix("mm")), to_kicad_y(float(row["Mid Y"].removesuffix("mm")))
        courtyard = footprint.GetCourtyard(pcbnew.B_CrtYd if footprint.IsFlipped() else pcbnew.F_CrtYd)
        assert courtyard.OutlineCount() and courtyard.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))), \
            f"{row['Designator']}: placement point ({x:.3f}, {y:.3f}) is not on the part"


def write_assembly_files(board_path: Path, parts: tuple[FabPart, ...]) -> None:
    FAB_DIR.mkdir(exist_ok=True)
    board = pcbnew.LoadBoard(str(board_path))
    write_bom(parts, FAB_DIR / "bom-jlcpcb.csv")
    write_placement(board, parts, FAB_DIR / "cpl-jlcpcb.csv")
    check_outputs(board, parts)
    BOARD_HASH_PATH.write_text(f"{board_hash(board_path)}  {board_path.name}\n")
    assembled = sum(part.machine_assembled for part in parts)
    lines = len(_bom_lines(parts))
    print(f"assembly files: {assembled} machine-placed parts on {lines} BOM lines; Gerbers, drill files, "
          "BOM and placement list agree with the board")
