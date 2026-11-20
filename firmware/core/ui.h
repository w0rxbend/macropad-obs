// SPDX-License-Identifier: MIT
// Widget model of the two panels and their tile grids (spec 9 `fw-ui`, docs/config.md "Widgets").
// The model holds the `main_display` and `strip_display` widgets of the stored document. A load
// marks dirty only the tiles of the widgets that changed, so the renderer pushes only those tiles.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define UI_WIDGETS_MAX 16
#define UI_TEXT_MAX 32
#define UI_ITEMS_MAX 5 // the longest word list a widget holds: the five strip parts
// A tile is 16 x 16 pixels: one tile row is one 16-line band of the renderer (R14). The tiles of
// the last column and row are cut to the panel edge.
#define UI_TILE 16

typedef enum { UI_MAIN, UI_STRIP, UI_DISPLAYS } ui_display_t;

// The order of each list in docs/config.md, as in config.c.
typedef enum { UI_KIND_STATUS, UI_KIND_KEY, UI_KIND_LEGEND, UI_KIND_SCENE_LINE, UI_KIND_STRIP, UI_KIND_TEXT } ui_kind_t;
typedef enum { UI_FIELD_LINK, UI_FIELD_REC, UI_FIELD_LIVE } ui_status_field_t;
typedef enum { UI_PART_NAME, UI_PART_DB, UI_PART_FADER, UI_PART_METER, UI_PART_PUSH } ui_strip_part_t;
typedef enum { UI_SCENE_PROGRAM, UI_SCENE_PREVIEW } ui_scene_t;
typedef enum { UI_SIZE_SMALL, UI_SIZE_LARGE } ui_size_t;

typedef struct {
	uint16_t x, y, w, h;
} ui_rect_t;

typedef struct {
	uint8_t kind; // ui_kind_t
	ui_rect_t rect;
	// `key`: the key, `legend`: the button, `strip`: the knob, `scene_line`: a ui_scene_t.
	uint8_t arg;
	uint8_t size; // `scene_line` only: a ui_size_t
	// `status` fields or `strip` parts in document order, each a ui_status_field_t or ui_strip_part_t.
	uint8_t item_count;
	uint8_t items[UI_ITEMS_MAX];
	uint8_t text_len; // `text` only
	char text[UI_TEXT_MAX + 1];
} ui_widget_t;

typedef struct {
	uint8_t count;
	ui_widget_t widget[UI_WIDGETS_MAX];
} ui_layout_t;

typedef struct {
	uint16_t width, height; // pixels
	uint16_t cols, rows;    // tiles
} ui_grid_t;

// 320 x 480 gives 20 x 30 tiles, the most of the two panels.
#define UI_TILE_BYTES ((20 * 30 + 7) / 8)

typedef struct {
	ui_layout_t layout[UI_DISPLAYS];
	uint8_t dirty[UI_DISPLAYS][UI_TILE_BYTES]; // bit (row * cols + col)
} ui_model_t;

ui_grid_t ui_grid(ui_display_t display);

// An empty model with every tile dirty: the first frame paints both panels whole.
void ui_init(ui_model_t *model);

// Reads both layouts from a document that config_validate accepted. Still refuses, with false,
// what would make the model unsafe to draw: bytes that are not one JSON object, more than
// UI_WIDGETS_MAX widgets, a rectangle outside its panel, and in a member the widget's kind uses an
// unknown word, a number that is not an integer, an argument out of range or a list or text too
// long. Members the kind does not use are ignored, as config.c does. Fields the document lacks
// read as 0. After false, `layouts` holds
// nothing to use. No heap. Takes 3.3 kB of stack on a 64-bit host
// (gcc -fstack-usage), plus the 1.7 kB of `layouts` the caller holds.
bool ui_parse(ui_layout_t layouts[UI_DISPLAYS], const uint8_t *doc, size_t len);

// The index of the first widget that overlaps a widget before it, or -1. Sharing an edge is not
// an overlap. The same pair rule 4 of docs/config.md names, so config.c reports the same index.
int ui_find_overlap(const ui_layout_t *layout);

// Takes both layouts. Every tile under a widget that left or came marks dirty; a widget found
// unchanged in the new layout, at any index, marks nothing. Refuses, with false and the model as
// it was, a layout with an overlap: the pad never shows half a layout.
bool ui_apply(ui_model_t *model, const ui_layout_t layouts[UI_DISPLAYS]);

bool ui_tile_dirty(const ui_model_t *model, ui_display_t display, uint16_t col, uint16_t row);

// After the renderer pushed every dirty tile of the display.
void ui_clean(ui_model_t *model, ui_display_t display);
