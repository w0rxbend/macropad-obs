// SPDX-License-Identifier: MIT
// Three layers. A canvas is one band span: primitives and glyphs clip to it, and text blends over
// the pixels already in it, so no widget needs to know its background. Widgets draw themselves
// whole into whatever span they cross. The frame loop finds the dirty runs and pushes them.
#include "render.h"

#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "font.h"

#define RGB565(r, g, b) ((uint16_t)(((r) >> 3) << 11 | ((g) >> 2) << 5 | (b) >> 3))

#define BLACK RGB565(0, 0, 0)
#define WHITE RGB565(255, 255, 255)
#define GREY RGB565(128, 128, 128)
#define DIM RGB565(64, 64, 64)
#define CELL RGB565(36, 36, 36)
#define BAR RGB565(24, 24, 28)
#define RED RGB565(200, 0, 0)
#define DEEP_RED RGB565(110, 0, 0)
#define GREEN RGB565(0, 200, 80)
#define YELLOW RGB565(230, 200, 0)
#define AMBER RGB565(240, 160, 0)

#define INSET 8
#define PREVIEW_BORDER 4
#define CODEPOINT_ELLIPSIS 0x2026
#define CODEPOINT_INVALID 0xFFFD
// Report 14: the fader bar runs -60 to 0 dB, linear in dB. The meter turns yellow at -20 dB and
// red at -9 dB.
#define FADER_FLOOR_TENTHS (-600)
#define METER_YELLOW_TENTHS (-200)
#define METER_RED_TENTHS (-90)

typedef struct {
	uint16_t *pixels; // area.w to a row
	ui_rect_t area;   // the band span, panel coordinates
	ui_rect_t clip;   // inside `area`: the widget being drawn writes nothing outside it
} canvas_t;

typedef struct {
	const font_t *font;
	uint16_t color;
} text_style_t;

typedef struct {
	const char *bytes; // UTF-8
	size_t len;
} text_t;

typedef struct {
	int x, y; // the pen: left edge, top of the line
} pen_t;

// ---- Canvas primitives ----

static int min_int(int a, int b) {
	return a < b ? a : b;
}

static int max_int(int a, int b) {
	return a > b ? a : b;
}

static ui_rect_t inset(ui_rect_t rect, int by) {
	int w = max_int(0, rect.w - 2 * by), h = max_int(0, rect.h - 2 * by);
	return (ui_rect_t){(uint16_t)(rect.x + by), (uint16_t)(rect.y + by), (uint16_t)w, (uint16_t)h};
}

static uint16_t *canvas_row(const canvas_t *canvas, int y) {
	return canvas->pixels + (size_t)(y - canvas->area.y) * canvas->area.w;
}

// Writes `color` over the part of the box inside the clip.
static void fill_box(canvas_t *canvas, int x, int y, int w, int h, uint16_t color) {
	ui_rect_t clip = canvas->clip;
	int x0 = max_int(x, clip.x), x1 = min_int(x + w, clip.x + clip.w);
	int y0 = max_int(y, clip.y), y1 = min_int(y + h, clip.y + clip.h);
	for (int row = y0; row < y1; row++) {
		uint16_t *line = canvas_row(canvas, row);
		for (int col = x0; col < x1; col++) {
			line[col - canvas->area.x] = color;
		}
	}
}

static void fill_rect(canvas_t *canvas, ui_rect_t rect, uint16_t color) {
	fill_box(canvas, rect.x, rect.y, rect.w, rect.h, color);
}

static void outline(canvas_t *canvas, ui_rect_t rect, int thickness, uint16_t color) {
	fill_box(canvas, rect.x, rect.y, rect.w, thickness, color);
	fill_box(canvas, rect.x, rect.y + rect.h - thickness, rect.w, thickness, color);
	fill_box(canvas, rect.x, rect.y, thickness, rect.h, color);
	fill_box(canvas, rect.x + rect.w - thickness, rect.y, thickness, rect.h, color);
}

// A 1 px outline of 4 px dashes and 4 px gaps, each side counted from its own start.
static void dashed_outline(canvas_t *canvas, ui_rect_t rect, uint16_t color) {
	for (int along = 0; along < rect.w; along += 8) {
		int dash = min_int(4, rect.w - along);
		fill_box(canvas, rect.x + along, rect.y, dash, 1, color);
		fill_box(canvas, rect.x + along, rect.y + rect.h - 1, dash, 1, color);
	}
	for (int along = 0; along < rect.h; along += 8) {
		int dash = min_int(4, rect.h - along);
		fill_box(canvas, rect.x, rect.y + along, 1, dash, color);
		fill_box(canvas, rect.x + rect.w - 1, rect.y + along, 1, dash, color);
	}
}

static unsigned blend_channel(unsigned under, unsigned over, unsigned alpha) {
	return (under * (15u - alpha) + over * alpha + 7u) / 15u;
}

// `alpha` 0..15 of `color` over the pixel, channel by channel.
static uint16_t blend(uint16_t under, uint16_t color, unsigned alpha) {
	unsigned r = blend_channel(under >> 11, color >> 11, alpha);
	unsigned g = blend_channel(under >> 5 & 0x3Fu, color >> 5 & 0x3Fu, alpha);
	unsigned b = blend_channel(under & 0x1Fu, color & 0x1Fu, alpha);
	return (uint16_t)(r << 11 | g << 5 | b);
}

// ---- Glyphs and text ----

static size_t utf8_extra_bytes(uint8_t lead) {
	if (lead >= 0xC2 && lead < 0xE0) {
		return 1;
	}
	if (lead >= 0xE0 && lead < 0xF0) {
		return 2;
	}
	return lead >= 0xF0 && lead < 0xF5 ? 3 : 0;
}

// Takes one codepoint off the front of the run. A byte that starts no complete sequence reads as
// one U+FFFD, so a cut or bad name still draws and nothing reads past `len`.
static uint32_t next_codepoint(text_t *text) {
	const uint8_t *s = (const uint8_t *)text->bytes;
	size_t extra = utf8_extra_bytes(s[0]);
	uint32_t codepoint = s[0] & (0x3Fu >> extra);
	bool whole = extra > 0 && extra < text->len;
	for (size_t i = 1; whole && i <= extra; i++) {
		whole = (s[i] & 0xC0) == 0x80;
		codepoint = codepoint << 6 | (s[i] & 0x3Fu);
	}
	size_t used = whole ? extra + 1 : 1;
	text->bytes += used;
	text->len -= used;
	if (s[0] < 0x80) {
		return s[0];
	}
	return whole ? codepoint : CODEPOINT_INVALID;
}

static const font_glyph_t *find_glyph(const font_t *font, uint32_t codepoint) {
	size_t low = 0, high = font->count;
	while (low < high) {
		size_t mid = (low + high) / 2;
		if (font->glyphs[mid].codepoint == codepoint) {
			return &font->glyphs[mid];
		}
		if (font->glyphs[mid].codepoint < codepoint) {
			low = mid + 1;
		} else {
			high = mid;
		}
	}
	return NULL;
}

// A codepoint the font lacks draws as an outlined box this wide (report 14).
static int missing_advance(const font_t *font) {
	return font->line_height / 2;
}

static int advance_of(const font_t *font, uint32_t codepoint) {
	const font_glyph_t *glyph = find_glyph(font, codepoint);
	return glyph != NULL ? glyph->advance : missing_advance(font);
}

static int text_width(const font_t *font, text_t text) {
	int width = 0;
	while (text.len > 0) {
		width += advance_of(font, next_codepoint(&text));
	}
	return width;
}

static void draw_glyph(canvas_t *canvas, text_style_t style, const font_glyph_t *glyph, pen_t pen) {
	ui_rect_t clip = canvas->clip;
	int x0 = pen.x + glyph->x, y0 = pen.y + glyph->y;
	int stride = (glyph->width + 1) / 2;
	int row_end = min_int(glyph->height, clip.y + clip.h - y0);
	int col_begin = max_int(0, clip.x - x0), col_end = min_int(glyph->width, clip.x + clip.w - x0);
	for (int row = max_int(0, clip.y - y0); row < row_end; row++) {
		const uint8_t *bits = style.font->bitmap + glyph->offset + (size_t)row * stride;
		uint16_t *line = canvas_row(canvas, y0 + row);
		for (int col = col_begin; col < col_end; col++) {
			unsigned alpha = col % 2 == 0 ? bits[col / 2] >> 4 : bits[col / 2] & 0x0Fu;
			uint16_t *out = &line[x0 + col - canvas->area.x];
			if (alpha != 0) {
				*out = blend(*out, style.color, alpha);
			}
		}
	}
}

// Draws one codepoint and returns its advance.
static int draw_codepoint(canvas_t *canvas, text_style_t style, uint32_t codepoint, pen_t pen) {
	const font_glyph_t *glyph = find_glyph(style.font, codepoint);
	if (glyph != NULL) {
		draw_glyph(canvas, style, glyph, pen);
		return glyph->advance;
	}
	int width = missing_advance(style.font);
	int top = style.font->line_height / 6;
	ui_rect_t box = {(uint16_t)(pen.x + 1), (uint16_t)(pen.y + top), (uint16_t)(width - 2),
	                 (uint16_t)(style.font->ascent - top)};
	outline(canvas, box, 1, style.color);
	return width;
}

// One line at the pen, no wider than `max_width`. A text that does not fit ends with an ellipsis
// at the last glyph that leaves room for it (report 14).
static void draw_text_line(canvas_t *canvas, text_style_t style, pen_t pen, int max_width, text_t text) {
	bool fits = text_width(style.font, text) <= max_width;
	int limit = fits ? max_width : max_width - advance_of(style.font, CODEPOINT_ELLIPSIS);
	int x = pen.x;
	while (text.len > 0) {
		text_t rest = text;
		uint32_t codepoint = next_codepoint(&rest);
		if (x + advance_of(style.font, codepoint) - pen.x > limit) {
			break;
		}
		x += draw_codepoint(canvas, style, codepoint, (pen_t){x, pen.y});
		text = rest;
	}
	if (!fits) {
		draw_codepoint(canvas, style, CODEPOINT_ELLIPSIS, (pen_t){x, pen.y});
	}
}

static text_t text_of(const char *string) {
	return (text_t){string, strlen(string)};
}

// The bytes of `text` that fit one line of `max_width`: whole words while they fit, else as many
// codepoints of the first word as fit, at least one. The next line starts after the spaces.
static text_t take_line(const font_t *font, text_t *text, int max_width) {
	text_t line = {text->bytes, 0}, cursor = *text;
	int width = 0;
	size_t word_end = 0;
	bool overflowed = false;
	while (cursor.len > 0 && !overflowed) {
		const char *at = cursor.bytes;
		uint32_t codepoint = next_codepoint(&cursor);
		width += advance_of(font, codepoint);
		if (codepoint == ' ') {
			word_end = (size_t)(at - text->bytes);
		}
		overflowed = codepoint != ' ' && width > max_width && line.len > 0;
		if (!overflowed) {
			line.len = (size_t)(cursor.bytes - text->bytes);
		}
	}
	if (overflowed && word_end > 0) {
		line.len = word_end;
	}
	text->bytes += line.len;
	text->len -= line.len;
	while (text->len > 0 && text->bytes[0] == ' ') {
		text->bytes++;
		text->len--;
	}
	return line;
}

// Word-wrapped lines of `font` from the top of `box`, as many as fit whole. The last one takes the
// rest of the text, cut with an ellipsis. `centered` centres each line in the box.
typedef struct {
	text_style_t style;
	bool centered;
} wrap_t;

static int wrapped_lines(const font_t *font, ui_rect_t box, text_t text) {
	int lines = 0;
	for (int room = box.h / font->line_height; text.len > 0 && lines < room; lines++) {
		take_line(font, &text, box.w);
	}
	return lines;
}

static void draw_wrapped(canvas_t *canvas, wrap_t wrap, ui_rect_t box, text_t text) {
	const font_t *font = wrap.style.font;
	int room = box.h / font->line_height;
	for (int line_index = 0; text.len > 0 && line_index < room; line_index++) {
		text_t line = line_index + 1 < room ? take_line(font, &text, box.w) : text;
		int width = min_int(text_width(font, line), box.w);
		int x = wrap.centered ? box.x + (box.w - width) / 2 : box.x;
		draw_text_line(canvas, wrap.style, (pen_t){x, box.y + line_index * font->line_height}, box.w, line);
		if (line.bytes == text.bytes) { // the last line took the rest
			break;
		}
	}
}

// The line's top so that one line of `font` sits in the middle of `rect`.
static int centred_top(const font_t *font, ui_rect_t rect) {
	return rect.y + (rect.h - font->line_height) / 2;
}

// ---- Widgets ----

static const char *const KEY_TAGS[] = {
	[RENDER_KEY_PROGRAM] = "PGM", [RENDER_KEY_PREVIEW] = "PVW", [RENDER_KEY_ON] = "ON"};

typedef struct {
	uint16_t fill;
	uint16_t text;
	uint16_t word;
} key_colors_t;

static key_colors_t key_colors(uint8_t state) {
	switch (state) {
	case RENDER_KEY_PROGRAM: return (key_colors_t){RED, WHITE, WHITE};
	case RENDER_KEY_ON: return (key_colors_t){AMBER, BLACK, BLACK};
	case RENDER_KEY_IDLE:
	case RENDER_KEY_PREVIEW: return (key_colors_t){CELL, WHITE, GREY};
	default: return (key_colors_t){BLACK, GREY, GREY};
	}
}

static void draw_key_frame(canvas_t *canvas, ui_rect_t rect, uint8_t state) {
	if (state == RENDER_KEY_PREVIEW) {
		outline(canvas, rect, PREVIEW_BORDER, GREEN);
	} else if (state == RENDER_KEY_MISSING) {
		dashed_outline(canvas, rect, GREY);
	} else if (state == RENDER_KEY_UNBOUND) {
		outline(canvas, rect, 1, DIM);
	}
}

// Action word at 14 px, label at 20 px on the lines that fit, tag at 14 px bottom right.
static void draw_key(canvas_t *canvas, ui_rect_t rect, const render_key_t *key) {
	key_colors_t colors = key_colors(key->state);
	fill_rect(canvas, rect, colors.fill);
	draw_key_frame(canvas, rect, key->state);
	if (key->state == RENDER_KEY_UNBOUND) {
		return;
	}
	ui_rect_t body = inset(rect, INSET);
	if (key->word[0] != '\0') {
		draw_text_line(canvas, (text_style_t){&FONT_NOTO14, colors.word}, (pen_t){body.x, body.y}, body.w,
		               text_of(key->word));
		body.y = (uint16_t)(body.y + FONT_NOTO14.line_height);
		body.h = (uint16_t)max_int(0, body.h - FONT_NOTO14.line_height);
	}
	draw_wrapped(canvas, (wrap_t){{&FONT_NOTO20, colors.text}, false}, body, text_of(key->label));
	const char *tag = key->state < sizeof KEY_TAGS / sizeof KEY_TAGS[0] ? KEY_TAGS[key->state] : NULL;
	if (tag != NULL) {
		text_t text = text_of(tag);
		int width = text_width(&FONT_NOTO14, text);
		pen_t pen = {rect.x + rect.w - INSET - width, rect.y + rect.h - INSET - FONT_NOTO14.line_height};
		draw_text_line(canvas, (text_style_t){&FONT_NOTO14, colors.text}, pen, width, text);
	}
}

static void draw_legend(canvas_t *canvas, ui_rect_t rect, const char *label) {
	fill_rect(canvas, rect, CELL);
	outline(canvas, rect, 1, DIM);
	ui_rect_t body = inset(rect, INSET / 2);
	text_t text = text_of(label);
	int lines = wrapped_lines(&FONT_NOTO20, body, text);
	body.y = (uint16_t)(body.y + (body.h - lines * FONT_NOTO20.line_height) / 2);
	draw_wrapped(canvas, (wrap_t){{&FONT_NOTO20, WHITE}, true}, body, text);
}

static const char *const SCENE_TAGS[] = {"PGM", "PVW"};
static const char *const SCENE_TITLES[] = {"PROGRAM", "PREVIEW"};
static const uint16_t SCENE_COLORS[] = {RED, GREEN};

// Small: the tag and the name on one 14 px line. Large: the title at 14 px, the name at 28 px.
static void draw_scene_line(canvas_t *canvas, const ui_widget_t *widget, const char *name) {
	ui_rect_t rect = widget->rect;
	fill_rect(canvas, rect, BAR);
	text_style_t tag = {&FONT_NOTO14, SCENE_COLORS[widget->arg]};
	int right = rect.x + rect.w - INSET;
	if (widget->size == UI_SIZE_LARGE) {
		pen_t pen = {rect.x + INSET, rect.y + INSET / 2};
		draw_text_line(canvas, tag, pen, right - pen.x, text_of(SCENE_TITLES[widget->arg]));
		pen.y += FONT_NOTO14.line_height;
		draw_text_line(canvas, (text_style_t){&FONT_NOTO28, WHITE}, pen, right - pen.x, text_of(name));
		return;
	}
	pen_t pen = {rect.x + INSET, centred_top(&FONT_NOTO14, rect)};
	draw_text_line(canvas, tag, pen, right - pen.x, text_of(SCENE_TAGS[widget->arg]));
	pen.x += 5 * FONT_NOTO14.line_height / 2;
	draw_text_line(canvas, (text_style_t){&FONT_NOTO14, WHITE}, pen, right - pen.x, text_of(name));
}

static void format_elapsed(char *out, size_t size, const char *name, uint32_t seconds) {
	snprintf(out, size, "%s %lu:%02lu:%02lu", name, (unsigned long)(seconds / 3600),
	         (unsigned long)(seconds / 60 % 60), (unsigned long)(seconds % 60));
}

static void draw_output(canvas_t *canvas, ui_rect_t slot, const char *name, render_output_t output) {
	char line[24];
	snprintf(line, sizeof line, "%s", name);
	if (output.on) {
		format_elapsed(line, sizeof line, name, output.seconds);
	}
	pen_t pen = {slot.x + INSET, centred_top(&FONT_NOTO14, slot)};
	text_style_t style = {&FONT_NOTO14, output.on ? RED : GREY};
	draw_text_line(canvas, style, pen, slot.w - INSET, text_of(line));
}

static void draw_link(canvas_t *canvas, ui_rect_t slot, const render_view_t *view) {
	int dot = 10;
	pen_t pen = {slot.x + INSET, centred_top(&FONT_NOTO14, slot)};
	fill_box(canvas, pen.x, slot.y + (slot.h - dot) / 2, dot, dot, view->link_ok ? GREEN : RED);
	pen.x += dot + INSET / 2;
	draw_text_line(canvas, (text_style_t){&FONT_NOTO14, WHITE}, pen, slot.x + slot.w - pen.x, text_of(view->link));
}

// The fields share the width equally, in document order.
static void draw_status(canvas_t *canvas, const ui_widget_t *widget, const render_view_t *view) {
	ui_rect_t rect = widget->rect;
	fill_rect(canvas, rect, BAR);
	for (uint8_t i = 0; i < widget->item_count; i++) {
		int x0 = rect.x + rect.w * i / widget->item_count, x1 = rect.x + rect.w * (i + 1) / widget->item_count;
		ui_rect_t slot = {(uint16_t)x0, rect.y, (uint16_t)(x1 - x0), rect.h};
		switch (widget->items[i]) {
		case UI_FIELD_LINK: draw_link(canvas, slot, view); break;
		case UI_FIELD_REC: draw_output(canvas, slot, "REC", view->rec); break;
		default: draw_output(canvas, slot, "LIVE", view->live); break;
		}
	}
}

// -12.4 dB from tenths.
static void format_db(char *out, size_t size, int tenths) {
	unsigned magnitude = (unsigned)(tenths < 0 ? -tenths : tenths);
	snprintf(out, size, "%s%u.%u dB", tenths < 0 ? "-" : "", magnitude / 10, magnitude % 10);
}

// The share of `width` that `tenths` fills between the fader floor and 0 dB.
static int bar_fill(int width, int tenths) {
	int clamped = min_int(max_int(tenths, FADER_FLOOR_TENTHS), 0);
	return width * (clamped - FADER_FLOOR_TENTHS) / -FADER_FLOOR_TENTHS;
}

static uint16_t meter_color(int tenths) {
	return tenths >= METER_RED_TENTHS ? RED : tenths >= METER_YELLOW_TENTHS ? YELLOW : GREEN;
}

// Draws one strip part at the pen and returns its height.
static int draw_strip_part(canvas_t *canvas, uint8_t part, pen_t pen, int width, const render_channel_t *channel) {
	char line[RENDER_WORD_MAX + 8];
	switch (part) {
	case UI_PART_NAME:
		draw_text_line(canvas, (text_style_t){&FONT_NOTO20, WHITE}, pen, width, text_of(channel->name));
		return FONT_NOTO20.line_height;
	case UI_PART_DB:
		format_db(line, sizeof line, channel->db_tenths);
		draw_text_line(canvas, (text_style_t){&FONT_NOTO28, WHITE}, pen, width,
		               text_of(channel->muted ? "MUTED" : line));
		return FONT_NOTO28.line_height;
	case UI_PART_FADER:
		fill_box(canvas, pen.x, pen.y, width, 10, DIM);
		fill_box(canvas, pen.x, pen.y, bar_fill(width, channel->db_tenths), 10, WHITE);
		return 14;
	case UI_PART_METER:
		fill_box(canvas, pen.x, pen.y, width, 6, DIM);
		fill_box(canvas, pen.x, pen.y, bar_fill(width, channel->peak_tenths), 6, meter_color(channel->peak_tenths));
		return 10;
	default:
		snprintf(line, sizeof line, "push: %s", channel->push);
		draw_text_line(canvas, (text_style_t){&FONT_NOTO14, GREY}, pen, width, text_of(line));
		return FONT_NOTO14.line_height;
	}
}

// The parts stack from the top in document order. Muted: the strip turns deep red (report 14).
static void draw_strip(canvas_t *canvas, const ui_widget_t *widget, const render_channel_t *channel) {
	ui_rect_t rect = widget->rect;
	fill_rect(canvas, rect, channel->muted ? DEEP_RED : CELL);
	pen_t pen = {rect.x + INSET, rect.y + INSET / 2};
	for (uint8_t i = 0; i < widget->item_count; i++) {
		pen.y += draw_strip_part(canvas, widget->items[i], pen, rect.w - 2 * INSET, channel);
	}
}

static void draw_fixed_text(canvas_t *canvas, const ui_widget_t *widget) {
	ui_rect_t rect = widget->rect;
	fill_rect(canvas, rect, BLACK);
	pen_t pen = {rect.x + INSET, centred_top(&FONT_NOTO20, rect)};
	draw_text_line(canvas, (text_style_t){&FONT_NOTO20, WHITE}, pen, rect.w - 2 * INSET,
	               (text_t){widget->text, widget->text_len});
}

static void draw_widget(canvas_t *canvas, const ui_widget_t *widget, const render_view_t *view) {
	switch (widget->kind) {
	case UI_KIND_STATUS: draw_status(canvas, widget, view); break;
	case UI_KIND_KEY: draw_key(canvas, widget->rect, &view->keys[widget->arg]); break;
	case UI_KIND_LEGEND: draw_legend(canvas, widget->rect, view->legends[widget->arg]); break;
	case UI_KIND_SCENE_LINE: draw_scene_line(canvas, widget, view->scene[widget->arg]); break;
	case UI_KIND_STRIP: draw_strip(canvas, widget, &view->channels[widget->arg]); break;
	default: draw_fixed_text(canvas, widget); break;
	}
}

// ---- What a widget shows, as a hash ----

#define FNV_OFFSET 2166136261u
#define FNV_PRIME 16777619u

static uint32_t hash_bytes(uint32_t hash, const void *bytes, size_t len) {
	const uint8_t *p = bytes;
	for (size_t i = 0; i < len; i++) {
		hash = (hash ^ p[i]) * FNV_PRIME;
	}
	return hash;
}

static uint32_t hash_number(uint32_t hash, uint32_t number) {
	uint8_t le[4] = {(uint8_t)number, (uint8_t)(number >> 8), (uint8_t)(number >> 16), (uint8_t)(number >> 24)};
	return hash_bytes(hash, le, sizeof le);
}

// With its NUL, so "ab" + "c" and "a" + "bc" differ.
static uint32_t hash_string(uint32_t hash, const char *string) {
	return hash_bytes(hash, string, strlen(string) + 1);
}

static uint32_t hash_layout_fields(const ui_widget_t *widget) {
	uint32_t hash = FNV_OFFSET;
	uint32_t fields[] = {widget->kind, widget->rect.x, widget->rect.y, widget->rect.w,
	                     widget->rect.h, widget->arg, widget->size, widget->item_count};
	for (size_t i = 0; i < sizeof fields / sizeof fields[0]; i++) {
		hash = hash_number(hash, fields[i]);
	}
	hash = hash_bytes(hash, widget->items, widget->item_count);
	return hash_bytes(hash, widget->text, widget->text_len);
}

static uint32_t hash_output(uint32_t hash, render_output_t output) {
	return hash_number(hash_number(hash, output.on), output.on ? output.seconds : 0);
}

static uint32_t hash_status(uint32_t hash, const ui_widget_t *widget, const render_view_t *view) {
	for (uint8_t i = 0; i < widget->item_count; i++) {
		switch (widget->items[i]) {
		case UI_FIELD_LINK: hash = hash_string(hash_number(hash, view->link_ok), view->link); break;
		case UI_FIELD_REC: hash = hash_output(hash, view->rec); break;
		default: hash = hash_output(hash, view->live); break;
		}
	}
	return hash;
}

static uint32_t hash_channel(uint32_t hash, const render_channel_t *channel) {
	hash = hash_string(hash, channel->name);
	hash = hash_number(hash, (uint16_t)channel->db_tenths);
	hash = hash_number(hash, (uint16_t)channel->peak_tenths);
	hash = hash_number(hash, channel->muted);
	return hash_string(hash, channel->push);
}

static uint32_t hash_shown(const ui_widget_t *widget, const render_view_t *view) {
	uint32_t hash = hash_layout_fields(widget);
	switch (widget->kind) {
	case UI_KIND_STATUS: return hash_status(hash, widget, view);
	case UI_KIND_KEY: {
		const render_key_t *key = &view->keys[widget->arg];
		return hash_string(hash_string(hash_number(hash, key->state), key->word), key->label);
	}
	case UI_KIND_LEGEND: return hash_string(hash, view->legends[widget->arg]);
	case UI_KIND_SCENE_LINE: return hash_string(hash, view->scene[widget->arg]);
	case UI_KIND_STRIP: return hash_channel(hash, &view->channels[widget->arg]);
	default: return hash;
	}
}

// ---- Frames ----

void render_init(render_t *render, render_sink_t sink) {
	memset(render, 0, sizeof *render);
	render->sink = sink;
}

static void mark_changed(render_t *render, ui_model_t *model, ui_display_t display, const render_view_t *view) {
	const ui_layout_t *layout = &model->layout[display];
	for (uint8_t i = 0; i < layout->count; i++) {
		uint32_t hash = hash_shown(&layout->widget[i], view);
		if (hash != render->shown[display][i]) {
			ui_mark(model, display, layout->widget[i].rect);
			render->shown[display][i] = hash;
		}
	}
}

static bool crosses(ui_rect_t a, ui_rect_t b) {
	return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

static ui_rect_t intersection(ui_rect_t a, ui_rect_t b) {
	int x0 = max_int(a.x, b.x), y0 = max_int(a.y, b.y);
	int x1 = min_int(a.x + a.w, b.x + b.w), y1 = min_int(a.y + a.h, b.y + b.h);
	return (ui_rect_t){(uint16_t)x0, (uint16_t)y0, (uint16_t)(x1 - x0), (uint16_t)(y1 - y0)};
}

static void paint_span(render_t *render, const ui_layout_t *layout, const render_view_t *view, ui_rect_t span) {
	canvas_t canvas = {render->band, span, span};
	fill_rect(&canvas, span, BLACK);
	for (uint8_t i = 0; i < layout->count; i++) {
		if (crosses(layout->widget[i].rect, span)) {
			canvas.clip = intersection(layout->widget[i].rect, span);
			draw_widget(&canvas, &layout->widget[i], view);
		}
	}
}

// The window of tiles first_col..end_col - 1 of a tile row, cut to the panel edge.
static ui_rect_t tile_span(ui_grid_t grid, unsigned row, unsigned first_col, unsigned end_col) {
	unsigned x = first_col * UI_TILE, y = row * UI_TILE;
	unsigned right = end_col * UI_TILE < grid.width ? end_col * UI_TILE : grid.width;
	unsigned bottom = y + UI_TILE < grid.height ? y + UI_TILE : grid.height;
	return (ui_rect_t){(uint16_t)x, (uint16_t)y, (uint16_t)(right - x), (uint16_t)(bottom - y)};
}

void render_display(render_t *render, ui_model_t *model, ui_display_t display, const render_view_t *view) {
	mark_changed(render, model, display, view);
	ui_grid_t grid = ui_grid(display);
	for (unsigned row = 0; row < grid.rows; row++) {
		unsigned col = 0;
		while (col < grid.cols) {
			if (!ui_tile_dirty(model, display, (uint16_t)col, (uint16_t)row)) {
				col++;
				continue;
			}
			unsigned first = col;
			while (col < grid.cols && ui_tile_dirty(model, display, (uint16_t)col, (uint16_t)row)) {
				col++;
			}
			ui_rect_t span = tile_span(grid, row, first, col);
			paint_span(render, &model->layout[display], view, span);
			render->sink.push(render->sink.context, display, span, render->band);
		}
	}
	ui_clean(model, display);
}
