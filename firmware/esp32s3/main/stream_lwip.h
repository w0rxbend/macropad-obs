// SPDX-License-Identifier: MIT
// The stream seam (stream.h, spec 9 fw-stream) on an lwIP BSD socket. One connection at a time.
#pragma once

#include "stream.h"

typedef struct {
	stream_t stream; // first, so a stream_lwip_t * is a stream_t *
	int fd;          // -1 while closed
} stream_lwip_t;

// Starts closed.
void stream_lwip_init(stream_lwip_t *lwip);
