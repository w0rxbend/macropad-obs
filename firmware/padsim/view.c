// SPDX-License-Identifier: MIT
#include "view.h"

#include "json.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#define TENTHS_MIN (ACTIONS_DB_MIN * 10)
#define TENTHS_MAX (ACTIONS_DB_MAX * 10)

// Indexed by action_do_t.
static const char *const WORDS[] = {"", "SCENE", "MUTE", "REC", "STREAM", "TRANS"};

static void copy_label(char out[RENDER_LABEL_MAX + 1], const json_event_t *event) {
	size_t len = event->len < RENDER_LABEL_MAX ? event->len : RENDER_LABEL_MAX;
	memcpy(out, event->text, len);
	out[len] = '\0';
}

static void keep_label(void *context, const json_event_t *event) {
	view_labels_t *labels = context;
	if (event->kind != JSON_STRING || event->depth < 3) {
		return;
	}
	uint16_t index = event->path[1].index;
	if (json_path_is(event, "keys[].label") && index < INPUT_KEYS) {
		copy_label(labels->keys[index], event);
	} else if (json_path_is(event, "buttons[].label") && index < INPUT_BUTTONS) {
		copy_label(labels->buttons[index], event);
	} else if (json_path_is(event, "knobs[].input.label") && index < INPUT_KNOBS) {
		copy_label(labels->knobs[index], event);
	}
}

void view_labels_parse(view_labels_t *labels, const uint8_t *doc, size_t len) {
	memset(labels, 0, sizeof *labels);
	json_reader_t reader;
	json_reader_init(&reader, keep_label, labels);
	json_feed(&reader, doc, len);
}

static const char *name_of(const obs_item_t *items, uint16_t count, const char *uuid) {
	for (uint16_t i = 0; i < count && uuid[0] != '\0'; i++) {
		if (strcmp(items[i].uuid, uuid) == 0) {
			return items[i].name;
		}
	}
	return NULL;
}

static const char *scene_name(const obs_state_t *obs, const char *uuid) {
	return name_of(obs->scenes, obs->scene_count, uuid);
}

static const char *input_name(const obs_state_t *obs, const char *uuid) {
	return name_of(obs->inputs, obs->input_count, uuid);
}

static const char *word_of(const action_t *action) {
	return action->what < sizeof WORDS / sizeof WORDS[0] ? WORDS[action->what] : "";
}

// True when OBS has told the whole state, so a reference it does not list is gone.
static bool obs_known(const view_source_t *source) {
	return source->obs_status == OBS_UP && obs_state_is_current(source->obs);
}

static bool input_muted(const obs_state_t *obs, const char *uuid) {
	for (size_t knob = 0; knob < OBS_KNOBS; knob++) {
		const obs_knob_t *watched = &obs->knobs[knob];
		if (strcmp(watched->uuid, uuid) == 0 && watched->mute_known) {
			return watched->muted;
		}
	}
	return false;
}

static render_key_state_t scene_key_state(const view_source_t *source, const char *uuid) {
	const obs_state_t *obs = source->obs;
	if (strcmp(obs->program, uuid) == 0) {
		return RENDER_KEY_PROGRAM;
	}
	if (strcmp(obs->preview, uuid) == 0) {
		return RENDER_KEY_PREVIEW;
	}
	return obs_known(source) && scene_name(obs, uuid) == NULL ? RENDER_KEY_MISSING : RENDER_KEY_IDLE;
}

static render_key_state_t mute_key_state(const view_source_t *source, const char *uuid) {
	if (obs_known(source) && input_name(source->obs, uuid) == NULL) {
		return RENDER_KEY_MISSING;
	}
	return input_muted(source->obs, uuid) ? RENDER_KEY_ON : RENDER_KEY_IDLE;
}

static render_key_state_t key_state(const view_source_t *source, const action_t *action) {
	switch (action->what) {
	case ACTION_SCENE:
		return scene_key_state(source, action->uuid);
	case ACTION_TOGGLE_MUTE:
		return mute_key_state(source, action->uuid);
	case ACTION_TOGGLE_RECORD:
		return source->obs->recording ? RENDER_KEY_ON : RENDER_KEY_IDLE;
	case ACTION_TOGGLE_STREAM:
		return source->obs->streaming ? RENDER_KEY_ON : RENDER_KEY_IDLE;
	case ACTION_TRANSITION:
		return RENDER_KEY_IDLE;
	default:
		return RENDER_KEY_UNBOUND;
	}
}

static const char *key_label(const view_source_t *source, size_t key) {
	const action_t *action = &source->map->keys[key];
	const char *named = NULL;
	if (action->what == ACTION_SCENE) {
		named = scene_name(source->obs, action->uuid);
	} else if (action->what == ACTION_TOGGLE_MUTE) {
		named = input_name(source->obs, action->uuid);
	}
	return named != NULL ? named : source->labels->keys[key];
}

static void build_keys(render_view_t *view, const view_source_t *source) {
	for (size_t key = 0; key < RENDER_KEYS; key++) {
		const action_t *action = &source->map->keys[key];
		render_key_t *shown = &view->keys[key];
		shown->state = (uint8_t)key_state(source, action);
		snprintf(shown->word, sizeof shown->word, "%s", word_of(action));
		snprintf(shown->label, sizeof shown->label, "%s", key_label(source, key));
	}
}

static void build_legends(render_view_t *view, const view_source_t *source) {
	for (size_t button = 0; button < RENDER_BUTTONS; button++) {
		const char *label = source->labels->buttons[button];
		const char *legend = label[0] != '\0' ? label : word_of(&source->map->buttons[button]);
		snprintf(view->legends[button], sizeof view->legends[button], "%s", legend);
	}
}

static int16_t tenths(float db) {
	float scaled = db * 10.0f;
	if (scaled <= TENTHS_MIN) {
		return TENTHS_MIN;
	}
	if (scaled >= TENTHS_MAX) {
		return TENTHS_MAX;
	}
	return (int16_t)(scaled + (scaled >= 0 ? 0.5f : -0.5f));
}

// The meter peak is linear: 1.0 is 0 dBFS.
static int16_t peak_tenths(float peak) {
	return peak > 0 ? tenths(20.0f * log10f(peak)) : TENTHS_MIN;
}

static void build_channel(render_channel_t *channel, const view_source_t *source, size_t knob) {
	const action_knob_t *mapped = &source->map->knobs[knob];
	const obs_knob_t *watched = &source->obs->knobs[knob];
	const char *named = input_name(source->obs, mapped->input);
	snprintf(channel->name, sizeof channel->name, "%s", named != NULL ? named : source->labels->knobs[knob]);
	channel->db_tenths = watched->volume_known ? tenths(watched->volume_db) : TENTHS_MIN;
	channel->peak_tenths = peak_tenths(watched->meter_peak);
	channel->muted = watched->mute_known && watched->muted;
	snprintf(channel->push, sizeof channel->push, "%s", word_of(&mapped->push));
}

static const char *link_word(const view_source_t *source) {
	if (source->wifi != LINK_WIFI_UP) {
		return "No network";
	}
	switch (source->obs_status) {
	case OBS_UP:
		return "OBS ok";
	case OBS_CONNECTING:
		return "Connecting";
	case OBS_IDLE:
		return "No OBS";
	default:
		return "OBS error";
	}
}

static void build_status(render_view_t *view, const view_source_t *source) {
	const obs_state_t *obs = source->obs;
	view->link_ok = source->obs_status == OBS_UP;
	snprintf(view->link, sizeof view->link, "%s", link_word(source));
	view->rec = (render_output_t){.on = obs->recording, .seconds = 0};
	view->live = (render_output_t){.on = obs->streaming, .seconds = 0};
	const char *program = scene_name(obs, obs->program);
	const char *preview = scene_name(obs, obs->preview);
	snprintf(view->scene[UI_SCENE_PROGRAM], sizeof view->scene[0], "%s", program != NULL ? program : "");
	snprintf(view->scene[UI_SCENE_PREVIEW], sizeof view->scene[0], "%s", preview != NULL ? preview : "");
}

void view_build(render_view_t *view, const view_source_t *source) {
	memset(view, 0, sizeof *view);
	build_status(view, source);
	build_keys(view, source);
	build_legends(view, source);
	for (size_t knob = 0; knob < RENDER_KNOBS; knob++) {
		build_channel(&view->channels[knob], source, knob);
	}
}
