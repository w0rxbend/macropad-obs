# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Geometry checks on the style A top shell, the display carriers, the foam frames, the back-wall
insert and the bottom plate. Every probe point comes from board.toml through spec.LAYOUT; a problem
is one line of text, and no problem means the part passes.

Probes are points tested inside or outside the solid, so a missing or misplaced cut shows up
even when the solid itself is valid. The carrier and foam numbers go through the rules of
tools/check_numbers.py, measured off the solids, so the model and the numbers test agree."""

import importlib.util

from build123d import Box, Pos

from obs_case import body, bottom, carriers, deck, spec
from obs_case.spec import LAYOUT

CNC_MIN_WALL = 2.0  # report 11: walls 2.0 mm or more (JLCCNC: above 1.5 for bead blast)
TOLERANCE = 1e-6  # mm, the build123d point and bounding-box tolerance
PAST_EDGE = 1e-3  # mm a probe sits past an edge it tests, well above TOLERANCE
CHECK_NUMBERS = spec.BOARD_TOML.parent / "tools" / "check_numbers.py"


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
    return _deck_probes() + _key_probes() + _display_probes() + _hole_probes() + _chamfer_probes()


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
    """Carrier = pocket less clearance a side (the pocket walls locate it), foam = module outline,
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
    found += _insert_rule_problems() + _post_height_problems() + _insert_extent_problems(parts["insert"])
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
    ]


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
