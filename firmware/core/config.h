// SPDX-License-Identifier: MIT
// Config document validator. Rules, check order and paths: docs/config.md.
// Stub until task 2.9: it runs no rule and answers CONFIG_UNIMPLEMENTED for every document.
#pragma once

#include <stddef.h>
#include <stdint.h>

#define CONFIG_MAX_BYTES 16384
// Longest path a verdict carries: the path field of RESULT (docs/protocol.md).
#define CONFIG_PATH_MAX 48

typedef enum {
	CONFIG_VALID,
	CONFIG_TOO_BIG,
	CONFIG_INVALID,       // `path` is the first bad field, or empty for bytes that are no JSON object
	CONFIG_UNIMPLEMENTED, // no rule ran: the only answer of the stub
} config_verdict_t;

typedef struct {
	config_verdict_t verdict;
	char path[CONFIG_PATH_MAX + 1]; // NUL-terminated. Empty unless the verdict is CONFIG_INVALID
} config_result_t;

// The verdict CFG_COMMIT gives the `len` bytes at `doc`.
config_result_t config_validate(const uint8_t *doc, size_t len);
