// SPDX-License-Identifier: MIT
// 4 bpp alpha fonts for the fw-ui renderer (spec 9). tools/gen_font.py writes the font_noto*.c
// data files; their glyphs are SIL OFL 1.1 (font_OFL.txt).
#pragma once

#include <stdint.h>

typedef struct {
	uint16_t codepoint;
	uint8_t advance;       // pixels to the next pen position
	uint8_t width, height; // the alpha box; a row is (width + 1) / 2 bytes, high nibble first
	int8_t x, y;           // the box's top left from the pen at the top of the line
	uint32_t offset;       // into the font's bitmap
} font_glyph_t;

typedef struct {
	uint8_t line_height;
	uint8_t ascent;
	uint16_t count;
	const font_glyph_t *glyphs; // ascending codepoint
	const uint8_t *bitmap;
} font_t;

extern const font_t FONT_NOTO14;
extern const font_t FONT_NOTO20;
extern const font_t FONT_NOTO28;
