// SPDX-License-Identifier: MIT
#include "st7789.h"

#include "font8x16.h"

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

static void test_init_bytes(void) {
	st_op_t ops[16];
	size_t n = st_build_init(ops, 16);
	CHECK(n == 11);
	CHECK(ops[0].kind == ST_CMD && ops[0].value == ST_SWRESET);
	CHECK(ops[1].kind == ST_DELAY && ops[1].value == 120);
	CHECK(ops[2].kind == ST_CMD && ops[2].value == ST_SLPOUT);
	CHECK(ops[3].kind == ST_DELAY && ops[3].value == 120);
	CHECK(ops[4].kind == ST_CMD && ops[4].value == ST_COLMOD);
	CHECK(ops[5].kind == ST_DATA && ops[5].value == 0x55);
	CHECK(ops[6].kind == ST_CMD && ops[6].value == ST_MADCTL);
	CHECK(ops[7].kind == ST_DATA && ops[7].value == 0x00);
	CHECK(ops[8].kind == ST_CMD && ops[8].value == ST_NORON);
	CHECK(ops[9].kind == ST_CMD && ops[9].value == ST_DISPON);
	CHECK(ops[10].kind == ST_DELAY && ops[10].value == 20);
	CHECK(ST_DELAY_RESET_MS == 120 && ST_DELAY_SLEEP_MS == 120 && ST_DELAY_DISPON_MS == 20);
}

static void test_host_glyphs_and_reclive(void) {
	st_status_layout_t layout;
	st_status_layout("127.0.0.1:4455-and-then-some-more", &layout);
	CHECK(layout.host_glyphs == 21);
	CHECK(ST_HOST_GLYPHS == 21);
	CHECK(layout.live_x == layout.rec_x + 24);
	CHECK(layout.rec_x == 176);
	char fitted[22];
	CHECK(st_fit_host("abcdefghijklmnopqrstuvwxyz", fitted) == 21);
	CHECK(fitted[20] == '.');
	CHECK(strlen(fitted) == 21);
}

static void test_glyph_rgb565_high_byte_first(void) {
	st_op_t ops[600];
	size_t n = st_draw_glyph('A', 0xF800, ops, 600);
	CHECK(n > 12);
	int ram = -1;
	for (size_t i = 0; i < n; i++) {
		if (ops[i].kind == ST_CMD && ops[i].value == ST_RAMWR) {
			ram = (int)i;
			break;
		}
	}
	CHECK(ram > 0);
	int found = 0;
	for (size_t i = (size_t)ram + 1; i + 1 < n; i += 2) {
		CHECK(ops[i].kind == ST_DATA && ops[i + 1].kind == ST_DATA);
		if (ops[i].value == 0xF8 && ops[i + 1].value == 0x00) {
			found = 1;
			break;
		}
	}
	CHECK(found == 1);
	CHECK(FONT8X16_BYTES == 1520);
	int blank = 1;
	for (int row = 0; row < 16; row++) {
		if (font8x16[0][row] != 0) {
			blank = 0;
		}
	}
	CHECK(blank == 1);
}

static void test_skip_unchanged(void) {
	st_panel_t panel;
	st_op_t ops[8];
	st_panel_init(&panel);
	size_t first = st_draw_status(&panel, "127.0.0.1:4455", true, true, NULL, 0);
	CHECK(first > 0);
	size_t second = st_draw_status(&panel, "127.0.0.1:4455", true, true, ops, 8);
	CHECK(second == 0);
	size_t third = st_draw_status(&panel, "127.0.0.1:4455", true, false, NULL, 0);
	CHECK(third > 0);
}

static void test_cell_wraps_sixteen(void) {
	char a[11];
	char b[11];
	st_cell_lines("0123456789abcdef", a, b);
	CHECK(strcmp(a, "0123456789") == 0);
	CHECK(strcmp(b, "abcdef") == 0);
	st_cell_lines("0123456789abcdefX", a, b);
	CHECK(strcmp(a, "0123456789") == 0);
	CHECK(strcmp(b, "abcdef") == 0);
	CHECK(strchr(a, 'X') == NULL && strchr(b, 'X') == NULL);
}

static void test_notice_and_no_link(void) {
	st_panel_t panel;
	st_panel_init(&panel);
	CHECK(strcmp(st_status_label(&panel), "NO LINK") == 0);
	st_set_link(&panel, true);
	st_show_notice(&panel, "studio off", 50);
	CHECK(st_notice_active(&panel, 1049));
	CHECK(!st_notice_active(&panel, 1050));
}

int main(void) {
	test_init_bytes();
	test_host_glyphs_and_reclive();
	test_glyph_rgb565_high_byte_first();
	test_skip_unchanged();
	test_cell_wraps_sixteen();
	test_notice_and_no_link();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	puts("st7789: all tests pass");
	return 0;
}
