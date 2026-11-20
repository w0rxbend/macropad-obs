# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Display carriers and foam frames (spec 7, layout rev 3). Each display sits on a printed carrier
ring that stands on the PCB top face and holds the panel up against a closed foam ring under the
deck. Each solid goes through body.cut, so a cut that fails stops the build.

Sizes come from board.toml [display_carrier], [foam_frame], [stack] and the two display tables.
The carrier height and the foam stock stay MEASURE there; this file models the nominal stack."""

from build123d import Box, Pos

from obs_case import body
from obs_case.spec import LAYOUT

NAMES = ("big", "narrow")  # [display_carrier] keys; each pairs with the [<name>_display] table
OVERRUN = 0.5  # mm a cut tool runs past the faces it opens, so no face is left coplanar


def panel(name):
    """The [<name>_display] table of the display a carrier holds."""
    return getattr(LAYOUT, f"{name}_display")


def block(rect, z_low, z_high):
    """A square-cornered box on a [x, y, width, depth] rectangle, from z_low to z_high."""
    x, y, width, depth = rect
    return Pos(x + width / 2, y + depth / 2, (z_low + z_high) / 2) * Box(width, depth, z_high - z_low)


def _tool(rect, z_low, z_high):
    """`block` run OVERRUN past z_low and z_high: a cut tool through the full height."""
    return block(rect, z_low - OVERRUN, z_high + OVERRUN)


def _across_wall(rect):
    """A [x, y, width, depth] wall gap grown OVERRUN front and back, past both wall faces."""
    x, y, width, depth = rect
    return [x, y - OVERRUN, width, depth + 2 * OVERRUN]


def carrier(name):
    """The carrier ring: outer minus inner, z pcb_top to its height, with the tail gap cut."""
    ring = getattr(LAYOUT.display_carrier, name)
    z_low = LAYOUT.stack.pcb_top
    z_high = z_low + ring.height
    part = body.cut(block(ring.outer, z_low, z_high), _tool(ring.inner, z_low, z_high),
                    f"{name} carrier hollow")
    return body.cut(part, _tool(_across_wall(ring.tail_gap), z_low, z_high), f"{name} carrier tail gap")


def foam_frame(name):
    """The foam ring as installed: module outline minus lens opening, its top on the deck underside
    and its thickness the installed (squeezed) one."""
    display = panel(name)
    z_high = LAYOUT.stack.deck_underside
    z_low = z_high - LAYOUT.foam_frame.installed
    return body.cut(block(display.outline, z_low, z_high), _tool(display.lens_opening, z_low, z_high),
                    f"{name} foam opening")
