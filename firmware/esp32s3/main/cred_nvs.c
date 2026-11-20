// SPDX-License-Identifier: MIT
// NVS calls are those of the IDF v6.1.1 headers nvs_flash.h and nvs.h. No log line here names a
// secret or its length: only the key and the esp_err name (R1).
#include "cred_nvs.h"

#include "esp_check.h"
#include "esp_log.h"
#include "nvs_flash.h"

#define PARTITION "cred"
#define NAMESPACE "cred"

static const char *TAG = "cred_nvs";

static cred_nvs_t *as_nvs(cred_t *cred) {
	return (cred_nvs_t *)cred;
}

// NVS keys are at most 15 characters.
static const char *key_of(enum link_credential_kind kind) {
	switch (kind) {
	case LINK_CREDENTIAL_OBS_PASSWORD:
		return "obs_password";
	case LINK_CREDENTIAL_WIFI_PASSPHRASE:
		return "wifi_psk";
	}
	return NULL;
}

static esp_err_t open_partition(cred_nvs_t *store) {
	esp_err_t err = nvs_flash_init_partition(PARTITION);
	if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
		ESP_LOGW(TAG, "unreadable (%s), erasing", esp_err_to_name(err));
		ESP_RETURN_ON_ERROR(nvs_flash_erase_partition(PARTITION), TAG, "erase");
		err = nvs_flash_init_partition(PARTITION);
	}
	ESP_RETURN_ON_ERROR(err, TAG, "init");
	ESP_RETURN_ON_ERROR(nvs_open_from_partition(PARTITION, NAMESPACE, NVS_READWRITE, &store->handle),
	                    TAG, "open");
	store->open = true;
	return ESP_OK;
}

static void close_partition(cred_nvs_t *store) {
	if (store->open) {
		nvs_close(store->handle);
		store->open = false;
	}
	// ESP_ERR_NVS_NOT_INITIALIZED when the init failed: nothing to undo.
	(void)nvs_flash_deinit_partition(PARTITION);
}

// NVS writes the new entry before it drops the old one, so a failed set leaves the old value.
static bool cred_nvs_put(cred_t *cred, enum link_credential_kind kind, const uint8_t *bytes,
                         size_t len) {
	cred_nvs_t *store = as_nvs(cred);
	const char *key = key_of(kind);
	if (!store->open || key == NULL) {
		return false;
	}
	esp_err_t err = nvs_set_blob(store->handle, key, bytes, len);
	if (err == ESP_OK) {
		err = nvs_commit(store->handle);
	}
	if (err != ESP_OK) {
		ESP_LOGE(TAG, "put %s: %s", key, esp_err_to_name(err));
	}
	return err == ESP_OK;
}

static bool cred_nvs_is_set(cred_t *cred, enum link_credential_kind kind) {
	cred_nvs_t *store = as_nvs(cred);
	const char *key = key_of(kind);
	size_t len = 0;
	return store->open && key != NULL && nvs_get_blob(store->handle, key, NULL, &len) == ESP_OK &&
	       len > 0;
}

static size_t cred_nvs_get(cred_t *cred, enum link_credential_kind kind, uint8_t *out, size_t cap) {
	cred_nvs_t *store = as_nvs(cred);
	const char *key = key_of(kind);
	size_t len = cap;
	if (!store->open || key == NULL || nvs_get_blob(store->handle, key, out, &len) != ESP_OK) {
		return 0; // none stored, or ESP_ERR_NVS_INVALID_LENGTH: it does not fit in `cap`
	}
	return len;
}

// An overwrite leaves the old entry in its page until NVS reclaims it, so only a whole-partition
// erase removes every copy. The partition opens again after it, for the next SET_CREDENTIAL.
static bool cred_nvs_erase_all(cred_t *cred) {
	cred_nvs_t *store = as_nvs(cred);
	close_partition(store);
	esp_err_t err = nvs_flash_erase_partition(PARTITION);
	if (err != ESP_OK) {
		ESP_LOGE(TAG, "erase: %s", esp_err_to_name(err));
		return false;
	}
	if (open_partition(store) != ESP_OK) {
		ESP_LOGE(TAG, "reopen after erase failed; puts fail until the next boot");
	}
	return true;
}

esp_err_t cred_nvs_init(cred_nvs_t *store) {
	*store = (cred_nvs_t){
	    .cred = {.put = cred_nvs_put,
	             .is_set = cred_nvs_is_set,
	             .get = cred_nvs_get,
	             .erase_all = cred_nvs_erase_all},
	};
	return open_partition(store);
}
