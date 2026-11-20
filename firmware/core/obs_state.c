// SPDX-License-Identifier: MIT
#include "obs_state.h"

#include "obs.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { OP_EVENT = 5 };
enum { ID_NONE, ID_MATCH, ID_OTHER };

// The reads, in the order a full read sends them (R05 section 5, note 5). The pending bit of a
// read is 1 << its number.
enum {
	READ_SCENES,
	READ_STUDIO,
	READ_INPUTS,
	READ_STREAM,
	READ_RECORD,
	READ_MUTE,                           // one per knob
	READ_VOLUME = READ_MUTE + OBS_KNOBS, // one per knob
	READ_COUNT = READ_VOLUME + OBS_KNOBS,
	NO_READ = -1,
};

static const char *const READ_TYPES[READ_COUNT] = {
    "GetSceneList",    "GetStudioModeEnabled", "GetInputList", "GetStreamStatus",
    "GetRecordStatus", "GetInputMute",         "GetInputMute", "GetInputMute",
    "GetInputVolume",  "GetInputVolume",       "GetInputVolume",
};

#define READ_BIT(read) ((uint16_t)(1u << (read)))
#define KNOB_READS(knob) ((uint16_t)(READ_BIT(READ_MUTE + (knob)) | READ_BIT(READ_VOLUME + (knob))))
#define METER_EVENTS 65536 // InputVolumeMeters (R05 section 4)
// obs_source_info output_flags: OBS_SOURCE_AUDIO (R05 section 5).
#define AUDIO_CAP 2u
// Each byte may need a backslash before it.
#define ESCAPED_UUID_MAX (2 * OBS_UUID_MAX)

// A field of the data object of a reply or of an event.
#define DATA_IS(event, key)                                                                      \
	(json_path_is(event, "d.responseData." key) || json_path_is(event, "d.eventData." key))

// One list in a reply that the pad keeps: the paths of its parts and the read that asks for it.
typedef struct {
	const char *list;
	const char *element;
	const char *uuid;
	const char *name;
	int8_t read;
	bool audio_only;
} list_paths_t;

static const list_paths_t SCENE_LIST = {
    "d.responseData.scenes",
    "d.responseData.scenes[]",
    "d.responseData.scenes[].sceneUuid",
    "d.responseData.scenes[].sceneName",
    READ_SCENES,
    false,
};

static const list_paths_t INPUT_LIST = {
    "d.responseData.inputs",
    "d.responseData.inputs[]",
    "d.responseData.inputs[].inputUuid",
    "d.responseData.inputs[].inputName",
    READ_INPUTS,
    true,
};

typedef struct {
	obs_item_t *items;
	uint16_t *count;
	bool *capped;
	uint16_t cap;
} table_t;

static table_t table_of(obs_state_t *state, int8_t read) {
	if (read == READ_SCENES) {
		return (table_t){state->scenes, &state->scene_count, &state->scenes_capped,
		                 OBS_SCENES_MAX};
	}
	return (table_t){state->inputs, &state->input_count, &state->inputs_capped, OBS_INPUTS_MAX};
}

static bool uuid_is_valid(const char *text, size_t len) {
	if (len == 0 || len > OBS_UUID_MAX) {
		return false;
	}
	for (size_t i = 0; i < len; i++) {
		if (text[i] < 0x21 || text[i] > 0x7E) {
			return false;
		}
	}
	return true;
}

// The UUID, or "" for one config would refuse.
static void copy_uuid(char out[OBS_UUID_MAX + 1], const json_event_t *event) {
	bool valid = event->kind == JSON_STRING && uuid_is_valid(event->text, event->len);
	size_t len = valid ? event->len : 0;
	memcpy(out, event->text, len);
	out[len] = '\0';
}

// The name cut to OBS_NAME_MAX bytes, never inside a character. A NUL byte ends it.
static void copy_name(char out[OBS_NAME_MAX + 1], const json_event_t *event) {
	size_t len = 0;
	if (event->kind == JSON_STRING) {
		const char *nul = memchr(event->text, '\0', event->len);
		len = nul == NULL ? event->len : (size_t)(nul - event->text);
	}
	if (len > OBS_NAME_MAX) {
		len = OBS_NAME_MAX;
		while (len > 0 && ((uint8_t)event->text[len] & 0xC0) == 0x80) {
			len--;
		}
	}
	memcpy(out, event->text, len);
	out[len] = '\0';
}

static int8_t flag_of(const json_event_t *event) {
	if (event->kind == JSON_TRUE) {
		return 1;
	}
	return event->kind == JSON_FALSE ? 0 : -1;
}

static void read_request_id(obs_state_t *state, const json_event_t *event) {
	char expected[16];
	snprintf(expected, sizeof expected, "r%" PRIu32, state->in_flight_id);
	bool match = state->in_flight != NO_READ && event->kind == JSON_STRING &&
	             event->len == strlen(expected) && memcmp(event->text, expected, event->len) == 0;
	state->reply.id = match ? ID_MATCH : ID_OTHER;
}

// The members around the data: op, requestId, requestStatus.result and eventType.
static bool read_envelope(obs_state_t *state, const json_event_t *event) {
	obs_reply_t *reply = &state->reply;
	if (json_path_is(event, "op")) {
		reply->op = event->kind == JSON_NUMBER ? (int32_t)strtol(event->text, NULL, 10) : -1;
	} else if (json_path_is(event, "d.requestId")) {
		read_request_id(state, event);
	} else if (json_path_is(event, "d.requestStatus.result")) {
		reply->result = event->kind == JSON_TRUE;
	} else if (json_path_is(event, "d.eventType")) {
		bool fits = event->kind == JSON_STRING && event->len <= OBS_EVENT_TYPE_MAX;
		snprintf(reply->event_type, sizeof reply->event_type, "%s", fits ? event->text : "");
	} else {
		return false;
	}
	return true;
}

// Whether a list in this message may go into its table: only the reply to the read in flight.
// A requestId not seen yet does not stop it: OBS sorts keys, so the id comes first anyway.
static bool list_is_wanted(const obs_state_t *state, const list_paths_t *list) {
	return state->in_flight == list->read && state->reply.id != ID_OTHER;
}

static void append_element(obs_state_t *state, const list_paths_t *list) {
	const obs_element_t *element = &state->reply.element;
	if (element->uuid[0] == '\0' || (list->audio_only && !element->audio)) {
		return;
	}
	table_t table = table_of(state, list->read);
	if (*table.count == table.cap) {
		*table.capped = true;
		return;
	}
	obs_item_t *item = &table.items[(*table.count)++];
	memcpy(item->uuid, element->uuid, sizeof item->uuid);
	memcpy(item->name, element->name, sizeof item->name);
}

static bool read_list(obs_state_t *state, const json_event_t *event, const list_paths_t *list) {
	obs_element_t *element = &state->reply.element;
	if (json_path_is(event, list->list) && event->kind == JSON_LIST_BEGIN) {
		if (list_is_wanted(state, list)) {
			table_t table = table_of(state, list->read);
			*table.count = 0;
			*table.capped = false;
			state->reply.touched_list = list->read;
		}
	} else if (json_path_is(event, list->element)) {
		if (event->kind == JSON_OBJECT_BEGIN) {
			*element = (obs_element_t){0};
		} else if (event->kind == JSON_OBJECT_END && list_is_wanted(state, list)) {
			append_element(state, list);
		}
	} else if (json_path_is(event, list->uuid)) {
		copy_uuid(element->uuid, event);
	} else if (json_path_is(event, list->name)) {
		copy_name(element->name, event);
	} else {
		return false;
	}
	return true;
}

static void read_input_caps(obs_reply_t *reply, const json_event_t *event) {
	unsigned long caps = event->kind == JSON_NUMBER ? strtoul(event->text, NULL, 10) : 0;
	reply->element.audio = (caps & AUDIO_CAP) != 0;
}

static void end_meter(obs_state_t *state) {
	const obs_element_t *element = &state->reply.element;
	for (size_t knob = 0; knob < OBS_KNOBS; knob++) {
		if (element->uuid[0] != '\0' && strcmp(state->knobs[knob].uuid, element->uuid) == 0) {
			state->reply.knob_peaks[knob] = element->peak;
		}
	}
}

// InputVolumeMeters: per input, each channel is [magnitude, peak, input peak]; the loudest
// channel's peak counts (R05 section 7).
static bool read_meter(obs_state_t *state, const json_event_t *event) {
	obs_element_t *element = &state->reply.element;
	if (json_path_is(event, "d.eventData.inputs[]")) {
		if (event->kind == JSON_OBJECT_BEGIN) {
			*element = (obs_element_t){0};
		} else if (event->kind == JSON_OBJECT_END) {
			end_meter(state);
		}
	} else if (json_path_is(event, "d.eventData.inputs[].inputUuid")) {
		copy_uuid(element->uuid, event);
	} else if (json_path_is(event, "d.eventData.inputs[].inputLevelsMul[][]")) {
		float level = event->kind == JSON_NUMBER ? strtof(event->text, NULL) : 0.0f;
		if (event->path[6].index == 1 && level > element->peak) {
			element->peak = level;
		}
	} else {
		return false;
	}
	return true;
}

static void read_data_field(obs_reply_t *reply, const json_event_t *event) {
	if (DATA_IS(event, "sceneUuid") || DATA_IS(event, "inputUuid")) {
		copy_uuid(reply->uuid, event);
	} else if (DATA_IS(event, "sceneName") || DATA_IS(event, "inputName")) {
		copy_name(reply->name, event);
	} else if (DATA_IS(event, "currentProgramSceneUuid")) {
		copy_uuid(reply->program, event);
	} else if (DATA_IS(event, "currentPreviewSceneUuid")) {
		copy_uuid(reply->preview, event);
	} else if (DATA_IS(event, "studioModeEnabled")) {
		reply->studio = flag_of(event);
	} else if (DATA_IS(event, "inputMuted")) {
		reply->muted = flag_of(event);
	} else if (DATA_IS(event, "outputActive")) {
		reply->active = flag_of(event);
	} else if (DATA_IS(event, "outputPaused")) {
		reply->paused = event->kind == JSON_TRUE;
	} else if (DATA_IS(event, "outputReconnecting")) {
		reply->reconnecting = event->kind == JSON_TRUE;
	} else if (DATA_IS(event, "outputState")) {
		reply->on = event->kind == JSON_STRING ? obs_output_is_on(event->text) : -1;
	} else if (DATA_IS(event, "inputVolumeDb") && event->kind == JSON_NUMBER) {
		reply->volume_db = strtof(event->text, NULL);
		reply->has_volume = true;
	}
}

void obs_state_sink(void *context, const json_event_t *event) {
	obs_state_t *state = context;
	if (read_envelope(state, event) || read_list(state, event, &SCENE_LIST) ||
	    read_list(state, event, &INPUT_LIST) || read_meter(state, event)) {
		return;
	}
	if (json_path_is(event, "d.responseData.inputs[].inputKindCaps")) {
		read_input_caps(&state->reply, event);
	} else {
		read_data_field(&state->reply, event);
	}
}

static void apply_knob_reply(obs_state_t *state, int8_t read) {
	const obs_reply_t *reply = &state->reply;
	if (read < READ_VOLUME) {
		obs_knob_t *knob = &state->knobs[read - READ_MUTE];
		if (reply->muted >= 0) {
			knob->muted = reply->muted;
			knob->mute_known = true;
		}
	} else if (reply->has_volume) {
		obs_knob_t *knob = &state->knobs[read - READ_VOLUME];
		knob->volume_db = reply->volume_db;
		knob->volume_known = true;
	}
}

static void apply_reply(obs_state_t *state, int8_t read) {
	const obs_reply_t *reply = &state->reply;
	switch (read) {
	case READ_SCENES:
		memcpy(state->program, reply->program, sizeof state->program);
		memcpy(state->preview, reply->preview, sizeof state->preview);
		break;
	case READ_STUDIO:
		state->studio_mode = reply->studio == 1;
		break;
	case READ_INPUTS:
		break; // the list went into its table while it streamed by
	case READ_STREAM:
		state->streaming = reply->active == 1 && !reply->reconnecting;
		break;
	case READ_RECORD:
		state->recording = reply->active == 1 && !reply->paused;
		break;
	default:
		apply_knob_reply(state, read);
		break;
	}
}

// Every read but those of a knob with no input.
static uint16_t full_read(const obs_state_t *state) {
	uint16_t reads = READ_BIT(READ_SCENES) | READ_BIT(READ_STUDIO) | READ_BIT(READ_INPUTS) |
	                 READ_BIT(READ_STREAM) | READ_BIT(READ_RECORD);
	for (size_t knob = 0; knob < OBS_KNOBS; knob++) {
		if (state->knobs[knob].uuid[0] != '\0') {
			reads |= KNOB_READS(knob);
		}
	}
	return reads;
}

static obs_item_t *find_item(obs_item_t *items, uint16_t count, const char *uuid) {
	for (uint16_t i = 0; uuid[0] != '\0' && i < count; i++) {
		if (strcmp(items[i].uuid, uuid) == 0) {
			return &items[i];
		}
	}
	return NULL;
}

static void on_program(obs_state_t *state) {
	memcpy(state->program, state->reply.uuid, sizeof state->program);
}

static void on_preview(obs_state_t *state) {
	memcpy(state->preview, state->reply.uuid, sizeof state->preview);
}

static void rename_item(obs_item_t *item, const char *name) {
	if (item != NULL) {
		memcpy(item->name, name, sizeof item->name);
	}
}

static void on_scene_renamed(obs_state_t *state) {
	rename_item(find_item(state->scenes, state->scene_count, state->reply.uuid), state->reply.name);
}

static void on_input_renamed(obs_state_t *state) {
	rename_item(find_item(state->inputs, state->input_count, state->reply.uuid), state->reply.name);
}

static void on_scene_list(obs_state_t *state) {
	state->pending |= READ_BIT(READ_SCENES);
}

static void on_input_list(obs_state_t *state) {
	state->pending |= READ_BIT(READ_INPUTS);
}

// OBS has no preview while studio mode is off.
static void on_studio(obs_state_t *state) {
	if (state->reply.studio < 0) {
		return;
	}
	state->studio_mode = state->reply.studio;
	if (!state->studio_mode) {
		state->preview[0] = '\0';
	}
}

static obs_knob_t *knob_of_event(obs_state_t *state) {
	for (size_t knob = 0; knob < OBS_KNOBS; knob++) {
		const char *uuid = state->reply.uuid;
		if (uuid[0] != '\0' && strcmp(state->knobs[knob].uuid, uuid) == 0) {
			return &state->knobs[knob];
		}
	}
	return NULL;
}

static void on_mute(obs_state_t *state) {
	obs_knob_t *knob = knob_of_event(state);
	if (knob != NULL && state->reply.muted >= 0) {
		knob->muted = state->reply.muted;
		knob->mute_known = true;
	}
}

static void on_volume(obs_state_t *state) {
	obs_knob_t *knob = knob_of_event(state);
	if (knob != NULL && state->reply.has_volume) {
		knob->volume_db = state->reply.volume_db;
		knob->volume_known = true;
	}
}

static void on_stream(obs_state_t *state) {
	if (state->reply.on >= 0) {
		state->streaming = state->reply.on;
	}
}

static void on_record(obs_state_t *state) {
	if (state->reply.on >= 0) {
		state->recording = state->reply.on;
	}
}

// Requests during a collection switch are undefined behaviour in OBS (R05 section 8, item 3).
static void on_collection_changing(obs_state_t *state) {
	state->collection_changing = true;
}

static void on_collection_changed(obs_state_t *state) {
	state->collection_changing = false;
	state->pending = full_read(state);
}

// A knob input missing from the event has stopped: its meter falls to zero.
static void on_meters(obs_state_t *state) {
	for (size_t knob = 0; knob < OBS_KNOBS; knob++) {
		state->knobs[knob].meter_peak = state->reply.knob_peaks[knob];
	}
}

typedef struct {
	const char *type;
	void (*apply)(obs_state_t *state);
} event_handler_t;

static const event_handler_t EVENT_HANDLERS[] = {
    {"CurrentProgramSceneChanged", on_program},
    {"CurrentPreviewSceneChanged", on_preview},
    {"SceneNameChanged", on_scene_renamed},
    {"SceneListChanged", on_scene_list},
    {"SceneCreated", on_scene_list},
    {"SceneRemoved", on_scene_list},
    {"StudioModeStateChanged", on_studio},
    {"InputCreated", on_input_list},
    {"InputRemoved", on_input_list},
    {"InputNameChanged", on_input_renamed},
    {"InputMuteStateChanged", on_mute},
    {"InputVolumeChanged", on_volume},
    {"StreamStateChanged", on_stream},
    {"RecordStateChanged", on_record},
    {"CurrentSceneCollectionChanging", on_collection_changing},
    {"CurrentSceneCollectionChanged", on_collection_changed},
    {"InputVolumeMeters", on_meters},
};

static void apply_event(obs_state_t *state) {
	for (size_t i = 0; i < sizeof EVENT_HANDLERS / sizeof EVENT_HANDLERS[0]; i++) {
		if (strcmp(EVENT_HANDLERS[i].type, state->reply.event_type) == 0) {
			EVENT_HANDLERS[i].apply(state);
			return;
		}
	}
}

// A cut reply is no answer: the read goes out again. A refused one is dropped.
static void finish_request(obs_state_t *state, bool whole) {
	int8_t read = state->in_flight;
	state->in_flight = NO_READ;
	if (!whole) {
		state->pending |= READ_BIT(read);
	} else if (state->reply.result) {
		apply_reply(state, read);
	}
}

void obs_state_begin_message(obs_state_t *state) {
	state->reply = (obs_reply_t){
	    .op = -1,
	    .id = ID_NONE,
	    .touched_list = NO_READ,
	    .studio = -1,
	    .muted = -1,
	    .active = -1,
	    .on = -1,
	};
}

void obs_state_end_message(obs_state_t *state, bool whole) {
	const obs_reply_t *reply = &state->reply;
	bool answered = whole && reply->id == ID_MATCH && reply->result;
	if (reply->touched_list != NO_READ && !answered) {
		state->pending |= READ_BIT(reply->touched_list); // the table holds a cut or stale list
	}
	if (reply->id == ID_MATCH) {
		finish_request(state, whole);
	} else if (whole && reply->op == OP_EVENT) {
		apply_event(state);
	}
}

void obs_state_init(obs_state_t *state) {
	*state = (obs_state_t){.in_flight = NO_READ, .next_id = 1};
	obs_state_begin_message(state);
}

void obs_state_begin(obs_state_t *state) {
	state->pending = full_read(state);
	state->in_flight = NO_READ;
	state->collection_changing = false;
	state->meters_subscribed = false;
}

static size_t write_reidentify(obs_state_t *state, char out[OBS_MESSAGE_MAX]) {
	state->meters_subscribed = state->meters_wanted;
	long events = OBS_EVENT_SUBSCRIPTIONS | (state->meters_wanted ? METER_EVENTS : 0);
	return (size_t)snprintf(out, OBS_MESSAGE_MAX, "{\"op\":3,\"d\":{\"eventSubscriptions\":%ld}}",
	                        events);
}

static void expire_request(obs_state_t *state, uint32_t now_ms) {
	// Unsigned difference: the timeout ends on time when the millisecond clock wraps.
	if (state->in_flight != NO_READ && now_ms - state->sent_ms >= OBS_REQUEST_TIMEOUT_MS) {
		state->pending |= READ_BIT(state->in_flight);
		state->in_flight = NO_READ;
	}
}

static const char *knob_uuid_of(const obs_state_t *state, int8_t read) {
	if (read >= READ_VOLUME) {
		return state->knobs[read - READ_VOLUME].uuid;
	}
	return read >= READ_MUTE ? state->knobs[read - READ_MUTE].uuid : NULL;
}

static int8_t take_next_read(obs_state_t *state) {
	for (int8_t read = 0; read < READ_COUNT; read++) {
		if (state->pending & READ_BIT(read)) {
			state->pending &= (uint16_t)~READ_BIT(read);
			return read;
		}
	}
	return NO_READ;
}

// A UUID holds 0x21-0x7E only, so '"' and '\' are all that JSON needs escaped.
static void escape_uuid(const char *uuid, char out[ESCAPED_UUID_MAX + 1]) {
	for (; *uuid != '\0'; uuid++) {
		if (*uuid == '"' || *uuid == '\\') {
			*out++ = '\\';
		}
		*out++ = *uuid;
	}
	*out = '\0';
}

static size_t write_request(obs_state_t *state, int8_t read, char out[OBS_MESSAGE_MAX],
                            uint32_t now_ms) {
	state->in_flight = read;
	state->in_flight_id = state->next_id++;
	state->sent_ms = now_ms;
	const char *uuid = knob_uuid_of(state, read);
	int len;
	if (uuid == NULL) {
		len = snprintf(out, OBS_MESSAGE_MAX,
		               "{\"op\":6,\"d\":{\"requestType\":\"%s\",\"requestId\":\"r%" PRIu32 "\"}}",
		               READ_TYPES[read], state->in_flight_id);
	} else {
		char escaped[ESCAPED_UUID_MAX + 1];
		escape_uuid(uuid, escaped);
		len = snprintf(out, OBS_MESSAGE_MAX,
		               "{\"op\":6,\"d\":{\"requestType\":\"%s\",\"requestId\":\"r%" PRIu32 "\","
		               "\"requestData\":{\"inputUuid\":\"%s\"}}}",
		               READ_TYPES[read], state->in_flight_id, escaped);
	}
	return (size_t)len;
}

size_t obs_state_next_message(obs_state_t *state, char out[OBS_MESSAGE_MAX], uint32_t now_ms) {
	if (state->collection_changing) {
		return 0;
	}
	if (state->meters_wanted != state->meters_subscribed) {
		return write_reidentify(state, out);
	}
	expire_request(state, now_ms);
	if (state->in_flight != NO_READ) {
		return 0;
	}
	int8_t read = take_next_read(state);
	return read == NO_READ ? 0 : write_request(state, read, out, now_ms);
}

bool obs_state_watch(obs_state_t *state, size_t knob, const char *uuid) {
	size_t len = uuid == NULL ? 0 : strlen(uuid);
	if (knob >= OBS_KNOBS || (len > 0 && !uuid_is_valid(uuid, len))) {
		return false;
	}
	obs_knob_t *slot = &state->knobs[knob];
	*slot = (obs_knob_t){0};
	state->pending &= (uint16_t)~KNOB_READS(knob);
	if (len > 0) {
		memcpy(slot->uuid, uuid, len);
		state->pending |= KNOB_READS(knob);
	}
	return true;
}

void obs_state_show_meters(obs_state_t *state, bool shown) {
	state->meters_wanted = shown;
}

bool obs_state_is_current(const obs_state_t *state) {
	return state->pending == 0 && state->in_flight == NO_READ;
}

bool obs_output_is_on(const char *output_state) {
	return strcmp(output_state, "OBS_WEBSOCKET_OUTPUT_STARTED") == 0 ||
	       strcmp(output_state, "OBS_WEBSOCKET_OUTPUT_RESUMED") == 0 ||
	       strcmp(output_state, "OBS_WEBSOCKET_OUTPUT_RECONNECTED") == 0;
}
