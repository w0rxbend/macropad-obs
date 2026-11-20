// SPDX-License-Identifier: MIT
#define _POSIX_C_SOURCE 200809L
#include "posix_stream.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <stdbool.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

static posix_stream_t *as_posix(stream_t *stream) {
	return (posix_stream_t *)stream;
}

static void posix_close(stream_t *stream) {
	posix_stream_t *posix = as_posix(stream);
	if (posix->fd >= 0) {
		close(posix->fd);
		posix->fd = -1;
	}
}

// The connect blocks: on loopback it ends at once. recv must not wait, so the socket turns
// non-blocking after it.
static stream_status_t posix_open(stream_t *stream, const uint8_t ip[4], uint16_t port) {
	posix_stream_t *posix = as_posix(stream);
	posix->open_calls++;
	posix_close(stream);
	struct sockaddr_in address = {.sin_family = AF_INET, .sin_port = htons(port)};
	memcpy(&address.sin_addr.s_addr, ip, 4);
	posix->fd = socket(AF_INET, SOCK_STREAM, 0);
	if (posix->fd < 0) {
		return STREAM_FAILED;
	}
	bool connected = connect(posix->fd, (struct sockaddr *)&address, sizeof address) == 0;
	int flags = fcntl(posix->fd, F_GETFL);
	if (!connected || flags < 0 || fcntl(posix->fd, F_SETFL, flags | O_NONBLOCK) != 0) {
		posix_close(stream);
		return STREAM_FAILED;
	}
	return STREAM_OK;
}

static stream_status_t lost_or_failed(int error) {
	return error == ECONNRESET || error == EPIPE ? STREAM_CLOSED : STREAM_FAILED;
}

static stream_status_t posix_send(stream_t *stream, const uint8_t *bytes, size_t len) {
	posix_stream_t *posix = as_posix(stream);
	while (len > 0) {
		ssize_t sent = send(posix->fd, bytes, len, MSG_NOSIGNAL);
		if (sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) {
			continue; // a full socket buffer drains on loopback in microseconds
		}
		if (sent < 0) {
			return lost_or_failed(errno);
		}
		bytes += sent;
		len -= (size_t)sent;
	}
	return STREAM_OK;
}

static stream_status_t posix_recv(stream_t *stream, uint8_t *buf, size_t cap, size_t *got) {
	posix_stream_t *posix = as_posix(stream);
	*got = 0;
	ssize_t received = recv(posix->fd, buf, cap, 0);
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

void posix_stream_init(posix_stream_t *posix) {
	*posix = (posix_stream_t){
	    .stream = {.open = posix_open, .send = posix_send, .recv = posix_recv, .close = posix_close},
	    .fd = -1,
	};
}
