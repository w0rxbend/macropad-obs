// SPDX-License-Identifier: MIT
// The CDC write loop (link_tx) against a fake port whose TX FIFO is smaller than one frame, so
// every frame meets back-pressure: a short queue, a drain, and the rest queued after it.
#include "link_tx.h"

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

#define FIFO_CAP 7
#define WIRE_CAP (4 * LINK_MAX_FRAME)
#define QUEUES_AFTER_GONE_MAX 1000

// The host side: a FIFO the queue call fills, a wire the drain empties it onto.
typedef struct {
	uint8_t fifo[FIFO_CAP];
	size_t fifo_len;
	uint8_t wire[WIRE_CAP];
	size_t wire_len;
	int drains;
	int queues_after_gone;
	int drains_before_gone; // the host goes away on this drain; -1: it stays
	bool gone;
} fake_host_t;

static size_t fake_queue(void *ctx, const uint8_t *bytes, size_t n) {
	fake_host_t *host = ctx;
	if (host->gone) {
		host->queues_after_gone++;
		// A loop that ignores a dead host spins here: fail it rather than hang the suite.
		if (host->queues_after_gone > QUEUES_AFTER_GONE_MAX) {
			fprintf(stderr, "%s: still queueing after the host went away\n", __FILE__);
			exit(1);
		}
	}
	size_t room = FIFO_CAP - host->fifo_len;
	size_t taken = n < room ? n : room;
	memcpy(host->fifo + host->fifo_len, bytes, taken);
	host->fifo_len += taken;
	return taken;
}

static bool fake_drain(void *ctx) {
	fake_host_t *host = ctx;
	if (host->drains == host->drains_before_gone) {
		host->gone = true;
	}
	host->drains++;
	if (host->gone) {
		return false;
	}
	memcpy(host->wire + host->wire_len, host->fifo, host->fifo_len);
	host->wire_len += host->fifo_len;
	host->fifo_len = 0;
	return true;
}

static fake_host_t host_that_stays(void) {
	fake_host_t host = {.drains_before_gone = -1};
	return host;
}

static link_tx_port_t port_of(fake_host_t *host) {
	link_tx_port_t port = {.queue = fake_queue, .drain = fake_drain, .ctx = host};
	return port;
}

static link_frame_t full_frame(void) {
	link_frame_t frame = {.type = LINK_CFG_DATA, .id = 9, .length = LINK_MAX_PAYLOAD};
	for (size_t i = 0; i < LINK_MAX_PAYLOAD; i++) {
		frame.payload[i] = (uint8_t)(i * 7 + 3);
	}
	return frame;
}

// A frame of LINK_MAX_FRAME bytes through a 7-byte FIFO arrives whole and in order.
static void test_full_frame_survives_back_pressure(void) {
	fake_host_t host = host_that_stays();
	link_tx_port_t port = port_of(&host);
	link_frame_t frame = full_frame();
	uint8_t expected[LINK_MAX_FRAME];
	size_t expected_len = link_encode(&frame, expected, sizeof expected);

	CHECK(expected_len == LINK_MAX_FRAME);
	CHECK(link_tx_send(&port, &frame));
	CHECK(host.wire_len == expected_len);
	CHECK(memcmp(host.wire, expected, expected_len) == 0);
	CHECK(host.fifo_len == 0);
	// One drain per full FIFO, then the closing drain that pushes the tail out.
	CHECK(host.drains == (int)((expected_len + FIFO_CAP - 1) / FIFO_CAP));
}

// Bytes that fit the FIFO still leave now: the write ends with a drain.
static void test_short_write_is_drained(void) {
	fake_host_t host = host_that_stays();
	link_tx_port_t port = port_of(&host);
	const uint8_t bytes[3] = {1, 2, 3};

	CHECK(link_tx_write(&port, bytes, sizeof bytes));
	CHECK(host.drains == 1);
	CHECK(host.wire_len == 3 && memcmp(host.wire, bytes, 3) == 0);
}

// Exactly one FIFO's worth: no drain inside the loop, one at the end.
static void test_write_of_exactly_the_fifo(void) {
	fake_host_t host = host_that_stays();
	link_tx_port_t port = port_of(&host);
	const uint8_t bytes[FIFO_CAP] = {9, 8, 7, 6, 5, 4, 3};

	CHECK(link_tx_write(&port, bytes, sizeof bytes));
	CHECK(host.drains == 1);
	CHECK(host.wire_len == FIFO_CAP && memcmp(host.wire, bytes, FIFO_CAP) == 0);
}

static void test_empty_write_queues_nothing(void) {
	fake_host_t host = host_that_stays();
	link_tx_port_t port = port_of(&host);

	CHECK(link_tx_write(&port, NULL, 0));
	CHECK(host.wire_len == 0 && host.fifo_len == 0);
}

// The host goes away mid-frame: the loop says so and stops queueing.
static void test_host_gone_mid_frame(void) {
	fake_host_t host = host_that_stays();
	host.drains_before_gone = 3;
	link_tx_port_t port = port_of(&host);
	link_frame_t frame = full_frame();

	CHECK(!link_tx_send(&port, &frame));
	CHECK(host.drains == 4);
	CHECK(host.queues_after_gone == 0);
	CHECK(host.wire_len == 3 * FIFO_CAP);
}

// The host is gone before the first byte: false, one drain, nothing on the wire.
static void test_host_gone_before_the_write(void) {
	fake_host_t host = host_that_stays();
	host.drains_before_gone = 0;
	link_tx_port_t port = port_of(&host);
	const uint8_t bytes[2] = {0xA5, 0x02};

	CHECK(!link_tx_write(&port, bytes, sizeof bytes));
	CHECK(host.drains == 1);
	CHECK(host.wire_len == 0);
}

// A frame the codec refuses never reaches the port.
static void test_unencodable_frame_is_refused(void) {
	fake_host_t host = host_that_stays();
	link_tx_port_t port = port_of(&host);
	link_frame_t frame = full_frame();
	frame.length = LINK_MAX_PAYLOAD + 1;

	CHECK(!link_tx_send(&port, &frame));
	CHECK(host.drains == 0 && host.fifo_len == 0 && host.wire_len == 0);
}

// Two frames back to back arrive as two frames, the second right after the first.
static void test_frames_do_not_interleave(void) {
	fake_host_t host = host_that_stays();
	link_tx_port_t port = port_of(&host);
	link_frame_t first = full_frame();
	link_frame_t second = {.type = LINK_CRED_STATUS, .id = 4, .length = 1, .payload = {0}};
	uint8_t a[LINK_MAX_FRAME];
	uint8_t b[LINK_MAX_FRAME];
	size_t a_len = link_encode(&first, a, sizeof a);
	size_t b_len = link_encode(&second, b, sizeof b);

	CHECK(link_tx_send(&port, &first));
	CHECK(link_tx_send(&port, &second));
	CHECK(host.wire_len == a_len + b_len);
	CHECK(memcmp(host.wire, a, a_len) == 0);
	CHECK(memcmp(host.wire + a_len, b, b_len) == 0);
}

int main(void) {
	test_full_frame_survives_back_pressure();
	test_short_write_is_drained();
	test_write_of_exactly_the_fifo();
	test_empty_write_queues_nothing();
	test_host_gone_mid_frame();
	test_host_gone_before_the_write();
	test_unencodable_frame_is_refused();
	test_frames_do_not_interleave();
	if (failures != 0) {
		fprintf(stderr, "test_link_tx: %d failures\n", failures);
		return 1;
	}
	printf("test_link_tx: ok\n");
	return 0;
}
