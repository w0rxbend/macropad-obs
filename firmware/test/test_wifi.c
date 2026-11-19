// SPDX-License-Identifier: MIT
#include "wifi.h"

#include <stdio.h>
#include <string.h>

#define STATE_COUNT 5
#define EVENT_COUNT 6

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

static const wifi_event_t LEASE = {.kind = WIFI_EVT_UP, .rssi_dbm = -61, .ip = {192, 168, 1, 50}};
static const uint8_t NO_IP[4] = {0, 0, 0, 0};
static const wifi_event_kind_t JOIN_FAILURES[] = {WIFI_EVT_BAD_KEY, WIFI_EVT_NO_AP, WIFI_EVT_LOST};
#define JOIN_FAILURE_COUNT (sizeof JOIN_FAILURES / sizeof JOIN_FAILURES[0])

// Every event carries the lease bytes, so a state that is not up has to drop them.
static wifi_action_t feed(wifi_t *wifi, wifi_event_kind_t kind, uint32_t now_ms) {
	wifi_event_t event = LEASE;
	event.kind = kind;
	return wifi_on_event(wifi, &event, now_ms);
}

// A machine that the event feed has brought to `state` at time 0.
static wifi_t wifi_in(enum link_wifi_state state) {
	wifi_t wifi;
	wifi_init(&wifi);
	if (state != LINK_WIFI_NO_SSID) {
		feed(&wifi, WIFI_EVT_SSID_SET, 0);
	}
	if (state == LINK_WIFI_BAD_KEY) {
		feed(&wifi, WIFI_EVT_BAD_KEY, 0);
	}
	if (state == LINK_WIFI_NO_AP) {
		feed(&wifi, WIFI_EVT_NO_AP, 0);
	}
	if (state == LINK_WIFI_UP) {
		feed(&wifi, WIFI_EVT_UP, 0);
	}
	return wifi;
}

static bool has_the_lease(const wifi_t *wifi) {
	return wifi->status.rssi_dbm == LEASE.rssi_dbm && memcmp(wifi->status.ip, LEASE.ip, 4) == 0;
}

static bool has_no_lease(const wifi_t *wifi) {
	return wifi->status.rssi_dbm == 0 && memcmp(wifi->status.ip, NO_IP, 4) == 0;
}

// True when the wait that began at `started_ms` ends at `started_ms + wait_ms`, not 1 ms sooner,
// and gives one join. The sums wrap as the pad's millisecond clock does.
static bool retry_comes_after(wifi_t *wifi, uint32_t started_ms, uint32_t wait_ms) {
	bool early = wifi_tick(wifi, started_ms + wait_ms - 1) != WIFI_ACT_NONE;
	bool on_time = wifi_tick(wifi, started_ms + wait_ms) == WIFI_ACT_JOIN;
	bool twice = wifi_tick(wifi, started_ms + wait_ms) != WIFI_ACT_NONE;
	return !early && on_time && !twice;
}

static void test_boot_is_no_ssid_and_asks_for_nothing(void) {
	wifi_t wifi;
	wifi_init(&wifi);
	CHECK(wifi.status.state == LINK_WIFI_NO_SSID);
	CHECK(has_no_lease(&wifi));
	CHECK(wifi_tick(&wifi, 0) == WIFI_ACT_NONE);
	CHECK(wifi_tick(&wifi, 60000) == WIFI_ACT_NONE);
}

static void test_the_feed_reaches_every_state(void) {
	for (int state = 0; state < STATE_COUNT; state++) {
		wifi_t wifi = wifi_in((enum link_wifi_state)state);
		CHECK((int)wifi.status.state == state);
	}
}

static const struct {
	enum link_wifi_state from;
	wifi_event_kind_t event;
	enum link_wifi_state to;
	wifi_action_t action;
} TRANSITIONS[] = {
	{LINK_WIFI_NO_SSID, WIFI_EVT_SSID_SET, LINK_WIFI_CONNECTING, WIFI_ACT_JOIN},
	{LINK_WIFI_NO_SSID, WIFI_EVT_NO_SSID, LINK_WIFI_NO_SSID, WIFI_ACT_NONE},
	{LINK_WIFI_NO_SSID, WIFI_EVT_UP, LINK_WIFI_NO_SSID, WIFI_ACT_NONE},
	{LINK_WIFI_NO_SSID, WIFI_EVT_BAD_KEY, LINK_WIFI_NO_SSID, WIFI_ACT_NONE},
	{LINK_WIFI_NO_SSID, WIFI_EVT_NO_AP, LINK_WIFI_NO_SSID, WIFI_ACT_NONE},
	{LINK_WIFI_NO_SSID, WIFI_EVT_LOST, LINK_WIFI_NO_SSID, WIFI_ACT_NONE},
	{LINK_WIFI_CONNECTING, WIFI_EVT_SSID_SET, LINK_WIFI_CONNECTING, WIFI_ACT_JOIN},
	{LINK_WIFI_CONNECTING, WIFI_EVT_NO_SSID, LINK_WIFI_NO_SSID, WIFI_ACT_LEAVE},
	{LINK_WIFI_CONNECTING, WIFI_EVT_UP, LINK_WIFI_UP, WIFI_ACT_NONE},
	{LINK_WIFI_CONNECTING, WIFI_EVT_BAD_KEY, LINK_WIFI_BAD_KEY, WIFI_ACT_NONE},
	{LINK_WIFI_CONNECTING, WIFI_EVT_NO_AP, LINK_WIFI_NO_AP, WIFI_ACT_NONE},
	{LINK_WIFI_CONNECTING, WIFI_EVT_LOST, LINK_WIFI_CONNECTING, WIFI_ACT_NONE},
	{LINK_WIFI_BAD_KEY, WIFI_EVT_SSID_SET, LINK_WIFI_CONNECTING, WIFI_ACT_JOIN},
	{LINK_WIFI_BAD_KEY, WIFI_EVT_NO_SSID, LINK_WIFI_NO_SSID, WIFI_ACT_LEAVE},
	{LINK_WIFI_BAD_KEY, WIFI_EVT_UP, LINK_WIFI_UP, WIFI_ACT_NONE},
	{LINK_WIFI_BAD_KEY, WIFI_EVT_BAD_KEY, LINK_WIFI_BAD_KEY, WIFI_ACT_NONE},
	{LINK_WIFI_BAD_KEY, WIFI_EVT_NO_AP, LINK_WIFI_NO_AP, WIFI_ACT_NONE},
	{LINK_WIFI_BAD_KEY, WIFI_EVT_LOST, LINK_WIFI_CONNECTING, WIFI_ACT_NONE},
	{LINK_WIFI_NO_AP, WIFI_EVT_SSID_SET, LINK_WIFI_CONNECTING, WIFI_ACT_JOIN},
	{LINK_WIFI_NO_AP, WIFI_EVT_NO_SSID, LINK_WIFI_NO_SSID, WIFI_ACT_LEAVE},
	{LINK_WIFI_NO_AP, WIFI_EVT_UP, LINK_WIFI_UP, WIFI_ACT_NONE},
	{LINK_WIFI_NO_AP, WIFI_EVT_BAD_KEY, LINK_WIFI_BAD_KEY, WIFI_ACT_NONE},
	{LINK_WIFI_NO_AP, WIFI_EVT_NO_AP, LINK_WIFI_NO_AP, WIFI_ACT_NONE},
	{LINK_WIFI_NO_AP, WIFI_EVT_LOST, LINK_WIFI_CONNECTING, WIFI_ACT_NONE},
	{LINK_WIFI_UP, WIFI_EVT_SSID_SET, LINK_WIFI_CONNECTING, WIFI_ACT_JOIN},
	{LINK_WIFI_UP, WIFI_EVT_NO_SSID, LINK_WIFI_NO_SSID, WIFI_ACT_LEAVE},
	{LINK_WIFI_UP, WIFI_EVT_UP, LINK_WIFI_UP, WIFI_ACT_NONE},
	{LINK_WIFI_UP, WIFI_EVT_BAD_KEY, LINK_WIFI_BAD_KEY, WIFI_ACT_NONE},
	{LINK_WIFI_UP, WIFI_EVT_NO_AP, LINK_WIFI_NO_AP, WIFI_ACT_NONE},
	{LINK_WIFI_UP, WIFI_EVT_LOST, LINK_WIFI_CONNECTING, WIFI_ACT_NONE},
};
#define TRANSITION_COUNT (sizeof TRANSITIONS / sizeof TRANSITIONS[0])

static void test_the_transition_table_names_every_state_and_event_once(void) {
	int named[STATE_COUNT][EVENT_COUNT] = {{0}};
	for (size_t i = 0; i < TRANSITION_COUNT; i++) {
		named[TRANSITIONS[i].from][TRANSITIONS[i].event]++;
	}
	for (int state = 0; state < STATE_COUNT; state++) {
		for (int event = 0; event < EVENT_COUNT; event++) {
			CHECK(named[state][event] == 1);
		}
	}
}

static void test_every_event_in_every_state_gives_its_state_and_action(void) {
	for (size_t i = 0; i < TRANSITION_COUNT; i++) {
		wifi_t wifi = wifi_in(TRANSITIONS[i].from);
		wifi_action_t action = feed(&wifi, TRANSITIONS[i].event, 0);
		CHECK(wifi.status.state == TRANSITIONS[i].to);
		CHECK(action == TRANSITIONS[i].action);
	}
}

static void test_rssi_and_ip_are_zero_unless_up(void) {
	for (size_t i = 0; i < TRANSITION_COUNT; i++) {
		wifi_t wifi = wifi_in(TRANSITIONS[i].from);
		feed(&wifi, TRANSITIONS[i].event, 0);
		if (wifi.status.state == LINK_WIFI_UP) {
			CHECK(has_the_lease(&wifi));
		} else {
			CHECK(has_no_lease(&wifi));
		}
	}
}

static void test_up_again_takes_the_new_rssi_and_ip(void) {
	wifi_t wifi = wifi_in(LINK_WIFI_UP);
	wifi_event_t renewed = {.kind = WIFI_EVT_UP, .rssi_dbm = -70, .ip = {10, 0, 0, 7}};
	CHECK(wifi_on_event(&wifi, &renewed, 0) == WIFI_ACT_NONE);
	CHECK(wifi.status.state == LINK_WIFI_UP);
	CHECK(wifi.status.rssi_dbm == -70 && memcmp(wifi.status.ip, renewed.ip, 4) == 0);
}

static void test_retry_waits_are_1_2_4_8_s_then_8_s_for_every_failure(void) {
	static const uint32_t WAITS_MS[] = {1000, 2000, 4000, 8000, 8000, 8000};
	for (size_t k = 0; k < JOIN_FAILURE_COUNT; k++) {
		wifi_t wifi = wifi_in(LINK_WIFI_CONNECTING);
		uint32_t now_ms = 500;
		for (size_t step = 0; step < sizeof WAITS_MS / sizeof WAITS_MS[0]; step++) {
			feed(&wifi, JOIN_FAILURES[k], now_ms);
			CHECK(retry_comes_after(&wifi, now_ms, WAITS_MS[step]));
			now_ms += WAITS_MS[step] + 300;
		}
	}
}

static void test_a_failure_state_stays_through_its_retries(void) {
	wifi_t wifi = wifi_in(LINK_WIFI_CONNECTING);
	feed(&wifi, WIFI_EVT_BAD_KEY, 0);
	CHECK(wifi_tick(&wifi, 1000) == WIFI_ACT_JOIN);
	CHECK(wifi.status.state == LINK_WIFI_BAD_KEY);
	feed(&wifi, WIFI_EVT_BAD_KEY, 1200);
	CHECK(wifi.status.state == LINK_WIFI_BAD_KEY);
}

static void test_a_lost_link_is_joined_again_after_the_first_wait(void) {
	wifi_t wifi = wifi_in(LINK_WIFI_UP);
	CHECK(wifi_tick(&wifi, 90000) == WIFI_ACT_NONE);
	feed(&wifi, WIFI_EVT_LOST, 90000);
	CHECK(retry_comes_after(&wifi, 90000, 1000));
}

static void test_up_starts_the_waits_again_at_1_s(void) {
	wifi_t wifi = wifi_in(LINK_WIFI_CONNECTING);
	feed(&wifi, WIFI_EVT_NO_AP, 0);
	CHECK(retry_comes_after(&wifi, 0, 1000));
	feed(&wifi, WIFI_EVT_NO_AP, 1000);
	CHECK(retry_comes_after(&wifi, 1000, 2000));
	feed(&wifi, WIFI_EVT_UP, 3500);
	feed(&wifi, WIFI_EVT_LOST, 9000);
	CHECK(retry_comes_after(&wifi, 9000, 1000));
}

static void test_up_during_a_wait_cancels_the_retry(void) {
	wifi_t wifi = wifi_in(LINK_WIFI_CONNECTING);
	feed(&wifi, WIFI_EVT_NO_AP, 0);
	feed(&wifi, WIFI_EVT_UP, 400);
	CHECK(wifi_tick(&wifi, 1000) == WIFI_ACT_NONE);
	CHECK(wifi_tick(&wifi, 60000) == WIFI_ACT_NONE);
	CHECK(wifi.status.state == LINK_WIFI_UP);
}

static void test_a_new_ssid_or_key_joins_at_once_and_starts_the_waits_again(void) {
	wifi_t wifi = wifi_in(LINK_WIFI_CONNECTING);
	feed(&wifi, WIFI_EVT_BAD_KEY, 0);
	CHECK(retry_comes_after(&wifi, 0, 1000));
	feed(&wifi, WIFI_EVT_BAD_KEY, 1000);
	CHECK(feed(&wifi, WIFI_EVT_SSID_SET, 1500) == WIFI_ACT_JOIN);
	CHECK(wifi_tick(&wifi, 3000) == WIFI_ACT_NONE);
	feed(&wifi, WIFI_EVT_BAD_KEY, 4000);
	CHECK(retry_comes_after(&wifi, 4000, 1000));
}

static void test_no_ssid_cancels_the_retry(void) {
	wifi_t wifi = wifi_in(LINK_WIFI_CONNECTING);
	feed(&wifi, WIFI_EVT_NO_AP, 0);
	CHECK(feed(&wifi, WIFI_EVT_NO_SSID, 400) == WIFI_ACT_LEAVE);
	CHECK(wifi_tick(&wifi, 1000) == WIFI_ACT_NONE);
	CHECK(wifi_tick(&wifi, 60000) == WIFI_ACT_NONE);
}

static void test_a_stale_failure_in_no_ssid_starts_no_retry(void) {
	for (size_t k = 0; k < JOIN_FAILURE_COUNT; k++) {
		wifi_t wifi = wifi_in(LINK_WIFI_NO_SSID);
		feed(&wifi, JOIN_FAILURES[k], 0);
		CHECK(wifi_tick(&wifi, 1000) == WIFI_ACT_NONE);
		CHECK(wifi_tick(&wifi, 60000) == WIFI_ACT_NONE);
	}
}

static void test_a_failure_during_a_wait_changes_the_state_only(void) {
	wifi_t wifi = wifi_in(LINK_WIFI_CONNECTING);
	feed(&wifi, WIFI_EVT_BAD_KEY, 0);
	feed(&wifi, WIFI_EVT_NO_AP, 600);
	CHECK(wifi.status.state == LINK_WIFI_NO_AP);
	CHECK(retry_comes_after(&wifi, 0, 1000));
	feed(&wifi, WIFI_EVT_NO_AP, 1000);
	CHECK(retry_comes_after(&wifi, 1000, 2000));
}

static void test_a_wait_ends_on_time_across_the_clock_wrap(void) {
	wifi_t wifi = wifi_in(LINK_WIFI_CONNECTING);
	uint32_t before_wrap_ms = UINT32_MAX - 499;
	feed(&wifi, WIFI_EVT_NO_AP, before_wrap_ms);
	CHECK(wifi_tick(&wifi, UINT32_MAX) == WIFI_ACT_NONE);
	CHECK(wifi_tick(&wifi, 0) == WIFI_ACT_NONE);
	CHECK(retry_comes_after(&wifi, before_wrap_ms, 1000));
}

static const struct {
	enum link_wifi_state state;
	const char *line;
} FAILURE_LINES[] = {
	{LINK_WIFI_NO_SSID, "Wi-Fi not set"},
	{LINK_WIFI_BAD_KEY, "Wrong Wi-Fi key"},
	{LINK_WIFI_NO_AP, "Wi-Fi not found"},
};
#define FAILURE_LINE_COUNT (sizeof FAILURE_LINES / sizeof FAILURE_LINES[0])

static bool same_text(const char *line, const char *text) {
	return line != NULL && strcmp(line, text) == 0;
}

static void test_each_failure_has_its_strip_line(void) {
	for (size_t i = 0; i < FAILURE_LINE_COUNT; i++) {
		CHECK(same_text(wifi_strip_line(FAILURE_LINES[i].state), FAILURE_LINES[i].line));
	}
}

static void test_connecting_and_up_have_no_failure_line(void) {
	CHECK(wifi_strip_line(LINK_WIFI_CONNECTING) == NULL);
	CHECK(wifi_strip_line(LINK_WIFI_UP) == NULL);
}

static bool is_a_failure_line(const char *line) {
	for (size_t i = 0; i < FAILURE_LINE_COUNT; i++) {
		if (same_text(line, FAILURE_LINES[i].line)) {
			return true;
		}
	}
	return false;
}

// R1: for every value a state byte can take, the line is absent or one of the three fixed texts,
// and wifi.h has no parameter that takes an SSID or a passphrase. So no line holds a secret, its
// length or a value derived from one.
static void test_no_strip_line_holds_a_secret(void) {
	for (int state = 0; state <= UINT8_MAX; state++) {
		const char *line = wifi_strip_line((enum link_wifi_state)state);
		CHECK(line == NULL || is_a_failure_line(line));
	}
}

static void test_every_strip_line_is_printable_ascii(void) {
	for (int state = 0; state < STATE_COUNT; state++) {
		const char *line = wifi_strip_line((enum link_wifi_state)state);
		for (size_t i = 0; line != NULL && line[i] != '\0'; i++) {
			CHECK(line[i] >= 0x20 && line[i] <= 0x7E);
		}
	}
}

int main(void) {
	test_boot_is_no_ssid_and_asks_for_nothing();
	test_the_feed_reaches_every_state();
	test_the_transition_table_names_every_state_and_event_once();
	test_every_event_in_every_state_gives_its_state_and_action();
	test_rssi_and_ip_are_zero_unless_up();
	test_up_again_takes_the_new_rssi_and_ip();
	test_retry_waits_are_1_2_4_8_s_then_8_s_for_every_failure();
	test_a_failure_state_stays_through_its_retries();
	test_a_lost_link_is_joined_again_after_the_first_wait();
	test_up_starts_the_waits_again_at_1_s();
	test_up_during_a_wait_cancels_the_retry();
	test_a_new_ssid_or_key_joins_at_once_and_starts_the_waits_again();
	test_no_ssid_cancels_the_retry();
	test_a_stale_failure_in_no_ssid_starts_no_retry();
	test_a_failure_during_a_wait_changes_the_state_only();
	test_a_wait_ends_on_time_across_the_clock_wrap();
	test_each_failure_has_its_strip_line();
	test_connecting_and_up_have_no_failure_line();
	test_no_strip_line_holds_a_secret();
	test_every_strip_line_is_printable_ascii();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	puts("wifi: all tests pass");
	return 0;
}
