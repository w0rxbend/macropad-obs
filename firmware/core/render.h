// SPDX-License-Identifier: MIT
// The fw-ui band renderer (spec 9, report 14 "Drawing rules"). No frame buffer: each tile row of a
// panel is one 16-line band, and only the runs of dirty tiles in it are painted and pushed. A
// widget whose shown values change dirties its own tiles, so a value change pushes only those.
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "ui.h"

#define RENDER_KEYS 9
#define RENDER_BUTTONS 4
#define RENDER_KNOBS 3
#define RENDER_LABEL_MAX 48 // a config `label` (docs/config.md)
#define RENDER_WORD_MAX 15
#define RENDER_BAND_WIDTH 320 // the widest panel

// The state a key widget shows, with two cues each so it reads without colour (report 14).
typedef enum {
	RENDER_KEY_UNBOUND, // empty outline
	RENDER_KEY_IDLE,    // dark fill
	RENDER_KEY_PROGRAM, // red fill, "PGM"
	RENDER_KEY_PREVIEW, // green border, "PVW"
	RENDER_KEY_ON,      // a toggle that is on: amber fill, "ON"
	RENDER_KEY_MISSING, // its scene or input is gone from OBS: grey text, dashed outline
} render_key_state_t;

typedef struct {
	uint8_t state;                   // render_key_state_t
	char word[RENDER_WORD_MAX + 1];  // the action word above the label, or empty
	char label[RENDER_LABEL_MAX + 1];
} render_key_t;

typedef struct {
	bool on;
	uint32_t seconds; // elapsed, shown as h:mm:ss
} render_output_t;

typedef struct {
	char name[RENDER_LABEL_MAX + 1];
	int16_t db_tenths;   // the fader setting, -1000..260
	int16_t peak_tenths; // the live peak
	bool muted;
	char push[RENDER_WORD_MAX + 1]; // the push action word
} render_channel_t;

// Everything the widgets show besides the layout. Strings are UTF-8 and end with NUL.
typedef struct {
	bool link_ok;
	char link[RENDER_WORD_MAX + 1]; // "OBS ok", "No network", ...
	render_output_t rec, live;
	char scene[2][RENDER_LABEL_MAX + 1]; // indexed by ui_scene_t
	render_key_t keys[RENDER_KEYS];
	char legends[RENDER_BUTTONS][RENDER_LABEL_MAX + 1];
	render_channel_t channels[RENDER_KNOBS];
} render_view_t;

// One window of the panel and its pixels, row by row, `window.w` to a row. RGB565 values; the
// port sends each one high byte first (spec 14).
typedef struct {
	void (*push)(void *context, ui_display_t display, ui_rect_t window, const uint16_t *pixels);
	void *context;
} render_sink_t;

typedef struct {
	render_sink_t sink;
	uint32_t shown[UI_DISPLAYS][UI_WIDGETS_MAX]; // a hash of what each widget last showed
	uint16_t band[RENDER_BAND_WIDTH * UI_TILE];
} render_t;

void render_init(render_t *render, render_sink_t sink);

// Marks the tiles of each widget whose values changed since the last call, paints every dirty
// tile of the display top to bottom, one push per run of dirty tiles in a band, then cleans the
// display. Pixels no widget covers are black.
void render_display(render_t *render, ui_model_t *model, ui_display_t display, const render_view_t *view);
