// SPDX-License-Identifier: MIT
#include "input.h"

void input_init(input_t *in, uint8_t pulses_per_detent) {
	in->pulses = pulses_per_detent;
	in->stable = 0;
	for (int i = 0; i < INPUT_KEYS; i++) {
		in->changing[i] = false;
		in->since[i] = 0;
	}
	in->quad_seeded = false;
	in->prev_ab = 0;
	in->acc = 0;
	in->push = false;
	in->push_since = 0;
	in->backlight = 0;
}

// One step of a gray-code quadrature. +1 and -1 are opposite directions.
static int8_t quad_step(uint8_t prev, uint8_t curr) {
	static const int8_t table[16] = {
		0, +1, -1, 0, -1, 0, 0, +1, +1, 0, 0, -1, 0, -1, +1, 0,
	};
	return table[((prev & 3u) << 2) | (curr & 3u)];
}

static int push_event(input_event_t *out, int cap, int count, input_event_t ev) {
	if (count < cap && out != 0) {
		out[count] = ev;
	}
	return count + 1;
}

int input_step(input_t *in, uint32_t now_ms, uint16_t keys_down, uint8_t ab, bool push,
	       bool usb_configured, input_event_t *out, int cap) {
	int count = 0;
	for (int i = 0; i < INPUT_KEYS; i++) {
		bool down = (keys_down & (1u << i)) != 0;
		bool was = (in->stable & (1u << i)) != 0;
		if (down == was) {
			in->changing[i] = false;
			continue;
		}
		if (!in->changing[i]) {
			in->changing[i] = true;
			in->since[i] = now_ms;
			continue;
		}
		if ((uint32_t)(now_ms - in->since[i]) < INPUT_DEBOUNCE_MS) {
			continue;
		}
		if (down) {
			in->stable = (uint16_t)(in->stable | (1u << i));
		} else {
			in->stable = (uint16_t)(in->stable & ~(1u << i));
		}
		in->changing[i] = false;
		input_event_t ev = {INPUT_EVT_KEY, (int8_t)i, down ? 1u : 0u};
		count = push_event(out, cap, count, ev);
	}

	uint8_t curr = (uint8_t)(ab & 3u);
	if (!in->quad_seeded) {
		in->prev_ab = curr;
		in->quad_seeded = true;
	} else if (curr != in->prev_ab && in->pulses > 0) {
		in->acc = (int16_t)(in->acc + quad_step(in->prev_ab, curr));
		in->prev_ab = curr;
		int8_t detents = 0;
		while (in->acc >= in->pulses || in->acc <= -(int16_t)in->pulses) {
			if (in->acc > 0) {
				in->acc = (int16_t)(in->acc - in->pulses);
				if (detents < 127) {
					detents++;
				}
			} else {
				in->acc = (int16_t)(in->acc + in->pulses);
				if (detents > -128) {
					detents--;
				}
			}
		}
		if (detents != 0) {
			input_event_t ev = {INPUT_EVT_KNOB, detents, 0};
			count = push_event(out, cap, count, ev);
		}
	}

	if (push && !in->push) {
		in->push = true;
		in->push_since = now_ms;
	} else if (!push && in->push) {
		uint32_t held = now_ms - in->push_since;
		int8_t delta = held < INPUT_PAGE_LONG_MS ? 1 : -1;
		input_event_t ev = {INPUT_EVT_PAGE, delta, 0};
		count = push_event(out, cap, count, ev);
		in->push = false;
	}

	in->backlight = usb_configured ? 1u : 0u;
	return count;
}

uint8_t input_backlight(const input_t *in) {
	return in->backlight;
}
