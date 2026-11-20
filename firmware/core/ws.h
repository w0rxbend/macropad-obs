// SPDX-License-Identifier: MIT
// RFC 6455 client over the stream seam (spec 8.3, fw-ws): the upgrade with its SHA-1 accept
// check, masked client frames, fragments, ping on idle, and close codes. Pure C, no SDK headers,
// no heap. A received message is never held whole: 500 scenes is one 55 to 75 kB text frame
// (R05), so ws_poll hands each text message out in slices as its bytes arrive.
#pragma once

#include "crypto.h"
#include "stream.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Close codes ws_poll reports (RFC 6455 section 7.4.1). The peer's own code passes through.
#define WS_CLOSE_NORMAL 1000
#define WS_CLOSE_PROTOCOL_ERROR 1002
#define WS_CLOSE_UNSUPPORTED_DATA 1003 // a binary message: obs-websocket JSON is text only
#define WS_CLOSE_NO_CODE 1005          // the peer's close frame carried no code
#define WS_CLOSE_ABNORMAL 1006         // no close frame: TCP lost, upgrade refused, or timed out

// The longest server response head the upgrade reads. Received bytes wait here too.
#define WS_RX_LEN 512
// RFC 6455 section 5.5: a control frame carries at most 125 payload bytes.
#define WS_CONTROL_MAX 125

// A silent link gets a ping after each WS_PING_EVERY_MS of silence. Any received byte answers.
// After WS_PINGS_UNANSWERED pings with no byte back, the link counts as lost. obs-websocket
// never pings on its own (R05), so this is the only way to see a dead peer.
#define WS_PING_EVERY_MS 5000u
#define WS_PINGS_UNANSWERED 2u
#define WS_UPGRADE_TIMEOUT_MS 5000u
// How long ws_close waits for the peer's close frame before it drops the TCP link.
#define WS_CLOSE_WAIT_MS 1000u

typedef enum {
	WS_OK,
	WS_NOT_OPEN,      // no upgraded link to send on
	WS_BUSY,          // ws_open on a client that is not closed
	WS_STREAM_FAILED, // the stream refused
} ws_status_t;

typedef enum {
	WS_EVT_NONE,   // nothing new yet: call again on the next pass
	WS_EVT_OPEN,   // the server accepted the upgrade
	WS_EVT_DATA,   // `bytes` and `len`: the next slice of the current text message
	WS_EVT_CLOSED, // the link is down for good: `close_code` says why. Reported once
} ws_event_kind_t;

typedef struct {
	ws_event_kind_t kind;
	const uint8_t *bytes; // WS_EVT_DATA: valid until the next ws_* call
	size_t len;           // WS_EVT_DATA: may be 0 only on the last slice
	bool message_end;     // WS_EVT_DATA: this slice ends the message
	uint16_t close_code;  // WS_EVT_CLOSED
} ws_event_t;

// The source of masking keys and of the upgrade nonce: esp_random on the pad. RFC 6455
// section 10.3 wants keys a proxy cannot guess.
typedef uint32_t (*ws_random_t)(void);

// The fields belong to ws.c.
typedef struct {
	stream_t *stream;
	ws_random_t next_random;
	uint8_t state;
	char accept[CRYPTO_BASE64_LEN(CRYPTO_SHA1_LEN) + 1];
	uint32_t timer_started_ms;
	uint32_t last_rx_ms;
	uint8_t pings_sent;
	uint8_t rx[WS_RX_LEN];
	size_t rx_len;
	size_t rx_pos;
	uint8_t head_step;
	uint8_t head_bytes_left;
	uint8_t opcode;
	bool fin;
	bool in_message;
	uint64_t payload_left;
	uint8_t control[WS_CONTROL_MAX];
	uint8_t control_len;
} ws_t;

// Starts closed. `stream` and `next_random` stay the client's for its life.
void ws_init(ws_t *ws, stream_t *stream, ws_random_t next_random);

// Opens TCP to ip:port and sends the upgrade request for "/". ws_poll then gives WS_EVT_OPEN
// or WS_EVT_CLOSED. WS_STREAM_FAILED: no connection, no event follows, call again later.
ws_status_t ws_open(ws_t *ws, const uint8_t ip[4], uint16_t port, uint32_t now_ms);

// Call on every pass of the main loop. Reads at most once from the stream, answers pings and
// the peer's close, sends a ping on a silent link, and returns at most one event. A protocol
// error closes with 1002 and a binary message with 1003. `now_ms` may wrap.
ws_event_t ws_poll(ws_t *ws, uint32_t now_ms);

// Sends one masked text frame. Only after WS_EVT_OPEN. WS_STREAM_FAILED drops the link and the
// next ws_poll reports WS_EVT_CLOSED with 1006.
ws_status_t ws_send_text(ws_t *ws, const char *text, size_t len);

// Sends a close frame with `code` and waits WS_CLOSE_WAIT_MS for the peer's. ws_poll then gives
// WS_EVT_CLOSED with the peer's code, or 1006 when none came. Only after WS_EVT_OPEN.
ws_status_t ws_close(ws_t *ws, uint16_t code, uint32_t now_ms);

// Drops the link now, in any state: an open link gets a close frame with `code` as a courtesy
// and no wait for the peer's. No event follows, and ws_open may run at once.
void ws_abort(ws_t *ws, uint16_t code);
