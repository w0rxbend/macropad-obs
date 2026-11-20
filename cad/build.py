# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Case build entry: `build.py [STEP]`. No step runs every step in order. Needs cad/.venv.

Steps:
  body  build the style A top shell (task 6.2a) and run the geometry checks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

USAGE_EXIT = 2


def body_step() -> int:
    from obs_case import checks, deck

    found = checks.problems(deck.top_shell())
    for problem in found:
        print(problem)
    print(f"body: {len(checks.probes())} probes, {len(found)} problems")
    return 1 if found else 0


STEPS = {"body": body_step}


def main(argv: list[str]) -> int:
    unknown = [step for step in argv if step not in STEPS]
    if unknown:
        print(f"usage: build.py [{'|'.join(STEPS)}]; unknown step {' '.join(unknown)}", file=sys.stderr)
        return USAGE_EXIT
    faults = [STEPS[step]() for step in argv or STEPS]
    return 1 if any(faults) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
