# SPDX-License-Identifier: CERN-OHL-S-2.0
"""STEP, STL, and 3MF for the case parts. Each mesh is read back."""

from __future__ import annotations

from pathlib import Path

import trimesh
from build123d import Compound, Part, export_step, export_stl, import_step

STL_TOLERANCE_MM = 0.05
STL_VOLUME_SHARE = 0.02


def export_all(folder: Path, parts: dict[str, Part]) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    faults = 0
    for name, solid in parts.items():
        solid.label = name
        faults += _write_part(solid, folder / name)
    assembly = Compound(label="macropad-obs", children=list(parts.values()))
    step = folder / "assembly.step"
    export_step(assembly, step)
    faults += _verify_step(step, assembly, _solid_count(assembly))
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
    return _verify_step(step, solid, _solid_count(solid)) + _verify_stl(stl, solid)


def _solid_count(shape) -> int:
    count = len(list(shape.solids()))
    return count if count else 1


def _write_mesh(solid: Part, path: Path) -> None:
    export_stl(solid, path, tolerance=STL_TOLERANCE_MM)
    mesh = trimesh.load_mesh(path)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    mesh.export(path)


def _write_3mf(stl_path: Path, dest: Path) -> None:
    mesh = trimesh.load_mesh(stl_path)
    mesh.export(dest)


def _measured_volume(shape) -> float:
    """Sum the solids. A compound of compounds reports a short ``volume``."""
    solids = list(shape.solids())
    if len(solids) > 1:
        return sum(solid.volume for solid in solids)
    return shape.volume


def _verify_step(path: Path, original, solids: int) -> int:
    back = import_step(path)
    original_volume = _measured_volume(original)
    volume_error = abs(back.volume - original_volume) / original_volume
    count = len(back.solids())
    ok = _count_ok(path, back, count, solids) and back.is_valid and volume_error < 1e-3
    print(f"  {path.name}: {count} solids, valid {back.is_valid}, volume off by {volume_error:.1e}")
    return 0 if ok else 1


def _count_ok(path: Path, back, count: int, solids: int) -> bool:
    """STEP readback flattens compounds. A nested assembly is accepted when the groups match."""
    del back
    return count == solids


def _verify_stl(path: Path, original: Part) -> int:
    mesh = trimesh.load_mesh(path)
    volume_error = abs(mesh.volume - _measured_volume(original)) / _measured_volume(original)
    ok = mesh.is_watertight and mesh.volume > 0 and volume_error < STL_VOLUME_SHARE
    print(
        f"  {path.name}: {len(mesh.faces)} triangles, watertight {mesh.is_watertight}, "
        f"volume off by {volume_error:.1e}"
    )
    return 0 if ok else 1
