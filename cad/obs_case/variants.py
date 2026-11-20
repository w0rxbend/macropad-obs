# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The `print` and `cnc` variants of the case (spec 9; report 11 section 4). One source: the shell,
the bottom plate and the back-wall insert as board.toml draws them are the cnc case. A variant
changes fits only:

- print: each lens recess grows by print.lens_fit - cnc.lens_fit a side, and each cap hole takes
  print.hole_clearance a side ([variants]).
- cnc: every square inside vertical corner a round cutter cannot reach gets a dog-bone relief
  (report 11: MX cut-outs, as macropad did), sized by the JLCCNC rule R = depth / 10 + 0.5 [J1] on
  the depth from the face the cutter comes in from. Where a relief opens the insert's pocket, the
  insert carries a matching lobe, so the two still meet line to line.

The corner finder is a port of macropad/cad/macropad_case/measure.py `sharp_internal_corners`;
checks.py counts what it finds on the finished parts."""

from dataclasses import dataclass
from functools import cache, reduce
from math import cos, pi, sin
from operator import add

from build123d import Cylinder, GeomType, Pos, Vector

from obs_case import body, bottom, deck, insert
from obs_case.spec import LAYOUT

PRINT, CNC = "print", "cnc"
VARIANTS = (PRINT, CNC)
PROBE = 0.02  # mm from a vertical edge to the probes round it
PROBES_PER_EDGE = 8
SHARP_SHARE = 0.6  # an edge with more of its probes in material is an inside corner
SQUARE_PROBES = 6  # probes in material round a 90 degree inside corner: three quadrants of eight
MIN_EDGE = 0.05  # mm; shorter vertical edges are boolean slivers
TOUCHING = 1e-6  # mm; a lobe this close to the insert fills its pocket
SHOP_DEPTH_SHARE = 10  # JLCCNC [J1]: inside corner radius >= depth / 10 + 0.5
SHOP_MIN_RADIUS = 0.5


@dataclass(frozen=True)
class Corner:
    """A sharp inside vertical corner: its middle, z span, unit direction into the air between its
    two walls, probes in material, and the depth a cutter reaches it from."""

    middle: Vector
    z_low: float
    z_high: float
    toward_air: Vector
    in_material: int
    depth: float

    @property
    def square(self):
        """True for a 90 degree corner, which a dog-bone clears; an acute one needs new geometry."""
        return self.in_material <= SQUARE_PROBES

    @property
    def relief_radius(self):
        return shop_radius(self.depth)


def shop_radius(depth):
    """The smallest inside corner radius JLCCNC mills at `depth` mm [J1]."""
    return depth / SHOP_DEPTH_SHARE + SHOP_MIN_RADIUS


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


def _cnc_parts():
    shell, shell_lobes = relieved(insert.shell(), "shell")
    plate, plate_lobes = relieved(bottom.plate(), "plate")
    part = insert.insert()
    lobes = [lobe for lobe in shell_lobes + plate_lobes if lobe.distance_to(part) <= TOUCHING]
    filled = _union([part, *lobes]) if lobes else part
    filled.color, filled.label = part.color, part.label
    return {"shell": shell, "plate": plate, "insert": filled}


def relieved(part, name):
    """`part` with a dog-bone at each square inside corner, and the pieces those reliefs removed.
    Acute corners are left as they are, for checks.py to report."""
    tools = [_relief_tool(corner) for corner in inside_corners(part) if corner.square]
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


def inside_corners(part):
    """Every vertical straight edge of `part` where two walls meet without a radius: most probes on
    a small circle round its middle are in material."""
    box = part.bounding_box()
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
        depth = _cutter_depth(part, middle, toward_air, (z_low, z_high), (box.min.Z, box.max.Z))
        found.append(Corner(middle, z_low, z_high, toward_air, in_material, depth))
    return found


def _cutter_depth(part, middle, toward_air, edge_span, part_span):
    """How deep a cutter plunges to finish the corner: from the part's top face when the corner is
    open above, from its bottom face when open below, the shallower if both. Measured to the
    part's extreme faces, so it never comes out short."""
    z_low, z_high = edge_span
    beside = middle + toward_air * PROBE
    depths = []
    if not part.is_inside(Vector(beside.X, beside.Y, z_high + PROBE)):
        depths.append(part_span[1] - z_low)
    if not part.is_inside(Vector(beside.X, beside.Y, z_low - PROBE)):
        depths.append(z_high - part_span[0])
    return min(depths) if depths else part_span[1] - part_span[0]
