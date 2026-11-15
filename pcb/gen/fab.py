# SPDX-License-Identifier: CERN-OHL-S-2.0
"""BOM and CPL rows. Y is the board.toml frame, +y toward the USB edge.
Bottom rotation is KiCad's rotation. It is not verified against PCBWay's preview.
"""

from circuit import Board, Part

BOM_HEADER = ["Comment", "Designator", "Footprint", "LCSC Part #", "Manufacturer", "Manufacturer Part"]
CPL_HEADER = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]
HAND_HEADER = BOM_HEADER + ["Note"]


def bom_rows(board: Board) -> list[dict[str, str]]:
    return [_bom(part) for part in board.parts if not part.hand]


def hand_rows(board: Board) -> list[dict[str, str]]:
    rows = []
    for part in board.parts:
        if not part.hand:
            continue
        row = _bom(part)
        row["Note"] = part.note
        rows.append(row)
    return rows


def cpl_rows(board: Board) -> list[dict[str, str]]:
    rows = []
    for part in board.parts:
        if part.hand:
            continue
        rows.append(
            {
                "Designator": part.designator,
                "Mid X": f"{part.x:.2f}",
                "Mid Y": f"{part.y:.2f}",
                "Layer": part.layer,
                "Rotation": f"{part.rotation:.1f}",
            }
        )
    return rows


def _bom(part: Part) -> dict[str, str]:
    return {
        "Comment": part.comment,
        "Designator": part.designator,
        "Footprint": part.footprint,
        "LCSC Part #": part.lcsc,
        "Manufacturer": part.manufacturer,
        "Manufacturer Part": part.mpn,
    }
