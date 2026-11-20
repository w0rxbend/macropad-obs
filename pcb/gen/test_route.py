# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Tests of route.py and route_order.txt. Plain Python, no KiCad: `just pcb-test`.

The routed board itself is checked by `just pcb route-critical` (KiCad's DRC, the locks, the antenna
setback); these tests hold the plan, the planes and the limits that step relies on.
"""

from __future__ import annotations

import math
import unittest

import circuit_hmi
import place
import route
import sexpr
from circuit_power import GND, V3, V5
from router import BACK, FRONT, Pad, Router, Track, Via
from test_router import is_connected

MODULE_FOOTPRINT = route.ORDER_PATH.parents[1] / "lib" / "macropad-obs.pretty" / "ESP32-S3-WROOM-1.kicad_mod"
MIN_DRILL = 0.3  # layout.DRC_RULES min_through_hole_diameter


def circuit_nets() -> dict[str, str]:
    """"U1.13" -> net, from the circuit the board is built from."""
    return {f"{part.ref}.{pin}": net for part in circuit_hmi.BOARD_PARTS for pin, net in part.nets.items()}


def spot_xy(ref: str) -> tuple[float, float]:
    spot = place.spots()[ref]
    return place.kicad_xy(spot.x, spot.y)


def inside(rects: tuple, x: float, y: float) -> bool:
    return any(left <= x <= right and top <= y <= bottom for left, top, right, bottom in rects)


def meets(a: tuple, b: tuple) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class OrderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.order = route.read_order(route.ORDER_PATH.read_text())

    def test_every_pad_of_the_order_is_on_its_net_in_the_circuit(self) -> None:
        nets = circuit_nets()
        for line in self.order:
            for pad in line.pads:
                self.assertEqual(nets.get(pad), line.net, f"{line.net} {pad}")

    def test_a_single_pad_line_is_a_via_into_a_plane(self) -> None:
        for line in self.order:
            if len(line.pads) == 1:
                self.assertIn(line.net, route.PLANE_NETS, line)

    def test_a_net_without_a_plane_is_drawn_whole(self) -> None:
        nets = circuit_nets()
        whole = route.whole_nets(self.order)
        self.assertEqual(whole, {"BUCK_SW", "BUCK_FB", "VBUS", "USB_CC2", *route.USB_NETS})
        for net in whole:
            drawn = {pad for line in self.order if line.net == net for pad in line.pads}
            self.assertEqual(drawn, {pad for pad, on in nets.items() if on == net}, net)

    def test_the_usb_lines_stay_on_their_layer(self) -> None:
        usb = [line for line in self.order if line.net in route.USB_NETS]
        self.assertEqual({line.net for line in usb}, set(route.USB_NETS))
        self.assertTrue(all(not line.vias for line in usb))

    def test_the_hot_loop_and_the_limited_nets_are_drawn(self) -> None:
        groups = [line for line in self.order if len(line.pads) > 1]
        loop = set().union(*(line.pads for line in groups if set(line.pads) <= route.HOT_LOOP_PADS))
        self.assertEqual(loop, route.HOT_LOOP_PADS)
        self.assertLessEqual(set(route.LENGTH_LIMIT), {line.net for line in groups})

    def test_a_line_with_an_unknown_option_is_refused(self) -> None:
        self.assertEqual(route.read_order("GND U1.1  # the module\n"), (route.Line(GND, ("U1.1",)),))
        self.assertEqual(route.read_order("N A.1 B.1 wide no-via"), (route.Line("N", ("A.1", "B.1"), True, False),))
        with self.assertRaises(AssertionError):
            route.read_order("N A.1 B.1 thick")
        with self.assertRaises(AssertionError):
            route.read_order("N wide")


class PlaneTest(unittest.TestCase):
    def test_the_five_volt_island_holds_the_input_side_and_no_three_volt_part(self) -> None:
        for ref in ("F1", "C1", "U2"):
            self.assertTrue(inside(route.V5_ISLAND, *spot_xy(ref)), ref)
        for ref in ("L1", "C2", "R7", "C3", "C4", "U1"):
            self.assertFalse(inside(route.V5_ISLAND, *spot_xy(ref)), ref)

    def test_no_plane_reaches_into_the_antenna_keepout(self) -> None:
        keepout = route.antenna_keepout()
        for plane in route.planes():
            for rect in plane.rects:
                self.assertFalse(meets(rect, keepout), plane)

    def test_the_keepout_is_the_board_cut_grown_by_the_setback(self) -> None:
        left, front, width, depth = place.BOARD["antenna"]["board_cut"]
        setback = route.ANTENNA_SETBACK
        self.assertEqual(route.antenna_keepout(), (left - setback, place.DEPTH - (front + depth) - setback,
                                                   left + width + setback, place.DEPTH - front + setback))

    def test_each_slot_keepout_is_the_slot_grown_by_the_edge_clearance(self) -> None:
        slots = place.PCB["board_slots"]
        self.assertEqual(len(route.slot_keepouts()), len(slots))
        clear = route.RULES.edge_clearance
        for (left, front, width, depth), rect in zip(slots, route.slot_keepouts()):
            wanted = (left - clear, place.DEPTH - (front + depth) - clear, left + width + clear, place.DEPTH - front + clear)
            for got, want in zip(rect, wanted):
                self.assertAlmostEqual(got, want, places=9)

    def test_ground_and_three_volt_planes_cover_the_board_outside_the_keepout(self) -> None:
        keepout = route.antenna_keepout()
        by_net = {plane.net: plane for plane in route.planes()}
        self.assertEqual((by_net[GND].layer, by_net[V3].layer, by_net[V5].layer),
                         (route.GROUND_PLANE, route.POWER_PLANE, route.POWER_PLANE))
        self.assertGreater(by_net[V5].priority, by_net[V3].priority)
        for x in range(0, int(place.WIDTH) + 1, 2):
            for y in range(0, int(place.DEPTH) + 1, 2):
                if not inside((keepout,), x, y):
                    for net in (GND, V3):
                        self.assertTrue(inside(by_net[net].rects, x, y), (net, x, y))

    def test_a_via_finds_its_plane_only_where_the_plane_is(self) -> None:
        island_left, island_top, _, _ = route.V5_ISLAND[0]
        in_island = (island_left + 1.0, island_top + 1.0)
        self.assertTrue(route.plane_here(V5, *in_island))
        self.assertFalse(route.plane_here(V3, *in_island))
        self.assertFalse(route.plane_here(V5, 60.0, 80.0))
        self.assertTrue(route.plane_here(V3, 60.0, 80.0))
        left, top, right, bottom = route.antenna_keepout()
        in_keepout = ((left + right) / 2, bottom - 0.1)
        for net in route.PLANE_NETS:
            self.assertFalse(route.plane_here(net, *in_keepout), net)


class ModuleGroundTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = sexpr.parse(MODULE_FOOTPRINT.read_text())
        self.pads = sexpr.children(self.module, "pad")

    def _at(self, pad: list) -> tuple[float, float]:
        node = sexpr.child(pad, "at")
        return float(node[1]), float(node[2])

    def test_the_footprint_has_no_hole_under_the_board_minimum(self) -> None:
        for pad in self.pads:
            drill = sexpr.child(pad, "drill")
            if drill is not None:
                self.assertGreaterEqual(float(drill[1]), MIN_DRILL, sexpr.dump(pad)[:60])

    def test_the_exposed_pad_vias_keep_off_the_paste_windows(self) -> None:
        """layout.check_paste_clear_of_vias on the board: 0.15 mm from a window to the 0.3 mm drill."""
        (exposed,) = [pad for pad in self.pads if sexpr.unquoted(pad[1]) == "41"]
        centre_x, centre_y = self._at(exposed)
        windows = [pad for pad in self.pads if sexpr.unquoted(pad[1]) == ""]
        self.assertEqual(len(windows), 9)
        reach = route.RULES.via_drill / 2 + 0.15
        for dx, dy in route.EXPOSED_PAD_VIA_OFFSETS:
            x, y = centre_x + dx, centre_y + dy
            for window in windows:
                wx, wy = self._at(window)
                half = float(sexpr.child(window, "size")[1]) / 2
                gap = math.hypot(max(abs(x - wx) - half, 0.0), max(abs(y - wy) - half, 0.0))
                self.assertGreaterEqual(gap, reach, (dx, dy))


def _square(name: str, net: str, x: float, y: float, half: float = 0.3) -> Pad:
    return Pad(name, net, (x - half, y - half, x + half, y + half), (BACK,))


class RouteTest(unittest.TestCase):
    def test_the_plan_puts_four_vias_in_pad_41_and_joins_a_line(self) -> None:
        exposed = Pad(route.EXPOSED_PAD, GND, (68.0, 13.0, 72.0, 17.0), (BACK,))
        pads = [exposed, _square("A.1", "N", 20.0, 40.0), _square("B.1", "N", 25.0, 40.0)]
        result = route.route(pads, [], (route.Line("N", ("A.1", "B.1")),))
        self.assertEqual(result.unrouted, [])
        self.assertEqual(sorted((via.x, via.y) for via in result.vias if via.net == GND),
                         [(69.3, 14.3), (69.3, 15.7), (70.7, 14.3), (70.7, 15.7)])
        self.assertAlmostEqual(result.router.net_length("N"), 5.0, places=3)

    def test_a_pad_a_wide_track_cannot_reach_joins_the_group_with_a_normal_one(self) -> None:
        """Through a 0.7 mm gap in a wall: room for a 0.22 mm track, none for a 0.4 mm one."""
        exposed = Pad(route.EXPOSED_PAD, GND, (68.0, 13.0, 72.0, 17.0), (BACK,))
        group = [_square("A.1", "N", 2.5, 40.0), _square("B.1", "N", 2.5, 44.0), _square("C.1", "N", 8.0, 42.0)]
        wall = [Pad("W.1", "M", (4.5, 0.0, 5.5, 41.65), (BACK,)), Pad("W.2", "M", (4.5, 42.35, 5.5, place.DEPTH), (BACK,))]
        line = route.Line("N", ("A.1", "B.1", "C.1"), wide=True, vias=False)
        result = route.route([exposed, *group, *wall], [], (line,))
        self.assertEqual(result.unrouted, [])
        self.assertTrue(is_connected(result.tracks, result.vias, group[0], group[2]))
        self.assertEqual({track.width for track in result.tracks}, {route.TRACK_WIDTH, route.WIDE_TRACK_WIDTH})

    def test_every_surface_supply_pad_gets_a_via_and_a_through_hole_pad_none(self) -> None:
        """Freerouting joins no pad to a closed plane (report 09 pitfall 3), so the plan gives each one a via."""
        exposed = Pad(route.EXPOSED_PAD, GND, (68.0, 13.0, 72.0, 17.0), (BACK,))
        ground, three_volt = _square("A.1", GND, 20.0, 40.0), _square("B.1", V3, 30.0, 40.0)
        through_hole = Pad("C.1", GND, (39.7, 39.7, 40.3, 40.3), (FRONT, BACK))
        signal = _square("D.1", "N", 50.0, 40.0)
        result = route.route([exposed, ground, three_volt, through_hole, signal], [], ())
        self.assertEqual(result.unrouted, [])
        near = {pad.name for pad in (ground, three_volt, through_hole, signal)
                if any(via.net == pad.net and math.dist((via.x, via.y), pad.centre) < 2.0 for via in result.vias)}
        self.assertEqual(near, {"A.1", "B.1"})
        self.assertEqual(len(result.vias), 4 + 2, "pad 41's four, then one each, no second via for pad 41")

    def test_a_supply_pad_the_order_already_joins_gets_no_second_via(self) -> None:
        exposed = Pad(route.EXPOSED_PAD, GND, (68.0, 13.0, 72.0, 17.0), (BACK,))
        pads = [exposed, _square("A.1", GND, 20.0, 40.0), _square("B.1", GND, 23.0, 40.0)]
        result = route.route(pads, [], (route.Line(GND, ("A.1", "B.1")), route.Line(GND, ("A.1",))))
        self.assertEqual(result.unrouted, [])
        self.assertEqual(len(result.vias), 4 + 1)

    def test_a_pad_on_another_net_than_the_order_says_stops_the_plan(self) -> None:
        exposed = Pad(route.EXPOSED_PAD, GND, (68.0, 13.0, 72.0, 17.0), (BACK,))
        pads = [exposed, _square("A.1", "N", 20.0, 40.0), _square("B.1", "M", 25.0, 40.0)]
        with self.assertRaises(AssertionError):
            route.route(pads, [], (route.Line("N", ("A.1", "B.1")),))


def _result(tracks: list[Track], vias: list[Via] = (), loop: float = 5.0) -> route.Result:
    router = Router(10.0, 10.0, 1.0)
    router.tracks.extend(tracks)
    router.vias.extend(vias)
    return route.Result(router, [], {route.Line(V5, ("C1.1", "U2.4")): loop})


def _good(usb_p: float = 50.0, usb_n: float = 51.0, layer: int = BACK) -> list[Track]:
    def track(net: str, length: float, on: int = BACK) -> Track:
        return Track(net, on, (0.0, 0.0), (length, 0.0), 0.22)
    return [track("BUCK_SW", 2.0), track("BUCK_FB", 3.0), track("USB_D_P", usb_p, layer), track("USB_DP", 1.0),
            track("USB_D_N", usb_n), track("USB_DM", 1.0)]


class LimitTest(unittest.TestCase):
    def test_copper_inside_every_limit_passes(self) -> None:
        self.assertEqual(route.problems(_result(_good())), [])

    def test_a_usb_pair_further_apart_than_the_limit_fails(self) -> None:
        found = route.problems(_result(_good(usb_n=50.0 + route.USB_PAIR_MISMATCH_LIMIT + 0.1)))
        self.assertEqual(len(found), 1)
        self.assertIn("differ", found[0])

    def test_a_usb_track_off_the_bottom_layer_or_a_usb_via_fails(self) -> None:
        self.assertEqual(len(route.problems(_result(_good(layer=FRONT)))), 1)
        self.assertEqual(len(route.problems(_result(_good(), [Via("USB_DP", 1.0, 1.0)]))), 1)

    def test_a_long_or_missing_limited_net_fails(self) -> None:
        tracks = [track for track in _good() if track.net != "BUCK_FB"]
        self.assertEqual(len(route.problems(_result(tracks))), 1)
        self.assertEqual(len(route.problems(_result(_good(usb_p=route.USB_PATH_LIMIT), loop=5.0))), 2,
                         "too long, and too far from D-")

    def test_a_hot_loop_over_its_limit_fails(self) -> None:
        self.assertEqual(len(route.problems(_result(_good(), loop=route.HOT_LOOP_LIMIT + 0.1))), 1)

    def test_an_unrouted_pad_fails(self) -> None:
        result = _result(_good())
        result.unrouted.append("GND: U1.1 (no via to its plane)")
        self.assertEqual(route.problems(result), ["GND: U1.1 (no via to its plane)"])


if __name__ == "__main__":
    unittest.main()
