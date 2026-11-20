// SPDX-License-Identifier: MIT
// The config slots (store.h) on esp_partition: `cfg_a` and `cfg_b`, raw data partitions of
// subtype 0x40 in partitions.csv (spec 10). No flash encryption, so reads and writes are raw.
// The slots hold no secret (R1); the credentials stay in `cred` behind cred_nvs.h.
#pragma once

#include "cred_nvs.h"
#include "device.h"

#include "esp_err.h"
#include "esp_partition.h"

// The `part` of store_flash_t: one slot's partition.
typedef struct {
	const esp_partition_t *part;
} store_flash_slot_t;

typedef struct {
	store_flash_slot_t a;
	store_flash_slot_t b;
} store_flash_slots_t;

// Finds `cfg_a` and `cfg_b` and fills the store fields of `port` for device_init: the slots, the
// flash calls, and `cred` (cred_nvs_init done). FACTORY_RESET and the clear key combination then
// run cred_nvs's whole-partition erase before they erase the slots (device.c, spec 8.2).
// ESP_ERR_NOT_FOUND when a slot is missing; ESP_ERR_INVALID_SIZE when one is smaller than
// STORE_SLOT_BYTES or does not erase in whole STORE_SECTOR_BYTES sectors; ESP_ERR_NOT_ALLOWED
// when one is read-only or encrypted. `port` is untouched on an error. `port` points into `slots`
// and `cred`: both live as long as the device.
esp_err_t store_flash_bind(device_port_t *port, store_flash_slots_t *slots, cred_nvs_t *cred);
