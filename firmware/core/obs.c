// SPDX-License-Identifier: MIT
#include "obs.h"

#include <stdio.h>
#include <string.h>

// Where the client stands. Each try runs DIAL -> HELLO -> IDENTIFIED -> UP; CLOSING waits for
// the close event of a link the client dropped itself.
enum {
	STEP_IDLE,
	STEP_DIAL,
	STEP_HELLO,
	STEP_IDENTIFIED,
	STEP_UP,
	STEP_CLOSING,
	STEP_WAIT,
	STEP_STOPPED,
};

enum { OP_HELLO = 0, OP_IDENTIFY = 1, OP_IDENTIFIED = 2 };

// obs-websocket close codes after which a client must not reconnect on its own (R05 section 8).
#define CLOSE_AUTHENTICATION_FAILED 4009
#define CLOSE_UNSUPPORTED_RPC_VERSION 4010
#define CLOSE_SESSION_INVALIDATED 4011

static const uint16_t RETRY_WAITS_MS[] = {500, 1000, 2000};
#define RETRY_STEPS (sizeof RETRY_WAITS_MS / sizeof RETRY_WAITS_MS[0])

#define AUTH_LEN CRYPTO_BASE64_LEN(CRYPTO_SHA256_LEN)
// The Identify with an auth string is 119 bytes (R05 section 2).
#define IDENTIFY_MAX 160
// A plain decimal field the pad reads: "1", "1118". Longer means not one the pad expects.
#define SMALL_NUMBER_DIGITS 9

// The compiler may drop a memset of a buffer that dies next. Writes through volatile stay.
static void wipe(void *bytes, size_t len) {
	volatile uint8_t *byte = bytes;
	while (len--) {
		*byte++ = 0;
	}
}

static bool is_stopped_status(obs_status_t status) {
	return status == OBS_NO_PASSWORD || status == OBS_WRONG_PASSWORD || status == OBS_TOO_OLD ||
	       status == OBS_RPC_REFUSED || status == OBS_KICKED;
}

// "1" as 1. -1 for anything but 1 to SMALL_NUMBER_DIGITS decimal digits.
static int32_t small_number(const char *text, size_t len) {
	if (len == 0 || len > SMALL_NUMBER_DIGITS) {
		return -1;
	}
	int32_t number = 0;
	for (size_t i = 0; i < len; i++) {
		if (text[i] < '0' || text[i] > '9') {
			return -1;
		}
		number = number * 10 + (text[i] - '0');
	}
	return number;
}

static void copy_field(obs_message_t *message, char *field, size_t cap, const json_event_t *event) {
	if (event->kind != JSON_STRING || event->truncated || event->len >= cap ||
	    memchr(event->text, '\0', event->len) != NULL) {
		message->bad_field = true;
		return;
	}
	memcpy(field, event->text, event->len + 1);
}

static void read_number(obs_message_t *message, int32_t *field, const json_event_t *event) {
	*field = event->kind == JSON_NUMBER ? small_number(event->text, event->len) : -1;
	message->bad_field |= *field < 0;
}

static void read_handshake_field(void *context, const json_event_t *event) {
	obs_message_t *message = context;
	if (json_path_is(event, "op")) {
		read_number(message, &message->op, event);
	} else if (json_path_is(event, "d.obsWebSocketVersion")) {
		copy_field(message, message->version, sizeof message->version, event);
	} else if (json_path_is(event, "d.authentication") && event->kind == JSON_OBJECT_BEGIN) {
		message->has_auth = true;
	} else if (json_path_is(event, "d.authentication.salt")) {
		copy_field(message, message->salt, sizeof message->salt, event);
	} else if (json_path_is(event, "d.authentication.challenge")) {
		copy_field(message, message->challenge, sizeof message->challenge, event);
	} else if (json_path_is(event, "d.negotiatedRpcVersion")) {
		read_number(message, &message->negotiated_rpc_version, event);
	}
}

static void begin_message(obs_t *obs) {
	obs->message = (obs_message_t){.op = -1, .negotiated_rpc_version = -1};
	json_reader_init(&obs->reader, read_handshake_field, &obs->message);
}

// Each part has at most 3 digits, so the order of the ranks is the order of the versions.
static uint32_t version_rank(unsigned major, unsigned minor, unsigned patch) {
	return major * 1000000u + minor * 1000u + patch;
}

// "5.4.0" and later. Anything but three dot-separated decimal numbers is not.
static bool version_is_supported(const char *version) {
	unsigned major, minor, patch;
	int end = 0;
	if (sscanf(version, "%3u.%3u.%3u%n", &major, &minor, &patch, &end) != 3 ||
	    version[end] != '\0' || strspn(version, "0123456789.") != strlen(version)) {
		return false;
	}
	return version_rank(major, minor, patch) >=
	       version_rank(OBS_MIN_MAJOR, OBS_MIN_MINOR, OBS_MIN_PATCH);
}

static void schedule_retry(obs_t *obs, uint32_t now_ms) {
	obs->status = obs->status == OBS_UP ? OBS_CONNECTING : OBS_UNREACHABLE;
	obs->step = STEP_WAIT;
	obs->retry_wait_started_ms = now_ms;
}

static void dial(obs_t *obs, uint32_t now_ms) {
	if (ws_open(&obs->ws, obs->ip, obs->port, now_ms) == WS_OK) {
		obs->step = STEP_DIAL;
	} else {
		schedule_retry(obs, now_ms);
	}
}

static void on_closed(obs_t *obs, uint16_t code, uint32_t now_ms);

// Drops the link. A stopped `status` stays once the link is down; any other gets a retry.
static void drop(obs_t *obs, obs_status_t status, uint16_t code, uint32_t now_ms) {
	obs->status = status;
	obs->step = STEP_CLOSING;
	if (ws_close(&obs->ws, code, now_ms) == WS_NOT_OPEN) {
		on_closed(obs, WS_CLOSE_ABNORMAL, now_ms);
	}
}

static void stop(obs_t *obs, obs_status_t status, uint32_t now_ms) {
	drop(obs, status, WS_CLOSE_NORMAL, now_ms);
}

// base64(sha256(base64(sha256(password + salt)) + challenge)), R05 section 3. The middle
// string opens OBS until its next start, so it is wiped.
static void make_auth(const obs_t *obs, char auth[AUTH_LEN + 1]) {
	crypto_sha256_t sha;
	uint8_t digest[CRYPTO_SHA256_LEN];
	char secret[AUTH_LEN + 1];
	crypto_sha256_init(&sha);
	crypto_sha256_update(&sha, obs->password, obs->password_len);
	crypto_sha256_update(&sha, obs->message.salt, strlen(obs->message.salt));
	crypto_sha256_final(&sha, digest);
	crypto_base64_encode(digest, sizeof digest, secret);
	crypto_sha256_init(&sha);
	crypto_sha256_update(&sha, secret, AUTH_LEN);
	crypto_sha256_update(&sha, obs->message.challenge, strlen(obs->message.challenge));
	crypto_sha256_final(&sha, digest);
	crypto_base64_encode(digest, sizeof digest, auth);
	wipe(secret, sizeof secret);
	wipe(digest, sizeof digest);
}

static void send_identify(obs_t *obs) {
	char identify[IDENTIFY_MAX];
	int len;
	if (obs->message.has_auth) {
		char auth[AUTH_LEN + 1];
		make_auth(obs, auth);
		len = snprintf(identify, sizeof identify,
		               "{\"op\":%d,\"d\":{\"rpcVersion\":%d,\"authentication\":\"%s\","
		               "\"eventSubscriptions\":%d}}",
		               OP_IDENTIFY, OBS_RPC_VERSION, auth, OBS_EVENT_SUBSCRIPTIONS);
		wipe(auth, sizeof auth);
	} else {
		len = snprintf(identify, sizeof identify,
		               "{\"op\":%d,\"d\":{\"rpcVersion\":%d,\"eventSubscriptions\":%d}}",
		               OP_IDENTIFY, OBS_RPC_VERSION, OBS_EVENT_SUBSCRIPTIONS);
	}
	// A failed send drops the link, and the next ws_poll reports the close.
	ws_send_text(&obs->ws, identify, (size_t)len);
	wipe(identify, sizeof identify);
	obs->step = STEP_IDENTIFIED;
}

static void on_hello(obs_t *obs, uint32_t now_ms) {
	const obs_message_t *hello = &obs->message;
	bool auth_complete = hello->salt[0] != '\0' && hello->challenge[0] != '\0';
	if (hello->op != OP_HELLO || (hello->has_auth && !auth_complete)) {
		drop(obs, obs->status, WS_CLOSE_PROTOCOL_ERROR, now_ms);
	} else if (!version_is_supported(hello->version)) {
		stop(obs, OBS_TOO_OLD, now_ms);
	} else if (hello->has_auth && obs->password == NULL) {
		stop(obs, OBS_NO_PASSWORD, now_ms);
	} else {
		send_identify(obs);
	}
}

static void on_identified(obs_t *obs, uint32_t now_ms) {
	if (obs->message.op != OP_IDENTIFIED) {
		drop(obs, obs->status, WS_CLOSE_PROTOCOL_ERROR, now_ms);
	} else if (obs->message.negotiated_rpc_version != OBS_RPC_VERSION) {
		stop(obs, OBS_RPC_REFUSED, now_ms);
	} else {
		obs->status = OBS_UP;
		obs->step = STEP_UP;
		obs->retry_step = 0;
	}
}

// A bad field fails only the message it is in, as broken JSON does.
static void on_data(obs_t *obs, const ws_event_t *event, uint32_t now_ms) {
	if (obs->step != STEP_HELLO && obs->step != STEP_IDENTIFIED) {
		return; // task 2.8 reads the requests and events after Identified
	}
	json_status_t status = json_feed(&obs->reader, event->bytes, event->len);
	if (!event->message_end) {
		return;
	}
	if (status != JSON_DONE || obs->message.bad_field) {
		drop(obs, obs->status, WS_CLOSE_PROTOCOL_ERROR, now_ms);
	} else if (obs->step == STEP_HELLO) {
		on_hello(obs, now_ms);
	} else {
		on_identified(obs, now_ms);
	}
	begin_message(obs);
}

static void on_closed(obs_t *obs, uint16_t code, uint32_t now_ms) {
	if (code == CLOSE_AUTHENTICATION_FAILED) {
		obs->status = OBS_WRONG_PASSWORD;
	} else if (code == CLOSE_UNSUPPORTED_RPC_VERSION) {
		obs->status = OBS_RPC_REFUSED;
	} else if (code == CLOSE_SESSION_INVALIDATED) {
		obs->status = OBS_KICKED;
	}
	if (is_stopped_status(obs->status)) {
		obs->step = STEP_STOPPED;
	} else {
		schedule_retry(obs, now_ms);
	}
}

void obs_init(obs_t *obs, stream_t *stream, ws_random_t next_random) {
	*obs = (obs_t){.status = OBS_IDLE, .step = STEP_IDLE};
	ws_init(&obs->ws, stream, next_random);
	begin_message(obs);
}

bool obs_start(obs_t *obs, const uint8_t ip[4], uint16_t port, const char *password,
               size_t password_len, uint32_t now_ms) {
	if (obs->step != STEP_IDLE && obs->step != STEP_STOPPED) {
		return false;
	}
	memcpy(obs->ip, ip, sizeof obs->ip);
	obs->port = port;
	obs->password = password;
	obs->password_len = password_len;
	obs->status = OBS_CONNECTING;
	obs->retry_step = 0;
	dial(obs, now_ms);
	return true;
}

static void poll_wait(obs_t *obs, uint32_t now_ms) {
	uint16_t wait_ms = RETRY_WAITS_MS[obs->retry_step];
	// Unsigned difference: the wait ends on time when the millisecond clock wraps.
	if (now_ms - obs->retry_wait_started_ms < wait_ms) {
		return;
	}
	if (obs->retry_step < RETRY_STEPS - 1) {
		obs->retry_step++;
	}
	dial(obs, now_ms);
}

void obs_poll(obs_t *obs, uint32_t now_ms) {
	if (obs->step == STEP_IDLE || obs->step == STEP_STOPPED) {
		return;
	}
	if (obs->step == STEP_WAIT) {
		poll_wait(obs, now_ms);
		return;
	}
	ws_event_t event = ws_poll(&obs->ws, now_ms);
	if (event.kind == WS_EVT_OPEN) {
		obs->step = STEP_HELLO;
		begin_message(obs);
	} else if (event.kind == WS_EVT_DATA) {
		on_data(obs, &event, now_ms);
	} else if (event.kind == WS_EVT_CLOSED) {
		on_closed(obs, event.close_code, now_ms);
	}
}

enum link_obs_state obs_link_state(obs_status_t status) {
	switch (status) {
	case OBS_IDLE:
		return LINK_OBS_IDLE;
	case OBS_CONNECTING:
		return LINK_OBS_CONNECTING;
	case OBS_NO_PASSWORD:
	case OBS_WRONG_PASSWORD:
		return LINK_OBS_AUTH_FAILED;
	case OBS_UP:
		return LINK_OBS_UP;
	case OBS_UNREACHABLE:
	case OBS_TOO_OLD:
	case OBS_RPC_REFUSED:
	case OBS_KICKED:
		break;
	}
	return LINK_OBS_REFUSED;
}

const char *obs_strip_line(obs_status_t status) {
	switch (status) {
	case OBS_UNREACHABLE:
		return "OBS unreachable";
	case OBS_NO_PASSWORD:
		return "OBS password not set";
	case OBS_WRONG_PASSWORD:
		return "Wrong OBS password";
	case OBS_TOO_OLD:
		return "OBS too old, need 30.1";
	case OBS_RPC_REFUSED:
		return "OBS refused protocol";
	case OBS_KICKED:
		return "OBS closed session";
	case OBS_IDLE:
	case OBS_CONNECTING:
	case OBS_UP:
		break;
	}
	return NULL;
}
