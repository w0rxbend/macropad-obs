# SPDX-License-Identifier: CERN-OHL-S-2.0
"""One isometric PNG of the assembly mesh. No window is opened."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d import proj3d


COLOURS = {
    "base": "#3a3c40",
    "top": "#d0d1d4",
    "glass": "#4a4c52",
    "display": "#07080c",
    "knob": "#2a2c30",
    "keycaps": "#e4e2de",
    "screws": "#c5c8cc",
    "pcb": "#1c4f32",
    "usb": "#b7b8b4",
    "encoder": "#242628",
    "switches": "#4a403c",
}
ELEV_DEG = 28.0
AZIM_DEG = -58.0
BACKGROUND = "#c4c0ba"


def _rgb(hex_colour: str) -> np.ndarray:
    value = int(hex_colour[1:], 16)
    return np.array(((value >> 16) & 255, (value >> 8) & 255, value & 255), dtype=np.uint8)


def _eye(elev: float = ELEV_DEG, azim: float = AZIM_DEG) -> np.ndarray:
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


def _load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(path)
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    return mesh


def render(folder: Path, png_path: Path, elev: float = ELEV_DEG, azim: float = AZIM_DEG) -> None:
    """folder holds one stl per COLOURS key."""
    png_path.parent.mkdir(parents=True, exist_ok=True)
    parts = [(_load_mesh(folder / f"{name}.stl"), _rgb(colour)) for name, colour in COLOURS.items()]
    low = np.min([mesh.bounds[0] for mesh, _colour in parts], axis=0)
    high = np.max([mesh.bounds[1] for mesh, _colour in parts], axis=0)
    figure, axis = _view(low, high, elev, azim)
    image = _paint(axis, parts, _eye(elev, azim))
    plt.close(figure)
    plt.imsave(png_path, image)
    print(f"rendered {png_path}")
