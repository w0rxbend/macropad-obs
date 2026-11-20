// SPDX-License-Identifier: MIT
// The CDC write loop (spec 8.1: USB writes block on back-pressure). Pure C, no SDK headers: the
// port (firmware/esp32s3/main/usb_port.c) gives the two calls below, and firmware/test drives
// the loop with a fake FIFO under ASan.
#pragma once

#include "link.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
	// Copies up to `n` bytes into the TX FIFO and returns how many it took; 0 when it is full.
	size_t (*queue)(void *ctx, const uint8_t *bytes, size_t n);
	// Sends what the FIFO holds and blocks until it is empty. False when the host is gone; the
	// port then drops what the FIFO still holds.
	bool (*drain)(void *ctx);
	void *ctx;
} link_tx_port_t;

// Writes all `n` bytes. A full FIFO makes it drain and queue the rest, so a slow host slows the
// pad and loses no byte. It ends with a drain, so the bytes leave now. False when the host went
// away: part of the bytes may have left, and the app finds the next SOF (docs/protocol.md).
bool link_tx_write(const link_tx_port_t *port, const uint8_t *bytes, size_t n);

// Encodes `frame` and writes it. False when it does not encode or the host went away.
bool link_tx_send(const link_tx_port_t *port, const link_frame_t *frame);
