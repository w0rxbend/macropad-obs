# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The assembled board as one STEP (task 5.11, spec criterion 11). Runs in kicad/kicad:10.0.7-full (`just pcb step`):
the plain 10.0.7 image has no /usr/share/kicad/3dmodels.

A copy of the routed board gets the cad envelopes (cad/exports/envelopes) where KiCad has no model: the MX switches
on the hot-swap sockets, the EC11 encoders, the USB4216 jack and the two panels. Every other part keeps its KiCad
library model. kicad-cli writes the STEP with the board.toml origin (front-left corner), so x and y are board.toml's.
kicad-cli exits 0 when a model is missing (R09), so the STEP is read back: every part with a model must have its
assembly occurrence, the solid count must be the board's solid plus each distinct model file's solids (a model
placed n times is written once), and only WITHOUT_SOLID parts may lack a model. The manifest beside the STEP
records the count and which part comes from which source. Into pcb/step, or into pcb/.build/step while a
PLACEHOLDER_* footprint is on the board (task 5.12).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import place
from circuit_hmi import BOARD

PCB_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PCB_DIR.parent
BOARD_PATH = PCB_DIR / "kicad" / "macropad-obs.kicad_pcb"
STEP_DIR = PCB_DIR / "step"
PROVISIONAL_STEP_DIR = PCB_DIR / ".build" / "step"
STEP_NAME = "macropad-obs.step"
ENVELOPE_DIR = REPO_ROOT / "cad" / "exports" / "envelopes"
ENVELOPE_SUFFIX = "-envelope"
KICAD_MODEL_DIR = Path("/usr/share/kicad/3dmodels")
_MODEL_VARIABLE = re.compile(r"^\$\{(KICAD\d+_3DMODEL_DIR)\}/")
# Parts with no solid: the holes; BOOT and RESET, whose XKB TS-1187A model KiCad 10 lacks and board.toml
# [envelopes] gives no envelope.
WITHOUT_SOLID = frozenset({*(f"H{n}" for n in range(1, 7)), "SW20", "SW21"})
BOARD_SOLIDS = 1
TOP, BOTTOM = place.TOP, place.BOTTOM


@dataclass(frozen=True)
class EnvelopeSpot:
    """A cad envelope on the board: body centre (x, y) in the board.toml frame, seat z above the top face.
    A bottom envelope seats on the bottom face and hangs down; KiCad flips it there."""
    ref: str
    stem: str
    x: float
    y: float
    side: str = TOP
    z: float = 0.0


def envelope_spots() -> tuple[EnvelopeSpot, ...]:
    keys, knobs, usb, stack = BOARD["keys"], BOARD["knobs"], BOARD["usb"], BOARD["stack"]
    switch_points = [(x, y) for y in keys["y"] for x in keys["x"]]  # SW1-SW9 row by row, as place.py
    switches = [EnvelopeSpot(f"SW{n}", "mx-switch", x, y) for n, (x, y) in enumerate(switch_points, start=1)]
    encoders = [EnvelopeSpot(f"SW{14 + n}", "ec11", knobs["x"], y) for n, y in enumerate(knobs["y"])]
    jack_y = BOARD["pcb"]["depth"] + usb["mouth_overhang"] - usb["body"][1] / 2
    panels = [_panel("PANEL-BIG", "big-display", "big_display", stack["panel_face"]),
              _panel("PANEL-NARROW", "narrow-display", "narrow_display", stack["panel_face"])]
    return (*switches, *encoders, EnvelopeSpot("J1", "usb4216", usb["x"], jack_y, BOTTOM), *panels)


def _panel(ref: str, stem: str, table: str, panel_face: float) -> EnvelopeSpot:
    left, front, width, depth = BOARD[table]["outline"]
    return EnvelopeSpot(ref, stem, left + width / 2, front + depth / 2, z=panel_face - BOARD[table]["thickness"])


def envelope_path(spot: EnvelopeSpot) -> Path:
    return ENVELOPE_DIR / f"{spot.stem}.step"


def resolve_model(name: str) -> Path:
    """A footprint's model path as the 10.0.7-full image finds it: the KiCad model variables name its library."""
    if "${" not in name:
        return Path(name)
    if not _MODEL_VARIABLE.match(name):
        raise ValueError(f"model path {name} names a variable other than KICADn_3DMODEL_DIR")
    return KICAD_MODEL_DIR / _MODEL_VARIABLE.sub("", name)


def solid_count(text: str) -> int:
    """The solids of a STEP file read back: one per MANIFOLD_SOLID_BREP entity."""
    if not (text.startswith("ISO-10303-21;") and text.rstrip().endswith("END-ISO-10303-21;")):
        raise ValueError("not a whole STEP file")
    return len(re.findall(r"=\s*MANIFOLD_SOLID_BREP\s*\(", text))


def placed_references(text: str) -> set[str]:
    """The part references a STEP file places: kicad-cli names each model's assembly occurrence after its
    footprint, and an envelope footprint after the part it stands in for."""
    names = re.findall(r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(\s*'[^']*'\s*,\s*'([^']*)'", text)
    return {name.removesuffix(ENVELOPE_SUFFIX) for name in names}


# --- KiCad side: needs pcbnew ------------------------------------------------------------------------------------

def _add_envelope(board, spot: EnvelopeSpot) -> None:
    import pcbnew
    footprint = pcbnew.FOOTPRINT(board)
    footprint.SetReference(spot.ref + ENVELOPE_SUFFIX)
    x, y = place.kicad_xy(spot.x, spot.y)
    footprint.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    model = pcbnew.FP_3DMODEL()
    model.m_Filename = str(envelope_path(spot))
    model.m_Offset = pcbnew.VECTOR3D(0.0, 0.0, spot.z)
    footprint.Models().push_back(model)
    board.Add(footprint)
    if spot.side == BOTTOM:
        footprint.Flip(footprint.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)


def write_assembly_board(work_dir: Path) -> Path:
    """The routed board with each envelope in place of its part's KiCad model, saved under work_dir."""
    import pcbnew
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    for spot in envelope_spots():
        part = board.FindFootprintByReference(spot.ref)
        if part is not None:
            part.Models().clear()
        _add_envelope(board, spot)
    path = work_dir / BOARD_PATH.name
    pcbnew.SaveBoard(str(path), board)
    return path


def model_sources(board_path: Path) -> dict[str, list[str]]:
    """Part reference -> the model files placed for it, as found in this image; [] for none. An envelope
    footprint counts for the part it stands in for."""
    import pcbnew
    sources: dict[str, list[str]] = {}
    for footprint in pcbnew.LoadBoard(str(board_path)).GetFootprints():
        paths = [resolve_model(model.m_Filename) for model in footprint.Models() if model.m_Show]
        part = footprint.GetReference().removesuffix(ENVELOPE_SUFFIX)
        sources.setdefault(part, []).extend(str(path) for path in paths if path.is_file())
    return sources


def expected_solids(sources: dict[str, list[str]]) -> int:
    """The board's solid plus each distinct model file's solids: the STEP writes a model placed n times once."""
    models = {path for paths in sources.values() for path in paths}
    return BOARD_SOLIDS + sum(solid_count(Path(path).read_text(errors="replace")) for path in models)


def export_step(board_path: Path, step_path: Path) -> None:
    origin = f"0x{BOARD['pcb']['depth']}mm"  # KiCad's point of the board.toml front-left corner
    subprocess.run(["kicad-cli", "pcb", "export", "step", "--force", "--user-origin", origin, "-o", str(step_path),
                    str(board_path)], check=True, stdout=subprocess.DEVNULL)


def _source_kind(paths: list[str]) -> str:
    if not paths:
        return "none"
    return "cad envelope" if all(Path(path).parent == ENVELOPE_DIR for path in paths) else "KiCad model"


def manifest(step_path: Path, solids: int, sources: dict[str, list[str]], placeholders: list[str]) -> dict:
    parts = {ref: {"source": _source_kind(paths), "files": [Path(path).name for path in paths]}
             for ref, paths in sorted(sources.items())}
    return {
        "step": step_path.name,
        "sha256": hashlib.sha256(step_path.read_bytes()).hexdigest(),
        "board_sha256": hashlib.sha256(BOARD_PATH.read_bytes()).hexdigest(),
        "kicad": subprocess.run(["kicad-cli", "version"], check=True, capture_output=True, text=True).stdout.strip(),
        "solids": solids,
        "frame": "board.toml x and y (front-left origin, y to the back edge); KiCad's board body z",
        "provisional_placeholders": placeholders,
        "parts": parts,
    }


def read_back(step_path: Path, sources: dict[str, list[str]]) -> int:
    """The STEP's solid count, once it holds every placed part and every model's solids (kicad-cli exits 0 on a
    missing model, R09)."""
    text = step_path.read_text(errors="replace")
    missing = sorted({ref for ref, paths in sources.items() if paths} - placed_references(text))
    assert not missing, f"{step_path.name} does not place {missing}"
    solids, wanted = solid_count(text), expected_solids(sources)
    assert solids == wanted, f"{step_path.name} reads back {solids} solids, the board and its models make {wanted}"
    return solids


def build() -> None:
    placeholders = sorted(part.ref for part in place.board_parts() if "PLACEHOLDER_" in part.footprint)
    step_dir = PROVISIONAL_STEP_DIR if placeholders else STEP_DIR
    step_dir.mkdir(parents=True, exist_ok=True)
    work_dir = PCB_DIR / ".build" / "step-board"
    work_dir.mkdir(parents=True, exist_ok=True)
    board_path = write_assembly_board(work_dir)
    sources = model_sources(board_path)
    no_solid = sorted(ref for ref, paths in sources.items() if not paths)
    assert set(no_solid) == WITHOUT_SOLID, f"parts without a solid {no_solid}, expected {sorted(WITHOUT_SOLID)}"
    step_path = step_dir / STEP_NAME
    export_step(board_path, step_path)
    solids = read_back(step_path, sources)
    (step_dir / "manifest.json").write_text(json.dumps(manifest(step_path, solids, sources, placeholders), indent=2)
                                            + "\n")
    print(f"step: {step_path.relative_to(PCB_DIR)} reads back {solids} solids, as the board and its models make; "
          f"no solid for {no_solid}")
    if placeholders:
        print(f"step: provisional, PLACEHOLDER_* footprints {placeholders}: pcb/step waits for task 5.12")


if __name__ == "__main__":
    if sys.argv[1:]:
        sys.exit(__doc__)
    build()
