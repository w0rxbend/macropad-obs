// SPDX-License-Identifier: MIT
#include "settings.h"

#include "json.h"

#include <string.h>

#define WS_PREFIX "ws://"
#define OCTET_MAX 255u
#define PORT_MAX 65535u
#define BRIGHTNESS_MAX 100u

// Reads the decimal digits at `*at`, at most `max_digits` of them, into `*out`. False when there
// is none or the number passes `max`.
static bool read_decimal(const char **at, const char *end, size_t max_digits, uint32_t max, uint32_t *out) {
	const char *start = *at;
	uint32_t number = 0;
	while (*at < end && (size_t)(*at - start) < max_digits && **at >= '0' && **at <= '9') {
		number = number * 10u + (uint32_t)(**at - '0');
		(*at)++;
	}
	*out = number;
	return *at > start && number <= max;
}

// `ws://a.b.c.d[:port]`. config.c holds the whole URL rule; this reads what that rule let through
// and refuses anything else, so a bad document starts no OBS client.
static bool parse_ws_url(const char *text, size_t len, uint8_t ip[4], uint16_t *port) {
	const char *at = text + strlen(WS_PREFIX);
	const char *end = text + len;
	uint32_t number;
	if (len <= strlen(WS_PREFIX) || memcmp(text, WS_PREFIX, strlen(WS_PREFIX)) != 0) {
		return false;
	}
	for (size_t octet = 0; octet < 4; octet++) {
		if ((octet > 0 && (at == end || *at++ != '.')) || !read_decimal(&at, end, 3, OCTET_MAX, &number)) {
			return false;
		}
		ip[octet] = (uint8_t)number;
	}
	*port = SETTINGS_OBS_PORT_DEFAULT;
	if (at < end && *at == ':') {
		at++;
		if (!read_decimal(&at, end, 5, PORT_MAX, &number) || number == 0) {
			return false;
		}
		*port = (uint16_t)number;
	}
	return at == end;
}

static void keep_ssid(settings_t *settings, const json_event_t *event) {
	bool fits = event->len <= SETTINGS_SSID_MAX && memchr(event->text, '\0', event->len) == NULL;
	size_t len = fits ? event->len : 0;
	memcpy(settings->ssid, event->text, len);
	settings->ssid[len] = '\0';
}

static void keep_brightness(settings_t *settings, const json_event_t *event) {
	const char *at = event->text;
	uint32_t percent;
	if (read_decimal(&at, event->text + event->len, 3, BRIGHTNESS_MAX, &percent) && at == event->text + event->len) {
		settings->brightness_percent = (uint8_t)percent;
	}
}

static void keep_setting(void *context, const json_event_t *event) {
	settings_t *settings = context;
	if (event->kind == JSON_STRING && json_path_is(event, "wifi.ssid")) {
		keep_ssid(settings, event);
	} else if (event->kind == JSON_STRING && json_path_is(event, "obs.url")) {
		settings->has_obs = parse_ws_url(event->text, event->len, settings->obs_ip, &settings->obs_port);
	} else if (event->kind == JSON_STRING && json_path_is(event, "obs.auth_mode")) {
		settings->obs_auth = strcmp(event->text, "stored") == 0;
	} else if (event->kind == JSON_NUMBER && json_path_is(event, "ui.brightness")) {
		keep_brightness(settings, event);
	}
}

void settings_parse(settings_t *settings, const uint8_t *doc, size_t len) {
	*settings = (settings_t){.brightness_percent = SETTINGS_BRIGHTNESS_DEFAULT};
	if (len == 0) {
		return;
	}
	json_reader_t reader;
	json_reader_init(&reader, keep_setting, settings);
	json_feed(&reader, doc, len);
}
