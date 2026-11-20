# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Case parameters, read from board.toml at run time. Pattern from
macropad-greycode/cad/greycode_case/spec.py: the layout lives in board.toml only, and no layout
number is written under cad/ (test_spec.py scans for one).

Frame and units are board.toml's: PCB frame, origin at the PCB front-left corner, +x right,
+y toward the back edge, z = 0 on the PCB top face, millimetres. MEASURE tags stay in board.toml.
"""

import tomllib
from pathlib import Path
from types import SimpleNamespace

BOARD_TOML = Path(__file__).resolve().parents[2] / "board.toml"
FIRST_LAYOUT_TABLE = "body"  # board.toml: "Layout rev 3 from here down."
TOLERANCE = 1e-9  # float noise of the two-decimal sums


def _namespace(table):
    """A TOML table with its nested tables as attributes; arrays stay lists."""
    return SimpleNamespace(
        **{key: _namespace(entry) if isinstance(entry, dict) else entry for key, entry in table.items()}
    )


def _outline_grow(body):
    return body.pcb_clearance + body.wall


def _outline_problems(layout):
    """The case outline must be the PCB grown by clearance plus wall, corners concentric."""
    body, pcb = layout.body, layout.pcb
    grow = _outline_grow(body)
    want = [-grow, -grow, pcb.width + 2 * grow, pcb.depth + 2 * grow]
    found = []
    if any(abs(got - expected) > TOLERANCE for got, expected in zip(body.outline, want, strict=True)):
        found.append(f"body.outline {body.outline}, PCB grown by clearance + wall is {want}")
    corner = pcb.corner_radius + grow
    if abs(body.corner_radius - corner) > TOLERANCE:
        found.append(f"body.corner_radius {body.corner_radius}, PCB corner + clearance + wall is {corner:g}")
    return found


def load(path):
    """The layout tables of the board.toml at `path`. Raises ValueError if the case outline does
    not grow from the PCB."""
    board = tomllib.loads(path.read_text(encoding="utf-8"))
    names = list(board)
    layout = _namespace({name: board[name] for name in names[names.index(FIRST_LAYOUT_TABLE) :]})
    problems = _outline_problems(layout)
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return layout


LAYOUT = load(BOARD_TOML)
OUTLINE_GROW = _outline_grow(LAYOUT.body)  # case outline = PCB outline grown by this
