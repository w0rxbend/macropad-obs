# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The bottom plate (spec 7, report 11 shell split A): a flat plate under the whole body outline,
its inside face at stack.bottom_plate_inside. Standoffs, encoder posts and key ribs stand on it up
to the PCB bottom face. It is cut for the 6 screw holes, the two pinholes, the USB notch, and the
antenna: `antenna_relief` plus the insert's footprint, which the insert (insert.py) fills.

Sizes come from board.toml [bottom_plate], [pcb], [usb], [antenna], [stack] and [screws]: each [pcb]
clearance hole gets a countersink on the outer face for the M2 countersunk screw (screws.py has the
shell side)."""

from functools import reduce
from math import radians, tan
from operator import add

from build123d import Cone, Cylinder, Pos

from obs_case import body
from obs_case.carriers import block
from obs_case.spec import LAYOUT

OVERRUN = 0.5  # mm a cut tool runs past the faces it opens, so no face is left coplanar


def outer_face():
    """z of the plate's outer (bottom) face."""
    return LAYOUT.stack.bottom_plate_inside - LAYOUT.bottom_plate.thickness


def cavity_rect():
    """The board bay in plan, [x, y, width, depth]: the PCB grown by pcb_clearance."""
    pcb, grow = LAYOUT.pcb, LAYOUT.body.pcb_clearance
    return [-grow, -grow, pcb.width + 2 * grow, pcb.depth + 2 * grow]


def bay(z_low, z_high):
    """The board bay with its rounded corners (body.cavity's plan), from z_low to z_high."""
    corner = LAYOUT.pcb.corner_radius + LAYOUT.body.pcb_clearance
    return body.prism(cavity_rect(), corner, z_low, z_high)


def insert_footprint():
    """The insert outline grown OVERRUN out through the back face, so a cut opens the plate edge."""
    x, y, width, depth = LAYOUT.antenna.insert.outline
    return [x, y, width, depth + OVERRUN]


def antenna_opening(z_low, z_high):
    """`antenna_relief` plus the insert footprint, z_low to z_high: the plate cut, the insert's foot."""
    relief = LAYOUT.bottom_plate.antenna_relief
    return block(relief, z_low, z_high) + block(insert_footprint(), z_low, z_high)


def plate():
    """The finished bottom plate: slab, posts, then every cut."""
    part = blank() + _posts()
    for name, tool in _cuts():
        part = body.cut(part, tool, name)
    return part


def blank():
    """The plain plate: the body outline, outer face to inside face, before posts and cuts."""
    case = LAYOUT.body
    return body.prism(case.outline, case.corner_radius, outer_face(), LAYOUT.stack.bottom_plate_inside)


def _union(solids):
    return reduce(add, solids)


def _post(diameter, height, at):
    x, y = at
    z_low = LAYOUT.stack.bottom_plate_inside
    return Pos(x, y, z_low + height / 2) * Cylinder(diameter / 2, height)


def _ribs():
    ribs = LAYOUT.bottom_plate.key_ribs
    x_low, x_high = ribs.x
    z_low = LAYOUT.stack.bottom_plate_inside
    return _union(block([x_low, y - ribs.width / 2, x_high - x_low, ribs.width], z_low, z_low + ribs.height)
                  for y in ribs.y)


def _posts():
    """Standoffs, encoder posts and key ribs, clipped to the board bay: where a standoff reaches past
    the cavity it merges into the wall line instead of running into the shell."""
    plate_table = LAYOUT.bottom_plate
    standoffs, encoders = plate_table.standoffs, plate_table.encoder_posts
    posts = [_post(standoffs.diameter, standoffs.height, at) for at in LAYOUT.pcb.holes]
    posts += [_post(encoders.diameter, encoders.height, at) for at in encoders.at]
    stack = LAYOUT.stack
    return (_union(posts) + _ribs()) & bay(stack.bottom_plate_inside, stack.pcb_bottom + OVERRUN)


def _through(diameter, points):
    """Round holes through the plate and anything standing on it, up to the PCB bottom face."""
    z_low, z_high = outer_face() - OVERRUN, LAYOUT.stack.pcb_bottom + OVERRUN
    return _union(Pos(x, y, (z_low + z_high) / 2) * Cylinder(diameter / 2, z_high - z_low) for x, y in points)


def _usb_notch():
    """The notch in the plate's inside face under the USB opening, from the wall inside face out
    through the back edge."""
    notch, stack = LAYOUT.bottom_plate.usb_notch, LAYOUT.stack
    y_low = cavity_rect()[1] + cavity_rect()[3]
    y_high = LAYOUT.body.outline[1] + LAYOUT.body.outline[3] + OVERRUN
    rect = [LAYOUT.usb.x - notch.width / 2, y_low, notch.width, y_high - y_low]
    return block(rect, stack.bottom_plate_inside - notch.depth, stack.bottom_plate_inside + OVERRUN)


def _cuts():
    pinholes = LAYOUT.bottom_plate.pinholes
    z_low, z_high = outer_face() - OVERRUN, LAYOUT.stack.bottom_plate_inside + OVERRUN
    return [
        ("screw holes", _through(LAYOUT.pcb.hole_diameter, LAYOUT.pcb.holes)),
        ("countersinks", countersinks()),
        ("pinholes", _through(pinholes.diameter, pinholes.at)),
        ("USB notch", _usb_notch()),
        ("antenna relief and insert footprint", antenna_opening(z_low, z_high)),
    ]


def countersink_depth():
    """How far each countersink cone reaches into the plate: from its face diameter to the hole."""
    sink = LAYOUT.screws.countersink
    return (sink.diameter - LAYOUT.pcb.hole_diameter) / 2 / tan(radians(sink.angle / 2))


def countersinks():
    """A countersink cone on the outer face at each [pcb] hole, run OVERRUN out below the face."""
    sink = LAYOUT.screws.countersink
    slope = tan(radians(sink.angle / 2))
    height = countersink_depth() + OVERRUN
    wide, narrow = sink.diameter / 2 + OVERRUN * slope, LAYOUT.pcb.hole_diameter / 2
    z_low = outer_face() - OVERRUN
    return _union(Pos(x, y, z_low + height / 2) * Cone(wide, narrow, height) for x, y in LAYOUT.pcb.holes)
