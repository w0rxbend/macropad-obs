// SPDX-License-Identifier: MIT
// The device side of the CDC link (spec 8.2): takes each request frame that link_pull delivered,
// acts on the config store and the credential store, and builds its one reply (same id). Pure C,
// no SDK headers. Config flow and try-only rules: docs/protocol.md "Config flow", docs/config.md
// "Try-only revert". OBS_LIST, STATUS and INPUT frames are task 2.11b.
//
// Replies the spec leaves open, set here:
// - A frame the typed decoder refuses (unknown type, a pad-to-app type, a bad payload, a wrong
//   magic) gets RESULT invalid with the stored seq. A refused SET_CREDENTIAL or CLEAR_CREDENTIALS
//   gets CRED_STATUS with the status link_credential_check gives.
// - CFG_BEGIN and CFG_CHUNK get RESULT ok with the stored seq.
// - FACTORY_RESET and BOOTLOADER get CRED_STATUS: ok, or store_fail when an erase failed. A
//   BOOTLOADER whose cred erase failed does not ask for download mode (CLAUDE.md, R1).
// - A flash fault in CFG_READ or CFG_COMMIT gets RESULT busy: RESULT has no flash-fault code.
//   Retry later. A failed commit keeps the write open, so chunks can be sent again.
#pragma once

#include "cred.h"
#include "input.h"
#include "link.h"
#include "store.h"

#include <stdbool.h>
#include <stdint.h>

// A try-only draft runs this long after its CFG_COMMIT (spec 8.2).
#define DEVICE_TRY_MS 30000u

// What the device reaches. `identity` holds the fixed INFO fields; the device sets `proto`, the
// schema range, `max_doc_bytes` and the two credential bits itself.
typedef struct {
	const link_info_t *identity;
	cred_t *cred;
	const store_flash_t *flash;
	void *slot_a;
	void *slot_b;
} device_port_t;

// The bytes of one CFG_BEGIN .. CFG_COMMIT write, then of the try-only draft they made.
typedef struct {
	bool open; // CFG_BEGIN taken, CFG_COMMIT not yet ok
	bool try_only;
	uint32_t base_seq;
	uint16_t total;
	uint32_t crc32;
	uint8_t bytes[CONFIG_MAX_BYTES];
} device_write_t;

// Read `store`. The rest belongs to device.c.
typedef struct {
	store_t store;
	const link_info_t *identity;
	cred_t *cred;
	device_write_t write;
	bool trying; // `write.bytes` holds the draft the panels show
	uint32_t try_until_ms;
	bool bootloader_asked;
	// The spans of the reply being built point here until device_handle has encoded it.
	uint8_t reply_bytes[LINK_CFG_DATA_MAX];
	char reply_path[CONFIG_PATH_MAX + 1];
} device_t;

// Boot: mounts the store. No write is open and no draft runs.
void device_init(device_t *dev, const device_port_t *port);

// Handles one frame from link_pull at `now_ms` and writes its one reply into `reply`, with the
// frame's id. False only when the reply could not be encoded, which is a bug in device.c.
bool device_handle(device_t *dev, uint32_t now_ms, const link_frame_t *frame, link_frame_t *reply);

// Ends a try-only draft whose 30 s have run out. Call it on the port's tick.
void device_tick(device_t *dev, uint32_t now_ms);

// Takes one event of input_step. The clear key combination erases cred, then both cfg slots, as
// FACTORY_RESET does. Other events are task 2.11b. False when an erase failed.
bool device_input(device_t *dev, const input_event_t *event);

// The draft the panels show. Empty (NULL, 0) when they show the stored document or the defaults.
link_span_t device_draft(const device_t *dev);

// True once a BOOTLOADER erased cred: send its reply, then run the download-mode sequence.
bool device_bootloader_asked(const device_t *dev);
