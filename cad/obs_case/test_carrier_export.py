# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The printable display carriers: each one exports in six formats that read back, and each STEP
stands on the bed at its board.toml height. Needs cad/.venv:
`cad/.venv/bin/python cad/obs_case/test_carrier_export.py`."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build123d import import_step  # noqa: E402

from obs_case import carrier_export, carriers  # noqa: E402
from obs_case.spec import LAYOUT  # noqa: E402

FORMATS = (".step", ".ap242.step", ".brep", ".igs", ".stl", ".3mf")


class CarrierExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        root = Path(cls.folder.name)
        cls.code = carrier_export.export_all(stage=root / "stage", target=root / "exports")
        cls.exports = root / "exports" / carrier_export.FOLDER

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_every_carrier_exports_in_every_format(self):
        self.assertEqual(self.code, 0)
        want = {f"{name}{suffix}" for name in carriers.NAMES for suffix in FORMATS}
        self.assertEqual({path.name for path in self.exports.iterdir()}, want)

    def test_each_step_stands_on_the_bed_at_its_height(self):
        for name in carriers.NAMES:
            box = import_step(str(self.exports / f"{name}.step")).bounding_box()
            ring = getattr(LAYOUT.display_carrier, name)
            self.assertAlmostEqual(box.min.Z, LAYOUT.stack.pcb_top, places=6, msg=name)
            self.assertAlmostEqual(box.max.Z - box.min.Z, ring.height, places=6, msg=name)


if __name__ == "__main__":
    unittest.main()
