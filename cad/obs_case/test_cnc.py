# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The cnc variant's shop rules: each dog-bone is sized for the setup that cuts it, and the CNC
drawing lists it in that setup. Needs cad/.venv: `cad/.venv/bin/python cad/obs_case/test_cnc.py`."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from obs_case import drawings, shop, variants  # noqa: E402
from obs_case.spec import LAYOUT  # noqa: E402

MILLED = ("shell", "plate")
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


if __name__ == "__main__":
    unittest.main()
