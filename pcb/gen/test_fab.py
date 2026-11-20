# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Tests of the fab set in fab.py: the outputs drop KiCad's creation dates so a second write is the same bytes,
the BOM, placement list and board name the same parts both ways, and what still stops an order is listed.

fab.py imports pcbnew, so these skip without it; run them in the KiCad container like test_board.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

HAVE_PCBNEW = importlib.util.find_spec("pcbnew") is not None
if HAVE_PCBNEW:
    import fab

GERBER_HEAD = ("%TF.GenerationSoftware,KiCad,Pcbnew,9.0.9*%\n%TF.CreationDate,{iso}*%\n%TF.FileFunction,Copper,L1,Top*%\n"
               "G04 Created by KiCad (PCBNEW 9.0.9) date {plain}*\n%MOMM*%\n")
DRILL_HEAD = ("M48\n; DRILL file {{KiCad 9.0.9}} date {iso}\n; FORMAT={{-:-/ absolute / metric / decimal}}\n"
              "; #@! TF.CreationDate,{iso}\n; #@! TF.FileFunction,Plated,1,4,PTH\nT1C0.300\n")
JOB = {"Header": {"GenerationSoftware": {"Vendor": "KiCad", "Version": "9.0.9"}, "CreationDate": "{iso}"},
       "GeneralSpecs": {"LayerNumber": 4}}


def _bom_row(refs: str, lcsc: str = "UNVERIFIED", maker: str = "Yageo", number: str = "RC0402") -> dict[str, str]:
    return {"Comment": "10k", "Designator": refs, "Footprint": "R_0402_1005Metric", "LCSC Part #": lcsc,
            "Manufacturer": maker, "Manufacturer Part #": number}


@unittest.skipUnless(HAVE_PCBNEW, "needs pcbnew: run in kicad/kicad:9.0.9")
class RepeatableTest(unittest.TestCase):
    def test_gerbers_from_two_minutes_are_the_same_bytes(self) -> None:
        first = fab.without_dates("board-F_Cu.gtl", GERBER_HEAD.format(iso="2026-11-20T08:20:04+00:00",
                                                                     plain="2026-11-20 08:20:04"))
        second = fab.without_dates("board-F_Cu.gtl", GERBER_HEAD.format(iso="2026-11-21T09:00:00+00:00",
                                                                      plain="2026-11-21 09:00:00"))
        self.assertEqual(first, second)
        self.assertNotIn("2026", first)
        self.assertIn("%TF.FileFunction,Copper,L1,Top*%", first)
        self.assertIn("G04 Created by KiCad (PCBNEW 9.0.9)*", first)

    def test_drill_files_from_two_minutes_are_the_same_bytes(self) -> None:
        first = fab.without_dates("board-PTH.drl", DRILL_HEAD.format(iso="2026-11-20T08:20:04+0000"))
        second = fab.without_dates("board-PTH.drl", DRILL_HEAD.format(iso="2026-11-21T09:00:00+0000"))
        self.assertEqual(first, second)
        self.assertNotIn("2026", first)
        self.assertIn("T1C0.300", first)

    def test_job_file_loses_its_date_and_stays_json(self) -> None:
        text = json.dumps(JOB, indent=2).replace("{iso}", "2026-11-20T08:20:04+00:00")
        job = json.loads(fab.without_dates("board-job.gbrjob", text))
        self.assertNotIn("CreationDate", job["Header"])
        self.assertEqual(job["GeneralSpecs"], {"LayerNumber": 4})

    def test_zip_ignores_file_times(self) -> None:
        gerber_dir = Path(tempfile.mkdtemp()) / "gerbers"
        gerber_dir.mkdir()
        (gerber_dir / "b.gbl").write_text("bottom\n")
        (gerber_dir / "a.gtl").write_text("top\n")
        first, second = gerber_dir.parent / "first.zip", gerber_dir.parent / "second.zip"
        fab.write_zip(gerber_dir, first)
        os.utime(gerber_dir / "a.gtl", (1_000_000_000, 1_000_000_000))
        fab.write_zip(gerber_dir, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_differing_files_names_changed_missing_and_extra_files(self) -> None:
        root = Path(tempfile.mkdtemp())
        first, second = root / "first", root / "second"
        for folder in (first, second):
            (folder / "gerbers").mkdir(parents=True)
            (folder / "gerbers" / "same.gtl").write_text("same\n")
        (first / "bom.csv").write_text("a\n")
        (second / "bom.csv").write_text("b\n")
        (first / "only-first.csv").write_text("x\n")
        (second / "gerbers" / "only-second.gbl").write_text("y\n")
        self.assertEqual(fab.differing_files(first, second), ["bom.csv", "gerbers/only-second.gbl", "only-first.csv"])
        self.assertEqual(fab.differing_files(first / "gerbers", second / "gerbers"), ["only-second.gbl"])


@unittest.skipUnless(HAVE_PCBNEW, "needs pcbnew: run in kicad/kicad:9.0.9")
class ReferencesTest(unittest.TestCase):
    def test_agreeing_lists_give_no_mismatch(self) -> None:
        self.assertEqual(fab.reference_mismatches(["R1", "R2"], ["R2", "R1"], {"R1", "R2"}), [])

    def test_a_placed_part_missing_from_the_bom_is_named(self) -> None:
        self.assertEqual(fab.reference_mismatches(["R1"], ["R1", "R2"], {"R1", "R2"}),
                         ["R2: in the placement list, not in the BOM", "R2: on the board, not in the BOM"])

    def test_a_bom_reference_with_no_footprint_is_named(self) -> None:
        self.assertEqual(fab.reference_mismatches(["R1", "R9"], ["R1", "R9"], {"R1"}),
                         ["R9: in the BOM, not on the board", "R9: in the placement list, not on the board"])

    def test_a_board_footprint_in_neither_list_is_named(self) -> None:
        self.assertEqual(fab.reference_mismatches(["R1"], ["R1"], {"R1", "U1"}),
                         ["U1: on the board, not in the BOM", "U1: on the board, not in the placement list"])

    def test_a_part_listed_twice_is_named(self) -> None:
        self.assertEqual(fab.reference_mismatches(["R1", "R1"], ["R1"], {"R1"}), ["R1: twice in the BOM"])
        self.assertEqual(fab.reference_mismatches(["R1"], ["R1", "R1"], {"R1"}),
                         ["R1: twice in the placement list"])


@unittest.skipUnless(HAVE_PCBNEW, "needs pcbnew: run in kicad/kicad:9.0.9")
class OrderBlockersTest(unittest.TestCase):
    def test_a_numbered_line_with_its_maker_is_orderable(self) -> None:
        self.assertEqual(fab.order_blockers([_bom_row("R1", lcsc="C25744")]), [])

    def test_unverified_lcsc_and_missing_maker_are_listed(self) -> None:
        rows = [_bom_row("R1,R2"), _bom_row("C1", lcsc="C1525", maker="", number="")]
        self.assertEqual(fab.order_blockers(rows),
                         ["R1,R2 10k: no JLCPCB part number (UNVERIFIED)", "C1 10k: no manufacturer part number"])


if __name__ == "__main__":
    unittest.main()
