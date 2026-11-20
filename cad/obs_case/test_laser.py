# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Task 6.7: the deck engrave sheet. Its marks pass the shop rules on the deck, the sheet reads
back and repeats byte for byte, and each check catches a broken mark or file. Needs cad/.venv:
`cad/.venv/bin/python cad/obs_case/test_laser.py`."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ezdxf  # noqa: E402
from build123d import Align, Circle, Pos, Rectangle, Text  # noqa: E402

from obs_case import deck, laser  # noqa: E402
from obs_case.spec import LAYOUT  # noqa: E402

SUFFIXES = (".dxf", ".svg", ".pdf")
SHELL = deck.top_shell()
MARKS = laser.marks()


def _problems(readbacks):
    return [problem for readback in readbacks for problem in readback.problems]


class Marks(unittest.TestCase):
    def test_the_deck_marks_pass_every_rule(self):
        self.assertEqual([], laser.problems(MARKS, SHELL))

    def test_each_knob_has_its_digit_and_a_scale_of_tick_count_ticks(self):
        knobs = len(LAYOUT.knobs.y)
        self.assertEqual(knobs, sum(name.startswith("index ") for name in MARKS))
        scales = [sketch for name, sketch in MARKS.items() if name.startswith("ticks ")]
        self.assertEqual([LAYOUT.laser.tick_count] * knobs, [len(sketch.faces()) for sketch in scales])

    def test_each_button_dot_sits_under_its_legend_cell(self):
        for x, button in zip(laser.legend_x(), LAYOUT.buttons.x, strict=True):
            self.assertAlmostEqual(x, button, delta=laser.DOT_ON_BUTTON)

    def test_a_text_mark_has_the_cap_height_it_is_built_for(self):
        cap = LAYOUT.laser.wordmark.cap_height
        glyph = laser.text_mark("H", cap, (0, 0), (Align.MIN, Align.MIN))
        self.assertAlmostEqual(cap, glyph.bounding_box().size.Y, places=6)

    def test_a_stroke_under_the_minimum_is_thin(self):
        under, over = laser.MIN_STROKE * 3 / 4, laser.MIN_STROKE * 5 / 4
        self.assertTrue(laser.thin(Rectangle(under, 2).faces()[0]))
        self.assertFalse(laser.thin(Rectangle(over, 2).faces()[0]))

    def test_a_neck_under_the_minimum_is_thin(self):
        neck = Rectangle(2, 2) + Pos(2, 0) * Rectangle(2, laser.MIN_STROKE * 3 / 4) + Pos(4, 0) * Rectangle(2, 2)
        self.assertTrue(laser.thin(neck.faces()[0]))

    def test_a_regular_weight_font_is_thin_at_this_cap_height(self):
        """DejaVu Sans Book joins its bowls with hairlines: the reason the marks use the bold."""
        book = next(path for path in laser.MARK_FONTS if path.is_file()).with_name("DejaVuSans.ttf")
        cap = LAYOUT.laser.wordmark.cap_height
        glyph = Text("d", font_size=cap / laser.cap_share(book), font_path=str(book))
        self.assertTrue(laser.thin(glyph.faces()[0]))

    def test_a_mark_over_a_window_is_off_the_deck(self):
        x, y, width, depth = LAYOUT.big_display.lens_opening
        stray = {**MARKS, "stray": Pos(x + width / 2, y + depth / 2) * Circle(LAYOUT.laser.dot.diameter / 2)}
        self.assertEqual(["stray is off the flat deck top"], laser.off_deck(stray, SHELL))


@unittest.skipIf(shutil.which("rsvg-convert") is None or shutil.which("pdfinfo") is None,
                 "rsvg-convert and pdfinfo write and read the PDF")
class Sheet(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.reference = laser.reference(SHELL)

    def test_every_format_reads_back(self):
        readbacks = laser.sheet_files(MARKS, self.reference, self.folder / "deck")
        self.assertEqual([], _problems(readbacks))
        self.assertEqual(sorted(f"deck{suffix}" for suffix in SUFFIXES),
                         sorted(readback.path.name for readback in readbacks))

    def test_a_second_run_writes_the_same_bytes(self):
        first = laser.sheet_files(MARKS, self.reference, self.folder / "one" / "deck")
        second = laser.sheet_files(MARKS, self.reference, self.folder / "two" / "deck")
        for a, b in zip(first, second, strict=True):
            self.assertEqual(a.path.read_bytes(), b.path.read_bytes(), a.path.name)

    def test_a_moved_outline_fails_the_dxf_read_back(self):
        laser.sheet_files(MARKS, self.reference, self.folder / "deck")
        path = self.folder / "deck.dxf"
        document = ezdxf.readfile(str(path))
        for entity in document.modelspace().query(f'*[layer=="{laser.REF}"]'):
            entity.translate(laser.SIZE_LIMIT * 2, 0, 0)
        document.saveas(str(path))
        problems = laser.dxf_readback(path, MARKS, self.reference).problems
        self.assertTrue(any(laser.REF in problem for problem in problems), problems)

    def test_a_lost_mark_fails_the_dxf_read_back(self):
        laser.sheet_files(MARKS, self.reference, self.folder / "deck")
        path = self.folder / "deck.dxf"
        document = ezdxf.readfile(str(path))
        space = document.modelspace()
        for entity in list(space.query(f'*[layer=="{laser.MARK}"]')):
            space.delete_entity(entity)
        document.saveas(str(path))
        problems = laser.dxf_readback(path, MARKS, self.reference).problems
        self.assertTrue(any(laser.MARK in problem for problem in problems), problems)


if __name__ == "__main__":
    unittest.main()
