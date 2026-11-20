// SPDX-License-Identifier: MIT
#include "config.h"

config_result_t config_validate(const uint8_t *doc, size_t len) {
	(void)doc;
	(void)len;
	return (config_result_t){.verdict = CONFIG_UNIMPLEMENTED};
}
