// SPDX-License-Identifier: MIT
#include "power.h"

#include "pins.h"

#include <stdio.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

#define CC_NONE 0u
#define CC_DEFAULT_USB 400u // a default-USB source shows 0.25 to 0.61 V on CC (USB Type-C 4-36)

static power_t booted_at(uint32_t boot_ms) {
	power_t power;
	power_init(&power, boot_ms);
	return power;
}

static void test_the_cap_values_come_from_board_toml(void) {
	CHECK(POWER_BACKLIGHT_CAP_PERMILLE > 0 && POWER_BACKLIGHT_CAP_PERMILLE < POWER_PERMILLE_FULL);
	CHECK(POWER_ENUMERATION_WAIT_MS == 2000);
	CHECK(POWER_CC_1A5_THRESHOLD_MV > 0);
}

static void test_everything_stays_off_before_usb_configures(void) {
	power_t power = booted_at(0);
	power_grant_t grant = power_step(&power, 0, false, CC_NONE);
	CHECK(!grant.radio);
	CHECK(grant.backlight_cap_permille == 0);
	grant = power_step(&power, POWER_ENUMERATION_WAIT_MS - 1, false, CC_NONE);
	CHECK(!grant.radio);
	CHECK(grant.backlight_cap_permille == 0);
}

static void test_usb_configured_grants_the_cap(void) {
	power_t power = booted_at(0);
	power_grant_t grant = power_step(&power, 500, true, CC_DEFAULT_USB);
	CHECK(grant.radio);
	CHECK(grant.backlight_cap_permille == POWER_BACKLIGHT_CAP_PERMILLE);
}

static void test_no_enumeration_in_the_wait_is_a_charger_at_the_same_cap(void) {
	power_t power = booted_at(0);
	power_grant_t grant = power_step(&power, POWER_ENUMERATION_WAIT_MS, false, CC_NONE);
	CHECK(grant.radio);
	CHECK(grant.backlight_cap_permille == POWER_BACKLIGHT_CAP_PERMILLE);
}

static void test_the_grant_stays_when_the_host_goes(void) {
	power_t power = booted_at(0);
	power_step(&power, 100, true, CC_NONE);
	power_grant_t grant = power_step(&power, 200, false, CC_NONE);
	CHECK(grant.radio);
	CHECK(grant.backlight_cap_permille == POWER_BACKLIGHT_CAP_PERMILLE);
}

static void test_a_1a5_advert_lifts_the_cap(void) {
	power_t power = booted_at(0);
	CHECK(power_step(&power, 100, true, POWER_CC_1A5_THRESHOLD_MV - 1).backlight_cap_permille ==
	      POWER_BACKLIGHT_CAP_PERMILLE);
	CHECK(power_step(&power, 110, true, POWER_CC_1A5_THRESHOLD_MV).backlight_cap_permille == POWER_PERMILLE_FULL);
	CHECK(power_step(&power, 120, true, CC_DEFAULT_USB).backlight_cap_permille ==
	      POWER_BACKLIGHT_CAP_PERMILLE);
}

static void test_a_1a5_advert_does_not_grant_before_usb_or_the_wait(void) {
	power_t power = booted_at(0);
	power_grant_t grant = power_step(&power, 100, false, POWER_CC_1A5_THRESHOLD_MV);
	CHECK(!grant.radio);
	CHECK(grant.backlight_cap_permille == 0);
}

static void test_the_wait_ends_on_time_across_the_clock_wrap(void) {
	uint32_t boot = UINT32_MAX - 500u;
	power_t power = booted_at(boot);
	CHECK(!power_step(&power, boot + POWER_ENUMERATION_WAIT_MS - 1u, false, CC_NONE).radio);
	CHECK(power_step(&power, boot + POWER_ENUMERATION_WAIT_MS, false, CC_NONE).radio);
}

static void test_a_backlight_is_the_wanted_level_held_under_the_cap(void) {
	power_grant_t off = {.radio = false, .backlight_cap_permille = 0};
	power_grant_t capped = {.radio = true, .backlight_cap_permille = 600};
	power_grant_t lifted = {.radio = true, .backlight_cap_permille = POWER_PERMILLE_FULL};
	CHECK(power_backlight(off, POWER_PERMILLE_FULL) == 0);
	CHECK(power_backlight(capped, POWER_PERMILLE_FULL) == 600);
	CHECK(power_backlight(capped, 600) == 600);
	CHECK(power_backlight(capped, 300) == 300);
	CHECK(power_backlight(capped, 0) == 0);
	CHECK(power_backlight(lifted, POWER_PERMILLE_FULL) == POWER_PERMILLE_FULL);
}

int main(void) {
	test_the_cap_values_come_from_board_toml();
	test_everything_stays_off_before_usb_configures();
	test_usb_configured_grants_the_cap();
	test_no_enumeration_in_the_wait_is_a_charger_at_the_same_cap();
	test_the_grant_stays_when_the_host_goes();
	test_a_1a5_advert_lifts_the_cap();
	test_a_1a5_advert_does_not_grant_before_usb_or_the_wait();
	test_the_wait_ends_on_time_across_the_clock_wrap();
	test_a_backlight_is_the_wanted_level_held_under_the_cap();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	puts("power: all tests pass");
	return 0;
}
