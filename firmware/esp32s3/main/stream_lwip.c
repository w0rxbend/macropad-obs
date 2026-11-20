// SPDX-License-Identifier: MIT
// lwIP sockets as IDF v6.1.1 ships them (lwip/sockets.h). The socket stays blocking for send,
// with a send timeout, and recv asks MSG_DONTWAIT, so the seam's recv never waits.
#include "stream_lwip.h"

#include "lwip/sockets.h"

#include <errno.h>
#include <stdbool.h>
#include <string.h>

// Bounds of the two waits. Choices, not measured: no hardware yet (task 4.8). A LAN connect ends
// in milliseconds; 3 s leaves most of criterion 3's 30 s to the join and the OBS handshake.
#define CONNECT_TIMEOUT_MS 3000
#define SEND_TIMEOUT_MS 3000

static stream_lwip_t *as_lwip(stream_t *stream) {
	return (stream_lwip_t *)stream;
}

static struct timeval timeval_of(int ms) {
	return (struct timeval){.tv_sec = ms / 1000, .tv_usec = (ms % 1000) * 1000};
}

static void seam_close(stream_t *stream) {
	stream_lwip_t *lwip = as_lwip(stream);
	if (lwip->fd >= 0) {
		close(lwip->fd);
		lwip->fd = -1;
	}
}

static bool set_blocking(int fd, bool blocking) {
	int flags = fcntl(fd, F_GETFL, 0);
	if (flags < 0) {
		return false;
	}
	flags = blocking ? flags & ~O_NONBLOCK : flags | O_NONBLOCK;
	return fcntl(fd, F_SETFL, flags) == 0;
}

// A non-blocking connect, then select for writable within CONNECT_TIMEOUT_MS, then SO_ERROR.
static bool connect_bounded(int fd, const struct sockaddr_in *address) {
	if (!set_blocking(fd, false)) {
		return false;
	}
	if (connect(fd, (const struct sockaddr *)address, sizeof *address) != 0 && errno != EINPROGRESS) {
		return false;
	}
	fd_set writable;
	FD_ZERO(&writable);
	FD_SET(fd, &writable);
	struct timeval wait = timeval_of(CONNECT_TIMEOUT_MS);
	if (select(fd + 1, NULL, &writable, NULL, &wait) != 1) {
		return false; // timed out, or select failed
	}
	int error = 0;
	socklen_t error_len = sizeof error;
	return getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &error_len) == 0 && error == 0 &&
	       set_blocking(fd, true);
}

// Small WebSocket frames go out at once instead of waiting for Nagle's coalescing.
static bool tune(int fd) {
	int on = 1;
	struct timeval send_wait = timeval_of(SEND_TIMEOUT_MS);
	return setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &on, sizeof on) == 0 &&
	       setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &send_wait, sizeof send_wait) == 0;
}

static stream_status_t seam_open(stream_t *stream, const uint8_t ip[4], uint16_t port) {
	stream_lwip_t *lwip = as_lwip(stream);
	seam_close(stream);
	struct sockaddr_in address = {.sin_family = AF_INET, .sin_port = htons(port)};
	memcpy(&address.sin_addr.s_addr, ip, 4);
	lwip->fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
	if (lwip->fd < 0) {
		return STREAM_FAILED;
	}
	if (!connect_bounded(lwip->fd, &address) || !tune(lwip->fd)) {
		seam_close(stream);
		return STREAM_FAILED;
	}
	return STREAM_OK;
}

static stream_status_t lost_or_failed(int error) {
	return error == ECONNRESET || error == EPIPE || error == ENOTCONN ? STREAM_CLOSED : STREAM_FAILED;
}

// A send that blocks past SEND_TIMEOUT_MS fails with EAGAIN: the peer stopped reading.
static stream_status_t seam_send(stream_t *stream, const uint8_t *bytes, size_t len) {
	stream_lwip_t *lwip = as_lwip(stream);
	if (lwip->fd < 0) {
		return STREAM_FAILED;
	}
	while (len > 0) {
		ssize_t sent = send(lwip->fd, bytes, len, 0);
		if (sent < 0 && errno == EINTR) {
			continue;
		}
		if (sent < 0) {
			return lost_or_failed(errno);
		}
		bytes += sent;
		len -= (size_t)sent;
	}
	return STREAM_OK;
}

static stream_status_t seam_recv(stream_t *stream, uint8_t *buf, size_t cap, size_t *got) {
	stream_lwip_t *lwip = as_lwip(stream);
	*got = 0;
	if (lwip->fd < 0) {
		return STREAM_FAILED;
	}
	ssize_t received = recv(lwip->fd, buf, cap, MSG_DONTWAIT);
	if (received > 0) {
		*got = (size_t)received;
		return STREAM_OK;
	}
	if (received == 0) {
		return STREAM_CLOSED;
	}
	if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
		return STREAM_OK;
	}
	return lost_or_failed(errno);
}

void stream_lwip_init(stream_lwip_t *lwip) {
	*lwip = (stream_lwip_t){
	    .stream = {.open = seam_open, .send = seam_send, .recv = seam_recv, .close = seam_close},
	    .fd = -1,
	};
}
