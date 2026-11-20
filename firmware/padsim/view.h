// SPDX-License-Identifier: MIT
// What the widgets show, built from the document, the OBS state and the link state: the
// render_view_t of render.h. A name OBS gives wins over the document's `label`, which shows
// while OBS is away (docs/config.md). obs_state reads no timecode, so REC and LIVE count 0 s.
// padsim's glue for now; the port and the app preview (task 3.4) need the same mapping.
#pragma once

#include "actions.h"
#include "link.h"
#include "obs.h"
#include "obs_state.h"
#include "render.h"

#include <stddef.h>
#include <stdint.h>

// The `label` members of a document. Empty where it has none.
typedef struct {
	char keys[INPUT_KEYS][RENDER_LABEL_MAX + 1];
	char buttons[INPUT_BUTTONS][RENDER_LABEL_MAX + 1];
	char knobs[INPUT_KNOBS][RENDER_LABEL_MAX + 1]; // knobs[].input.label
} view_labels_t;

typedef struct {
	const action_map_t *map;
	const view_labels_t *labels;
	const obs_state_t *obs;
	obs_status_t obs_status;
	enum link_wifi_state wifi;
} view_source_t;

// Reads the labels of a document that config_validate accepted.
void view_labels_parse(view_labels_t *labels, const uint8_t *doc, size_t len);

void view_build(render_view_t *view, const view_source_t *source);
