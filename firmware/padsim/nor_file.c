// SPDX-License-Identifier: MIT
#define _POSIX_C_SOURCE 200809L
#include "nor_file.h"

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static bool write_all(int fd, uint32_t at, const uint8_t *bytes, uint32_t len) {
	return pwrite(fd, bytes, len, at) == (ssize_t)len;
}

static bool read_all(int fd, uint32_t at, uint8_t *out, uint32_t len) {
	return pread(fd, out, len, at) == (ssize_t)len;
}

static bool fill_erased(int fd, uint32_t at, uint32_t len) {
	uint8_t erased[STORE_SECTOR_BYTES];
	memset(erased, 0xFF, sizeof erased);
	for (uint32_t done = 0; done < len; done += STORE_SECTOR_BYTES) {
		if (!write_all(fd, at + done, erased, STORE_SECTOR_BYTES)) {
			return false;
		}
	}
	return true;
}

bool nor_file_open(nor_file_t *file, const char *path, uint32_t cut_at) {
	*file = (nor_file_t){.fd = open(path, O_RDWR | O_CREAT, 0600), .cut_at = cut_at};
	struct stat info;
	if (file->fd < 0 || fstat(file->fd, &info) != 0) {
		fprintf(stderr, "padsim: %s: %s\n", path, strerror(errno));
		return false;
	}
	if (info.st_size == 0 && !fill_erased(file->fd, 0, NOR_FILE_BYTES)) {
		fprintf(stderr, "padsim: %s: cannot write the erased image\n", path);
		return false;
	}
	if (info.st_size != 0 && info.st_size != NOR_FILE_BYTES) {
		fprintf(stderr, "padsim: %s holds %lld bytes, not the %d of a NOR image\n", path,
		        (long long)info.st_size, NOR_FILE_BYTES);
		return false;
	}
	return true;
}

static bool in_part(const nor_file_part_t *part, uint32_t offset, uint32_t len) {
	return offset <= part->size && len <= part->size - offset;
}

static bool nor_erase(void *handle, uint32_t offset, uint32_t len) {
	nor_file_part_t *part = handle;
	if (!in_part(part, offset, len) || offset % STORE_SECTOR_BYTES != 0 ||
	    len % STORE_SECTOR_BYTES != 0) {
		return false;
	}
	return fill_erased(part->file->fd, part->base + offset, len);
}

// SIGKILL, not exit: no handler and no buffer flush runs, as when the power goes.
static void count_program_call(nor_file_t *file) {
	file->program_calls++;
	if (file->program_calls == file->cut_at) {
		fprintf(stderr, "padsim: cut at program call %u\n", (unsigned)file->program_calls);
		raise(SIGKILL);
	}
}

static bool nor_program(void *handle, uint32_t offset, const uint8_t *bytes, uint32_t len) {
	nor_file_part_t *part = handle;
	if (!in_part(part, offset, len)) {
		return false;
	}
	count_program_call(part->file);
	uint8_t cells[STORE_SECTOR_BYTES];
	for (uint32_t done = 0; done < len; done += sizeof cells) {
		uint32_t at = part->base + offset + done;
		uint32_t n = len - done < sizeof cells ? len - done : (uint32_t)sizeof cells;
		if (!read_all(part->file->fd, at, cells, n)) {
			return false;
		}
		for (uint32_t i = 0; i < n; i++) {
			cells[i] &= bytes[done + i];
		}
		if (!write_all(part->file->fd, at, cells, n)) {
			return false;
		}
	}
	return true;
}

static bool nor_read(void *handle, uint32_t offset, uint8_t *out, uint32_t len) {
	nor_file_part_t *part = handle;
	return in_part(part, offset, len) && read_all(part->file->fd, part->base + offset, out, len);
}

const store_flash_t NOR_FILE_FLASH = {.erase = nor_erase, .program = nor_program, .read = nor_read};

// ---- cred: one sector per kind, a length byte, then the secret. 0xFF: none stored. ----

_Static_assert(LINK_CREDENTIAL_MAX < 0xFF, "a length byte holds every secret length");

static nor_file_cred_t *as_file_cred(cred_t *cred) {
	return (nor_file_cred_t *)cred;
}

static bool known_kind(enum link_credential_kind kind) {
	return kind == LINK_CREDENTIAL_OBS_PASSWORD || kind == LINK_CREDENTIAL_WIFI_PASSPHRASE;
}

static uint32_t sector_of(enum link_credential_kind kind) {
	return ((uint32_t)kind - 1) * STORE_SECTOR_BYTES;
}

// 0 when no secret of `kind` is stored or the read failed.
static uint8_t stored_len(nor_file_cred_t *file_cred, enum link_credential_kind kind) {
	uint8_t len = 0;
	if (!known_kind(kind) || !nor_read(&file_cred->part, sector_of(kind), &len, 1) ||
	    len > LINK_CREDENTIAL_MAX) {
		return 0;
	}
	return len;
}

static bool cred_put(cred_t *cred, enum link_credential_kind kind, const uint8_t *bytes, size_t len) {
	nor_file_cred_t *file_cred = as_file_cred(cred);
	if (!known_kind(kind) || len < 1 || len > LINK_CREDENTIAL_MAX) {
		return false;
	}
	uint8_t record[1 + LINK_CREDENTIAL_MAX];
	record[0] = (uint8_t)len;
	memcpy(&record[1], bytes, len);
	uint32_t sector = sector_of(kind);
	bool stored = nor_erase(&file_cred->part, sector, STORE_SECTOR_BYTES) &&
	              nor_program(&file_cred->part, sector, record, (uint32_t)(1 + len));
	memset(record, 0, sizeof record);
	return stored;
}

static bool cred_is_set(cred_t *cred, enum link_credential_kind kind) {
	return stored_len(as_file_cred(cred), kind) > 0;
}

static size_t cred_get(cred_t *cred, enum link_credential_kind kind, uint8_t *out, size_t cap) {
	nor_file_cred_t *file_cred = as_file_cred(cred);
	uint8_t len = stored_len(file_cred, kind);
	if (len == 0 || len > cap || !nor_read(&file_cred->part, sector_of(kind) + 1, out, len)) {
		return 0;
	}
	return len;
}

static bool cred_erase_all(cred_t *cred) {
	return nor_erase(&as_file_cred(cred)->part, 0, NOR_FILE_CRED_BYTES);
}

void nor_file_cred_init(nor_file_cred_t *cred, nor_file_t *file) {
	*cred = (nor_file_cred_t){
	    .cred = {.put = cred_put, .is_set = cred_is_set, .get = cred_get, .erase_all = cred_erase_all},
	    .part = {.file = file, .base = NOR_FILE_CRED_BASE, .size = NOR_FILE_CRED_BYTES},
	};
}
