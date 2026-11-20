# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Interference of the case with the board STEP (task 6.8; spec 13 `cad`, spec 14 risk rows).

Every case part of each variant (shell, plate, insert, both carriers and foam frames, the three knob
dials and the four B3F caps) is checked against every solid of the task 5.11 board STEP, the module
among them, and against the other case parts. A shared volume above checks.TOLERANCE is an
interference; a touch (line to line) is none. Then the gaps the spec leaves MEASURE are reported
from the STEP: the module stack to the plate, the USB shell past the PCB edge and behind the thinned
wall, and the insert fit.

Frame: the STEP keeps board.toml x and y. Its z is moved so that the top face cad envelopes (z = 0
on their seat) sit on z = 0, as board.toml. The STEP is moved as one rigid body: where KiCad puts the
bottom face elsewhere than board.toml's PCB thickness, the bottom parts move with it, and the report
says by how much.

One allowance: the EC11 envelope's shaft is round, the real shaft has a flat. The dial's D bore
bears on that flat, so its overlap with the round shaft beyond the flat is allowed and reported,
never counted. The DSA keycaps are not checked: their seat on the stem is MEASURE ([keys] keycap).

Provisional until task 5.12: while the board carries PLACEHOLDER_* footprints, the STEP lives in
pcb/.build/step. `just pcb step` writes it; this check never runs KiCad."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from build123d import Compound, Cylinder, Pos, Shape, import_step

from obs_case import b3f_cap, carriers, insert, knob, variants
from obs_case.carriers import block
from obs_case.checks import TOLERANCE
from obs_case.spec import BOARD_TOML, LAYOUT

ROOT = BOARD_TOML.parent
STEP_NAME = "macropad-obs.step"
STEP_DIRS = (ROOT / "pcb" / "step", ROOT / "pcb" / ".build" / "step")  # the 5.12 STEP first
BOARD_FILE = ROOT / "pcb" / "kicad" / "macropad-obs.kicad_pcb"
TOP_SEAT, BOTTOM_SEAT = "mx-switch", "usb4216"  # cad envelopes, z = 0 on their seat (pcb/gen/step.py)
MODULE = "ESP32-S3-WROOM-1"


@dataclass(frozen=True)
class BoardSolid:
    label: str  # the STEP product name: a KiCad model or a cad envelope stem
    solid: Shape


@dataclass(frozen=True)
class Board:
    path: Path
    placeholders: list[str]
    solids: list[BoardSolid]
    faces_apart: float  # z from the bottom face seat to the top face seat in the STEP


@dataclass(frozen=True)
class Hit:
    part: str
    other: str
    volume: float  # mm3 shared outside the part's allowance: an interference above TOLERANCE
    allowed: float  # mm3 shared inside it


def find_step(dirs=STEP_DIRS) -> Path:
    for folder in dirs:
        if (folder / STEP_NAME).is_file():
            return folder / STEP_NAME
    raise FileNotFoundError(f"no {STEP_NAME} in {', '.join(str(folder) for folder in dirs)}: run `just pcb step`")


def manifest_problems(step_path: Path, board_file: Path = BOARD_FILE) -> list[str]:
    """The STEP must be the file its manifest names, written from the board as it is now."""
    facts = json.loads((step_path.parent / "manifest.json").read_text(encoding="utf-8"))
    found = []
    if _sha256(step_path) != facts["sha256"]:
        found.append(f"{step_path.name}: sha256 is not the one its manifest records")
    if _sha256(board_file) != facts["board_sha256"]:
        found.append(f"{step_path.name} was written from an older {board_file.name}: run `just pcb step`")
    return found


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_board(step_path: Path) -> Board:
    """Every placed solid of the STEP, moved into the board.toml z frame."""
    placed = [(child.label, solid) for child in import_step(str(step_path)).children for solid in child.solids()]
    top = min(solid.bounding_box().min.Z for label, solid in placed if label == TOP_SEAT)
    bottom = max(solid.bounding_box().max.Z for label, solid in placed if label == BOTTOM_SEAT)
    facts = json.loads((step_path.parent / "manifest.json").read_text(encoding="utf-8"))
    return Board(step_path, facts["provisional_placeholders"],
                 [BoardSolid(label, Pos(0, 0, -top) * solid) for label, solid in placed], top - bottom)


def case_parts(variant: str) -> dict[str, Shape]:
    """Every case part of `variant`, placed in the board.toml frame."""
    parts = dict(variants.parts(variant))
    for name in carriers.NAMES:
        parts[f"{name} carrier"] = carriers.carrier(name)
        parts[f"{name} foam frame"] = carriers.foam_frame(name)
    dial = knob.dial()
    parts |= {f"dial {LAYOUT.knobs.x:g},{y:g}": Pos(LAYOUT.knobs.x, y, 0) * dial for y in LAYOUT.knobs.y}
    cap = b3f_cap.cap(variant)
    parts |= {f"b3f cap {x:g},{LAYOUT.buttons.y:g}": Pos(x, LAYOUT.buttons.y, 0) * cap for x in LAYOUT.buttons.x}
    return parts


def allowances() -> dict[str, Shape]:
    """{dial name: the round shaft past its flat}, named as case_parts names the dials."""
    return {f"dial {LAYOUT.knobs.x:g},{y:g}": shaft_flat_allowance(LAYOUT.knobs.x, y) for y in LAYOUT.knobs.y}


def shaft_flat_allowance(x: float, y: float) -> Shape:
    """The part of the envelope's round shaft that the real shaft's flat leaves out, flat on +y as
    the dial's D faces (knob.py), from the start of the flat to the shaft end."""
    shaft, shaft_end = LAYOUT.envelopes.ec11_shaft
    flat_across, flat_length = LAYOUT.knob_dial.shaft_flat
    radius, flat_start = shaft / 2, shaft_end - flat_length
    round_shaft = Pos(x, y, shaft_end - flat_length / 2) * Cylinder(radius, flat_length)
    past_flat = block([x - radius, y + flat_across - radius, shaft, shaft - flat_across], flat_start, shaft_end)
    return round_shaft & past_flat


def interferences(parts: dict[str, Shape], board: list[BoardSolid], allowed: dict[str, Shape]) -> list[Hit]:
    """Each case part against each board solid and each later case part: every pair that shares
    volume, inside or outside the part's allowance."""
    names = list(parts)
    pairs = [(name, solid.label, parts[name], solid.solid) for name in names for solid in board]
    pairs += [(first, second, parts[first], parts[second])
              for index, first in enumerate(names) for second in names[index + 1 :]]
    hits = [_hit(name, other, part, solid, allowed.get(name)) for name, other, part, solid in pairs
            if _boxes_meet(part, solid)]
    return [hit for hit in hits if hit.volume > TOLERANCE or hit.allowed > TOLERANCE]


def _boxes_meet(first: Shape, second: Shape) -> bool:
    one, two = first.bounding_box(), second.bounding_box()
    return all(one_low < two_high and two_low < one_high for one_low, one_high, two_low, two_high
               in zip(one.min, one.max, two.min, two.max, strict=True))


def _hit(name: str, other: str, part: Shape, solid: Shape, allowance: Shape | None) -> Hit:
    shared = part & solid
    total = _volume(shared)
    allowed = _volume(shared & allowance) if allowance is not None and total > TOLERANCE else 0.0
    return Hit(name, other, total - allowed, allowed)


def _volume(shape: Shape | None) -> float:
    return sum(piece.volume for piece in shape.solids()) if shape else 0.0


def gaps(parts: dict[str, Shape], board: Board) -> list[str]:
    """The MEASURE gaps of spec 14 read from the STEP, each beside its board.toml design value."""
    stack, usb, pcb = LAYOUT.stack, LAYOUT.usb, LAYOUT.pcb
    module = Compound([solid.solid for solid in board.solids if solid.label == MODULE])
    jack = next(solid.solid for solid in board.solids if solid.label == BOTTOM_SEAT)
    jack_face = jack.bounding_box().max.Y
    design_face = pcb.depth + usb.mouth_overhang
    return [
        _gap("module stack to the plate", parts["plate"].distance_to(module),
             stack.pcb_bottom - LAYOUT.mcu.height - stack.bottom_plate_inside, "MEASURE"),
        _gap("USB shell past the PCB edge", jack_face - pcb.depth, usb.mouth_overhang, "MEASURE"),
        _gap("USB shell face behind the thinned wall face", insert.thinned_face_y() - jack_face,
             insert.thinned_face_y() - design_face, "design"),
        _gap("USB shell to the shell opening", parts["shell"].distance_to(jack), None, "overmold MEASURE"),
        _gap("insert to the shell", parts["shell"].distance_to(parts["insert"]), 0.0, "line to line, fit MEASURE"),
    ]


def _gap(name: str, got: float, design: float | None, tag: str) -> str:
    want = "no design value" if design is None else f"board.toml {design:.2f}"
    return f"gap {name}: {got:.2f} ({want}; {tag})"


def run() -> int:
    """Print every interference, allowance and gap; 1 on any interference or a stale STEP."""
    step_path = find_step()
    found = manifest_problems(step_path)
    board = load_board(step_path)
    state = f"provisional until 5.12 ({', '.join(board.placeholders)})" if board.placeholders else "final"
    print(f"fit: {step_path.relative_to(ROOT)}, {len(board.solids)} placed solids, {state}")
    print(f"fit: STEP faces {board.faces_apart:.3f} apart, board.toml PCB {LAYOUT.pcb.thickness:g}: bottom parts sit"
          f" {board.faces_apart - LAYOUT.pcb.thickness:.3f} lower than board.toml draws them")
    for variant in variants.VARIANTS:
        found += _variant_report(variant, board)
    for problem in found:
        print(problem)
    print(f"fit: {len(found)} problems; DSA keycaps not checked (seat MEASURE)")
    return 1 if found else 0


def _variant_report(variant: str, board: Board) -> list[str]:
    parts = case_parts(variant)
    hits = interferences(parts, board.solids, allowances())
    found = [f"{variant}: {hit.part} and {hit.other} share {hit.volume:.4f} mm3" for hit in hits
             if hit.volume > TOLERANCE]
    for hit in hits:
        if hit.allowed > TOLERANCE:
            print(f"fit {variant}: {hit.part} D bore on the round {hit.other} shaft: {hit.allowed:.4f} mm3 inside"
                  f" the shaft flat, allowed")
    print(f"fit {variant}: {len(parts)} case parts x {len(board.solids)} board solids and each other,"
          f" {len(found)} interferences")
    for line in gaps(parts, board):
        print(f"fit {variant}: {line}")
    return found


if __name__ == "__main__":
    raise SystemExit(run())
