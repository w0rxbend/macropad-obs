// SPDX-License-Identifier: MIT
// padsim's flash: one image file in the order of the pad's partitions, `cfg_a`, `cfg_b`, then
// `cred`. Each call goes straight to the file, so a killed process leaves the image as the last
// whole call left it, and the next start mounts the same bytes. Erase sets 0xFF, program can only
// clear bits, as on NOR. `--cut-after N` kills the process when program call N begins: that call
// writes nothing, as a power cut before it would.
#pragma once

#include "cred.h"
#include "store.h"

#include <stdbool.h>
#include <stdint.h>

#define NOR_FILE_CRED_BASE (2 * STORE_SLOT_BYTES)
// One sector per credential kind.
#define NOR_FILE_CRED_BYTES (2 * STORE_SECTOR_BYTES)
#define NOR_FILE_BYTES (NOR_FILE_CRED_BASE + NOR_FILE_CRED_BYTES)
#define NOR_FILE_NO_CUT 0

typedef struct {
	int fd;
	uint32_t program_calls;
	uint32_t cut_at; // the program call that kills the process, or NOR_FILE_NO_CUT
} nor_file_t;

// One partition: `size` bytes of the image from `base`. The `part` of store_flash_t.
typedef struct {
	nor_file_t *file;
	uint32_t base;
	uint32_t size;
} nor_file_part_t;

// Opens the image at `path`, or makes an erased one when the file is absent or empty. False,
// with the reason on stderr, when it cannot, or when the file has another size.
bool nor_file_open(nor_file_t *file, const char *path, uint32_t cut_at);

extern const store_flash_t NOR_FILE_FLASH;

// The credential store on the `cred` partition of the image.
typedef struct {
	cred_t cred; // first, so a nor_file_cred_t * is a cred_t *
	nor_file_part_t part;
} nor_file_cred_t;

void nor_file_cred_init(nor_file_cred_t *cred, nor_file_t *file);
