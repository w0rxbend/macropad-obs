# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The CNC pack (spec 10 `fab`, report 12): for each milled part of the cnc variant, a STEP, an A3
drawing as SVG and PDF, and a DXF, each read back. The drawing carries the tolerances, the D3 style
A finish (bead blast, black anodise) and the engrave layer MARK.

Ported from macropad/cad/macropad_case/drawings.py (`Frame`, `_outline`, `_points_along`,
`_polyline`, `_dimension`, `_title_block`, `_feature_table`, `_sheet_frame`, `_svg`,
`write_underside_marks`). Every size on a sheet is read from the model or from board.toml; the
tolerances below are the drawing's own. Nothing here has been milled, anodised or engraved."""

import shutil
import subprocess
import textwrap
from collections import Counter
from dataclasses import dataclass
from xml.sax.saxutils import escape

import ezdxf
from build123d import ExportDXF, GeomType, Plane, Pos, Unit, export_step, import_step, section

from obs_case import checks, deck, laser, shop, variants
from obs_case.spec import BOARD_TOML, LAYOUT

PACK = BOARD_TOML.parent / ".build" / "cad" / "cnc"
SHEET = (420.0, 297.0)  # A3 landscape, mm
FAR = 500.0
CURVE_STEP = 0.6  # mm between points when a curved edge is drawn as a polyline
FONT = "DejaVu Sans, Arial, sans-serif"
STEP_VOLUME_SHARE = 1e-4  # STEP read-back volume error allowed (task 6.5's figure)
# Tolerances on the critical fits, all after anodise. ISO 2768-m holds everywhere else (report 11).
CUTOUT_PLUS = 0.05  # MX cut-outs, cap holes, knob holes and lens recesses: +0.05 / 0
DEPTH_TOLERANCE = 0.05  # lens recess depth
POSITION_TOLERANCE = 0.05  # screw holes and the insert pocket, from datum A
LEDGE_FLATNESS = 0.05  # each lens ledge carries its lens on tape
FINISH = "#120 glass bead blast, then black anodise MIL-A-8625 Type II, Class 2"
FINISH_NOTES = (
    "MATERIAL AND FINISH (D3, style A)",
    "6061-T6 aluminium.",
    f"{FINISH} (dyed black), 8 to 12 um. Bead blast all over, then anodise.",
    "Shell and plate in one anodise batch: colour varies between batches. Rack marks inside the cavity or on "
    "the plate's inside face only. About half the coat builds on each face: the tolerances hold after anodise.",
    "Break unmarked edges 0.1. No thread on this part: screws wait on open question 3.",
)
TABLE_LINE = 3.6
LABEL_LIFT = 1.3  # sheet mm between a dimension line, or a box edge, and its text
NOTE_LINE = 3.2
NOTE_WIDTH = 72  # characters per line in the right column
TITLE_AT = (250, 10)  # sheet mm
TITLE_SIZE = (162.0, 4.4)  # width, row height
TABLE_AT = (250, 54)
LAST_LINE = SHEET[1] - 8  # no text below this, inside the sheet frame
LEFT_NOTES_AT = (14, 236)


@dataclass(frozen=True)
class Frame:
    """Where a view sits on the sheet: sheet position of the view's centre, in mm, at 1:1."""

    x: float
    y: float

    def place(self, across, up):
        return self.x + across, self.y - up


ABOVE = Frame(76, 128)
BELOW = Frame(190, 128)


@dataclass(frozen=True)
class Sheet:
    name: str  # the key in variants.parts() and the file stem
    title: str
    part_number: str
    features: tuple  # (tag, (x, y) board position, text) rows of the feature table
    tolerances: tuple
    notes: tuple
    section_z: float  # z of the DXF REF section


def write_pack(folder):
    """Write and read back the pack for each milled cnc part. Returns 1 on any fault."""
    folder.mkdir(parents=True, exist_ok=True)
    converter = shutil.which("rsvg-convert")
    reader = shutil.which("pdftotext")
    if converter is None or reader is None:
        print("cnc: rsvg-convert and pdftotext are needed for the PDF and its read-back; pack not written")
        return 1
    parts = variants.parts(variants.CNC)
    marks = list(laser.marks().values())
    faults = 0
    for sheet in sheets():
        part = parts[sheet.name]
        stem = folder / sheet.name
        faults += _write_step(part, stem.with_suffix(".step"))
        sheet_marks = marks if sheet.name == "shell" else None
        svg = drawing(sheet, part, sheet_marks)
        stem.with_suffix(".svg").write_text(svg, encoding="utf-8")
        subprocess.run([converter, "-f", "pdf", "-o", str(stem.with_suffix(".pdf")), str(stem.with_suffix(".svg"))],
                       check=True)
        faults += _check_pdf(stem.with_suffix(".pdf"), reader, _required_text(sheet, sheet_marks))
        _write_dxf(part, sheet.section_z, sheet_marks, stem.with_suffix(".dxf"))
        faults += _check_dxf(stem.with_suffix(".dxf"), sheet_marks is not None)
    print(f"cnc: pack of {len(sheets())} parts in {folder}; {faults} faults")
    return 1 if faults else 0


def sheets():
    stack = LAYOUT.stack
    plate_inside = stack.bottom_plate_inside
    return (
        Sheet("shell", "macropad-obs case: top shell, CNC variant", "OBS-CASE-SHELL-CNC", _shell_features(),
              _shell_tolerances(), _shell_notes(), laser.ref_z()),
        Sheet("plate", "macropad-obs case: bottom plate, CNC variant", "OBS-CASE-PLATE-CNC", _plate_features(),
              _plate_tolerances(), _plate_notes(), plate_inside - LAYOUT.bottom_plate.thickness / 2),
    )


def _mm(value, places=2):
    return f"{value + 0.0:.{places}f}".rstrip("0").rstrip(".")


def _size(rect):
    return f"{rect[2]:.2f} x {rect[3]:.2f}"


def _centre(rect):
    return rect[0] + rect[2] / 2, rect[1] + rect[3] / 2


def _plus():
    return f"+{_mm(CUTOUT_PLUS)}/0"


def _shell_features():
    keys, knobs, buttons = LAYOUT.keys, LAYOUT.knobs, LAYOUT.buttons
    width, depth, corner = deck.button_hole()
    rows = [("K1", (keys.x[0], keys.y[0]),
             f"MX cut-out {keys.plate_hole:.2f} {_plus()} square through the plate, dog-bone corners; "
             f"first of {len(keys.x) * len(keys.y)} on a {_mm(keys.pitch)} grid")]
    rows += [(f"B{index + 1}", (x, buttons.y), f"cap hole {width:.2f} {_plus()} x {depth:.2f} {_plus()}, "
              f"R{_mm(corner)}, through the deck") for index, x in enumerate(buttons.x)]
    rows += [(f"E{index + 1}", (knobs.x, y), f"knob hole ⌀{_mm(knobs.bushing_hole)} {_plus()} through")
             for index, y in enumerate(knobs.y)]
    for index, panel in enumerate(deck.panels()):
        recess = deck.lens_recess(panel)
        rows.append((f"L{index + 1}", _centre(recess),
                     f"lens recess {_size(recess)} {_plus()}, R{_mm(LAYOUT.window.lens_recess_corner_radius)}, "
                     f"{_mm(LAYOUT.window.lens_recess_depth)} ±{_mm(DEPTH_TOLERANCE)} deep; window "
                     f"{_size(panel.lens_opening)}, R{_mm(LAYOUT.window.window_corner_radius)}, through"))
    outline = LAYOUT.antenna.insert.outline
    rows.append(("IP", _centre(outline), f"insert pocket {_size(outline)} through the back wall, "
                 f"±{_mm(POSITION_TOLERANCE)}; insert fit MEASURE"))
    usb = LAYOUT.usb
    rows.append(("UO", (usb.x, LAYOUT.pcb.depth), f"USB opening {_mm(usb.opening[0])} x {_mm(usb.opening[1])} "
                 f"through the back wall from the bottom face; wall thinned to {_mm(usb.back_wall_thinned.to)} "
                 f"over {_mm(usb.back_wall_thinned.area[0])} x {_mm(usb.back_wall_thinned.area[1])} from outside"))
    return tuple(rows)


def _plate_features():
    plate, pcb = LAYOUT.bottom_plate, LAYOUT.pcb
    rows = [(f"S{index + 1}", tuple(at), f"⌀{_mm(pcb.hole_diameter)} through plate and standoff, position "
             f"±{_mm(POSITION_TOLERANCE)}") for index, at in enumerate(pcb.holes)]
    rows += [(f"P{index + 1}", tuple(at), f"pinhole ⌀{_mm(plate.pinholes.diameter)} through")
             for index, at in enumerate(plate.pinholes.at)]
    relief = plate.antenna_relief
    rows.append(("AR", _centre(relief), f"antenna relief {_size(relief)} through, dog-bone corners; the insert "
                 f"tongue fills it, ±{_mm(POSITION_TOLERANCE)}"))
    rows.append(("UN", (LAYOUT.usb.x, relief[1] + relief[3]),
                 f"USB notch {_mm(plate.usb_notch.width)} wide, {_mm(plate.usb_notch.depth)} deep from the "
                 "inside face, out through the back edge"))
    return tuple(rows)


def _relief_note(name):
    radii = sorted({round(radius, 2) for radius, _ in _relief_walls(name)})
    listed = ", ".join(f"R{_mm(radius)}" for radius in radii) or "none"
    return (f"Inside corners: each at least JLCCNC's depth / {shop.SHOP_DEPTH_SHARE} + "
            f"{_mm(shop.SHOP_MIN_RADIUS)}, square ones dog-boned; radii here {listed}, from the STEP file.")


def _thin_wall_note(name):
    """The walls board.toml draws under checks.CNC_MIN_WALL on purpose, so the shop expects them."""
    walls = ", ".join(f"{wall.name} {_mm(wall.thickness)}" for wall in checks.thin_walls(name))
    return f"Walls {_mm(checks.CNC_MIN_WALL)} or more, but these thin walls on purpose: {walls}."


def _relief_walls(name):
    return checks.concave_walls(variants.parts(variants.CNC)[name])


def _shell_tolerances():
    stack, keys = LAYOUT.stack, LAYOUT.keys
    return (
        "TOLERANCES (after anodise)",
        "General: ISO 2768-m.",
        f"MX cut-outs {keys.plate_hole:.2f} {_plus()} square in a {_mm(stack.mx_plate_top - stack.mx_plate_underside)}"
        f" plate; cap holes, knob holes and lens recesses {_plus()} on size.",
        f"Lens recess depth {_mm(LAYOUT.window.lens_recess_depth)} ±{_mm(DEPTH_TOLERANCE)}; flatness "
        f"{_mm(LEDGE_FLATNESS)} on each lens ledge.",
        f"Insert pocket ±{_mm(POSITION_TOLERANCE)} from datum A; the insert fit stays MEASURE.",
    )


def _plate_tolerances():
    return (
        "TOLERANCES (after anodise)",
        "General: ISO 2768-m.",
        f"S1-S{len(LAYOUT.pcb.holes)} positions ±{_mm(POSITION_TOLERANCE)} from datum A.",
        f"Antenna relief and insert footprint ±{_mm(POSITION_TOLERANCE)}; the insert fit stays MEASURE.",
    )


# How each milled part is held in each setup and what it cuts there besides its dog-bones. The
# drawing numbers the setups in variants.SETUPS order and lists each dog-bone in its corner's setup.
SETUP_WORK = {
    "shell": {variants.BELOW: ("underside up", "cavity, display pocket walls, insert pocket, USB opening and the "
                                               "thinned wall round it"),
              variants.ABOVE: ("top up", "key well, MX cut-outs, lens recesses, holes, insert pocket deck rim, "
                                         "chamfers")},
    "plate": {variants.ABOVE: ("inside face up, outer face down on a fixture through the six screw holes",
                               "posts, USB notch, antenna relief and insert footprint")},
}


def _setup_notes(name):
    """One 'Setup N, how held: what it cuts; its dog-bones.' note per setup of part `name`."""
    notes = []
    for number, setup in enumerate(variants.SETUPS[name], start=1):
        held, work = SETUP_WORK[name][setup]
        notes.append(f"Setup {number}, {held}: {work}; {_dog_bones(name, setup)}.")
    return tuple(notes)


def _dog_bones(name, setup):
    """The dog-bones `setup` cuts in part `name`, as counts of each radius, sized for its depth."""
    radii = Counter(round(corner.relief_radius, 2) for corner in variants.relief_corners(name)
                    if corner.setup == setup)
    if not radii:
        return "no dog-bones"
    return "dog-bones " + ", ".join(f"{count} x R{_mm(radius)}" for radius, count in sorted(radii.items()))


def _shell_notes():
    marks = LAYOUT.knobs.index_marks
    return (
        f"3-axis, two setups. {_thin_wall_note('shell')}",
        *_setup_notes("shell"),
        "Style A: the top chamfer is machined after the bead blast (setup 2) so it shows bright, then the part is "
        "anodised. Order as \"chamfer machined after blast\".",
        _relief_note("shell"),
        "No metal in the antenna board cut: the back-wall insert (plastic, not in this pack) fills the pocket.",
        "ENGRAVE (layer MARK)",
        f"Fibre laser after anodise, 0.03 to 0.1 deep. Fill each closed contour on layer MARK of shell.dxf; never "
        f"mark layer REF. Marks (orange on the plan), from cad/exports/laser/deck.dxf (task 6.7): knob index "
        f"digits {' '.join(marks.text)}, {_mm(marks.height)} cap height, a tick scale round each knob, a dot in "
        "front of each button and the wordmark (open question 5: no logo yet).",
    )


def _plate_notes():
    return (
        f"3-axis, one setup. {_thin_wall_note('plate')}",
        *_setup_notes("plate"),
        _relief_note("plate"),
        "ENGRAVE: none on this part.",
    )


def drawing(sheet, part, marks):
    """One A3 sheet as SVG text: plans from above and below, overall sizes, the feature table, the
    title block, tolerances, finish and, where there is one, the engrave layer."""
    box = part.bounding_box()
    centre = ((box.min.X + box.max.X) / 2, (box.min.Y + box.max.Y) / 2)
    body = [
        _sheet_frame(),
        _outline(part, (*centre, FAR), centre, ABOVE),
        _outline(part, (*centre, -FAR), centre, BELOW),
        *_overall(box, centre),
        _feature_table(sheet.features),
        _title_block(sheet),
        _note_block((*sheet.tolerances, *FINISH_NOTES), TABLE_AT[0], _table_bottom(sheet.features) + TABLE_LINE,
                    NOTE_WIDTH),
        _left_notes(sheet.notes),
        *_view_labels(box, centre),
    ]
    if marks:
        body.append(_mark_layer(marks, centre))
    return _svg(body)


def _outline(part, eye, centre, frame):
    """Visible edges of `part` seen from `eye`, looking at `centre` on z 0."""
    visible, _hidden = part.project_to_viewport(eye, (0, 1, 0), look_at=(*centre, 0))
    paths = [_polyline([frame.place(x, y) for x, y in _points_along(edge)]) for edge in visible]
    return f'<path class="visible" d="{" ".join(paths)}"/>'


def _points_along(edge):
    steps = 1 if edge.geom_type == GeomType.LINE else max(4, int(edge.length / CURVE_STEP))
    return [(point.X, point.Y) for point in (edge.position_at(step / steps) for step in range(steps + 1))]


def _polyline(points):
    return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _plan(board_x, board_y, centre):
    """Board position as (across, up) of the plan from above."""
    return board_x - centre[0], board_y - centre[1]


def _dimension(frame, start, end, offset, text):
    """A horizontal or vertical dimension between two view points, `offset` sheet mm off them."""
    (x1, y1), (x2, y2) = frame.place(*start), frame.place(*end)
    if abs(y1 - y2) < abs(x1 - x2):
        line_y = (min(y1, y2) if offset < 0 else max(y1, y2)) + offset
        witness = f"M{x1:.2f},{y1:.2f} V{line_y:.2f} M{x2:.2f},{y2:.2f} V{line_y:.2f}"
        line = f"M{x1:.2f},{line_y:.2f} H{x2:.2f}"
        label = f'<text x="{(x1 + x2) / 2:.2f}" y="{line_y - LABEL_LIFT:.2f}" text-anchor="middle">{escape(text)}</text>'
    else:
        line_x = (min(x1, x2) if offset < 0 else max(x1, x2)) + offset
        middle = (y1 + y2) / 2
        witness = f"M{x1:.2f},{y1:.2f} H{line_x:.2f} M{x2:.2f},{y2:.2f} H{line_x:.2f}"
        line = f"M{line_x:.2f},{y1:.2f} V{y2:.2f}"
        label = (f'<text x="{line_x - LABEL_LIFT:.2f}" y="{middle:.2f}" text-anchor="middle" '
                 f'transform="rotate(-90 {line_x - LABEL_LIFT:.2f} {middle:.2f})">{escape(text)}</text>')
    return f'<path class="witness" d="{witness}"/><path class="dimension" d="{line}"/>{label}'


def _overall(box, centre):
    front_left = _plan(box.min.X, box.min.Y, centre)
    front_right = _plan(box.max.X, box.min.Y, centre)
    back_left = _plan(box.min.X, box.max.Y, centre)
    return [
        _dimension(ABOVE, front_left, front_right, 8, _mm(box.size.X)),
        _dimension(ABOVE, front_left, back_left, -8, _mm(box.size.Y)),
    ]


def _view_labels(box, centre):
    def title(frame, text):
        x, y = frame.place(*_plan(box.min.X, box.max.Y, centre))
        return f'<text class="title" x="{x:.2f}" y="{y - 5:.2f}">{escape(text)}</text>'

    datum_x, datum_y = ABOVE.place(*_plan(box.min.X, box.min.Y, centre))
    height = f"{_mm(box.size.Z)} high, z {_mm(box.min.Z)} to {_mm(box.max.Z)} from the PCB top face"
    return [
        title(ABOVE, "FROM ABOVE, 1:1"),
        title(BELOW, "FROM BELOW (mirrored left to right), 1:1"),
        f'<circle class="datum" cx="{datum_x:.2f}" cy="{datum_y:.2f}" r="1.6"/>'
        f'<text class="title" x="{datum_x - 6:.2f}" y="{datum_y + 5:.2f}">A</text>',
        f'<text class="note" x="{BELOW.x - 48:.2f}" y="{BELOW.y + box.size.Y / 2 + 9:.2f}">{escape(height)}</text>',
    ]


def _datum(position):
    """Board position measured from datum A, the front-left corner of the body outline box."""
    x, y, _, _ = LAYOUT.body.outline
    return position[0] - x, position[1] - y


def _feature_table(features):
    left, top = TABLE_AT
    lines = [f'<text class="title" x="{left}" y="{top}">Holes and recesses, centres from datum A</text>',
             f'<text class="note" x="{left}" y="{top + TABLE_LINE}">tag</text>'
             f'<text class="note" x="{left + 26}" y="{top + TABLE_LINE}" text-anchor="end">X</text>'
             f'<text class="note" x="{left + 44}" y="{top + TABLE_LINE}" text-anchor="end">Y</text>']
    line, previous = top + 2 * TABLE_LINE, None
    for tag, position, text in features:
        if text != previous:  # one description above each run of equal features
            for part in textwrap.wrap(text, NOTE_WIDTH + 18):
                lines.append(f'<text class="small" x="{left}" y="{line:.1f}">{escape(part)}</text>')
                line += TABLE_LINE
            previous = text
        x, y = _datum(position)
        lines.append(f'<text class="note" x="{left}" y="{line:.1f}">{tag}</text>'
                     f'<text class="note" x="{left + 26}" y="{line:.1f}" text-anchor="end">{_mm(x, 3)}</text>'
                     f'<text class="note" x="{left + 44}" y="{line:.1f}" text-anchor="end">{_mm(y, 3)}</text>')
        line += TABLE_LINE
    _fits_on_sheet(line, "feature table")
    return "".join(lines)


def _table_bottom(features):
    """Sheet y just under the feature table: where the tolerance and finish notes start."""
    descriptions = sum(len(textwrap.wrap(text, NOTE_WIDTH + 18))
                       for index, (_, _, text) in enumerate(features) if index == 0 or features[index - 1][2] != text)
    return TABLE_AT[1] + TABLE_LINE * (2 + len(features) + descriptions)


def _left_notes(notes):
    general = (
        "Dimensions in mm, from the model (board.toml). Datum A: front-left corner of the outline box, seen from "
        "above; X to the right, Y toward the back edge.",
        "The STEP file is the master for all geometry not dimensioned here. Not made or measured yet: values "
        "tagged MEASURE in board.toml are from datasheets.",
        *notes,
    )
    return _note_block(general, *LEFT_NOTES_AT, 2 * NOTE_WIDTH - 10)


def _note_block(notes, left, top, width):
    lines = []
    for note in notes:
        heading = note.split(" (")[0].split(":")[0].isupper()  # "TOLERANCES (after anodise)", "ENGRAVE: none"
        if heading and lines:
            lines.append(("", False))
        lines += [(part, heading) for part in textwrap.wrap(note, width)]
    _fits_on_sheet(top + NOTE_LINE * (len(lines) - 1), "notes")
    return "".join(
        f'<text class="{"title" if heading else "small"}" x="{left}" y="{top + NOTE_LINE * index:.1f}">'
        f"{escape(part)}</text>" for index, (part, heading) in enumerate(lines))


def _fits_on_sheet(line, what):
    if line > LAST_LINE:
        raise ValueError(f"{what} run off the sheet: last line at y {line:.1f}, limit {LAST_LINE}")


def _title_block(sheet):
    left, top = TITLE_AT
    width, row = TITLE_SIZE
    rows = [
        ("PART", sheet.title),
        ("PART NO.", sheet.part_number),
        ("QUANTITY", "1 per macropad-obs"),
        ("MATERIAL", "6061-T6 aluminium"),
        ("FINISH", FINISH),
        ("UNITS", "mm; plans from above and from below, as titled"),
        ("TOLERANCE", "ISO 2768-m unless stated; fits as listed"),
        ("STATUS", "Not made or measured yet: check the first part"),
    ]
    lines = [f'<rect class="block" x="{left}" y="{top}" width="{width}" height="{row * len(rows):.1f}"/>']
    for index, (field, value) in enumerate(rows):
        baseline = top + row * (index + 0.75)
        lines.append(f'<text class="small" x="{left + LABEL_LIFT}" y="{baseline:.1f}">{field}</text>'
                     f'<text class="small" x="{left + 20}" y="{baseline:.1f}">{escape(value)}</text>')
        if index:
            lines.append(f'<path class="witness" d="M{left},{top + row * index:.1f} H{left + width}"/>')
    return "".join(lines)


def _mark_layer(marks, centre):
    """The engrave outlines on the plan from above, in their own group: layer MARK."""
    paths = []
    for sketch in marks:
        for face in sketch.faces():
            for loop in [face.outer_wire(), *face.inner_wires()]:
                points = [point for edge in loop.order_edges() for point in _points_along(edge)]
                paths.append(_polyline([ABOVE.place(*_plan(x, y, centre)) for x, y in points]) + " Z")
    return f'<g id="MARK"><path class="engrave" fill-rule="evenodd" d="{" ".join(paths)}"/></g>'


def _sheet_frame():
    width, height = SHEET
    return f'<rect class="sheet" x="5" y="5" width="{width - 10}" height="{height - 10}"/>'


def _svg(body):
    width, height = SHEET
    style = f"""
      text {{ font-family: {FONT}; font-size: 3.2px; fill: #1b1f24; }}
      .title {{ font-size: 3.6px; font-weight: bold; }}
      .note {{ font-size: 3px; }}
      .small {{ font-size: 2.6px; }}
      .datum {{ fill: none; stroke: #b5651d; stroke-width: 0.4; }}
      .block {{ fill: none; stroke: #1b1f24; stroke-width: 0.3; }}
      .sheet {{ fill: #ffffff; stroke: #1b1f24; stroke-width: 0.5; }}
      .visible {{ fill: none; stroke: #1b1f24; stroke-width: 0.25; stroke-linecap: round; stroke-linejoin: round; }}
      .engrave {{ fill: #e07a1f; stroke: #b5651d; stroke-width: 0.05; }}
      .witness {{ fill: none; stroke: #2a6f97; stroke-width: 0.13; }}
      .dimension {{ fill: none; stroke: #2a6f97; stroke-width: 0.2; marker-start: url(#arrow); marker-end: url(#arrow); }}
    """
    definitions = """
      <marker id="arrow" viewBox="0 0 6 4" refX="6" refY="2" markerWidth="6" markerHeight="4" orient="auto-start-reverse">
        <path d="M0,0 L6,2 L0,4 Z" fill="#2a6f97"/>
      </marker>
    """
    lines = "\n".join(body)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" '
            f'viewBox="0 0 {width} {height}">\n<style>{style}</style>\n<defs>{definitions}</defs>\n{lines}\n</svg>\n')


def _required_text(sheet, marks):
    """Words the PDF must hold when read back: tolerances, the finish and the engrave layer."""
    words = ["ISO 2768-m", f"\u00b1{_mm(POSITION_TOLERANCE)}", "bead blast", "black anodise", "Type II",
             sheet.part_number]
    return words + ([f"+{_mm(CUTOUT_PLUS)}/0", "ENGRAVE (layer MARK)"] if marks else ["ENGRAVE: none"])


def _write_step(part, path):
    export_step(part, str(path))
    back = import_step(str(path))
    error = abs(back.volume - part.volume) / part.volume
    count = len(back.solids())
    ok = count == 1 and back.is_valid and error < STEP_VOLUME_SHARE
    print(f"  {path.name}: {count} solids, valid {back.is_valid}, volume off by {error:.1e}")
    return 0 if ok else 1


def _check_pdf(path, reader, words):
    text = " ".join(subprocess.run([reader, str(path), "-"], check=True, capture_output=True, text=True).stdout.split())
    missing = [word for word in words if word not in text]
    print(f"  {path.name}: {len(text)} characters read back" + (f", missing {missing}" if missing else ""))
    return 1 if missing else 0


def _write_dxf(part, z, marks, path):
    """Layer REF: the part cut at `z`, outline and through features, to register on. Layer MARK:
    the engrave outlines, filled by the laser. 1:1, mm, R2013 (ExportDXF)."""
    exporter = ExportDXF(unit=Unit.MM)
    exporter.add_layer("REF")
    exporter.add_shape(Pos(0, 0, -z) * section(part, section_by=Plane.XY.offset(z)), layer="REF")
    if marks:
        exporter.add_layer("MARK")
        exporter.add_shape(marks, layer="MARK")
    exporter.write(str(path))


def _check_dxf(path, wants_marks):
    document = ezdxf.readfile(str(path))
    auditor = document.audit()
    layers = {entity.dxf.layer for entity in document.modelspace()}
    want = {"REF", "MARK"} if wants_marks else {"REF"}
    ok = not auditor.has_errors and want <= layers
    print(f"  {path.name}: audit errors {len(auditor.errors)}, layers {sorted(layers)}")
    return 0 if ok else 1
