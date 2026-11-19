#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Draw a layout TOML as a to-scale SVG top view: draw_layout.py [LAYOUT.toml OUT.svg].
With no arguments it redraws docs/images/layout-v2.svg and .png from docs/spec/layout-v2.toml;
the PNG needs rsvg-convert.
Frame: PCB frame, origin front-left, +x right, +y toward the back, mm."""

import subprocess
import sys
import tomllib
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = ROOT / "docs" / "spec" / "layout-v2.toml"
PICTURE = ROOT / "docs" / "images" / "layout-v2.svg"
PNG_ZOOM = "2"  # 8 px per mm, the size of the approved picture
PX = 4.0  # SVG user units per mm
MARGIN = 14.0  # mm around the body
STYLE = {
    "body": "fill:#f4f4f2;stroke:#222;stroke-width:0.6",
    "pcb": "fill:#dfeee0;stroke:#2a7a3a;stroke-width:0.35;stroke-dasharray:2 1",
    "module": "fill:#c8ccd4;stroke:#333;stroke-width:0.35",
    "active": "fill:#1f2a44;stroke:none",
    "lens": "fill:none;stroke:#e08a00;stroke-width:0.25;stroke-dasharray:1 0.6",
    "cap": "fill:#ffffff;stroke:#111;stroke-width:0.4",
    "plate": "fill:none;stroke:#999;stroke-width:0.2",
    "knob": "fill:#555;stroke:#111;stroke-width:0.4",
    "keepout": "fill:none;stroke:#b33;stroke-width:0.2;stroke-dasharray:0.8 0.5",
    "hole": "fill:#fff;stroke:#b33;stroke-width:0.3",
    "fpc": "fill:#e9c46a;stroke:#8a6d1d;stroke-width:0.25;stroke-dasharray:1 0.5;opacity:0.6",
    "pocket": "fill:none;stroke:#557;stroke-width:0.15",
    "slot": "fill:#333;stroke:none",
    "post": "fill:none;stroke:#2a5db0;stroke-width:0.2;stroke-dasharray:0.6 0.4",
    "usb": "fill:#9ab;stroke:#234;stroke-width:0.3;stroke-dasharray:1 0.5;opacity:0.7",
    "under": "fill:none;stroke:#444;stroke-width:0.3;stroke-dasharray:1 0.5",
    "pad": "fill:none;stroke:#b33;stroke-width:0.25;stroke-dasharray:0.6 0.4",
    "cut": "fill:#f4f4f2;stroke:#b33;stroke-width:0.3",
    "insert": "fill:#f2c14e;stroke:#7a5a00;stroke-width:0.3",
    "carrier": "fill:none;stroke:#7b3fa0;stroke-width:0.25",
}


class Svg:
    def __init__(self, x0, y0, w, h):
        self.x0, self.y1 = x0 - MARGIN, y0 + h + MARGIN
        self.w, self.h = w + 2 * MARGIN, h + 2 * MARGIN
        self.items = []

    def pt(self, x, y):
        return (x - self.x0) * PX, (self.y1 - y) * PX

    def rect(self, x, y, w, h, style, r=0.0):
        sx, sy = self.pt(x, y + h)
        self.items.append(
            f'<rect x="{sx:.2f}" y="{sy:.2f}" width="{w * PX:.2f}" height="{h * PX:.2f}" '
            f'rx="{r * PX:.2f}" style="{scale_style(style)}"/>'
        )

    def centred_rect(self, cx, cy, w, h, style, r=0.0):
        self.rect(cx - w / 2, cy - h / 2, w, h, style, r)

    def circle(self, cx, cy, d, style):
        sx, sy = self.pt(cx, cy)
        self.items.append(
            f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="{d / 2 * PX:.2f}" style="{scale_style(style)}"/>'
        )

    def line(self, x1, y1, x2, y2, width=0.4):
        (a, b), (c, d) = self.pt(x1, y1), self.pt(x2, y2)
        self.items.append(
            f'<line x1="{a:.2f}" y1="{b:.2f}" x2="{c:.2f}" y2="{d:.2f}" '
            f'style="stroke:#111;stroke-width:{width * PX:.2f}"/>'
        )

    def text(self, x, y, s, size=2.4, colour="#111", anchor="middle"):
        sx, sy = self.pt(x, y)
        self.items.append(
            f'<text x="{sx:.2f}" y="{sy:.2f}" font-family="sans-serif" font-size="{size * PX:.2f}" '
            f'fill="{colour}" text-anchor="{anchor}" dominant-baseline="middle">{escape(s)}</text>'
        )

    def render(self):
        w, h = self.w * PX, self.h * PX
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
                f'viewBox="0 0 {w:.2f} {h:.2f}">\n<rect width="100%" height="100%" fill="#fff"/>')
        return "\n".join([head, *self.items, "</svg>\n"])


def scale_style(style):
    """Turn mm stroke widths and dash lengths into SVG user units."""
    out = []
    for part in style.split(";"):
        key, _, val = part.partition(":")
        if key in ("stroke-width", "stroke-dasharray"):
            val = " ".join(f"{float(v) * PX:g}" for v in val.split())
        out.append(f"{key}:{val}")
    return ";".join(out)


def draw_display(svg, d, name, carrier):
    svg.rect(*d["pocket"], STYLE["pocket"])
    svg.rect(*carrier["outer"], STYLE["carrier"])
    svg.rect(*d["outline"], STYLE["module"])
    svg.rect(*d["active"], STYLE["active"])
    svg.rect(*d["lens_opening"], STYLE["lens"])
    x, y, w, h = d["active"]
    svg.text(x + w / 2, y + h / 2 + 3, name, 3.0, "#fff")
    svg.text(x + w / 2, y + h / 2 - 1.5, f"active {w:g} x {h:g}", 2.0, "#cfd6e6")
    ow, oh = d["outline"][2:]
    svg.text(x + w / 2, y + h / 2 - 5, f"module {ow:g} x {oh:g}", 2.0, "#cfd6e6")


def draw_antenna(svg, ant):
    """Board cut for the antenna keep-out, the antenna area, and the back-wall insert."""
    svg.rect(*ant["board_cut"], STYLE["cut"])
    svg.rect(*ant["area"], STYLE["under"])
    x, y, w, h = ant["area"]
    svg.text(x + w / 2, y + h / 2, "PCB antenna", 1.8)
    svg.rect(*ant["insert"]["outline"], STYLE["insert"])
    x, y, w, h = ant["insert"]["outline"]
    svg.text(x + w / 2, y + h / 2, "non-metal insert", 1.8)


def draw_under_board(svg, lay):
    """Bottom-face parts, dashed: USB-C with its shell pads and pegs, module, buck."""
    pcb, usb = lay["pcb"], lay["usb"]
    uw, uh = usb["body"]
    mouth_y = pcb["depth"] + usb["mouth_overhang"]
    svg.centred_rect(usb["x"], mouth_y - uh / 2, uw, uh, STYLE["usb"])
    for pad in usb["shell_pads"]:
        svg.centred_rect(*pad, STYLE["pad"])
    for x, y in usb["peg_holes"]["at"]:
        svg.circle(x, y, usb["peg_holes"]["diameter"], STYLE["hole"])
    svg.text(usb["x"], pcb["depth"] + 4.5, "USB-C", 2.2)
    mcu = lay["mcu"]
    svg.rect(*mcu["outline"], STYLE["under"])
    x, y, w, h = mcu["outline"]
    svg.text(x + w / 2, y + h / 2 - 3, "ESP32-S3 module", 1.8)
    svg.rect(*lay["regulator"]["zone"], STYLE["under"])
    x, y, w, h = lay["regulator"]["zone"]
    svg.text(x + w / 2, y + h / 2, "buck", 1.8)


def draw(lay):
    bx, by, bw, bh = lay["body"]["outline"]
    svg = Svg(bx, by, bw, bh)
    svg.rect(bx, by, bw, bh, STYLE["body"], lay["body"]["corner_radius"])
    pcb = lay["pcb"]
    svg.rect(0, 0, pcb["width"], pcb["depth"], STYLE["pcb"], pcb["corner_radius"])
    draw_antenna(svg, lay["antenna"])
    carriers = lay["display_carrier"]
    draw_display(svg, lay["big_display"], "BIG 3.5in 320x480", carriers["big"])
    draw_display(svg, lay["narrow_display"], "BAR 2.79in", carriers["narrow"])
    for name, f in lay["fpc"].items():
        svg.centred_rect(*f["centre"], *f["body"], STYLE["fpc"])
        svg.text(f["centre"][0], f["centre"][1], f"FPC {name}", 1.4)
    for slot in pcb["board_slots"]:
        svg.rect(*slot, STYLE["slot"])
    keys = lay["keys"]
    for row, y in enumerate(keys["y"]):
        for col, x in enumerate(keys["x"]):
            svg.centred_rect(x, y, keys["keycap"], keys["keycap"], STYLE["cap"], 1.5)
            svg.centred_rect(x, y, keys["plate_hole"], keys["plate_hole"], STYLE["plate"])
            svg.text(x, y, f"K{row * 3 + col + 1}", 2.6)
    btn = lay["buttons"]
    for i, x in enumerate(btn["x"]):
        svg.centred_rect(x, btn["y"], *btn["cap"], STYLE["cap"], 1.0)
        svg.text(x, btn["y"], f"B{i + 1}", 2.0)
    kn = lay["knobs"]
    for i, y in enumerate(kn["y"]):
        svg.circle(kn["x"], y, kn["diameter"], STYLE["knob"])
        svg.circle(kn["x"], y, 6.0, "fill:#888;stroke:#222;stroke-width:0.2")
        svg.text(kn["x"], y, f"E{i + 1}", 2.2, "#fff")
    for (x, y), digit in zip(kn["index_marks"]["at"], kn["index_marks"]["text"]):
        svg.text(x, y, digit, kn["index_marks"]["height"], "#a33")
    posts = lay["bottom_plate"]["encoder_posts"]
    for x, y in posts["at"]:
        svg.circle(x, y, lay["bottom_plate"]["encoder_post_keepout"], STYLE["post"])
    for x, y in pcb["holes"]:
        svg.circle(x, y, pcb["hole_keepout_diameter"], STYLE["keepout"])
        svg.circle(x, y, pcb["hole_diameter"], STYLE["hole"])
    draw_under_board(svg, lay)
    sx, sy = bx, by - 7.0  # 10 mm scale bar under the body
    svg.line(sx, sy, sx + 10, sy, 0.6)
    svg.line(sx, sy - 1, sx, sy + 1, 0.3), svg.line(sx + 10, sy - 1, sx + 10, sy + 1, 0.3)
    svg.text(sx + 5, sy - 2.5, "10 mm", 2.4)
    svg.text(bx + bw, sy, f"body {bw:g} x {bh:g} mm, PCB {pcb['width']:g} x {pcb['depth']:g}",
             2.4, anchor="end")
    svg.text(bx + bw / 2, by + bh + 6, f"macropad-obs layout v2 rev {lay['layout_revision']} - top view, back edge up; "
             "dashed parts sit under the board", 3.0)
    return svg.render()


def main(argv):
    if len(argv) not in (1, 3):
        sys.exit("usage: draw_layout.py [LAYOUT.toml OUT.svg]")
    source, picture = (Path(argv[1]), Path(argv[2])) if len(argv) == 3 else (LAYOUT, PICTURE)
    with open(source, "rb") as fh:
        layout = tomllib.load(fh)
    picture.write_text(draw(layout), encoding="utf-8")
    if len(argv) == 1:
        subprocess.run(
            ["rsvg-convert", "--zoom", PNG_ZOOM, "--output", str(picture.with_suffix(".png")), str(picture)],
            check=True,
        )


if __name__ == "__main__":
    main(sys.argv)
