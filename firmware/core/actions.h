// SPDX-License-Identifier: MIT
// Inputs to obs-websocket 5 requests (spec 9 `fw-actions`, docs/config.md "An action", criterion
// 4c). The map comes from the stored document. A key, button or knob push acts on press. A knob
// turn sets its input's volume to an absolute dB: the first detent goes at once, the others of a
// 30 ms window go as one sum when actions_poll closes it, clamped to OBS's -100..26 dB. Port of
// the old host keymap.rs and volume.rs. Pure C, no SDK headers, no heap.
#pragma once

#include "input.h"
#include "obs_state.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ACTIONS_WINDOW_MS 30
#define ACTIONS_DB_MIN (-100)
#define ACTIONS_DB_MAX 26
// Holds the longest `requestData`, a 36-byte UUID with every byte escaped and a volume (112 bytes
// with its NUL), and the longer bound gcc's -Wformat-truncation takes for the volume text.
#define ACTIONS_DATA_MAX 160

// The order of docs/config.md "An action".
typedef enum {
	ACTION_NONE,
	ACTION_SCENE,
	ACTION_TOGGLE_MUTE,
	ACTION_TOGGLE_RECORD,
	ACTION_TOGGLE_STREAM,
	ACTION_TRANSITION,
} action_do_t;

typedef struct {
	uint8_t what;                // action_do_t
	char uuid[OBS_UUID_MAX + 1]; // `scene` and `toggle_mute`; empty for a knob push
} action_t;

typedef struct {
	char input[OBS_UUID_MAX + 1]; // empty: `input` is null
	int32_t step_mdb;             // `step_db` in thousandths of a dB. 0 when missing: a turn sends nothing
	action_t push;                // `toggle_mute` acts on `input`
} action_knob_t;

typedef struct {
	action_t keys[INPUT_KEYS];
	action_t buttons[INPUT_BUTTONS];
	action_knob_t knobs[INPUT_KNOBS];
} action_map_t;

// One knob's volume window. Belongs to actions.c.
typedef struct {
	bool window_open;
	uint32_t window_ends_ms;
	int32_t detents_waiting;
	bool sent;            // `sent_mdb` is the last volume sent
	int32_t sent_mdb;
	int32_t obs_mdb_then; // what OBS had said when it went
} action_volume_t;

typedef struct {
	action_map_t map;
	action_volume_t volume[INPUT_KNOBS];
} actions_t;

// The request: `type` is the requestType; `data` the requestData object, or "" for none. The
// sender adds the op 6 envelope and the requestId.
typedef struct {
	const char *type;
	char data[ACTIONS_DATA_MAX];
} action_request_t;

// Reads `keys`, `buttons` and `knobs` from a document that config_validate accepted. Still
// refuses, with false, what it cannot map: bytes that are not one JSON object, an unknown `do`,
// a list longer than its count, a UUID config refuses, and a `step_db` outside (0, 6]. Members it
// does not use are ignored; fields the document lacks read as `none` and null. After false, `map`
// holds nothing to use.
bool actions_parse(action_map_t *map, const uint8_t *doc, size_t len);

// Takes a map, with every knob window closed.
void actions_init(actions_t *actions, const action_map_t *map);

// The request one input event gives, if any, into `request`. A release, the clear combination, a
// `none`, a transition while studio mode is off, and a turn of a knob with no input or no volume
// known give none. `now_ms` may wrap.
bool actions_on_input(actions_t *actions, const obs_state_t *state, const input_event_t *event, uint32_t now_ms,
                      action_request_t *request);

// Call on every pass of the main loop. Closes each knob window that has run its 30 ms and gives
// one volume request for a window that holds more detents. Call again while it returns true.
bool actions_poll(actions_t *actions, const obs_state_t *state, uint32_t now_ms, action_request_t *request);
