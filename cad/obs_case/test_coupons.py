# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Task 6.9: every print coupon is one valid solid on the bed, its parent's material inside its box,
holds the feature it tests, and reads back; the checks catch a coupon that misses its feature or
falls apart. Needs cad/.venv: `cad/.venv/bin/python cad/obs_case/test_coupons.py`."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build123d import Box, Pos  # noqa: E402

from obs_case import coupons, insert  # noqa: E402
from obs_case.export import part_files  # noqa: E402
from obs_case.spec import LAYOUT  # noqa: E402

NUDGE = 0.04  # mm a probe sits inside the pocket corner it tests
WANT = {"module-stack", "usb-top", "usb-base", "mx-cutout", "cap-hole", "knob-hole", "knob-bore", "fpc-big",
        "fpc-narrow"}


class Coupons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = coupons.parents()
        cls.placed = coupons.built(cls.parts)

    def test_every_asked_coupon_is_built(self):
        self.assertEqual(set(self.placed), WANT)

    def test_no_problem(self):
        self.assertEqual(coupons.problems(self.placed, self.parts), [])

    def test_a_coupon_off_its_feature_is_caught(self):
        moved = coupons.Coupon("mx-cutout", "shell", Pos(LAYOUT.keys.pitch, 0, 0) * self.placed["mx-cutout"].coupon.window)
        found = coupons.problems({"mx-cutout": coupons.place(moved, self.parts)}, self.parts)
        self.assertTrue(any("feature" in problem or "expected air" in problem for problem in found), found)

    def test_a_loose_stand_in_is_caught(self):
        original = self.placed["fpc-big"].coupon
        floating = Pos(0, 0, -LAYOUT.pcb.thickness * 3) * original.added
        broken = coupons.Coupon(original.name, original.parent, original.window, floating)
        found = coupons.problems({"fpc-big": coupons.place(broken, self.parts)}, self.parts)
        self.assertTrue(any("solids, valid" in problem for problem in found), found)

    def test_a_coupon_unlike_its_parent_is_caught(self):
        original = self.placed["cap-hole"]
        corner = original.whole.bounding_box().min  # the front wall: solid there
        nick = Pos(corner.X + 0.5, corner.Y + 0.5, corner.Z + 0.5) * Box(1, 1, 1)
        changed = coupons.Placed(original.coupon, original.whole - nick, original.location)
        found = coupons.problems({"cap-hole": changed}, self.parts)
        self.assertTrue(any("differs from its parent" in problem for problem in found), found)

    def test_module_stack_posts_stand_at_the_pcb_bottom(self):
        top = self.placed["module-stack"].whole.bounding_box().max.Z
        self.assertAlmostEqual(top, LAYOUT.stack.pcb_bottom, places=6)

    def test_usb_top_holds_the_whole_thinned_pocket(self):
        box = self.placed["usb-top"].whole.bounding_box()
        half = LAYOUT.usb.back_wall_thinned.area[0] / 2
        self.assertLess(box.min.X, LAYOUT.usb.x - half)
        self.assertGreater(box.max.X, LAYOUT.usb.x + half)
        back = LAYOUT.body.outline[1] + LAYOUT.body.outline[3]  # off the pocket's rounded inside corners
        inside_the_pocket = (LAYOUT.usb.x + half - NUDGE, back - NUDGE, insert.usb_mouth_z())
        self.assertFalse(self.placed["usb-top"].whole.is_inside(inside_the_pocket))

    def test_a_rebuilt_coupon_keeps_its_face_order(self):
        """Parallel booleans gave the FPC coupons two face orders, so two export runs wrote other bytes."""
        def order(coupon):
            whole = coupons.assembled(coupon, self.parts)
            return tuple(tuple(round(value, 4) for value in face.center()) for face in whole.faces())

        for name in ("fpc-big", "fpc-narrow"):
            coupon = self.placed[name].coupon
            self.assertEqual(len({order(coupon) for _ in range(6)}), 1, name)

    def test_each_coupon_reads_back(self):
        with tempfile.TemporaryDirectory() as folder:
            entry = self.placed["knob-bore"]
            readbacks = part_files(entry.on_the_bed, coupons.label("knob-bore"), Path(folder) / "knob-bore")
        self.assertEqual([problem for readback in readbacks for problem in readback.problems], [])


if __name__ == "__main__":
    unittest.main()
