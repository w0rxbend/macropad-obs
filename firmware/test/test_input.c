// SPDX-License-Identifier: MIT
#include "input.h"

#include <stdio.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

static int step(input_t *in, uint32_t now, uint16_t keys, uint8_t ab, bool push, bool cfg,
		input_event_t *ev) {
	return input_step(in, now, keys, ab, push, cfg, ev, 8);
}

static void test_debounce_down_and_up(void) {
	input_t in;
	input_event_t ev[8];
	input_init(&in, 4);
	int n = 0;
	for (uint32_t t = 0; t < 10; t++) {
		n = step(&in, t, 0x1, 0, false, false, ev);
		CHECK(n == 0);
	}
	n = step(&in, 10, 0x1, 0, false, false, ev);
	CHECK(n == 1 && ev[0].type == INPUT_EVT_KEY && ev[0].a == 0 && ev[0].b == 1);
	for (uint32_t t = 11; t < 21; t++) {
		n = step(&in, t, 0, 0, false, false, ev);
		CHECK(n == 0);
	}
	n = step(&in, 21, 0, 0, false, false, ev);
	CHECK(n == 1 && ev[0].type == INPUT_EVT_KEY && ev[0].b == 0);
}

static void test_quadrature_one_detent(void) {
	input_t in;
	input_event_t ev[8];
	input_init(&in, 4);
	uint8_t seq[5] = {0, 1, 3, 2, 0};
	int n = step(&in, 0, 0, seq[0], false, false, ev);
	CHECK(n == 0);
	int detents = 0;
	for (int i = 1; i < 5; i++) {
		n = step(&in, (uint32_t)i, 0, seq[i], false, false, ev);
		for (int k = 0; k < n; k++) {
			if (ev[k].type == INPUT_EVT_KNOB) {
				detents += ev[k].a;
			}
		}
	}
	CHECK(detents == 1);
}

static void test_push_split(void) {
	input_t in;
	input_event_t ev[8];
	input_init(&in, 4);
	CHECK(step(&in, 0, 0, 0, true, false, ev) == 0);
	int n = step(&in, 399, 0, 0, false, false, ev);
	CHECK(n == 1 && ev[0].type == INPUT_EVT_PAGE && ev[0].a == 1);

	input_init(&in, 4);
	CHECK(step(&in, 1000, 0, 0, true, false, ev) == 0);
	n = step(&in, 1400, 0, 0, false, false, ev);
	CHECK(n == 1 && ev[0].type == INPUT_EVT_PAGE && ev[0].a == -1);
}

static void test_backlight_gate(void) {
	input_t in;
	input_event_t ev[8];
	input_init(&in, 4);
	CHECK(input_backlight(&in) == 0);
	step(&in, 0, 0, 0, false, false, ev);
	CHECK(input_backlight(&in) == 0);
	step(&in, 1, 0, 0, false, true, ev);
	CHECK(input_backlight(&in) == 1);
	step(&in, 2, 0, 0, false, false, ev);
	CHECK(input_backlight(&in) == 0);
}

int main(void) {
	test_debounce_down_and_up();
	test_quadrature_one_detent();
	test_push_split();
	test_backlight_gate();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	puts("input: all tests pass");
	return 0;
}
