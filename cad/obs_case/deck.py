# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The deck of the style A top shell: the key well over the MX plate, two lens recesses with their
windows, the button cap holes and the knob bushing holes. Each cut goes through body.cut, so a cut
that fails stops the build.

Sizes and places come from board.toml: [keys], [buttons], [knobs], [window], the two display
tables and [stack]. Fits that need a coupon stay MEASURE there."""

from functools import reduce
from operator import add

from build123d import Box, Cylinder, Pos

from obs_case import body
from obs_case.spec import LAYOUT

OVERRUN = 0.5  # mm a through-cut tool runs past the faces it opens, so no face is left coplanar


def panels():
    """The big and the narrow display tables."""
    return LAYOUT.big_display, LAYOUT.narrow_display


def grown(rect, by):
    """A [x, y, width, depth] rectangle grown by `by` on every side."""
    x, y, width, depth = rect
    return [x - by, y - by, width + 2 * by, depth + 2 * by]


def key_well():
    """The well round all nine keycaps, each cap grown by well_clearance, as [x, y, width, depth]."""
    keys = LAYOUT.keys
    half = keys.keycap / 2 + keys.well_clearance
    x_low, y_low = min(keys.x) - half, min(keys.y) - half
    return [x_low, y_low, max(keys.x) + half - x_low, max(keys.y) + half - y_low]


def lens_recess(panel):
    """The lens recess of one display: its lens opening grown by the ledge."""
    return grown(panel.lens_opening, LAYOUT.window.lens_ledge)


def button_hole():
    """(width, depth, corner radius) of one cap hole: the cap plus hole_clearance a side."""
    buttons = LAYOUT.buttons
    width, depth = buttons.cap
    clearance = buttons.hole_clearance
    return width + 2 * clearance, depth + 2 * clearance, buttons.cap_corner_radius + clearance


def plate_block():
    """The MX plate under the well, plate_margin past it on each side, up to the deck underside.
    It stays out of the cavity, so the well walls stand on it."""
    keys, stack = LAYOUT.keys, LAYOUT.stack
    rect = grown(key_well(), keys.plate_margin)
    return body.prism(rect, keys.well_corner_radius + keys.plate_margin, stack.mx_plate_underside,
                      stack.deck_underside)


def top_shell():
    """The finished top shell: the slab, its cavity and every deck cut."""
    part = body.shell(plate_block())
    for name, tool in _cuts():
        part = body.cut(part, tool, name)
    return part


def _cuts():
    return [
        ("key well", _key_well_tool()),
        ("plate holes", _plate_hole_tools()),
        ("lens recesses", _union(_recess_tool(panel) for panel in panels())),
        ("windows", _union(_window_tool(panel) for panel in panels())),
        ("button holes", _button_hole_tools()),
        ("knob holes", _knob_hole_tools()),
    ]


def _union(tools):
    return reduce(add, tools)


def _key_well_tool():
    stack = LAYOUT.stack
    return body.flared_prism(key_well(), LAYOUT.keys.well_corner_radius, stack.mx_plate_top,
                             stack.deck_top, LAYOUT.body.opening_chamfer)


def _plate_hole_tools():
    keys, stack = LAYOUT.keys, LAYOUT.stack
    z_low, z_high = stack.mx_plate_underside - OVERRUN, stack.mx_plate_top + OVERRUN
    side = keys.plate_hole
    return _union(Pos(x, y, (z_low + z_high) / 2) * Box(side, side, z_high - z_low)
                  for x in keys.x for y in keys.y)


def _recess_tool(panel):
    stack = LAYOUT.stack
    return body.flared_prism(lens_recess(panel), LAYOUT.window.lens_recess_corner_radius,
                             stack.lens_recess_floor, stack.deck_top, LAYOUT.body.opening_chamfer)


def _window_tool(panel):
    stack = LAYOUT.stack
    return body.prism(panel.lens_opening, LAYOUT.window.window_corner_radius,
                      stack.deck_underside - OVERRUN, stack.lens_recess_floor + OVERRUN)


def _through_deck():
    stack = LAYOUT.stack
    return stack.deck_underside - OVERRUN, stack.deck_top + OVERRUN


def _button_hole_tools():
    width, depth, corner = button_hole()
    z_low, z_high = _through_deck()
    y = LAYOUT.buttons.y
    return _union(body.prism([x - width / 2, y - depth / 2, width, depth], corner, z_low, z_high)
                  for x in LAYOUT.buttons.x)


def _knob_hole_tools():
    knobs = LAYOUT.knobs
    z_low, z_high = _through_deck()
    return _union(Pos(knobs.x, y, (z_low + z_high) / 2) * Cylinder(knobs.bushing_hole / 2, z_high - z_low)
                  for y in knobs.y)
