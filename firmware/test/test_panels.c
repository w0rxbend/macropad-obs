// SPDX-License-Identifier: MIT
// Vectors for the panel tables. Each one names where it was read: R06 is
// docs/research/06-big-display.md and R07 is docs/research/07-long-display.md.
#include "panels.h"

#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

// A vector row is: command, wait after it in ms, parameter count, parameters.

// R06 [C1], Sitronix ST7796U V1.0. Hardware reset leaves the chip asleep, display off, at
// 18 bit/pixel and MADCTL 0x00 (pages 165, 173, 196, 190).
static const uint8_t MAIN_INIT_VECTOR[] = {
	0x11, 120, 0, // SLPOUT, page 164. Page 165 asks for 5 ms; R06 [C3] waits 120 ms.
	0x36, 0, 1, 0x00, // MADCTL, page 188. The reset value: mirror and colour order are MEASURE.
	0x3A, 0, 1, 0x05, // COLMOD, page 195. Page 96: RGB565 on 4-line SPI is 3Ah = 05h.
	0x29, 0, 0, // DISPON, page 173.
};

// R07 [C4], Arduino_GFX `nv3007_279_init_operations`, in its order. R07 [C1], LVGL v9.4.0
// `lv_nv3007.c`, sends the same 114 register writes between the unlock and the lock. This is
// driver source: the NV3007 datasheet (R07 [B4]) was not read.
static const uint8_t STRIP_INIT_VECTOR[] = {
	0xFF, 0, 1, 0xA5, // unlock the vendor registers
	0x9A, 0, 1, 0x08,
	0x9B, 0, 1, 0x08,
	0x9C, 0, 1, 0xB0,
	0x9D, 0, 1, 0x16,
	0x9E, 0, 1, 0xC4,
	0x8F, 0, 2, 0x55, 0x04,
	0x84, 0, 1, 0x90,
	0x83, 0, 1, 0x7B,
	0x85, 0, 1, 0x33,
	0x60, 0, 1, 0x00,
	0x70, 0, 1, 0x00,
	0x61, 0, 1, 0x02,
	0x71, 0, 1, 0x02,
	0x62, 0, 1, 0x04,
	0x72, 0, 1, 0x04,
	0x6C, 0, 1, 0x29,
	0x7C, 0, 1, 0x29,
	0x6D, 0, 1, 0x31,
	0x7D, 0, 1, 0x31,
	0x6E, 0, 1, 0x0F,
	0x7E, 0, 1, 0x0F,
	0x66, 0, 1, 0x21,
	0x76, 0, 1, 0x21,
	0x68, 0, 1, 0x3A,
	0x78, 0, 1, 0x3A,
	0x63, 0, 1, 0x07,
	0x73, 0, 1, 0x07,
	0x64, 0, 1, 0x05,
	0x74, 0, 1, 0x05,
	0x65, 0, 1, 0x02,
	0x75, 0, 1, 0x02,
	0x67, 0, 1, 0x23,
	0x77, 0, 1, 0x23,
	0x69, 0, 1, 0x08,
	0x79, 0, 1, 0x08,
	0x6A, 0, 1, 0x13,
	0x7A, 0, 1, 0x13,
	0x6B, 0, 1, 0x13,
	0x7B, 0, 1, 0x13,
	0x6F, 0, 1, 0x00,
	0x7F, 0, 1, 0x00,
	0x50, 0, 1, 0x00,
	0x52, 0, 1, 0xD6,
	0x53, 0, 1, 0x08,
	0x54, 0, 1, 0x08,
	0x55, 0, 1, 0x1E,
	0x56, 0, 1, 0x1C,
	0xA0, 0, 3, 0x2B, 0x24, 0x00,
	0xA1, 0, 1, 0x87,
	0xA2, 0, 1, 0x86,
	0xA5, 0, 1, 0x00,
	0xA6, 0, 1, 0x00,
	0xA7, 0, 1, 0x00,
	0xA8, 0, 1, 0x36,
	0xA9, 0, 1, 0x7E,
	0xAA, 0, 1, 0x7E,
	0xB9, 0, 1, 0x85,
	0xBA, 0, 1, 0x84,
	0xBB, 0, 1, 0x83,
	0xBC, 0, 1, 0x82,
	0xBD, 0, 1, 0x81,
	0xBE, 0, 1, 0x80,
	0xBF, 0, 1, 0x01,
	0xC0, 0, 1, 0x02,
	0xC1, 0, 1, 0x00,
	0xC2, 0, 1, 0x00,
	0xC3, 0, 1, 0x00,
	0xC4, 0, 1, 0x33,
	0xC5, 0, 1, 0x7E,
	0xC6, 0, 1, 0x7E,
	0xC8, 0, 2, 0x33, 0x33,
	0xC9, 0, 1, 0x68,
	0xCA, 0, 1, 0x69,
	0xCB, 0, 1, 0x6A,
	0xCC, 0, 1, 0x6B,
	0xCD, 0, 2, 0x33, 0x33,
	0xCE, 0, 1, 0x6C,
	0xCF, 0, 1, 0x6D,
	0xD0, 0, 1, 0x6E,
	0xD1, 0, 1, 0x6F,
	0xAB, 0, 2, 0x03, 0x67,
	0xAC, 0, 2, 0x03, 0x6B,
	0xAD, 0, 2, 0x03, 0x68,
	0xAE, 0, 2, 0x03, 0x6C,
	0xB3, 0, 1, 0x00,
	0xB4, 0, 1, 0x00,
	0xB5, 0, 1, 0x00,
	0xB6, 0, 1, 0x32,
	0xB7, 0, 1, 0x7E,
	0xB8, 0, 1, 0x7E,
	0xE0, 0, 1, 0x00,
	0xE1, 0, 2, 0x03, 0x0F,
	0xE2, 0, 1, 0x04,
	0xE3, 0, 1, 0x01,
	0xE4, 0, 1, 0x0E,
	0xE5, 0, 1, 0x01,
	0xE6, 0, 1, 0x19,
	0xE7, 0, 1, 0x10,
	0xE8, 0, 1, 0x10,
	0xEA, 0, 1, 0x12,
	0xEB, 0, 1, 0xD0,
	0xEC, 0, 1, 0x04,
	0xED, 0, 1, 0x07,
	0xEE, 0, 1, 0x07,
	0xEF, 0, 1, 0x09,
	0xF0, 0, 1, 0xD0,
	0xF1, 0, 1, 0x0E,
	0xF9, 0, 1, 0x17,
	0xF2, 0, 4, 0x2C, 0x1B, 0x0B, 0x20,
	0xE9, 0, 1, 0x29,
	0xEC, 0, 1, 0x04,
	0x35, 0, 1, 0x00,
	0x44, 0, 2, 0x00, 0x10,
	0x46, 0, 1, 0x10,
	0xFF, 0, 1, 0x00, // lock
	// Not in the list: both drivers send MADCTL 0x00 for rotation 0 ([C4] `setRotation`, [C1]
	// generic init). Its place before COLMOD is this table's choice.
	0x36, 0, 1, 0x00,
	0x3A, 0, 1, 0x05, // 16 bit/pixel
	0x11, 120, 0, // SLPOUT, then `DELAY, 120`
	0x29, 0, 0, // DISPON
};

#define TRACE_CAP 1024

// The table in the vector row layout. Returns 0 when a step or the trace is too long.
static size_t init_trace(const panel_t *panel, uint8_t trace[TRACE_CAP]) {
	size_t n = 0;
	for (size_t i = 0; i < panel->init_len; i++) {
		const panel_init_step_t *step = &panel->init[i];
		bool step_too_long = step->param_len > PANEL_INIT_PARAMS_MAX;
		if (step_too_long || n + 3 + step->param_len > TRACE_CAP) {
			return 0;
		}
		trace[n++] = step->cmd;
		trace[n++] = step->wait_ms;
		trace[n++] = step->param_len;
		memcpy(&trace[n], step->params, step->param_len);
		n += step->param_len;
	}
	return n;
}

static void check_init_matches(const panel_t *panel, const uint8_t *vector, size_t vector_len) {
	uint8_t trace[TRACE_CAP];
	size_t trace_len = init_trace(panel, trace);
	CHECK(trace_len == vector_len);
	for (size_t i = 0; i < trace_len && i < vector_len; i++) {
		if (trace[i] != vector[i]) {
			fprintf(stderr, "init table leaves its vector at trace byte %zu\n", i);
			failures++;
			return;
		}
	}
}

static void test_main_init_matches_the_st7796u_vector(void) {
	check_init_matches(&panel_main, MAIN_INIT_VECTOR, sizeof MAIN_INIT_VECTOR);
}

static void test_strip_init_matches_the_nv3007_vector(void) {
	check_init_matches(&panel_strip, STRIP_INIT_VECTOR, sizeof STRIP_INIT_VECTOR);
}

// The strip table has no datasheet behind it. Task S.3 clears the mark when docs/spike.md
// records the panel ID read and a drawn frame. The big table is cited byte by byte above.
static void test_only_the_strip_init_is_marked_unverified(void) {
	CHECK(panel_strip.init_unverified);
	CHECK(!panel_main.init_unverified);
}

// R06 [D1]: 320 x 480. R07 [D1]: 142 x 428. R07 [C5] line 103: column offset 12 at rotation 0,
// a driver constant. The frame sizes are spec 13 criterion 4b.
static void test_sizes_and_column_offsets(void) {
	CHECK(panel_main.width == 320 && panel_main.height == 480);
	CHECK(panel_main.col_offset == 0);
	CHECK(panel_strip.width == 142 && panel_strip.height == 428);
	CHECK(panel_strip.col_offset == 12);
	CHECK(panel_main.width * panel_main.height * 2 == 307200);
	CHECK(panel_strip.width * panel_strip.height * 2 == 121552);
}

// R06 [C1] page 59: reset low 10 us or more, ready 120 ms after release at the latest.
// R07 [C4]: `NV3007_RST_DELAY` 120 for both. One line resets both panels.
static void test_reset_timing_covers_both_panels(void) {
	CHECK(PANEL_RESET_LOW_MS == 120);
	CHECK(PANEL_RESET_WAIT_MS == 120);
}

static bool window_is(const panel_t *panel, panel_rect_t rect, const uint8_t caset[4],
		      const uint8_t raset[4]) {
	panel_window_t window;
	return panel_window(panel, rect, &window) && memcmp(window.caset, caset, 4) == 0 &&
	       memcmp(window.raset, raset, 4) == 0;
}

// R06 [C1] pages 174, 176 and 177: CASET 2Ah and RASET 2Bh take start then end, high byte
// first, up to 013Fh and 01DFh. RAMWR 2Ch follows.
static void test_main_window_bytes(void) {
	CHECK(PANEL_CASET == 0x2A && PANEL_RASET == 0x2B && PANEL_RAMWR == 0x2C);
	CHECK(window_is(&panel_main, (panel_rect_t){0, 0, 320, 480},
			(uint8_t[]){0x00, 0x00, 0x01, 0x3F}, (uint8_t[]){0x00, 0x00, 0x01, 0xDF}));
	// The right key cell of board.toml [ui_mirror]: 96 px wide at x 224.
	CHECK(window_is(&panel_main, (panel_rect_t){224, 128, 96, 96},
			(uint8_t[]){0x00, 0xE0, 0x01, 0x3F}, (uint8_t[]){0x00, 0x80, 0x00, 0xDF}));
}

// R07 [C4] `.cpp` lines 25 to 34: the same three commands, with the column offset added.
// Visible columns 0 to 141 are RAM columns 12 to 153.
static void test_strip_window_adds_the_column_offset(void) {
	CHECK(window_is(&panel_strip, (panel_rect_t){0, 0, 142, 428},
			(uint8_t[]){0x00, 0x0C, 0x00, 0x99}, (uint8_t[]){0x00, 0x00, 0x01, 0xAB}));
	CHECK(window_is(&panel_strip, (panel_rect_t){141, 427, 1, 1},
			(uint8_t[]){0x00, 0x99, 0x00, 0x99}, (uint8_t[]){0x01, 0xAB, 0x01, 0xAB}));
}

static bool window_is_refused(const panel_t *panel, panel_rect_t rect) {
	panel_window_t window;
	memset(&window, 0xEE, sizeof window);
	panel_window_t untouched = window;
	return !panel_window(panel, rect, &window) &&
	       memcmp(&window, &untouched, sizeof window) == 0;
}

static void test_window_refuses_an_empty_or_outside_rect(void) {
	CHECK(window_is_refused(&panel_main, (panel_rect_t){0, 0, 0, 480}));
	CHECK(window_is_refused(&panel_main, (panel_rect_t){0, 0, 320, 0}));
	CHECK(window_is_refused(&panel_main, (panel_rect_t){1, 0, 320, 480}));
	CHECK(window_is_refused(&panel_main, (panel_rect_t){0, 1, 320, 480}));
	CHECK(window_is_refused(&panel_strip, (panel_rect_t){142, 0, 1, 1}));
	CHECK(window_is_refused(&panel_strip, (panel_rect_t){0, 428, 1, 1}));
	// 65535 + 2 wraps to 1 in 16 bits.
	CHECK(window_is_refused(&panel_main, (panel_rect_t){65535, 0, 2, 1}));
	CHECK(window_is_refused(&panel_main, (panel_rect_t){0, 65535, 1, 2}));
}

int main(void) {
	test_main_init_matches_the_st7796u_vector();
	test_strip_init_matches_the_nv3007_vector();
	test_only_the_strip_init_is_marked_unverified();
	test_sizes_and_column_offsets();
	test_reset_timing_covers_both_panels();
	test_main_window_bytes();
	test_strip_window_adds_the_column_offset();
	test_window_refuses_an_empty_or_outside_rect();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	puts("panels: all tests pass");
	return 0;
}
