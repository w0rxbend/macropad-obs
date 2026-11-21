# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The M2 screw seats (board.toml [screws]): each boss joins its walls through rounded joins, the cnc
shell has a blind tap drill that leaves the deck whole, the print shell an insert pocket, the plate
a countersink at each hole, and the screw check catches a screw that does not fit. Needs cad/.venv:
`cad/.venv/bin/python cad/obs_case/test_screws.py`."""

import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build123d import GeomType, Vector  # noqa: E402

from obs_case import bottom, screws, variants  # noqa: E402
from obs_case.spec import LAYOUT  # noqa: E402

NUDGE = 0.04  # mm a probe sits off the face it tests


class Screws(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cnc = variants.parts(variants.CNC)
        cls.printed = variants.parts(variants.PRINT)

    def test_board_toml_screw_fits_its_thread_and_its_pocket(self):
        self.assertEqual(screws.problems(), [])

    def test_a_long_screw_is_caught(self):
        layout = deepcopy(LAYOUT)
        layout.screws.length += 2 * NUDGE + LAYOUT.screws.cnc.thread_depth - (screws.screw_tip() - LAYOUT.stack.pcb_top)
        with mock.patch.object(screws, "LAYOUT", layout), mock.patch.object(bottom, "LAYOUT", layout):
            found = screws.problems()
        self.assertTrue(any("thread" in problem for problem in found), found)

    def test_each_boss_join_is_rounded(self):
        for hole in LAYOUT.pcb.holes:
            radii = [edge.radius for edge in screws.boss_plan(hole).edges().filter_by(GeomType.CIRCLE)]
            joins = [radius for radius in radii if abs(radius - LAYOUT.pcb.boss_merge_fillet) < 1e-6]
            self.assertEqual(len(joins), 2, f"{hole}: arcs {radii}")

    def test_cnc_tap_drill_is_blind_and_the_boss_stands_round_it(self):
        cnc, stack, shell = LAYOUT.screws.cnc, LAYOUT.stack, self.cnc["shell"]
        for x, y in LAYOUT.pcb.holes:
            self.assertFalse(shell.is_inside(Vector(x, y, stack.pcb_top + cnc.drill_depth - NUDGE)), (x, y))
            self.assertTrue(shell.is_inside(Vector(x, y, stack.pcb_top + cnc.drill_depth + NUDGE)), (x, y))
            self.assertTrue(shell.is_inside(Vector(x, y + screws.radius() - NUDGE, stack.pcb_top + NUDGE)), (x, y))

    def test_print_shell_has_the_insert_pocket(self):
        (pocket_radius, depth), stack, shell = LAYOUT.screws.print.pocket, LAYOUT.stack, self.printed["shell"]
        between = (pocket_radius + LAYOUT.screws.cnc.tap_drill / 2) / 2
        for x, y in LAYOUT.pcb.holes:
            self.assertFalse(shell.is_inside(Vector(x, y + between, stack.pcb_top + depth / 2)), (x, y))
            self.assertTrue(shell.is_inside(Vector(x, y + pocket_radius + NUDGE, stack.pcb_top + NUDGE)), (x, y))
            self.assertTrue(self.cnc["shell"].is_inside(Vector(x, y + between, stack.pcb_top + depth / 2)))

    def test_plate_is_countersunk_on_the_outer_face(self):
        sink, plate = LAYOUT.screws.countersink, self.cnc["plate"]
        face = bottom.outer_face() + NUDGE / 2
        for x, y in LAYOUT.pcb.holes:
            self.assertFalse(plate.is_inside(Vector(x + sink.diameter / 2 - NUDGE, y, face)), (x, y))
            self.assertTrue(plate.is_inside(Vector(x + sink.diameter / 2 + NUDGE, y, face)), (x, y))
        self.assertLess(bottom.countersink_depth(), LAYOUT.bottom_plate.thickness)


if __name__ == "__main__":
    unittest.main()
