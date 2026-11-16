#!/usr/bin/env python3
"""Print LAUNCH, SKIP, or STOP for the Apple case supervisor.

STOP at 21:00 Europe/Kyiv on 2026-11-16, and on any later date.
SKIP while a case-apple-form run is still active, or for three minutes
after a launch lock is taken. LAUNCH takes that lock.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SESSION = Path(
    "/home/worxbend/.grok/sessions/"
    "%2Fhome%2Fworxbend%2FProjects%2Fmacropad-obs/"
    "01a1e362-d351-7a92-b1d6-54b39892c5ec/workflows"
)
LOCK = Path("/tmp/macropad-obs-apple-launch.lock")
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


def _stop_now(now: datetime) -> bool:
    if now.date().isoformat() > "2026-11-16":
        return True
    return now.date().isoformat() == "2026-11-16" and (now.hour > 21 or (now.hour == 21 and now.minute >= 0))


def _busy() -> bool:
    if not SESSION.is_dir():
        return False
    for state_path in SESSION.glob("wf_*/state.json"):
        data = json.loads(state_path.read_text(encoding="utf-8")).get("state", {})
        if data.get("name") != "case-apple-form":
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
    now = datetime.now(ZoneInfo("Europe/Kyiv"))
    if _stop_now(now):
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
