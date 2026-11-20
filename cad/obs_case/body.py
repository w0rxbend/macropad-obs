# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Style A slab (D3, report 17): a flat tub with vertical walls and one 45 degree chamfer round the
top edge. The bottom plate (task 6.3) closes it at stack.bottom_plate_inside.

PCB frame from board.toml: origin at the PCB front-left corner, z = 0 on the PCB top face, mm.
Rectangles are [x, y, width, depth], as board.toml writes them."""

from build123d import Axis, Pos, RectangleRounded, chamfer, extrude

from obs_case.spec import LAYOUT

VOLUME_TOLERANCE = 1e-6  # share of the removed volume; OCCT boolean noise sits far below this


class CutFailed(RuntimeError):
    """A cut removed the wrong volume or broke the solid. The build stops; nothing is kept."""


def _rounded_face(rect, corner_radius, z):
    """A rounded rectangle [x, y, width, depth] lying flat at height z."""
    x, y, width, depth = rect
    return Pos(x + width / 2, y + depth / 2, z) * RectangleRounded(width, depth, corner_radius)


def prism(rect, corner_radius, z_low, z_high):
    """A vertical prism on a rounded rectangle [x, y, width, depth], from z_low to z_high."""
    return extrude(_rounded_face(rect, corner_radius, z_low), amount=z_high - z_low)


def flared_prism(rect, corner_radius, z_low, z_high, flare):
    """`prism` with a 45 degree flare of `flare` mm at its top: a cut tool that chamfers its edge."""
    straight = prism(rect, corner_radius, z_low, z_high - flare)
    return straight + extrude(_rounded_face(rect, corner_radius, z_high - flare), amount=flare, taper=-45)


def cut(solid, tool, name):
    """`solid` minus `tool`. Raises CutFailed unless the result is one valid solid that lost exactly
    the volume the two shared, and that volume is not zero."""
    shared = solid & tool
    removed = sum(piece.volume for piece in shared.solids()) if shared else 0.0
    result = solid - tool
    lost = solid.volume - result.volume
    if removed <= 0.0 or abs(lost - removed) > VOLUME_TOLERANCE * removed:
        raise CutFailed(f"{name}: removed {lost:.4f} mm3, the tool overlaps {removed:.4f} mm3")
    if len(result.solids()) != 1 or not result.is_valid:
        raise CutFailed(f"{name}: left {len(result.solids())} solids, valid {result.is_valid}")
    return result


def slab():
    """The outer slab, deck top to the plate seam, with the top edge chamfered."""
    body, stack = LAYOUT.body, LAYOUT.stack
    outer = prism(body.outline, body.corner_radius, stack.bottom_plate_inside, stack.deck_top)
    return chamfer(outer.edges().group_by(Axis.Z)[-1], body.top_chamfer)


def cavity():
    """The board bay: the PCB outline grown by pcb_clearance, up to the deck underside."""
    pcb, stack = LAYOUT.pcb, LAYOUT.stack
    grow = LAYOUT.body.pcb_clearance
    rect = [-grow, -grow, pcb.width + 2 * grow, pcb.depth + 2 * grow]
    return prism(rect, pcb.corner_radius + grow, stack.bottom_plate_inside, stack.deck_underside)


def shell(keep):
    """The slab hollowed by the cavity, except the solid `keep` (the MX plate block and the pocket
    walls) stays."""
    return cut(slab(), cavity() - keep, "cavity")
