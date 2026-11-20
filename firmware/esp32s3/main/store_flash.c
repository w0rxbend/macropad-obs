// SPDX-License-Identifier: MIT
// esp_partition calls are those of the IDF v6.1.1 header esp_partition.h. A log line names the
// slot, the offset and the esp_err name, never a document byte.
#include "store_flash.h"

#include "esp_log.h"

#include <inttypes.h>

// partitions.csv: `cfg_a` and `cfg_b` are data, subtype 0x40, the first one IDF leaves to apps.
#define SLOT_SUBTYPE ((esp_partition_subtype_t)0x40)

static const char *TAG = "store_flash";

static const esp_partition_t *partition_of(void *part) {
	return ((const store_flash_slot_t *)part)->part;
}

static bool succeeded(const char *call, const esp_partition_t *partition, uint32_t offset,
                      esp_err_t err) {
	if (err != ESP_OK) {
		ESP_LOGE(TAG, "%s %s @0x%" PRIx32 ": %s", call, partition->label, offset,
		         esp_err_to_name(err));
	}
	return err == ESP_OK;
}

// store.c erases whole STORE_SECTOR_BYTES sectors; store_flash_bind checked that erase_size divides
// them.
static bool flash_erase(void *part, uint32_t offset, uint32_t len) {
	const esp_partition_t *partition = partition_of(part);
	return succeeded("erase", partition, offset, esp_partition_erase_range(partition, offset, len));
}

// esp_partition_write programs without an erase, so it only clears bits, as store.h expects.
static bool flash_program(void *part, uint32_t offset, const uint8_t *bytes, uint32_t len) {
	const esp_partition_t *partition = partition_of(part);
	return succeeded("program", partition, offset,
	                 esp_partition_write(partition, offset, bytes, len));
}

static bool flash_read(void *part, uint32_t offset, uint8_t *out, uint32_t len) {
	const esp_partition_t *partition = partition_of(part);
	return succeeded("read", partition, offset, esp_partition_read(partition, offset, out, len));
}

static const store_flash_t STORE_FLASH = {
    .erase = flash_erase, .program = flash_program, .read = flash_read};

static esp_err_t find_slot(const char *label, store_flash_slot_t *slot) {
	const esp_partition_t *partition =
	    esp_partition_find_first(ESP_PARTITION_TYPE_DATA, SLOT_SUBTYPE, label);
	if (partition == NULL) {
		ESP_LOGE(TAG, "%s: no data partition of subtype 0x40", label);
		return ESP_ERR_NOT_FOUND;
	}
	if (partition->size < STORE_SLOT_BYTES || partition->erase_size == 0 ||
	    STORE_SECTOR_BYTES % partition->erase_size != 0) {
		ESP_LOGE(TAG, "%s: size 0x%" PRIx32 ", erase size 0x%" PRIx32 "; needs 0x%x in 0x%x sectors",
		         label, partition->size, partition->erase_size, STORE_SLOT_BYTES, STORE_SECTOR_BYTES);
		return ESP_ERR_INVALID_SIZE;
	}
	if (partition->readonly || partition->encrypted) {
		ESP_LOGE(TAG, "%s: read-only or encrypted", label);
		return ESP_ERR_NOT_ALLOWED;
	}
	slot->part = partition;
	return ESP_OK;
}

esp_err_t store_flash_bind(device_port_t *port, store_flash_slots_t *slots, cred_nvs_t *cred) {
	store_flash_slots_t found;
	esp_err_t err = find_slot("cfg_a", &found.a);
	if (err == ESP_OK) {
		err = find_slot("cfg_b", &found.b);
	}
	if (err != ESP_OK) {
		return err;
	}
	*slots = found;
	port->cred = &cred->cred;
	port->flash = &STORE_FLASH;
	port->slot_a = &slots->a;
	port->slot_b = &slots->b;
	return ESP_OK;
}
