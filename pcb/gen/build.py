# SPDX-License-Identifier: CERN-OHL-S-2.0
"""PCB build steps. Run inside the KiCad container (`just pcb`).

    build.py          every step of PIPELINE, in order
    build.py erc      the circuit -> the schematic, KiCad's ERC on it, its netlist against the circuit
    build.py place    board.toml + circuit -> the placed, unrouted board, checked by the contract
    build.py route-critical  place, then route.py's critical copper locked, the planes and the antenna
                      keep-out; route.py's limits, the contract and KiCad's DRC with no violation
    build.py dsn      route-critical, then the board as a Specctra DSN for Freerouting (freeroute.py)
    build.py routed   Freerouting's session read back, filled, and judged: the contract, the locks, and
                      KiCad's DRC at error severity with 0 violations, 0 unconnected, 0 parity (criterion 10)
    build.py fab      the routed board judged again, then the JLCPCB set (fab.py) written twice and compared byte
                      for byte; into pcb/fab, or into pcb/.build/fab while a PLACEHOLDER_* footprint is on it
    build.py contract the saved board against board.toml: outline, holes, positions, antenna, carriers
    build.py drc      KiCad's DRC: the project rules reach it, and no warning is left

Several steps run in order: `build.py erc dsn`. Freerouting runs between `dsn` and `routed`, on the host in
its own image (`just pcb route`); `fab` follows `routed`.

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
import fab
import freeroute
import layout
import place
import route
import schematic
import sheets

PCB_DIR = Path(__file__).resolve().parents[1]
KICAD_DIR = PCB_DIR / "kicad"
BOARD_PATH = KICAD_DIR / f"{schematic.PROJECT}.kicad_pcb"
SCHEMATIC_PATH = KICAD_DIR / f"{schematic.PROJECT}.kicad_sch"
BUILD_DIR = PCB_DIR / ".build"
NETLIST_PATH = BUILD_DIR / "schematic.net"
# The fab set while the board still stands on PLACEHOLDER_* footprints: test_footprints.py keeps them out of pcb/fab.
PROVISIONAL_FAB_DIR = BUILD_DIR / "fab"
IMAGE_DIR = PCB_DIR.parent / "docs" / "images" / "pcb"
# Camera for the two angled renders, as kicad-cli wants it: degrees about X, Y, Z.
ASSEMBLED_VIEW_ROTATION = "-50,0,25"
UNDERSIDE_VIEW_ROTATION = "-130,0,-25"
# The session's tracks and vias get the same UUIDs on every run.
KIID_SEED = 1
# DRC findings that are meant: (kind, item). U1 differs from its library copy because layout.py trims the
# module's silkscreen that lies in the antenna board cut, where the fab house would clip it.
ACCEPTED_FINDINGS: frozenset[tuple[str, str]] = frozenset({("lib_footprint_mismatch", "Footprint U1")})


def _kicad_cli(*arguments: str) -> None:
    subprocess.run(["kicad-cli", *arguments], check=True, stdout=subprocess.DEVNULL)


def read_netlist(netlist_path: Path) -> dict[str, str]:
    """"U1.5" -> net, from a netlist KiCad exported for the schematic."""
    nets = {}
    for block in netlist_path.read_text().split("(net (code")[1:]:
        name = re.search(r'\(name "/?([^"]*)"\)', block).group(1)
        for ref, pin in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', block):
            nets[f"{ref}.{pin}"] = name
    return nets


def open_pin_nets(nets: dict[str, str]) -> dict[str, str]:
    """The nets of the open pins ("U1.14" -> "unconnected-(U1-GPIO10-Pad14)"): the board must carry them too."""
    return {pin: net for pin, net in nets.items() if net.startswith(schematic.OPEN_PIN_NET_PREFIX)}


def _schematic_nets() -> dict[str, str]:
    """"U1.5" -> net, read back from the netlist KiCad exports for the schematic."""
    _kicad_cli("sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(NETLIST_PATH), str(SCHEMATIC_PATH))
    return read_netlist(NETLIST_PATH)


def write_schematic(sheet: schematic.Sheet) -> None:
    """Schematic of the sheet, then KiCad's own view of it: rule check, and the netlist compared pin by pin.
    The netlist stays in NETLIST_PATH, where place_board reads the open pins' nets."""
    BUILD_DIR.mkdir(exist_ok=True)
    KICAD_DIR.mkdir(exist_ok=True)
    # The project file is where kicad-cli finds the project's sym-lib-table, so it must exist before ERC.
    layout.write_project_rules(BOARD_PATH.with_suffix(".kicad_pro"))
    schematic.write(KICAD_DIR, sheet)
    _kicad_cli("sch", "erc", "--severity-all", "--exit-code-violations", "-o", str(BUILD_DIR / "erc.rpt"),
               str(SCHEMATIC_PATH))
    exported, wanted = _schematic_nets(), schematic.nets_by_pin(sheet.parts)
    open_pins = open_pin_nets(exported)
    drawn = {pin: net for pin, net in exported.items() if pin not in open_pins}
    wrong = sorted(pin for pin in drawn.keys() | wanted.keys() if drawn.get(pin) != wanted.get(pin))
    assert not wrong, f"schematic and circuit disagree on {wrong}"
    print(f"schematic: ERC clean, {len(drawn)} pins match the circuit")


SCHEMATIC_FILES = (f"{schematic.PROJECT}.kicad_sch", f"{schematic.PROJECT}.kicad_sym", "sym-lib-table", "fp-lib-table")


def check_schematic_repeatable(sheet: schematic.Sheet) -> None:
    """The sheet written a second time, into an empty folder, is the same bytes as the saved one."""
    again_dir = BUILD_DIR / "schematic-again"
    shutil.rmtree(again_dir, ignore_errors=True)
    again_dir.mkdir(parents=True)
    schematic.write(again_dir, sheet)
    differ = [name for name in SCHEMATIC_FILES if (again_dir / name).read_bytes() != (KICAD_DIR / name).read_bytes()]
    assert not differ, f"a second write of the schematic differs in {differ}"
    print(f"schematic: byte-repeatable, {len(SCHEMATIC_FILES)} files")


def erc() -> None:
    write_schematic(sheets.SHEET)
    check_schematic_repeatable(sheets.SHEET)


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
    widths = [pcbnew.ToMM(track.GetWidth()) for track in pcbnew.LoadBoard(str(board_path)).GetTracks()
              if track.GetClass() == "PCB_TRACK"]
    assert widths, f"{board_path.name} has no track for the rules probe"
    too_wide = min(widths) + 0.05
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


def place_board(board_path: Path = BOARD_PATH, netlist_path: Path = NETLIST_PATH) -> None:
    """The parts at their place.py spots on the board.toml outline, saved, then read back by the contract.
    Each open pin gets the net the schematic's netlist (from `build.py erc`) names for it."""
    assert netlist_path.exists(), f"no {netlist_path}: run `build.py erc` first"
    board_path.parent.mkdir(exist_ok=True)
    layout.write_project_rules(board_path.with_suffix(".kicad_pro"))
    parts = place.board_parts()
    board = layout.build_board(board_path, parts, open_pin_nets(read_netlist(netlist_path)))
    pcbnew.SaveBoard(str(board_path), board)
    placeholders = sorted(part.ref for part in parts if "PLACEHOLDER_" in part.footprint)
    print(f"place: {len(parts)} footprints, {len(circuit_hmi.BOARD_PARTS)} circuit parts; provisional on "
          f"PLACEHOLDER_* tails {placeholders}")
    contract.check(pcbnew.LoadBoard(str(board_path)))


def check_locked(board: pcbnew.BOARD, result: route.Result) -> None:
    """The board's copper is route.py's, every track and via of it locked."""
    items = list(board.GetTracks())
    wanted = len(result.tracks) + len(result.vias)
    assert len(items) == wanted, f"{len(items)} tracks and vias on the board, route.py drew {wanted}"
    loose = [layout.pad_xy(item) for item in items if not item.IsLocked()]  # a track's position is its start
    assert not loose, f"copper not locked at {loose[:5]}"


def check_clearances(board_path: Path, work_dir: Path, whole_nets: frozenset[str]) -> int:
    """KiCad's DRC at error severity finds no violation, and no unconnected item on a net the critical copper
    draws whole. Returns the unconnected items left: the nets for the autorouter (task 5.9) still have them."""
    report_path = work_dir / "drc-critical.json"
    _kicad_cli("pcb", "drc", "--severity-error", "--format", "json", "-o", str(report_path), str(board_path))
    report = json.loads(report_path.read_text())
    found = sorted({(violation["type"], violation["description"]) for violation in report["violations"]})
    assert not found, f"DRC: {found}; see {report_path}"
    open_nets = {schematic.circuit_net_name(net) for item in report["unconnected_items"]
                 for end in item["items"] for net in re.findall(r"\[([^\]]+)\]", end["description"])}
    assert not open_nets & whole_nets, f"DRC finds {sorted(open_nets & whole_nets)} unconnected; see {report_path}"
    return len(report["unconnected_items"])


def route_critical() -> None:
    """The placed board, then route.py's critical copper written locked, the planes and the antenna keep-out,
    filled on a reloaded board and checked."""
    place_board()
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    order = route.read_order(route.ORDER_PATH.read_text())
    result = route.route(*layout.router_obstacles(board), order)
    for line in result.report_lines():
        print(line)
    found = route.problems(result)
    assert not found, f"critical copper: {found}"
    layout.write_locked_copper(board, result.tracks, result.vias, route.RULES)
    layout.add_planes(board, route.planes())
    layout.add_copper_keepout(board, route.antenna_keepout())
    for rect in route.slot_keepouts():
        layout.add_copper_keepout(board, rect)
    layout.add_encoder_post_keepouts(board)
    save_filled(board, BOARD_PATH)
    routed = pcbnew.LoadBoard(str(BOARD_PATH))
    check_locked(routed, result)
    print(f"route-critical: {len(result.tracks)} tracks and {len(result.vias)} vias, all locked")
    inside = contract.copper_in(routed, route.antenna_keepout())
    assert not inside, f"copper within {route.ANTENNA_SETBACK} mm of the antenna board cut: {inside}"
    layout.check_paste_clear_of_vias(routed)
    print(f"route-critical: no copper within {route.ANTENNA_SETBACK} mm of the antenna cut, paste clear of the vias")
    contract.check(routed)
    check_rules_reach_drc(BOARD_PATH, BUILD_DIR)
    whole = route.whole_nets(order)
    unconnected = check_clearances(BOARD_PATH, BUILD_DIR, whole)
    print(f"route-critical: DRC 0 violations, {len(whole)} nets drawn whole and connected; "
          f"{unconnected} unconnected items left for the autorouter")


def write_dsn() -> None:
    """route-critical, then the board as Freerouting reads it. The inner planes go with it, so the supply vias
    count as joined; pcb/outer.rules keeps the router off those layers."""
    route_critical()
    freeroute.WORK_DIR.mkdir(parents=True, exist_ok=True)
    assert pcbnew.ExportSpecctraDSN(pcbnew.LoadBoard(str(BOARD_PATH)), str(freeroute.DSN_PATH)), "DSN export failed"
    print(f"dsn: wrote {freeroute.DSN_PATH.relative_to(PCB_DIR)}")


def _locked_items(board: pcbnew.BOARD) -> list[tuple]:
    return sorted((item.GetClass(), layout.pad_xy(item), item.GetNetname()) for item in board.GetTracks()
                  if item.IsLocked())


DRC_KINDS = ("violations", "unconnected_items", "schematic_parity")


def check_routed(board_path: Path, work_dir: Path) -> dict[str, int]:
    """Criterion 10: KiCad's DRC at error severity, against the schematic, finds no violation, no unconnected
    item and no parity issue on a board of four copper layers. Returns the count of each kind from the report."""
    layers = pcbnew.LoadBoard(str(board_path)).GetCopperLayerCount()
    assert layers == 4, f"{board_path.name} has {layers} copper layers"
    report_path = work_dir / "drc-routed.json"
    _kicad_cli("pcb", "drc", "--severity-error", "--schematic-parity", "--format", "json", "-o", str(report_path),
               str(board_path))
    report = json.loads(report_path.read_text())
    found = {key: report[key] for key in DRC_KINDS if report[key]}
    summary = {key: sorted({item["description"] for item in items})[:5] for key, items in found.items()}
    assert not found, f"DRC: {summary}; see {report_path}"
    print("routed: DRC at error severity: 0 violations, 0 unconnected, 0 parity; 4 copper layers")
    return {key: len(report[key]) for key in DRC_KINDS}


def import_routes() -> None:
    """Freerouting's session on the route-critical board, the locked copper kept, filled on a reloaded board
    and judged."""
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    locked = _locked_items(board)
    assert locked, f"{BOARD_PATH.name} has no locked copper: run `build.py dsn` first"
    assert freeroute.SES_PATH.exists(), f"no {freeroute.SES_PATH}: run freeroute.py first"
    pcbnew.KIID.SeedGenerator(KIID_SEED)
    assert pcbnew.ImportSpecctraSES(board, str(freeroute.SES_PATH)), "session import failed"
    save_filled(board, BOARD_PATH)
    routed = pcbnew.LoadBoard(str(BOARD_PATH))
    assert _locked_items(routed) == locked, "the session import moved or dropped locked copper"
    added = len(routed.GetTracks()) - len(locked)
    print(f"routed: {added} tracks and vias from Freerouting, {len(locked)} locked ones kept")
    inner = [layout.pad_xy(track) for track in routed.GetTracks()
             if track.GetClass() == "PCB_TRACK" and track.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu)]
    assert not inner, f"tracks cut into the inner planes at {inner[:5]}"
    inside = contract.copper_in(routed, route.antenna_keepout())
    assert not inside, f"copper within {route.ANTENNA_SETBACK} mm of the antenna board cut: {inside}"
    contract.check(routed)
    check_rules_reach_drc(BOARD_PATH, BUILD_DIR)
    check_routed(BOARD_PATH, BUILD_DIR)


def write_fab() -> None:
    """The saved board judged by criterion 10 again, then the fab set written twice from it: the second write,
    into an empty folder, must be the same bytes."""
    BUILD_DIR.mkdir(exist_ok=True)
    drc_counts = check_routed(BOARD_PATH, BUILD_DIR)
    parts = place.board_parts()
    placeholders = sorted(part.ref for part in parts if "PLACEHOLDER_" in part.footprint)
    fab_dir = PROVISIONAL_FAB_DIR if placeholders else fab.FAB_DIR
    blockers = fab.write_set(BOARD_PATH, parts, fab_dir, drc_counts)
    again_dir = BUILD_DIR / "fab-again"
    fab.write_set(BOARD_PATH, parts, again_dir, drc_counts)
    differ = fab.differing_files(fab_dir, again_dir)
    assert not differ, f"a second write of the fab set differs in {differ}"
    files = sum(path.is_file() for path in fab_dir.rglob("*"))
    print(f"fab: {files} files in {fab_dir.relative_to(PCB_DIR)}, byte-repeatable; BOM, placement list and board "
          "name the same parts, Gerbers and drill files agree with the board")
    if placeholders:
        print(f"fab: provisional, PLACEHOLDER_* footprints {placeholders}: pcb/fab waits for task 5.12")
    if blockers:
        print(f"fab: not orderable yet, {len(blockers)} BOM findings; F.1 and `just gate` decide on ordering")
    for line in blockers:
        print(f"  {line}")


STEPS = {"erc": erc, "place": place_board, "route-critical": route_critical, "dsn": write_dsn,
         "routed": import_routes, "fab": write_fab,
         "contract": lambda: contract.check(pcbnew.LoadBoard(str(BOARD_PATH))), "drc": drc}
# The KiCad side of `just pcb`; freeroute.py and `routed` follow on the host. dsn places the board first.
PIPELINE = ("erc", "dsn")

if __name__ == "__main__":
    names = sys.argv[1:] or PIPELINE
    unknown = [name for name in names if name not in STEPS]
    if unknown:
        sys.exit(__doc__)
    for name in names:
        STEPS[name]()
