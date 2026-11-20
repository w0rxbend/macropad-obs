#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""A fake OBS for tests: an obs-websocket 5 server on the Python standard library alone
(docs/spec/spec-v2.md 8.3, docs/research/05-obs-websocket.md). It listens on loopback only and
serves one OBS state file.

    python3 tools/fake_obs.py --log requests.log

The first stdout line is `listening <port>`. SIGTERM or SIGINT ends the run with exit code 0.

Request log (spec 13 criterion 4c): one line per request (op 6), in arrival order, written before
the request is answered. A line is compact JSON: `requestType`, then `requestData` with sorted
keys. `requestData` is left out when the request has none or an empty one. `requestId` is not
logged. Identify is not logged, so nothing made from a password reaches the log.

    {"requestType":"ToggleRecord"}
    {"requestType":"SetInputVolume","requestData":{"inputUuid":"U_B","inputVolumeDb":-18}}

Not a whole OBS: it sends no events, takes no request batch, and finds a scene or an input by
UUID only. A request type outside the table in Studio is logged and gets status 204.
"""

import argparse
import asyncio
import base64
import contextlib
import hashlib
import json
import secrets
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

DEFAULT_STATE = Path(__file__).resolve().parent / "fixtures" / "ui_state.json"
LOOPBACK = "127.0.0.1"

# RFC 6455.
HTTP_HEAD_END = b"\r\n\r\n"
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SUBPROTOCOL = "obswebsocket.json"
OPCODE_CONTINUATION, OPCODE_TEXT, OPCODE_CLOSE, OPCODE_PING, OPCODE_PONG = 0x0, 0x1, 0x8, 0x9, 0xA
FINAL_BIT, OPCODE_BITS = 0x80, 0x0F
MASK_BIT, LENGTH_BITS = 0x80, 0x7F
MASK_BYTES = 4
CLOSE_CODE_BYTES = 2
LENGTH_IS_16_BIT, LENGTH_IS_64_BIT = 126, 127
EXTENDED_LENGTH_BYTES = {LENGTH_IS_16_BIT: 2, LENGTH_IS_64_BIT: 8}
MAX_16_BIT_LENGTH = 0xFFFF
MAX_CLIENT_FRAME_BYTES = 1 << 20
CLOSE_PROTOCOL_ERROR = 1002
CLOSE_MESSAGE_TOO_BIG = 1009
CLOSE_WAIT_S = 1.0
THROTTLE_CHUNK_BYTES = 1024

# obs-websocket 5.7.6: WebSocketOpCode, WebSocketCloseCode and RequestStatus of protocol.json.
OP_HELLO, OP_IDENTIFY, OP_IDENTIFIED, OP_REIDENTIFY = 0, 1, 2, 3
OP_REQUEST, OP_REQUEST_RESPONSE = 6, 7
RPC_VERSION = 1
CLOSE_MESSAGE_DECODE_ERROR = 4002
CLOSE_MISSING_DATA_FIELD = 4003
CLOSE_UNKNOWN_OPCODE = 4006
CLOSE_NOT_IDENTIFIED = 4007
CLOSE_ALREADY_IDENTIFIED = 4008
CLOSE_AUTHENTICATION_FAILED = 4009
CLOSE_UNSUPPORTED_RPC_VERSION = 4010
CLOSE_SESSION_INVALIDATED = 4011
REFUSE_IDENTIFY_MODES = (CLOSE_AUTHENTICATION_FAILED, CLOSE_UNSUPPORTED_RPC_VERSION)
CLOSE_MODES = (*REFUSE_IDENTIFY_MODES, CLOSE_SESSION_INVALIDATED)
STATUS_SUCCESS = 100
STATUS_UNKNOWN_REQUEST_TYPE = 204
STATUS_MISSING_REQUEST_FIELD = 300
STATUS_INVALID_REQUEST_FIELD_TYPE = 401
STATUS_REQUEST_FIELD_OUT_OF_RANGE = 402
STATUS_RESOURCE_NOT_FOUND = 600
# `inputVolumeDb` runs from -100 to 26, and silence reads -100 (R05 section 5).
MIN_VOLUME_DB, MAX_VOLUME_DB = -100, 26
NUMBER = (int, float)
# The state file gives an input no kind. Each one is audio: bit 1 of `inputKindCaps` (R05 section 5).
INPUT_KIND = "pulse_input_capture"
AUDIO_INPUT_KIND_CAPS = 1 << 1
# An output here moves no data: its timecode and counters stay at zero.
IDLE_TIMECODE = "00:00:00.000"
CURRENT_OBS_WEBSOCKET_VERSION = "5.7.6"
OBS_STUDIO_VERSION = "33.0.1"
# Hello carries `obsStudioVersion` from 5.6.0 on (R05 section 9).
OBS_STUDIO_VERSION_SINCE = (5, 6, 0)
NONCE_BYTES = 32
# The worst case R05 section 5 sizes: 500 scenes with names this long make one 75 kB reply.
SCENE_NAME_BYTES = 64


class ProtocolClose(Exception):
    """The connection ends with this WebSocket close code."""

    def __init__(self, code, reason):
        super().__init__(reason)
        self.code, self.reason = code, reason


class RequestRefused(Exception):
    """A request fails with this obs-websocket request status."""

    def __init__(self, code, comment):
        super().__init__(comment)
        self.code, self.comment = code, comment


@dataclass(frozen=True)
class Options:
    """Where one run departs from a current OBS with authentication off."""

    password: str | None = None  # None: authentication off. A test string, never a real one.
    obs_websocket_version: str = CURRENT_OBS_WEBSOCKET_VERSION
    close_code: int | None = None  # 4009, 4010: refuse every Identify. 4011: kick after Identified.
    throttle_bytes_per_s: int = 0  # 0: no throttle


def version_triple(version):
    """'5.7.6' as (5, 7, 6). Raises ValueError for any other form."""
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def nonce():
    """A salt or a challenge: base64 of 32 random bytes, 44 characters (R05 section 3)."""
    return base64.b64encode(secrets.token_bytes(NONCE_BYTES)).decode()


def auth_response(password, salt, challenge):
    """The `authentication` string a client must send in Identify (R05 section 3)."""

    def base64_sha256(text):
        return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()

    return base64_sha256(base64_sha256(password + salt) + challenge)


def compact_json(value):
    """JSON as OBS writes it: nlohmann::json sorts keys, so "d" precedes "op" (R05 section 6)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_log_line(request_type, request_data):
    """One request as its log line. The module docstring gives the format."""
    line = f'{{"requestType":{compact_json(request_type)}'
    if request_data not in (None, {}):
        line += f',"requestData":{compact_json(request_data)}'
    return line + "}"


def with_scene_collection(state, count):
    """The state with its scenes swapped for count made-up ones, each with a 36-byte UUID and a
    64-byte name. Program is the first of them. Preview, when the state has one, is the last."""
    scenes = [
        {
            "sceneName": f"Scene {index:03d} ".ljust(SCENE_NAME_BYTES, "-"),
            "sceneUuid": f"{index:08x}-0000-4000-8000-000000000000",
        }
        for index in range(count)
    ]
    has_preview = state["currentPreviewSceneUuid"] is not None
    return state | {
        "scenes": scenes,
        "currentProgramSceneUuid": scenes[0]["sceneUuid"],
        "currentPreviewSceneUuid": scenes[-1]["sceneUuid"] if has_preview else None,
    }


def parse_http_head(head):
    """(request line, headers under lower-case names) of the head of one HTTP request."""
    request_line, *header_lines = head.decode("latin-1").split("\r\n")
    headers = {
        name.strip().lower(): value.strip()
        for name, _, value in (line.partition(":") for line in header_lines)
    }
    return request_line, headers


def parse_message(payload):
    """(op, d) of one client message. Raises the close a malformed message gets."""
    try:
        message = json.loads(payload)
    except ValueError:
        raise ProtocolClose(CLOSE_MESSAGE_DECODE_ERROR, "the message is not JSON") from None
    if not isinstance(message, dict) or not isinstance(message.get("d"), dict):
        raise ProtocolClose(CLOSE_MISSING_DATA_FIELD, "the message needs an object `d`")
    return message.get("op"), message["d"]


def request_field(request_data, name, kind):
    """request_data[name] as kind. Raises the status OBS gives a missing or mistyped field."""
    if name not in request_data:
        raise RequestRefused(STATUS_MISSING_REQUEST_FIELD, f"the request needs `{name}`")
    value = request_data[name]
    # bool is an int in Python, and JSON true is not a number.
    if not isinstance(value, kind) or (isinstance(value, bool) and kind is not bool):
        raise RequestRefused(STATUS_INVALID_REQUEST_FIELD_TYPE, f"`{name}` has the wrong type")
    return value


class Studio:
    """The OBS state of one state file. A request reads it or changes it."""

    def __init__(self, state):
        self._scene_names = {scene["sceneUuid"]: scene["sceneName"] for scene in state["scenes"]}
        self._inputs = {entry["inputUuid"]: dict(entry) for entry in state["inputs"]}
        self._program_uuid = state["currentProgramSceneUuid"]
        self._preview_uuid = state["currentPreviewSceneUuid"]
        self._studio_mode = state["studioModeEnabled"]
        self._record_active = state["recordActive"]
        self._stream_active = state["streamActive"]
        if self._program_uuid not in self._scene_names:
            raise ValueError(f"program scene {self._program_uuid!r} is not in `scenes`")
        if self._preview_uuid is not None and self._preview_uuid not in self._scene_names:
            raise ValueError(f"preview scene {self._preview_uuid!r} is not in `scenes`")

    def answer(self, request_type, request_data):
        """The `responseData` of one request, or None when it has none. Raises RequestRefused."""
        if request_type not in self._REQUESTS:
            raise RequestRefused(STATUS_UNKNOWN_REQUEST_TYPE, f"no request {request_type!r} here")
        if request_data is None:
            request_data = {}
        if not isinstance(request_data, dict):
            raise RequestRefused(STATUS_INVALID_REQUEST_FIELD_TYPE, "`requestData` is no object")
        return self._REQUESTS[request_type](self, request_data)

    def _get_scene_list(self, _request_data):
        scenes = [
            {"sceneIndex": index, "sceneName": name, "sceneUuid": uuid}
            for index, (uuid, name) in enumerate(self._scene_names.items())
        ]
        return {
            "currentPreviewSceneName": self._scene_names.get(self._preview_uuid),
            "currentPreviewSceneUuid": self._preview_uuid,
            "currentProgramSceneName": self._scene_names[self._program_uuid],
            "currentProgramSceneUuid": self._program_uuid,
            "scenes": scenes,
        }

    def _set_current_program_scene(self, request_data):
        scene_uuid = request_field(request_data, "sceneUuid", str)
        if scene_uuid not in self._scene_names:
            raise RequestRefused(STATUS_RESOURCE_NOT_FOUND, f"no scene {scene_uuid!r}")
        self._program_uuid = scene_uuid

    def _get_studio_mode_enabled(self, _request_data):
        return {"studioModeEnabled": self._studio_mode}

    def _get_input_list(self, _request_data):
        # OBS lists no volume and no mute here (R05 section 5, note 1).
        inputs = [
            {
                "inputKind": INPUT_KIND,
                "inputKindCaps": AUDIO_INPUT_KIND_CAPS,
                "inputName": entry["inputName"],
                "inputUuid": input_uuid,
                "unversionedInputKind": INPUT_KIND,
            }
            for input_uuid, entry in self._inputs.items()
        ]
        return {"inputs": inputs}

    def _input(self, request_data):
        """The input that a request names with `inputUuid`."""
        input_uuid = request_field(request_data, "inputUuid", str)
        if input_uuid not in self._inputs:
            raise RequestRefused(STATUS_RESOURCE_NOT_FOUND, f"no input {input_uuid!r}")
        return self._inputs[input_uuid]

    def _get_input_volume(self, request_data):
        decibel = self._input(request_data)["inputVolumeDb"]
        multiplier = 0 if decibel <= MIN_VOLUME_DB else 10 ** (decibel / 20)
        return {"inputVolumeDb": decibel, "inputVolumeMul": multiplier}

    def _set_input_volume(self, request_data):
        # shortcut: `inputVolumeMul` is not taken, the pad sets dB (criterion 4c); add it when a
        # client sends the multiplier.
        entry = self._input(request_data)
        decibel = request_field(request_data, "inputVolumeDb", NUMBER)
        if not MIN_VOLUME_DB <= decibel <= MAX_VOLUME_DB:
            comment = f"`inputVolumeDb` is outside {MIN_VOLUME_DB}..{MAX_VOLUME_DB}"
            raise RequestRefused(STATUS_REQUEST_FIELD_OUT_OF_RANGE, comment)
        entry["inputVolumeDb"] = decibel

    def _get_input_mute(self, request_data):
        return {"inputMuted": self._input(request_data)["inputMuted"]}

    def _set_input_mute(self, request_data):
        entry = self._input(request_data)
        entry["inputMuted"] = request_field(request_data, "inputMuted", bool)

    def _toggle_input_mute(self, request_data):
        entry = self._input(request_data)
        entry["inputMuted"] = not entry["inputMuted"]
        return {"inputMuted": entry["inputMuted"]}

    def _get_record_status(self, _request_data):
        return {
            "outputActive": self._record_active,
            "outputBytes": 0,
            "outputDuration": 0,
            "outputPaused": False,
            "outputTimecode": IDLE_TIMECODE,
        }

    def _toggle_record(self, _request_data):
        self._record_active = not self._record_active
        return {"outputActive": self._record_active}

    def _get_stream_status(self, _request_data):
        return {
            "outputActive": self._stream_active,
            "outputBytes": 0,
            "outputCongestion": 0,
            "outputDuration": 0,
            "outputReconnecting": False,
            "outputSkippedFrames": 0,
            "outputTimecode": IDLE_TIMECODE,
            "outputTotalFrames": 0,
        }

    def _toggle_stream(self, _request_data):
        self._stream_active = not self._stream_active
        return {"outputActive": self._stream_active}

    _REQUESTS = {
        "GetInputList": _get_input_list,
        "GetInputMute": _get_input_mute,
        "GetInputVolume": _get_input_volume,
        "GetRecordStatus": _get_record_status,
        "GetSceneList": _get_scene_list,
        "GetStreamStatus": _get_stream_status,
        "GetStudioModeEnabled": _get_studio_mode_enabled,
        "SetCurrentProgramScene": _set_current_program_scene,
        "SetInputMute": _set_input_mute,
        "SetInputVolume": _set_input_volume,
        "ToggleInputMute": _toggle_input_mute,
        "ToggleRecord": _toggle_record,
        "ToggleStream": _toggle_stream,
    }


class Frame(NamedTuple):
    final: bool
    opcode: int
    payload: bytes


class Peer:
    """One client connection: the HTTP upgrade, then RFC 6455 frames."""

    def __init__(self, reader, writer, throttle_bytes_per_s):
        self._reader, self._writer = reader, writer
        self._throttle_bytes_per_s = throttle_bytes_per_s

    async def accept_upgrade(self):
        """Answers the HTTP request: 101 and True for a WebSocket upgrade, else 400 and False."""
        request_line, headers = parse_http_head(await self._reader.readuntil(HTTP_HEAD_END))
        key = headers.get("sec-websocket-key")
        # OBS talks JSON to a client that offers no subprotocol (R05 section 1).
        offered = headers.get("sec-websocket-protocol", SUBPROTOCOL).split(",")
        wants_websocket = headers.get("upgrade", "").lower() == "websocket"
        wants_json = SUBPROTOCOL in (name.strip() for name in offered)
        if not (request_line.startswith("GET ") and wants_websocket and wants_json and key):
            await self._write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            return False
        accept = base64.b64encode(hashlib.sha1((key + WEBSOCKET_GUID).encode()).digest()).decode()
        response = ["HTTP/1.1 101 Switching Protocols", "Upgrade: websocket", "Connection: Upgrade"]
        response.append(f"Sec-WebSocket-Accept: {accept}")
        if "sec-websocket-protocol" in headers:
            response.append(f"Sec-WebSocket-Protocol: {SUBPROTOCOL}")
        await self._write("\r\n".join([*response, "", ""]).encode())
        return True

    async def read_message(self):
        """The payload of the next text message, or None once the client has closed.
        A ping is answered here."""
        # shortcut: fragment order is not policed and only one frame's size is capped; police both
        # before anything but a test client connects.
        fragments = []
        while True:
            frame = await self._read_frame()
            if frame.opcode == OPCODE_CLOSE:
                await self._send_frame(OPCODE_CLOSE, frame.payload[:CLOSE_CODE_BYTES])
                return None
            if frame.opcode == OPCODE_PING:
                await self._send_frame(OPCODE_PONG, frame.payload)
            elif frame.opcode in (OPCODE_TEXT, OPCODE_CONTINUATION):
                fragments.append(frame.payload)
                if frame.final:
                    return b"".join(fragments)
            elif frame.opcode != OPCODE_PONG:
                raise ProtocolClose(CLOSE_MESSAGE_DECODE_ERROR, "only a text frame carries JSON")

    async def send_text(self, text):
        await self._send_frame(OPCODE_TEXT, text.encode())

    async def close(self, code, reason):
        """Sends a close frame, then waits for the client's own, so that closing the socket with
        unread client bytes cannot reset the connection before the client reads the code."""
        payload = code.to_bytes(CLOSE_CODE_BYTES, "big") + reason.encode()
        try:
            await self._send_frame(OPCODE_CLOSE, payload)
            async with asyncio.timeout(CLOSE_WAIT_S):
                while (await self._read_frame()).opcode != OPCODE_CLOSE:
                    pass
        except (TimeoutError, ProtocolClose, asyncio.IncompleteReadError, ConnectionError):
            pass  # The code is sent. A client that leaves first or sends rubbish is not waited for.

    async def _read_frame(self):
        first_byte, second_byte = await self._reader.readexactly(2)
        length = second_byte & LENGTH_BITS
        if length in EXTENDED_LENGTH_BYTES:
            extended = await self._reader.readexactly(EXTENDED_LENGTH_BYTES[length])
            length = int.from_bytes(extended, "big")
        if not second_byte & MASK_BIT:
            raise ProtocolClose(CLOSE_PROTOCOL_ERROR, "a client frame must be masked")
        if length > MAX_CLIENT_FRAME_BYTES:
            raise ProtocolClose(CLOSE_MESSAGE_TOO_BIG, "the frame is too big")
        mask = await self._reader.readexactly(MASK_BYTES)
        masked = await self._reader.readexactly(length)
        payload = bytes(byte ^ mask[index % MASK_BYTES] for index, byte in enumerate(masked))
        return Frame(bool(first_byte & FINAL_BIT), first_byte & OPCODE_BITS, payload)

    async def _send_frame(self, opcode, payload):
        """Writes one whole, unmasked frame: the server never fragments (R05 section 6)."""
        length = len(payload)
        if length < LENGTH_IS_16_BIT:
            header = bytes([FINAL_BIT | opcode, length])
        elif length <= MAX_16_BIT_LENGTH:
            header = bytes([FINAL_BIT | opcode, LENGTH_IS_16_BIT]) + length.to_bytes(2, "big")
        else:
            header = bytes([FINAL_BIT | opcode, LENGTH_IS_64_BIT]) + length.to_bytes(8, "big")
        await self._write(header + payload)

    async def _write(self, data):
        if not self._throttle_bytes_per_s:
            self._writer.write(data)
            await self._writer.drain()
            return
        for start in range(0, len(data), THROTTLE_CHUNK_BYTES):
            chunk = data[start : start + THROTTLE_CHUNK_BYTES]
            self._writer.write(chunk)
            await self._writer.drain()
            await asyncio.sleep(len(chunk) / self._throttle_bytes_per_s)


class Session:
    """One connection's obs-websocket state, and its messages as JSON over the Peer."""

    def __init__(self, peer, challenge):
        self._peer = peer
        self.challenge = challenge
        self.identified = False

    async def send(self, op, data):
        await self._peer.send_text(compact_json({"d": data, "op": op}))

    async def receive(self):
        """(op, d) of the next message, or None once the client has closed."""
        payload = await self._peer.read_message()
        return None if payload is None else parse_message(payload)


class FakeObs:
    """The server: one Studio and one request log, shared by every connection."""

    def __init__(self, studio, log, options=Options()):
        self._studio, self._log, self._options = studio, log, options
        # OBS makes the salt once per server start and a challenge per connection (R05 section 3).
        self._salt = nonce()
        self._handlers = {
            OP_IDENTIFY: self._identify,
            OP_REIDENTIFY: self._reidentify,
            OP_REQUEST: self._request,
        }

    async def start(self, port):
        """Listens on loopback. Port 0 takes a free port: read it from the returned server."""
        return await asyncio.start_server(self._serve_connection, LOOPBACK, port)

    async def _serve_connection(self, reader, writer):
        peer = Peer(reader, writer, self._options.throttle_bytes_per_s)
        try:
            if await peer.accept_upgrade():
                await self._converse(Session(peer, nonce()))
        except ProtocolClose as ending:
            await peer.close(ending.code, ending.reason)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
            pass  # The client left, or never ended its HTTP header.
        finally:
            writer.close()

    async def _converse(self, session):
        await session.send(OP_HELLO, self._hello(session.challenge))
        while (message := await session.receive()) is not None:
            await self._dispatch(session, *message)

    def _hello(self, challenge):
        version = self._options.obs_websocket_version
        hello = {"obsWebSocketVersion": version, "rpcVersion": RPC_VERSION}
        if version_triple(version) >= OBS_STUDIO_VERSION_SINCE:
            hello["obsStudioVersion"] = OBS_STUDIO_VERSION
        if self._options.password is not None:
            hello["authentication"] = {"challenge": challenge, "salt": self._salt}
        return hello

    async def _dispatch(self, session, op, data):
        # `type is int`: JSON true equals 1 in Python and must not pass as Identify.
        handler = self._handlers.get(op) if type(op) is int else None
        if handler is None:
            raise ProtocolClose(CLOSE_UNKNOWN_OPCODE, "unknown op")
        if op == OP_IDENTIFY and session.identified:
            raise ProtocolClose(CLOSE_ALREADY_IDENTIFIED, "already identified")
        if op != OP_IDENTIFY and not session.identified:
            raise ProtocolClose(CLOSE_NOT_IDENTIFIED, "not identified")
        await handler(session, data)

    async def _identify(self, session, data):
        close_mode = self._options.close_code
        if close_mode in REFUSE_IDENTIFY_MODES:
            raise ProtocolClose(close_mode, "close mode")
        # OBS checks the authentication string before the RPC version.
        if not self._authenticates(session, data):
            raise ProtocolClose(CLOSE_AUTHENTICATION_FAILED, "authentication failed")
        rpc_version = data.get("rpcVersion")
        if type(rpc_version) is not int or rpc_version != RPC_VERSION:
            raise ProtocolClose(CLOSE_UNSUPPORTED_RPC_VERSION, "unsupported rpcVersion")
        session.identified = True
        await session.send(OP_IDENTIFIED, {"negotiatedRpcVersion": RPC_VERSION})
        if close_mode == CLOSE_SESSION_INVALIDATED:
            raise ProtocolClose(CLOSE_SESSION_INVALIDATED, "session invalidated")

    def _authenticates(self, session, identify_data):
        password = self._options.password
        if password is None:
            return True
        expected = auth_response(password, self._salt, session.challenge)
        return identify_data.get("authentication") == expected

    async def _reidentify(self, session, _data):
        # shortcut: no event is ever sent, so the new `eventSubscriptions` mask is dropped; keep it
        # in Session when events land.
        await session.send(OP_IDENTIFIED, {"negotiatedRpcVersion": RPC_VERSION})

    async def _request(self, session, data):
        request_id, request_type = data.get("requestId"), data.get("requestType")
        if not isinstance(request_id, str) or not isinstance(request_type, str):
            raise ProtocolClose(CLOSE_MISSING_DATA_FIELD, "a request needs an id and a type")
        request_data = data.get("requestData")
        self._log.write(request_log_line(request_type, request_data) + "\n")
        self._log.flush()
        response = {"requestId": request_id, "requestType": request_type}
        response |= self._outcome(request_type, request_data)
        await session.send(OP_REQUEST_RESPONSE, response)

    def _outcome(self, request_type, request_data):
        """The `requestStatus` of one request, with its `responseData` when it has one."""
        try:
            response_data = self._studio.answer(request_type, request_data)
        except RequestRefused as refusal:
            status = {"code": refusal.code, "comment": refusal.comment, "result": False}
            return {"requestStatus": status}
        outcome = {"requestStatus": {"code": STATUS_SUCCESS, "result": True}}
        return outcome if response_data is None else outcome | {"responseData": response_data}


def positive_int(text):
    number = int(text)
    if number < 1:
        raise ValueError(text)
    return number


def checked_version(text):
    version_triple(text)
    return text


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    flag = parser.add_argument
    flag("--port", type=int, default=0, help="loopback port; 0 (default) takes a free one")
    flag("--state", type=Path, default=DEFAULT_STATE, help="OBS state file (default: %(default)s)")
    flag("--log", type=Path, help="request log file, emptied at start (default: stdout)")
    flag("--password", help="turn authentication on with this test string; never a real password")
    flag(
        "--obs-websocket-version",
        type=checked_version,
        default=CURRENT_OBS_WEBSOCKET_VERSION,
        help="version that Hello reports, to play an older OBS (default: %(default)s)",
    )
    flag(
        "--close-code",
        type=int,
        choices=CLOSE_MODES,
        help="4009 or 4010: refuse every Identify with it; 4011: kick right after Identified",
    )
    flag(
        "--scenes",
        type=positive_int,
        metavar="COUNT",
        help="swap the state's scenes for COUNT made-up ones; 500 make a 75 kB GetSceneList reply",
    )
    flag(
        "--throttle-bytes-per-s",
        type=positive_int,
        default=0,
        metavar="RATE",
        help="send at most RATE bytes per second, in 1024-byte pieces (default: no throttle)",
    )
    return parser.parse_args(argv)


async def serve(obs, port):
    """Runs the server until SIGINT or SIGTERM."""
    server = await obs.start(port)
    print(f"listening {server.sockets[0].getsockname()[1]}", flush=True)
    stop = asyncio.Event()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(signal_number, stop.set)
    await stop.wait()
    server.close()


def main(argv=None):
    arguments = parse_arguments(argv)
    state = json.loads(arguments.state.read_text(encoding="utf-8"))
    if arguments.scenes:
        state = with_scene_collection(state, arguments.scenes)
    options = Options(
        password=arguments.password,
        obs_websocket_version=arguments.obs_websocket_version,
        close_code=arguments.close_code,
        throttle_bytes_per_s=arguments.throttle_bytes_per_s,
    )
    stdout_log = contextlib.nullcontext(sys.stdout)
    with arguments.log.open("w", encoding="utf-8") if arguments.log else stdout_log as log:
        asyncio.run(serve(FakeObs(Studio(state), log, options), arguments.port))
    return 0


if __name__ == "__main__":
    sys.exit(main())
