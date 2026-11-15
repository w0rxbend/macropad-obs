// SPDX-License-Identifier: MIT
// Samples GPIO and calls input.c. GP0 and GP1 stay unused.
#include "input.h"
#include "link.h"
#include "panel.h"
#include "pins.h"
#include "usb.h"

#include "hardware/gpio.h"
#include "pico/stdlib.h"
#include "tusb.h"

static const uint8_t key_pins[PIN_KEY_COUNT] = {
	PIN_KEY_0, PIN_KEY_1, PIN_KEY_2, PIN_KEY_3, PIN_KEY_4,
	PIN_KEY_5, PIN_KEY_6, PIN_KEY_7, PIN_KEY_8,
};

static void send_hello(link_t *link) {
	uint8_t payload[4] = {LINK_PROTO, PIN_KEY_COUNT, 0, 0};
	link_send(link, LINK_HELLO, payload, 4);
}

static uint16_t read_keys(void) {
	uint16_t down = 0;
	for (int i = 0; i < PIN_KEY_COUNT; i++) {
		if (!gpio_get(key_pins[i])) {
			down = (uint16_t)(down | (1u << i));
		}
	}
	return down;
}

static void emit(link_t *link, const input_event_t *ev) {
	if (ev->type == INPUT_EVT_KEY) {
		uint8_t payload[2] = {(uint8_t)ev->a, ev->b};
		link_send(link, LINK_KEY, payload, 2);
	} else if (ev->type == INPUT_EVT_KNOB && ev->a != 0) {
		uint8_t payload[1] = {(uint8_t)ev->a};
		link_send(link, LINK_KNOB, payload, 1);
	} else if (ev->type == INPUT_EVT_PAGE && ev->a != 0) {
		uint8_t payload[1] = {(uint8_t)ev->a};
		link_send(link, LINK_PAGE, payload, 1);
	}
}

int main(void) {
	board_init();
	for (int i = 0; i < PIN_KEY_COUNT; i++) {
		gpio_init(key_pins[i]);
		gpio_set_dir(key_pins[i], GPIO_IN);
		gpio_pull_up(key_pins[i]);
	}
	gpio_init(PIN_KNOB_A);
	gpio_init(PIN_KNOB_B);
	gpio_init(PIN_KNOB_PUSH);
	gpio_set_dir(PIN_KNOB_A, GPIO_IN);
	gpio_set_dir(PIN_KNOB_B, GPIO_IN);
	gpio_set_dir(PIN_KNOB_PUSH, GPIO_IN);
	gpio_pull_up(PIN_KNOB_A);
	gpio_pull_up(PIN_KNOB_B);
	gpio_pull_up(PIN_KNOB_PUSH);

	link_t link;
	link_init(&link);
	input_t input;
	input_init(&input, PIN_KNOB_PULSES_PER_DETENT);
	panel_init();
	usb_init();
	uint32_t last_hello = 0;

	while (1) {
		uint32_t now = to_ms_since_boot(get_absolute_time());
		link_frame_t frames[8];
		int n = usb_poll(&link, frames, 8);
		for (int i = 0; i < n; i++) {
			if (frames[i].type >= LINK_HELLO_ACK) {
				link_mark_host(&link, now);
			}
			panel_on_frame(&frames[i], now);
		}
		if (usb_hello_due() || (!link_acked(&link) && (uint32_t)(now - last_hello) >= 1000u)) {
			send_hello(&link);
			last_hello = now;
			usb_hello_sent();
		}
		uint8_t ab = (uint8_t)((gpio_get(PIN_KNOB_A) ? 2u : 0u) | (gpio_get(PIN_KNOB_B) ? 1u : 0u));
		bool push = !gpio_get(PIN_KNOB_PUSH);
		input_event_t ev[12];
		int count = input_step(&input, now, read_keys(), ab, push, tud_mounted(), ev, 12);
		for (int i = 0; i < count && i < 12; i++) {
			emit(&link, &ev[i]);
		}
		panel_backlight(input_backlight(&input) != 0);
		panel_poll(now, !link_no_link(&link, now));
		sleep_ms(1);
	}
}
