# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Writes the KiCad schematic of a circuit. Pure Python, but it reads KiCad's symbol libraries.

The schematic is a drawing of the netlist, not a second source of truth. Parts use KiCad's own
library symbols where KiCad has one, so their pin numbers, pin names and pin types come from a
maintained library and not from this repository. The sheet's blocks (sheet_layout.py types) say
where each part sits and which wires are drawn; every other pin gets its supply symbol or its net
label by rule. The build then lets KiCad export the netlist of the result and compares it with the
circuit pin by pin (`nets_by_pin`).

Sheet positions are grid steps of 1.27 mm, Y down.

Copied from macropad-greycode pcb/gen (decision D5). Here the circuit comes in as a `Sheet`
instead of greycode's circuit module, each part names its own symbol, and greycode's LED symbols
and RP2040 pin check are gone.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import sexpr
import sheet_layout
from sheet_layout import Block, Place
from symlib import GRID, LibPin, LibSymbol, SymbolLibrary

KICAD_SYMBOLS = Path("/usr/share/kicad/symbols")
PROJECT = "macropad-obs"
STUB = 2  # grid steps of wire between a pin and its label or supply symbol
NO_NET = ""
SUPPLY_NETS = ("GND", "VBUS", "+5V", "+3V3")  # each is the name of its symbol in KiCad's power library
_UUID_NAMESPACE = uuid.UUID("6f1c2b0e-7d5a-4c1e-9b7e-3a2f0c9d4e11")
_POWER_SYMBOL = {net: f"power:{net}" for net in SUPPLY_NETS}
_FLAG_SYMBOL = "power:PWR_FLAG"


class SheetPart(Protocol):
    """What the schematic needs of a circuit's part."""
    ref: str
    value: str
    footprint: str             # "library:name"
    lcsc: str                  # empty: not in the BOM
    symbol: str                # lib_id: KiCad's ("Device:R") or one of the sheet's own ("macropad-obs:...")
    nets: Mapping[str, str]    # pin number -> net; a pin left out is open


@dataclass(frozen=True)
class Sheet:
    parts: tuple[SheetPart, ...]
    blocks: tuple[Block, ...]
    own_symbols: tuple[LibSymbol, ...] = ()  # drawn here (symlib.box_symbol), lib_id "macropad-obs:..."
    # A project footprint copied from a stock one with only the paste changed -> that stock footprint.
    derived_footprints: Mapping[str, str] = field(default_factory=dict)


def board_net_name(net: str) -> str:
    """The name KiCad gives this net on the board: a supply symbol names its net as it is, a label on
    the root sheet gets a leading slash. With the same names the board can be checked against the schematic."""
    return net if net in _POWER_SYMBOL else "/" + net


OPEN_PIN_NET_PREFIX = "unconnected-"  # KiCad's netlist names the net of every open pin like this


def circuit_net_name(board_net: str) -> str:
    return NO_NET if board_net.startswith(OPEN_PIN_NET_PREFIX) else board_net.removeprefix("/")


# Where the library's default text position runs into a pin or a wire of this sheet: (x, y) grid steps.
_VALUE_OFFSET = {"Device:RotaryEncoder_Switch_MP": (-8, 5), "Switch:SW_Push": (-1, 2.2)}


def check_part_against_symbol(part: SheetPart, symbol: LibSymbol, derived_footprints: Mapping[str, str]) -> None:
    """The circuit may only name pins the symbol has, and must use the footprint the symbol was drawn for, or a
    project copy of it with only the paste changed (the layout checks the copper)."""
    unknown = set(part.nets) - {pin.number for pin in symbol.pins}
    assert not unknown, f"{part.ref}: {symbol.lib_id} has no pins {sorted(unknown)}"
    library_footprint = symbol.property_value("Footprint")
    stock_footprint = derived_footprints.get(part.footprint, part.footprint)
    assert library_footprint in ("", stock_footprint), (
        f"{part.ref}: {symbol.lib_id} is drawn for {library_footprint}, the circuit uses {part.footprint}")


# --- small s-expression helpers ---------------------------------------------------------------

def _uuid(key: str) -> str:
    return str(uuid.uuid5(_UUID_NAMESPACE, key))


def symbol_uuid(ref: str) -> str:
    """The schematic symbol's id. The layout gives the footprint the same one, so KiCad can pair them."""
    return _uuid(ref)


ROOT_UUID = _uuid("root")


def _mm(steps: float) -> str:
    return f"{steps * GRID:.4f}".rstrip("0").rstrip(".")


def _at(point: tuple[float, float], angle: int = 0) -> str:
    return f"(at {_mm(point[0])} {_mm(point[1])} {angle})"


_HIDDEN = "(effects (font (size 1.27 1.27)) (hide yes))"


def _instances(ref: str) -> str:
    return f'(instances (project "{PROJECT}" (path "/{ROOT_UUID}" (reference "{ref}") (unit 1)))))'


# --- one block --------------------------------------------------------------------------------

@dataclass(frozen=True)
class PlacedPin:
    name: str                 # "R7.1"
    net: str
    point: tuple[int, int]    # on the sheet
    outward: tuple[int, int]
    pin: LibPin


@dataclass
class Drawing:
    """What has been drawn so far: KiCad items as text, and the wire ends for the junction dots."""
    items: list[str] = field(default_factory=list)
    segments: list[tuple[tuple[int, int], tuple[int, int]]] = field(default_factory=list)
    net_at: dict[tuple[int, int], str] = field(default_factory=dict)  # every connection point and its net
    pin_points: list[tuple[int, int]] = field(default_factory=list)
    power_count: int = 0
    lib_symbols: dict[str, LibSymbol] = field(default_factory=dict)

    def claim(self, point: tuple[int, int], net: str) -> None:
        other = self.net_at.setdefault(point, net)
        assert other == net, f"{net} and {other} meet at {point}"

    def wire(self, net: str, start: tuple[int, int], end: tuple[int, int]) -> None:
        assert start != end and (start[0] == end[0] or start[1] == end[1]), f"{net}: wire {start} to {end} is not straight"
        self.claim(start, net)
        self.claim(end, net)
        self.segments.append((start, end))

    def label(self, net: str, point: tuple[int, int], direction: tuple[int, int]) -> None:
        angle, justify = {(1, 0): (0, "left"), (-1, 0): (180, "right"), (0, -1): (90, "left"),
                          (0, 1): (270, "right")}[direction]
        self.claim(point, net)
        self.items.append(
            f'(label "{net}" {_at(point, angle)} (effects (font (size 1.27 1.27)) (justify {justify} bottom)) '
            f'(uuid "{_uuid(f"label/{net}/{point}")}"))')

    def power(self, lib_symbol: LibSymbol, net: str, point: tuple[int, int]) -> None:
        """A supply symbol or a power flag with its one pin at the point."""
        self.power_count += 1
        self.lib_symbols[lib_symbol.lib_id] = lib_symbol
        self.claim(point, net)
        self.pin_points.append(point)
        is_flag = lib_symbol.lib_id == _FLAG_SYMBOL
        ref = f"#FLG{self.power_count:03}" if is_flag else f"#PWR{self.power_count:03}"
        value_x, value_y, _, value_style = lib_symbol.property_at("Value")
        value_at = (point[0] + value_x / GRID, point[1] + value_y / GRID)
        self.items.append("\n".join([
            f'(symbol (lib_id "{lib_symbol.lib_id}") {_at(point)} (unit 1) (exclude_from_sim no) (in_bom yes) '
            f'(on_board yes) (dnp no) (uuid "{_uuid(ref)}")',
            f'(property "Reference" "{ref}" {_at(point)} {_HIDDEN})',
            f'(property "Value" "{lib_symbol.name}" {_at(value_at)} {sexpr.dump(value_style)})',
            f'(property "Footprint" "" {_at(point)} {_HIDDEN})',
            f'(property "Datasheet" "" {_at(point)} {_HIDDEN})',
            f'(property "Description" "" {_at(point)} {_HIDDEN})',
            f'(pin "1" (uuid "{_uuid(ref + "/1")}"))',
            _instances(ref),
        ]))


def _field_positions(place: Place, symbol: LibSymbol, origin: tuple[int, int]) -> dict[str, str]:
    """Reference and Value: the library's own spots, or on one line above a part that lies on its side."""
    if place.rotation in (90, 270):
        # A text field turns with its symbol, so 90 here reads horizontally on the sheet.
        # A quarter turn one way also swaps what KiCad calls left and right.
        before, after = ("left", "right") if place.rotation == 90 else ("right", "left")
        line_y = origin[1] - 1.8
        style = "(effects (font (size 1.27 1.27)) (justify {}))"
        return {"Reference": f"{_at((origin[0] - 0.5, line_y), 90)} {style.format(before)}",
                "Value": f"{_at((origin[0] + 0.5, line_y), 90)} {style.format(after)}"}
    assert place.rotation == 0, f"{place.ref}: only two-pin parts are drawn turned"
    positions = {}
    for name in ("Reference", "Value"):
        x, y, angle, style = symbol.property_at(name)
        if name == "Value" and symbol.lib_id in _VALUE_OFFSET:
            x, y = (step * GRID for step in _VALUE_OFFSET[symbol.lib_id])
        positions[name] = f"{_at((origin[0] + x / GRID, origin[1] + y / GRID), angle)} {sexpr.dump(style)}"
    return positions


def _place_part(drawing: Drawing, part: SheetPart, symbol: LibSymbol, place: Place, origin: tuple[int, int]) -> list[PlacedPin]:
    drawing.lib_symbols[symbol.lib_id] = symbol
    fields = _field_positions(place, symbol, origin)
    in_bom = "yes" if part.lcsc else "no"
    lines = [
        f'(symbol (lib_id "{symbol.lib_id}") {_at(origin, place.rotation)} (unit 1) (exclude_from_sim no) '
        f'(in_bom {in_bom}) (on_board yes) (dnp no) (uuid "{symbol_uuid(part.ref)}")',
        f'(property "Reference" "{part.ref}" {fields["Reference"]})',
        f'(property "Value" "{part.value}" {fields["Value"]})',
        f'(property "Footprint" "{part.footprint}" {_at(origin)} {_HIDDEN})',
        f'(property "Datasheet" "" {_at(origin)} {_HIDDEN})',
        f'(property "Description" "" {_at(origin)} {_HIDDEN})',
        f'(property "LCSC" "{part.lcsc}" {_at(origin)} {_HIDDEN})',
    ]
    lines += [f'(pin "{pin.number}" (uuid "{_uuid(f"{part.ref}/{pin.number}")}"))' for pin in symbol.pins]
    lines.append(_instances(part.ref))
    drawing.items.append("\n".join(lines))
    placed = []
    for pin in symbol.pins:
        dx, dy = pin.at(place.rotation)
        placed.append(PlacedPin(f"{part.ref}.{pin.number}", part.nets.get(pin.number, NO_NET),
                                (origin[0] + dx, origin[1] + dy), pin.outward(place.rotation), pin))
    return placed


def _draw_wires(drawing: Drawing, block: Block, pins: dict[str, PlacedPin]) -> set[tuple[int, int]]:
    """The wires the block lists. Returns the points they connect."""
    def resolve(wire_net: str, point) -> tuple[int, int]:
        if isinstance(point, str):
            assert pins[point].net == wire_net, f"{point} is on {pins[point].net}, the drawn wire says {wire_net}"
            return pins[point].point
        return block.x + point[0], block.y + point[1]

    wired = set()
    for wire in block.wires:
        points = [resolve(wire.net, point) for point in wire.points]
        for start, end in zip(points, points[1:]):
            drawing.wire(wire.net, start, end)
        wired.update(points)
        if wire.label is not None:
            x, y, *side = wire.label
            drawing.label(wire.net, (block.x + x, block.y + y), (-1, 0) if side == ["left"] else (1, 0))
    return wired


def _connect_by_rule(drawing: Drawing, library: SymbolLibrary, placed: list[PlacedPin], wired: set) -> None:
    """Every pin position no drawn wire reaches: supply symbol, net label or no-connect mark."""
    by_point: dict[tuple[int, int], list[PlacedPin]] = {}
    for pin in placed:
        by_point.setdefault(pin.point, []).append(pin)
    for point, stacked in by_point.items():
        nets = {pin.net for pin in stacked}
        assert len(nets) == 1, f"{[pin.name for pin in stacked]} share one spot on the symbol but not one net"
        net, first = nets.pop(), stacked[0]
        drawing.pin_points.append(point)
        if net == NO_NET:
            if first.pin.kind != "no_connect":
                drawing.items.append(f'(no_connect (at {_mm(point[0])} {_mm(point[1])}) (uuid "{_uuid(first.name + "/nc")}"))')
            continue
        drawing.claim(point, net)
        if point in wired:
            continue
        end = (point[0] + first.outward[0] * STUB, point[1] + first.outward[1] * STUB)
        drawing.wire(net, point, end)
        if net in _POWER_SYMBOL:
            drawing.power(library.get(_POWER_SYMBOL[net]), net, end)
        else:
            drawing.label(net, end, first.outward)


def _draw_block(drawing: Drawing, block: Block, sheet: Sheet, library: SymbolLibrary) -> None:
    parts = {part.ref: part for part in sheet.parts}
    placed: list[PlacedPin] = []
    for place in block.places:
        part = parts[place.ref]
        symbol = library.get(part.symbol)
        check_part_against_symbol(part, symbol, sheet.derived_footprints)
        placed += _place_part(drawing, part, symbol, place, (block.x + place.x, block.y + place.y))
    wired = _draw_wires(drawing, block, {pin.name: pin for pin in placed})
    for rail in block.rails:
        drawing.power(library.get(_POWER_SYMBOL[rail.net]), rail.net, (block.x + rail.point[0], block.y + rail.point[1]))
    for flag in block.flags:
        point = (block.x + flag.point[0], block.y + flag.point[1])
        assert point in drawing.net_at, f"{block.title}: power flag at {flag.point} touches nothing"
        drawing.power(library.get(_FLAG_SYMBOL), drawing.net_at[point], point)
    _connect_by_rule(drawing, library, placed, wired)
    drawing.items.append(_text(block.title, block.x + 1, block.y + 3, 2.0, bold=True))
    drawing.items += [_text(note.text, block.x + note.x, block.y + note.y, 1.27) for note in block.notes]
    drawing.items.append(
        f'(rectangle (start {_mm(block.x)} {_mm(block.y)}) (end {_mm(block.x + block.width)} {_mm(block.y + block.height)}) '
        f'(stroke (width 0.15) (type dash)) (fill (type none)) (uuid "{_uuid("frame/" + block.title)}"))')


def _text(text: str, x: float, y: float, size: float, bold: bool = False) -> str:
    weight = " (bold yes)" if bold else ""
    return (f'(text "{text}" (exclude_from_sim no) {_at((x, y))} '
            f'(effects (font (size {size} {size}){weight}) (justify left bottom)) (uuid "{_uuid("text/" + text)}"))')


# --- wires: split where another wire or a pin ends on them, dot where three meet --------------

def _strictly_inside(point: tuple[int, int], start: tuple[int, int], end: tuple[int, int]) -> bool:
    (x, y), (x1, y1), (x2, y2) = point, start, end
    if x1 == x2 == x:
        return min(y1, y2) < y < max(y1, y2)
    if y1 == y2 == y:
        return min(x1, x2) < x < max(x1, x2)
    return False


def split_segments(segments: list, ends: set) -> list:
    """Cuts every wire at each point where something ends on it. KiCad joins wires at their ends."""
    pieces = []
    for start, end in segments:
        cuts = sorted(point for point in ends if _strictly_inside(point, start, end))
        if start > end:
            cuts.reverse()
        chain = [start, *cuts, end]
        pieces += list(zip(chain, chain[1:]))
    return pieces


def junctions(pieces: list, pin_points: list) -> list:
    """Points where three or more wire ends and pins meet."""
    count: dict[tuple[int, int], int] = {}
    for point in [end for piece in pieces for end in piece] + list(pin_points):
        count[point] = count.get(point, 0) + 1
    return sorted(point for point, meeting in count.items() if meeting >= 3)


def _wire_items(drawing: Drawing) -> list[str]:
    ends = {end for segment in drawing.segments for end in segment} | set(drawing.pin_points)
    pieces = split_segments(drawing.segments, ends)
    items = [
        f'(wire (pts (xy {_mm(start[0])} {_mm(start[1])}) (xy {_mm(end[0])} {_mm(end[1])})) '
        f'(stroke (width 0) (type default)) (uuid "{_uuid(f"wire/{start}/{end}")}"))'
        for start, end in pieces]
    items += [f'(junction (at {_mm(x)} {_mm(y)}) (diameter 0) (color 0 0 0 0) (uuid "{_uuid(f"junction/{x}/{y}")}"))'
              for x, y in junctions(pieces, drawing.pin_points)]
    return items


# --- the sheet --------------------------------------------------------------------------------

def draw_sheet(sheet: Sheet, library: SymbolLibrary) -> Drawing:
    """Every part in exactly one block, every block on the paper. The library must hold the sheet's own symbols."""
    refs = [part.ref for part in sheet.parts]
    assert len(refs) == len(set(refs)), f"a part reference repeats: {sorted(refs)}"
    drawn = [place.ref for block in sheet.blocks for place in block.places]
    assert sorted(drawn) == sorted(refs), f"parts not in exactly one block: {set(drawn) ^ set(refs)}"
    drawing = Drawing()
    for block in sheet.blocks:
        assert block.x + block.width <= sheet_layout.SHEET_WIDTH and block.y + block.height <= sheet_layout.SHEET_HEIGHT, (
            f"{block.title} runs off the sheet")
        _draw_block(drawing, block, sheet, library)
    return drawing


def render(drawing: Drawing) -> str:
    lines = [
        f'(kicad_sch (version 20250114) (generator "macropad_obs_gen") (generator_version "9.0") (uuid "{ROOT_UUID}")',
        f'(paper "{sheet_layout.PAPER}")',
        f'(title_block (title "{PROJECT}") (rev "A") (company "worxbend")',
        '(comment 1 "Generated by pcb/gen. Do not edit: change the circuit and run just pcb.")',
        '(comment 2 "Not built. Nothing on this sheet has been measured on hardware."))',
        "(lib_symbols", *(drawing.lib_symbols[lib_id].embedded() for lib_id in sorted(drawing.lib_symbols)), ")",
        *drawing.items,
        *_wire_items(drawing),
        '(sheet_instances (path "/" (page "1")))',
        "(embedded_fonts no))",
    ]
    return "\n".join(lines) + "\n"


def render_symbol_library(own_symbols: tuple[LibSymbol, ...]) -> str:
    """The project's own symbol library: the parts KiCad has no fitting symbol for."""
    lines = [f'(kicad_symbol_lib (version 20241209) (generator "macropad_obs_gen") (generator_version "9.0")',
             *(symbol.embedded(symbol.name) for symbol in own_symbols), ")"]
    return "\n".join(lines) + "\n"


def symbol_library_table(lib_ids: list[str]) -> str:
    """The project's own symbols, and the KiCad libraries the sheet uses, so the rule check can compare
    every symbol on the sheet with its library even on a machine where KiCad was never set up."""
    libraries = sorted({lib_id.split(":")[0] for lib_id in lib_ids} - {PROJECT})
    lines = ["(sym_lib_table", "  (version 7)",
             f'  (lib (name "{PROJECT}")(type "KiCad")(uri "${{KIPRJMOD}}/{PROJECT}.kicad_sym")(options "")'
             '(descr "Generated by pcb/gen/schematic.py"))']
    lines += [f'  (lib (name "{name}")(type "KiCad")(uri "${{KICAD9_SYMBOL_DIR}}/{name}.kicad_sym")(options "")(descr ""))'
              for name in libraries]
    return "\n".join(lines) + "\n)\n"


FOOTPRINT_LIBRARY_TABLE = f"""\
(fp_lib_table
  (version 7)
  (lib (name "{PROJECT}")(type "KiCad")(uri "${{KIPRJMOD}}/../lib/{PROJECT}.pretty")(options "")(descr "Project footprints"))
)
"""


def write(kicad_dir: Path, sheet: Sheet, symbol_dir: Path = KICAD_SYMBOLS) -> None:
    """The schematic, its symbol library and the two library tables KiCad needs to find the project's own parts."""
    library = SymbolLibrary(symbol_dir)
    for symbol in sheet.own_symbols:
        library.add(symbol)
    drawing = draw_sheet(sheet, library)
    (kicad_dir / f"{PROJECT}.kicad_sch").write_text(render(drawing))
    (kicad_dir / f"{PROJECT}.kicad_sym").write_text(render_symbol_library(sheet.own_symbols))
    (kicad_dir / "sym-lib-table").write_text(symbol_library_table(list(drawing.lib_symbols)))
    (kicad_dir / "fp-lib-table").write_text(FOOTPRINT_LIBRARY_TABLE)


def nets_by_pin(parts: tuple[SheetPart, ...]) -> dict[str, str]:
    """"U1.5" -> net, for every pin that has a net. What the exported netlist must say."""
    return {f"{part.ref}.{pad}": net for part in parts for pad, net in part.nets.items() if net != NO_NET}
