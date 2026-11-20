// SPDX-License-Identifier: MIT
// Calls, event ids and reason codes are those of the IDF v6.1.1 headers esp_wifi.h,
// esp_wifi_types_generic.h and esp_netif_types.h. Not run on hardware yet (task 4.8).
//
// R1: esp_wifi_set_storage(WIFI_STORAGE_RAM) runs right after esp_wifi_init, before any
// esp_wifi_set_config; the default WIFI_STORAGE_FLASH writes SSID and passphrase to plain `nvs`.
// The config that carries the passphrase is wiped once the driver has its copy. No log line names
// the SSID, the passphrase or its length.
// IDF names its WIFI_EVENT id enum wifi_event_t too. In this file the core's struct is
// fw_wifi_event_t; it is the same type, so callers of wifi_port.h see no difference. No other
// file includes both wifi.h and esp_wifi.h.
#define wifi_event_t fw_wifi_event_t
#include "wifi_port.h"
#undef wifi_event_t

#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "nvs_flash.h"

#include <string.h>

// Driver events between two main-loop passes. A join gives at most a few; more means the loop
// stalled, and the overflow is logged.
#define EVENT_QUEUE_LEN 8
#define SSID_MAX sizeof(((wifi_sta_config_t *)0)->ssid)
#define PASSPHRASE_MAX sizeof(((wifi_sta_config_t *)0)->password)

static const char *TAG = "wifi_port";

static QueueHandle_t s_events;
static bool s_started; // the radio is on; only wifi_port_act changes it

// The compiler may drop a memset of a buffer that dies next. Writes through volatile stay.
static void wipe(void *bytes, size_t len) {
	volatile uint8_t *byte = bytes;
	while (len-- > 0) {
		*byte++ = 0;
	}
}

static void queue_event(const fw_wifi_event_t *event) {
	if (xQueueSend(s_events, event, 0) != pdTRUE) {
		ESP_LOGW(TAG, "event queue full, event %d dropped", (int)event->kind);
	}
}

static wifi_event_kind_t kind_of(uint8_t reason) {
	switch (reason) {
	case WIFI_REASON_AUTH_FAIL:
	case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT: // what a wrong WPA2 passphrase gives
	case WIFI_REASON_HANDSHAKE_TIMEOUT:
		return WIFI_EVT_BAD_KEY;
	case WIFI_REASON_NO_AP_FOUND:
	case WIFI_REASON_NO_AP_FOUND_W_COMPATIBLE_SECURITY:
	case WIFI_REASON_NO_AP_FOUND_IN_AUTHMODE_THRESHOLD:
	case WIFI_REASON_NO_AP_FOUND_IN_RSSI_THRESHOLD:
		return WIFI_EVT_NO_AP;
	default:
		return WIFI_EVT_LOST;
	}
}

static void on_wifi(void *arg, esp_event_base_t base, int32_t id, void *data) {
	(void)arg;
	(void)base;
	if (id == WIFI_EVENT_STA_START) {
		// The first join started the radio; its config is already set.
		esp_err_t err = esp_wifi_connect();
		if (err != ESP_OK) {
			ESP_LOGE(TAG, "connect: %s", esp_err_to_name(err));
			queue_event(&(fw_wifi_event_t){.kind = WIFI_EVT_LOST});
		}
	} else if (id == WIFI_EVENT_STA_DISCONNECTED) {
		const wifi_event_sta_disconnected_t *gone = data;
		// ASSOC_LEAVE is the station leaving on its own: this port's disconnect or stop.
		if (gone->reason != WIFI_REASON_ASSOC_LEAVE) {
			ESP_LOGI(TAG, "disconnected, reason %u", gone->reason);
			queue_event(&(fw_wifi_event_t){.kind = kind_of(gone->reason)});
		}
	}
}

static void on_ip(void *arg, esp_event_base_t base, int32_t id, void *data) {
	(void)arg;
	(void)base;
	(void)id; // registered for IP_EVENT_STA_GOT_IP only
	const ip_event_got_ip_t *got = data;
	fw_wifi_event_t up = {.kind = WIFI_EVT_UP};
	memcpy(up.ip, &got->ip_info.ip.addr, sizeof up.ip); // esp_ip4_addr_t is in network order
	int rssi = 0;
	if (esp_wifi_sta_get_rssi(&rssi) == ESP_OK) {
		up.rssi_dbm = (int8_t)rssi;
	}
	queue_event(&up);
}

// The PHY calibration data lives in the default `nvs`; no secret goes there (spec 10).
static esp_err_t init_default_nvs(void) {
	esp_err_t err = nvs_flash_init();
	if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
		ESP_RETURN_ON_ERROR(nvs_flash_erase(), TAG, "nvs erase");
		err = nvs_flash_init();
	}
	return err;
}

// Another port may have made these already.
static esp_err_t allow_made(esp_err_t err) {
	return err == ESP_ERR_INVALID_STATE ? ESP_OK : err;
}

esp_err_t wifi_port_init(void) {
	s_events = xQueueCreate(EVENT_QUEUE_LEN, sizeof(fw_wifi_event_t));
	ESP_RETURN_ON_FALSE(s_events, ESP_ERR_NO_MEM, TAG, "queue");
	ESP_RETURN_ON_ERROR(init_default_nvs(), TAG, "nvs");
	ESP_RETURN_ON_ERROR(allow_made(esp_netif_init()), TAG, "netif");
	ESP_RETURN_ON_ERROR(allow_made(esp_event_loop_create_default()), TAG, "event loop");
	ESP_RETURN_ON_FALSE(esp_netif_create_default_wifi_sta(), ESP_FAIL, TAG, "sta netif");

	wifi_init_config_t config = WIFI_INIT_CONFIG_DEFAULT();
	ESP_RETURN_ON_ERROR(esp_wifi_init(&config), TAG, "init");
	ESP_RETURN_ON_ERROR(esp_wifi_set_storage(WIFI_STORAGE_RAM), TAG, "storage");
	ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG, "mode");
	ESP_RETURN_ON_ERROR(
	    esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi, NULL, NULL), TAG,
	    "wifi events");
	return esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_ip, NULL, NULL);
}

// Fills the STA config. ESP_ERR_INVALID_ARG for an SSID outside 1..32 bytes,
// ESP_ERR_INVALID_SIZE for a stored passphrase that does not load into the driver's 64 bytes.
static esp_err_t fill_config(wifi_config_t *config, const char *ssid, cred_t *cred) {
	size_t ssid_len = ssid == NULL ? 0 : strnlen(ssid, SSID_MAX + 1);
	if (ssid_len == 0 || ssid_len > SSID_MAX) {
		return ESP_ERR_INVALID_ARG;
	}
	memcpy(config->sta.ssid, ssid, ssid_len);
	size_t key_len =
	    cred->get(cred, LINK_CREDENTIAL_WIFI_PASSPHRASE, config->sta.password, PASSPHRASE_MAX);
	if (key_len == 0 && cred->is_set(cred, LINK_CREDENTIAL_WIFI_PASSPHRASE)) {
		return ESP_ERR_INVALID_SIZE;
	}
	// With a passphrase of 8 bytes or more the driver joins WPA2 or better only (threshold note
	// in esp_wifi_types_generic.h), so no AP can talk it down to WEP or open.
	return ESP_OK;
}

static esp_err_t join(const char *ssid, cred_t *cred) {
	wifi_config_t config = {0};
	esp_err_t err = fill_config(&config, ssid, cred);
	if (err == ESP_OK && s_started) {
		// With no link up there is nothing to drop. set_config and connect report what matters.
		(void)esp_wifi_disconnect();
	}
	if (err == ESP_OK) {
		err = esp_wifi_set_config(WIFI_IF_STA, &config);
	}
	wipe(&config, sizeof config);
	if (err == ESP_OK && !s_started) {
		err = esp_wifi_start(); // WIFI_EVENT_STA_START then connects
		s_started = err == ESP_OK;
	} else if (err == ESP_OK) {
		err = esp_wifi_connect();
	}
	if (err != ESP_OK) {
		ESP_LOGE(TAG, "join: %s", esp_err_to_name(err));
		wifi_event_kind_t kind = err == ESP_ERR_INVALID_SIZE ? WIFI_EVT_BAD_KEY : WIFI_EVT_LOST;
		queue_event(&(fw_wifi_event_t){.kind = kind});
	}
	return err;
}

static esp_err_t leave(void) {
	if (!s_started) {
		return ESP_OK;
	}
	s_started = false;
	return esp_wifi_stop();
}

esp_err_t wifi_port_act(wifi_action_t action, const char *ssid, cred_t *cred) {
	switch (action) {
	case WIFI_ACT_NONE:
		return ESP_OK;
	case WIFI_ACT_JOIN:
		return join(ssid, cred);
	case WIFI_ACT_LEAVE:
		return leave();
	}
	return ESP_ERR_INVALID_ARG;
}

bool wifi_port_next_event(fw_wifi_event_t *out, uint32_t timeout_ms) {
	return xQueueReceive(s_events, out, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
}
