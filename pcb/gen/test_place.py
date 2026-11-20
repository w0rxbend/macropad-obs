# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Tests of place.py. The first class is plain Python and runs in `just pcb-test`; the second needs
pcbnew and runs in the KiCad container, as test_board.py says:

    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:$PWD" -w "$PWD" kicad/kicad:9.0.9 \\
        python3 -B -m unittest discover -s pcb/gen -p 'test_place.py'
"""

from __future__ import annotations

import importlib.util
import math
import tempfile
import tomllib
import unittest
from dataclasses import replace
from pathlib import Path

import circuit_hmi
import place
import sexpr

# Only the pcbnew the pipeline pins (kicad/kicad:9.0.9): a host KiCad of another version skips these tests.
PCBNEW_FOUND = "no pcbnew"
if importlib.util.find_spec("pcbnew") is not None:
    import pcbnew

    PCBNEW_FOUND = f"pcbnew {pcbnew.GetMajorMinorVersion()}"
HAVE_PCBNEW = PCBNEW_FOUND == "pcbnew 9.0"
PCBNEW_SKIP = f"needs pcbnew 9.0, found {PCBNEW_FOUND}: run `just pcb-test-kicad`"
if HAVE_PCBNEW:
    import contract
    import layout
    import route

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARD = tomllib.loads((REPO_ROOT / "board.toml").read_text())
THT_FOOTPRINTS = {"macropad-obs:SW_TH_Tactile_Omron_B3F-100x",
                  "macropad-obs:RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm", "macropad-obs:Hole_M2"}


def _spots() -> dict[str, tuple[float, float]]:
    """Ref -> the board.toml point the placement aimed at."""
    return {ref: (spot.x, spot.y) for ref, spot in place.spots().items()}


def _inside(point: tuple[float, float], rect: list[float]) -> bool:
    x, y = point
    left, front, width, depth = rect
    return left <= x <= left + width and front <= y <= front + depth


def _distance_to_rect(point: tuple[float, float], rect: tuple[float, float, float, float]) -> float:
    x, y = point
    left, front, right, back = rect
    return math.dist(point, (min(max(x, left), right), min(max(y, front), back)))


def _switch_sharing(net: str) -> str:
    (ref,) = [part.ref for part in circuit_hmi.PARTS
              if part.ref.startswith("SW") and net in part.nets.values()]
    return ref


def _outline_contains(path: list, x: float, y: float) -> bool:
    """Ray cast over the outline path, each arc taken as its two chords (fine at these radii)."""
    edges = []
    for kind, *points in path:
        edges += list(zip(points, points[1:])) if kind == "arc" else [tuple(points)]
    crossings = 0
    for (x1, y1), (x2, y2) in edges:
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            crossings += 1
    return crossings % 2 == 1


class PlacementTest(unittest.TestCase):
    def test_every_circuit_part_and_every_hole_is_placed_once(self) -> None:
        refs = [part.ref for part in place.board_parts()]
        holes = [f"H{n}" for n in range(1, len(BOARD["pcb"]["holes"]) + 1)]
        self.assertEqual(sorted(refs), sorted([part.ref for part in circuit_hmi.BOARD_PARTS] + holes))

    def test_holes_sit_on_the_board_toml_holes(self) -> None:
        holes = [(part.x, part.y) for part in place.board_parts() if part.value == "M2"]
        self.assertEqual(holes, [place.kicad_xy(x, y) for x, y in BOARD["pcb"]["holes"]])

    def test_keys_buttons_and_knobs_sit_on_their_board_toml_points(self) -> None:
        spots = _spots()
        keys = [spots[f"SW{n}"] for n in range(1, 10)]
        self.assertEqual(keys, [(x, y) for y in BOARD["keys"]["y"] for x in BOARD["keys"]["x"]])
        self.assertEqual([spots[f"SW{n}"] for n in range(10, 14)],
                         [(x, BOARD["buttons"]["y"]) for x in BOARD["buttons"]["x"]])
        self.assertEqual([spots[f"SW{n}"] for n in range(14, 17)],
                         [(BOARD["knobs"]["x"], y) for y in BOARD["knobs"]["y"]])

    def test_only_through_hole_parts_are_on_the_top_face(self) -> None:
        # Report 12: every SMT part, the hot-swap sockets with them, is on the bottom face.
        for part in place.board_parts():
            wanted = place.TOP if part.footprint in THT_FOOTPRINTS else place.BOTTOM
            self.assertEqual(part.side, wanted, part.ref)

    def test_module_jack_and_tails_sit_where_board_toml_puts_them(self) -> None:
        spots = _spots()
        left, front, width, depth = BOARD["mcu"]["outline"]
        self.assertEqual(spots["U1"], (left + width / 2, front + depth / 2))
        usb = BOARD["usb"]
        self.assertEqual(spots["J1"], (usb["x"], BOARD["pcb"]["depth"] + usb["mouth_overhang"]))
        self.assertEqual(spots["J3"], tuple(BOARD["fpc"]["big"]["centre"]))
        self.assertEqual(spots["J4"], tuple(BOARD["fpc"]["narrow"]["centre"]))
        side = BOARD["bottom_side"]
        self.assertEqual((spots["SW20"], spots["SW21"], spots["J2"]),
                         (tuple(side["boot"]), tuple(side["reset"]), tuple(side["debug_uart"]["at"])))

    def test_buck_parts_sit_in_the_regulator_zone(self) -> None:
        spots = _spots()
        for ref in ("U2", "C1", "L1", "R7", "R8", "C2"):
            self.assertTrue(_inside(spots[ref], BOARD["regulator"]["zone"]), ref)

    def test_usb_support_parts_sit_within_the_support_radius_of_the_jack(self) -> None:
        spots, usb = _spots(), BOARD["usb"]
        mouth = BOARD["pcb"]["depth"] + usb["mouth_overhang"]
        width, depth = usb["body"]
        body = (usb["x"] - width / 2, mouth - depth, usb["x"] + width / 2, mouth)
        for ref in ("R1", "R2", "R3", "R4", "U3", "F1"):
            self.assertLessEqual(_distance_to_rect(spots[ref], body), BOARD["bottom_side"]["usb_support_radius"], ref)

    def test_usb_series_resistors_sit_in_line_with_their_module_pads(self) -> None:
        """Report 10 block 4: the 22 ohm resistors "placed close to the chip", beside pads 13 (IO19, D-)
        and 14 (IO20, D+) on the module's right edge."""
        spots = _spots()
        left, front, width, depth = BOARD["mcu"]["outline"]
        module = sexpr.parse((REPO_ROOT / "pcb" / "lib" / "macropad-obs.pretty" / "ESP32-S3-WROOM-1.kicad_mod").read_text())
        pad_y = {sexpr.unquoted(pad[1]): float(sexpr.child(pad, "at")[2]) for pad in sexpr.children(module, "pad")}
        for ref, pad in (("R5", "13"), ("R6", "14")):
            x, y = spots[ref]
            self.assertLessEqual(x - (left + width), 2.0, ref)
            # The footprint's y runs from the antenna end; board.toml's y runs towards it.
            self.assertAlmostEqual(y, front + depth / 2 - pad_y[pad], places=2, msg=ref)

    def test_sinks_pull_ups_and_encoder_filters_sit_in_the_mcu_zone(self) -> None:
        spots = _spots()
        refs = ["U4", "R12", "R13", "U5", "R14", "R15"] + [f"R{n}" for n in range(20, 24)]
        refs += [f"R{n}" for n in range(25, 36, 2)] + [f"C{n}" for n in range(20, 26)]
        for ref in refs:
            self.assertTrue(_inside(spots[ref], BOARD["bottom_side"]["mcu_zone"]), ref)

    def test_each_matrix_diode_is_nearest_the_switch_it_serves(self) -> None:
        spots = _spots()
        switches = [ref for ref in spots if ref.startswith("SW") and int(ref[2:]) <= 16]
        for diode in (part for part in circuit_hmi.PARTS if part.ref.startswith("D")):
            nearest = min(switches, key=lambda ref: math.dist(spots[ref], spots[diode.ref]))
            self.assertEqual(nearest, _switch_sharing(diode.nets["2"]), diode.ref)

    def test_each_encoder_pull_up_is_nearest_its_encoder(self) -> None:
        spots = _spots()
        encoders = ["SW14", "SW15", "SW16"]
        for number, encoder in enumerate(encoders, start=1):
            for phase in ("A", "B"):
                (pull_up,) = [part.ref for part in circuit_hmi.PARTS
                              if part.value == "3.3k" and f"ENC{number}_{phase}_RAW" in part.nets.values()]
                nearest = min(encoders, key=lambda ref: math.dist(spots[ref], spots[pull_up]))
                self.assertEqual(nearest, encoder, pull_up)

    def test_outline_is_one_closed_path(self) -> None:
        path = place.outline_path()
        ends = [(points[0], points[-1]) for _, *points in path]
        for (_, end), (start, _) in zip(ends, ends[1:] + ends[:1]):
            self.assertLess(math.dist(end, start), 1e-9)

    def test_outline_rounds_three_board_corners_and_the_three_cut_corners(self) -> None:
        radii = []
        for kind, start, middle, end in (segment for segment in place.outline_path() if segment[0] == "arc"):
            # The circumradius of the three arc points.
            a, b, c = math.dist(start, middle), math.dist(middle, end), math.dist(start, end)
            area = abs((middle[0] - start[0]) * (end[1] - start[1]) - (end[0] - start[0]) * (middle[1] - start[1])) / 2
            radii.append(round(a * b * c / (4 * area), 3))  # kicad_xy rounds the points to 0.1 um
        corner = BOARD["pcb"]["corner_radius"]
        self.assertEqual(sorted(radii), sorted([corner] * 3 + [place.ANTENNA_CUT_CORNER_RADIUS] * 3))

    def test_outline_spans_the_board_and_leaves_out_the_antenna_cut(self) -> None:
        path = place.outline_path()
        points = [point for _, *segment in path for point in segment]
        self.assertEqual((min(p[0] for p in points), max(p[0] for p in points)), (0.0, BOARD["pcb"]["width"]))
        self.assertEqual((min(p[1] for p in points), max(p[1] for p in points)), (0.0, BOARD["pcb"]["depth"]))
        left, front, width, depth = BOARD["antenna"]["area"]
        for x, y in ((left + 0.1, front + 0.1), (left + width / 2, front + depth / 2), (left + width - 0.1, front + 0.1)):
            self.assertFalse(_outline_contains(path, *place.kicad_xy(x, y)), (x, y))
        self.assertTrue(_outline_contains(path, *place.kicad_xy(BOARD["pcb"]["width"] / 2, 100.0)))


def _moved(ref: str, x: float, y: float) -> tuple[place.PlacedPart, ...]:
    """The board's parts with one footprint origin moved to this board.toml point."""
    return tuple(replace(part, x=place.kicad_xy(x, y)[0], y=place.kicad_xy(x, y)[1]) if part.ref == ref else part
                 for part in place.board_parts())


@unittest.skipUnless(HAVE_PCBNEW, PCBNEW_SKIP)
class PlacedBoardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.board_path = Path(tempfile.mkdtemp()) / "probe.kicad_pcb"

    def _saved_board(self, parts: tuple[place.PlacedPart, ...]) -> pcbnew.BOARD:
        board = layout.build_board(self.board_path, parts, {})
        pcbnew.SaveBoard(str(self.board_path), board)
        return pcbnew.LoadBoard(str(self.board_path))

    def test_placed_board_meets_the_contract(self) -> None:
        board = self._saved_board(place.board_parts())
        for check in contract.CHECKS:
            check(board)

    def test_bottom_parts_are_mirrored_and_top_parts_are_not(self) -> None:
        board = self._saved_board(place.board_parts())
        for part in place.board_parts():
            self.assertEqual(board.FindFootprintByReference(part.ref).IsFlipped(), part.side == place.BOTTOM, part.ref)

    def test_contract_finds_a_part_off_its_board_toml_point(self) -> None:
        board = self._saved_board(_moved("SW5", 31.65, 43.65))
        with self.assertRaisesRegex(AssertionError, "key"):
            contract.check_positions(board)

    def test_contract_finds_a_top_part_under_a_carrier(self) -> None:
        board = self._saved_board(_moved("SW10", 20.0, 120.0))
        with self.assertRaisesRegex(AssertionError, "SW10 .*big carrier"):
            contract.check_carriers(board)

    def test_contract_finds_a_hole_under_a_carrier(self) -> None:
        board = self._saved_board(_moved("H6", 30.0, 130.0))
        with self.assertRaisesRegex(AssertionError, "hole .*big carrier"):
            contract.check_carriers(board)

    def test_contract_finds_a_tall_part_beside_a_pocket(self) -> None:
        # Knob 1's courtyard reaches 8.55 behind its shaft: 0.5 short of the narrow pocket's skirt edge.
        pocket_front = BOARD["narrow_display"]["pocket"][1]
        board = self._saved_board(_moved_knob("SW14", pocket_front - 1.0 - 8.55 + 0.5))
        with self.assertRaisesRegex(AssertionError, "SW14 .*narrow pocket"):
            contract.check_pocket_skirt(board)

    def test_contract_finds_copper_in_the_antenna_cut(self) -> None:
        # In the cut, right of the module's courtyard.
        left, front, width, depth = BOARD["antenna"]["board_cut"]
        board = self._saved_board(_moved("C4", left + width - 6.6, front + depth / 2))
        with self.assertRaisesRegex(AssertionError, "C4 .*antenna"):
            contract.check_antenna(board)

    def test_route_planes_keep_the_antenna_setback_and_a_whole_board_pour_does_not(self) -> None:
        """The fill keeps only the 0.3 mm edge clearance from the cut; route.py's planes stop at its setback."""
        whole_board = route.Plane("GND", route.GROUND_PLANE, ((0.0, 0.0, place.WIDTH, place.DEPTH),))
        for planes, wanted in ((route.planes(), []), ((whole_board,), ["GND pour on In2.Cu"])):
            board = layout.build_board(self.board_path, place.board_parts(), {})
            layout.add_planes(board, planes)
            pcbnew.SaveBoard(str(self.board_path), board)
            board = pcbnew.LoadBoard(str(self.board_path))
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            contract.check_antenna(board)
            self.assertEqual(contract.copper_in(board, route.antenna_keepout()), wanted)

    def test_overlapping_courtyards_fail_the_build(self) -> None:
        r1 = place.spots()["R1"]
        parts = _moved("R2", r1.x + 0.5, r1.y)
        with self.assertRaisesRegex(AssertionError, "R1 and R2 courtyards overlap"):
            layout.build_board(self.board_path, parts, {})


def _moved_knob(ref: str, shaft_y: float) -> tuple[place.PlacedPart, ...]:
    """The board's parts with one knob's shaft moved along y, footprint and all."""
    shift = shaft_y - place.spots()[ref].y
    return tuple(replace(part, y=round(part.y - shift, 4)) if part.ref == ref else part
                 for part in place.board_parts())


if __name__ == "__main__":
    unittest.main()
