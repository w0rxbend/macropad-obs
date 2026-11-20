// SPDX-License-Identifier: MIT
// The credential store (cred.h) on plain NVS in its own partition, `cred` (spec 10, D8, R1).
// This file owns nvs_flash_init_partition("cred") and nvs_flash_erase_partition("cred"); nothing
// else opens or erases that partition. No NVS encryption: the key would sit in the same flash.
#pragma once

#include "cred.h"

#include "esp_err.h"
#include "nvs.h"

#include <stdbool.h>

typedef struct {
	cred_t cred; // first, so a cred_nvs_t * is a cred_t *
	nvs_handle_t handle;
	bool open; // false when the partition could not be opened; every call then fails
} cred_nvs_t;

// Opens `cred`. A partition NVS cannot read (no free page, newer layout) is erased and opened
// again: it holds secrets only, so nothing else is lost.
esp_err_t cred_nvs_init(cred_nvs_t *store);
