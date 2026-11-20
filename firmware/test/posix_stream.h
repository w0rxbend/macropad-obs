// SPDX-License-Identifier: MIT
// The stream seam over a POSIX TCP socket, for host tests against a real server such as
// tools/fake_obs.py.
#pragma once

#include "stream.h"

typedef struct {
	stream_t stream; // first, so a posix_stream_t * is a stream_t *
	int fd;          // -1 while closed
	int open_calls;
} posix_stream_t;

// Starts closed.
void posix_stream_init(posix_stream_t *posix);
