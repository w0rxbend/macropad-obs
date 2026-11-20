# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The Omron B3F button caps (task 6.10; spec section 6, report 08 item 4, report 11 section 6).
The plunger follows open question 2: [button_cap] plunger, by default the round black B3F-1060.
Two caps on the same switch, one per case variant:

- print: a press-on cap. A round socket of the plunger size sits on the plunger; no flange, so it
  goes in and out from above.
- cnc: a turned floating cap. The plunger holds its flange up against the deck underside, and a
  round blind bore over the plunger locates it. Nothing is pressed or glued.

Both stand flush with the deck top (report 08 item 4) on the [buttons] cap plan and corner; the deck
hole is that plan plus the variant's hole_clearance. Frame: x, y on the switch centre, z = 0 on the
PCB top face, mm. The cap fit on the plunger stays MEASURE.
`python -m obs_case.b3f_cap` checks both caps, writes their 3D exports and reads each back."""

from build123d import Cylinder, Pos

from obs_case import body
from obs_case.deck import OVERRUN
from obs_case.export import EXPORTS, STAGE, fresh, part_files, publish
from obs_case.spec import LAYOUT
from obs_case.variants import CNC, PRINT, VARIANTS

FOLDER = "b3f-cap"
MEASURE = ("cap fit on the plunger, on the cap hole coupon",)


def label(variant: str) -> str:
    """The STEP product name of the cap of `variant`."""
    return f"OBS-B3F-CAP-{variant.upper()}"


def bottom(variant: str, table=None) -> float:
    """z of the cap's lower face at rest: the socket mouth (print) or the flange (cnc)."""
    table = table or LAYOUT.button_cap
    if variant == PRINT:
        return table.plunger_top - table.socket_depth
    if variant == CNC:
        return LAYOUT.stack.deck_underside - table.flange
    raise ValueError(f"no B3F cap for variant {variant!r}; variants are {', '.join(VARIANTS)}")


def problems(variant: str, table=None, buttons=None) -> list[str]:
    """What keeps the cap of `variant` from working on the switch; [] when it is sound. `table` and
    `buttons` stand in for [button_cap] and [buttons]."""
    table, buttons, stack = table or LAYOUT.button_cap, buttons or LAYOUT.buttons, LAYOUT.stack
    found = []
    if table.plunger_top >= stack.deck_top:
        found.append(f"{variant} cap: the plunger top {table.plunger_top:g} reaches the cap top")
    if bottom(variant, table) - table.travel <= stack.b3f_body_top:
        found.append(f"{variant} cap: lands on the switch body before the plunger has travelled {table.travel:g}")
    if variant == CNC:
        hole_depth = buttons.cap[1] + 2 * LAYOUT.variants.cnc.hole_clearance
        if buttons.cap_flange[1] <= hole_depth:
            found.append(f"cnc cap: the flange, {buttons.cap_flange[1]:g} deep, passes the {hole_depth:g} deck hole")
        if 2 * table.bore_radius <= LAYOUT.envelopes.b3f_plunger:
            found.append(f"cnc cap: the {2 * table.bore_radius:g} bore does not clear the plunger")
    return [f"b3f {problem}" for problem in found]


def cap(variant: str):
    """The finished cap of `variant`, one solid."""
    table, stack, buttons = LAYOUT.button_cap, LAYOUT.stack, LAYOUT.buttons
    low = bottom(variant)
    if variant == PRINT:
        part = _plan(buttons.cap, low, stack.deck_top)
        return body.cut(part, _bore(LAYOUT.envelopes.b3f_plunger, low, table.plunger_top), "press-on socket")
    flange = _plan(buttons.cap_flange, low, stack.deck_underside)
    part = flange + _plan(buttons.cap, stack.deck_underside, stack.deck_top)
    return body.cut(part, _bore(2 * table.bore_radius, low, table.plunger_top), "floating cap bore")


def _plan(size, z_low, z_high):
    """A [width, depth] plan with the [buttons] cap corner, centred, from z_low to z_high."""
    width, depth = size
    return body.prism([-width / 2, -depth / 2, width, depth], LAYOUT.buttons.cap_corner_radius, z_low, z_high)


def _bore(diameter, z_low, z_high):
    """A blind bore from below the cap's lower face up to z_high."""
    z_low -= OVERRUN
    return Pos(0, 0, (z_low + z_high) / 2) * Cylinder(diameter / 2, z_high - z_low)


def export_all(stage=STAGE, target=EXPORTS) -> int:
    """Check both caps; when sound, write their 3D exports under `stage`, read each back, then
    replace `target`/b3f-cap and the manifest's "b3f-cap" section. Returns 1 on any fault."""
    found = [problem for variant in VARIANTS for problem in problems(variant)]
    for problem in found:
        print(problem)
    print(f"{FOLDER}: {', '.join(VARIANTS)}, {len(found)} problems; MEASURE: {', '.join(MEASURE)}")
    if found:
        return 1
    folder = fresh(stage / FOLDER)
    readbacks = [readback for variant in VARIANTS for readback in part_files(cap(variant), label(variant), folder / variant)]
    return publish(readbacks, stage, target, (FOLDER,), FOLDER)


if __name__ == "__main__":
    raise SystemExit(export_all())
