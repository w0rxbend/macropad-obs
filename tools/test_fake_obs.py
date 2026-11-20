#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""fake_obs self-test: a Python client drives the handshake, the requests and the request log.
The client below is written apart from the server's code, so one side cannot hide the other's
framing mistake."""

import asyncio
import base64
import hashlib
import io
import json
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_obs

# RFC 6455 section 1.3: this key must be answered with this accept value.
RFC_6455_SAMPLE_KEY = "dGhlIHNhbXBsZSBub25jZQ=="
RFC_6455_SAMPLE_ACCEPT = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
# docs/research/05-obs-websocket.md section 3. A published example, not a real password.
R05_PASSWORD = "supersecretpassword"
R05_SALT = "lM1GncleQOaCu9lT1yeUZhFYnqhsLLP1G5lAGo3ixaI="
R05_CHALLENGE = "+IxH4CnCiqpX1rM9scsNynZzbOe4KhDeYcTNS3PDaeY="
R05_AUTH = "1Ct943GAT+6YQUUX47Ia/ncufilbe6+oD6lY+5kaCu4="
TEXT, CLOSE, PING, PONG = 0x1, 0x8, 0x9, 0xA
FINAL = 0x80
MASKED = 0x80
LENGTH_IS_64_BIT = 127
REPLY_WAIT_S = 5.0
THROTTLE_BYTES_PER_S = 1_000_000
FAKE_OBS = Path(fake_obs.__file__)
SPEC = FAKE_OBS.parent.parent / "docs" / "spec" / "spec-v2.md"
GET_SCENE_LIST = {"op": 6, "d": {"requestType": "GetSceneList", "requestId": "r1"}}


def fixture_state():
    return json.loads(fake_obs.DEFAULT_STATE.read_text(encoding="utf-8"))


def criterion_4c_log_lines():
    """The request log lines that spec 13 criterion 4c quotes, in its order."""
    spec = SPEC.read_text(encoding="utf-8")
    criterion = spec[spec.index("**4c. Input remap round trip") : spec.index("5. Unplug during")]
    return re.findall(r"`(\{\"requestType\"[^`]*)`", criterion)


def client_auth(password, hello):
    """The Identify `authentication` string for a Hello, computed without the server's code."""

    def base64_sha256(text):
        return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()

    challenge = hello["d"]["authentication"]
    return base64_sha256(base64_sha256(password + challenge["salt"]) + challenge["challenge"])


class Client:
    """A small RFC 6455 client on asyncio streams. It speaks obs-websocket JSON."""

    def __init__(self, reader, writer, response_headers):
        self.reader, self.writer, self.response_headers = reader, writer, response_headers

    @classmethod
    async def connect(cls, port, key=RFC_6455_SAMPLE_KEY):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
            "Sec-WebSocket-Protocol: obswebsocket.json\r\n\r\n".encode()
        )
        status, *lines = (await reader.readuntil(b"\r\n\r\n")).decode().split("\r\n")
        if not status.startswith("HTTP/1.1 101"):
            raise AssertionError(status)
        headers = dict(line.split(": ", 1) for line in lines if line)
        return cls(reader, writer, {name.lower(): value for name, value in headers.items()})

    def send_frame(self, first_byte, payload, mask=b"\x11\x22\x33\x44"):
        """Writes one frame. mask=None sends it unmasked, which RFC 6455 forbids a client."""
        mask_bit = MASKED if mask else 0
        if len(payload) <= 125:
            header = bytes([first_byte, mask_bit | len(payload)])
        else:
            header = bytes([first_byte, mask_bit | 126]) + struct.pack("!H", len(payload))
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload)) if mask else payload
        self.writer.write(header + (mask or b"") + masked)

    def send(self, message):
        self.send_frame(FINAL | TEXT, json.dumps(message).encode())

    async def read_frame(self):
        """The next frame as (first byte, 7-bit length field, payload). A server frame has no mask."""
        first_byte, length_field = await self.reader.readexactly(2)
        length = length_field
        if length_field == 126:
            (length,) = struct.unpack("!H", await self.reader.readexactly(2))
        elif length_field == 127:
            (length,) = struct.unpack("!Q", await self.reader.readexactly(8))
        return first_byte, length_field, await self.reader.readexactly(length)

    async def receive_text(self):
        async with asyncio.timeout(REPLY_WAIT_S):
            first_byte, _, payload = await self.read_frame()
        if first_byte != FINAL | TEXT:
            raise AssertionError(f"wanted one whole text frame, got {first_byte:#x} {payload!r}")
        return payload.decode()

    async def receive(self):
        return json.loads(await self.receive_text())

    async def receive_close_code(self):
        async with asyncio.timeout(REPLY_WAIT_S):
            first_byte, _, payload = await self.read_frame()
        if first_byte != FINAL | CLOSE:
            raise AssertionError(f"wanted a close frame, got {first_byte:#x} {payload!r}")
        return struct.unpack("!H", payload[:2])[0]

    async def identify(self, password=None):
        """Reads Hello and sends Identify. Returns the Hello; the server's answer is still unread."""
        hello = await self.receive()
        identify = {"rpcVersion": 1, "eventSubscriptions": 1118}
        if password is not None:
            identify["authentication"] = client_auth(password, hello)
        self.send({"op": 1, "d": identify})
        return hello

    async def request(self, request_type, request_data=None, request_id="r1"):
        """Sends one request and returns the `d` of its response."""
        message = {"requestType": request_type, "requestId": request_id}
        if request_data is not None:
            message["requestData"] = request_data
        self.send({"op": 6, "d": message})
        return (await self.receive())["d"]

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()


async def stop(server):
    server.close()
    await server.wait_closed()


class FakeObsCase(unittest.IsolatedAsyncioTestCase):
    """Starts a fake OBS on a free loopback port and connects clients to it."""

    async def serve(self, state=None, **options):
        self.log = io.StringIO()
        studio = fake_obs.Studio(state or fixture_state())
        server = await fake_obs.FakeObs(studio, self.log, fake_obs.Options(**options)).start(0)
        self.addAsyncCleanup(stop, server)
        self.port = server.sockets[0].getsockname()[1]

    async def connect(self, **arguments):
        client = await Client.connect(self.port, **arguments)
        self.addAsyncCleanup(client.close)
        return client

    async def identified_client(self, password=None):
        client = await self.connect()
        await client.identify(password)
        self.assertEqual(await client.receive_text(), '{"d":{"negotiatedRpcVersion":1},"op":2}')
        return client

    def log_lines(self):
        return self.log.getvalue().splitlines()


class UpgradeTest(FakeObsCase):
    async def test_upgrade_answers_the_rfc_6455_sample_key(self):
        await self.serve()
        client = await self.connect(key=RFC_6455_SAMPLE_KEY)
        self.assertEqual(client.response_headers["sec-websocket-accept"], RFC_6455_SAMPLE_ACCEPT)

    async def test_upgrade_picks_the_json_subprotocol(self):
        await self.serve()
        client = await self.connect()
        self.assertEqual(client.response_headers["sec-websocket-protocol"], "obswebsocket.json")

    async def test_plain_http_request_gets_400(self):
        await self.serve()
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        self.addAsyncCleanup(writer.wait_closed)
        self.addCleanup(writer.close)
        writer.write(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        self.assertTrue((await reader.read()).startswith(b"HTTP/1.1 400 "))


class HelloTest(FakeObsCase):
    async def test_hello_with_auth_off_is_the_sorted_5_7_6_message(self):
        await self.serve()
        client = await self.connect()
        self.assertEqual(
            await client.receive_text(),
            '{"d":{"obsStudioVersion":"33.0.1","obsWebSocketVersion":"5.7.6","rpcVersion":1},"op":0}',
        )

    async def test_hello_with_auth_on_carries_a_44_byte_salt_and_challenge(self):
        await self.serve(password=R05_PASSWORD)
        client = await self.connect()
        authentication = (await client.receive())["d"]["authentication"]
        self.assertEqual(sorted(authentication), ["challenge", "salt"])
        self.assertEqual([len(base64.b64decode(text)) for text in authentication.values()], [32, 32])

    async def test_salt_stays_and_challenge_changes_between_connections(self):
        await self.serve(password=R05_PASSWORD)
        first = (await (await self.connect()).receive())["d"]["authentication"]
        second = (await (await self.connect()).receive())["d"]["authentication"]
        self.assertEqual(first["salt"], second["salt"])
        self.assertNotEqual(first["challenge"], second["challenge"])

    async def test_hello_of_an_older_server_reports_it_and_has_no_obs_studio_version(self):
        await self.serve(obs_websocket_version="5.3.4")
        client = await self.connect()
        self.assertEqual(
            (await client.receive())["d"], {"obsWebSocketVersion": "5.3.4", "rpcVersion": 1}
        )


class IdentifyTest(FakeObsCase):
    def test_auth_response_matches_the_r05_vector(self):
        self.assertEqual(fake_obs.auth_response(R05_PASSWORD, R05_SALT, R05_CHALLENGE), R05_AUTH)

    async def test_identify_with_auth_off_is_identified(self):
        await self.serve()
        await self.identified_client()

    async def test_identify_with_the_password_is_identified(self):
        await self.serve(password=R05_PASSWORD)
        await self.identified_client(password=R05_PASSWORD)

    async def test_wrong_password_closes_4009(self):
        await self.serve(password=R05_PASSWORD)
        client = await self.connect()
        await client.identify(password="not the password")
        self.assertEqual(await client.receive_close_code(), 4009)

    async def test_missing_authentication_closes_4009(self):
        await self.serve(password=R05_PASSWORD)
        client = await self.connect()
        await client.identify(password=None)
        self.assertEqual(await client.receive_close_code(), 4009)

    async def test_rpc_version_2_closes_4010(self):
        await self.serve()
        client = await self.connect()
        await client.receive()
        client.send({"op": 1, "d": {"rpcVersion": 2}})
        self.assertEqual(await client.receive_close_code(), 4010)

    async def test_request_before_identify_closes_4007(self):
        await self.serve()
        client = await self.connect()
        await client.receive()
        client.send({"op": 6, "d": {"requestType": "GetSceneList", "requestId": "r1"}})
        self.assertEqual(await client.receive_close_code(), 4007)

    async def test_second_identify_closes_4008(self):
        await self.serve()
        client = await self.identified_client()
        client.send({"op": 1, "d": {"rpcVersion": 1}})
        self.assertEqual(await client.receive_close_code(), 4008)

    async def test_reidentify_is_answered_with_identified(self):
        await self.serve()
        client = await self.identified_client()
        client.send({"op": 3, "d": {"eventSubscriptions": 66654}})
        self.assertEqual(await client.receive(), {"d": {"negotiatedRpcVersion": 1}, "op": 2})

    async def test_unknown_opcode_closes_4006(self):
        await self.serve()
        client = await self.identified_client()
        client.send({"op": 8, "d": {}})
        self.assertEqual(await client.receive_close_code(), 4006)

    async def test_message_that_is_not_json_closes_4002(self):
        await self.serve()
        client = await self.identified_client()
        client.send_frame(FINAL | TEXT, b"{not json")
        self.assertEqual(await client.receive_close_code(), 4002)


class CloseModeTest(FakeObsCase):
    async def test_close_mode_4009_and_4010_refuse_a_good_identify(self):
        for code in (4009, 4010):
            with self.subTest(code=code):
                await self.serve(close_code=code)
                client = await self.connect()
                await client.identify()
                self.assertEqual(await client.receive_close_code(), code)

    async def test_close_mode_4011_kicks_right_after_identified(self):
        await self.serve(close_code=4011)
        client = await self.identified_client()
        self.assertEqual(await client.receive_close_code(), 4011)


class FrameTest(FakeObsCase):
    async def test_ping_gets_a_pong_with_the_same_payload(self):
        await self.serve()
        client = await self.identified_client()
        client.send_frame(FINAL | PING, b"still there")
        self.assertEqual(await client.read_frame(), (FINAL | PONG, 11, b"still there"))

    async def test_unmasked_frame_closes_1002(self):
        await self.serve()
        client = await self.identified_client()
        client.send_frame(FINAL | TEXT, b"{}", mask=None)
        self.assertEqual(await client.receive_close_code(), 1002)

    async def test_client_close_is_echoed(self):
        await self.serve()
        client = await self.identified_client()
        client.send_frame(FINAL | CLOSE, struct.pack("!H", 1000))
        self.assertEqual(await client.receive_close_code(), 1000)

    async def test_request_split_in_two_fragments_is_read_as_one_message(self):
        await self.serve()
        client = await self.identified_client()
        request = b'{"op":6,"d":{"requestType":"GetStudioModeEnabled","requestId":"r1"}}'
        client.send_frame(TEXT, request[:20])
        client.send_frame(FINAL, request[20:])
        self.assertEqual((await client.receive())["d"]["requestId"], "r1")


class RequestTest(FakeObsCase):
    """Requests against tools/fixtures/ui_state.json."""

    async def asyncSetUp(self):
        await self.serve()
        self.client = await self.identified_client()

    async def volume_db(self, input_uuid):
        reply = await self.client.request("GetInputVolume", {"inputUuid": input_uuid})
        return reply["responseData"]["inputVolumeDb"]

    async def test_response_is_the_sorted_message_obs_sends(self):
        self.client.send({"op": 6, "d": {"requestType": "ToggleRecord", "requestId": "r7"}})
        self.assertEqual(
            await self.client.receive_text(),
            '{"d":{"requestId":"r7","requestStatus":{"code":100,"result":true},'
            '"requestType":"ToggleRecord","responseData":{"outputActive":true}},"op":7}',
        )

    async def test_get_scene_list_serves_the_state_file(self):
        reply = await self.client.request("GetSceneList")
        self.assertEqual(
            reply["responseData"],
            {
                "currentPreviewSceneName": "Screen",
                "currentPreviewSceneUuid": "S_B",
                "currentProgramSceneName": "Camera",
                "currentProgramSceneUuid": "S_A",
                "scenes": [
                    {"sceneIndex": 0, "sceneName": "Camera", "sceneUuid": "S_A"},
                    {"sceneIndex": 1, "sceneName": "Screen", "sceneUuid": "S_B"},
                    {"sceneIndex": 2, "sceneName": "Break", "sceneUuid": "S_C"},
                ],
            },
        )

    async def test_set_current_program_scene_moves_the_program_scene(self):
        reply = await self.client.request("SetCurrentProgramScene", {"sceneUuid": "S_C"})
        self.assertEqual(reply["requestStatus"], {"code": 100, "result": True})
        self.assertNotIn("responseData", reply)
        scenes = (await self.client.request("GetSceneList"))["responseData"]
        self.assertEqual(
            (scenes["currentProgramSceneUuid"], scenes["currentProgramSceneName"]), ("S_C", "Break")
        )

    async def test_get_input_list_has_the_three_inputs_and_no_volume_or_mute(self):
        inputs = (await self.client.request("GetInputList"))["responseData"]["inputs"]
        self.assertEqual(
            [(entry["inputUuid"], entry["inputName"]) for entry in inputs],
            [("U_A", "Mic"), ("U_B", "Desktop"), ("U_C", "Music")],
        )
        for entry in inputs:
            self.assertEqual(
                sorted(entry),
                ["inputKind", "inputKindCaps", "inputName", "inputUuid", "unversionedInputKind"],
            )
            self.assertTrue(entry["inputKindCaps"] & 2, "bit 1 marks an audio input (R05 section 5)")

    async def test_get_input_volume_of_u_b_starts_at_minus_20_db(self):
        reply = await self.client.request("GetInputVolume", {"inputUuid": "U_B"})
        self.assertEqual(reply["responseData"]["inputVolumeDb"], -20)
        self.assertAlmostEqual(reply["responseData"]["inputVolumeMul"], 0.1)

    async def test_set_input_volume_changes_what_get_input_volume_returns(self):
        reply = await self.client.request("SetInputVolume", {"inputUuid": "U_B", "inputVolumeDb": -18})
        self.assertEqual(reply["requestStatus"], {"code": 100, "result": True})
        self.assertEqual(await self.volume_db("U_B"), -18)
        self.assertEqual(await self.volume_db("U_A"), -6)

    async def test_set_input_volume_takes_both_ends_of_the_range(self):
        for decibel in (-100, 26):
            with self.subTest(decibel=decibel):
                await self.client.request("SetInputVolume", {"inputUuid": "U_A", "inputVolumeDb": decibel})
                self.assertEqual(await self.volume_db("U_A"), decibel)

    async def test_silence_reads_as_a_multiplier_of_0(self):
        await self.client.request("SetInputVolume", {"inputUuid": "U_A", "inputVolumeDb": -100})
        reply = await self.client.request("GetInputVolume", {"inputUuid": "U_A"})
        self.assertEqual(reply["responseData"]["inputVolumeMul"], 0)

    async def test_get_input_mute_serves_the_state_file(self):
        muted = {}
        for input_uuid in ("U_A", "U_C"):
            reply = await self.client.request("GetInputMute", {"inputUuid": input_uuid})
            muted[input_uuid] = reply["responseData"]
        self.assertEqual(muted, {"U_A": {"inputMuted": False}, "U_C": {"inputMuted": True}})

    async def test_toggle_input_mute_flips_the_mute_and_returns_it(self):
        first = await self.client.request("ToggleInputMute", {"inputUuid": "U_B"})
        second = await self.client.request("ToggleInputMute", {"inputUuid": "U_B"})
        self.assertEqual(
            [first["responseData"], second["responseData"]], [{"inputMuted": True}, {"inputMuted": False}]
        )

    async def test_set_input_mute_changes_what_get_input_mute_returns(self):
        await self.client.request("SetInputMute", {"inputUuid": "U_A", "inputMuted": True})
        reply = await self.client.request("GetInputMute", {"inputUuid": "U_A"})
        self.assertEqual(reply["responseData"], {"inputMuted": True})

    async def test_record_is_off_until_toggle_record(self):
        before = (await self.client.request("GetRecordStatus"))["responseData"]
        toggled = (await self.client.request("ToggleRecord"))["responseData"]
        after = (await self.client.request("GetRecordStatus"))["responseData"]
        self.assertEqual(
            before,
            {
                "outputActive": False,
                "outputBytes": 0,
                "outputDuration": 0,
                "outputPaused": False,
                "outputTimecode": "00:00:00.000",
            },
        )
        self.assertEqual((toggled, after["outputActive"]), ({"outputActive": True}, True))

    async def test_stream_is_off_until_toggle_stream(self):
        before = (await self.client.request("GetStreamStatus"))["responseData"]
        toggled = (await self.client.request("ToggleStream"))["responseData"]
        after = (await self.client.request("GetStreamStatus"))["responseData"]
        self.assertEqual(
            before,
            {
                "outputActive": False,
                "outputBytes": 0,
                "outputCongestion": 0,
                "outputDuration": 0,
                "outputReconnecting": False,
                "outputSkippedFrames": 0,
                "outputTimecode": "00:00:00.000",
                "outputTotalFrames": 0,
            },
        )
        self.assertEqual((toggled, after["outputActive"]), ({"outputActive": True}, True))

    async def test_toggle_record_leaves_the_stream_off(self):
        await self.client.request("ToggleRecord")
        stream = (await self.client.request("GetStreamStatus"))["responseData"]
        self.assertFalse(stream["outputActive"])

    async def test_get_studio_mode_enabled_serves_the_state_file(self):
        reply = await self.client.request("GetStudioModeEnabled")
        self.assertEqual(reply["responseData"], {"studioModeEnabled": True})

    async def test_refused_request_gets_its_status_code_and_a_comment(self):
        refused = (
            ("NoSuchRequest", None, 204),
            ("GetSceneList", [1], 401),
            ("GetInputVolume", {}, 300),
            ("GetInputVolume", {"inputUuid": 7}, 401),
            ("GetInputVolume", {"inputUuid": "U_Z"}, 600),
            ("SetInputVolume", {"inputUuid": "U_B"}, 300),
            ("SetInputVolume", {"inputUuid": "U_B", "inputVolumeDb": "loud"}, 401),
            ("SetInputVolume", {"inputUuid": "U_B", "inputVolumeDb": True}, 401),
            ("SetInputVolume", {"inputUuid": "U_B", "inputVolumeDb": -100.5}, 402),
            ("SetInputVolume", {"inputUuid": "U_B", "inputVolumeDb": 26.5}, 402),
            ("SetInputMute", {"inputUuid": "U_B"}, 300),
            ("SetInputMute", {"inputUuid": "U_B", "inputMuted": 1}, 401),
            ("ToggleInputMute", {"inputUuid": "U_Z"}, 600),
            ("SetCurrentProgramScene", {}, 300),
            ("SetCurrentProgramScene", {"sceneUuid": "S_Z"}, 600),
        )
        for request_type, request_data, code in refused:
            with self.subTest(request_type=request_type, request_data=request_data):
                status = (await self.client.request(request_type, request_data))["requestStatus"]
                self.assertEqual((status["code"], status["result"]), (code, False))
                self.assertIsInstance(status["comment"], str)

    async def test_refused_request_changes_no_state(self):
        await self.client.request("SetInputVolume", {"inputUuid": "U_B", "inputVolumeDb": 27})
        await self.client.request("SetInputMute", {"inputUuid": "U_B", "inputMuted": "yes"})
        await self.client.request("SetCurrentProgramScene", {"sceneUuid": "S_Z"})
        mute = (await self.client.request("GetInputMute", {"inputUuid": "U_B"}))["responseData"]
        scenes = (await self.client.request("GetSceneList"))["responseData"]
        self.assertEqual(await self.volume_db("U_B"), -20)
        self.assertEqual(mute, {"inputMuted": False})
        self.assertEqual(scenes["currentProgramSceneUuid"], "S_A")

    async def test_request_without_a_request_id_closes_4003(self):
        self.client.send({"op": 6, "d": {"requestType": "GetSceneList"}})
        self.assertEqual(await self.client.receive_close_code(), 4003)


class StateFileTest(unittest.TestCase):
    def test_state_whose_program_scene_is_not_in_scenes_is_refused(self):
        state = fixture_state() | {"currentProgramSceneUuid": "S_Z"}
        with self.assertRaises(ValueError):
            fake_obs.Studio(state)

    def test_state_file_matches_criterion_4c_and_gap_3(self):
        state = fixture_state()
        volumes = {entry["inputUuid"]: entry["inputVolumeDb"] for entry in state["inputs"]}
        self.assertEqual(sorted(volumes), ["U_A", "U_B", "U_C"])
        self.assertEqual(volumes["U_B"], -20)
        self.assertEqual((state["recordActive"], state["streamActive"]), (False, False))


class RequestLogTest(FakeObsCase):
    async def asyncSetUp(self):
        await self.serve()
        self.client = await self.identified_client()

    async def test_log_holds_the_three_lines_of_criterion_4c_in_order(self):
        quoted = criterion_4c_log_lines()
        self.assertEqual(len(quoted), 3, "spec 13 criterion 4c quotes three requests")
        for number, line in enumerate(quoted):
            request = json.loads(line)
            await self.client.request(
                request["requestType"], request.get("requestData"), request_id=f"r{number}"
            )
        self.assertEqual(self.log_lines(), quoted)

    async def test_log_line_sorts_request_data_and_drops_the_request_id(self):
        await self.client.request(
            "SetInputVolume", {"inputVolumeDb": -18, "inputUuid": "U_B"}, request_id="6b3f"
        )
        self.assertEqual(
            self.log_lines(),
            ['{"requestType":"SetInputVolume","requestData":{"inputUuid":"U_B","inputVolumeDb":-18}}'],
        )

    async def test_log_line_leaves_out_an_empty_request_data(self):
        await self.client.request("ToggleRecord", {})
        self.assertEqual(self.log_lines(), ['{"requestType":"ToggleRecord"}'])

    async def test_log_keeps_a_request_that_is_refused(self):
        await self.client.request("TriggerStudioModeTransition")
        self.assertEqual(self.log_lines(), ['{"requestType":"TriggerStudioModeTransition"}'])

    async def test_log_keeps_a_name_that_is_not_ascii(self):
        await self.client.request("GetInputMute", {"inputUuid": "Мікрофон"})
        self.assertEqual(
            self.log_lines(), ['{"requestType":"GetInputMute","requestData":{"inputUuid":"Мікрофон"}}']
        )


class RequestLogSecretTest(FakeObsCase):
    async def test_log_holds_no_identify_and_nothing_made_from_the_password(self):
        await self.serve(password=R05_PASSWORD)
        client = await self.connect()
        hello = await client.identify(R05_PASSWORD)
        await client.receive()
        await client.request("ToggleRecord")
        log = self.log.getvalue()
        self.assertEqual(log, '{"requestType":"ToggleRecord"}\n')
        for secret in (R05_PASSWORD, client_auth(R05_PASSWORD, hello), *hello["d"]["authentication"].values()):
            self.assertNotIn(secret, log)


class SceneCollectionTest(FakeObsCase):
    async def scene_list_frame(self, **options):
        """The GetSceneList reply of a 500-scene server as (first byte, length field, payload)."""
        await self.serve(state=fake_obs.with_scene_collection(fixture_state(), 500), **options)
        client = await self.identified_client()
        client.send(GET_SCENE_LIST)
        return await client.read_frame()

    async def test_500_scenes_come_back_as_one_frame_of_about_75_kb(self):
        first_byte, length_field, payload = await self.scene_list_frame()
        self.assertEqual((first_byte, length_field), (FINAL | TEXT, LENGTH_IS_64_BIT))
        self.assertEqual(len(json.loads(payload)["d"]["responseData"]["scenes"]), 500)
        self.assertTrue(74_000 <= len(payload) <= 76_000, len(payload))

    async def test_each_scene_has_its_own_36_byte_uuid_and_a_64_byte_name(self):
        _, _, payload = await self.scene_list_frame()
        scenes = json.loads(payload)["d"]["responseData"]["scenes"]
        self.assertEqual({len(scene["sceneUuid"]) for scene in scenes}, {36})
        self.assertEqual({len(scene["sceneName"].encode()) for scene in scenes}, {64})
        self.assertEqual(len({scene["sceneUuid"] for scene in scenes}), 500)
        self.assertEqual(len({scene["sceneName"] for scene in scenes}), 500)

    async def test_program_and_preview_are_scenes_of_the_collection(self):
        _, _, payload = await self.scene_list_frame()
        reply = json.loads(payload)["d"]["responseData"]
        uuids = [scene["sceneUuid"] for scene in reply["scenes"]]
        self.assertEqual(
            (reply["currentProgramSceneUuid"], reply["currentPreviewSceneUuid"]), (uuids[0], uuids[-1])
        )

    async def test_throttled_75_kb_reply_takes_its_time_and_arrives_whole(self):
        _, _, unthrottled = await self.scene_list_frame()
        clock = asyncio.get_running_loop().time
        started = clock()
        _, _, throttled = await self.scene_list_frame(throttle_bytes_per_s=THROTTLE_BYTES_PER_S)
        elapsed_s = clock() - started
        self.assertEqual(throttled, unthrottled)
        self.assertGreaterEqual(elapsed_s, 0.9 * len(throttled) / THROTTLE_BYTES_PER_S)


async def reap(process):
    if process.returncode is None:
        process.kill()
    await process.wait()


class CommandLineTest(unittest.IsolatedAsyncioTestCase):
    async def start(self, *arguments):
        """Runs tools/fake_obs.py. Returns the process and a client on the port it prints."""
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(FAKE_OBS), *arguments, stdout=asyncio.subprocess.PIPE
        )
        self.addAsyncCleanup(reap, process)
        async with asyncio.timeout(REPLY_WAIT_S):
            word, port = (await process.stdout.readline()).split()
        self.assertEqual(word, b"listening")
        client = await Client.connect(int(port))
        self.addAsyncCleanup(client.close)
        return process, client

    async def test_log_file_holds_each_request_while_the_server_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "requests.log"
            _, client = await self.start("--log", str(log), "--password", R05_PASSWORD)
            await client.identify(R05_PASSWORD)
            await client.receive()
            await client.request("ToggleRecord")
            self.assertEqual(log.read_text(encoding="utf-8"), '{"requestType":"ToggleRecord"}\n')

    async def test_without_a_log_file_the_log_goes_to_stdout(self):
        process, client = await self.start()
        await client.identify()
        await client.receive()
        await client.request("ToggleRecord")
        async with asyncio.timeout(REPLY_WAIT_S):
            self.assertEqual(await process.stdout.readline(), b'{"requestType":"ToggleRecord"}\n')

    async def test_sigterm_ends_the_run_with_exit_code_0(self):
        process, _ = await self.start()
        process.terminate()
        async with asyncio.timeout(REPLY_WAIT_S):
            self.assertEqual(await process.wait(), 0)

    async def test_version_and_close_code_flags_reach_the_server(self):
        _, client = await self.start("--obs-websocket-version", "5.3.4", "--close-code", "4011")
        hello = await client.identify()
        await client.receive()
        self.assertEqual(hello["d"], {"obsWebSocketVersion": "5.3.4", "rpcVersion": 1})
        self.assertEqual(await client.receive_close_code(), 4011)

    async def test_scenes_throttle_and_state_flags_reach_the_server(self):
        _, client = await self.start(
            "--scenes", "500", "--throttle-bytes-per-s", "4000000", "--state", str(fake_obs.DEFAULT_STATE)
        )
        await client.identify()
        await client.receive()
        client.send(GET_SCENE_LIST)
        _, _, payload = await client.read_frame()
        self.assertEqual(len(json.loads(payload)["d"]["responseData"]["scenes"]), 500)

    def test_bad_flag_value_exits_2(self):
        for arguments in (
            ("--close-code", "4012"),
            ("--obs-websocket-version", "five"),
            ("--scenes", "0"),
            ("--throttle-bytes-per-s", "-1"),
        ):
            with self.subTest(arguments=arguments):
                run = subprocess.run(
                    [sys.executable, str(FAKE_OBS), *arguments], capture_output=True, check=False
                )
                self.assertEqual(run.returncode, 2)


if __name__ == "__main__":
    unittest.main()
