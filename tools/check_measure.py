#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Board-order gate (docs/spec/spec-v2.md section 9, build order step 6): list every MEASURE tag
that board.toml still carries on an entry the board depends on, and exit 1 if any is open.
No board order while this exits 1. A tag is closed by replacing it with the measured value."""

import re
import sys
from pathlib import Path
from typing import NamedTuple

BOARD = Path(__file__).resolve().parent.parent / "board.toml"
TAG = "MEASURE"
# The entries spec 9 step 6 names: whole tables, and single keys of the other tables.
GATED_TABLES = {"display_carrier", "knobs", "mcu", "antenna", "usb", "regulator"}
GATED_TABLE_PREFIX = "fpc."
GATED_KEYS = {"board_slots", "key_ribs", "holes", "antenna_relief"}
TABLE_HEADER = re.compile(r"\[([^\[\]]+)\]\s*(#.*)?$")
KEY = re.compile(r"([A-Za-z0-9_-]+)\s*=")


class OpenMeasure(NamedTuple):
    line_number: int
    table: str
    key: str
    text: str


def owned_lines(text):
    """Each line of a board file as (line number, table, keys, line), in file order.
    A value line has one key. A comment line has the key above it and the key below it, both
    of its own table: the file comments an entry on either side, and the gate must not miss one."""
    table, key_above, comments = "", None, []

    def flush(key_below=None):
        keys = tuple(key for key in (key_above, key_below) if key)
        yield from ((number, table, keys, comment) for number, comment in comments)
        comments.clear()

    for number, line in enumerate(text.splitlines(), start=1):
        header, key = TABLE_HEADER.match(line), KEY.match(line)
        if line.lstrip().startswith("#"):
            comments.append((number, line))
        elif header:
            yield from flush()
            table, key_above = header.group(1), None
        elif key:
            yield from flush(key.group(1))
            key_above = key.group(1)
            yield number, table, (key_above,), line
        elif line.strip():
            yield number, table, (key_above,) if key_above else (), line
    yield from flush()


def is_gated_table(table):
    return table in GATED_TABLES or table.startswith(GATED_TABLE_PREFIX)


def open_measures(text):
    """Every MEASURE tag of a board file that sits on a gated table or a gated key."""
    found = []
    for number, table, keys, line in owned_lines(text):
        gated_keys = [key for key in keys if key in GATED_KEYS]
        if TAG in line and (gated_keys or is_gated_table(table)):
            key = (gated_keys or keys or ("",))[0]
            found.append(OpenMeasure(number, table, key, line.strip()))
    return found


def main(board=BOARD):
    found = open_measures(board.read_text(encoding="utf-8"))
    for tag in found:
        print(f"{board.name}:{tag.line_number} [{tag.table}] {tag.key}: {tag.text}")
    if found:
        print(f"check_measure: {len(found)} open {TAG} tags on the gated entries: no board order")
        return 1
    print(f"check_measure: no open {TAG} tag on the gated entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
