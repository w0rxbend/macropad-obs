// SPDX-License-Identifier: MIT
#include "link.h"

#include <string.h>

void link_init(link_t *link) {
	memset(link, 0, sizeof(*link));
}

void link_session_reset(link_t *link) {
	link->len = 0;
	link->acked = false;
	link->host_seen = false;
	link->tx_len = 0;
}

uint16_t link_crc(const uint8_t *data, size_t len) {
	uint16_t crc = 0xFFFF;
	for (size_t i = 0; i < len; i++) {
		crc ^= data[i];
		for (int bit = 0; bit < 8; bit++) {
			if (crc & 1u) {
				crc = (uint16_t)((crc >> 1) ^ 0xA001u);
			} else {
				crc = (uint16_t)(crc >> 1);
			}
		}
	}
	return crc;
}

size_t link_encode(uint8_t type, const uint8_t *payload, uint16_t length, uint8_t *dst,
		   size_t cap) {
	if (length > LINK_MAX_PAYLOAD) {
		return 0;
	}
	size_t total = (size_t)5 + length + 2;
	if (cap < total) {
		return 0;
	}
	dst[0] = LINK_SOF;
	dst[1] = LINK_VERSION;
	dst[2] = type;
	dst[3] = (uint8_t)(length & 0xFFu);
	dst[4] = (uint8_t)((length >> 8) & 0xFFu);
	if (length > 0 && payload != NULL) {
		memcpy(dst + 5, payload, length);
	}
	uint16_t crc = link_crc(dst + 1, (size_t)4 + length);
	dst[5 + length] = (uint8_t)(crc & 0xFFu);
	dst[6 + length] = (uint8_t)((crc >> 8) & 0xFFu);
	return total;
}

static void drop_bytes(link_t *link, size_t n) {
	if (n >= link->len) {
		link->len = 0;
		return;
	}
	memmove(link->buf, link->buf + n, link->len - n);
	link->len -= n;
}

static bool host_type(uint8_t type) {
	return type >= LINK_HELLO_ACK && type <= LINK_NOTICE;
}

static bool known_type(uint8_t type) {
	return (type >= LINK_HELLO && type <= LINK_PAGE) || host_type(type);
}

int link_feed(link_t *link, const uint8_t *data, size_t n, link_frame_t *out, int cap) {
	int produced = 0;
	for (size_t i = 0; i < n; i++) {
		if (link->len >= sizeof link->buf) {
			drop_bytes(link, 1);
		}
		link->buf[link->len++] = data[i];
	}
	while (link->len > 0) {
		if (link->buf[0] != LINK_SOF) {
			drop_bytes(link, 1);
			continue;
		}
		if (link->len < 5) {
			break;
		}
		if (link->buf[1] != LINK_VERSION) {
			drop_bytes(link, 1);
			continue;
		}
		uint16_t length = (uint16_t)(link->buf[3] | ((uint16_t)link->buf[4] << 8));
		if (length > LINK_MAX_PAYLOAD) {
			drop_bytes(link, 1);
			continue;
		}
		size_t total = (size_t)5 + length + 2;
		if (link->len < total) {
			break;
		}
		uint16_t got = (uint16_t)(link->buf[total - 2] | ((uint16_t)link->buf[total - 1] << 8));
		uint16_t want = link_crc(link->buf + 1, (size_t)4 + length);
		if (got != want) {
			drop_bytes(link, 1);
			continue;
		}
		uint8_t type = link->buf[2];
		if (host_type(type) && !link->acked && type != LINK_HELLO_ACK) {
			link->rejected++;
			drop_bytes(link, total);
			continue;
		}
		if (!known_type(type)) {
			link->unknown++;
			drop_bytes(link, total);
			continue;
		}
		if (type == LINK_HELLO_ACK) {
			link->acked = true;
		}
		if (produced < cap && out != NULL) {
			out[produced].type = type;
			out[produced].length = length;
			if (length > 0) {
				memcpy(out[produced].payload, link->buf + 5, length);
			}
			produced++;
		}
		drop_bytes(link, total);
	}
	return produced;
}

void link_mark_host(link_t *link, uint32_t now_ms) {
	link->host_seen = true;
	link->last_host_ms = now_ms;
}

bool link_no_link(const link_t *link, uint32_t now_ms) {
	if (!link->acked || !link->host_seen) {
		return false;
	}
	return (uint32_t)(now_ms - link->last_host_ms) >= 3000u;
}

bool link_send(link_t *link, uint8_t type, const uint8_t *payload, uint16_t length) {
	uint8_t frame[5 + LINK_MAX_PAYLOAD + 2];
	size_t n = link_encode(type, payload, length, frame, sizeof frame);
	if (n == 0 || link->tx_len + n > sizeof link->tx) {
		return false;
	}
	memcpy(link->tx + link->tx_len, frame, n);
	link->tx_len += n;
	return true;
}

size_t link_next(link_t *link, uint8_t *dst, size_t cap) {
	size_t n = link->tx_len < cap ? link->tx_len : cap;
	if (n == 0) {
		return 0;
	}
	memcpy(dst, link->tx, n);
	memmove(link->tx, link->tx + n, link->tx_len - n);
	link->tx_len -= n;
	return n;
}

uint32_t link_unknown_count(const link_t *link) {
	return link->unknown;
}

uint32_t link_rejected_count(const link_t *link) {
	return link->rejected;
}

bool link_acked(const link_t *link) {
	return link->acked;
}
