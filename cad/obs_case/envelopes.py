# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bought-part envelopes (task 6.6; spec criterion 11): one STEP AP214 per bought part, for the
owner's CAD and for the board STEP where KiCad has no model (MX, EC11). Each envelope is stacked
boxes and cylinders fused into one solid that holds the part at nominal size; it is no datasheet
model. Frame of board.toml [envelopes]: x, y centred on the body, z = 0 on the seating face, +z
away from it. Every size is read from board.toml; the fpc heights and plan sizes stay MEASURE there.
Each STEP is read back: one solid, valid, volume within export.BREP_SHARE, fixed header."""

from __future__ import annotations

from pathlib import Path

from build123d import Box, Cylinder, Pos, Solid, export_step

from obs_case.export import AP214, EXPORTS, TIMESTAMP, Readback, fresh, publish, step_readback
from obs_case.spec import BOARD_TOML, LAYOUT

STAGE = BOARD_TOML.parent / ".build" / "cad" / "exports"
FOLDER = "envelopes"


def _box(width: float, depth: float, z_low: float, z_high: float) -> Solid:
    return Pos(0, 0, (z_low + z_high) / 2) * Box(width, depth, z_high - z_low)


def _round(diameter: float, z_low: float, z_high: float) -> Solid:
    return Pos(0, 0, (z_low + z_high) / 2) * Cylinder(diameter / 2, z_high - z_low)


def _rect(rect: list[float], height: float) -> Solid:
    """A board.toml [x, y, width, depth] rectangle as a box `height` tall."""
    return _box(rect[2], rect[3], 0.0, height)


def _fused(*pieces: Solid) -> Solid:
    whole = pieces[0]
    for piece in pieces[1:]:
        whole = whole + piece
    return whole


def parts() -> dict[str, Solid]:
    """{file stem: envelope} of every bought part board.toml sizes."""
    keys, buttons, knobs, stack, table = LAYOUT.keys, LAYOUT.buttons, LAYOUT.knobs, LAYOUT.stack, LAYOUT.envelopes
    big, narrow, fpc = LAYOUT.big_display, LAYOUT.narrow_display, LAYOUT.fpc
    bushing, bushing_top = table.ec11_bushing
    shaft, shaft_end = table.ec11_shaft
    cap, cap_height = table.dsa_cap
    return {
        "mx-switch": _fused(_box(keys.plate_hole, keys.plate_hole, stack.pcb_top, stack.mx_plate_top),
                            _box(keys.housing, keys.housing, stack.mx_plate_top, table.mx_stem_top)),
        "dsa-keycap": _box(cap, cap, 0.0, cap_height),
        "omron-b3f": _fused(_box(buttons.body, buttons.body, stack.pcb_top, stack.b3f_body_top),
                            _round(table.b3f_plunger, stack.b3f_body_top, table.b3f_plunger_top)),
        "ec11": _fused(_box(*knobs.encoder_body, stack.pcb_top, stack.ec11_body_top),
                       _round(bushing, stack.ec11_body_top, bushing_top), _round(shaft, bushing_top, shaft_end)),
        "big-display": _rect(big.outline, big.thickness),
        "narrow-display": _rect(narrow.outline, narrow.thickness),
        "usb4216": _box(*LAYOUT.usb.body, 0.0, LAYOUT.usb.height),
        "esp32-s3-wroom-1": _rect(LAYOUT.mcu.outline, LAYOUT.mcu.height),
        "fpc-big": _box(*fpc.big.body, 0.0, table.fpc_height),
        "fpc-narrow": _box(*fpc.narrow.body, 0.0, table.fpc_height),
    }


def label(name: str) -> str:
    """The STEP product name: OBS-ENV-<stem>."""
    return f"OBS-ENV-{name.upper()}"


def part_files(folder: Path) -> list[Readback]:
    """One STEP AP214 per envelope in `folder`, each read back."""
    readbacks = []
    for name, solid in parts().items():
        path = folder / f"{name}.step"
        solid.label = label(name)
        export_step(solid, str(path), timestamp=TIMESTAMP)
        readbacks.append(step_readback(path, solid, label(name), AP214))
    return readbacks


def export_all(stage: Path = STAGE, target: Path = EXPORTS) -> int:
    """Write and read back every envelope under `stage`, then replace `target`/envelopes and the
    manifest's "envelopes" section. Returns 1 on any fault."""
    return publish(part_files(fresh(stage / FOLDER)), stage, target, (FOLDER,), FOLDER)


if __name__ == "__main__":
    raise SystemExit(export_all())
