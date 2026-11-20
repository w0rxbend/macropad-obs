# SPDX-License-Identifier: CERN-OHL-S-2.0
"""cad/exports/manifest.json (report 11 section 8, criterion 11): each export's SHA-256, size and
what its read-back found, plus the tool versions that wrote it. One section per writer: task 6.5
writes "case"; the envelopes (6.6) and the board STEP (5.11) add their own. A writer replaces only
its own section, and the file holds no time or path outside the repo, so a rebuild keeps git clean."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

NAME = "manifest.json"
TOOLS = ("build123d", "cadquery-ocp-novtk", "trimesh", "lib3mf")


def entry(path: Path, facts: dict) -> dict:
    """One file's line: size, SHA-256 and its read-back facts."""
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), **facts}


def write_section(path: Path, section: str, files: dict) -> None:
    """Replace `section` of the manifest at `path` with `files` and the tool versions."""
    document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    document[section] = {"tools": {tool: version(tool) for tool in TOOLS}, "files": files}
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
