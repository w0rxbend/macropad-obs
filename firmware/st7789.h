// SPDX-License-Identifier: MIT
// ST7789 command builder. Writes a byte trace. No panel and no SPI hardware.
// MADCTL 0x00 is MEASURE until a real panel says otherwise.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ST_SWRESET 0x01
#define ST_SLPOUT 0x11
#define ST_NORON 0x13
#define ST_DISPON 0x29
#define ST_CASET 0x2A
#define ST_RASET 0x2B
#define ST_RAMWR 0x2C
#define ST_MADCTL 0x36
#define ST_COLMOD 0x3A

#define ST_COLMOD_16BIT 0x55
#define ST_MADCTL_VALUE 0x00
#define ST_DELAY_RESET_MS 120
#define ST_DELAY_SLEEP_MS 120
#define ST_DELAY_DISPON_MS 20

#define ST_WIDTH 240
#define ST_HEIGHT 320
#define ST_HOST_GLYPHS 21
#define ST_HOST_PX (ST_HOST_GLYPHS * 8)
#define ST_STATUS_GAP_PX 8
#define ST_REC_X (ST_HOST_PX + ST_STATUS_GAP_PX)
#define ST_LIVE_X (ST_REC_X + 24)

#define ST_COLOR_BG 0x18E3
#define ST_COLOR_TEXT 0xF7BE
#define ST_COLOR_CELL 0x39C7
#define ST_COLOR_REC 0xF9C6
#define ST_COLOR_LIVE 0xFCE1
#define ST_COLOR_EMPTY 0x630C

enum st_kind {
	ST_CMD = 1,
	ST_DATA = 2,
	ST_DELAY = 3,
};

typedef struct {
	uint8_t kind;
	uint16_t value;
} st_op_t;

typedef struct {
	char host[ST_HOST_GLYPHS + 1];
	bool rec;
	bool live;
	bool valid;
	bool link_up;
	char notice[33];
	uint32_t notice_until;
	bool notice_on;
} st_panel_t;

size_t st_build_init(st_op_t *out, size_t cap);

// Fit host:port into the 21-glyph field. Longer text keeps 20 glyphs and a trailing '.'.
size_t st_fit_host(const char *host, char out[ST_HOST_GLYPHS + 1]);

// Draw the status row. Returns 0 when the text, colours, and flags did not change.
typedef struct {
	uint16_t host_glyphs;
	uint16_t rec_x;
	uint16_t live_x;
} st_status_layout_t;

void st_status_layout(const char *host, st_status_layout_t *layout);

size_t st_draw_status(st_panel_t *panel, const char *host, bool rec, bool live, st_op_t *out,
		      size_t cap);

// One glyph as CASET, RASET, RAMWR, then RGB565 pixels, high byte first.
size_t st_draw_glyph(char ch, uint16_t color, st_op_t *out, size_t cap);

// A cell name is at most 16 bytes, drawn as two lines of at most 10 glyphs.
void st_cell_lines(const char *name, char line1[11], char line2[11]);

void st_panel_init(st_panel_t *panel);
void st_set_link(st_panel_t *panel, bool up);
void st_show_notice(st_panel_t *panel, const char *text, uint32_t now_ms);
bool st_notice_active(const st_panel_t *panel, uint32_t now_ms);
const char *st_status_label(const st_panel_t *panel);
