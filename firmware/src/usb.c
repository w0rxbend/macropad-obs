// SPDX-License-Identifier: MIT
#include "usb.h"

#include "tusb.h"

static link_t *bound;
static bool prev_dtr;
static volatile bool hello_due;

void usb_init(void) {
	tusb_init();
	bound = 0;
	prev_dtr = false;
	hello_due = true;
}

bool usb_hello_due(void) {
	return hello_due;
}

void usb_hello_sent(void) {
	hello_due = false;
}

void tud_cdc_line_state_cb(uint8_t itf, bool dtr, bool rts) {
	(void)itf;
	(void)rts;
	if (dtr && !prev_dtr && bound != 0) {
		link_session_reset(bound);
		hello_due = true;
	}
	prev_dtr = dtr;
}

int usb_poll(link_t *link, link_frame_t *out, int cap) {
	bound = link;
	tud_task();
	int total = 0;
	uint8_t buf[64];
	while (tud_cdc_available() && total < cap) {
		uint32_t n = tud_cdc_read(buf, sizeof buf);
		if (n == 0) {
			break;
		}
		int got = link_feed(link, buf, n, out + total, cap - total);
		if (got > 0) {
			total += got;
		}
	}
	uint8_t tx[64];
	for (;;) {
		size_t n = link_next(link, tx, sizeof tx);
		if (n == 0) {
			break;
		}
		tud_cdc_write(tx, (uint32_t)n);
	}
	tud_cdc_write_flush();
	return total;
}
