#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""check_pins passes the spec pin table, fails one vector per rule, and binds the two sources."""

import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_pins

ROOT = Path(__file__).resolve().parent.parent
VECTORS = Path(__file__).resolve().parent / "pin_vectors"
# Each fail vector breaks one rule, so it must give exactly this one message.
FAIL_VECTORS = {
    "fail_duplicate_gpio.toml": "IO13 carries LCD_CS_STRIP and LCD_DC",
    "fail_net_on_open_strapping_pin.toml": "IO3 is a strapping pin and must stay open, not carry STRIP_TE",
    "fail_io0_not_boot.toml": "IO0 is a strapping pin for BOOT only, not STRIP_TE",
    "fail_strapping_allow_list.toml": "[strapping] must be",
}


def vector(name):
    return tomllib.loads((VECTORS / name).read_text(encoding="utf-8"))


def spec_table_with(net, pin):
    """The pass vector with one net moved to another pad."""
    board = vector("pass_spec_table.toml")
    board["gpio"][net] = pin
    return board


def real_sources():
    """board.toml, pins.h and protocol.rs as they are in the tree."""
    board = tomllib.loads((ROOT / "board.toml").read_text(encoding="utf-8"))
    pins_h = (ROOT / check_pins.PINS_H).read_text(encoding="utf-8")
    protocol_rs = (ROOT / check_pins.PROTOCOL_RS).read_text(encoding="utf-8")
    return board, pins_h, protocol_rs


class PinRuleTest(unittest.TestCase):
    def test_spec_table_passes(self):
        self.assertEqual(check_pins.pin_errors(vector("pass_spec_table.toml")), [])

    def test_spec_table_uses_30_pads(self):
        self.assertEqual(len(set(vector("pass_spec_table.toml")["gpio"].values())), 30)

    def test_each_fail_vector_breaks_exactly_its_rule(self):
        for name, message in FAIL_VECTORS.items():
            with self.subTest(vector=name):
                errors = check_pins.pin_errors(vector(name))
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(message, errors[0])

    def test_every_vector_file_is_run(self):
        on_disk = {path.name for path in VECTORS.glob("*.toml")}
        self.assertEqual(on_disk, {"pass_spec_table.toml", *FAIL_VECTORS})

    def test_a_net_on_each_open_strapping_pin_fails(self):
        for pin in (3, 45, 46):
            with self.subTest(pin=pin):
                errors = check_pins.pin_errors(spec_table_with("STRIP_TE", pin))
                self.assertEqual(errors, [f"IO{pin} is a strapping pin and must stay open, not carry STRIP_TE"])

    def test_board_toml_carries_the_spec_table(self):
        board, _, _ = real_sources()
        spec = vector("pass_spec_table.toml")
        self.assertEqual(board["gpio"], spec["gpio"])
        self.assertEqual(board["strapping"], spec["strapping"])


class BindingTest(unittest.TestCase):
    def test_tree_sources_match_board_toml(self):
        self.assertEqual(check_pins.binding_errors(*real_sources()), [])

    def test_pins_h_names_every_net_and_the_usb_ids(self):
        pins_h = check_pins.render_pins_h(real_sources()[0])
        for line in ("#define PIN_BOOT 0", "#define PIN_BL_STRIP 48", "#define USB_VID 0x1209", "#define USB_PID 0x4F42"):
            self.assertIn(line + "\n", pins_h)

    def test_a_hand_edited_pins_h_fails(self):
        board, pins_h, protocol_rs = real_sources()
        edited = pins_h.replace("#define PIN_ROW0 4\n", "#define PIN_ROW0 5\n")
        self.assertNotEqual(edited, pins_h)
        errors = check_pins.binding_errors(board, edited, protocol_rs)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(check_pins.PINS_H, errors[0])

    def test_a_usb_id_that_differs_in_protocol_rs_fails(self):
        board, pins_h, protocol_rs = real_sources()
        edited = protocol_rs.replace("USB_PID: u16 = 0x4F42", "USB_PID: u16 = 0x4F43")
        self.assertNotEqual(edited, protocol_rs)
        errors = check_pins.binding_errors(board, pins_h, edited)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("protocol.rs USB", errors[0])


if __name__ == "__main__":
    unittest.main()
