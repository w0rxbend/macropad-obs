#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""padsim smoke test (task 2.16): padsim starts, answers INFO over its pseudo-terminal, connects
to tools/fake_obs.py, gives the bad-key STATUS after `wifi bad_key`, takes the stdin commands, and
a `--cut-after 3` run dies at program call 3 while the next start mounts the same NOR image.

    python3 tools/padsim_smoke.py PADSIM

Python standard library only. Exits 0 when every check passes.
"""

import hashlib
import os
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time
import tty
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKE_OBS = ROOT / "tools" / "fake_obs.py"
MINIMAL_DOC = ROOT / "firmware" / "test" / "config_vectors" / "valid_minimal.json"
TIMEOUT_S = 10.0

SOF, VERSION = 0xA5, 0x02
INFO_GET, CFG_READ, CFG_BEGIN, CFG_CHUNK, CFG_COMMIT = 0x01, 0x02, 0x03, 0x04, 0x05
INFO, CFG_DATA, STATUS, INPUT = 0x82, 0x83, 0x85, 0x87
RESULT_OK = 0
OBS_UP = 4
WIFI_UP, WIFI_BAD_KEY = 4, 2
CHUNK_MAX, READ_MAX = 238, 232
MAIN_FRAME_BYTES, STRIP_FRAME_BYTES = 320 * 480 * 2, 142 * 428 * 2


def crc16_modbus(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def encode(frame_type, frame_id, payload=b""):
    body = struct.pack("<BBBH", VERSION, frame_type, frame_id, len(payload)) + payload
    return bytes([SOF]) + body + struct.pack("<H", crc16_modbus(body))


class Pad:
    """One padsim process and its pseudo-terminal."""

    def __init__(self, padsim, nor, obs_port=None, cut_after=None):
        command = [padsim, "--nor", str(nor)]
        if obs_port is not None:
            command += ["--obs", f"127.0.0.1:{obs_port}"]
        if cut_after is not None:
            command += ["--cut-after", str(cut_after)]
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        first = self.line()
        check(first.startswith("pty "), f"first line names the pty: {first!r}")
        self.fd = os.open(first.split(" ", 1)[1], os.O_RDWR | os.O_NOCTTY)
        tty.setraw(self.fd, termios.TCSANOW)
        self.buffer = b""
        self.next_id = 1
        self.statuses = []

    def line(self):
        ready, _, _ = select.select([self.process.stdout], [], [], TIMEOUT_S)
        check(bool(ready), "padsim printed a line in time")
        return self.process.stdout.readline().rstrip("\n")

    def command(self, text):
        self.process.stdin.write(text + "\n")
        self.process.stdin.flush()

    def frame(self, deadline):
        """The next whole frame, or None at the deadline. STATUS frames are kept in `statuses`."""
        while True:
            start = self.buffer.find(bytes([SOF]))
            if start >= 0 and len(self.buffer) - start >= 6:
                length = struct.unpack_from("<H", self.buffer, start + 4)[0]
                end = start + 6 + length + 2
                if len(self.buffer) >= end:
                    raw, self.buffer = self.buffer[start:end], self.buffer[end:]
                    check(crc16_modbus(raw[1:-2]) == struct.unpack("<H", raw[-2:])[0], "frame CRC")
                    frame = (raw[2], raw[3], raw[6:-2])
                    if frame[0] == STATUS:
                        self.statuses.append(frame[2])
                    return frame
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            ready, _, _ = select.select([self.fd], [], [], left)
            if ready:
                self.buffer += os.read(self.fd, 4096)

    def ask(self, frame_type, payload=b""):
        frame_id, self.next_id = self.next_id, self.next_id % 255 + 1
        os.write(self.fd, encode(frame_type, frame_id, payload))
        deadline = time.monotonic() + TIMEOUT_S
        while (frame := self.frame(deadline)) is not None:
            if frame[1] == frame_id and frame[0] != STATUS:
                return frame
        fail(f"no reply to type {frame_type:#04x}")

    def wait_status(self, obs_state=None, wifi_state=None):
        deadline = time.monotonic() + TIMEOUT_S
        while True:
            for status in self.statuses:
                if (obs_state is None or status[0] == obs_state) and (
                    wifi_state is None or status[1] == wifi_state
                ):
                    return status
            self.statuses.clear()
            if self.frame(deadline) is None:
                fail(f"no STATUS with obs {obs_state} and wifi {wifi_state}")

    def wait_frame(self, frame_type):
        deadline = time.monotonic() + TIMEOUT_S
        while (frame := self.frame(deadline)) is not None:
            if frame[0] == frame_type:
                return frame
        fail(f"no frame of type {frame_type:#04x}")

    def send_document(self, doc, base_seq):
        """CFG_BEGIN and the chunks of `doc`; CFG_COMMIT is the caller's."""
        reply = self.ask(CFG_BEGIN, struct.pack("<IHIB", base_seq, len(doc), zlib.crc32(doc), 0))
        check(reply[2][0] == RESULT_OK, "CFG_BEGIN ok")
        for offset in range(0, len(doc), CHUNK_MAX):
            reply = self.ask(CFG_CHUNK, struct.pack("<H", offset) + doc[offset : offset + CHUNK_MAX])
            check(reply[2][0] == RESULT_OK, "CFG_CHUNK ok")

    def read_document(self):
        doc, seq, total = b"", None, None
        while total is None or len(doc) < total:
            reply = self.ask(CFG_READ, struct.pack("<HB", len(doc), READ_MAX))
            check(reply[0] == CFG_DATA, "CFG_READ gives CFG_DATA")
            seq, total, offset = struct.unpack_from("<IHH", reply[2])
            check(offset == len(doc), "CFG_DATA offset")
            doc += reply[2][8:]
            if total == 0:
                break
        return seq, doc

    def close(self):
        """Ends a live padsim through end of stdin: it must exit 0 with no sanitizer report."""
        os.close(self.fd)
        if self.process.poll() is None:
            self.process.stdin.close()
            check(self.process.wait(TIMEOUT_S) == 0, "padsim exits 0 at end of stdin")
            errors = self.process.stderr.read()
            check("runtime error" not in errors and "Sanitizer" not in errors, f"sanitizers: {errors}")
        self.process.stdout.close()
        self.process.stderr.close()


def check(condition, what):
    if not condition:
        fail(what)


def fail(what):
    print(f"padsim smoke: FAIL: {what}", file=sys.stderr)
    sys.exit(1)


def document(seq):
    """valid_minimal.json with its own `seq` member, so each write is a different document."""
    return MINIMAL_DOC.read_bytes().replace(b'"seq":0', f'"seq":{seq}'.encode())


# An unbound key draws its outline, so its first and last columns are lit and its middle is black.
# On the strip a column lands right only when every CASET carries the panel's column offset.
STRIP_KEY = b'{"widgets":[{"kind":"key","x":0,"y":0,"w":142,"h":48,"key":0}]}'


def strip_pixel(frame, x, y):
    return struct.unpack_from(">H", frame, (y * 142 + x) * 2)[0]


def start_fake_obs(log):
    obs = subprocess.Popen(
        [sys.executable, str(FAKE_OBS), "--log", str(log)], stdout=subprocess.PIPE, text=True
    )
    first = obs.stdout.readline().split()
    check(first[:1] == ["listening"], "fake_obs listens")
    return obs, int(first[1])


def check_info_and_obs(padsim, tmp):
    obs, port = start_fake_obs(tmp / "requests.log")
    pad = Pad(padsim, tmp / "obs.nor", obs_port=port)
    try:
        info = pad.ask(INFO_GET)
        check(info[0] == INFO and info[2][0] == 2, "INFO, proto 2")
        check(info[2][8:11] == bytes([9, 4, 3]), "INFO counts 9 keys, 4 buttons, 3 knobs")
        check(info[2][34:] == b"padsim", "INFO fw version")
        pad.wait_status(obs_state=OBS_UP, wifi_state=WIFI_UP)
        print("padsim smoke: INFO answered, OBS up over TCP")
        pad.command("wifi bad_key")
        status = pad.wait_status(wifi_state=WIFI_BAD_KEY)
        check(status[2:] == bytes(5), "bad-key STATUS has RSSI 0 and IP 0.0.0.0")
        print("padsim smoke: wifi bad_key gives STATUS wifi_state 2")
        doc = document(1).replace(b'"strip_display":{"widgets":[]}', b'"strip_display":' + STRIP_KEY)
        pad.send_document(doc, 0)
        check(pad.ask(CFG_COMMIT)[2] == bytes([RESULT_OK, 1, 0, 0, 0]), "commit with a strip key, seq 1")
        pad.command("key 4")
        check(pad.wait_frame(INPUT)[2] == bytes([1, 4, 1]), "key 4 press gives INPUT")
        pad.command("knob 0 -2")
        pad.command("wait-idle")
        check(pad.line() == "idle", "wait-idle answers idle")
        pad.command(f"dump {tmp}")
        dumped = pad.line()
        check(dumped == f"dumped {tmp} bad_windows=0 line=Wrong Wi-Fi key", f"dump reply: {dumped!r}")
        check((tmp / "main.rgb565").stat().st_size == MAIN_FRAME_BYTES, "main.rgb565 size")
        strip = (tmp / "strip.rgb565").read_bytes()
        check(len(strip) == STRIP_FRAME_BYTES, "strip.rgb565 size")
        lit = [strip_pixel(strip, x, 24) != 0 for x in (0, 70, 141)]
        check(lit == [True, False, True], f"the strip key outline sits on columns 0 and 141: {lit}")
        pad.command("knob 7 push")
        check(pad.line() == "error knob 7 push", "a bad command gets error")
        print("padsim smoke: key, knob, wait-idle and dump answer")
    finally:
        pad.close()
        obs.terminate()
        obs.wait(TIMEOUT_S)
    log = (tmp / "requests.log").read_text(encoding="utf-8")
    check('"requestType":"GetSceneList"' in log, "padsim read the scenes from fake_obs")


def check_cut(padsim, tmp):
    """A commit is two program calls, body then header: the second commit dies at its body."""
    nor = tmp / "cut.nor"
    pad = Pad(padsim, nor, cut_after=3)
    pad.send_document(document(1), 0)
    check(pad.ask(CFG_COMMIT)[2][0] == RESULT_OK, "the first commit is ok")
    pad.send_document(document(2), 1)
    os.write(pad.fd, encode(CFG_COMMIT, 0xFF))
    check(pad.process.wait(TIMEOUT_S) == -9, "the --cut-after 3 run is killed")
    check("cut at program call 3" in pad.process.stderr.read(), "it dies at program call 3")
    pad.close()
    image = hashlib.sha256(nor.read_bytes()).hexdigest()
    print("padsim smoke: --cut-after 3 killed padsim at program call 3")
    pad = Pad(padsim, nor)
    try:
        check(pad.read_document() == (1, document(1)), "the next start serves the old document, seq 1")
    finally:
        pad.close()
    check(hashlib.sha256(nor.read_bytes()).hexdigest() == image, "the next start wrote no flash")
    print("padsim smoke: the next start read the same NOR image")


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().split("\n\n")[1].strip(), file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="padsim-smoke-") as tmp:
        check_info_and_obs(argv[1], Path(tmp))
        check_cut(argv[1], Path(tmp))
    print("padsim smoke: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
