// SPDX-License-Identifier: MIT
// A NOR flash chip for the host tests (research 13, item 6): erase sets whole sectors to 0xFF,
// program can only clear bits. The power can be cut after any number of erase and program calls,
// and the call that meets the cut can be torn: it changes only the first half of its bytes.
#pragma once

#include "store.h"

#include <stdbool.h>
#include <stdint.h>

#define NOR_CHIP_BYTES (2 * STORE_SLOT_BYTES + 2 * STORE_SECTOR_BYTES)
#define NOR_NO_CUT (-1)

typedef struct {
	uint8_t bytes[NOR_CHIP_BYTES];
	int calls_left;    // erase and program calls before the cut, or NOR_NO_CUT
	bool torn;         // the call that meets the cut does half its work before the power goes
	bool powered;      // false after the cut: every later call fails and changes nothing
	bool raised_a_bit; // a program asked for a 0 -> 1 change, which NOR cannot do
	int mutations;     // erase and program calls that ran, whole or torn
} nor_chip_t;

// A partition: `size` bytes of `chip` from `base`. The `part` of store_flash_t.
typedef struct {
	nor_chip_t *chip;
	uint32_t base;
	uint32_t size;
} nor_part_t;

// Erased, powered, no cut.
void nor_chip_init(nor_chip_t *chip);

// Cuts the power after `calls` more erase or program calls. `torn` tears the call that meets it.
void nor_chip_cut_after(nor_chip_t *chip, int calls, bool torn);

// Power back, no cut set. The bytes stay as the cut left them.
void nor_chip_restore(nor_chip_t *chip);

extern const store_flash_t NOR_FLASH;
