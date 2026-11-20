# SPDX-License-Identifier: CERN-OHL-S-2.0
"""How a schematic sheet is laid out: the types a sheet's blocks are written in. Data only;
schematic.py draws it, and the circuit's own module lists its blocks.

Units are grid steps of 1.27 mm. Inside a block, positions count from the block's top-left corner,
X to the right and Y down. A point is either a pin ("R7.1") or a position (x, y).

What is not listed here is drawn by rule (see schematic.py): a pin on a supply net gets a short
wire and the supply symbol, a pin on a signal net gets a short wire and the net's label, an open
pin gets a no-connect mark.

Copied from macropad-greycode pcb/gen (decision D5), without greycode's blocks.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Place:
    ref: str
    x: int
    y: int
    rotation: int = 0  # degrees counter-clockwise


@dataclass(frozen=True)
class Wire:
    """A chain of straight wires through the points. Every pin on it must be on this net in the circuit."""
    net: str
    points: tuple
    label: tuple | None = None  # (x, y) on the wire, text to the right; (x, y, "left") for text to the left


@dataclass(frozen=True)
class Rail:
    """A supply symbol at this point."""
    net: str
    point: tuple[int, int]


@dataclass(frozen=True)
class Flag:
    """KiCad's PWR_FLAG: tells the rule check that this net is driven from outside the sheet's symbols
    (through the fuse, an inductor or a resistor)."""
    point: tuple[int, int]


@dataclass(frozen=True)
class Note:
    text: str
    x: int
    y: int


@dataclass(frozen=True)
class Block:
    title: str
    x: int
    y: int
    width: int
    height: int
    places: tuple[Place, ...]
    wires: tuple[Wire, ...] = ()
    rails: tuple[Rail, ...] = ()
    flags: tuple[Flag, ...] = ()
    notes: tuple[Note, ...] = ()


PAPER = "A3"
SHEET_WIDTH, SHEET_HEIGHT = 330, 233  # A3 landscape in grid steps
