// SPDX-License-Identifier: MIT
#include "panels.h"

#define SLPOUT 0x11
#define DISPON 0x29
#define MADCTL 0x36
#define COLMOD 0x3A

// Both driver sources wait this long after SLPOUT (R06 [C3], R07 [C4]).
#define SLPOUT_WAIT_MS 120
// No mirror, no row/column swap, RGB order: the ST7796U reset value, and what both NV3007
// drivers send. Mirror and colour order are MEASURE until a panel draws a frame.
#define MADCTL_UNROTATED_RGB 0x00
#define COLMOD_RGB565 0x05

#define STEP_COUNT(table) (sizeof(table) / sizeof((table)[0]))

// R06 [C1]: SLPOUT page 164, MADCTL page 188, COLMOD pages 96 and 195, DISPON page 173.
// Power, VCOM and gamma keep their reset values: the panel datasheet (R06 [D1]) has no init list.
static const panel_init_step_t MAIN_INIT[] = {
	{SLPOUT, SLPOUT_WAIT_MS, 0, {0}},
	{MADCTL, 0, 1, {MADCTL_UNROTATED_RGB}},
	{COLMOD, 0, 1, {COLMOD_RGB565}},
	{DISPON, 0, 0, {0}},
};

// The 114 vendor register writes are read from LVGL v9.4.0 `lv_nv3007.c` (MIT, R07 [C1]),
// which took them from Arduino_GFX `nv3007_279_init_operations` (BSD, R07 [C4]).
static const panel_init_step_t STRIP_INIT[] = {
	{0xFF, 0, 1, {0xA5}}, // unlock the vendor registers
	{0x9A, 0, 1, {0x08}},
	{0x9B, 0, 1, {0x08}},
	{0x9C, 0, 1, {0xB0}},
	{0x9D, 0, 1, {0x16}},
	{0x9E, 0, 1, {0xC4}},
	{0x8F, 0, 2, {0x55, 0x04}},
	{0x84, 0, 1, {0x90}},
	{0x83, 0, 1, {0x7B}},
	{0x85, 0, 1, {0x33}},
	{0x60, 0, 1, {0x00}},
	{0x70, 0, 1, {0x00}},
	{0x61, 0, 1, {0x02}},
	{0x71, 0, 1, {0x02}},
	{0x62, 0, 1, {0x04}},
	{0x72, 0, 1, {0x04}},
	{0x6C, 0, 1, {0x29}},
	{0x7C, 0, 1, {0x29}},
	{0x6D, 0, 1, {0x31}},
	{0x7D, 0, 1, {0x31}},
	{0x6E, 0, 1, {0x0F}},
	{0x7E, 0, 1, {0x0F}},
	{0x66, 0, 1, {0x21}},
	{0x76, 0, 1, {0x21}},
	{0x68, 0, 1, {0x3A}},
	{0x78, 0, 1, {0x3A}},
	{0x63, 0, 1, {0x07}},
	{0x73, 0, 1, {0x07}},
	{0x64, 0, 1, {0x05}},
	{0x74, 0, 1, {0x05}},
	{0x65, 0, 1, {0x02}},
	{0x75, 0, 1, {0x02}},
	{0x67, 0, 1, {0x23}},
	{0x77, 0, 1, {0x23}},
	{0x69, 0, 1, {0x08}},
	{0x79, 0, 1, {0x08}},
	{0x6A, 0, 1, {0x13}},
	{0x7A, 0, 1, {0x13}},
	{0x6B, 0, 1, {0x13}},
	{0x7B, 0, 1, {0x13}},
	{0x6F, 0, 1, {0x00}},
	{0x7F, 0, 1, {0x00}},
	{0x50, 0, 1, {0x00}},
	{0x52, 0, 1, {0xD6}},
	{0x53, 0, 1, {0x08}},
	{0x54, 0, 1, {0x08}},
	{0x55, 0, 1, {0x1E}},
	{0x56, 0, 1, {0x1C}},
	{0xA0, 0, 3, {0x2B, 0x24, 0x00}},
	{0xA1, 0, 1, {0x87}},
	{0xA2, 0, 1, {0x86}},
	{0xA5, 0, 1, {0x00}},
	{0xA6, 0, 1, {0x00}},
	{0xA7, 0, 1, {0x00}},
	{0xA8, 0, 1, {0x36}},
	{0xA9, 0, 1, {0x7E}},
	{0xAA, 0, 1, {0x7E}},
	{0xB9, 0, 1, {0x85}},
	{0xBA, 0, 1, {0x84}},
	{0xBB, 0, 1, {0x83}},
	{0xBC, 0, 1, {0x82}},
	{0xBD, 0, 1, {0x81}},
	{0xBE, 0, 1, {0x80}},
	{0xBF, 0, 1, {0x01}},
	{0xC0, 0, 1, {0x02}},
	{0xC1, 0, 1, {0x00}},
	{0xC2, 0, 1, {0x00}},
	{0xC3, 0, 1, {0x00}},
	{0xC4, 0, 1, {0x33}},
	{0xC5, 0, 1, {0x7E}},
	{0xC6, 0, 1, {0x7E}},
	{0xC8, 0, 2, {0x33, 0x33}},
	{0xC9, 0, 1, {0x68}},
	{0xCA, 0, 1, {0x69}},
	{0xCB, 0, 1, {0x6A}},
	{0xCC, 0, 1, {0x6B}},
	{0xCD, 0, 2, {0x33, 0x33}},
	{0xCE, 0, 1, {0x6C}},
	{0xCF, 0, 1, {0x6D}},
	{0xD0, 0, 1, {0x6E}},
	{0xD1, 0, 1, {0x6F}},
	{0xAB, 0, 2, {0x03, 0x67}},
	{0xAC, 0, 2, {0x03, 0x6B}},
	{0xAD, 0, 2, {0x03, 0x68}},
	{0xAE, 0, 2, {0x03, 0x6C}},
	{0xB3, 0, 1, {0x00}},
	{0xB4, 0, 1, {0x00}},
	{0xB5, 0, 1, {0x00}},
	{0xB6, 0, 1, {0x32}},
	{0xB7, 0, 1, {0x7E}},
	{0xB8, 0, 1, {0x7E}},
	{0xE0, 0, 1, {0x00}},
	{0xE1, 0, 2, {0x03, 0x0F}},
	{0xE2, 0, 1, {0x04}},
	{0xE3, 0, 1, {0x01}},
	{0xE4, 0, 1, {0x0E}},
	{0xE5, 0, 1, {0x01}},
	{0xE6, 0, 1, {0x19}},
	{0xE7, 0, 1, {0x10}},
	{0xE8, 0, 1, {0x10}},
	{0xEA, 0, 1, {0x12}},
	{0xEB, 0, 1, {0xD0}},
	{0xEC, 0, 1, {0x04}},
	{0xED, 0, 1, {0x07}},
	{0xEE, 0, 1, {0x07}},
	{0xEF, 0, 1, {0x09}},
	{0xF0, 0, 1, {0xD0}},
	{0xF1, 0, 1, {0x0E}},
	{0xF9, 0, 1, {0x17}},
	{0xF2, 0, 4, {0x2C, 0x1B, 0x0B, 0x20}},
	{0xE9, 0, 1, {0x29}},
	{0xEC, 0, 1, {0x04}},
	{0x35, 0, 1, {0x00}},
	{0x44, 0, 2, {0x00, 0x10}},
	{0x46, 0, 1, {0x10}},
	{0xFF, 0, 1, {0x00}}, // lock
	{MADCTL, 0, 1, {MADCTL_UNROTATED_RGB}},
	{COLMOD, 0, 1, {COLMOD_RGB565}},
	{SLPOUT, SLPOUT_WAIT_MS, 0, {0}},
	{DISPON, 0, 0, {0}},
};

const panel_t panel_main = {
	.width = 320,
	.height = 480,
	.col_offset = 0,
	.init = MAIN_INIT,
	.init_len = STEP_COUNT(MAIN_INIT),
	.init_unverified = false,
};

const panel_t panel_strip = {
	.width = 142,
	.height = 428,
	// RAM is 168 columns: 12 + 142 + 14. A driver constant (R07 [C5]), not a datasheet value.
	.col_offset = 12,
	.init = STRIP_INIT,
	.init_len = STEP_COUNT(STRIP_INIT),
	.init_unverified = true,
};

static void put_span(uint8_t params[4], uint32_t first, uint32_t count) {
	uint32_t last = first + count - 1;
	params[0] = (uint8_t)(first >> 8);
	params[1] = (uint8_t)first;
	params[2] = (uint8_t)(last >> 8);
	params[3] = (uint8_t)last;
}

bool panel_window(const panel_t *panel, panel_rect_t rect, panel_window_t *out) {
	bool empty = rect.w == 0 || rect.h == 0;
	bool outside = (uint32_t)rect.x + rect.w > panel->width ||
		       (uint32_t)rect.y + rect.h > panel->height;
	if (empty || outside) {
		return false;
	}
	put_span(out->caset, (uint32_t)rect.x + panel->col_offset, rect.w);
	put_span(out->raset, rect.y, rect.h);
	return true;
}
