// SPDX-License-Identifier: MIT
// Volumes are whole thousandths of a dB, so a step of 0.5 or 1.25 dB adds up exactly and prints
// the same on every build. A knob's next step builds on the volume it last sent until OBS reports
// a new one: the reply to a request comes after the next detent may (host volume.rs kept the sent
// volume until the next snapshot for the same reason).
#include "actions.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "json.h"

#define MDB_PER_DB 1000
#define MDB_UNKNOWN INT32_MIN
// docs/config.md "A knob": `step_db` lies above 0 and at most 6.
#define STEP_DB_MAX 6.0

static const char *const DO_WORDS[] = {"none", "scene", "toggle_mute", "toggle_record", "toggle_stream", "transition"};

enum { GROUP_KEYS, GROUP_BUTTONS, GROUP_KNOBS, GROUP_COUNT };
static const char *const GROUP_NAMES[GROUP_COUNT] = {"keys", "buttons", "knobs"};
static const uint16_t GROUP_SIZES[GROUP_COUNT] = {INPUT_KEYS, INPUT_BUTTONS, INPUT_KNOBS};

typedef struct {
	action_map_t *map;
	bool root_is_object;
	bool unmappable;
} reading_t;

// ---- Reading the map ----

static bool is_end(const json_event_t *event) {
	return event->kind == JSON_OBJECT_END || event->kind == JSON_LIST_END;
}

static bool is_member(const json_step_t *step, const char *name) {
	return !step->in_list && step->key != NULL && strcmp(step->key, name) == 0;
}

static int group_of(const json_step_t *step) {
	for (int group = 0; group < GROUP_COUNT; group++) {
		if (is_member(step, GROUP_NAMES[group])) {
			return group;
		}
	}
	return -1;
}

// docs/config.md "An OBS reference": 1..36 bytes, each 0x21-0x7E.
static bool read_uuid(const json_event_t *event, char out[OBS_UUID_MAX + 1]) {
	if (event->kind != JSON_STRING || event->truncated || event->len == 0 || event->len > OBS_UUID_MAX) {
		return false;
	}
	for (size_t i = 0; i < event->len; i++) {
		if (event->text[i] < 0x21 || event->text[i] > 0x7E) {
			return false;
		}
	}
	memcpy(out, event->text, event->len);
	out[event->len] = '\0';
	return true;
}

static bool read_do(const json_event_t *event, uint8_t *what) {
	if (event->kind != JSON_STRING) {
		return false;
	}
	for (uint8_t i = 0; i < sizeof DO_WORDS / sizeof DO_WORDS[0]; i++) {
		if (strlen(DO_WORDS[i]) == event->len && memcmp(DO_WORDS[i], event->text, event->len) == 0) {
			*what = i;
			return true;
		}
	}
	return false;
}

// A step below a thousandth of a dB still moves the volume: it counts as one thousandth.
static bool read_step(const json_event_t *event, int32_t *step_mdb) {
	if (event->kind != JSON_NUMBER) {
		return false;
	}
	double db = strtod(event->text, NULL);
	if (!(db > 0.0 && db <= STEP_DB_MAX)) {
		return false;
	}
	int32_t mdb = (int32_t)(db * MDB_PER_DB + 0.5);
	*step_mdb = mdb > 0 ? mdb : 1;
	return true;
}

// `depth` is the depth of the action object. A new object replaces the first one whole.
static void read_action_event(reading_t *reading, action_t *action, const json_event_t *event, size_t depth) {
	if (event->depth == depth) {
		*action = (action_t){0};
		return;
	}
	if (event->depth != depth + 1) {
		return;
	}
	const json_step_t *member = &event->path[depth];
	if (is_member(member, "do")) {
		reading->unmappable |= !read_do(event, &action->what);
	} else if (is_member(member, "uuid")) {
		reading->unmappable |= !read_uuid(event, action->uuid);
	}
}

static void read_input_event(reading_t *reading, action_knob_t *knob, const json_event_t *event) {
	if (event->depth == 3) {
		knob->input[0] = '\0';
		reading->unmappable |= event->kind != JSON_NULL && event->kind != JSON_OBJECT_BEGIN;
	} else if (event->depth == 4 && is_member(&event->path[3], "uuid")) {
		reading->unmappable |= !read_uuid(event, knob->input);
	}
}

static void read_knob_event(reading_t *reading, action_knob_t *knob, const json_event_t *event) {
	if (event->depth == 2) {
		*knob = (action_knob_t){0};
		return;
	}
	const json_step_t *member = &event->path[2];
	if (is_member(member, "push")) {
		read_action_event(reading, &knob->push, event, 3);
	} else if (is_member(member, "input")) {
		read_input_event(reading, knob, event);
	} else if (event->depth == 3 && is_member(member, "step_db")) {
		reading->unmappable |= !read_step(event, &knob->step_mdb);
	}
}

static void clear_group(action_map_t *map, int group) {
	if (group == GROUP_KEYS) {
		memset(map->keys, 0, sizeof map->keys);
	} else if (group == GROUP_BUTTONS) {
		memset(map->buttons, 0, sizeof map->buttons);
	} else {
		memset(map->knobs, 0, sizeof map->knobs);
	}
}

// A new value for a list drops what the first one held.
static void on_event(void *context, const json_event_t *event) {
	reading_t *reading = context;
	if (event->depth == 0) {
		reading->root_is_object |= event->kind == JSON_OBJECT_BEGIN;
		return;
	}
	int group = group_of(&event->path[0]);
	if (group < 0 || is_end(event)) {
		return;
	}
	if (event->depth == 1) {
		clear_group(reading->map, group);
		return;
	}
	if (!event->path[1].in_list) {
		return;
	}
	uint16_t index = event->path[1].index;
	if (index >= GROUP_SIZES[group]) {
		reading->unmappable = true;
	} else if (group == GROUP_KNOBS) {
		read_knob_event(reading, &reading->map->knobs[index], event);
	} else {
		action_t *actions = group == GROUP_KEYS ? reading->map->keys : reading->map->buttons;
		read_action_event(reading, &actions[index], event, 2);
	}
}

bool actions_parse(action_map_t *map, const uint8_t *doc, size_t len) {
	memset(map, 0, sizeof *map);
	reading_t reading = {map, false, false};
	json_reader_t reader;
	json_reader_init(&reader, on_event, &reading);
	return json_feed(&reader, doc, len) == JSON_DONE && reading.root_is_object && !reading.unmappable;
}

void actions_init(actions_t *actions, const action_map_t *map) {
	memset(actions, 0, sizeof *actions);
	actions->map = *map;
}

// ---- Writing requests ----

// A UUID holds 0x21-0x7E only, so '"' and '\' are the bytes JSON needs escaped.
static void escape_uuid(const char *uuid, char out[2 * OBS_UUID_MAX + 1]) {
	size_t at = 0;
	for (const char *c = uuid; *c != '\0'; c++) {
		if (*c == '"' || *c == '\\') {
			out[at++] = '\\';
		}
		out[at++] = *c;
	}
	out[at] = '\0';
}

static bool plain_request(action_request_t *request, const char *type) {
	request->type = type;
	request->data[0] = '\0';
	return true;
}

static bool uuid_request(action_request_t *request, const char *type, const char *field, const char *uuid) {
	char escaped[2 * OBS_UUID_MAX + 1];
	if (uuid[0] == '\0') {
		return false;
	}
	escape_uuid(uuid, escaped);
	request->type = type;
	snprintf(request->data, sizeof request->data, "{\"%s\":\"%s\"}", field, escaped);
	return true;
}

// `mute_uuid` is the input `toggle_mute` acts on: the action's own, or a knob push's knob input.
static bool press_request(const action_t *action, const char *mute_uuid, const obs_state_t *state,
                          action_request_t *request) {
	switch (action->what) {
	case ACTION_SCENE: return uuid_request(request, "SetCurrentProgramScene", "sceneUuid", action->uuid);
	case ACTION_TOGGLE_MUTE: return uuid_request(request, "ToggleInputMute", "inputUuid", mute_uuid);
	case ACTION_TOGGLE_RECORD: return plain_request(request, "ToggleRecord");
	case ACTION_TOGGLE_STREAM: return plain_request(request, "ToggleStream");
	case ACTION_TRANSITION: return state->studio_mode && plain_request(request, "TriggerStudioModeTransition");
	default: return false;
	}
}

#define DB_TEXT_MAX 24

// Whole and thousandths, with no trailing zero: -18000 is "-18", -750 is "-0.75".
static void write_db(char out[DB_TEXT_MAX], int32_t mdb) {
	uint32_t magnitude = (uint32_t)(mdb < 0 ? -(int64_t)mdb : mdb);
	unsigned thousandths = magnitude % MDB_PER_DB;
	char fraction[5] = {'.', (char)('0' + thousandths / 100), (char)('0' + thousandths / 10 % 10),
	                    (char)('0' + thousandths % 10), '\0'};
	for (size_t end = 4; end > 0 && (fraction[end - 1] == '0' || fraction[end - 1] == '.'); end--) {
		fraction[end - 1] = '\0';
	}
	snprintf(out, DB_TEXT_MAX, "%s%u%s", mdb < 0 ? "-" : "", (unsigned)(magnitude / MDB_PER_DB), fraction);
}

static bool volume_request(action_request_t *request, const char *uuid, int32_t mdb) {
	char escaped[2 * OBS_UUID_MAX + 1];
	char db[DB_TEXT_MAX];
	escape_uuid(uuid, escaped);
	write_db(db, mdb);
	request->type = "SetInputVolume";
	snprintf(request->data, sizeof request->data, "{\"inputUuid\":\"%s\",\"inputVolumeDb\":%s}", escaped, db);
	return true;
}

// ---- Knob volume ----

static int32_t clamp_mdb(int64_t mdb) {
	const int64_t low = (int64_t)ACTIONS_DB_MIN * MDB_PER_DB, high = (int64_t)ACTIONS_DB_MAX * MDB_PER_DB;
	return (int32_t)(mdb < low ? low : mdb > high ? high : mdb);
}

// The knob input's volume as OBS last reported it, or MDB_UNKNOWN.
static int32_t obs_mdb(const obs_state_t *state, size_t knob, const char *input) {
	const obs_knob_t *watched = &state->knobs[knob];
	float db = watched->volume_db;
	if (!watched->volume_known || strcmp(watched->uuid, input) != 0 || isnan(db)) {
		return MDB_UNKNOWN;
	}
	db = db < ACTIONS_DB_MIN ? ACTIONS_DB_MIN : db > ACTIONS_DB_MAX ? ACTIONS_DB_MAX : db;
	return (int32_t)(db * MDB_PER_DB + (db < 0 ? -0.5f : 0.5f));
}

static bool send_volume(action_volume_t *volume, const action_knob_t *knob, int32_t base_mdb, int32_t detents,
                        int32_t obs_mdb_now, action_request_t *request) {
	volume->sent_mdb = clamp_mdb(base_mdb + (int64_t)detents * knob->step_mdb);
	volume->sent = true;
	volume->obs_mdb_then = obs_mdb_now;
	return volume_request(request, knob->input, volume->sent_mdb);
}

static bool knob_turn(actions_t *actions, const obs_state_t *state, size_t index, int8_t detents, uint32_t now_ms,
                      action_request_t *request) {
	const action_knob_t *knob = &actions->map.knobs[index];
	action_volume_t *volume = &actions->volume[index];
	if (knob->input[0] == '\0' || knob->step_mdb == 0 || detents == 0) {
		return false;
	}
	if (volume->window_open) {
		volume->detents_waiting += detents;
		return false;
	}
	int32_t obs_now = obs_mdb(state, index, knob->input);
	bool builds_on_sent = volume->sent && obs_now == volume->obs_mdb_then;
	if (!builds_on_sent && obs_now == MDB_UNKNOWN) {
		return false;
	}
	int32_t first = detents > 0 ? 1 : -1;
	volume->detents_waiting = detents - first;
	volume->window_open = true;
	volume->window_ends_ms = now_ms + ACTIONS_WINDOW_MS;
	return send_volume(volume, knob, builds_on_sent ? volume->sent_mdb : obs_now, first, obs_now, request);
}

bool actions_poll(actions_t *actions, const obs_state_t *state, uint32_t now_ms, action_request_t *request) {
	for (size_t index = 0; index < INPUT_KNOBS; index++) {
		action_volume_t *volume = &actions->volume[index];
		if (!volume->window_open || (int32_t)(now_ms - volume->window_ends_ms) < 0) {
			continue;
		}
		volume->window_open = false;
		int32_t waiting = volume->detents_waiting;
		volume->detents_waiting = 0;
		if (waiting != 0) {
			const action_knob_t *knob = &actions->map.knobs[index];
			return send_volume(volume, knob, volume->sent_mdb, waiting, obs_mdb(state, index, knob->input),
			                   request);
		}
	}
	return false;
}

// ---- Dispatch ----

bool actions_on_input(actions_t *actions, const obs_state_t *state, const input_event_t *event, uint32_t now_ms,
                      action_request_t *request) {
	const action_map_t *map = &actions->map;
	uint8_t index = event->index;
	if (event->source == INPUT_SOURCE_KNOB_TURN) {
		return index < INPUT_KNOBS && knob_turn(actions, state, index, event->value, now_ms, request);
	}
	if (event->value != 1) {
		return false;
	}
	switch (event->source) {
	case INPUT_SOURCE_KEY:
		return index < INPUT_KEYS && press_request(&map->keys[index], map->keys[index].uuid, state, request);
	case INPUT_SOURCE_BUTTON:
		return index < INPUT_BUTTONS &&
		       press_request(&map->buttons[index], map->buttons[index].uuid, state, request);
	case INPUT_SOURCE_KNOB_PUSH:
		return index < INPUT_KNOBS && press_request(&map->knobs[index].push, map->knobs[index].input, state, request);
	default: return false;
	}
}
