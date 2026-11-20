// SPDX-License-Identifier: MIT
// Config document validator over the json.h stream reader. Rules, check order and paths:
// docs/config.md. host/obs_core/src/document.rs runs the same rules (R3).
#pragma once

#include <stddef.h>
#include <stdint.h>

#define CONFIG_MAX_BYTES 16384
// Longest path a verdict carries: the path field of RESULT (docs/protocol.md).
#define CONFIG_PATH_MAX 48
// The schema range this firmware reports in INFO and accepts in a document.
#define CONFIG_SCHEMA_MIN 1
#define CONFIG_SCHEMA_MAX 1

typedef enum {
	CONFIG_VALID,
	CONFIG_TOO_BIG,
	CONFIG_INVALID, // `path` is the first bad field, or empty for bytes that are no JSON object
} config_verdict_t;

typedef struct {
	config_verdict_t verdict;
	char path[CONFIG_PATH_MAX + 1]; // NUL-terminated. Empty unless the verdict is CONFIG_INVALID
} config_result_t;

// The verdict CFG_COMMIT gives the `len` bytes at `doc`. No heap. Takes under 4 kB of stack
// (3.4 kB of state on a 64-bit host): size the calling task for it.
config_result_t config_validate(const uint8_t *doc, size_t len);
