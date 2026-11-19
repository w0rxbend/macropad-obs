#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""check_numbers passes on the tree and fails on one broken copy per rule."""

import copy
import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_numbers

LAYOUT_TEXT = check_numbers.LAYOUT.read_text(encoding="utf-8")
BOARD_TEXT = check_numbers.BOARD.read_text(encoding="utf-8")


def problems_after(change_layout=None, change_board=None):
    """Problems for a copy of the tree's two tables after the given edits."""
    layout = tomllib.loads(LAYOUT_TEXT)
    board = tomllib.loads(BOARD_TEXT)
    if change_layout:
        change_layout(layout)
        change_layout(board)
    if change_board:
        change_board(board)
    return check_numbers.problems(layout, board)


class TreeTest(unittest.TestCase):
    def test_tree_has_no_problem(self):
        self.assertEqual(problems_after(), [])

    def test_tree_keeps_every_measure_tag(self):
        self.assertEqual(check_numbers.lost_measure_tags(LAYOUT_TEXT, BOARD_TEXT), [])

    def test_layout_is_revision_3(self):
        self.assertEqual(tomllib.loads(LAYOUT_TEXT)["layout_revision"], 3)


class StackTest(unittest.TestCase):
    def test_report_11_panel_face_is_rejected(self):
        def panel_face_5_5(tables):
            tables["stack"]["panel_face"] = 5.5

        found = problems_after(panel_face_5_5)
        self.assertTrue(any("panel_face" in line for line in found), found)

    def test_wrong_big_carrier_height_is_rejected(self):
        def tall_big_carrier(tables):
            tables["display_carrier"]["big"]["height"] = 3.50

        found = problems_after(tall_big_carrier)
        self.assertTrue(any("big carrier height" in line for line in found), found)

    def test_wrong_narrow_carrier_height_is_rejected(self):
        def short_narrow_carrier(tables):
            tables["display_carrier"]["narrow"]["height"] = 3.45

        found = problems_after(short_narrow_carrier)
        self.assertTrue(any("narrow carrier height" in line for line in found), found)

    def test_foam_squeeze_limits_are_inside_the_range(self):
        self.assertEqual(check_numbers.squeeze_problems({"thickness": 0.5, "installed": 0.45}), [])
        self.assertEqual(check_numbers.squeeze_problems({"thickness": 0.4, "installed": 0.3}), [])

    def test_foam_squeeze_outside_the_range_is_rejected(self):
        for installed in (0.5, 0.46, 0.37, 0.3):
            foam = {"thickness": 0.5, "installed": installed}
            self.assertEqual(len(check_numbers.squeeze_problems(foam)), 1, installed)


class KeepoutTest(unittest.TestCase):
    def test_hole_keepout_under_a_carrier_is_rejected(self):
        def hole_at_the_big_carrier_edge(tables):
            tables["pcb"]["holes"][5] = [3.3, 164.8]  # keep-out reaches y 162.3, carrier top 162.35

        found = problems_after(hole_at_the_big_carrier_edge)
        self.assertTrue(any("hole keep-out" in line and "big carrier" in line for line in found), found)

    def test_slot_under_a_carrier_is_rejected(self):
        def bar_slot_moved_back(tables):
            tables["pcb"]["board_slots"][1] = [72.75, 91.0, 6.5, 1.5]

        found = problems_after(bar_slot_moved_back)
        self.assertTrue(any("board slot" in line and "narrow carrier" in line for line in found), found)

    def test_through_hole_part_under_a_carrier_is_rejected(self):
        def top_knob_moved_back(tables):
            tables["knobs"]["y"][0] = 90.0

        found = problems_after(top_knob_moved_back)
        self.assertTrue(any("encoder" in line and "narrow carrier" in line for line in found), found)

    def test_usb_peg_under_a_carrier_is_rejected(self):
        def pegs_moved_forward(tables):
            tables["usb"]["peg_holes"]["at"] = [[42.8, 162.5], [48.8, 162.5]]

        found = problems_after(pegs_moved_forward)
        self.assertTrue(any("USB peg" in line and "big carrier" in line for line in found), found)

    def test_touching_edges_do_not_overlap(self):
        self.assertFalse(check_numbers.rects_overlap([0, 0, 2, 2], [2, 0, 2, 2]))
        self.assertTrue(check_numbers.rects_overlap([0, 0, 2, 2], [1.9, 1.9, 2, 2]))

    def test_seventh_hole_is_rejected(self):
        def back_right_hole_restored(tables):
            tables["pcb"]["holes"].append([88.3, 166.0])

        found = problems_after(back_right_hole_restored)
        self.assertTrue(any("6 holes" in line for line in found), found)


class PortTest(unittest.TestCase):
    def test_board_value_that_differs_from_the_layout_is_rejected(self):
        def old_wedge_width(board):
            board["pcb"]["width"] = 88.0

        self.assertEqual(
            problems_after(change_board=old_wedge_width),
            ["board.toml pcb.width: 88.0, layout-v2.toml 91.6"],
        )

    def test_layout_table_missing_from_the_board_is_rejected(self):
        def drop_stack(board):
            del board["stack"]

        found = problems_after(change_board=drop_stack)
        self.assertIn("board.toml stack: missing, layout-v2.toml has it", found)

    def test_dropped_measure_tag_is_reported(self):
        untagged = BOARD_TEXT.replace("bottom_plate_inside = -5.6     # MEASURE", "bottom_plate_inside = -5.6     #")
        self.assertNotEqual(untagged, BOARD_TEXT)
        lost = check_numbers.lost_measure_tags(LAYOUT_TEXT, untagged)
        self.assertEqual(len(lost), 1)
        self.assertIn("bottom_plate_inside", lost[0])


if __name__ == "__main__":
    unittest.main()
