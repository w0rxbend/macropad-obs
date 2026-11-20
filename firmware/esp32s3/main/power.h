// SPDX-License-Identifier: MIT
// The VBUS power cap (spec 13 criterion 15, spec 14, report 18 section 4). Pure C, no IDF header,
// host-tested (test_power.c). The values come from board.toml [power] through pins.h.
//
// Backlights and Wi-Fi stay off until USB configures. With no configuration POWER_ENUMERATION_WAIT_MS
// after boot the pad is on a charger and runs anyway, at the same cap. Once given, the grant stays:
// a host that goes away leaves the pad on the same supply. A source that advertises 1.5 A or more
// on CC lifts the backlight cap; a lower advert puts it back.
#pragma once

#include <stdbool.h>
#include <stdint.h>

#define POWER_PERMILLE_FULL 1000

typedef struct {
	uint32_t boot_ms;
	bool granted;
} power_t;

// What may run now.
typedef struct {
	bool radio;                      // Wi-Fi may join
	uint16_t backlight_cap_permille; // the most either backlight may have; 0 while held off
} power_grant_t;

void power_init(power_t *power, uint32_t boot_ms);

// Call on every pass. `usb_configured` is the host's SET_CONFIGURATION state; `cc_mv` the higher
// of the two CC voltages. `now_ms` may wrap.
power_grant_t power_step(power_t *power, uint32_t now_ms, bool usb_configured, uint32_t cc_mv);

// The PWM a backlight gets: `wanted_permille` held under the grant's cap.
uint16_t power_backlight(power_grant_t grant, uint16_t wanted_permille);
