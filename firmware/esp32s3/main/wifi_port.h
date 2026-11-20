// SPDX-License-Identifier: MIT
// The Wi-Fi station on esp_wifi, 2.4 GHz STA (spec 10, R1). The driver keeps its config in RAM
// only, so no SSID or passphrase reaches the default `nvs`. The passphrase loads from `cred` on
// every join, so on every boot. fw-wifi (wifi.h) decides; this port feeds it the driver's events
// and does the action it returns.
#pragma once

#include "cred.h"
#include "wifi.h"

#include "esp_err.h"

#include <stdbool.h>
#include <stdint.h>

// Brings up the default `nvs` (PHY calibration only), esp_netif, the default event loop and the
// driver in STA mode, radio off. Call once, before the rest.
esp_err_t wifi_port_init(void);

// Does what wifi_on_event or wifi_tick returned. WIFI_ACT_JOIN drops any link and joins `ssid`
// (NUL-terminated, 1..32 bytes) with the passphrase of `cred`, or open when none is stored; the
// first join starts the radio. WIFI_ACT_LEAVE stops the radio. A join that cannot start queues
// its own failure event (WIFI_EVT_BAD_KEY for a stored passphrase that does not load,
// WIFI_EVT_LOST otherwise), so fw-wifi's retry runs; the return value is for the log.
esp_err_t wifi_port_act(wifi_action_t action, const char *ssid, cred_t *cred);

// Takes the next driver event for wifi_on_event, waiting up to `timeout_ms`. False when none
// came. The disconnect that this port's own join or leave causes is never queued.
bool wifi_port_next_event(wifi_event_t *out, uint32_t timeout_ms);
