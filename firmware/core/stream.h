// SPDX-License-Identifier: MIT
// The TCP seam (spec 9, fw-stream): open, send, receive, close. The port puts lwIP behind it,
// the host tests a POSIX socket or a scripted fake. Pure C, no SDK headers.
#pragma once

#include <stddef.h>
#include <stdint.h>

typedef enum {
	STREAM_OK,
	STREAM_CLOSED, // the peer closed or reset the connection
	STREAM_FAILED, // no connection: refused, unreachable, timed out, or a socket error
} stream_status_t;

// An implementation embeds stream_t as its first member and casts the pointer back.
typedef struct stream stream_t;
struct stream {
	// Connects to ip:port (IPv4, network order). Returns when connected or failed; the port
	// bounds the wait.
	stream_status_t (*open)(stream_t *stream, const uint8_t ip[4], uint16_t port);
	// Sends all `len` bytes or fails.
	stream_status_t (*send)(stream_t *stream, const uint8_t *bytes, size_t len);
	// Copies up to `cap` bytes that have arrived into `buf` without waiting. `*got` is 0 when
	// none have.
	stream_status_t (*recv)(stream_t *stream, uint8_t *buf, size_t cap, size_t *got);
	// Drops the connection. Safe on a stream that is not open.
	void (*close)(stream_t *stream);
};
