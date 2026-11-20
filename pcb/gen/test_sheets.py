# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Tests of the board's schematic layout (sheets.py). Plain Python: no KiCad, no symbol libraries.

KiCad's rule check and the netlist comparison on the drawn sheet run in `just pcb erc`.
"""

from __future__ import annotations

import unittest

import circuit_hmi
import schematic
import sheet_layout
import sheets


class BoardSheetTest(unittest.TestCase):
    def test_the_sheet_draws_the_whole_circuit(self) -> None:
        self.assertEqual(sheets.SHEET.parts, circuit_hmi.BOARD_PARTS)

    def test_every_part_is_drawn_once(self) -> None:
        drawn = sorted(place.ref for block in sheets.BLOCKS for place in block.places)
        self.assertEqual(drawn, sorted(part.ref for part in circuit_hmi.BOARD_PARTS))

    def test_blocks_stay_on_the_sheet_and_apart(self) -> None:
        for block in sheets.BLOCKS:
            self.assertLessEqual(block.x + block.width, sheet_layout.SHEET_WIDTH, block.title)
            self.assertLessEqual(block.y + block.height, sheet_layout.SHEET_HEIGHT, block.title)
        for index, first in enumerate(sheets.BLOCKS):
            for second in sheets.BLOCKS[index + 1:]:
                apart = (first.x + first.width <= second.x or second.x + second.width <= first.x
                         or first.y + first.height <= second.y or second.y + second.height <= first.y)
                self.assertTrue(apart, f"{first.title} overlaps {second.title}")

    def test_drawn_wires_name_pins_of_their_own_net(self) -> None:
        net_of = schematic.nets_by_pin(circuit_hmi.BOARD_PARTS)
        for block in sheets.BLOCKS:
            for wire in block.wires:
                for point in wire.points:
                    if isinstance(point, str):
                        self.assertEqual(net_of[point], wire.net, f"{block.title}: {point}")

    def test_every_supply_net_carries_a_power_flag(self) -> None:
        """The supplies enter through passive parts (J1, F1, L1), so ERC needs a flag on each."""
        flagged = set()
        for block in sheets.BLOCKS:
            at = {point: wire.net for wire in block.wires for point in wire.points if not isinstance(point, str)}
            flagged |= {at[flag.point] for flag in block.flags}
        self.assertEqual(flagged, set(schematic.SUPPLY_NETS))

    def test_tail_supply_pins_reach_their_bus(self) -> None:
        big = next(part for part in circuit_hmi.BOARD_PARTS if part.ref == "J3")
        bussed = {point for block in sheets.BLOCKS for wire in block.wires for point in wire.points
                  if isinstance(point, str) and point.startswith("J3.")}
        wanted = {f"J3.{pin}" for pin, net in big.nets.items() if net in ("GND", "+3V3", "+5V") and pin != "MP"}
        self.assertEqual(bussed, wanted)


if __name__ == "__main__":
    unittest.main()
