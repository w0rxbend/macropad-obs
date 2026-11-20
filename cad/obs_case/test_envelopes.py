# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Task 6.6: one envelope solid per bought part, sized from board.toml, and each STEP reads back.
Needs cad/.venv: `cad/.venv/bin/python cad/obs_case/test_envelopes.py`."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from obs_case import envelopes  # noqa: E402
from obs_case.spec import LAYOUT  # noqa: E402

PARTS = ["big-display", "dsa-keycap", "ec11", "esp32-s3-wroom-1", "fpc-big", "fpc-narrow", "mx-switch",
         "narrow-display", "omron-b3f", "usb4216"]


class Solids(unittest.TestCase):
    def test_one_valid_solid_per_bought_part(self):
        parts = envelopes.parts()
        self.assertEqual(PARTS, sorted(parts))
        for name, solid in parts.items():
            self.assertEqual(1, len(solid.solids()), name)
            self.assertTrue(solid.is_valid, name)

    def test_each_stands_on_its_seat_centred(self):
        for name, solid in envelopes.parts().items():
            box = solid.bounding_box()
            self.assertAlmostEqual(0.0, box.min.Z, places=9, msg=name)
            self.assertAlmostEqual(0.0, box.center().X, places=9, msg=name)
            self.assertAlmostEqual(0.0, box.center().Y, places=9, msg=name)

    def test_heights_come_from_board_toml(self):
        parts, table = envelopes.parts(), LAYOUT.envelopes
        self.assertAlmostEqual(table.mx_stem_top, parts["mx-switch"].bounding_box().max.Z)
        self.assertAlmostEqual(table.ec11_shaft[1], parts["ec11"].bounding_box().max.Z)
        self.assertAlmostEqual(table.b3f_plunger_top, parts["omron-b3f"].bounding_box().max.Z)
        self.assertAlmostEqual(LAYOUT.usb.height, parts["usb4216"].bounding_box().max.Z)

    def test_the_mx_body_below_the_plate_fits_the_plate_hole(self):
        lower = envelopes.parts()["mx-switch"].solids()[0]
        width = max(edge.length for edge in lower.edges() if edge.center().Z == 0.0)
        self.assertAlmostEqual(LAYOUT.keys.plate_hole, width)


class Files(unittest.TestCase):
    def test_every_step_reads_back_with_one_solid(self):
        folder = Path(tempfile.mkdtemp())
        readbacks = envelopes.part_files(folder)
        self.assertEqual([], [problem for readback in readbacks for problem in readback.problems])
        self.assertEqual([1] * len(PARTS), [readback.facts["solids"] for readback in readbacks])


if __name__ == "__main__":
    unittest.main()
