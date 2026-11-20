// SPDX-License-Identifier: MIT
// A scripted stream for the host tests: the test queues what the server says, picks how many
// bytes one recv may give, and reads back what the client sent.
#pragma once

#include "stream.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Room for a 75 kB obs-websocket reply (R05) and its frame head, each way.
#define FAKE_STREAM_CAP (80 * 1024)

typedef struct {
	stream_t stream; // first, so a fake_stream_t * is a stream_t *
	stream_status_t open_result;
	stream_status_t send_result;
	bool is_open;
	uint8_t ip[4];
	uint16_t port;
	int close_calls;
	size_t read_size;   // the most bytes one recv gives
	bool hang_up;       // once the queue is read, recv reports STREAM_CLOSED
	uint8_t from_server[FAKE_STREAM_CAP];
	size_t from_server_len;
	size_t from_server_pos;
	uint8_t sent[FAKE_STREAM_CAP];
	size_t sent_len;
} fake_stream_t;

// Open and send succeed; recv gives at most `read_size` bytes at a time.
void fake_stream_init(fake_stream_t *fake, size_t read_size);

// Queues bytes for recv. Aborts the test run past FAKE_STREAM_CAP.
void fake_stream_queue(fake_stream_t *fake, const void *bytes, size_t len);
