// SPDX-License-Identifier: MIT
#include "link.h"

#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_VECTORS 128
#define READ_LEN 64
#define STREAM_CAP 4096
#define FRAMES_BEHIND 40

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

typedef struct {
	char name[32];
	uint8_t bytes[LINK_MAX_FRAME];
	size_t len;
} vector_t;

typedef struct {
	uint8_t bytes[STREAM_CAP];
	size_t len;
} stream_t;

static vector_t vectors[MAX_VECTORS];
static size_t vector_count;

static void die(const char *what, const char *name) {
	fprintf(stderr, "%s %s\n", what, name);
	exit(2);
}

static void load_vector_line(char *line) {
	char *tok = strtok(line, " \t\n");
	if (tok == NULL || tok[0] == '#') {
		return;
	}
	if (vector_count >= MAX_VECTORS || strlen(tok) >= sizeof vectors[0].name) {
		die("no room for vector", tok);
	}
	vector_t *v = &vectors[vector_count++];
	strcpy(v->name, tok);
	while ((tok = strtok(NULL, " \t\n")) != NULL) {
		if (v->len >= sizeof v->bytes) {
			die("vector too long", v->name);
		}
		v->bytes[v->len++] = (uint8_t)strtoul(tok, NULL, 16);
	}
}

static void load_vectors(void) {
	FILE *f = fopen(VECTORS, "r");
	char line[1024];
	if (f == NULL) {
		die("cannot open", VECTORS);
	}
	while (fgets(line, sizeof line, f)) {
		load_vector_line(line);
	}
	fclose(f);
}

static const vector_t *vector(const char *name) {
	for (size_t i = 0; i < vector_count; i++) {
		if (strcmp(vectors[i].name, name) == 0) {
			return &vectors[i];
		}
	}
	die("vector missing", name);
	return NULL;
}

static bool refused(const vector_t *v) {
	return strncmp(v->name, "refuse_", 7) == 0;
}

// What the codec must hand back for a vector: the frame itself, or the reply to a refused one.
static const vector_t *answer(const vector_t *v) {
	char name[sizeof v->name];
	if (!refused(v)) {
		return v;
	}
	snprintf(name, sizeof name, "reply_%s", v->name + 7);
	return vector(name);
}

static void append(stream_t *s, const uint8_t *data, size_t n) {
	if (s->len + n > sizeof s->bytes) {
		die("stream full", "append");
	}
	memcpy(s->bytes + s->len, data, n);
	s->len += n;
}

static void append_frame(stream_t *s, const link_frame_t *frame) {
	uint8_t raw[LINK_MAX_FRAME];
	size_t n = link_encode(frame, raw, sizeof raw);
	CHECK(n > 0);
	append(s, raw, n);
}

// Drains the parser. Every frame and every reply is written to `seen`, encoded again.
static int drain(link_rx_t *rx, stream_t *seen) {
	link_frame_t frame;
	int pulled = 0;
	while (link_pull(rx, &frame) != LINK_EMPTY) {
		append_frame(seen, &frame);
		pulled++;
	}
	return pulled;
}

// Feeds `in` the way the USB task does: reads of `read_len`, pull until empty, push the rest.
static void pump(link_rx_t *rx, const stream_t *in, size_t read_len, stream_t *seen) {
	size_t at = 0;
	while (at < in->len) {
		size_t end = at + read_len < in->len ? at + read_len : in->len;
		while (at < end) {
			size_t took = link_rx_push(rx, in->bytes + at, end - at);
			at += took;
			if (drain(rx, seen) == 0 && took == 0) {
				die("parser stalled", "pump");
			}
		}
	}
}

static bool same(const stream_t *a, const stream_t *b) {
	return a->len == b->len && memcmp(a->bytes, b->bytes, a->len) == 0;
}

static link_frame_t filled_frame(uint16_t length) {
	link_frame_t frame = {.type = 0x7F, .id = 0x33, .length = length};
	for (uint16_t i = 0; i < length; i++) {
		frame.payload[i] = (uint8_t)(i * 7u + 1u);
	}
	return frame;
}

static void test_crc_check_value(void) {
	const uint8_t text[] = "123456789";
	CHECK(link_crc(text, 9) == 0x4B37);
}

static void test_good_vector_gives_type_id_and_payload(void) {
	const vector_t *v = vector("payload_3");
	link_rx_t rx;
	link_frame_t frame;
	link_rx_init(&rx);
	CHECK(link_rx_push(&rx, v->bytes, v->len) == v->len);
	CHECK(link_pull(&rx, &frame) == LINK_FRAME);
	CHECK(frame.type == 0x7F && frame.id == 0x09 && frame.length == 3);
	CHECK(frame.payload[0] == 1 && frame.payload[1] == 2 && frame.payload[2] == 3);
	CHECK(link_pull(&rx, &frame) == LINK_EMPTY);
}

static void test_every_vector_decodes_alone(void) {
	for (size_t i = 0; i < vector_count; i++) {
		const vector_t *v = &vectors[i];
		const vector_t *want = answer(v);
		link_rx_t rx;
		link_frame_t frame;
		uint8_t raw[LINK_MAX_FRAME];
		link_rx_init(&rx);
		CHECK(link_rx_push(&rx, v->bytes, v->len) == v->len);
		CHECK(link_pull(&rx, &frame) == (refused(v) ? LINK_REPLY : LINK_FRAME));
		size_t n = link_encode(&frame, raw, sizeof raw);
		CHECK(n == want->len && memcmp(raw, want->bytes, n) == 0);
		CHECK(link_pull(&rx, &frame) == LINK_EMPTY);
	}
}

static void test_refusals_carry_the_type_and_code(void) {
	link_rx_t rx;
	link_frame_t frame;
	const vector_t *v = vector("refuse_too_big");
	link_rx_init(&rx);
	link_rx_push(&rx, v->bytes, v->len);
	CHECK(link_pull(&rx, &frame) == LINK_REPLY);
	CHECK(frame.type == LINK_RESULT && frame.id == 0x07);
	CHECK(frame.payload[0] == LINK_RESULT_TOO_BIG);

	v = vector("refuse_bad_crc");
	link_rx_init(&rx);
	link_rx_push(&rx, v->bytes, v->len);
	CHECK(link_pull(&rx, &frame) == LINK_REPLY);
	CHECK(frame.type == LINK_RESULT && frame.id == 0x09);
	CHECK(frame.payload[0] == LINK_RESULT_BAD_CRC);

	v = vector("refuse_v1_key");
	link_rx_init(&rx);
	link_rx_push(&rx, v->bytes, v->len);
	CHECK(link_pull(&rx, &frame) == LINK_REPLY);
	CHECK(frame.type == LINK_NOTICE && frame.id == 0);
}

// Spec 11 fw-link: every vector in one stream, the first one at each offset of a 64-byte read.
static void test_all_vectors_at_all_64_read_alignments(void) {
	static stream_t in, want, seen;
	for (size_t lead = 0; lead < READ_LEN; lead++) {
		memset(&in, 0, sizeof in);
		want.len = 0;
		seen.len = 0;
		in.len = lead;
		for (size_t i = 0; i < vector_count; i++) {
			const vector_t *reply = answer(&vectors[i]);
			append(&in, vectors[i].bytes, vectors[i].len);
			append(&want, reply->bytes, reply->len);
		}
		link_rx_t rx;
		link_rx_init(&rx);
		pump(&rx, &in, READ_LEN, &seen);
		CHECK(same(&seen, &want));
	}
}

static void test_all_vectors_one_byte_at_a_time(void) {
	static stream_t in, want, seen;
	for (size_t i = 0; i < vector_count; i++) {
		const vector_t *reply = answer(&vectors[i]);
		append(&in, vectors[i].bytes, vectors[i].len);
		append(&want, reply->bytes, reply->len);
	}
	link_rx_t rx;
	link_rx_init(&rx);
	pump(&rx, &in, 1, &seen);
	CHECK(same(&seen, &want));
}

// docs/research/02-repo-inventory.md: the v1 parser lost the head of a 247-byte frame with
// traffic behind it at 54 of 64 read alignments, and dropped frames past the caller's cap.
static void big_frame_keeps_its_head(uint16_t payload_len) {
	static stream_t in, want, seen;
	link_frame_t big = filled_frame(payload_len);
	const vector_t *small = vector("empty_payload");
	for (size_t lead = 0; lead < READ_LEN; lead++) {
		memset(&in, 0, sizeof in);
		want.len = 0;
		seen.len = 0;
		in.len = lead;
		append_frame(&want, &big);
		for (int i = 0; i < FRAMES_BEHIND; i++) {
			append(&want, small->bytes, small->len);
		}
		append(&in, want.bytes, want.len);
		link_rx_t rx;
		link_rx_init(&rx);
		pump(&rx, &in, READ_LEN, &seen);
		CHECK(same(&seen, &want));
	}
}

static void test_247_byte_frame_keeps_its_head(void) {
	CHECK(LINK_HEADER_LEN + 239 + LINK_CRC_LEN == 247);
	big_frame_keeps_its_head(239);
}

static void test_largest_frame_keeps_its_head(void) {
	CHECK(LINK_MAX_FRAME == 248);
	big_frame_keeps_its_head(LINK_MAX_PAYLOAD);
}

static void test_cut_frame_is_answered_and_the_next_frame_survives(void) {
	static stream_t in, want, seen;
	const vector_t *cut = vector("payload_3");
	const vector_t *next = vector("empty_payload");
	const vector_t *reply = vector("reply_bad_crc");
	append(&in, cut->bytes, LINK_HEADER_LEN + 1);
	append(&in, next->bytes, next->len);
	append(&want, reply->bytes, reply->len);
	append(&want, next->bytes, next->len);
	link_rx_t rx;
	link_rx_init(&rx);
	pump(&rx, &in, READ_LEN, &seen);
	CHECK(same(&seen, &want));
}

static void test_push_takes_only_what_fits(void) {
	uint8_t raw[LINK_MAX_FRAME + 1] = {0};
	link_frame_t big = filled_frame(LINK_MAX_PAYLOAD);
	link_frame_t frame;
	link_rx_t rx;
	link_rx_init(&rx);
	CHECK(link_encode(&big, raw, sizeof raw) == LINK_MAX_FRAME);
	CHECK(link_rx_push(&rx, raw, sizeof raw) == LINK_MAX_FRAME);
	CHECK(link_rx_push(&rx, raw, 1) == 0);
	CHECK(link_pull(&rx, &frame) == LINK_FRAME);
	CHECK(frame.length == LINK_MAX_PAYLOAD);
	CHECK(memcmp(frame.payload, big.payload, LINK_MAX_PAYLOAD) == 0);
}

static void test_encode_refuses_what_does_not_fit(void) {
	uint8_t raw[LINK_MAX_FRAME];
	link_frame_t frame = filled_frame(3);
	CHECK(link_encode(&frame, raw, LINK_HEADER_LEN + 3 + LINK_CRC_LEN - 1) == 0);
	frame.length = LINK_MAX_PAYLOAD + 1;
	CHECK(link_encode(&frame, raw, sizeof raw) == 0);
}

static bool named(const vector_t *v, const char *prefix) {
	return strncmp(v->name, prefix, strlen(prefix)) == 0;
}

static link_frame_t pulled_frame(const vector_t *v) {
	link_rx_t rx;
	link_frame_t frame;
	link_rx_init(&rx);
	link_rx_push(&rx, v->bytes, v->len);
	if (link_pull(&rx, &frame) == LINK_EMPTY) {
		die("vector is not a whole frame", v->name);
	}
	return frame;
}

// The span points into `frame`, so the caller keeps the frame alive.
static link_msg_t decoded(const char *name, link_frame_t *frame) {
	link_msg_t msg;
	*frame = pulled_frame(vector(name));
	if (!link_msg_decode(frame, &msg)) {
		die("message refused", name);
	}
	return msg;
}

static bool span_is(link_span_t span, const char *text) {
	return span.len == strlen(text) && memcmp(span.bytes, text, span.len) == 0;
}

static link_span_t span_of(const uint8_t *bytes, size_t len) {
	return (link_span_t){.bytes = bytes, .len = len};
}

static void test_every_msg_vector_decodes_and_encodes_back(void) {
	int seen = 0;
	for (size_t i = 0; i < vector_count; i++) {
		const vector_t *v = &vectors[i];
		if (!named(v, "msg_")) {
			continue;
		}
		link_frame_t frame = pulled_frame(v);
		link_frame_t again;
		link_msg_t msg;
		uint8_t raw[LINK_MAX_FRAME];
		CHECK(link_msg_decode(&frame, &msg));
		CHECK(msg.type == frame.type);
		CHECK(link_msg_encode(&msg, frame.id, &again));
		size_t n = link_encode(&again, raw, sizeof raw);
		CHECK(n == v->len && memcmp(raw, v->bytes, n) == 0);
		seen++;
	}
	CHECK(seen == 25);
}

static void test_every_bad_vector_is_refused_by_the_typed_decoder(void) {
	int seen = 0;
	for (size_t i = 0; i < vector_count; i++) {
		const vector_t *v = &vectors[i];
		if (!named(v, "bad_")) {
			continue;
		}
		link_frame_t frame = pulled_frame(v);
		link_msg_t msg;
		CHECK(!link_msg_decode(&frame, &msg));
		seen++;
	}
	CHECK(seen == 35);
}

static void test_an_unknown_type_is_refused(void) {
	link_frame_t frame = pulled_frame(vector("payload_3"));
	link_msg_t msg;
	CHECK(!link_msg_decode(&frame, &msg));
}

static void test_request_vectors_carry_these_fields(void) {
	link_frame_t frame;
	link_msg_t msg = decoded("msg_info_get", &frame);
	CHECK(msg.type == LINK_INFO_GET && frame.id == 0x10);

	msg = decoded("msg_cfg_read", &frame);
	CHECK(msg.type == LINK_CFG_READ);
	CHECK(msg.as.cfg_read.offset == 0 && msg.as.cfg_read.len == LINK_CFG_DATA_MAX);

	msg = decoded("msg_cfg_begin", &frame);
	CHECK(msg.type == LINK_CFG_BEGIN);
	CHECK(msg.as.cfg_begin.base_seq == 7 && msg.as.cfg_begin.total == 20);
	CHECK(msg.as.cfg_begin.crc32 == 0xCA7AE782u && !msg.as.cfg_begin.try_only);

	msg = decoded("msg_cfg_begin_try", &frame);
	CHECK(msg.as.cfg_begin.base_seq == 7 && msg.as.cfg_begin.try_only);

	msg = decoded("msg_cfg_chunk", &frame);
	CHECK(msg.type == LINK_CFG_CHUNK && msg.as.cfg_chunk.offset == 0);
	CHECK(span_is(msg.as.cfg_chunk.bytes, "{\"schema\":1,\"seq\":7}"));

	msg = decoded("msg_cfg_commit", &frame);
	CHECK(msg.type == LINK_CFG_COMMIT && frame.id == 0x15);
}

static void test_info_vector_carries_these_fields(void) {
	static const uint8_t git_hash[] = {0x00, 0xC0, 0xFF, 0xEE};
	static const uint8_t unique_id[] = {0x02, 0x00, 0x00, 0x00, 0x00, 0x01};
	link_frame_t frame;
	link_msg_t msg = decoded("msg_info", &frame);
	const link_info_t *info = &msg.as.info;
	CHECK(msg.type == LINK_INFO && info->proto == LINK_VERSION);
	CHECK(info->obs_password_set && !info->wifi_psk_set);
	CHECK(info->schema_min == 1 && info->schema_max == 1 && info->max_doc_bytes == 16384);
	CHECK(info->keys == 9 && info->buttons == 4 && info->knobs == 3);
	CHECK(info->main_display.width == 320 && info->main_display.height == 480);
	CHECK(info->strip_display.width == 142 && info->strip_display.height == 428);
	CHECK(info->capabilities == 0 && info->board_rev == 1);
	CHECK(memcmp(info->git_hash, git_hash, sizeof git_hash) == 0);
	CHECK(memcmp(info->unique_id, unique_id, sizeof unique_id) == 0);
	CHECK(span_is(info->fw_version, "0.2.0"));

	msg = decoded("msg_info_wifi_psk", &frame);
	CHECK(!msg.as.info.obs_password_set && msg.as.info.wifi_psk_set);
}

static int bits_changed(const link_frame_t *a, const link_frame_t *b) {
	int changed = 0;
	CHECK(a->length == b->length);
	for (uint16_t i = 0; i < a->length; i++) {
		changed += __builtin_popcount((unsigned)(a->payload[i] ^ b->payload[i]));
	}
	return changed;
}

// Acceptance of task 1.7: a stored credential moves one bit of INFO and nothing else.
static void test_info_carries_each_credential_as_one_bit(void) {
	link_frame_t frame, unset, obs_set, wifi_set;
	link_msg_t msg = decoded("msg_info", &frame);
	msg.as.info.obs_password_set = false;
	msg.as.info.wifi_psk_set = false;
	CHECK(link_msg_encode(&msg, 1, &unset));
	msg.as.info.obs_password_set = true;
	CHECK(link_msg_encode(&msg, 1, &obs_set));
	msg.as.info.obs_password_set = false;
	msg.as.info.wifi_psk_set = true;
	CHECK(link_msg_encode(&msg, 1, &wifi_set));
	CHECK(bits_changed(&unset, &obs_set) == 1);
	CHECK(bits_changed(&unset, &wifi_set) == 1);
	CHECK(bits_changed(&obs_set, &wifi_set) == 2);
}

static void test_reply_vectors_carry_these_fields(void) {
	link_frame_t frame;
	link_msg_t msg = decoded("msg_cfg_data", &frame);
	CHECK(msg.type == LINK_CFG_DATA && msg.as.cfg_data.seq == 7);
	CHECK(msg.as.cfg_data.total == 20 && msg.as.cfg_data.offset == 0);
	CHECK(span_is(msg.as.cfg_data.bytes, "{\"schema\":1,\"seq\":7}"));

	msg = decoded("msg_cfg_data_empty", &frame);
	CHECK(msg.as.cfg_data.total == 0 && msg.as.cfg_data.bytes.len == 0);

	msg = decoded("msg_result_ok", &frame);
	CHECK(msg.type == LINK_RESULT && msg.as.result.code == LINK_RESULT_OK);
	CHECK(msg.as.result.seq == 8 && msg.as.result.path.len == 0);

	msg = decoded("msg_result_busy", &frame);
	CHECK(msg.as.result.code == LINK_RESULT_BUSY);
	msg = decoded("msg_result_stale_seq", &frame);
	CHECK(msg.as.result.code == LINK_RESULT_STALE_SEQ && msg.as.result.seq == 9);
	msg = decoded("reply_bad_crc", &frame);
	CHECK(msg.as.result.code == LINK_RESULT_BAD_CRC && msg.as.result.seq == 0);
	msg = decoded("reply_too_big", &frame);
	CHECK(msg.as.result.code == LINK_RESULT_TOO_BIG);

	msg = decoded("msg_result_invalid", &frame);
	CHECK(msg.as.result.code == LINK_RESULT_INVALID && msg.as.result.seq == 7);
	CHECK(span_is(msg.as.result.path, "obs.url"));
}

static const struct {
	const char *prefix;
	uint8_t status;
} CRED_NAMES[] = {
	{"cred_ok_", LINK_CRED_OK},
	{"cred_bad_kind_", LINK_CRED_BAD_KIND},
	{"cred_bad_len_", LINK_CRED_BAD_LEN},
	{"cred_bad_value_", LINK_CRED_BAD_VALUE},
};

// The status a `cred_<status>_<x>` vector names.
static uint8_t named_cred_status(const vector_t *v) {
	for (size_t i = 0; i < sizeof CRED_NAMES / sizeof CRED_NAMES[0]; i++) {
		if (named(v, CRED_NAMES[i].prefix)) {
			return CRED_NAMES[i].status;
		}
	}
	die("no status in the name of", v->name);
	return 0;
}

// Spec 8.2: one reject vector per rule. The typed decoder takes a credential frame only when ok.
static void test_every_cred_vector_gets_the_status_in_its_name(void) {
	int seen = 0;
	for (size_t i = 0; i < vector_count; i++) {
		const vector_t *v = &vectors[i];
		if (!named(v, "cred_")) {
			continue;
		}
		uint8_t want = named_cred_status(v);
		link_frame_t frame = pulled_frame(v);
		link_frame_t again;
		link_msg_t msg;
		CHECK(link_credential_check(&frame) == want);
		CHECK(link_msg_decode(&frame, &msg) == (want == LINK_CRED_OK));
		if (want == LINK_CRED_OK) {
			CHECK(link_msg_encode(&msg, frame.id, &again));
			CHECK(again.length == frame.length);
			CHECK(memcmp(again.payload, frame.payload, frame.length) == 0);
		}
		seen++;
	}
	CHECK(seen == 15);
}

static void test_credential_vectors_carry_these_fields(void) {
	link_frame_t frame;
	link_msg_t msg = decoded("cred_ok_obs", &frame);
	CHECK(msg.type == LINK_SET_CREDENTIAL);
	CHECK(msg.as.set_credential.kind == LINK_CREDENTIAL_OBS_PASSWORD);
	CHECK(span_is(msg.as.set_credential.bytes, "dummy-obs-password"));

	msg = decoded("cred_ok_wifi_8", &frame);
	CHECK(msg.as.set_credential.kind == LINK_CREDENTIAL_WIFI_PASSPHRASE);
	CHECK(span_is(msg.as.set_credential.bytes, "dummy-pw"));

	msg = decoded("cred_ok_clear", &frame);
	CHECK(msg.type == LINK_CLEAR_CREDENTIALS && frame.length == 0);
}

// Spec 8.2: 239 is the payload cap less the kind byte. A 240-byte password has no frame (8.1).
static void test_an_obs_password_stops_at_239_bytes(void) {
	static const uint8_t dummy[LINK_CREDENTIAL_MAX + 1] = {0};
	link_frame_t frame;
	link_msg_t msg = decoded("cred_ok_obs_239", &frame);
	CHECK(LINK_CREDENTIAL_MAX == 239 && msg.as.set_credential.bytes.len == LINK_CREDENTIAL_MAX);
	CHECK(frame.length == LINK_MAX_PAYLOAD);

	msg.as.set_credential.bytes = span_of(dummy, LINK_CREDENTIAL_MAX + 1);
	CHECK(!link_msg_encode(&msg, 1, &frame));

	frame = pulled_frame(vector("refuse_cred_240"));
	CHECK(frame.type == LINK_RESULT && frame.id == 0x4F);
	CHECK(frame.payload[0] == LINK_RESULT_TOO_BIG);
}

// Spec 8.2: a 32-bit magic each, so no single flipped bit erases the pad.
static void test_a_wrong_magic_is_refused(void) {
	static const char *const MAGIC_VECTORS[] = {"msg_factory_reset", "msg_bootloader"};
	for (size_t i = 0; i < sizeof MAGIC_VECTORS / sizeof MAGIC_VECTORS[0]; i++) {
		link_frame_t frame = pulled_frame(vector(MAGIC_VECTORS[i]));
		link_msg_t msg;
		CHECK(frame.length == 4 && link_msg_decode(&frame, &msg));
		for (int bit = 0; bit < 32; bit++) {
			link_frame_t flipped = frame;
			flipped.payload[bit / 8] ^= (uint8_t)(1u << (bit % 8));
			CHECK(!link_msg_decode(&flipped, &msg));
		}
	}
	link_frame_t reset = pulled_frame(vector("msg_factory_reset"));
	link_frame_t boot = pulled_frame(vector("msg_bootloader"));
	CHECK(reset.type == LINK_FACTORY_RESET && boot.type == LINK_BOOTLOADER);
	CHECK(memcmp(reset.payload, "WIPE", 4) == 0 && memcmp(boot.payload, "BOOT", 4) == 0);
}

static void test_status_and_list_vectors_carry_these_fields(void) {
	static const uint8_t ip[] = {192, 168, 1, 50};
	static const uint8_t uuid[LINK_UUID_LEN] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
	                                            0x88, 0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF};
	link_frame_t frame;
	link_msg_t msg = decoded("msg_cred_status_store_fail", &frame);
	CHECK(msg.type == LINK_CRED_STATUS && msg.as.cred_status.code == LINK_CRED_STORE_FAIL);

	msg = decoded("msg_status_up", &frame);
	CHECK(msg.type == LINK_STATUS && msg.as.status.obs_state == LINK_OBS_UP);
	CHECK(msg.as.status.wifi_state == LINK_WIFI_UP && msg.as.status.rssi_dbm == -52);
	CHECK(memcmp(msg.as.status.ip, ip, sizeof ip) == 0);
	msg = decoded("msg_status_no_ssid", &frame);
	CHECK(msg.as.status.obs_state == LINK_OBS_IDLE && msg.as.status.wifi_state == LINK_WIFI_NO_SSID);

	msg = decoded("msg_obs_list", &frame);
	CHECK(msg.type == LINK_OBS_LIST && msg.as.obs_list.list == LINK_LIST_SCENES);
	CHECK(msg.as.obs_list.index == 0);

	msg = decoded("msg_obs_item", &frame);
	CHECK(msg.type == LINK_OBS_ITEM && msg.as.obs_item.list == LINK_LIST_SCENES);
	CHECK(msg.as.obs_item.index == 0 && msg.as.obs_item.total == 2);
	CHECK(memcmp(msg.as.obs_item.uuid, uuid, sizeof uuid) == 0);
	CHECK(span_is(msg.as.obs_item.name, "Cam\xC3\xA9ra"));
	msg = decoded("msg_obs_item_none", &frame);
	CHECK(msg.as.obs_item.list == LINK_LIST_TRANSITIONS && msg.as.obs_item.total == 0);
	CHECK(msg.as.obs_item.name.len == 0);

	msg = decoded("msg_input_key", &frame);
	CHECK(msg.type == LINK_INPUT && msg.as.input.source == LINK_INPUT_KEY);
	CHECK(msg.as.input.index == 4 && msg.as.input.value == 1);
	msg = decoded("msg_input_turn", &frame);
	CHECK(msg.as.input.source == LINK_INPUT_KNOB_TURN && msg.as.input.index == 2);
	CHECK(msg.as.input.value == -1);
}

// R1: every pad-to-app type the typed codec knows, a vector of it, the fixed payload bytes, and
// the one byte run that may follow them. NOTICE is the codec's own fixed text and has no fields.
typedef struct {
	uint8_t type;
	const char *sample;
	uint16_t fixed_len;
	const char *run; // what feeds the bytes after the fixed part. NULL: nothing may follow
} pad_type_t;

static const pad_type_t PAD_TYPES[] = {
	{LINK_RESULT, "msg_result_invalid", 5, "path of the first bad config field"},
	{LINK_INFO, "msg_info", 34, "firmware version text"},
	{LINK_CFG_DATA, "msg_cfg_data", 8, "config document bytes: the cfg slot, never `cred`"},
	{LINK_CRED_STATUS, "msg_cred_status_ok", 1, NULL},
	{LINK_STATUS, "msg_status_up", 7, NULL},
	{LINK_OBS_ITEM, "msg_obs_item", 21, "name of an OBS scene, input or transition"},
	{LINK_INPUT, "msg_input_key", 3, NULL},
};
#define PAD_TYPE_COUNT (sizeof PAD_TYPES / sizeof PAD_TYPES[0])

static bool is_listed_pad_type(uint8_t type) {
	for (size_t i = 0; i < PAD_TYPE_COUNT; i++) {
		if (PAD_TYPES[i].type == type) {
			return true;
		}
	}
	return false;
}

// A pad-to-app type that is not in PAD_TYPES must not exist: a new one fails here until it is
// listed and its fields are judged against R1.
static void test_the_pad_to_app_types_are_a_closed_list(void) {
	link_msg_t msg;
	for (unsigned type = 0x80; type <= 0xFF; type++) {
		if (is_listed_pad_type((uint8_t)type)) {
			continue;
		}
		link_frame_t zeros = {.type = (uint8_t)type};
		for (zeros.length = 0; zeros.length <= LINK_MAX_PAYLOAD; zeros.length++) {
			CHECK(!link_msg_decode(&zeros, &msg));
		}
		for (size_t i = 0; i < PAD_TYPE_COUNT; i++) {
			link_frame_t relabelled = pulled_frame(vector(PAD_TYPES[i].sample));
			relabelled.type = (uint8_t)type;
			CHECK(!link_msg_decode(&relabelled, &msg));
		}
	}
}

// No listed type has room for a field the table does not name.
static void test_each_pad_to_app_type_has_only_its_named_bytes(void) {
	link_msg_t msg;
	for (size_t i = 0; i < PAD_TYPE_COUNT; i++) {
		const pad_type_t *pad = &PAD_TYPES[i];
		link_frame_t frame = pulled_frame(vector(pad->sample));
		CHECK(frame.type == pad->type && (frame.type & 0x80u) != 0);
		CHECK(link_msg_decode(&frame, &msg));
		CHECK(pad->run != NULL ? frame.length > pad->fixed_len : frame.length == pad->fixed_len);
		frame.length = pad->fixed_len;
		CHECK(link_msg_decode(&frame, &msg));
		frame.length = (uint16_t)(pad->fixed_len - 1);
		CHECK(!link_msg_decode(&frame, &msg));
		if (pad->run == NULL) {
			frame.length = (uint16_t)(pad->fixed_len + 1);
			frame.payload[pad->fixed_len] = 0;
			CHECK(!link_msg_decode(&frame, &msg));
		}
	}
}

// R1 names two exceptions: bytes that look like a hash or an opaque run, and are neither a
// credential nor made from one. The INFO git hash is the caller's four bytes whatever the two
// credential bits say. The CFG_DATA bytes are the caller's document bytes and nothing else:
// that message has no credential input at all.
static void test_the_git_hash_and_the_document_bytes_are_not_fed_by_a_credential(void) {
	enum { GIT_HASH_AT = 24, DOCUMENT_AT = 8 };
	link_frame_t frame, out;
	link_msg_t msg = decoded("msg_info", &frame);
	for (int flags = 0; flags < 4; flags++) {
		msg.as.info.obs_password_set = (flags & 1) != 0;
		msg.as.info.wifi_psk_set = (flags & 2) != 0;
		CHECK(link_msg_encode(&msg, 1, &out));
		CHECK(memcmp(out.payload + GIT_HASH_AT, msg.as.info.git_hash, LINK_GIT_HASH_LEN) == 0);
	}

	static const uint8_t document[] = "{\"schema\":1,\"seq\":7}";
	link_msg_t data = {.type = LINK_CFG_DATA};
	data.as.cfg_data.bytes = span_of(document, sizeof document - 1);
	CHECK(link_msg_encode(&data, 1, &out));
	CHECK(out.length == DOCUMENT_AT + sizeof document - 1);
	CHECK(memcmp(out.payload + DOCUMENT_AT, document, sizeof document - 1) == 0);
}

// The one answer to a credential is one status byte. It is the same byte for an 8-byte, a
// 63-byte and a 239-byte secret, so it gives away no value, no length and no hash.
static void test_the_credential_reply_is_the_same_for_every_accepted_secret(void) {
	static const char *const ACCEPTED[] = {"cred_ok_obs", "cred_ok_obs_239", "cred_ok_wifi_8",
	                                       "cred_ok_wifi_63", "cred_ok_wifi_hex64"};
	link_frame_t first_reply = {0};
	for (size_t i = 0; i < sizeof ACCEPTED / sizeof ACCEPTED[0]; i++) {
		link_frame_t request = pulled_frame(vector(ACCEPTED[i]));
		link_frame_t reply;
		link_msg_t status = {.type = LINK_CRED_STATUS};
		CHECK((request.type & 0x80u) == 0);
		status.as.cred_status.code = link_credential_check(&request);
		CHECK(link_msg_encode(&status, 1, &reply) && reply.length == 1);
		if (i == 0) {
			first_reply = reply;
		}
		CHECK(reply.payload[0] == first_reply.payload[0]);
	}
}

static void test_chunk_and_data_sizes_stop_at_the_payload_cap(void) {
	static const uint8_t bytes[LINK_CFG_CHUNK_MAX + 1] = {0};
	link_frame_t frame;
	link_msg_t chunk = {.type = LINK_CFG_CHUNK};
	CHECK(LINK_CFG_CHUNK_MAX == 238 && LINK_CFG_DATA_MAX == 232);
	chunk.as.cfg_chunk.bytes = span_of(bytes, LINK_CFG_CHUNK_MAX);
	CHECK(link_msg_encode(&chunk, 1, &frame) && frame.length == LINK_MAX_PAYLOAD);
	chunk.as.cfg_chunk.bytes = span_of(bytes, LINK_CFG_CHUNK_MAX + 1);
	CHECK(!link_msg_encode(&chunk, 1, &frame));

	link_msg_t data = {.type = LINK_CFG_DATA};
	data.as.cfg_data.bytes = span_of(bytes, LINK_CFG_DATA_MAX);
	CHECK(link_msg_encode(&data, 1, &frame) && frame.length == LINK_MAX_PAYLOAD);
	data.as.cfg_data.bytes = span_of(bytes, LINK_CFG_DATA_MAX + 1);
	CHECK(!link_msg_encode(&data, 1, &frame));
}

static void test_encode_refuses_what_decode_refuses(void) {
	static const uint8_t long_path[LINK_PATH_MAX + 1] = "pppppppppppppppppppppppppppppppppppppppppppppppp";
	link_frame_t frame;
	link_msg_t msg = {.type = 0x7F};
	CHECK(!link_msg_encode(&msg, 1, &frame));

	msg = (link_msg_t){.type = LINK_CFG_READ};
	CHECK(!link_msg_encode(&msg, 1, &frame));
	msg.as.cfg_read.len = LINK_CFG_DATA_MAX + 1;
	CHECK(!link_msg_encode(&msg, 1, &frame));

	msg = (link_msg_t){.type = LINK_CFG_CHUNK};
	CHECK(!link_msg_encode(&msg, 1, &frame));

	msg = (link_msg_t){.type = LINK_RESULT};
	msg.as.result.code = LINK_RESULT_INVALID + 1;
	CHECK(!link_msg_encode(&msg, 1, &frame));
	msg.as.result.code = LINK_RESULT_INVALID;
	msg.as.result.path = span_of(long_path, LINK_PATH_MAX);
	CHECK(link_msg_encode(&msg, 1, &frame));
	msg.as.result.path = span_of(long_path, LINK_PATH_MAX + 1);
	CHECK(!link_msg_encode(&msg, 1, &frame));
	msg.as.result.path = span_of((const uint8_t *)"a\nb", 3);
	CHECK(!link_msg_encode(&msg, 1, &frame));

	msg = (link_msg_t){.type = LINK_SET_CREDENTIAL};
	msg.as.set_credential.kind = LINK_CREDENTIAL_WIFI_PASSPHRASE;
	msg.as.set_credential.bytes = span_of((const uint8_t *)"dummy-p", 7);
	CHECK(!link_msg_encode(&msg, 1, &frame));

	msg = (link_msg_t){.type = LINK_CRED_STATUS};
	msg.as.cred_status.code = LINK_CRED_STORE_FAIL + 1;
	CHECK(!link_msg_encode(&msg, 1, &frame));

	msg = (link_msg_t){.type = LINK_STATUS};
	CHECK(link_msg_encode(&msg, 1, &frame));
	msg.as.status.wifi_state = LINK_WIFI_UP + 1;
	CHECK(!link_msg_encode(&msg, 1, &frame));

	msg = (link_msg_t){.type = LINK_OBS_LIST};
	CHECK(!link_msg_encode(&msg, 1, &frame));

	msg = (link_msg_t){.type = LINK_INPUT};
	msg.as.input.source = LINK_INPUT_KNOB_TURN;
	CHECK(!link_msg_encode(&msg, 1, &frame));
}

int main(void) {
	load_vectors();
	test_crc_check_value();
	test_good_vector_gives_type_id_and_payload();
	test_every_vector_decodes_alone();
	test_refusals_carry_the_type_and_code();
	test_all_vectors_at_all_64_read_alignments();
	test_all_vectors_one_byte_at_a_time();
	test_247_byte_frame_keeps_its_head();
	test_largest_frame_keeps_its_head();
	test_cut_frame_is_answered_and_the_next_frame_survives();
	test_push_takes_only_what_fits();
	test_encode_refuses_what_does_not_fit();
	test_every_msg_vector_decodes_and_encodes_back();
	test_every_bad_vector_is_refused_by_the_typed_decoder();
	test_an_unknown_type_is_refused();
	test_request_vectors_carry_these_fields();
	test_info_vector_carries_these_fields();
	test_info_carries_each_credential_as_one_bit();
	test_reply_vectors_carry_these_fields();
	test_every_cred_vector_gets_the_status_in_its_name();
	test_credential_vectors_carry_these_fields();
	test_an_obs_password_stops_at_239_bytes();
	test_a_wrong_magic_is_refused();
	test_status_and_list_vectors_carry_these_fields();
	test_the_pad_to_app_types_are_a_closed_list();
	test_each_pad_to_app_type_has_only_its_named_bytes();
	test_the_git_hash_and_the_document_bytes_are_not_fed_by_a_credential();
	test_the_credential_reply_is_the_same_for_every_accepted_secret();
	test_chunk_and_data_sizes_stop_at_the_payload_cap();
	test_encode_refuses_what_decode_refuses();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	printf("link: all tests pass (%zu vectors, %d read alignments)\n", vector_count, READ_LEN);
	return 0;
}
