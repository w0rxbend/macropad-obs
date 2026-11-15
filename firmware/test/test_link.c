// SPDX-License-Identifier: MIT
#define _GNU_SOURCE
#include "link.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

static void vector(const char *name, uint8_t *dst, size_t cap, size_t *out_len) {
	FILE *f = fopen(VECTORS, "r");
	char line[512];
	if (f == NULL) {
		fprintf(stderr, "cannot open %s\n", VECTORS);
		exit(2);
	}
	while (fgets(line, sizeof line, f)) {
		char *tok = strtok(line, " \t\n");
		if (tok == NULL || tok[0] == '#' || strcmp(tok, name) != 0) {
			continue;
		}
		size_t n = 0;
		while ((tok = strtok(NULL, " \t\n")) != NULL) {
			if (n >= cap) {
				fprintf(stderr, "vector %s too long\n", name);
				exit(2);
			}
			dst[n++] = (uint8_t)strtoul(tok, NULL, 16);
		}
		fclose(f);
		*out_len = n;
		return;
	}
	fprintf(stderr, "vector %s missing\n", name);
	exit(2);
}

static void test_crc_check_value(void) {
	const uint8_t text[] = "123456789";
	CHECK(link_crc(text, 9) == 0x4B37);
}

static void test_key_vector_roundtrip(void) {
	uint8_t raw[64];
	size_t n = 0;
	vector("key_3_down", raw, sizeof raw, &n);
	CHECK(n == 9);
	CHECK(raw[0] == 0xA5 && raw[1] == 0x01 && raw[2] == 0x02);
	CHECK(raw[5] == 0x03 && raw[6] == 0x01 && raw[7] == 0xB8 && raw[8] == 0x82);

	uint8_t encoded[16];
	uint8_t payload[2] = {0x03, 0x01};
	size_t en = link_encode(LINK_KEY, payload, 2, encoded, sizeof encoded);
	CHECK(en == n && memcmp(encoded, raw, n) == 0);

	link_t link;
	link_frame_t frame;
	link_init(&link);
	CHECK(link_feed(&link, raw, n, &frame, 1) == 1);
	CHECK(frame.type == LINK_KEY && frame.length == 2);
	CHECK(frame.payload[0] == 3 && frame.payload[1] == 1);
}

static void test_bind_has_no_secret(void) {
	const char *secret = "replace-me";
	uint8_t raw[64];
	size_t n = 0;
	vector("bind_loopback", raw, sizeof raw, &n);
	CHECK(n > 8);
	CHECK(memmem(raw, n, secret, strlen(secret)) == NULL);

	uint8_t payload[16];
	const char *host = "127.0.0.1";
	payload[0] = 3;
	payload[1] = 0x67;
	payload[2] = 0x11;
	payload[3] = (uint8_t)strlen(host);
	memcpy(payload + 4, host, strlen(host));
	uint8_t encoded[64];
	size_t en = link_encode(LINK_BIND, payload, (uint16_t)(4 + strlen(host)), encoded,
				sizeof encoded);
	CHECK(en == n && memcmp(encoded, raw, n) == 0);
	CHECK(memmem(encoded, en, secret, strlen(secret)) == NULL);
	CHECK(memmem(encoded, en, "password", 8) == NULL);
}

static void test_page_view_rejected_before_ack(void) {
	uint8_t page[64];
	uint8_t ack[16];
	size_t page_n = 0;
	size_t ack_n = 0;
	vector("page_view_empty", page, sizeof page, &page_n);
	vector("hello_ack", ack, sizeof ack, &ack_n);

	link_t link;
	link_frame_t frame;
	link_init(&link);
	link_session_reset(&link);
	CHECK(link_feed(&link, page, page_n, &frame, 1) == 0);
	CHECK(!link_acked(&link));
	CHECK(link_rejected_count(&link) == 1);

	CHECK(link_feed(&link, ack, ack_n, &frame, 1) == 1);
	CHECK(frame.type == LINK_HELLO_ACK && link_acked(&link));
	CHECK(link_feed(&link, page, page_n, &frame, 1) == 1);
	CHECK(frame.type == LINK_PAGE_VIEW);

	link_session_reset(&link);
	CHECK(!link_acked(&link));
	CHECK(link_feed(&link, page, page_n, &frame, 1) == 0);
}

static void test_bad_crc_resyncs(void) {
	uint8_t bad[16];
	uint8_t good[16];
	size_t bad_n = 0;
	size_t good_n = 0;
	vector("key_bad_crc", bad, sizeof bad, &bad_n);
	vector("key_3_down", good, sizeof good, &good_n);
	uint8_t buf[32];
	memcpy(buf, bad, bad_n);
	memcpy(buf + bad_n, good, good_n);

	link_t link;
	link_frame_t frame;
	link_init(&link);
	CHECK(link_feed(&link, buf, bad_n + good_n, &frame, 1) == 1);
	CHECK(frame.type == LINK_KEY && frame.payload[0] == 3);
}

static void test_byte_at_a_time_and_unknown(void) {
	uint8_t good[16];
	size_t n = 0;
	vector("key_3_down", good, sizeof good, &n);
	link_t link;
	link_frame_t frame;
	link_init(&link);
	int got = 0;
	for (size_t i = 0; i < n; i++) {
		got += link_feed(&link, &good[i], 1, &frame, 1);
	}
	CHECK(got == 1 && frame.type == LINK_KEY);

	uint8_t payload[1] = {0x00};
	uint8_t unknown[16];
	size_t un = link_encode(0x7F, payload, 1, unknown, sizeof unknown);
	CHECK(un > 0);
	link_session_reset(&link);
	uint8_t ack_pay[1] = {0x01};
	link_send(&link, LINK_HELLO_ACK, ack_pay, 1);
	uint8_t tx[32];
	size_t tn = link_next(&link, tx, sizeof tx);
	CHECK(link_feed(&link, tx, tn, &frame, 1) == 1);
	CHECK(link_acked(&link));
	CHECK(link_feed(&link, unknown, un, &frame, 1) == 0);
	CHECK(link_unknown_count(&link) == 1);
	CHECK(link_acked(&link));
}

static void test_three_missed_heartbeats(void) {
	uint8_t ack[16];
	size_t n = 0;
	vector("hello_ack", ack, sizeof ack, &n);
	link_t link;
	link_frame_t frame;
	link_init(&link);
	CHECK(link_feed(&link, ack, n, &frame, 1) == 1);
	link_mark_host(&link, 1000);
	CHECK(!link_no_link(&link, 3999));
	CHECK(link_no_link(&link, 4000));
}

int main(void) {
	test_crc_check_value();
	test_key_vector_roundtrip();
	test_bind_has_no_secret();
	test_page_view_rejected_before_ack();
	test_bad_crc_resyncs();
	test_byte_at_a_time_and_unknown();
	test_three_missed_heartbeats();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	puts("link: all tests pass");
	return 0;
}
