// SPDX-License-Identifier: MIT
#include "ws.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

enum { STATE_CLOSED, STATE_UPGRADING, STATE_OPEN, STATE_CLOSING, STATE_DROPPED };
// Where the frame reader stands: the two fixed head bytes, the extended length, the payload.
enum { STEP_FIRST, STEP_SECOND, STEP_LENGTH, STEP_PAYLOAD };

enum {
	OP_CONTINUATION = 0x0,
	OP_TEXT = 0x1,
	OP_BINARY = 0x2,
	OP_CLOSE = 0x8,
	OP_PING = 0x9,
	OP_PONG = 0xA,
};

#define FIN_BIT 0x80
#define RSV_BITS 0x70
#define OPCODE_BITS 0x0F
#define CONTROL_BIT 0x08
#define MASK_BIT 0x80
#define LENGTH_BITS 0x7F
#define LENGTH_16 126
#define LENGTH_64 127
#define MASK_LEN 4
#define HEAD_MAX (2 + 8 + MASK_LEN)
// One send carries the head and up to this many masked payload bytes, so a request goes out in
// one TCP write.
#define SEND_CHUNK_LEN 256
#define NONCE_LEN 16
#define NONCE_WORDS (NONCE_LEN / 4)
#define KEY_LEN CRYPTO_BASE64_LEN(NONCE_LEN)
// The request line, five headers of known length, and "255.255.255.255:65535" fit with room.
#define REQUEST_MAX 192

// RFC 6455 section 1.3.
static const char ACCEPT_GUID[] = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

void ws_init(ws_t *ws, stream_t *stream, ws_random_t next_random) {
	*ws = (ws_t){.stream = stream, .next_random = next_random, .state = STATE_CLOSED};
}

static ws_event_t no_event(void) {
	return (ws_event_t){.kind = WS_EVT_NONE};
}

static ws_event_t closed_event(ws_t *ws, uint16_t code) {
	ws->state = STATE_CLOSED;
	return (ws_event_t){.kind = WS_EVT_CLOSED, .close_code = code};
}

static void put_be32(uint8_t *out, uint32_t word) {
	for (int i = 0; i < 4; i++) {
		out[i] = (uint8_t)(word >> (24 - 8 * i));
	}
}

static size_t write_head(uint8_t *out, uint8_t opcode, size_t len, const uint8_t mask[MASK_LEN]) {
	size_t head_len = 2;
	out[0] = (uint8_t)(FIN_BIT | opcode);
	if (len < LENGTH_16) {
		out[1] = (uint8_t)(MASK_BIT | len);
	} else if (len <= 0xFFFF) {
		out[1] = MASK_BIT | LENGTH_16;
		out[2] = (uint8_t)(len >> 8);
		out[3] = (uint8_t)len;
		head_len = 4;
	} else {
		out[1] = MASK_BIT | LENGTH_64;
		for (int i = 0; i < 8; i++) {
			out[2 + i] = (uint8_t)((uint64_t)len >> (56 - 8 * i));
		}
		head_len = 10;
	}
	memcpy(out + head_len, mask, MASK_LEN);
	return head_len + MASK_LEN;
}

// Every client frame is masked with a fresh key (RFC 6455 section 5.3).
static bool send_frame(ws_t *ws, uint8_t opcode, const uint8_t *payload, size_t len) {
	uint8_t mask[MASK_LEN];
	put_be32(mask, ws->next_random());
	uint8_t out[HEAD_MAX + SEND_CHUNK_LEN];
	size_t out_len = write_head(out, opcode, len, mask);
	size_t done = 0;
	do {
		size_t take = len - done < SEND_CHUNK_LEN ? len - done : SEND_CHUNK_LEN;
		for (size_t i = 0; i < take; i++) {
			out[out_len + i] = payload[done + i] ^ mask[(done + i) % MASK_LEN];
		}
		if (ws->stream->send(ws->stream, out, out_len + take) != STREAM_OK) {
			return false;
		}
		done += take;
		out_len = 0;
	} while (done < len);
	return true;
}

static bool send_close(ws_t *ws, uint16_t code) {
	uint8_t payload[2] = {(uint8_t)(code >> 8), (uint8_t)code};
	return send_frame(ws, OP_CLOSE, payload, sizeof payload);
}

// The link ended without a close frame from the peer.
static ws_event_t drop(ws_t *ws) {
	ws->stream->close(ws->stream);
	return closed_event(ws, WS_CLOSE_ABNORMAL);
}

// _Fail the WebSocket Connection_ (RFC 6455 section 7.1.7). The close frame is a courtesy: the
// link goes down whether or not it is sent.
static ws_event_t fail(ws_t *ws, uint16_t code) {
	(void)send_close(ws, code);
	ws->stream->close(ws->stream);
	return closed_event(ws, code);
}

// A send failed outside ws_poll: the next ws_poll reports it.
static ws_status_t drop_later(ws_t *ws) {
	ws->stream->close(ws->stream);
	ws->state = STATE_DROPPED;
	return WS_STREAM_FAILED;
}

static void start_link(ws_t *ws, uint8_t state, uint32_t now_ms) {
	ws->state = state;
	ws->timer_started_ms = now_ms;
	ws->last_rx_ms = now_ms;
	ws->pings_sent = 0;
	ws->rx_len = 0;
	ws->rx_pos = 0;
	ws->head_step = STEP_FIRST;
	ws->in_message = false;
}

// Writes the Sec-WebSocket-Key of a fresh nonce into `key`, and the accept value it asks for
// into ws->accept.
static void make_key(ws_t *ws, char key[KEY_LEN + 1]) {
	uint8_t nonce[NONCE_LEN];
	for (int i = 0; i < NONCE_WORDS; i++) {
		put_be32(nonce + 4 * i, ws->next_random());
	}
	crypto_base64_encode(nonce, sizeof nonce, key);
	crypto_sha1_t sha;
	uint8_t digest[CRYPTO_SHA1_LEN];
	crypto_sha1_init(&sha);
	crypto_sha1_update(&sha, key, KEY_LEN);
	crypto_sha1_update(&sha, ACCEPT_GUID, sizeof ACCEPT_GUID - 1);
	crypto_sha1_final(&sha, digest);
	crypto_base64_encode(digest, sizeof digest, ws->accept);
}

ws_status_t ws_open(ws_t *ws, const uint8_t ip[4], uint16_t port, uint32_t now_ms) {
	if (ws->state != STATE_CLOSED) {
		return WS_BUSY;
	}
	if (ws->stream->open(ws->stream, ip, port) != STREAM_OK) {
		return WS_STREAM_FAILED;
	}
	char key[KEY_LEN + 1];
	make_key(ws, key);
	char request[REQUEST_MAX];
	int len = snprintf(request, sizeof request,
	                   "GET / HTTP/1.1\r\n"
	                   "Host: %u.%u.%u.%u:%u\r\n"
	                   "Upgrade: websocket\r\n"
	                   "Connection: Upgrade\r\n"
	                   "Sec-WebSocket-Key: %s\r\n"
	                   "Sec-WebSocket-Version: 13\r\n"
	                   "\r\n",
	                   ip[0], ip[1], ip[2], ip[3], port, key);
	if (ws->stream->send(ws->stream, (const uint8_t *)request, (size_t)len) != STREAM_OK) {
		ws->stream->close(ws->stream);
		return WS_STREAM_FAILED;
	}
	start_link(ws, STATE_UPGRADING, now_ms);
	return WS_OK;
}

// A run of response head text. Not NUL-terminated.
typedef struct {
	const char *at;
	size_t len;
} text_t;

static bool same_ignoring_case(text_t text, const char *word) {
	if (text.len != strlen(word)) {
		return false;
	}
	for (size_t i = 0; i < text.len; i++) {
		if (tolower((unsigned char)text.at[i]) != tolower((unsigned char)word[i])) {
			return false;
		}
	}
	return true;
}

static text_t trimmed(text_t text) {
	while (text.len > 0 && (text.at[0] == ' ' || text.at[0] == '\t')) {
		text.at++;
		text.len--;
	}
	while (text.len > 0 && (text.at[text.len - 1] == ' ' || text.at[text.len - 1] == '\t')) {
		text.len--;
	}
	return text;
}

// The text before the first `separator` of `*rest`, or all of it. `*rest` moves past both.
static text_t take_until(text_t *rest, const char *separator) {
	size_t sep_len = strlen(separator);
	text_t part = {rest->at, 0};
	while (part.len + sep_len <= rest->len && memcmp(part.at + part.len, separator, sep_len) != 0) {
		part.len++;
	}
	if (part.len + sep_len > rest->len) {
		part.len = rest->len;
		*rest = (text_t){rest->at + rest->len, 0};
		return part;
	}
	*rest = (text_t){rest->at + part.len + sep_len, rest->len - part.len - sep_len};
	return part;
}

// HTTP header values like Connection are comma-separated token lists (RFC 9110 section 5.6.1).
static bool has_token(text_t list, const char *token) {
	while (list.len > 0) {
		if (same_ignoring_case(trimmed(take_until(&list, ",")), token)) {
			return true;
		}
	}
	return false;
}

static bool is_switching_protocols(text_t status_line) {
	static const char want[] = "HTTP/1.1 101";
	size_t want_len = sizeof want - 1;
	return status_line.len >= want_len && memcmp(status_line.at, want, want_len) == 0 &&
	       (status_line.len == want_len || status_line.at[want_len] == ' ');
}

// What the response head granted (RFC 6455 section 4.1, the client's checks 1 to 6).
typedef struct {
	bool upgrade;
	bool connection;
	bool accept;
	bool asked_for_nothing_more; // no extension and no subprotocol: the request named none
} grants_t;

static void note_header(grants_t *grants, text_t name, text_t value, const char *accept) {
	if (same_ignoring_case(name, "Upgrade")) {
		grants->upgrade = same_ignoring_case(value, "websocket");
	} else if (same_ignoring_case(name, "Connection")) {
		grants->connection = has_token(value, "upgrade");
	} else if (same_ignoring_case(name, "Sec-WebSocket-Accept")) {
		grants->accept = value.len == strlen(accept) && memcmp(value.at, accept, value.len) == 0;
	} else if (same_ignoring_case(name, "Sec-WebSocket-Extensions") ||
	           same_ignoring_case(name, "Sec-WebSocket-Protocol")) {
		grants->asked_for_nothing_more = false;
	}
}

// `head` ends with the blank line.
static bool upgrade_granted(const ws_t *ws, text_t head) {
	if (!is_switching_protocols(take_until(&head, "\r\n"))) {
		return false;
	}
	grants_t grants = {.asked_for_nothing_more = true};
	for (text_t line = take_until(&head, "\r\n"); line.len > 0; line = take_until(&head, "\r\n")) {
		text_t value = line;
		text_t name = take_until(&value, ":");
		if (name.len == line.len) {
			return false; // a header line with no colon
		}
		note_header(&grants, name, trimmed(value), ws->accept);
	}
	return grants.upgrade && grants.connection && grants.accept && grants.asked_for_nothing_more;
}

// The length of the response head up to and with its blank line, or 0 while it is incomplete.
static size_t head_end(const uint8_t *bytes, size_t len) {
	for (size_t i = 3; i < len; i++) {
		if (memcmp(bytes + i - 3, "\r\n\r\n", 4) == 0) {
			return i + 1;
		}
	}
	return 0;
}

static ws_event_t poll_upgrade(ws_t *ws, uint32_t now_ms) {
	size_t got = 0;
	stream_status_t status =
	    ws->stream->recv(ws->stream, ws->rx + ws->rx_len, WS_RX_LEN - ws->rx_len, &got);
	if (status != STREAM_OK) {
		return drop(ws);
	}
	ws->rx_len += got;
	size_t head_len = head_end(ws->rx, ws->rx_len);
	if (head_len == 0) {
		bool too_long = ws->rx_len == WS_RX_LEN;
		bool too_late = now_ms - ws->timer_started_ms >= WS_UPGRADE_TIMEOUT_MS;
		return too_long || too_late ? drop(ws) : no_event();
	}
	if (!upgrade_granted(ws, (text_t){(const char *)ws->rx, head_len})) {
		return drop(ws);
	}
	size_t rx_len = ws->rx_len;
	start_link(ws, STATE_OPEN, now_ms);
	ws->rx_len = rx_len;
	ws->rx_pos = head_len; // frame bytes that came in the same read
	return (ws_event_t){.kind = WS_EVT_OPEN};
}

static ws_event_t on_close_frame(ws_t *ws) {
	if (ws->control_len == 1) {
		return fail(ws, WS_CLOSE_PROTOCOL_ERROR);
	}
	uint16_t code = ws->control_len == 0 ? WS_CLOSE_NO_CODE
	                                     : (uint16_t)(ws->control[0] << 8 | ws->control[1]);
	if (ws->state == STATE_OPEN) {
		// The echo is a courtesy too (section 5.5.1): the link closes either way.
		(void)send_frame(ws, OP_CLOSE, ws->control, ws->control_len < 2 ? 0 : 2);
	}
	ws->stream->close(ws->stream);
	return closed_event(ws, code);
}

static ws_event_t on_control_frame(ws_t *ws) {
	if (ws->opcode == OP_CLOSE) {
		return on_close_frame(ws);
	}
	if (ws->opcode == OP_PING && !send_frame(ws, OP_PONG, ws->control, ws->control_len)) {
		return drop(ws);
	}
	return no_event();
}

// The frame is read: the next byte starts a new head.
static void next_head(ws_t *ws) {
	ws->head_step = STEP_FIRST;
	if (ws->fin && !(ws->opcode & CONTROL_BIT)) {
		ws->in_message = false;
	}
}

// A frame with no payload bytes ends as soon as its head does.
static ws_event_t end_empty_frame(ws_t *ws) {
	next_head(ws);
	if (ws->opcode & CONTROL_BIT) {
		return on_control_frame(ws);
	}
	if (!ws->fin) {
		return no_event();
	}
	return (ws_event_t){.kind = WS_EVT_DATA, .bytes = ws->rx + ws->rx_pos, .message_end = true};
}

// The head is complete: check the frame against RFC 6455 sections 5.2, 5.4 and 5.5.
static ws_event_t begin_frame(ws_t *ws) {
	bool control = (ws->opcode & CONTROL_BIT) != 0;
	if (ws->opcode == OP_BINARY) {
		return fail(ws, WS_CLOSE_UNSUPPORTED_DATA);
	}
	bool known = ws->opcode == OP_CONTINUATION || ws->opcode == OP_TEXT ||
	             ws->opcode == OP_CLOSE || ws->opcode == OP_PING || ws->opcode == OP_PONG;
	bool bad_control = control && (!ws->fin || ws->payload_left > WS_CONTROL_MAX);
	bool bad_order = (ws->opcode == OP_TEXT && ws->in_message) ||
	                 (ws->opcode == OP_CONTINUATION && !ws->in_message);
	if (!known || bad_control || bad_order) {
		return fail(ws, WS_CLOSE_PROTOCOL_ERROR);
	}
	if (ws->opcode == OP_TEXT) {
		ws->in_message = true;
	}
	ws->control_len = 0;
	ws->head_step = STEP_PAYLOAD;
	return ws->payload_left == 0 ? end_empty_frame(ws) : no_event();
}

static ws_event_t take_head_byte(ws_t *ws, uint8_t byte) {
	switch (ws->head_step) {
	case STEP_FIRST:
		if (byte & RSV_BITS) {
			return fail(ws, WS_CLOSE_PROTOCOL_ERROR); // no extension was agreed
		}
		ws->fin = (byte & FIN_BIT) != 0;
		ws->opcode = byte & OPCODE_BITS;
		ws->head_step = STEP_SECOND;
		return no_event();
	case STEP_SECOND:
		if (byte & MASK_BIT) {
			return fail(ws, WS_CLOSE_PROTOCOL_ERROR); // servers never mask (section 5.1)
		}
		ws->payload_left = byte & LENGTH_BITS;
		if (ws->payload_left < LENGTH_16) {
			return begin_frame(ws);
		}
		ws->head_bytes_left = ws->payload_left == LENGTH_16 ? 2 : 8;
		ws->payload_left = 0;
		ws->head_step = STEP_LENGTH;
		return no_event();
	default:
		ws->payload_left = ws->payload_left << 8 | byte;
		if (--ws->head_bytes_left > 0) {
			return no_event();
		}
		if (ws->payload_left >> 63) {
			return fail(ws, WS_CLOSE_PROTOCOL_ERROR); // section 5.2: the top bit is 0
		}
		return begin_frame(ws);
	}
}

static ws_event_t take_payload(ws_t *ws) {
	size_t buffered = ws->rx_len - ws->rx_pos;
	size_t take = ws->payload_left < buffered ? (size_t)ws->payload_left : buffered;
	const uint8_t *bytes = ws->rx + ws->rx_pos;
	ws->rx_pos += take;
	ws->payload_left -= take;
	if (ws->opcode & CONTROL_BIT) {
		memcpy(ws->control + ws->control_len, bytes, take);
		ws->control_len = (uint8_t)(ws->control_len + take);
		if (ws->payload_left > 0) {
			return no_event();
		}
		next_head(ws);
		return on_control_frame(ws);
	}
	ws_event_t slice = {.kind = WS_EVT_DATA, .bytes = bytes, .len = take};
	if (ws->payload_left == 0) {
		slice.message_end = ws->fin;
		next_head(ws);
	}
	return slice;
}

static ws_event_t read_buffered(ws_t *ws) {
	while (ws->rx_pos < ws->rx_len) {
		ws_event_t event = ws->head_step == STEP_PAYLOAD
		                       ? take_payload(ws)
		                       : take_head_byte(ws, ws->rx[ws->rx_pos++]);
		if (event.kind != WS_EVT_NONE) {
			return event;
		}
	}
	return no_event();
}

static ws_event_t check_timers(ws_t *ws, uint32_t now_ms) {
	if (ws->state == STATE_CLOSING) {
		bool waited = now_ms - ws->timer_started_ms >= WS_CLOSE_WAIT_MS;
		return waited ? drop(ws) : no_event();
	}
	uint32_t silent_ms = now_ms - ws->last_rx_ms;
	if (silent_ms < (ws->pings_sent + 1u) * WS_PING_EVERY_MS) {
		return no_event();
	}
	if (ws->pings_sent == WS_PINGS_UNANSWERED || !send_frame(ws, OP_PING, NULL, 0)) {
		return drop(ws);
	}
	ws->pings_sent++;
	return no_event();
}

static ws_event_t poll_frames(ws_t *ws, uint32_t now_ms) {
	ws_event_t event = read_buffered(ws);
	if (event.kind != WS_EVT_NONE) {
		return event;
	}
	size_t got = 0;
	if (ws->stream->recv(ws->stream, ws->rx, WS_RX_LEN, &got) != STREAM_OK) {
		return drop(ws);
	}
	ws->rx_len = got;
	ws->rx_pos = 0;
	if (got == 0) {
		return check_timers(ws, now_ms);
	}
	ws->last_rx_ms = now_ms;
	ws->pings_sent = 0;
	return read_buffered(ws);
}

ws_event_t ws_poll(ws_t *ws, uint32_t now_ms) {
	switch (ws->state) {
	case STATE_CLOSED:
		return no_event();
	case STATE_DROPPED:
		return closed_event(ws, WS_CLOSE_ABNORMAL);
	case STATE_UPGRADING:
		return poll_upgrade(ws, now_ms);
	default:
		return poll_frames(ws, now_ms);
	}
}

ws_status_t ws_send_text(ws_t *ws, const char *text, size_t len) {
	if (ws->state != STATE_OPEN) {
		return WS_NOT_OPEN;
	}
	return send_frame(ws, OP_TEXT, (const uint8_t *)text, len) ? WS_OK : drop_later(ws);
}

ws_status_t ws_close(ws_t *ws, uint16_t code, uint32_t now_ms) {
	if (ws->state != STATE_OPEN) {
		return WS_NOT_OPEN;
	}
	if (!send_close(ws, code)) {
		return drop_later(ws);
	}
	ws->state = STATE_CLOSING;
	ws->timer_started_ms = now_ms;
	return WS_OK;
}
