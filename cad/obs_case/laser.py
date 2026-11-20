# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The deck engrave sheet (task 6.7; spec 13 `cad` laser; report 17 direction A, style A).

Only marks that never change with the mapping (report 17 item 7): the knob index digits of
[knobs] index_marks, a tick scale round each knob, a dot in front of each button under its
[ui_mirror] legend cell, and the wordmark in the logo's place (open question 5). Layer MARK is
filled by a fibre laser after anodise. Layer REF is the shell cut just under the top chamfer, the
outline and the through openings, to register on; it is never marked. Seen from above, 1:1, mm,
in the PCB frame of board.toml. Sizes come from [laser]; nothing here has been engraved.

Ported from macropad/cad/macropad_case/drawings.py (`write_underside_marks`: ExportDXF in mm with
layers MARK and REF). That sheet was the underside, seen from below and mirrored back; this one is
the top face, so nothing is mirrored.

Checks (`problems`): each mark lies on the flat deck top; no stroke or neck under MIN_STROKE (each
contour, eroded by half of it on a PIXEL raster, stays one piece); text cap height at least
MIN_CAP; each dot on its button's centre line. Read-back: the DXF by ezdxf audit, units, layers,
each layer within SIZE_LIMIT of the model both ways and REF's extents against [body] outline;
the SVG by size; the PDF by page and fonts (export2d)."""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import ezdxf
import ezdxf.path
import numpy as np
from build123d import (Align, Circle, Compound, ExportSVG, Plane, Pos, Rectangle, Rot, Shape, Sketch, Text, Unit,
                       import_svg, section)
from matplotlib.path import Path as Polygon
from scipy import ndimage
from scipy.spatial import cKDTree

from obs_case import deck, export2d
from obs_case.export import EXPORTS, Readback, fresh, publish
from obs_case.export2d import INSUNITS_MM, MARGIN, REPEATABLE, SIZE_LIMIT, STAGE
from obs_case.spec import LAYOUT

FOLDER = "laser"
NAME = "deck"
MARK, REF = "MARK", "REF"
# The marks need a font file, never a family name (report 11 section 7). The bold: the book weight
# joins its bowls with hairlines under MIN_STROKE at a 2.5 cap height (test_laser.py).
MARK_FONTS = (Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
              Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
MIN_STROKE = 0.2  # mm, spec 13 `cad` laser
MIN_CAP = 2.0  # mm text cap height, spec 13 `cad` laser
DOT_ON_BUTTON = 0.05  # mm a legend cell centre may sit off its button's centre line
PIXEL = 0.005  # mm raster step of the stroke check: a stroke is measured to one pixel
SAMPLE = 0.05  # mm between points taken along a model edge
DENSE = 0.01  # mm between points compared in the read-back
BELOW_CHAMFER = 0.01  # mm under the top chamfer foot where REF cuts the shell
AREA_FLOOR = 1e-6  # mm2 of a mark off the deck top that still counts as on it
ON_FACE = 1e-6  # mm a face centre may sit off deck_top and still be the deck top


def marks() -> dict[str, Sketch]:
    """Every mark by name, flat at z 0, as seen from above."""
    index = LAYOUT.knobs.index_marks
    found = {f"index {text}": text_mark(text, index.height, at, (Align.CENTER, Align.CENTER))
             for text, at in zip(index.text, index.at, strict=True)}
    found |= {f"ticks E{number}": tick_scale(y) for number, y in enumerate(LAYOUT.knobs.y, start=1)}
    found |= {f"dot B{number}": Pos(x, LAYOUT.laser.dot.y) * Circle(LAYOUT.laser.dot.diameter / 2)
              for number, x in enumerate(legend_x(), start=1)}
    wordmark = LAYOUT.laser.wordmark
    found["wordmark"] = text_mark(wordmark.text, wordmark.cap_height, wordmark.at, (Align.MIN, Align.MIN))
    return found


def mark_font() -> Path:
    font = next((path for path in MARK_FONTS if path.is_file()), None)
    if font is None:
        raise FileNotFoundError(f"no engrave font: none of {', '.join(map(str, MARK_FONTS))}")
    return font


def cap_share(font: Path) -> float:
    """Cap height of `font` per unit font size: the height of its H."""
    return Text("H", font_size=1, font_path=str(font)).bounding_box().size.Y


def text_mark(text: str, cap_height: float, at, align) -> Sketch:
    """`text` in the mark font with cap height `cap_height`, aligned at `at`."""
    font = mark_font()
    return Pos(*at) * Text(text, font_size=cap_height / cap_share(font), font_path=str(font), align=align)


def tick_scale(y: float) -> Sketch:
    """tick_count ticks over tick_sweep degrees round the knob at y, centred on the top; the two end
    ticks long."""
    laser, knobs = LAYOUT.laser, LAYOUT.knobs
    inner = knobs.diameter / 2 + laser.tick_gap
    short, long = laser.tick_length
    step = laser.tick_sweep / (laser.tick_count - 1)
    ticks = []
    for number in range(laser.tick_count):
        length = long if number in (0, laser.tick_count - 1) else short
        clockwise = number * step - laser.tick_sweep / 2  # from the top
        ticks.append(Rot(0, 0, -clockwise) * Pos(0, inner + length / 2) * Rectangle(laser.tick_width, length))
    return Pos(knobs.x, y) * Sketch(ticks)


def legend_x() -> list[float]:
    """Board x of each [ui_mirror] legend cell centre on the big display."""
    mirror, laser = LAYOUT.ui_mirror, LAYOUT.laser
    x, _, width, _ = LAYOUT.big_display.active
    return [x + (cell + mirror.legend_cell_w / 2) * width / laser.big_width_px for cell in mirror.legend_cells_x]


def ref_z() -> float:
    """z of the REF cut: just under the top chamfer, where the shell has its full outline."""
    return LAYOUT.stack.deck_top - LAYOUT.body.top_chamfer - BELOW_CHAMFER


def reference(shell: Shape) -> Shape:
    """Layer REF: the shell cut at ref_z, moved to z 0."""
    z = ref_z()
    return Pos(0, 0, -z) * section(shell, section_by=Plane.XY.offset(z))


def problems(found: dict[str, Sketch], shell: Shape) -> list[str]:
    """Every broken shop or layout rule of the marks `found` on `shell`."""
    faults = off_deck(found, shell)
    faults += [f"{name} has a stroke or neck under {MIN_STROKE} mm"
               for name, sketch in found.items() if any(thin(face) for face in sketch.faces())]
    faults += [f"{text} cap height {cap} mm, under {MIN_CAP}" for text, cap in _text_caps().items() if cap < MIN_CAP]
    faults += [f"dot B{number} at x {x:.3f}, button at {button:.3f}"
               for number, (x, button) in enumerate(zip(legend_x(), LAYOUT.buttons.x, strict=True), start=1)
               if abs(x - button) > DOT_ON_BUTTON]
    return faults


def _text_caps() -> dict[str, float]:
    index, wordmark = LAYOUT.knobs.index_marks, LAYOUT.laser.wordmark
    return {**{text: index.height for text in index.text}, wordmark.text: wordmark.cap_height}


def off_deck(found: dict[str, Sketch], shell: Shape) -> list[str]:
    """Names of the marks not wholly on the flat deck top face of `shell`."""
    z = LAYOUT.stack.deck_top
    top = max((face for face in shell.faces() if abs(face.center().Z - z) < ON_FACE), key=lambda face: face.area)
    return [f"{name} is off the flat deck top" for name, sketch in found.items()
            if (Pos(0, 0, z) * sketch - top).area > AREA_FLOOR]


def thin(face) -> bool:
    """True when `face`, eroded by half of MIN_STROKE, is not one piece: a stroke or a neck is
    thinner than MIN_STROKE, to one PIXEL."""
    inside = _raster(face)
    depth = ndimage.distance_transform_edt(inside) * PIXEL  # mm to the nearest pixel outside
    _, pieces = ndimage.label(depth >= MIN_STROKE / 2)
    return pieces != 1


def _raster(face) -> np.ndarray:
    """Pixel centres inside `face` (even-odd over its wires), on a PIXEL grid with a blank border."""
    box, border = face.bounding_box(), 2 * PIXEL
    xs = np.arange(box.min.X - border, box.max.X + border, PIXEL)
    ys = np.arange(box.min.Y - border, box.max.Y + border, PIXEL)
    grid_x, grid_y = np.meshgrid(xs, ys)
    centres = np.column_stack([grid_x.ravel(), grid_y.ravel()])
    inside = np.zeros(len(centres), dtype=bool)
    for wire in [face.outer_wire(), *face.inner_wires()]:
        inside ^= Polygon(_wire_points(wire)).contains_points(centres)
    return inside.reshape(grid_x.shape)


def _wire_points(wire) -> np.ndarray:
    return np.concatenate([_edge_points(edge) for edge in wire.order_edges()])


def _edge_points(edge) -> np.ndarray:
    count = max(2, math.ceil(edge.length / SAMPLE))
    return np.array([(point.X, point.Y) for point in edge.positions([step / count for step in range(count + 1)])])


def sheet_files(found: dict[str, Sketch], ref: Shape, stem: Path) -> list[Readback]:
    """DXF, SVG and PDF of the marks and REF, each read back."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    dxf, svg, pdf = stem.with_suffix(".dxf"), stem.with_suffix(".svg"), stem.with_suffix(".pdf")
    shapes = list(found.values())
    export2d.write_dxf({REF: ref, MARK: shapes}, dxf)
    exporter = ExportSVG(unit=Unit.MM, margin=MARGIN)
    exporter.add_layer(REF)
    exporter.add_layer(MARK, fill_color=(0, 0, 0))
    exporter.add_shape(ref, layer=REF)
    exporter.add_shape(shapes, layer=MARK)
    exporter.write(str(svg))
    subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(pdf), str(svg)], check=True, env=REPEATABLE)
    return [dxf_readback(dxf, found, ref), svg_readback(svg, ref), export2d.pdf_readback(pdf, svg)]


def dxf_readback(path: Path, found: dict[str, Sketch], ref: Shape) -> Readback:
    document = ezdxf.readfile(str(path))
    errors = len(document.audit().errors)
    units = document.header.get("$INSUNITS")
    layers = sorted({entity.dxf.layer for entity in document.modelspace()})
    off = {MARK: _distance(document, MARK, Sketch(list(found.values()))), REF: _distance(document, REF, ref)}
    outline = _outline_off(_layer_points(document, REF))
    faults = [f"layer {layer} is {gap:.3f} mm off the model, limit {SIZE_LIMIT}"
              for layer, gap in off.items() if not gap <= SIZE_LIMIT]
    if not outline <= SIZE_LIMIT:
        faults.append(f"layer {REF} extents {outline:.3f} mm off [body] outline, limit {SIZE_LIMIT}")
    if errors:
        faults.append(f"ezdxf audit found {errors} errors")
    if units != INSUNITS_MM:
        faults.append(f"$INSUNITS {units}, expected {INSUNITS_MM} (mm)")
    if layers != [MARK, REF]:
        faults.append(f"layers {layers}, expected {[MARK, REF]}")
    print(f"  {path.parent.name}/{path.name}: DXF, audit errors {errors}, layers {layers}, MARK off by "
          f"{off[MARK]:.4f} mm, REF off by {off[REF]:.4f} mm, outline off by {outline:.4f} mm")
    facts = {"format": "DXF", "audit_errors": errors, "layers": layers, "version": document.dxfversion,
             "mark_off_mm": round(off[MARK], 4), "ref_off_mm": round(off[REF], 4),
             "outline_off_mm": round(outline, 4), "marks": len(found)}
    return Readback(path, facts, tuple(faults))


def _distance(document, layer: str, expected: Shape) -> float:
    """Largest gap, either way, between the DXF `layer` and the edges of `expected` (Hausdorff)."""
    written = _layer_points(document, layer)
    model = np.concatenate([_dense(_edge_points(edge)) for edge in expected.edges()])
    if not len(written):
        return math.inf
    return max(cKDTree(model).query(written)[0].max(), cKDTree(written).query(model)[0].max())


def _layer_points(document, layer: str) -> np.ndarray:
    entities = document.modelspace().query(f'*[layer=="{layer}"]')
    polylines = [np.array([(vertex.x, vertex.y) for vertex in ezdxf.path.make_path(entity).flattening(DENSE / 10)])
                 for entity in entities]
    return np.concatenate([_dense(points) for points in polylines]) if polylines else np.empty((0, 2))


def _dense(points: np.ndarray) -> np.ndarray:
    """`points` with straight-line points added so no two neighbours are more than DENSE apart."""
    pieces = [points[:1]]
    for start, end in zip(points[:-1], points[1:]):
        count = max(1, math.ceil(np.linalg.norm(end - start) / DENSE))
        pieces.append(start + np.outer(np.arange(1, count + 1) / count, end - start))
    return np.concatenate(pieces)


def _outline_off(points: np.ndarray) -> float:
    """Largest gap between the extents of `points` and the [body] outline box."""
    if not len(points):
        return math.inf
    x, y, width, depth = LAYOUT.body.outline
    want = np.array([x, y, x + width, y + depth])
    return float(np.abs(np.concatenate([points.min(axis=0), points.max(axis=0)]) - want).max())


def svg_readback(path: Path, ref: Shape) -> Readback:
    """ExportSVG moves the drawing into its view box, so the size is compared, not the place."""
    box, want = Compound(import_svg(str(path))).bounding_box(), ref.bounding_box()
    off = max(abs(box.size.X - want.size.X), abs(box.size.Y - want.size.Y))
    faults = [f"size {off:.3f} mm off REF, limit {SIZE_LIMIT}"] if not off <= SIZE_LIMIT else []
    if "<text" in path.read_text(encoding="utf-8"):
        faults.append("SVG holds <text>")
    print(f"  {path.parent.name}/{path.name}: SVG, size off by {off:.4f} mm")
    return Readback(path, {"format": "SVG", "size_off_mm": round(off, 4)}, tuple(faults))


def export_all(stage: Path = STAGE, target: Path = EXPORTS) -> int:
    """Check the marks, write the sheet under `stage`/laser, read it back, and only when all pass
    replace `target`/laser and the manifest's "laser" section. Returns 1 on any fault."""
    if shutil.which("rsvg-convert") is None or shutil.which("pdfinfo") is None:
        print("laser: rsvg-convert and pdfinfo write and read the PDF; nothing written")
        return 1
    shell = deck.top_shell()
    found = marks()
    faults = problems(found, shell)
    for fault in faults:
        print(fault)
    print(f"laser: {len(found)} marks, {len(faults)} problems; strokes >= {MIN_STROKE} mm to {PIXEL} mm, "
          f"cap heights >= {MIN_CAP} mm, all on the flat deck top")
    if faults:
        return 1
    readbacks = sheet_files(found, reference(shell), fresh(stage / FOLDER) / NAME)
    return publish(readbacks, stage, target, (FOLDER,), FOLDER)


if __name__ == "__main__":
    raise SystemExit(export_all())
