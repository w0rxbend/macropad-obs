// SPDX-License-Identifier: MIT
// Debounce, quadrature, knob-push page split, and the backlight gate.
// No SDK headers. The platform layer samples GPIO and calls input_step.
#pragma once

#include <stdbool.h>
#include <stdint.h>

#define INPUT_KEYS 9
#define INPUT_DEBOUNCE_MS 10
#define INPUT_PAGE_LONG_MS 400

enum input_event_type {
	INPUT_EVT_KEY = 1,
	INPUT_EVT_KNOB = 2,
	INPUT_EVT_PAGE = 3,
};

typedef struct {
	uint8_t type;
	int8_t a;
	uint8_t b;
} input_event_t;

typedef struct {
	uint8_t pulses;
	uint16_t stable;
	bool changing[INPUT_KEYS];
	uint32_t since[INPUT_KEYS];
	bool quad_seeded;
	uint8_t prev_ab;
	int16_t acc;
	bool push;
	uint32_t push_since;
	uint8_t backlight;
} input_t;

void input_init(input_t *in, uint8_t pulses_per_detent);

// One sample. `keys_down` bit i is set when key i is pressed (already active-low decoded).
// `ab` is encoder A in bit 1 and B in bit 0. `push` is the knob switch.
// Returns the number of events written.
int input_step(input_t *in, uint32_t now_ms, uint16_t keys_down, uint8_t ab, bool push,
	       bool usb_configured, input_event_t *out, int cap);

uint8_t input_backlight(const input_t *in);
