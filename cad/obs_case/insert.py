# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The non-metal back-wall insert (D7, spec 6 and 7): it replaces the back wall from x 56.0 to the
corner arc for the full case height, plate outer face to deck top, and its floor tongue fills the
plate's `antenna_relief`, so the PCB antenna sees no metal below or behind it.

The wall part is the slab itself cut to the insert outline, so it carries the outer face and the
top chamfer. Below the slab it runs down through the plate's insert footprint and meets the tongue
there. The shell gets the matching pocket (`shell()`).

Modelled line to line: the insert fit, its fixing and its material stay MEASURE (spec 6).
Colour per open question 1 (spec 15): black until the owner answers."""

from build123d import Color

from obs_case import body, bottom, deck
from obs_case.carriers import block
from obs_case.spec import LAYOUT

OVERRUN = 0.5  # mm a cut tool runs past the faces it opens, so no face is left coplanar
COLOUR = "black"  # open question 1, default black; [antenna] insert.material names the plastic
MEASURE = ("insert fit (modelled line to line)", "insert fixing", "insert material")


def _wall_tool():
    """The insert outline from below the slab to above it, run out through the back face."""
    stack = LAYOUT.stack
    return block(bottom.insert_footprint(), stack.bottom_plate_inside - OVERRUN, stack.deck_top + OVERRUN)


def insert():
    """The insert: the slab's wall and deck rim over the outline, the foot through the plate, and
    the tongue in `antenna_relief`. One solid, coloured COLOUR."""
    below_plate = bottom.outer_face() - OVERRUN
    foot_and_tongue = bottom.antenna_opening(below_plate, LAYOUT.stack.bottom_plate_inside) & bottom.blank()
    part = (body.slab() & _wall_tool()) + foot_and_tongue
    part.color = Color(COLOUR)
    part.label = "back-wall insert"
    return part


def shell():
    """The finished top shell: deck.top_shell() with the insert pocket cut out of the back wall."""
    return body.cut(deck.top_shell(), _wall_tool(), "insert pocket")
