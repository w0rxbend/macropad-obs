# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The non-metal back-wall insert (D7, spec 6 and 7): it replaces the back wall from x 56.0 to the
corner arc for the full case height, plate outer face to deck top, and its floor tongue fills the
plate's `antenna_relief`, so the PCB antenna sees no metal below or behind it.

The wall part is the slab itself cut to the insert outline, so it carries the outer face and the
top chamfer. Below the slab it runs down through the plate's insert footprint and meets the tongue
there. The shell gets the matching pocket (`shell()`), and the [usb] opening with the outside
pocket that thins the wall round it, over the plate's USB notch (bottom.py).

Modelled line to line: the insert fit, its fixing and its material stay MEASURE (spec 6).
Colour per open question 1 (spec 15): black until the owner answers."""

from build123d import Axis, Color, fillet

from obs_case import body, bottom, deck
from obs_case.carriers import block
from obs_case.shop import shop_radius
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


def usb_mouth_z():
    """z of the USB mouth centre: the receptacle hangs under the PCB ([usb] face bottom)."""
    return LAYOUT.stack.pcb_bottom - LAYOUT.usb.height / 2


def thinned_face_y():
    """y of the back wall's outside face where [usb] back_wall_thinned leaves it `to` thick."""
    cavity = bottom.cavity_rect()
    return cavity[1] + cavity[3] + LAYOUT.usb.back_wall_thinned.to


def _usb_tool():
    """[usb] opening through the back wall, centred on the mouth, and the outside pocket of
    back_wall_thinned area round it, down to thinned_face_y(). Both run out below the shell.
    The pocket's two inside vertical corners are drawn round, at the JLCCNC radius for a cutter
    from the shell's bottom face: a dog-bone there would mill into the thinned wall behind it."""
    usb, case_back = LAYOUT.usb, LAYOUT.body.outline[1] + LAYOUT.body.outline[3]
    inside = thinned_face_y() - usb.back_wall_thinned.to
    mouth_z = usb_mouth_z()
    width, height = usb.opening
    area_width, area_height = usb.back_wall_thinned.area
    opening = block([usb.x - width / 2, inside - OVERRUN, width, case_back - inside + 2 * OVERRUN],
                    mouth_z - height / 2, mouth_z + height / 2)
    pocket_top = mouth_z + area_height / 2
    pocket = block([usb.x - area_width / 2, thinned_face_y(), area_width, case_back + OVERRUN - thinned_face_y()],
                   mouth_z - area_height / 2, pocket_top)
    inside_corners = pocket.edges().filter_by(Axis.Z).group_by(Axis.Y)[0]
    pocket = fillet(inside_corners, shop_radius(pocket_top - LAYOUT.stack.bottom_plate_inside))
    return opening + pocket


def shell():
    """The finished top shell: deck.top_shell() with the insert pocket and the USB opening cut out
    of the back wall."""
    part = body.cut(deck.top_shell(), _wall_tool(), "insert pocket")
    return body.cut(part, _usb_tool(), "USB opening")
