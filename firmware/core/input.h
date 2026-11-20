// SPDX-License-Identifier: MIT
// The pad's controls: a 4x4 diode matrix of 9 keys, 4 buttons and 3 knob pushes, and 3 knobs.
// No SDK headers. The platform layer drives the rows, reads the PCNT units and calls input_step
// on its tick (1 kHz, docs/research/08-input-parts.md).
//
// Matrix (report 08 section 4). ROWr is the driven line, COLc the sensed one.
//         COL0      COL1      COL2      COL3
// ROW0    key 0     key 1     key 2     knob 0 push
// ROW1    key 3     key 4     key 5     knob 1 push
// ROW2    key 6     key 7     key 8     knob 2 push
// ROW3    button 0  button 1  button 2  button 3
#pragma once

#include <stdint.h>

#define INPUT_ROWS 4
#define INPUT_COLS 4
#define INPUT_CONTACTS (INPUT_ROWS * INPUT_COLS)
#define INPUT_KEYS 9
#define INPUT_BUTTONS 4
#define INPUT_KNOBS 3
// A contact changes once its samples have disagreed with it for this long. Cherry MX and B3F
// bounce for 5 ms at most (report 08).
#define INPUT_DEBOUNCE_MS 10
// EC11E18244AU: 2 edges per detent (spec section 6). The PCNT unit counts every edge of A and B.
#define INPUT_COUNTS_PER_DETENT 2
// Buttons 0 and 3 (B1 + B4), low in every sample from the first one after power-on, raise
// INPUT_SOURCE_CLEAR after this long (spec 8.2).
#define INPUT_CLEAR_HOLD_MS 5000
// Most events one step can give: every contact, every knob and the clear combination.
#define INPUT_MAX_EVENTS (INPUT_CONTACTS + INPUT_KNOBS + 1)

// 1 to 4 are the `source` byte of the INPUT frame (docs/protocol.md). The clear combination is
// not an INPUT source: that frame takes 1 to 4 only.
enum input_source {
	INPUT_SOURCE_KEY = 1,
	INPUT_SOURCE_BUTTON = 2,
	INPUT_SOURCE_KNOB_PUSH = 3,
	INPUT_SOURCE_KNOB_TURN = 4,
	INPUT_SOURCE_CLEAR = 5,
};

typedef struct {
	uint8_t source; // enum input_source
	uint8_t index;  // 0-based within its source. 0 for the clear combination
	int8_t value;   // 1 down, 0 up. For a turn: detents, + clockwise, never 0. Clear: 1
} input_event_t;

// One sample of every control.
typedef struct {
	uint32_t now_ms;
	// Per driven row: bit c is set when COLc read low while that row alone was low.
	uint8_t cols_low[INPUT_ROWS];
	// Per knob: PCNT counts since the last sample, + clockwise.
	int16_t knob_counts[INPUT_KNOBS];
} input_sample_t;

typedef struct {
	uint16_t closed;    // debounced contacts: bit row * INPUT_COLS + col
	uint16_t unsettled; // contacts whose last sample differed from `closed`
	uint32_t unsettled_since_ms[INPUT_CONTACTS];
	int8_t knob_counts_left[INPUT_KNOBS]; // counts short of a whole detent
	uint8_t clear_hold;                   // private to input.c
	uint32_t clear_hold_since_ms;
} input_t;

// Call once at power-on: the clear combination counts from the first sample after it.
void input_init(input_t *in);

// Takes one sample and writes the events it causes: contacts in matrix order, then knob turns,
// then the clear combination. Returns how many, 0..INPUT_MAX_EVENTS. A turn of more than 127
// detents in one sample is cut to 127: no knob moves that far in a tick.
int input_step(input_t *in, const input_sample_t *sample, input_event_t out[INPUT_MAX_EVENTS]);
