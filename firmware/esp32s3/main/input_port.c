// SPDX-License-Identifier: MIT
// Calls are those of the IDF v6.1.1 headers driver/gpio.h, driver/pulse_cnt.h and esp_timer.h.
// Pins come from pins.h only. Not run on hardware yet (task 4.8).
//
// Matrix (R08 section 4, QMK COL2ROW): COL0-3 are inputs with the board's 4.7 k pull-ups. ROW0-3
// are open drain and float high-Z; one at a time is pulled low, then the columns are read.
// Knobs: one PCNT unit per encoder, both channels, so every edge of A and of B counts
// (INPUT_COUNTS_PER_DETENT). The board's RC filter (100 us) does the debounce; the PCNT glitch
// filter drops the shorter spikes.
#include "input_port.h"

#include "pins.h"

#include "driver/gpio.h"
#include "driver/pulse_cnt.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#define TICK_US 1000
// QMK's default wait from driving a row to reading the columns (R08, verified). A 4.7 k line
// should settle in under 5 us: MEASURE on a scope, then shorten. 4 rows x 30 us is 12 % of a tick.
#define ROW_SETTLE_US 30
// The hardware filter counts APB cycles, 1023 at most: 12.7 us at 80 MHz.
#define GLITCH_NS 10000
// PCNT clears its count to 0 when it reaches either limit. The scan reads the change modulo this,
// and a knob gives a few counts per tick, far below half of it.
#define COUNT_LIMIT 30000
// Events of several ticks between two reads by the consumer.
#define EVENT_QUEUE_LEN (4 * INPUT_MAX_EVENTS)
#define SCAN_STACK 3072

static const char *TAG = "input_port";

static const gpio_num_t ROW_PINS[INPUT_ROWS] = {PIN_ROW0, PIN_ROW1, PIN_ROW2, PIN_ROW3};
static const gpio_num_t COL_PINS[INPUT_COLS] = {PIN_COL0, PIN_COL1, PIN_COL2, PIN_COL3};
static const gpio_num_t KNOB_A_PINS[INPUT_KNOBS] = {PIN_ENC1_A, PIN_ENC2_A, PIN_ENC3_A};
static const gpio_num_t KNOB_B_PINS[INPUT_KNOBS] = {PIN_ENC1_B, PIN_ENC2_B, PIN_ENC3_B};

static pcnt_unit_handle_t s_knob_units[INPUT_KNOBS];
static int s_knob_last[INPUT_KNOBS];
static QueueHandle_t s_events;
static TaskHandle_t s_scan_task;

static uint64_t pin_mask(const gpio_num_t *pins, int count) {
	uint64_t mask = 0;
	for (int i = 0; i < count; i++) {
		mask |= 1ULL << pins[i];
	}
	return mask;
}

static esp_err_t matrix_init(void) {
	// Released before the pins turn into outputs, so no row is driven low at start.
	for (int row = 0; row < INPUT_ROWS; row++) {
		ESP_RETURN_ON_ERROR(gpio_set_level(ROW_PINS[row], 1), TAG, "row level");
	}
	const gpio_config_t rows = {
		.pin_bit_mask = pin_mask(ROW_PINS, INPUT_ROWS),
		.mode = GPIO_MODE_OUTPUT_OD,
		.pull_up_en = GPIO_PULLUP_DISABLE,
		.pull_down_en = GPIO_PULLDOWN_DISABLE,
		.intr_type = GPIO_INTR_DISABLE,
	};
	ESP_RETURN_ON_ERROR(gpio_config(&rows), TAG, "rows");
	// The board has the 4.7 k pull-ups. The internal 45 k one in parallel keeps a column defined
	// if a resistor is missing; there are no pull-downs anywhere (R08).
	const gpio_config_t cols = {
		.pin_bit_mask = pin_mask(COL_PINS, INPUT_COLS),
		.mode = GPIO_MODE_INPUT,
		.pull_up_en = GPIO_PULLUP_ENABLE,
		.pull_down_en = GPIO_PULLDOWN_DISABLE,
		.intr_type = GPIO_INTR_DISABLE,
	};
	return gpio_config(&cols);
}

// x4 quadrature: each channel counts the edges of one phase, and the other phase gives the way.
// A leading B counts up. MEASURE at bring-up that this is clockwise (spec 11, R15 "every knob
// reports INPUT"); if not, swap the edge actions of both channels.
static esp_err_t knob_channel(pcnt_unit_handle_t unit, gpio_num_t edge, gpio_num_t level,
			      pcnt_channel_edge_action_t rise, pcnt_channel_edge_action_t fall) {
	const pcnt_chan_config_t config = {.edge_gpio_num = edge, .level_gpio_num = level};
	pcnt_channel_handle_t chan;
	ESP_RETURN_ON_ERROR(pcnt_new_channel(unit, &config, &chan), TAG, "channel");
	ESP_RETURN_ON_ERROR(pcnt_channel_set_edge_action(chan, rise, fall), TAG, "edge action");
	return pcnt_channel_set_level_action(chan, PCNT_CHANNEL_LEVEL_ACTION_KEEP,
					     PCNT_CHANNEL_LEVEL_ACTION_INVERSE);
}

static esp_err_t knob_init(int knob) {
	const pcnt_unit_config_t unit_config = {.low_limit = -COUNT_LIMIT, .high_limit = COUNT_LIMIT};
	pcnt_unit_handle_t unit;
	ESP_RETURN_ON_ERROR(pcnt_new_unit(&unit_config, &unit), TAG, "unit for knob %d", knob);
	const pcnt_glitch_filter_config_t filter = {.max_glitch_ns = GLITCH_NS};
	ESP_RETURN_ON_ERROR(pcnt_unit_set_glitch_filter(unit, &filter), TAG, "glitch filter");
	ESP_RETURN_ON_ERROR(knob_channel(unit, KNOB_A_PINS[knob], KNOB_B_PINS[knob],
					 PCNT_CHANNEL_EDGE_ACTION_DECREASE,
					 PCNT_CHANNEL_EDGE_ACTION_INCREASE),
			    TAG, "channel A");
	ESP_RETURN_ON_ERROR(knob_channel(unit, KNOB_B_PINS[knob], KNOB_A_PINS[knob],
					 PCNT_CHANNEL_EDGE_ACTION_INCREASE,
					 PCNT_CHANNEL_EDGE_ACTION_DECREASE),
			    TAG, "channel B");
	ESP_RETURN_ON_ERROR(pcnt_unit_enable(unit), TAG, "enable");
	ESP_RETURN_ON_ERROR(pcnt_unit_clear_count(unit), TAG, "clear");
	ESP_RETURN_ON_ERROR(pcnt_unit_start(unit), TAG, "start");
	s_knob_units[knob] = unit;
	s_knob_last[knob] = 0;
	return ESP_OK;
}

static uint8_t row_cols_low(int row) {
	gpio_set_level(ROW_PINS[row], 0);
	esp_rom_delay_us(ROW_SETTLE_US);
	uint8_t low = 0;
	for (int col = 0; col < INPUT_COLS; col++) {
		if (gpio_get_level(COL_PINS[col]) == 0) {
			low |= (uint8_t)(1u << col);
		}
	}
	gpio_set_level(ROW_PINS[row], 1);
	return low;
}

// Counts since the last read. Never clears the unit, so no edge between a read and a clear is lost.
static int16_t knob_counts(int knob) {
	int count = s_knob_last[knob];
	if (pcnt_unit_get_count(s_knob_units[knob], &count) != ESP_OK) {
		return 0; // a valid handle never fails; the unchanged count gives no turn
	}
	int delta = count - s_knob_last[knob];
	if (delta > COUNT_LIMIT / 2) {
		delta -= COUNT_LIMIT;
	} else if (delta < -COUNT_LIMIT / 2) {
		delta += COUNT_LIMIT;
	}
	s_knob_last[knob] = count;
	return (int16_t)delta;
}

static void sample(input_sample_t *out) {
	out->now_ms = (uint32_t)(esp_timer_get_time() / 1000);
	for (int row = 0; row < INPUT_ROWS; row++) {
		out->cols_low[row] = row_cols_low(row);
	}
	for (int knob = 0; knob < INPUT_KNOBS; knob++) {
		out->knob_counts[knob] = knob_counts(knob);
	}
}

static void on_tick(void *arg) {
	(void)arg;
	xTaskNotifyGive(s_scan_task);
}

static void scan_task(void *arg) {
	(void)arg;
	input_t in;
	input_init(&in);
	for (;;) {
		// Ticks missed while the queue was full collapse into one: the sample carries the time.
		ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
		input_sample_t now;
		sample(&now);
		input_event_t events[INPUT_MAX_EVENTS];
		int count = input_step(&in, &now, events);
		for (int i = 0; i < count; i++) {
			xQueueSend(s_events, &events[i], portMAX_DELAY);
		}
	}
}

esp_err_t input_port_start(UBaseType_t priority) {
	ESP_RETURN_ON_FALSE(s_scan_task == NULL, ESP_ERR_INVALID_STATE, TAG, "already started");
	ESP_RETURN_ON_ERROR(matrix_init(), TAG, "matrix");
	for (int knob = 0; knob < INPUT_KNOBS; knob++) {
		ESP_RETURN_ON_ERROR(knob_init(knob), TAG, "knob %d", knob);
	}
	s_events = xQueueCreate(EVENT_QUEUE_LEN, sizeof(input_event_t));
	ESP_RETURN_ON_FALSE(s_events != NULL, ESP_ERR_NO_MEM, TAG, "event queue");
	ESP_RETURN_ON_FALSE(xTaskCreate(scan_task, "input_scan", SCAN_STACK, NULL, priority,
					&s_scan_task) == pdPASS,
			    ESP_ERR_NO_MEM, TAG, "scan task");
	const esp_timer_create_args_t tick = {.callback = on_tick, .name = "input_tick"};
	esp_timer_handle_t timer;
	ESP_RETURN_ON_ERROR(esp_timer_create(&tick, &timer), TAG, "tick timer");
	return esp_timer_start_periodic(timer, TICK_US);
}

bool input_port_next_event(input_event_t *out, uint32_t timeout_ms) {
	return xQueueReceive(s_events, out, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
}
