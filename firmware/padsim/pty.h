// SPDX-License-Identifier: MIT
// padsim's CDC port: a pseudo-terminal in raw mode. The app opens the slave path as it opens
// /dev/ttyACM0 on the pad. padsim holds the slave open too, so the master keeps working while no
// app has it open, and frames sent meanwhile wait in the terminal queue.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PTY_PATH_MAX 64
// How long a send waits for an app that does not read before it drops the frame.
#define PTY_SEND_WAIT_MS 1000

typedef struct {
	int master; // non-blocking
	int slave;
	char path[PTY_PATH_MAX];
} pty_t;

// False, with the reason on stderr, when no raw pseudo-terminal can be had.
bool pty_open(pty_t *pty);

// Sends all `len` bytes, or drops the rest after PTY_SEND_WAIT_MS with a line on stderr.
void pty_send(const pty_t *pty, const uint8_t *bytes, size_t len);

// Copies up to `cap` bytes that have arrived, without waiting. 0 when none have.
size_t pty_recv(const pty_t *pty, uint8_t *buf, size_t cap);
