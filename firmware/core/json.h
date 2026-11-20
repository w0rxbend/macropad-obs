// SPDX-License-Identifier: MIT
// Streaming JSON reader over the LwJSON v1.10.1 stream parser. Pure C, no SDK headers, no heap.
// The whole state is one json_reader_t: a 90 kB OBS reply costs the same RAM as a 40-byte one.
// Feed the bytes in any chunks. The events do not depend on where a chunk ends.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "lwjson/lwjson.h"

// Limits. third_party/lwjson/lwjson_opts.h sets the first four.
// Each object, each member name and each list on the way down to a value takes one stack entry.
#define JSON_STACK_DEPTH LWJSON_CFG_STREAM_STACK_SIZE
#define JSON_KEY_MAX LWJSON_CFG_STREAM_KEY_MAX_LEN
#define JSON_STRING_MAX LWJSON_CFG_STREAM_STRING_MAX_LEN
#define JSON_NUMBER_MAX LWJSON_CFG_STREAM_PRIMITIVE_MAX_LEN
// LwJSON counts list items in a uint16_t. The reader stops before that count wraps.
#define JSON_LIST_MAX 65535

// Every status but JSON_MORE is final: later bytes do not change it and give no event.
typedef enum {
	JSON_MORE, // no fault so far and the root is still open: feed more bytes
	JSON_DONE, // the root closed. Whitespace may follow, nothing else
	// Not one JSON document in UTF-8 (RFC 8259). Also refused: a root that is not an object or
	// a list, and a number literal longer than JSON_NUMBER_MAX bytes.
	JSON_BAD_SYNTAX,
	JSON_OVER_LIMIT, // deeper than JSON_STACK_DEPTH, or a list longer than JSON_LIST_MAX
} json_status_t;

typedef enum {
	JSON_OBJECT_BEGIN,
	JSON_OBJECT_END,
	JSON_LIST_BEGIN,
	JSON_LIST_END,
	JSON_STRING,
	JSON_NUMBER,
	JSON_TRUE,
	JSON_FALSE,
	JSON_NULL,
} json_kind_t;

// One step on the way from the root to a value.
typedef struct {
	bool in_list;    // true: `index` is the place in a list. false: `key` is a member name
	uint16_t index;  // counts from 0
	const char *key; // decoded. NULL for a name the reader does not hold: see json_path_is
} json_step_t;

// What the sink gets. Every pointer is good only until the sink returns.
typedef struct {
	json_kind_t kind;
	const json_step_t *path; // `depth` steps, root first. A begin and its end carry the same path
	size_t depth;            // 0 for the root itself
	// JSON_STRING: the decoded bytes, checked UTF-8. `\u0000` decodes to a NUL byte, so count
	// with `len`. JSON_NUMBER: the literal as written, checked against the JSON grammar.
	// Any other kind: empty. A NUL byte follows the last byte in each case.
	const char *text;
	size_t len;
	// JSON_STRING only. The string took JSON_STRING_MAX bytes or more in the JSON text. `text`
	// is what its first JSON_STRING_MAX bytes decode to, cut back to a whole character.
	bool truncated;
} json_event_t;

// Events arrive before the reader knows the document is whole. Act on them at JSON_DONE.
typedef void (*json_sink_fn)(void *context, const json_event_t *event);

// The check of the string being read. Reset when a string opens.
typedef struct {
	bool escaped;      // the byte before was a backslash that opens an escape
	bool cut;          // the string reached JSON_STRING_MAX bytes: its event has gone
	uint8_t hex_left;  // hex digits a \uXXXX still needs
	uint16_t unit;     // the \uXXXX value read so far
	uint16_t high;     // a high surrogate that waits for its low half, else 0
	uint8_t utf8_left; // continuation bytes the open UTF-8 sequence still needs
	uint8_t utf8_low;  // the range the next continuation byte must be in
	uint8_t utf8_high;
} json_text_check_t;

// Do not copy a reader after json_reader_init: it holds a pointer to itself.
typedef struct {
	lwjson_stream_parser_t parser;
	json_sink_fn sink;
	void *context;
	json_status_t status;
	uint32_t unheld_keys; // bit n: the name in stack entry n is not the whole decoded name
	bool after_comma;     // the last byte outside a string and outside whitespace was ','
	json_text_check_t text;
} json_reader_t;

// Starts a reader for one document. `sink` gets each event with `context`.
void json_reader_init(json_reader_t *reader, json_sink_fn sink, void *context);

// Takes the next bytes of the document and returns the status after the last of them. A document
// that ends while the status is JSON_MORE is cut short: the caller knows where its bytes end.
json_status_t json_feed(json_reader_t *reader, const uint8_t *bytes, size_t len);

// True when the event's path has the shape of `pattern`: member names joined by '.', and "[]"
// for any list index. "d.responseData.scenes[].sceneName" has five steps; "" is the root.
// A name never matches when it is empty, holds '.', '[' or a NUL byte, or is longer than
// JSON_KEY_MAX bytes. Read `path` for those, and for the index.
bool json_path_is(const json_event_t *event, const char *pattern);
