# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The printable display carriers (carriers.py): check them against the shell, then write each
carrier's 3D exports (STEP AP214 and AP242, BREP, IGES, STL, 3MF), read each back, and replace
cad/exports/carriers and the manifest's "carriers" section. Each carrier stands on its PCB-face end,
which is its print pose. Its height stays MEASURE until a panel is calipered ([display_carrier]).

Its own module, as export.py imports the case parts that import carriers.py.
`python -m obs_case.carrier_export` runs it."""

from obs_case import carriers, checks, deck
from obs_case.export import EXPORTS, STAGE, fresh, part_files, publish

FOLDER = "carriers"
MEASURE = ("carrier height from the calipered panel",)


def label(name):
    """The STEP product name of a carrier."""
    return f"OBS-CARRIER-{name.upper()}"


def export_all(stage=STAGE, target=EXPORTS) -> int:
    """Check the carriers; when sound, write and read back each one's exports, then publish them.
    Returns 1 on any fault."""
    found = checks.carrier_problems(deck.top_shell())
    for problem in found:
        print(problem)
    print(f"{FOLDER}: {len(carriers.NAMES)} carriers, {len(found)} problems; MEASURE: {', '.join(MEASURE)}")
    if found:
        return 1
    folder = fresh(stage / FOLDER)
    readbacks = [readback for name in carriers.NAMES
                 for readback in part_files(carriers.carrier(name), label(name), folder / name)]
    return publish(readbacks, stage, target, (FOLDER,), FOLDER)


if __name__ == "__main__":
    raise SystemExit(export_all())
