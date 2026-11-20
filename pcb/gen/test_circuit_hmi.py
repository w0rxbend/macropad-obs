# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The HMI netlist against board.toml [gpio], report 08 and the panel pin tables. Plain Python, no KiCad.

    python3 -B -m unittest discover -s pcb/gen -p 'test_*.py'
"""

from __future__ import annotations

import tomllib
import unittest
from dataclasses import replace
from pathlib import Path

import circuit_hmi as hmi
import circuit_power as power

BOARD = tomllib.loads((Path(__file__).resolve().parents[2] / "board.toml").read_text())
PARTS = {part.ref: part for part in hmi.PARTS}


def parts_between(net_1: str, net_2: str) -> list[power.Part]:
    return [p for p in hmi.PARTS if set(p.nets.values()) == {net_1, net_2}]


class SelfCheckTest(unittest.TestCase):
    def test_both_sheets_together_leave_no_open_pin_and_no_single_pad_net(self) -> None:
        self.assertEqual(power.problems(hmi.BOARD_PARTS, frozenset()), [])

    def test_a_dropped_hmi_pad_is_found(self) -> None:
        strip = PARTS["J4"]
        broken = replace(strip, nets={pin: net for pin, net in strip.nets.items() if pin != "6"})
        parts = power.PARTS + tuple(broken if p.ref == "J4" else p for p in hmi.PARTS)
        found = power.problems(parts, frozenset())
        self.assertIn("J4.6 is open", found)
        self.assertIn("net STRIP_TE has one pad: U1.35", found)


class GpioTest(unittest.TestCase):
    def test_the_hmi_sheet_finishes_every_net_the_power_sheet_left_open(self) -> None:
        here = set(power.nets_to_pads(hmi.PARTS))
        self.assertEqual(power.HMI_NETS - here, set())

    def test_the_gpio_nets_on_this_sheet_are_exactly_the_ones_left_open(self) -> None:
        used = set(power.nets_to_pads(hmi.PARTS))
        self.assertEqual(used & set(BOARD["gpio"]), power.HMI_NETS - {power.LEDK_BIG, power.LEDK_STRIP})


class MatrixTest(unittest.TestCase):
    """Report 08 section 4 and firmware/core/input.h: contact to COLc, diode anode to the contact,
    cathode to ROWr. Keys 0-8 row by row, knob pushes in COL3, buttons on ROW3."""

    EXPECTED = {
        (row, col): (f"SW{3 * row + col + 1}", "MX") for row in range(3) for col in range(3)
    } | {(row, 3): (f"SW{14 + row}", "EC11E18244AU") for row in range(3)} | {
        (3, col): (f"SW{10 + col}", "B3F-1060") for col in range(4)}

    def test_each_contact_sits_between_its_column_and_its_own_diode_to_its_row(self) -> None:
        for (row, col), (ref, kind) in self.EXPECTED.items():
            contact = PARTS[ref]
            self.assertIn(kind, contact.value, ref)
            pins = ("S1", "S2") if kind == "EC11E18244AU" else ("1", "2")
            self.assertEqual(contact.nets[pins[0]], f"COL{col}", ref)
            junction = contact.nets[pins[1]]
            diode = PARTS[f"D{4 * row + col + 1}"]
            self.assertEqual(diode.nets, {"1": f"ROW{row}", "2": junction}, ref)  # D_Schottky: 1 K, 2 A
            self.assertEqual(sorted(power.nets_to_pads(hmi.BOARD_PARTS)[junction]),
                             sorted([f"{ref}.{pins[1]}", f"{diode.ref}.2"]))

    def test_sixteen_bat54_in_sod123(self) -> None:
        diodes = [p for p in hmi.PARTS if p.ref.startswith("D")]
        self.assertEqual(len(diodes), 16)
        self.assertEqual({(p.value, p.symbol, p.footprint) for p in diodes},
                         {("BAT54", "Device:D_Schottky", "Diode_SMD:D_SOD-123")})

    def test_columns_have_4k7_pull_ups_and_no_line_has_a_pull_down(self) -> None:
        for col in range(4):
            self.assertEqual([p.value for p in parts_between(f"COL{col}", power.V3)], ["4.7k"])
        for line in [f"ROW{n}" for n in range(4)] + [f"COL{n}" for n in range(4)]:
            self.assertEqual(parts_between(line, power.GND), [], line)

    def test_part_counts(self) -> None:
        values = [p.value for p in hmi.PARTS]
        self.assertEqual(sum("CPG151101S11" in v for v in values), 9)
        self.assertEqual(values.count("B3F-1060"), 4)
        self.assertEqual(values.count("EC11E18244AU"), 3)


class EncoderTest(unittest.TestCase):
    def test_each_phase_has_a_3k3_pull_up_10k_in_series_and_10nf_at_the_pin(self) -> None:
        for number in (1, 2, 3):
            encoder = PARTS[f"SW{13 + number}"]
            self.assertEqual({encoder.nets[pin] for pin in ("C", "MP")}, {power.GND})
            for phase in ("A", "B"):
                gpio = f"ENC{number}_{phase}"
                raw = encoder.nets[phase]
                self.assertNotIn(raw, BOARD["gpio"])
                self.assertEqual([p.value for p in parts_between(raw, power.V3)], ["3.3k"], gpio)
                self.assertEqual([p.value for p in parts_between(raw, gpio)], ["10k"], gpio)
                self.assertEqual([p.value for p in parts_between(gpio, power.GND)], ["10nF"], gpio)


class PanelTest(unittest.TestCase):
    def test_big_panel_40_pin_tail(self) -> None:
        nets = PARTS["J3"].nets
        self.assertEqual([nets[str(p)] for p in (1, 2, 6, 29, 31, 32, 33)],
                         [power.LEDK_BIG, power.V5, "LCD_RESET", "LCD_MOSI", "LCD_SCK", "LCD_DC", "LCD_CS_BIG"])
        self.assertEqual({nets[str(p)] for p in (3, 4, 5, 30, 34, 35)}, {power.V3})  # IM0-2, RD, IOVCC, VCI
        self.assertEqual({nets[str(p)] for p in [*range(7, 29), 36]}, {power.GND})   # NC 7-10, DB17-DB0, GND
        self.assertEqual(PARTS["J3"].no_connect, {"37", "38", "39", "40"})

    def test_strip_10_pin_tail(self) -> None:
        nets = PARTS["J4"].nets
        self.assertEqual([nets[str(p)] for p in range(1, 11)],
                         ["LCD_MOSI", "LCD_SCK", "LCD_DC", "LCD_RESET", "LCD_CS_STRIP", "STRIP_TE", power.V3,
                          power.LEDK_STRIP, power.V5, power.GND])

    def test_connectors_are_the_fh12_placeholders_until_task_5_3b(self) -> None:
        self.assertEqual(PARTS["J3"].footprint, "macropad-obs:PLACEHOLDER_FPC_FH12-40S")
        self.assertEqual(PARTS["J4"].footprint, "macropad-obs:PLACEHOLDER_FPC_FH12-10S")


class SourcingTest(unittest.TestCase):
    def test_lcsc_cells_stay_unverified_and_no_part_is_sk6812(self) -> None:
        self.assertEqual(power.forbidden_lcsc(hmi.PARTS), [])
        named = " ".join(f"{p.value} {p.footprint} {p.symbol} {' '.join(p.manufacturer_part)}" for p in hmi.PARTS)
        self.assertNotIn("SK6812", named.upper())

    def test_through_hole_parts_on_the_top_face_are_hand_soldered(self) -> None:
        hand = {p.ref for p in hmi.PARTS if not p.machine_assembled}
        self.assertEqual(hand, {f"SW{n}" for n in range(10, 17)})


if __name__ == "__main__":
    unittest.main()
