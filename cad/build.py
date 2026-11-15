# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Case check. Numbers always run. Geometry runs only under cad/.venv."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from obs_case.geometry import build_solids
from obs_case.numbers import check

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / "cad" / ".venv" / "bin" / "python"


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "check"
    if command not in {"check", "geometry"}:
        print("usage: build.py check", file=sys.stderr)
        return 2
    problems = check()
    for problem in problems:
        print(problem)
    if problems:
        return 1
    if command == "check" and not VENV.exists():
        print("cad check skipped: no cad/.venv")
        return 0
    if command == "check" and VENV.exists() and Path(sys.executable).resolve() != VENV.resolve():
        os_exec()
    build_solids()
    return 0


def os_exec() -> None:
    import os

    os.execv(VENV, [str(VENV), str(Path(__file__).resolve()), "geometry"])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
