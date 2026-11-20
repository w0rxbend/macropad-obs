# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Tests of step.py's plain parts: where the cad envelopes land, how a model path resolves, and how a STEP file
is read back to its solid count. Plain Python, no KiCad: `just pcb-test`. The export runs in `just pcb step`."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import step
from circuit_hmi import BOARD

STEP_TEXT = ("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\nENDSEC;\n"
             "DATA;\n#10 = MANIFOLD_SOLID_BREP('',#11);\n#20 = MANIFOLD_SOLID_BREP('R1',#21);\nENDSEC;\n"
             "END-ISO-10303-21;\n")


class SolidCountTest(unittest.TestCase):
    def test_counts_each_solid_entity(self) -> None:
        self.assertEqual(step.solid_count(STEP_TEXT), 2)

    def test_a_cut_off_file_is_not_read(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a whole STEP"):
            step.solid_count(STEP_TEXT.removesuffix("END-ISO-10303-21;\n"))

    def test_a_file_of_another_kind_is_not_read(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a whole STEP"):
            step.solid_count("solid stl\nendsolid stl\n")


class ExpectedSolidsTest(unittest.TestCase):
    def test_a_model_placed_twice_adds_its_solids_once_as_the_step_shares_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "r.step"
            model.write_text(STEP_TEXT)
            self.assertEqual(step.expected_solids({"R1": [str(model)], "R2": [str(model)], "H1": []}),
                             step.BOARD_SOLIDS + 2)


class PlacedReferencesTest(unittest.TestCase):
    def test_each_occurrence_names_its_part_and_an_envelope_counts_for_its_part(self) -> None:
        text = ("#1 = NEXT_ASSEMBLY_USAGE_OCCURRENCE('1','R1','',#2,#3,$);\n"
                "#4 = NEXT_ASSEMBLY_USAGE_OCCURRENCE('2','SW1-envelope','',#2,#5,$);\n")
        self.assertEqual(step.placed_references(text), {"R1", "SW1"})


class ResolveTest(unittest.TestCase):
    def test_the_kicad_9_and_10_model_variables_name_the_image_library(self) -> None:
        for variable in ("KICAD9_3DMODEL_DIR", "KICAD10_3DMODEL_DIR"):
            self.assertEqual(step.resolve_model("${" + variable + "}/RF_Module.3dshapes/ESP32-S3-WROOM-1.step"),
                             step.KICAD_MODEL_DIR / "RF_Module.3dshapes/ESP32-S3-WROOM-1.step")

    def test_another_variable_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "KIPRJMOD"):
            step.resolve_model("${KIPRJMOD}/part.step")


class EnvelopeSpotTest(unittest.TestCase):
    def _spots(self, stem: str) -> list[step.EnvelopeSpot]:
        return [spot for spot in step.envelope_spots() if spot.stem == stem]

    def test_a_switch_envelope_stands_on_every_key_point(self) -> None:
        keys = BOARD["keys"]
        points = {(spot.x, spot.y) for spot in self._spots("mx-switch")}
        self.assertEqual(points, {(x, y) for x in keys["x"] for y in keys["y"]})
        self.assertEqual({spot.ref for spot in self._spots("mx-switch")}, {f"SW{n}" for n in range(1, 10)})

    def test_an_encoder_envelope_stands_on_every_knob_shaft(self) -> None:
        knobs = BOARD["knobs"]
        spots = self._spots("ec11")
        self.assertEqual([(spot.ref, spot.x, spot.y) for spot in spots],
                         [(f"SW{14 + n}", knobs["x"], y) for n, y in enumerate(knobs["y"])])

    def test_the_jack_hangs_under_the_board_with_its_shell_front_past_the_back_edge(self) -> None:
        usb, depth = BOARD["usb"], BOARD["pcb"]["depth"]
        [jack] = self._spots("usb4216")
        self.assertEqual((jack.ref, jack.side), ("J1", step.BOTTOM))
        self.assertAlmostEqual(jack.y + usb["body"][1] / 2, depth + usb["mouth_overhang"])
        self.assertEqual(jack.x, usb["x"])

    def test_each_panel_back_sits_its_thickness_below_the_panel_face(self) -> None:
        face = BOARD["stack"]["panel_face"]
        for stem, table in (("big-display", "big_display"), ("narrow-display", "narrow_display")):
            [panel] = self._spots(stem)
            left, front, width, depth = BOARD[table]["outline"]
            self.assertEqual((panel.x, panel.y), (left + width / 2, front + depth / 2))
            self.assertAlmostEqual(panel.z, face - BOARD[table]["thickness"])
            self.assertEqual(panel.side, step.TOP)

    def test_switches_and_encoders_seat_on_the_board_top(self) -> None:
        for stem in ("mx-switch", "ec11"):
            self.assertEqual({(spot.side, spot.z) for spot in self._spots(stem)}, {(step.TOP, 0.0)})

    def test_every_envelope_file_is_exported_by_cad(self) -> None:
        for spot in step.envelope_spots():
            self.assertTrue(step.envelope_path(spot).is_file(), spot.stem)


if __name__ == "__main__":
    unittest.main()
