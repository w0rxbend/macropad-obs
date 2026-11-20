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
            the "case" section of cad/exports/manifest.json. Tests: obs_case/test_export.py.
  export2d  write the 2D sheets (task 6.6): DXF, SVG and PDF of each lens and foam frame, read
            back, into cad/exports/2d and the "2d" section. Tests: obs_case/test_export2d.py.
  envelopes write one STEP per bought part (task 6.6), read back, into cad/exports/envelopes and
            the "envelopes" section. Tests: obs_case/test_envelopes.py.
  fcstd     record in the "freecad" section that the FCStd is not built, and why.
  laser     check the deck engrave marks (task 6.7) against the shop rules and the deck, write the
            sheet (DXF layers MARK and REF, SVG, PDF), read it back, into cad/exports/laser and the
            "laser" section. Tests: obs_case/test_laser.py.
  knob      check the knob dial (task 6.10), write its 3D exports, read each back, into
            cad/exports/knob and the "knob" section. Tests: obs_case/test_knob_caps.py.
  b3f       check the B3F caps, press-on (print) and floating (cnc) (task 6.10), write their 3D
            exports, read each back, into cad/exports/b3f-cap and the "b3f-cap" section.
  coupons   cut the print coupons (task 6.9) from the print parts, check each, write their 3D
            exports, read each back, into cad/exports/coupons and the "coupons" section.
            Tests: obs_case/test_coupons.py.
  render    render the cnc case to docs/images case.png, rear.png and underside.png (task 6.9).
  fit       check every case part of both variants against the board STEP of `just pcb step` and
            each other (task 6.8): 0 interferences, and the MEASURE gaps reported.
            Tests: obs_case/test_fit.py."""

import os
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
    return _fresh_process("obs_case.export")


def export2d_step() -> int:
    """In a fresh process with a fixed hash seed: ezdxf orders the DXF OBJECTS section by string
    hash, so another seed writes other bytes."""
    return _fresh_process("obs_case.export2d")


def _fresh_process(module: str) -> int:
    sys.stdout.flush()  # keep the step lines in order when stdout is a pipe
    return subprocess.run([sys.executable, "-m", module], cwd=Path(__file__).resolve().parent,
                          env={**os.environ, "PYTHONHASHSEED": "0"}, check=False).returncode


def laser_step() -> int:
    """In a fresh process with a fixed hash seed, for the DXF bytes (as export2d)."""
    return _fresh_process("obs_case.laser")


def knob_step() -> int:
    """In a fresh process with a fixed hash seed, as export: the same bytes from any step order."""
    return _fresh_process("obs_case.knob")


def b3f_step() -> int:
    """In a fresh process with a fixed hash seed, as export."""
    return _fresh_process("obs_case.b3f_cap")


def coupons_step() -> int:
    """In a fresh process with a fixed hash seed, as export."""
    return _fresh_process("obs_case.coupons")


def render_step() -> int:
    """In a fresh process, as export: the same triangles, so the same PNG bytes, from any step order."""
    return _fresh_process("obs_case.render")


def fit_step() -> int:
    from obs_case import fit

    return fit.run()


def envelopes_step() -> int:
    from obs_case import envelopes

    return envelopes.export_all()


FCSTD_NOT_BUILT = ("not built: the FCStd needs FreeCAD (freecadcmd), which task 6.6 may use only after the"
                   " owner says yes; nyxilab freecad_doc.py is not copied until then")


def fcstd_step() -> int:
    """Task 6.6 accepts an FCStd that is reopened or marked not built in the manifest: this marks it."""
    from obs_case import manifest
    from obs_case.export import EXPORTS

    manifest.write_section(EXPORTS / manifest.NAME, "freecad",
                           {"case.FCStd": {"built": False, "reason": FCSTD_NOT_BUILT}})
    print(f"freecad: case.FCStd {FCSTD_NOT_BUILT}")
    return 0


STEPS = {"body": body_step, "carriers": carriers_step, "insert": insert_step, "variants": variants_step,
         "cnc": cnc_step, "export": export_step, "export2d": export2d_step, "envelopes": envelopes_step,
         "fcstd": fcstd_step, "laser": laser_step, "knob": knob_step, "b3f": b3f_step,
         "coupons": coupons_step, "render": render_step, "fit": fit_step}


def main(argv: list[str]) -> int:
    unknown = [step for step in argv if step not in STEPS]
    if unknown:
        print(f"usage: build.py [{'|'.join(STEPS)}]; unknown step {' '.join(unknown)}", file=sys.stderr)
        return USAGE_EXIT
    faults = [STEPS[step]() for step in argv or STEPS]
    return 1 if any(faults) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
