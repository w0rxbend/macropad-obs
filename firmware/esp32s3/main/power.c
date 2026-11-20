// SPDX-License-Identifier: MIT
#include "power.h"

#include "pins.h"

void power_init(power_t *power, uint32_t boot_ms) {
	*power = (power_t){.boot_ms = boot_ms, .granted = false};
}

power_grant_t power_step(power_t *power, uint32_t now_ms, bool usb_configured, uint32_t cc_mv) {
	bool waited_out = now_ms - power->boot_ms >= POWER_ENUMERATION_WAIT_MS;
	power->granted = power->granted || usb_configured || waited_out;
	if (!power->granted) {
		return (power_grant_t){.radio = false, .backlight_cap_permille = 0};
	}
	uint16_t cap = cc_mv >= POWER_CC_1A5_THRESHOLD_MV ? POWER_PERMILLE_FULL : POWER_BACKLIGHT_CAP_PERMILLE;
	return (power_grant_t){.radio = true, .backlight_cap_permille = cap};
}

uint16_t power_backlight(power_grant_t grant, uint16_t wanted_permille) {
	return wanted_permille < grant.backlight_cap_permille ? wanted_permille : grant.backlight_cap_permille;
}
