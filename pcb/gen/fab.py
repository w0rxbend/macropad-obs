# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The JLCPCB file set from the routed board: Gerbers and drill files from kicad-cli, their zip, the bill of
materials and component placement list, the routing summary and the board's SHA-256, and the checks that they
agree with the board and with each other. Runs inside the KiCad container (`just pcb fab`).

KiCad stamps each Gerber, drill and job file with the time it wrote it; `without_dates` drops those stamps and
`write_zip` fixes the member times, so the set is byte-repeatable from the same board.

Copied from macropad-greycode pcb/gen (decision D5). The parts come in as `FabPart`s instead of
greycode's circuit module. LCSC cells stay UNVERIFIED (CLAUDE.md), so a BOM line without a JLCPCB number or a
manufacturer part number does not fail the set: `order_blockers` lists it, and the owner's upload (F.1) and
`just gate` decide on ordering.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Protocol

import pcbnew

import schematic

FAB_DIR = Path(__file__).resolve().parents[1] / "fab"
# In each fab folder: the board's SHA-256 when the set was written, and the board's DRC counts and copper.
# test_order_files.py compares both with the committed board.
BOARD_HASH_NAME = "board-sha256.txt"
ROUTING_NAME = "routing.txt"
GERBER_LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
# Midnight of 1980-01-01, the earliest time a zip member can carry.
ZIP_MEMBER_TIME = (1980, 1, 1, 0, 0, 0)
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


_GERBER_DATE = re.compile(r"^(G04 Created by KiCad \([^)]*\)) date [^*]*\*$", re.MULTILINE)
_DRILL_DATE = re.compile(r"^(; DRILL file \{[^}]*\}) date \S+$", re.MULTILINE)
_X2_DATE = re.compile(r"^(%TF\.CreationDate,[^*]*\*%|; #@! TF\.CreationDate,.*)\n", re.MULTILINE)


def without_dates(name: str, text: str) -> str:
    """A Gerber, drill or job file as KiCad wrote it, less the time it wrote it. The X2 creation date is optional."""
    if name.endswith(".gbrjob"):
        job = json.loads(text)
        del job["Header"]["CreationDate"]
        return json.dumps(job, indent=2) + "\n"
    text = _X2_DATE.sub("", text)
    text = _GERBER_DATE.sub(r"\1*", text)
    return _DRILL_DATE.sub(r"\1", text)


def write_gerbers(board_path: Path, gerber_dir: Path) -> None:
    """kicad-cli's Gerbers and Excellon drill files (plated and unplated apart), without their dates."""
    gerber_dir.mkdir(parents=True)
    subprocess.run(["kicad-cli", "pcb", "export", "gerbers", "--layers", GERBER_LAYERS, "--subtract-soldermask",
                    "-o", f"{gerber_dir}/", str(board_path)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm",
                    "--excellon-separate-th", "-o", f"{gerber_dir}/", str(board_path)],
                   check=True, stdout=subprocess.DEVNULL)
    for path in gerber_dir.iterdir():
        path.write_text(without_dates(path.name, path.read_text()))


def write_zip(gerber_dir: Path, zip_path: Path) -> None:
    """The folder as the zip the board house takes: members in name order, each at the same fixed time."""
    with zipfile.ZipFile(zip_path, "w") as archive:
        for path in sorted(gerber_dir.iterdir()):
            member = zipfile.ZipInfo(f"{gerber_dir.name}/{path.name}", ZIP_MEMBER_TIME)
            member.compress_type = zipfile.ZIP_DEFLATED
            member.external_attr = 0o644 << 16
            archive.writestr(member, path.read_bytes())


def differing_files(first: Path, second: Path) -> list[str]:
    """Relative paths of the files that differ between two folders, or that only one of them holds."""
    def files(root: Path) -> dict[str, Path]:
        return {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_file()}
    in_first, in_second = files(first), files(second)
    return sorted(name for name in in_first.keys() | in_second.keys()
                  if name not in in_first or name not in in_second
                  or in_first[name].read_bytes() != in_second[name].read_bytes())


_WHERE = {"bom": "in the BOM", "placement": "in the placement list", "board": "on the board"}
_PAIRS = (("bom", "placement"), ("bom", "board"), ("placement", "bom"), ("placement", "board"), ("board", "bom"),
          ("board", "placement"))


def reference_mismatches(bom_refs: list[str], placement_refs: list[str], board_refs: set[str]) -> list[str]:
    """Each reference the BOM, the placement list and the board's placed footprints do not all name once."""
    found = [f"{ref}: twice {_WHERE[name]}" for name, refs in (("bom", bom_refs), ("placement", placement_refs))
             for ref in sorted({ref for ref in refs if refs.count(ref) > 1})]
    named = {"bom": set(bom_refs), "placement": set(placement_refs), "board": board_refs}
    for ref in sorted(set().union(*named.values())):
        found += [f"{ref}: {_WHERE[here]}, not {_WHERE[there]}" for here, there in _PAIRS
                  if ref in named[here] and ref not in named[there]]
    return found


def order_blockers(bom_rows: list[dict[str, str]]) -> list[str]:
    """BOM lines JLCPCB cannot buy from yet: no JLCPCB part number, or no manufacturer part number."""
    found = []
    for row in bom_rows:
        line = f"{row['Designator']} {row['Comment']}"
        if not re.fullmatch(r"C\d+", row["LCSC Part #"]):
            found.append(f"{line}: no JLCPCB part number ({row['LCSC Part #']})")
        if not (row["Manufacturer"] and row["Manufacturer Part #"]):
            found.append(f"{line}: no manufacturer part number")
    return found


def check_outputs(board: pcbnew.BOARD, parts: tuple[FabPart, ...], fab_dir: Path) -> None:
    """The files in fab_dir agree with the board and with each other. Run after the Gerber export."""
    gerber_dir = fab_dir / "gerbers"
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
    bom_rows = _read_csv(fab_dir / "bom-jlcpcb.csv")
    placement_rows = _read_csv(fab_dir / "cpl-jlcpcb.csv")
    placed = [row["Designator"] for row in placement_rows]
    listed = [ref for row in bom_rows for ref in row["Designator"].split(",")]
    on_board = {fp.GetReference() for fp in board.GetFootprints() if not fp.IsExcludedFromPosFiles()}
    mismatched = reference_mismatches(listed, placed, on_board)
    assert not mismatched, f"BOM, placement list and board differ: {mismatched}"
    assert on_board == machine_assembled, "the board's placed footprints and the circuit's machine-placed parts differ"
    assert {row["Layer"] for row in placement_rows} <= {"Top", "Bottom"}, "side is not Top or Bottom"
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


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open() as csv_file:
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


def routing_summary(board: pcbnew.BOARD, drc_counts: dict[str, int]) -> str:
    """One line: the DRC counts the routed board was judged by, then its tracks and vias."""
    counts = "  ".join(f"{name} {count}" for name, count in drc_counts.items())
    tracks = sum(item.GetClass() == "PCB_TRACK" for item in board.GetTracks())
    vias = sum(item.GetClass() == "PCB_VIA" for item in board.GetTracks())
    return f"{counts}  tracks {tracks}  vias {vias}\n"


def write_set(board_path: Path, parts: tuple[FabPart, ...], fab_dir: Path, drc_counts: dict[str, int]) -> list[str]:
    """The whole set into an emptied fab_dir, checked against the board. Returns the BOM's order blockers."""
    shutil.rmtree(fab_dir, ignore_errors=True)
    write_gerbers(board_path, fab_dir / "gerbers")
    write_zip(fab_dir / "gerbers", fab_dir / f"{schematic.PROJECT}-gerbers.zip")
    board = pcbnew.LoadBoard(str(board_path))
    write_bom(parts, fab_dir / "bom-jlcpcb.csv")
    write_placement(board, parts, fab_dir / "cpl-jlcpcb.csv")
    check_outputs(board, parts, fab_dir)
    (fab_dir / ROUTING_NAME).write_text(routing_summary(board, drc_counts))
    (fab_dir / BOARD_HASH_NAME).write_text(f"{board_hash(board_path)}  {board_path.name}\n")
    return order_blockers(_read_csv(fab_dir / "bom-jlcpcb.csv"))
