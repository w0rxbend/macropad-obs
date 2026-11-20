# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Task 6.10: the knob dial and the two B3F caps are one valid solid each, sized from board.toml,
their checks catch a bad size, and each reads back. Needs cad/.venv:
`cad/.venv/bin/python cad/obs_case/test_knob_caps.py`."""

import sys
import tempfile
import unittest
from copy import deepcopy
from math import cos, pi, radians, sin
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build123d import Vector  # noqa: E402

from obs_case import b3f_cap, knob  # noqa: E402
from obs_case.export import part_files  # noqa: E402
from obs_case.spec import LAYOUT  # noqa: E402
from obs_case.variants import CNC, PRINT, VARIANTS  # noqa: E402

NUDGE = 0.04  # mm a probe sits off the face it tests


def edited(table, path, value):
    """A deep copy of the namespace `table` with the dotted attribute `path` set to `value`."""
    copy = deepcopy(table)
    *parents, name = path.split(".")
    target = copy
    for parent in parents:
        target = getattr(target, parent)
    setattr(target, name, value)
    return copy


class Dial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dial, cls.seat, cls.table = knob.dial(), knob.seat(), LAYOUT.knob_dial

    def inside(self, x, y, z):
        return self.dial.is_inside(Vector(x, y, z))

    def test_one_valid_solid(self):
        self.assertEqual(1, len(self.dial.solids()))
        self.assertTrue(self.dial.is_valid)

    def test_size_and_place_come_from_board_toml(self):
        box = self.dial.bounding_box()
        self.assertAlmostEqual(LAYOUT.knobs.diameter, box.size.X, places=6)
        self.assertAlmostEqual(self.table.skirt, box.min.Z, places=6)
        self.assertAlmostEqual(LAYOUT.envelopes.ec11_shaft[1] + self.table.top_cover, box.max.Z, places=6)
        self.assertAlmostEqual(0.0, box.center().X, places=6)

    def test_d_bore_over_the_flat_and_round_below_it(self):
        seat = self.seat
        flat_y = seat.across - seat.bore / 2
        below_screw = (seat.d_start + seat.screw_z - self.table.set_screw.hole / 2) / 2
        self.assertFalse(self.inside(0, 0, below_screw))
        self.assertTrue(self.inside(0, flat_y + NUDGE, below_screw))  # the flat land
        self.assertFalse(self.inside(0, flat_y + NUDGE, seat.d_start - NUDGE))  # round below the D
        self.assertTrue(self.inside(0, 0, seat.shaft_end + NUDGE))  # cover over the shaft end

    def test_pocket_clears_the_bushing(self):
        seat = self.seat
        self.assertFalse(self.inside(seat.pocket_radius - NUDGE, 0, seat.roof - NUDGE))
        self.assertTrue(self.inside(seat.pocket_radius + NUDGE, 0, seat.roof - NUDGE))

    def test_set_screw_reaches_the_flat_on_the_index_side_only(self):
        seat = self.seat
        flat_y = seat.across - seat.bore / 2
        self.assertFalse(self.inside(0, flat_y + NUDGE, seat.screw_z))
        wall = seat.radius - self.table.flutes.depth - NUDGE
        self.assertFalse(self.inside(0, wall, seat.screw_z))
        self.assertTrue(self.inside(0, -wall, seat.screw_z))

    def test_index_breaks_the_top_rim_on_plus_y(self):
        seat, index = self.seat, self.table.index
        rim = seat.radius - self.table.chamfer - NUDGE
        self.assertFalse(self.inside(0, rim, seat.top - NUDGE))
        self.assertTrue(self.inside(0, -rim, seat.top - NUDGE))
        self.assertTrue(self.inside(0, rim, seat.top - index.depth - NUDGE))

    def test_flutes_cut_between_lands_and_a_land_faces_the_index(self):
        seat, flutes = self.seat, self.table.flutes
        z = (seat.foot + seat.top) / 2
        probe = seat.radius - flutes.depth / 2
        step = 360 / flutes.count
        flute = radians(90 + step / 2)
        self.assertFalse(self.inside(probe * cos(flute), probe * sin(flute), z))
        below_screw = (seat.foot + self.table.plain_band + seat.screw_z - self.table.set_screw.hole / 2) / 2
        self.assertTrue(self.inside(0, probe, below_screw))  # the land on +y, below the set screw
        self.assertEqual(flutes.count, round(2 * pi / radians(step)))


class DialChecks(unittest.TestCase):
    def test_board_toml_passes(self):
        self.assertEqual([], knob.problems())

    def test_lands_too_thin_are_caught(self):
        bad = edited(LAYOUT.knob_dial, "flutes.half_width", LAYOUT.knobs.diameter)
        self.assertTrue(any("flute lands" in problem for problem in knob.problems(bad)))

    def test_air_under_the_push_travel_is_caught(self):
        bad = edited(LAYOUT.knob_dial, "skirt", LAYOUT.stack.deck_top + LAYOUT.knob_dial.push_travel / 2)
        self.assertTrue(any("air under the dial" in problem for problem in knob.problems(bad)))

    def test_index_into_the_bore_is_caught(self):
        bad = edited(LAYOUT.knob_dial, "index.depth", LAYOUT.knob_dial.top_cover)
        self.assertTrue(any("index" in problem for problem in knob.problems(bad)))


class Caps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.caps = {variant: b3f_cap.cap(variant) for variant in VARIANTS}

    def test_one_valid_solid_each_flush_with_the_deck(self):
        for variant, cap in self.caps.items():
            self.assertEqual(1, len(cap.solids()), variant)
            self.assertTrue(cap.is_valid, variant)
            self.assertAlmostEqual(LAYOUT.stack.deck_top, cap.bounding_box().max.Z, places=6, msg=variant)

    def test_cnc_cap_is_floating_with_a_flange_under_the_deck(self):
        cap, buttons, table = self.caps[CNC], LAYOUT.buttons, LAYOUT.button_cap
        box = cap.bounding_box()
        self.assertAlmostEqual(buttons.cap_flange[1], box.size.Y, places=6)
        self.assertAlmostEqual(LAYOUT.stack.deck_underside - table.flange, box.min.Z, places=6)
        flange_y = buttons.cap_flange[1] / 2 - NUDGE
        self.assertTrue(cap.is_inside(Vector(0, flange_y, LAYOUT.stack.deck_underside - NUDGE)))
        self.assertFalse(cap.is_inside(Vector(0, flange_y, LAYOUT.stack.deck_underside + NUDGE)))
        self.assertFalse(cap.is_inside(Vector(table.bore_radius - NUDGE, 0, table.plunger_top - NUDGE)))
        self.assertTrue(cap.is_inside(Vector(0, 0, table.plunger_top + NUDGE)))

    def test_print_cap_is_press_on_without_a_flange(self):
        cap, buttons, table = self.caps[PRINT], LAYOUT.buttons, LAYOUT.button_cap
        box = cap.bounding_box()
        self.assertAlmostEqual(buttons.cap[1], box.size.Y, places=6)
        self.assertAlmostEqual(table.plunger_top - table.socket_depth, box.min.Z, places=6)
        socket = LAYOUT.envelopes.b3f_plunger / 2
        self.assertFalse(cap.is_inside(Vector(socket - NUDGE, 0, table.plunger_top - NUDGE)))
        self.assertTrue(cap.is_inside(Vector(socket + NUDGE, 0, table.plunger_top - NUDGE)))

    def test_board_toml_passes_the_checks(self):
        for variant in VARIANTS:
            self.assertEqual([], b3f_cap.problems(variant), variant)

    def test_a_flange_inside_the_hole_is_caught(self):
        buttons = edited(LAYOUT.buttons, "cap_flange", LAYOUT.buttons.cap)
        self.assertTrue(any("flange" in problem for problem in b3f_cap.problems(CNC, buttons=buttons)))

    def test_a_cap_on_the_switch_body_is_caught(self):
        table = edited(LAYOUT.button_cap, "socket_depth", LAYOUT.button_cap.plunger_top)
        self.assertTrue(any("switch body" in problem for problem in b3f_cap.problems(PRINT, table=table)))

    def test_unknown_variant_is_refused(self):
        with self.assertRaises(ValueError):
            b3f_cap.cap("resin")


class Files(unittest.TestCase):
    def test_dial_and_both_caps_read_back(self):
        folder = Path(tempfile.mkdtemp())
        readbacks = part_files(knob.dial(), knob.LABEL, folder / "dial")
        for variant in VARIANTS:
            readbacks += part_files(b3f_cap.cap(variant), b3f_cap.label(variant), folder / variant)
        self.assertEqual([], [problem for readback in readbacks for problem in readback.problems])
        self.assertEqual(18, len(readbacks))


if __name__ == "__main__":
    unittest.main()
