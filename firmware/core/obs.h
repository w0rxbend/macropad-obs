// SPDX-License-Identifier: MIT
// The obs-websocket 5 handshake over fw-ws (spec 8.3, R05): Hello, the 5.4.0 floor, the auth
// string, Identify with rpcVersion 1 and eventSubscriptions 1118, Identified, and the reconnect
// backoff. No retry after close 4009, 4010 or 4011. Pure C, no SDK headers, no heap.
// Requests and events after Identified are task 2.8: until then their messages are not read.
#pragma once

#include "json.h"
#include "link.h"
#include "ws.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// The oldest obs-websocket the pad talks to: the first with UUIDs (OBS 30.1, spec 4 item 3).
#define OBS_MIN_MAJOR 5
#define OBS_MIN_MINOR 4
#define OBS_MIN_PATCH 0
#define OBS_RPC_VERSION 1
// Config 2, Scenes 4, Inputs 8, Transitions 16, Outputs 64 and Ui 1024 (R05 section 4).
#define OBS_EVENT_SUBSCRIPTIONS 1118
// The longest salt or challenge the pad hashes. OBS sends 44 characters (R05 section 3).
#define OBS_NONCE_MAX 64
#define OBS_VERSION_MAX 16

// The fine state behind the strip line. obs_link_state folds it into the STATUS byte.
typedef enum {
	OBS_IDLE,           // obs_start not called
	OBS_CONNECTING,     // first try, or the link to an identified OBS dropped
	OBS_UNREACHABLE,    // a try failed: no TCP, no upgrade, or no handshake. Retried
	OBS_NO_PASSWORD,    // OBS asks for auth and no password is stored. Stopped
	OBS_WRONG_PASSWORD, // close 4009. Stopped
	OBS_TOO_OLD,        // Hello reports obs-websocket below 5.4.0, or no version. Stopped
	OBS_RPC_REFUSED,    // close 4010, or Identified with an rpcVersion other than 1. Stopped
	OBS_KICKED,         // close 4011: OBS says not to reconnect. Stopped
	OBS_UP,             // Identified
} obs_status_t;

// The fields of one received handshake message that the pad reads. Belongs to obs.c.
typedef struct {
	int32_t op; // -1 until read
	int32_t negotiated_rpc_version;
	bool has_auth;
	bool bad_field; // a field the pad reads is too long or has the wrong type
	char version[OBS_VERSION_MAX + 1];
	char salt[OBS_NONCE_MAX + 1];
	char challenge[OBS_NONCE_MAX + 1];
} obs_message_t;

// Read `status`. The rest belongs to obs.c. Do not copy after obs_init: the reader points at
// itself.
typedef struct {
	obs_status_t status;
	ws_t ws;
	uint8_t step;
	uint8_t ip[4];
	uint16_t port;
	const char *password;
	size_t password_len;
	uint8_t retry_step;
	uint32_t retry_wait_started_ms;
	json_reader_t reader;
	obs_message_t message;
} obs_t;

// Starts idle. `stream` and `next_random` stay the client's for its life.
void obs_init(obs_t *obs, stream_t *stream, ws_random_t next_random);

// Dials ws://ip:port at once. `password` is the stored OBS password, or NULL when none is
// stored; its bytes must stay valid until the next obs_start. Only on a client that is idle or
// stopped: false, and nothing changes, otherwise.
bool obs_start(obs_t *obs, const uint8_t ip[4], uint16_t port, const char *password,
               size_t password_len, uint32_t now_ms);

// Call on every pass of the main loop. A failed try waits 0.5, 1, 2 s, then 2 s each time, and
// the waits start again after Identified. The 2 s cap keeps criterion 3 (reconnect within 5 s
// of an OBS restart) with room for the handshake. A failure state stays through its retries.
// `now_ms` may wrap.
void obs_poll(obs_t *obs, uint32_t now_ms);

// The STATUS byte of a state (docs/protocol.md): unreachable, too old, RPC refused and kicked
// are `refused`; no password and wrong password are `auth_failed`.
enum link_obs_state obs_link_state(obs_status_t status);

// The strip line of a failure state: fixed printable ASCII, never a secret. NULL for idle,
// connecting, up and a value outside the enum.
const char *obs_strip_line(obs_status_t status);
