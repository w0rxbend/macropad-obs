# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The board's schematic: where each part of circuit_power.py and circuit_hmi.py sits on the one A3
sheet, and the few wires drawn by hand. Data only; schematic.py draws it and `just pcb erc` checks it.

Units and rules are sheet_layout.py's: grid steps of 1.27 mm, block-relative, Y down. A pin no wire
here reaches gets its supply symbol or its net label by rule. Two-pin parts lie on their side
(rotation 90: pin 1 left, pin 2 right) so a label or supply symbol sits at each end.

Pin offsets used below come from the kicad/kicad:9.0.9 symbols, read on 2026-11-20:
Conn_01xNN_MountingPin pin n at (-4, 2n - NN); SW_Push 1 and 2 at (-4, 0) and (4, 0);
D_Schottky K and A at (-3, 0) and (3, 0); RotaryEncoder_Switch_MP S2 at (6, 2);
TLV62569DBV VIN (-6, -2), EN (-6, 0), SW (6, -2); BCR421UW6 (circuit_power) OUT at (6, -1..1).
A wrong offset fails the build: schematic.py refuses a wire that is not straight.
"""

from __future__ import annotations

from circuit_hmi import BOARD_PARTS, COLS, KEY_COLS, ROWS
from circuit_power import (BCR421_SYMBOL, BUCK_SW, DERIVED_FOOTPRINTS, GND, LEDK_BIG, LEDK_STRIP, V3, V5,
                           VBUS, Part)
from schematic import Sheet
from sheet_layout import Block, Flag, Note, Place, Rail, Wire

_PARTS = {part.ref: part for part in BOARD_PARTS}
SIDEWAYS = 90


def _column(refs: tuple[str, ...], x: int, top: int, pitch: int) -> tuple[Place, ...]:
    """Two-pin parts on their side, one under the other."""
    return tuple(Place(ref, x, top + pitch * index, SIDEWAYS) for index, ref in enumerate(refs))


# --- power, MCU, USB ----------------------------------------------------------------------------

_USB = Block(
    "USB-C device port: CC resistors and sense, ESD, series resistors, fuse", 4, 6, 100, 52,
    places=(Place("J1", 16, 24), *_column(("R1", "R2", "R3", "R4", "R5", "R6"), 56, 12, 5),
            Place("U3", 86, 18), Place("F1", 86, 36, SIDEWAYS)),
    notes=(Note("5.1 k on each CC pad; 100 k into ADC1 senses the source current.", 2, 50),),
)

_BUCK = Block(
    "3.3 V buck: TLV62569, 2.2 uH, FB 453 k / 100 k", 4, 60, 100, 40,
    places=(Place("U2", 22, 18), Place("L1", 36, 16, SIDEWAYS), *_column(("C1", "C2", "R7", "R8"), 60, 10, 6)),
    wires=(
        Wire(V5, ((10, 16), "U2.4")),
        Wire(V5, ((13, 16), (13, 18), "U2.1")),
        Wire(BUCK_SW, ("U2.3", (30, 16), (30, 12)), label=(30, 12)),
        Wire(BUCK_SW, ((30, 16), "L1.1")),
    ),
    rails=(Rail(V5, (10, 16)),),
    notes=(Note("EN on VIN: the buck runs whenever +5V is up.", 2, 38),),
)

_MODULE = Block(
    "MCU: ESP32-S3-WROOM-1-N16R2, reset, boot, UART0 debug", 106, 6, 108, 70,
    places=(Place("U1", 40, 32), *_column(("C3", "C4", "R9", "C5", "R10", "R11"), 86, 10, 6),
            Place("SW21", 86, 46), Place("SW20", 86, 52), Place("J2", 72, 56)),
    notes=(Note("SW21 RESET, SW20 BOOT. J2: 1 RX, 2 GND, 3 TX.", 2, 68),),
)


def _sink_wires(ref: str, x: int, y: int, cathode: str) -> tuple[Wire, ...]:
    """The three OUT pins of a BCR421 joined, one label for the panel cathode."""
    return (Wire(cathode, (f"{ref}.2", (x + 8, y - 1), (x + 8, y + 1), f"{ref}.5")),
            Wire(cathode, (f"{ref}.3", (x + 8, y), (x + 10, y)), label=(x + 10, y)))


_BACKLIGHTS = Block(
    "Backlights: BCR421 constant-current sinks on the panel cathodes", 106, 78, 108, 22,
    places=(Place("U4", 20, 10), *_column(("R12", "R13"), 50, 8, 6),
            Place("U5", 72, 10), *_column(("R14", "R15"), 98, 8, 6)),
    wires=_sink_wires("U4", 20, 10, LEDK_BIG) + _sink_wires("U5", 72, 10, LEDK_STRIP),
)

# --- HMI ----------------------------------------------------------------------------------------


def _switch_cell(switch: str, diode: str, x: int, y: int) -> tuple[tuple[Place, ...], Wire]:
    """A push contact with its diode under it: COL on the left, the diode cathode on ROW."""
    net = _PARTS[diode].nets["2"]
    wire = Wire(net, (f"{switch}.2", (x + 6, y), (x + 6, y + 6), f"{diode}.2"), label=(x + 6, y))
    return (Place(switch, x, y), Place(diode, x, y + 6)), wire


def _switch_block(title: str, y: int, height: int, cells: list[tuple[str, str, int, int]]) -> Block:
    drawn = [_switch_cell(*cell) for cell in cells]
    return Block(title, 218, y, 108, height, places=tuple(p for places, _ in drawn for p in places),
                 wires=tuple(wire for _, wire in drawn))


_KEYS = _switch_block(
    "Keys: MX hot-swap sockets, one BAT54 each, COL sensed, ROW driven", 6, 52,
    [(f"SW{KEY_COLS * row + col + 1}", f"D{COLS * row + col + 1}", 14 + 30 * col, 12 + 14 * row)
     for row in range(ROWS - 1) for col in range(KEY_COLS)])

_BUTTONS = _switch_block(
    "Buttons: B3F on ROW3", 60, 22,
    [(f"SW{10 + col}", f"D{COLS * (ROWS - 1) + col + 1}", 14 + 26 * col, 8) for col in range(COLS)])


def _knob_cell(number: int) -> tuple[tuple[Place, ...], Wire]:
    """An EC11: phases on the left to their filters, the push contact on COL3 through its diode."""
    x, y = 22 + 35 * (number - 1), 14
    switch, diode = f"SW{13 + number}", f"D{COLS * (number - 1) + KEY_COLS + 1}"
    net = _PARTS[diode].nets["2"]
    wire = Wire(net, (f"{switch}.S2", (x + 8, y + 2), (x + 8, y + 13), f"{diode}.2"), label=(x + 8, y + 2))
    return (Place(switch, x, y), Place(diode, x + 3, y + 13)), wire


_knobs = [_knob_cell(number) for number in (1, 2, 3)]
_KNOBS = Block(
    "Knobs: EC11 phases and push contact (COL3)", 218, 84, 108, 34,
    places=tuple(p for places, _ in _knobs for p in places), wires=tuple(wire for _, wire in _knobs))

_FILTER_PITCH = 6
_FILTERS = Block(
    "Encoder filters: 3.3 k pull-up, 10 k series, 10 nF at the GPIO", 218, 120, 108, 44,
    places=tuple(place for index in range(6) for place in (
        Place(f"R{24 + 2 * index}", 18, 8 + _FILTER_PITCH * index, SIDEWAYS),
        Place(f"R{25 + 2 * index}", 54, 8 + _FILTER_PITCH * index, SIDEWAYS),
        Place(f"C{20 + index}", 90, 8 + _FILTER_PITCH * index, SIDEWAYS))),
)

_PULL_UPS = Block(
    "Column pull-ups: 4.7 k", 218, 166, 108, 14,
    places=tuple(Place(f"R{20 + col}", 14 + 26 * col, 8, SIDEWAYS) for col in range(COLS)),
)


def _flag_wire(net: str, x: int) -> tuple[Wire, Rail, Flag]:
    return Wire(net, ((x, 10), (x + 6, 10))), Rail(net, (x, 10)), Flag((x + 6, 10))


_flags = [_flag_wire(net, 10 + 24 * index) for index, net in enumerate((GND, VBUS, V5, V3))]
_FLAGS = Block(
    "Power flags", 218, 182, 108, 18,
    places=(),
    wires=tuple(wire for wire, _, _ in _flags), rails=tuple(rail for _, rail, _ in _flags),
    flags=tuple(flag for _, _, flag in _flags),
    notes=(Note("The supplies enter through J1, F1 and L1, which are passive: ERC needs a flag on each.", 2, 16),),
)

# --- display tails ------------------------------------------------------------------------------


def _tail_buses(part: Part, place: Place, buses: dict[str, tuple[int, int]]) -> tuple[list[Wire], list[Rail]]:
    """Each supply pin of a connector wired out to its net's bus (x), the bus run to its symbol (end y)."""
    count = sum(1 for pin in part.pins if pin.number != "MP")
    wires, rails = [], []
    for net, (bus_x, end_y) in buses.items():
        numbers = [int(pin) for pin, pin_net in part.nets.items() if pin_net == net and pin != "MP"]
        rows = [place.y + 2 * number - count for number in numbers]
        wires += [Wire(net, (f"{part.ref}.{number}", (bus_x, row))) for number, row in zip(numbers, rows)]
        start = max(rows) if end_y < min(rows) else min(rows)
        wires.append(Wire(net, ((bus_x, start), (bus_x, end_y))))
        rails.append(Rail(net, (bus_x, end_y)))
    return wires, rails


_BIG_TAIL, _STRIP_TAIL = Place("J3", 60, 52), Place("J4", 160, 30)
_big_wires, _big_rails = _tail_buses(_PARTS["J3"], _BIG_TAIL, {V5: (40, 10), V3: (33, 10), GND: (36, 96)})
_strip_wires, _strip_rails = _tail_buses(_PARTS["J4"], _STRIP_TAIL, {V3: (136, 18), V5: (130, 18)})
_TAILS = Block(
    "Display tails: J3 big panel (40 pins), J4 strip (10 pins)", 4, 102, 210, 106,
    places=(_BIG_TAIL, _STRIP_TAIL),
    wires=tuple(_big_wires + _strip_wires), rails=tuple(_big_rails + _strip_rails),
    notes=(Note("Panel pin n on pad n. J3 and J4 are PLACEHOLDER_* footprints until task 5.3b;", 90, 70),
           Note("the FH12 contact face is MEASURE, and a flipped face reverses the pad order.", 90, 73),
           Note("J3: IM0-IM2 and RD on +3V3 (4-wire SPI), DB17-DB0 on GND, 37-40 open.", 90, 78)),
)

BLOCKS: tuple[Block, ...] = (_USB, _BUCK, _MODULE, _BACKLIGHTS, _KEYS, _BUTTONS, _KNOBS, _FILTERS, _PULL_UPS,
                             _FLAGS, _TAILS)
SHEET = Sheet(parts=BOARD_PARTS, blocks=BLOCKS, own_symbols=(BCR421_SYMBOL,),
              derived_footprints=DERIVED_FOOTPRINTS)
