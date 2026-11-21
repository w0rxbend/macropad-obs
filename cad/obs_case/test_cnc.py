# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The cnc variant's shop rules: each dog-bone is sized for the setup that cuts it, and the CNC
drawing lists it in that setup; every milled wall holds CNC_MIN_WALL, or the thickness of a thin
wall board.toml draws on purpose, which the check names. Needs cad/.venv: `cad/.venv/bin/python cad/obs_case/test_cnc.py`."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build123d import Box, Pos, Vector  # noqa: E402

from obs_case import checks, drawings, shop, variants  # noqa: E402
from obs_case.spec import LAYOUT  # noqa: E402

MILLED = ("shell", "plate")
THIN, THINNER = 1.45, 1.15  # mm, test walls under checks.CNC_MIN_WALL
PLACES = 6


def reach(part, corner):
    """How deep the cutter of the corner's setup plunges, to the part's extreme face."""
    box = part.bounding_box()
    if corner.setup == variants.ABOVE:
        return box.max.Z - corner.z_low
    return corner.z_high - box.min.Z


def setup_sentences(notes):
    """{setup number: sentence} of the 'Setup N, ...' notes."""
    return {int(note.split(",")[0].split()[1]): note for note in notes if note.startswith("Setup ")}


class ReliefSetups(unittest.TestCase):
    def test_each_relief_is_sized_for_the_setup_that_cuts_it(self):
        for name in MILLED:
            part = variants.drawn(name)
            for corner in variants.relief_corners(name):
                with self.subTest(name=name, x=corner.middle.X, y=corner.middle.Y):
                    self.assertIn(corner.setup, variants.SETUPS[name])
                    self.assertAlmostEqual(corner.relief_radius, shop.shop_radius(reach(part, corner)), PLACES)

    def test_the_mx_cut_outs_are_cut_top_up(self):
        stack = LAYOUT.stack
        cut_outs = [corner for corner in variants.relief_corners("shell")
                    if abs(corner.z_low - stack.mx_plate_underside) < 1e-6 and abs(corner.z_high - stack.mx_plate_top) < 1e-6]
        self.assertEqual(len(cut_outs), 4 * len(LAYOUT.keys.x) * len(LAYOUT.keys.y))
        self.assertEqual({corner.setup for corner in cut_outs}, {variants.ABOVE})

    def test_the_plate_reliefs_come_from_its_one_setup_inside_face_up(self):
        self.assertEqual({corner.setup for corner in variants.relief_corners("plate")}, {variants.ABOVE})

    def test_the_drawing_lists_each_relief_in_the_setup_that_cuts_it(self):
        notes = {"shell": drawings._shell_notes(), "plate": drawings._plate_notes()}
        for name in MILLED:
            sentences = setup_sentences(notes[name])
            self.assertEqual(len(sentences), len(variants.SETUPS[name]), name)
            for number, setup in enumerate(variants.SETUPS[name], start=1):
                radii = {f"R{drawings._mm(corner.relief_radius)}" for corner in variants.relief_corners(name)
                         if corner.setup == setup}
                for radius in radii:
                    with self.subTest(name=name, setup=number, radius=radius):
                        self.assertIn(radius, sentences[number])

    def test_the_shell_drawing_names_the_mx_cut_outs_in_the_top_up_setup(self):
        sentences = setup_sentences(drawings._shell_notes())
        top_up = variants.SETUPS["shell"].index(variants.ABOVE) + 1
        self.assertIn("MX cut-outs", sentences[top_up])
        self.assertNotIn("cut-outs", " ".join(text for number, text in sentences.items() if number != top_up))


def walled_box(wall):
    """A 10 mm cube hollowed from its top and +x face, leaving a `wall` thick wall at x 0 to `wall`
    and a 2 mm floor."""
    outer = Pos(5, 5, 5) * Box(10, 10, 10)
    return outer - Pos(5 + wall / 2 + 1, 5, 6 + 1) * Box(10 - wall + 2, 6, 8 + 2)


def thin_wall(thickness, region=(-1, -1, -1, 11, 11, 11)):
    return checks.ThinWall("test wall", "test.wall", thickness, (region,))


class MinimumWall(unittest.TestCase):
    def test_a_wall_under_the_cnc_minimum_is_a_problem(self):
        found = checks.wall_problems(walled_box(THIN), ())
        self.assertTrue(found)
        self.assertTrue(all(f"wall {THIN:.2f}" in problem for problem in found), found)

    def test_a_wall_at_the_cnc_minimum_passes(self):
        self.assertEqual(checks.wall_problems(walled_box(checks.CNC_MIN_WALL), ()), [])

    def test_an_accepted_thin_wall_passes_where_board_toml_draws_it(self):
        self.assertEqual(checks.wall_problems(walled_box(THIN), (thin_wall(THIN),)), [])

    def test_an_accepted_thin_wall_milled_thinner_is_a_problem(self):
        found = checks.wall_problems(walled_box(THINNER), (thin_wall(THIN),))
        walls = [problem for problem in found if problem.startswith("wall ")]
        self.assertTrue(walls, found)
        self.assertTrue(all(f"wall {THINNER:.2f}" in problem and "test wall" in problem for problem in walls), found)

    def test_an_accepted_thin_wall_elsewhere_does_not_cover_it(self):
        found = checks.wall_problems(walled_box(THIN), (thin_wall(THIN, (20, 20, 20, 30, 30, 30)),))
        self.assertTrue(any(f"wall {THIN:.2f}" in problem for problem in found), found)

    def test_an_accepted_thin_wall_the_part_lost_is_a_problem(self):
        found = checks.wall_problems(walled_box(checks.CNC_MIN_WALL), (thin_wall(THIN),))
        self.assertEqual(found, [f"accepted thin wall test wall (test.wall {THIN:g}) not found"])

    def test_the_milled_cnc_parts_hold_the_minimum_or_an_accepted_thin_wall(self):
        parts = variants.parts(variants.CNC)
        for name in MILLED:
            with self.subTest(name=name):
                self.assertEqual(checks.wall_problems(parts[name], checks.thin_walls(name)), [])

    def test_the_accepted_thin_walls_are_the_ones_board_toml_draws(self):
        names = {name: {wall.source for wall in checks.thin_walls(name)} for name in MILLED}
        self.assertEqual(names, {"shell": {"[usb] back_wall_thinned.to", "[display_carrier] skirt", "[screws] boss_diameter"},
                                 "plate": {"[bottom_plate] key_ribs.width", "[pcb] holes 3.3,166"}})

    def test_the_back_left_standoff_web_is_the_hole_to_the_bay_arc(self):
        pcb, body = LAYOUT.pcb, LAYOUT.body
        corner = pcb.corner_radius + body.pcb_clearance
        centre = Vector(-body.pcb_clearance + corner, pcb.depth + body.pcb_clearance - corner, 0)
        hole = Vector(*pcb.holes[-1], 0)
        want = corner - (hole - centre).length - pcb.hole_diameter / 2
        webs = [wall.thickness for wall in checks.thin_walls("plate") if wall.name.startswith("standoff")]
        self.assertEqual(len(webs), 1)
        self.assertAlmostEqual(webs[0], want, PLACES)
        self.assertGreaterEqual(webs[0], checks.SHOP_MIN_WALL)


if __name__ == "__main__":
    unittest.main()
