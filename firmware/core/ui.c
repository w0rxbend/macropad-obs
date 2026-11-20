// SPDX-License-Identifier: MIT
// Two steps, as in config.c. The read step keeps each widget member the json.h events give, and
// marks one it cannot hold. The finish step then takes only the members of the widget's kind, so
// member order does not matter and a member the kind does not use is ignored, as config.c does.
#include "ui.h"

#include <string.h>

#include "json.h"

typedef struct {
	uint16_t width, height;
} panel_t;

// docs/config.md "Layout names".
static const panel_t PANELS[UI_DISPLAYS] = {{320, 480}, {142, 428}};
static const char *const DISPLAY_NAMES[UI_DISPLAYS] = {"main_display", "strip_display"};

typedef struct {
	const char *const *names;
	uint8_t count;
} words_t;

#define WORDS(list) {(list), (uint8_t)(sizeof(list) / sizeof((list)[0]))}

static const char *const KINDS[] = {"status", "key", "legend", "scene_line", "strip", "text"};
static const char *const STATUS_FIELDS[] = {"link", "rec", "live"};
static const char *const STRIP_PARTS[] = {"name", "db", "fader", "meter", "push"};
static const char *const SCENES[] = {"program", "preview"};
static const char *const SIZES[] = {"small", "large"};

// The counts of docs/config.md "Fields": an argument lies below its count.
#define KEYS 9
#define BUTTONS 4
#define KNOBS 3

// Members before M_TEXT hold a number: an integer, or a word's index.
enum { M_KIND, M_X, M_Y, M_W, M_H, M_KEY, M_BUTTON, M_KNOB, M_SCENE, M_SIZE, M_TEXT, M_FIELDS, M_PARTS, M_COUNT };
static const char *const MEMBER_NAMES[M_COUNT] = {"kind", "x",     "y",    "w",    "h",      "key",  "button",
                                                  "knob", "scene", "size", "text", "fields", "parts"};
// A word member has its list here. The other number members are integers.
static const words_t MEMBER_WORDS[M_TEXT] = {[M_KIND] = WORDS(KINDS), [M_SCENE] = WORDS(SCENES), [M_SIZE] = WORDS(SIZES)};
static const words_t LIST_WORDS[] = {WORDS(STATUS_FIELDS), WORDS(STRIP_PARTS)}; // M_FIELDS, M_PARTS

typedef struct {
	uint8_t count;
	uint8_t items[UI_ITEMS_MAX];
} word_list_t;

typedef struct {
	uint16_t unreadable; // bit m: member m is there and holds nothing the model can keep
	uint16_t number[M_TEXT];
	uint8_t text_len;
	char text[UI_TEXT_MAX + 1];
	word_list_t lists[2]; // M_FIELDS, M_PARTS
} member_values_t;

typedef struct {
	bool root_is_object;
	bool too_many;
	uint8_t count[UI_DISPLAYS];
	member_values_t widget[UI_DISPLAYS][UI_WIDGETS_MAX];
} reading_t;

// ---- Grid ----

ui_grid_t ui_grid(ui_display_t display) {
	panel_t panel = PANELS[display];
	return (ui_grid_t){panel.width, panel.height, (uint16_t)((panel.width + UI_TILE - 1) / UI_TILE),
	                   (uint16_t)((panel.height + UI_TILE - 1) / UI_TILE)};
}

// Clipped to the grid, so no rectangle writes past the display's bits.
void ui_mark(ui_model_t *model, ui_display_t display, ui_rect_t rect) {
	ui_grid_t grid = ui_grid(display);
	if (rect.w == 0 || rect.h == 0 || rect.x >= grid.width || rect.y >= grid.height) {
		return;
	}
	unsigned last_col = ((unsigned)rect.x + rect.w - 1) / UI_TILE;
	unsigned last_row = ((unsigned)rect.y + rect.h - 1) / UI_TILE;
	last_col = last_col < grid.cols ? last_col : grid.cols - 1u;
	last_row = last_row < grid.rows ? last_row : grid.rows - 1u;
	for (unsigned row = rect.y / UI_TILE; row <= last_row; row++) {
		for (unsigned col = rect.x / UI_TILE; col <= last_col; col++) {
			unsigned bit = row * grid.cols + col;
			model->dirty[display][bit / 8] |= (uint8_t)(1u << (bit % 8));
		}
	}
}

void ui_init(ui_model_t *model) {
	memset(model, 0, sizeof *model);
	for (int display = 0; display < UI_DISPLAYS; display++) {
		ui_grid_t grid = ui_grid((ui_display_t)display);
		ui_mark(model, (ui_display_t)display, (ui_rect_t){0, 0, grid.width, grid.height});
	}
}

bool ui_tile_dirty(const ui_model_t *model, ui_display_t display, uint16_t col, uint16_t row) {
	ui_grid_t grid = ui_grid(display);
	if (col >= grid.cols || row >= grid.rows) {
		return false;
	}
	unsigned bit = (unsigned)row * grid.cols + col;
	return (model->dirty[display][bit / 8] >> (bit % 8) & 1u) != 0;
}

void ui_clean(ui_model_t *model, ui_display_t display) {
	memset(model->dirty[display], 0, sizeof model->dirty[display]);
}

// ---- The read step ----

static bool is_end(const json_event_t *event) {
	return event->kind == JSON_OBJECT_END || event->kind == JSON_LIST_END;
}

static bool is_member(const json_step_t *step, const char *name) {
	return !step->in_list && step->key != NULL && strcmp(step->key, name) == 0;
}

static int display_of(const json_step_t *step) {
	for (int display = 0; display < UI_DISPLAYS; display++) {
		if (is_member(step, DISPLAY_NAMES[display])) {
			return display;
		}
	}
	return -1;
}

static int member_of(const json_step_t *step) {
	for (int member = 0; member < M_COUNT; member++) {
		if (is_member(step, MEMBER_NAMES[member])) {
			return member;
		}
	}
	return -1;
}

// A JSON integer 0..UINT16_MAX: digits only, no sign, fraction or exponent.
static bool read_integer(const json_event_t *event, uint16_t *number) {
	if (event->kind != JSON_NUMBER) {
		return false;
	}
	uint32_t value = 0;
	for (size_t i = 0; i < event->len; i++) {
		char c = event->text[i];
		if (c < '0' || c > '9') {
			return false;
		}
		value = value * 10 + (uint32_t)(c - '0');
		if (value > UINT16_MAX) {
			return false;
		}
	}
	*number = (uint16_t)value;
	return true;
}

static bool read_word(const json_event_t *event, words_t words, uint16_t *index) {
	if (event->kind != JSON_STRING || event->truncated) {
		return false;
	}
	for (uint8_t i = 0; i < words.count; i++) {
		if (strlen(words.names[i]) == event->len && memcmp(words.names[i], event->text, event->len) == 0) {
			*index = i;
			return true;
		}
	}
	return false;
}

static bool read_text(member_values_t *values, const json_event_t *event) {
	if (event->kind != JSON_STRING || event->truncated || event->len > UI_TEXT_MAX) {
		return false;
	}
	memcpy(values->text, event->text, event->len);
	values->text[event->len] = '\0';
	values->text_len = (uint8_t)event->len;
	return true;
}

static bool read_value(member_values_t *values, int member, const json_event_t *event) {
	if (member == M_FIELDS || member == M_PARTS) {
		values->lists[member - M_FIELDS].count = 0;
		return event->kind == JSON_LIST_BEGIN;
	}
	if (member == M_TEXT) {
		return read_text(values, event);
	}
	words_t words = MEMBER_WORDS[member];
	return words.count == 0 ? read_integer(event, &values->number[member])
	                        : read_word(event, words, &values->number[member]);
}

// A member that appears again replaces the first: its mark goes with its value.
static void read_member(member_values_t *values, int member, const json_event_t *event) {
	uint16_t bit = (uint16_t)(1u << member);
	values->unreadable &= (uint16_t)~bit;
	if (!read_value(values, member, event)) {
		values->unreadable |= bit;
	}
}

static void read_list_item(member_values_t *values, int member, const json_event_t *event) {
	uint16_t bit = (uint16_t)(1u << member);
	word_list_t *list = &values->lists[member - M_FIELDS];
	uint16_t index = event->path[4].index, word = 0;
	if ((values->unreadable & bit) != 0) {
		return;
	}
	if (index >= UI_ITEMS_MAX || !read_word(event, LIST_WORDS[member - M_FIELDS], &word)) {
		values->unreadable |= bit;
		return;
	}
	list->items[index] = (uint8_t)word;
	list->count = (uint8_t)(index + 1);
}

// An event at depth 4 or 5 under one widget: a member's value, or an item of `fields` or `parts`.
static void read_widget_event(member_values_t *values, const json_event_t *event) {
	int member = member_of(&event->path[3]);
	if (member < 0) {
		return;
	}
	if (event->depth == 4) {
		read_member(values, member, event);
	} else if (event->depth == 5 && (member == M_FIELDS || member == M_PARTS) && event->path[4].in_list) {
		read_list_item(values, member, event);
	}
}

// A new value for the display, or for its `widgets`, drops what the first one held.
static void on_event(void *context, const json_event_t *event) {
	reading_t *reading = context;
	if (event->depth == 0) {
		reading->root_is_object |= event->kind == JSON_OBJECT_BEGIN;
		return;
	}
	int display = display_of(&event->path[0]);
	if (display < 0 || is_end(event)) {
		return;
	}
	if (event->depth == 1 || (event->depth == 2 && is_member(&event->path[1], "widgets"))) {
		reading->count[display] = 0;
		return;
	}
	if (event->depth == 2 || !is_member(&event->path[1], "widgets") || !event->path[2].in_list) {
		return;
	}
	uint16_t index = event->path[2].index;
	if (index >= UI_WIDGETS_MAX) {
		reading->too_many = true;
		return;
	}
	member_values_t *values = &reading->widget[display][index];
	if (event->depth == 3) {
		memset(values, 0, sizeof *values);
		reading->count[display] = (uint8_t)(index + 1);
		return;
	}
	read_widget_event(values, event);
}

// ---- The finish step ----

static bool readable(const member_values_t *values, int member) {
	return (values->unreadable & (1u << member)) == 0;
}

static bool take_arg(const member_values_t *values, int member, uint8_t count, ui_widget_t *widget) {
	widget->arg = (uint8_t)values->number[member];
	return readable(values, member) && values->number[member] < count;
}

static bool take_list(const member_values_t *values, int member, ui_widget_t *widget) {
	const word_list_t *list = &values->lists[member - M_FIELDS];
	widget->item_count = list->count;
	memcpy(widget->items, list->items, sizeof widget->items);
	return readable(values, member);
}

static bool take_kind_members(const member_values_t *values, ui_widget_t *widget) {
	switch (widget->kind) {
	case UI_KIND_STATUS: return take_list(values, M_FIELDS, widget);
	case UI_KIND_KEY: return take_arg(values, M_KEY, KEYS, widget);
	case UI_KIND_LEGEND: return take_arg(values, M_BUTTON, BUTTONS, widget);
	case UI_KIND_SCENE_LINE:
		widget->size = (uint8_t)values->number[M_SIZE];
		return take_arg(values, M_SCENE, MEMBER_WORDS[M_SCENE].count, widget) && readable(values, M_SIZE);
	case UI_KIND_STRIP: return take_arg(values, M_KNOB, KNOBS, widget) && take_list(values, M_PARTS, widget);
	case UI_KIND_TEXT:
	default:
		widget->text_len = values->text_len;
		memcpy(widget->text, values->text, sizeof widget->text);
		return readable(values, M_TEXT);
	}
}

static bool finish_widget(const member_values_t *values, panel_t panel, ui_widget_t *widget) {
	for (int member = M_KIND; member <= M_H; member++) {
		if (!readable(values, member)) {
			return false;
		}
	}
	memset(widget, 0, sizeof *widget);
	widget->kind = (uint8_t)values->number[M_KIND];
	widget->rect = (ui_rect_t){values->number[M_X], values->number[M_Y], values->number[M_W], values->number[M_H]};
	bool inside = (unsigned)widget->rect.x + widget->rect.w <= panel.width &&
	              (unsigned)widget->rect.y + widget->rect.h <= panel.height;
	return inside && take_kind_members(values, widget);
}

bool ui_parse(ui_layout_t layouts[UI_DISPLAYS], const uint8_t *doc, size_t len) {
	reading_t reading;
	memset(&reading, 0, sizeof reading);
	json_reader_t reader;
	json_reader_init(&reader, on_event, &reading);
	if (json_feed(&reader, doc, len) != JSON_DONE || !reading.root_is_object || reading.too_many) {
		return false;
	}
	for (int display = 0; display < UI_DISPLAYS; display++) {
		layouts[display].count = reading.count[display];
		for (uint8_t i = 0; i < reading.count[display]; i++) {
			if (!finish_widget(&reading.widget[display][i], PANELS[display], &layouts[display].widget[i])) {
				return false;
			}
		}
	}
	return true;
}

// ---- Overlap and dirty tiles ----

// Rule 4 of docs/config.md: sharing an edge is not an overlap.
static bool overlaps(ui_rect_t a, ui_rect_t b) {
	return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

int ui_find_overlap(const ui_layout_t *layout) {
	for (int later = 1; later < layout->count; later++) {
		for (int earlier = 0; earlier < later; earlier++) {
			if (overlaps(layout->widget[later].rect, layout->widget[earlier].rect)) {
				return later;
			}
		}
	}
	return -1;
}

static bool same_rect(ui_rect_t a, ui_rect_t b) {
	return a.x == b.x && a.y == b.y && a.w == b.w && a.h == b.h;
}

static bool same_widget(const ui_widget_t *a, const ui_widget_t *b) {
	return a->kind == b->kind && same_rect(a->rect, b->rect) && a->arg == b->arg && a->size == b->size &&
	       a->item_count == b->item_count && memcmp(a->items, b->items, a->item_count) == 0 &&
	       a->text_len == b->text_len && memcmp(a->text, b->text, a->text_len) == 0;
}

static bool holds(const ui_layout_t *layout, const ui_widget_t *widget) {
	for (uint8_t i = 0; i < layout->count; i++) {
		if (same_widget(&layout->widget[i], widget)) {
			return true;
		}
	}
	return false;
}

// Marks the tiles of each widget of `from` that `to` does not hold.
static void mark_gone(ui_model_t *model, ui_display_t display, const ui_layout_t *from, const ui_layout_t *to) {
	for (uint8_t i = 0; i < from->count; i++) {
		if (!holds(to, &from->widget[i])) {
			ui_mark(model, display, from->widget[i].rect);
		}
	}
}

bool ui_apply(ui_model_t *model, const ui_layout_t layouts[UI_DISPLAYS]) {
	for (int display = 0; display < UI_DISPLAYS; display++) {
		if (ui_find_overlap(&layouts[display]) >= 0) {
			return false;
		}
	}
	for (int display = 0; display < UI_DISPLAYS; display++) {
		ui_layout_t *shown = &model->layout[display];
		mark_gone(model, (ui_display_t)display, shown, &layouts[display]);
		mark_gone(model, (ui_display_t)display, &layouts[display], shown);
		*shown = layouts[display];
	}
	return true;
}
