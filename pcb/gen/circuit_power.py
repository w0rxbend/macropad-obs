# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The power, MCU and USB netlist: every part, its pins and its nets. Pure Python, no KiCad.

Parts: the ESP32-S3-WROOM-1-N16R2 module, the TLV62569 3.3 V buck, the GCT USB4216-03-A jack with
5.1 k on each CC pad, 100 k CC sense lines, USBLC6-2SC6 ESD, a PPTC fuse, BOOT and RESET, the
UART0 debug JST and the two BCR421UW6 backlight sinks (spec-v2 sections 6 and 7,
docs/research/10-electrical-design.md blocks 1 to 5 and 9). Placement is task 5.6.

Each part lists all its pins. A pin is on a net or marked no-connect, never neither (`problems`).
A pin with a `rail` must sit on that supply rail. The MCU's GPIO nets are board.toml [gpio] names.
The nets in HMI_NETS have one pad here; circuit_hmi.py (task 5.5) gives them the rest.

Pin numbers of the KiCad symbols named here were read from the kicad/kicad:9.0.9 library on
2026-11-20. BCR421UW6 has no KiCad symbol: its pins are from the Diodes datasheet DS37667 Rev. 4-2,
page 1 pin-out. LCSC cells stay UNVERIFIED (spec rule R2).

References: below 20 for R and C here, SW20 and SW21 for BOOT and RESET; the HMI sheet keeps the
rest. `problems` over both sheets finds a reference used twice.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from symlib import BoxPin, box_symbol

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARD = tomllib.loads((REPO_ROOT / "board.toml").read_text())
UNVERIFIED = "UNVERIFIED"

GND = "GND"
VBUS = "VBUS"
V5 = "+5V"
V3 = "+3V3"


@dataclass(frozen=True)
class Pin:
    number: str
    rail: str = ""  # a supply pin: the rail it must sit on


@dataclass(frozen=True)
class Part:
    ref: str
    value: str
    footprint: str                       # "library:name"
    symbol: str                          # KiCad lib_id, or "macropad-obs:..." drawn by the sheet (task 5.7)
    pins: tuple[Pin, ...]
    nets: Mapping[str, str]              # pin number -> net
    no_connect: frozenset[str] = frozenset()
    manufacturer_part: tuple[str, str] = ("", "")
    lcsc: str = UNVERIFIED
    machine_assembled: bool = True       # all of this sheet is SMT on the bottom face


def gpio_net(name: str) -> str:
    """A [gpio] net name, so a rename in board.toml fails here and not on the board."""
    assert name in BOARD["gpio"], f"board.toml [gpio] has no {name}"
    return name


# --- pin tables ---------------------------------------------------------------------------------

TWO_PINS = (Pin("1"), Pin("2"))

# ESP32-S3-WROOM-1 pad of each GPIO: datasheet v1.8 table 3-1, equal to KiCad RF_Module:ESP32-S3-WROOM-1.
WROOM_IO_PIN = {
    0: 27, 1: 39, 2: 38, 3: 15, 4: 4, 5: 5, 6: 6, 7: 7, 8: 12, 9: 17, 10: 18, 11: 19, 12: 20, 13: 21,
    14: 22, 15: 8, 16: 9, 17: 10, 18: 11, 19: 13, 20: 14, 21: 23, 35: 28, 36: 29, 37: 30, 38: 31,
    39: 32, 40: 33, 41: 34, 42: 35, 43: 37, 44: 36, 45: 26, 46: 16, 47: 24, 48: 25,
}
WROOM_EN_PIN = "3"
WROOM_PINS = (Pin("1", GND), Pin("2", V3), Pin(WROOM_EN_PIN), Pin("40", GND), Pin("41", GND),
              *(Pin(str(pad)) for pad in WROOM_IO_PIN.values()))
SPARE_IO = (35, 36, 37)  # free on the N16R2 (spec-v2 section 7)

# TLV62569DBV, SLVSDG1C pin functions: 1 EN, 2 GND, 3 SW, 4 VIN, 5 FB.
TLV62569_PINS = (Pin("1"), Pin("2", GND), Pin("3"), Pin("4", V5), Pin("5"))
# USBLC6-2SC6: 1 and 6 I/O1, 3 and 4 I/O2, 2 GND, 5 VBUS.
USBLC6_PINS = (Pin("1"), Pin("2", GND), Pin("3"), Pin("4"), Pin("5", VBUS), Pin("6"))
# BCR421UW6, DS37667 page 1: 1 EN, 2 OUT, 3 OUT, 4 GND, 5 OUT, 6 REXT.
BCR421_PINS = (Pin("1"), Pin("2"), Pin("3"), Pin("4", GND), Pin("5"), Pin("6"))
BCR421_SYMBOL = box_symbol("macropad-obs:BCR421UW6", "BCR421UW6", (4, 3), (
    BoxPin("1", "EN", "input", "left", 0), BoxPin("6", "REXT", "passive", "left", 2),
    BoxPin("2", "OUT", "passive", "right", -1), BoxPin("3", "OUT", "passive", "right", 0),
    BoxPin("5", "OUT", "passive", "right", 1), BoxPin("4", "GND", "power_in", "bottom", 0)))
# USB4216-03-A pads as the footprint names them, KiCad Connector:USB_C_Receptacle_USB2.0_16P.
USB_GND_PADS = ("A1", "A12", "B1", "B12", "S1")
USB_VBUS_PADS = ("A4", "A9", "B4", "B9")
USB_C_PINS = (*(Pin(pad, GND) for pad in USB_GND_PADS), *(Pin(pad, VBUS) for pad in USB_VBUS_PADS),
              *(Pin(pad) for pad in ("A5", "B5", "A6", "B6", "A7", "B7", "A8", "B8")))
JST_PINS = (Pin("1"), Pin("2", GND), Pin("3"), Pin("MP", GND))

# --- footprints and symbols ---------------------------------------------------------------------

R0402 = "Resistor_SMD:R_0402_1005Metric"
R0805 = "Resistor_SMD:R_0805_2012Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
# Project footprint -> the stock one the KiCad symbol names. Pads 1 to 41 are the stock copper; only the
# keep-out and courtyard changed (pcb/lib/SOURCES.txt). For schematic.Sheet.derived_footprints.
DERIVED_FOOTPRINTS = {"macropad-obs:ESP32-S3-WROOM-1": "RF_Module:ESP32-S3-WROOM-1"}


def _resistor(ref: str, value: str, net_1: str, net_2: str, footprint: str = R0402) -> Part:
    return Part(ref, value, footprint, "Device:R", TWO_PINS, {"1": net_1, "2": net_2})


def _capacitor(ref: str, value: str, net: str, footprint: str = C0402) -> Part:
    return Part(ref, value, footprint, "Device:C", TWO_PINS, {"1": net, "2": GND})


# --- blocks -------------------------------------------------------------------------------------

USB_CC1, USB_CC2 = "USB_CC1", "USB_CC2"   # CC pads, before the 100 k sense resistors
USB_D_P, USB_D_N = "USB_D_P", "USB_D_N"   # the jack side of the 22 ohm resistors


def _usb() -> tuple[Part, ...]:
    """USB-C device port: shell to ground, A6/B6 and A7/B7 joined at the pads, fuse after VBUS."""
    jack_nets = {pad: GND for pad in USB_GND_PADS} | {pad: VBUS for pad in USB_VBUS_PADS}
    jack_nets |= {"A5": USB_CC1, "B5": USB_CC2, "A6": USB_D_P, "B6": USB_D_P, "A7": USB_D_N, "B7": USB_D_N}
    return (
        Part("J1", "USB4216-03-A", "macropad-obs:USB_C_Receptacle_GCT_USB4216-03-A",
             "Connector:USB_C_Receptacle_USB2.0_16P", USB_C_PINS, jack_nets, frozenset({"A8", "B8"}),
             ("GCT", "USB4216-03-A")),
        # One 5.1 k per CC pad, never shared (USB Type-C spec table 4-28, report 10 block 1).
        _resistor("R1", "5.1k", USB_CC1, GND),
        _resistor("R2", "5.1k", USB_CC2, GND),
        # CC sense into ADC1: a 1.5 A or 3 A source shows 0.746 V or more (report 10 block 1).
        _resistor("R3", "100k", USB_CC1, gpio_net("CC1")),
        _resistor("R4", "100k", USB_CC2, gpio_net("CC2")),
        Part("U3", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6", "Power_Protection:USBLC6-2SC6", USBLC6_PINS,
             {"1": USB_D_N, "6": USB_D_N, "3": USB_D_P, "4": USB_D_P, "2": GND, "5": VBUS},
             manufacturer_part=("STMicroelectronics", "USBLC6-2SC6")),
        # Espressif: "reserve series resistors (initial value can be 22/33 ohm)" on IO19 and IO20.
        _resistor("R5", "22R", USB_D_N, gpio_net("USB_DM")),
        _resistor("R6", "22R", USB_D_P, gpio_net("USB_DP")),
        # About 0.75 A hold against the 510 mA peak (report 18 section 4). Part unverified.
        Part("F1", "PPTC 0.75A hold", "Fuse:Fuse_1206_3216Metric", "Device:Polyfuse", TWO_PINS,
             {"1": VBUS, "2": V5}),
    )


BUCK_SW, BUCK_FB = "BUCK_SW", "BUCK_FB"


def _buck() -> tuple[Part, ...]:
    """TLV62569 at 3.3 V (SLVSDG1C 8.2): 2.2 uH, 4.7 uF in, 10 uF out; FB 0.6 V x (1 + 453k / 100k) = 3.32 V.
    EN must not float, so it sits on VIN. The optional 6.8 pF feed-forward is left out."""
    return (
        Part("U2", "TLV62569DBV", "Package_TO_SOT_SMD:SOT-23-5", "Regulator_Switching:TLV62569DBV",
             TLV62569_PINS, {"1": V5, "2": GND, "3": BUCK_SW, "4": V5, "5": BUCK_FB},
             manufacturer_part=("Texas Instruments", "TLV62569DBVR")),
        _capacitor("C1", "4.7uF", V5, C0805),
        # 2.5 x 2.0 so it stays under [bottom_side] max_part_height; part and saturation current unverified.
        Part("L1", "2.2uH", "Inductor_SMD:L_1008_2520Metric", "Device:L", TWO_PINS, {"1": BUCK_SW, "2": V3}),
        _resistor("R7", "453k", V3, BUCK_FB),
        _resistor("R8", "100k", BUCK_FB, GND),
        _capacitor("C2", "10uF", V3, C0805),
    )


RESET_NET = "EN"
DEBUG_TX = "DBG_TX"


def _module() -> tuple[Part, ...]:
    """The module with 22 uF + 0.1 uF at its 3V3 pad, EN 10 k / 1 uF with RESET, IO0 10 k with BOOT
    and no capacitor (Espressif: "Do not add high-value capacitors at GPIO0"), and UART0 on the JST."""
    nets = {"1": GND, "2": V3, WROOM_EN_PIN: RESET_NET, "40": GND, "41": GND}
    nets |= {str(WROOM_IO_PIN[io]): net for net, io in BOARD["gpio"].items()}
    left_open = [int(pad[2:]) for pad, net in BOARD["strapping"].items() if net == ""] + list(SPARE_IO)
    return (
        Part("U1", BOARD["mcu"]["part"], "macropad-obs:ESP32-S3-WROOM-1", "RF_Module:ESP32-S3-WROOM-1",
             WROOM_PINS, nets, frozenset(str(WROOM_IO_PIN[io]) for io in left_open),
             ("Espressif", BOARD["mcu"]["part"])),
        _capacitor("C3", "22uF", V3, C0805),
        _capacitor("C4", "100nF", V3),
        _resistor("R9", "10k", RESET_NET, V3),
        _capacitor("C5", "1uF", RESET_NET),
        Part("SW21", "TS-1187A", "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", "Switch:SW_Push", TWO_PINS,
             {"1": RESET_NET, "2": GND}),
        _resistor("R10", "10k", gpio_net("BOOT"), V3),
        Part("SW20", "TS-1187A", "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", "Switch:SW_Push", TWO_PINS,
             {"1": gpio_net("BOOT"), "2": GND}),
        # Report 10 block 9: pin 1 RX, pin 2 GND, pin 3 TX, 499 ohm in series with TX.
        Part("J2", "SM03B-SRSS-TB", "Connector_JST:JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal",
             "Connector_Generic_MountingPin:Conn_01x03_MountingPin", JST_PINS,
             {"1": gpio_net("UART0_RX"), "2": GND, "3": DEBUG_TX, "MP": GND},
             manufacturer_part=("JST", "SM03B-SRSS-TB(LF)(SN)")),
        _resistor("R11", "499R", gpio_net("UART0_TX"), DEBUG_TX),
    )


LEDK_BIG, LEDK_STRIP = "LEDK_BIG", "LEDK_STRIP"


def _sink(ref: str, enable: str, cathode: str, set_ref: str, set_value: str, pull_ref: str) -> tuple[Part, ...]:
    rext = f"{enable}_REXT"
    return (
        Part(ref, "BCR421UW6", "Package_TO_SOT_SMD:SOT-23-6", "macropad-obs:BCR421UW6", BCR421_PINS,
             {"1": enable, "2": cathode, "3": cathode, "4": GND, "5": cathode, "6": rext},
             manufacturer_part=("Diodes Incorporated", "BCR421UW6-7")),
        _resistor(set_ref, set_value, rext, GND, R0805),
        _resistor(pull_ref, "100k", enable, GND),  # off until the firmware drives it (report 10 block 5)
    )


def _backlights() -> tuple[Part, ...]:
    """Two constant-current sinks; the panel anodes take +5V on the FPC (task 5.5). REXT read off the
    DS37667 V_EN = 3.3 V curve: 6 ohm gives about 125 mA and 8 ohm about 100 mA. Bench check: MEASURE."""
    return (_sink("U4", gpio_net("BL_BIG"), LEDK_BIG, "R12", "6.2R", "R13")
            + _sink("U5", gpio_net("BL_STRIP"), LEDK_STRIP, "R14", "8.2R", "R15"))


PARTS: tuple[Part, ...] = _usb() + _buck() + _module() + _backlights()

_FINISHED_HERE = {"BOOT", "CC1", "CC2", "USB_DM", "USB_DP", "UART0_TX", "UART0_RX", "BL_BIG", "BL_STRIP"}
HMI_NETS = frozenset(set(BOARD["gpio"]) - _FINISHED_HERE) | {LEDK_BIG, LEDK_STRIP}


# --- checks -------------------------------------------------------------------------------------

def nets_to_pads(parts: tuple[Part, ...]) -> dict[str, list[str]]:
    pads: dict[str, list[str]] = {}
    for part in parts:
        for pin, net in part.nets.items():
            pads.setdefault(net, []).append(f"{part.ref}.{pin}")
    return pads


def _pin_problems(part: Part) -> list[str]:
    numbers = {pin.number for pin in part.pins}
    found = [f"{part.ref}.{pin} is not a pin of {part.value}" for pin in sorted(set(part.nets) - numbers)]
    found += [f"{part.ref}.{pin} is marked no-connect but is on {part.nets[pin]}"
              for pin in sorted(part.no_connect & set(part.nets))]
    found += [f"{part.ref}.{pin} is open" for pin in sorted(numbers - set(part.nets) - part.no_connect)]
    found += [f"{part.ref}.{pin.number} is a {pin.rail} pin on {part.nets[pin.number]}"
              for pin in part.pins if pin.rail and pin.number in part.nets and part.nets[pin.number] != pin.rail]
    return found


def problems(parts: tuple[Part, ...], unfinished: frozenset[str]) -> list[str]:
    """Every netlist fault: a repeated reference, an open pin, a supply pin off its rail, and a net
    with one pad that is not in `unfinished` (nets another sheet completes)."""
    refs = [part.ref for part in parts]
    found = [f"reference {ref} is used twice" for ref in sorted({r for r in refs if refs.count(r) > 1})]
    for part in parts:
        found += _pin_problems(part)
    found += [f"net {net} has one pad: {pads[0]}" for net, pads in sorted(nets_to_pads(parts).items())
              if len(pads) < 2 and net not in unfinished]
    return found


def forbidden_lcsc(parts: tuple[Part, ...]) -> list[str]:
    """References whose LCSC cell is not UNVERIFIED (CLAUDE.md: LCSC cells stay UNVERIFIED)."""
    return [part.ref for part in parts if part.lcsc != UNVERIFIED]


if __name__ == "__main__":
    for line in problems(PARTS, HMI_NETS):
        print(line)
    for net_name, pad_names in sorted(nets_to_pads(PARTS).items()):
        print(f"{net_name:14} {' '.join(pad_names)}")
