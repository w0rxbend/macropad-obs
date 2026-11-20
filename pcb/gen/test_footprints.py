# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Tests of the project footprint library (pcb/lib/macropad-obs.pretty) against board.toml and
the drawings cited in pcb/lib/SOURCES.txt. Plain Python: no KiCad.

    python3 -m unittest discover -s pcb/gen -p 'test_*.py'
"""

from __future__ import annotations

import io
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

import sexpr

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "pcb" / "lib" / "macropad-obs.pretty"
SOURCES = ROOT / "pcb" / "lib" / "SOURCES.txt"
FAB = ROOT / "pcb" / "fab"
PLACEHOLDER = "PLACEHOLDER_"
TOLERANCE = 0.01  # board.toml rounds to two decimals (rear shell pad 162.675 -> 162.68)

# WROOM-1 datasheet v1.8 figure 10-1 (top view): the antenna's feed and ground legs meet the
# module body on the pin 40 side; the far end of the meander, over pin 1, is open.
FEED_PIN = "40"
# Espressif keep-out text in board.toml [antenna]: board allowed at most 2 beyond the feed side.
FEED_SIDE_ALLOWANCE = 2.0
COPPER_LAYERS = {'"F.Cu"', '"In1.Cu"', '"In2.Cu"', '"B.Cu"'}
# The 16 contacts of a USB 2.0 Type-C receptacle; GCT USB4216 drawing rev A2 pin table.
USB_PINS = {
    "A1", "A4", "A5", "A6", "A7", "A8", "A9", "A12",
    "B1", "B4", "B5", "B6", "B7", "B8", "B9", "B12",
}


def board() -> dict:
    return tomllib.loads((ROOT / "board.toml").read_text(encoding="utf-8"))


def footprint(name: str) -> list:
    return sexpr.parse((LIB / f"{name}.kicad_mod").read_text(encoding="utf-8"))


def numbers(node: list) -> list[float]:
    return [float(atom) for atom in node[1:] if isinstance(atom, str)]


def pads(module: list) -> list[dict]:
    """Each pad as name, kind, at (x, y), size (w, h) and drill (first number or None)."""
    found = []
    for pad in sexpr.children(module, "pad"):
        drill = sexpr.child(pad, "drill")
        drill_numbers = [float(atom) for atom in drill[1:] if atom != "oval"] if drill else []
        found.append({
            "name": sexpr.unquoted(pad[1]),
            "kind": pad[2],
            "at": tuple(numbers(sexpr.child(pad, "at"))[:2]),
            "size": tuple(numbers(sexpr.child(pad, "size"))),
            "drill": drill_numbers[0] if drill_numbers else None,
            "layers": set(sexpr.child(pad, "layers")[1:]),
        })
    return found


def copper_pads(module: list, name: str) -> list[dict]:
    return [pad for pad in pads(module) if pad["name"] == name and pad["kind"] == "smd"
            and '"F.Cu"' in pad["layers"]]


def source_blocks() -> dict[str, str]:
    """SOURCES.txt entries: a line `<file>.kicad_mod:` at column 0 opens a block."""
    blocks: dict[str, list[str]] = {}
    current = None
    for line in SOURCES.read_text(encoding="utf-8").splitlines():
        if line.endswith(".kicad_mod:") and not line[0].isspace():
            current = line[:-1]
            blocks[current] = []
        elif current:
            blocks[current].append(line)
    return {name: "\n".join(lines) for name, lines in blocks.items()}


def placeholder_hits(fab_dir: Path) -> list[str]:
    """Files under fab_dir, and members of zip files there, that name a PLACEHOLDER_ footprint."""
    hits = []
    for path in sorted(p for p in fab_dir.rglob("*") if p.is_file()):
        raw = path.read_bytes()
        if PLACEHOLDER.encode() in raw:
            hits.append(str(path.relative_to(fab_dir)))
        if zipfile.is_zipfile(io.BytesIO(raw)):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                hits += [f"{path.name}:{member}" for member in archive.namelist()
                         if PLACEHOLDER.encode() in archive.read(member)]
    return hits


def mirrored_side(x: float) -> str:
    """Side of a footprint x in the PCB top view once the part is flipped to the bottom face."""
    return "left" if -x < 0 else "right"


class Provenance(unittest.TestCase):
    def test_every_footprint_cites_its_drawing(self):
        blocks = source_blocks()
        files = sorted(path.name for path in LIB.glob("*.kicad_mod"))
        self.assertTrue(files)
        self.assertEqual(sorted(blocks), files)
        for name, text in blocks.items():
            with self.subTest(name):
                drawing = [line for line in text.splitlines() if line.strip().startswith("Drawing:")]
                self.assertTrue(drawing and drawing[0].split(":", 1)[1].strip(), name)

    def test_footprint_name_is_its_file_name(self):
        for path in LIB.glob("*.kicad_mod"):
            with self.subTest(path.name):
                module = sexpr.parse(path.read_text(encoding="utf-8"))
                self.assertEqual(module[0], "footprint")
                self.assertEqual(sexpr.unquoted(module[1]), path.stem)

    def test_no_sk6812(self):
        for path in LIB.parent.rglob("*"):
            if path.is_file():
                self.assertNotIn("sk6812", path.read_text(encoding="utf-8").lower(), path.name)


class Placeholders(unittest.TestCase):
    def test_each_fpc_has_a_footprint(self):
        names = [path.stem for path in LIB.glob("*.kicad_mod")]
        for pins in (40, 10):
            with self.subTest(pins):
                fpc = [name for name in names if name.startswith((PLACEHOLDER + "FPC", "FPC_"))
                       and f"-{pins}S" in name]
                self.assertEqual(len(fpc), 1, fpc)

    def test_placeholder_declares_itself(self):
        for path in LIB.glob(PLACEHOLDER + "*.kicad_mod"):
            with self.subTest(path.name):
                module = sexpr.parse(path.read_text(encoding="utf-8"))
                descr = sexpr.unquoted(sexpr.child(module, "descr")[1])
                self.assertTrue(descr.startswith("PLACEHOLDER"), descr)

    def test_guard_finds_a_placeholder_in_fab_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            (fab / "cpl.csv").write_text("J3,PLACEHOLDER_FPC_FH12-40S,1.0,2.0,0,bottom\n")
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("board-B_Cu.gbl", "%TO.CFtp,PLACEHOLDER_FPC_FH12-10S*%\n")
            (fab / "gerbers.zip").write_bytes(buffer.getvalue())
            (fab / "bom.csv").write_text("J1,USB_C_Receptacle_GCT_USB4216-03-A\n")
            self.assertEqual(placeholder_hits(fab),
                             ["cpl.csv", "gerbers.zip:board-B_Cu.gbl"])

    def test_no_placeholder_reaches_fab(self):
        self.assertEqual(placeholder_hits(FAB), [])


class Antenna(unittest.TestCase):
    def setUp(self):
        self.module = footprint("ESP32-S3-WROOM-1")
        self.antenna = board()["antenna"]

    def test_feed_side_in_board_toml_is_read_from_the_footprint(self):
        (feed_pad,) = copper_pads(self.module, FEED_PIN)
        (pin_1,) = copper_pads(self.module, "1")
        self.assertGreater(feed_pad["at"][0], 0)
        self.assertLess(pin_1["at"][0], 0)
        self.assertEqual(self.antenna["feed_side"], mirrored_side(feed_pad["at"][0]))

    def test_board_cut_allows_two_on_the_feed_side(self):
        area, cut = self.antenna["area"], self.antenna["board_cut"]
        side = self.antenna["feed_side"]
        beyond = area[0] - cut[0] if side == "left" else cut[0] + cut[2] - area[0] - area[2]
        self.assertAlmostEqual(beyond, FEED_SIDE_ALLOWANCE, delta=TOLERANCE)

    def test_keepout_covers_the_antenna_area_on_every_copper_layer(self):
        (zone,) = sexpr.children(self.module, "zone")
        self.assertIsNotNone(sexpr.child(zone, "keepout"))
        self.assertEqual(set(sexpr.child(zone, "layers")[1:]), COPPER_LAYERS)
        points = [numbers(xy) for xy in sexpr.children(sexpr.child(sexpr.child(zone, "polygon"), "pts"), "xy")]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        area = self.antenna["area"]
        self.assertAlmostEqual(max(xs) - min(xs), area[2], delta=TOLERANCE)
        self.assertAlmostEqual(max(ys) - min(ys), area[3], delta=TOLERANCE)
        pad_ys = [pad["at"][1] for pad in pads(self.module) if pad["name"]]
        self.assertLess(max(ys), min(pad_ys), "keep-out must sit at the antenna end, past pin 1")

    def test_courtyard_stays_on_the_module(self):
        outline = board()["mcu"]["outline"]
        lines = [line for line in sexpr.children(self.module, "fp_line")
                 if sexpr.child(line, "layer")[1] == '"F.CrtYd"']
        xs = [numbers(sexpr.child(line, end))[0] for line in lines for end in ("start", "end")]
        ys = [numbers(sexpr.child(line, end))[1] for line in lines for end in ("start", "end")]
        self.assertLessEqual(max(xs) - min(xs), outline[2] + 1.5)
        self.assertLessEqual(max(ys) - min(ys), outline[3] + 1.5)


class UsbC(unittest.TestCase):
    """Footprint origin: the shell front (mouth) on the centre line; pads at negative y."""

    def setUp(self):
        layout = board()
        self.usb = layout["usb"]
        self.mouth_y = layout["pcb"]["depth"] + self.usb["mouth_overhang"]
        self.module = footprint("USB_C_Receptacle_GCT_USB4216-03-A")

    def placed(self, at: tuple[float, float]) -> tuple[float, float]:
        """PCB top-view centre of a footprint point, the part on the bottom face, mouth at the back."""
        return (self.usb["x"] - at[0], self.mouth_y + at[1])

    def assertPointsEqual(self, got, want):
        self.assertEqual(len(got), len(want))
        for g, w in zip(sorted(got), sorted(want)):
            for a, b in zip(g, w):
                self.assertAlmostEqual(a, b, delta=TOLERANCE)

    def test_shell_pads_match_board_toml(self):
        shell = [pad for pad in pads(self.module) if pad["name"] == "S1"]
        got = [self.placed(pad["at"]) + pad["size"] for pad in shell]
        self.assertPointsEqual(got, [tuple(pad) for pad in self.usb["shell_pads"]])
        self.assertTrue(all(pad["kind"] == "smd" for pad in shell))

    def test_peg_holes_match_board_toml(self):
        pegs = [pad for pad in pads(self.module) if pad["kind"] == "np_thru_hole"]
        self.assertEqual({pad["drill"] for pad in pegs}, {self.usb["peg_holes"]["diameter"]})
        self.assertPointsEqual([self.placed(pad["at"]) for pad in pegs],
                               [tuple(at) for at in self.usb["peg_holes"]["at"]])

    def test_every_contact_has_one_pad_in_one_row(self):
        contacts = [pad for pad in pads(self.module) if pad["name"] in USB_PINS]
        self.assertEqual(sorted(pad["name"] for pad in contacts), sorted(USB_PINS))
        self.assertEqual(len({pad["at"][1] for pad in contacts}), 1)
        self.assertEqual(len({pad["at"] for pad in contacts}), 12)

    def test_rows_that_share_a_pad_carry_the_same_signal(self):
        by_place = {}
        for pad in pads(self.module):
            if pad["name"] in USB_PINS:
                by_place.setdefault(pad["at"], set()).add(pad["name"])
        shared = sorted(sorted(names) for names in by_place.values() if len(names) == 2)
        self.assertEqual(shared, [["A1", "B12"], ["A12", "B1"], ["A4", "B9"], ["A9", "B4"]])


class Holes(unittest.TestCase):
    def setUp(self):
        self.pcb = board()["pcb"]

    def test_plain_hole_is_the_board_toml_drill(self):
        (hole,) = pads(footprint("Hole_M2"))
        self.assertEqual(hole["kind"], "np_thru_hole")
        self.assertEqual(hole["drill"], self.pcb["hole_diameter"])

    def test_ground_bond_ring_fills_the_hole_keepout(self):
        (hole,) = pads(footprint("Hole_M2_Ground"))
        self.assertEqual(hole["kind"], "thru_hole")
        self.assertEqual(hole["drill"], self.pcb["hole_diameter"])
        self.assertEqual(hole["size"], (self.pcb["hole_keepout_diameter"],) * 2)
        self.assertIn('"*.Cu"', hole["layers"])


class Hmi(unittest.TestCase):
    def test_board_toml_footprints_are_in_the_library(self):
        layout = board()
        for table in ("buttons", "knobs"):
            with self.subTest(table):
                name = layout[table]["footprint"].split(":", 1)[1]
                self.assertTrue((LIB / f"{name}.kicad_mod").is_file(), name)

    def test_b3f_holes_are_6_5_by_4_5_drill_1_0(self):
        (name,) = [board()["buttons"]["footprint"].split(":", 1)[1]]
        holes = pads(footprint(name))
        self.assertEqual({pad["drill"] for pad in holes}, {1.0})
        self.assertEqual(sorted(pad["at"] for pad in holes),
                         [(0.0, 0.0), (0.0, 4.5), (6.5, 0.0), (6.5, 4.5)])

    def test_mx_hotswap_has_two_socket_pads_and_the_switch_holes(self):
        module = footprint("MX_Hotswap")
        self.assertEqual(sorted(pad["name"] for pad in pads(module) if pad["kind"] == "smd"), ["1", "2"])
        centre = [pad for pad in pads(module) if pad["at"] == (0.0, 0.0)]
        self.assertEqual([pad["drill"] for pad in centre], [4.0])


if __name__ == "__main__":
    unittest.main()
