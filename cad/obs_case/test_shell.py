# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The top shell's display pocket walls: they stand outside each pocket from
stack.pocket_skirt_bottom to the deck underside, leave the pocket open, and hold each carrier at
[display_carrier] clearance. Needs cad/.venv: `cad/.venv/bin/python cad/obs_case/test_shell.py`."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build123d import Vector  # noqa: E402

from obs_case import carriers, checks, deck  # noqa: E402
from obs_case.spec import LAYOUT  # noqa: E402

NUDGE = 0.05  # mm a probe sits off the face it tests


def mid(low, high):
    return (low + high) / 2


def wall_heights():
    """z of probes in the wall: just above its bottom, its middle and just under the deck."""
    low, high = LAYOUT.stack.pocket_skirt_bottom, LAYOUT.stack.deck_underside
    return low + NUDGE, mid(low, high), high - NUDGE


class PocketWalls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shell = deck.top_shell()

    def inside(self, x, y, z):
        return self.shell.is_inside(Vector(x, y, z))

    def test_a_wall_stands_beside_each_pocket(self):
        skirt = LAYOUT.display_carrier.skirt
        for name in carriers.NAMES:
            x, y, width, depth = carriers.panel(name).pocket
            for z in wall_heights():
                for wall_x in (x - skirt / 2, x + width + skirt / 2):
                    with self.subTest(name=name, x=wall_x, z=z):
                        self.assertTrue(self.inside(wall_x, mid(y, y + depth), z))

    def test_a_wall_stands_in_front_of_each_pocket_off_the_tail_notch(self):
        skirt = LAYOUT.display_carrier.skirt
        for name in carriers.NAMES:
            x, y, _, _ = carriers.panel(name).pocket
            beside_notch = mid(x, carriers.panel(name).pocket_tail_notch[0])
            with self.subTest(name=name):
                self.assertTrue(self.inside(beside_notch, y - skirt / 2, mid(*wall_heights()[::2])))

    def test_the_pocket_stays_open_inside_its_walls(self):
        for name in carriers.NAMES:
            x, y, width, depth = carriers.panel(name).pocket
            for z in wall_heights():
                for open_x in (x + NUDGE, x + width - NUDGE):
                    with self.subTest(name=name, x=open_x, z=z):
                        self.assertFalse(self.inside(open_x, mid(y, y + depth), z))

    def test_the_tail_notch_stays_open(self):
        for name in carriers.NAMES:
            x, y, width, depth = carriers.panel(name).pocket_tail_notch
            with self.subTest(name=name):
                self.assertFalse(self.inside(mid(x, x + width), mid(y, y + depth), mid(*wall_heights()[::2])))

    def test_no_wall_below_the_skirt_bottom(self):
        skirt = LAYOUT.display_carrier.skirt
        x, y, _, depth = carriers.panel("big").pocket
        self.assertFalse(self.inside(x - skirt / 2, mid(y, y + depth), LAYOUT.stack.pocket_skirt_bottom - NUDGE))

    def test_each_carrier_sits_the_clearance_off_the_walls(self):
        for name in carriers.NAMES:
            with self.subTest(name=name):
                self.assertAlmostEqual(carriers.carrier(name).distance_to(self.shell),
                                       LAYOUT.display_carrier.clearance, places=6)

    def test_the_body_check_probes_the_walls(self):
        names = {name for name, _, _ in checks.probes()}
        for name in carriers.NAMES:
            with self.subTest(name=name):
                self.assertIn(f"{name} pocket wall left", names)
                self.assertIn(f"{name} pocket open left", names)

    def test_the_carrier_check_reports_a_carrier_the_walls_do_not_locate(self):
        far = carriers.block([0.0, 0.0, 1.0, 1.0], LAYOUT.stack.pcb_top, LAYOUT.stack.deck_underside)
        found = checks.location_problems("big", carriers.carrier("big"), far)
        self.assertEqual(len(found), 1)
        self.assertIn("big carrier", found[0])


if __name__ == "__main__":
    unittest.main()
