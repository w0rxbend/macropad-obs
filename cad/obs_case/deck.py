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


def lens_recess(panel, grow=0.0):
    """The lens recess of one display: its lens opening grown by the ledge, plus `grow` a side."""
    return grown(panel.lens_opening, LAYOUT.window.lens_ledge + grow)


def button_hole(clearance=None):
    """(width, depth, corner radius) of one cap hole: the cap plus `clearance` a side, by default
    [buttons] hole_clearance."""
    buttons = LAYOUT.buttons
    width, depth = buttons.cap
    if clearance is None:
        clearance = buttons.hole_clearance
    return width + 2 * clearance, depth + 2 * clearance, buttons.cap_corner_radius + clearance


def plate_block():
    """The MX plate under the well, plate_margin past it on each side, up to the deck underside.
    It stays out of the cavity, so the well walls stand on it. Where it reaches the left cavity wall
    it runs square into the wall with a concave fillet of the cavity corner radius each side: its
    own corner arc would leave an acute wedge there that no cutter reaches (report 11 CNC rules)."""
    keys, stack = LAYOUT.keys, LAYOUT.stack
    x, y, width, depth = grown(key_well(), keys.plate_margin)
    corner = keys.well_corner_radius + keys.plate_margin
    wall_x = -LAYOUT.body.pcb_clearance  # the left cavity face
    z_low, z_high = stack.mx_plate_underside, stack.deck_underside
    if x >= wall_x + corner:
        return body.prism([x, y, width, depth], corner, z_low, z_high)
    right = x + width
    x = wall_x - corner  # the corner arcs now sit inside the wall, where the cavity tool never cuts
    block = body.prism([x, y, right - x, depth], corner, z_low, z_high)
    return block + _wall_fillet(wall_x, y, -1, z_low, z_high) + _wall_fillet(wall_x, y + depth, 1, z_low, z_high)


def _wall_fillet(wall_x, face_y, side, z_low, z_high):
    """A concave fillet of the cavity corner radius between the wall face x = wall_x and the block
    face y = face_y, on the side of that face given by `side` (-1 in front, +1 behind)."""
    radius = LAYOUT.pcb.corner_radius + LAYOUT.body.pcb_clearance
    y_low = face_y if side > 0 else face_y - radius
    centre_y = face_y + side * radius
    z_mid = (z_low + z_high) / 2
    piece = Pos(wall_x + radius / 2, y_low + radius / 2, z_mid) * Box(radius, radius, z_high - z_low)
    return piece - Pos(wall_x + radius, centre_y, z_mid) * Cylinder(radius, z_high - z_low + 2 * OVERRUN)


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
        ("lens recesses", _union(recess_tool(panel) for panel in panels())),
        ("windows", _union(_window_tool(panel) for panel in panels())),
        ("button holes", button_hole_tools()),
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


def recess_tool(panel, grow=0.0):
    """The cut tool of one lens recess, grown by `grow` a side, its corner grown with it."""
    stack = LAYOUT.stack
    return body.flared_prism(lens_recess(panel, grow), LAYOUT.window.lens_recess_corner_radius + grow,
                             stack.lens_recess_floor, stack.deck_top, LAYOUT.body.opening_chamfer)


def _window_tool(panel):
    stack = LAYOUT.stack
    return body.prism(panel.lens_opening, LAYOUT.window.window_corner_radius,
                      stack.deck_underside - OVERRUN, stack.lens_recess_floor + OVERRUN)


def _through_deck():
    stack = LAYOUT.stack
    return stack.deck_underside - OVERRUN, stack.deck_top + OVERRUN


def button_hole_tools(clearance=None):
    """The four cap hole cut tools, each cap plus `clearance` a side (button_hole)."""
    width, depth, corner = button_hole(clearance)
    z_low, z_high = _through_deck()
    y = LAYOUT.buttons.y
    return _union(body.prism([x - width / 2, y - depth / 2, width, depth], corner, z_low, z_high)
                  for x in LAYOUT.buttons.x)


def _knob_hole_tools():
    knobs = LAYOUT.knobs
    z_low, z_high = _through_deck()
    return _union(Pos(knobs.x, y, (z_low + z_high) / 2) * Cylinder(knobs.bushing_hole / 2, z_high - z_low)
                  for y in knobs.y)
