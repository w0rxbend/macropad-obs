# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The knob dial on the Alps EC11 shaft (task 6.10; report 08 knob note 5, report 11 section 6).

Ported from the rev 1 dial, `git show d3f75a2:cad/obs_case/geometry.py`: `_knob`, `_knob_seat`,
`_knob_grooves`, `_knob_pointer`, `_knob_setscrew` and `_d_solid`; that commit's numbers.py sizes
now sit in board.toml [knob_dial]. Changed in the port: the 18 mm dial of [knobs] takes narrower
flutes so the lands stay; the set screw hole now reaches the shaft flat (rev 1 stopped 1.3 mm short
of it); the index may not reach the bore; each cut goes through `_cut` (body.cut with exact
volumes), so a failed cut stops the build.

One dial for both variants, turned or printed. Frame: x, y on the shaft axis, z = 0 on the PCB top
face, mm. The shaft flat, the index and the set screw face +y. The shaft fit stays MEASURE.
`python -m obs_case.knob` checks the dial, writes its 3D exports and reads each back."""

from dataclasses import dataclass
from functools import reduce
from math import pi
from operator import add

from build123d import Box, Circle, Cylinder, GeomType, Polygon, Pos, Rectangle, Rot, chamfer, extrude
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from obs_case import body
from obs_case.deck import OVERRUN
from obs_case.export import EXPORTS, STAGE, fresh, part_files, publish
from obs_case.spec import LAYOUT

LABEL = "OBS-KNOB"
FOLDER = "knob"
MEASURE = ("shaft fit on the knob bore coupon",)
VOLUME_EPS = 1e-9  # relative error goal of the adaptive volume integrator


@dataclass(frozen=True)
class Seat:
    """The dial's levels and bore sizes, PCB frame."""

    radius: float  # dial
    foot: float  # skirt
    top: float
    shaft_end: float
    flat_start: float  # where the shaft flat begins
    d_start: float  # where the D bore begins
    bore: float  # round bore diameter
    across: float  # D bore, flat to the far side
    pocket_radius: float  # counterbore over the bushing
    roof: float  # counterbore roof
    screw_z: float  # set screw axis


def seat(table=None) -> Seat:
    """The Seat from board.toml; `table` stands in for [knob_dial]."""
    table = table or LAYOUT.knob_dial
    _, shaft_end = LAYOUT.envelopes.ec11_shaft
    _, bushing_top = LAYOUT.envelopes.ec11_bushing
    _, flat_length = table.shaft_flat
    bore, across = table.bore
    pocket, room = table.bushing_pocket
    top = shaft_end + table.top_cover
    flat_start = shaft_end - flat_length
    return Seat(radius=LAYOUT.knobs.diameter / 2, foot=table.skirt, top=top, shaft_end=shaft_end,
                flat_start=flat_start, d_start=flat_start + table.flat_margin, bore=bore, across=across,
                pocket_radius=pocket / 2, roof=bushing_top + room, screw_z=top - table.set_screw.from_top)


def problems(table=None) -> list[str]:
    """What keeps the dial from fitting the EC11 or from being made; [] when it is sound."""
    table = table or LAYOUT.knob_dial
    s = seat(table)
    bushing, bushing_top = LAYOUT.envelopes.ec11_bushing
    shaft, _ = LAYOUT.envelopes.ec11_shaft
    flat_across, _ = table.shaft_flat
    flutes, index, screw = table.flutes, table.index, table.set_screw
    air = s.foot - LAYOUT.stack.deck_top
    found = []
    if air <= table.push_travel:
        found.append(f"knob: {air:g} air under the dial, the push travels {table.push_travel:g}")
    if s.foot >= bushing_top or 2 * s.pocket_radius <= bushing:
        found.append("knob: the counterbore does not take the bushing")
    if s.roof >= s.flat_start:
        found.append(f"knob: the counterbore roof {s.roof:g} reaches the shaft flat at {s.flat_start:g}")
    if s.bore <= shaft or s.across <= flat_across or s.across >= s.bore:
        found.append("knob: the bore is no D round the shaft")
    if index.depth >= table.top_cover:
        found.append(f"knob: the index {index.depth:g} deep opens the bore under {table.top_cover:g} of cover")
    if screw.from_top - screw.hole / 2 <= index.depth:
        found.append("knob: the set screw hole runs into the index")
    if not s.d_start <= s.screw_z - screw.hole / 2 < s.screw_z + screw.hole / 2 <= s.shaft_end:
        found.append(f"knob: the set screw at z {s.screw_z:g} misses the D bore, z {s.d_start:g} to {s.shaft_end:g}")
    land = 2 * pi * s.radius / flutes.count - 2 * flutes.half_width
    if land < flutes.land:
        found.append(f"knob: flute lands {land:.3f} wide, under {flutes.land:g}")
    if table.chamfer >= table.plain_band or index.depth > table.plain_band:
        found.append("knob: the rim chamfer or the index runs into the flutes")
    return found


def dial(table=None):
    """The finished dial, one solid; `table` stands in for [knob_dial]."""
    table = table or LAYOUT.knob_dial
    s = seat(table)
    blank = _cylinder(s.radius, s.foot, s.top)
    part = chamfer(blank.edges().filter_by(GeomType.CIRCLE), table.chamfer)
    for name, tool in (("knob seat", _seat_tool(s)), ("knob flutes", _flutes(s, table)),
                       ("knob index", _index(s, table.index)), ("knob set screw", _set_screw(s, table.set_screw))):
        part = _cut(part, tool, name)
    return part


def _cut(part, tool, name):
    """body.cut's rule with exact volumes. Where the radial set screw hole meets the dial cylinder,
    OCCT's default volume integration is off by about 4e-5 of the removed volume, which
    body.VOLUME_TOLERANCE rejects; the adaptive integrator at VOLUME_EPS agrees to 3e-8."""
    shared = part & tool
    removed = sum(_volume(piece) for piece in shared.solids()) if shared else 0.0
    result = part - tool
    lost = _volume(part) - _volume(result)
    if removed <= 0.0 or abs(lost - removed) > body.VOLUME_TOLERANCE * removed:
        raise body.CutFailed(f"{name}: removed {lost:.4f} mm3, the tool overlaps {removed:.4f} mm3")
    if len(result.solids()) != 1 or not result.is_valid:
        raise body.CutFailed(f"{name}: left {len(result.solids())} solids, valid {result.is_valid}")
    return result


def _volume(shape):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props, VOLUME_EPS)
    return props.Mass()


def _cylinder(radius, z_low, z_high):
    return Pos(0, 0, (z_low + z_high) / 2) * Cylinder(radius, z_high - z_low)


def _seat_tool(s):
    """The counterbore over the bushing, the round bore, then the D over the shaft flat."""
    pocket = _cylinder(s.pocket_radius, s.foot - OVERRUN, s.roof)
    round_bore = _cylinder(s.bore / 2, s.foot - OVERRUN, s.d_start)
    return pocket + round_bore + _d_bore(s)


def _d_bore(s):
    """The bore circle cut by the flat at y = across - radius, from d_start to the shaft end."""
    radius = s.bore / 2
    flat_y = s.across - radius
    keep = Pos(0, (flat_y - radius) / 2) * Rectangle(s.bore, flat_y + radius)
    return Pos(0, 0, s.d_start) * extrude(Circle(radius) & keep, amount=s.shaft_end - s.d_start)


def _flutes(s, table):
    """One V flute per pitch between the plain bands, half a pitch off +y, so a land and not a flute
    lines up with the index. The half width is set at the rim; the V runs OVERRUN past it."""
    flutes = table.flutes
    outer = s.radius + OVERRUN
    outer_half = flutes.half_width * (flutes.depth + OVERRUN) / flutes.depth
    vee = Polygon((s.radius - flutes.depth, 0), (outer, -outer_half), (outer, outer_half), align=None)
    band_low, band_high = s.foot + table.plain_band, s.top - table.plain_band
    flute = Pos(0, 0, band_low) * extrude(vee, amount=band_high - band_low)
    step = 360 / flutes.count
    return reduce(add, (Rot(0, 0, 90 + (number + 0.5) * step) * flute for number in range(flutes.count)))


def _index(s, index):
    """A slot on +y from `inner` off the axis out through the rim, `depth` down from the top."""
    outer = s.radius + OVERRUN
    length = outer - index.inner
    return Pos(0, index.inner + length / 2, s.top + (OVERRUN - index.depth) / 2) * Box(
        index.width, length, index.depth + OVERRUN)


def _set_screw(s, screw):
    """A radial hole on +y from the axis out through the rim, so it opens onto the shaft flat."""
    length = s.radius + OVERRUN
    return Pos(0, length / 2, s.screw_z) * (Rot(90, 0, 0) * Cylinder(screw.hole / 2, length))


def export_all(stage=STAGE, target=EXPORTS) -> int:
    """Check the dial; when sound, write its 3D exports under `stage`, read each back, then replace
    `target`/knob and the manifest's "knob" section. Returns 1 on any fault."""
    found = problems()
    for problem in found:
        print(problem)
    print(f"knob: {len(found)} problems; MEASURE: {', '.join(MEASURE)}")
    if found:
        return 1
    return publish(part_files(dial(), LABEL, fresh(stage / FOLDER) / "dial"), stage, target, (FOLDER,), FOLDER)


if __name__ == "__main__":
    raise SystemExit(export_all())
