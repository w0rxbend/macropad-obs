# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Geometry checks on the style A top shell, the display carriers, the foam frames, the back-wall
insert and the bottom plate. Every probe point comes from board.toml through spec.LAYOUT; a problem
is one line of text, and no problem means the part passes.

Probes are points tested inside or outside the solid, so a missing or misplaced cut shows up
even when the solid itself is valid. The carrier and foam numbers go through the rules of
tools/check_numbers.py, measured off the solids, so the model and the numbers test agree.

`variant_problems` runs these on the print and cnc variants (variants.py) and adds the CNC-only
shop rules, ported from macropad/cad/macropad_case/checks.py and measure.py (`machinability`,
`_tool_reach`): no sharp inside corner, corner radius against depth, cutter reach; and a measured
wall thickness, where only the thin walls board.toml draws on purpose (thin_walls) pass under
CNC_MIN_WALL, each by name."""

import importlib.util
from dataclasses import dataclass
from math import inf, pi

from build123d import Box, GeomType, Pos, Vector
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

from obs_case import body, bottom, carriers, deck, insert, shop, spec, variants
from obs_case.shop import SHOP_MIN_WALL
from obs_case.spec import LAYOUT

CNC_MIN_WALL = 2.0  # report 11: walls 2.0 mm or more (JLCCNC: above 1.5 for bead blast)
WALL_MESH = 0.05  # mm, mesh tolerance of the faces the wall check samples
TOLERANCE = 1e-6  # mm, the build123d point and bounding-box tolerance
PAST_EDGE = 1e-3  # mm a probe sits past an edge it tests, well above TOLERANCE
CHECK_NUMBERS = spec.BOARD_TOML.parent / "tools" / "check_numbers.py"
MILLED = ("shell", "plate")  # the 6061 parts; the insert is plastic ([antenna] insert.material)
MAX_TOOL_DEPTH_RATIO = 3  # JLCCNC [J1]: a pocket is best at 2 to 3 cutter diameters deep
FULL_TURN = 1e-3  # share of a cylinder's area by which a drilled hole may miss a full turn


def _load_check_numbers():
    """tools/check_numbers.py as a module: one copy of the stack and squeeze rules."""
    module_spec = importlib.util.spec_from_file_location("check_numbers", CHECK_NUMBERS)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


NUMBERS = _load_check_numbers()


def problems(part):
    """Every broken rule of `part`, the top shell from deck.top_shell()."""
    found = _solid_problems(part) + _extent_problems(part) + _stack_problems() + _web_problems()
    found += [f"probe {name}: expected {_word(inside)}" for name, point, inside in probes()
              if part.is_inside(point) != inside]
    return found + _cut_fault_problems()


def probes():
    """(name, point, expected inside) for each feature of the shell."""
    return (_deck_probes() + _key_probes() + _display_probes() + _pocket_wall_probes() + _hole_probes()
            + _chamfer_probes())


def _word(inside):
    return "solid" if inside else "empty"


def _solid_problems(part):
    solids = part.solids()
    found = [] if len(solids) == 1 else [f"{len(solids)} solids, expected 1"]
    return found if part.is_valid else found + ["the shell is not a valid solid"]


def _extent_problems(part):
    box = part.bounding_box()
    x, y, width, depth = LAYOUT.body.outline
    stack = LAYOUT.stack
    want = (x, y, stack.bottom_plate_inside, x + width, y + depth, stack.deck_top)
    got = (box.min.X, box.min.Y, box.min.Z, box.max.X, box.max.Y, box.max.Z)
    if all(abs(have - need) <= TOLERANCE for have, need in zip(got, want, strict=True)):
        return []
    return [f"bounding box {tuple(round(value, 4) for value in got)}, expected {want}"]


def _stack_problems():
    stack, window = LAYOUT.stack, LAYOUT.window
    found = []
    if abs(stack.deck_top - window.lens_recess_depth - stack.lens_recess_floor) > TOLERANCE:
        found.append("stack.lens_recess_floor is not deck_top - window.lens_recess_depth")
    if stack.deck_top - stack.deck_underside < CNC_MIN_WALL - TOLERANCE:
        found.append(f"deck {stack.deck_top - stack.deck_underside:g} thick, CNC minimum {CNC_MIN_WALL}")
    if LAYOUT.body.wall < CNC_MIN_WALL - TOLERANCE:
        found.append(f"wall {LAYOUT.body.wall:g}, CNC minimum {CNC_MIN_WALL}")
    return found


def _web_problems():
    """Deck webs between neighbouring openings of one row, and between the two lens recesses."""
    buttons = LAYOUT.buttons
    hole_width = deck.button_hole()[0]
    webs = {f"button web {left:g}-{right:g}": right - left - hole_width
            for left, right in zip(buttons.x, buttons.x[1:])}
    big, narrow = (deck.lens_recess(panel) for panel in deck.panels())
    webs["lens recess web"] = narrow[0] - (big[0] + big[2]) - 2 * LAYOUT.body.opening_chamfer
    return [f"{name} {web:.2f}, CNC minimum {CNC_MIN_WALL}"
            for name, web in webs.items() if web < CNC_MIN_WALL - TOLERANCE]


def _mid(low, high):
    return (low + high) / 2


def _deck_mid():
    return _mid(LAYOUT.stack.deck_underside, LAYOUT.stack.deck_top)


def _plate_mid():
    return _mid(LAYOUT.stack.mx_plate_underside, LAYOUT.stack.mx_plate_top)


def _deck_probes():
    pcb, case, stack = LAYOUT.pcb, LAYOUT.body, LAYOUT.stack
    x, y, _, depth = case.outline
    side = _mid(x, x + case.wall)
    well_back = deck.key_well()[1] + deck.key_well()[3]
    big_front = deck.lens_recess(LAYOUT.big_display)[1]
    return [
        ("cavity at the PCB centre", (pcb.width / 2, pcb.depth / 2, 0.0), False),
        ("left wall", (side, _mid(y, y + depth), 0.0), True),
        ("deck between the key well and the big recess",
         (LAYOUT.keys.x[1], _mid(well_back, big_front), _deck_mid()), True),
        ("bottom face open", (pcb.width / 2, pcb.depth / 2, stack.bottom_plate_inside + TOLERANCE), False),
    ]


def _key_probes():
    keys, stack = LAYOUT.keys, LAYOUT.stack
    well_z = _mid(stack.mx_plate_top, stack.deck_top)
    found = []
    for key_x in keys.x:
        for key_y in keys.y:
            found.append((f"plate hole {key_x:g},{key_y:g}", (key_x, key_y, _plate_mid()), False))
            found.append((f"key well {key_x:g},{key_y:g}", (key_x, key_y, well_z), False))
    between = _mid(keys.x[0], keys.x[1])
    found.append(("plate web between key columns", (between, keys.y[0], _plate_mid()), True))
    well_x = deck.key_well()[0]
    found.append(("plate under the well wall", (well_x - PAST_EDGE, keys.y[1], _plate_mid()), True))
    return found


def _display_probes():
    window, stack = LAYOUT.window, LAYOUT.stack
    ledge_z = _mid(stack.deck_underside, stack.lens_recess_floor)
    recess_z = _mid(stack.lens_recess_floor, stack.deck_top)
    found = []
    for panel in deck.panels():
        x, y, width, depth = panel.lens_opening
        name = panel.part.split()[0]
        centre_y = _mid(y, y + depth)
        on_ledge = x - window.lens_ledge / 2
        found += [
            (f"{name} window", (_mid(x, x + width), centre_y, ledge_z), False),
            (f"{name} lens ledge", (on_ledge, centre_y, ledge_z), True),
            (f"{name} lens recess", (on_ledge, centre_y, recess_z), False),
        ]
    return found


def _pocket_wall_probes():
    """Mid skirt, half a skirt outside each long pocket side: the wall. Just inside it: the pocket.
    And the tail notch open, so the tail can fold."""
    stack, skirt = LAYOUT.stack, LAYOUT.display_carrier.skirt
    z = _mid(stack.pocket_skirt_bottom, stack.deck_underside)
    found = []
    for name in carriers.NAMES:
        panel = carriers.panel(name)
        x, y, width, depth = panel.pocket
        centre_y = _mid(y, y + depth)
        for side, face, outward in (("left", x, -1), ("right", x + width, 1)):
            found += [
                (f"{name} pocket wall {side}", (face + outward * skirt / 2, centre_y, z), True),
                (f"{name} pocket open {side}", (face - outward * PAST_EDGE, centre_y, z), False),
            ]
        notch_x, notch_y, notch_width, notch_depth = panel.pocket_tail_notch
        found.append((f"{name} pocket tail notch open",
                      (_mid(notch_x, notch_x + notch_width), _mid(notch_y, notch_y + notch_depth), z), False))
    return found


def _hole_probes():
    buttons, knobs = LAYOUT.buttons, LAYOUT.knobs
    found = [(f"button hole {x:g}", (x, buttons.y, _deck_mid()), False) for x in buttons.x]
    found += [(f"knob hole {y:g}", (knobs.x, y, _deck_mid()), False) for y in knobs.y]
    edge = knobs.x + knobs.bushing_hole / 2
    found += [(f"deck past knob hole {y:g}", (edge + PAST_EDGE, y, _deck_mid()), True) for y in knobs.y]
    return found


def _chamfer_probes():
    """A point a quarter chamfer in from each chamfered edge, a quarter chamfer below the top: empty
    when the chamfer is cut, solid when the edge is square."""
    case, stack = LAYOUT.body, LAYOUT.stack
    x, y, _, depth = case.outline
    top = case.top_chamfer / 4
    opening = case.opening_chamfer / 4
    well_x = deck.key_well()[0]
    recess_x, recess_y, _, recess_depth = deck.lens_recess(LAYOUT.big_display)
    return [
        ("outer top chamfer", (x + top, _mid(y, y + depth), stack.deck_top - top), False),
        ("key well chamfer", (well_x - opening, LAYOUT.keys.y[1], stack.deck_top - opening), False),
        ("big recess chamfer",
         (recess_x - opening, _mid(recess_y, recess_y + recess_depth), stack.deck_top - opening), False),
        ("deck below the key well chamfer",
         (well_x - opening, LAYOUT.keys.y[1], stack.deck_top - 3 * case.opening_chamfer), True),
    ]


def _cut_fault_problems():
    """A cut that removes nothing must raise, never hand back the uncut solid (no _keep())."""
    block = Box(1, 1, 1)
    try:
        body.cut(block, Pos(5, 0, 0) * Box(1, 1, 1), "probe cut off the solid")
    except body.CutFailed:
        return []
    return ["body.cut returned a solid for a cut that removed nothing"]


def carrier_problems(shell):
    """Every broken rule of the carriers and foam frames; `shell` is deck.top_shell()."""
    parts = {name: (carriers.carrier(name), carriers.foam_frame(name)) for name in carriers.NAMES}
    found = []
    for name in carriers.NAMES:
        found += [f"{name} foam frame: {problem}" for problem in NUMBERS.stack_problems(_measured(parts, name))]
        found += [f"{name} {problem}" for problem in NUMBERS.squeeze_problems(_measured_foam(parts[name][1]))]
        found += _seat_problems(name, *parts[name]) + _footprint_problems(name, *parts[name])
        found += location_problems(name, parts[name][0], shell)
        found += [f"{name} {kind} cuts into the top shell" for kind, part in zip(("carrier", "foam"), parts[name])
                  if _shared_volume(part, shell) > TOLERANCE]
    return found + [f"probe {name}: expected {_word(inside)}" for name, part, point, inside
                    in carrier_probes(parts) if part.is_inside(point) != inside]


def _z_span(part):
    box = part.bounding_box()
    return box.min.Z, box.max.Z


def _height(part):
    low, high = _z_span(part)
    return high - low


def _rect(part):
    box = part.bounding_box()
    return [box.min.X, box.min.Y, box.size.X, box.size.Y]


def _measured_foam(foam):
    face, top = _z_span(foam)
    return {"installed": top - face, "thickness": LAYOUT.foam_frame.thickness}


def _measured(parts, foam_name):
    """check_numbers' layout tables, with every height and z read off the solids: the stack of
    one foam frame over both carriers."""
    face, top = _z_span(parts[foam_name][1])
    heights = {name: {"height": _height(carrier)} for name, (carrier, _) in parts.items()}
    panels = {f"{name}_display": {"thickness": carriers.panel(name).thickness} for name in parts}
    return {"stack": {"panel_face": face, "deck_underside": top},
            "foam_frame": _measured_foam(parts[foam_name][1]), "display_carrier": heights, **panels}


def _seat_problems(name, carrier, foam):
    """The carrier stands on the PCB top face and the foam presses on the deck underside."""
    stack = LAYOUT.stack
    found = []
    if abs(_z_span(carrier)[0] - stack.pcb_top) > TOLERANCE:
        found.append(f"{name} carrier bottom at z {_z_span(carrier)[0]:g}, PCB top face is {stack.pcb_top:g}")
    if abs(_z_span(foam)[1] - stack.deck_underside) > TOLERANCE:
        found.append(f"{name} foam top at z {_z_span(foam)[1]:g}, deck underside is {stack.deck_underside:g}")
    return found


def _footprint_problems(name, carrier, foam):
    """Carrier = pocket less clearance a side (location_problems checks the walls hold it), foam = module outline,
    and the panel rests on the carrier ring: inside its outer edge, over its hollow."""
    ring, display = getattr(LAYOUT.display_carrier, name), carriers.panel(name)
    want = {"carrier": (_rect(carrier), deck.grown(display.pocket, -LAYOUT.display_carrier.clearance)),
            f"carrier against [display_carrier] {name}.outer": (_rect(carrier), ring.outer),
            "foam": (_rect(foam), display.outline)}
    found = [f"{name} {kind} footprint {[round(v, 4) for v in got]}, expected {[round(v, 4) for v in need]}"
             for kind, (got, need) in want.items() if not _same_rect(got, need)]
    if not (_contains(ring.outer, display.outline) and _contains(display.outline, ring.inner)):
        found.append(f"{name} panel outline {display.outline} does not rest on the carrier ring")
    return found


def location_problems(name, carrier, shell):
    """The pocket walls locate the carrier: its nearest approach to the shell is the
    [display_carrier] clearance. More lets the carrier and its panel slide under the lens ledge."""
    clearance = LAYOUT.display_carrier.clearance
    gap = carrier.distance_to(shell)
    if abs(gap - clearance) <= TOLERANCE:
        return []
    return [f"{name} carrier sits {gap:.3f} off the shell, the pocket walls locate it at {clearance:g}"]


def _same_rect(got, need):
    return all(abs(have - want) <= TOLERANCE for have, want in zip(got, need, strict=True))


def _contains(outer, inner):
    """True if [x, y, w, h] `inner` lies inside `outer`, edges allowed to touch."""
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return ox <= ix + TOLERANCE and oy <= iy + TOLERANCE and ix + iw <= ox + ow + TOLERANCE \
        and iy + ih <= oy + oh + TOLERANCE


def _shared_volume(part, other):
    shared = part & other
    return sum(piece.volume for piece in shared.solids()) if shared else 0.0


def carrier_probes(parts):
    """(name, part, point, expected inside) for each carrier wall, hollow and tail gap, and each
    foam ring and opening."""
    found = []
    for name, (carrier, foam) in parts.items():
        ring = getattr(LAYOUT.display_carrier, name)
        carrier_z, foam_z = _mid(*_z_span(carrier)), _mid(*_z_span(foam))
        x, y, width, depth = ring.outer
        gap_x, gap_y, gap_width, gap_depth = ring.tail_gap
        lens_x, lens_y, lens_width, lens_depth = carriers.panel(name).lens_opening
        outline_x = carriers.panel(name).outline[0]
        found += [
            (f"{name} carrier wall", carrier, (ring.inner[0] - PAST_EDGE, _mid(y, y + depth), carrier_z), True),
            (f"{name} carrier hollow", carrier, (_mid(x, x + width), _mid(y, y + depth), carrier_z), False),
            (f"{name} carrier tail gap", carrier,
             (_mid(gap_x, gap_x + gap_width), _mid(gap_y, gap_y + gap_depth), carrier_z), False),
            (f"{name} foam ring", foam, (_mid(outline_x, lens_x), _mid(lens_y, lens_y + lens_depth), foam_z), True),
            (f"{name} foam opening", foam, (_mid(lens_x, lens_x + lens_width), _mid(lens_y, lens_y + lens_depth),
                                            foam_z), False),
        ]
    return found


def insert_problems(parts):
    """Every broken rule of the back-wall insert and the bottom plate. `parts` maps "shell" to
    insert.shell(), "plate" to bottom.plate() and "insert" to insert.insert(). The shell and the
    plate count as metal (the CNC case): neither may hold any volume in the antenna board cut."""
    found = [problem for name, solid in parts.items() for problem in _one_solid(name, solid)]
    found += _insert_rule_problems() + _usb_rule_problems() + _post_height_problems()
    found += _insert_extent_problems(parts["insert"])
    found += [f"{name} is metal in the antenna board cut" for name in ("shell", "plate")
              if _shared_volume(parts[name], _antenna_cut()) > TOLERANCE]
    names = list(parts)
    found += [f"{first} and {second} overlap" for index, first in enumerate(names) for second in names[index + 1 :]
              if _shared_volume(parts[first], parts[second]) > TOLERANCE]
    return found + [f"probe {name}: expected {_word(inside)}" for name, solid, point, inside
                    in insert_probes(parts) if solid.is_inside(point) != inside]


def _one_solid(name, solid):
    count = len(solid.solids())
    found = [] if count == 1 else [f"{name}: {count} solids, expected 1"]
    return found if solid.is_valid else found + [f"{name} is not a valid solid"]


def _antenna_cut():
    """The antenna board cut, from below the plate to the deck underside: the room the PCB antenna
    radiates into, with the deck above it the one metal face spec 7 accepts. The cut runs off the
    PCB edge, so it is clipped to the rounded board bay: past the bay is the case wall, which spec 7
    counts as the metal 9.0 to the right."""
    z_low, z_high = bottom.outer_face() - carriers.OVERRUN, LAYOUT.stack.deck_underside
    return carriers.block(LAYOUT.antenna.board_cut, z_low, z_high) & bottom.bay(z_low, z_high)


def _right(rect):
    return rect[0] + rect[2]


def _back(rect):
    return rect[1] + rect[3]


def _insert_rule_problems():
    """The insert outline and the plate relief must close on the shell's own faces: the wall
    inside face, the back face, the corner arc's start and the cavity's right face."""
    case, cavity = LAYOUT.body, bottom.cavity_rect()
    outline, relief = LAYOUT.antenna.insert.outline, LAYOUT.bottom_plate.antenna_relief
    edges = {
        "insert front against the wall inside face": (outline[1], _back(cavity)),
        "insert back against the case back face": (_back(outline), _back(case.outline)),
        "insert right end at the corner arc": (_right(outline), _right(case.outline) - case.corner_radius),
        "relief back against the insert front": (_back(relief), outline[1]),
        "relief right against the cavity right face": (_right(relief), _right(cavity)),
    }
    found = [f"{name}: {got:g}, expected {need:g}" for name, (got, need) in edges.items()
             if abs(got - need) > TOLERANCE]
    if not _contains(relief, LAYOUT.antenna.board_cut):
        found.append(f"antenna_relief {relief} does not cover the board cut {LAYOUT.antenna.board_cut}")
    return found


def _post_height_problems():
    """Standoffs, encoder posts and key ribs reach from the plate to the PCB bottom face."""
    stack, plate_table = LAYOUT.stack, LAYOUT.bottom_plate
    gap = stack.pcb_bottom - stack.bottom_plate_inside
    heights = {"standoffs": plate_table.standoffs.height, "encoder_posts": plate_table.encoder_posts.height,
               "key_ribs": plate_table.key_ribs.height}
    return [f"bottom_plate.{name} height {height:g}, plate to PCB is {gap:g}"
            for name, height in heights.items() if abs(height - gap) > TOLERANCE]


def _insert_extent_problems(part):
    x, y, width, depth = LAYOUT.antenna.insert.outline
    relief = LAYOUT.bottom_plate.antenna_relief
    box = part.bounding_box()
    want = (min(x, relief[0]), relief[1], bottom.outer_face(), max(x + width, _right(relief)), y + depth,
            LAYOUT.stack.deck_top)
    got = (box.min.X, box.min.Y, box.min.Z, box.max.X, box.max.Y, box.max.Z)
    if all(abs(have - need) <= TOLERANCE for have, need in zip(got, want, strict=True)):
        return []
    return [f"insert bounding box {tuple(round(value, 4) for value in got)}, expected {want}"]


def variant_problems(parts, variant):
    """Every broken rule of one variant's {"shell", "plate", "insert"}: the shell and insert rules
    above, the variant's own fits found where they should be, and for cnc the shop rules."""
    found = [f"{variant} shell: {problem}" for problem in problems(parts["shell"])]
    if variant == variants.PRINT:
        found += [f"{variant}: {problem}" for problem in insert_problems(parts)]
    else:  # the cnc reliefs and lobes run past the drawn outlines that insert_problems checks
        found += [f"{variant}: {problem}" for problem in _metal_and_overlap_problems(parts)]
        found += cnc_problems(parts)
    return found + [f"{variant} probe {name}: expected {_word(inside)}" for name, solid, point, inside
                    in variant_probes(parts, variant) if solid.is_inside(point) != inside]


def _metal_and_overlap_problems(parts):
    found = [problem for name, solid in parts.items() for problem in _one_solid(name, solid)]
    found += [f"{name} is metal in the antenna board cut" for name in ("shell", "plate")
              if _shared_volume(parts[name], _antenna_cut()) > TOLERANCE]
    names = list(parts)
    return found + [f"{first} and {second} overlap" for index, first in enumerate(names)
                    for second in names[index + 1 :] if _shared_volume(parts[first], parts[second]) > TOLERANCE]


def variant_probes(parts, variant):
    """(name, part, point, expected inside): just inside each print fit and just outside each cnc
    fit, so a variant that lost its fit shows up. Points sit halfway between the two fits."""
    fit = variants.fits(variant)
    other = variants.fits(variants.CNC if variant == variants.PRINT else variants.PRINT)
    shell, stack = parts["shell"], LAYOUT.stack
    cap_width = LAYOUT.buttons.cap[0]
    cap_edge = cap_width / 2 + _mid(fit.hole_clearance, other.hole_clearance)
    recess_x = LAYOUT.big_display.lens_opening[0] - LAYOUT.window.lens_ledge
    recess_edge = recess_x - _mid(fit.lens_fit, other.lens_fit) + LAYOUT.variants.cnc.lens_fit
    recess_y = _mid(LAYOUT.big_display.lens_opening[1], _back(LAYOUT.big_display.lens_opening))
    loose = fit.hole_clearance > other.hole_clearance
    wide = fit.lens_fit > other.lens_fit
    return [(f"button hole {x:g} fit", shell, (x + cap_edge, LAYOUT.buttons.y, _deck_mid()), not loose)
            for x in LAYOUT.buttons.x] + [
        ("big lens recess fit", shell,
         (recess_edge, recess_y, _mid(stack.lens_recess_floor, stack.deck_top - LAYOUT.body.opening_chamfer)), not wide),
    ] + _thinned_wall_probes(shell)


def _thinned_wall_probes(shell):
    """Just inside the thinned wall's outside face, between the USB opening and each side of the
    thinning pocket: the wall keeps [usb] back_wall_thinned.to there, so no relief milled into it."""
    usb = LAYOUT.usb
    between = _mid(usb.opening[0], usb.back_wall_thinned.area[0]) / 2
    y = insert.thinned_face_y() - PAST_EDGE
    return [("shell thinned wall full beside the USB opening", shell, (usb.x + side * between, y, insert.usb_mouth_z()),
             True) for side in (-1, 1)]


def cnc_problems(parts):
    """The shop rules on the milled shell and plate (report 11 section 3): no sharp inside corner
    left, every inside corner radius at least JLCCNC's depth / 10 + 0.5 [J1] and no deeper than
    MAX_TOOL_DEPTH_RATIO cutter diameters, every wall CNC_MIN_WALL or a named thin wall, and the
    corner finder still sees the drawn MX cut-outs."""
    found = [f"cnc {name}: {_corner_text(corner)}" for name in MILLED
             for corner in variants.inside_corners(parts[name], variants.SETUPS[name])]
    found += [f"cnc {name}: inside corner at {corner.middle.X:.2f},{corner.middle.Y:.2f} open to none of its setups"
              for name in MILLED for corner in variants.relief_corners(name) if corner.setup is None]
    found += [f"cnc {name}: {problem}" for name in MILLED for problem in _radius_problems(parts[name])]
    found += [f"cnc {name}: {problem}" for name in MILLED for problem in wall_problems(parts[name], thin_walls(name))]
    if LAYOUT.variants.cnc.hole_clearance != LAYOUT.buttons.hole_clearance:
        found.append("variants.cnc.hole_clearance is not buttons.hole_clearance, the drawn deck")
    return found + _finder_problems()


@dataclass(frozen=True)
class ThinWall:
    """A wall board.toml draws thinner than CNC_MIN_WALL on purpose: what it is, the board.toml key
    that sets its thickness, that thickness, and the boxes (x, y, z low, x, y, z high) it stands in."""

    name: str
    source: str
    thickness: float
    regions: tuple

    def covers(self, point):
        return any(low_x - PAST_EDGE <= point.X <= high_x + PAST_EDGE and low_y - PAST_EDGE <= point.Y <= high_y
                   + PAST_EDGE and low_z - PAST_EDGE <= point.Z <= high_z + PAST_EDGE
                   for low_x, low_y, low_z, high_x, high_y, high_z in self.regions)


def _box(rect, z_low, z_high):
    x, y, width, depth = rect
    return x, y, z_low, x + width, y + depth, z_high


def thin_walls(name):
    """The thin walls of milled part `name` the shop is told to expect: sizes from layout-v2 as the
    owner approved it (D3), under report 11's CNC_MIN_WALL and over the shops' SHOP_MIN_WALL. The
    wall check names each one it measures and fails on any other wall under CNC_MIN_WALL."""
    stack = LAYOUT.stack
    if name == "plate":
        ribs = LAYOUT.bottom_plate.key_ribs
        rects = [[ribs.x[0], y - ribs.width / 2, ribs.x[1] - ribs.x[0], ribs.width] for y in ribs.y]
        return (ThinWall("key ribs", "[bottom_plate] key_ribs.width", ribs.width,
                         tuple(_box(rect, stack.bottom_plate_inside, stack.pcb_bottom) for rect in rects)),
                *_clipped_standoffs())
    usb, mouth_z = LAYOUT.usb, insert.usb_mouth_z()
    area_width, area_height = usb.back_wall_thinned.area
    inside = _back(bottom.cavity_rect())
    usb_rect = [usb.x - area_width / 2, inside, area_width, insert.thinned_face_y() - inside]
    bars = [bar for panel in deck.panels() for bar in deck.pocket_wall_rects(panel)]
    return (
        ThinWall("USB thinned back wall", "[usb] back_wall_thinned.to", usb.back_wall_thinned.to,
                 (_box(usb_rect, mouth_z - area_height / 2, mouth_z + area_height / 2),)),
        ThinWall("display pocket walls", "[display_carrier] skirt", LAYOUT.display_carrier.skirt,
                 tuple(_box(bar, stack.pocket_skirt_bottom, stack.deck_underside) for bar in bars)),
        _boss_walls(),
    )


def _boss_walls():
    """The wall of each screw boss between its tap drill and its free side: the boss can grow no
    wider than the [pcb] hole keep-out it lands on, so the wall is that radius less the drill's."""
    screws, stack = LAYOUT.screws, LAYOUT.stack
    radius = screws.boss_diameter / 2
    rects = [[x - radius, y - radius, screws.boss_diameter, screws.boss_diameter] for x, y in LAYOUT.pcb.holes]
    return ThinWall("M2 bosses", "[screws] boss_diameter",
                    radius - screws.cnc.tap_drill / 2,
                    tuple(_box(rect, stack.pcb_top, stack.deck_underside) for rect in rects))


def _clipped_standoffs():
    """A thin wall for each standoff the board bay clips (bottom.py) to under CNC_MIN_WALL between
    its screw hole and the bay: the [pcb] hole sits that close to the bay edge in layout-v2 (the
    back-left drill, 0.5 from the R 4.0 arc), so the post wall there is the hole's web to the bay."""
    pcb, stack, posts = LAYOUT.pcb, LAYOUT.stack, LAYOUT.bottom_plate.standoffs
    found = []
    for hole in pcb.holes:
        web = _bay_distance(hole) - pcb.hole_diameter / 2
        if _bay_distance(hole) >= posts.diameter / 2 or web >= CNC_MIN_WALL - TOLERANCE:
            continue
        x, y = hole
        rect = [x - posts.diameter / 2, y - posts.diameter / 2, posts.diameter, posts.diameter]
        found.append(ThinWall(f"standoff {x:g},{y:g} web to the bay", f"[pcb] holes {x:g},{y:g}", web,
                              (_box(rect, stack.bottom_plate_inside, stack.pcb_bottom),)))
    return tuple(found)


def _bay_distance(point):
    """Distance from `point`, inside the board bay, to the bay's rounded outline."""
    corner = LAYOUT.pcb.corner_radius + LAYOUT.body.pcb_clearance
    x, y, width, depth = deck.grown(bottom.cavity_rect(), -corner)  # the rectangle of arc centres
    nearest = Vector(min(max(point[0], x), x + width), min(max(point[1], y), y + depth), 0)
    offset = (Vector(point[0], point[1], 0) - nearest).length
    if offset > 0:
        return corner - offset
    return corner + min(point[0] - x, x + width - point[0], point[1] - y, y + depth - point[1])


def wall_problems(part, walls):
    """The thinnest sample of each vertical plane face of `part` under CNC_MIN_WALL that no wall in
    `walls` accepts, and each wall in `walls` the part no longer has. A wall accepts a sample it
    covers that is at least its own thickness and SHOP_MIN_WALL."""
    thinnest, seen = {}, set()
    for face, point, thickness in wall_samples(part):
        if thickness >= CNC_MIN_WALL - TOLERANCE:
            continue
        wall = next((wall for wall in walls if wall.covers(point)), None)
        if wall and thickness >= max(wall.thickness, SHOP_MIN_WALL) - TOLERANCE:
            seen.add(wall.name)
        elif face not in thinnest or thickness < thinnest[face][1]:
            thinnest[face] = (point, thickness, wall)
    found = [f"wall {thickness:.2f} at {point.X:.2f},{point.Y:.2f} z {point.Z:.2f}, CNC minimum {CNC_MIN_WALL:g}"
             + (f", {wall.name} {wall.thickness:g}" if wall else "") for point, thickness, wall in thinnest.values()]
    return found + [f"accepted thin wall {wall.name} ({wall.source} {wall.thickness:g}) not found"
                    for wall in walls if wall.name not in seen]


def wall_samples(part):
    """(face index, point, thickness) at the middle of each mesh triangle of each vertical plane face
    of `part`: how far a ray from there along the face's inward normal runs in material. The mesh
    reaches every strip of a face, however narrow, where a grid of points could miss it."""
    rays = IntCurvesFace_ShapeIntersector()
    rays.Load(part.wrapped, TOLERANCE)
    found = []
    for index, face in enumerate(part.faces().filter_by(GeomType.PLANE)):
        inward = -face.normal_at()
        if abs(inward.Z) > TOLERANCE:
            continue
        vertices, triangles = face.tessellate(WALL_MESH)
        for corners in triangles:
            point = sum((vertices[corner] for corner in corners), Vector()) / len(corners)
            found.append((index, point, _run_in_material(rays, point, inward)))
    return found


def _run_in_material(rays, point, inward):
    """How far from `point`, on a face, a ray along `inward` runs before it leaves the material."""
    start = point + inward * PAST_EDGE
    rays.PerformNearest(gp_Lin(gp_Pnt(start.X, start.Y, start.Z), gp_Dir(inward.X, inward.Y, inward.Z)), 0, inf)
    if not rays.IsDone() or rays.NbPnt() == 0:
        return inf
    return rays.WParameter(1) + PAST_EDGE


def _corner_text(corner):
    kind = "square inside corner left sharp" if corner.square else "acute inside corner (no relief fits)"
    return f"{kind} at {corner.middle.X:.2f},{corner.middle.Y:.2f} z {corner.z_low:g} to {corner.z_high:g}"


def concave_walls(part):
    """(radius, height) of each concave vertical cylinder wall of `part` that is not a full hole:
    the corners a cutter has to fit. Full round holes are drilled and left out."""
    found = []
    for face in part.faces().filter_by(GeomType.CYLINDER):
        cylinder = BRepAdaptor_Surface(face.wrapped).Cylinder()  # Face.radius is None once trimmed
        axis, radius = cylinder.Axis(), cylinder.Radius()
        if abs(axis.Direction().Z()) < 1 - FULL_TURN:
            continue
        on_face = face.position_at(0.5, 0.5)
        centre = axis.Location()
        toward_axis = Vector(centre.X() - on_face.X, centre.Y() - on_face.Y, 0).normalized()
        height = face.bounding_box().size.Z
        full = abs(face.area - 2 * pi * radius * height) < FULL_TURN * face.area
        if part.is_inside(on_face + toward_axis * variants.PROBE) or full:
            continue  # material on the axis side: an outside corner, or a drilled hole
        found.append((radius, height))
    return found


def _radius_problems(part):
    found = []
    for radius, height in concave_walls(part):
        if radius < shop.shop_radius(height) - TOLERANCE:
            found.append(f"inside corner R {radius:.3f}, {height:g} deep, JLCCNC wants R {shop.shop_radius(height):.3f}")
        if height > MAX_TOOL_DEPTH_RATIO * 2 * radius + TOLERANCE:
            found.append(f"inside corner R {radius:.3f} is {height / (2 * radius):.1f} cutter diameters deep")
    return found


def _finder_problems():
    """The finder must see the four sharp corners of every drawn MX cut-out in the shell before the
    reliefs go in; seeing none would pass any part."""
    want = 4 * len(LAYOUT.keys.x) * len(LAYOUT.keys.y)
    seen = len(variants.inside_corners(deck.top_shell(), variants.SETUPS["shell"]))
    return [] if seen >= want else [f"corner finder sees {seen} corners in the drawn shell, expected {want} or more"]


def insert_probes(parts):
    """(name, part, point, expected inside) for the insert, its pocket in the shell, and each
    plate feature."""
    return _insert_probes(parts) + _plate_probes(parts["plate"])


def _bottom_mid():
    return _mid(bottom.outer_face(), LAYOUT.stack.bottom_plate_inside)


def _post_mid():
    return _mid(LAYOUT.stack.bottom_plate_inside, LAYOUT.stack.pcb_bottom)


def _insert_probes(parts):
    shell, plate, part = parts["shell"], parts["plate"], parts["insert"]
    x, y, width, depth = LAYOUT.antenna.insert.outline
    relief_x, relief_y, relief_width, relief_depth = LAYOUT.bottom_plate.antenna_relief
    relief_centre = (_mid(relief_x, relief_x + relief_width), _mid(relief_y, relief_y + relief_depth))
    wall_x, wall_y = _mid(x, x + width), _mid(y, y + depth)
    chamfer = LAYOUT.body.top_chamfer / 4
    top = LAYOUT.stack.deck_top
    return [
        ("tongue fills the relief", part, (*relief_centre, _bottom_mid()), True),
        ("plate open at the relief", plate, (*relief_centre, _bottom_mid()), False),
        ("insert foot through the plate", part, (wall_x, wall_y, _bottom_mid()), True),
        ("plate open under the insert", plate, (wall_x, wall_y, _bottom_mid()), False),
        ("insert wall", part, (wall_x, wall_y, 0.0), True),
        ("insert deck rim", part, (wall_x, wall_y, _deck_mid()), True),
        ("insert top chamfer", part, (wall_x, _back(LAYOUT.body.outline) - chamfer, top - chamfer), False),
        ("shell pocket at the insert wall", shell, (wall_x, wall_y, 0.0), False),
        ("shell pocket at the insert deck rim", shell, (wall_x, wall_y, _deck_mid()), False),
        ("shell wall left of the insert", shell, (x - PAST_EDGE, wall_y, 0.0), True),
        ("shell wall right of the insert", shell, (x + width + PAST_EDGE, wall_y, 0.0), True),
    ] + _usb_probes(shell)


def _usb_probes(shell):
    """The USB opening through the back wall and the outside pocket that thins the wall round it."""
    usb, mouth_z = LAYOUT.usb, insert.usb_mouth_z()
    opening_width, opening_height = usb.opening
    area_width, area_height = usb.back_wall_thinned.area
    inside, thinned, back = _back(bottom.cavity_rect()), insert.thinned_face_y(), _back(LAYOUT.body.outline)
    beside = usb.x + opening_width / 2 + PAST_EDGE
    return [
        ("shell open at the USB mouth", shell, (usb.x, _mid(inside, back), mouth_z), False),
        ("shell thinned beside the USB opening", shell, (beside, _mid(thinned, back), mouth_z), False),
        ("shell thin wall beside the USB opening", shell, (beside, _mid(inside, thinned), mouth_z), True),
        ("shell over the USB opening", shell,
         (usb.x, _mid(inside, thinned), mouth_z + opening_height / 2 + PAST_EDGE), True),
        ("shell full wall beside the thinned area", shell,
         (usb.x + area_width / 2 + PAST_EDGE, _mid(thinned, back), mouth_z), True),
        ("shell full wall over the thinned area", shell,
         (usb.x, _mid(thinned, back), mouth_z + area_height / 2 + PAST_EDGE), True),
    ]


def _usb_rule_problems():
    """The USB opening must pass the receptacle, meet the plate notch, and leave the receptacle face
    behind the thinned wall face ([usb]: 0.4 behind it)."""
    usb, notch = LAYOUT.usb, LAYOUT.bottom_plate.usb_notch
    width, depth = usb.body
    opening_width, opening_height = usb.opening
    mouth_z = insert.usb_mouth_z()
    receptacle_face = LAYOUT.pcb.depth + usb.mouth_overhang
    found = []
    if opening_width <= width or opening_height <= usb.height:
        found.append(f"usb.opening {usb.opening} does not pass the {width:g} x {usb.height:g} shell")
    if opening_width > notch.width or mouth_z - opening_height / 2 < LAYOUT.stack.bottom_plate_inside - notch.depth:
        found.append(f"usb.opening {usb.opening} runs past the plate notch {notch.width:g} x {notch.depth:g}")
    if insert.thinned_face_y() <= receptacle_face:
        found.append(f"USB receptacle face y {receptacle_face:g} is not behind the thinned face "
                     f"y {insert.thinned_face_y():g}")
    return found


def _plate_probes(plate):
    plate_table, pcb = LAYOUT.bottom_plate, LAYOUT.pcb
    found = [("plate at the PCB centre", plate, (pcb.width / 2, pcb.depth / 2, _bottom_mid()), True)]
    for hole_x, hole_y in pcb.holes:
        found += [
            (f"screw hole {hole_x:g},{hole_y:g} in the plate", plate, (hole_x, hole_y, _bottom_mid()), False),
            (f"screw hole {hole_x:g},{hole_y:g} in the standoff", plate, (hole_x, hole_y, _post_mid()), False),
            (f"standoff {hole_x:g},{hole_y:g}", plate,
             (hole_x + pcb.hole_diameter / 2 + PAST_EDGE, hole_y, _post_mid()), True),
        ]
    found += [(f"encoder post {x:g},{y:g}", plate, (x, y, _post_mid()), True)
              for x, y in plate_table.encoder_posts.at]
    ribs = plate_table.key_ribs
    found += [(f"key rib {y:g}", plate, (_mid(*ribs.x), y, _post_mid()), True) for y in ribs.y]
    pinholes = plate_table.pinholes
    found += [(f"pinhole {x:g},{y:g}", plate, (x, y, _bottom_mid()), False) for x, y in pinholes.at]
    beside = pinholes.diameter / 2 + PAST_EDGE
    found += [(f"plate beside pinhole {x:g},{y:g}", plate, (x + beside, y, _bottom_mid()), True)
              for x, y in pinholes.at]
    notch, inside = plate_table.usb_notch, LAYOUT.stack.bottom_plate_inside
    notch_y = _mid(_back(bottom.cavity_rect()), _back(LAYOUT.body.outline))
    found += [
        ("USB notch", plate, (LAYOUT.usb.x, notch_y, inside - notch.depth / 2), False),
        ("plate under the USB notch", plate, (LAYOUT.usb.x, notch_y, inside - notch.depth - PAST_EDGE), True),
    ]
    return found
