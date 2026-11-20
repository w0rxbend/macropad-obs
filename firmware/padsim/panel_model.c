// SPDX-License-Identifier: MIT
#include "panel_model.h"

#include <stdio.h>
#include <stdlib.h>

#define PIXEL_BYTES 2
#define SPAN_BYTES 4 // start then end, high byte first

bool panel_model_init(panel_model_t *model, const panel_t *panel) {
	uint16_t ram_width = (uint16_t)(panel->width + 2 * panel->col_offset);
	*model = (panel_model_t){
	    .panel = panel,
	    .ram_width = ram_width,
	    .col_last = (uint16_t)(ram_width - 1),
	    .row_last = (uint16_t)(panel->height - 1),
	    .ram = calloc((size_t)ram_width * panel->height, PIXEL_BYTES),
	};
	return model->ram != NULL;
}

static uint16_t be16(const uint8_t *bytes) {
	return (uint16_t)(bytes[0] << 8 | bytes[1]);
}

// False, and the window as it was, for a span that is not SPAN_BYTES long, runs backwards or
// leaves `limit`.
static bool read_span(const uint8_t *bytes, size_t len, uint16_t limit, uint16_t *first, uint16_t *last) {
	if (len != SPAN_BYTES || be16(bytes) > be16(bytes + 2) || be16(bytes + 2) >= limit) {
		return false;
	}
	*first = be16(bytes);
	*last = be16(bytes + 2);
	return true;
}

static void write_pixels(panel_model_t *model, const uint8_t *bytes, size_t len) {
	model->col = model->col_first;
	model->row = model->row_first;
	if (len % PIXEL_BYTES != 0) {
		model->bad_windows++;
	}
	for (size_t at = 0; at + PIXEL_BYTES <= len; at += PIXEL_BYTES) {
		if (model->row > model->row_last) {
			model->bad_windows++;
			return;
		}
		uint8_t *cell = &model->ram[((size_t)model->row * model->ram_width + model->col) * PIXEL_BYTES];
		cell[0] = bytes[at];
		cell[1] = bytes[at + 1];
		if (model->col == model->col_last) {
			model->col = model->col_first;
			model->row++;
		} else {
			model->col++;
		}
	}
}

void panel_model_send(panel_model_t *model, uint8_t cmd, const uint8_t *bytes, size_t len) {
	bool window_ok = true;
	switch (cmd) {
	case PANEL_CASET:
		window_ok = read_span(bytes, len, model->ram_width, &model->col_first, &model->col_last);
		break;
	case PANEL_RASET:
		window_ok = read_span(bytes, len, model->panel->height, &model->row_first, &model->row_last);
		break;
	case PANEL_RAMWR:
		write_pixels(model, bytes, len);
		break;
	default:
		break;
	}
	if (!window_ok) {
		model->bad_windows++;
	}
}

bool panel_model_dump(const panel_model_t *model, const char *path) {
	FILE *out = fopen(path, "wb");
	if (out == NULL) {
		return false;
	}
	size_t row_bytes = (size_t)model->panel->width * PIXEL_BYTES;
	bool written = true;
	for (uint16_t row = 0; row < model->panel->height && written; row++) {
		size_t first = ((size_t)row * model->ram_width + model->panel->col_offset) * PIXEL_BYTES;
		written = fwrite(&model->ram[first], 1, row_bytes, out) == row_bytes;
	}
	return fclose(out) == 0 && written;
}
