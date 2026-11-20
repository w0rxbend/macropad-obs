# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Tests of layout.py, contract.py, fab.py and build.py. They need pcbnew and kicad-cli, so plain
`just pcb-test` skips them; `just pcb-test-kicad` runs them in kicad/kicad:9.0.9, and `just pcb` runs that first.

The board here is the board.toml outline with six stock M2 holes: no circuit yet (tasks 5.4 to 5.6).
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import tempfile
import tomllib
import unittest
from dataclasses import dataclass, field, replace
from pathlib import Path

# Only the pcbnew the pipeline pins (kicad/kicad:9.0.9): a host KiCad of another version skips these tests.
PCBNEW_FOUND = "no pcbnew"
if importlib.util.find_spec("pcbnew") is not None:
    import pcbnew

    PCBNEW_FOUND = f"pcbnew {pcbnew.GetMajorMinorVersion()}"
HAVE_PCBNEW = PCBNEW_FOUND == "pcbnew 9.0"
PCBNEW_SKIP = f"needs pcbnew 9.0, found {PCBNEW_FOUND}: run `just pcb-test-kicad`"
if HAVE_PCBNEW:
    import build
    import contract
    import fab
    import layout
    import schematic
    import sheets

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARD_TOML = tomllib.loads((REPO_ROOT / "board.toml").read_text())


class RecipeTest(unittest.TestCase):
    """The tests above skip on the host, so a recipe runs them in the pinned image, and every board build first."""

    def setUp(self) -> None:
        self.justfile = (REPO_ROOT / "justfile").read_text()

    def test_the_kicad_tests_run_in_the_pinned_image(self) -> None:
        recipe = re.search(r"^pcb-test-kicad:\n((?:    .*\n)+)", self.justfile, re.MULTILINE)
        self.assertIsNotNone(recipe, "no pcb-test-kicad recipe")
        self.assertIn("kicad/kicad:9.0.9 python3 -B -m unittest discover -s pcb/gen -p 'test_*.py'",
                      " ".join(recipe.group(1).replace("\\\n", " ").split()))

    def test_every_board_build_runs_the_kicad_tests_first(self) -> None:
        self.assertRegex(self.justfile, r"(?m)^pcb \*STEP: pcb-test-kicad$")

    def test_the_whole_board_build_ends_with_drc_at_every_severity(self) -> None:
        self.assertIn('"") kicad erc; route; kicad fab drc ;;', self.justfile)


@dataclass(frozen=True)
class Part:
    ref: str
    value: str
    footprint: str
    x: float
    y: float
    lcsc: str = ""
    nets: dict[str, str] = field(default_factory=dict)
    rotation: float = 0.0
    side: str = "top"
    machine_assembled: bool = False
    manufacturer_part: tuple[str, str] = ("", "")


def _holes() -> tuple[Part, ...]:
    return tuple(Part(f"H{n}", "M2", "MountingHole:MountingHole_2.2mm_M2", *layout.kicad_xy(x, y))
                 for n, (x, y) in enumerate(BOARD_TOML["pcb"]["holes"], start=1))


@unittest.skipUnless(HAVE_PCBNEW, PCBNEW_SKIP)
class BoardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.board_path = self.dir / "probe.kicad_pcb"

    def _saved_board(self, parts: tuple[Part, ...]) -> pcbnew.BOARD:
        board = layout.build_board(self.board_path, parts, {})
        pcbnew.SaveBoard(str(self.board_path), board)
        return pcbnew.LoadBoard(str(self.board_path))

    def test_contract_reads_board_toml(self) -> None:
        self.assertEqual(contract.PCB, BOARD_TOML["pcb"])

    def test_board_from_board_toml_meets_the_contract(self) -> None:
        board = self._saved_board(_holes())
        pcb = BOARD_TOML["pcb"]
        self.assertIn(f"{pcb['width']} x {pcb['depth']} mm", contract.check_outline(board))
        self.assertIn(f"{len(pcb['holes'])} M2 holes", contract.check_holes(board))

    def test_contract_finds_a_missing_hole(self) -> None:
        board = self._saved_board(_holes()[1:])
        with self.assertRaisesRegex(AssertionError, "holes of"):
            contract.check_holes(board)

    def test_contract_finds_a_wrong_layer_count(self) -> None:
        board = self._saved_board(_holes())
        board.SetCopperLayerCount(2)
        with self.assertRaisesRegex(AssertionError, "copper layers"):
            contract.check_outline(board)

    def test_part_inside_a_hole_keepout_fails(self) -> None:
        x, y = _holes()[0].x, _holes()[0].y
        resistor = Part("R1", "10k", "Resistor_SMD:R_0402_1005Metric", x + 1.0, y)
        with self.assertRaisesRegex(AssertionError, "R1 pad 1 inside the keep-out"):
            layout.build_board(self.board_path, _holes() + (resistor,), {})

    def test_bottom_part_is_flipped(self) -> None:
        resistor = Part("R1", "10k", "Resistor_SMD:R_0402_1005Metric", 45.0, 100.0, side=layout.BOTTOM)
        board = self._saved_board(_holes() + (resistor,))
        self.assertTrue(board.FindFootprintByReference("R1").IsFlipped())

    def test_project_rules_are_written_and_merged(self) -> None:
        project = self.dir / "probe.kicad_pro"
        layout.write_project_rules(project)
        layout.write_project_rules(project, layout.DRC_RULES | {"min_track_width": 0.2})
        text = project.read_text()
        self.assertIn('"min_track_width": 0.2', text)
        self.assertIn(f'"min_hole_to_hole": {layout.DRC_RULES["min_hole_to_hole"]}', text)
        self.assertIn(f'"track_width": {layout.TRACK_WIDTH}', text)

    def test_drc_reads_the_project_rules(self) -> None:
        board = layout.build_board(self.board_path, _holes(), {})
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(layout.point(30.0, 100.0))
        track.SetEnd(layout.point(40.0, 100.0))
        track.SetWidth(layout.mm(layout.TRACK_WIDTH))
        track.SetLayer(pcbnew.F_Cu)
        board.Add(track)
        pcbnew.SaveBoard(str(self.board_path), board)
        layout.write_project_rules(self.board_path.with_suffix(".kicad_pro"))
        build.check_rules_reach_drc(self.board_path, self.dir)


def _kicad_cli(*arguments: str) -> None:
    subprocess.run(["kicad-cli", *arguments], check=True, stdout=subprocess.DEVNULL)


@unittest.skipUnless(HAVE_PCBNEW, PCBNEW_SKIP)
class ParityTest(unittest.TestCase):
    """The placed board beside the schematic it was placed from, judged by DRC at warning severity. The folder
    sits next to a link to pcb/lib, as pcb/kicad does, so the project footprints resolve."""

    @classmethod
    def setUpClass(cls) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "lib").symlink_to(REPO_ROOT / "pcb" / "lib")
        folder = root / "kicad"
        folder.mkdir()
        board_path = folder / f"{schematic.PROJECT}.kicad_pcb"
        netlist_path = folder / "schematic.net"
        schematic.write(folder, sheets.SHEET)
        _kicad_cli("sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(netlist_path),
                   str(board_path.with_suffix(".kicad_sch")))
        build.place_board(board_path, netlist_path)
        report_path = folder / "drc.json"
        _kicad_cli("pcb", "drc", "--severity-warning", "--schematic-parity", "--format", "json", "-o",
                   str(report_path), str(board_path))
        cls.report = json.loads(report_path.read_text())

    def _found(self, key: str, kind: str) -> list[str]:
        return sorted(item["items"][0]["description"] for item in self.report[key] if item["type"] == kind)

    def test_every_open_pin_keeps_the_net_the_schematic_gives_it(self) -> None:
        self.assertEqual(self._found("schematic_parity", "net_conflict"), [])

    def test_the_mounting_holes_are_board_only(self) -> None:
        self.assertEqual(self._found("schematic_parity", "extra_footprint"), [])

    def test_every_footprint_is_found_in_its_library(self) -> None:
        self.assertEqual(self._found("violations", "lib_footprint_issues"), [])

    def test_silkscreen_clears_the_pads_and_the_other_silkscreen(self) -> None:
        self.assertEqual(self._found("violations", "silk_over_copper") + self._found("violations", "silk_overlap"), [])


@unittest.skipUnless(HAVE_PCBNEW, PCBNEW_SKIP)
class FabTest(unittest.TestCase):
    def test_drill_hits_are_counted_per_tool(self) -> None:
        drill = Path(tempfile.mkdtemp()) / "probe.drl"
        drill.write_text("M48\nT1C0.300\nT2C2.200\n%\nG05\nT1\nX1.0Y1.0\nX2.0Y2.0\nT2\nX3.0Y3.0\nX4.0Y4.0G85X5.0Y4.0\nM30\n")
        self.assertEqual(fab._drill_hits_by_diameter(drill), {"0.300": 2, "2.200": 1})

    def test_bom_groups_machine_placed_parts(self) -> None:
        resistor = Part("R1", "10k", "Resistor_SMD:R_0402_1005Metric", 0.0, 0.0, lcsc="UNVERIFIED",
                        machine_assembled=True, manufacturer_part=("Yageo", "RC0402"))
        parts = (resistor, replace(resistor, ref="R2"), Part("H1", "M2", "MountingHole:MountingHole_2.2mm_M2", 0.0, 0.0))
        bom = Path(tempfile.mkdtemp()) / "bom.csv"
        fab.write_bom(parts, bom)
        self.assertEqual(bom.read_text().splitlines()[1:],
                         ['10k,"R1,R2",R_0402_1005Metric,UNVERIFIED,Yageo,RC0402'])


if __name__ == "__main__":
    unittest.main()
