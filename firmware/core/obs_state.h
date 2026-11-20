// SPDX-License-Identifier: MIT
// The OBS state the pad shows and acts on, kept from obs-websocket 5 replies and events (spec
// 8.3, R05 sections 5 to 8): scenes, program and preview, studio mode, audio inputs, mute and
// volume of the knob inputs, stream and record. One request in flight, matched by requestId, so
// a late reply to an older request is dropped. A full re-read after each Identified. Meters
// (65536) only while one shows, through Reidentify. Pure C, no SDK headers, no heap: 500 scenes
// cost the same RAM as 3.
#pragma once

#include "json.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// A UUID as config holds one (docs/config.md): 1..36 bytes, each 0x21-0x7E.
#define OBS_UUID_MAX 36
// Names are cut to the config label cap (docs/config.md, R13), at a whole UTF-8 character.
#define OBS_NAME_MAX 48
// Past these the list keeps its first items and sets its `capped` flag.
#define OBS_SCENES_MAX 512
#define OBS_INPUTS_MAX 256
// The knob inputs: the only ones whose mute and volume the pad reads (R05 section 5, note 1).
#define OBS_KNOBS 3
// The longest message obs_state_next_message writes: a request that names a 36-byte UUID with
// every byte escaped fits.
#define OBS_MESSAGE_MAX 192
// A reply that has not come by then frees the request slot, and the read goes out again.
#define OBS_REQUEST_TIMEOUT_MS 5000u
#define OBS_EVENT_TYPE_MAX 40

typedef struct {
	char uuid[OBS_UUID_MAX + 1];
	char name[OBS_NAME_MAX + 1];
} obs_item_t;

typedef struct {
	char uuid[OBS_UUID_MAX + 1]; // empty: no input on this knob
	bool mute_known;
	bool volume_known;
	bool muted;
	float volume_db;  // -100 to 26 (R05 section 5)
	float meter_peak; // linear, the loudest channel's peak; 0 while OBS sends no meter for it
} obs_knob_t;

// One list element while it is read. Belongs to obs_state.c.
typedef struct {
	char uuid[OBS_UUID_MAX + 1];
	char name[OBS_NAME_MAX + 1];
	bool audio;
	float peak;
} obs_element_t;

// The fields of one received message that the pad reads. Keys come in any order, so they are
// caught first and acted on at the end (R05 section 6). Belongs to obs_state.c.
typedef struct {
	int32_t op;
	uint8_t id;  // enum in obs_state.c: no requestId yet, the one in flight, another
	bool result; // requestStatus.result
	int8_t touched_list; // the read whose table this message wrote, or -1
	char event_type[OBS_EVENT_TYPE_MAX + 1];
	char uuid[OBS_UUID_MAX + 1];
	char name[OBS_NAME_MAX + 1];
	char program[OBS_UUID_MAX + 1];
	char preview[OBS_UUID_MAX + 1];
	int8_t studio; // -1 until read, then 0 or 1, as are the three below
	int8_t muted;
	int8_t active;
	int8_t on; // outputState is one of the on states
	bool paused;
	bool reconnecting;
	bool has_volume;
	float volume_db;
	obs_element_t element;
	float knob_peaks[OBS_KNOBS];
} obs_reply_t;

// Read the fields above `pending`. The rest belongs to obs_state.c.
typedef struct {
	obs_item_t scenes[OBS_SCENES_MAX]; // in the order of the GetSceneList reply
	uint16_t scene_count;
	bool scenes_capped;
	obs_item_t inputs[OBS_INPUTS_MAX]; // inputs with audio, in the order of GetInputList
	uint16_t input_count;
	bool inputs_capped;
	char program[OBS_UUID_MAX + 1];
	char preview[OBS_UUID_MAX + 1]; // empty while studio mode is off
	bool studio_mode;
	bool streaming; // stream on and not reconnecting
	bool recording; // record on and not paused
	obs_knob_t knobs[OBS_KNOBS];

	uint16_t pending; // bit n: read n waits to go out
	int8_t in_flight; // the read in flight, or -1
	uint32_t in_flight_id;
	uint32_t sent_ms;
	uint32_t next_id;
	bool collection_changing;
	bool meters_wanted;
	bool meters_subscribed;
	obs_reply_t reply;
} obs_state_t;

// Empty, with no read queued.
void obs_state_init(obs_state_t *state);

// Call on each Identified that opens a session: queues the full read and forgets the request in
// flight. Identify subscribes 1118, so meters, when wanted, go on again by Reidentify.
void obs_state_begin(obs_state_t *state);

// The next message to send, or 0 when there is none: a Reidentify when the meter wish changed,
// else the next queued read once no request is in flight. Writes it, NUL-terminated, into
// `out` and returns its length. `now_ms` may wrap.
size_t obs_state_next_message(obs_state_t *state, char out[OBS_MESSAGE_MAX], uint32_t now_ms);

// Starts one received message. Then feed its bytes to a json_reader_t with obs_state_sink and
// `state`, and call obs_state_end_message with whether the reader ended at JSON_DONE.
void obs_state_begin_message(obs_state_t *state);
void obs_state_sink(void *state, const json_event_t *event);
void obs_state_end_message(obs_state_t *state, bool whole);

// Puts the input `uuid` on knob `knob` and queues its mute and volume reads. NULL or "" takes
// the input off. False, and nothing changes, for a knob past OBS_KNOBS or a UUID config refuses.
bool obs_state_watch(obs_state_t *state, size_t knob, const char *uuid);

// Whether a meter shows. The subscription follows on the next obs_state_next_message.
void obs_state_show_meters(obs_state_t *state, bool shown);

// True when no read waits and none is in flight: the state is as OBS last told it.
bool obs_state_is_current(const obs_state_t *state);

// The outputState values of an output that runs: STARTED, RESUMED and RECONNECTED, as
// obs-websocket sets outputActive (R05 section 5, note 3). Paused and reconnecting are off.
bool obs_output_is_on(const char *output_state);
