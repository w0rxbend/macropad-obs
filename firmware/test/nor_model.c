// SPDX-License-Identifier: MIT
#include "nor_model.h"

#include <string.h>

void nor_chip_init(nor_chip_t *chip) {
	memset(chip->bytes, 0xFF, sizeof chip->bytes);
	chip->calls_left = NOR_NO_CUT;
	chip->torn = false;
	chip->powered = true;
	chip->raised_a_bit = false;
	chip->mutations = 0;
}

void nor_chip_cut_after(nor_chip_t *chip, int calls, bool torn) {
	chip->calls_left = calls;
	chip->torn = torn;
}

void nor_chip_restore(nor_chip_t *chip) {
	chip->powered = true;
	chip->calls_left = NOR_NO_CUT;
	chip->torn = false;
}

static bool in_part(const nor_part_t *part, uint32_t offset, uint32_t len) {
	return offset <= part->size && len <= part->size - offset;
}

// How many of `len` bytes this call may change: all, half when torn at the cut, none after it.
static uint32_t bytes_this_call_changes(nor_chip_t *chip, uint32_t len) {
	if (!chip->powered) {
		return 0;
	}
	if (chip->calls_left == 0) {
		chip->powered = false;
		if (chip->torn) {
			chip->mutations++;
			return len / 2;
		}
		return 0;
	}
	if (chip->calls_left != NOR_NO_CUT) {
		chip->calls_left--;
	}
	chip->mutations++;
	return len;
}

static bool nor_erase(void *handle, uint32_t offset, uint32_t len) {
	nor_part_t *part = handle;
	if (!in_part(part, offset, len) || offset % STORE_SECTOR_BYTES != 0 ||
	    len % STORE_SECTOR_BYTES != 0) {
		return false;
	}
	uint32_t erased = bytes_this_call_changes(part->chip, len);
	memset(&part->chip->bytes[part->base + offset], 0xFF, erased);
	return erased == len;
}

static bool nor_program(void *handle, uint32_t offset, const uint8_t *bytes, uint32_t len) {
	nor_part_t *part = handle;
	if (!in_part(part, offset, len)) {
		return false;
	}
	uint32_t programmed = bytes_this_call_changes(part->chip, len);
	uint8_t *cells = &part->chip->bytes[part->base + offset];
	for (uint32_t i = 0; i < programmed; i++) {
		if ((bytes[i] & ~cells[i]) != 0) {
			part->chip->raised_a_bit = true;
		}
		cells[i] &= bytes[i];
	}
	return programmed == len;
}

static bool nor_read(void *handle, uint32_t offset, uint8_t *out, uint32_t len) {
	nor_part_t *part = handle;
	if (!part->chip->powered || !in_part(part, offset, len)) {
		return false;
	}
	memcpy(out, &part->chip->bytes[part->base + offset], len);
	return true;
}

const store_flash_t NOR_FLASH = {.erase = nor_erase, .program = nor_program, .read = nor_read};
