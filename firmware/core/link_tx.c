// SPDX-License-Identifier: MIT
#include "link_tx.h"

bool link_tx_write(const link_tx_port_t *port, const uint8_t *bytes, size_t n) {
	while (n > 0) {
		size_t taken = port->queue(port->ctx, bytes, n);
		bytes += taken;
		n -= taken;
		if (n > 0 && !port->drain(port->ctx)) {
			return false;
		}
	}
	return port->drain(port->ctx);
}

bool link_tx_send(const link_tx_port_t *port, const link_frame_t *frame) {
	uint8_t wire[LINK_MAX_FRAME];
	size_t len = link_encode(frame, wire, sizeof wire);
	return len != 0 && link_tx_write(port, wire, len);
}
