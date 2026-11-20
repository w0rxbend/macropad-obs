// SPDX-License-Identifier: MIT
#include "settings.h"

#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

static settings_t parse(const char *doc) {
	settings_t settings;
	settings_parse(&settings, (const uint8_t *)doc, strlen(doc));
	return settings;
}

static void test_the_config_md_example_gives_its_network_and_brightness(void) {
	settings_t s = parse("{\"schema\":1,\"seq\":17,"
	                     "\"obs\":{\"url\":\"ws://192.168.1.20:4455\",\"auth_mode\":\"stored\"},"
	                     "\"wifi\":{\"ssid\":\"studio\"},\"ui\":{\"brightness\":80}}");
	CHECK(strcmp(s.ssid, "studio") == 0);
	CHECK(s.has_obs);
	CHECK(memcmp(s.obs_ip, (uint8_t[]){192, 168, 1, 20}, 4) == 0);
	CHECK(s.obs_port == 4455);
	CHECK(s.obs_auth);
	CHECK(s.brightness_percent == 80);
}

static void test_a_url_without_a_port_uses_4455(void) {
	settings_t s = parse("{\"obs\":{\"url\":\"ws://10.0.0.7\",\"auth_mode\":\"none\"}}");
	CHECK(s.has_obs);
	CHECK(memcmp(s.obs_ip, (uint8_t[]){10, 0, 0, 7}, 4) == 0);
	CHECK(s.obs_port == SETTINGS_OBS_PORT_DEFAULT);
	CHECK(!s.obs_auth);
}

static void test_the_highest_octets_and_port_read_whole(void) {
	settings_t s = parse("{\"obs\":{\"url\":\"ws://172.31.255.254:65535\",\"auth_mode\":\"stored\"}}");
	CHECK(s.has_obs);
	CHECK(memcmp(s.obs_ip, (uint8_t[]){172, 31, 255, 254}, 4) == 0);
	CHECK(s.obs_port == 65535);
}

static void test_no_document_gives_the_factory_defaults(void) {
	settings_t s;
	settings_parse(&s, NULL, 0);
	CHECK(s.ssid[0] == '\0');
	CHECK(!s.has_obs);
	CHECK(s.brightness_percent == SETTINGS_BRIGHTNESS_DEFAULT);
}

static void test_an_empty_ssid_means_none(void) {
	settings_t s = parse("{\"wifi\":{\"ssid\":\"\"}}");
	CHECK(s.ssid[0] == '\0');
}

static void test_a_32_byte_ssid_is_kept_whole(void) {
	settings_t s = parse("{\"wifi\":{\"ssid\":\"0123456789abcdef0123456789abcdef\"}}");
	CHECK(strcmp(s.ssid, "0123456789abcdef0123456789abcdef") == 0);
}

static void test_a_ssid_the_driver_cannot_take_is_none(void) {
	CHECK(parse("{\"wifi\":{\"ssid\":\"0123456789abcdef0123456789abcdefX\"}}").ssid[0] == '\0');
	CHECK(parse("{\"wifi\":{\"ssid\":\"a\\u0000b\"}}").ssid[0] == '\0');
}

static void test_a_url_outside_the_rule_starts_no_obs(void) {
	static const char *const BAD[] = {
	    "{\"obs\":{\"url\":\"wss://192.168.1.20\"}}",    "{\"obs\":{\"url\":\"ws://192.168.1\"}}",
	    "{\"obs\":{\"url\":\"ws://192.168.1.256\"}}",    "{\"obs\":{\"url\":\"ws://192.168.1.2:0\"}}",
	    "{\"obs\":{\"url\":\"ws://192.168.1.2:65536\"}}", "{\"obs\":{\"url\":\"ws://192.168.1.2/\"}}",
	    "{\"obs\":{\"url\":\"ws://192.168.1.2:\"}}",     "{\"obs\":{\"url\":\"ws://obs.lan\"}}",
	};
	for (size_t i = 0; i < sizeof BAD / sizeof BAD[0]; i++) {
		CHECK(!parse(BAD[i]).has_obs);
	}
}

static void test_brightness_0_stays_0(void) {
	CHECK(parse("{\"ui\":{\"brightness\":0}}").brightness_percent == 0);
}

int main(void) {
	test_the_config_md_example_gives_its_network_and_brightness();
	test_a_url_without_a_port_uses_4455();
	test_the_highest_octets_and_port_read_whole();
	test_no_document_gives_the_factory_defaults();
	test_an_empty_ssid_means_none();
	test_a_32_byte_ssid_is_kept_whole();
	test_a_ssid_the_driver_cannot_take_is_none();
	test_a_url_outside_the_rule_starts_no_obs();
	test_brightness_0_stays_0();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	puts("settings: all tests pass");
	return 0;
}
