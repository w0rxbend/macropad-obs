# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The M2 screw seats (board.toml [screws]; owner 2026-11-21, open question 3). One screw per [pcb]
hole goes up from below: countersunk in the plate's outer face, through the standoff and the PCB,
into a boss that hangs from the deck underside to the PCB top face and clamps the board.

Each boss is a round post of [screws] boss_diameter. It joins every cavity wall within its radius
plus merge_reach, through a web as wide as the post, and each place a web meets a wall is rounded
by [pcb] boss_merge_fillet: no slot narrower than a cutter is left between a post and a wall.

The cnc shell (as board.toml draws it) gets a blind tap drill in each boss; the print shell widens
it to a heat-set insert pocket. The plate's countersinks are in bottom.py."""

from functools import reduce
from operator import add

from build123d import Circle, Cylinder, Pos, Rectangle, RectangleRounded, extrude, fillet

from obs_case import bottom
from obs_case.spec import LAYOUT

OVERRUN = 0.5  # mm a tool or a web runs past the faces it meets, so no face is left coplanar
ON_EDGE = 1e-4  # mm; a vertex this close to a boundary lies on it


def _union(solids):
    return reduce(add, solids)


def radius():
    return LAYOUT.screws.boss_diameter / 2


def walls(hole):
    """The cavity walls a boss at `hole` joins: (axis, wall coordinate, side) for x and y, side -1 for
    the low wall and +1 for the high one."""
    x_low, y_low, width, depth = bottom.cavity_rect()
    reach = radius() + LAYOUT.screws.merge_reach
    found = []
    for axis, centre, low, high in (("x", hole[0], x_low, x_low + width), ("y", hole[1], y_low, y_low + depth)):
        if centre - low <= reach:
            found.append((axis, low, -1))
        elif high - centre <= reach:
            found.append((axis, high, 1))
    return found


def _span(centre, wall, side):
    """The coordinate range from a boss centre out past its wall."""
    end = wall + side * OVERRUN
    return (min(centre, end), max(centre, end))


def _rect(x_range, y_range):
    (x_low, x_high), (y_low, y_high) = x_range, y_range
    return Pos((x_low + x_high) / 2, (y_low + y_high) / 2) * Rectangle(x_high - x_low, y_high - y_low)


def boss_plan(hole):
    """The plan of one boss: the post, a web to each wall it joins (a corner block when it joins
    two), the wall material round the joins, and a fillet at each place a web meets a wall."""
    x, y = hole
    r = radius()
    joined = {axis: (wall, side) for axis, wall, side in walls(hole)}
    pieces = [Pos(x, y) * Circle(r)]
    if "x" in joined:
        pieces.append(_rect(_span(x, *joined["x"]), (y - r, y + r)))
    if "y" in joined:
        pieces.append(_rect((x - r, x + r), _span(y, *joined["y"])))
    if len(joined) == 2:
        pieces.append(_rect(_span(x, *joined["x"]), _span(y, *joined["y"])))
    # The wall itself, from the cavity edge out past the webs' ends: the joins become inside
    # corners of the plan, which the fillet rounds.
    reach = r + LAYOUT.screws.merge_reach + OVERRUN
    window = _rect((x - reach, x + reach), (y - reach, y + reach))
    cavity = bottom.cavity_rect()
    corner = LAYOUT.pcb.corner_radius + LAYOUT.body.pcb_clearance
    bay = Pos(cavity[0] + cavity[2] / 2, cavity[1] + cavity[3] / 2) * RectangleRounded(cavity[2], cavity[3], corner)
    plan = _union(pieces) + (window - bay)
    joins = [vertex for vertex in plan.vertices()
             if _on_bay_edge(vertex, cavity) and not _on_window_edge(vertex, (x, y), reach)]
    if joins:
        plan = fillet(joins, LAYOUT.pcb.boss_merge_fillet)
    return plan


def _on_bay_edge(vertex, cavity):
    x_low, y_low, width, depth = cavity
    return (min(abs(vertex.X - x_low), abs(vertex.X - (x_low + width))) < ON_EDGE
            or min(abs(vertex.Y - y_low), abs(vertex.Y - (y_low + depth))) < ON_EDGE)


def _on_window_edge(vertex, centre, reach):
    return (abs(abs(vertex.X - centre[0]) - reach) < ON_EDGE
            or abs(abs(vertex.Y - centre[1]) - reach) < ON_EDGE)


def bosses():
    """Every boss, from the PCB top face to the deck underside: a solid the shell keeps."""
    stack = LAYOUT.stack
    return _union(Pos(0, 0, stack.pcb_top) * extrude(boss_plan(hole), amount=stack.deck_underside - stack.pcb_top)
                  for hole in LAYOUT.pcb.holes)


def _blind(diameter, depth):
    """A round hole at each [pcb] hole, from below the boss foot up to `depth` above the PCB top."""
    z_low, z_high = LAYOUT.stack.pcb_top - OVERRUN, LAYOUT.stack.pcb_top + depth
    return _union(Pos(x, y, (z_low + z_high) / 2) * Cylinder(diameter / 2, z_high - z_low)
                  for x, y in LAYOUT.pcb.holes)


def tap_drills():
    """The cnc seat: a blind tap drill in each boss ([screws] cnc)."""
    cnc = LAYOUT.screws.cnc
    return _blind(cnc.tap_drill, cnc.drill_depth)


def insert_pockets():
    """The print seat: a heat-set insert pocket in each boss ([screws] print)."""
    seat = LAYOUT.screws.print
    pocket_radius, depth = seat.pocket
    return _blind(2 * pocket_radius, depth)


def screw_tip():
    """z of the screw tip, its head flush with the plate's outer face."""
    return bottom.outer_face() + LAYOUT.screws.length


def problems():
    """Where the bought screw, the tapped thread and the insert pocket disagree."""
    screws, stack = LAYOUT.screws, LAYOUT.stack
    seat, cnc = getattr(screws, "print"), screws.cnc
    tip = screw_tip() - stack.pcb_top
    found = []
    if tip > cnc.thread_depth:
        found.append(f"screw tip {tip:.2f} above the boss foot runs past the {cnc.thread_depth} thread")
    pocket_depth = seat.pocket[1]
    if tip > pocket_depth:
        found.append(f"screw tip {tip:.2f} runs past the {pocket_depth} insert pocket")
    if tip < seat.insert_length:
        found.append(f"screw tip {tip:.2f} stops inside the {seat.insert_length} insert")
    if cnc.drill_depth <= cnc.thread_depth:
        found.append("tap drill no deeper than its thread: no plain bottom")
    deck_room = stack.deck_underside - stack.pcb_top
    for name, depth in (("tap drill", cnc.drill_depth), ("insert pocket", pocket_depth)):
        if depth >= deck_room:
            found.append(f"{name} {depth} reaches the deck underside")
    if bottom.countersink_depth() >= LAYOUT.bottom_plate.thickness:
        found.append("countersink deeper than the plate")
    return found
