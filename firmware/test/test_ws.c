// SPDX-License-Identifier: MIT
#include "fake_stream.h"
#include "ws.h"

#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

// Polls that a test allows before it calls the client stuck: one per byte of the largest frame.
#define POLL_LIMIT (FAKE_STREAM_CAP + 64)

static const uint8_t OBS_IP[4] = {192, 168, 1, 20};
#define OBS_PORT 4455

// RFC 6455 section 1.3: the nonce "the sample nonce" gives the key and the accept below.
static const uint32_t NONCE_WORDS[4] = {0x74686520, 0x73616d70, 0x6c65206e, 0x6f6e6365};
#define RFC_KEY "dGhlIHNhbXBsZSBub25jZQ=="
#define RFC_ACCEPT "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
// RFC 6455 section 5.7 masks with 37 fa 21 3d.
#define MASK_WORD 0x37fa213du

static unsigned random_calls;

// The nonce first, then the same masking key every time.
static uint32_t scripted_random(void) {
	uint32_t word = random_calls < 4 ? NONCE_WORDS[random_calls] : MASK_WORD;
	random_calls++;
	return word;
}

#define GOOD_RESPONSE                                                                        \
	"HTTP/1.1 101 Switching Protocols\r\n"                                               \
	"Upgrade: websocket\r\n"                                                             \
	"Connection: Upgrade\r\n"                                                            \
	"Sec-WebSocket-Accept: " RFC_ACCEPT "\r\n"                                           \
	"\r\n"

static void start(ws_t *ws, fake_stream_t *fake, size_t read_size) {
	random_calls = 0;
	fake_stream_init(fake, read_size);
	ws_init(ws, &fake->stream, scripted_random);
}

static ws_event_t poll_until_event(ws_t *ws, uint32_t now_ms) {
	ws_event_t event = {.kind = WS_EVT_NONE};
	for (int i = 0; i < POLL_LIMIT && event.kind == WS_EVT_NONE; i++) {
		event = ws_poll(ws, now_ms);
	}
	return event;
}

// A client that sent its upgrade at time 0 and saw the server accept it. `sent` is cleared.
static bool upgraded(ws_t *ws, fake_stream_t *fake, size_t read_size) {
	start(ws, fake, read_size);
	if (ws_open(ws, OBS_IP, OBS_PORT, 0) != WS_OK) {
		return false;
	}
	fake_stream_queue(fake, GOOD_RESPONSE, strlen(GOOD_RESPONSE));
	bool open = poll_until_event(ws, 0).kind == WS_EVT_OPEN;
	fake->sent_len = 0;
	return open;
}

// Writes one unmasked server frame into `out` and returns its length.
static size_t server_frame(uint8_t *out, bool fin, uint8_t opcode, const void *payload,
                           size_t len) {
	size_t head = 2;
	out[0] = (uint8_t)((fin ? 0x80 : 0) | opcode);
	if (len < 126) {
		out[1] = (uint8_t)len;
	} else if (len <= 0xFFFF) {
		out[1] = 126;
		out[2] = (uint8_t)(len >> 8);
		out[3] = (uint8_t)len;
		head = 4;
	} else {
		out[1] = 127;
		for (int i = 0; i < 8; i++) {
			out[2 + i] = (uint8_t)((uint64_t)len >> (56 - 8 * i));
		}
		head = 10;
	}
	memcpy(out + head, payload, len);
	return head + len;
}

static void queue_frame(fake_stream_t *fake, bool fin, uint8_t opcode, const void *payload,
                        size_t len) {
	static uint8_t frame[FAKE_STREAM_CAP];
	fake_stream_queue(fake, frame, server_frame(frame, fin, opcode, payload, len));
}

// Collects text message slices until one ends the message. Returns the length, or -1 when an
// event other than WS_EVT_DATA comes first.
static long read_message(ws_t *ws, uint32_t now_ms, uint8_t *out, size_t cap, int *slices) {
	size_t len = 0;
	*slices = 0;
	for (;;) {
		ws_event_t event = poll_until_event(ws, now_ms);
		if (event.kind != WS_EVT_DATA || event.len > cap - len) {
			return -1;
		}
		memcpy(out + len, event.bytes, event.len);
		len += event.len;
		(*slices)++;
		if (event.message_end) {
			return (long)len;
		}
	}
}

// One client frame as it went on the wire, unmasked.
typedef struct {
	bool masked;
	bool fin;
	uint8_t opcode;
	uint8_t mask[4];
	size_t len;
	size_t wire_len;
	uint8_t payload[FAKE_STREAM_CAP];
} client_frame_t;

static client_frame_t sent_frame;

// Parses the client frame at `offset` of what the client sent. False when it is cut short.
static bool parse_sent(const fake_stream_t *fake, size_t offset) {
	const uint8_t *wire = fake->sent + offset;
	size_t avail = fake->sent_len - offset;
	if (offset >= fake->sent_len || avail < 2) {
		return false;
	}
	client_frame_t *frame = &sent_frame;
	frame->fin = (wire[0] & 0x80) != 0;
	frame->opcode = wire[0] & 0x0F;
	frame->masked = (wire[1] & 0x80) != 0;
	size_t head = 2;
	frame->len = wire[1] & 0x7F;
	if (frame->len == 126) {
		frame->len = (size_t)wire[2] << 8 | wire[3];
		head = 4;
	} else if (frame->len == 127) {
		frame->len = 0;
		for (int i = 0; i < 8; i++) {
			frame->len = frame->len << 8 | wire[2 + i];
		}
		head = 10;
	}
	if (frame->masked) {
		memcpy(frame->mask, wire + head, 4);
		head += 4;
	}
	if (avail < head + frame->len) {
		return false;
	}
	for (size_t i = 0; i < frame->len; i++) {
		uint8_t key = frame->masked ? frame->mask[i % 4] : 0;
		frame->payload[i] = wire[head + i] ^ key;
	}
	frame->wire_len = head + frame->len;
	return true;
}

static bool sent_is_one_frame(const fake_stream_t *fake, uint8_t opcode, const void *payload,
                              size_t len) {
	return parse_sent(fake, 0) && sent_frame.wire_len == fake->sent_len && sent_frame.masked &&
	       sent_frame.fin && sent_frame.opcode == opcode && sent_frame.len == len &&
	       memcmp(sent_frame.payload, payload, len) == 0;
}

static bool sent_is_close(const fake_stream_t *fake, uint16_t code) {
	uint8_t payload[2] = {(uint8_t)(code >> 8), (uint8_t)code};
	return sent_is_one_frame(fake, 0x8, payload, 2);
}

static bool closed_with(ws_event_t event, uint16_t code) {
	return event.kind == WS_EVT_CLOSED && event.close_code == code;
}

static bool has_line(const char *text, const char *line) {
	return strstr(text, line) != NULL;
}

static void test_upgrade_request_carries_the_nonce_key(void) {
	ws_t ws;
	static fake_stream_t fake;
	start(&ws, &fake, 1);
	CHECK(ws_open(&ws, OBS_IP, OBS_PORT, 0) == WS_OK);
	CHECK(fake.is_open && memcmp(fake.ip, OBS_IP, 4) == 0 && fake.port == OBS_PORT);
	char request[256] = {0};
	CHECK(fake.sent_len < sizeof request);
	memcpy(request, fake.sent, fake.sent_len < sizeof request ? fake.sent_len : 0);
	CHECK(strncmp(request, "GET / HTTP/1.1\r\n", 16) == 0);
	CHECK(has_line(request, "\r\nHost: 192.168.1.20:4455\r\n"));
	CHECK(has_line(request, "\r\nUpgrade: websocket\r\n"));
	CHECK(has_line(request, "\r\nConnection: Upgrade\r\n"));
	CHECK(has_line(request, "\r\nSec-WebSocket-Key: " RFC_KEY "\r\n"));
	CHECK(has_line(request, "\r\nSec-WebSocket-Version: 13\r\n"));
	CHECK(fake.sent_len >= 4 && memcmp(request + fake.sent_len - 4, "\r\n\r\n", 4) == 0);
}

static void test_the_sha1_base64_accept_opens_the_link(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	CHECK(fake.is_open && fake.close_calls == 0);
	CHECK(ws_poll(&ws, 0).kind == WS_EVT_NONE);
}

static void test_header_names_and_tokens_ignore_case(void) {
	static const char response[] = "HTTP/1.1 101 Switching Protocols\r\n"
	                               "upgrade: WebSocket\r\n"
	                               "CONNECTION: keep-alive, upgrade\r\n"
	                               "Server: test\r\n"
	                               "sec-websocket-accept:  " RFC_ACCEPT " \r\n"
	                               "\r\n";
	ws_t ws;
	static fake_stream_t fake;
	start(&ws, &fake, 7);
	CHECK(ws_open(&ws, OBS_IP, OBS_PORT, 0) == WS_OK);
	fake_stream_queue(&fake, response, strlen(response));
	CHECK(poll_until_event(&ws, 0).kind == WS_EVT_OPEN);
}

static void test_a_bad_upgrade_response_is_refused(void) {
	static const char *const responses[] = {
	    "HTTP/1.1 200 OK\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
	    "Sec-WebSocket-Accept: " RFC_ACCEPT "\r\n\r\n",
	    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
	    "Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOp=\r\n\r\n",
	    "HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\n"
	    "Sec-WebSocket-Accept: " RFC_ACCEPT "\r\n\r\n",
	    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: h2c\r\nConnection: Upgrade\r\n"
	    "Sec-WebSocket-Accept: " RFC_ACCEPT "\r\n\r\n",
	    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
	    "Sec-WebSocket-Accept: " RFC_ACCEPT "\r\n\r\n",
	    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgraded\r\n"
	    "Sec-WebSocket-Accept: " RFC_ACCEPT "\r\n\r\n",
	    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n",
	    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
	    "Sec-WebSocket-Accept: " RFC_ACCEPT "\r\n"
	    "Sec-WebSocket-Extensions: permessage-deflate\r\n\r\n",
	    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
	    "Sec-WebSocket-Accept: " RFC_ACCEPT "\r\n"
	    "Sec-WebSocket-Protocol: obswebsocket.msgpack\r\n\r\n",
	};
	for (size_t i = 0; i < sizeof responses / sizeof responses[0]; i++) {
		ws_t ws;
		static fake_stream_t fake;
		start(&ws, &fake, 3);
		CHECK(ws_open(&ws, OBS_IP, OBS_PORT, 0) == WS_OK);
		fake_stream_queue(&fake, responses[i], strlen(responses[i]));
		ws_event_t event = poll_until_event(&ws, 0);
		if (!closed_with(event, WS_CLOSE_ABNORMAL)) {
			fprintf(stderr, "bad response %zu was not refused\n", i);
		}
		CHECK(closed_with(event, WS_CLOSE_ABNORMAL));
		CHECK(!fake.is_open && fake.close_calls == 1);
		CHECK(ws_poll(&ws, 0).kind == WS_EVT_NONE);
	}
}

static void test_a_response_head_past_the_buffer_is_refused(void) {
	ws_t ws;
	static fake_stream_t fake;
	start(&ws, &fake, 64);
	CHECK(ws_open(&ws, OBS_IP, OBS_PORT, 0) == WS_OK);
	static const char head[] = "HTTP/1.1 101 Switching Protocols\r\nX-Pad: ";
	fake_stream_queue(&fake, head, strlen(head));
	for (int i = 0; i < WS_RX_LEN; i++) {
		fake_stream_queue(&fake, "a", 1);
	}
	CHECK(closed_with(poll_until_event(&ws, 0), WS_CLOSE_ABNORMAL));
	CHECK(!fake.is_open);
}

static void test_the_upgrade_times_out(void) {
	ws_t ws;
	static fake_stream_t fake;
	start(&ws, &fake, 1);
	uint32_t opened_ms = 0xFFFFF000u; // the wait crosses the clock wrap
	CHECK(ws_open(&ws, OBS_IP, OBS_PORT, opened_ms) == WS_OK);
	CHECK(ws_poll(&ws, opened_ms + WS_UPGRADE_TIMEOUT_MS - 1).kind == WS_EVT_NONE);
	CHECK(closed_with(ws_poll(&ws, opened_ms + WS_UPGRADE_TIMEOUT_MS), WS_CLOSE_ABNORMAL));
	CHECK(!fake.is_open);
}

static void test_a_refused_tcp_open_reports_failure_and_can_retry(void) {
	ws_t ws;
	static fake_stream_t fake;
	start(&ws, &fake, 1);
	fake.open_result = STREAM_FAILED;
	CHECK(ws_open(&ws, OBS_IP, OBS_PORT, 0) == WS_STREAM_FAILED);
	CHECK(ws_poll(&ws, 0).kind == WS_EVT_NONE);
	CHECK(ws_send_text(&ws, "x", 1) == WS_NOT_OPEN);
	fake.open_result = STREAM_OK;
	CHECK(ws_open(&ws, OBS_IP, OBS_PORT, 0) == WS_OK);
	CHECK(ws_open(&ws, OBS_IP, OBS_PORT, 0) == WS_BUSY);
}

static void test_frame_bytes_in_the_upgrade_read_are_kept(void) {
	ws_t ws;
	static fake_stream_t fake;
	start(&ws, &fake, sizeof GOOD_RESPONSE + 16);
	CHECK(ws_open(&ws, OBS_IP, OBS_PORT, 0) == WS_OK);
	fake_stream_queue(&fake, GOOD_RESPONSE, strlen(GOOD_RESPONSE));
	queue_frame(&fake, true, 0x1, "{\"op\":0}", 8);
	CHECK(poll_until_event(&ws, 0).kind == WS_EVT_OPEN);
	uint8_t text[16];
	int slices;
	CHECK(read_message(&ws, 0, text, sizeof text, &slices) == 8);
	CHECK(memcmp(text, "{\"op\":0}", 8) == 0);
}

static void test_one_byte_reads_give_the_message_in_slices(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	static const char hello[] = "{\"d\":{\"obsWebSocketVersion\":\"5.4.0\",\"rpcVersion\":1},\"op\":0}";
	queue_frame(&fake, true, 0x1, hello, strlen(hello));
	uint8_t text[128];
	int slices;
	CHECK(read_message(&ws, 0, text, sizeof text, &slices) == (long)strlen(hello));
	CHECK(memcmp(text, hello, strlen(hello)) == 0);
	CHECK(slices == (int)strlen(hello));
	CHECK(fake.sent_len == 0);
}

static void test_every_length_encoding_reads_back(void) {
	static const size_t lengths[] = {0, 1, 125, 126, 0xFFFF, 0x10000, 75 * 1000};
	static uint8_t payload[75 * 1000];
	static uint8_t text[75 * 1000];
	for (size_t i = 0; i < sizeof payload; i++) {
		payload[i] = (uint8_t)('a' + i % 26);
	}
	for (size_t i = 0; i < sizeof lengths / sizeof lengths[0]; i++) {
		ws_t ws;
		static fake_stream_t fake;
		CHECK(upgraded(&ws, &fake, i % 2 == 0 ? 1 : 300));
		queue_frame(&fake, true, 0x1, payload, lengths[i]);
		int slices;
		long len = read_message(&ws, 0, text, sizeof text, &slices);
		CHECK(len == (long)lengths[i]);
		CHECK(len >= 0 && memcmp(text, payload, (size_t)len) == 0);
	}
}

static void test_fragments_join_around_a_ping(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	queue_frame(&fake, false, 0x1, "{\"op\":", 6);
	queue_frame(&fake, true, 0x9, "beat", 4);
	queue_frame(&fake, false, 0x0, "", 0);
	queue_frame(&fake, true, 0x0, "7}", 2);
	uint8_t text[16];
	int slices;
	CHECK(read_message(&ws, 0, text, sizeof text, &slices) == 8);
	CHECK(memcmp(text, "{\"op\":7}", 8) == 0);
	CHECK(sent_is_one_frame(&fake, 0xA, "beat", 4));
	CHECK(memcmp(sent_frame.mask, "\x37\xfa\x21\x3d", 4) == 0);
}

static void test_an_unsolicited_pong_is_ignored(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	queue_frame(&fake, true, 0xA, "x", 1);
	queue_frame(&fake, true, 0x1, "ok", 2);
	uint8_t text[4];
	int slices;
	CHECK(read_message(&ws, 0, text, sizeof text, &slices) == 2);
	CHECK(fake.sent_len == 0);
}

static void test_send_masks_every_length_encoding(void) {
	static const size_t lengths[] = {0, 2, 125, 126, 0xFFFF, 0x10000};
	static char text[0x10000];
	for (size_t i = 0; i < sizeof text; i++) {
		text[i] = (char)('A' + i % 26);
	}
	for (size_t i = 0; i < sizeof lengths / sizeof lengths[0]; i++) {
		ws_t ws;
		static fake_stream_t fake;
		CHECK(upgraded(&ws, &fake, 1));
		CHECK(ws_send_text(&ws, text, lengths[i]) == WS_OK);
		CHECK(sent_is_one_frame(&fake, 0x1, text, lengths[i]));
		size_t head = lengths[i] < 126 ? 6 : lengths[i] <= 0xFFFF ? 8 : 14;
		CHECK(sent_frame.wire_len == head + lengths[i]);
	}
}

static void test_send_masks_with_the_rfc_example_key(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	CHECK(ws_send_text(&ws, "Hello", 5) == WS_OK);
	// RFC 6455 section 5.7: "a single-frame masked text message".
	static const uint8_t wire[] = {0x81, 0x85, 0x37, 0xfa, 0x21, 0x3d,
	                               0x7f, 0x9f, 0x4d, 0x51, 0x58};
	CHECK(fake.sent_len == sizeof wire && memcmp(fake.sent, wire, sizeof wire) == 0);
}

static void test_a_silent_link_gets_pings_then_drops(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	CHECK(ws_poll(&ws, WS_PING_EVERY_MS - 1).kind == WS_EVT_NONE);
	CHECK(fake.sent_len == 0);
	CHECK(ws_poll(&ws, WS_PING_EVERY_MS).kind == WS_EVT_NONE);
	CHECK(parse_sent(&fake, 0) && sent_frame.masked && sent_frame.opcode == 0x9);
	CHECK(sent_frame.wire_len == fake.sent_len);
	CHECK(ws_poll(&ws, 2 * WS_PING_EVERY_MS - 1).kind == WS_EVT_NONE);
	CHECK(fake.sent_len == sent_frame.wire_len);
	CHECK(ws_poll(&ws, 2 * WS_PING_EVERY_MS).kind == WS_EVT_NONE);
	CHECK(parse_sent(&fake, sent_frame.wire_len) && sent_frame.opcode == 0x9);
	uint32_t drop_ms = (WS_PINGS_UNANSWERED + 1) * WS_PING_EVERY_MS;
	CHECK(ws_poll(&ws, drop_ms - 1).kind == WS_EVT_NONE);
	CHECK(closed_with(ws_poll(&ws, drop_ms), WS_CLOSE_ABNORMAL));
	CHECK(!fake.is_open);
}

static void test_a_received_byte_restarts_the_silence(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	CHECK(ws_poll(&ws, WS_PING_EVERY_MS).kind == WS_EVT_NONE);
	size_t ping_len = fake.sent_len;
	CHECK(ping_len > 0);
	queue_frame(&fake, true, 0xA, "", 0);
	uint32_t pong_ms = WS_PING_EVERY_MS + 1000;
	CHECK(ws_poll(&ws, pong_ms).kind == WS_EVT_NONE);
	CHECK(ws_poll(&ws, pong_ms).kind == WS_EVT_NONE);
	CHECK(ws_poll(&ws, pong_ms + WS_PING_EVERY_MS - 1).kind == WS_EVT_NONE);
	CHECK(fake.sent_len == ping_len);
	CHECK(ws_poll(&ws, pong_ms + WS_PING_EVERY_MS).kind == WS_EVT_NONE);
	CHECK(fake.sent_len == 2 * ping_len);
	uint32_t old_drop_ms = (WS_PINGS_UNANSWERED + 1) * WS_PING_EVERY_MS;
	CHECK(ws_poll(&ws, old_drop_ms).kind == WS_EVT_NONE);
	CHECK(fake.is_open);
}

static void test_the_peer_close_is_echoed_and_reported(void) {
	static const uint16_t codes[] = {1000, 1001, 4009, 4010, 4011};
	for (size_t i = 0; i < sizeof codes / sizeof codes[0]; i++) {
		ws_t ws;
		static fake_stream_t fake;
		CHECK(upgraded(&ws, &fake, 1));
		uint8_t payload[] = {(uint8_t)(codes[i] >> 8), (uint8_t)codes[i], 'b', 'y', 'e'};
		queue_frame(&fake, true, 0x8, payload, sizeof payload);
		CHECK(closed_with(poll_until_event(&ws, 0), codes[i]));
		CHECK(sent_is_close(&fake, codes[i]));
		CHECK(!fake.is_open && fake.close_calls == 1);
		CHECK(ws_poll(&ws, 0).kind == WS_EVT_NONE);
		CHECK(ws_send_text(&ws, "x", 1) == WS_NOT_OPEN);
	}
}

static void test_a_close_without_a_code_reports_1005(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	queue_frame(&fake, true, 0x8, "", 0);
	CHECK(closed_with(poll_until_event(&ws, 0), WS_CLOSE_NO_CODE));
	CHECK(sent_is_one_frame(&fake, 0x8, "", 0));
}

static void test_our_close_waits_for_the_echo(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	CHECK(ws_close(&ws, WS_CLOSE_NORMAL, 100) == WS_OK);
	CHECK(sent_is_close(&fake, WS_CLOSE_NORMAL));
	CHECK(ws_send_text(&ws, "x", 1) == WS_NOT_OPEN);
	CHECK(ws_poll(&ws, 100).kind == WS_EVT_NONE);
	CHECK(fake.is_open);
	uint8_t echo[] = {0x03, 0xE8};
	queue_frame(&fake, true, 0x8, echo, sizeof echo);
	fake.sent_len = 0;
	CHECK(closed_with(poll_until_event(&ws, 200), WS_CLOSE_NORMAL));
	CHECK(fake.sent_len == 0);
	CHECK(!fake.is_open);
}

static void test_our_close_gives_up_after_the_wait(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	CHECK(ws_close(&ws, WS_CLOSE_NORMAL, 100) == WS_OK);
	CHECK(ws_poll(&ws, 100 + WS_CLOSE_WAIT_MS - 1).kind == WS_EVT_NONE);
	CHECK(closed_with(ws_poll(&ws, 100 + WS_CLOSE_WAIT_MS), WS_CLOSE_ABNORMAL));
	CHECK(!fake.is_open);
	CHECK(ws_close(&ws, WS_CLOSE_NORMAL, 0) == WS_NOT_OPEN);
}

typedef struct {
	const char *name;
	uint8_t wire[16];
	size_t len;
	uint16_t code;
} bad_frame_t;

static void test_a_bad_frame_fails_the_link(void) {
	static const bad_frame_t frames[] = {
	    {"masked server frame", {0x81, 0x81, 1, 2, 3, 4, 'x'}, 7, WS_CLOSE_PROTOCOL_ERROR},
	    {"RSV1 set", {0xC1, 0x01, 'x'}, 3, WS_CLOSE_PROTOCOL_ERROR},
	    {"opcode 3", {0x83, 0x01, 'x'}, 3, WS_CLOSE_PROTOCOL_ERROR},
	    {"opcode 11", {0x8B, 0x00}, 2, WS_CLOSE_PROTOCOL_ERROR},
	    {"fragmented ping", {0x09, 0x00}, 2, WS_CLOSE_PROTOCOL_ERROR},
	    {"ping of 126", {0x89, 0x7E, 0x00, 0x7E}, 4, WS_CLOSE_PROTOCOL_ERROR},
	    {"lone continuation", {0x80, 0x01, 'x'}, 3, WS_CLOSE_PROTOCOL_ERROR},
	    {"text inside a message", {0x01, 0x01, 'a', 0x81, 0x01, 'b'}, 6, WS_CLOSE_PROTOCOL_ERROR},
	    {"64-bit length top bit", {0x81, 0x7F, 0x80, 0, 0, 0, 0, 0, 0, 0}, 10,
	     WS_CLOSE_PROTOCOL_ERROR},
	    {"close of 1 byte", {0x88, 0x01, 0x03}, 3, WS_CLOSE_PROTOCOL_ERROR},
	    {"binary message", {0x82, 0x01, 0x00}, 3, WS_CLOSE_UNSUPPORTED_DATA},
	};
	for (size_t i = 0; i < sizeof frames / sizeof frames[0]; i++) {
		ws_t ws;
		static fake_stream_t fake;
		CHECK(upgraded(&ws, &fake, 1));
		fake_stream_queue(&fake, frames[i].wire, frames[i].len);
		ws_event_t event = {.kind = WS_EVT_NONE};
		for (int n = 0; n < POLL_LIMIT && event.kind != WS_EVT_CLOSED; n++) {
			event = ws_poll(&ws, 0);
		}
		if (!closed_with(event, frames[i].code) || !sent_is_close(&fake, frames[i].code)) {
			fprintf(stderr, "bad frame \"%s\" did not close with %u\n", frames[i].name,
			        frames[i].code);
		}
		CHECK(closed_with(event, frames[i].code));
		CHECK(sent_is_close(&fake, frames[i].code));
		CHECK(!fake.is_open);
	}
}

static void test_a_tcp_drop_mid_frame_reports_1006_once(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	fake_stream_queue(&fake, "\x81\x05he", 4);
	fake.hang_up = true;
	ws_event_t event = poll_until_event(&ws, 0);
	CHECK(event.kind == WS_EVT_DATA && !event.message_end);
	event = poll_until_event(&ws, 0);
	CHECK(event.kind == WS_EVT_DATA && !event.message_end);
	CHECK(closed_with(poll_until_event(&ws, 0), WS_CLOSE_ABNORMAL));
	CHECK(fake.sent_len == 0 && fake.close_calls == 1);
	CHECK(ws_poll(&ws, 0).kind == WS_EVT_NONE);
}

static void test_a_failed_send_drops_the_link(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	fake.send_result = STREAM_CLOSED;
	CHECK(ws_send_text(&ws, "{}", 2) == WS_STREAM_FAILED);
	CHECK(closed_with(ws_poll(&ws, 0), WS_CLOSE_ABNORMAL));
	CHECK(!fake.is_open);
	CHECK(ws_poll(&ws, 0).kind == WS_EVT_NONE);
}

static void test_the_link_reopens_after_a_close(void) {
	ws_t ws;
	static fake_stream_t fake;
	CHECK(upgraded(&ws, &fake, 1));
	queue_frame(&fake, true, 0x8, "\x03\xE9", 2);
	CHECK(closed_with(poll_until_event(&ws, 0), 1001));
	random_calls = 0;
	fake.sent_len = 0;
	CHECK(ws_open(&ws, OBS_IP, OBS_PORT, 50) == WS_OK);
	fake_stream_queue(&fake, GOOD_RESPONSE, strlen(GOOD_RESPONSE));
	CHECK(poll_until_event(&ws, 50).kind == WS_EVT_OPEN);
	queue_frame(&fake, true, 0x1, "new", 3);
	uint8_t text[4];
	int slices;
	CHECK(read_message(&ws, 50, text, sizeof text, &slices) == 3);
}

int main(void) {
	test_upgrade_request_carries_the_nonce_key();
	test_the_sha1_base64_accept_opens_the_link();
	test_header_names_and_tokens_ignore_case();
	test_a_bad_upgrade_response_is_refused();
	test_a_response_head_past_the_buffer_is_refused();
	test_the_upgrade_times_out();
	test_a_refused_tcp_open_reports_failure_and_can_retry();
	test_frame_bytes_in_the_upgrade_read_are_kept();
	test_one_byte_reads_give_the_message_in_slices();
	test_every_length_encoding_reads_back();
	test_fragments_join_around_a_ping();
	test_an_unsolicited_pong_is_ignored();
	test_send_masks_every_length_encoding();
	test_send_masks_with_the_rfc_example_key();
	test_a_silent_link_gets_pings_then_drops();
	test_a_received_byte_restarts_the_silence();
	test_the_peer_close_is_echoed_and_reported();
	test_a_close_without_a_code_reports_1005();
	test_our_close_waits_for_the_echo();
	test_our_close_gives_up_after_the_wait();
	test_a_bad_frame_fails_the_link();
	test_a_tcp_drop_mid_frame_reports_1006_once();
	test_a_failed_send_drops_the_link();
	test_the_link_reopens_after_a_close();
	if (failures != 0) {
		fprintf(stderr, "test_ws: %d failures\n", failures);
		return 1;
	}
	printf("test_ws: ok\n");
	return 0;
}
