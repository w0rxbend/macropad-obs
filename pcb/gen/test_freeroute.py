# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Tests of freeroute.py: the jar is taken only at its sha256, and the router runs offline on the outer
layers. Plain Python, no network, no Docker: `just pcb-test`."""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from pathlib import Path

import freeroute
import sexpr

GOOD = b"the jar"
GOOD_SHA256 = hashlib.sha256(GOOD).hexdigest()


class Opener:
    """Stands in for urllib's urlopen: serves `body`, counts the calls."""

    def __init__(self, body: bytes) -> None:
        self.body, self.calls = body, 0

    def __call__(self, url: str, timeout: float) -> io.BytesIO:
        self.calls += 1
        return io.BytesIO(self.body)


class FetchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.jar = Path(self.folder.name) / "cache" / "freerouting.jar"

    def tearDown(self) -> None:
        self.folder.cleanup()

    def test_a_download_at_the_pinned_sha256_lands_in_the_cache(self) -> None:
        opener = Opener(GOOD)
        self.assertEqual(freeroute.fetch(self.jar, GOOD_SHA256, opener), self.jar)
        self.assertEqual(self.jar.read_bytes(), GOOD)
        freeroute.fetch(self.jar, GOOD_SHA256, opener)
        self.assertEqual(opener.calls, 1, "a cached jar at the right sha256 is not fetched again")

    def test_a_download_with_another_sha256_stops_the_run_and_leaves_nothing(self) -> None:
        with self.assertRaises(freeroute.WrongDigest):
            freeroute.fetch(self.jar, GOOD_SHA256, Opener(b"something else"))
        self.assertEqual(list(self.jar.parent.iterdir()), [])

    def test_a_cached_jar_with_another_sha256_stops_the_run(self) -> None:
        self.jar.parent.mkdir(parents=True)
        self.jar.write_bytes(b"tampered")
        opener = Opener(GOOD)
        with self.assertRaises(freeroute.WrongDigest):
            freeroute.fetch(self.jar, GOOD_SHA256, opener)
        self.assertEqual(opener.calls, 0)
        self.assertEqual(self.jar.read_bytes(), b"tampered", "the run stops; it does not replace the file")

    def test_the_pinned_jar_is_release_2_5_0(self) -> None:
        self.assertEqual(freeroute.SHA256, "f6f51bb02245e8e717f9359bd260cc9c5c0b1bc0acc8b7cb2cd5b8ffeb5de3c7")
        self.assertTrue(freeroute.URL.endswith("/v2.5.0/freerouting-2.5.0.jar"), freeroute.URL)


class CommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.command = freeroute.command(1000, 1000)

    def test_the_router_runs_in_the_pinned_image_without_a_network(self) -> None:
        self.assertEqual(self.command[:2], ["docker", "run"])
        self.assertIn("--network", self.command)
        self.assertEqual(self.command[self.command.index("--network") + 1], "none")
        self.assertIn("eclipse-temurin:25-jre", self.command)
        self.assertIn("1000:1000", self.command)

    def test_the_router_reads_the_outer_rules_and_keeps_its_width(self) -> None:
        def value(flag: str) -> str:
            return self.command[self.command.index(flag) + 1]
        self.assertEqual(value("-de"), str(freeroute.DSN_PATH))
        self.assertEqual(value("-do"), str(freeroute.SES_PATH))
        self.assertEqual(value("-dr"), str(freeroute.RULES_PATH))
        self.assertEqual(value("-jar"), str(freeroute.JAR_PATH))
        self.assertIn("--router.automatic_neckdown=false", self.command)  # report 09 pitfall 2
        self.assertIn("--router.fanout.enabled=false", self.command)  # the pre-pass necks down anyway
        self.assertIn("--router.copper_to_edge_clearance_um=300", self.command)  # KiCad's edge rule
        self.assertIn("--gui.enabled=false", self.command)


class OuterRulesTest(unittest.TestCase):
    def test_the_inner_layers_are_closed_to_the_router(self) -> None:
        rules = sexpr.parse(freeroute.RULES_PATH.read_text())
        self.assertEqual(rules[1:3], ["PCB", freeroute.DSN_PATH.stem], "Freerouting skips rules of another design")
        settings = [node for node in rules if isinstance(node, list) and node[0] == "autoroute_settings"]
        self.assertEqual(len(settings), 1)
        active = {node[1]: node[2][1] for node in settings[0] if isinstance(node, list) and node[0] == "layer_rule"}
        self.assertEqual(active, {"F.Cu": "on", "In1.Cu": "off", "In2.Cu": "off", "B.Cu": "on"})


if __name__ == "__main__":
    unittest.main()
