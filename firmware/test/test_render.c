// SPDX-License-Identifier: MIT
// The band renderer against committed golden frames of the big panel: 320 x 480, big-endian
// RGB565, 307,200 bytes, compared byte for byte. The test sink writes each push into a frame the
// way the panel would take it, and logs which tiles each push covered.
// RENDER_GOLDEN_UPDATE=1 rewrites the goldens instead of comparing; review the change before
// committing it.
#include "render.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

#define WIDTH 320
#define HEIGHT 480
#define FRAME_BYTES (WIDTH * HEIGHT * 2)
#define COLS (WIDTH / UI_TILE)
#define ROWS (HEIGHT / UI_TILE)

typedef struct {
	uint8_t frame[FRAME_BYTES];
	int pushes;
	int tile_pushes[ROWS][COLS]; // how often each tile was pushed since the last reset
	bool bad_window;
} panel_t;

typedef bool tiles_t[ROWS][COLS];

static void on_push(void *context, ui_display_t display, ui_rect_t window, const uint16_t *pixels) {
	panel_t *panel = context;
	panel->pushes++;
	bool aligned = window.x % UI_TILE == 0 && window.y % UI_TILE == 0 && window.w % UI_TILE == 0 &&
	               window.h == UI_TILE;
	if (display != UI_MAIN || !aligned || window.w == 0 || window.x + window.w > WIDTH || window.y + window.h > HEIGHT) {
		panel->bad_window = true;
		return;
	}
	for (int y = 0; y < window.h; y++) {
		for (int x = 0; x < window.w; x++) {
			uint16_t pixel = pixels[y * window.w + x];
			size_t at = ((size_t)(window.y + y) * WIDTH + window.x + x) * 2;
			panel->frame[at] = (uint8_t)(pixel >> 8);
			panel->frame[at + 1] = (uint8_t)pixel;
		}
	}
	for (int col = window.x / UI_TILE; col < (window.x + window.w) / UI_TILE; col++) {
		panel->tile_pushes[window.y / UI_TILE][col]++;
	}
}

static void reset_log(panel_t *panel) {
	panel->pushes = 0;
	memset(panel->tile_pushes, 0, sizeof panel->tile_pushes);
}

typedef struct {
	ui_model_t model;
	render_t render;
	panel_t panel;
} pad_t;

static pad_t *new_pad(const char *doc) {
	pad_t *pad = calloc(1, sizeof *pad);
	ui_layout_t layouts[UI_DISPLAYS];
	ui_init(&pad->model);
	bool parsed = ui_parse(layouts, (const uint8_t *)doc, strlen(doc));
	CHECK(parsed);
	CHECK(parsed && ui_apply(&pad->model, layouts));
	render_init(&pad->render, (render_sink_t){on_push, &pad->panel});
	return pad;
}

static void show(pad_t *pad, const render_view_t *view) {
	render_display(&pad->render, &pad->model, UI_MAIN, view);
}

// ---- Goldens ----

static void check_golden(const char *name, const uint8_t *frame) {
	char path[512];
	snprintf(path, sizeof path, "%s/%s.rgb565", GOLDEN, name);
	const char *update = getenv("RENDER_GOLDEN_UPDATE");
	if (update != NULL && strcmp(update, "1") == 0) {
		FILE *out = fopen(path, "wb");
		CHECK(out != NULL && fwrite(frame, 1, FRAME_BYTES, out) == FRAME_BYTES);
		if (out != NULL) {
			fclose(out);
		}
		printf("wrote %s\n", path);
		return;
	}
	static uint8_t golden[FRAME_BYTES + 1];
	FILE *in = fopen(path, "rb");
	size_t got = in != NULL ? fread(golden, 1, sizeof golden, in) : 0;
	if (in != NULL) {
		fclose(in);
	}
	CHECK(got == FRAME_BYTES);
	for (size_t i = 0; got == FRAME_BYTES && i < FRAME_BYTES; i++) {
		if (golden[i] != frame[i]) {
			fprintf(stderr, "%s: first difference at byte %zu (x %zu, y %zu)\n", name, i, i / 2 % WIDTH, i / 2 / WIDTH);
			failures++;
			break;
		}
	}
}

// ---- Layouts and views ----

#define KEY(n, x, y, h) "{\"kind\":\"key\",\"x\":" #x ",\"y\":" #y ",\"w\":104,\"h\":" #h ",\"key\":" #n "}"
#define LEGEND(n, x, y, h) "{\"kind\":\"legend\",\"x\":" #x ",\"y\":" #y ",\"w\":77,\"h\":" #h ",\"button\":" #n "}"

// Report 14 preset A, "Mirror".
static const char MIRROR[] =
	"{\"main_display\":{\"widgets\":["
	"{\"kind\":\"status\",\"x\":0,\"y\":0,\"w\":320,\"h\":36,\"fields\":[\"link\",\"rec\",\"live\"]},"
	KEY(0, 0, 40, 104) "," KEY(1, 108, 40, 104) "," KEY(2, 216, 40, 104) ","
	KEY(3, 0, 148, 104) "," KEY(4, 108, 148, 104) "," KEY(5, 216, 148, 104) ","
	KEY(6, 0, 256, 104) "," KEY(7, 108, 256, 104) "," KEY(8, 216, 256, 104) ","
	"{\"kind\":\"scene_line\",\"x\":0,\"y\":364,\"w\":320,\"h\":24,\"scene\":\"program\",\"size\":\"small\"},"
	"{\"kind\":\"scene_line\",\"x\":0,\"y\":388,\"w\":320,\"h\":24,\"scene\":\"preview\",\"size\":\"small\"},"
	LEGEND(0, 0, 416, 64) "," LEGEND(1, 81, 416, 64) "," LEGEND(2, 162, 416, 64) "," LEGEND(3, 243, 416, 64)
	"]},\"strip_display\":{\"widgets\":[]}}";

// Every kind, the large scene line, and text the fonts cannot fully show.
static const char KINDS[] =
	"{\"main_display\":{\"widgets\":["
	"{\"kind\":\"status\",\"x\":0,\"y\":0,\"w\":320,\"h\":36,\"fields\":[\"link\",\"live\"]},"
	"{\"kind\":\"scene_line\",\"x\":0,\"y\":40,\"w\":320,\"h\":80,\"scene\":\"program\",\"size\":\"large\"},"
	KEY(0, 0, 124, 72) "," KEY(1, 108, 124, 72) "," KEY(2, 216, 124, 72) ","
	"{\"kind\":\"strip\",\"x\":0,\"y\":200,\"w\":142,\"h\":140,\"knob\":0,"
	"\"parts\":[\"name\",\"db\",\"fader\",\"meter\",\"push\"]},"
	"{\"kind\":\"strip\",\"x\":146,\"y\":200,\"w\":142,\"h\":140,\"knob\":1,\"parts\":[\"name\",\"db\",\"fader\"]},"
	"{\"kind\":\"scene_line\",\"x\":0,\"y\":344,\"w\":320,\"h\":24,\"scene\":\"preview\",\"size\":\"small\"},"
	LEGEND(0, 0, 372, 56) ","
	"{\"kind\":\"text\",\"x\":0,\"y\":432,\"w\":320,\"h\":48,\"text\":\"\xd0\x9f\xd1\x80\xd0\xb8 01:02\"}"
	"]},\"strip_display\":{\"widgets\":[]}}";

static void set_key(render_key_t *key, render_key_state_t state, const char *word, const char *label) {
	key->state = (uint8_t)state;
	snprintf(key->word, sizeof key->word, "%s", word);
	snprintf(key->label, sizeof key->label, "%s", label);
}

static render_view_t mirror_view(void) {
	render_view_t view;
	memset(&view, 0, sizeof view);
	view.link_ok = true;
	snprintf(view.link, sizeof view.link, "OBS ok");
	view.rec = (render_output_t){true, 761};
	view.live = (render_output_t){true, 3733};
	snprintf(view.scene[UI_SCENE_PROGRAM], sizeof view.scene[0], "Desk wide");
	snprintf(view.scene[UI_SCENE_PREVIEW], sizeof view.scene[0], "Screen share");
	set_key(&view.keys[0], RENDER_KEY_IDLE, "SCENE", "Intro card");
	set_key(&view.keys[1], RENDER_KEY_PROGRAM, "SCENE", "Desk wide");
	set_key(&view.keys[2], RENDER_KEY_ON, "MUTE", "Mic");
	set_key(&view.keys[3], RENDER_KEY_PREVIEW, "SCENE", "Screen share");
	set_key(&view.keys[4], RENDER_KEY_IDLE, "SCENE", "Guest");
	set_key(&view.keys[5], RENDER_KEY_MISSING, "SCENE", "Game");
	set_key(&view.keys[6], RENDER_KEY_IDLE, "REC", "Record");
	set_key(&view.keys[7], RENDER_KEY_IDLE, "STREAM", "Go live");
	set_key(&view.keys[8], RENDER_KEY_IDLE, "HOTKEY", "Replay save");
	const char *legends[RENDER_BUTTONS] = {"Studio mode", "Cut", "Fade", "Page 2/3"};
	for (int i = 0; i < RENDER_BUTTONS; i++) {
		snprintf(view.legends[i], sizeof view.legends[i], "%s", legends[i]);
	}
	return view;
}

static render_view_t kinds_view(void) {
	render_view_t view = mirror_view();
	view.link_ok = false;
	snprintf(view.link, sizeof view.link, "No network");
	view.live = (render_output_t){false, 0};
	// U+2014 is not in the Latin set: it draws as a box. The name is cut with an ellipsis.
	snprintf(view.scene[UI_SCENE_PROGRAM], sizeof view.scene[0], "Caf\xc3\xa9 \xe2\x80\x94 \xc3\x9c" "ber wide shot");
	set_key(&view.keys[0], RENDER_KEY_UNBOUND, "", "");
	set_key(&view.keys[1], RENDER_KEY_IDLE, "", "\xc3\x9cn\xc3\xaf" "c\xc3\xb8" "de ok");
	set_key(&view.keys[2], RENDER_KEY_MISSING, "SCENE", "bad \xc3(utf8");
	view.channels[0] = (render_channel_t){"Mic", -124, -150, false, "mute"};
	view.channels[1] = (render_channel_t){"Desktop audio", -60, -300, true, ""};
	return view;
}

// ---- Tests ----

static void expect_rect(tiles_t tiles, ui_rect_t rect) {
	for (int row = rect.y / UI_TILE; row <= (rect.y + rect.h - 1) / UI_TILE; row++) {
		for (int col = rect.x / UI_TILE; col <= (rect.x + rect.w - 1) / UI_TILE; col++) {
			tiles[row][col] = true;
		}
	}
}

// Each tile in `expected` pushed exactly once, every other tile not at all.
static void check_pushed(const panel_t *panel, tiles_t expected) {
	int wrong = 0;
	for (int row = 0; row < ROWS; row++) {
		for (int col = 0; col < COLS; col++) {
			wrong += panel->tile_pushes[row][col] != (expected[row][col] ? 1 : 0);
		}
	}
	CHECK(wrong == 0);
	CHECK(!panel->bad_window);
}

static void test_first_frame_paints_every_tile_once(void) {
	pad_t *pad = new_pad(MIRROR);
	render_view_t view = mirror_view();
	show(pad, &view);
	tiles_t all;
	memset(all, 1, sizeof all);
	check_pushed(&pad->panel, all);
	CHECK(pad->panel.pushes == ROWS); // a band row of all-dirty tiles is one run
	check_golden("main_mirror", pad->panel.frame);
	free(pad);
}

static void test_unchanged_view_pushes_nothing(void) {
	pad_t *pad = new_pad(MIRROR);
	render_view_t view = mirror_view();
	show(pad, &view);
	reset_log(&pad->panel);
	show(pad, &view);
	CHECK(pad->panel.pushes == 0);
	free(pad);
}

// A cut to "Guest": keys 1 and 4 and the program line change, so only their tiles are pushed, and
// the frame then equals a fresh full paint of the new state.
static void test_scene_change_pushes_only_changed_tiles(void) {
	pad_t *pad = new_pad(MIRROR);
	render_view_t view = mirror_view();
	show(pad, &view);
	reset_log(&pad->panel);
	view.keys[1].state = RENDER_KEY_IDLE;
	view.keys[4].state = RENDER_KEY_PROGRAM;
	snprintf(view.scene[UI_SCENE_PROGRAM], sizeof view.scene[0], "Guest");
	show(pad, &view);
	tiles_t expected = {{false}};
	expect_rect(expected, (ui_rect_t){108, 40, 104, 104});
	expect_rect(expected, (ui_rect_t){108, 148, 104, 104});
	expect_rect(expected, (ui_rect_t){0, 364, 320, 24});
	check_pushed(&pad->panel, expected);
	check_golden("main_cut", pad->panel.frame);

	pad_t *fresh = new_pad(MIRROR);
	show(fresh, &view);
	CHECK(memcmp(fresh->panel.frame, pad->panel.frame, FRAME_BYTES) == 0);
	free(fresh);
	free(pad);
}

static void test_timecode_tick_pushes_only_the_status(void) {
	pad_t *pad = new_pad(MIRROR);
	render_view_t view = mirror_view();
	show(pad, &view);
	reset_log(&pad->panel);
	view.rec.seconds++;
	show(pad, &view);
	tiles_t expected = {{false}};
	expect_rect(expected, (ui_rect_t){0, 0, 320, 36});
	check_pushed(&pad->panel, expected);
	free(pad);
}

// A widget never writes outside its own rectangle: a frame with the key widgets alone is black
// around them, whatever their text does.
static void test_widgets_stay_inside_their_rectangle(void) {
	static const char ONE_KEY[] = "{\"main_display\":{\"widgets\":[" KEY(8, 108, 148, 24) "]},\"strip_display\":{\"widgets\":[]}}";
	pad_t *pad = new_pad(ONE_KEY);
	render_view_t view = mirror_view();
	set_key(&view.keys[8], RENDER_KEY_PREVIEW, "HOTKEY", "A label far too long for two lines of this key");
	show(pad, &view);
	int outside = 0;
	for (int y = 0; y < HEIGHT; y++) {
		for (int x = 0; x < WIDTH; x++) {
			bool inside = x >= 108 && x < 212 && y >= 148 && y < 172;
			size_t at = ((size_t)y * WIDTH + x) * 2;
			outside += !inside && (pad->panel.frame[at] | pad->panel.frame[at + 1]) != 0;
		}
	}
	CHECK(outside == 0);
	free(pad);
}

static void test_every_kind_frame(void) {
	pad_t *pad = new_pad(KINDS);
	render_view_t view = kinds_view();
	show(pad, &view);
	check_golden("main_kinds", pad->panel.frame);
	free(pad);
}

int main(void) {
	test_first_frame_paints_every_tile_once();
	test_unchanged_view_pushes_nothing();
	test_scene_change_pushes_only_changed_tiles();
	test_timecode_tick_pushes_only_the_status();
	test_widgets_stay_inside_their_rectangle();
	test_every_kind_frame();
	if (failures != 0) {
		fprintf(stderr, "test_render: %d failures\n", failures);
		return 1;
	}
	printf("test_render: ok\n");
	return 0;
}
