// SPDX-License-Identifier: MIT
// SPI player for the st7789 trace. Glyph CASET stays inside st7789.c.
#include "panel.h"

#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include "pins.h"
#include "st7789.h"

#include <stdio.h>
#include <string.h>

static st_panel_t panel;
static char host_port[56];
static bool rec_on;
static bool live_on;
static bool booted;

static void play(const st_op_t *ops, size_t n) {
	for (size_t i = 0; i < n; i++) {
		if (ops[i].kind == ST_DELAY) {
			sleep_ms(ops[i].value);
			continue;
		}
		gpio_put(PIN_DISP_DC, ops[i].kind == ST_DATA);
		gpio_put(PIN_DISP_CS, 0);
		uint8_t byte = (uint8_t)ops[i].value;
		spi_write_blocking(spi0, &byte, 1);
		gpio_put(PIN_DISP_CS, 1);
	}
}

void panel_init(void) {
	spi_init(spi0, 20 * 1000 * 1000);
	gpio_set_function(PIN_DISP_SCK, GPIO_FUNC_SPI);
	gpio_set_function(PIN_DISP_MOSI, GPIO_FUNC_SPI);
	gpio_init(PIN_DISP_CS);
	gpio_init(PIN_DISP_DC);
	gpio_init(PIN_DISP_RESET);
	gpio_init(PIN_DISP_BL);
	gpio_set_dir(PIN_DISP_CS, GPIO_OUT);
	gpio_set_dir(PIN_DISP_DC, GPIO_OUT);
	gpio_set_dir(PIN_DISP_RESET, GPIO_OUT);
	gpio_set_dir(PIN_DISP_BL, GPIO_OUT);
	gpio_put(PIN_DISP_CS, 1);
	gpio_put(PIN_DISP_BL, 0);
	gpio_put(PIN_DISP_RESET, 0);
	sleep_ms(10);
	gpio_put(PIN_DISP_RESET, 1);
	st_panel_init(&panel);
	host_port[0] = '\0';
	static st_op_t init_ops[32];
	size_t n = st_build_init(init_ops, 32);
	play(init_ops, n);
	booted = true;
}

void panel_backlight(bool on) {
	gpio_put(PIN_DISP_BL, on);
}

static void take_text(const uint8_t *payload, uint16_t length, uint16_t at, char *dst, size_t cap) {
	if (at >= length || cap == 0) {
		return;
	}
	uint8_t n = payload[at];
	size_t copy = n;
	if (at + 1u + copy > length) {
		copy = length - at - 1u;
	}
	if (copy >= cap) {
		copy = cap - 1u;
	}
	for (size_t i = 0; i < copy; i++) {
		uint8_t ch = payload[at + 1u + i];
		dst[i] = (ch >= 0x20 && ch <= 0x7E) ? (char)ch : '?';
	}
	dst[copy] = '\0';
}

void panel_on_frame(const link_frame_t *frame, uint32_t now_ms) {
	if (frame->type == LINK_BIND && frame->length >= 4) {
		uint16_t port = (uint16_t)frame->payload[1] | ((uint16_t)frame->payload[2] << 8);
		char host[49];
		take_text(frame->payload, frame->length, 3, host, sizeof host);
		snprintf(host_port, sizeof host_port, "%s:%u", host, port);
	} else if (frame->type == LINK_PAGE_VIEW && frame->length >= 3) {
		live_on = (frame->payload[2] & 0x02u) != 0;
		rec_on = (frame->payload[2] & 0x04u) != 0;
	} else if (frame->type == LINK_NOTICE && frame->length >= 1) {
		char text[33];
		take_text(frame->payload, frame->length, 0, text, sizeof text);
		st_show_notice(&panel, text, now_ms);
	}
}

void panel_poll(uint32_t now_ms, bool link_up) {
	if (!booted) {
		return;
	}
	st_set_link(&panel, link_up);
	const char *label = st_notice_active(&panel, now_ms) ? panel.notice : st_status_label(&panel);
	if (!link_up && !st_notice_active(&panel, now_ms)) {
		label = st_status_label(&panel);
	}
	if (label[0] == '\0') {
		label = host_port;
	}
	static st_op_t ops[8192];
	size_t n = st_draw_status(&panel, label, rec_on, live_on, ops, 8192);
	play(ops, n);
}
