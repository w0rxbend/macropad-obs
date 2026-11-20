# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The committed board and order files belong together. Plain Python, no KiCad: `just pcb-test`.

Fails when the routing summary shows a DRC finding, when the board changed after the order files in pcb/fab/
were written: by its hash (recorded by `just pcb fab`), and by file times where they mean something, or when
the BOM and placement list name different parts.

`just pcb fab` writes pcb/fab/ only when no PLACEHOLDER_* footprint is left on the board (task 5.12); until then
it writes pcb/.build/fab/, and the check of pcb/fab/ skips. The fixture tests run either way.

Copied from macropad-greycode pcb/gen/test_order_files.py (decision D5). Greycode's pcb/routing.txt, written by
its own router, is here the DRC summary in the fab folder; the BOM and placement check is new.
"""

from __future__ import annotations

import csv
import hashlib
import os
import tempfile
import unittest
from pathlib import Path

PCB_DIR = Path(__file__).resolve().parents[1]
BOARD_PATH = PCB_DIR / "kicad" / "macropad-obs.kicad_pcb"
FAB_DIR = PCB_DIR / "fab"
GERBER_GLOB = "macropad-obs-*"
CLEAN_DRC = "violations 0  unconnected_items 0  schematic_parity 0"
# A fresh checkout writes every file within a moment, in path order, so pcb/fab/ lands a little before
# pcb/kicad/. A board rebuilt after the order files is minutes newer.
CHECKOUT_SLACK_SECONDS = 10.0


def _csv_refs(path: Path) -> list[str]:
    with path.open(newline="") as csv_file:
        return [ref for row in csv.DictReader(csv_file) for ref in row["Designator"].split(",")]


def order_file_problems(fab_dir: Path, board_path: Path) -> list[str]:
    """What is wrong with fab_dir as the order files of the board at board_path."""
    problems = []
    first_line = (fab_dir / "routing.txt").read_text().splitlines()[0]
    if not first_line.startswith(CLEAN_DRC):
        problems.append(f"routing.txt: {first_line}")
    recorded = (fab_dir / "board-sha256.txt").read_text().split()[0]
    if recorded != hashlib.sha256(board_path.read_bytes()).hexdigest():
        problems.append("the board changed after `just pcb fab`; run it again")
    gerbers = sorted((fab_dir / "gerbers").glob(GERBER_GLOB))
    if not gerbers:
        problems.append(f"no Gerbers in {fab_dir / 'gerbers'}")
    board_time = board_path.stat().st_mtime
    stale = [gerber.name for gerber in gerbers if gerber.stat().st_mtime < board_time - CHECKOUT_SLACK_SECONDS]
    if stale:
        problems.append(f"Gerbers older than the board: {stale}")
    if sorted(_csv_refs(fab_dir / "bom-jlcpcb.csv")) != sorted(_csv_refs(fab_dir / "cpl-jlcpcb.csv")):
        problems.append("the BOM and the placement list name different parts")
    return problems


class FixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.board = root / "macropad-obs.kicad_pcb"
        self.board.write_text("(kicad_pcb)\n")
        self.fab = root / "fab"
        (self.fab / "gerbers").mkdir(parents=True)
        (self.fab / "gerbers" / "macropad-obs-F_Cu.gtl").write_text("%MOMM*%\n")
        (self.fab / "routing.txt").write_text(f"{CLEAN_DRC}  tracks 10  vias 2\n")
        (self.fab / "board-sha256.txt").write_text(
            f"{hashlib.sha256(self.board.read_bytes()).hexdigest()}  {self.board.name}\n")
        (self.fab / "bom-jlcpcb.csv").write_text('Comment,Designator\n10k,"R1,R2"\n')
        (self.fab / "cpl-jlcpcb.csv").write_text("Designator,Mid X\nR2,1.000mm\nR1,2.000mm\n")

    def test_matching_files_pass(self) -> None:
        self.assertEqual(order_file_problems(self.fab, self.board), [])

    def test_a_drc_finding_fails(self) -> None:
        (self.fab / "routing.txt").write_text("violations 0  unconnected_items 3  schematic_parity 0\n")
        self.assertEqual(order_file_problems(self.fab, self.board),
                         ["routing.txt: violations 0  unconnected_items 3  schematic_parity 0"])

    def test_a_changed_board_fails(self) -> None:
        self.board.write_text("(kicad_pcb (version 2))\n")
        self.assertEqual(order_file_problems(self.fab, self.board),
                         ["the board changed after `just pcb fab`; run it again"])

    def test_a_gerber_older_than_the_board_fails(self) -> None:
        gerber = self.fab / "gerbers" / "macropad-obs-F_Cu.gtl"
        then = self.board.stat().st_mtime - 600
        os.utime(gerber, (then, then))
        self.assertEqual(order_file_problems(self.fab, self.board),
                         ["Gerbers older than the board: ['macropad-obs-F_Cu.gtl']"])

    def test_no_gerber_fails(self) -> None:
        (self.fab / "gerbers" / "macropad-obs-F_Cu.gtl").unlink()
        self.assertEqual(order_file_problems(self.fab, self.board), [f"no Gerbers in {self.fab / 'gerbers'}"])

    def test_a_part_only_placed_fails(self) -> None:
        (self.fab / "cpl-jlcpcb.csv").write_text("Designator,Mid X\nR2,1.000mm\nR1,2.000mm\nR3,3.000mm\n")
        self.assertEqual(order_file_problems(self.fab, self.board),
                         ["the BOM and the placement list name different parts"])


@unittest.skipUnless((FAB_DIR / "board-sha256.txt").is_file(),
                     "no pcb/fab yet: `just pcb fab` writes it once no PLACEHOLDER_* footprint is left (task 5.12)")
class OrderFilesTest(unittest.TestCase):
    def test_the_committed_order_files_were_written_from_the_committed_board(self) -> None:
        self.assertEqual(order_file_problems(FAB_DIR, BOARD_PATH), [])


if __name__ == "__main__":
    unittest.main()
