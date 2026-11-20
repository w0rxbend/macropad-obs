// SPDX-License-Identifier: MIT
#include "fake_stream.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static fake_stream_t *as_fake(stream_t *stream) {
	return (fake_stream_t *)stream;
}

static stream_status_t fake_open(stream_t *stream, const uint8_t ip[4], uint16_t port) {
	fake_stream_t *fake = as_fake(stream);
	memcpy(fake->ip, ip, sizeof fake->ip);
	fake->port = port;
	fake->is_open = fake->open_result == STREAM_OK;
	return fake->open_result;
}

static stream_status_t fake_send(stream_t *stream, const uint8_t *bytes, size_t len) {
	fake_stream_t *fake = as_fake(stream);
	if (!fake->is_open) {
		return STREAM_CLOSED;
	}
	if (fake->send_result != STREAM_OK) {
		return fake->send_result;
	}
	if (len > FAKE_STREAM_CAP - fake->sent_len) {
		fprintf(stderr, "fake_stream: the client sent more than %d bytes\n", FAKE_STREAM_CAP);
		abort();
	}
	memcpy(fake->sent + fake->sent_len, bytes, len);
	fake->sent_len += len;
	return STREAM_OK;
}

static stream_status_t fake_recv(stream_t *stream, uint8_t *buf, size_t cap, size_t *got) {
	fake_stream_t *fake = as_fake(stream);
	*got = 0;
	if (!fake->is_open) {
		return STREAM_CLOSED;
	}
	size_t left = fake->from_server_len - fake->from_server_pos;
	if (left == 0) {
		return fake->hang_up ? STREAM_CLOSED : STREAM_OK;
	}
	size_t n = left < cap ? left : cap;
	n = n < fake->read_size ? n : fake->read_size;
	memcpy(buf, fake->from_server + fake->from_server_pos, n);
	fake->from_server_pos += n;
	*got = n;
	return STREAM_OK;
}

static void fake_close(stream_t *stream) {
	fake_stream_t *fake = as_fake(stream);
	fake->is_open = false;
	fake->close_calls++;
}

void fake_stream_init(fake_stream_t *fake, size_t read_size) {
	memset(fake, 0, sizeof *fake);
	fake->stream = (stream_t){
	    .open = fake_open, .send = fake_send, .recv = fake_recv, .close = fake_close};
	fake->open_result = STREAM_OK;
	fake->send_result = STREAM_OK;
	fake->read_size = read_size;
}

void fake_stream_queue(fake_stream_t *fake, const void *bytes, size_t len) {
	if (len > FAKE_STREAM_CAP - fake->from_server_len) {
		fprintf(stderr, "fake_stream: the queue holds at most %d bytes\n", FAKE_STREAM_CAP);
		abort();
	}
	memcpy(fake->from_server + fake->from_server_len, bytes, len);
	fake->from_server_len += len;
}
