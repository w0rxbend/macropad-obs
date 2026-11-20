// SPDX-License-Identifier: MIT
#include "store.h"

// ASCII "MPCF", little-endian. The header: magic, schema, seq, body length, body CRC-32, then the
// CRC-32 of those 20 bytes. All u32 little-endian.
#define HEADER_MAGIC 0x4643504Du
#define HEADER_CHECKED_BYTES 20
#define HEADER_BYTES (HEADER_CHECKED_BYTES + 4)
#define NO_SLOT (-1)
// The stack buffer a body CRC reads through.
#define READ_CHUNK 256

typedef struct {
	store_doc_t doc;
	uint32_t body_crc;
} header_t;

static uint32_t crc32_continue(uint32_t crc, const uint8_t *bytes, size_t len) {
	for (size_t i = 0; i < len; i++) {
		crc ^= bytes[i];
		for (int bit = 0; bit < 8; bit++) {
			crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
		}
	}
	return crc;
}

uint32_t store_crc32(const uint8_t *bytes, size_t len) {
	return ~crc32_continue(0xFFFFFFFFu, bytes, len);
}

static void put_u32(uint8_t *at, uint32_t value) {
	for (int i = 0; i < 4; i++) {
		at[i] = (uint8_t)(value >> (8 * i));
	}
}

static uint32_t get_u32(const uint8_t *at) {
	return (uint32_t)at[0] | (uint32_t)at[1] << 8 | (uint32_t)at[2] << 16 | (uint32_t)at[3] << 24;
}

static void encode_header(const header_t *header, uint8_t out[HEADER_BYTES]) {
	put_u32(&out[0], HEADER_MAGIC);
	put_u32(&out[4], header->doc.schema);
	put_u32(&out[8], header->doc.seq);
	put_u32(&out[12], header->doc.len);
	put_u32(&out[16], header->body_crc);
	put_u32(&out[20], store_crc32(out, HEADER_CHECKED_BYTES));
}

// False for an erased, torn or foreign header, or a length out of range.
static bool decode_header(const uint8_t in[HEADER_BYTES], header_t *header) {
	if (get_u32(&in[0]) != HEADER_MAGIC ||
	    get_u32(&in[20]) != store_crc32(in, HEADER_CHECKED_BYTES)) {
		return false;
	}
	header->doc.schema = get_u32(&in[4]);
	header->doc.seq = get_u32(&in[8]);
	header->doc.len = get_u32(&in[12]);
	header->body_crc = get_u32(&in[16]);
	return header->doc.len >= 1 && header->doc.len <= CONFIG_MAX_BYTES;
}

static bool body_matches(const store_t *store, int slot, const header_t *header) {
	uint8_t chunk[READ_CHUNK];
	uint32_t crc = 0xFFFFFFFFu;
	for (uint32_t at = 0; at < header->doc.len; at += READ_CHUNK) {
		uint32_t len = header->doc.len - at < READ_CHUNK ? header->doc.len - at : READ_CHUNK;
		if (!store->flash->read(store->slots[slot], STORE_BODY_OFFSET + at, chunk, len)) {
			return false;
		}
		crc = crc32_continue(crc, chunk, len);
	}
	return ~crc == header->body_crc;
}

static bool slot_is_good(const store_t *store, int slot, header_t *header) {
	uint8_t bytes[HEADER_BYTES];
	return store->flash->read(store->slots[slot], 0, bytes, HEADER_BYTES) &&
	       decode_header(bytes, header) && body_matches(store, slot, header);
}

static void make_current(store_t *store, int slot, const store_doc_t *doc) {
	store->current = slot;
	store->doc = *doc;
	bool in_range = doc->schema >= CONFIG_SCHEMA_MIN && doc->schema <= CONFIG_SCHEMA_MAX;
	store->state = in_range ? STORE_LOADED : STORE_UNLOADED;
}

static void drop_current(store_t *store) {
	store->current = NO_SLOT;
	store->doc = (store_doc_t){0};
	store->state = STORE_NONE;
}

void store_mount(store_t *store, const store_flash_t *flash, void *slot_a, void *slot_b) {
	*store = (store_t){.flash = flash, .slots = {slot_a, slot_b}};
	drop_current(store);
	header_t headers[2];
	bool good[2];
	for (int slot = 0; slot < 2; slot++) {
		good[slot] = slot_is_good(store, slot, &headers[slot]);
	}
	if (good[0] && (!good[1] || headers[0].doc.seq >= headers[1].doc.seq)) {
		make_current(store, 0, &headers[0].doc);
	} else if (good[1]) {
		make_current(store, 1, &headers[1].doc);
	}
}

bool store_read(const store_t *store, uint32_t offset, uint8_t *out, uint32_t len) {
	if (store->state == STORE_NONE || offset > store->doc.len || len > store->doc.len - offset) {
		return false;
	}
	return store->flash->read(store->slots[store->current], STORE_BODY_OFFSET + offset, out, len);
}

static uint32_t whole_sectors(uint32_t len) {
	return (len + STORE_SECTOR_BYTES - 1) / STORE_SECTOR_BYTES * STORE_SECTOR_BYTES;
}

// The header sector goes first, so the slot reads as bad from the first call on; the header is
// programmed last, so the slot reads as good only once the body is whole.
static bool write_slot(const store_t *store, int slot, const header_t *header, const uint8_t *body) {
	const store_flash_t *flash = store->flash;
	void *part = store->slots[slot];
	uint8_t bytes[HEADER_BYTES];
	encode_header(header, bytes);
	return flash->erase(part, 0, STORE_SECTOR_BYTES) &&
	       flash->erase(part, STORE_BODY_OFFSET, whole_sectors(header->doc.len)) &&
	       flash->program(part, STORE_BODY_OFFSET, body, header->doc.len) &&
	       flash->program(part, 0, bytes, HEADER_BYTES);
}

store_status_t store_commit(store_t *store, const store_doc_t *doc, const uint8_t *body) {
	if (doc->len < 1 || doc->len > CONFIG_MAX_BYTES) {
		return STORE_BAD_LEN;
	}
	// The higher seq wins at boot: a lower one would come back as the older document.
	if (store->state != STORE_NONE && doc->seq <= store->doc.seq) {
		return STORE_STALE_SEQ;
	}
	int target = store->current == 0 ? 1 : 0;
	header_t header = {.doc = *doc, .body_crc = store_crc32(body, doc->len)};
	header_t written;
	if (!write_slot(store, target, &header, body) || !slot_is_good(store, target, &written) ||
	    written.body_crc != header.body_crc) {
		return STORE_FLASH_FAIL;
	}
	make_current(store, target, doc);
	return STORE_OK;
}

store_status_t store_erase(store_t *store) {
	drop_current(store);
	bool erased = true;
	for (int slot = 0; slot < 2; slot++) {
		erased = store->flash->erase(store->slots[slot], 0, STORE_SLOT_BYTES) && erased;
	}
	return erased ? STORE_OK : STORE_FLASH_FAIL;
}

const char *store_strip_line(const store_t *store) {
	switch (store->state) {
	case STORE_LOADED:
		return NULL;
	case STORE_UNLOADED:
		if (store->doc.schema < CONFIG_SCHEMA_MIN) {
			return "Factory config, update config";
		}
		break;
	case STORE_NONE:
		break;
	}
	return "Factory config";
}
