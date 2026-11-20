# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Tests of the schematic writer's own logic. Plain Python: no KiCad, no symbol libraries.

    python3 -m unittest discover -s pcb/gen -p 'test_*.py'

What KiCad itself checks on the finished sheet (rule check, netlist against the circuit) runs in
`just pcb`. Copied from macropad-greycode pcb/gen (decision D5); the sheet tests draw
fixture_circuit.py, not greycode's circuit.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fixture_circuit
import schematic
import sexpr
import sheet_layout
import symlib

_LIBRARY_TEXT = """
(kicad_symbol_lib (version 20241209)
  (symbol "BASE" (pin_names (offset 1.016)) (in_bom yes)
    (property "Reference" "U" (at -5.08 5.08 0) (effects (font (size 1.27 1.27)) (justify left)))
    (property "Value" "BASE" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "Lib:Base" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (symbol "BASE_0_1" (rectangle (start -5.08 2.54) (end 5.08 -2.54)))
    (symbol "BASE_1_1"
      (pin power_in line (at -7.62 0 0) (length 2.54) (name "VIN" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
      (pin passive line (at -7.62 0 0) (length 2.54) (hide yes) (name "VIN" (effects (font (size 1.27 1.27)))) (number "3" (effects (font (size 1.27 1.27)))))
      (pin power_out line (at 0 -5.08 90) (length 2.54) (name "A \\"quoted\\" name" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))))
  (symbol "CHILD" (extends "BASE")
    (property "Reference" "U" (at -5.08 5.08 0) (effects (font (size 1.27 1.27)) (justify left)))
    (property "Value" "CHILD" (at 0 5.08 0) (effects (font (size 1.27 1.27))))))
"""


def _library() -> dict[str, list]:
    tree = sexpr.parse(_LIBRARY_TEXT)
    return {sexpr.unquoted(symbol[1]): symbol for symbol in sexpr.children(tree, "symbol")}


class SexprTest(unittest.TestCase):
    def test_text_survives_a_round_trip(self) -> None:
        tree = sexpr.parse(_LIBRARY_TEXT)
        self.assertEqual(sexpr.parse(sexpr.dump(tree)), tree)

    def test_a_quote_inside_a_string_does_not_end_it(self) -> None:
        pin = sexpr.children(sexpr.children(_library()["BASE"], "symbol")[1], "pin")[2]
        self.assertEqual(sexpr.unquoted(sexpr.child(pin, "name")[1]), 'A "quoted" name')
        self.assertEqual(sexpr.unquoted(sexpr.quoted('a "b" \\ c')), 'a "b" \\ c')

    def test_unbalanced_text_is_refused(self) -> None:
        for text in ("(a (b)", "(a))", "(a) (b)"):
            with self.assertRaises(AssertionError):
                sexpr.parse(text)


class SymbolLibraryTest(unittest.TestCase):
    def test_a_derived_symbol_gets_its_parents_pins_under_its_own_name(self) -> None:
        flat = symlib.flatten(_library(), "CHILD")
        self.assertIsNone(sexpr.child(flat, "extends"))
        self.assertEqual([sexpr.unquoted(unit[1]) for unit in sexpr.children(flat, "symbol")], ["CHILD_0_1", "CHILD_1_1"])
        values = {sexpr.unquoted(p[1]): sexpr.unquoted(p[2]) for p in sexpr.children(flat, "property")}
        self.assertEqual(values, {"Reference": "U", "Value": "CHILD", "Footprint": "Lib:Base"})

    def test_pins_are_read_on_the_grid_with_their_type(self) -> None:
        pins = {pin.number: pin for pin in symlib._pins(symlib.flatten(_library(), "CHILD"))}
        self.assertEqual((pins["1"].x, pins["1"].y, pins["1"].kind, pins["1"].hidden), (-6, 0, "power_in", False))
        self.assertTrue(pins["3"].hidden)
        self.assertEqual((pins["2"].x, pins["2"].y, pins["2"].angle), (0, -4, 90))

    def test_off_grid_position_is_refused(self) -> None:
        with self.assertRaises(AssertionError):
            symlib.to_grid(1.0)

    def test_pin_position_and_direction_follow_the_rotation(self) -> None:
        left = symlib.LibPin("1", "A", "passive", x=-6, y=0, angle=0, hidden=False)
        # Symbol Y points up, sheet Y points down; a quarter turn is counter-clockwise as seen on the sheet.
        self.assertEqual([left.at(r) for r in symlib.ROTATIONS], [(-6, 0), (0, 6), (6, 0), (0, -6)])
        self.assertEqual([left.outward(r) for r in symlib.ROTATIONS], [(-1, 0), (0, 1), (1, 0), (0, -1)])
        top = symlib.LibPin("2", "B", "passive", x=0, y=3, angle=270, hidden=False)
        self.assertEqual(top.at(0), (0, -3))
        self.assertEqual(top.outward(0), (0, -1))
        self.assertEqual(top.at(90), (-3, 0))  # pin 1 of a resistor turned 90 is on the left

    def test_box_symbol_puts_each_pin_outside_its_side(self) -> None:
        box = symlib.box_symbol("macropad:Box", "box", (4, 3), (
            symlib.BoxPin("1", "IN", "input", "left", 0), symlib.BoxPin("2", "OUT", "output", "right", 2),
            symlib.BoxPin("3", "V", "power_in", "top", 0), symlib.BoxPin("4", "G", "power_in", "bottom", -1)))
        at = {pin.number: (pin.at(0), pin.outward(0)) for pin in box.pins}
        self.assertEqual(at, {"1": ((-6, 0), (-1, 0)), "2": ((6, 2), (1, 0)),
                              "3": ((0, -5), (0, -1)), "4": ((-1, 5), (0, 1))})
        self.assertIn('(symbol "macropad:Box"', box.embedded())
        self.assertIn('(symbol "Box"', box.embedded("Box"))


class WireTest(unittest.TestCase):
    def test_a_wire_is_cut_where_another_ends_on_it(self) -> None:
        through, branch = ((0, 0), (10, 0)), ((4, 0), (4, 5))
        pieces = schematic.split_segments([through, branch], {(0, 0), (10, 0), (4, 0), (4, 5)})
        self.assertEqual(pieces, [((0, 0), (4, 0)), ((4, 0), (10, 0)), ((4, 0), (4, 5))])
        self.assertEqual(schematic.junctions(pieces, []), [(4, 0)])

    def test_cuts_keep_the_direction_of_a_wire_drawn_backwards(self) -> None:
        pieces = schematic.split_segments([((10, 0), (0, 0))], {(3, 0), (7, 0)})
        self.assertEqual(pieces, [((10, 0), (7, 0)), ((7, 0), (3, 0)), ((3, 0), (0, 0))])

    def test_crossing_wires_stay_apart(self) -> None:
        crossing = [((0, 2), (10, 2)), ((5, 0), (5, 5))]
        ends = {end for wire in crossing for end in wire}
        self.assertEqual(schematic.split_segments(crossing, ends), crossing)
        self.assertEqual(schematic.junctions(crossing, []), [])

    def test_a_pin_on_a_corner_needs_no_dot_but_a_pin_on_a_run_does(self) -> None:
        corner = [((0, 0), (4, 0)), ((4, 0), (4, 4))]
        self.assertEqual(schematic.junctions(corner, [(0, 0)]), [])
        self.assertEqual(schematic.junctions(corner, [(4, 0)]), [(4, 0)])

    def test_two_nets_may_not_meet(self) -> None:
        drawing = schematic.Drawing()
        drawing.wire("A", (0, 0), (4, 0))
        with self.assertRaises(AssertionError):
            drawing.wire("B", (4, 0), (4, 4))

    def test_a_slanted_wire_is_refused(self) -> None:
        with self.assertRaises(AssertionError):
            schematic.Drawing().wire("A", (0, 0), (3, 4))



    def test_an_own_symbol_is_found_by_its_lib_id_and_added_once(self) -> None:
        library = symlib.SymbolLibrary(Path("/nonexistent"))
        library.add(fixture_circuit.JACK)
        self.assertIs(library.get("macropad-obs:FIXTURE_JACK"), fixture_circuit.JACK)
        with self.assertRaises(AssertionError):
            library.add(fixture_circuit.JACK)


class NetNameTest(unittest.TestCase):
    def test_board_names_follow_kicad(self) -> None:
        self.assertEqual(schematic.board_net_name("GND"), "GND")
        self.assertEqual(schematic.board_net_name("KEY3"), "/KEY3")
        for net in ("+3V3", "USB_D_P"):
            self.assertEqual(schematic.circuit_net_name(schematic.board_net_name(net)), net)
        self.assertEqual(schematic.circuit_net_name("unconnected-(U1-GPIO10-Pad14)"), schematic.NO_NET)

    def test_every_supply_net_keeps_its_name_on_the_board(self) -> None:
        for net in schematic.SUPPLY_NETS:
            self.assertEqual(schematic.board_net_name(net), net)


class PartCheckTest(unittest.TestCase):
    def _part(self, footprint: str, nets: dict[str, str]) -> fixture_circuit.Part:
        return fixture_circuit.Part("U9", "BASE", footprint, "", "Lib:BASE", nets)

    def test_a_part_uses_the_symbols_footprint_or_a_paste_copy_of_it(self) -> None:
        symbol = symlib.LibSymbol("Lib:BASE", symlib._freeze(_library()["BASE"]), ())
        schematic.check_part_against_symbol(self._part("Lib:Base", {}), symbol, {})
        schematic.check_part_against_symbol(self._part("mine:Base", {}), symbol, {"mine:Base": "Lib:Base"})
        with self.assertRaises(AssertionError):
            schematic.check_part_against_symbol(self._part("mine:Base", {}), symbol, {})

    def test_a_part_may_not_name_a_pin_the_symbol_lacks(self) -> None:
        flat = symlib.flatten(_library(), "BASE")
        symbol = symlib.LibSymbol("Lib:BASE", symlib._freeze(flat), symlib._pins(flat))
        schematic.check_part_against_symbol(self._part("Lib:Base", {"1": "A", "2": "B"}), symbol, {})
        with self.assertRaises(AssertionError):
            schematic.check_part_against_symbol(self._part("Lib:Base", {"9": "A"}), symbol, {})


class FixtureLayoutTest(unittest.TestCase):
    def test_every_part_is_drawn_once(self) -> None:
        drawn = sorted(place.ref for block in fixture_circuit.BLOCKS for place in block.places)
        self.assertEqual(drawn, sorted(part.ref for part in fixture_circuit.PARTS))

    def test_blocks_stay_on_the_sheet_and_apart(self) -> None:
        blocks = fixture_circuit.BLOCKS
        for block in blocks:
            self.assertLessEqual(block.x + block.width, sheet_layout.SHEET_WIDTH, block.title)
            self.assertLessEqual(block.y + block.height, sheet_layout.SHEET_HEIGHT, block.title)
        for index, first in enumerate(blocks):
            for second in blocks[index + 1:]:
                apart = (first.x + first.width <= second.x or second.x + second.width <= first.x
                         or first.y + first.height <= second.y or second.y + second.height <= first.y)
                self.assertTrue(apart, f"{first.title} overlaps {second.title}")

    def test_drawn_wires_name_pins_of_their_own_net(self) -> None:
        net_of = schematic.nets_by_pin(fixture_circuit.PARTS)
        for block in fixture_circuit.BLOCKS:
            for wire in block.wires:
                for point in wire.points:
                    if isinstance(point, str):
                        self.assertEqual(net_of[point], wire.net, f"{block.title}: {point}")

    def test_open_pins_have_no_net(self) -> None:
        self.assertNotIn("J1.4", schematic.nets_by_pin(fixture_circuit.PARTS))


class SheetTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        for name, text in fixture_circuit.LIBRARY_FILES.items():
            (self.folder / name).write_text(text)

    def _library(self) -> symlib.SymbolLibrary:
        library = symlib.SymbolLibrary(self.folder)
        library.add(fixture_circuit.JACK)
        return library

    def _render(self, sheet: schematic.Sheet = fixture_circuit.SHEET) -> str:
        return schematic.render(schematic.draw_sheet(sheet, self._library()))

    def _items(self, head: str) -> list[list]:
        return sexpr.children(sexpr.parse(self._render()), head)

    def test_the_sheet_is_one_s_expression_and_byte_repeatable(self) -> None:
        text = self._render()
        self.assertEqual(sexpr.parse(text)[0], "kicad_sch")
        self.assertEqual(text, self._render())

    def test_each_part_and_each_supply_symbol_is_placed(self) -> None:
        refs = sorted(sexpr.unquoted(prop[2]) for symbol in self._items("symbol")
                      for prop in sexpr.children(symbol, "property") if sexpr.unquoted(prop[1]) == "Reference")
        # Supplies by rule: J1.2, C1.2, R1.2 to GND. The flag on the VBUS wire.
        self.assertEqual(refs, ["#FLG001", "#PWR002", "#PWR003", "#PWR004", "C1", "J1", "R1"])
        embedded = [sexpr.unquoted(symbol[1]) for symbol in sexpr.child(sexpr.parse(self._render()), "lib_symbols")[1:]]
        self.assertEqual(embedded, ["Device:C", "Device:R", "macropad-obs:FIXTURE_JACK", "power:GND", "power:PWR_FLAG"])

    def test_signal_pins_get_labels_and_the_open_pin_a_mark(self) -> None:
        labels = sorted(sexpr.unquoted(label[1]) for label in self._items("label"))
        self.assertEqual(labels, ["SENSE", "SENSE"])
        self.assertEqual(len(self._items("no_connect")), 1)

    def test_the_power_flag_on_a_wire_gets_a_dot(self) -> None:
        dots = [junction[1][1:3] for junction in self._items("junction")]
        self.assertEqual(dots, [["43.18", "30.48"]])  # block (6, 10) + flag (28, 14), in mm

    def test_a_part_outside_every_block_is_refused(self) -> None:
        lone = fixture_circuit.Part("R9", "1k", "Resistor_SMD:R_0402_1005Metric", "UNVERIFIED", "Device:R")
        sheet = schematic.Sheet(fixture_circuit.PARTS + (lone,), fixture_circuit.BLOCKS, (fixture_circuit.JACK,))
        with self.assertRaises(AssertionError):
            self._render(sheet)

    def test_a_block_off_the_paper_is_refused(self) -> None:
        wide = sheet_layout.Block("Wide", 300, 10, 40, 30, places=fixture_circuit.BLOCKS[1].places)
        sheet = schematic.Sheet(fixture_circuit.PARTS, (fixture_circuit.BLOCKS[0], wide), (fixture_circuit.JACK,))
        with self.assertRaises(AssertionError):
            self._render(sheet)

    def test_write_names_the_project_libraries(self) -> None:
        out = self.folder / "kicad"
        out.mkdir()
        schematic.write(out, fixture_circuit.SHEET, self.folder)
        self.assertEqual(sorted(path.name for path in out.iterdir()),
                         ["fp-lib-table", "macropad-obs.kicad_sch", "macropad-obs.kicad_sym", "sym-lib-table"])
        table = (out / "sym-lib-table").read_text()
        for name in ("macropad-obs", "Device", "power"):
            self.assertIn(f'(name "{name}")', table)
        self.assertIn('(symbol "FIXTURE_JACK"', (out / "macropad-obs.kicad_sym").read_text())
        self.assertIn("macropad-obs.pretty", (out / "fp-lib-table").read_text())

    def test_the_footprint_table_names_each_stock_library_of_the_sheet(self) -> None:
        """DRC compares each board footprint with its library; a library missing from the table is a finding."""
        out = self.folder / "kicad"
        out.mkdir()
        schematic.write(out, fixture_circuit.SHEET, self.folder)
        table = (out / "fp-lib-table").read_text()
        for name in ("Capacitor_SMD", "Resistor_SMD"):
            self.assertIn(f'(lib (name "{name}")(type "KiCad")(uri "${{KICAD9_FOOTPRINT_DIR}}/{name}.pretty")', table)


if __name__ == "__main__":
    unittest.main()
