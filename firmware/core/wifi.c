// SPDX-License-Identifier: MIT
#include "wifi.h"

#include <stddef.h>
#include <string.h>

static const uint16_t RETRY_WAIT_MS[] = {1000, 2000, 4000, 8000};
#define LAST_RETRY_STEP (sizeof RETRY_WAIT_MS / sizeof RETRY_WAIT_MS[0] - 1)

void wifi_init(wifi_t *wifi) {
	*wifi = (wifi_t){.status = {.state = LINK_WIFI_NO_SSID}};
}

// The status of a link that is not up: no RSSI and no IP go with the state.
static wifi_status_t down_status(enum link_wifi_state state) {
	return (wifi_status_t){.state = state};
}

static void restart_retry_waits(wifi_t *wifi) {
	wifi->retry_pending = false;
	wifi->retry_step = 0;
}

static void start_retry_wait(wifi_t *wifi, uint32_t now_ms) {
	wifi->retry_pending = true;
	wifi->retry_wait_started_ms = now_ms;
	wifi->retry_wait_ms = RETRY_WAIT_MS[wifi->retry_step];
	if (wifi->retry_step < LAST_RETRY_STEP) {
		wifi->retry_step++;
	}
}

static enum link_wifi_state state_after_failure(wifi_event_kind_t kind) {
	switch (kind) {
	case WIFI_EVT_BAD_KEY:
		return LINK_WIFI_BAD_KEY;
	case WIFI_EVT_NO_AP:
		return LINK_WIFI_NO_AP;
	default:
		return LINK_WIFI_CONNECTING;
	}
}

static void go_up(wifi_t *wifi, const wifi_event_t *lease) {
	wifi->status.state = LINK_WIFI_UP;
	wifi->status.rssi_dbm = lease->rssi_dbm;
	memcpy(wifi->status.ip, lease->ip, sizeof wifi->status.ip);
	restart_retry_waits(wifi);
}

static void go_down(wifi_t *wifi, wifi_event_kind_t failure, uint32_t now_ms) {
	wifi->status = down_status(state_after_failure(failure));
	if (!wifi->retry_pending) {
		start_retry_wait(wifi, now_ms);
	}
}

wifi_action_t wifi_on_event(wifi_t *wifi, const wifi_event_t *event, uint32_t now_ms) {
	if (event->kind == WIFI_EVT_SSID_SET) {
		wifi->status = down_status(LINK_WIFI_CONNECTING);
		restart_retry_waits(wifi);
		return WIFI_ACT_JOIN;
	}
	if (wifi->status.state == LINK_WIFI_NO_SSID) {
		// Off the air already: a driver event is stale, and there is no link to leave.
		return WIFI_ACT_NONE;
	}
	if (event->kind == WIFI_EVT_NO_SSID) {
		wifi->status = down_status(LINK_WIFI_NO_SSID);
		restart_retry_waits(wifi);
		return WIFI_ACT_LEAVE;
	}
	if (event->kind == WIFI_EVT_UP) {
		go_up(wifi, event);
	} else {
		go_down(wifi, event->kind, now_ms);
	}
	return WIFI_ACT_NONE;
}

wifi_action_t wifi_tick(wifi_t *wifi, uint32_t now_ms) {
	if (!wifi->retry_pending) {
		return WIFI_ACT_NONE;
	}
	// Unsigned difference: the wait ends on time when the millisecond clock wraps.
	uint32_t waited_ms = now_ms - wifi->retry_wait_started_ms;
	if (waited_ms < wifi->retry_wait_ms) {
		return WIFI_ACT_NONE;
	}
	wifi->retry_pending = false;
	return WIFI_ACT_JOIN;
}

const char *wifi_strip_line(enum link_wifi_state state) {
	switch (state) {
	case LINK_WIFI_NO_SSID:
		return "Wi-Fi not set";
	case LINK_WIFI_BAD_KEY:
		return "Wrong Wi-Fi key";
	case LINK_WIFI_NO_AP:
		return "Wi-Fi not found";
	case LINK_WIFI_CONNECTING:
	case LINK_WIFI_UP:
		break;
	}
	return NULL;
}
