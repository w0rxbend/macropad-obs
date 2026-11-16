# SPDX-License-Identifier: CERN-OHL-S-2.0
"""One isometric PNG of the assembly mesh. No window is opened."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


COLOURS = {
    "base": "#3a3a3c",
    "top": "#d8d8dc",
    "glass": "#1c1c22",
    "knob": "#636366",
}


def render(folder: Path, png_path: Path) -> None:
    """folder holds base.stl, top.stl, glass.stl, and knob.stl."""
    png_path.parent.mkdir(parents=True, exist_ok=True)
    figure = plt.figure(figsize=(9, 7), dpi=140, facecolor="#141416")
    axis = figure.add_subplot(111, projection="3d", facecolor="#141416")
    low = np.array([np.inf, np.inf, np.inf])
    high = np.array([-np.inf, -np.inf, -np.inf])
    for name, colour in COLOURS.items():
        mesh = trimesh.load_mesh(folder / f"{name}.stl")
        collection = Poly3DCollection(mesh.vertices[mesh.faces], linewidths=0.0)
        collection.set_facecolor(colour)
        collection.set_edgecolor("none")
        axis.add_collection3d(collection)
        low = np.minimum(low, mesh.bounds[0])
        high = np.maximum(high, mesh.bounds[1])
    axis.set_xlim(low[0], high[0])
    axis.set_ylim(low[1], high[1])
    axis.set_zlim(low[2], high[2])
    axis.view_init(elev=64, azim=-128)
    axis.set_axis_off()
    axis.set_box_aspect(high - low)
    figure.tight_layout(pad=0)
    figure.savefig(png_path, facecolor=figure.get_facecolor())
    plt.close(figure)
    print(f"rendered {png_path}")
