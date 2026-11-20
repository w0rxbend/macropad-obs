# SPDX-License-Identifier: CERN-OHL-S-2.0
"""2D exports with read-back (task 6.6; spec section 1 row 8, criterion 11; report 11 section 8).

The flat case parts cut from sheet stock leave as DXF (laser, R2013, mm, layer CUT), SVG (1:1
outlines, no text) and PDF (the SVG through rsvg-convert, a 1:1 template): the lens over each
display and the foam frame under the deck. Each sheet sits in the PCB frame of board.toml, so it
registers on the deck. Read-back: DXF by `ezdxf` audit, units, layer, closed outlines, area and
extents; SVG by closed outlines, area and size; PDF by page size and no fonts. The files are
byte-repeatable: ezdxf writes fixed metadata and cairo takes SOURCE_DATE_EPOCH.

The lens is the cnc lens recess less [variants] cnc.lens_fit a side, so the one lens fits both
variants (the print recess grows). Its corner shrinks with it. Nothing here has been cut."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import ezdxf
from build123d import Axis, ExportDXF, ExportSVG, Face, Pos, RectangleRounded, Shape, Unit, Wire, import_dxf, import_svg

from obs_case import carriers, deck
from obs_case.export import EXPORTS, Readback, fresh, publish
from obs_case.spec import BOARD_TOML, LAYOUT

STAGE = BOARD_TOML.parent / ".build" / "cad" / "exports"
FOLDER = "2d"
PANELS = carriers.NAMES  # big, narrow
LAYER = "CUT"
MARGIN = 3.2  # mm of blank sheet round the part: JLCCNC asks at least 3 (report 11 section 7)
INSUNITS_MM = 4
AREA_SHARE = 1e-4  # read-back area error allowed, the B-rep share of spec 13 `cad`
SIZE_LIMIT = 0.05  # mm: read-back extents, the laser outline rule of spec 13
PT_PER_MM = 72 / 25.4
PAGE_LIMIT = 0.01  # pt between the PDF page and the SVG size; pdfinfo prints 3 places
REPEATABLE = {**os.environ, "SOURCE_DATE_EPOCH": "0", "TZ": "UTC"}  # cairo's creation date


def lens(name: str) -> Shape:
    """The lens sheet of display `name`, flat at z 0."""
    fit = LAYOUT.variants.cnc.lens_fit
    x, y, width, depth = deck.lens_recess(carriers.panel(name), -fit)
    return Pos(x + width / 2, y + depth / 2) * RectangleRounded(width, depth,
                                                                 LAYOUT.window.lens_recess_corner_radius - fit)


def foam(name: str) -> Shape:
    """The foam frame of display `name` as cut: the top face of the modelled ring, moved to z 0."""
    top = carriers.foam_frame(name).faces().sort_by(Axis.Z)[-1]
    return Pos(0, 0, -top.center().Z) * top


def sheets() -> dict[str, Shape]:
    return {**{f"lens-{name}": lens(name) for name in PANELS}, **{f"foam-{name}": foam(name) for name in PANELS}}


def export_all(stage: Path = STAGE, target: Path = EXPORTS) -> int:
    """Write every sheet under `stage`/2d, read each back, and only when all pass replace
    `target`/2d and the manifest's "2d" section. Returns 1 on any fault."""
    if shutil.which("rsvg-convert") is None or shutil.which("pdfinfo") is None:
        print("2d: rsvg-convert and pdfinfo write and read the PDF; nothing written")
        return 1
    folder = fresh(stage / FOLDER)
    readbacks = [readback for name, face in sheets().items() for readback in sheet_files(face, folder / name)]
    return publish(readbacks, stage, target, (FOLDER,), FOLDER)


def sheet_files(face: Shape, stem: Path) -> list[Readback]:
    """DXF, SVG and PDF of one flat face, each read back."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    dxf, svg, pdf = stem.with_suffix(".dxf"), stem.with_suffix(".svg"), stem.with_suffix(".pdf")
    _write_dxf(face, dxf)
    exporter = ExportSVG(unit=Unit.MM, margin=MARGIN)
    exporter.add_layer(LAYER)
    exporter.add_shape(face, layer=LAYER)
    exporter.write(str(svg))
    subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(pdf), str(svg)], check=True, env=REPEATABLE)
    return [dxf_readback(dxf, face), svg_readback(svg, face), pdf_readback(pdf, svg)]


def _write_dxf(face: Shape, path: Path) -> None:
    """ExportDXF with ezdxf's fixed metadata, set before the document is made: no create or write
    time and no random GUID."""
    fixed = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    try:
        exporter = ExportDXF(unit=Unit.MM)
        exporter.add_layer(LAYER)
        exporter.add_shape(face, layer=LAYER)
        exporter.write(str(path))
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = fixed  # the option is global


def dxf_readback(path: Path, expected: Shape) -> Readback:
    document = ezdxf.readfile(str(path))
    errors = len(document.audit().errors)
    units = document.header.get("$INSUNITS")
    layers = sorted({entity.dxf.layer for entity in document.modelspace()})
    found = _outline_facts(path, "DXF", Wire.combine(import_dxf(str(path)).edges()), expected, extents=True)
    problems = list(found.problems)
    if errors:
        problems.append(f"ezdxf audit found {errors} errors")
    if units != INSUNITS_MM:
        problems.append(f"$INSUNITS {units}, expected {INSUNITS_MM} (mm)")
    if layers != [LAYER]:
        problems.append(f"layers {layers}, expected [{LAYER!r}]")
    facts = {**found.facts, "audit_errors": errors, "layers": layers, "version": document.dxfversion}
    return Readback(path, facts, tuple(problems))


def svg_readback(path: Path, expected: Shape) -> Readback:
    """ExportSVG moves the drawing into its view box, so the size is compared, not the place."""
    found = _outline_facts(path, "SVG", Wire.combine(import_svg(str(path)).edges()), expected, extents=False)
    problems = found.problems + (("SVG holds <text>",) if "<text" in path.read_text(encoding="utf-8") else ())
    return Readback(path, found.facts, problems)


def pdf_readback(path: Path, svg: Path) -> Readback:
    """The page is the SVG's size at 1:1 and the file carries no font."""
    info = subprocess.run(["pdfinfo", str(path)], check=True, capture_output=True, text=True).stdout
    page = next(line.split(":", 1)[1].split() for line in info.splitlines() if line.startswith("Page size:"))
    size = (float(page[0]), float(page[2]))
    want = tuple(value * PT_PER_MM for value in _svg_size_mm(svg))
    fonts = subprocess.run(["pdffonts", str(path)], check=True, capture_output=True, text=True).stdout
    font_count = len(fonts.splitlines()[2:])  # two header lines
    problems = []
    if any(abs(got - expected) > PAGE_LIMIT for got, expected in zip(size, want, strict=True)):
        problems.append(f"page {size[0]:.3f} x {size[1]:.3f} pt, the SVG is {want[0]:.3f} x {want[1]:.3f}")
    if font_count:
        problems.append(f"{font_count} fonts, expected none")
    print(f"  {path.parent.name}/{path.name}: PDF, page {size[0]:.3f} x {size[1]:.3f} pt, {font_count} fonts")
    return Readback(path, {"format": "PDF", "page_pt": [round(value, 3) for value in size], "fonts": font_count},
                   tuple(problems))


def _svg_size_mm(svg: Path) -> tuple[float, float]:
    head = svg.read_text(encoding="utf-8").split("<svg", 1)[1].split(">", 1)[0]
    return tuple(float(head.split(f'{key}="', 1)[1].split("mm", 1)[0]) for key in ("width", "height"))


def _outline_facts(path: Path, kind: str, wires: list[Wire], expected: Shape, extents: bool) -> Readback:
    """Every wire closed; the enclosed area (largest wire less the others) and the size within the
    limits; with `extents`, the place too."""
    if not wires:
        return Readback(path, {"format": kind, "outlines": 0}, ("no outline read back",))
    problems = []
    open_wires = sum(1 for wire in wires if not wire.is_closed)
    if open_wires:
        problems.append(f"{open_wires} open outlines")
    want_wires = len(expected.wires())  # the outer one and each hole
    if len(wires) != want_wires:
        problems.append(f"{len(wires)} outlines, expected {want_wires}")
    area = 0.0 if open_wires else _enclosed_area(wires)
    error = abs(area - expected.area) / expected.area
    if not error < AREA_SHARE:
        problems.append(f"area off by {error:.1e}, limit {AREA_SHARE:.0e}")
    box, want = _box(wires), expected.bounding_box()
    pairs = [(box.size.X, want.size.X), (box.size.Y, want.size.Y)]
    if extents:
        pairs += [(box.min.X, want.min.X), (box.min.Y, want.min.Y)]
    off = max(abs(got - expected) for got, expected in pairs)
    if not off <= SIZE_LIMIT:
        problems.append(f"extents off by {off:.3f} mm, limit {SIZE_LIMIT}")
    print(f"  {path.parent.name}/{path.name}: {kind}, {len(wires)} outlines, area off by {error:.1e}, "
          f"extents off by {off:.3f} mm")
    facts = {"format": kind, "outlines": len(wires), "area_mm2": round(area, 3), "area_error": f"{error:.1e}",
             "extents_off_mm": round(off, 3)}
    return Readback(path, facts, tuple(problems))


def _enclosed_area(wires: list[Wire]) -> float:
    areas = sorted((Face(wire).area for wire in wires), reverse=True)
    return areas[0] - sum(areas[1:])


def _box(wires: list[Wire]):
    box = wires[0].bounding_box()
    for wire in wires[1:]:
        box = box.add(wire.bounding_box())
    return box


if __name__ == "__main__":
    raise SystemExit(export_all())
