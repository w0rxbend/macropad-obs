#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""spec.py reads the layout from board.toml at run time, rejects a case outline that does not grow
from the PCB, and no source under cad/ writes a layout number. Stdlib only: `just cad-check`."""

import ast
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

CAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAD))

from obs_case import spec

BOARD_TEXT = spec.BOARD_TOML.read_text(encoding="utf-8")
# Scale-free factors (halve, double, unit, zero) that also happen to be board.toml values.
ARITHMETIC = {0.0, 0.5, 1.0, 2.0}


def load_edited(old, new):
    """spec.load on a copy of board.toml with one exact text edit."""
    if BOARD_TEXT.count(old) != 1:
        raise AssertionError(f"edit target {old!r} is not unique in board.toml")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "board.toml"
        path.write_text(BOARD_TEXT.replace(old, new), encoding="utf-8")
        return spec.load(path)


def layout_numbers():
    """Every float in the board.toml tables from [body] down. Integers there are pixel or layer
    counts, never millimetres, so only floats count as layout numbers."""
    board = tomllib.loads(BOARD_TEXT)
    names = list(board)
    found = set()
    pending = [board[name] for name in names[names.index(spec.FIRST_LAYOUT_TABLE) :]]
    while pending:
        entry = pending.pop()
        if isinstance(entry, dict):
            pending.extend(entry.values())
        elif isinstance(entry, list):
            pending.extend(entry)
        elif isinstance(entry, float):
            found.add(entry)
    return found - ARITHMETIC


def layout_literals(source, numbers):
    """(line, value) of each float literal in Python `source` that is a layout number."""
    return [
        (node.lineno, node.value)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, float) and node.value in numbers
    ]


def cad_sources():
    return [path for path in sorted(CAD.rglob("*.py")) if ".venv" not in path.relative_to(CAD).parts]


class LoadTest(unittest.TestCase):
    def test_tree_outline_is_board_toml_body_outline(self):
        self.assertEqual(spec.LAYOUT.body.outline, tomllib.loads(BOARD_TEXT)["body"]["outline"])

    def test_inline_tables_read_as_attributes(self):
        want = tomllib.loads(BOARD_TEXT)["display_carrier"]["big"]["outer"]
        self.assertEqual(spec.LAYOUT.display_carrier.big.outer, want)

    def test_a_changed_board_toml_changes_the_params(self):
        layout = load_edited("x = 76.0                              # design", "x = 75.0 #")
        self.assertEqual(layout.knobs.x, 75.0)

    def test_tables_above_body_are_not_layout(self):
        self.assertFalse(hasattr(spec.LAYOUT, "gpio"))

    def test_outline_grow_is_wall_plus_clearance(self):
        body = tomllib.loads(BOARD_TEXT)["body"]
        self.assertAlmostEqual(spec.OUTLINE_GROW, body["wall"] + body["pcb_clearance"])


class OutlineRuleTest(unittest.TestCase):
    def test_outline_off_the_pcb_grow_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "body.outline"):
            load_edited("outline = [-2.9, -2.9, 97.4, 173.5]", "outline = [-2.9, -2.9, 97.4, 174.0]")

    def test_thinner_wall_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "body.outline"):
            load_edited("wall = 2.5                            # design", "wall = 2.0 #")

    def test_corner_not_concentric_with_the_pcb_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "body.corner_radius"):
            load_edited("corner_radius = 6.9", "corner_radius = 6.0")


class NoLayoutLiteralTest(unittest.TestCase):
    def test_no_cad_source_writes_a_layout_number(self):
        numbers = layout_numbers()
        found = {
            str(path.relative_to(CAD)): hits
            for path in cad_sources()
            if (hits := layout_literals(path.read_text(encoding="utf-8"), numbers))
        }
        self.assertEqual(found, {})

    def test_the_scan_sees_the_key_pitch(self):
        pitch = spec.LAYOUT.keys.pitch
        self.assertEqual(layout_literals(f"PITCH = {pitch!r}\n", layout_numbers()), [(1, pitch)])

    def test_the_scan_reaches_the_case_sources(self):
        names = {path.name for path in cad_sources()}
        self.assertTrue({"spec.py", "build.py", "export.py"} <= names, names)


if __name__ == "__main__":
    unittest.main()
