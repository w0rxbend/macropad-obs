# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Where every part sits, and the board outline. Pure Python, no KiCad; layout.py builds the board from
`board_parts()` and `outline_path()` (`just pcb place`).

Parts that board.toml names sit on its points: keys, buttons, knobs, holes, the module, the USB jack,
the two tails, BOOT, RESET and the debug JST. The rest are design positions here, inside the zones
board.toml gives them ([regulator] zone, [bottom_side] mcu_zone and usb_support_radius) or beside the
part they serve. Every SMT part, the hot-swap sockets with them, is on the bottom face (report 12);
the buttons, encoders and holes are on the top face. A bottom-face part is mirrored as seen from the top.

Provisional (tasks/todo.md 5.6): the tails stand on the PLACEHOLDER_* footprints and the MEASURE
centres of [fpc.*] until S.3; task 5.12 runs this again.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from circuit_hmi import BOARD, BOARD_PARTS

PCB = BOARD["pcb"]
WIDTH, DEPTH = PCB["width"], PCB["depth"]
TOP, BOTTOM = "top", "bottom"
# board.toml [antenna]: "Cut corners R 0.5, design". The concave one is the router's radius.
ANTENNA_CUT_CORNER_RADIUS = 0.5
HOLE_FOOTPRINT = "macropad-obs:Hole_M2"
# Footprint points (footprint coordinates, mm) that land on the board.toml point.
EC11_SHAFT = (7.5, 2.5)        # stock EC11E footprint: origin on pad A
B3F_CENTRE = (3.25, 2.25)      # stock B3F footprint: origin on pin 1
FH12_COURTYARD_CENTRE = (0.0, 0.95)  # FH12 placeholder courtyard -3.0 to 4.9 about the origin


@dataclass(frozen=True)
class Spot:
    """A part's place: (x, y) in the board.toml frame, where `anchor` (footprint coordinates) lands."""
    x: float
    y: float
    rotation: float = 0.0  # degrees, as seen from the top
    side: str = BOTTOM
    anchor: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class PlacedPart:
    """A part as layout.BoardPart wants it: footprint origin in KiCad coordinates."""
    ref: str
    value: str
    footprint: str
    lcsc: str
    nets: Mapping[str, str]
    x: float
    y: float
    rotation: float
    side: str
    machine_assembled: bool
    manufacturer_part: tuple[str, str] = ("", "")


def kicad_xy(x: float, y: float) -> tuple[float, float]:
    """board.toml (front-left origin, y towards the back edge) -> KiCad (back-left origin, y towards the front)."""
    return x, round(DEPTH - y, 4)


def _turned(dx: float, dy: float, rotation: float, side: str) -> tuple[float, float]:
    """A footprint offset as it lands on the board, in KiCad axes. pcbnew turns a footprint counter-clockwise
    on screen (y down); a bottom-face footprint is the X mirror, then the turn (layout._place)."""
    if side == BOTTOM:
        dx = -dx
    angle = math.radians(rotation)
    return dx * math.cos(angle) + dy * math.sin(angle), -dx * math.sin(angle) + dy * math.cos(angle)


def _origin(spot: Spot) -> tuple[float, float]:
    x, y = kicad_xy(spot.x, spot.y)
    dx, dy = _turned(*spot.anchor, spot.rotation, spot.side)
    return round(x - dx, 4), round(y - dy, 4)


# --- board.toml points --------------------------------------------------------------------------

def _inputs() -> dict[str, Spot]:
    """SW1-SW9 row by row from the back-left, SW10-SW13 left to right, SW14-SW16 top to bottom
    (circuit_hmi). The hot-swap socket is on the bottom face; its switch plugs in from the top."""
    keys, buttons, knobs = BOARD["keys"], BOARD["buttons"], BOARD["knobs"]
    spots = {f"SW{n}": Spot(x, y) for n, (x, y) in
             enumerate(((x, y) for y in keys["y"] for x in keys["x"]), start=1)}
    spots |= {f"SW{10 + n}": Spot(x, buttons["y"], side=TOP, anchor=B3F_CENTRE) for n, x in enumerate(buttons["x"])}
    # Turned 90: the lugs straddle the shaft left and right, the terminal rows lie in front and behind,
    # so the E2 hole's keep-out stays clear of the lug pads (board.toml [pcb] holes).
    spots |= {f"SW{14 + n}": Spot(knobs["x"], y, 90.0, TOP, EC11_SHAFT) for n, y in enumerate(knobs["y"])}
    return spots


def _named_bottom_parts() -> dict[str, Spot]:
    """Module, jack, tails, BOOT, RESET and the debug JST: board.toml [mcu], [usb], [fpc.*], [bottom_side]."""
    left, front, width, depth = BOARD["mcu"]["outline"]
    usb, fpc, side = BOARD["usb"], BOARD["fpc"], BOARD["bottom_side"]
    return {
        # Stock origin is the module centre; turned 0 its antenna end faces the back edge.
        "U1": Spot(left + width / 2, front + depth / 2),
        # Origin on the shell front; turned 180 the mouth faces the back edge, mouth_overhang past it.
        "J1": Spot(usb["x"], DEPTH + usb["mouth_overhang"], 180.0),
        # Turned 0 the tail enters from the front, where the board slot is.
        "J3": Spot(*fpc["big"]["centre"], anchor=FH12_COURTYARD_CENTRE),
        "J4": Spot(*fpc["narrow"]["centre"], anchor=FH12_COURTYARD_CENTRE),
        "SW20": Spot(*side["boot"]),
        "SW21": Spot(*side["reset"]),
        "J2": Spot(*side["debug_uart"]["at"]),
    }


# --- design positions ---------------------------------------------------------------------------

def _usb_support() -> dict[str, Spot]:
    """Within usb_support_radius of the jack body, clear of BOOT and RESET. EN and BOOT parts sit in the
    lane between the two switches."""
    x = BOARD["usb"]["x"]
    body_rear = DEPTH + BOARD["usb"]["mouth_overhang"] - BOARD["usb"]["body"][1]
    switches = BOARD["bottom_side"]
    lane_x = (switches["boot"][0] + switches["reset"][0]) / 2
    lane_y = switches["boot"][1]
    return {
        "F1": Spot(x - 9.0, body_rear + 0.3, 90.0),
        "U3": Spot(x + 0.6, body_rear - 3.4, 90.0),
        **{f"R{n}": Spot(x + 8.2, body_rear - 2.9 + 1.3 * (n - 1)) for n in (1, 2, 3, 4)},
        "R10": Spot(lane_x, lane_y - 2.8),
        "R9": Spot(lane_x, lane_y - 1.5),
        "C5": Spot(lane_x, lane_y - 0.2),
    }


def _wroom_pad_y(pad: int) -> float:
    """board.toml y of side pad 1 to 14 of the module (stock footprint: pad 1 5.26 from the centre towards
    the antenna end, 1.27 pitch)."""
    _, front, _, depth = BOARD["mcu"]["outline"]
    return round(front + depth / 2 + 5.26 - 1.27 * (pad - 1), 4)


def _module_support() -> dict[str, Spot]:
    """22 uF and 100 nF right of the module, by its 3V3 pad (pad 2 lands on the right when mirrored);
    the 22 ohm USB resistors in line with pads 13 and 14, "placed close to the chip" (report 10 block 4);
    the 499 ohm UART resistor beside the debug JST."""
    left, front, width, depth = BOARD["mcu"]["outline"]
    debug_x, debug_y = BOARD["bottom_side"]["debug_uart"]["at"]
    return {
        "C3": Spot(left + width + 2.9, front + depth / 2 + 3.0, 90.0),
        "C4": Spot(left + width + 2.9, front + depth / 2, 90.0),
        "R5": Spot(left + width + 1.7, _wroom_pad_y(13)),
        "R6": Spot(left + width + 1.7, _wroom_pad_y(14)),
        "R11": Spot(debug_x + 5.5, debug_y),
    }


def _buck() -> dict[str, Spot]:
    """board.toml [regulator] zone: the input cap in front of the chip, its +5V pad under VIN and its GND pad
    under the gap that leads to the GND pin; the inductor and the output cap to the right; the feedback
    divider behind, by FB."""
    x, y, _, _ = BOARD["regulator"]["zone"]
    return {
        "U2": Spot(x + 4.0, y + 4.0),
        "C1": Spot(x + 3.9, y + 1.2, 180.0),
        "L1": Spot(x + 8.5, y + 4.0, 180.0),
        "C2": Spot(x + 8.5, y + 1.3),
        "R7": Spot(x + 0.9, y + 6.7, 180.0),
        "R8": Spot(x + 2.9, y + 6.7, 180.0),
    }


def _mcu_zone() -> dict[str, Spot]:
    """board.toml [bottom_side] mcu_zone: the backlight sinks near their tails, and three rows under the
    module: column pull-ups, then the encoder 10 k series resistors, then their 10 nF."""
    x, y, _, depth = BOARD["bottom_side"]["mcu_zone"]
    back = y + depth
    spots = {
        "U4": Spot(x + 26.0, y + 2.0), "R12": Spot(x + 26.0, y + 5.5), "R13": Spot(x + 30.0, y + 2.0),
        "U5": Spot(x + 56.0, y + 4.0), "R14": Spot(x + 56.0, y + 7.5), "R15": Spot(x + 56.0, y + 1.0),
    }
    spots |= {f"R{20 + n}": Spot(x + 38.0 + 1.5 * n, back - 2.5, 90.0) for n in range(4)}
    for n in range(6):  # encoder phases in circuit_hmi order: R25, R27 ... and C20 ... C25
        spots[f"R{25 + 2 * n}"] = Spot(x + 38.0 + 1.5 * n, back - 5.5, 90.0)
        spots[f"C{20 + n}"] = Spot(x + 38.0 + 1.5 * n, back - 8.5, 90.0)
    return spots


def _matrix_support() -> dict[str, Spot]:
    """Each BAT54 beside its own switch: in front of each key's centre hole, behind each button, left of
    each encoder; each encoder's 3.3 k pull-ups beside its diode."""
    keys, buttons, knobs = BOARD["keys"], BOARD["buttons"], BOARD["knobs"]
    spots = {}
    for row, y in enumerate(keys["y"]):
        for col, x in enumerate(keys["x"]):
            spots[f"D{4 * row + col + 1}"] = Spot(x, y - 4.5)
    for col, x in enumerate(buttons["x"]):
        spots[f"D{13 + col}"] = Spot(x, buttons["y"] + 6.9)
    side_x = knobs["x"] - 13.0
    for number, y in enumerate(knobs["y"], start=1):
        spots[f"D{4 * number}"] = Spot(side_x, y)
        pull_up = 24 + 4 * (number - 1)  # R24/R26 for knob 1 A/B, R28/R30, R32/R34
        spots[f"R{pull_up}"] = Spot(side_x, y + 3.0)
        spots[f"R{pull_up + 2}"] = Spot(side_x, y - 3.0)
    return spots


def spots() -> dict[str, Spot]:
    """Ref -> Spot for every circuit part."""
    found: dict[str, Spot] = {}
    for block in (_inputs(), _named_bottom_parts(), _usb_support(), _module_support(), _buck(), _mcu_zone(),
                  _matrix_support()):
        repeated = found.keys() & block.keys()
        assert not repeated, f"placed twice: {sorted(repeated)}"
        found |= block
    return found


def _holes() -> tuple[PlacedPart, ...]:
    return tuple(PlacedPart(f"H{n}", "M2", HOLE_FOOTPRINT, "", {}, *kicad_xy(x, y), 0.0, TOP, False)
                 for n, (x, y) in enumerate(PCB["holes"], start=1))


def board_parts() -> tuple[PlacedPart, ...]:
    """Every circuit part at its spot, then the mounting holes."""
    places = spots()
    refs = {part.ref for part in BOARD_PARTS}
    assert places.keys() == refs, f"unplaced {sorted(refs - places.keys())}, unknown {sorted(places.keys() - refs)}"
    parts = []
    for part in BOARD_PARTS:
        spot = places[part.ref]
        parts.append(PlacedPart(part.ref, part.value, part.footprint, part.lcsc, part.nets, *_origin(spot),
                                spot.rotation, spot.side, part.machine_assembled, part.manufacturer_part))
    return tuple(parts) + _holes()


# --- outline ------------------------------------------------------------------------------------

def _corners() -> list[tuple[float, float, float]]:
    """(x, y, radius) round the board, board.toml frame: the rounded rectangle with the antenna board cut
    out of its back-right corner. The cut runs off the right edge and up to the back edge."""
    radius = PCB["corner_radius"]
    cut_left, cut_front, cut_width, cut_depth = BOARD["antenna"]["board_cut"]
    assert cut_left + cut_width >= WIDTH and math.isclose(cut_front + cut_depth, DEPTH), \
        "the antenna board cut must run off the right edge from the back edge"
    cut = ANTENNA_CUT_CORNER_RADIUS
    return [(0.0, 0.0, radius), (WIDTH, 0.0, radius), (WIDTH, cut_front, cut), (cut_left, cut_front, cut),
            (cut_left, DEPTH, cut), (0.0, DEPTH, radius)]


def _unit(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    return dx / length, dy / length


def _corner_arc(previous: tuple, corner: tuple, following: tuple) -> tuple:
    """("arc", start, middle, end) rounding `corner`, convex or concave, between straight edges."""
    x, y, radius = corner
    to_previous = _unit(previous[0] - x, previous[1] - y)
    to_following = _unit(following[0] - x, following[1] - y)
    start = (x + radius * to_previous[0], y + radius * to_previous[1])
    end = (x + radius * to_following[0], y + radius * to_following[1])
    centre = (start[0] + end[0] - x, start[1] + end[1] - y)
    outward = _unit(x - centre[0], y - centre[1])
    middle = (centre[0] + radius * outward[0], centre[1] + radius * outward[1])
    return ("arc", *(kicad_xy(*point) for point in (start, middle, end)))


def outline_path() -> list[tuple]:
    """The closed board edge in KiCad coordinates: ("arc", start, middle, end) and ("line", start, end)."""
    corners = _corners()
    arcs = [_corner_arc(corners[i - 1], corners[i], corners[(i + 1) % len(corners)]) for i in range(len(corners))]
    path = []
    for arc, next_arc in zip(arcs, arcs[1:] + arcs[:1]):
        path += [arc, ("line", arc[3], next_arc[1])]
    return path
