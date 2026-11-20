# SPDX-License-Identifier: CERN-OHL-S-2.0
"""PCB build steps. Run inside the KiCad container (`just pcb`).

    build.py          every step of PIPELINE, in order
    build.py place    board.toml + circuit -> the placed, unrouted board, checked by the contract
    build.py contract the saved board against board.toml: outline, holes, positions, antenna, carriers
    build.py drc      KiCad's DRC: the project rules reach it, and no warning is left

The schematic, routing and the order files join as steps in tasks 5.7 to 5.10.

Copied from macropad-greycode pcb/gen (decision D5), with `_check_rules_reach_drc` as macropad's
pcb/gen/build.py has it. Greycode's place and order steps are gone until this board has a circuit
and a routing plan; the DRC checks and the schematic check take their paths as arguments.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pcbnew

import circuit_hmi
import contract
import layout
import place
import schematic

PCB_DIR = Path(__file__).resolve().parents[1]
KICAD_DIR = PCB_DIR / "kicad"
BOARD_PATH = KICAD_DIR / f"{schematic.PROJECT}.kicad_pcb"
SCHEMATIC_PATH = KICAD_DIR / f"{schematic.PROJECT}.kicad_sch"
BUILD_DIR = PCB_DIR / ".build"
IMAGE_DIR = PCB_DIR.parent / "docs" / "images" / "pcb"
# Camera for the two angled renders, as kicad-cli wants it: degrees about X, Y, Z.
ASSEMBLED_VIEW_ROTATION = "-50,0,25"
UNDERSIDE_VIEW_ROTATION = "-130,0,-25"
# DRC findings that are meant: (kind, item). None yet.
ACCEPTED_FINDINGS: frozenset[tuple[str, str]] = frozenset()


def _kicad_cli(*arguments: str) -> None:
    subprocess.run(["kicad-cli", *arguments], check=True, stdout=subprocess.DEVNULL)


def _schematic_nets() -> dict[str, str]:
    """"U1.5" -> net, read back from the netlist KiCad exports for the schematic."""
    netlist_path = BUILD_DIR / "schematic.net"
    _kicad_cli("sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(netlist_path), str(SCHEMATIC_PATH))
    nets = {}
    for block in netlist_path.read_text().split("(net (code")[1:]:
        name = re.search(r'\(name "/?([^"]*)"\)', block).group(1)
        for ref, pin in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', block):
            nets[f"{ref}.{pin}"] = name
    return nets


def write_schematic(sheet: schematic.Sheet) -> dict[str, str]:
    """Schematic of the sheet, then KiCad's own view of it: rule check, and the netlist compared pin by pin.

    Returns the nets of the open pins ("U1.14" -> "unconnected-(U1-GPIO10-Pad14)") for the board."""
    BUILD_DIR.mkdir(exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    schematic.write(KICAD_DIR, sheet)
    _kicad_cli("sch", "erc", "--severity-all", "--exit-code-violations", "-o", str(BUILD_DIR / "erc.rpt"),
               str(SCHEMATIC_PATH))
    exported, wanted = _schematic_nets(), schematic.nets_by_pin(sheet.parts)
    open_pin_nets = {pin: net for pin, net in exported.items() if net.startswith(schematic.OPEN_PIN_NET_PREFIX)}
    drawn = {pin: net for pin, net in exported.items() if pin not in open_pin_nets}
    wrong = sorted(pin for pin in drawn.keys() | wanted.keys() if drawn.get(pin) != wanted.get(pin))
    assert not wrong, f"schematic and circuit disagree on {wrong}"
    _kicad_cli("sch", "export", "svg", "--exclude-drawing-sheet", "-o", str(BUILD_DIR), str(SCHEMATIC_PATH))
    (BUILD_DIR / f"{schematic.PROJECT}.svg").replace(IMAGE_DIR / "schematic.svg")
    _kicad_cli("sch", "export", "pdf", "-o", str(IMAGE_DIR / "schematic.pdf"), str(SCHEMATIC_PATH))
    print(f"schematic: ERC clean, {len(drawn)} pins match the circuit")
    return open_pin_nets


def _render(board_path: Path, name: str, *view: str) -> None:
    _kicad_cli("pcb", "render", *view, "--width", "1600", "--height", "1600", "--quality", "high",
               "--background", "opaque", "-o", str(IMAGE_DIR / f"{name}.png"), str(board_path))


def _write_bare_copy() -> Path:
    """The board without its part models, so the bare-board renders show the silkscreen."""
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    for footprint in board.GetFootprints():
        footprint.Models().clear()
    bare_path = BUILD_DIR / "bare.kicad_pcb"
    pcbnew.SaveBoard(str(bare_path), board)
    return bare_path


def write_images() -> None:
    """Renders of the bare and the populated board, and one drawing per copper layer."""
    bare_path = _write_bare_copy()
    for side in ("top", "bottom"):
        _render(bare_path, f"render-{side}", "--side", side)
        _render(BOARD_PATH, f"assembled-{side}", "--side", side)
    _render(BOARD_PATH, "assembled-angle", "--rotate", ASSEMBLED_VIEW_ROTATION, "--perspective", "--zoom", "0.75")
    _render(BOARD_PATH, "assembled-underside", "--rotate", UNDERSIDE_VIEW_ROTATION, "--perspective", "--zoom", "0.75")
    drawings = {"copper-top": "F.Cu", "copper-ground": pcbnew.LayerName(layout.GROUND_LAYER),
                "copper-power": pcbnew.LayerName(layout.POWER_LAYER), "copper-bottom": "B.Cu",
                "assembly-top": "F.SilkS,F.Mask,F.Fab", "assembly-bottom": "B.SilkS,B.Mask,B.Fab"}
    for name, layers in drawings.items():
        mirror = ["--mirror"] if name == "assembly-bottom" else []
        _kicad_cli("pcb", "export", "svg", "--layers", f"{layers},Edge.Cuts", "--exclude-drawing-sheet",
                   "--page-size-mode", "2", *mirror, "-o", str(IMAGE_DIR / f"{name}.svg"), str(BOARD_PATH))


def save_filled(board: pcbnew.BOARD, path: Path) -> None:
    pcbnew.SaveBoard(str(path), board)
    # Filled on a freshly loaded board: on the board still in memory the fill ignores the holes.
    reloaded = pcbnew.LoadBoard(str(path))
    pcbnew.ZONE_FILLER(reloaded).Fill(reloaded.Zones())
    pcbnew.SaveBoard(str(path), reloaded)


def check_rules_reach_drc(board_path: Path, work_dir: Path) -> None:
    """Proof that kicad-cli's DRC reads the rules write_project_rules put in the project file: a copy of the board
    with a project file that raises the minimum track width above the board's tracks must fail on track width."""
    probe_dir = work_dir / "rules-probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe_board = probe_dir / board_path.name
    shutil.copyfile(board_path, probe_board)
    shutil.copyfile(board_path.with_suffix(".kicad_pro"), probe_board.with_suffix(".kicad_pro"))
    too_wide = layout.TRACK_WIDTH + 0.05
    layout.write_project_rules(probe_board.with_suffix(".kicad_pro"), layout.DRC_RULES | {"min_track_width": too_wide})
    report_path = probe_dir / "drc.json"
    _kicad_cli("pcb", "drc", "--severity-error", "--format", "json", "-o", str(report_path), str(probe_board))
    kinds = {violation["type"] for violation in json.loads(report_path.read_text())["violations"]}
    assert "track_width" in kinds, f"DRC ignored a {too_wide} mm minimum track width in the project file: {kinds}"


def check_no_warnings(board_path: Path, work_dir: Path) -> None:
    """KiCad's warnings fail the build too: a track end that touches nothing, silkscreen over a pad or off the edge,
    a footprint, value or net that differs from the schematic."""
    report_path = work_dir / "drc-all.rpt"
    _kicad_cli("pcb", "drc", "--severity-all", "--schematic-parity", "-o", str(report_path), str(board_path))
    report = report_path.read_text()
    findings = re.findall(r"^\[(\w+)\][^\n]*\n[^\n]*\n[^\n]*: (.*)$", report, re.MULTILINE)
    unexpected = sorted(set(findings) - ACCEPTED_FINDINGS)
    assert not unexpected, f"DRC warnings {unexpected}; see {report_path}"
    kinds = set(re.findall(r"^\[(\w+)\]", report, re.MULTILINE))
    assert kinds <= {kind for kind, _ in ACCEPTED_FINDINGS}, f"DRC warnings {sorted(kinds)}; see {report_path}"
    for clean in ("unconnected pads", "Footprint errors"):
        assert f"Found 0 {clean}" in report, f"{clean}; see {report_path}"
    assert f"Found {len(findings)} DRC violations" in report, f"not every finding was read; see {report_path}"


def drc() -> None:
    BUILD_DIR.mkdir(exist_ok=True)
    check_rules_reach_drc(BOARD_PATH, BUILD_DIR)
    check_no_warnings(BOARD_PATH, BUILD_DIR)
    print("drc: the project rules reach DRC, no warnings")


def place_board() -> None:
    """The parts at their place.py spots on the board.toml outline, saved, then read back by the contract.
    Open pins stay without a net until the schematic step (task 5.7) names them."""
    KICAD_DIR.mkdir(exist_ok=True)
    layout.write_project_rules(BOARD_PATH.with_suffix(".kicad_pro"))
    parts = place.board_parts()
    board = layout.build_board(BOARD_PATH, parts, {})
    pcbnew.SaveBoard(str(BOARD_PATH), board)
    placeholders = sorted(part.ref for part in parts if "PLACEHOLDER_" in part.footprint)
    print(f"place: {len(parts)} footprints, {len(circuit_hmi.BOARD_PARTS)} circuit parts; provisional on "
          f"PLACEHOLDER_* tails {placeholders}")
    contract.check(pcbnew.LoadBoard(str(BOARD_PATH)))


STEPS = {"place": place_board, "contract": lambda: contract.check(pcbnew.LoadBoard(str(BOARD_PATH))), "drc": drc}
PIPELINE = ("place",)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        for name in PIPELINE:
            STEPS[name]()
        sys.exit()
    step = STEPS.get(sys.argv[1])
    if step is None:
        sys.exit(__doc__)
    step()
