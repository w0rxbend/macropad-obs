# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The netlist against board.toml and the datasheet rules. Plain Python, no KiCad.

    python3 -B -m unittest discover -s pcb/gen -p 'test_*.py'

The rules carried over from the retired RP2040 test (`git show d3f75a2:pcb/gen/test_circuit.py`):
LCSC cells stay UNVERIFIED and nothing names SK6812, the power chain from the USB-C VBUS pads to
the 3.3 V rail, the CC resistors to ground, the BOOT and RESET buttons, and the decoupling counts.
Its length, keep-out and placement rules belong to placement and routing (tasks 5.6 and 5.8).
"""

from __future__ import annotations

import tomllib
import unittest
from dataclasses import replace
from pathlib import Path

import circuit_power as power

BOARD = tomllib.loads((Path(__file__).resolve().parents[2] / "board.toml").read_text())
PARTS = {part.ref: part for part in power.PARTS}


def ohms(value: str) -> float:
    """'5.1k' -> 5100.0, '22R' -> 22.0, '6.2R' -> 6.2."""
    scale = {"R": 1.0, "k": 1e3, "M": 1e6}[value[-1]]
    return float(value[:-1]) * scale


def nets_of(ref: str) -> set[str]:
    return set(PARTS[ref].nets.values())


def pads_on(net: str) -> set[str]:
    return set(power.nets_to_pads(power.PARTS).get(net, ()))


class SelfCheckTest(unittest.TestCase):
    def test_no_open_pin_and_every_power_pin_on_its_rail(self) -> None:
        self.assertEqual(power.problems(power.PARTS, power.HMI_NETS), [])

    def test_an_open_pin_is_found(self) -> None:
        buck = PARTS["U2"]
        broken = replace(buck, nets={pin: net for pin, net in buck.nets.items() if pin != "5"})
        found = power.problems(_swap(broken), power.HMI_NETS)
        self.assertIn("U2.5 is open", found)

    def test_a_power_pin_off_its_rail_is_found(self) -> None:
        module = PARTS["U1"]
        broken = replace(module, nets={**module.nets, "2": power.V5})
        found = power.problems(_swap(broken), power.HMI_NETS)
        self.assertIn("U1.2 is a +3V3 pin on +5V", found)

    def test_a_pin_the_part_lacks_and_a_wired_no_connect_are_found(self) -> None:
        module = PARTS["U1"]
        broken = replace(module, nets={**module.nets, "42": power.GND, "15": power.GND})
        found = power.problems(_swap(broken), power.HMI_NETS)
        self.assertIn("U1.42 is not a pin of ESP32-S3-WROOM-1-N16R2", found)
        self.assertIn("U1.15 is marked no-connect but is on GND", found)

    def test_a_single_pad_net_is_found_unless_the_hmi_sheet_finishes_it(self) -> None:
        stray = replace(PARTS["R13"], ref="R99", nets={"1": "STRAY", "2": power.GND})
        self.assertIn("net STRAY has one pad: R99.1", power.problems(power.PARTS + (stray,), power.HMI_NETS))
        self.assertIn("net ROW0 has one pad: U1.4", power.problems(power.PARTS, frozenset()))

    def test_a_repeated_reference_is_found(self) -> None:
        found = power.problems(power.PARTS + (PARTS["R1"],), power.HMI_NETS)
        self.assertIn("reference R1 is used twice", found)


def _swap(changed: power.Part) -> tuple[power.Part, ...]:
    return tuple(changed if part.ref == changed.ref else part for part in power.PARTS)


class SourcingTest(unittest.TestCase):
    def test_lcsc_cells_stay_unverified_and_no_part_is_sk6812(self) -> None:
        self.assertEqual(power.forbidden_lcsc(power.PARTS), [])
        self.assertTrue(all(part.lcsc == "UNVERIFIED" for part in power.PARTS))
        named = " ".join(f"{p.value} {p.footprint} {p.symbol} {' '.join(p.manufacturer_part)}" for p in power.PARTS)
        self.assertNotIn("SK6812", named.upper())

    def test_forbidden_lcsc_lists_a_numbered_cell(self) -> None:
        numbered = replace(PARTS["R1"], lcsc="C25905")
        self.assertEqual(power.forbidden_lcsc((numbered,)), ["R1"])

    def test_the_named_parts_are_the_spec_parts(self) -> None:
        values = {ref: PARTS[ref].value for ref in ("U1", "U2", "U3", "U4", "U5", "J1", "J2")}
        self.assertEqual(values, {"U1": "ESP32-S3-WROOM-1-N16R2", "U2": "TLV62569DBV", "U3": "USBLC6-2SC6",
                                  "U4": "BCR421UW6", "U5": "BCR421UW6", "J1": "USB4216-03-A",
                                  "J2": "SM03B-SRSS-TB"})
        self.assertEqual(BOARD["mcu"]["part"], PARTS["U1"].value)


class PowerChainTest(unittest.TestCase):
    def test_vbus_runs_through_the_fuse_to_the_buck(self) -> None:
        jack = PARTS["J1"]
        self.assertEqual({jack.nets[pad] for pad in ("A4", "A9", "B4", "B9")}, {power.VBUS})
        self.assertEqual({jack.nets[pad] for pad in ("A1", "A12", "B1", "B12", "S1")}, {power.GND})
        self.assertEqual(PARTS["F1"].nets, {"1": power.VBUS, "2": power.V5})
        self.assertEqual(pads_on(power.VBUS) - {"J1.A4", "J1.A9", "J1.B4", "J1.B9"}, {"F1.1", "U3.5"})
        buck = PARTS["U2"]
        self.assertEqual((buck.nets["4"], buck.nets["1"], buck.nets["2"]), (power.V5, power.V5, power.GND))
        self.assertEqual(PARTS["L1"].nets, {"1": buck.nets["3"], "2": power.V3})

    def test_the_divider_sets_3v3(self) -> None:
        feedback = PARTS["U2"].nets["5"]
        top = next(p for p in power.PARTS if set(p.nets.values()) == {power.V3, feedback})
        bottom = next(p for p in power.PARTS if set(p.nets.values()) == {feedback, power.GND})
        volts = 0.6 * (1 + ohms(top.value) / ohms(bottom.value))  # TLV62569 equation 2, VFB 0.6 V
        self.assertAlmostEqual(volts, 3.3, delta=0.033)
        self.assertLessEqual(ohms(bottom.value), 200e3)  # TLV62569 8.2.2.2: R2 at most 200 k

    def test_capacitors_at_the_buck_and_the_module(self) -> None:
        caps = [(p.value, frozenset(p.nets.values())) for p in power.PARTS if p.symbol == "Device:C"]
        self.assertIn(("4.7uF", frozenset({power.V5, power.GND})), caps)
        on_3v3 = sorted(value for value, nets in caps if nets == {power.V3, power.GND})
        self.assertEqual(on_3v3, ["100nF", "10uF", "22uF"])
        self.assertEqual(sum(1 for value, _ in caps if value == "1uF"), 1)

    def test_every_module_supply_pad_is_tied(self) -> None:
        module = PARTS["U1"]
        self.assertEqual(module.nets["2"], power.V3)
        self.assertEqual({module.nets[pad] for pad in ("1", "40", "41")}, {power.GND})


class UsbTest(unittest.TestCase):
    def test_each_cc_pad_has_its_own_5k1_to_ground_and_a_100k_sense(self) -> None:
        jack = PARTS["J1"]
        cc_nets = (jack.nets["A5"], jack.nets["B5"])
        self.assertNotEqual(*cc_nets)
        for cc_net, gpio_net in zip(cc_nets, ("CC1", "CC2")):
            pull = [p for p in power.PARTS if set(p.nets.values()) == {cc_net, power.GND}]
            self.assertEqual([p.value for p in pull], ["5.1k"], cc_net)
            sense = [p for p in power.PARTS if set(p.nets.values()) == {cc_net, gpio_net}]
            self.assertEqual([p.value for p in sense], ["100k"], cc_net)

    def test_data_pairs_join_at_the_jack_pass_the_esd_part_and_22r_to_the_module(self) -> None:
        jack, esd, module = PARTS["J1"], PARTS["U3"], PARTS["U1"]
        plus, minus = jack.nets["A6"], jack.nets["A7"]
        self.assertEqual((jack.nets["B6"], jack.nets["B7"]), (plus, minus))
        self.assertEqual((esd.nets["3"], esd.nets["4"], esd.nets["1"], esd.nets["6"]), (plus, plus, minus, minus))
        self.assertEqual((esd.nets["2"], esd.nets["5"]), (power.GND, power.VBUS))
        for jack_net, gpio_net, module_pad in ((plus, "USB_DP", "14"), (minus, "USB_DM", "13")):
            series = [p for p in power.PARTS if set(p.nets.values()) == {jack_net, gpio_net}]
            self.assertEqual([p.value for p in series], ["22R"])
            self.assertEqual(module.nets[module_pad], gpio_net)
        self.assertEqual({"A8", "B8"}, set(jack.no_connect))


class McuTest(unittest.TestCase):
    def test_every_gpio_net_is_on_its_board_toml_pad(self) -> None:
        module = PARTS["U1"]
        for net, io in BOARD["gpio"].items():
            self.assertEqual(module.nets[str(power.WROOM_IO_PIN[io])], net, f"IO{io}")

    def test_strapping_pins_and_spares_stay_open(self) -> None:
        module = PARTS["U1"]
        open_io = {int(name[2:]) for name, net in BOARD["strapping"].items() if net == ""} | {35, 36, 37}
        self.assertEqual(module.no_connect, {str(power.WROOM_IO_PIN[io]) for io in open_io})
        self.assertEqual(module.nets[str(power.WROOM_IO_PIN[0])], BOARD["strapping"]["IO0"])

    def test_the_pin_table_has_36_gpio_and_41_pads(self) -> None:
        self.assertEqual(len(power.WROOM_IO_PIN), 36)
        pads = set(power.WROOM_IO_PIN.values()) | {1, 2, 3, 40, 41}
        self.assertEqual(pads, set(range(1, 42)))

    def test_boot_and_reset(self) -> None:
        self.assertEqual(PARTS["SW20"].nets, {"1": "BOOT", "2": power.GND})
        self.assertEqual(PARTS["SW21"].nets, {"1": "EN", "2": power.GND})
        self.assertEqual(PARTS["U1"].nets["3"], "EN")
        on_boot = sorted((p.symbol, p.value) for p in power.PARTS if "BOOT" in p.nets.values() and p.ref != "U1")
        self.assertEqual(on_boot, [("Device:R", "10k"), ("Switch:SW_Push", "TS-1187A")])  # no capacitor on IO0
        on_en = sorted((p.value, frozenset(p.nets.values())) for p in power.PARTS if "EN" in p.nets.values())
        self.assertIn(("10k", frozenset({"EN", power.V3})), on_en)
        self.assertIn(("1uF", frozenset({"EN", power.GND})), on_en)

    def test_debug_jst_carries_uart0_with_499r_on_tx(self) -> None:
        jack = PARTS["J2"]
        self.assertEqual((jack.nets["1"], jack.nets["2"], jack.nets["MP"]), ("UART0_RX", power.GND, power.GND))
        series = [p for p in power.PARTS if set(p.nets.values()) == {"UART0_TX", jack.nets["3"]}]
        self.assertEqual([p.value for p in series], ["499R"])


class BacklightTest(unittest.TestCase):
    def test_each_sink_is_enabled_by_its_pwm_pin_pulled_down_and_set_by_its_resistor(self) -> None:
        for ref, enable, cathode, set_value in (("U4", "BL_BIG", "LEDK_BIG", "6.2R"),
                                                ("U5", "BL_STRIP", "LEDK_STRIP", "8.2R")):
            sink = PARTS[ref]
            self.assertEqual(sink.nets["1"], enable)
            self.assertEqual({sink.nets[pin] for pin in ("2", "3", "5")}, {cathode})
            self.assertEqual(sink.nets["4"], power.GND)
            pull_down = [p.value for p in power.PARTS if set(p.nets.values()) == {enable, power.GND}]
            self.assertEqual(pull_down, ["100k"])
            setting = [p.value for p in power.PARTS if set(p.nets.values()) == {sink.nets["6"], power.GND}]
            self.assertEqual(setting, [set_value])
            self.assertIn(cathode, power.HMI_NETS)

    def test_the_drawn_sink_symbol_has_the_pin_table_pins(self) -> None:
        self.assertEqual({pin.number for pin in power.BCR421_SYMBOL.pins}, {pin.number for pin in power.BCR421_PINS})
        self.assertEqual(PARTS["U4"].symbol, power.BCR421_SYMBOL.lib_id)

    def test_hmi_nets_are_the_rest_of_board_toml_gpio_and_the_two_cathodes(self) -> None:
        here = {"BOOT", "CC1", "CC2", "USB_DM", "USB_DP", "UART0_TX", "UART0_RX", "BL_BIG", "BL_STRIP"}
        self.assertEqual(power.HMI_NETS, (set(BOARD["gpio"]) - here) | {"LEDK_BIG", "LEDK_STRIP"})


if __name__ == "__main__":
    unittest.main()
