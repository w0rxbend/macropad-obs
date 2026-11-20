# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The `print` and `cnc` variants of the case (spec 9; report 11 section 4). One source: the shell,
the bottom plate and the back-wall insert as board.toml draws them are the cnc case. A variant
changes fits only:

- print: each lens recess grows by print.lens_fit - cnc.lens_fit a side, and each cap hole takes
  print.hole_clearance a side ([variants]).
- cnc: every square inside vertical corner a round cutter cannot reach gets a dog-bone relief
  (report 11: MX cut-outs, as macropad did), sized by the JLCCNC rule R = depth / 10 + 0.5 [J1] on
  the depth from the face the cutter comes in from. Each corner carries the setup that cuts it,
  from the part's SETUPS, and drawings.py lists the reliefs by that same setup. Where a relief
  opens the insert's pocket, the insert carries a matching lobe, so the two still meet line to
  line.

The corner finder is a port of macropad/cad/macropad_case/measure.py `sharp_internal_corners`;
checks.py counts what it finds on the finished parts."""

from dataclasses import dataclass
from functools import cache, reduce
from math import cos, pi, sin
from operator import add

from build123d import Cylinder, GeomType, Pos, Vector

from obs_case import body, bottom, deck, insert
from obs_case.shop import shop_radius
from obs_case.spec import LAYOUT

PRINT, CNC = "print", "cnc"
VARIANTS = (PRINT, CNC)
PROBE = 0.02  # mm from a vertical edge to the probes round it
PROBES_PER_EDGE = 8
SHARP_SHARE = 0.6  # an edge with more of its probes in material is an inside corner
SQUARE_PROBES = 6  # probes in material round a 90 degree inside corner: three quadrants of eight
MIN_EDGE = 0.05  # mm; shorter vertical edges are boolean slivers
TOUCHING = 1e-6  # mm; a lobe this close to the insert fills its pocket
ABOVE, BELOW = "from above", "from below"  # the side a setup's cutter comes in from
# The milled parts as board.toml draws them, and their setups in the CNC drawing's order: the shell
# underside up then top up (report 11 setups 1 and 2), the plate inside face up only.
MILLED_PARTS = {"shell": insert.shell, "plate": bottom.plate}
SETUPS = {"shell": (BELOW, ABOVE), "plate": (ABOVE,)}


@dataclass(frozen=True)
class Corner:
    """A sharp inside vertical corner: its middle, z span, unit direction into the air between its
    two walls, probes in material, the setup that cuts it (ABOVE or BELOW, None if none of the
    part's setups reaches it) and the depth its cutter plunges there."""

    middle: Vector
    z_low: float
    z_high: float
    toward_air: Vector
    in_material: int
    setup: str | None
    depth: float

    @property
    def square(self):
        """True for a 90 degree corner, which a dog-bone clears; an acute one needs new geometry."""
        return self.in_material <= SQUARE_PROBES

    @property
    def relief_radius(self):
        return shop_radius(self.depth)


def fits(variant):
    """The [variants] row of `variant`: lens_fit and hole_clearance, mm a side."""
    return getattr(LAYOUT.variants, variant)


@cache
def parts(variant):
    """{"shell", "plate", "insert"} of `variant`. Each cut goes through body.cut."""
    if variant == PRINT:
        return _print_parts()
    if variant == CNC:
        return _cnc_parts()
    raise ValueError(f"variant {variant!r}, expected one of {VARIANTS}")


def _union(solids):
    return reduce(add, solids)


def _print_parts():
    grow = fits(PRINT).lens_fit - fits(CNC).lens_fit
    shell = body.cut(insert.shell(), _union(deck.recess_tool(panel, grow) for panel in deck.panels()),
                     "print lens recesses")
    shell = body.cut(shell, deck.button_hole_tools(fits(PRINT).hole_clearance), "print cap holes")
    return {"shell": shell, "plate": bottom.plate(), "insert": insert.insert()}


@cache
def drawn(name):
    """The milled part `name` ("shell" or "plate") as board.toml draws it, before any relief."""
    return MILLED_PARTS[name]()


@cache
def relief_corners(name):
    """The square inside corners of drawn(name), each with its setup: where the dog-bones go."""
    return tuple(corner for corner in inside_corners(drawn(name), SETUPS[name]) if corner.square)


def _cnc_parts():
    shell, shell_lobes = relieved("shell")
    plate, plate_lobes = relieved("plate")
    part = insert.insert()
    lobes = [lobe for lobe in shell_lobes + plate_lobes if lobe.distance_to(part) <= TOUCHING]
    filled = _union([part, *lobes]) if lobes else part
    filled.color, filled.label = part.color, part.label
    return {"shell": shell, "plate": plate, "insert": filled}


def relieved(name):
    """drawn(name) with a dog-bone at each square inside corner, and the pieces those reliefs
    removed. Acute corners are left as they are, for checks.py to report."""
    part = drawn(name)
    tools = [_relief_tool(corner) for corner in relief_corners(name)]
    if not tools:
        return part, []
    # A parallel boolean returns its pieces in any order, and the insert's union follows the order:
    # sort them, so the cnc insert and its exports repeat byte for byte (task 6.5).
    lobes = sorted((piece for tool in tools for piece in (part & tool).solids()),
                   key=lambda piece: tuple(piece.center()))
    return body.cut(part, _union(tools), f"{name} corner reliefs"), lobes


def _relief_tool(corner):
    """A cylinder of the corner's relief radius, its centre that far into the air along the
    bisector, so its edge passes through the corner. It spans the corner's own z range."""
    radius = corner.relief_radius
    centre = corner.middle + corner.toward_air * radius
    height = corner.z_high - corner.z_low
    return Pos(centre.X, centre.Y, (corner.z_low + corner.z_high) / 2) * Cylinder(radius, height)


def inside_corners(part, setups):
    """Every vertical straight edge of `part` where two walls meet without a radius: most probes on
    a small circle round its middle are in material. Each is cut by one of `setups`."""
    found = []
    for edge in part.edges().filter_by(GeomType.LINE):
        start, end = edge.position_at(0), edge.position_at(1)
        if edge.length < MIN_EDGE or abs(start.X - end.X) > TOUCHING or abs(start.Y - end.Y) > TOUCHING:
            continue
        middle = edge.position_at(0.5)
        directions = [Vector(cos(angle), sin(angle), 0)
                      for angle in (2 * pi * (step + 0.5) / PROBES_PER_EDGE for step in range(PROBES_PER_EDGE))]
        air = [direction for direction in directions if not part.is_inside(middle + direction * PROBE)]
        in_material = PROBES_PER_EDGE - len(air)
        if in_material <= PROBES_PER_EDGE * SHARP_SHARE or not air:
            continue
        toward_air = sum(air, Vector()).normalized()
        z_low, z_high = min(start.Z, end.Z), max(start.Z, end.Z)
        setup, depth = _cutting_setup(part, middle + toward_air * PROBE, (z_low, z_high), setups)
        found.append(Corner(middle, z_low, z_high, toward_air, in_material, setup, depth))
    return found


def _cutting_setup(part, beside, edge_span, setups):
    """(setup, depth) of the setup in `setups` that finishes the corner with the shortest plunge:
    ABOVE if the corner is open above, from the part's top face; BELOW if open below, from its
    bottom face. Depths run to the part's extreme faces, so they never come out short. A corner no
    setup reaches gives (None, the part's full height)."""
    box = part.bounding_box()
    z_low, z_high = edge_span
    reach = {ABOVE: (z_high + PROBE, box.max.Z - z_low), BELOW: (z_low - PROBE, z_high - box.min.Z)}
    open_to = []
    for setup in setups:
        probe_z, depth = reach[setup]
        if not part.is_inside(Vector(beside.X, beside.Y, probe_z)):
            open_to.append((depth, setup))
    if not open_to:
        return None, box.max.Z - box.min.Z
    depth, setup = min(open_to)
    return setup, depth
