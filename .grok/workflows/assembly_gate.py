#!/usr/bin/env python3
"""Print LAUNCH, SKIP, or STOP for the assembly supervisor.

STOP when the handoff says the clean agent accepted.
SKIP while a case-assembly run is active, or for three minutes after a launch lock.
LAUNCH takes that lock. There is no clock stop.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

SESSION = Path(
    "/home/worxbend/.grok/sessions/"
    "%2Fhome%2Fworxbend%2FProjects%2Fmacropad-obs/"
    "01a1e362-d351-7a92-b1d6-54b39892c5ec/workflows"
)
LOCK = Path("/tmp/macropad-obs-assembly-launch.lock")
HANDOFF = Path("/tmp/macropad-obs-assembly-handoff.md")
TERMINAL = {
    "complete",
    "failed",
    "cancelled",
    "canceled",
    "stopped",
    "interrupted",
    "error",
}
LOCK_SECONDS = 180


def _accepted() -> bool:
    if not HANDOFF.is_file():
        return False
    for line in HANDOFF.read_text(encoding="utf-8").splitlines():
        if line.strip() == "accept: true":
            return True
    return False


def _is_assembly_run(name: object) -> bool:
    text = str(name or "")
    return text == "case-assembly" or text.startswith("case-assembly-")


def _busy() -> bool:
    if not SESSION.is_dir():
        return False
    for state_path in SESSION.glob("wf_*/state.json"):
        data = json.loads(state_path.read_text(encoding="utf-8")).get("state", {})
        if not _is_assembly_run(data.get("name")):
            continue
        status = str(data.get("status", "")).lower()
        if status not in TERMINAL:
            return True
    return False


def _take_lock() -> bool:
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        age = time.time() - LOCK.stat().st_mtime
        if age < LOCK_SECONDS:
            return False
        LOCK.unlink(missing_ok=True)
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            return False
    os.write(fd, str(int(time.time())).encode())
    os.close(fd)
    return True


def main() -> None:
    if _accepted():
        print("STOP")
        return
    try:
        if _busy():
            print("SKIP")
            return
    except (OSError, json.JSONDecodeError, UnicodeError):
        print("SKIP")
        return
    if not _take_lock():
        print("SKIP")
        return
    print("LAUNCH")


if __name__ == "__main__":
    main()
