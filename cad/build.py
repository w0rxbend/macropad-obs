# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Case check and export. Numbers always run. Solids need cad/.venv."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from obs_case.numbers import check

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / "cad" / ".venv" / "bin" / "python"
EXPORTS = Path(__file__).resolve().parent / "exports"


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "check"
    if command not in {"check", "geometry", "export"}:
        print("usage: build.py check|export", file=sys.stderr)
        return 2
    problems = check()
    for problem in problems:
        print(problem)
    if problems:
        return 1
    if command == "check" and not VENV.exists():
        print("cad check skipped: no cad/.venv")
        return 0
    if command == "check":
        return 0
    if VENV.exists() and Path(sys.executable).resolve() != VENV.resolve():
        _reexec(command)
    from obs_case.export import export_all
    from obs_case.render import render

    faults = export_all(EXPORTS)
    render(EXPORTS, ROOT / "docs" / "images" / "case.png")
    return faults


def _reexec(command: str) -> None:
    import os

    os.execv(VENV, [str(VENV), str(Path(__file__).resolve()), command])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
