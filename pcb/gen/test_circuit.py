# SPDX-License-Identifier: CERN-OHL-S-2.0
"""In-memory netlist, BOM rows, and the board.toml keep-out. No pcbnew."""

import tomllib
import unittest
from pathlib import Path

from circuit import (
    ENCODER_BODY,
    FH12_COURTYARD,
    QSPI,
    SOCKET_HALF,
    USB_DM,
    USB_DP,
    XIN,
    XOUT,
    build,
    circle_hits_rect,
    forbidden_lcsc,
    keepout_hits,
    path_len,
)
from fab import BOM_HEADER, CPL_HEADER, HAND_HEADER, bom_rows, cpl_rows, hand_rows

ROOT = Path(__file__).resolve().parents[2]
BOARD = tomllib.loads((ROOT / "board.toml").read_text())


class CircuitTest(unittest.TestCase):
    def setUp(self):
        self.board = build(BOARD)

    def test_locked_parts_and_unverified_cells(self):
        by_des = {part.designator: part for part in self.board.parts}
        self.assertEqual(by_des["U1"].lcsc, "C2040")
        self.assertEqual(by_des["U2"].lcsc, "C97521")
        self.assertIn("SOIC-8 208 mil", by_des["U2"].comment)
        self.assertEqual(by_des["J2"].lcsc, "C596730")
        self.assertEqual(by_des["J2"].layer, "top")
        for des in ("J1", "U3", "U4", "SW10", "SW11", "Y1", "Q1", "R20", "R21", "F1", "SW1"):
            self.assertEqual(by_des[des].lcsc, "UNVERIFIED", des)
        self.assertEqual(by_des["Q1"].comment, "N-channel, Rds(on) at Vgs=2.5 V, Id ≥ 200 mA, SOT-23")
        self.assertEqual(by_des["SW1"].comment, "MX hot-swap, Kailh CPG151101S11 class")
        self.assertEqual(by_des["Y1"].mpn, "ABM8-272-T3")
        self.assertEqual(forbidden_lcsc(self.board), [])
        self.assertFalse(any("SK6812" in part.comment or "SK6812" in part.footprint for part in self.board.parts))
        self.assertEqual(sum(1 for part in self.board.parts if part.designator.startswith("SW") and part.comment.startswith("MX")), 9)

    def test_power_crystal_flash_and_fpc(self):
        nets = self.board.nets
        self.assertIn(("J1", "VBUS"), nets["VBUS"])
        self.assertIn(("F1", "2"), nets["V5"])
        self.assertIn(("U3", "OUT"), nets["V3"])
        self.assertIn(("U4", "D+"), nets["USB_DP_C"])
        self.assertIn(("R1", "2"), nets["GND"])
        self.assertIn(("R2", "2"), nets["GND"])
        self.assertIn(("Y1", "1"), nets["XIN"])
        self.assertIn(("R5", "1"), nets["XOUT"])
        self.assertEqual(sum(1 for part in self.board.parts if part.comment == "100 nF"), 10)
        self.assertEqual(sum(1 for part in self.board.parts if part.comment == "1 uF"), 2)
        self.assertIn(("U2", "1"), nets["QSPI_SS"])
        self.assertIn(("R6", "1"), nets["QSPI_SS"])
        self.assertIn(("SW10", "1"), nets["BOOT"])
        self.assertIn(("SW11", "1"), nets["RUN"])
        for pad in ("A", "B", "C", "S1", "S2"):
            self.assertTrue(any(pin == pad and des == "EN1" for pairs in nets.values() for des, pin in pairs))
        self.assertIn(("J2", "14"), nets["IM3"])
        self.assertIn(("R20", "1"), nets["IM3"])
        self.assertNotIn(("J2", "12"), {pin for pairs in nets.values() for pin in pairs})
        self.assertEqual(BOARD["display"]["fpc_pins"], 20)
        self.assertIn(("Q1", "G"), nets["GPIO22"])
        self.assertIn(("R21", "1"), nets["V5"])

    def test_lengths_stay_inside_the_budget(self):
        mismatch = abs(path_len(USB_DP) - path_len(USB_DM))
        self.assertLessEqual(mismatch, 1.0)
        self.assertAlmostEqual(mismatch, 1.0)
        for name, points in QSPI.items():
            self.assertLessEqual(path_len(points), 15.0, name)
        self.assertLessEqual(path_len(XIN), 10.0)
        self.assertLessEqual(path_len(XOUT), 10.0)

    def test_keepout_radius_is_half_the_diameter(self):
        self.assertEqual(BOARD["pcb"]["hole_keepout_diameter"], 5.0)
        self.assertEqual(BOARD["pcb"]["mx_rotation_deg"], 0)
        self.assertEqual(keepout_hits(BOARD, BOARD["pcb"]["hole_keepout_diameter"] / 2), [])
        self.assertTrue(keepout_hits(BOARD, 5.0))
        self.assertTrue(circle_hits_rect(12.5, 5, 2.5, (0, 0, 10, 10)))
        self.assertFalse(circle_hits_rect(12.6, 5, 2.5, (0, 0, 10, 10)))
        front_left_x = BOARD["pcb"]["key_x"][0]
        self.assertAlmostEqual(front_left_x - SOCKET_HALF, 12.8)

    def test_placement_matches_board_toml(self):
        by_des = {part.designator: part for part in self.board.parts}
        self.assertEqual(by_des["SW1"].x, BOARD["pcb"]["key_x"][0])
        self.assertEqual(by_des["SW1"].y, BOARD["pcb"]["key_y"][0])
        self.assertEqual(by_des["SW7"].x, BOARD["pcb"]["key_x"][0])
        self.assertEqual(by_des["SW7"].y, BOARD["pcb"]["key_y"][2])
        self.assertEqual((by_des["EN1"].x, by_des["EN1"].y), tuple(BOARD["pcb"]["knob"]))
        self.assertEqual((by_des["J2"].x, by_des["J2"].y), tuple(BOARD["pcb"]["fpc"]))
        self.assertEqual((by_des["SW10"].x, by_des["SW10"].y), tuple(BOARD["pcb"]["boot"]))
        self.assertEqual((by_des["SW11"].x, by_des["SW11"].y), tuple(BOARD["pcb"]["reset"]))
        self.assertEqual(by_des["SW1"].rotation, 0)
        self.assertEqual(FH12_COURTYARD, (15.0, 5.0))
        self.assertEqual(ENCODER_BODY, (12.4, 12.4))


class FabTest(unittest.TestCase):
    def setUp(self):
        self.board = build(BOARD)

    def test_bom_cpl_and_hand_rows(self):
        bom = bom_rows(self.board)
        cpl = cpl_rows(self.board)
        hand = hand_rows(self.board)
        self.assertEqual(list(bom[0]), BOM_HEADER)
        self.assertEqual(list(cpl[0]), CPL_HEADER)
        self.assertEqual(list(hand[0]), HAND_HEADER)
        j2 = next(row for row in cpl if row["Designator"] == "J2")
        boot = next(row for row in cpl if row["Designator"] == "SW10")
        self.assertEqual(j2["Mid Y"], "73.50")
        self.assertEqual(j2["Layer"], "top")
        self.assertEqual(boot["Mid Y"], "8.00")
        self.assertEqual(boot["Layer"], "bottom")
        self.assertTrue(all(row["Layer"] in {"top", "bottom"} for row in cpl))
        placed = {row["Designator"] for row in cpl}
        self.assertNotIn("EN1", placed)
        self.assertNotIn("DS1", placed)
        self.assertEqual({row["Designator"] for row in hand}, {"EN1", "DS1"})
        self.assertTrue(all(row["LCSC Part #"] == "UNVERIFIED" for row in hand))


if __name__ == "__main__":
    unittest.main()
