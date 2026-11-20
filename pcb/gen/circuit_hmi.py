# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The HMI netlist: the 4x4 key matrix, the encoder filters and the two display tails. Pure Python, no KiCad.

It finishes the nets circuit_power.HMI_NETS leaves with one pad; `problems(BOARD_PARTS, frozenset())`
checks both sheets together. Placement is task 5.6.

Matrix (docs/research/08-input-parts.md section 4, firmware/core/input.h): ROWr is driven, COLc is
sensed with a 4.7 k pull-up. Each contact runs from COLc to the anode of its own BAT54, cathode on
ROWr. Keys 0-8 row by row (board.toml [keys], row 0 at the back), knob pushes in COL3, buttons on ROW3.
No pull-downs anywhere.

Encoders (report 08, report 10 block 8): terminal C and the lugs to ground; per phase 3.3 k to 3.3 V
at the terminal, 10 k in series and 10 nF at the GPIO. Knob 1 is the top knob ([knobs] y).

Tails: panel pin n on connector pad n. Big panel, Focus E35GH-I-RW300-N (report 06 pin table and
item 4): IM0-IM2 and RD to IOVCC, pins 7-10 and DB17-DB0 to ground, 37-40 open, no TE. Strip,
Wisevision N279 (report 07 item 4): SDA, SCL, RS, RESET, CS, TE, VDD, LEDK, LEDA, GND. Both anodes on
+5V, cathodes into the circuit_power sinks. The connectors are the PLACEHOLDER_* footprints and the
contact face (FH12 or FH12A) is MEASURE until task 5.3b; a flipped face reverses pad order there.

References: SW1-SW16 (keys, buttons, encoders), D1-D16 (contact order), R20 up, C20 up, J3 and J4.
LCSC cells stay UNVERIFIED (spec rule R2).
"""

from __future__ import annotations

from circuit_power import (BOARD, GND, LEDK_BIG, LEDK_STRIP, PARTS as POWER_PARTS, TWO_PINS, V3, V5,
                           Part, Pin, capacitor, gpio_net, nets_to_pads, problems, resistor)

ROWS = COLS = 4
KEY_COLS = 3


def _project_footprint(table: str) -> str:
    """The board.toml footprint of a table, from the project library (pcb/lib/SOURCES.txt)."""
    return "macropad-obs:" + BOARD[table]["footprint"].split(":", 1)[1]


def _junction(row: int, col: int) -> str:
    return f"MTX_R{row}C{col}"


def _diode(row: int, col: int) -> Part:
    return Part(f"D{COLS * row + col + 1}", "BAT54", "Diode_SMD:D_SOD-123", "Device:D_Schottky", TWO_PINS,
                {"1": gpio_net(f"ROW{row}"), "2": _junction(row, col)}, manufacturer_part=("onsemi", "BAT54T1G"))


def _contact_nets(row: int, col: int, to_column: str, to_diode: str) -> dict[str, str]:
    return {to_column: gpio_net(f"COL{col}"), to_diode: _junction(row, col)}


def _key(row: int, col: int) -> Part:
    """The SMT hot-swap socket on the bottom face; the MX switch plugs in by hand."""
    return Part(f"SW{KEY_COLS * row + col + 1}", "MX in CPG151101S11-1", "macropad-obs:MX_Hotswap",
                "Switch:SW_Push", TWO_PINS, _contact_nets(row, col, "1", "2"),
                manufacturer_part=("Kailh", "CPG151101S11-1"))


def _button(col: int) -> Part:
    return Part(f"SW{10 + col}", "B3F-1060", _project_footprint("buttons"), "Switch:SW_Push", TWO_PINS,
                _contact_nets(ROWS - 1, col, "1", "2"), manufacturer_part=("Omron", "B3F-1060"),
                machine_assembled=False)


ENCODER_PINS = (Pin("A"), Pin("B"), Pin("C", GND), Pin("MP", GND), Pin("S1"), Pin("S2"))


def _raw(number: int, phase: str) -> str:
    """The encoder terminal, before the series resistor."""
    return f"ENC{number}_{phase}_RAW"


def _encoder(number: int) -> Part:
    row = number - 1
    nets = {"A": _raw(number, "A"), "B": _raw(number, "B"), "C": GND, "MP": GND}
    return Part(f"SW{13 + number}", "EC11E18244AU", _project_footprint("knobs"), "Device:RotaryEncoder_Switch_MP",
                ENCODER_PINS, nets | _contact_nets(row, KEY_COLS, "S1", "S2"),
                manufacturer_part=("Alps", "EC11E18244AU"), machine_assembled=False)


def _matrix() -> tuple[Part, ...]:
    keys = tuple(_key(row, col) for row in range(ROWS - 1) for col in range(KEY_COLS))
    buttons = tuple(_button(col) for col in range(COLS))
    encoders = tuple(_encoder(number) for number in (1, 2, 3))
    diodes = tuple(_diode(row, col) for row in range(ROWS) for col in range(COLS))
    pull_ups = tuple(resistor(f"R{20 + col}", "4.7k", gpio_net(f"COL{col}"), V3) for col in range(COLS))
    return keys + buttons + encoders + diodes + pull_ups


def _encoder_filters() -> tuple[Part, ...]:
    phases = [(number, phase) for number in (1, 2, 3) for phase in ("A", "B")]
    parts: tuple[Part, ...] = ()
    for index, (number, phase) in enumerate(phases):
        pin = gpio_net(f"ENC{number}_{phase}")
        parts += (resistor(f"R{24 + 2 * index}", "3.3k", _raw(number, phase), V3),
                  resistor(f"R{25 + 2 * index}", "10k", _raw(number, phase), pin),
                  capacitor(f"C{20 + index}", "10nF", pin))
    return parts


def _fpc_pins(count: int, rails: dict[int, str]) -> tuple[Pin, ...]:
    return (*(Pin(str(n), rails.get(n, "")) for n in range(1, count + 1)), Pin("MP", GND))


BIG_RAILS = {2: V5, 34: V3, 35: V3, 36: GND}
STRIP_RAILS = {7: V3, 9: V5, 10: GND}


def _big_tail() -> Part:
    nets = {1: LEDK_BIG, 2: V5, 6: gpio_net("LCD_RESET"), 29: gpio_net("LCD_MOSI"), 31: gpio_net("LCD_SCK"),
            32: gpio_net("LCD_DC"), 33: gpio_net("LCD_CS_BIG"), 36: GND}
    nets |= {n: V3 for n in (3, 4, 5, 30, 34, 35)}   # IM0-IM2 and RD strapped to IOVCC: 4-wire SPI
    nets |= {n: GND for n in range(7, 29)}           # NC 7-10 (Winstar sync inputs) and DB17-DB0
    return Part("J3", "FH12-40S-0.5SH(55)", "macropad-obs:PLACEHOLDER_FPC_FH12-40S",
                "Connector_Generic_MountingPin:Conn_01x40_MountingPin", _fpc_pins(40, BIG_RAILS),
                {str(n): net for n, net in nets.items()} | {"MP": GND}, frozenset({"37", "38", "39", "40"}),
                ("Hirose", "FH12-40S-0.5SH(55)"))


def _strip_tail() -> Part:
    order = ("LCD_MOSI", "LCD_SCK", "LCD_DC", "LCD_RESET", "LCD_CS_STRIP", "STRIP_TE")
    nets = {str(n): gpio_net(name) for n, name in enumerate(order, start=1)}
    nets |= {"7": V3, "8": LEDK_STRIP, "9": V5, "10": GND, "MP": GND}
    return Part("J4", "FH12-10S-0.5SH(55)", "macropad-obs:PLACEHOLDER_FPC_FH12-10S",
                "Connector_Generic_MountingPin:Conn_01x10_MountingPin", _fpc_pins(10, STRIP_RAILS), nets,
                manufacturer_part=("Hirose", "FH12-10S-0.5SH(55)"))


PARTS: tuple[Part, ...] = _matrix() + _encoder_filters() + (_big_tail(), _strip_tail())
BOARD_PARTS: tuple[Part, ...] = POWER_PARTS + PARTS


if __name__ == "__main__":
    for line in problems(BOARD_PARTS, frozenset()):
        print(line)
    for net_name, pad_names in sorted(nets_to_pads(PARTS).items()):
        print(f"{net_name:14} {' '.join(pad_names)}")
