// SPDX-License-Identifier: MIT
// The band renderer on the strip panel, 142 x 428, and the three mock-ups of report 14 (R14),
// against committed golden frames: big-endian RGB565, compared byte for byte. A strip frame is
// 121,552 bytes, a big-panel frame 307,200 (criterion 4b). The strip is not a whole number of
// tiles wide or tall, so its last tile column is 14 px wide and its last tile row 12 px tall.
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

#define STRIP_WIDTH 142
#define STRIP_HEIGHT 428
#define STRIP_FRAME_BYTES (STRIP_WIDTH * STRIP_HEIGHT * 2)
#define MAIN_FRAME_BYTES (320 * 480 * 2)
#define MAX_COLS (320 / UI_TILE)
#define MAX_ROWS (480 / UI_TILE)

// One panel as it takes pushes: each window lands in `frame`, and each tile it covers is counted.
typedef struct {
	ui_display_t display;
	ui_grid_t grid;
	uint8_t frame[MAIN_FRAME_BYTES]; // grid.width * grid.height * 2 used
	int pushes;
	int tile_pushes[MAX_ROWS][MAX_COLS];
	bool bad_window;
} panel_t;

typedef bool tiles_t[MAX_ROWS][MAX_COLS];

static size_t frame_bytes(const panel_t *panel) {
	return (size_t)panel->grid.width * panel->grid.height * 2;
}

// A window starts on a tile corner and spans whole tiles, cut only where the panel ends.
static bool window_fits(const panel_t *panel, ui_display_t display, ui_rect_t window) {
	unsigned right = (unsigned)window.x + window.w, bottom = (unsigned)window.y + window.h;
	bool on_corner = window.x % UI_TILE == 0 && window.y % UI_TILE == 0;
	bool whole_cols = window.w % UI_TILE == 0 || right == panel->grid.width;
	bool one_band = window.h == UI_TILE || (bottom == panel->grid.height && window.h < UI_TILE);
	return display == panel->display && window.w > 0 && window.h > 0 && right <= panel->grid.width &&
	       bottom <= panel->grid.height && on_corner && whole_cols && one_band;
}

static void on_push(void *context, ui_display_t display, ui_rect_t window, const uint16_t *pixels) {
	panel_t *panel = context;
	panel->pushes++;
	if (!window_fits(panel, display, window)) {
		panel->bad_window = true;
		return;
	}
	for (int y = 0; y < window.h; y++) {
		for (int x = 0; x < window.w; x++) {
			uint16_t pixel = pixels[y * window.w + x];
			size_t at = ((size_t)(window.y + y) * panel->grid.width + window.x + x) * 2;
			panel->frame[at] = (uint8_t)(pixel >> 8);
			panel->frame[at + 1] = (uint8_t)pixel;
		}
	}
	for (int col = window.x / UI_TILE; col <= (window.x + window.w - 1) / UI_TILE; col++) {
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

// A pad that shows `doc` on one display.
static pad_t *new_pad(const char *doc, ui_display_t display) {
	pad_t *pad = calloc(1, sizeof *pad);
	ui_layout_t layouts[UI_DISPLAYS];
	ui_init(&pad->model);
	bool parsed = ui_parse(layouts, (const uint8_t *)doc, strlen(doc));
	CHECK(parsed);
	CHECK(parsed && ui_apply(&pad->model, layouts));
	pad->panel.display = display;
	pad->panel.grid = ui_grid(display);
	render_init(&pad->render, (render_sink_t){on_push, &pad->panel});
	return pad;
}

static void show(pad_t *pad, const render_view_t *view) {
	render_display(&pad->render, &pad->model, pad->panel.display, view);
}

// ---- Goldens ----

static void write_golden(const char *path, const uint8_t *frame, size_t size) {
	FILE *out = fopen(path, "wb");
	CHECK(out != NULL && fwrite(frame, 1, size, out) == size);
	if (out != NULL) {
		fclose(out);
	}
	printf("wrote %s\n", path);
}

static void check_golden(const char *name, const panel_t *panel) {
	char path[512];
	snprintf(path, sizeof path, "%s/%s.rgb565", GOLDEN, name);
	size_t size = frame_bytes(panel);
	const char *update = getenv("RENDER_GOLDEN_UPDATE");
	if (update != NULL && strcmp(update, "1") == 0) {
		write_golden(path, panel->frame, size);
		return;
	}
	static uint8_t golden[MAIN_FRAME_BYTES + 1];
	FILE *in = fopen(path, "rb");
	size_t got = in != NULL ? fread(golden, 1, sizeof golden, in) : 0;
	if (in != NULL) {
		fclose(in);
	}
	if (got != size) {
		fprintf(stderr, "%s: %zu bytes, want %zu\n", name, got, size);
		failures++;
		return;
	}
	for (size_t i = 0; i < size; i++) {
		if (golden[i] != panel->frame[i]) {
			fprintf(stderr, "%s: first difference at byte %zu (x %zu, y %zu)\n", name, i,
			        i / 2 % panel->grid.width, i / 2 / panel->grid.width);
			failures++;
			return;
		}
	}
}

// ---- Layouts ----

#define EMPTY_MAIN "\"main_display\":{\"widgets\":[]}"
#define STRIP(n, y, parts) \
	"{\"kind\":\"strip\",\"x\":0,\"y\":" #y ",\"w\":142,\"h\":140,\"knob\":" #n ",\"parts\":[" parts "]}"
#define THREE_STRIPS(parts) STRIP(0, 0, parts) "," STRIP(1, 144, parts) "," STRIP(2, 288, parts)
#define KEY(n, x, y, h) "{\"kind\":\"key\",\"x\":" #x ",\"y\":" #y ",\"w\":104,\"h\":" #h ",\"key\":" #n "}"
#define LEGEND(n, x, y, h) "{\"kind\":\"legend\",\"x\":" #x ",\"y\":" #y ",\"w\":77,\"h\":" #h ",\"button\":" #n "}"
#define STATUS(y, fields) "{\"kind\":\"status\",\"x\":0,\"y\":" #y ",\"w\":320,\"h\":36,\"fields\":[" fields "]}"
#define ALL_STATUS STATUS(0, "\"link\",\"rec\",\"live\"")

// R14 "Narrow strips (presets A and B)": three strips 140 tall with a 4 px gap, every part.
static const char STRIP_METERS[] =
	"{" EMPTY_MAIN ",\"strip_display\":{\"widgets\":["
	THREE_STRIPS("\"name\",\"db\",\"fader\",\"meter\",\"push\"") "]}}";

// Spec 4, assumption 4: `level` is the fader dB and meters are opt-in, so no meter part.
static const char STRIP_FADER[] =
	"{" EMPTY_MAIN ",\"strip_display\":{\"widgets\":["
	THREE_STRIPS("\"name\",\"db\",\"fader\",\"push\"") "]}}";

// R14 preset A, "Mirror", as drawn.
static const char R14_MIRROR[] =
	"{\"main_display\":{\"widgets\":[" ALL_STATUS ","
	KEY(0, 0, 40, 104) "," KEY(1, 108, 40, 104) "," KEY(2, 216, 40, 104) ","
	KEY(3, 0, 148, 104) "," KEY(4, 108, 148, 104) "," KEY(5, 216, 148, 104) ","
	KEY(6, 0, 256, 104) "," KEY(7, 108, 256, 104) "," KEY(8, 216, 256, 104) ","
	"{\"kind\":\"scene_line\",\"x\":0,\"y\":364,\"w\":320,\"h\":24,\"scene\":\"program\",\"size\":\"small\"},"
	"{\"kind\":\"scene_line\",\"x\":0,\"y\":388,\"w\":320,\"h\":24,\"scene\":\"preview\",\"size\":\"small\"},"
	LEGEND(0, 0, 416, 64) "," LEGEND(1, 81, 416, 64) "," LEGEND(2, 162, 416, 64) "," LEGEND(3, 243, 416, 64)
	"]},\"strip_display\":{\"widgets\":[" THREE_STRIPS("\"name\",\"db\",\"fader\",\"meter\",\"push\"") "]}}";

// R14 preset B, "On air". Schema 1 has no stream-health binding (docs/config.md), so the stream
// line is a fixed `text`.
static const char R14_ON_AIR[] =
	"{\"main_display\":{\"widgets\":[" ALL_STATUS ","
	"{\"kind\":\"scene_line\",\"x\":0,\"y\":40,\"w\":320,\"h\":80,\"scene\":\"program\",\"size\":\"large\"},"
	KEY(0, 0, 124, 72) "," KEY(1, 108, 124, 72) "," KEY(2, 216, 124, 72) ","
	KEY(3, 0, 200, 72) "," KEY(4, 108, 200, 72) "," KEY(5, 216, 200, 72) ","
	KEY(6, 0, 276, 72) "," KEY(7, 108, 276, 72) "," KEY(8, 216, 276, 72) ","
	LEGEND(0, 0, 352, 56) "," LEGEND(1, 81, 352, 56) "," LEGEND(2, 162, 352, 56) "," LEGEND(3, 243, 352, 56) ","
	"{\"kind\":\"text\",\"x\":0,\"y\":412,\"w\":320,\"h\":68,\"text\":\"Dropped 0 / 81,204 frames\"}"
	"]},\"strip_display\":{\"widgets\":[" THREE_STRIPS("\"name\",\"db\",\"fader\",\"meter\",\"push\"") "]}}";

// R14 preset C, "Idle": REC, LIVE and the link on the big panel, name and number on the strip.
static const char R14_IDLE[] =
	"{\"main_display\":{\"widgets\":["
	STATUS(88, "\"rec\"") "," STATUS(200, "\"live\"") "," STATUS(312, "\"link\"")
	"]},\"strip_display\":{\"widgets\":[" THREE_STRIPS("\"name\",\"db\"") "]}}";

// ---- Views ----

static void set_key(render_key_t *key, render_key_state_t state, const char *word, const char *label) {
	key->state = (uint8_t)state;
	snprintf(key->word, sizeof key->word, "%s", word);
	snprintf(key->label, sizeof key->label, "%s", label);
}

// The pad state R14 draws: REC 00:12:41, LIVE 01:02:13, "Desk wide" on program, "Screen share"
// on preview, and the three channels of the strip drawing.
static render_view_t r14_view(void) {
	render_view_t view;
	memset(&view, 0, sizeof view);
	view.link_ok = true;
	snprintf(view.link, sizeof view.link, "OBS ok");
	view.rec = (render_output_t){true, 12 * 60 + 41};
	view.live = (render_output_t){true, 3600 + 2 * 60 + 13};
	snprintf(view.scene[UI_SCENE_PROGRAM], sizeof view.scene[0], "Desk wide");
	snprintf(view.scene[UI_SCENE_PREVIEW], sizeof view.scene[0], "Screen share");
	set_key(&view.keys[0], RENDER_KEY_IDLE, "SCENE", "Intro card");
	set_key(&view.keys[1], RENDER_KEY_PROGRAM, "SCENE", "Desk wide");
	set_key(&view.keys[2], RENDER_KEY_IDLE, "MUTE", "Mic");
	set_key(&view.keys[3], RENDER_KEY_PREVIEW, "SCENE", "Screen share");
	set_key(&view.keys[4], RENDER_KEY_IDLE, "SCENE", "Guest");
	set_key(&view.keys[5], RENDER_KEY_IDLE, "SCENE", "Game");
	set_key(&view.keys[6], RENDER_KEY_IDLE, "REC", "Record");
	set_key(&view.keys[7], RENDER_KEY_IDLE, "STREAM", "Go live");
	set_key(&view.keys[8], RENDER_KEY_IDLE, "HOTKEY", "Replay save");
	const char *legends[RENDER_BUTTONS] = {"Studio mode", "Cut", "Fade", "Page 2/3"};
	for (int i = 0; i < RENDER_BUTTONS; i++) {
		snprintf(view.legends[i], sizeof view.legends[i], "%s", legends[i]);
	}
	// The peaks span the meter colours: yellow from -20 dB, green below, red from -9 dB.
	view.channels[0] = (render_channel_t){"Mic", -124, -150, false, "mute"};
	view.channels[1] = (render_channel_t){"Desktop", -60, -40, true, "mute"};
	view.channels[2] = (render_channel_t){"Music", -300, -420, false, "mute"};
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

// Each tile in `expected` pushed exactly once, every other tile of the grid not at all.
static void check_pushed(const panel_t *panel, tiles_t expected) {
	int wrong = 0;
	for (int row = 0; row < panel->grid.rows; row++) {
		for (int col = 0; col < panel->grid.cols; col++) {
			wrong += panel->tile_pushes[row][col] != (expected[row][col] ? 1 : 0);
		}
	}
	CHECK(wrong == 0);
	CHECK(!panel->bad_window);
}

static void check_all_pushed_once(const panel_t *panel) {
	tiles_t all;
	memset(all, 1, sizeof all);
	check_pushed(panel, all);
	CHECK(panel->pushes == panel->grid.rows); // a band row of all-dirty tiles is one run
}

static void test_strip_grid_is_cut_to_the_panel(void) {
	ui_grid_t grid = ui_grid(UI_STRIP);
	CHECK(grid.width == STRIP_WIDTH && grid.height == STRIP_HEIGHT);
	CHECK(grid.cols == 9 && grid.rows == 27);
	CHECK((size_t)grid.width * grid.height * 2 == STRIP_FRAME_BYTES && STRIP_FRAME_BYTES == 121552);
}

static void test_strip_first_frame_paints_every_tile_once(void) {
	pad_t *pad = new_pad(STRIP_METERS, UI_STRIP);
	render_view_t view = r14_view();
	show(pad, &view);
	check_all_pushed_once(&pad->panel);
	check_golden("strip_meters", &pad->panel);
	free(pad);
}

static void test_strip_unchanged_view_pushes_nothing(void) {
	pad_t *pad = new_pad(STRIP_FADER, UI_STRIP);
	render_view_t view = r14_view();
	show(pad, &view);
	reset_log(&pad->panel);
	show(pad, &view);
	CHECK(pad->panel.pushes == 0);
	free(pad);
}

// Knob 1 turns down and knob 2 mutes: only the tiles of strips 1 and 2 are pushed, and the frame
// then equals a fresh full paint of the new state.
static void test_strip_level_and_mute_push_only_their_strips(void) {
	pad_t *pad = new_pad(STRIP_FADER, UI_STRIP);
	render_view_t view = r14_view();
	show(pad, &view);
	reset_log(&pad->panel);
	view.channels[1].db_tenths = -180;
	view.channels[1].muted = false;
	view.channels[2].muted = true;
	show(pad, &view);
	tiles_t expected = {{false}};
	expect_rect(expected, (ui_rect_t){0, 144, 142, 140});
	expect_rect(expected, (ui_rect_t){0, 288, 142, 140});
	check_pushed(&pad->panel, expected);
	check_golden("strip_fader", &pad->panel);

	pad_t *fresh = new_pad(STRIP_FADER, UI_STRIP);
	show(fresh, &view);
	CHECK(memcmp(fresh->panel.frame, pad->panel.frame, STRIP_FRAME_BYTES) == 0);
	free(fresh);
	free(pad);
}

// One R14 preset on both panels: each paints whole on the first frame and matches its golden.
static void check_mock_up(const char *doc, const char *main_golden, const char *strip_golden) {
	render_view_t view = r14_view();
	pad_t *main = new_pad(doc, UI_MAIN);
	show(main, &view);
	check_all_pushed_once(&main->panel);
	check_golden(main_golden, &main->panel);
	free(main);
	pad_t *strip = new_pad(doc, UI_STRIP);
	show(strip, &view);
	check_all_pushed_once(&strip->panel);
	check_golden(strip_golden, &strip->panel);
	free(strip);
}

// The pixels of the panel in `rect`, row by row.
static bool same_pixels(const panel_t *a, const panel_t *b, ui_rect_t rect) {
	for (int y = rect.y; y < rect.y + rect.h; y++) {
		size_t at = ((size_t)y * a->grid.width + rect.x) * 2;
		if (memcmp(a->frame + at, b->frame + at, (size_t)rect.w * 2) != 0) {
			return false;
		}
	}
	return true;
}

// Preset B's keys are 72 px tall, so the label line and the PGM or PVW tag share a row. The label
// stops short of the tag: the tag's right part, inside the 8 px inset, is the same with no label.
static void test_key_label_stays_clear_of_its_tag(void) {
	render_view_t labelled = r14_view(), bare = r14_view();
	bare.keys[1].label[0] = '\0';
	bare.keys[3].label[0] = '\0';
	pad_t *with_label = new_pad(R14_ON_AIR, UI_MAIN), *without = new_pad(R14_ON_AIR, UI_MAIN);
	show(with_label, &labelled);
	show(without, &bare);
	CHECK(same_pixels(&with_label->panel, &without->panel, (ui_rect_t){184, 168, 20, 20})); // key 1, PGM
	CHECK(same_pixels(&with_label->panel, &without->panel, (ui_rect_t){76, 244, 20, 20}));  // key 3, PVW
	free(with_label);
	free(without);
}

// Presets A and B share the R14 strip drawing, so both check it against `strip_meters`.
static void test_r14_mock_ups(void) {
	check_mock_up(R14_MIRROR, "r14_mirror", "strip_meters");
	check_mock_up(R14_ON_AIR, "r14_on_air", "strip_meters");
	check_mock_up(R14_IDLE, "r14_idle", "r14_idle_strip");
}

int main(void) {
	test_strip_grid_is_cut_to_the_panel();
	test_strip_first_frame_paints_every_tile_once();
	test_strip_unchanged_view_pushes_nothing();
	test_strip_level_and_mute_push_only_their_strips();
	test_key_label_stays_clear_of_its_tag();
	test_r14_mock_ups();
	if (failures != 0) {
		fprintf(stderr, "test_render_strip: %d failures\n", failures);
		return 1;
	}
	printf("test_render_strip: ok\n");
	return 0;
}
