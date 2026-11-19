#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail if the layout rev 3 stack, foam, carriers or holes break a rule of spec section 7,
or if board.toml differs from docs/spec/layout-v2.toml.
Rules: docs/research/gap-5.md, "Text for layout-v2.toml", checks 1 to 4."""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = ROOT / "docs" / "spec" / "layout-v2.toml"
BOARD = ROOT / "board.toml"

PANEL_FACE = 5.6  # spec 7: report 11's 5.5 gives 0 % foam squeeze
HOLE_COUNT = 6  # spec 7: the (88.3, 166) hole went with the antenna board cut
SQUEEZE_MIN = 0.10  # gap-5 check 3: below this the foam has no preload
SQUEEZE_MAX = 0.25  # Rogers: above 25 % speeds stress relaxation (gap-5)
PANELS = {"big": "big_display", "narrow": "narrow_display"}
TOLERANCE = 1e-9  # float noise of the two-decimal sums


def differs(got, want):
    return abs(got - want) > TOLERANCE


def stack_problems(layout):
    stack = layout["stack"]
    face = stack["panel_face"]
    found = []
    if differs(face, PANEL_FACE):
        found.append(f"stack.panel_face: {face}, expected {PANEL_FACE}")
    under_foam = stack["deck_underside"] - layout["foam_frame"]["installed"]
    if differs(face, under_foam):
        found.append(f"stack.panel_face: {face}, deck_underside - foam installed is {under_foam:g}")
    for name, panel in PANELS.items():
        height = layout["display_carrier"][name]["height"]
        want = face - layout[panel]["thickness"]
        if differs(height, want):
            found.append(f"{name} carrier height: {height}, panel_face - panel thickness is {want:g}")
    return found


def squeeze_problems(foam):
    squeeze = 1 - foam["installed"] / foam["thickness"]
    if SQUEEZE_MIN - TOLERANCE <= squeeze <= SQUEEZE_MAX + TOLERANCE:
        return []
    return [f"foam squeeze: {squeeze:.0%}, expected {SQUEEZE_MIN:.0%} to {SQUEEZE_MAX:.0%}"]


def rects_overlap(first, second):
    """True if two [x, y, w, h] rectangles share area. Touching edges do not overlap."""
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def circle_overlaps_rect(centre, diameter, rect):
    x, y, w, h = rect
    dx = centre[0] - min(max(centre[0], x), x + w)
    dy = centre[1] - min(max(centre[1], y), y + h)
    return dx * dx + dy * dy < (diameter / 2) ** 2


def centred(x, y, w, h):
    return [x - w / 2, y - h / 2, w, h]


def top_face_rects(layout):
    """Named [x, y, w, h] of every slot, cut and through-hole part on the PCB top face."""
    keys, buttons, knobs = layout["keys"], layout["buttons"], layout["knobs"]
    rects = [(f"board slot {slot}", slot) for slot in layout["pcb"]["board_slots"]]
    rects.append(("antenna board cut", layout["antenna"]["board_cut"]))
    rects += [
        (f"key ({x}, {y})", centred(x, y, keys["housing"], keys["housing"]))
        for x in keys["x"]
        for y in keys["y"]
    ]
    rects += [
        (f"button x {x}", centred(x, buttons["y"], buttons["body"], buttons["body"]))
        for x in buttons["x"]
    ]
    rects += [(f"encoder y {y}", centred(knobs["x"], y, *knobs["encoder_body"])) for y in knobs["y"]]
    return rects


def top_face_circles(layout):
    """Named (centre, diameter) of every hole keep-out and USB peg hole."""
    pcb, pegs = layout["pcb"], layout["usb"]["peg_holes"]
    circles = [(f"hole keep-out {at}", at, pcb["hole_keepout_diameter"]) for at in pcb["holes"]]
    return circles + [(f"USB peg {at}", at, pegs["diameter"]) for at in pegs["at"]]


def keepout_problems(layout):
    rects, circles = top_face_rects(layout), top_face_circles(layout)
    found = []
    for name in PANELS:
        outer = layout["display_carrier"][name]["outer"]
        hits = [label for label, rect in rects if rects_overlap(rect, outer)]
        hits += [label for label, at, diameter in circles if circle_overlaps_rect(at, diameter, outer)]
        found += [f"{label} lies under the {name} carrier {outer}" for label in hits]
    return found


def hole_problems(pcb):
    count = len(pcb["holes"])
    return [] if count == HOLE_COUNT else [f"pcb.holes: {count}, expected {HOLE_COUNT} holes"]


def port_problems(layout, board, path=""):
    """Every layout value must sit in board.toml under the same key with the same value."""
    found = []
    for key, want in layout.items():
        where = f"{path}{key}"
        if key not in board:
            found.append(f"board.toml {where}: missing, layout-v2.toml has it")
        elif isinstance(want, dict) and isinstance(board[key], dict):
            found += port_problems(want, board[key], f"{where}.")
        elif board[key] != want:
            found.append(f"board.toml {where}: {board[key]!r}, layout-v2.toml {want!r}")
    return found


def problems(layout, board):
    return [
        *stack_problems(layout),
        *squeeze_problems(layout["foam_frame"]),
        *keepout_problems(layout),
        *hole_problems(layout["pcb"]),
        *port_problems(layout, board),
    ]


def lost_measure_tags(layout_text, board_text):
    """Layout lines tagged MEASURE that board.toml does not carry word for word."""
    board_lines = {line.strip() for line in board_text.splitlines()}
    tagged = [line.strip() for line in layout_text.splitlines() if "MEASURE" in line]
    return [f"board.toml lost a MEASURE line: {line}" for line in tagged if line not in board_lines]


def main():
    layout_text = LAYOUT.read_text(encoding="utf-8")
    board_text = BOARD.read_text(encoding="utf-8")
    layout, board = tomllib.loads(layout_text), tomllib.loads(board_text)
    bad = problems(layout, board) + lost_measure_tags(layout_text, board_text)
    tagged = sum("MEASURE" in line for line in layout_text.splitlines())
    print("\n".join(bad) or f"check_numbers: layout rev {layout['layout_revision']} holds; "
          f"board.toml carries it and its {tagged} MEASURE lines")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
