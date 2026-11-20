// SPDX-License-Identifier: MIT
// The device link's OBS lists, STATUS and INPUT frames (task 2.11b, spec 8.2): OBS_LIST served
// from a real obs_state, STATUS from a real wifi_t, INPUT from real input_step events.
#include "cred.h"
#include "device.h"
#include "input.h"
#include "link.h"
#include "nor_model.h"
#include "obs_state.h"
#include "store.h"
#include "wifi.h"

#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

#define SCENES 500
#define FIELD_MAX 64
#define REPLY_CAP (64 * 1024)

static nor_chip_t chip;
static nor_part_t slot_a = {.chip = &chip, .base = 0, .size = STORE_SLOT_BYTES};
static nor_part_t slot_b = {.chip = &chip, .base = STORE_SLOT_BYTES, .size = STORE_SLOT_BYTES};

// ---- A cred that holds nothing: these frames never reach it. ----

static bool no_put(cred_t *cred, enum link_credential_kind kind, const uint8_t *bytes, size_t len) {
	(void)cred, (void)kind, (void)bytes, (void)len;
	return false;
}

static bool no_is_set(cred_t *cred, enum link_credential_kind kind) {
	(void)cred, (void)kind;
	return false;
}

static size_t no_get(cred_t *cred, enum link_credential_kind kind, uint8_t *out, size_t cap) {
	(void)cred, (void)kind, (void)out, (void)cap;
	return 0;
}

static bool no_erase_all(cred_t *cred) {
	(void)cred;
	return true;
}

static cred_t empty_cred = {
    .put = no_put, .is_set = no_is_set, .get = no_get, .erase_all = no_erase_all};

static const link_info_t IDENTITY = {
    .keys = INPUT_KEYS, .buttons = INPUT_BUTTONS, .knobs = INPUT_KNOBS};

static obs_state_t obs;
static device_t dev;

static void boot(void) {
	nor_chip_init(&chip);
	device_port_t port = {
		.identity = &IDENTITY,
		.cred = &empty_cred,
		.flash = &NOR_FLASH,
		.slot_a = &slot_a,
		.slot_b = &slot_b,
		.obs_state = &obs,
	};
	device_init(&dev, &port);
}

// ---- An OBS session read through obs_state, as fw-obs reads it ----

static char reply_text[REPLY_CAP];
static const char *scene_list; // responseData of GetSceneList
static const char *input_list; // responseData of GetInputList

static void feed(const char *text) {
	json_reader_t reader;
	obs_state_begin_message(&obs);
	json_reader_init(&reader, obs_state_sink, &obs);
	json_status_t status = json_feed(&reader, (const uint8_t *)text, strlen(text));
	obs_state_end_message(&obs, status == JSON_DONE);
}

static void string_field(const char *text, const char *name, char out[FIELD_MAX]) {
	char key[FIELD_MAX];
	snprintf(key, sizeof key, "\"%s\":\"", name);
	const char *start = strstr(text, key);
	out[0] = '\0';
	if (start != NULL) {
		start += strlen(key);
		snprintf(out, FIELD_MAX, "%.*s", (int)strcspn(start, "\""), start);
	}
}

static const char *response_data_of(const char *type) {
	if (strcmp(type, "GetSceneList") == 0) {
		return scene_list;
	}
	if (strcmp(type, "GetInputList") == 0) {
		return input_list;
	}
	return "{\"studioModeEnabled\":false,\"outputActive\":false}";
}

// Answers every read of the full read until the state is current.
static void read_session(void) {
	static char response[REPLY_CAP + 256];
	char request[OBS_MESSAGE_MAX];
	obs_state_init(&obs);
	obs_state_begin(&obs);
	for (int i = 0; i < 20 && obs_state_next_message(&obs, request, 0) > 0; i++) {
		char type[FIELD_MAX];
		char id[FIELD_MAX];
		string_field(request, "requestType", type);
		string_field(request, "requestId", id);
		snprintf(response, sizeof response,
		         "{\"d\":{\"requestId\":\"%s\",\"requestStatus\":{\"code\":100,\"result\":true},"
		         "\"requestType\":\"%s\",\"responseData\":%s},\"op\":7}",
		         id, type, response_data_of(type));
		feed(response);
	}
	CHECK(obs_state_is_current(&obs));
}

static void uuid_text(unsigned i, char out[FIELD_MAX]) {
	snprintf(out, FIELD_MAX, "00000000-0000-4000-8000-%012u", i);
}

static void read_500_scenes(void) {
	size_t len = (size_t)snprintf(reply_text, sizeof reply_text, "{\"scenes\":[");
	for (unsigned i = 0; i < SCENES; i++) {
		char uuid[FIELD_MAX];
		uuid_text(i, uuid);
		len += (size_t)snprintf(reply_text + len, sizeof reply_text - len,
		                        "%s{\"sceneIndex\":%u,\"sceneName\":\"Scene %03u\","
		                        "\"sceneUuid\":\"%s\"}",
		                        i ? "," : "", SCENES - 1 - i, i, uuid);
	}
	snprintf(reply_text + len, sizeof reply_text - len, "]}");
	scene_list = reply_text;
	input_list = "{\"inputs\":[]}";
	read_session();
	CHECK(obs.scene_count == SCENES);
}

// ---- The link ----

// The decoded name points into this frame, so it stays valid until the next ask_item.
static link_frame_t reply;

static link_msg_t ask_item(uint8_t list, uint16_t index) {
	link_msg_t request = {.type = LINK_OBS_LIST};
	request.as.obs_list.list = list;
	request.as.obs_list.index = index;
	uint8_t id = (uint8_t)(index % 255 + 1);
	link_frame_t frame;
	CHECK(link_msg_encode(&request, id, &frame));
	CHECK(device_handle(&dev, 0, &frame, &reply));
	CHECK(reply.id == id);
	link_msg_t got = {0};
	CHECK(link_msg_decode(&reply, &got));
	CHECK(got.type == LINK_OBS_ITEM);
	return got;
}

static bool name_is(const link_msg_t *item, const char *name) {
	return item->as.obs_item.name.len == strlen(name) &&
	       memcmp(item->as.obs_item.name.bytes, name, strlen(name)) == 0;
}

static bool uuid_is_nil(const link_msg_t *item) {
	static const uint8_t NIL[LINK_UUID_LEN];
	return memcmp(item->as.obs_item.uuid, NIL, LINK_UUID_LEN) == 0;
}

// The 16 bytes of the text form, read pair by pair, so the test does not share device.c's parser.
static void uuid_bytes(const char *text, uint8_t out[LINK_UUID_LEN]) {
	size_t at = 0;
	for (const char *c = text; *c != '\0' && at < LINK_UUID_LEN; c++) {
		if (*c != '-') {
			unsigned byte = 0;
			sscanf(c, "%2x", &byte);
			out[at++] = (uint8_t)byte;
			c++;
		}
	}
}

// ---- OBS_LIST and OBS_ITEM ----

static void test_500_scenes_come_back_as_500_items_in_order(void) {
	boot();
	read_500_scenes();
	for (unsigned i = 0; i < SCENES; i++) {
		link_msg_t item = ask_item(LINK_LIST_SCENES, (uint16_t)i);
		char uuid[FIELD_MAX];
		char name[FIELD_MAX];
		uint8_t want[LINK_UUID_LEN];
		uuid_text(i, uuid);
		uuid_bytes(uuid, want);
		snprintf(name, sizeof name, "Scene %03u", i);
		CHECK(item.as.obs_item.list == LINK_LIST_SCENES);
		CHECK(item.as.obs_item.index == i);
		CHECK(item.as.obs_item.total == SCENES);
		CHECK(memcmp(item.as.obs_item.uuid, want, LINK_UUID_LEN) == 0);
		CHECK(name_is(&item, name));
	}
}

static void test_the_uuid_text_form_packs_into_16_bytes(void) {
	boot();
	scene_list = "{\"scenes\":[{\"sceneIndex\":0,\"sceneName\":\"Cam\","
	             "\"sceneUuid\":\"0B0E6b1c-7f0a-4a55-9a43-1f2d3c4b5a69\"}]}";
	input_list = "{\"inputs\":[]}";
	read_session();
	static const uint8_t WANT[LINK_UUID_LEN] = {0x0b, 0x0e, 0x6b, 0x1c, 0x7f, 0x0a, 0x4a, 0x55,
	                                            0x9a, 0x43, 0x1f, 0x2d, 0x3c, 0x4b, 0x5a, 0x69};
	link_msg_t item = ask_item(LINK_LIST_SCENES, 0);
	CHECK(memcmp(item.as.obs_item.uuid, WANT, LINK_UUID_LEN) == 0);
}

static void test_an_index_at_or_past_total_is_no_item(void) {
	boot();
	read_500_scenes();
	uint16_t past[] = {SCENES, SCENES + 1, 0xFFFF};
	for (size_t i = 0; i < sizeof past / sizeof past[0]; i++) {
		link_msg_t item = ask_item(LINK_LIST_SCENES, past[i]);
		CHECK(item.as.obs_item.index == past[i] && item.as.obs_item.total == SCENES);
		CHECK(uuid_is_nil(&item) && item.as.obs_item.name.len == 0);
	}
}

static void test_inputs_are_the_audio_inputs_and_transitions_are_empty(void) {
	boot();
	scene_list = "{\"scenes\":[]}";
	input_list = "{\"inputs\":[{\"inputKind\":\"pulse\",\"inputKindCaps\":2,\"inputName\":\"Mic\","
	             "\"inputUuid\":\"6d1f0c52-93a7-4a0e-8f0b-52c1e7a9d340\"},{\"inputKind\":"
	             "\"browser\",\"inputKindCaps\":1,\"inputName\":\"Web\",\"inputUuid\":"
	             "\"7d1f0c52-93a7-4a0e-8f0b-52c1e7a9d340\"}]}";
	read_session();
	link_msg_t mic = ask_item(LINK_LIST_INPUTS, 0);
	CHECK(mic.as.obs_item.list == LINK_LIST_INPUTS && mic.as.obs_item.total == 1);
	CHECK(name_is(&mic, "Mic") && mic.as.obs_item.uuid[0] == 0x6d);
	link_msg_t scenes = ask_item(LINK_LIST_SCENES, 0);
	CHECK(scenes.as.obs_item.total == 0 && uuid_is_nil(&scenes));
	link_msg_t transitions = ask_item(LINK_LIST_TRANSITIONS, 0);
	CHECK(transitions.as.obs_item.list == LINK_LIST_TRANSITIONS);
	CHECK(transitions.as.obs_item.total == 0 && uuid_is_nil(&transitions));
}

// Config takes short test UUIDs such as U_B; 16 raw bytes cannot carry them.
static void test_a_uuid_not_in_text_form_goes_as_nil_with_its_name(void) {
	boot();
	scene_list = "{\"scenes\":[{\"sceneIndex\":0,\"sceneName\":\"Cam\",\"sceneUuid\":\"S_A\"},"
	             "{\"sceneIndex\":1,\"sceneName\":\"Bad\",\"sceneUuid\":"
	             "\"0b0e6b1c-7f0a-4a55-9a43-1f2d3c4b5a6g\"},"
	             "{\"sceneIndex\":2,\"sceneName\":\"Dash\",\"sceneUuid\":"
	             "\"0b0e6b1c07f0a-4a55-9a43-1f2d3c4b5a69\"}]}";
	input_list = "{\"inputs\":[]}";
	read_session();
	CHECK(obs.scene_count == 3);
	const char *names[] = {"Cam", "Bad", "Dash"};
	for (uint16_t i = 0; i < 3; i++) {
		link_msg_t item = ask_item(LINK_LIST_SCENES, i);
		CHECK(item.as.obs_item.total == 3 && uuid_is_nil(&item) && name_is(&item, names[i]));
	}
}

// ---- STATUS ----

static wifi_t wifi;
static enum link_obs_state obs_link;
static link_frame_t status_frame;

static int status_frames_now(void) {
	int sent = 0;
	for (int pass = 0; pass < 3; pass++) {
		if (device_status(&dev, obs_link, &wifi.status, &status_frame)) {
			sent++;
			CHECK(status_frame.id == 0);
		}
	}
	return sent;
}

static link_msg_t last_status(void) {
	link_msg_t got = {0};
	CHECK(link_msg_decode(&status_frame, &got));
	CHECK(got.type == LINK_STATUS);
	return got;
}

static void wifi_event(wifi_event_kind_t kind) {
	wifi_event_t event = {.kind = kind, .rssi_dbm = -52, .ip = {192, 168, 1, 40}};
	wifi_on_event(&wifi, &event, 0);
}

static void test_boot_sends_one_status(void) {
	boot();
	wifi_init(&wifi);
	obs_link = LINK_OBS_IDLE;
	CHECK(status_frames_now() == 1);
	link_msg_t got = last_status();
	CHECK(got.as.status.obs_state == LINK_OBS_IDLE);
	CHECK(got.as.status.wifi_state == LINK_WIFI_NO_SSID);
}

static void test_each_wifi_change_sends_one_status(void) {
	boot();
	wifi_init(&wifi);
	obs_link = LINK_OBS_IDLE;
	CHECK(status_frames_now() == 1);
	wifi_event(WIFI_EVT_SSID_SET);
	CHECK(status_frames_now() == 1);
	CHECK(last_status().as.status.wifi_state == LINK_WIFI_CONNECTING);
	wifi_event(WIFI_EVT_UP);
	CHECK(status_frames_now() == 1);
	link_msg_t up = last_status();
	CHECK(up.as.status.wifi_state == LINK_WIFI_UP && up.as.status.rssi_dbm == -52);
	CHECK(memcmp(up.as.status.ip, (uint8_t[]){192, 168, 1, 40}, 4) == 0);
	wifi_event_t weaker = {.kind = WIFI_EVT_UP, .rssi_dbm = -60, .ip = {192, 168, 1, 40}};
	wifi_on_event(&wifi, &weaker, 0); // still up: the RSSI alone changed
	CHECK(status_frames_now() == 1);
	CHECK(last_status().as.status.rssi_dbm == -60);
	wifi_event(WIFI_EVT_BAD_KEY);
	CHECK(status_frames_now() == 1);
	link_msg_t down = last_status();
	CHECK(down.as.status.wifi_state == LINK_WIFI_BAD_KEY && down.as.status.rssi_dbm == 0);
	CHECK(memcmp(down.as.status.ip, (uint8_t[]){0, 0, 0, 0}, 4) == 0);
	wifi_event(WIFI_EVT_NO_AP);
	CHECK(status_frames_now() == 1);
	wifi_event(WIFI_EVT_NO_AP); // the same state again: no change
	CHECK(status_frames_now() == 0);
}

static void test_each_obs_change_sends_one_status(void) {
	boot();
	wifi_init(&wifi);
	obs_link = LINK_OBS_IDLE;
	CHECK(status_frames_now() == 1);
	enum link_obs_state steps[] = {LINK_OBS_CONNECTING, LINK_OBS_REFUSED, LINK_OBS_CONNECTING,
	                               LINK_OBS_UP, LINK_OBS_AUTH_FAILED};
	for (size_t i = 0; i < sizeof steps / sizeof steps[0]; i++) {
		obs_link = steps[i];
		CHECK(status_frames_now() == 1);
		CHECK(last_status().as.status.obs_state == steps[i]);
	}
}

// ---- INPUT ----

static input_t in;
static uint32_t in_ms;
static link_msg_t inputs[INPUT_MAX_EVENTS * 4];
static int input_count;

// Runs `sample` for one debounce and more, and turns each event into its INPUT frames.
static void hold(input_sample_t sample) {
	for (int ms = 0; ms <= INPUT_DEBOUNCE_MS + 1; ms++) {
		sample.now_ms = in_ms++;
		input_event_t events[INPUT_MAX_EVENTS];
		int count = input_step(&in, &sample, events);
		for (int i = 0; i < count; i++) {
			link_frame_t frame;
			CHECK(device_input_frame(&events[i], &frame));
			CHECK(frame.id == 0);
			CHECK(input_count < (int)(sizeof inputs / sizeof inputs[0]));
			CHECK(link_msg_decode(&frame, &inputs[input_count++]));
		}
		memset(sample.knob_counts, 0, sizeof sample.knob_counts);
	}
}

static bool input_is(int at, uint8_t source, uint8_t index, int8_t value) {
	const link_msg_t *msg = &inputs[at];
	return msg->type == LINK_INPUT && msg->as.input.source == source &&
	       msg->as.input.index == index && msg->as.input.value == value;
}

// Matrix order of input.h: keys on COL0..2 of ROW0..2, pushes on COL3, buttons on ROW3.
static void contact_of(int row, int col, uint8_t *source, uint8_t *index) {
	if (row == INPUT_ROWS - 1) {
		*source = LINK_INPUT_BUTTON, *index = (uint8_t)col;
	} else if (col == INPUT_COLS - 1) {
		*source = LINK_INPUT_KNOB_PUSH, *index = (uint8_t)row;
	} else {
		*source = LINK_INPUT_KEY, *index = (uint8_t)(row * 3 + col);
	}
}

static void test_each_press_and_release_sends_one_input(void) {
	for (int row = 0; row < INPUT_ROWS; row++) {
		for (int col = 0; col < INPUT_COLS; col++) {
			input_init(&in);
			in_ms = 0;
			input_count = 0;
			input_sample_t pressed = {0};
			pressed.cols_low[row] = (uint8_t)(1u << col);
			hold(pressed);
			hold((input_sample_t){0});
			uint8_t source;
			uint8_t index;
			contact_of(row, col, &source, &index);
			CHECK(input_count == 2);
			CHECK(input_is(0, source, index, 1));
			CHECK(input_is(1, source, index, 0));
		}
	}
}

static void test_each_knob_step_sends_one_input(void) {
	for (int knob = 0; knob < INPUT_KNOBS; knob++) {
		input_init(&in);
		in_ms = 0;
		input_count = 0;
		input_sample_t turned = {0};
		turned.knob_counts[knob] = INPUT_COUNTS_PER_DETENT;
		hold(turned);
		turned.knob_counts[knob] = -3 * INPUT_COUNTS_PER_DETENT;
		hold(turned);
		CHECK(input_count == 2);
		CHECK(input_is(0, LINK_INPUT_KNOB_TURN, (uint8_t)knob, 1));
		CHECK(input_is(1, LINK_INPUT_KNOB_TURN, (uint8_t)knob, -3));
	}
}

static void test_the_clear_combination_sends_no_input(void) {
	input_event_t clear = {.source = INPUT_SOURCE_CLEAR, .index = 0, .value = 1};
	link_frame_t frame;
	CHECK(!device_input_frame(&clear, &frame));
}

int main(void) {
	test_500_scenes_come_back_as_500_items_in_order();
	test_the_uuid_text_form_packs_into_16_bytes();
	test_an_index_at_or_past_total_is_no_item();
	test_inputs_are_the_audio_inputs_and_transitions_are_empty();
	test_a_uuid_not_in_text_form_goes_as_nil_with_its_name();
	test_boot_sends_one_status();
	test_each_wifi_change_sends_one_status();
	test_each_obs_change_sends_one_status();
	test_each_press_and_release_sends_one_input();
	test_each_knob_step_sends_one_input();
	test_the_clear_combination_sends_no_input();
	if (failures != 0) {
		fprintf(stderr, "test_device_obs: %d failure(s)\n", failures);
		return 1;
	}
	puts("test_device_obs: ok");
	return 0;
}
