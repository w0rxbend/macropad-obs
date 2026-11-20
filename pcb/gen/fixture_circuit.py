# SPDX-License-Identifier: CERN-OHL-S-2.0
"""A four-part circuit for test_schematic.py. Not the board: the board's circuit comes in tasks 5.4 and 5.5.

A jack feeds VBUS to a capacitor and a sense line to a resistor in a second block. Between them the
sheet gets a drawn wire with a power flag on it, supply symbols, net labels, a turned part and an
open pin, so every rule of schematic.py draws something.

`LIBRARY_FILES` stands in for the few symbols of KiCad 9's own libraries that the circuit uses, with
their pins where KiCad puts them, so the sheet can be drawn without the KiCad container.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from schematic import Sheet
from sheet_layout import Block, Flag, Note, Place, Wire
from symlib import BoxPin, box_symbol

GND = "GND"
VBUS = "VBUS"
SENSE = "SENSE"


@dataclass(frozen=True)
class Part:
    ref: str
    value: str
    footprint: str
    lcsc: str
    symbol: str
    nets: dict[str, str] = field(default_factory=dict)


JACK = box_symbol("macropad-obs:FIXTURE_JACK", "FIXTURE_JACK", (4, 3), (
    BoxPin("1", "VBUS", "power_out", "right", -1), BoxPin("2", "GND", "power_out", "bottom", 0),
    BoxPin("3", "SENSE", "output", "right", 1), BoxPin("4", "NC", "passive", "left", 0)))

PARTS = (
    Part("J1", "FIXTURE_JACK", "macropad-obs:FIXTURE_JACK", "", JACK.lib_id, {"1": VBUS, "2": GND, "3": SENSE}),
    Part("C1", "1u", "Capacitor_SMD:C_0402_1005Metric", "UNVERIFIED", "Device:C", {"1": VBUS, "2": GND}),
    Part("R1", "10k", "Resistor_SMD:R_0402_1005Metric", "UNVERIFIED", "Device:R", {"1": SENSE, "2": GND}),
)

BLOCKS = (
    Block("Input", 6, 10, 60, 30,
          places=(Place("J1", 14, 15), Place("C1", 36, 17)),
          wires=(Wire(VBUS, ("J1.1", (28, 14), "C1.1")),),
          flags=(Flag((28, 14)),),
          notes=(Note("Fixture only: not the board.", 2, 28),)),
    Block("Sense", 70, 10, 40, 30, places=(Place("R1", 20, 15, 90),)),
)

SHEET = Sheet(parts=PARTS, blocks=BLOCKS, own_symbols=(JACK,))

_FONT = "(effects (font (size 1.27 1.27)))"
_HIDE = "(effects (font (size 1.27 1.27)) (hide yes))"


def _two_pin(name: str, reference: str) -> str:
    return (f'(symbol "{name}" (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes)) (in_bom yes) (on_board yes) '
            f'(property "Reference" "{reference}" (at 2.032 0 90) {_FONT}) (property "Value" "{name}" (at 0 0 90) {_FONT}) '
            f'(property "Footprint" "" (at 0 0 0) {_HIDE}) '
            f'(symbol "{name}_1_1" '
            f'(pin passive line (at 0 3.81 270) (length 1.27) (name "~" {_FONT}) (number "1" {_FONT})) '
            f'(pin passive line (at 0 -3.81 90) (length 1.27) (name "~" {_FONT}) (number "2" {_FONT}))))')


def _power(name: str, kind: str, pin_angle: int, value_y: float) -> str:
    return (f'(symbol "{name}" (power) (pin_names (offset 0) (hide yes)) (in_bom yes) (on_board yes) '
            f'(property "Reference" "#PWR" (at 0 0 0) {_HIDE}) (property "Value" "{name}" (at 0 {value_y} 0) {_FONT}) '
            f'(symbol "{name}_1_1" (pin {kind} line (at 0 0 {pin_angle}) (length 0) (name "~" {_FONT}) (number "1" {_FONT}))))')


LIBRARY_FILES = {
    "Device.kicad_sym": f'(kicad_symbol_lib (version 20241209) {_two_pin("C", "C")} {_two_pin("R", "R")})',
    "power.kicad_sym": (f'(kicad_symbol_lib (version 20241209) {_power("GND", "power_in", 270, -3.81)} '
                        f'{_power("PWR_FLAG", "power_out", 90, 3.81)})'),
}
