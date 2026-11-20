// SPDX-License-Identifier: MIT
// The config store (spec 8.2, 10): two raw flash slots, `cfg_a` and `cfg_b`. A commit writes the
// slot that does not hold the current document, body first and header last, so a power cut at any
// point leaves the old document or the new one, never a mix. Pure C, no SDK headers: the port puts
// esp_partition behind store_flash_t, firmware/test a NOR model. No secret is stored here (R1);
// credentials have their own partition behind cred.h.
#pragma once

#include "config.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define STORE_SECTOR_BYTES 4096
// A slot is one header sector, then the body. Each slot partition holds at least this many bytes.
#define STORE_BODY_OFFSET STORE_SECTOR_BYTES
#define STORE_SLOT_BYTES (STORE_BODY_OFFSET + CONFIG_MAX_BYTES)

// The flash under one slot. `part` is the port's handle of that slot's partition; offsets count
// from its start. erase takes whole sectors and leaves 0xFF; program can only clear bits. Each
// call returns false when the flash refused it.
typedef struct {
	bool (*erase)(void *part, uint32_t offset, uint32_t len);
	bool (*program)(void *part, uint32_t offset, const uint8_t *bytes, uint32_t len);
	bool (*read)(void *part, uint32_t offset, uint8_t *out, uint32_t len);
} store_flash_t;

typedef enum {
	STORE_NONE,     // no slot holds a good document: the pad runs on its factory defaults
	STORE_LOADED,   // a good document with a `schema` from CONFIG_SCHEMA_MIN to CONFIG_SCHEMA_MAX
	STORE_UNLOADED, // a good document with a `schema` outside that range: kept, served, not run
} store_state_t;

// What the header of the current slot says about its body.
typedef struct {
	uint32_t schema;
	uint32_t seq;
	uint32_t len; // body bytes, 1..CONFIG_MAX_BYTES
} store_doc_t;

typedef enum {
	STORE_OK,
	STORE_BAD_LEN,    // the body is empty or longer than CONFIG_MAX_BYTES; nothing is written
	STORE_STALE_SEQ,  // `seq` is not above the current one; nothing is written
	STORE_FLASH_FAIL, // erase, program or read-back failed; the current document stays current
} store_status_t;

// Read `state`, and `doc` unless the state is STORE_NONE. The rest belongs to store.c.
typedef struct {
	store_state_t state;
	store_doc_t doc;
	const store_flash_t *flash;
	void *slots[2];
	int current; // index into `slots`, or -1
} store_t;

// Boot: picks the good slot with the higher `seq`. A slot is good when its header has the magic,
// its own CRC-32 and a length in range, and the body matches the header's CRC-32. Writes nothing,
// so a document with a `schema` below min (older firmware's) survives, and CFG_READ serves it.
void store_mount(store_t *store, const store_flash_t *flash, void *slot_a, void *slot_b);

// Copies `len` bytes of the current body from `offset` (CFG_READ). False when the state is
// STORE_NONE, the range runs past `doc.len`, or the flash read failed.
bool store_read(const store_t *store, uint32_t offset, uint8_t *out, uint32_t len);

// CFG_COMMIT, after config_validate passed: writes `doc->len` bytes at `body` with `doc->schema`
// and `doc->seq` to the other slot, reads it back, and makes it current. The display freezes
// while a sector erases: call it on CFG_COMMIT only.
store_status_t store_commit(store_t *store, const store_doc_t *doc, const uint8_t *body);

// FACTORY_RESET and the clear key combination, after cred is erased: erases both slots. The
// state is STORE_NONE after it, even when an erase failed.
store_status_t store_erase(store_t *store);

// CRC-32 (IEEE 802.3, reflected, as zlib), the one CFG_BEGIN carries. "123456789" -> 0xCBF43926.
uint32_t store_crc32(const uint8_t *bytes, size_t len);
