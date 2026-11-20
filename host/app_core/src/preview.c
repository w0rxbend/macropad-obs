// SPDX-License-Identifier: MIT
// The app's display preview (spec 13 criterion 4b, R13 "Live preview"): the firmware's own fw-ui
// C draws a document and a sample OBS state. padsim's view_build maps them to what the widgets
// show, as on the pad; the renderer's bands go straight into two frame buffers instead of
// through a panel window. Built by build.rs through `cc`, called only from preview.rs.
#include "actions.h"
#include "obs.h"
#include "obs_state.h"
#include "render.h"
#include "ui.h"
#include "view.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// One scene or input of the sample state. The caller passes what obs_state.c would keep from an
// OBS reply: a UUID config takes and a name already cut to OBS_NAME_MAX bytes, both ending in NUL.
typedef struct {
	const char *uuid;
	const char *name;
	bool muted;      // inputs only
	float volume_db; // inputs only
} preview_item_t;

typedef struct {
	const preview_item_t *scenes;
	size_t scene_count;
	const preview_item_t *inputs;
	size_t input_count;
	const char *program; // "" for none
	const char *preview; // "" for none
	bool studio_mode;
	bool recording;
	bool streaming;
} preview_obs_t;

// The values preview.rs maps to its error type.
enum { PREVIEW_OK, PREVIEW_REFUSED, PREVIEW_NO_MEMORY, PREVIEW_BAD_WINDOW };

typedef struct {
	uint8_t *rgb[UI_DISPLAYS];
	bool bad_window;
} frames_t;

// The large state lives on the heap: obs_state_t alone is about 57 kB.
typedef struct {
	obs_state_t obs;
	action_map_t map;
	view_labels_t labels;
	ui_layout_t layouts[UI_DISPLAYS];
	ui_model_t model;
	render_view_t view;
	render_t render;
} preview_work_t;

// Big-endian RGB565, row by row, the panel's width to a row: the bytes padsim's dump writes.
static void put_pixels(void *context, ui_display_t display, ui_rect_t window, const uint16_t *pixels) {
	frames_t *frames = context;
	ui_grid_t grid = ui_grid(display);
	if ((uint32_t)window.x + window.w > grid.width || (uint32_t)window.y + window.h > grid.height) {
		frames->bad_window = true;
		return;
	}
	for (size_t row = 0; row < window.h; row++) {
		uint8_t *out = frames->rgb[display] + (((size_t)window.y + row) * grid.width + window.x) * 2;
		for (size_t col = 0; col < window.w; col++) {
			uint16_t pixel = pixels[row * window.w + col];
			out[2 * col] = (uint8_t)(pixel >> 8);
			out[2 * col + 1] = (uint8_t)pixel;
		}
	}
}

// Past the table's cap the list keeps its first items, as obs_state.c does.
static uint16_t copy_items(obs_item_t *table, size_t cap, const preview_item_t *items, size_t count) {
	size_t kept = count < cap ? count : cap;
	for (size_t i = 0; i < kept; i++) {
		snprintf(table[i].uuid, sizeof table[i].uuid, "%s", items[i].uuid);
		snprintf(table[i].name, sizeof table[i].name, "%s", items[i].name);
	}
	return (uint16_t)kept;
}

// The knob reads obs_state.c makes for each mapped input: mute and volume, known when OBS
// lists the input.
static void watch_knobs(obs_state_t *obs, const action_map_t *map, const preview_obs_t *sample) {
	for (size_t knob = 0; knob < OBS_KNOBS; knob++) {
		obs_knob_t *watched = &obs->knobs[knob];
		snprintf(watched->uuid, sizeof watched->uuid, "%s", map->knobs[knob].input);
		for (size_t i = 0; i < sample->input_count && watched->uuid[0] != '\0'; i++) {
			if (strcmp(sample->inputs[i].uuid, watched->uuid) == 0) {
				watched->mute_known = watched->volume_known = true;
				watched->muted = sample->inputs[i].muted;
				watched->volume_db = sample->inputs[i].volume_db;
				break;
			}
		}
	}
}

// The state as obs_state.c holds it once OBS has answered the whole read: nothing pending.
static void fill_obs(obs_state_t *obs, const action_map_t *map, const preview_obs_t *sample) {
	obs_state_init(obs);
	obs->scene_count = copy_items(obs->scenes, OBS_SCENES_MAX, sample->scenes, sample->scene_count);
	obs->scenes_capped = sample->scene_count > OBS_SCENES_MAX;
	obs->input_count = copy_items(obs->inputs, OBS_INPUTS_MAX, sample->inputs, sample->input_count);
	obs->inputs_capped = sample->input_count > OBS_INPUTS_MAX;
	snprintf(obs->program, sizeof obs->program, "%s", sample->program);
	snprintf(obs->preview, sizeof obs->preview, "%s", sample->preview);
	obs->studio_mode = sample->studio_mode;
	obs->recording = sample->recording;
	obs->streaming = sample->streaming;
	watch_knobs(obs, map, sample);
}

static int draw(preview_work_t *work, const uint8_t *doc, size_t len, const preview_obs_t *sample, frames_t *frames) {
	if (!actions_parse(&work->map, doc, len) || !ui_parse(work->layouts, doc, len)) {
		return PREVIEW_REFUSED;
	}
	view_labels_parse(&work->labels, doc, len);
	ui_init(&work->model);
	if (!ui_apply(&work->model, work->layouts)) {
		return PREVIEW_REFUSED;
	}
	fill_obs(&work->obs, &work->map, sample);
	view_source_t source = {
	    .map = &work->map,
	    .labels = &work->labels,
	    .obs = &work->obs,
	    .obs_status = OBS_UP,
	    .wifi = LINK_WIFI_UP,
	};
	view_build(&work->view, &source);
	render_init(&work->render, (render_sink_t){put_pixels, frames});
	render_display(&work->render, &work->model, UI_MAIN, &work->view);
	render_display(&work->render, &work->model, UI_STRIP, &work->view);
	return frames->bad_window ? PREVIEW_BAD_WINDOW : PREVIEW_OK;
}

// Draws both panels of a document that config_validate accepted, with OBS up and current and
// Wi-Fi up. `main_rgb` holds 320 x 480 x 2 bytes, `strip_rgb` 142 x 428 x 2; pixels no widget
// covers are black. Returns a PREVIEW_* value; after an error the frames hold nothing to use.
int preview_render(const uint8_t *doc, size_t len, const preview_obs_t *sample, uint8_t *main_rgb,
                   uint8_t *strip_rgb) {
	preview_work_t *work = calloc(1, sizeof *work);
	if (work == NULL) {
		return PREVIEW_NO_MEMORY;
	}
	frames_t frames = {.rgb = {main_rgb, strip_rgb}, .bad_window = false};
	int result = draw(work, doc, len, sample, &frames);
	free(work);
	return result;
}
