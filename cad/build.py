# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Case build entry: `build.py [STEP]`. No step runs every step in order. Needs cad/.venv.

Steps:
  body      build the style A top shell (task 6.2a) and run the geometry checks.
  carriers  build the display carriers and foam frames (task 6.2b) and check them against the
            shell and the tools/check_numbers.py stack and squeeze rules.
  insert    build the back-wall insert, its pocket in the shell and the bottom plate (task 6.3),
            and check that no metal sits in the antenna board cut.
  variants  build the print and cnc variants (task 6.4) and check each: its fits, and for cnc the
            shop rules (no sharp inside corner, JLCCNC corner radius, cutter reach).
  cnc       write the CNC pack (task 6.4): STEP, PDF drawing and DXF of each milled part, read
            back, under .build/cad/cnc.
  export    write the 3D exports of both variants (task 6.5): STEP AP214 and AP242, BREP, IGES,
            STL, 3MF and the assembly GLB, read each back, then replace cad/exports/<variant> and
            the "case" section of cad/exports/manifest.json. Tests: obs_case/test_export.py."""

import subprocess
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


def carriers_step() -> int:
    from obs_case import carriers, checks, deck

    found = checks.carrier_problems(deck.top_shell())
    for problem in found:
        print(problem)
    print(f"carriers: {len(carriers.NAMES)} carriers and foam frames, {len(found)} problems")
    return 1 if found else 0


def insert_step() -> int:
    from obs_case import bottom, checks, insert

    parts = {"shell": insert.shell(), "plate": bottom.plate(), "insert": insert.insert()}
    found = checks.insert_problems(parts)
    for problem in found:
        print(problem)
    print(f"insert: {len(checks.insert_probes(parts))} probes, {len(found)} problems;"
          f" MEASURE: {', '.join(insert.MEASURE)}")
    return 1 if found else 0


def variants_step() -> int:
    from obs_case import checks, variants

    found = []
    for variant in variants.VARIANTS:
        found += checks.variant_problems(variants.parts(variant), variant)
    for problem in found:
        print(problem)
    reliefs = len(variants.inside_corners(variants.parts(variants.CNC)["shell"]))
    print(f"variants: {', '.join(variants.VARIANTS)} built, {len(found)} problems;"
          f" sharp inside corners left in the cnc shell: {reliefs}")
    return 1 if found else 0


def cnc_step() -> int:
    from obs_case import drawings

    return drawings.write_pack(drawings.PACK)


def export_step() -> int:
    """In a fresh process: the steps above add pcurves to the cached parts and nudge their
    tolerances, and BREP and IGES would carry that history into the files."""
    sys.stdout.flush()  # keep the step lines in order when stdout is a pipe
    return subprocess.run([sys.executable, "-m", "obs_case.export"], cwd=Path(__file__).resolve().parent,
                          check=False).returncode


STEPS = {"body": body_step, "carriers": carriers_step, "insert": insert_step, "variants": variants_step,
         "cnc": cnc_step, "export": export_step}


def main(argv: list[str]) -> int:
    unknown = [step for step in argv if step not in STEPS]
    if unknown:
        print(f"usage: build.py [{'|'.join(STEPS)}]; unknown step {' '.join(unknown)}", file=sys.stderr)
        return USAGE_EXIT
    faults = [STEPS[step]() for step in argv or STEPS]
    return 1 if any(faults) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
