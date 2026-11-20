// SPDX-License-Identifier: MIT
// The widget model and its tile grid. Every document built here first passes config_validate, so
// the model is tested on documents the pad would store.
#include "ui.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "config.h"

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

// valid_minimal.json with the two widget lists cut out.
static const char DOC_HEAD[] =
	"{\"schema\":1,\"seq\":0,\"obs\":{\"url\":\"ws://10.0.0.2\",\"auth_mode\":\"none\"},\"wifi\":{\"ssid\":\"\"},"
	"\"keys\":[{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},"
	"{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"}],"
	"\"buttons\":[{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"},{\"do\":\"none\"}],"
	"\"knobs\":[{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}},"
	"{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}},"
	"{\"input\":null,\"step_db\":1,\"push\":{\"do\":\"none\"}}],";

typedef struct {
	char bytes[CONFIG_MAX_BYTES];
	size_t len;
} doc_t;

static doc_t document(const char *main_widgets, const char *strip_widgets) {
	doc_t doc;
	int n = snprintf(doc.bytes, sizeof doc.bytes,
	                 "%s\"main_display\":{\"widgets\":[%s]},\"strip_display\":{\"widgets\":[%s]},"
	                 "\"ui\":{\"brightness\":0}}",
	                 DOC_HEAD, main_widgets, strip_widgets);
	if (n < 0 || (size_t)n >= sizeof doc.bytes) {
		fprintf(stderr, "document too long\n");
		exit(2);
	}
	doc.len = (size_t)n;
	return doc;
}

static bool is_valid(const doc_t *doc) {
	return config_validate((const uint8_t *)doc->bytes, doc->len).verdict == CONFIG_VALID;
}

// A model that has drawn `doc`: loaded, then every tile pushed.
static ui_model_t model_showing(const doc_t *doc) {
	ui_model_t model;
	ui_layout_t layouts[UI_DISPLAYS];
	ui_init(&model);
	CHECK(is_valid(doc));
	CHECK(ui_parse(layouts, (const uint8_t *)doc->bytes, doc->len));
	CHECK(ui_apply(&model, layouts));
	ui_clean(&model, UI_MAIN);
	ui_clean(&model, UI_STRIP);
	return model;
}

static bool load(ui_model_t *model, const doc_t *doc) {
	ui_layout_t layouts[UI_DISPLAYS];
	return ui_parse(layouts, (const uint8_t *)doc->bytes, doc->len) && ui_apply(model, layouts);
}

static bool tile_meets(uint16_t col, uint16_t row, ui_rect_t r) {
	unsigned left = col * UI_TILE, top = row * UI_TILE;
	return r.w > 0 && r.h > 0 && left < (unsigned)r.x + r.w && r.x < left + UI_TILE && top < (unsigned)r.y + r.h &&
	       r.y < top + UI_TILE;
}

// True when exactly the tiles that meet one of `rects` are dirty on the display.
static bool dirty_exactly(const ui_model_t *model, ui_display_t display, const ui_rect_t *rects, size_t count) {
	ui_grid_t grid = ui_grid(display);
	for (uint16_t row = 0; row < grid.rows; row++) {
		for (uint16_t col = 0; col < grid.cols; col++) {
			bool expected = false;
			for (size_t i = 0; i < count; i++) {
				expected |= tile_meets(col, row, rects[i]);
			}
			if (ui_tile_dirty(model, display, col, row) != expected) {
				fprintf(stderr, "display %d tile %u,%u\n", (int)display, col, row);
				return false;
			}
		}
	}
	return true;
}

static bool nothing_dirty(const ui_model_t *model) {
	return dirty_exactly(model, UI_MAIN, NULL, 0) && dirty_exactly(model, UI_STRIP, NULL, 0);
}

// ---- Grid ----

static void test_grids_cover_both_panels(void) {
	ui_grid_t main = ui_grid(UI_MAIN), strip = ui_grid(UI_STRIP);
	CHECK(main.width == 320 && main.height == 480 && main.cols == 20 && main.rows == 30);
	CHECK(strip.width == 142 && strip.height == 428 && strip.cols == 9 && strip.rows == 27);
}

static void test_a_new_model_has_every_tile_dirty(void) {
	ui_model_t model;
	ui_init(&model);
	ui_rect_t main_whole = {0, 0, 320, 480}, strip_whole = {0, 0, 142, 428};
	CHECK(dirty_exactly(&model, UI_MAIN, &main_whole, 1));
	CHECK(dirty_exactly(&model, UI_STRIP, &strip_whole, 1));
	CHECK(model.layout[UI_MAIN].count == 0 && model.layout[UI_STRIP].count == 0);
}

static void test_clean_clears_only_its_display(void) {
	ui_model_t model;
	ui_init(&model);
	ui_clean(&model, UI_STRIP);
	ui_rect_t main_whole = {0, 0, 320, 480};
	CHECK(dirty_exactly(&model, UI_MAIN, &main_whole, 1));
	CHECK(dirty_exactly(&model, UI_STRIP, NULL, 0));
}

// ---- Parse ----

static const char FULL_MAIN[] =
	"{\"kind\":\"status\",\"x\":0,\"y\":0,\"w\":320,\"h\":36,\"fields\":[\"live\",\"link\"]},"
	"{\"kind\":\"key\",\"x\":0,\"y\":40,\"w\":104,\"h\":104,\"key\":8},"
	"{\"kind\":\"legend\",\"x\":108,\"y\":40,\"w\":80,\"h\":24,\"button\":3},"
	"{\"kind\":\"scene_line\",\"x\":0,\"y\":148,\"w\":320,\"h\":40,\"scene\":\"preview\",\"size\":\"large\"},"
	"{\"kind\":\"text\",\"x\":0,\"y\":440,\"w\":320,\"h\":40,\"text\":\"T\\u00e9st 1\"}";
static const char FULL_STRIP[] =
	"{\"kind\":\"strip\",\"x\":0,\"y\":0,\"w\":142,\"h\":140,\"knob\":2,\"parts\":[\"push\",\"name\",\"fader\"]}";

static void test_parse_reads_every_field_of_every_kind(void) {
	doc_t doc = document(FULL_MAIN, FULL_STRIP);
	ui_layout_t layouts[UI_DISPLAYS];
	CHECK(is_valid(&doc));
	CHECK(ui_parse(layouts, (const uint8_t *)doc.bytes, doc.len));
	const ui_layout_t *main = &layouts[UI_MAIN];
	CHECK(main->count == 5);
	const ui_widget_t *status = &main->widget[0];
	CHECK(status->kind == UI_KIND_STATUS && status->rect.w == 320 && status->rect.h == 36);
	CHECK(status->item_count == 2 && status->items[0] == UI_FIELD_LIVE && status->items[1] == UI_FIELD_LINK);
	CHECK(main->widget[1].kind == UI_KIND_KEY && main->widget[1].arg == 8 && main->widget[1].rect.y == 40);
	CHECK(main->widget[2].kind == UI_KIND_LEGEND && main->widget[2].arg == 3 && main->widget[2].rect.x == 108);
	const ui_widget_t *scene = &main->widget[3];
	CHECK(scene->kind == UI_KIND_SCENE_LINE && scene->arg == UI_SCENE_PREVIEW && scene->size == UI_SIZE_LARGE);
	const ui_widget_t *text = &main->widget[4];
	CHECK(text->kind == UI_KIND_TEXT && text->rect.y == 440);
	CHECK(text->text_len == 7 && memcmp(text->text, "T\xc3\xa9st 1", 7) == 0);
	const ui_layout_t *strip = &layouts[UI_STRIP];
	CHECK(strip->count == 1 && strip->widget[0].kind == UI_KIND_STRIP && strip->widget[0].arg == 2);
	CHECK(strip->widget[0].item_count == 3 && strip->widget[0].items[0] == UI_PART_PUSH &&
	      strip->widget[0].items[1] == UI_PART_NAME && strip->widget[0].items[2] == UI_PART_FADER);
}

static void test_parse_keeps_the_last_of_a_member_given_twice(void) {
	doc_t doc = document("{\"kind\":\"text\",\"x\":0,\"y\":0,\"w\":40,\"h\":40,\"text\":\"a\",\"text\":\"bc\"}", "");
	ui_layout_t layouts[UI_DISPLAYS];
	CHECK(is_valid(&doc));
	CHECK(ui_parse(layouts, (const uint8_t *)doc.bytes, doc.len));
	CHECK(layouts[UI_MAIN].count == 1 && layouts[UI_MAIN].widget[0].text_len == 2);
	CHECK(strcmp(layouts[UI_MAIN].widget[0].text, "bc") == 0);

	const char twice[] = "{\"main_display\":{\"widgets\":[{\"kind\":\"key\",\"x\":0,\"y\":0,\"w\":30,\"h\":30,\"key\":1},"
	                     "{\"kind\":\"key\",\"x\":40,\"y\":0,\"w\":30,\"h\":30,\"key\":2}]},"
	                     "\"main_display\":{\"widgets\":[{\"kind\":\"legend\",\"x\":0,\"y\":0,\"w\":30,\"h\":30,"
	                     "\"button\":1,\"button\":2}]}}";
	CHECK(ui_parse(layouts, (const uint8_t *)twice, strlen(twice)));
	CHECK(layouts[UI_MAIN].count == 1 && layouts[UI_MAIN].widget[0].kind == UI_KIND_LEGEND);
	CHECK(layouts[UI_MAIN].widget[0].arg == 2 && layouts[UI_MAIN].widget[0].rect.x == 0);
	CHECK(layouts[UI_STRIP].count == 0);
}

// config.c checks only the members of the widget's kind, so the model must take the rest as they come.
static void test_parse_ignores_members_the_kind_does_not_use(void) {
	doc_t doc = document("{\"kind\":\"text\",\"x\":0,\"y\":0,\"w\":40,\"h\":40,\"text\":\"a\",\"key\":9,"
	                     "\"parts\":[\"clock\"],\"size\":7}",
	                     "{\"kind\":\"key\",\"x\":0,\"y\":0,\"w\":40,\"h\":40,\"key\":3,\"text\":"
	                     "\"123456789012345678901234567890123\"}");
	ui_layout_t layouts[UI_DISPLAYS];
	CHECK(is_valid(&doc));
	CHECK(ui_parse(layouts, (const uint8_t *)doc.bytes, doc.len));
	CHECK(layouts[UI_MAIN].widget[0].arg == 0 && layouts[UI_MAIN].widget[0].item_count == 0);
	CHECK(layouts[UI_STRIP].widget[0].arg == 3 && layouts[UI_STRIP].widget[0].text_len == 0);
}

static bool parses(const char *text) {
	ui_layout_t layouts[UI_DISPLAYS];
	return ui_parse(layouts, (const uint8_t *)text, strlen(text));
}

// Documents config_validate refuses. The model never sees one, but none may make it unsafe.
static void test_parse_refuses_what_is_unsafe_to_draw(void) {
	CHECK(parses("{\"main_display\":{\"widgets\":[{\"kind\":\"key\",\"x\":296,\"y\":0,\"w\":24,\"h\":24}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"kind\":\"key\",\"x\":297,\"y\":0,\"w\":24,\"h\":24}]}}"));
	CHECK(!parses("{\"strip_display\":{\"widgets\":[{\"kind\":\"key\",\"x\":0,\"y\":405,\"w\":24,\"h\":24}]}}"));
	CHECK(!parses("{\"strip_display\":{\"widgets\":[{\"x\":0,\"y\":0,\"w\":65536,\"h\":24}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"kind\":\"clock\"}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"kind\":\"key\",\"key\":9}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"kind\":\"legend\",\"button\":4}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"kind\":\"strip\",\"knob\":3}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"x\":1.5}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"x\":-1}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"x\":\"1\"}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"kind\":\"strip\",\"parts\":[\"name\",\"name\",\"db\",\"fader\",\"meter\",\"push\"]}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"kind\":\"status\",\"fields\":[\"clock\"]}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"kind\":\"text\",\"text\":\"123456789012345678901234567890123\"}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{\"kind\":\"scene_line\",\"size\":\"huge\"}]}}"));
	CHECK(!parses("{\"main_display\":{\"widgets\":[{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}]}}"));
	CHECK(parses("{\"main_display\":{\"widgets\":[{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}]}}"));
	CHECK(!parses("{\"main_display\":"));
	CHECK(!parses("[]"));
	CHECK(!parses("not json"));
}

// ---- Overlap: the same index as the validator ----

// The widget index in a validator path that is exactly `<display>.widgets[N]`, else -1.
static int validator_widget(const doc_t *doc, const char *display) {
	config_result_t result = config_validate((const uint8_t *)doc->bytes, doc->len);
	char tail[8];
	int index = -1;
	char pattern[64];
	snprintf(pattern, sizeof pattern, "%s.widgets[%%d%%7s", display);
	if (result.verdict != CONFIG_INVALID || sscanf(result.path, pattern, &index, tail) != 2 || strcmp(tail, "]") != 0) {
		return -1;
	}
	return index;
}

static int model_overlap(const doc_t *doc, ui_display_t display) {
	ui_layout_t layouts[UI_DISPLAYS];
	if (!ui_parse(layouts, (const uint8_t *)doc->bytes, doc->len)) {
		return -2;
	}
	return ui_find_overlap(&layouts[display]);
}

static doc_t read_vector(const char *name) {
	char path[512];
	snprintf(path, sizeof path, "%s/%s", CONFIG_VECTORS, name);
	FILE *f = fopen(path, "rb");
	if (f == NULL) {
		fprintf(stderr, "cannot open %s\n", path);
		exit(2);
	}
	doc_t doc;
	doc.len = fread(doc.bytes, 1, sizeof doc.bytes, f);
	fclose(f);
	return doc;
}

static void test_overlap_vectors_give_the_validator_index(void) {
	doc_t main_pair = read_vector("widgets_overlap.json");
	CHECK(validator_widget(&main_pair, "main_display") == 1);
	CHECK(model_overlap(&main_pair, UI_MAIN) == 1);
	CHECK(model_overlap(&main_pair, UI_STRIP) == -1);

	doc_t strip_three = read_vector("widgets_overlap_on_the_strip.json");
	CHECK(validator_widget(&strip_three, "strip_display") == 2);
	CHECK(model_overlap(&strip_three, UI_STRIP) == 2);
	CHECK(model_overlap(&strip_three, UI_MAIN) == -1);

	const char *valid[] = {"valid_widgets_share_an_edge.json", "valid_sixteen_widgets.json", "valid_full.json"};
	for (size_t i = 0; i < sizeof valid / sizeof valid[0]; i++) {
		doc_t doc = read_vector(valid[i]);
		CHECK(is_valid(&doc));
		CHECK(model_overlap(&doc, UI_MAIN) == -1 && model_overlap(&doc, UI_STRIP) == -1);
	}
}

static void widget_json(char *out, size_t size, ui_rect_t r) {
	snprintf(out, size, "{\"kind\":\"text\",\"x\":%u,\"y\":%u,\"w\":%u,\"h\":%u,\"text\":\"\"}", r.x, r.y, r.w, r.h);
}

// One fixed widget, then a second one at every position near each of its edges: apart, sharing
// an edge, and one pixel over. Both checks must name the same widget, or none.
static int sweep_display(ui_display_t display, ui_rect_t fixed) {
	static const int NEAR[] = {-1, 0, 1};
	static const uint16_t SIDES[] = {24, 49};
	const char *name = display == UI_MAIN ? "main_display" : "strip_display";
	int overlaps = 0;
	for (size_t s = 0; s < sizeof SIDES / sizeof SIDES[0]; s++) {
		uint16_t side = SIDES[s];
		int xs[] = {fixed.x - side, fixed.x, fixed.x + fixed.w};
		int ys[] = {fixed.y - side, fixed.y, fixed.y + fixed.h};
		for (size_t xi = 0; xi < 3 * 3; xi++) {
			for (size_t yi = 0; yi < 3 * 3; yi++) {
				ui_rect_t moved = {(uint16_t)(xs[xi / 3] + NEAR[xi % 3]), (uint16_t)(ys[yi / 3] + NEAR[yi % 3]), side, side};
				char first[96], second[96], both[200];
				widget_json(first, sizeof first, fixed);
				widget_json(second, sizeof second, moved);
				snprintf(both, sizeof both, "%s,%s", first, second);
				doc_t doc = display == UI_MAIN ? document(both, "") : document("", both);
				int expected = validator_widget(&doc, name);
				CHECK(expected == -1 || expected == 1);
				CHECK(expected != -1 || is_valid(&doc));
				CHECK(model_overlap(&doc, display) == expected);
				overlaps += expected == 1;
			}
		}
	}
	return overlaps;
}

static void test_overlap_sweep_agrees_with_the_validator(void) {
	// On each axis 5 of the 9 positions overlap: one pixel over each edge and the 3 at the start.
	CHECK(sweep_display(UI_MAIN, (ui_rect_t){100, 200, 60, 60}) == 2 * 5 * 5);
	CHECK(sweep_display(UI_STRIP, (ui_rect_t){50, 100, 40, 80}) == 2 * 5 * 5);
}

// ---- Dirty tiles ----

#define TEXT_W(text) "{\"kind\":\"text\",\"x\":0,\"y\":440,\"w\":320,\"h\":40,\"text\":\"" text "\"}"
#define KEY_W(x) "{\"kind\":\"key\",\"x\":" #x ",\"y\":40,\"w\":104,\"h\":104,\"key\":0}"
#define STATUS_W "{\"kind\":\"status\",\"x\":0,\"y\":0,\"w\":320,\"h\":36,\"fields\":[\"link\",\"rec\",\"live\"]}"
#define STRIP_W(knob, y, parts) \
	"{\"kind\":\"strip\",\"x\":0,\"y\":" #y ",\"w\":142,\"h\":140,\"knob\":" #knob ",\"parts\":[" parts "]}"
#define STRIPS(first_parts) \
	STRIP_W(0, 0, first_parts) "," STRIP_W(1, 140, "\"name\",\"db\"") "," STRIP_W(2, 280, "\"name\"")

static const ui_rect_t TEXT_RECT = {0, 440, 320, 40};
static const ui_rect_t STRIP0_RECT = {0, 0, 142, 140};

static void test_a_first_load_dirties_its_widgets(void) {
	ui_model_t model;
	ui_init(&model);
	ui_clean(&model, UI_MAIN);
	ui_clean(&model, UI_STRIP);
	doc_t doc = document(KEY_W(8), "");
	CHECK(load(&model, &doc));
	ui_rect_t key = {8, 40, 104, 104};
	CHECK(dirty_exactly(&model, UI_MAIN, &key, 1));
	CHECK(dirty_exactly(&model, UI_STRIP, NULL, 0));
}

static void test_the_same_document_dirties_nothing(void) {
	doc_t doc = document(STATUS_W "," KEY_W(8) "," TEXT_W("Live"), STRIPS("\"name\",\"db\",\"fader\""));
	ui_model_t model = model_showing(&doc);
	CHECK(load(&model, &doc));
	CHECK(nothing_dirty(&model));
}

// Criterion 4b's edit: one `text` widget gets new words, knob 0's strip drops `fader`.
static void test_an_edit_dirties_only_its_widgets_tiles(void) {
	doc_t before = document(STATUS_W "," KEY_W(8) "," TEXT_W("Live"), STRIPS("\"name\",\"db\",\"fader\""));
	doc_t after = document(STATUS_W "," KEY_W(8) "," TEXT_W("Test 1"), STRIPS("\"name\",\"db\""));
	ui_model_t model = model_showing(&before);
	CHECK(is_valid(&after));
	CHECK(load(&model, &after));
	CHECK(dirty_exactly(&model, UI_MAIN, &TEXT_RECT, 1));
	CHECK(dirty_exactly(&model, UI_STRIP, &STRIP0_RECT, 1));
	CHECK(strcmp(model.layout[UI_MAIN].widget[2].text, "Test 1") == 0);
}

static void test_a_moved_widget_dirties_where_it_was_and_where_it_is(void) {
	doc_t before = document(STATUS_W "," KEY_W(8), "");
	doc_t after = document(STATUS_W "," KEY_W(200), "");
	ui_model_t model = model_showing(&before);
	CHECK(load(&model, &after));
	ui_rect_t both[] = {{8, 40, 104, 104}, {200, 40, 104, 104}};
	CHECK(dirty_exactly(&model, UI_MAIN, both, 2));
	CHECK(dirty_exactly(&model, UI_STRIP, NULL, 0));
}

static void test_a_removed_widget_dirties_its_old_tiles(void) {
	doc_t before = document(STATUS_W "," KEY_W(8) "," TEXT_W("Live"), "");
	doc_t after = document(STATUS_W "," TEXT_W("Live"), "");
	ui_model_t model = model_showing(&before);
	CHECK(load(&model, &after));
	ui_rect_t key = {8, 40, 104, 104};
	CHECK(dirty_exactly(&model, UI_MAIN, &key, 1));
	CHECK(model.layout[UI_MAIN].count == 2);
}

static void test_reordered_widgets_dirty_nothing(void) {
	doc_t before = document(STATUS_W "," KEY_W(8) "," TEXT_W("Live"), STRIPS("\"name\""));
	doc_t after = document(TEXT_W("Live") "," STATUS_W "," KEY_W(8), STRIPS("\"name\""));
	ui_model_t model = model_showing(&before);
	CHECK(load(&model, &after));
	CHECK(nothing_dirty(&model));
}

// Criterion 4b: a layout with two overlapping widgets leaves the frames as they were.
static void test_an_overlapping_layout_leaves_the_model_as_it_was(void) {
	doc_t before = document(STATUS_W "," KEY_W(8), "");
	ui_model_t model = model_showing(&before);
	ui_model_t kept;
	memcpy(&kept, &model, sizeof kept);
	const char overlapping[] =
		"{\"main_display\":{\"widgets\":[" STATUS_W "," KEY_W(8) ",{\"kind\":\"key\",\"x\":100,\"y\":100,\"w\":30,"
		"\"h\":30,\"key\":1}]}}";
	ui_layout_t layouts[UI_DISPLAYS];
	CHECK(ui_parse(layouts, (const uint8_t *)overlapping, strlen(overlapping)));
	CHECK(ui_find_overlap(&layouts[UI_MAIN]) == 2);
	CHECK(!ui_apply(&model, layouts));
	CHECK(memcmp(&model, &kept, sizeof model) == 0);
}

int main(void) {
	test_grids_cover_both_panels();
	test_a_new_model_has_every_tile_dirty();
	test_clean_clears_only_its_display();
	test_parse_reads_every_field_of_every_kind();
	test_parse_keeps_the_last_of_a_member_given_twice();
	test_parse_ignores_members_the_kind_does_not_use();
	test_parse_refuses_what_is_unsafe_to_draw();
	test_overlap_vectors_give_the_validator_index();
	test_overlap_sweep_agrees_with_the_validator();
	test_a_first_load_dirties_its_widgets();
	test_the_same_document_dirties_nothing();
	test_an_edit_dirties_only_its_widgets_tiles();
	test_a_moved_widget_dirties_where_it_was_and_where_it_is();
	test_a_removed_widget_dirties_its_old_tiles();
	test_reordered_widgets_dirty_nothing();
	test_an_overlapping_layout_leaves_the_model_as_it_was();
	if (failures != 0) {
		fprintf(stderr, "test_ui: %d failures\n", failures);
		return 1;
	}
	printf("test_ui: ok\n");
	return 0;
}
