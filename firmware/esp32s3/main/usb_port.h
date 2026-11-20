// SPDX-License-Identifier: MIT
// The one CDC-ACM port on esp_tinyusb 3.0.1 (spec 8.1). VID and PID come from pins.h, the serial
// number from the base MAC. Logs go to UART0, never here. Call usb_port_start before the rest.
#pragma once

#include "link.h"

#include "esp_err.h"

#include <stdbool.h>
#include <stdint.h>

// Installs TinyUSB and the CDC port. The device enumerates from here on.
esp_err_t usb_port_start(void);

// The 6 base-MAC bytes the USB serial number spells: INFO `unique_id`.
esp_err_t usb_port_unique_id(uint8_t out[LINK_UNIQUE_ID_LEN]);

// True once the host has configured the device (SET_CONFIGURATION): from then on it may draw
// 500 mA, before it 100 mA (USB 2.0, report 10). False again after a bus reset or detach.
bool usb_port_configured(void);

// Pull read: moves into `rx` what the host sent, no more than `rx` has room for. TinyUSB keeps
// the rest and NAKs the host while its own FIFO is full, so no byte is dropped. Waits up to
// `timeout_ms` when nothing is there. Returns the bytes moved; 0 when `rx` is full (link_pull
// first) or nothing came.
size_t usb_port_feed(link_rx_t *rx, uint32_t timeout_ms);

// Sends one frame whole: frames from different tasks never interleave. Blocks while the host has
// the port open and does not read (spec 8.1). False when the frame does not encode or the host
// closed the port; what was queued is then dropped.
bool usb_port_send(const link_frame_t *frame);

// Detaches from the bus and uninstalls TinyUSB (the BOOTLOADER sequence, spec 8.2).
esp_err_t usb_port_stop(void);
