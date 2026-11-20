// SPDX-License-Identifier: MIT
// Two passes. The read pass takes the json.h events in document order and keeps, for each field
// the rules name, whether it was there and fit its own rule. The check pass then walks those fields
// in the order of docs/config.md, so the first bad path does not depend on member order.
// A member that appears twice: the last one wins, as in serde_json (vectors duplicate_*).
#include "config.h"

#include <math.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "json.h"

#define KEYS 9
#define BUTTONS 4
#define KNOBS 3
#define WIDGETS_MAX 16
#define WIDGET_SIDE_MIN 24
#define UUID_MAX 36
#define LABEL_MAX 48
#define SSID_MAX 32
#define TEXT_MAX 32
#define STEP_DB_MAX 6.0
#define BRIGHTNESS_MAX 100
#define PORT_MAX 65535u
#define PORT_DIGITS_MAX 5
#define OCTET_DIGITS_MAX 3
#define OCTET_MAX 255u
#define PRINTABLE_FIRST 0x21
#define PRINTABLE_LAST 0x7E
#define WS_PREFIX "ws://"

// ---- Names. Each enum follows the order of its list ----

typedef struct {
	const char *const *names;
	uint8_t count;
} words_t;

#define WORDS_INIT(list) {(list), (uint8_t)(sizeof(list) / sizeof((list)[0]))}
#define WORDS(list) ((words_t)WORDS_INIT(list))

enum { DO_NONE, DO_SCENE, DO_TOGGLE_MUTE, DO_TOGGLE_RECORD, DO_TOGGLE_STREAM, DO_TRANSITION };
static const char *const ACTIONS[] = {"none",          "scene",         "toggle_mute",
                                      "toggle_record", "toggle_stream", "transition"};
enum { KIND_STATUS, KIND_KEY, KIND_LEGEND, KIND_SCENE_LINE, KIND_STRIP, KIND_TEXT };
static const char *const KINDS[] = {"status", "key", "legend", "scene_line", "strip", "text"};
static const char *const AUTH_MODES[] = {"stored", "none"};
static const char *const STATUS_FIELDS[] = {"link", "rec", "live"};
static const char *const STRIP_PARTS[] = {"name", "db", "fader", "meter", "push"};
static const char *const SCENES[] = {"program", "preview"};
static const char *const SIZES[] = {"small", "large"};

// ---- What the read pass keeps ----

typedef enum { FIELD_MISSING, FIELD_OK, FIELD_BAD } field_state_t;

// One leaf. A wrong type and a bad value are both FIELD_BAD: each gives the field's own path.
typedef struct {
	uint8_t state;  // field_state_t
	uint16_t value; // FIELD_OK only: the word's index, or the integer capped at UINT16_MAX
} field_t;

typedef enum { NODE_MISSING, NODE_OBJECT, NODE_NULL, NODE_OTHER } node_t;

typedef struct {
	bool is_list;
	uint16_t count; // every item, also those past the records kept
} list_t;

// A list of names, none twice. The check pass needs only the first bad item.
typedef struct {
	list_t list;
	bool has_bad;
	uint16_t bad_index;
	uint8_t seen; // bit n: the name at index n of its words_t
} word_list_t;

typedef struct {
	field_t uuid, label;
} reference_t;

typedef struct {
	field_t act; // the member `do`
	reference_t ref;
} action_t;

typedef struct {
	node_t node;
	reference_t ref;
} input_t;

typedef struct {
	node_t node;
	action_t action;
} push_t;

typedef struct {
	input_t input;
	field_t step_db;
	push_t push;
} knob_t;

typedef struct {
	field_t kind, x, y, w, h, key, button, knob, scene, size, text;
	word_list_t fields, parts;
} widget_t;

typedef struct {
	node_t node;
	struct {
		list_t list;
		widget_t item[WIDGETS_MAX];
	} widgets;
} display_t;

typedef struct {
	bool root_is_object;
	bool number_out_of_range; // serde_json refuses the whole document for one such number
	field_t schema, seq;
	struct {
		node_t node;
		field_t url, auth_mode;
	} obs;
	struct {
		node_t node;
		field_t ssid;
	} wifi;
	struct {
		list_t list;
		action_t item[KEYS];
	} keys;
	struct {
		list_t list;
		action_t item[BUTTONS];
	} buttons;
	struct {
		list_t list;
		knob_t item[KNOBS];
	} knobs;
	display_t main_display, strip_display;
	struct {
		node_t node;
		field_t brightness;
	} ui;
} doc_t;

// ---- Leaf rules ----

typedef enum { RULE_INTEGER, RULE_STEP_DB, RULE_STRING, RULE_WORD, RULE_UUID, RULE_URL } rule_kind_t;

typedef struct {
	rule_kind_t kind;
	uint64_t min, max; // RULE_INTEGER: the value. RULE_STRING: the length in bytes
	words_t words;     // RULE_WORD
} rule_t;

#define INTEGER_RULE(min, max) {RULE_INTEGER, (min), (max), {0}}
#define STRING_RULE(max) {RULE_STRING, 0, (max), {0}}
#define WORD_RULE(list) {RULE_WORD, 0, 0, WORDS_INIT(list)}
#define POSITION_RULE INTEGER_RULE(0, UINT64_MAX)
#define SIDE_RULE INTEGER_RULE(WIDGET_SIDE_MIN, UINT64_MAX)

static const rule_t SCHEMA_RULE = INTEGER_RULE(CONFIG_SCHEMA_MIN, CONFIG_SCHEMA_MAX);
static const rule_t SEQ_RULE = INTEGER_RULE(0, UINT32_MAX);
static const rule_t URL_RULE = {RULE_URL, 0, 0, {0}};
static const rule_t AUTH_MODE_RULE = WORD_RULE(AUTH_MODES);
static const rule_t SSID_RULE = STRING_RULE(SSID_MAX);
static const rule_t DO_RULE = WORD_RULE(ACTIONS);
static const rule_t UUID_RULE = {RULE_UUID, 0, 0, {0}};
static const rule_t LABEL_RULE = STRING_RULE(LABEL_MAX);
static const rule_t STEP_DB_RULE = {RULE_STEP_DB, 0, 0, {0}};
static const rule_t BRIGHTNESS_RULE = INTEGER_RULE(0, BRIGHTNESS_MAX);

static bool is_digit(char c) {
	return c >= '0' && c <= '9';
}

static field_t fit(bool ok, uint64_t value) {
	if (!ok) {
		return (field_t){.state = FIELD_BAD};
	}
	return (field_t){.state = FIELD_OK, .value = value > UINT16_MAX ? UINT16_MAX : (uint16_t)value};
}

// A JSON number with no sign, fraction or exponent that fits in a u64, as serde_json's as_u64.
static field_t integer_field(const json_event_t *event, uint64_t min, uint64_t max) {
	if (event->kind != JSON_NUMBER) {
		return fit(false, 0);
	}
	uint64_t number = 0;
	for (size_t i = 0; i < event->len; i++) {
		char c = event->text[i];
		if (!is_digit(c) || number > (UINT64_MAX - (uint64_t)(c - '0')) / 10) {
			return fit(false, 0);
		}
		number = number * 10 + (uint64_t)(c - '0');
	}
	return fit(number >= min && number <= max, number);
}

static bool is_whole_string(const json_event_t *event) {
	return event->kind == JSON_STRING && !event->truncated;
}

static field_t word_field(const json_event_t *event, words_t words) {
	for (uint8_t i = 0; is_whole_string(event) && i < words.count; i++) {
		if (strlen(words.names[i]) == event->len && memcmp(words.names[i], event->text, event->len) == 0) {
			return fit(true, i);
		}
	}
	return fit(false, 0);
}

static bool is_printable(const char *text, size_t len) {
	for (size_t i = 0; i < len; i++) {
		if ((uint8_t)text[i] < PRINTABLE_FIRST || (uint8_t)text[i] > PRINTABLE_LAST) {
			return false;
		}
	}
	return true;
}

// Four decimal octets 0..255, no leading zero, nothing else: Rust's Ipv4Addr::from_str.
static bool parse_ipv4(const char *text, size_t len, uint8_t octets[4]) {
	size_t at = 0;
	for (size_t i = 0; i < 4; i++) {
		if (i > 0 && (at >= len || text[at++] != '.')) {
			return false;
		}
		size_t start = at;
		unsigned octet = 0;
		while (at < len && is_digit(text[at]) && at - start < OCTET_DIGITS_MAX) {
			octet = octet * 10 + (unsigned)(text[at++] - '0');
		}
		bool leading_zero = at - start > 1 && text[start] == '0';
		if (at == start || leading_zero || octet > OCTET_MAX) {
			return false;
		}
		octets[i] = (uint8_t)octet;
	}
	return at == len;
}

// RFC 1918 section 3.
static bool is_private(const uint8_t octets[4]) {
	return octets[0] == 10 || (octets[0] == 172 && (octets[1] & 0xF0) == 16) ||
	       (octets[0] == 192 && octets[1] == 168);
}

// 1..65535 in decimal digits, no sign and no leading zero.
static bool is_port(const char *text, size_t len) {
	if (len == 0 || len > PORT_DIGITS_MAX || text[0] == '0') {
		return false;
	}
	unsigned port = 0;
	for (size_t i = 0; i < len; i++) {
		if (!is_digit(text[i])) {
			return false;
		}
		port = port * 10 + (unsigned)(text[i] - '0');
	}
	return port <= PORT_MAX;
}

// `ws://<private IPv4>[:port]` and nothing else. The host ends at the first ':'.
static bool is_private_ws_url(const char *text, size_t len) {
	size_t prefix = strlen(WS_PREFIX);
	if (len < prefix || memcmp(text, WS_PREFIX, prefix) != 0) {
		return false;
	}
	const char *authority = text + prefix;
	size_t authority_len = len - prefix;
	const char *colon = memchr(authority, ':', authority_len);
	size_t host_len = colon == NULL ? authority_len : (size_t)(colon - authority);
	uint8_t octets[4];
	if (!parse_ipv4(authority, host_len, octets) || !is_private(octets)) {
		return false;
	}
	return colon == NULL || is_port(colon + 1, authority_len - host_len - 1);
}

static field_t apply_rule(const rule_t *rule, const json_event_t *event) {
	bool whole = is_whole_string(event);
	switch (rule->kind) {
	case RULE_INTEGER: return integer_field(event, rule->min, rule->max);
	case RULE_WORD: return word_field(event, rule->words);
	case RULE_STRING: // `len` is the whole decoded length, also for a cut string: see on_event
		return fit(event->kind == JSON_STRING && event->len >= rule->min && event->len <= rule->max, 0);
	case RULE_UUID:
		return fit(whole && event->len >= 1 && event->len <= UUID_MAX && is_printable(event->text, event->len), 0);
	case RULE_URL: return fit(whole && is_private_ws_url(event->text, event->len), 0);
	case RULE_STEP_DB: {
		double step = event->kind == JSON_NUMBER ? strtod(event->text, NULL) : 0.0;
		return fit(step > 0.0 && step <= STEP_DB_MAX, 0);
	}
	}
	return fit(false, 0);
}

// ---- The read pass ----

// An event seen from one record: `at` steps of its path lead to the record's own value.
typedef struct {
	const json_event_t *event;
	size_t at;
} cursor_t;

static bool is_value(cursor_t c) {
	return c.at == c.event->depth;
}

static bool is_end(cursor_t c) {
	return c.event->kind == JSON_OBJECT_END || c.event->kind == JSON_LIST_END;
}

static cursor_t step_in(cursor_t c) {
	c.at++;
	return c;
}

// The member name under the record, or NULL: a list step, or a name the reader does not hold.
static const char *member_name(cursor_t c) {
	const json_step_t *step = &c.event->path[c.at];
	return step->in_list ? NULL : step->key;
}

static bool is_member(cursor_t c, const char *name) {
	const char *key = member_name(c);
	return key != NULL && strcmp(key, name) == 0;
}

static void read_field(field_t *field, cursor_t c, const rule_t *rule) {
	if (is_value(c) && !is_end(c)) {
		*field = apply_rule(rule, c.event);
	}
}

static node_t node_of(json_kind_t kind) {
	return kind == JSON_OBJECT_BEGIN ? NODE_OBJECT : kind == JSON_NULL ? NODE_NULL : NODE_OTHER;
}

// True for an event inside the object. A new value for the member clears `record`, which holds
// `node`, so a member that appears twice keeps nothing of the first.
static bool enter_object(node_t *node, void *record, size_t size, cursor_t c) {
	if (!is_value(c)) {
		return *node == NODE_OBJECT;
	}
	if (!is_end(c)) {
		memset(record, 0, size);
		*node = node_of(c.event->kind);
	}
	return false;
}

// True for an event inside the list, whose next step is then an index. Counts the items.
static bool enter_list(list_t *list, void *record, size_t size, cursor_t c) {
	if (is_value(c)) {
		if (!is_end(c)) {
			memset(record, 0, size);
			list->is_list = c.event->kind == JSON_LIST_BEGIN;
		}
		return false;
	}
	if (!list->is_list) {
		return false;
	}
	if (c.at + 1 == c.event->depth && !is_end(c)) {
		list->count = (uint16_t)(c.event->path[c.at].index + 1);
	}
	return true;
}

static uint16_t item_index(cursor_t c) {
	return c.event->path[c.at].index;
}

static void read_word_list(word_list_t *words_seen, cursor_t c, words_t words) {
	bool is_item = enter_list(&words_seen->list, words_seen, sizeof *words_seen, c) &&
	               c.at + 1 == c.event->depth && !is_end(c);
	if (!is_item || words_seen->has_bad) {
		return;
	}
	field_t word = word_field(c.event, words);
	unsigned bit = 1u << word.value;
	if (word.state == FIELD_OK && (words_seen->seen & bit) == 0) {
		words_seen->seen |= (uint8_t)bit;
	} else {
		words_seen->has_bad = true;
		words_seen->bad_index = item_index(c);
	}
}

static void read_reference_member(reference_t *ref, cursor_t c) {
	if (is_member(c, "uuid")) {
		read_field(&ref->uuid, step_in(c), &UUID_RULE);
	} else if (is_member(c, "label")) {
		read_field(&ref->label, step_in(c), &LABEL_RULE);
	}
}

// `c` is at a list item or at an object member's value. An item that is no object keeps nothing.
static void read_action(action_t *action, cursor_t c) {
	if (is_value(c)) {
		return;
	}
	if (is_member(c, "do")) {
		read_field(&action->act, step_in(c), &DO_RULE);
	} else {
		read_reference_member(&action->ref, c);
	}
}

static void read_knob(knob_t *knob, cursor_t c) {
	if (is_value(c)) {
		return;
	}
	cursor_t member = step_in(c);
	if (is_member(c, "input")) {
		if (enter_object(&knob->input.node, &knob->input, sizeof knob->input, member)) {
			read_reference_member(&knob->input.ref, member);
		}
	} else if (is_member(c, "step_db")) {
		read_field(&knob->step_db, member, &STEP_DB_RULE);
	} else if (is_member(c, "push")) {
		if (enter_object(&knob->push.node, &knob->push, sizeof knob->push, member)) {
			read_action(&knob->push.action, member);
		}
	}
}

typedef struct {
	const char *name;
	size_t offset;
	rule_t rule;
} widget_member_t;

static const widget_member_t WIDGET_MEMBERS[] = {
	{"kind", offsetof(widget_t, kind), WORD_RULE(KINDS)},
	{"x", offsetof(widget_t, x), POSITION_RULE},
	{"y", offsetof(widget_t, y), POSITION_RULE},
	{"w", offsetof(widget_t, w), SIDE_RULE},
	{"h", offsetof(widget_t, h), SIDE_RULE},
	{"key", offsetof(widget_t, key), INTEGER_RULE(0, KEYS - 1)},
	{"button", offsetof(widget_t, button), INTEGER_RULE(0, BUTTONS - 1)},
	{"knob", offsetof(widget_t, knob), INTEGER_RULE(0, KNOBS - 1)},
	{"scene", offsetof(widget_t, scene), WORD_RULE(SCENES)},
	{"size", offsetof(widget_t, size), WORD_RULE(SIZES)},
	{"text", offsetof(widget_t, text), STRING_RULE(TEXT_MAX)},
};

static void read_widget(widget_t *widget, cursor_t c) {
	if (is_value(c)) {
		return;
	}
	if (is_member(c, "fields")) {
		read_word_list(&widget->fields, step_in(c), WORDS(STATUS_FIELDS));
		return;
	}
	if (is_member(c, "parts")) {
		read_word_list(&widget->parts, step_in(c), WORDS(STRIP_PARTS));
		return;
	}
	for (size_t i = 0; i < sizeof WIDGET_MEMBERS / sizeof WIDGET_MEMBERS[0]; i++) {
		const widget_member_t *member = &WIDGET_MEMBERS[i];
		if (is_member(c, member->name)) {
			read_field((field_t *)((char *)widget + member->offset), step_in(c), &member->rule);
			return;
		}
	}
}

static void read_display(display_t *display, cursor_t c) {
	if (!enter_object(&display->node, display, sizeof *display, c) || !is_member(c, "widgets")) {
		return;
	}
	cursor_t list = step_in(c);
	if (enter_list(&display->widgets.list, &display->widgets, sizeof display->widgets, list) &&
	    item_index(list) < WIDGETS_MAX) {
		read_widget(&display->widgets.item[item_index(list)], step_in(list));
	}
}

static void read_obs(doc_t *doc, cursor_t c) {
	if (!enter_object(&doc->obs.node, &doc->obs, sizeof doc->obs, c)) {
		return;
	}
	if (is_member(c, "url")) {
		read_field(&doc->obs.url, step_in(c), &URL_RULE);
	} else if (is_member(c, "auth_mode")) {
		read_field(&doc->obs.auth_mode, step_in(c), &AUTH_MODE_RULE);
	}
}

static void read_wifi(doc_t *doc, cursor_t c) {
	if (enter_object(&doc->wifi.node, &doc->wifi, sizeof doc->wifi, c) && is_member(c, "ssid")) {
		read_field(&doc->wifi.ssid, step_in(c), &SSID_RULE);
	}
}

static void read_ui(doc_t *doc, cursor_t c) {
	if (enter_object(&doc->ui.node, &doc->ui, sizeof doc->ui, c) && is_member(c, "brightness")) {
		read_field(&doc->ui.brightness, step_in(c), &BRIGHTNESS_RULE);
	}
}

static void read_keys(doc_t *doc, cursor_t c) {
	if (enter_list(&doc->keys.list, &doc->keys, sizeof doc->keys, c) && item_index(c) < KEYS) {
		read_action(&doc->keys.item[item_index(c)], step_in(c));
	}
}

static void read_buttons(doc_t *doc, cursor_t c) {
	if (enter_list(&doc->buttons.list, &doc->buttons, sizeof doc->buttons, c) && item_index(c) < BUTTONS) {
		read_action(&doc->buttons.item[item_index(c)], step_in(c));
	}
}

static void read_knobs(doc_t *doc, cursor_t c) {
	if (enter_list(&doc->knobs.list, &doc->knobs, sizeof doc->knobs, c) && item_index(c) < KNOBS) {
		read_knob(&doc->knobs.item[item_index(c)], step_in(c));
	}
}

static void read_schema(doc_t *doc, cursor_t c) {
	read_field(&doc->schema, c, &SCHEMA_RULE);
}

static void read_seq(doc_t *doc, cursor_t c) {
	read_field(&doc->seq, c, &SEQ_RULE);
}

static void read_main_display(doc_t *doc, cursor_t c) {
	read_display(&doc->main_display, c);
}

static void read_strip_display(doc_t *doc, cursor_t c) {
	read_display(&doc->strip_display, c);
}

static const struct {
	const char *name;
	void (*read)(doc_t *doc, cursor_t value);
} ROOT_MEMBERS[] = {
	{"schema", read_schema},   {"seq", read_seq},         {"obs", read_obs},
	{"wifi", read_wifi},       {"keys", read_keys},       {"buttons", read_buttons},
	{"knobs", read_knobs},     {"main_display", read_main_display},
	{"strip_display", read_strip_display},                {"ui", read_ui},
};

// The document bytes beside the read pass. `at` is the byte json_feed takes now.
typedef struct {
	doc_t doc;
	const uint8_t *bytes;
	size_t len;
	size_t at;
} reading_t;

static int hex_digit(uint8_t c) {
	if (c >= '0' && c <= '9') {
		return c - '0';
	}
	c = (uint8_t)(c | 0x20);
	return c >= 'a' && c <= 'f' ? c - 'a' + 10 : 0;
}

// UTF-8 bytes of one \uXXXX. A high surrogate counts the whole pair, its low half nothing.
static size_t unit_length(const uint8_t *hex) {
	unsigned unit = 0;
	for (size_t i = 0; i < 4; i++) {
		unit = unit << 4 | (unsigned)hex_digit(hex[i]);
	}
	if (unit >= 0xD800 && unit <= 0xDFFF) {
		return unit < 0xDC00 ? 4 : 0;
	}
	return unit < 0x80 ? 1 : unit < 0x800 ? 2 : 3;
}

// The opening quote of the string that holds byte `at`: the first quote before it that an even
// run of backslashes precedes. Inside a string every quote is escaped.
static size_t string_open(const uint8_t *bytes, size_t at) {
	for (size_t open = at;; open--) {
		size_t slashes = 0;
		while (slashes < open && bytes[open - 1 - slashes] == '\\') {
			slashes++;
		}
		if (bytes[open] == '"' && slashes % 2 == 0) {
			return open;
		}
	}
}

// The decoded length of the string that holds byte `at`, which json.c cut at JSON_STRING_MAX raw
// bytes. A label of 48 bytes can take 288 raw bytes as \u escapes, and Rust takes it (vector
// valid_label_48_escaped_bytes). Bytes past `at` are not checked yet: the verdict stands only if
// the reader ends at JSON_DONE, and then they were.
static size_t cut_string_length(const reading_t *reading) {
	const uint8_t *bytes = reading->bytes;
	size_t decoded = 0;
	size_t at = string_open(bytes, reading->at) + 1;
	while (at < reading->len && bytes[at] != '"') {
		bool unicode = bytes[at] == '\\' && at + 6 <= reading->len && bytes[at + 1] == 'u';
		size_t step = unicode ? 6 : bytes[at] == '\\' ? 2 : 1;
		decoded += unicode ? unit_length(bytes + at + 2) : 1;
		at += step;
	}
	return decoded;
}

static void on_event(void *context, const json_event_t *event) {
	reading_t *reading = context;
	doc_t *doc = &reading->doc;
	if (event->kind == JSON_NUMBER && isinf(strtod(event->text, NULL))) {
		doc->number_out_of_range = true;
	}
	json_event_t whole = *event;
	if (event->kind == JSON_STRING && event->truncated) {
		whole.len = cut_string_length(reading);
	}
	cursor_t root = {&whole, 0};
	if (is_value(root)) {
		doc->root_is_object |= whole.kind == JSON_OBJECT_BEGIN;
		return;
	}
	for (size_t i = 0; i < sizeof ROOT_MEMBERS / sizeof ROOT_MEMBERS[0]; i++) {
		if (is_member(root, ROOT_MEMBERS[i].name)) {
			ROOT_MEMBERS[i].read(doc, step_in(root));
			return;
		}
	}
}

// ---- The check pass: docs/config.md, "Order of the checks and the path" ----

typedef struct {
	char text[CONFIG_PATH_MAX + 1];
} path_t;

static path_t member_path(const char *parent, const char *name) {
	path_t path;
	snprintf(path.text, sizeof path.text, "%s%s%s", parent, parent[0] == '\0' ? "" : ".", name);
	return path;
}

static path_t item_path(const char *parent, unsigned index) {
	path_t path;
	snprintf(path.text, sizeof path.text, "%s[%u]", parent, index);
	return path;
}

static bool refuse(config_result_t *result, path_t path) {
	result->verdict = CONFIG_INVALID;
	memcpy(result->path, path.text, sizeof result->path);
	return false;
}

static bool check_field(const field_t *field, const char *parent, const char *name, config_result_t *result) {
	return field->state == FIELD_OK || refuse(result, member_path(parent, name));
}

static bool check_object(node_t node, const char *parent, const char *name, config_result_t *result) {
	return node == NODE_OBJECT || refuse(result, member_path(parent, name));
}

static bool check_reference(const reference_t *ref, const char *parent, config_result_t *result) {
	return check_field(&ref->uuid, parent, "uuid", result) && check_field(&ref->label, parent, "label", result);
}

// An entry of `keys` or `buttons`.
static bool check_list_action(const action_t *action, const char *parent, config_result_t *result) {
	if (!check_field(&action->act, parent, "do", result)) {
		return false;
	}
	bool needs_ref = action->act.value == DO_SCENE || action->act.value == DO_TOGGLE_MUTE;
	return !needs_ref || check_reference(&action->ref, parent, result);
}

// A knob's `push`: its `toggle_mute` acts on the knob's own input and carries no reference.
static bool check_push(const action_t *action, const char *parent, config_result_t *result) {
	if (!check_field(&action->act, parent, "do", result)) {
		return false;
	}
	return action->act.value != DO_SCENE || check_reference(&action->ref, parent, result);
}

static bool check_count(const list_t *list, size_t min, size_t max, path_t path, config_result_t *result) {
	return (list->is_list && list->count >= min && list->count <= max) || refuse(result, path);
}

static bool check_actions(const list_t *list, const action_t *items, size_t count, const char *name,
                          config_result_t *result) {
	if (!check_count(list, count, count, member_path("", name), result)) {
		return false;
	}
	for (size_t i = 0; i < count; i++) {
		if (!check_list_action(&items[i], item_path(name, (unsigned)i).text, result)) {
			return false;
		}
	}
	return true;
}

static bool check_knob(const knob_t *knob, const char *parent, config_result_t *result) {
	path_t input = member_path(parent, "input");
	if (knob->input.node != NODE_NULL &&
	    !(check_object(knob->input.node, parent, "input", result) && check_reference(&knob->input.ref, input.text, result))) {
		return false;
	}
	return check_field(&knob->step_db, parent, "step_db", result) &&
	       check_object(knob->push.node, parent, "push", result) &&
	       check_push(&knob->push.action, member_path(parent, "push").text, result);
}

static bool check_knobs(const doc_t *doc, config_result_t *result) {
	if (!check_count(&doc->knobs.list, KNOBS, KNOBS, member_path("", "knobs"), result)) {
		return false;
	}
	for (unsigned i = 0; i < KNOBS; i++) {
		if (!check_knob(&doc->knobs.item[i], item_path("knobs", i).text, result)) {
			return false;
		}
	}
	return true;
}

static bool check_word_list(const word_list_t *words_seen, uint8_t max, const char *parent, const char *name,
                            config_result_t *result) {
	path_t list = member_path(parent, name);
	if (!check_count(&words_seen->list, 1, max, list, result)) {
		return false;
	}
	return !words_seen->has_bad || refuse(result, item_path(list.text, words_seen->bad_index));
}

typedef struct {
	const char *name;
	uint32_t width, height;
} panel_t;

static const panel_t MAIN_PANEL = {"main_display", 320, 480};
static const panel_t STRIP_PANEL = {"strip_display", 142, 428};

static bool check_kind_fields(const widget_t *widget, const char *path, config_result_t *result) {
	switch (widget->kind.value) {
	case KIND_STATUS: return check_word_list(&widget->fields, WORDS(STATUS_FIELDS).count, path, "fields", result);
	case KIND_KEY: return check_field(&widget->key, path, "key", result);
	case KIND_LEGEND: return check_field(&widget->button, path, "button", result);
	case KIND_SCENE_LINE:
		return check_field(&widget->scene, path, "scene", result) && check_field(&widget->size, path, "size", result);
	case KIND_STRIP:
		return check_field(&widget->knob, path, "knob", result) &&
		       check_word_list(&widget->parts, WORDS(STRIP_PARTS).count, path, "parts", result);
	case KIND_TEXT:
	default: return check_field(&widget->text, path, "text", result);
	}
}

// Rule 1 on `w` and `h` (their rule), rule 2, then the fields of the kind.
static bool check_widget(const widget_t *widget, panel_t panel, path_t path, config_result_t *result) {
	bool fields = check_field(&widget->kind, path.text, "kind", result) &&
	              check_field(&widget->x, path.text, "x", result) && check_field(&widget->y, path.text, "y", result) &&
	              check_field(&widget->w, path.text, "w", result) && check_field(&widget->h, path.text, "h", result);
	if (!fields) {
		return false;
	}
	// Each value is capped at UINT16_MAX, above every panel side, so the sum cannot wrap.
	bool inside = (uint32_t)widget->x.value + widget->w.value <= panel.width &&
	              (uint32_t)widget->y.value + widget->h.value <= panel.height;
	return (inside || refuse(result, path)) && check_kind_fields(widget, path.text, result);
}

// The argument rule 3 allows once per display, or 0 for a kind that has none.
static uint32_t slot_of(const widget_t *widget) {
	switch (widget->kind.value) {
	case KIND_KEY: return 1u << 16 | widget->key.value;
	case KIND_LEGEND: return 2u << 16 | widget->button.value;
	case KIND_STRIP: return 3u << 16 | widget->knob.value;
	default: return 0;
	}
}

// Rule 4: sharing an edge is not an overlap.
static bool overlaps(const widget_t *a, const widget_t *b) {
	bool across = a->x.value < (uint32_t)b->x.value + b->w.value && b->x.value < (uint32_t)a->x.value + a->w.value;
	bool down = a->y.value < (uint32_t)b->y.value + b->h.value && b->y.value < (uint32_t)a->y.value + a->h.value;
	return across && down;
}

static bool clashes(const widget_t *widget, const widget_t *earlier) {
	uint32_t slot = slot_of(widget);
	return (slot != 0 && slot == slot_of(earlier)) || overlaps(widget, earlier);
}

static bool check_display(const display_t *display, panel_t panel, config_result_t *result) {
	path_t list = member_path(panel.name, "widgets");
	if (!check_object(display->node, "", panel.name, result) ||
	    !check_count(&display->widgets.list, 0, WIDGETS_MAX, list, result)) {
		return false;
	}
	const widget_t *items = display->widgets.item;
	for (unsigned i = 0; i < display->widgets.list.count; i++) {
		path_t path = item_path(list.text, i);
		if (!check_widget(&items[i], panel, path, result)) {
			return false;
		}
		for (unsigned j = 0; j < i; j++) {
			if (clashes(&items[i], &items[j])) {
				return refuse(result, path);
			}
		}
	}
	return true;
}

static bool check_document(const doc_t *doc, config_result_t *result) {
	return check_field(&doc->schema, "", "schema", result) && check_field(&doc->seq, "", "seq", result) &&
	       check_object(doc->obs.node, "", "obs", result) && check_field(&doc->obs.url, "obs", "url", result) &&
	       check_field(&doc->obs.auth_mode, "obs", "auth_mode", result) &&
	       check_object(doc->wifi.node, "", "wifi", result) && check_field(&doc->wifi.ssid, "wifi", "ssid", result) &&
	       check_actions(&doc->keys.list, doc->keys.item, KEYS, "keys", result) &&
	       check_actions(&doc->buttons.list, doc->buttons.item, BUTTONS, "buttons", result) &&
	       check_knobs(doc, result) && check_display(&doc->main_display, MAIN_PANEL, result) &&
	       check_display(&doc->strip_display, STRIP_PANEL, result) &&
	       check_object(doc->ui.node, "", "ui", result) && check_field(&doc->ui.brightness, "ui", "brightness", result);
}

config_result_t config_validate(const uint8_t *doc, size_t len) {
	config_result_t result = {.verdict = CONFIG_VALID};
	if (len > CONFIG_MAX_BYTES) {
		result.verdict = CONFIG_TOO_BIG;
		return result;
	}
	reading_t reading;
	memset(&reading, 0, sizeof reading);
	reading.bytes = doc;
	reading.len = len;
	json_reader_t reader;
	json_reader_init(&reader, on_event, &reading);
	json_status_t status = JSON_MORE;
	for (reading.at = 0; reading.at < len; reading.at++) { // one byte a call, so `at` is exact
		status = json_feed(&reader, doc + reading.at, 1);
	}
	bool one_object = status == JSON_DONE && reading.doc.root_is_object;
	if (!one_object || reading.doc.number_out_of_range) {
		result.verdict = CONFIG_INVALID;
		return result;
	}
	check_document(&reading.doc, &result);
	return result;
}
