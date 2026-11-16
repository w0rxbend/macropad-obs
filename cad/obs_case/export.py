# SPDX-License-Identifier: CERN-OHL-S-2.0
"""STEP, STL, and 3MF for the wedge. Each mesh is read back."""

from __future__ import annotations

from pathlib import Path

import trimesh
from build123d import Compound, Part, export_step, export_stl, import_step

from .geometry import build_parts

STL_TOLERANCE_MM = 0.05
STL_VOLUME_SHARE = 0.02


def export_all(folder: Path) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    parts = build_parts()
    faults = 0
    for name, solid in parts.items():
        solid.label = name
        faults += _write_part(solid, folder / name)
    assembly = Compound(label="macropad-obs", children=list(parts.values()))
    step = folder / "assembly.step"
    export_step(assembly, step)
    faults += _verify_step(step, assembly, len(parts))
    stl = folder / "assembly.stl"
    _write_mesh(assembly, stl)
    faults += _verify_stl(stl, assembly)
    _write_3mf(stl, folder / "assembly.3mf")
    print(f"exported {len(parts)} parts plus assembly to {folder}; {faults} faults")
    return 1 if faults else 0


def _write_part(solid: Part, stem: Path) -> int:
    step = stem.with_suffix(".step")
    stl = stem.with_suffix(".stl")
    export_step(solid, step)
    _write_mesh(solid, stl)
    _write_3mf(stl, stem.with_suffix(".3mf"))
    return _verify_step(step, solid, 1) + _verify_stl(stl, solid)


def _write_mesh(solid: Part, path: Path) -> None:
    export_stl(solid, path, tolerance=STL_TOLERANCE_MM)
    mesh = trimesh.load_mesh(path)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    mesh.export(path)


def _write_3mf(stl_path: Path, dest: Path) -> None:
    mesh = trimesh.load_mesh(stl_path)
    mesh.export(dest)


def _verify_step(path: Path, original, solids: int) -> int:
    back = import_step(path)
    volume_error = abs(back.volume - original.volume) / original.volume
    ok = len(back.solids()) == solids and back.is_valid and volume_error < 1e-3
    print(f"  {path.name}: {len(back.solids())} solids, valid {back.is_valid}, volume off by {volume_error:.1e}")
    return 0 if ok else 1


def _verify_stl(path: Path, original: Part) -> int:
    mesh = trimesh.load_mesh(path)
    volume_error = abs(mesh.volume - original.volume) / original.volume
    ok = mesh.is_watertight and mesh.volume > 0 and volume_error < STL_VOLUME_SHARE
    print(
        f"  {path.name}: {len(mesh.faces)} triangles, watertight {mesh.is_watertight}, "
        f"volume off by {volume_error:.1e}"
    )
    return 0 if ok else 1
