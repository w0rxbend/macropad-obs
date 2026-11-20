// SPDX-License-Identifier: MIT
// Calls are those of the IDF v6.1.1 headers driver/ledc.h and driver/gpio.h. Pins come from pins.h only. Not run on
// hardware yet (task 4.8); backlight currents are MEASURE in bring-up (spec 14).
#include "backlight.h"

#include "pins.h"

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_check.h"

// About 20 kHz: no flicker on camera and above hearing (R14), under the BCR421's 25 kHz PWM limit
// (R10). The S3 has low-speed LEDC only; 10 bits at 20 kHz needs 20.5 MHz of the 80 MHz clock.
#define BACKLIGHT_PWM_HZ 20000
#define BACKLIGHT_RESOLUTION LEDC_TIMER_10_BIT
#define BACKLIGHT_DUTY_FULL (1u << BACKLIGHT_RESOLUTION) // LEDC holds the pin high at 2^bits
#define BACKLIGHT_MODE LEDC_LOW_SPEED_MODE
#define BACKLIGHT_TIMER LEDC_TIMER_0

static const char *TAG = "backlight";

static const gpio_num_t PINS[UI_DISPLAYS] = {[UI_MAIN] = PIN_BL_BIG, [UI_STRIP] = PIN_BL_STRIP};
static const ledc_channel_t CHANNELS[UI_DISPLAYS] = {[UI_MAIN] = LEDC_CHANNEL_0,
						     [UI_STRIP] = LEDC_CHANNEL_1};

esp_err_t backlight_init(void) {
	const ledc_timer_config_t timer = {
		.speed_mode = BACKLIGHT_MODE,
		.duty_resolution = BACKLIGHT_RESOLUTION,
		.timer_num = BACKLIGHT_TIMER,
		.freq_hz = BACKLIGHT_PWM_HZ,
		.clk_cfg = LEDC_AUTO_CLK,
	};
	ESP_RETURN_ON_ERROR(ledc_timer_config(&timer), TAG, "timer");
	for (int display = 0; display < UI_DISPLAYS; display++) {
		const ledc_channel_config_t channel = {
			.gpio_num = PINS[display],
			.speed_mode = BACKLIGHT_MODE,
			.channel = CHANNELS[display],
			.timer_sel = BACKLIGHT_TIMER,
			.duty = 0,
		};
		ESP_RETURN_ON_ERROR(ledc_channel_config(&channel), TAG, "channel for display %d", display);
	}
	return ESP_OK;
}

esp_err_t backlight_set(ui_display_t display, uint16_t permille) {
	ESP_RETURN_ON_FALSE(permille <= BACKLIGHT_PERMILLE_MAX, ESP_ERR_INVALID_ARG, TAG,
			    "%u permille", permille);
	const uint32_t duty = (uint32_t)permille * BACKLIGHT_DUTY_FULL / BACKLIGHT_PERMILLE_MAX;
	ESP_RETURN_ON_ERROR(ledc_set_duty(BACKLIGHT_MODE, CHANNELS[display], duty), TAG, "duty");
	return ledc_update_duty(BACKLIGHT_MODE, CHANNELS[display]);
}
