# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Renders of the cnc case for docs/images (task 6.9): case.png from the front, rear.png from the
back (insert, USB opening), underside.png from below (plate). No window is opened. The case parts
are the cnc variant; the keycaps and switches are their [envelopes] envelopes and the PCB a plain
board, so the renders show the case, not the bought parts. A z-buffer paints the triangles of every part.
`python -m obs_case.render` writes the three PNGs; a rerun writes the same bytes."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from build123d import Compound, Pos, extrude
from mpl_toolkits.mplot3d import proj3d

from obs_case import b3f_cap, body, envelopes, export, export2d, knob, variants
from obs_case.spec import BOARD_TOML, LAYOUT

IMAGES = BOARD_TOML.parent / "docs" / "images"
VIEWS = {"case.png": (28.0, -58.0), "rear.png": (22.0, 118.0), "underside.png": (-38.0, -58.0)}  # elev, azim
COLOURS = {
    "shell": export.COLOURS[variants.CNC, "shell"],
    "plate": export.COLOURS[variants.CNC, "plate"],
    "insert": export.COLOURS[variants.CNC, "insert"],
    "lens": "#0b0d12",
    "keycaps": "#e4e2de",
    "switches": "#4a403c",
    "knobs": "#2a2c30",
    "caps": "#9a9ca0",
    "pcb": "#1c4f32",
    "usb": "#b7b8b4",
}
KEYCAP_SEAT = 6.6  # mm, MX housing top over the plate top (report 08 [C1]: 11.6 over the PCB); render only
TESSELLATION = 0.02  # mm chord error of each part's triangles
BACKGROUND = "#c4c0ba"


def _rgb(hex_colour: str) -> np.ndarray:
    value = int(hex_colour[1:], 16)
    return np.array(((value >> 16) & 255, (value >> 8) & 255, value & 255), dtype=np.uint8)


def _eye(elev: float, azim: float) -> np.ndarray:
    elev = np.deg2rad(elev)
    azim = np.deg2rad(azim)
    return np.array((np.cos(elev) * np.cos(azim), np.cos(elev) * np.sin(azim), np.sin(elev)))


def _view(low: np.ndarray, high: np.ndarray, elev: float, azim: float):
    figure = plt.figure(figsize=(9, 7), dpi=140, facecolor=BACKGROUND)
    axis = figure.add_subplot(111, projection="3d", facecolor=BACKGROUND)
    axis.set_xlim(low[0], high[0])
    axis.set_ylim(low[1], high[1])
    axis.set_zlim(low[2], high[2])
    axis.view_init(elev=elev, azim=azim)
    axis.set_axis_off()
    axis.set_box_aspect(high - low)
    figure.tight_layout(pad=0)
    figure.canvas.draw()
    return figure, axis


def _screen(axis, vertices: np.ndarray, height: int) -> np.ndarray:
    xs, ys, zs = proj3d.proj_transform(vertices[:, 0], vertices[:, 1], vertices[:, 2], axis.get_proj())
    xy = axis.transData.transform(np.column_stack((xs, ys)))
    return np.column_stack((xy[:, 0], height - xy[:, 1], zs))


def _fill(image: np.ndarray, depth: np.ndarray, triangle: np.ndarray, colour: np.ndarray) -> None:
    height, width = depth.shape
    xy = triangle[:, :2]
    min_x = max(int(np.floor(xy[:, 0].min())), 0)
    max_x = min(int(np.ceil(xy[:, 0].max())), width - 1)
    min_y = max(int(np.floor(xy[:, 1].min())), 0)
    max_y = min(int(np.ceil(xy[:, 1].max())), height - 1)
    if min_x > max_x or min_y > max_y:
        return
    grid_x, grid_y = np.meshgrid(np.arange(min_x, max_x + 1) + 0.5, np.arange(min_y, max_y + 1) + 0.5)
    first, second, third = xy
    area = (second[1] - third[1]) * (first[0] - third[0]) + (third[0] - second[0]) * (first[1] - third[1])
    if abs(area) < 1e-9:
        return
    weight_a = ((second[1] - third[1]) * (grid_x - third[0]) + (third[0] - second[0]) * (grid_y - third[1])) / area
    weight_b = ((third[1] - first[1]) * (grid_x - third[0]) + (first[0] - third[0]) * (grid_y - third[1])) / area
    weight_c = 1.0 - weight_a - weight_b
    inside = (weight_a >= 0) & (weight_b >= 0) & (weight_c >= 0)
    if not np.any(inside):
        return
    surface = weight_a * triangle[0, 2] + weight_b * triangle[1, 2] + weight_c * triangle[2, 2]
    view = depth[min_y : max_y + 1, min_x : max_x + 1]
    closer = inside & (surface < view)
    if not np.any(closer):
        return
    view[closer] = surface[closer]
    patch = image[min_y : max_y + 1, min_x : max_x + 1]
    patch[closer] = colour


def _shade(colour: np.ndarray, normal: np.ndarray, light: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(normal))
    if length < 1e-12:
        return colour
    facing = max(float(normal @ light) / length, 0.0)
    shade = 0.45 + 0.55 * facing
    return np.clip(np.rint(colour * shade), 0, 255).astype(np.uint8)


def _paint(axis, parts: list[tuple[trimesh.Trimesh, np.ndarray]], eye: np.ndarray) -> np.ndarray:
    # Face sort in mplot3d draws the cavity through the top. This buffer keeps the shell.
    width, height = axis.figure.canvas.get_width_height()
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:] = _rgb(BACKGROUND)
    depth = np.full((height, width), np.inf)
    light = eye / np.linalg.norm(eye)
    for mesh, colour in parts:
        triangles = mesh.vertices[mesh.faces]
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        front = normals @ eye > 0
        screen = _screen(axis, mesh.vertices, height)
        for normal, triangle in zip(normals[front], screen[mesh.faces[front]], strict=True):
            _fill(image, depth, triangle, _shade(colour, normal, light))
    return image


def _placed(shape, points):
    """One Compound of `shape` moved to each (x, y) of `points`."""
    return Compound([Pos(x, y, 0) * shape for x, y in points])


def scene() -> dict[str, object]:
    """{COLOURS key: shape} of the assembled cnc case, PCB frame."""
    keys, buttons, knobs, stack = LAYOUT.keys, LAYOUT.buttons, LAYOUT.knobs, LAYOUT.stack
    pcb, usb = LAYOUT.pcb, LAYOUT.usb
    parts = variants.parts(variants.CNC)
    lens_thickness = stack.lens_top - stack.lens_recess_floor
    lenses = Compound([extrude(Pos(0, 0, stack.lens_recess_floor) * export2d.lens(name), amount=lens_thickness)
                       for name in export2d.PANELS])
    keycap = Pos(0, 0, stack.mx_plate_top + KEYCAP_SEAT) * envelopes.parts()["dsa-keycap"]
    _, depth = usb.body
    receptacle = Pos(usb.x, pcb.depth + usb.mouth_overhang - depth / 2, stack.pcb_bottom - usb.height) * (
        envelopes.parts()["usb4216"])
    return {
        "shell": parts["shell"], "plate": parts["plate"], "insert": parts["insert"], "lens": lenses,
        "keycaps": _placed(keycap, [(x, y) for x in keys.x for y in keys.y]),
        "switches": _placed(envelopes.parts()["mx-switch"], [(x, y) for x in keys.x for y in keys.y]),
        "knobs": _placed(knob.dial(), [(knobs.x, y) for y in knobs.y]),
        "caps": _placed(b3f_cap.cap(variants.CNC), [(x, buttons.y) for x in buttons.x]),
        "pcb": body.prism([0, 0, pcb.width, pcb.depth], pcb.corner_radius, stack.pcb_bottom, stack.pcb_top),
        "usb": receptacle,
    }


def _mesh(shape) -> trimesh.Trimesh:
    vertices, triangles = shape.tessellate(TESSELLATION)
    return trimesh.Trimesh([tuple(vertex) for vertex in vertices], triangles, process=False)


def render(parts: list[tuple[trimesh.Trimesh, np.ndarray]], png_path: Path, elev: float, azim: float) -> None:
    """One PNG of `parts`, (mesh, rgb) each, seen from `elev` and `azim` degrees."""
    png_path.parent.mkdir(parents=True, exist_ok=True)
    low = np.min([mesh.bounds[0] for mesh, _colour in parts], axis=0)
    high = np.max([mesh.bounds[1] for mesh, _colour in parts], axis=0)
    figure, axis = _view(low, high, elev, azim)
    image = _paint(axis, parts, _eye(elev, azim))
    plt.close(figure)
    plt.imsave(png_path, image, metadata={"Software": None})
    print(f"rendered {png_path.name}")


def render_all(folder: Path = IMAGES) -> int:
    """Every VIEWS png of the scene into `folder`."""
    parts = [(_mesh(shape), _rgb(COLOURS[name])) for name, shape in scene().items()]
    for name, (elev, azim) in VIEWS.items():
        render(parts, folder / name, elev, azim)
    return 0


if __name__ == "__main__":
    raise SystemExit(render_all())
