# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Print coupons (task 6.9; spec 14 risk rows, report 11 section 4 item 5): small pieces cut from the
printed parts with boxes, to test one fit each before the whole case prints. Each coupon is the
real part inside its box, turned the way that part prints, and lowered onto the bed.

Copied from macropad/cad/macropad_case/coupons.py (`Coupon`, `parent_piece`, `assembled`,
`placement`, `difference_from_parent`, `built`) and adapted: one box from one parent per coupon (no
`Cut`, no shift, no pilot); the placement is kept with the coupon (`Placed`); the parents are this
case's print variant, the display carriers and the knob dial; the poses are POSES; each box keeps a
case wall's width (board.toml [body] wall) of material round what it tests; the pilot-hole, lap and
light-channel coupons are gone with the parts they tested.

- module-stack: the plate under the WROOM-1, with four stand-in standoffs beside it. A 1.6 board
  scrap on the posts with the bought module under it shows the 0.9 left to the plate (spec 14).
- usb-top, usb-base: the USB opening's bite from the shell and the plate, for a bought USB4216 and
  the owner's cables (spec 14).
- mx-cutout, cap-hole, knob-hole, knob-bore: one MX plate hole, one B3F cap hole, one EC11 bushing
  hole and the dial's bore, the fits board.toml leaves MEASURE on a coupon.
- fpc-big, fpc-narrow: the front of each carrier with its tail gap, on a stand-in board 1.6 thick
  with the [pcb] board slot, to fold the bought panel's tail through.

Two kinds add what their parent does not have: the stand-in posts and the stand-in boards. They
are kept apart in the checks. Frame: board.toml's PCB frame (the dial's is on its shaft axis).
`python -m obs_case.coupons` checks every coupon, writes its 3D exports and reads each back."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

from build123d import Cylinder, Location, Part, Pos, Rot
from build123d.topology import downcast
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Fuse
from OCP.collections import List_TopoDS_Shape
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

from obs_case import bottom, carriers, insert, knob, variants
from obs_case.carriers import block
from obs_case.deck import OVERRUN, button_hole
from obs_case.export import EXPORTS, STAGE, fresh, part_files, publish
from obs_case.spec import LAYOUT

FOLDER = "coupons"
FLIP = Rot(180, 0, 0)  # the deck top (shell) or the dial top on the bed: no cut opens downward
POSES = {"shell": FLIP, "plate": Location(), "dial": FLIP, "carrier-big": Location(), "carrier-narrow": Location()}
STAND_IN_GAP = 0.5  # mm between a stand-in post and the module outline
TOLERANCE = 1e-6  # mm, the bed and the volume noise allowed
MEASURE = ("module stack 0.9 to the plate", "USB4216 and cable in the opening", "MX plate hole",
           "B3F cap hole", "EC11 bushing hole", "shaft fit on the knob bore", "FPC tail fold through the slot")


@dataclass(frozen=True)
class Coupon:
    """One box cut from one parent part, in the parent's own frame. The parent's print pose is the
    coupon's."""

    name: str
    parent: str
    window: Part
    added: Part | None = field(default=None)  # what the coupon has that its parent does not


def _rim():
    """Material a coupon keeps round what it tests: one case wall."""
    return LAYOUT.body.wall


def _window(x_range, y_range, z_range):
    """A box over ((x_low, x_high), (y_low, y_high), (z_low, z_high))."""
    (x_low, x_high), (y_low, y_high), (z_low, z_high) = x_range, y_range, z_range
    return block([x_low, y_low, x_high - x_low, y_high - y_low], z_low, z_high)


def _back(rect):
    return rect[1] + rect[3]


def _right(rect):
    return rect[0] + rect[2]


def _deck_z():
    return LAYOUT.stack.deck_underside - OVERRUN, LAYOUT.stack.deck_top + OVERRUN


def coupons() -> list[Coupon]:
    return [_module_stack(), *_usb_pair(), _mx_cutout(), _cap_hole(), _knob_hole(), _knob_bore(),
            *(_fpc_tail(name, index) for index, name in enumerate(carriers.NAMES))]


def _module_stack() -> Coupon:
    """The plate under the module, out through the back edge, with four stand-in standoffs up to the
    PCB bottom face beside the module: at its front corners and where the plate ends at the relief."""
    x, y, width, depth = LAYOUT.mcu.outline
    standoff = LAYOUT.bottom_plate.standoffs.diameter
    stack = LAYOUT.stack
    beside = standoff / 2 + STAND_IN_GAP
    reach = standoff + STAND_IN_GAP + _rim()
    window = _window((x - reach, x + width + reach), (y - reach, _back(LAYOUT.body.outline) + OVERRUN),
                     (bottom.outer_face() - OVERRUN, stack.pcb_bottom + OVERRUN))
    back_y = min(y + depth, LAYOUT.bottom_plate.antenna_relief[1]) - beside  # the plate ends at the relief
    height = stack.pcb_bottom - stack.bottom_plate_inside
    posts = Part() + [Pos(post_x, post_y, stack.bottom_plate_inside + height / 2) * Cylinder(standoff / 2, height)
                      for post_x in (x - beside, x + width + beside) for post_y in (y - beside, back_y)]
    return Coupon("module-stack", "plate", window, posts)


def _usb_pair() -> list[Coupon]:
    """The shell's back wall round the opening and its thinned pocket, and the plate round its notch."""
    usb, stack = LAYOUT.usb, LAYOUT.stack
    half = usb.back_wall_thinned.area[0] / 2 + _rim()
    x_range = (usb.x - half, usb.x + half)
    y_range = (_back(bottom.cavity_rect()) - _rim(), _back(LAYOUT.body.outline) + OVERRUN)
    top = _window(x_range, y_range, (stack.bottom_plate_inside - OVERRUN, stack.deck_top + OVERRUN))
    base = _window(x_range, y_range, (bottom.outer_face() - OVERRUN, stack.pcb_bottom + OVERRUN))
    return [Coupon("usb-top", "shell", top), Coupon("usb-base", "plate", base)]


def _mx_cutout() -> Coupon:
    """The first key of the middle row: its plate hole, the plate to half a pitch round it, the well
    wall and the left wall."""
    keys, stack = LAYOUT.keys, LAYOUT.stack
    x, y, reach = keys.x[0], keys.y[1], keys.pitch / 2
    window = _window((LAYOUT.body.outline[0] - OVERRUN, x + reach), (y - reach, y + reach),
                     (stack.mx_plate_underside - OVERRUN, stack.deck_top + OVERRUN))
    return Coupon("mx-cutout", "shell", window)


def _cap_hole() -> Coupon:
    """The first B3F cap hole and the deck round it, out through the front wall."""
    width, depth, _ = button_hole(variants.fits(variants.PRINT).hole_clearance)
    x, y = LAYOUT.buttons.x[0], LAYOUT.buttons.y
    window = _window((x - width / 2 - _rim(), x + width / 2 + _rim()),
                     (LAYOUT.body.outline[1] - OVERRUN, y + depth / 2 + _rim()), _deck_z())
    return Coupon("cap-hole", "shell", window)


def _knob_hole() -> Coupon:
    """The first EC11 bushing hole and the deck round it."""
    knobs = LAYOUT.knobs
    reach = knobs.bushing_hole / 2 + _rim()
    window = _window((knobs.x - reach, knobs.x + reach), (knobs.y[0] - reach, knobs.y[0] + reach), _deck_z())
    return Coupon("knob-hole", "shell", window)


def _knob_bore() -> Coupon:
    """The dial cut square round its counterbore, from the skirt to just over the shaft end, so the
    bore stays closed and the set screw hole stays in."""
    seat = knob.seat()
    reach = seat.pocket_radius + _rim()
    window = _window((-reach, reach), (-reach, reach), (seat.foot - OVERRUN, seat.shaft_end + OVERRUN))
    return Coupon("knob-bore", "dial", window)


def _fpc_tail(name: str, index: int) -> Coupon:
    """The tail edge of one carrier, the whole width with a wall's depth of its side walls, on a
    stand-in board under it from a rim in front of the [pcb] board slot."""
    ring, stack = getattr(LAYOUT.display_carrier, name), LAYOUT.stack
    x_range = (ring.outer[0] - OVERRUN, _right(ring.outer) + OVERRUN)
    y_high = ring.inner[1] + LAYOUT.display_carrier.wall
    window = _window(x_range, (ring.outer[1] - OVERRUN, y_high),
                     (stack.pcb_top - OVERRUN, stack.pcb_top + ring.height + OVERRUN))
    slot = LAYOUT.pcb.board_slots[index]
    board = _window((ring.outer[0], _right(ring.outer)), (slot[1] - _rim(), y_high),
                    (stack.pcb_bottom, stack.pcb_top))
    board = board - block(slot, stack.pcb_bottom - OVERRUN, stack.pcb_top + OVERRUN)
    return Coupon(f"fpc-{name}", f"carrier-{name}", window, board)


@cache
def parents() -> dict[str, Part]:
    """The parts the coupons are cut from: the print variant, the dial and the carriers."""
    printed = variants.parts(variants.PRINT)
    found = {"shell": printed["shell"], "plate": printed["plate"], "dial": knob.dial()}
    return found | {f"carrier-{name}": carriers.carrier(name) for name in carriers.NAMES}


def _serial(operation, shape: Part, tool: Part) -> Part:
    """`shape` (operation) `tool`, cleaned as build123d's own booleans are, on one thread.
    build123d runs every boolean in parallel, and the threads finish in any order, so a coupon's
    faces came out in either of two orders from run to run and its exports changed bytes."""
    arguments, tools = List_TopoDS_Shape(), List_TopoDS_Shape()
    arguments.Append(shape.wrapped)
    tools.Append(tool.wrapped)
    boolean = operation()
    boolean.SetArguments(arguments)
    boolean.SetTools(tools)
    boolean.SetRunParallel(False)
    boolean.Build()
    if not boolean.IsDone():
        raise RuntimeError(f"{operation.__name__} failed")
    unify = ShapeUpgrade_UnifySameDomain(boolean.Shape(), True, True, True)
    unify.AllowInternalEdges(False)
    unify.Build()
    return Part(downcast(unify.Shape()))


def parent_piece(coupon: Coupon, parts: dict[str, Part]) -> Part:
    """What the parent holds inside the coupon's box, in the parent's frame."""
    return _serial(BRepAlgoAPI_Common, parts[coupon.parent], coupon.window)


def assembled(coupon: Coupon, parts: dict[str, Part]) -> Part:
    """The coupon in its parent's frame, before it is turned to its print pose."""
    piece = parent_piece(coupon, parts)
    return _serial(BRepAlgoAPI_Fuse, piece, coupon.added) if coupon.added is not None else piece


def placement(coupon: Coupon, solid: Part) -> Location:
    """Turns the coupon to its parent's print pose, centres it over the origin and lowers it onto the bed."""
    pose = POSES[coupon.parent]
    bounds = (pose * solid).bounding_box()
    return Pos(-bounds.center().X, -bounds.center().Y, -bounds.min.Z) * pose


@dataclass(frozen=True)
class Placed:
    """A coupon in its parent's frame and the one placement that puts it on the bed. The placement
    is kept: a second one can differ by float noise, and a boolean on faces that far apart fails."""

    coupon: Coupon
    whole: Part
    location: Location

    @property
    def on_the_bed(self) -> Part:
        return self.location * self.whole


def _volume(part: Part) -> float:
    return sum(solid.volume for solid in part.solids())


def difference_from_parent(placed: Placed, parts: dict[str, Part]) -> float:
    """Volume in mm^3 by which the coupon on the bed differs from its parent inside the box, after it
    is turned back. What the coupon adds on purpose is left out of both."""
    coupon = placed.coupon
    mine, theirs = placed.location.inverse() * placed.on_the_bed, parent_piece(coupon, parts)
    if coupon.added is not None:
        mine, theirs = mine - coupon.added, theirs - coupon.added
    return _volume(mine) + _volume(theirs) - 2 * _volume(mine & theirs)


def place(coupon: Coupon, parts: dict[str, Part]) -> Placed:
    whole = assembled(coupon, parts)
    return Placed(coupon, whole, placement(coupon, whole))


def built(parts: dict[str, Part] | None = None) -> dict[str, Placed]:
    """Every coupon, placed on the bed, by name."""
    parts = parts or parents()
    return {coupon.name: place(coupon, parts) for coupon in coupons()}


def problems(placed: dict[str, Placed], parts: dict[str, Part] | None = None) -> list[str]:
    """What keeps a coupon from printing as its parent: [] when every one is one valid solid on the
    bed, its parent's material inside the box exactly, and holds the feature it tests."""
    parts = parts or parents()
    found = []
    for name, entry in placed.items():
        solid = entry.on_the_bed
        count, box = len(solid.solids()), solid.bounding_box()
        if count != 1 or not solid.is_valid:
            found.append(f"{name}: {count} solids, valid {solid.is_valid}")
        if abs(box.min.Z) > TOLERANCE:
            found.append(f"{name}: lowest point z {box.min.Z:.4f}, not on the bed")
        difference = difference_from_parent(entry, parts)
        if difference > TOLERANCE * _volume(entry.whole):
            found.append(f"{name}: differs from its parent by {difference:.4f} mm3")
        found += [f"{name}: {miss}" for miss in _feature_misses(name, entry.whole)]
    return found


def _feature_misses(name: str, whole: Part) -> list[str]:
    """Each coupon must hold what it tests: the hole as air inside the coupon's box, or for the
    module stack the stand-in post top at the PCB bottom face."""
    point, inside = _feature_probe(name)
    box = whole.bounding_box()
    if not (box.min.X < point[0] < box.max.X and box.min.Y < point[1] < box.max.Y):
        return [f"the feature at {tuple(round(value, 3) for value in point)} lies outside the coupon"]
    if whole.is_inside(point) != inside:
        return [f"expected {'solid' if inside else 'air'} at {tuple(round(value, 3) for value in point)}"]
    return []


def _feature_probe(name: str) -> tuple[tuple[float, float, float], bool]:
    """(point, expected inside) of the feature coupon `name` tests, in its parents' frame."""
    keys, knobs, usb, stack, mcu = LAYOUT.keys, LAYOUT.knobs, LAYOUT.usb, LAYOUT.stack, LAYOUT.mcu.outline
    deck_mid = (stack.deck_underside + stack.deck_top) / 2
    beside = LAYOUT.bottom_plate.standoffs.diameter / 2 + STAND_IN_GAP
    back_face = _back(LAYOUT.body.outline) - OVERRUN
    probes = {
        "module-stack": ((mcu[0] - beside, mcu[1] - beside, stack.pcb_bottom - OVERRUN), True),
        "usb-top": ((usb.x, back_face, insert.usb_mouth_z()), False),
        "usb-base": ((usb.x, back_face, stack.bottom_plate_inside - LAYOUT.bottom_plate.usb_notch.depth / 2), False),
        "mx-cutout": ((keys.x[0], keys.y[1], (stack.mx_plate_underside + stack.mx_plate_top) / 2), False),
        "cap-hole": ((LAYOUT.buttons.x[0], LAYOUT.buttons.y, deck_mid), False),
        "knob-hole": ((knobs.x, knobs.y[0], deck_mid), False),
        "knob-bore": ((0.0, 0.0, knob.seat().d_start), False),
    }
    for index, carrier in enumerate(carriers.NAMES):
        x, y, width, depth = LAYOUT.pcb.board_slots[index]
        probes[f"fpc-{carrier}"] = ((x + width / 2, y + depth / 2, stack.pcb_bottom / 2), False)
    return probes[name]


def label(name: str) -> str:
    """The STEP product name of a coupon."""
    return f"OBS-COUPON-{name.upper()}"


def export_all(stage=STAGE, target=EXPORTS) -> int:
    """Check every coupon; when sound, write each one's 3D exports under `stage`, read each back, then
    replace `target`/coupons and the manifest's "coupons" section. Returns 1 on any fault."""
    placed = built()
    found = problems(placed)
    for problem in found:
        print(problem)
    print(f"{FOLDER}: {len(placed)} coupons, {len(found)} problems; MEASURE: {', '.join(MEASURE)}")
    if found:
        return 1
    folder = fresh(stage / FOLDER)
    readbacks = [readback for name, entry in placed.items()
                 for readback in part_files(entry.on_the_bed, label(name), folder / name)]
    return publish(readbacks, stage, target, (FOLDER,), FOLDER)


if __name__ == "__main__":
    raise SystemExit(export_all())
