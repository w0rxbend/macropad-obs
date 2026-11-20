// SPDX-License-Identifier: MIT
// LwJSON finds the structure. This file adds what LwJSON leaves out: it checks each string byte
// for UTF-8 and escapes, decodes strings and names in place, checks number literals, refuses a
// trailing comma and a list longer than JSON_LIST_MAX, and turns the LwJSON stack into a path.
#include "json.h"

#include <string.h>

// The bounded RAM of a parse: every byte the reader keeps between two json_feed calls.
_Static_assert(sizeof(json_reader_t) <= 1024, "json_reader_t grew past its RAM cap");
_Static_assert(JSON_STACK_DEPTH <= 32, "unheld_keys has one bit per stack entry");

#define HIGH_SURROGATE_FIRST 0xD800u
#define LOW_SURROGATE_FIRST 0xDC00u
#define LOW_SURROGATE_LAST 0xDFFFu
#define UTF8_CONTINUATION_FIRST 0x80u
#define UTF8_CONTINUATION_LAST 0xBFu
#define ESCAPE_LEN 2               // \n
#define UNICODE_ESCAPE_LEN 6       // é
#define SURROGATE_PAIR_ESCAPE_LEN 12 // 🎬

static bool is_space(uint8_t byte) {
	return byte == ' ' || byte == '\t' || byte == '\r' || byte == '\n';
}

static bool is_digit(uint8_t byte) {
	return byte >= '0' && byte <= '9';
}

// -1 when `byte` is not a hex digit.
static int hex_value(uint8_t byte) {
	if (is_digit(byte)) {
		return byte - '0';
	}
	if (byte >= 'a' && byte <= 'f') {
		return byte - 'a' + 10;
	}
	if (byte >= 'A' && byte <= 'F') {
		return byte - 'A' + 10;
	}
	return -1;
}

static bool is_high_surrogate(uint32_t unit) {
	return unit >= HIGH_SURROGATE_FIRST && unit < LOW_SURROGATE_FIRST;
}

static bool is_low_surrogate(uint32_t unit) {
	return unit >= LOW_SURROGATE_FIRST && unit <= LOW_SURROGATE_LAST;
}

// ---- The string check: one byte at a time, so it does not care where a chunk ends ----

typedef struct {
	uint8_t left; // continuation bytes
	uint8_t low;  // the range of the first continuation byte (RFC 3629 section 4)
	uint8_t high;
} utf8_lead_t;

// False when `byte` cannot open a UTF-8 sequence of two bytes or more.
static bool utf8_lead(uint8_t byte, utf8_lead_t *lead) {
	if (byte >= 0xC2 && byte <= 0xDF) {
		*lead = (utf8_lead_t){1, UTF8_CONTINUATION_FIRST, UTF8_CONTINUATION_LAST};
	} else if (byte == 0xE0) {
		*lead = (utf8_lead_t){2, 0xA0, UTF8_CONTINUATION_LAST};
	} else if (byte == 0xED) { // no encoded surrogate
		*lead = (utf8_lead_t){2, UTF8_CONTINUATION_FIRST, 0x9F};
	} else if (byte >= 0xE1 && byte <= 0xEF) {
		*lead = (utf8_lead_t){2, UTF8_CONTINUATION_FIRST, UTF8_CONTINUATION_LAST};
	} else if (byte == 0xF0) {
		*lead = (utf8_lead_t){3, 0x90, UTF8_CONTINUATION_LAST};
	} else if (byte >= 0xF1 && byte <= 0xF3) {
		*lead = (utf8_lead_t){3, UTF8_CONTINUATION_FIRST, UTF8_CONTINUATION_LAST};
	} else if (byte == 0xF4) { // nothing past U+10FFFF
		*lead = (utf8_lead_t){3, UTF8_CONTINUATION_FIRST, 0x8F};
	} else {
		return false;
	}
	return true;
}

static bool take_unit(json_text_check_t *text) {
	uint16_t unit = text->unit;
	if (text->high != 0) {
		text->high = 0;
		return is_low_surrogate(unit);
	}
	if (is_high_surrogate(unit)) {
		text->high = unit;
		return true;
	}
	return !is_low_surrogate(unit);
}

static bool take_escape(json_text_check_t *text, uint8_t byte) {
	text->escaped = false;
	if (byte == 'u') {
		text->hex_left = 4;
		text->unit = 0;
		return true;
	}
	// A high surrogate takes only \u next.
	return text->high == 0 && byte != '\0' && strchr("\"\\/bfnrt", byte) != NULL;
}

// False when `byte` cannot come next in a JSON string. The closing quote counts as a string byte:
// it is refused while an escape, a surrogate pair or a UTF-8 sequence is still open.
static bool text_take(json_text_check_t *text, uint8_t byte) {
	if (text->utf8_left > 0) {
		bool in_range = byte >= text->utf8_low && byte <= text->utf8_high;
		text->utf8_left--;
		text->utf8_low = UTF8_CONTINUATION_FIRST;
		text->utf8_high = UTF8_CONTINUATION_LAST;
		return in_range;
	}
	if (text->hex_left > 0) {
		int value = hex_value(byte);
		if (value < 0) {
			return false;
		}
		text->unit = (uint16_t)(text->unit << 4 | value);
		return --text->hex_left > 0 || take_unit(text);
	}
	if (text->escaped) {
		return take_escape(text, byte);
	}
	if (byte == '\\') {
		text->escaped = true;
		return true;
	}
	if (text->high != 0 || byte < 0x20) {
		return false;
	}
	if (byte < 0x80) {
		return true;
	}
	utf8_lead_t lead;
	if (!utf8_lead(byte, &lead)) {
		return false;
	}
	text->utf8_left = lead.left;
	text->utf8_low = lead.low;
	text->utf8_high = lead.high;
	return true;
}

// ---- Decoding in place. The bytes passed text_take, so only the end can be cut short ----

static size_t utf8_length(uint8_t lead) {
	return lead < 0x80 ? 1 : lead < 0xE0 ? 2 : lead < 0xF0 ? 3 : 4;
}

static uint32_t hex4(const char *digits) {
	uint32_t unit = 0;
	for (size_t i = 0; i < 4; i++) {
		unit = unit << 4 | (uint32_t)hex_value((uint8_t)digits[i]);
	}
	return unit;
}

static size_t put_utf8(char *out, uint32_t code) {
	if (code < 0x80) {
		out[0] = (char)code;
		return 1;
	}
	if (code < 0x800) {
		out[0] = (char)(0xC0 | code >> 6);
		out[1] = (char)(0x80 | (code & 0x3F));
		return 2;
	}
	if (code < 0x10000) {
		out[0] = (char)(0xE0 | code >> 12);
		out[1] = (char)(0x80 | (code >> 6 & 0x3F));
		out[2] = (char)(0x80 | (code & 0x3F));
		return 3;
	}
	out[0] = (char)(0xF0 | code >> 18);
	out[1] = (char)(0x80 | (code >> 12 & 0x3F));
	out[2] = (char)(0x80 | (code >> 6 & 0x3F));
	out[3] = (char)(0x80 | (code & 0x3F));
	return 4;
}

static char simple_escape(char letter) {
	switch (letter) {
	case 'b': return '\b';
	case 'f': return '\f';
	case 'n': return '\n';
	case 'r': return '\r';
	case 't': return '\t';
	default: return letter; // '"', '\\' and '/'
	}
}

// Decodes the escape at `raw` into `out`. Returns the raw bytes it took, or 0 when the escape
// does not fit in the `left` raw bytes.
static size_t decode_escape(const char *raw, size_t left, char *out, size_t *written) {
	if (left < ESCAPE_LEN) {
		return 0;
	}
	if (raw[1] != 'u') {
		*out = simple_escape(raw[1]);
		*written = 1;
		return ESCAPE_LEN;
	}
	if (left < UNICODE_ESCAPE_LEN) {
		return 0;
	}
	uint32_t code = hex4(raw + 2);
	size_t taken = UNICODE_ESCAPE_LEN;
	if (is_high_surrogate(code)) {
		if (left < SURROGATE_PAIR_ESCAPE_LEN) {
			return 0;
		}
		uint32_t low = hex4(raw + UNICODE_ESCAPE_LEN + 2);
		code = 0x10000 + ((code - HIGH_SURROGATE_FIRST) << 10) + (low - LOW_SURROGATE_FIRST);
		taken = SURROGATE_PAIR_ESCAPE_LEN;
	}
	*written = put_utf8(out, code);
	return taken;
}

// Decodes `len` raw string bytes in place, drops a character cut at the end, adds a NUL byte and
// returns the decoded length. Each step writes no more bytes than it reads, so `out` never
// passes `in`.
static size_t decode_in_place(char *text, size_t len) {
	size_t in = 0;
	size_t out = 0;
	while (in < len) {
		size_t taken;
		size_t written;
		if (text[in] == '\\') {
			taken = decode_escape(text + in, len - in, text + out, &written);
		} else {
			taken = utf8_length((uint8_t)text[in]);
			taken = in + taken <= len ? taken : 0;
			written = taken;
			memmove(text + out, text + in, taken);
		}
		if (taken == 0) {
			break;
		}
		in += taken;
		out += written;
	}
	text[out] = '\0';
	return out;
}

// ---- Numbers: RFC 8259 section 6. LwJSON takes any run of bytes up to a separator ----

static size_t skip_digits(const char *text, size_t at, size_t len) {
	while (at < len && is_digit((uint8_t)text[at])) {
		at++;
	}
	return at;
}

static bool is_number(const char *text, size_t len) {
	size_t at = 0;
	if (at < len && text[at] == '-') {
		at++;
	}
	if (at < len && text[at] == '0') {
		at++;
	} else if (at < len && is_digit((uint8_t)text[at])) {
		at = skip_digits(text, at, len);
	} else {
		return false;
	}
	if (at < len && text[at] == '.') {
		size_t digits = at + 1;
		at = skip_digits(text, digits, len);
		if (at == digits) {
			return false;
		}
	}
	if (at < len && (text[at] == 'e' || text[at] == 'E')) {
		at++;
		if (at < len && (text[at] == '+' || text[at] == '-')) {
			at++;
		}
		size_t digits = at;
		at = skip_digits(text, digits, len);
		if (at == digits) {
			return false;
		}
	}
	return at == len;
}

// ---- Events ----

// Turns the LwJSON stack into the steps of `path` and returns their count.
static size_t path_from_stack(const json_reader_t *reader, json_step_t *path) {
	const lwjson_stream_parser_t *parser = &reader->parser;
	size_t depth = 0;
	for (size_t i = 0; i < parser->stack_pos; i++) {
		const lwjson_stream_stack_t *entry = &parser->stack[i];
		if (entry->type == LWJSON_STREAM_TYPE_ARRAY) {
			path[depth++] = (json_step_t){.in_list = true, .index = entry->meta.index};
		} else if (entry->type == LWJSON_STREAM_TYPE_KEY) {
			bool held = (reader->unheld_keys & (UINT32_C(1) << i)) == 0;
			path[depth++] = (json_step_t){.key = held ? entry->meta.name : NULL};
		}
	}
	return depth;
}

static bool is_end(json_kind_t kind) {
	return kind == JSON_OBJECT_END || kind == JSON_LIST_END;
}

static void send_event(json_reader_t *reader, json_event_t *event) {
	json_step_t path[JSON_STACK_DEPTH];
	event->path = path;
	event->depth = path_from_stack(reader, path);
	json_step_t *last = event->depth == 0 ? NULL : &path[event->depth - 1];
	if (last != NULL && last->in_list) {
		if (is_end(event->kind)) {
			// LwJSON counts the closed value into its list before it reports the end.
			last->index--;
		} else if (last->index == JSON_LIST_MAX) {
			// One more item would wrap the LwJSON count.
			reader->status = JSON_OVER_LIMIT;
			return;
		}
	}
	reader->sink(reader->context, event);
}

static void send_plain(json_reader_t *reader, json_kind_t kind) {
	send_event(reader, &(json_event_t){.kind = kind, .text = ""});
}

static void send_text(json_reader_t *reader, json_kind_t kind, const char *text, size_t len,
                      bool truncated) {
	json_event_t event = {.kind = kind, .text = text, .len = len, .truncated = truncated};
	send_event(reader, &event);
}

// LwJSON hands a string over in parts of JSON_STRING_MAX raw bytes, then the rest at the quote.
// The first part of a long string is its event; the parts after it are dropped.
static void take_string(json_reader_t *reader) {
	lwjson_stream_parser_t *parser = &reader->parser;
	bool whole = parser->data.str.is_last;
	if (reader->text.cut) {
		return;
	}
	reader->text.cut = !whole;
	size_t len = decode_in_place(parser->data.str.buff, parser->data.str.buff_pos);
	send_text(reader, JSON_STRING, parser->data.str.buff, len, !whole);
}

// A member name. LwJSON copies `buff_pos` bytes of the buffer into the stack entry it pushes
// next, so the decoded name goes there. A name that does not fit whole is marked unheld.
static void take_key(json_reader_t *reader) {
	lwjson_stream_parser_t *parser = &reader->parser;
	if (!parser->data.str.is_last) {
		reader->text.cut = true;
		return;
	}
	bool held = !reader->text.cut;
	if (held) {
		char *name = parser->data.str.buff;
		size_t len = decode_in_place(name, parser->data.str.buff_pos);
		parser->data.str.buff_pos = len;
		held = len <= JSON_KEY_MAX && memchr(name, '\0', len) == NULL;
	}
	uint32_t bit = UINT32_C(1) << parser->stack_pos; // the entry LwJSON pushes next
	reader->unheld_keys = held ? reader->unheld_keys & ~bit : reader->unheld_keys | bit;
}

static void take_number(json_reader_t *reader) {
	const char *text = reader->parser.data.prim.buff;
	size_t len = reader->parser.data.prim.buff_pos;
	if (!is_number(text, len)) {
		reader->status = JSON_BAD_SYNTAX;
		return;
	}
	send_text(reader, JSON_NUMBER, text, len, false);
}

static void on_token(lwjson_stream_parser_t *parser, lwjson_stream_type_t type) {
	json_reader_t *reader = lwjson_stream_get_user_data(parser);
	if (reader->status != JSON_MORE) {
		return;
	}
	switch (type) {
	case LWJSON_STREAM_TYPE_OBJECT: send_plain(reader, JSON_OBJECT_BEGIN); break;
	case LWJSON_STREAM_TYPE_OBJECT_END: send_plain(reader, JSON_OBJECT_END); break;
	case LWJSON_STREAM_TYPE_ARRAY: send_plain(reader, JSON_LIST_BEGIN); break;
	case LWJSON_STREAM_TYPE_ARRAY_END: send_plain(reader, JSON_LIST_END); break;
	case LWJSON_STREAM_TYPE_KEY: take_key(reader); break;
	case LWJSON_STREAM_TYPE_STRING: take_string(reader); break;
	case LWJSON_STREAM_TYPE_NUMBER: take_number(reader); break;
	case LWJSON_STREAM_TYPE_TRUE: send_plain(reader, JSON_TRUE); break;
	case LWJSON_STREAM_TYPE_FALSE: send_plain(reader, JSON_FALSE); break;
	case LWJSON_STREAM_TYPE_NULL: send_plain(reader, JSON_NULL); break;
	default: break;
	}
}

// ---- Feeding ----

void json_reader_init(json_reader_t *reader, json_sink_fn sink, void *context) {
	memset(reader, 0, sizeof *reader);
	lwjson_stream_init(&reader->parser, on_token);
	lwjson_stream_set_user_data(&reader->parser, reader);
	reader->sink = sink;
	reader->context = context;
	reader->status = JSON_MORE;
}

static json_status_t status_of(lwjsonr_t parsed) {
	switch (parsed) {
	case lwjsonSTREAMWAITFIRSTCHAR:
	case lwjsonSTREAMINPROG: return JSON_MORE;
	case lwjsonSTREAMDONE: return JSON_DONE;
	case lwjsonERRMEM: return JSON_OVER_LIMIT;
	default: return JSON_BAD_SYNTAX;
	}
}

// A byte outside every string. LwJSON takes "[1,]" and "{\"a\":1,}": this refuses them.
static bool take_structure_byte(json_reader_t *reader, uint8_t byte) {
	if (is_space(byte)) {
		return true;
	}
	bool closes = byte == ']' || byte == '}';
	if (closes && reader->after_comma) {
		return false;
	}
	reader->after_comma = byte == ',';
	return true;
}

static bool in_string(const json_reader_t *reader) {
	return reader->parser.parse_state == LWJSON_STREAM_STATE_PARSING_STRING;
}

static void feed_byte(json_reader_t *reader, uint8_t byte) {
	if (reader->status == JSON_DONE) {
		if (!is_space(byte)) {
			reader->status = JSON_BAD_SYNTAX;
		}
		return;
	}
	bool was_in_string = in_string(reader);
	bool fits = was_in_string ? text_take(&reader->text, byte) : take_structure_byte(reader, byte);
	if (!fits) {
		reader->status = JSON_BAD_SYNTAX;
		return;
	}
	json_status_t parsed = status_of(lwjson_stream_parse(&reader->parser, (char)byte));
	// A fault the sink side found in this byte comes first.
	if (reader->status == JSON_MORE) {
		reader->status = parsed;
	}
	if (!was_in_string && in_string(reader)) {
		memset(&reader->text, 0, sizeof reader->text);
	}
}

json_status_t json_feed(json_reader_t *reader, const uint8_t *bytes, size_t len) {
	for (size_t i = 0; i < len && reader->status <= JSON_DONE; i++) {
		feed_byte(reader, bytes[i]);
	}
	return reader->status;
}

// ---- Paths ----

// Matches one member name of `pattern` at `*at` against `key`, and moves `*at` past it.
static bool take_name(const char *pattern, size_t *at, const char *key) {
	size_t start = *at;
	size_t end = start + strcspn(pattern + start, ".[");
	*at = end;
	size_t len = end - start;
	return key != NULL && len > 0 && len <= JSON_KEY_MAX && strlen(key) == len &&
	       memcmp(key, pattern + start, len) == 0;
}

bool json_path_is(const json_event_t *event, const char *pattern) {
	size_t at = 0;
	for (size_t i = 0; i < event->depth; i++) {
		const json_step_t *step = &event->path[i];
		if (strncmp(pattern + at, "[]", 2) == 0) {
			if (!step->in_list) {
				return false;
			}
			at += 2;
			continue;
		}
		if (at > 0) {
			if (pattern[at] != '.') {
				return false;
			}
			at++;
		}
		if (step->in_list || !take_name(pattern, &at, step->key)) {
			return false;
		}
	}
	return pattern[at] == '\0';
}
