// SPDX-License-Identifier: MIT
// actions: each mapped input gives its obs-websocket request, criterion 4c gives its exact log,
// and knob steps clamp to OBS's -100..26 dB. Every document first passes config_validate, and the
// OBS state is fed real obs-websocket events, so the map and the volumes are those the pad holds.
#include "actions.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "config.h"
#include "json.h"

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

#define LOG_MAX 256

static obs_state_t state;
static actions_t actions;

// One action per key, and the rest of valid_minimal.json after `knobs`.
static const char DOC_FORMAT[] =
	"{\"schema\":1,\"seq\":0,\"obs\":{\"url\":\"ws://10.0.0.2\",\"auth_mode\":\"none\"},\"wifi\":{\"ssid\":\"\"},"
	"\"keys\":[%s],\"buttons\":[%s],\"knobs\":[%s],"
	"\"main_display\":{\"widgets\":[]},\"strip_display\":{\"widgets\":[]},\"ui\":{\"brightness\":0}}";

static const char NO_KEYS[] =
	"{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},"
	"{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"}";
static const char NO_BUTTONS[] = "{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"}";
static const char NO_KNOB[] = "{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}}";

// Loads a document built from the three lists. It must be one the pad would store.
static void load(const char *keys, const char *buttons, const char *knobs) {
	char doc[CONFIG_MAX_BYTES];
	int n = snprintf(doc, sizeof doc, DOC_FORMAT, keys, buttons, knobs);
	if (n < 0 || (size_t)n >= sizeof doc) {
		fprintf(stderr, "document too long\n");
		exit(2);
	}
	config_result_t verdict = config_validate((const uint8_t *)doc, (size_t)n);
	if (verdict.verdict != CONFIG_VALID) {
		fprintf(stderr, "invalid test document at '%s': %s\n", verdict.path, doc);
		exit(2);
	}
	action_map_t map;
	CHECK(actions_parse(&map, (const uint8_t *)doc, (size_t)n));
	actions_init(&actions, &map);
	for (size_t knob = 0; knob < OBS_KNOBS; knob++) {
		CHECK(obs_state_watch(&state, knob, map.knobs[knob].input));
	}
}

static void feed(const char *message) {
	json_reader_t reader;
	obs_state_begin_message(&state);
	json_reader_init(&reader, obs_state_sink, &state);
	json_status_t status = json_feed(&reader, (const uint8_t *)message, strlen(message));
	obs_state_end_message(&state, status == JSON_DONE);
}

static void volume_event(const char *uuid, const char *db) {
	char message[256];
	snprintf(message, sizeof message,
	         "{\"op\":5,\"d\":{\"eventType\":\"InputVolumeChanged\",\"eventIntent\":8,"
	         "\"eventData\":{\"inputName\":\"x\",\"inputUuid\":\"%s\",\"inputVolumeMul\":0.1,\"inputVolumeDb\":%s}}}",
	         uuid, db);
	feed(message);
}

static void studio_event(bool on) {
	char message[160];
	snprintf(message, sizeof message,
	         "{\"op\":5,\"d\":{\"eventType\":\"StudioModeStateChanged\",\"eventIntent\":1024,"
	         "\"eventData\":{\"studioModeEnabled\":%s}}}",
	         on ? "true" : "false");
	feed(message);
}

// The request as fake_obs.py logs it for criterion 4c, `requestId` left out. "" for no request.
static const char *logged(bool sent, const action_request_t *request) {
	static char line[LOG_MAX];
	if (!sent) {
		return "";
	}
	if (request->data[0] == '\0') {
		snprintf(line, sizeof line, "{\"requestType\":\"%s\"}", request->type);
	} else {
		snprintf(line, sizeof line, "{\"requestType\":\"%s\",\"requestData\":%s}", request->type, request->data);
	}
	return line;
}

static const char *on_input(uint8_t source, uint8_t index, int8_t value, uint32_t now_ms) {
	input_event_t event = {source, index, value};
	action_request_t request;
	bool sent = actions_on_input(&actions, &state, &event, now_ms, &request);
	return logged(sent, &request);
}

static const char *poll_at(uint32_t now_ms) {
	action_request_t request;
	bool sent = actions_poll(&actions, &state, now_ms, &request);
	return logged(sent, &request);
}

static void expect(const char *got, const char *want, int line) {
	if (strcmp(got, want) != 0) {
		fprintf(stderr, "%s:%d: got '%s', want '%s'\n", __FILE__, line, got, want);
		failures++;
	}
}

#define EXPECT(got, want) expect((got), (want), __LINE__)

static void reset(void) {
	obs_state_init(&state);
}

// Criterion 4c: the old mapping first, then the write, then the exact log, and no `U_A`.
static void test_criterion_4c(void) {
	reset();
	load(NO_KEYS, "{\"do\":\"none\"},{\"do\":\"toggle_stream\"},{\"do\":\"none\"},{\"do\":\"none\"}",
	     "{\"input\":{\"uuid\":\"U_A\",\"label\":\"A\"},\"step_db\":1,\"push\":{\"do\":\"none\"}},"
	     "{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}},"
	     "{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}}");
	volume_event("U_A", "-20.0");
	EXPECT(on_input(INPUT_SOURCE_BUTTON, 1, 1, 0), "{\"requestType\":\"ToggleStream\"}");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, 1, 1),
	       "{\"requestType\":\"SetInputVolume\",\"requestData\":{\"inputUuid\":\"U_A\",\"inputVolumeDb\":-19}}");
	EXPECT(on_input(INPUT_SOURCE_KNOB_PUSH, 0, 1, 2), "");

	reset();
	load(NO_KEYS, "{\"do\":\"none\"},{\"do\":\"toggle_record\"},{\"do\":\"none\"},{\"do\":\"none\"}",
	     "{\"input\":{\"uuid\":\"U_B\",\"label\":\"B\"},\"step_db\":2,\"push\":{\"do\":\"toggle_mute\"}},"
	     "{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}},"
	     "{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}}");
	volume_event("U_B", "-20.0");
	EXPECT(on_input(INPUT_SOURCE_BUTTON, 1, 1, 100), "{\"requestType\":\"ToggleRecord\"}");
	EXPECT(on_input(INPUT_SOURCE_BUTTON, 1, 0, 110), "");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, 1, 120),
	       "{\"requestType\":\"SetInputVolume\",\"requestData\":{\"inputUuid\":\"U_B\",\"inputVolumeDb\":-18}}");
	EXPECT(on_input(INPUT_SOURCE_KNOB_PUSH, 0, 1, 130),
	       "{\"requestType\":\"ToggleInputMute\",\"requestData\":{\"inputUuid\":\"U_B\"}}");
	EXPECT(poll_at(200), "");
}

static void test_each_key_action(void) {
	reset();
	load("{\"do\":\"scene\",\"uuid\":\"S-1\",\"label\":\"Cam\"},"
	     "{\"do\":\"toggle_mute\",\"uuid\":\"I-1\",\"label\":\"Mic\"},"
	     "{\"do\":\"toggle_record\"},{\"do\":\"toggle_stream\"},{\"do\":\"transition\"},{\"do\":\"none\"},"
	     "{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"scene\",\"uuid\":\"a\\\"b\\\\c\",\"label\":\"\"}",
	     "{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"scene\",\"uuid\":\"S-2\",\"label\":\"\"}",
	     "{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"toggle_record\"}},"
	     "{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"toggle_mute\"}},"
	     "{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"scene\",\"uuid\":\"S-3\",\"label\":\"\"}}");
	EXPECT(on_input(INPUT_SOURCE_KEY, 0, 1, 0),
	       "{\"requestType\":\"SetCurrentProgramScene\",\"requestData\":{\"sceneUuid\":\"S-1\"}}");
	EXPECT(on_input(INPUT_SOURCE_KEY, 1, 1, 0),
	       "{\"requestType\":\"ToggleInputMute\",\"requestData\":{\"inputUuid\":\"I-1\"}}");
	EXPECT(on_input(INPUT_SOURCE_KEY, 2, 1, 0), "{\"requestType\":\"ToggleRecord\"}");
	EXPECT(on_input(INPUT_SOURCE_KEY, 3, 1, 0), "{\"requestType\":\"ToggleStream\"}");
	EXPECT(on_input(INPUT_SOURCE_KEY, 5, 1, 0), "");
	EXPECT(on_input(INPUT_SOURCE_KEY, 8, 1, 0),
	       "{\"requestType\":\"SetCurrentProgramScene\",\"requestData\":{\"sceneUuid\":\"a\\\"b\\\\c\"}}");
	EXPECT(on_input(INPUT_SOURCE_KEY, 0, 0, 0), "");
	EXPECT(on_input(INPUT_SOURCE_BUTTON, 3, 1, 0),
	       "{\"requestType\":\"SetCurrentProgramScene\",\"requestData\":{\"sceneUuid\":\"S-2\"}}");
	EXPECT(on_input(INPUT_SOURCE_KNOB_PUSH, 0, 1, 0), "{\"requestType\":\"ToggleRecord\"}");
	// A knob with no input has nothing to mute or turn.
	EXPECT(on_input(INPUT_SOURCE_KNOB_PUSH, 1, 1, 0), "");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 1, 1, 0), "");
	EXPECT(on_input(INPUT_SOURCE_KNOB_PUSH, 2, 1, 0),
	       "{\"requestType\":\"SetCurrentProgramScene\",\"requestData\":{\"sceneUuid\":\"S-3\"}}");
	EXPECT(on_input(INPUT_SOURCE_CLEAR, 0, 1, 0), "");
	EXPECT(on_input(INPUT_SOURCE_KEY, INPUT_KEYS, 1, 0), "");
	EXPECT(on_input(INPUT_SOURCE_BUTTON, INPUT_BUTTONS, 1, 0), "");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, INPUT_KNOBS, 1, 0), "");
}

// TriggerStudioModeTransition fails while studio mode is off, so the pad sends nothing then.
static void test_transition_needs_studio_mode(void) {
	reset();
	load("{\"do\":\"transition\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},"
	     "{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"}",
	     NO_BUTTONS, "{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}},"
	     "{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}},"
	     "{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}}");
	EXPECT(on_input(INPUT_SOURCE_KEY, 0, 1, 0), "");
	studio_event(true);
	EXPECT(on_input(INPUT_SOURCE_KEY, 0, 1, 0), "{\"requestType\":\"TriggerStudioModeTransition\"}");
	studio_event(false);
	EXPECT(on_input(INPUT_SOURCE_KEY, 0, 1, 0), "");
}

static void load_knob(const char *uuid, const char *step_db) {
	char knobs[256];
	snprintf(knobs, sizeof knobs,
	         "{\"input\":{\"uuid\":\"%s\",\"label\":\"\"},\"step_db\":%s,\"push\":{\"do\":\"none\"}},%s,%s", uuid,
	         step_db, NO_KNOB, NO_KNOB);
	load(NO_KEYS, NO_BUTTONS, knobs);
}

static const char *volume_request(const char *db) {
	static char line[LOG_MAX];
	snprintf(line, sizeof line,
	         "{\"requestType\":\"SetInputVolume\",\"requestData\":{\"inputUuid\":\"K\",\"inputVolumeDb\":%s}}", db);
	return line;
}

static void test_knob_steps_clamp(void) {
	reset();
	load_knob("K", "2");
	volume_event("K", "25.0");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, 1, 0), volume_request("26"));

	reset();
	load_knob("K", "1");
	volume_event("K", "-99.5");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, -1, 0), volume_request("-100"));

	// The summed detents of one window clamp too.
	reset();
	load_knob("K", "6");
	volume_event("K", "20");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, 3, 0), volume_request("26"));
	EXPECT(poll_at(30), volume_request("26"));
}

// Port of host volume.rs: the first detent goes at once, the rest of a 30 ms window as one sum.
static void test_knob_window(void) {
	reset();
	load_knob("K", "2");
	volume_event("K", "-20");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, 3, 1000), volume_request("-18"));
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, 1, 1010), "");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, -1, 1015), "");
	// OBS echoes the first step inside the window. The sum still builds on what the pad sent.
	volume_event("K", "-18");
	EXPECT(poll_at(1029), "");
	EXPECT(poll_at(1030), volume_request("-14"));
	EXPECT(poll_at(1100), "");
}

// Until OBS reports a new volume, the next step builds on the last one sent, not on the old one.
static void test_knob_builds_on_sent_until_obs_reports(void) {
	reset();
	load_knob("K", "2");
	volume_event("K", "-20");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, 1, 0), volume_request("-18"));
	EXPECT(poll_at(30), "");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, 1, 40), volume_request("-16"));
	EXPECT(poll_at(70), "");
	// Another client set it: OBS's word wins once it comes.
	volume_event("K", "-10");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, -1, 200), volume_request("-12"));
}

static void test_knob_needs_a_known_volume(void) {
	reset();
	load_knob("K", "1");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, 1, 0), "");
	volume_event("OTHER", "-5");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, 1, 0), "");
}

static void test_fractional_steps_and_escaped_uuid(void) {
	reset();
	load_knob("K", "0.5");
	volume_event("K", "-20");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, -1, 0), volume_request("-20.5"));
	reset();
	load_knob("K", "1.25");
	volume_event("K", "0.5");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, -1, 0), volume_request("-0.75"));

	reset();
	load_knob("q\\\"u", "1");
	volume_event("q\\\"u", "0");
	EXPECT(on_input(INPUT_SOURCE_KNOB_TURN, 0, 1, 0),
	       "{\"requestType\":\"SetInputVolume\",\"requestData\":{\"inputUuid\":\"q\\\"u\",\"inputVolumeDb\":1}}");
}

static void test_parse_refuses_what_it_cannot_map(void) {
	action_map_t map;
	static const char *const bad[] = {
		"[]",
		"{\"keys\":[{\"do\":\"page\"}]}",
		"{\"buttons\":[{},{},{},{},{\"do\":\"none\"}]}",
		"{\"knobs\":[{\"step_db\":0}]}",
		"{\"knobs\":[{\"step_db\":7}]}",
		"{\"knobs\":[{\"input\":{\"uuid\":\"\"}}]}",
		"{\"keys\":[{\"do\":\"scene\",\"uuid\":\"0123456789012345678901234567890123456\"}]}",
		"{\"keys\":[{\"do\":\"scene\",\"uuid\":\"a b\"}]}",
	};
	for (size_t i = 0; i < sizeof bad / sizeof bad[0]; i++) {
		CHECK(!actions_parse(&map, (const uint8_t *)bad[i], strlen(bad[i])));
	}
	static const char later_wins[] =
		"{\"knobs\":[{\"input\":{\"uuid\":\"A\"},\"input\":null,\"step_db\":1,\"push\":{\"do\":\"toggle_record\"},"
		"\"push\":{\"do\":\"none\"}}],\"keys\":[{\"do\":\"toggle_stream\"}],\"keys\":[{\"do\":\"none\"}]}";
	CHECK(actions_parse(&map, (const uint8_t *)later_wins, strlen(later_wins)));
	CHECK(map.knobs[0].input[0] == '\0');
	CHECK(map.knobs[0].push.what == ACTION_NONE);
	CHECK(map.keys[0].what == ACTION_NONE);
}

int main(void) {
	test_criterion_4c();
	test_each_key_action();
	test_transition_needs_studio_mode();
	test_knob_steps_clamp();
	test_knob_window();
	test_knob_builds_on_sent_until_obs_reports();
	test_knob_needs_a_known_volume();
	test_fractional_steps_and_escaped_uuid();
	test_parse_refuses_what_it_cannot_map();
	if (failures > 0) {
		fprintf(stderr, "test_actions: %d failures\n", failures);
		return 1;
	}
	printf("test_actions: ok\n");
	return 0;
}
