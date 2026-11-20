// SPDX-License-Identifier: MIT
// Both panels as data: the init table, the visible size and the RAM column offset.
// No SPI and no GPIO here. The port resets the panels, then sends each table.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// One reset line serves both panels. Hold it low, release it, then wait before the first
// command. ST7796U: low 10 us or more, ready 120 ms after release at the latest (R06 [C1]
// page 59). NV3007: 120 ms each, a driver constant (R07 [C4] `NV3007_RST_DELAY`).
#define PANEL_RESET_LOW_MS 120
#define PANEL_RESET_WAIT_MS 120

#define PANEL_CASET 0x2A
#define PANEL_RASET 0x2B
#define PANEL_RAMWR 0x2C

#define PANEL_INIT_PARAMS_MAX 4

// One command, its parameters, then a wait before the next command.
typedef struct {
	uint8_t cmd;
	uint8_t wait_ms;
	uint8_t param_len;
	uint8_t params[PANEL_INIT_PARAMS_MAX];
} panel_init_step_t;

typedef struct {
	uint16_t width; // visible pixels
	uint16_t height;
	uint16_t col_offset; // RAM column of visible column 0
	const panel_init_step_t *init;
	size_t init_len;
	bool init_unverified; // true while no datasheet and no bench record stands behind `init`
} panel_t;

// Big panel: Focus E35GH-I-RW300-N, ST7796U. Each table byte is cited to the datasheet
// (R06 [C1]). MADCTL 0x00 and inversion off are reset values: mirror, colour order and
// inversion are MEASURE until a panel draws a frame.
extern const panel_t panel_main;

// Strip: Wisevision N279-1428KIWIG01-C10, NV3007. The table is driver source (R07 [C1] [C4]):
// the NV3007 datasheet was not read (R07 [B4]). It stays unverified until task S.3 records the
// panel ID read and a drawn frame.
extern const panel_t panel_strip;

// Visible pixels.
typedef struct {
	uint16_t x;
	uint16_t y;
	uint16_t w;
	uint16_t h;
} panel_rect_t;

// CASET and RASET parameters: start then end, high byte first. Send PANEL_CASET with `caset`,
// PANEL_RASET with `raset`, then PANEL_RAMWR with the pixels.
typedef struct {
	uint8_t caset[4];
	uint8_t raset[4];
} panel_window_t;

// Returns false and leaves `out` alone when `rect` is empty or leaves the panel.
bool panel_window(const panel_t *panel, panel_rect_t rect, panel_window_t *out);
