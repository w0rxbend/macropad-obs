# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Freerouting 2.5.0 on the board's free nets (task 5.9, report 09). Runs on the host, stdlib only.

    freeroute.py   the jar by sha256 into pcb/.cache, then DSN_PATH -> SES_PATH in eclipse-temurin:25-jre

build.py writes the DSN (step `dsn`) and reads the session back (step `routed`) in the KiCad image; this
step sits between them because the router needs Java, which the KiCad image does not have. The jar is
GPL-3.0 (report 09 [F3]): it is fetched, kept in an ignored cache and never committed. A file at another
sha256, fetched or cached, stops the run.

The call is report 09's: outer layers only (pcb/outer.rules), no neck-down (pitfall 2), no GUI, no network.
Two more settings: the fan-out pre-pass is off, as it necks tracks down at pins whatever the neck-down
setting says, and the edge clearance is KiCad's 0.3 mm. The host name resolves to the loopback, or the
logger fails to look it up without a network.
Freerouting's own verdict is not used (pitfall 1); KiCad's DRC on the imported board is the judge.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

VERSION = "2.5.0"
SHA256 = "f6f51bb02245e8e717f9359bd260cc9c5c0b1bc0acc8b7cb2cd5b8ffeb5de3c7"  # report 09 [F1]
URL = f"https://github.com/freerouting/freerouting/releases/download/v{VERSION}/freerouting-{VERSION}.jar"
IMAGE = "eclipse-temurin:25-jre"
PCB_DIR = Path(__file__).resolve().parents[1]
JAR_PATH = PCB_DIR / ".cache" / f"freerouting-{VERSION}.jar"
RULES_PATH = PCB_DIR / "outer.rules"
WORK_DIR = PCB_DIR / ".build" / "freeroute"
# Freerouting reads pcb/outer.rules only for a design of this name, the DSN file's stem.
DESIGN = "macropad-obs"
DSN_PATH = WORK_DIR / f"{DESIGN}.dsn"
SES_PATH = WORK_DIR / f"{DESIGN}.ses"
# KiCad's board edge clearance (layout.EDGE_CLEARANCE); Freerouting's own default is 250 um (pitfall 5).
EDGE_CLEARANCE_UM = 300
DOWNLOAD_TIMEOUT = 120  # s, per read
CHUNK = 1 << 20


class WrongDigest(Exception):
    """The jar is not the pinned release."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _check(path: Path, expected: str) -> None:
    found = _sha256(path)
    if found != expected:
        raise WrongDigest(f"{path} has sha256 {found}, not the pinned {expected}")


def fetch(jar: Path = JAR_PATH, expected: str = SHA256, opener: Callable = urllib.request.urlopen) -> Path:
    """The jar at `expected`, from the cache or downloaded into it. Raises WrongDigest on any other file."""
    if jar.exists():
        _check(jar, expected)  # a bad cached file is not replaced: someone should look at it
        return jar
    jar.parent.mkdir(parents=True, exist_ok=True)
    partial = jar.with_name(jar.name + ".part")
    try:
        with opener(URL, timeout=DOWNLOAD_TIMEOUT) as response, partial.open("wb") as out:
            for block in iter(lambda: response.read(CHUNK), b""):
                out.write(block)
        _check(partial, expected)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(jar)
    return jar


def command(uid: int, gid: int) -> list[str]:
    """The router call, as report 09 ran it clean, with the repository mounted at its own path."""
    root = str(PCB_DIR.parent)
    return ["docker", "run", "--rm", "--network", "none", "--hostname", "router", "--add-host", "router:127.0.0.1",
            "-u", f"{uid}:{gid}", "-e", "HOME=/tmp", "-v", f"{root}:{root}", "-w", root, IMAGE,
            "java", "-jar", str(JAR_PATH), "-de", str(DSN_PATH), "-do", str(SES_PATH), "-dr", str(RULES_PATH),
            "-da", "--gui.enabled=false", "--router.automatic_neckdown=false", "--router.fanout.enabled=false",
            f"--router.copper_to_edge_clearance_um={EDGE_CLEARANCE_UM}", f"--user_data_path={WORK_DIR}"]


def run() -> None:
    fetch()
    assert DSN_PATH.exists(), f"no {DSN_PATH}: run `just pcb dsn` first"
    SES_PATH.unlink(missing_ok=True)
    subprocess.run(command(os.getuid(), os.getgid()), check=True, stdout=subprocess.DEVNULL)
    assert SES_PATH.exists(), f"Freerouting exited without writing {SES_PATH}"
    print(f"freeroute: Freerouting {VERSION} (sha256 {SHA256[:12]}...) wrote {SES_PATH.name}")


if __name__ == "__main__":
    try:
        run()
    except WrongDigest as error:
        sys.exit(f"freeroute: {error}")
