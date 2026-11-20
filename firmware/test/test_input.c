// SPDX-License-Identifier: MIT
#include "input.h"

#include <stdbool.h>
#include <stdio.h>

#define EVENT_LOG_CAP 512
#define ALL_CONTACTS 0xFFFFu
#define KEY(i) ((uint16_t)(1u << ((i) / 3 * INPUT_COLS + (i) % 3)))
#define BUTTON(i) ((uint16_t)(1u << (3 * INPUT_COLS + (i))))
#define CLEAR_BUTTONS ((uint16_t)(BUTTON(0) | BUTTON(3)))

// EC11E18244AU at the spec's limit: 36 detents and 18 pulses a turn, 2 turns a second.
#define TURNS_PER_SECOND 2
#define EDGES_PER_SECOND (TURNS_PER_SECOND * 18 * 4) // 4 edges a pulse
#define SPIN_EDGES EDGES_PER_SECOND // the spin lasts one second
#define SPIN_DETENTS (TURNS_PER_SECOND * 36)
#define SPIN_MS 1010 // the spin, then the last edge's chatter
#define CHATTER_US 3000 // Alps: chattering 3 ms max
#define CHATTER_FLIP_US 400
#define PCNT_LOOK_US 100

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

// The unit under test on a 1 kHz tick, with every event it has given.
typedef struct {
	input_t in;
	uint32_t now_ms;
	input_event_t events[EVENT_LOG_CAP];
	int event_count;
} bench_t;

#define KEY_DOWN(index) {INPUT_SOURCE_KEY, (index), 1}
#define BUTTON_DOWN(index) {INPUT_SOURCE_BUTTON, (index), 1}
#define PUSH_DOWN(index) {INPUT_SOURCE_KNOB_PUSH, (index), 1}

// Report 08 section 4, one matrix row a line.
static const input_event_t DOWN_OF_CONTACT[INPUT_CONTACTS] = {
	KEY_DOWN(0),    KEY_DOWN(1),    KEY_DOWN(2),    PUSH_DOWN(0),
	KEY_DOWN(3),    KEY_DOWN(4),    KEY_DOWN(5),    PUSH_DOWN(1),
	KEY_DOWN(6),    KEY_DOWN(7),    KEY_DOWN(8),    PUSH_DOWN(2),
	BUTTON_DOWN(0), BUTTON_DOWN(1), BUTTON_DOWN(2), BUTTON_DOWN(3),
};

static const input_event_t CLEAR = {INPUT_SOURCE_CLEAR, 0, 1};

static void bench_start(bench_t *bench, uint32_t now_ms) {
	*bench = (bench_t){.now_ms = now_ms};
	input_init(&bench->in);
}

// Feeds one sample at the bench's time and moves the clock one tick on.
static void tick(bench_t *bench, input_sample_t sample) {
	input_event_t out[INPUT_MAX_EVENTS];
	sample.now_ms = bench->now_ms++;
	int count = input_step(&bench->in, &sample, out);
	CHECK(count >= 0 && count <= INPUT_MAX_EVENTS);
	CHECK(bench->event_count + count <= EVENT_LOG_CAP);
	for (int i = 0; i < count && bench->event_count < EVENT_LOG_CAP; i++) {
		bench->events[bench->event_count++] = out[i];
	}
}

static uint8_t row_cols(uint16_t closed, int row) {
	return (uint8_t)((closed >> (row * INPUT_COLS)) & 0xFu);
}

static uint8_t cols_of_rows(uint16_t closed, uint8_t rows) {
	uint8_t cols = 0;
	for (int row = 0; row < INPUT_ROWS; row++) {
		if ((rows & (1u << row)) != 0) {
			cols |= row_cols(closed, row);
		}
	}
	return cols;
}

static uint8_t rows_of_cols(uint16_t closed, uint8_t cols) {
	uint8_t rows = 0;
	for (int row = 0; row < INPUT_ROWS; row++) {
		if ((row_cols(closed, row) & cols) != 0) {
			rows |= (uint8_t)(1u << row);
		}
	}
	return rows;
}

// The diode matrix as the scan sees it: with one ROW line low, a COL line reads low only
// through a closed contact of that row.
static input_sample_t with_diodes(uint16_t closed) {
	input_sample_t sample = {0};
	for (int row = 0; row < INPUT_ROWS; row++) {
		sample.cols_low[row] = row_cols(closed, row);
	}
	return sample;
}

// The same matrix with every diode bridged: a closed contact now also pulls its ROW line low
// from its COL line, so the low spreads to every line the closed contacts join.
static input_sample_t without_diodes(uint16_t closed) {
	input_sample_t sample = {0};
	for (int row = 0; row < INPUT_ROWS; row++) {
		uint8_t rows_low = (uint8_t)(1u << row);
		for (int hop = 0; hop < INPUT_ROWS; hop++) {
			rows_low |= rows_of_cols(closed, cols_of_rows(closed, rows_low));
		}
		sample.cols_low[row] = cols_of_rows(closed, rows_low);
	}
	return sample;
}

// `ms` ticks with these contacts closed and the knobs still.
static void hold(bench_t *bench, uint16_t closed, uint32_t ms) {
	for (uint32_t i = 0; i < ms; i++) {
		tick(bench, with_diodes(closed));
	}
}

// One tick in which the PCNT unit of `knob` moved by `counts`.
static void turn(bench_t *bench, int knob, int16_t counts) {
	input_sample_t sample = {0};
	sample.knob_counts[knob] = counts;
	tick(bench, sample);
}

static input_event_t event(uint8_t source, int index, int value) {
	return (input_event_t){source, (uint8_t)index, (int8_t)value};
}

static bool same_event(input_event_t a, input_event_t b) {
	return a.source == b.source && a.index == b.index && a.value == b.value;
}

static int count_of(const bench_t *bench, input_event_t wanted) {
	int count = 0;
	for (int i = 0; i < bench->event_count; i++) {
		if (same_event(bench->events[i], wanted)) {
			count++;
		}
	}
	return count;
}

static void test_press_is_reported_after_10_ms(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, KEY(0), 10);
	CHECK(bench.event_count == 0);
	hold(&bench, KEY(0), 1);
	CHECK(bench.event_count == 1);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KEY, 0, 1)) == 1);
}

static void test_release_is_reported_after_10_ms(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, KEY(0), 20);
	hold(&bench, 0, 10);
	CHECK(bench.event_count == 1);
	hold(&bench, 0, 1);
	CHECK(bench.event_count == 2);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KEY, 0, 0)) == 1);
}

static void test_bounce_gives_one_press(void) {
	bench_t bench;
	bench_start(&bench, 0);
	for (int ms = 0; ms < 5; ms++) {
		hold(&bench, ms % 2 == 0 ? KEY(0) : 0, 1);
	}
	hold(&bench, KEY(0), 9);
	CHECK(bench.event_count == 0);
	hold(&bench, KEY(0), 50);
	CHECK(bench.event_count == 1);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KEY, 0, 1)) == 1);
}

static void test_glitch_under_10_ms_is_dropped(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, KEY(0), 10);
	hold(&bench, 0, 50);
	CHECK(bench.event_count == 0);
}

static void test_contacts_debounce_apart(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, KEY(0), 5);
	hold(&bench, KEY(0) | KEY(1), 6);
	CHECK(bench.event_count == 1);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KEY, 0, 1)) == 1);
	hold(&bench, KEY(0) | KEY(1), 4);
	CHECK(bench.event_count == 1);
	hold(&bench, KEY(0) | KEY(1), 1);
	CHECK(bench.event_count == 2);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KEY, 1, 1)) == 1);
}

static void test_debounce_spans_the_clock_wrap(void) {
	bench_t bench;
	bench_start(&bench, UINT32_MAX - 4);
	hold(&bench, KEY(0), 10);
	CHECK(bench.event_count == 0);
	hold(&bench, KEY(0), 1);
	CHECK(bench.event_count == 1);
}

static void test_each_contact_is_its_own_control(void) {
	for (int contact = 0; contact < INPUT_CONTACTS; contact++) {
		bench_t bench;
		bench_start(&bench, 0);
		hold(&bench, (uint16_t)(1u << contact), INPUT_DEBOUNCE_MS + 1);
		CHECK(bench.event_count == 1);
		CHECK(same_event(bench.events[0], DOWN_OF_CONTACT[contact]));
	}
}

// Keys 0, 1 and 3 are three corners of a rectangle. Key 4 is the fourth: the classic ghost.
static void test_three_corners_do_not_ghost_the_fourth(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, KEY(0) | KEY(1) | KEY(3), 50);
	CHECK(bench.event_count == 3);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KEY, 4, 1)) == 0);
}

// The control for the test above: the same three keys do read as four once no diode blocks
// the way back, so the pattern is a real ghost and the diode is what stops it.
static void test_three_corners_ghost_with_bridged_diodes(void) {
	bench_t bench;
	bench_start(&bench, 0);
	for (int ms = 0; ms < 50; ms++) {
		tick(&bench, without_diodes(KEY(0) | KEY(1) | KEY(3)));
	}
	CHECK(bench.event_count == 4);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KEY, 4, 1)) == 1);
}

static void test_sixteen_held_contacts_report_once_each_in_matrix_order(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, ALL_CONTACTS, 50);
	CHECK(bench.event_count == INPUT_CONTACTS);
	for (int contact = 0; contact < INPUT_CONTACTS; contact++) {
		CHECK(same_event(bench.events[contact], DOWN_OF_CONTACT[contact]));
	}
}

static void test_one_release_among_sixteen_is_reported_alone(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, ALL_CONTACTS, 50);
	hold(&bench, (uint16_t)(ALL_CONTACTS & ~KEY(4)), 50);
	CHECK(bench.event_count == INPUT_CONTACTS + 1);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KEY, 4, 0)) == 1);
}

static void test_bits_above_col3_reach_no_other_row(void) {
	bench_t bench;
	bench_start(&bench, 0);
	input_sample_t sample = {0};
	sample.cols_low[0] = 0xF0;
	for (int ms = 0; ms < 50; ms++) {
		tick(&bench, sample);
	}
	CHECK(bench.event_count == 0);
}

static void test_two_counts_make_one_detent(void) {
	bench_t bench;
	bench_start(&bench, 0);
	turn(&bench, 0, 2);
	CHECK(bench.event_count == 1);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KNOB_TURN, 0, 1)) == 1);
	turn(&bench, 0, -2);
	CHECK(bench.event_count == 2);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KNOB_TURN, 0, -1)) == 1);
}

static void test_counts_add_up_across_samples(void) {
	bench_t bench;
	bench_start(&bench, 0);
	turn(&bench, 2, 1);
	CHECK(bench.event_count == 0);
	turn(&bench, 2, 1);
	CHECK(bench.event_count == 1);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KNOB_TURN, 2, 1)) == 1);
}

static void test_one_count_of_wobble_makes_no_turn(void) {
	bench_t bench;
	bench_start(&bench, 0);
	for (int i = 0; i < 100; i++) {
		turn(&bench, 1, 1);
		turn(&bench, 1, -1);
	}
	for (int i = 0; i < 100; i++) {
		turn(&bench, 1, -1);
		turn(&bench, 1, 1);
	}
	CHECK(bench.event_count == 0);
}

static void test_knobs_turn_apart_in_one_sample(void) {
	bench_t bench;
	bench_start(&bench, 0);
	input_sample_t sample = {.knob_counts = {2, -4, 6}};
	tick(&bench, sample);
	CHECK(bench.event_count == 3);
	CHECK(same_event(bench.events[0], event(INPUT_SOURCE_KNOB_TURN, 0, 1)));
	CHECK(same_event(bench.events[1], event(INPUT_SOURCE_KNOB_TURN, 1, -2)));
	CHECK(same_event(bench.events[2], event(INPUT_SOURCE_KNOB_TURN, 2, 3)));
}

static void test_a_turn_is_cut_to_127_detents(void) {
	bench_t bench;
	bench_start(&bench, 0);
	turn(&bench, 0, INT16_MAX);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KNOB_TURN, 0, 127)) == 1);
	turn(&bench, 0, INT16_MIN);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KNOB_TURN, 0, -127)) == 1);
	turn(&bench, 0, 0);
	CHECK(bench.event_count == 2);
}

// A in bit 1 and B in bit 0, `us` into a one-second spin at 2 turns a second. For CHATTER_US
// after each edge the line that moved flips back and forth.
static uint8_t spinning_ab(int32_t us, int direction) {
	static const uint8_t GRAY[4] = {0, 1, 3, 2};
	int32_t edges = us * EDGES_PER_SECOND / 1000000;
	if (edges > SPIN_EDGES) {
		edges = SPIN_EDGES;
	}
	int32_t edge_us = (edges * 1000000 + EDGES_PER_SECOND - 1) / EDGES_PER_SECOND;
	int32_t since_edge_us = us - edge_us;
	bool flipped_back = edges > 0 && since_edge_us < CHATTER_US &&
			    since_edge_us / CHATTER_FLIP_US % 2 == 1;
	int32_t shown_edges = flipped_back ? edges - 1 : edges;
	return GRAY[(direction * shown_edges % 4 + 4) % 4];
}

// A PCNT unit that counts every edge of A and B sees the lines every PCNT_LOOK_US. The unit
// under test gets its count once a tick.
static void spin_one_second(bench_t *bench, int knob, int direction) {
	// By (old A, old B, A, B): +1 for a quarter cycle clockwise, -1 for one back.
	static const int8_t QUARTER_CYCLE[16] = {
		0, +1, -1, 0, -1, 0, 0, +1, +1, 0, 0, -1, 0, -1, +1, 0,
	};
	uint8_t ab = 0;
	for (int32_t ms = 0; ms < SPIN_MS; ms++) {
		int16_t counts = 0;
		for (int32_t us = ms * 1000; us < (ms + 1) * 1000; us += PCNT_LOOK_US) {
			uint8_t seen_ab = spinning_ab(us, direction);
			counts = (int16_t)(counts + QUARTER_CYCLE[(ab << 2) | seen_ab]);
			ab = seen_ab;
		}
		turn(bench, knob, counts);
	}
}

static void test_two_turns_a_second_clockwise_with_bounce(void) {
	bench_t bench;
	bench_start(&bench, 0);
	spin_one_second(&bench, 0, +1);
	CHECK(bench.event_count == SPIN_DETENTS);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KNOB_TURN, 0, +1)) == SPIN_DETENTS);
}

static void test_two_turns_a_second_back_with_bounce(void) {
	bench_t bench;
	bench_start(&bench, 0);
	spin_one_second(&bench, 2, -1);
	CHECK(bench.event_count == SPIN_DETENTS);
	CHECK(count_of(&bench, event(INPUT_SOURCE_KNOB_TURN, 2, -1)) == SPIN_DETENTS);
}

// Tick n is the sample n ms after power-on, so 5000 ticks end 4999 ms into the hold.
static void test_b1_b4_held_5000_ms_from_power_on_raise_clear_once(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, CLEAR_BUTTONS, 5000);
	CHECK(count_of(&bench, CLEAR) == 0);
	hold(&bench, CLEAR_BUTTONS, 1);
	CHECK(count_of(&bench, CLEAR) == 1);
	hold(&bench, CLEAR_BUTTONS, 6000);
	CHECK(count_of(&bench, CLEAR) == 1);
}

static void test_b1_b4_held_4900_ms_raise_no_clear(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, CLEAR_BUTTONS, 4901);
	hold(&bench, 0, 1000);
	CHECK(count_of(&bench, CLEAR) == 0);
}

static void test_a_hold_that_starts_after_power_on_raises_no_clear(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, 0, 1);
	hold(&bench, CLEAR_BUTTONS, 6000);
	CHECK(count_of(&bench, CLEAR) == 0);
}

static void test_one_open_sample_ends_the_clear_hold(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, CLEAR_BUTTONS, 2500);
	hold(&bench, BUTTON(0), 1);
	hold(&bench, CLEAR_BUTTONS, 6000);
	CHECK(count_of(&bench, CLEAR) == 0);
}

static void test_one_button_alone_raises_no_clear(void) {
	bench_t bench;
	bench_start(&bench, 0);
	hold(&bench, BUTTON(0), 6000);
	CHECK(count_of(&bench, CLEAR) == 0);
	bench_start(&bench, 0);
	hold(&bench, BUTTON(3), 6000);
	CHECK(count_of(&bench, CLEAR) == 0);
}

int main(void) {
	test_press_is_reported_after_10_ms();
	test_release_is_reported_after_10_ms();
	test_bounce_gives_one_press();
	test_glitch_under_10_ms_is_dropped();
	test_contacts_debounce_apart();
	test_debounce_spans_the_clock_wrap();
	test_each_contact_is_its_own_control();
	test_three_corners_do_not_ghost_the_fourth();
	test_three_corners_ghost_with_bridged_diodes();
	test_sixteen_held_contacts_report_once_each_in_matrix_order();
	test_one_release_among_sixteen_is_reported_alone();
	test_bits_above_col3_reach_no_other_row();
	test_two_counts_make_one_detent();
	test_counts_add_up_across_samples();
	test_one_count_of_wobble_makes_no_turn();
	test_knobs_turn_apart_in_one_sample();
	test_a_turn_is_cut_to_127_detents();
	test_two_turns_a_second_clockwise_with_bounce();
	test_two_turns_a_second_back_with_bounce();
	test_b1_b4_held_5000_ms_from_power_on_raise_clear_once();
	test_b1_b4_held_4900_ms_raise_no_clear();
	test_a_hold_that_starts_after_power_on_raises_no_clear();
	test_one_open_sample_ends_the_clear_hold();
	test_one_button_alone_raises_no_clear();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	puts("input: all tests pass");
	return 0;
}
