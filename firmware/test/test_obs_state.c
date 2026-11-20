// SPDX-License-Identifier: MIT
// obs_state: the full read, one request in flight, late replies, events, meters, a 500-scene
// reply, then the whole client over a POSIX stream against tools/fake_obs.py.
#define _POSIX_C_SOURCE 200809L
#include "obs.h"
#include "obs_state.h"
#include "posix_stream.h"

#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

#define FIELD_MAX 64
// 500 scenes with 64-byte names: about 75 kB (R05 section 5).
#define BIG_REPLY_CAP (96 * 1024)
#define LONG_NAME "Scene ---------------------------------------------------------- %03u"

static obs_state_t state;
static char message[OBS_MESSAGE_MAX];
static char big_reply[BIG_REPLY_CAP];

// Feeds one whole message in pieces of `piece` bytes.
static void feed_in_pieces(const char *text, size_t piece) {
	json_reader_t reader;
	obs_state_begin_message(&state);
	json_reader_init(&reader, obs_state_sink, &state);
	json_status_t status = JSON_MORE;
	size_t len = strlen(text);
	for (size_t at = 0; at < len; at += piece) {
		size_t take = len - at < piece ? len - at : piece;
		status = json_feed(&reader, (const uint8_t *)text + at, take);
	}
	obs_state_end_message(&state, status == JSON_DONE);
}

static void feed(const char *text) {
	feed_in_pieces(text, strlen(text));
}

// The string value of `"name":"` in `text`, or "" when it is not there.
static void string_field(const char *text, const char *name, char out[FIELD_MAX]) {
	char key[FIELD_MAX];
	snprintf(key, sizeof key, "\"%s\":\"", name);
	const char *start = strstr(text, key);
	out[0] = '\0';
	if (start != NULL) {
		start += strlen(key);
		size_t len = strcspn(start, "\"");
		snprintf(out, FIELD_MAX, "%.*s", (int)len, start);
	}
}

typedef struct {
	char type[FIELD_MAX];
	char id[FIELD_MAX];
	char uuid[FIELD_MAX];
} request_t;

// The next message, which the test expects to be a request.
static request_t next_request(uint32_t now_ms) {
	request_t request = {.type = ""};
	if (obs_state_next_message(&state, message, now_ms) > 0) {
		CHECK(strstr(message, "{\"op\":6,") == message);
		string_field(message, "requestType", request.type);
		string_field(message, "requestId", request.id);
		string_field(message, "inputUuid", request.uuid);
	}
	return request;
}

static void reply(const request_t *request, const char *response_data) {
	char text[1024];
	snprintf(text, sizeof text,
	         "{\"d\":{\"requestId\":\"%s\",\"requestStatus\":{\"code\":100,\"result\":true},"
	         "\"requestType\":\"%s\",\"responseData\":%s},\"op\":7}",
	         request->id, request->type, response_data);
	feed(text);
}

static void event(const char *type, const char *event_data) {
	char text[1024];
	snprintf(text, sizeof text,
	         "{\"d\":{\"eventData\":%s,\"eventIntent\":4,\"eventType\":\"%s\"},\"op\":5}",
	         event_data, type);
	feed(text);
}

static const char SCENES_ABC[] =
    "{\"currentPreviewSceneName\":\"Screen\",\"currentPreviewSceneUuid\":\"S_B\","
    "\"currentProgramSceneName\":\"Camera\",\"currentProgramSceneUuid\":\"S_A\",\"scenes\":["
    "{\"sceneIndex\":0,\"sceneName\":\"Camera\",\"sceneUuid\":\"S_A\"},"
    "{\"sceneIndex\":1,\"sceneName\":\"Screen\",\"sceneUuid\":\"S_B\"},"
    "{\"sceneIndex\":2,\"sceneName\":\"Break\",\"sceneUuid\":\"S_C\"}]}";
static const char INPUTS[] =
    "{\"inputs\":[{\"inputKind\":\"pulse\",\"inputKindCaps\":2,\"inputName\":\"Mic\","
    "\"inputUuid\":\"U_A\"},{\"inputKind\":\"browser\",\"inputKindCaps\":1,\"inputName\":\"Web\","
    "\"inputUuid\":\"V_A\"},{\"inputKind\":\"pulse\",\"inputKindCaps\":3,\"inputName\":\"Desktop\","
    "\"inputUuid\":\"U_B\"}]}";

// Answers the next request by its type, as OBS with the SCENES_ABC state would.
static void answer(const request_t *request) {
	if (strcmp(request->type, "GetSceneList") == 0) {
		reply(request, SCENES_ABC);
	} else if (strcmp(request->type, "GetStudioModeEnabled") == 0) {
		reply(request, "{\"studioModeEnabled\":true}");
	} else if (strcmp(request->type, "GetInputList") == 0) {
		reply(request, INPUTS);
	} else if (strcmp(request->type, "GetStreamStatus") == 0) {
		reply(request, "{\"outputActive\":true,\"outputReconnecting\":false}");
	} else if (strcmp(request->type, "GetRecordStatus") == 0) {
		reply(request, "{\"outputActive\":true,\"outputPaused\":true}");
	} else if (strcmp(request->type, "GetInputMute") == 0) {
		reply(request, "{\"inputMuted\":true}");
	} else if (strcmp(request->type, "GetInputVolume") == 0) {
		reply(request, "{\"inputVolumeDb\":-20.0,\"inputVolumeMul\":0.1}");
	}
}

// A fresh session with knob 1 on U_B, read to the end.
static void start_session(void) {
	obs_state_init(&state);
	CHECK(obs_state_watch(&state, 1, "U_B"));
	obs_state_begin(&state);
	for (int i = 0; i < 20 && !obs_state_is_current(&state); i++) {
		request_t request = next_request(0);
		answer(&request);
	}
	CHECK(obs_state_is_current(&state));
}

static void test_the_full_read_after_identified(void) {
	static const char *const ORDER[] = {"GetSceneList",    "GetStudioModeEnabled", "GetInputList",
	                                    "GetStreamStatus", "GetRecordStatus",      "GetInputMute",
	                                    "GetInputVolume"};
	obs_state_init(&state);
	CHECK(obs_state_next_message(&state, message, 0) == 0); // nothing before Identified
	CHECK(obs_state_watch(&state, 1, "U_B"));
	obs_state_begin(&state);
	CHECK(!obs_state_is_current(&state));
	for (size_t i = 0; i < sizeof ORDER / sizeof ORDER[0]; i++) {
		request_t request = next_request(0);
		CHECK(strcmp(request.type, ORDER[i]) == 0);
		CHECK(request.id[0] != '\0');
		if (i >= 5) {
			CHECK(strcmp(request.uuid, "U_B") == 0);
		}
		answer(&request);
	}
	CHECK(obs_state_is_current(&state));
	CHECK(obs_state_next_message(&state, message, 0) == 0);
	CHECK(state.scene_count == 3);
	CHECK(strcmp(state.scenes[2].name, "Break") == 0 && strcmp(state.scenes[2].uuid, "S_C") == 0);
	CHECK(strcmp(state.program, "S_A") == 0 && strcmp(state.preview, "S_B") == 0);
	CHECK(state.studio_mode);
	CHECK(state.input_count == 2); // the browser source has no audio
	CHECK(strcmp(state.inputs[1].name, "Desktop") == 0);
	CHECK(state.streaming);
	CHECK(!state.recording); // paused
	CHECK(state.knobs[1].mute_known && state.knobs[1].muted);
	CHECK(state.knobs[1].volume_known && state.knobs[1].volume_db == -20.0f);
	CHECK(!state.knobs[0].mute_known && !state.knobs[0].volume_known);
}

static void test_one_request_in_flight(void) {
	obs_state_init(&state);
	obs_state_begin(&state);
	request_t first = next_request(0);
	CHECK(strcmp(first.type, "GetSceneList") == 0);
	CHECK(obs_state_next_message(&state, message, 1000) == 0);
	event("CurrentProgramSceneChanged", "{\"sceneName\":\"Screen\",\"sceneUuid\":\"S_B\"}");
	CHECK(obs_state_next_message(&state, message, 1000) == 0); // an event is no reply
	answer(&first);
	request_t second = next_request(1000);
	CHECK(strcmp(second.type, "GetStudioModeEnabled") == 0);
	CHECK(strcmp(first.id, second.id) != 0);
}

// The reply to a request that timed out comes after the request sent in its place.
static void test_a_late_reply_is_matched_by_id_and_dropped(void) {
	obs_state_init(&state);
	obs_state_begin(&state);
	request_t late = next_request(0);
	CHECK(obs_state_next_message(&state, message, OBS_REQUEST_TIMEOUT_MS - 1) == 0);
	request_t again = next_request(OBS_REQUEST_TIMEOUT_MS);
	CHECK(strcmp(again.type, "GetSceneList") == 0);
	CHECK(strcmp(late.id, again.id) != 0);

	reply(&late, "{\"currentProgramSceneUuid\":\"OLD\",\"currentPreviewSceneUuid\":null,"
	             "\"scenes\":[{\"sceneName\":\"Old\",\"sceneUuid\":\"OLD\"}]}");
	CHECK(state.program[0] == '\0' && state.scene_count == 0);
	CHECK(obs_state_next_message(&state, message, OBS_REQUEST_TIMEOUT_MS) == 0); // still waits
	request_t stranger = {"GetSceneList", "r999999", ""};
	reply(&stranger, SCENES_ABC);
	CHECK(state.program[0] == '\0' && state.scene_count == 0);

	reply(&again, SCENES_ABC);
	CHECK(state.scene_count == 3);
	CHECK(strcmp(state.program, "S_A") == 0);
	request_t next = next_request(OBS_REQUEST_TIMEOUT_MS);
	CHECK(strcmp(next.type, "GetStudioModeEnabled") == 0);
	reply(&again, "{\"currentProgramSceneUuid\":\"OLD\",\"scenes\":[]}"); // answered already
	CHECK(state.scene_count == 3 && strcmp(state.program, "S_A") == 0);
}

// With the id after the list, the list streams into the table before the id is known. A late
// reply then leaves the table stale, so the list is read once more.
static void test_a_late_list_with_its_id_last_is_read_again(void) {
	obs_state_init(&state);
	obs_state_begin(&state);
	request_t late = next_request(0);
	request_t again = next_request(OBS_REQUEST_TIMEOUT_MS);
	char text[512];
	snprintf(text, sizeof text,
	         "{\"op\":7,\"d\":{\"responseData\":{\"scenes\":[{\"sceneName\":\"Old\","
	         "\"sceneUuid\":\"OLD\"}]},\"requestStatus\":{\"result\":true},\"requestId\":\"%s\"}}",
	         late.id);
	feed(text);
	CHECK(state.program[0] == '\0');
	reply(&again, SCENES_ABC);
	CHECK(state.scene_count == 3 && strcmp(state.program, "S_A") == 0);
	request_t next = next_request(OBS_REQUEST_TIMEOUT_MS);
	CHECK(strcmp(next.type, "GetSceneList") == 0);
}

static void test_a_failed_or_broken_reply_changes_nothing(void) {
	start_session();
	obs_state_watch(&state, 1, "U_B");
	request_t mute = next_request(0);
	CHECK(strcmp(mute.type, "GetInputMute") == 0);
	char text[256];
	snprintf(text, sizeof text,
	         "{\"d\":{\"requestId\":\"%s\",\"requestStatus\":{\"code\":600,\"result\":false},"
	         "\"requestType\":\"GetInputMute\"},\"op\":7}",
	         mute.id);
	feed(text);
	CHECK(!state.knobs[1].mute_known);
	request_t volume = next_request(0);
	CHECK(strcmp(volume.type, "GetInputVolume") == 0);
	snprintf(text, sizeof text,
	         "{\"d\":{\"requestId\":\"%s\",\"requestStatus\":{\"result\":true},"
	         "\"responseData\":{\"inputVolumeDb\":-3",
	         volume.id);
	feed(text);
	CHECK(!state.knobs[1].volume_known);
	request_t retry = next_request(0); // the cut reply is no answer: the read goes out again
	CHECK(strcmp(retry.type, "GetInputVolume") == 0);
}

static void test_500_scenes_load_in_fixed_ram_one_byte_at_a_time(void) {
	obs_state_init(&state);
	obs_state_begin(&state);
	request_t request = next_request(0);
	size_t len = (size_t)snprintf(big_reply, sizeof big_reply,
	                              "{\"d\":{\"requestId\":\"%s\",\"requestStatus\":{\"code\":100,"
	                              "\"result\":true},\"requestType\":\"GetSceneList\","
	                              "\"responseData\":{\"currentProgramSceneUuid\":"
	                              "\"00000000-0000-4000-8000-000000000007\",\"scenes\":[",
	                              request.id);
	for (unsigned i = 0; i < 500; i++) {
		len += (size_t)snprintf(big_reply + len, sizeof big_reply - len,
		                        "%s{\"sceneIndex\":%u,\"sceneName\":\"" LONG_NAME "\","
		                        "\"sceneUuid\":\"00000000-0000-4000-8000-%012u\"}",
		                        i ? "," : "", 499 - i, i, i);
	}
	len += (size_t)snprintf(big_reply + len, sizeof big_reply - len, "]}},\"op\":7}");
	CHECK(len > 70000 && len < sizeof big_reply - 1);
	feed_in_pieces(big_reply, 1);
	CHECK(state.scene_count == 500 && !state.scenes_capped);
	CHECK(strcmp(state.scenes[499].uuid, "00000000-0000-4000-8000-000000000499") == 0);
	CHECK(strlen(state.scenes[499].name) == OBS_NAME_MAX);
	CHECK(strncmp(state.scenes[499].name, "Scene ---", 9) == 0);
	CHECK(strcmp(state.program, "00000000-0000-4000-8000-000000000007") == 0);
	printf("obs_state_t: %zu bytes, any scene count\n", sizeof state);
}

static void test_a_list_past_its_cap_keeps_the_first_items(void) {
	obs_state_init(&state);
	obs_state_begin(&state);
	request_t request = next_request(0);
	size_t len = (size_t)snprintf(big_reply, sizeof big_reply,
	                              "{\"d\":{\"requestId\":\"%s\",\"requestStatus\":{\"result\":true},"
	                              "\"responseData\":{\"scenes\":[",
	                              request.id);
	for (unsigned i = 0; i < OBS_SCENES_MAX + 1; i++) {
		len += (size_t)snprintf(big_reply + len, sizeof big_reply - len,
		                        "%s{\"sceneName\":\"s%u\",\"sceneUuid\":\"S%u\"}", i ? "," : "", i, i);
	}
	snprintf(big_reply + len, sizeof big_reply - len, "]}},\"op\":7}");
	feed(big_reply);
	CHECK(state.scene_count == OBS_SCENES_MAX && state.scenes_capped);
	CHECK(strcmp(state.scenes[OBS_SCENES_MAX - 1].uuid, "S511") == 0);
}

static void test_a_scene_with_a_uuid_config_refuses_is_skipped(void) {
	obs_state_init(&state);
	obs_state_begin(&state);
	request_t request = next_request(0);
	reply(&request, "{\"scenes\":[{\"sceneName\":\"a\",\"sceneUuid\":\"has space\"},"
	                "{\"sceneName\":\"b\",\"sceneUuid\":\"0123456789012345678901234567890123456\"},"
	                "{\"sceneName\":\"c\",\"sceneUuid\":\"\"},{\"sceneName\":\"d\",\"sceneUuid\":7},"
	                "{\"sceneName\":\"e\"},{\"sceneName\":\"f\",\"sceneUuid\":\"S_F\"}]}");
	CHECK(state.scene_count == 1);
	CHECK(strcmp(state.scenes[0].name, "f") == 0);
}

static void test_names_are_cut_at_a_whole_character(void) {
	obs_state_init(&state);
	obs_state_begin(&state);
	request_t request = next_request(0);
	// 47 ASCII bytes, then a 2-byte letter: byte 48 would split it.
	reply(&request, "{\"scenes\":[{\"sceneName\":\"" "abcdefghijabcdefghijabcdefghijabcdefghijabcdefg"
	                "\xc3\xa9xyz\",\"sceneUuid\":\"S_A\"}]}");
	CHECK(state.scene_count == 1);
	CHECK(strlen(state.scenes[0].name) == 47);
}

static void test_events_reach_the_state(void) {
	start_session();
	event("CurrentProgramSceneChanged", "{\"sceneName\":\"Break\",\"sceneUuid\":\"S_C\"}");
	CHECK(strcmp(state.program, "S_C") == 0);
	event("CurrentPreviewSceneChanged", "{\"sceneName\":\"Camera\",\"sceneUuid\":\"S_A\"}");
	CHECK(strcmp(state.preview, "S_A") == 0);
	event("SceneNameChanged", "{\"oldSceneName\":\"Break\",\"sceneName\":\"Pause\",\"sceneUuid\":\"S_C\"}");
	CHECK(strcmp(state.scenes[2].name, "Pause") == 0);
	event("StudioModeStateChanged", "{\"studioModeEnabled\":false}");
	CHECK(!state.studio_mode && state.preview[0] == '\0');
	event("InputNameChanged", "{\"inputName\":\"Speakers\",\"inputUuid\":\"U_B\",\"oldInputName\":\"Desktop\"}");
	CHECK(strcmp(state.inputs[1].name, "Speakers") == 0);
	event("InputMuteStateChanged", "{\"inputMuted\":false,\"inputName\":\"Desktop\",\"inputUuid\":\"U_B\"}");
	CHECK(!state.knobs[1].muted);
	event("InputVolumeChanged",
	      "{\"inputName\":\"Desktop\",\"inputUuid\":\"U_B\",\"inputVolumeDb\":-4.437,\"inputVolumeMul\":0.6}");
	CHECK(state.knobs[1].volume_db > -4.44f && state.knobs[1].volume_db < -4.43f);
	event("InputVolumeChanged", "{\"inputUuid\":\"U_A\",\"inputVolumeDb\":-1}");
	CHECK(state.knobs[1].volume_db < -4.4f); // not a knob input
	event("StreamStateChanged", "{\"outputActive\":false,\"outputState\":\"OBS_WEBSOCKET_OUTPUT_RECONNECTING\"}");
	CHECK(!state.streaming);
	event("StreamStateChanged", "{\"outputActive\":true,\"outputState\":\"OBS_WEBSOCKET_OUTPUT_RECONNECTED\"}");
	CHECK(state.streaming);
	event("RecordStateChanged", "{\"outputActive\":true,\"outputPath\":null,\"outputState\":\"OBS_WEBSOCKET_OUTPUT_RESUMED\"}");
	CHECK(state.recording);
	event("RecordStateChanged", "{\"outputActive\":false,\"outputState\":\"OBS_WEBSOCKET_OUTPUT_STOPPED\"}");
	CHECK(!state.recording);
	CHECK(obs_state_is_current(&state));
}

static void test_event_keys_in_any_order(void) {
	start_session();
	feed("{\"op\":5,\"d\":{\"eventType\":\"CurrentProgramSceneChanged\","
	     "\"eventData\":{\"sceneUuid\":\"S_B\",\"sceneName\":\"Screen\"}}}");
	CHECK(strcmp(state.program, "S_B") == 0);
}

static void test_list_events_queue_a_new_read(void) {
	start_session();
	event("SceneListChanged", "{\"scenes\":[]}");
	request_t scenes = next_request(0);
	CHECK(strcmp(scenes.type, "GetSceneList") == 0);
	answer(&scenes);
	event("InputCreated", "{\"inputName\":\"Cam mic\",\"inputSettings\":{\"a\":[1,2]},\"inputUuid\":\"U_D\"}");
	request_t inputs = next_request(0);
	CHECK(strcmp(inputs.type, "GetInputList") == 0);
	answer(&inputs);
	event("InputRemoved", "{\"inputName\":\"Mic\",\"inputUuid\":\"U_A\"}");
	CHECK(strcmp(next_request(0).type, "GetInputList") == 0);
}

static void test_a_collection_switch_holds_requests_then_reads_all(void) {
	start_session();
	event("CurrentSceneCollectionChanging", "{\"sceneCollectionName\":\"Old\"}");
	CHECK(obs_state_watch(&state, 0, "U_A"));
	CHECK(obs_state_next_message(&state, message, 0) == 0);
	event("CurrentSceneCollectionChanged", "{\"sceneCollectionName\":\"New\"}");
	CHECK(strcmp(next_request(0).type, "GetSceneList") == 0);
}

static void test_meters_only_while_one_shows(void) {
	start_session();
	CHECK(obs_state_next_message(&state, message, 0) == 0); // Identify asked for 1118
	obs_state_show_meters(&state, true);
	CHECK(obs_state_next_message(&state, message, 0) > 0);
	CHECK(strcmp(message, "{\"op\":3,\"d\":{\"eventSubscriptions\":66654}}") == 0);
	CHECK(obs_state_next_message(&state, message, 0) == 0);

	CHECK(obs_state_watch(&state, 2, "U_C"));
	state.knobs[2].meter_peak = 0.5f;
	feed("{\"op\":2,\"d\":{\"negotiatedRpcVersion\":1}}"); // the Reidentify reply
	CHECK(state.pending != 0); // it is no new session: the watch reads stay queued
	event("InputVolumeMeters",
	      "{\"inputs\":[{\"inputLevelsMul\":[[0.1,0.25,0.3],[0.2,0.5,0.6]],\"inputName\":\"Desktop\","
	      "\"inputUuid\":\"U_B\"},{\"inputLevelsMul\":[[0.9,0.9,0.9]],\"inputUuid\":\"U_X\"}]}");
	CHECK(state.knobs[1].meter_peak == 0.5f);
	CHECK(state.knobs[2].meter_peak == 0.0f); // U_C sent no meter: it falls to zero

	obs_state_begin(&state); // a new session subscribes 1118 again
	CHECK(obs_state_next_message(&state, message, 0) > 0);
	CHECK(strstr(message, "66654") != NULL);
	obs_state_show_meters(&state, false);
	CHECK(obs_state_next_message(&state, message, 0) > 0);
	CHECK(strcmp(message, "{\"op\":3,\"d\":{\"eventSubscriptions\":1118}}") == 0);
}

static void test_watch_refuses_what_config_refuses(void) {
	obs_state_init(&state);
	CHECK(!obs_state_watch(&state, OBS_KNOBS, "U_A"));
	CHECK(!obs_state_watch(&state, 0, "has space"));
	CHECK(!obs_state_watch(&state, 0, "0123456789012345678901234567890123456"));
	CHECK(state.knobs[0].uuid[0] == '\0');
	CHECK(obs_state_watch(&state, 0, "a\"b\\c"));
	obs_state_begin(&state);
	for (int i = 0; i < 5; i++) {
		answer((request_t[]){next_request(0)});
	}
	CHECK(obs_state_next_message(&state, message, 0) > 0);
	CHECK(strstr(message, "\"inputUuid\":\"a\\\"b\\\\c\"") != NULL);
	CHECK(obs_state_watch(&state, 0, NULL));
	CHECK(state.knobs[0].uuid[0] == '\0');
}

static void test_output_on_states(void) {
	static const char *const ON[] = {"OBS_WEBSOCKET_OUTPUT_STARTED", "OBS_WEBSOCKET_OUTPUT_RESUMED",
	                                 "OBS_WEBSOCKET_OUTPUT_RECONNECTED"};
	static const char *const OFF[] = {"OBS_WEBSOCKET_OUTPUT_STARTING",     "OBS_WEBSOCKET_OUTPUT_STOPPING",
	                                  "OBS_WEBSOCKET_OUTPUT_STOPPED",      "OBS_WEBSOCKET_OUTPUT_RECONNECTING",
	                                  "OBS_WEBSOCKET_OUTPUT_PAUSED",       "outputActive",
	                                  "true",                              ""};
	for (size_t i = 0; i < sizeof ON / sizeof ON[0]; i++) {
		CHECK(obs_output_is_on(ON[i]));
	}
	for (size_t i = 0; i < sizeof OFF / sizeof OFF[0]; i++) {
		CHECK(!obs_output_is_on(OFF[i]));
	}
}

// The whole client against tools/fake_obs.py: after Identified the state reads itself in.
#define SETTLE_MS 10000u

static uint32_t now_ms(void) {
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	return (uint32_t)now.tv_sec * 1000u + (uint32_t)(now.tv_nsec / 1000000);
}

static uint32_t next_random(void) {
	return (uint32_t)rand();
}

static void test_the_client_reads_the_state_of_fake_obs(void) {
	int out[2];
	if (pipe(out) != 0) {
		perror("pipe");
		exit(2);
	}
	pid_t pid = fork();
	if (pid == 0) {
		dup2(out[1], STDOUT_FILENO);
		close(out[0]);
		execlp("python3", "python3", FAKE_OBS, "--log", "/dev/null", "--scenes", "500", (char *)NULL);
		_exit(127);
	}
	close(out[1]);
	char line[64] = {0};
	unsigned port = 0;
	struct pollfd ready = {.fd = out[0], .events = POLLIN};
	for (size_t len = 0; len < sizeof line - 1 && !strchr(line, '\n'); len++) {
		if (poll(&ready, 1, SETTLE_MS) != 1 || read(out[0], line + len, 1) != 1) {
			break;
		}
	}
	if (pid < 0 || sscanf(line, "listening %u", &port) != 1) {
		fprintf(stderr, "tools/fake_obs.py did not start\n");
		exit(2);
	}

	static posix_stream_t posix;
	static obs_t obs;
	posix_stream_init(&posix);
	obs_init(&obs, &posix.stream, next_random);
	obs_state_init(&state);
	obs_attach_state(&obs, &state);
	CHECK(obs_state_watch(&state, 0, "U_B"));
	CHECK(obs_start(&obs, (const uint8_t[]){127, 0, 0, 1}, (uint16_t)port, NULL, 0, now_ms()));
	uint32_t start = now_ms();
	while (!(obs.status == OBS_UP && obs_state_is_current(&state)) && now_ms() - start < SETTLE_MS) {
		obs_poll(&obs, now_ms());
		nanosleep(&(struct timespec){.tv_nsec = 1000000}, NULL);
	}
	kill(pid, SIGTERM);
	waitpid(pid, NULL, 0);
	close(out[0]);

	CHECK(obs.status == OBS_UP && obs_state_is_current(&state));
	CHECK(state.scene_count == 500);
	CHECK(state.input_count == 3);
	CHECK(state.studio_mode);
	CHECK(!state.streaming && !state.recording);
	CHECK(state.knobs[0].volume_known && state.knobs[0].volume_db == -20.0f);
	CHECK(state.knobs[0].mute_known && !state.knobs[0].muted);
}

int main(void) {
	signal(SIGPIPE, SIG_IGN);
	test_the_full_read_after_identified();
	test_one_request_in_flight();
	test_a_late_reply_is_matched_by_id_and_dropped();
	test_a_late_list_with_its_id_last_is_read_again();
	test_a_failed_or_broken_reply_changes_nothing();
	test_500_scenes_load_in_fixed_ram_one_byte_at_a_time();
	test_a_list_past_its_cap_keeps_the_first_items();
	test_a_scene_with_a_uuid_config_refuses_is_skipped();
	test_names_are_cut_at_a_whole_character();
	test_events_reach_the_state();
	test_event_keys_in_any_order();
	test_list_events_queue_a_new_read();
	test_a_collection_switch_holds_requests_then_reads_all();
	test_meters_only_while_one_shows();
	test_watch_refuses_what_config_refuses();
	test_output_on_states();
	test_the_client_reads_the_state_of_fake_obs();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	puts("obs state: all tests pass");
	return 0;
}
