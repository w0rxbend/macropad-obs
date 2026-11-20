// SPDX-License-Identifier: MIT
#include "device.h"

#include "config.h"
#include "json.h"

#include <stdlib.h>
#include <string.h>

// The fixed fields of OBS_ITEM, before the name (docs/protocol.md).
#define OBS_ITEM_FIXED (5 + LINK_UUID_LEN)
#define UUID_TEXT_LEN 36
// The id of a frame no request asked for (docs/protocol.md, STATUS).
#define UNASKED_ID 0

_Static_assert(OBS_NAME_MAX <= LINK_MAX_PAYLOAD - OBS_ITEM_FIXED,
               "an obs_state name fits OBS_ITEM whole, so the handler never cuts one");

static uint32_t stored_seq(const device_t *dev) {
	return dev->store.state == STORE_NONE ? 0 : dev->store.doc.seq;
}

static link_msg_t result_with_path(uint8_t code, uint32_t seq, const char *path) {
	link_msg_t msg = {.type = LINK_RESULT};
	msg.as.result.code = code;
	msg.as.result.seq = seq;
	msg.as.result.path = (link_span_t){.bytes = (const uint8_t *)path, .len = strlen(path)};
	return msg;
}

static link_msg_t result(const device_t *dev, uint8_t code) {
	return result_with_path(code, stored_seq(dev), "");
}

static link_msg_t cred_status(uint8_t code) {
	link_msg_t msg = {.type = LINK_CRED_STATUS};
	msg.as.cred_status.code = code;
	return msg;
}

static link_msg_t cred_status_of(bool done) {
	return cred_status(done ? LINK_CRED_OK : LINK_CRED_STORE_FAIL);
}

void device_init(device_t *dev, const device_port_t *port) {
	dev->identity = port->identity;
	dev->cred = port->cred;
	dev->obs_state = port->obs_state;
	dev->status_sent = false;
	dev->write.open = false;
	dev->trying = false;
	dev->try_until_ms = 0;
	dev->bootloader_asked = false;
	store_mount(&dev->store, port->flash, port->slot_a, port->slot_b);
}

static void end_write_and_draft(device_t *dev) {
	dev->write.open = false;
	dev->trying = false;
}

// cred first, then both slots (spec 8.2). The slots are erased even when cred failed, so a
// half-failed wipe still leaves as little as it can.
static bool wipe(device_t *dev) {
	end_write_and_draft(dev);
	bool cred_erased = dev->cred->erase_all(dev->cred);
	bool slots_erased = store_erase(&dev->store) == STORE_OK;
	return cred_erased && slots_erased;
}

static link_msg_t info_reply(const device_t *dev) {
	link_msg_t msg = {.type = LINK_INFO};
	link_info_t *info = &msg.as.info;
	*info = *dev->identity;
	info->proto = LINK_VERSION;
	info->obs_password_set = dev->cred->is_set(dev->cred, LINK_CREDENTIAL_OBS_PASSWORD);
	info->wifi_psk_set = dev->cred->is_set(dev->cred, LINK_CREDENTIAL_WIFI_PASSPHRASE);
	info->schema_min = CONFIG_SCHEMA_MIN;
	info->schema_max = CONFIG_SCHEMA_MAX;
	info->max_doc_bytes = CONFIG_MAX_BYTES;
	return msg;
}

// Serves the stored document, never the draft, and so ends the draft (docs/config.md).
static link_msg_t cfg_read(device_t *dev, const link_msg_t *request) {
	dev->trying = false;
	uint32_t total = dev->store.state == STORE_NONE ? 0 : dev->store.doc.len;
	uint32_t offset = request->as.cfg_read.offset;
	if (offset > total) {
		return result(dev, LINK_RESULT_INVALID);
	}
	uint32_t len = total - offset < request->as.cfg_read.len ? total - offset
	                                                         : request->as.cfg_read.len;
	if (len > 0 && !store_read(&dev->store, offset, dev->reply_bytes, len)) {
		return result(dev, LINK_RESULT_BUSY);
	}
	link_msg_t msg = {.type = LINK_CFG_DATA};
	msg.as.cfg_data.seq = stored_seq(dev);
	msg.as.cfg_data.total = (uint16_t)total;
	msg.as.cfg_data.offset = (uint16_t)offset;
	msg.as.cfg_data.bytes = (link_span_t){.bytes = dev->reply_bytes, .len = len};
	return msg;
}

// Clears the bytes, so a chunk that never came fails the CRC-32 at CFG_COMMIT even when an
// earlier write left the same document in the buffer.
static link_msg_t cfg_begin(device_t *dev, const link_msg_t *request) {
	end_write_and_draft(dev);
	uint32_t total = request->as.cfg_begin.total;
	if (total > CONFIG_MAX_BYTES) {
		return result(dev, LINK_RESULT_TOO_BIG);
	}
	if (total == 0) {
		return result(dev, LINK_RESULT_INVALID);
	}
	if (request->as.cfg_begin.base_seq != stored_seq(dev)) {
		return result(dev, LINK_RESULT_STALE_SEQ);
	}
	device_write_t *write = &dev->write;
	write->open = true;
	write->try_only = request->as.cfg_begin.try_only;
	write->base_seq = request->as.cfg_begin.base_seq;
	write->total = (uint16_t)total;
	write->crc32 = request->as.cfg_begin.crc32;
	memset(write->bytes, 0, total);
	return result(dev, LINK_RESULT_OK);
}

static link_msg_t cfg_chunk(device_t *dev, const link_msg_t *request) {
	uint32_t offset = request->as.cfg_chunk.offset;
	link_span_t bytes = request->as.cfg_chunk.bytes;
	if (!dev->write.open || offset + bytes.len > dev->write.total) {
		return result(dev, LINK_RESULT_INVALID);
	}
	memcpy(&dev->write.bytes[offset], bytes.bytes, bytes.len);
	return result(dev, LINK_RESULT_OK);
}

static void keep_schema(void *context, const json_event_t *event) {
	if (event->kind == JSON_NUMBER && json_path_is(event, "schema")) {
		*(uint32_t *)context = (uint32_t)strtoul(event->text, NULL, 10);
	}
}

// The `schema` of a document config_validate passed: an integer in the pad's range. Like the
// validator, the last of two `schema` members counts.
static uint32_t schema_of(const uint8_t *doc, size_t len) {
	uint32_t schema = 0;
	json_reader_t reader;
	json_reader_init(&reader, keep_schema, &schema);
	json_feed(&reader, doc, len);
	return schema;
}

static link_msg_t store_write(device_t *dev) {
	const device_write_t *write = &dev->write;
	store_doc_t doc = {
		.schema = schema_of(write->bytes, write->total),
		.seq = write->base_seq + 1,
		.len = write->total,
	};
	switch (store_commit(&dev->store, &doc, write->bytes)) {
	case STORE_OK:
		dev->write.open = false;
		return result(dev, LINK_RESULT_OK);
	case STORE_STALE_SEQ: // base_seq 0xFFFFFFFF: the next seq would wrap to 0
		return result(dev, LINK_RESULT_STALE_SEQ);
	case STORE_BAD_LEN: // cfg_begin keeps total in 1..CONFIG_MAX_BYTES
	case STORE_FLASH_FAIL:
		break;
	}
	return result(dev, LINK_RESULT_BUSY);
}

// A failed commit leaves the write open, so the app can send chunks again and retry.
static link_msg_t cfg_commit(device_t *dev, uint32_t now_ms) {
	const device_write_t *write = &dev->write;
	if (!write->open) {
		return result(dev, LINK_RESULT_INVALID);
	}
	if (store_crc32(write->bytes, write->total) != write->crc32) {
		return result(dev, LINK_RESULT_BAD_CRC);
	}
	config_result_t verdict = config_validate(write->bytes, write->total);
	if (verdict.verdict != CONFIG_VALID) {
		memcpy(dev->reply_path, verdict.path, sizeof dev->reply_path);
		uint8_t code = verdict.verdict == CONFIG_TOO_BIG ? LINK_RESULT_TOO_BIG : LINK_RESULT_INVALID;
		return result_with_path(code, stored_seq(dev), dev->reply_path);
	}
	if (!write->try_only) {
		return store_write(dev);
	}
	dev->write.open = false;
	dev->trying = true;
	dev->try_until_ms = now_ms + DEVICE_TRY_MS;
	return result(dev, LINK_RESULT_OK);
}

static link_msg_t set_credential(device_t *dev, const link_msg_t *request) {
	link_span_t secret = request->as.set_credential.bytes;
	enum link_credential_kind kind = request->as.set_credential.kind;
	return cred_status_of(dev->cred->put(dev->cred, kind, secret.bytes, secret.len));
}

// Download mode lets anyone read the flash, so no cred erase means no download mode (R1).
static link_msg_t bootloader(device_t *dev) {
	end_write_and_draft(dev);
	dev->bootloader_asked = dev->cred->erase_all(dev->cred);
	return cred_status_of(dev->bootloader_asked);
}

static int hex_value(char c) {
	if (c >= '0' && c <= '9') {
		return c - '0';
	}
	if (c >= 'a' && c <= 'f') {
		return c - 'a' + 10;
	}
	if (c >= 'A' && c <= 'F') {
		return c - 'A' + 10;
	}
	return -1;
}

static bool is_dash_place(size_t at) {
	return at == 8 || at == 13 || at == 18 || at == 23;
}

// False, and `out` unspecified, for text not in the 8-4-4-4-12 form.
static bool uuid_from_text(const char *text, uint8_t out[LINK_UUID_LEN]) {
	if (strlen(text) != UUID_TEXT_LEN) {
		return false;
	}
	size_t nibble = 0;
	for (size_t at = 0; at < UUID_TEXT_LEN; at++) {
		if (is_dash_place(at)) {
			if (text[at] != '-') {
				return false;
			}
			continue;
		}
		int digit = hex_value(text[at]);
		if (digit < 0) {
			return false;
		}
		uint8_t *byte = &out[nibble / 2];
		*byte = nibble % 2 == 0 ? (uint8_t)(digit << 4) : (uint8_t)(*byte | digit);
		nibble++;
	}
	return true;
}

static const obs_item_t *obs_list_items(const obs_state_t *state, uint8_t list, uint16_t *count) {
	*count = 0;
	if (state == NULL) {
		return NULL;
	}
	switch (list) {
	case LINK_LIST_SCENES:
		*count = state->scene_count;
		return state->scenes;
	case LINK_LIST_INPUTS:
		*count = state->input_count;
		return state->inputs;
	default: // LINK_LIST_TRANSITIONS: obs_state reads none
		return NULL;
	}
}

// The name span points into obs_state, which device_handle encodes before it returns.
static link_msg_t obs_item(const device_t *dev, const link_msg_t *request) {
	link_msg_t msg = {.type = LINK_OBS_ITEM};
	uint8_t list = request->as.obs_list.list;
	uint16_t index = request->as.obs_list.index;
	uint16_t total;
	const obs_item_t *items = obs_list_items(dev->obs_state, list, &total);
	msg.as.obs_item.list = list;
	msg.as.obs_item.index = index;
	msg.as.obs_item.total = total;
	if (index >= total) {
		return msg;
	}
	const obs_item_t *item = &items[index];
	uint8_t uuid[LINK_UUID_LEN];
	if (uuid_from_text(item->uuid, uuid)) {
		memcpy(msg.as.obs_item.uuid, uuid, LINK_UUID_LEN);
	}
	msg.as.obs_item.name =
	    (link_span_t){.bytes = (const uint8_t *)item->name, .len = strlen(item->name)};
	return msg;
}

static link_msg_t reply_to(device_t *dev, uint32_t now_ms, const link_frame_t *frame) {
	if (frame->type == LINK_SET_CREDENTIAL || frame->type == LINK_CLEAR_CREDENTIALS) {
		uint8_t status = link_credential_check(frame);
		if (status != LINK_CRED_OK) {
			return cred_status(status);
		}
	}
	link_msg_t request;
	if (!link_msg_decode(frame, &request)) {
		return result(dev, LINK_RESULT_INVALID);
	}
	switch (request.type) {
	case LINK_INFO_GET:
		return info_reply(dev);
	case LINK_CFG_READ:
		return cfg_read(dev, &request);
	case LINK_CFG_BEGIN:
		return cfg_begin(dev, &request);
	case LINK_CFG_CHUNK:
		return cfg_chunk(dev, &request);
	case LINK_CFG_COMMIT:
		return cfg_commit(dev, now_ms);
	case LINK_SET_CREDENTIAL:
		return set_credential(dev, &request);
	case LINK_CLEAR_CREDENTIALS:
		return cred_status_of(dev->cred->erase_all(dev->cred));
	case LINK_FACTORY_RESET:
		return cred_status_of(wipe(dev));
	case LINK_BOOTLOADER:
		return bootloader(dev);
	case LINK_OBS_LIST:
		return obs_item(dev, &request);
	default: // a pad-to-app type: it decodes, but the pad takes no such request
		return result(dev, LINK_RESULT_INVALID);
	}
}

bool device_handle(device_t *dev, uint32_t now_ms, const link_frame_t *frame, link_frame_t *reply) {
	link_msg_t msg = reply_to(dev, now_ms, frame);
	return link_msg_encode(&msg, frame->id, reply);
}

void device_tick(device_t *dev, uint32_t now_ms) {
	if (dev->trying && (int32_t)(now_ms - dev->try_until_ms) >= 0) {
		dev->trying = false;
	}
}

bool device_input(device_t *dev, const input_event_t *event) {
	return event->source != INPUT_SOURCE_CLEAR || wipe(dev);
}

bool device_input_frame(const input_event_t *event, link_frame_t *frame) {
	if (event->source == INPUT_SOURCE_CLEAR) {
		return false;
	}
	link_msg_t msg = {.type = LINK_INPUT};
	msg.as.input.source = event->source;
	msg.as.input.index = event->index;
	msg.as.input.value = event->value;
	return link_msg_encode(&msg, UNASKED_ID, frame);
}

static bool same_status(const link_msg_t *a, const link_msg_t *b) {
	return a->as.status.obs_state == b->as.status.obs_state &&
	       a->as.status.wifi_state == b->as.status.wifi_state &&
	       a->as.status.rssi_dbm == b->as.status.rssi_dbm &&
	       memcmp(a->as.status.ip, b->as.status.ip, sizeof a->as.status.ip) == 0;
}

bool device_status(device_t *dev, enum link_obs_state obs, const wifi_status_t *wifi,
                   link_frame_t *frame) {
	link_msg_t msg = {.type = LINK_STATUS};
	msg.as.status.obs_state = (uint8_t)obs;
	msg.as.status.wifi_state = (uint8_t)wifi->state;
	msg.as.status.rssi_dbm = wifi->rssi_dbm;
	memcpy(msg.as.status.ip, wifi->ip, sizeof msg.as.status.ip);
	if (dev->status_sent && same_status(&msg, &dev->status)) {
		return false;
	}
	if (!link_msg_encode(&msg, UNASKED_ID, frame)) {
		return false;
	}
	dev->status = msg;
	dev->status_sent = true;
	return true;
}

link_span_t device_draft(const device_t *dev) {
	if (!dev->trying) {
		return (link_span_t){.bytes = NULL, .len = 0};
	}
	return (link_span_t){.bytes = dev->write.bytes, .len = dev->write.total};
}

bool device_bootloader_asked(const device_t *dev) {
	return dev->bootloader_asked;
}
