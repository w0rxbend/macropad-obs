# SPDX-License-Identifier: CERN-OHL-S-2.0
"""3D exports with read-back (task 6.5; spec section 1 row 8, criterion 11; report 11 section 8).

Each part of each variant leaves as STEP AP214 (the master for shops), STEP AP242, BREP, IGES, STL
and 3MF; each variant's assembly as STEP AP214, 3MF and GLB. Every file is read back: B-rep files
by solid count (exact), validity and volume (within BREP_SHARE); meshes by watertight, consistent
winding and volume (within MESH_SHARE). The files are byte-repeatable: the STEP and IGES headers
carry TIMESTAMP and AUTHOR, the 3MF UUIDs come from the file name, and each mesh starts from a
cleaned shape, so no finer cached triangulation leaks in (report 11 trap 3). The assembly STEP
carries names and no colours: OCCT writes colour styles in a per-process order. 3MF and GLB carry
the colours.

`_write_3mf`, `assembly` and the GLB path are copied from
macropad-nyxilab/common/cad/macropad_cad/export.py and adapted: deterministic UUIDs, one level of
labelled parts, no components. The AP242 writer is report 11's recipe; it calls build123d's private
`_create_xde`, so cad/pyproject.toml pins build123d 0.13.0."""

from __future__ import annotations

import copy
import shutil
import uuid
from dataclasses import dataclass, field
from math import radians
from pathlib import Path

import trimesh
from build123d import Color, Compound, Mesher, Shape, export_brep, export_gltf, export_step, import_brep, import_step
from build123d.exporters3d import _create_xde
from lib3mf.Lib3MF import ModelUnit
from OCP.APIHeaderSection import APIHeaderSection_MakeHeader
from OCP.BRepTools import BRepTools
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.IGESControl import IGESControl_Controller, IGESControl_Reader, IGESControl_Writer
from OCP.Interface import Interface_Static
from OCP.Message import Message, Message_Gravity
from OCP.STEPCAFControl import STEPCAFControl_Controller, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_StepModelType
from OCP.TCollection import TCollection_HAsciiString
from OCP.XSControl import XSControl_WorkSession

from obs_case import manifest, variants
from obs_case.spec import BOARD_TOML

ROOT = BOARD_TOML.parent
EXPORTS = ROOT / "cad" / "exports"
STAGE = ROOT / ".build" / "cad" / "exports"  # written and read back here, then moved to EXPORTS
TIMESTAMP = "1970-01-01T00:00:00"  # STEP FILE_NAME time stamp; a fixed one keeps git clean
IGES_DATE = "19700101.000000"  # the same instant in the IGES global section format
AUTHOR = "macropad-obs"  # the IGES writer would put the login name here
UUID_SPACE = uuid.uuid5(uuid.NAMESPACE_URL, "macropad-obs/cad/exports")
AP214, AP242 = "AUTOMOTIVE_DESIGN", "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING"
BREP_SHARE = 1e-4  # B-rep read-back volume error allowed (spec 13 `cad`)
MESH_SHARE = 1e-3  # mesh read-back volume error allowed: 0.1 % (spec 13 `cad`)
MESH_LINEAR = 0.01  # relative linear deflection (OCCT isRelative) of every mesh
MESH_ANGULAR = radians(5)  # per segment on a curved edge
GLB_TO_MM = 1000  # glTF is in metres
COLOURS = {  # sRGB hex per (variant, part); the insert is black (open question 1, default)
    (variants.PRINT, "shell"): "#d8d8d4", (variants.PRINT, "plate"): "#d8d8d4",
    (variants.PRINT, "insert"): "#151515",
    (variants.CNC, "shell"): "#2b2f36", (variants.CNC, "plate"): "#2b2f36", (variants.CNC, "insert"): "#151515",
}


@dataclass(frozen=True)
class Readback:
    """What reading one written file back found: facts for the manifest, problems that fail the build."""

    path: Path
    facts: dict
    problems: tuple = field(default=())


def label(variant: str, name: str) -> str:
    """The STEP product name and mesh name of a part: its part number, as the CNC pack's sheets."""
    return f"OBS-CASE-{name.upper()}-{variant.upper()}"


def export_all(stage: Path = STAGE, target: Path = EXPORTS) -> int:
    """Write every variant under `stage`, read each file back, and only when all pass replace the
    variant folders under `target` and the manifest's "case" section. Returns 1 on any fault."""
    readbacks = []
    for variant in variants.VARIANTS:
        readbacks += variant_files(variant, fresh(stage / variant))
    return publish(readbacks, stage, target, variants.VARIANTS, "case")


def fresh(folder: Path) -> Path:
    """`folder`, emptied and made."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    return folder


def publish(readbacks: list[Readback], stage: Path, target: Path, folders, section: str) -> int:
    """Only when no read-back found a problem: replace each of `folders` under `target` with its
    staged copy and `section` of the manifest. Returns 1 on any problem, leaving `target` as it was."""
    problems = [f"{r.path.relative_to(stage)}: {problem}" for r in readbacks for problem in r.problems]
    for problem in problems:
        print(problem)
    if problems:
        print(f"{section}: {len(readbacks)} files, {len(problems)} problems; {target} left as it was")
        return 1
    for folder in folders:
        shutil.rmtree(target / folder, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
        shutil.move(stage / folder, target / folder)
    files = {str(r.path.relative_to(stage)): manifest.entry(target / r.path.relative_to(stage), r.facts)
             for r in readbacks}
    manifest.write_section(target / manifest.NAME, section, files)
    print(f"{section}: {len(readbacks)} files read back, 0 problems; in {target}")
    return 0


def variant_files(variant: str, folder: Path) -> list[Readback]:
    """The parts of `variant` one by one, then its assembly (report 11 trap 2: parts first)."""
    parts = variants.parts(variant)
    readbacks = []
    for name, part in parts.items():
        readbacks += part_files(part, label(variant, name), folder / name)
    pieces = {label(variant, name): (part, COLOURS[variant, name]) for name, part in parts.items()}
    return readbacks + assembly_files(pieces, f"macropad-obs-{variant}", folder / "assembly")


def part_files(part: Shape, name: str, stem: Path) -> list[Readback]:
    """STEP AP214, STEP AP242, BREP, IGES, STL and 3MF of one part, each read back."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    named = _colored(part, name, None)
    step, ap242, brep = stem.with_suffix(".step"), stem.with_suffix(".ap242.step"), stem.with_suffix(".brep")
    iges, stl, three_mf = stem.with_suffix(".igs"), stem.with_suffix(".stl"), stem.with_suffix(".3mf")
    export_step(named, str(step), timestamp=TIMESTAMP)
    _write_ap242(named, ap242)
    BRepTools.Clean_s(named.wrapped)  # BREP stores any cached triangulation
    export_brep(named, str(brep))
    _write_iges(named, iges)
    _write_mesh(stl, [(name, part, None)])
    _write_mesh(three_mf, [(name, part, None)])
    return [step_readback(step, part, name, AP214), step_readback(ap242, part, name, AP242),
            _brep_facts(brep, "BREP", import_brep(str(brep)), part), iges_readback(iges, part),
            stl_readback(stl, name, part), three_mf_readback(three_mf, {name: part})]


def assembly(pieces: dict[str, tuple[Shape, str]], name: str) -> Compound:
    """One Compound of labelled, coloured copies, one level deep: the glTF writer drops deeper
    nesting (nyxilab `assembly_flat`)."""
    return Compound(label=name, children=[_colored(shape, piece, colour) for piece, (shape, colour) in pieces.items()])


def assembly_files(pieces: dict[str, tuple[Shape, str]], name: str, stem: Path) -> list[Readback]:
    """STEP AP214, 3MF and GLB of an assembly of {label: (shape, colour)}, each read back."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    shapes = {piece: shape for piece, (shape, _) in pieces.items()}
    step, three_mf, glb = stem.with_suffix(".step"), stem.with_suffix(".3mf"), stem.with_suffix(".glb")
    export_step(assembly({piece: (shape, None) for piece, shape in shapes.items()}, name), str(step),
                timestamp=TIMESTAMP)
    _write_mesh(three_mf, [(piece, shape, colour) for piece, (shape, colour) in pieces.items()])
    together = assembly(pieces, name)
    for shape in together.children:
        BRepTools.Clean_s(shape.wrapped)
    export_gltf(together, str(glb), binary=True, linear_deflection=MESH_LINEAR, angular_deflection=MESH_ANGULAR)
    readbacks = [step_readback(step, assembly(pieces, name), name, AP214), three_mf_readback(three_mf, shapes),
                 glb_readback(glb, shapes)]
    missing = [piece for piece in shapes if f"PRODUCT('{piece}'" not in step.read_text(encoding="ascii")]
    if missing:
        readbacks[0] = Readback(step, readbacks[0].facts, readbacks[0].problems + (f"no product {missing}",))
    return readbacks


def _colored(shape: Shape, name: str, colour: str | None) -> Shape:
    """A shallow copy with a label and a colour: the original stays out of any assembly."""
    named = copy.copy(shape)
    named.label = name
    if colour:
        named.color = Color(colour)
    return named


def _write_ap242(part: Shape, path: Path) -> None:
    """Report 11's AP242 recipe: `export_step` writes AP214 whatever the schema setting, so transfer
    with the schema set, then make the header (after Transfer, not before)."""
    for printer in Message.DefaultMessenger_s().Printers():  # as export_step: no transfer report
        printer.SetTraceLevel(Message_Gravity.Message_Fail)
    STEPCAFControl_Controller.Init_s()
    Interface_Static.SetCVal_s("write.step.schema", "AP242DIS")
    try:
        writer = STEPCAFControl_Writer(XSControl_WorkSession(), False)
        writer.SetColorMode(True)
        writer.SetLayerMode(True)
        writer.SetNameMode(True)
        writer.Transfer(_create_xde(part, auto_naming=True), STEPControl_StepModelType.STEPControl_AsIs)
        header = APIHeaderSection_MakeHeader(writer.Writer().Model())
        header.SetName(TCollection_HAsciiString(part.label))
        header.SetTimeStamp(TCollection_HAsciiString(TIMESTAMP))
        header.SetOriginatingSystem(TCollection_HAsciiString("build123d"))
        if writer.Write(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
            raise RuntimeError(f"AP242 writer failed on {path}")
    finally:
        Interface_Static.SetCVal_s("write.step.schema", "AP214IS")  # the setting is global


def _write_iges(part: Shape, path: Path) -> None:
    """IGES 5.3 in mm, B-rep mode (mode 0 writes loose faces), with a fixed date and author."""
    IGESControl_Controller.Init_s()
    writer = IGESControl_Writer("MM", 1)
    if not writer.AddShape(part.wrapped):
        raise RuntimeError(f"IGES writer refused {part.label}")
    writer.ComputeModel()
    section = writer.Model().GlobalSection()
    section.SetFileName(TCollection_HAsciiString(path.name))
    section.SetDate(TCollection_HAsciiString(IGES_DATE))
    section.SetLastChangeDate(TCollection_HAsciiString(IGES_DATE))
    section.SetAuthorName(TCollection_HAsciiString(AUTHOR))
    writer.Model().SetGlobalSection(section)
    if not writer.Write(str(path)):
        raise RuntimeError(f"IGES writer failed on {path}")


def _write_mesh(path: Path, items: list[tuple[str, Shape, str | None]]) -> None:
    """3MF or STL by suffix through lib3mf (nyxilab `_write_3mf`): one named, coloured mesh object
    per item, mm. STL takes the same welded mesh, so it has no degenerate triangle either."""
    mesher = Mesher()
    for name, shape, colour in items:
        BRepTools.Clean_s(shape.wrapped)
        mesher.add_shape(_colored(shape, name, colour), linear_deflection=MESH_LINEAR,
                         angular_deflection=MESH_ANGULAR)
    _fix_uuids(mesher.model, path.name)
    mesher.write(str(path))


def _fix_uuids(model, seed: str) -> None:
    """lib3mf gives every object, component and build item a random UUID; name them from `seed`."""
    def stamp(kind, index):
        return str(uuid.uuid5(UUID_SPACE, f"{seed}/{kind}/{index}"))

    for index, item in enumerate(_each(model.GetObjects(), "GetCurrentObject")):
        item.SetUUID(stamp("object", index))
    for index, group in enumerate(_each(model.GetComponentsObjects(), "GetCurrentComponentsObject")):
        for part in range(group.GetComponentCount()):
            group.GetComponent(part).SetUUID(stamp(f"component{index}", part))
    for index, item in enumerate(_each(model.GetBuildItems(), "GetCurrent")):
        item.SetUUID(stamp("item", index))
    model.SetBuildUUID(stamp("build", 0))


def _each(iterator, getter: str):
    while iterator.MoveNext():
        yield getattr(iterator, getter)()


def _solids_volume(shape: Shape) -> tuple[int, float]:
    """Solid count and summed volume. A compound of compounds reports a short `volume`."""
    solids = shape.solids()
    return len(solids), sum(solid.volume for solid in solids)


def _brep_facts(path: Path, kind: str, back: Shape, expected: Shape) -> Readback:
    count, volume = _solids_volume(expected)
    back_count, back_volume = _solids_volume(back)
    error = abs(back_volume - volume) / volume
    problems = []
    if back_count != count:
        problems.append(f"{back_count} solids read back, {count} written")
    if not back.is_valid:
        problems.append("read back invalid")
    if not error < BREP_SHARE:
        problems.append(f"volume off by {error:.1e}, limit {BREP_SHARE:.0e}")
    facts = {"format": kind, "solids": back_count, "valid": back.is_valid, "volume_mm3": round(back_volume, 3),
             "volume_error": f"{error:.1e}"}
    print(f"  {path.parent.name}/{path.name}: {kind}, {back_count} solids, valid {back.is_valid}, "
          f"volume off by {error:.1e}")
    return Readback(path, facts, tuple(problems))


def step_readback(path: Path, expected: Shape, name: str, schema: str) -> Readback:
    """Solids, validity and volume, plus the header: schema, product name and the fixed time stamp."""
    kind = "STEP AP242" if schema == AP242 else "STEP AP214"
    found = _brep_facts(path, kind, import_step(str(path)), expected)
    header = "".join(path.read_text(encoding="ascii").split("ENDSEC;", 1)[0].split())  # no line breaks
    wants = {f"FILE_SCHEMA(('{schema}": "schema", f"FILE_NAME('{name}','{TIMESTAMP}'": "name or time stamp"}
    problems = [f"header lacks the {what}" for text, what in wants.items() if "".join(text.split()) not in header]
    return Readback(path, found.facts, found.problems + tuple(problems))


def iges_readback(path: Path, expected: Shape) -> Readback:
    reader = IGESControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
        return Readback(path, {"format": "IGES"}, ("IGES reader failed",))
    reader.TransferRoots()
    return _brep_facts(path, "IGES", Shape.cast(reader.OneShape()), expected)


def _mesh_facts(path: Path, kind: str, meshes: dict, expected: dict[str, Shape], scale: float = 1.0) -> Readback:
    """Each expected body's mesh: watertight, consistent winding, volume within MESH_SHARE."""
    problems = []
    bodies = {}
    if sorted(meshes) != sorted(expected):
        problems.append(f"bodies {sorted(meshes)}, expected {sorted(expected)}")
    for name in sorted(set(meshes) & set(expected)):
        mesh = meshes[name]
        _, volume = _solids_volume(expected[name])
        error = abs(mesh.volume * scale ** 3 - volume) / volume
        closed = bool(mesh.is_watertight and mesh.is_winding_consistent)
        if not closed:
            problems.append(f"{name} not watertight or winding inconsistent")
        if not error < MESH_SHARE:
            problems.append(f"{name} volume off by {error:.1e}, limit {MESH_SHARE:.0e}")
        bodies[name] = {"triangles": len(mesh.faces), "watertight": closed, "volume_error": f"{error:.1e}"}
        print(f"  {path.parent.name}/{path.name}: {kind} {name}, {len(mesh.faces)} triangles, watertight {closed}, "
              f"volume off by {error:.1e}")
    return Readback(path, {"format": kind, "bodies": bodies}, tuple(problems))


def stl_readback(path: Path, name: str, expected: Shape) -> Readback:
    return _mesh_facts(path, "STL", {name: trimesh.load_mesh(path, file_type="stl")}, {name: expected})


def three_mf_readback(path: Path, expected: dict[str, Shape]) -> Readback:
    """lib3mf reads the names, the unit and each object's triangles back."""
    reader = Mesher()
    reader.model.QueryReader("3mf").ReadFromFile(str(path))
    meshes = {}
    for mesh in _each(reader.model.GetMeshObjects(), "GetCurrentMeshObject"):
        vertices = [vertex.Coordinates[0:3] for vertex in mesh.GetVertices()]
        faces = [triangle.Indices[0:3] for triangle in mesh.GetTriangleIndices()]
        meshes[mesh.GetName()] = trimesh.Trimesh(vertices, faces, process=False)
    found = _mesh_facts(path, "3MF", meshes, expected)
    unit = reader.model.GetUnit()
    problems = () if unit == ModelUnit.MilliMeter else (f"unit {unit}, expected mm",)
    return Readback(path, found.facts, found.problems + problems)


def glb_readback(path: Path, expected: dict[str, Shape]) -> Readback:
    """Each labelled node's face meshes, joined and welded, in mm (glTF is metres, Y up). The OCCT
    triangulation can hold a zero-area triangle where a curved face pinches; it is dropped before the
    watertight check, and the count is recorded."""
    scene = trimesh.load(path, file_type="glb", force="scene")
    meshes = {}
    dropped = {}
    for name in expected:
        if name not in scene.graph.nodes:
            continue
        pieces = [scene.geometry[geometry].copy().apply_transform(scene.graph[node][0])
                  for node in _descendants(scene.graph.transforms.children, name)
                  if (geometry := scene.graph[node][1]) is not None]
        joined = trimesh.util.concatenate(pieces)
        joined.merge_vertices(merge_tex=True, merge_norm=True)
        kept = joined.nondegenerate_faces()
        dropped[name] = int(len(kept) - kept.sum())
        joined.update_faces(kept)
        meshes[name] = joined
    found = _mesh_facts(path, "GLB", meshes, expected, scale=GLB_TO_MM)
    return Readback(path, {**found.facts, "zero_area_dropped": dropped}, found.problems)


def _descendants(children: dict, node: str) -> list[str]:
    below = [node]
    for child in children.get(node, ()):
        below += _descendants(children, child)
    return below


if __name__ == "__main__":
    raise SystemExit(export_all())
