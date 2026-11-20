// SPDX-License-Identifier: MIT
// What the port reads from the config document for itself (docs/config.md): the SSID to join,
// the OBS address and auth mode, and the backlight brightness. Pure C on fw-json, no IDF header,
// host-tested (test_settings.c). The document holds no secret (R1), so neither does this.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define SETTINGS_SSID_MAX 32           // docs/config.md `wifi.ssid`, 0..32 bytes
#define SETTINGS_OBS_PORT_DEFAULT 4455 // docs/config.md "URL rule": no port means 4455
// No document: full brightness, which the power cap holds down (power.h). The strip line still
// has to show why the pad is not up.
#define SETTINGS_BRIGHTNESS_DEFAULT 100

typedef struct {
	char ssid[SETTINGS_SSID_MAX + 1]; // "" when none
	bool has_obs;                     // false: no `obs.url`, or one outside the URL rule
	uint8_t obs_ip[4];                // network order
	uint16_t obs_port;
	bool obs_auth;                    // `obs.auth_mode` is `stored`: log in with the stored password
	uint8_t brightness_percent;       // `ui.brightness`, 0..100
} settings_t;

// Reads `doc`, a document config_validate accepted, or none when `len` is 0. A field that is
// missing or outside its rule keeps its default: no SSID, no OBS, auth `none`, full brightness.
void settings_parse(settings_t *settings, const uint8_t *doc, size_t len);
