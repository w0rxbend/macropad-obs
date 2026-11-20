// SPDX-License-Identifier: MIT
#define _GNU_SOURCE // ptsname_r, cfmakeraw
#include "pty.h"

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>

static bool fail(const char *step) {
	fprintf(stderr, "padsim: pty %s: %s\n", step, strerror(errno));
	return false;
}

bool pty_open(pty_t *pty) {
	pty->master = posix_openpt(O_RDWR | O_NOCTTY);
	if (pty->master < 0 || grantpt(pty->master) != 0 || unlockpt(pty->master) != 0) {
		return fail("open");
	}
	if (ptsname_r(pty->master, pty->path, sizeof pty->path) != 0) {
		return fail("name");
	}
	pty->slave = open(pty->path, O_RDWR | O_NOCTTY);
	struct termios raw;
	if (pty->slave < 0 || tcgetattr(pty->slave, &raw) != 0) {
		return fail("slave");
	}
	cfmakeraw(&raw);
	if (tcsetattr(pty->slave, TCSANOW, &raw) != 0) {
		return fail("raw mode");
	}
	int flags = fcntl(pty->master, F_GETFL);
	if (flags < 0 || fcntl(pty->master, F_SETFL, flags | O_NONBLOCK) != 0) {
		return fail("non-blocking");
	}
	return true;
}

static bool wait_writable(int fd) {
	struct pollfd watch = {.fd = fd, .events = POLLOUT};
	return poll(&watch, 1, PTY_SEND_WAIT_MS) == 1 && (watch.revents & POLLOUT) != 0;
}

void pty_send(const pty_t *pty, const uint8_t *bytes, size_t len) {
	while (len > 0) {
		ssize_t sent = write(pty->master, bytes, len);
		if (sent > 0) {
			bytes += sent;
			len -= (size_t)sent;
			continue;
		}
		bool busy = sent < 0 && (errno == EAGAIN || errno == EINTR);
		if (!busy || !wait_writable(pty->master)) {
			fprintf(stderr, "padsim: pty: no app reads, %zu bytes dropped\n", len);
			return;
		}
	}
}

size_t pty_recv(const pty_t *pty, uint8_t *buf, size_t cap) {
	ssize_t got = read(pty->master, buf, cap);
	return got > 0 ? (size_t)got : 0;
}
