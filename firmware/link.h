// SPDX-License-Identifier: MIT
// CDC frame parser. Pure C, no SDK headers, so firmware/test runs it under ASan.
// Wire format: docs/protocol.md. There is no password argument on purpose.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define LINK_SOF 0xA5
#define LINK_VERSION 0x01
#define LINK_MAX_PAYLOAD 240
#define LINK_KEYS 9
#define LINK_PROTO 1

enum link_type {
	LINK_HELLO = 0x01,
	LINK_KEY = 0x02,
	LINK_KNOB = 0x03,
	LINK_PAGE = 0x04,
	LINK_HELLO_ACK = 0x10,
	LINK_HEARTBEAT = 0x11,
	LINK_BIND = 0x12,
	LINK_PROFILE = 0x13,
	LINK_PAGE_VIEW = 0x14,
	LINK_INPUT = 0x15,
	LINK_NOTICE = 0x16,
};

typedef struct {
	uint8_t type;
	uint16_t length;
	uint8_t payload[LINK_MAX_PAYLOAD];
} link_frame_t;

typedef struct {
	uint8_t buf[256];
	size_t len;
	bool acked;
	uint32_t unknown;
	uint32_t rejected;
	bool host_seen;
	uint32_t last_host_ms;
	uint8_t tx[1024];
	size_t tx_len;
} link_t;

void link_init(link_t *link);
void link_session_reset(link_t *link);

// CRC-16/MODBUS over `data`. Check value: ASCII "123456789" -> 0x4B37.
uint16_t link_crc(const uint8_t *data, size_t len);

// Encode one frame. Returns the byte count, or 0 if it does not fit.
size_t link_encode(uint8_t type, const uint8_t *payload, uint16_t length, uint8_t *dst,
		   size_t cap);

// Append bytes. Accepted frames are written to `out`. Returns how many were written.
// Host frames other than HELLO_ACK are rejected until HELLO_ACK. A bad CRC, a bad
// version, or a length above 240 drops one byte and scans for SOF again.
int link_feed(link_t *link, const uint8_t *data, size_t n, link_frame_t *out, int cap);

// Call with the clock when `link_feed` delivered a host frame. Three seconds of
// silence after that sets the link dead. The pad keeps the last page text.
void link_mark_host(link_t *link, uint32_t now_ms);
bool link_no_link(const link_t *link, uint32_t now_ms);

// Transmit queue. usb.c drains it with link_next.
bool link_send(link_t *link, uint8_t type, const uint8_t *payload, uint16_t length);
size_t link_next(link_t *link, uint8_t *dst, size_t cap);

uint32_t link_unknown_count(const link_t *link);
uint32_t link_rejected_count(const link_t *link);
bool link_acked(const link_t *link);
