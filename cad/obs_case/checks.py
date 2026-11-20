# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Geometry checks on the style A top shell. Every probe point comes from board.toml through
spec.LAYOUT; a problem is one line of text, and no problem means the shell passes.

Probes are points tested inside or outside the solid, so a missing or misplaced cut shows up
even when the solid itself is valid."""

from build123d import Box, Pos

from obs_case import body, deck
from obs_case.spec import LAYOUT

CNC_MIN_WALL = 2.0  # report 11: walls 2.0 mm or more (JLCCNC: above 1.5 for bead blast)
TOLERANCE = 1e-6  # mm, the build123d point and bounding-box tolerance
PAST_EDGE = 1e-3  # mm a probe sits past an edge it tests, well above TOLERANCE


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
