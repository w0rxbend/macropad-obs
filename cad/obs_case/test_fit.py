# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Task 6.8: the fit check counts shared volume as an interference, a touch as none, and overlap
inside a part's allowance as allowed; it finds the board STEP and refuses a STEP that is not the
one its manifest names or that an older board wrote. Needs cad/.venv, not the board STEP:
`cad/.venv/bin/python cad/obs_case/test_fit.py`."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build123d import Box, Pos  # noqa: E402

from obs_case import fit  # noqa: E402
from obs_case.spec import LAYOUT  # noqa: E402


def cube(x, size=10):
    """A cube `size` on a side, its low corner at (x, 0, 0)."""
    return Pos(x + size / 2, size / 2, size / 2) * Box(size, size, size)


def board(*solids):
    return [fit.BoardSolid(f"part{index}", solid) for index, solid in enumerate(solids)]


class Interferences(unittest.TestCase):
    def test_shared_volume_is_an_interference(self):
        hits = fit.interferences({"shell": cube(0)}, board(cube(8)), {})
        self.assertEqual([(hit.part, hit.other) for hit in hits], [("shell", "part0")])
        self.assertAlmostEqual(hits[0].volume, 200.0, places=6)

    def test_a_touch_is_no_interference(self):
        self.assertEqual(fit.interferences({"shell": cube(0)}, board(cube(10)), {}), [])

    def test_overlap_inside_the_allowance_is_allowed_not_counted(self):
        allowance = cube(8, size=20)
        hits = fit.interferences({"dial": cube(0)}, board(cube(8)), {"dial": allowance})
        self.assertEqual(len(hits), 1)
        self.assertAlmostEqual(hits[0].volume, 0.0, places=6)
        self.assertAlmostEqual(hits[0].allowed, 200.0, places=6)

    def test_overlap_past_the_allowance_still_counts(self):
        allowance = Pos(19 / 2, 5, 5) * Box(1, 10, 10)  # covers x 9 to 10 of the 8 to 10 overlap
        hits = fit.interferences({"dial": cube(0)}, board(cube(8)), {"dial": allowance})
        self.assertAlmostEqual(hits[0].volume, 100, places=6)

    def test_case_parts_are_checked_against_each_other(self):
        hits = fit.interferences({"shell": cube(0), "cap": cube(5)}, [], {})
        self.assertEqual([(hit.part, hit.other) for hit in hits], [("shell", "cap")])


class ShaftFlat(unittest.TestCase):
    def test_the_allowance_is_the_round_shaft_past_its_flat(self):
        flat = fit.shaft_flat_allowance(0.0, 0.0)
        shaft, shaft_end = LAYOUT.envelopes.ec11_shaft
        flat_across, flat_length = LAYOUT.knob_dial.shaft_flat
        flat_y, middle_z = flat_across - shaft / 2, shaft_end - flat_length / 2
        self.assertTrue(flat.is_inside((0, (flat_y + shaft / 2) / 2, middle_z)))
        self.assertFalse(flat.is_inside((0, 0, middle_z)))
        self.assertFalse(flat.is_inside((0, (flat_y + shaft / 2) / 2, shaft_end - flat_length - 1)))


class FindStep(unittest.TestCase):
    def test_the_final_step_wins_over_the_provisional_one(self):
        with tempfile.TemporaryDirectory() as folder:
            final, provisional = Path(folder, "step"), Path(folder, "build")
            for path in (final, provisional):
                path.mkdir()
                (path / fit.STEP_NAME).write_text("x")
            self.assertEqual(fit.find_step((final, provisional)), final / fit.STEP_NAME)

    def test_no_step_names_the_recipe(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(FileNotFoundError, "just pcb step"):
                fit.find_step((Path(folder),))


class Manifest(unittest.TestCase):
    def write(self, folder, step_bytes, board_bytes, named_step, named_board):
        step, board_file = Path(folder, fit.STEP_NAME), Path(folder, "board.kicad_pcb")
        step.write_bytes(step_bytes)
        board_file.write_bytes(board_bytes)
        Path(folder, "manifest.json").write_text(json.dumps({
            "sha256": hashlib.sha256(named_step).hexdigest(),
            "board_sha256": hashlib.sha256(named_board).hexdigest()}))
        return step, board_file

    def test_a_matching_manifest_has_no_problem(self):
        with tempfile.TemporaryDirectory() as folder:
            step, board_file = self.write(folder, b"step", b"board", b"step", b"board")
            self.assertEqual(fit.manifest_problems(step, board_file), [])

    def test_a_step_its_manifest_does_not_name_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            step, board_file = self.write(folder, b"edited", b"board", b"step", b"board")
            self.assertRegex(" ".join(fit.manifest_problems(step, board_file)), "sha256")

    def test_a_step_from_an_older_board_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            step, board_file = self.write(folder, b"step", b"rerouted", b"step", b"board")
            self.assertRegex(" ".join(fit.manifest_problems(step, board_file)), "just pcb step")


if __name__ == "__main__":
    unittest.main()
