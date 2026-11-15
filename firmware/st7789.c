// SPDX-License-Identifier: MIT
#include "st7789.h"

#include "font8x16.h"

#include <string.h>

static size_t push_op(st_op_t *out, size_t cap, size_t n, uint8_t kind, uint16_t value) {
	if (n < cap && out != NULL) {
		out[n].kind = kind;
		out[n].value = value;
	}
	return n + 1;
}

size_t st_build_init(st_op_t *out, size_t cap) {
	size_t n = 0;
	n = push_op(out, cap, n, ST_CMD, ST_SWRESET);
	n = push_op(out, cap, n, ST_DELAY, ST_DELAY_RESET_MS);
	n = push_op(out, cap, n, ST_CMD, ST_SLPOUT);
	n = push_op(out, cap, n, ST_DELAY, ST_DELAY_SLEEP_MS);
	n = push_op(out, cap, n, ST_CMD, ST_COLMOD);
	n = push_op(out, cap, n, ST_DATA, ST_COLMOD_16BIT);
	n = push_op(out, cap, n, ST_CMD, ST_MADCTL);
	n = push_op(out, cap, n, ST_DATA, ST_MADCTL_VALUE);
	n = push_op(out, cap, n, ST_CMD, ST_NORON);
	n = push_op(out, cap, n, ST_CMD, ST_DISPON);
	n = push_op(out, cap, n, ST_DELAY, ST_DELAY_DISPON_MS);
	return n;
}

static char ascii_or_q(unsigned char c) {
	if (c >= 0x20 && c <= 0x7E) {
		return (char)c;
	}
	return '?';
}

size_t st_fit_host(const char *host, char out[ST_HOST_GLYPHS + 1]) {
	size_t n = 0;
	if (host == NULL) {
		host = "";
	}
	for (size_t i = 0; host[i] != '\0' && n < 64; i++) {
		n++;
	}
	size_t keep = n;
	bool dotted = false;
	if (keep > ST_HOST_GLYPHS) {
		keep = ST_HOST_GLYPHS - 1;
		dotted = true;
	}
	for (size_t i = 0; i < keep; i++) {
		out[i] = ascii_or_q((unsigned char)host[i]);
	}
	if (dotted) {
		out[keep] = '.';
		keep++;
	}
	out[keep] = '\0';
	return keep;
}

static const uint8_t *glyph_rows(char ch) {
	unsigned char c = (unsigned char)ch;
	if (c < FONT8X16_FIRST || c > FONT8X16_LAST) {
		c = (unsigned char)'?';
	}
	return font8x16[c - FONT8X16_FIRST];
}

size_t st_draw_glyph(char ch, uint16_t color, st_op_t *out, size_t cap) {
	size_t n = 0;
	n = push_op(out, cap, n, ST_CMD, ST_CASET);
	n = push_op(out, cap, n, ST_DATA, 0);
	n = push_op(out, cap, n, ST_DATA, 0);
	n = push_op(out, cap, n, ST_DATA, 0);
	n = push_op(out, cap, n, ST_DATA, 7);
	n = push_op(out, cap, n, ST_CMD, ST_RASET);
	n = push_op(out, cap, n, ST_DATA, 0);
	n = push_op(out, cap, n, ST_DATA, 0);
	n = push_op(out, cap, n, ST_DATA, 0);
	n = push_op(out, cap, n, ST_DATA, 15);
	n = push_op(out, cap, n, ST_CMD, ST_RAMWR);
	const uint8_t *rows = glyph_rows(ch);
	for (int y = 0; y < FONT8X16_ROWS; y++) {
		for (int x = 0; x < 8; x++) {
			bool on = (rows[y] & (uint8_t)(0x80u >> x)) != 0;
			uint16_t px = on ? color : ST_COLOR_BG;
			n = push_op(out, cap, n, ST_DATA, (uint16_t)((px >> 8) & 0xFFu));
			n = push_op(out, cap, n, ST_DATA, (uint16_t)(px & 0xFFu));
		}
	}
	return n;
}

void st_status_layout(const char *host, st_status_layout_t *layout) {
	char fitted[ST_HOST_GLYPHS + 1];
	layout->host_glyphs = (uint16_t)st_fit_host(host, fitted);
	layout->rec_x = ST_REC_X;
	layout->live_x = ST_LIVE_X;
}

static size_t draw_at(st_op_t *out, size_t cap, size_t n, char ch, uint16_t color) {
	st_op_t *dst = NULL;
	size_t room = 0;
	if (out != NULL && n < cap) {
		dst = out + n;
		room = cap - n;
	}
	return n + st_draw_glyph(ch, color, dst, room);
}

size_t st_draw_status(st_panel_t *panel, const char *host, bool rec, bool live, st_op_t *out,
		      size_t cap) {
	char fitted[ST_HOST_GLYPHS + 1];
	st_fit_host(host, fitted);
	if (panel->valid && panel->rec == rec && panel->live == live &&
	    strcmp(panel->host, fitted) == 0) {
		return 0;
	}
	memcpy(panel->host, fitted, sizeof panel->host);
	panel->rec = rec;
	panel->live = live;
	panel->valid = true;
	size_t n = 0;
	for (size_t i = 0; fitted[i] != '\0'; i++) {
		n = draw_at(out, cap, n, fitted[i], ST_COLOR_TEXT);
	}
	if (rec) {
		const char *word = "REC";
		for (int i = 0; word[i] != '\0'; i++) {
			n = draw_at(out, cap, n, word[i], ST_COLOR_REC);
		}
	}
	if (live) {
		const char *word = "LIVE";
		for (int i = 0; word[i] != '\0'; i++) {
			n = draw_at(out, cap, n, word[i], ST_COLOR_LIVE);
		}
	}
	return n;
}

void st_cell_lines(const char *name, char line1[11], char line2[11]) {
	memset(line1, 0, 11);
	memset(line2, 0, 11);
	if (name == NULL) {
		return;
	}
	char raw[17];
	size_t n = 0;
	for (size_t i = 0; name[i] != '\0' && n < 16; i++) {
		raw[n++] = ascii_or_q((unsigned char)name[i]);
	}
	size_t first = n < 10 ? n : 10;
	memcpy(line1, raw, first);
	line1[first] = '\0';
	if (n > 10) {
		size_t second = n - 10;
		memcpy(line2, raw + 10, second);
		line2[second] = '\0';
	}
}

void st_panel_init(st_panel_t *panel) {
	memset(panel, 0, sizeof(*panel));
	panel->link_up = false;
}

void st_set_link(st_panel_t *panel, bool up) {
	panel->link_up = up;
}

void st_show_notice(st_panel_t *panel, const char *text, uint32_t now_ms) {
	size_t n = 0;
	if (text != NULL) {
		for (; text[n] != '\0' && n < 32; n++) {
			panel->notice[n] = ascii_or_q((unsigned char)text[n]);
		}
	}
	panel->notice[n] = '\0';
	panel->notice_on = true;
	panel->notice_until = now_ms + 1000u;
}

bool st_notice_active(const st_panel_t *panel, uint32_t now_ms) {
	return panel->notice_on && now_ms < panel->notice_until;
}

const char *st_status_label(const st_panel_t *panel) {
	if (!panel->link_up) {
		return "NO LINK";
	}
	return panel->host;
}
