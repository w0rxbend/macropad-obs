# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The critical copper, drawn in code and locked before any other routing (task 5.8, report 09).

Pure Python, no KiCad import, so the plan and its checks run in `just pcb-test`. build.py reads the
placed board's pads with pcbnew, hands them to `route`, writes the copper locked, adds `planes()` and
the antenna keep-out, and runs KiCad's DRC on the result (`just pcb route-critical`).

What is drawn: four ground vias in the module's pad 41, then route_order.txt line by line: the buck
loop, the module's supply and ground pads, the USB pair (B.Cu only, report 10 section 10) and VBUS. Last, a via
into its plane for every other surface pad on GND or +3V3 (`supply_pads`), for Freerouting (task 5.9).

The planes: In2.Cu is ground and In1.Cu is +3V3, each over the whole board but the antenna setback.
In1.Cu carries one +5V island under the fuse and the buck input. Report 10 drew In1.Cu as a 5 V plane
with a 3.3 V island; here 25 pads are on +3V3 and 6 on +5V, 2 of them on the tails between +3V3 pins,
so +3V3 takes the plane and the tails' +5V pins get tracks (task 5.9).

The plane edge at the antenna: every copper layer ends ANTENNA_SETBACK behind the antenna board cut,
by a keep-out area on all four layers that later pours and the autorouter also obey.

Coordinates are KiCad's: mm, back-left origin, y towards the front edge (place.kicad_xy).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from circuit_power import GND, USB_D_N, USB_D_P, V3, V5
from place import BOARD, DEPTH, WIDTH, kicad_xy
from router import BACK, BOTH_LAYERS, Pad, Rect, Router, Rules, Track, Via

ORDER_PATH = Path(__file__).with_name("route_order.txt")
PCB = BOARD["pcb"]
# Report 10 section 10: 0.22 mm tracks 0.15 mm apart are about 90 ohm differential on B.Cu over In2.Cu,
# on the JLCPCB and the PCBWay 7628 stackups. Every critical track is at least this wide.
TRACK_WIDTH = 0.22
WIDE_TRACK_WIDTH = 0.4  # design: the buck's switch node, input and output
# Clearance, vias and edge clearance as layout.ROUTING_RULES (router.Rules defaults).
RULES = Rules(track_width=TRACK_WIDTH, wide_track_width=WIDE_TRACK_WIDTH)
GROUND_PLANE, POWER_PLANE = "ground", "power"  # layout.GROUND_LAYER (In2.Cu) and POWER_LAYER (In1.Cu)
# Design: copper on every layer stops this far behind the antenna board cut. More than the 0.3 mm edge
# clearance, so the edge is set here and not by the fill.
ANTENNA_SETBACK = 0.5
# The keep-out under the module stops this far inside its outline, so its edge pads stay reachable.
MODULE_KEEPOUT_INSET = 0.6
# A via this close to the edge of its plane island might miss it (greycode route.py).
PLANE_EDGE_MARGIN = 0.55
# The +5V island on In1.Cu (left, top, right, bottom): under the buck's input capacitor and VIN pins,
# and on to the fuse. Design; test_route checks it holds the +5V parts and none of the +3V3 ones.
V5_ISLAND = ((25.2, 14.0, 30.6, 19.6), (28.4, 4.4, 39.0, 14.4))
# Ground vias in the module's pad 41, from its centre: the four crossings of the gaps between the nine
# paste windows, 0.2 mm from the nearest window (layout.PASTE_TO_VIA_DRILL wants 0.15).
EXPOSED_PAD = "U1.41"
EXPOSED_PAD_VIA_OFFSETS = ((-0.7, -0.7), (0.7, -0.7), (-0.7, 0.7), (0.7, 0.7))
# Limits, mm, that fail the build. Not datasheet values: they catch a detour or a part that drifts.
# Report 10 rule 4 keeps the two USB lines within 3 mm, the sibling board's number, not a datasheet's.
# Here the pair wraps 270 degrees round the module with D- on the outside and ends on pad 13, 1.27 mm
# past pad 14; the best placement found measures 3.6 mm. 4 mm is about 27 ps against an 83 ns bit.
USB_PAIR_MISMATCH_LIMIT = 4.0
LENGTH_LIMIT = {"BUCK_SW": 4.0, "BUCK_FB": 4.0}
USB_PATH_LIMIT = 60.0
HOT_LOOP_LIMIT = 7.0  # the input capacitor's +5V and GND tracks to VIN and GND, together
HOT_LOOP_PADS = frozenset({"C1.1", "U2.4", "C1.2", "U2.2"})
USB_NETS = (USB_D_N, USB_D_P, "USB_DM", "USB_DP")


@dataclass(frozen=True)
class Line:
    """One line of route_order.txt."""
    net: str
    pads: tuple[str, ...]
    wide: bool = False
    vias: bool = True


@dataclass(frozen=True)
class Plane:
    net: str
    layer: str  # GROUND_PLANE or POWER_PLANE
    rects: tuple[Rect, ...]  # one zone over their union
    priority: int = 0  # the higher wins where zones of one layer overlap


@dataclass
class Result:
    router: Router
    unrouted: list[str]
    group_lengths: dict[Line, float]  # track length each joining line of route_order.txt drew

    @property
    def tracks(self) -> list[Track]:
        return self.router.tracks

    @property
    def vias(self) -> list[Via]:
        return self.router.vias

    def report_lines(self) -> list[str]:
        router = self.router
        lines = [f"route-critical: {len(router.tracks)} tracks, {len(router.vias)} vias, "
                 f"{sum(t.length for t in router.tracks):.1f} mm, {len(self.unrouted)} pads unrouted",
                 f"route-critical: USB D+ {usb_path_length(router, 'P'):.2f} mm, D- {usb_path_length(router, 'N'):.2f} mm "
                 f"(limit {USB_PATH_LIMIT}, mismatch {USB_PAIR_MISMATCH_LIMIT}); hot loop {hot_loop_length(self):.2f} mm "
                 f"(limit {HOT_LOOP_LIMIT})"]
        lines += [f"route-critical: {net} {router.net_length(net):.2f} mm (limit {limit})"
                  for net, limit in LENGTH_LIMIT.items()]
        return lines + [f"route-critical: unrouted {name}" for name in self.unrouted]


def read_order(text: str) -> tuple[Line, ...]:
    """route_order.txt: `NET PAD... [wide] [no-via]`, `#` starts a comment."""
    lines = []
    for number, raw in enumerate(text.splitlines(), start=1):
        words = raw.split("#")[0].split()
        if not words:
            continue
        net, rest = words[0], words[1:]
        pads = tuple(word for word in rest if "." in word)
        options = set(rest) - set(pads)
        assert pads and options <= {"wide", "no-via"}, f"route_order.txt line {number}: {raw!r}"
        lines.append(Line(net, pads, "wide" in options, "no-via" not in options))
    return tuple(lines)


PLANE_NETS = frozenset({GND, V3, V5})
# The planes every surface pad of these nets gets a via into, after the order. The tails' +5V pins are off
# the +5V island: Freerouting gives them tracks (task 5.9).
FAN_OUT_NETS = (GND, V3)


def whole_nets(order: tuple[Line, ...]) -> frozenset[str]:
    """The nets the order draws in full: every net in it that has no plane (test_route checks it names all
    their pads). KiCad must find none of them unconnected."""
    return frozenset(line.net for line in order) - PLANE_NETS


def _box(rect: list[float]) -> Rect:
    """board.toml [x, y, w, h] -> (left, top, right, bottom), KiCad coordinates."""
    left, front, width, depth = rect
    return left, DEPTH - (front + depth), left + width, DEPTH - front


def _grown(rect: Rect, margin: float) -> Rect:
    left, top, right, bottom = rect
    return left - margin, top - margin, right + margin, bottom + margin


def antenna_keepout() -> Rect:
    """The antenna board cut grown by ANTENNA_SETBACK: no copper on any layer inside."""
    return _grown(_box(BOARD["antenna"]["board_cut"]), ANTENNA_SETBACK)


def slot_keepouts() -> tuple[Rect, ...]:
    """Each board slot grown by the edge clearance: no copper inside, on any layer. Freerouting reads a slot
    as a keep-out and keeps only its track clearance from it, under KiCad's edge clearance."""
    return tuple(_grown(_box(slot), RULES.edge_clearance) for slot in PCB["board_slots"])


def _clear_of_antenna() -> tuple[Rect, ...]:
    """The whole board but the antenna keep-out, as two rectangles. The cut runs off the right and back edges."""
    left, _, _, bottom = antenna_keepout()
    return (0.0, bottom, WIDTH, DEPTH), (0.0, 0.0, left, bottom)


def planes() -> tuple[Plane, ...]:
    whole = _clear_of_antenna()
    return (Plane(GND, GROUND_PLANE, whole), Plane(V3, POWER_PLANE, whole),
            Plane(V5, POWER_PLANE, V5_ISLAND, priority=1))


def _inside(rects: tuple[Rect, ...], x: float, y: float, margin: float) -> bool:
    """Inside the union of the rectangles, at least `margin` from their edges (outside it, if negative)."""
    return any(left + margin <= x <= right - margin and top + margin <= y <= bottom - margin
               for left, top, right, bottom in rects)


def plane_here(net: str, x: float, y: float) -> bool:
    """Is the net's plane under this point, far enough from its edge for a via?"""
    clear = _clear_of_antenna()
    if net == GND:
        return _inside(clear, x, y, PLANE_EDGE_MARGIN)
    if net == V3:
        return _inside(clear, x, y, PLANE_EDGE_MARGIN) and not _inside(V5_ISLAND, x, y, -PLANE_EDGE_MARGIN)
    if net == V5:
        return _inside(V5_ISLAND, x, y, PLANE_EDGE_MARGIN)
    raise AssertionError(f"{net} has no plane")


def _no_copper(router: Router, rect: Rect) -> None:
    """No track or via of the critical copper reaches into the rectangle."""
    rules = router.rules
    router.add_keepout(_grown(rect, rules.track_width / 2 + rules.grid_allowance), BOTH_LAYERS)
    router.add_keepout(_grown(rect, rules.via_diameter / 2 + rules.grid_allowance), ())


def _add_obstacles(router: Router, pads: list[Pad], holes: list[Rect]) -> None:
    for pad in pads:
        router.add_pad(pad)
    for hole in holes:
        router.add_hole(hole)
    for rect in slot_keepouts():
        _no_copper(router, rect)
    _no_copper(router, antenna_keepout())
    # board.toml hole_keepout_diameter: no copper inside, on any layer (a square round the circle).
    for x, y in (kicad_xy(*hole) for hole in PCB["holes"]):
        _no_copper(router, _grown((x, y, x, y), PCB["hole_keepout_diameter"] / 2))
    # No critical track or via under the module body, where the USB pair would run along the antenna.
    router.add_keepout(_grown(_box(BOARD["mcu"]["outline"]), -MODULE_KEEPOUT_INSET), (BACK,))


class _Plan:
    def __init__(self, router: Router, pads: list[Pad]) -> None:
        self.router = router
        self.pads: dict[str, list[Pad]] = {}
        for pad in pads:
            self.pads.setdefault(pad.name, []).append(pad)
        self.unrouted: list[str] = []
        self.group_lengths: dict[Line, float] = {}

    def pad(self, name: str, net: str) -> Pad:
        found = self.pads.get(name)
        assert found, f"route_order.txt names {name}, which the board does not have"
        assert found[0].net == net, f"route_order.txt puts {name} on {net}; the board has it on {found[0].net}"
        return found[0]

    def exposed_pad_vias(self) -> None:
        x, y = self.pad(EXPOSED_PAD, GND).centre
        for dx, dy in EXPOSED_PAD_VIA_OFFSETS:
            self.router.add_via_in_pad(GND, x + dx, y + dy)

    def follow(self, line: Line) -> None:
        pads = [self.pad(name, line.net) for name in line.pads]
        if len(pads) == 1:
            self.fan_out(line.net, pads[0], line.wide)
            return
        before = len(self.router.tracks)
        failed = self.router.route_group(line.net, pads, line.wide, line.vias)
        if line.wide and failed:  # a wide track does not fit between fine-pitch pads
            # Seeded from the first pad, which the wide pass joined, so the rest reach the same copper.
            failed = self.router.route_group(line.net, [pads[0]] + [pad for pad in pads if pad.name in failed],
                                             vias=line.vias)
        self.unrouted += [f"{line.net}: {name}" for name in failed]
        self.group_lengths[line] = sum(track.length for track in self.router.tracks[before:])

    def fan_out(self, net: str, pad: Pad, wide: bool) -> None:
        def here(x: float, y: float) -> bool:
            return plane_here(net, x, y)
        if not ((wide and self.router.fan_out(net, pad, here, wide=True)) or self.router.fan_out(net, pad, here)):
            self.unrouted.append(f"{net}: {pad.name} (no via to its plane)")


def route(pads: list[Pad], holes: list[Rect], order: tuple[Line, ...] | None = None) -> Result:
    """Plans the critical copper over the placed board's pads and drilled holes. Writes nothing."""
    router = Router(WIDTH, DEPTH, PCB["corner_radius"], RULES)
    _add_obstacles(router, pads, holes)
    plan = _Plan(router, pads)
    plan.exposed_pad_vias()
    order = order if order is not None else read_order(ORDER_PATH.read_text())
    for line in order:
        plan.follow(line)
    for pad in supply_pads(pads, order):
        plan.fan_out(pad.net, pad, wide=False)
    return Result(router, plan.unrouted, plan.group_lengths)


def supply_pads(pads: list[Pad], order: tuple[Line, ...]) -> list[Pad]:
    """Surface pads on FAN_OUT_NETS that the order does not name. Freerouting joins no pad to a closed plane
    (report 09 pitfall 3), so each gets a via here. A through-hole pad meets the planes in its barrel."""
    named = {name for line in order for name in line.pads}
    return [pad for pad in pads if pad.net in FAN_OUT_NETS and len(pad.layers) == 1 and pad.name not in named]


# --- checks ---------------------------------------------------------------------------------------

def usb_path_length(router: Router, polarity: str) -> float:
    """Copper from the jack to the module pin of one USB line, both sides of the 22 ohm resistor."""
    jack_side, module_side = {"P": (USB_D_P, "USB_DP"), "N": (USB_D_N, "USB_DM")}[polarity]
    return router.net_length(jack_side) + router.net_length(module_side)


def hot_loop_length(result: Result) -> float:
    """The buck's input loop: the groups that join C1 to U2 on +5V and GND, without their vias' stubs."""
    return sum(length for line, length in result.group_lengths.items()
               if line.net in (V5, GND) and set(line.pads) <= HOT_LOOP_PADS)


def problems(result: Result) -> list[str]:
    """Every way the critical copper misses its limits. Empty when it passes."""
    router = result.router
    found = list(result.unrouted)
    for net, limit in LENGTH_LIMIT.items():
        length = router.net_length(net)
        if not 0 < length <= limit:
            found.append(f"{net} is {length:.2f} mm long, limit {limit} mm")
    paths = {polarity: usb_path_length(router, polarity) for polarity in "PN"}
    for polarity, length in paths.items():
        if not 0 < length <= USB_PATH_LIMIT:
            found.append(f"USB D{'+' if polarity == 'P' else '-'} is {length:.2f} mm long, limit {USB_PATH_LIMIT} mm")
    loop = hot_loop_length(result)
    if not 0 < loop <= HOT_LOOP_LIMIT:
        found.append(f"the buck's input loop is {loop:.2f} mm of track, limit {HOT_LOOP_LIMIT} mm")
    if abs(paths["P"] - paths["N"]) > USB_PAIR_MISMATCH_LIMIT:
        found.append(f"USB D+ and D- differ by {abs(paths['P'] - paths['N']):.2f} mm")
    found += [f"{track.net} track off B.Cu at {track.start}" for track in router.tracks
              if track.net in USB_NETS and track.layer != BACK]
    found += [f"{via.net} via at ({via.x}, {via.y})" for via in router.vias if via.net in USB_NETS]
    return found
