# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Task 6.5: the 3D writers read back and repeat byte for byte, and the read-back checks catch a bad
file. Needs cad/.venv: `cad/.venv/bin/python cad/obs_case/test_export.py`."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build123d import Box, Pos, Sphere, export_step  # noqa: E402

from obs_case import export  # noqa: E402

PART_SUFFIXES = (".step", ".ap242.step", ".brep", ".igs", ".stl", ".3mf")
ASSEMBLY_SUFFIXES = (".step", ".3mf", ".glb")


def _part():
    """A box with a ball cut from a corner: flat and curved faces, one solid."""
    box = Box(20, 10, 5)
    return box - Pos(box.bounding_box().max) * Sphere(3)


def _problems(readbacks):
    return [problem for readback in readbacks for problem in readback.problems]


class Writers(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def test_every_part_format_reads_back(self):
        readbacks = export.part_files(_part(), "OBS-TEST", self.folder / "part")
        self.assertEqual([], _problems(readbacks))
        self.assertEqual(sorted(f"part{suffix}" for suffix in PART_SUFFIXES),
                         sorted(readback.path.name for readback in readbacks))

    def test_the_assembly_reads_back_with_its_labels(self):
        pieces = {"OBS-A": (_part(), "#202020"), "OBS-B": (Pos(0, 30, 0) * _part(), "#d0d0d0")}
        readbacks = export.assembly_files(pieces, "obs-test", self.folder / "assembly")
        self.assertEqual([], _problems(readbacks))
        self.assertEqual(sorted(f"assembly{suffix}" for suffix in ASSEMBLY_SUFFIXES),
                         sorted(readback.path.name for readback in readbacks))
        glb = next(readback for readback in readbacks if readback.path.suffix == ".glb")
        self.assertEqual(["OBS-A", "OBS-B"], sorted(glb.facts["bodies"]))

    def test_a_second_run_writes_the_same_bytes(self):
        first = export.part_files(_part(), "OBS-TEST", self.folder / "one" / "part")
        second = export.part_files(_part(), "OBS-TEST", self.folder / "two" / "part")
        for a, b in zip(first, second, strict=True):
            self.assertEqual(a.path.read_bytes(), b.path.read_bytes(), a.path.name)

    def test_the_step_header_is_fixed(self):
        export.part_files(_part(), "OBS-TEST", self.folder / "part")
        for name, schema in (("part.step", "AUTOMOTIVE_DESIGN"), ("part.ap242.step", "AP242_MANAGED_MODEL")):
            header = (self.folder / name).read_text(encoding="ascii").split("ENDSEC;")[0]
            self.assertIn(f"FILE_NAME('OBS-TEST','{export.TIMESTAMP}'", header, name)
            self.assertIn(schema, header, name)

    def test_a_wrong_solid_fails_the_step_read_back(self):
        path = self.folder / "part.step"
        export_step(Box(20, 10, 5), str(path), timestamp=export.TIMESTAMP)
        problems = export.step_readback(path, _part(), "OBS-TEST", "AUTOMOTIVE_DESIGN").problems
        self.assertTrue(any("volume" in problem for problem in problems), problems)

    def test_a_hole_in_the_mesh_fails_the_stl_read_back(self):
        readback = next(r for r in export.part_files(_part(), "OBS-TEST", self.folder / "part")
                        if r.path.suffix == ".stl")
        data = readback.path.read_bytes()
        count = int.from_bytes(data[80:84], "little") - 1  # drop the last 50-byte triangle
        readback.path.write_bytes(data[:80] + count.to_bytes(4, "little") + data[84:-50])
        problems = export.stl_readback(readback.path, "OBS-TEST", _part()).problems
        self.assertTrue(any("watertight" in problem for problem in problems), problems)


if __name__ == "__main__":
    unittest.main()
