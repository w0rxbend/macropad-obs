// SPDX-License-Identifier: MIT
#include "json.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TRACE_CAP 4096
#define FNV_OFFSET 2166136261u
#define FNV_PRIME 16777619u

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

// A string literal with its length, so a document or a trace may hold a NUL byte.
typedef struct {
	const char *bytes;
	size_t len;
} text_t;

#define TEXT(literal) ((text_t){(literal), sizeof(literal) - 1})

// What one parse gave: the last status and every event, one trace line each.
// A line is the path, the kind and the text: `$.keys[2].do s scene`. `S` marks a cut string.
typedef struct {
	json_status_t status;
	size_t events;
	uint32_t hash; // FNV-1a over every trace byte, also the ones past TRACE_CAP
	char trace[TRACE_CAP];
	size_t trace_len;
} run_t;

static void die(const char *what, const char *name) {
	fprintf(stderr, "%s %s\n", what, name);
	exit(2);
}

static void trace_put(run_t *run, const char *bytes, size_t len) {
	for (size_t i = 0; i < len; i++) {
		run->hash = (run->hash ^ (uint8_t)bytes[i]) * FNV_PRIME;
	}
	size_t room = sizeof run->trace - run->trace_len;
	size_t kept = len < room ? len : room;
	memcpy(run->trace + run->trace_len, bytes, kept);
	run->trace_len += kept;
}

static void trace_step(run_t *run, const json_step_t *step) {
	char index[16];
	if (step->in_list) {
		trace_put(run, index, (size_t)snprintf(index, sizeof index, "[%u]", step->index));
	} else if (step->key == NULL) {
		trace_put(run, ".?", 2);
	} else {
		trace_put(run, ".", 1);
		trace_put(run, step->key, strlen(step->key));
	}
}

static void trace_event(void *context, const json_event_t *event) {
	static const char KINDS[] = "{}[]sntfz";
	run_t *run = context;
	run->events++;
	trace_put(run, "$", 1);
	for (size_t i = 0; i < event->depth; i++) {
		trace_step(run, &event->path[i]);
	}
	trace_put(run, " ", 1);
	trace_put(run, event->truncated ? "S" : &KINDS[event->kind], 1);
	if (event->kind == JSON_STRING || event->kind == JSON_NUMBER) {
		trace_put(run, " ", 1);
		trace_put(run, event->text, event->len);
	}
	trace_put(run, "\n", 1);
}

// Feeds a chunk from its own heap block of the exact size. ASan then sees a read past either
// end of a chunk, and a pointer into a chunk that the reader keeps across calls.
static json_status_t feed_copy(json_reader_t *reader, const char *bytes, size_t len) {
	if (len == 0) {
		return json_feed(reader, NULL, 0);
	}
	uint8_t *chunk = malloc(len);
	if (chunk == NULL) {
		die("no memory for", "a chunk");
	}
	memcpy(chunk, bytes, len);
	json_status_t status = json_feed(reader, chunk, len);
	free(chunk);
	return status;
}

// Parses `doc` fed as two chunks: [0, split) and [split, len). The reader sits in its own heap
// block of sizeof(json_reader_t) bytes, so ASan sees any write outside the reader state.
static void parse_split(text_t doc, size_t split, run_t *run) {
	json_reader_t *reader = malloc(sizeof *reader);
	if (reader == NULL) {
		die("no memory for", "a reader");
	}
	memset(run, 0, sizeof *run);
	run->hash = FNV_OFFSET;
	json_reader_init(reader, trace_event, run);
	feed_copy(reader, doc.bytes, split);
	run->status = feed_copy(reader, doc.bytes + split, doc.len - split);
	free(reader);
}

static bool same_run(const run_t *a, const run_t *b) {
	return a->status == b->status && a->events == b->events && a->hash == b->hash &&
	       a->trace_len == b->trace_len && memcmp(a->trace, b->trace, a->trace_len) == 0;
}

static void print_trace(const char *label, const char *bytes, size_t len) {
	fprintf(stderr, "%s:\n", label);
	fwrite(bytes, 1, len, stderr);
}

// Parses `doc` in one chunk and checks the status and the trace. Then checks that a split at
// every byte gives that same run.
static void check_doc(int line, text_t doc, json_status_t status, text_t trace) {
	static run_t whole;
	static run_t split_run;
	parse_split(doc, doc.len, &whole);
	bool as_wanted = whole.status == status && whole.trace_len == trace.len &&
	                 memcmp(whole.trace, trace.bytes, trace.len) == 0;
	if (!as_wanted) {
		fprintf(stderr, "%s:%d: status %d, wanted %d\n", __FILE__, line, whole.status, status);
		print_trace("wanted", trace.bytes, trace.len);
		print_trace("got", whole.trace, whole.trace_len);
		failures++;
	}
	for (size_t split = 0; split < doc.len; split++) {
		parse_split(doc, split, &split_run);
		if (!same_run(&whole, &split_run)) {
			fprintf(stderr, "%s:%d: a split at byte %zu changes the run\n", __FILE__, line, split);
			failures++;
			return;
		}
	}
}

#define CHECK_DOC(doc, status, trace) check_doc(__LINE__, TEXT(doc), status, TEXT(trace))

static void test_each_value_arrives_with_its_kind_path_and_text(void) {
	CHECK_DOC("{\"a\":[1,{\"b\":\"x\"},[],true],\"c\":null,\"d\":{\"e\":false,\"f\":-2.5e3}}",
	          JSON_DONE,
	          "$ {\n"
	          "$.a [\n"
	          "$.a[0] n 1\n"
	          "$.a[1] {\n"
	          "$.a[1].b s x\n"
	          "$.a[1] }\n"
	          "$.a[2] [\n"
	          "$.a[2] ]\n"
	          "$.a[3] t\n"
	          "$.a ]\n"
	          "$.c z\n"
	          "$.d {\n"
	          "$.d.e f\n"
	          "$.d.f n -2.5e3\n"
	          "$.d }\n"
	          "$ }\n");
}

static void test_a_list_root_and_whitespace_parse(void) {
	CHECK_DOC(" \t\r\n[ [ ] , { } , \"\" ]\r\n ",
	          JSON_DONE,
	          "$ [\n"
	          "$[0] [\n"
	          "$[0] ]\n"
	          "$[1] {\n"
	          "$[1] }\n"
	          "$[2] s \n"
	          "$ ]\n");
}

static void test_a_document_cut_short_stays_open(void) {
	CHECK_DOC("", JSON_MORE, "");
	CHECK_DOC("  \n", JSON_MORE, "");
	CHECK_DOC("{\"schema\":1,\"seq\":17,", JSON_MORE, "$ {\n$.schema n 1\n$.seq n 17\n");
	CHECK_DOC("[\"ab", JSON_MORE, "$ [\n");
}

#define BAD_AFTER_LIST_OPENS(doc) CHECK_DOC(doc, JSON_BAD_SYNTAX, "$ [\n")

static void test_string_escapes_decode(void) {
	CHECK_DOC("[\"\\\"\\\\\\/\\b\\f\\n\\r\\t\"]", JSON_DONE, "$ [\n$[0] s \"\\/\b\f\n\r\t\n$ ]\n");
	CHECK_DOC("[\"\\u00e9\\u00E9\\u20AC\"]", JSON_DONE, "$ [\n$[0] s \xC3\xA9\xC3\xA9\xE2\x82\xAC\n$ ]\n");
	CHECK_DOC("[\"\\u007f\\u0080\\u07ff\\u0800\\uffff\"]", JSON_DONE,
	          "$ [\n$[0] s \x7F\xC2\x80\xDF\xBF\xE0\xA0\x80\xEF\xBF\xBF\n$ ]\n");
}

static void test_a_surrogate_pair_decodes_to_one_character(void) {
	CHECK_DOC("[\"\\ud83c\\udfac\"]", JSON_DONE, "$ [\n$[0] s \xF0\x9F\x8E\xAC\n$ ]\n");
	CHECK_DOC("[\"\\ud800\\udc00\\udbff\\udfff\"]", JSON_DONE,
	          "$ [\n$[0] s \xF0\x90\x80\x80\xF4\x8F\xBF\xBF\n$ ]\n");
}

static void test_an_escaped_nul_is_a_byte_of_the_text(void) {
	CHECK_DOC("[\"a\\u0000b\"]", JSON_DONE, "$ [\n$[0] s a\0b\n$ ]\n");
}

static void test_raw_utf8_passes_as_it_is(void) {
	CHECK_DOC("[\"\xD0\x9E\xD0\xB1\xD0\xB7\xD0\xBE\xD1\x80 \xF0\x9F\x8E\xAC\"]", JSON_DONE,
	          "$ [\n$[0] s \xD0\x9E\xD0\xB1\xD0\xB7\xD0\xBE\xD1\x80 \xF0\x9F\x8E\xAC\n$ ]\n");
	// The first and the last code point of each UTF-8 length, and both sides of the surrogates.
	CHECK_DOC("[\"\xC2\x80\xDF\xBF\xE0\xA0\x80\xED\x9F\xBF\xEE\x80\x80\xEF\xBF\xBF"
	          "\xF0\x90\x80\x80\xF4\x8F\xBF\xBF\"]",
	          JSON_DONE,
	          "$ [\n$[0] s \xC2\x80\xDF\xBF\xE0\xA0\x80\xED\x9F\xBF\xEE\x80\x80\xEF\xBF\xBF"
	          "\xF0\x90\x80\x80\xF4\x8F\xBF\xBF\n$ ]\n");
}

static void test_a_bad_escape_is_refused(void) {
	BAD_AFTER_LIST_OPENS("[\"\\x\"]");
	BAD_AFTER_LIST_OPENS("[\"\\u12\"]");
	BAD_AFTER_LIST_OPENS("[\"\\u12G4\"]");
	BAD_AFTER_LIST_OPENS("[\"\\U0041\"]");
}

static void test_a_lone_surrogate_is_refused(void) {
	BAD_AFTER_LIST_OPENS("[\"\\ud83c\"]");
	BAD_AFTER_LIST_OPENS("[\"\\ud83cx\"]");
	BAD_AFTER_LIST_OPENS("[\"\\ud83c\\n\"]");
	BAD_AFTER_LIST_OPENS("[\"\\ud83c\\u0041\"]");
	BAD_AFTER_LIST_OPENS("[\"\\ud83c\\ud83c\"]");
	BAD_AFTER_LIST_OPENS("[\"\\udfac\"]");
}

static void test_a_raw_control_byte_in_a_string_is_refused(void) {
	BAD_AFTER_LIST_OPENS("[\"a\x01\"]");
	BAD_AFTER_LIST_OPENS("[\"a\tb\"]");
	BAD_AFTER_LIST_OPENS("[\"a\nb\"]");
	BAD_AFTER_LIST_OPENS("[\"a\0b\"]");
	BAD_AFTER_LIST_OPENS("[\"\x1F\"]");
}

static void test_bytes_that_are_not_utf8_are_refused(void) {
	BAD_AFTER_LIST_OPENS("[\"\xFF\"]");
	BAD_AFTER_LIST_OPENS("[\"\x80\"]");
	BAD_AFTER_LIST_OPENS("[\"\xC0\x80\"]");
	BAD_AFTER_LIST_OPENS("[\"\xC1\xBF\"]");
	BAD_AFTER_LIST_OPENS("[\"\xE0\x9F\xBF\"]");
	BAD_AFTER_LIST_OPENS("[\"\xED\xA0\x80\"]");
	BAD_AFTER_LIST_OPENS("[\"\xF0\x8F\xBF\xBF\"]");
	BAD_AFTER_LIST_OPENS("[\"\xF4\x90\x80\x80\"]");
	BAD_AFTER_LIST_OPENS("[\"\xF5\x80\x80\x80\"]");
	BAD_AFTER_LIST_OPENS("[\"\xC3\"]");
	BAD_AFTER_LIST_OPENS("[\"\xE2\x82\"]");
	BAD_AFTER_LIST_OPENS("[\"\xE2\x82\x41\"]");
	BAD_AFTER_LIST_OPENS("[\"\xC3\\n\"]");
	// The config vector not_utf8.json.
	CHECK_DOC("{\"schema\":1,\"seq\":17,\"note\":\"\xFF\"}", JSON_BAD_SYNTAX,
	          "$ {\n$.schema n 1\n$.seq n 17\n");
}

// Builds `[" + body + "]` in `doc`, where body is `fill` bytes of 'a' and then `tail`.
static text_t long_string_doc(char *doc, size_t cap, size_t fill, const char *tail) {
	size_t tail_len = strlen(tail);
	if (fill + tail_len + 4 > cap) {
		die("too long for its buffer:", tail);
	}
	doc[0] = '[';
	doc[1] = '"';
	memset(doc + 2, 'a', fill);
	memcpy(doc + 2 + fill, tail, tail_len);
	memcpy(doc + 2 + fill + tail_len, "\"]", 2);
	return (text_t){doc, fill + tail_len + 4};
}

// The trace of `[<one string>]` whose text is `fill` bytes of 'a' then `tail`.
static text_t long_string_trace(char *trace, size_t cap, bool cut, size_t fill, const char *tail) {
	size_t tail_len = strlen(tail);
	int head = snprintf(trace, cap, "$ [\n$[0] %s ", cut ? "S" : "s");
	if (head < 0 || (size_t)head + fill + tail_len + 6 > cap) {
		die("too long for its buffer:", tail);
	}
	size_t len = (size_t)head;
	memset(trace + len, 'a', fill);
	len += fill;
	memcpy(trace + len, tail, tail_len);
	len += tail_len;
	memcpy(trace + len, "\n$ ]\n", 5);
	return (text_t){trace, len + 5};
}

static void check_long_string(int line, size_t fill, const char *tail, json_status_t status,
                              bool cut, size_t kept_fill, const char *kept_tail) {
	char doc[2 * JSON_STRING_MAX];
	char trace[2 * JSON_STRING_MAX];
	text_t doc_text = long_string_doc(doc, sizeof doc, fill, tail);
	text_t wanted = long_string_trace(trace, sizeof trace, cut, kept_fill, kept_tail);
	if (status != JSON_DONE) {
		wanted.len -= 4; // no "$ ]" line
	}
	check_doc(line, doc_text, status, wanted);
}

#define CUT JSON_STRING_MAX

static void test_a_long_string_is_cut_at_its_limit(void) {
	check_long_string(__LINE__, CUT - 1, "", JSON_DONE, false, CUT - 1, "");
	check_long_string(__LINE__, CUT, "", JSON_DONE, true, CUT, "");
	check_long_string(__LINE__, CUT + 40, "", JSON_DONE, true, CUT, "");
	// Escapes count with their raw bytes: "\n" is 2 bytes of the limit and 1 of the text.
	check_long_string(__LINE__, CUT - 2, "\\n", JSON_DONE, true, CUT - 2, "\n");
	check_long_string(__LINE__, CUT - 3, "\\n", JSON_DONE, false, CUT - 3, "\n");
}

static void test_a_cut_drops_a_character_split_at_the_limit(void) {
	check_long_string(__LINE__, CUT - 1, "\xC3\xA9", JSON_DONE, true, CUT - 1, "");
	check_long_string(__LINE__, CUT - 2, "\xE2\x82\xAC", JSON_DONE, true, CUT - 2, "");
	check_long_string(__LINE__, CUT - 3, "\xF0\x9F\x8E\xAC", JSON_DONE, true, CUT - 3, "");
	check_long_string(__LINE__, CUT - 1, "\\n", JSON_DONE, true, CUT - 1, "");
	check_long_string(__LINE__, CUT - 4, "\\u00e9", JSON_DONE, true, CUT - 4, "");
	check_long_string(__LINE__, CUT - 6, "\\u00e9", JSON_DONE, true, CUT - 6, "\xC3\xA9");
	check_long_string(__LINE__, CUT - 6, "\\ud83c\\udfac", JSON_DONE, true, CUT - 6, "");
	check_long_string(__LINE__, CUT - 12, "\\ud83c\\udfac", JSON_DONE, true, CUT - 12,
	                  "\xF0\x9F\x8E\xAC");
}

static void test_bytes_past_the_cut_are_still_checked(void) {
	check_long_string(__LINE__, CUT + 10, "\xFF", JSON_BAD_SYNTAX, true, CUT, "");
	check_long_string(__LINE__, CUT + 10, "\\x", JSON_BAD_SYNTAX, true, CUT, "");
	check_long_string(__LINE__, CUT + 10, "\\ud83c", JSON_BAD_SYNTAX, true, CUT, "");
}

static void test_names_decode_and_each_one_counts_alone(void) {
	CHECK_DOC("{\"a\\u0062\":1,\"\\u00e9\":{\"\\\"\":true},\"a\":[{\"b\":null}]}", JSON_DONE,
	          "$ {\n"
	          "$.ab n 1\n"
	          "$.\xC3\xA9 {\n"
	          "$.\xC3\xA9.\" t\n"
	          "$.\xC3\xA9 }\n"
	          "$.a [\n"
	          "$.a[0] {\n"
	          "$.a[0].b z\n"
	          "$.a[0] }\n"
	          "$.a ]\n"
	          "$ }\n");
}

static void test_a_name_the_reader_cannot_hold_has_no_key(void) {
	// JSON_KEY_MAX (32) bytes fit; 33 do not. A NUL byte does not fit a C string.
	CHECK_DOC("{\"abcdefghijklmnopqrstuvwxyz012345\":1,\"abcdefghijklmnopqrstuvwxyz0123456\":2,"
	          "\"a\\u0000b\":3,\"x\":4}",
	          JSON_DONE,
	          "$ {\n"
	          "$.abcdefghijklmnopqrstuvwxyz012345 n 1\n"
	          "$.? n 2\n"
	          "$.? n 3\n"
	          "$.x n 4\n"
	          "$ }\n");
	char doc[2 * JSON_STRING_MAX];
	memset(doc, 'k', sizeof doc);
	memcpy(doc, "{\"", 2);
	memcpy(doc + 2 + JSON_STRING_MAX, "\":7,\"k\":8}", 10);
	check_doc(__LINE__, (text_t){doc, JSON_STRING_MAX + 12}, JSON_DONE,
	          TEXT("$ {\n$.? n 7\n$.k n 8\n$ }\n"));
}

static void test_numbers_follow_the_json_grammar(void) {
	CHECK_DOC("[0,-0,12,-3.25,1e5,1E+5,2.5e-3,0.0]", JSON_DONE,
	          "$ [\n$[0] n 0\n$[1] n -0\n$[2] n 12\n$[3] n -3.25\n$[4] n 1e5\n$[5] n 1E+5\n"
	          "$[6] n 2.5e-3\n$[7] n 0.0\n$ ]\n");
	BAD_AFTER_LIST_OPENS("[01]");
	BAD_AFTER_LIST_OPENS("[1.]");
	BAD_AFTER_LIST_OPENS("[.5]");
	BAD_AFTER_LIST_OPENS("[-]");
	BAD_AFTER_LIST_OPENS("[+1]");
	BAD_AFTER_LIST_OPENS("[1e]");
	BAD_AFTER_LIST_OPENS("[1e+]");
	BAD_AFTER_LIST_OPENS("[1.2.3]");
	BAD_AFTER_LIST_OPENS("[0x10]");
	BAD_AFTER_LIST_OPENS("[-a]");
	BAD_AFTER_LIST_OPENS("[1\"a\"]");
	BAD_AFTER_LIST_OPENS("[1:2]");
	BAD_AFTER_LIST_OPENS("[NaN]");
	BAD_AFTER_LIST_OPENS("[Infinity]");
	// JSON_NUMBER_MAX (32) bytes is the longest literal.
	CHECK_DOC("[12345678901234567890123456789012]", JSON_DONE,
	          "$ [\n$[0] n 12345678901234567890123456789012\n$ ]\n");
	BAD_AFTER_LIST_OPENS("[123456789012345678901234567890123]");
}

static void test_literals_are_spelled_whole(void) {
	BAD_AFTER_LIST_OPENS("[tru]");
	BAD_AFTER_LIST_OPENS("[truex]");
	BAD_AFTER_LIST_OPENS("[nul]");
	BAD_AFTER_LIST_OPENS("[False]");
}

static void test_a_trailing_comma_is_refused(void) {
	CHECK_DOC("[1,]", JSON_BAD_SYNTAX, "$ [\n$[0] n 1\n");
	CHECK_DOC("[\"a\" , ]", JSON_BAD_SYNTAX, "$ [\n$[0] s a\n");
	CHECK_DOC("[{},]", JSON_BAD_SYNTAX, "$ [\n$[0] {\n$[0] }\n");
	CHECK_DOC("{\"a\":1,}", JSON_BAD_SYNTAX, "$ {\n$.a n 1\n");
	CHECK_DOC("{\"a\":[],\n}", JSON_BAD_SYNTAX, "$ {\n$.a [\n$.a ]\n");
	BAD_AFTER_LIST_OPENS("[,1]");
	BAD_AFTER_LIST_OPENS("[,]");
	CHECK_DOC("[1,,2]", JSON_BAD_SYNTAX, "$ [\n$[0] n 1\n");
}

static void test_broken_structure_is_refused(void) {
	CHECK_DOC("1", JSON_BAD_SYNTAX, "");
	CHECK_DOC("\"a\"", JSON_BAD_SYNTAX, "");
	CHECK_DOC("true", JSON_BAD_SYNTAX, "");
	CHECK_DOC("]", JSON_BAD_SYNTAX, "");
	CHECK_DOC("{\"a\"}", JSON_BAD_SYNTAX, "$ {\n");
	CHECK_DOC("{\"a\":}", JSON_BAD_SYNTAX, "$ {\n");
	CHECK_DOC("{,}", JSON_BAD_SYNTAX, "$ {\n");
	CHECK_DOC("{1:2}", JSON_BAD_SYNTAX, "$ {\n");
	CHECK_DOC("{\"a\" 1}", JSON_BAD_SYNTAX, "$ {\n");
	CHECK_DOC("{\"a\":1 \"b\":2}", JSON_BAD_SYNTAX, "$ {\n$.a n 1\n");
	CHECK_DOC("[1 2]", JSON_BAD_SYNTAX, "$ [\n$[0] n 1\n");
	CHECK_DOC("[}", JSON_BAD_SYNTAX, "$ [\n");
	CHECK_DOC("[\xC3\xA9]", JSON_BAD_SYNTAX, "$ [\n");
}

static void test_only_whitespace_may_follow_the_root(void) {
	CHECK_DOC("[1] \r\n\t", JSON_DONE, "$ [\n$[0] n 1\n$ ]\n");
	CHECK_DOC("[1]]", JSON_BAD_SYNTAX, "$ [\n$[0] n 1\n$ ]\n");
	CHECK_DOC("[1] x", JSON_BAD_SYNTAX, "$ [\n$[0] n 1\n$ ]\n");
	CHECK_DOC("{}{}", JSON_BAD_SYNTAX, "$ {\n$ }\n");
}

// `levels` nested lists around a 0: "[[0]]" for 2.
static text_t nested_lists(char *doc, size_t levels) {
	memset(doc, '[', levels);
	doc[levels] = '0';
	memset(doc + levels + 1, ']', levels);
	return (text_t){doc, 2 * levels + 1};
}

static void test_depth_past_the_stack_is_over_limit(void) {
	char doc[2 * JSON_STACK_DEPTH + 3];
	run_t *run = malloc(sizeof *run);
	if (run == NULL) {
		die("no memory for", "a run");
	}
	parse_split(nested_lists(doc, JSON_STACK_DEPTH), 0, run);
	CHECK(run->status == JSON_DONE);
	parse_split(nested_lists(doc, JSON_STACK_DEPTH + 1), 0, run);
	CHECK(run->status == JSON_OVER_LIMIT);
	// LwJSON reports a list before it finds no room for it.
	CHECK(run->events == JSON_STACK_DEPTH + 1);
	// A member name takes an entry too: 8 objects with a name each fill the stack.
	parse_split(TEXT("{\"a\":{\"a\":{\"a\":{\"a\":{\"a\":{\"a\":{\"a\":{\"a\":1}}}}}}}}"), 0, run);
	CHECK(run->status == JSON_DONE);
	parse_split(TEXT("{\"a\":{\"a\":{\"a\":{\"a\":{\"a\":{\"a\":{\"a\":{\"a\":{}}}}}}}}}"), 0, run);
	CHECK(run->status == JSON_OVER_LIMIT);
	free(run);
}

typedef struct {
	size_t items;
	uint16_t last_index;
} list_count_t;

static void count_items(void *context, const json_event_t *event) {
	list_count_t *count = context;
	if (event->kind == JSON_NUMBER) {
		count->items++;
		count->last_index = event->path[0].index;
	}
}

// A list of `items` zeros, parsed in one chunk. Too long for a split at every byte.
static json_status_t parse_zeros(size_t items, list_count_t *count) {
	size_t len = 2 * items + 1;
	char *doc = malloc(len);
	json_reader_t *reader = malloc(sizeof *reader);
	if (doc == NULL || reader == NULL) {
		die("no memory for", "a long list");
	}
	for (size_t i = 0; i < items; i++) {
		doc[2 * i] = i == 0 ? '[' : ',';
		doc[2 * i + 1] = '0';
	}
	doc[len - 1] = ']';
	*count = (list_count_t){0};
	json_reader_init(reader, count_items, count);
	json_status_t status = json_feed(reader, (const uint8_t *)doc, len);
	free(reader);
	free(doc);
	return status;
}

static void test_a_list_past_its_count_is_over_limit(void) {
	list_count_t count;
	CHECK(parse_zeros(JSON_LIST_MAX, &count) == JSON_DONE);
	CHECK(count.items == JSON_LIST_MAX && count.last_index == JSON_LIST_MAX - 1);
	CHECK(parse_zeros(JSON_LIST_MAX + 1, &count) == JSON_OVER_LIMIT);
	CHECK(count.items == JSON_LIST_MAX);
}

// Counts the events whose path has the shape of `pattern`.
typedef struct {
	const char *pattern;
	size_t matches;
} path_count_t;

static void count_matches(void *context, const json_event_t *event) {
	path_count_t *count = context;
	count->matches += json_path_is(event, count->pattern);
}

static size_t matches(const char *doc, const char *pattern) {
	path_count_t count = {pattern, 0};
	json_reader_t reader;
	json_reader_init(&reader, count_matches, &count);
	CHECK(json_feed(&reader, (const uint8_t *)doc, strlen(doc)) == JSON_DONE);
	return count.matches;
}

static void test_a_path_pattern_names_members_and_any_index(void) {
	const char *doc = "{\"d\":{\"scenes\":[{\"sceneName\":\"A\"},{\"sceneName\":\"B\"}]},\"x\":[[1,2],[3]],"
	                  "\"a.b\":5,\"\":6,\"abcdefghijklmnopqrstuvwxyz0123456\":7}";
	CHECK(matches(doc, "") == 2); // the root's begin and end
	CHECK(matches(doc, "d.scenes[].sceneName") == 2);
	CHECK(matches(doc, "d.scenes[]") == 4);
	CHECK(matches(doc, "d.scenes") == 2);
	CHECK(matches(doc, "x[][]") == 3);
	CHECK(matches(doc, "x[]") == 4);
	CHECK(matches("[[1],2]", "[]") == 3);
	CHECK(matches("[[1],2]", "[][]") == 1);
	CHECK(matches("[{\"n\":1}]", "[].n") == 1);
	// No match for a name with '.' or '[', an empty name, a name the reader does not hold, an
	// index written out, or a pattern with a stray separator.
	CHECK(matches(doc, "a.b") == 0);
	CHECK(matches(doc, ".") == 0);
	CHECK(matches(doc, "abcdefghijklmnopqrstuvwxyz0123456") == 0);
	CHECK(matches(doc, "abcdefghijklmnopqrstuvwxyz012345") == 0);
	CHECK(matches(doc, "x[0][]") == 0);
	CHECK(matches(doc, "d..scenes") == 0);
	CHECK(matches(doc, ".d") == 0);
	CHECK(matches(doc, "d.") == 0);
	CHECK(matches(doc, "d.scenes[") == 0);
	CHECK(matches(doc, "d.scenes.sceneName") == 0);
	CHECK(matches(doc, "d.scenes[]sceneName") == 0);
}

// ---- The OBS fixtures: 500 scenes (75 kB) and 500 inputs (114 kB) in one reply each ----

#define FIXTURE_ITEMS 500
#define NAME_PAD_BYTES 64

static text_t read_fixture(const char *name) {
	char path[512];
	snprintf(path, sizeof path, "%s/%s", FIXTURES, name);
	FILE *file = fopen(path, "rb");
	if (file == NULL) {
		die("cannot open", path);
	}
	static char bytes[256 * 1024];
	size_t len = fread(bytes, 1, sizeof bytes, file);
	bool whole = feof(file) && !ferror(file);
	fclose(file);
	if (!whole) {
		die("cannot read all of", path);
	}
	return (text_t){bytes, len};
}

// Keeps the name of each list item that `pattern` picks.
typedef struct {
	const char *pattern;
	size_t count;
	char names[FIXTURE_ITEMS][JSON_STRING_MAX + 1];
	bool in_order;
} names_t;

static void keep_names(void *context, const json_event_t *event) {
	names_t *names = context;
	if (event->kind != JSON_STRING || !json_path_is(event, names->pattern)) {
		return;
	}
	uint16_t index = event->path[event->depth - 2].index;
	names->in_order = names->in_order && index == names->count;
	if (index < FIXTURE_ITEMS && !event->truncated) {
		memcpy(names->names[index], event->text, event->len + 1);
	}
	names->count++;
}

static void check_fixture_names(const char *file, const char *pattern, const char *word) {
	text_t doc = read_fixture(file);
	static names_t names;
	names = (names_t){.pattern = pattern, .in_order = true};
	json_reader_t *reader = malloc(sizeof *reader);
	if (reader == NULL) {
		die("no memory for", "a reader");
	}
	json_reader_init(reader, keep_names, &names);
	CHECK(json_feed(reader, (const uint8_t *)doc.bytes, doc.len) == JSON_DONE);
	free(reader);
	CHECK(names.count == FIXTURE_ITEMS && names.in_order);
	char wanted[NAME_PAD_BYTES + 1];
	for (size_t i = 0; i < FIXTURE_ITEMS; i++) {
		if (i == 7 || i == 42 || i == 123 || i == 250) {
			continue;
		}
		int len = snprintf(wanted, sizeof wanted, "%s %03zu ", word, i);
		memset(wanted + len, '-', NAME_PAD_BYTES - (size_t)len);
		wanted[NAME_PAD_BYTES] = '\0';
		CHECK(strcmp(names.names[i], wanted) == 0);
	}
	CHECK(strcmp(names.names[7], "Cam \"7\" \\ wide") == 0);
	CHECK(strcmp(names.names[42], "\xD0\xA1\xD1\x86\xD0\xB5\xD0\xBD\xD0\xB0 42") == 0);
	CHECK(strcmp(names.names[123], "Intro \xF0\x9F\x8E\xAC") == 0);
	CHECK(strcmp(names.names[250], "Bell \x07 tab\t") == 0);
}

static void test_the_500_item_fixtures_parse(void) {
	check_fixture_names("obs_500_scenes.json", "d.responseData.scenes[].sceneName", "Scene");
	check_fixture_names("obs_500_inputs.json", "d.responseData.inputs[].inputName", "Input");
}

// Parses `doc` fed in chunks of `chunk` bytes.
static void parse_chunks(text_t doc, size_t chunk, run_t *run) {
	json_reader_t *reader = malloc(sizeof *reader);
	if (reader == NULL) {
		die("no memory for", "a reader");
	}
	memset(run, 0, sizeof *run);
	run->hash = FNV_OFFSET;
	json_reader_init(reader, trace_event, run);
	for (size_t at = 0; at < doc.len; at += chunk) {
		size_t len = doc.len - at < chunk ? doc.len - at : chunk;
		run->status = feed_copy(reader, doc.bytes + at, len);
	}
	free(reader);
}

// One byte per chunk puts a chunk end after every byte at once. The two-chunk splits below
// then sample the boundaries: a split at every byte of a 100 kB reply takes too long here.
static void check_fixture_splits(const char *file) {
	static run_t whole;
	static run_t other;
	text_t doc = read_fixture(file);
	parse_split(doc, doc.len, &whole);
	CHECK(whole.status == JSON_DONE);
	parse_chunks(doc, 1, &other);
	CHECK(same_run(&whole, &other));
	parse_chunks(doc, 7, &other);
	CHECK(same_run(&whole, &other));
	for (size_t split = 0; split < doc.len; split += 997) {
		parse_split(doc, split, &other);
		CHECK(same_run(&whole, &other));
	}
}

static void test_a_split_in_a_fixture_changes_nothing(void) {
	check_fixture_splits("obs_500_scenes.json");
	check_fixture_splits("obs_500_inputs.json");
}

int main(void) {
	test_each_value_arrives_with_its_kind_path_and_text();
	test_a_list_root_and_whitespace_parse();
	test_a_document_cut_short_stays_open();
	test_string_escapes_decode();
	test_a_surrogate_pair_decodes_to_one_character();
	test_an_escaped_nul_is_a_byte_of_the_text();
	test_raw_utf8_passes_as_it_is();
	test_a_bad_escape_is_refused();
	test_a_lone_surrogate_is_refused();
	test_a_raw_control_byte_in_a_string_is_refused();
	test_bytes_that_are_not_utf8_are_refused();
	test_a_long_string_is_cut_at_its_limit();
	test_a_cut_drops_a_character_split_at_the_limit();
	test_bytes_past_the_cut_are_still_checked();
	test_names_decode_and_each_one_counts_alone();
	test_a_name_the_reader_cannot_hold_has_no_key();
	test_numbers_follow_the_json_grammar();
	test_literals_are_spelled_whole();
	test_a_trailing_comma_is_refused();
	test_broken_structure_is_refused();
	test_only_whitespace_may_follow_the_root();
	test_depth_past_the_stack_is_over_limit();
	test_a_list_past_its_count_is_over_limit();
	test_a_path_pattern_names_members_and_any_index();
	test_the_500_item_fixtures_parse();
	test_a_split_in_a_fixture_changes_nothing();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	printf("json: all tests pass\n");
	return 0;
}
