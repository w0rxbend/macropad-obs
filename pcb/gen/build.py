# SPDX-License-Identifier: CERN-OHL-S-2.0
"""KiCad 9 entry point for `just pcb`. Unit tests do not import this module."""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def place() -> None:
    from kicad_board import write_board

    write_board()


def write_hash(netlist: bytes) -> None:
    dest = ROOT / "pcb" / "fab" / "board-sha256.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(hashlib.sha256(netlist).hexdigest() + "\n")


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "place"
    if command != "place":
        print("usage: build.py place", file=sys.stderr)
        return 2
    place()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
