// SPDX-License-Identifier: MIT
#include "device.h"

#include "config.h"
#include "json.h"

#include <stdlib.h>
#include <string.h>

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

// The OBS session's lists are task 2.11b. Until then the pad holds none: total 0, no item.
static link_msg_t no_obs_item(const link_msg_t *request) {
	link_msg_t msg = {.type = LINK_OBS_ITEM};
	msg.as.obs_item.list = request->as.obs_list.list;
	msg.as.obs_item.index = request->as.obs_list.index;
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
		return no_obs_item(&request);
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

link_span_t device_draft(const device_t *dev) {
	if (!dev->trying) {
		return (link_span_t){.bytes = NULL, .len = 0};
	}
	return (link_span_t){.bytes = dev->write.bytes, .len = dev->write.total};
}

bool device_bootloader_asked(const device_t *dev) {
	return dev->bootloader_asked;
}
