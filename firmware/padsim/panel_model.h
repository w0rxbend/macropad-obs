// SPDX-License-Identifier: MIT
// A panel controller as padsim's SPI sees it: CASET and RASET set a window in controller RAM,
// RAMWR fills it, high byte of each pixel first, column by column then row by row. RAM columns
// count from the controller's column 0, so the panel's `col_offset` (the NV3007 strip's 12) must be
// in every CASET for the picture to land on the visible pixels. Other commands change nothing.
#pragma once

#include "panels.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
	const panel_t *panel;
	uint16_t ram_width; // visible width plus `col_offset` on each side
	uint16_t col_first, col_last, row_first, row_last; // the window, RAM coordinates, inclusive
	uint16_t col, row;                                 // where the next RAMWR pixel goes
	uint32_t bad_windows; // a CASET or RASET outside RAM, or a RAMWR past its window
	uint8_t *ram;         // ram_width x height pixels, big-endian RGB565
} panel_model_t;

// Black RAM, the whole of it as the window. False when the RAM cannot be had.
bool panel_model_init(panel_model_t *model, const panel_t *panel);

// One command and its parameter bytes; for RAMWR, the pixel bytes.
void panel_model_send(panel_model_t *model, uint8_t cmd, const uint8_t *bytes, size_t len);

// Writes the visible pixels, row by row, big-endian RGB565. False when the file cannot be written.
bool panel_model_dump(const panel_model_t *model, const char *path);
