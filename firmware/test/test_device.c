// SPDX-License-Identifier: MIT
// The device link dispatcher over the NOR model: config flow, credentials and the erase paths
// (task 2.11a, spec 8.2).
#include "cred.h"
#include "device.h"
#include "input.h"
#include "link.h"
#include "nor_model.h"
#include "store.h"

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

#define CRED_BYTES (2 * STORE_SECTOR_BYTES)
#define SECRET_RUN 4
#define STORED_SEQ 41u
#define MAX_REPLIES 64
#define STREAM_CAP (MAX_REPLIES * LINK_MAX_FRAME)

static nor_chip_t chip;
static nor_part_t slot_a = {.chip = &chip, .base = 0, .size = STORE_SLOT_BYTES};
static nor_part_t slot_b = {.chip = &chip, .base = STORE_SLOT_BYTES, .size = STORE_SLOT_BYTES};
static nor_part_t cred_part = {.chip = &chip, .base = 2 * STORE_SLOT_BYTES, .size = CRED_BYTES};

#define MINIMAL_DOC(schema, brightness)                                                          \
	"{\"schema\":" schema ",\"seq\":41,\"obs\":{\"url\":\"ws://10.0.0.2\",\"auth_mode\":"    \
	"\"none\"},\"wifi\":{\"ssid\":\"\"},\"keys\":[{\"do\":\"none\"},{\"do\":\"none\"},"      \
	"{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":"       \
	"\"none\"},{\"do\":\"none\"},{\"do\":\"none\"}],\"buttons\":[{\"do\":\"none\"},{\"do\":" \
	"\"none\"},{\"do\":\"none\"},{\"do\":\"none\"}],\"knobs\":[{\"input\":null,\"step_db\":" \
	"1,\"push\":{\"do\":\"none\"}},{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}}" \
	",{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}}],\"main_display\":{"         \
	"\"widgets\":[]},\"strip_display\":{\"widgets\":[]},\"ui\":{\"brightness\":" brightness "}}"

static const char STORED_DOC[] = MINIMAL_DOC("1", "0");
static const char EDITED_DOC[] = MINIMAL_DOC("1", "80");
static const char OLD_SCHEMA_DOC[] = MINIMAL_DOC("0", "0");
static const char BAD_URL_DOC[] = "{\"schema\":1,\"seq\":41,\"obs\":{\"url\":\"ws://8.8.8.8\"}}";

// No 4-byte run of either occurs in a document or a fixed INFO field.
static const char OBS_PASSWORD[] = "Zq7!Xv#9Lm@2Pp";
static const char WIFI_PSK[] = "Kj4$Rt8&Wn5*Hy";

// ---- A cred fake in the NOR model: kind k owns sector k-1 as [len][bytes]. ----

typedef struct {
	cred_t cred;
	bool put_fails;
	bool erase_fails;
} cred_fake_t;

static uint32_t sector_of(enum link_credential_kind kind) {
	return ((uint32_t)kind - 1u) * STORE_SECTOR_BYTES;
}

static bool fake_put(cred_t *cred, enum link_credential_kind kind, const uint8_t *bytes, size_t len) {
	uint8_t head = (uint8_t)len;
	return !((cred_fake_t *)cred)->put_fails &&
	       NOR_FLASH.erase(&cred_part, sector_of(kind), STORE_SECTOR_BYTES) &&
	       NOR_FLASH.program(&cred_part, sector_of(kind) + 1, bytes, (uint32_t)len) &&
	       NOR_FLASH.program(&cred_part, sector_of(kind), &head, 1);
}

static bool fake_is_set(cred_t *cred, enum link_credential_kind kind) {
	(void)cred;
	uint8_t head = 0xFF;
	return NOR_FLASH.read(&cred_part, sector_of(kind), &head, 1) && head != 0xFF;
}

static size_t fake_get(cred_t *cred, enum link_credential_kind kind, uint8_t *out, size_t cap) {
	(void)cred;
	uint8_t head = 0xFF;
	if (!NOR_FLASH.read(&cred_part, sector_of(kind), &head, 1) || head == 0xFF || head > cap) {
		return 0;
	}
	return NOR_FLASH.read(&cred_part, sector_of(kind) + 1, out, head) ? head : 0;
}

static bool fake_erase_all(cred_t *cred) {
	return !((cred_fake_t *)cred)->erase_fails && NOR_FLASH.erase(&cred_part, 0, CRED_BYTES);
}

static cred_fake_t fake = {
	.cred = {.put = fake_put, .is_set = fake_is_set, .get = fake_get, .erase_all = fake_erase_all},
};

// ---- The device under test ----

static const uint8_t FW_VERSION[] = "2.0.0-test";
static const link_info_t IDENTITY = {
	.keys = INPUT_KEYS,
	.buttons = INPUT_BUTTONS,
	.knobs = INPUT_KNOBS,
	.main_display = {320, 480},
	.strip_display = {142, 428},
	.board_rev = 1,
	.git_hash = {0xde, 0xad, 0xbe, 0xef},
	.unique_id = {1, 2, 3, 4, 5, 6},
	.fw_version = {FW_VERSION, sizeof FW_VERSION - 1},
};

static device_t dev;
static uint32_t now_ms;

static void boot(void) {
	device_port_t port = {
		.identity = &IDENTITY,
		.cred = &fake.cred,
		.flash = &NOR_FLASH,
		.slot_a = &slot_a,
		.slot_b = &slot_b,
	};
	device_init(&dev, &port);
}

static void store_doc(const char *doc, uint32_t schema, uint32_t seq) {
	store_t store;
	store_mount(&store, &NOR_FLASH, &slot_a, &slot_b);
	store_doc_t header = {.schema = schema, .seq = seq, .len = (uint32_t)strlen(doc)};
	CHECK(store_commit(&store, &header, (const uint8_t *)doc) == STORE_OK);
}

static void put_secret(enum link_credential_kind kind, const char *secret) {
	CHECK(fake.cred.put(&fake.cred, kind, (const uint8_t *)secret, strlen(secret)));
}

// A fresh chip with STORED_DOC at STORED_SEQ and both dummy secrets, then a boot.
static void start(void) {
	nor_chip_init(&chip);
	fake.put_fails = false;
	fake.erase_fails = false;
	now_ms = 1000;
	store_doc(STORED_DOC, 1, STORED_SEQ);
	put_secret(LINK_CREDENTIAL_OBS_PASSWORD, OBS_PASSWORD);
	put_secret(LINK_CREDENTIAL_WIFI_PASSPHRASE, WIFI_PSK);
	boot();
}

static bool holds_a_run_of(const uint8_t *bytes, size_t len, const char *secret) {
	size_t secret_len = strlen(secret);
	for (size_t start = 0; start + SECRET_RUN <= secret_len; start++) {
		for (size_t at = 0; at + SECRET_RUN <= len; at++) {
			if (memcmp(&bytes[at], &secret[start], SECRET_RUN) == 0) {
				return true;
			}
		}
	}
	return false;
}

static bool holds_a_secret(const uint8_t *bytes, size_t len) {
	return holds_a_run_of(bytes, len, OBS_PASSWORD) || holds_a_run_of(bytes, len, WIFI_PSK);
}

static bool is_erased(const nor_part_t *part) {
	for (uint32_t i = 0; i < part->size; i++) {
		if (chip.bytes[part->base + i] != 0xFF) {
			return false;
		}
	}
	return true;
}

static bool secrets_kept(void) {
	return fake.cred.is_set(&fake.cred, LINK_CREDENTIAL_OBS_PASSWORD) &&
	       fake.cred.is_set(&fake.cred, LINK_CREDENTIAL_WIFI_PASSPHRASE);
}

static link_frame_t reply;

// Sends one frame and decodes its reply. Every reply is checked for a secret (R1).
static link_msg_t send_frame(const link_frame_t *frame) {
	CHECK(device_handle(&dev, now_ms, frame, &reply));
	CHECK(reply.id == frame->id);
	CHECK(!holds_a_secret(reply.payload, reply.length));
	link_msg_t got = {0};
	CHECK(link_msg_decode(&reply, &got));
	return got;
}

static link_msg_t send_msg(const link_msg_t *msg, uint8_t id) {
	link_frame_t frame;
	CHECK(link_msg_encode(msg, id, &frame));
	return send_frame(&frame);
}

static link_msg_t send_empty(uint8_t type) {
	link_msg_t msg = {.type = type};
	return send_msg(&msg, 7);
}

static link_msg_t begin_msg(uint32_t base_seq, const char *doc, bool try_only) {
	link_msg_t msg = {.type = LINK_CFG_BEGIN};
	msg.as.cfg_begin.base_seq = base_seq;
	msg.as.cfg_begin.total = (uint16_t)strlen(doc);
	msg.as.cfg_begin.crc32 = store_crc32((const uint8_t *)doc, strlen(doc));
	msg.as.cfg_begin.try_only = try_only;
	return msg;
}

static link_msg_t chunk_msg(const char *doc, size_t offset) {
	size_t left = strlen(doc) - offset;
	link_msg_t msg = {.type = LINK_CFG_CHUNK};
	msg.as.cfg_chunk.offset = (uint16_t)offset;
	msg.as.cfg_chunk.bytes = (link_span_t){(const uint8_t *)&doc[offset],
	                                       left < LINK_CFG_CHUNK_MAX ? left : LINK_CFG_CHUNK_MAX};
	return msg;
}

static link_msg_t read_msg(size_t offset) {
	link_msg_t msg = {.type = LINK_CFG_READ};
	msg.as.cfg_read.offset = (uint16_t)offset;
	msg.as.cfg_read.len = LINK_CFG_DATA_MAX;
	return msg;
}

static bool is_result(link_msg_t msg, uint8_t code, uint32_t seq) {
	return msg.type == LINK_RESULT && msg.as.result.code == code && msg.as.result.seq == seq;
}

static bool is_cred_status(link_msg_t msg, uint8_t code) {
	return msg.type == LINK_CRED_STATUS && msg.as.cred_status.code == code;
}

// BEGIN, every chunk, COMMIT. Returns the reply to COMMIT; BEGIN and each chunk must get ok.
static link_msg_t write_doc(uint32_t base_seq, const char *doc, bool try_only) {
	link_msg_t begin = begin_msg(base_seq, doc, try_only);
	link_msg_t got = send_msg(&begin, 1);
	CHECK(is_result(got, LINK_RESULT_OK, base_seq));
	for (size_t offset = 0; offset < strlen(doc); offset += LINK_CFG_CHUNK_MAX) {
		link_msg_t chunk = chunk_msg(doc, offset);
		got = send_msg(&chunk, 2);
		CHECK(is_result(got, LINK_RESULT_OK, base_seq));
	}
	return send_empty(LINK_CFG_COMMIT);
}

// True when CFG_READ serves `doc` with `seq`, read to `total` one CFG_DATA at a time.
static bool serves(const char *doc, uint32_t seq) {
	static char got[CONFIG_MAX_BYTES];
	size_t len = 0;
	link_msg_t data;
	do {
		link_msg_t read = read_msg(len);
		data = send_msg(&read, 3);
		if (data.type != LINK_CFG_DATA || data.as.cfg_data.seq != seq ||
		    data.as.cfg_data.offset != len) {
			return false;
		}
		memcpy(&got[len], data.as.cfg_data.bytes.bytes, data.as.cfg_data.bytes.len);
		len += data.as.cfg_data.bytes.len;
	} while (data.as.cfg_data.bytes.len > 0 && len < data.as.cfg_data.total);
	return len == strlen(doc) && data.as.cfg_data.total == len && memcmp(got, doc, len) == 0;
}

// ---- The fixed byte sequence: INFO, a whole read, the edited document written back ----

typedef struct {
	uint8_t bytes[STREAM_CAP];
	size_t len;
	uint8_t ids[MAX_REPLIES];
	int count;
} stream_t;

static void append(stream_t *stream, const link_msg_t *msg) {
	link_frame_t frame;
	uint8_t id = (uint8_t)(0x10 + stream->count);
	CHECK(stream->count < MAX_REPLIES && link_msg_encode(msg, id, &frame));
	stream->len += link_encode(&frame, &stream->bytes[stream->len], STREAM_CAP - stream->len);
	stream->ids[stream->count++] = id;
}

static void build_session(stream_t *stream) {
	link_msg_t info = {.type = LINK_INFO_GET};
	append(stream, &info);
	for (size_t offset = 0; offset < strlen(STORED_DOC); offset += LINK_CFG_DATA_MAX) {
		link_msg_t read = read_msg(offset);
		append(stream, &read);
	}
	link_msg_t begin = begin_msg(STORED_SEQ, EDITED_DOC, false);
	append(stream, &begin);
	for (size_t offset = 0; offset < strlen(EDITED_DOC); offset += LINK_CFG_CHUNK_MAX) {
		link_msg_t chunk = chunk_msg(EDITED_DOC, offset);
		append(stream, &chunk);
	}
	link_msg_t commit = {.type = LINK_CFG_COMMIT};
	append(stream, &commit);
}

static void test_a_whole_read_edit_and_commit_returns_seq_plus_one(void) {
	start();
	static stream_t stream;
	stream = (stream_t){0};
	build_session(&stream);
	link_rx_t rx;
	link_rx_init(&rx);
	static char read_back[CONFIG_MAX_BYTES];
	size_t read_len = 0;
	int replies = 0;
	link_msg_t got = {0};
	for (size_t fed = 0; fed < stream.len;) {
		fed += link_rx_push(&rx, &stream.bytes[fed], stream.len - fed);
		link_frame_t frame;
		while (link_pull(&rx, &frame) == LINK_FRAME) {
			got = send_frame(&frame);
			CHECK(replies < stream.count && reply.id == stream.ids[replies]);
			replies++;
			if (got.type == LINK_CFG_DATA) {
				memcpy(&read_back[read_len], got.as.cfg_data.bytes.bytes, got.as.cfg_data.bytes.len);
				read_len += got.as.cfg_data.bytes.len;
			}
		}
	}
	CHECK(replies == stream.count);
	CHECK(read_len == strlen(STORED_DOC) && memcmp(read_back, STORED_DOC, read_len) == 0);
	CHECK(is_result(got, LINK_RESULT_OK, STORED_SEQ + 1));
	CHECK(serves(EDITED_DOC, STORED_SEQ + 1));
	boot();
	CHECK(serves(EDITED_DOC, STORED_SEQ + 1));
}

static void test_info_reports_the_ranges_and_the_two_credential_bits(void) {
	start();
	link_msg_t got = send_empty(LINK_INFO_GET);
	CHECK(got.type == LINK_INFO);
	CHECK(got.as.info.proto == LINK_VERSION);
	CHECK(got.as.info.schema_min == CONFIG_SCHEMA_MIN && got.as.info.schema_max == CONFIG_SCHEMA_MAX);
	CHECK(got.as.info.max_doc_bytes == CONFIG_MAX_BYTES);
	CHECK(got.as.info.obs_password_set && got.as.info.wifi_psk_set);
	CHECK(got.as.info.keys == INPUT_KEYS && got.as.info.board_rev == 1);
	CHECK(memcmp(got.as.info.git_hash, IDENTITY.git_hash, LINK_GIT_HASH_LEN) == 0);
	CHECK(got.as.info.fw_version.len == sizeof FW_VERSION - 1);
	CHECK(is_cred_status(send_empty(LINK_CLEAR_CREDENTIALS), LINK_CRED_OK));
	got = send_empty(LINK_INFO_GET);
	CHECK(!got.as.info.obs_password_set && !got.as.info.wifi_psk_set);
}

static void test_a_stale_write_gets_stale_seq(void) {
	start();
	link_msg_t begin = begin_msg(STORED_SEQ - 1, EDITED_DOC, false);
	link_msg_t got = send_msg(&begin, 1);
	CHECK(is_result(got, LINK_RESULT_STALE_SEQ, STORED_SEQ));
	link_msg_t chunk = chunk_msg(EDITED_DOC, 0);
	got = send_msg(&chunk, 2);
	CHECK(is_result(got, LINK_RESULT_INVALID, STORED_SEQ));
	got = send_empty(LINK_CFG_COMMIT);
	CHECK(is_result(got, LINK_RESULT_INVALID, STORED_SEQ));
	CHECK(serves(STORED_DOC, STORED_SEQ));
}

static void test_a_try_only_write_reverts_after_30_s(void) {
	start();
	link_msg_t got = write_doc(STORED_SEQ, EDITED_DOC, true);
	CHECK(is_result(got, LINK_RESULT_OK, STORED_SEQ));
	link_span_t draft = device_draft(&dev);
	CHECK(draft.len == strlen(EDITED_DOC) && memcmp(draft.bytes, EDITED_DOC, draft.len) == 0);
	device_tick(&dev, now_ms + DEVICE_TRY_MS - 1);
	CHECK(device_draft(&dev).bytes != NULL);
	device_tick(&dev, now_ms + DEVICE_TRY_MS);
	CHECK(device_draft(&dev).bytes == NULL && device_draft(&dev).len == 0);
	CHECK(serves(STORED_DOC, STORED_SEQ));
	boot();
	CHECK(serves(STORED_DOC, STORED_SEQ));
}

static void test_a_try_only_draft_ends_on_cfg_read_and_on_cfg_begin(void) {
	start();
	write_doc(STORED_SEQ, EDITED_DOC, true);
	CHECK(device_draft(&dev).bytes != NULL);
	link_msg_t read = read_msg(0);
	CHECK(send_msg(&read, 3).as.cfg_data.seq == STORED_SEQ);
	CHECK(device_draft(&dev).bytes == NULL);
	write_doc(STORED_SEQ, EDITED_DOC, true);
	link_msg_t begin = begin_msg(STORED_SEQ, EDITED_DOC, false);
	send_msg(&begin, 1);
	CHECK(device_draft(&dev).bytes == NULL);
}

static void test_a_try_only_draft_counts_30_s_across_a_clock_wrap(void) {
	start();
	now_ms = 0xFFFFF000u;
	write_doc(STORED_SEQ, EDITED_DOC, true);
	device_tick(&dev, now_ms + DEVICE_TRY_MS - 1);
	CHECK(device_draft(&dev).bytes != NULL);
	device_tick(&dev, now_ms + DEVICE_TRY_MS);
	CHECK(device_draft(&dev).bytes == NULL);
}

static void test_bad_writes_store_nothing(void) {
	start();
	link_msg_t got = write_doc(STORED_SEQ, BAD_URL_DOC, false);
	CHECK(is_result(got, LINK_RESULT_INVALID, STORED_SEQ));
	CHECK(got.as.result.path.len == 7 && memcmp(got.as.result.path.bytes, "obs.url", 7) == 0);
	write_doc(STORED_SEQ, BAD_URL_DOC, true);
	CHECK(device_draft(&dev).bytes == NULL);

	link_msg_t begin = begin_msg(STORED_SEQ, EDITED_DOC, false);
	begin.as.cfg_begin.crc32 ^= 1u;
	send_msg(&begin, 1);
	for (size_t offset = 0; offset < strlen(EDITED_DOC); offset += LINK_CFG_CHUNK_MAX) {
		link_msg_t chunk = chunk_msg(EDITED_DOC, offset);
		send_msg(&chunk, 2);
	}
	got = send_empty(LINK_CFG_COMMIT);
	CHECK(is_result(got, LINK_RESULT_BAD_CRC, STORED_SEQ));

	begin = begin_msg(STORED_SEQ, EDITED_DOC, false);
	send_msg(&begin, 1);
	got = send_empty(LINK_CFG_COMMIT); // no chunk came
	CHECK(is_result(got, LINK_RESULT_BAD_CRC, STORED_SEQ));
	link_msg_t past_total = chunk_msg(EDITED_DOC, strlen(EDITED_DOC) - 10);
	past_total.as.cfg_chunk.bytes.len = 11;
	CHECK(is_result(send_msg(&past_total, 2), LINK_RESULT_INVALID, STORED_SEQ));

	begin.as.cfg_begin.total = CONFIG_MAX_BYTES + 1;
	CHECK(is_result(send_msg(&begin, 1), LINK_RESULT_TOO_BIG, STORED_SEQ));
	begin.as.cfg_begin.total = 0;
	CHECK(is_result(send_msg(&begin, 1), LINK_RESULT_INVALID, STORED_SEQ));
	CHECK(serves(STORED_DOC, STORED_SEQ));
}

static void test_a_failed_commit_can_be_retried(void) {
	start();
	link_msg_t begin = begin_msg(STORED_SEQ, EDITED_DOC, false);
	send_msg(&begin, 1);
	link_msg_t got = send_empty(LINK_CFG_COMMIT);
	CHECK(is_result(got, LINK_RESULT_BAD_CRC, STORED_SEQ));
	for (size_t offset = 0; offset < strlen(EDITED_DOC); offset += LINK_CFG_CHUNK_MAX) {
		link_msg_t chunk = chunk_msg(EDITED_DOC, offset);
		send_msg(&chunk, 2);
	}
	got = send_empty(LINK_CFG_COMMIT);
	CHECK(is_result(got, LINK_RESULT_OK, STORED_SEQ + 1));
}

static void test_a_flash_fault_at_commit_gets_busy(void) {
	start();
	link_msg_t begin = begin_msg(STORED_SEQ, EDITED_DOC, false);
	send_msg(&begin, 1);
	for (size_t offset = 0; offset < strlen(EDITED_DOC); offset += LINK_CFG_CHUNK_MAX) {
		link_msg_t chunk = chunk_msg(EDITED_DOC, offset);
		send_msg(&chunk, 2);
	}
	nor_chip_cut_after(&chip, 1, false);
	link_msg_t got = send_empty(LINK_CFG_COMMIT);
	CHECK(is_result(got, LINK_RESULT_BUSY, STORED_SEQ));
	nor_chip_restore(&chip);
	boot();
	CHECK(serves(STORED_DOC, STORED_SEQ));
}

static void test_a_schema_below_min_is_served_and_migrated(void) {
	nor_chip_init(&chip);
	store_doc(OLD_SCHEMA_DOC, 0, 17);
	boot();
	CHECK(dev.store.state == STORE_UNLOADED);
	CHECK(serves(OLD_SCHEMA_DOC, 17));
	link_msg_t got = write_doc(17, EDITED_DOC, false);
	CHECK(is_result(got, LINK_RESULT_OK, 18));
	CHECK(dev.store.state == STORE_LOADED && dev.store.doc.schema == 1);
	CHECK(serves(EDITED_DOC, 18));
}

static void test_the_first_write_on_an_empty_pad_has_base_seq_0(void) {
	nor_chip_init(&chip);
	boot();
	link_msg_t read = read_msg(0);
	link_msg_t got = send_msg(&read, 3);
	CHECK(got.type == LINK_CFG_DATA && got.as.cfg_data.seq == 0 && got.as.cfg_data.total == 0);
	CHECK(got.as.cfg_data.bytes.len == 0);
	read = read_msg(1);
	CHECK(is_result(send_msg(&read, 3), LINK_RESULT_INVALID, 0));
	got = write_doc(0, EDITED_DOC, false);
	CHECK(is_result(got, LINK_RESULT_OK, 1));
	CHECK(dev.store.doc.schema == 1);
}

// ---- Credentials ----

static link_msg_t set_credential(uint8_t kind, const char *secret) {
	link_msg_t msg = {.type = LINK_SET_CREDENTIAL};
	msg.as.set_credential.kind = kind;
	msg.as.set_credential.bytes = (link_span_t){(const uint8_t *)secret, strlen(secret)};
	return send_msg(&msg, 9);
}

static void test_set_credential_stores_through_cred(void) {
	start();
	CHECK(is_cred_status(send_empty(LINK_CLEAR_CREDENTIALS), LINK_CRED_OK));
	link_msg_t got = set_credential(LINK_CREDENTIAL_WIFI_PASSPHRASE, WIFI_PSK);
	CHECK(is_cred_status(got, LINK_CRED_OK));
	uint8_t stored[LINK_CREDENTIAL_MAX];
	size_t len = fake.cred.get(&fake.cred, LINK_CREDENTIAL_WIFI_PASSPHRASE, stored, sizeof stored);
	CHECK(len == strlen(WIFI_PSK) && memcmp(stored, WIFI_PSK, len) == 0);
	CHECK(!fake.cred.is_set(&fake.cred, LINK_CREDENTIAL_OBS_PASSWORD));
	fake.put_fails = true;
	got = set_credential(LINK_CREDENTIAL_OBS_PASSWORD, OBS_PASSWORD);
	CHECK(is_cred_status(got, LINK_CRED_STORE_FAIL));
}

static void test_a_refused_set_credential_leaves_cred_as_it_was(void) {
	start();
	link_frame_t frame = {.type = LINK_SET_CREDENTIAL, .id = 4, .length = 4};
	memcpy(frame.payload, "\x03" "abc", 4); // kind 3
	CHECK(is_cred_status(send_frame(&frame), LINK_CRED_BAD_KIND));
	frame.length = 8;
	memcpy(frame.payload, "\x02" "short!!", 8); // a 7-byte passphrase
	CHECK(is_cred_status(send_frame(&frame), LINK_CRED_BAD_LEN));
	uint8_t stored[LINK_CREDENTIAL_MAX];
	size_t len = fake.cred.get(&fake.cred, LINK_CREDENTIAL_WIFI_PASSPHRASE, stored, sizeof stored);
	CHECK(len == strlen(WIFI_PSK) && memcmp(stored, WIFI_PSK, len) == 0);
}

static void test_clear_credentials_with_one_payload_byte_is_bad_len(void) {
	start();
	link_frame_t frame = {.type = LINK_CLEAR_CREDENTIALS, .id = 5, .length = 1, .payload = {0}};
	CHECK(is_cred_status(send_frame(&frame), LINK_CRED_BAD_LEN));
	CHECK(secrets_kept());
	CHECK(holds_a_secret(&chip.bytes[cred_part.base], CRED_BYTES));
}

static void test_clear_credentials_erases_cred_only(void) {
	start();
	CHECK(is_cred_status(send_empty(LINK_CLEAR_CREDENTIALS), LINK_CRED_OK));
	CHECK(is_erased(&cred_part));
	CHECK(serves(STORED_DOC, STORED_SEQ));
	fake.erase_fails = true;
	CHECK(is_cred_status(send_empty(LINK_CLEAR_CREDENTIALS), LINK_CRED_STORE_FAIL));
}

// ---- The erase paths ----

static link_msg_t send_magic(uint8_t type, uint32_t magic) {
	link_frame_t frame = {.type = type, .id = 6, .length = 4};
	for (int i = 0; i < 4; i++) {
		frame.payload[i] = (uint8_t)(magic >> (8 * i));
	}
	return send_frame(&frame);
}

static bool all_erased(void) {
	return is_erased(&cred_part) && is_erased(&slot_a) && is_erased(&slot_b) &&
	       dev.store.state == STORE_NONE;
}

static void test_factory_reset_erases_cred_then_both_slots(void) {
	start();
	link_msg_t got = send_magic(LINK_FACTORY_RESET, LINK_FACTORY_RESET_MAGIC);
	CHECK(is_cred_status(got, LINK_CRED_OK));
	CHECK(all_erased());
	boot();
	CHECK(dev.store.state == STORE_NONE);
}

static void test_the_wipe_erases_cred_before_the_slots(void) {
	start();
	nor_chip_cut_after(&chip, 1, false); // the first erase runs, then the power goes
	link_msg_t got = send_magic(LINK_FACTORY_RESET, LINK_FACTORY_RESET_MAGIC);
	CHECK(is_cred_status(got, LINK_CRED_STORE_FAIL));
	nor_chip_restore(&chip);
	CHECK(is_erased(&cred_part));
	boot();
	CHECK(serves(STORED_DOC, STORED_SEQ));
}

static void test_a_wrong_magic_erases_nothing(void) {
	start();
	link_msg_t got = send_magic(LINK_FACTORY_RESET, LINK_BOOTLOADER_MAGIC);
	CHECK(is_result(got, LINK_RESULT_INVALID, STORED_SEQ));
	got = send_magic(LINK_BOOTLOADER, LINK_FACTORY_RESET_MAGIC);
	CHECK(is_result(got, LINK_RESULT_INVALID, STORED_SEQ));
	CHECK(secrets_kept() && !device_bootloader_asked(&dev));
	CHECK(serves(STORED_DOC, STORED_SEQ));
}

static void test_bootloader_erases_cred_and_keeps_the_config(void) {
	start();
	link_msg_t got = send_magic(LINK_BOOTLOADER, LINK_BOOTLOADER_MAGIC);
	CHECK(is_cred_status(got, LINK_CRED_OK));
	CHECK(device_bootloader_asked(&dev));
	CHECK(is_erased(&cred_part));
	CHECK(serves(STORED_DOC, STORED_SEQ));
}

static void test_bootloader_without_a_cred_erase_stays_out_of_download_mode(void) {
	start();
	fake.erase_fails = true;
	link_msg_t got = send_magic(LINK_BOOTLOADER, LINK_BOOTLOADER_MAGIC);
	CHECK(is_cred_status(got, LINK_CRED_STORE_FAIL));
	CHECK(!device_bootloader_asked(&dev));
}

// B1 + B4 held from power-on through input_step, one sample a millisecond, every event to the
// device. Sample n is n ms after power-on.
static void hold_clear_buttons(uint32_t last_ms) {
	input_t in;
	input_init(&in);
	for (uint32_t ms = 0; ms <= last_ms; ms++) {
		input_sample_t sample = {.now_ms = ms};
		sample.cols_low[3] = 0x9; // button 0 on COL0, button 3 on COL3
		input_event_t events[INPUT_MAX_EVENTS];
		int count = input_step(&in, &sample, events);
		for (int i = 0; i < count; i++) {
			CHECK(device_input(&dev, &events[i]));
		}
	}
}

static void test_b1_b4_held_5000_ms_empty_cred_and_both_slots(void) {
	start();
	hold_clear_buttons(INPUT_CLEAR_HOLD_MS);
	CHECK(all_erased());
	CHECK(!fake.cred.is_set(&fake.cred, LINK_CREDENTIAL_OBS_PASSWORD));
	CHECK(!fake.cred.is_set(&fake.cred, LINK_CREDENTIAL_WIFI_PASSPHRASE));
	CHECK(!holds_a_secret(chip.bytes, NOR_CHIP_BYTES));
}

static void test_b1_b4_held_4900_ms_leave_everything(void) {
	start();
	hold_clear_buttons(4900);
	CHECK(secrets_kept());
	CHECK(serves(STORED_DOC, STORED_SEQ));
}

// ---- Frames the pad takes no request from ----

static void test_unknown_and_pad_to_app_types_get_invalid(void) {
	start();
	link_frame_t frame = {.type = 0x7F, .id = 8, .length = 0};
	CHECK(is_result(send_frame(&frame), LINK_RESULT_INVALID, STORED_SEQ));
	link_msg_t status = {.type = LINK_CRED_STATUS};
	CHECK(is_result(send_msg(&status, 8), LINK_RESULT_INVALID, STORED_SEQ));
	link_msg_t list = {.type = LINK_OBS_LIST};
	list.as.obs_list.list = LINK_LIST_SCENES;
	list.as.obs_list.index = 3;
	link_msg_t got = send_msg(&list, 8);
	CHECK(got.type == LINK_OBS_ITEM && got.as.obs_item.total == 0 && got.as.obs_item.index == 3);
}

int main(void) {
	test_a_whole_read_edit_and_commit_returns_seq_plus_one();
	test_info_reports_the_ranges_and_the_two_credential_bits();
	test_a_stale_write_gets_stale_seq();
	test_a_try_only_write_reverts_after_30_s();
	test_a_try_only_draft_ends_on_cfg_read_and_on_cfg_begin();
	test_a_try_only_draft_counts_30_s_across_a_clock_wrap();
	test_bad_writes_store_nothing();
	test_a_failed_commit_can_be_retried();
	test_a_flash_fault_at_commit_gets_busy();
	test_a_schema_below_min_is_served_and_migrated();
	test_the_first_write_on_an_empty_pad_has_base_seq_0();
	test_set_credential_stores_through_cred();
	test_a_refused_set_credential_leaves_cred_as_it_was();
	test_clear_credentials_with_one_payload_byte_is_bad_len();
	test_clear_credentials_erases_cred_only();
	test_factory_reset_erases_cred_then_both_slots();
	test_the_wipe_erases_cred_before_the_slots();
	test_a_wrong_magic_erases_nothing();
	test_bootloader_erases_cred_and_keeps_the_config();
	test_bootloader_without_a_cred_erase_stays_out_of_download_mode();
	test_b1_b4_held_5000_ms_empty_cred_and_both_slots();
	test_b1_b4_held_4900_ms_leave_everything();
	test_unknown_and_pad_to_app_types_get_invalid();
	if (failures != 0) {
		fprintf(stderr, "test_device: %d failure(s)\n", failures);
		return 1;
	}
	puts("test_device: ok");
	return 0;
}
