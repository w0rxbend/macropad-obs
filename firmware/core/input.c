// SPDX-License-Identifier: MIT
#include "input.h"

#include "link.h"

#define COLS_MASK ((1u << INPUT_COLS) - 1u)
#define CONTACT(row, col) (1u << ((row) * INPUT_COLS + (col)))
// B1 and B4: the outer two of the button row.
#define CLEAR_CONTACTS (CONTACT(3, 0) | CONTACT(3, 3))
// The INPUT frame's value is one signed byte. -128 is left out to keep both ways alike.
#define TURN_DETENTS_MAX 127

// Sources 1 to 4 go into the INPUT frame as they are. The cast is for -Wenum-compare.
_Static_assert(INPUT_SOURCE_KEY == (int)LINK_INPUT_KEY, "INPUT source of a key");
_Static_assert(INPUT_SOURCE_BUTTON == (int)LINK_INPUT_BUTTON, "INPUT source of a button");
_Static_assert(INPUT_SOURCE_KNOB_PUSH == (int)LINK_INPUT_KNOB_PUSH, "INPUT source of a push");
_Static_assert(INPUT_SOURCE_KNOB_TURN == (int)LINK_INPUT_KNOB_TURN, "INPUT source of a turn");
_Static_assert(INPUT_KEYS + INPUT_BUTTONS + INPUT_KNOBS == INPUT_CONTACTS,
	       "every contact is a key, a button or a knob push");
_Static_assert(INPUT_COUNTS_PER_DETENT >= 2,
	       "one count of contact bounce must stay short of a detent");

enum clear_hold {
	CLEAR_HOLD_NOT_SAMPLED, // no sample since power-on
	CLEAR_HOLD_RUNNING,     // B1 and B4 were low in every sample so far
	CLEAR_HOLD_OVER,        // broken or raised: nothing more until the next power-on
};

typedef struct {
	uint8_t source; // enum input_source
	uint8_t index;
} control_t;

#define KEY(index) {INPUT_SOURCE_KEY, (index)}
#define BUTTON(index) {INPUT_SOURCE_BUTTON, (index)}
#define PUSH(index) {INPUT_SOURCE_KNOB_PUSH, (index)}

// By contact, row * INPUT_COLS + col: the matrix of input.h, one row a line.
static const control_t CONTROL_OF_CONTACT[INPUT_CONTACTS] = {
	KEY(0),    KEY(1),    KEY(2),    PUSH(0),
	KEY(3),    KEY(4),    KEY(5),    PUSH(1),
	KEY(6),    KEY(7),    KEY(8),    PUSH(2),
	BUTTON(0), BUTTON(1), BUTTON(2), BUTTON(3),
};

void input_init(input_t *in) {
	*in = (input_t){.clear_hold = CLEAR_HOLD_NOT_SAMPLED};
}

// One bit per contact. A row keeps its own four bits, so a stray high bit of one row sample
// cannot close a contact of the next row.
static uint16_t sampled_contacts(const input_sample_t *sample) {
	uint16_t sampled = 0;
	for (int row = 0; row < INPUT_ROWS; row++) {
		sampled |= (uint16_t)((sample->cols_low[row] & COLS_MASK) << (row * INPUT_COLS));
	}
	return sampled;
}

// Flips each contact whose samples have disagreed with it for INPUT_DEBOUNCE_MS without a
// break. Returns the contacts that flipped.
static uint16_t debounce(input_t *in, uint32_t now_ms, uint16_t sampled) {
	uint16_t differs = sampled ^ in->closed;
	uint16_t flipped = 0;
	for (int contact = 0; contact < INPUT_CONTACTS; contact++) {
		uint16_t bit = (uint16_t)(1u << contact);
		if ((differs & bit) == 0) {
			continue;
		}
		if ((in->unsettled & bit) == 0) {
			in->unsettled_since_ms[contact] = now_ms;
			continue;
		}
		uint32_t unsettled_ms = now_ms - in->unsettled_since_ms[contact];
		if (unsettled_ms >= INPUT_DEBOUNCE_MS) {
			flipped |= bit;
		}
	}
	in->closed ^= flipped;
	in->unsettled = (uint16_t)(differs & ~flipped);
	return flipped;
}

static int report_contacts(uint16_t flipped, uint16_t closed, input_event_t *out) {
	int count = 0;
	for (int contact = 0; contact < INPUT_CONTACTS; contact++) {
		uint16_t bit = (uint16_t)(1u << contact);
		if ((flipped & bit) == 0) {
			continue;
		}
		control_t control = CONTROL_OF_CONTACT[contact];
		int8_t down = (closed & bit) != 0 ? 1 : 0;
		out[count++] = (input_event_t){control.source, control.index, down};
	}
	return count;
}

static int8_t clamped_detents(int32_t detents) {
	if (detents > TURN_DETENTS_MAX) {
		return TURN_DETENTS_MAX;
	}
	if (detents < -TURN_DETENTS_MAX) {
		return -TURN_DETENTS_MAX;
	}
	return (int8_t)detents;
}

// Counts short of a detent wait in knob_counts_left. Contact bounce on one phase moves the
// count one forth and one back, so it nets out there and never makes a turn.
static int decode_knobs(input_t *in, const int16_t counts[INPUT_KNOBS], input_event_t *out) {
	int count = 0;
	for (int knob = 0; knob < INPUT_KNOBS; knob++) {
		int32_t total = in->knob_counts_left[knob] + counts[knob];
		int32_t detents = total / INPUT_COUNTS_PER_DETENT;
		in->knob_counts_left[knob] = (int8_t)(total % INPUT_COUNTS_PER_DETENT);
		if (detents != 0) {
			out[count++] = (input_event_t){INPUT_SOURCE_KNOB_TURN, (uint8_t)knob,
						       clamped_detents(detents)};
		}
	}
	return count;
}

// The clear combination erases the pad, so it reads the samples as they come, not the
// debounced contacts: one sample with B1 or B4 up ends the hold, and only a hold that runs
// from the first sample after power-on counts.
static int step_clear_hold(input_t *in, uint32_t now_ms, uint16_t sampled, input_event_t *out) {
	if (in->clear_hold == CLEAR_HOLD_OVER) {
		return 0;
	}
	if ((sampled & CLEAR_CONTACTS) != CLEAR_CONTACTS) {
		in->clear_hold = CLEAR_HOLD_OVER;
		return 0;
	}
	if (in->clear_hold == CLEAR_HOLD_NOT_SAMPLED) {
		in->clear_hold = CLEAR_HOLD_RUNNING;
		in->clear_hold_since_ms = now_ms;
	}
	uint32_t held_ms = now_ms - in->clear_hold_since_ms;
	if (held_ms < INPUT_CLEAR_HOLD_MS) {
		return 0;
	}
	in->clear_hold = CLEAR_HOLD_OVER;
	out[0] = (input_event_t){INPUT_SOURCE_CLEAR, 0, 1};
	return 1;
}

int input_step(input_t *in, const input_sample_t *sample, input_event_t out[INPUT_MAX_EVENTS]) {
	uint16_t sampled = sampled_contacts(sample);
	uint16_t flipped = debounce(in, sample->now_ms, sampled);
	int count = report_contacts(flipped, in->closed, out);
	count += decode_knobs(in, sample->knob_counts, out + count);
	count += step_clear_hold(in, sample->now_ms, sampled, out + count);
	return count;
}
