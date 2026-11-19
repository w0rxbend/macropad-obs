#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""check_measure passes a fixture with no open MEASURE on a gated entry and fails a tagged one."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_measure

CLEAN = """\
# MEASURE = needs a caliper. This header line belongs to no table.
[keys]
keycap = 18.0                         # seat MEASURE: [keys] is not a gated table

[pcb]
width = 91.6                          # design
holes = [
  [3.0, 3.0],                         # front corner
]
board_slots = [[19.9, 76.1, 21.5, 1.5]]

[fpc.big]
centre = [30.65, 92.30]               # measured 2026-12-01

[usb]
x = 45.8                              # design
"""


def open_tags(text):
    """The (table, key) pair of every open MEASURE that check_measure finds in text."""
    return [(tag.table, tag.key) for tag in check_measure.open_measures(text)]


def exit_code(text):
    """The exit code of the check run on a board file that holds text."""
    with tempfile.TemporaryDirectory() as folder:
        board = Path(folder) / "board.toml"
        board.write_text(text, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            return check_measure.main(board)


class CleanFixtureTest(unittest.TestCase):
    def test_no_tag_is_open(self):
        self.assertEqual(open_tags(CLEAN), [])

    def test_check_exits_0(self):
        self.assertEqual(exit_code(CLEAN), 0)


class TaggedFixtureTest(unittest.TestCase):
    def test_check_exits_1(self):
        self.assertEqual(exit_code(CLEAN + "mouth_overhang = 1.0   # MEASURE\n"), 1)

    def test_tag_in_a_gated_table_is_listed(self):
        for table in ("display_carrier", "knobs", "mcu", "antenna", "usb", "regulator"):
            with self.subTest(table=table):
                text = f"[{table}]\nheight = 3.1   # MEASURE stack\n"
                self.assertEqual(open_tags(text), [(table, "height")])

    def test_tag_in_any_fpc_table_is_listed(self):
        text = "[fpc.narrow]\ncentre = [76.0, 104.9]   # MEASURE: fold not known\n"
        self.assertEqual(open_tags(text), [("fpc.narrow", "centre")])

    def test_tag_on_a_gated_key_of_another_table_is_listed(self):
        for key in ("board_slots", "key_ribs", "holes", "antenna_relief"):
            with self.subTest(key=key):
                text = f"[pcb]\n{key} = [1.0, 2.0]   # MEASURE\n"
                self.assertEqual(open_tags(text), [("pcb", key)])

    def test_tag_inside_a_multi_line_value_is_listed(self):
        text = "[pcb]\nholes = [\n  [88.6, 41.1],   # lug pads ~83.0 MEASURE\n]\nwidth = 91.6\n"
        self.assertEqual(open_tags(text), [("pcb", "holes")])

    def test_tag_in_a_comment_under_a_gated_key_is_listed(self):
        text = "[bottom_plate]\nkey_ribs = { width = 1.5 }\n# Check the pads (MEASURE).\npinholes = 2.0\n"
        self.assertEqual(open_tags(text), [("bottom_plate", "key_ribs")])

    def test_tag_in_a_comment_above_a_gated_key_is_listed(self):
        text = "[bottom_plate]\npinholes = 2.0\n# MEASURE the tongue.\nantenna_relief = [58.6, 161.7]\n"
        self.assertEqual(open_tags(text), [("bottom_plate", "antenna_relief")])

    def test_tag_in_a_comment_of_a_gated_table_is_listed(self):
        text = "[antenna]\n# Feed side: check against the footprint, MEASURE.\npart = \"on-module\"\n"
        self.assertEqual(open_tags(text), [("antenna", "part")])

    def test_tag_is_listed_with_its_line_number_and_text(self):
        tag = check_measure.open_measures("[mcu]\nheight = 3.1   # MEASURE stack\n")[0]
        self.assertEqual((tag.line_number, tag.text), (2, "height = 3.1   # MEASURE stack"))

    def test_tag_on_a_key_that_is_not_gated_is_not_listed(self):
        text = "[pcb]\nwidth = 91.6   # MEASURE\n# MEASURE the edge.\nthickness = 1.6\n"
        self.assertEqual(open_tags(text), [])

    def test_gated_key_does_not_reach_into_the_next_table(self):
        text = "[pcb]\nboard_slots = [[1.0, 2.0]]\n\n[bottom_plate]\n# MEASURE the plate.\nstandoffs = 5.0\n"
        self.assertEqual(open_tags(text), [])


if __name__ == "__main__":
    unittest.main()
