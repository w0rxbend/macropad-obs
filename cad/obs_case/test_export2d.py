# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Task 6.6: the 2D sheets (DXF, SVG, PDF) read back and repeat byte for byte, and the read-back
catches a broken file. Needs cad/.venv: `cad/.venv/bin/python cad/obs_case/test_export2d.py`."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ezdxf  # noqa: E402
from build123d import Pos, Rectangle, RectangleRounded  # noqa: E402

from obs_case import deck, export2d  # noqa: E402
from obs_case.spec import LAYOUT  # noqa: E402

SUFFIXES = (".dxf", ".svg", ".pdf")


def _ring():
    """A rounded plate with a square hole: arcs, lines, an outer and an inner wire."""
    return Pos(30, 40) * (RectangleRounded(40, 25, 3) - Rectangle(10, 8))


def _problems(readbacks):
    return [problem for readback in readbacks for problem in readback.problems]


@unittest.skipIf(shutil.which("rsvg-convert") is None or shutil.which("pdfinfo") is None,
                 "rsvg-convert and pdfinfo write and read the PDF")
class Sheets(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def test_every_format_reads_back(self):
        readbacks = export2d.sheet_files(_ring(), self.folder / "ring")
        self.assertEqual([], _problems(readbacks))
        self.assertEqual(sorted(f"ring{suffix}" for suffix in SUFFIXES),
                         sorted(readback.path.name for readback in readbacks))

    def test_a_second_run_writes_the_same_bytes(self):
        first = export2d.sheet_files(_ring(), self.folder / "one" / "ring")
        second = export2d.sheet_files(_ring(), self.folder / "two" / "ring")
        for a, b in zip(first, second, strict=True):
            self.assertEqual(a.path.read_bytes(), b.path.read_bytes(), a.path.name)

    def test_a_missing_edge_fails_the_dxf_read_back(self):
        export2d.sheet_files(_ring(), self.folder / "ring")
        path = self.folder / "ring.dxf"
        document = ezdxf.readfile(str(path))
        space = document.modelspace()
        space.delete_entity(next(iter(space)))
        document.saveas(str(path))
        problems = export2d.dxf_readback(path, _ring()).problems
        self.assertTrue(problems, "a DXF with an open outline passed")

    def test_a_wrong_outline_fails_the_svg_read_back(self):
        export2d.sheet_files(Pos(30, 40) * RectangleRounded(40, 25, 3), self.folder / "plate")
        problems = export2d.svg_readback(self.folder / "plate.svg", _ring()).problems
        self.assertTrue(any("area" in problem for problem in problems), problems)


class Shapes(unittest.TestCase):
    def test_the_lens_is_the_cnc_recess_less_the_lens_fit(self):
        fit = LAYOUT.variants.cnc.lens_fit
        for name, panel in zip(export2d.PANELS, deck.panels(), strict=True):
            recess = deck.lens_recess(panel)
            box = export2d.lens(name).bounding_box()
            self.assertAlmostEqual(box.size.X, recess[2] - 2 * fit, places=6)
            self.assertAlmostEqual(box.size.Y, recess[3] - 2 * fit, places=6)

    def test_the_foam_frame_is_the_module_outline_less_the_lens_opening(self):
        for name, panel in zip(export2d.PANELS, deck.panels(), strict=True):
            _, _, width, depth = panel.outline
            _, _, open_width, open_depth = panel.lens_opening
            face = export2d.foam(name)
            self.assertAlmostEqual(face.area, width * depth - open_width * open_depth, places=6)
            self.assertEqual(0.0, face.bounding_box().max.Z)

    def test_every_sheet_is_named(self):
        self.assertEqual(["foam-big", "foam-narrow", "lens-big", "lens-narrow"], sorted(export2d.sheets()))


if __name__ == "__main__":
    unittest.main()
