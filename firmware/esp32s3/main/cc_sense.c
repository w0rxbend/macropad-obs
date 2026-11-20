// SPDX-License-Identifier: MIT
#include "cc_sense.h"

#include "pins.h"

#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_check.h"

#define CC_PINS 2

static const char *TAG = "cc_sense";
static const int PINS[CC_PINS] = {PIN_CC1, PIN_CC2};

static adc_oneshot_unit_handle_t s_unit;
static adc_channel_t s_channel[CC_PINS];
static adc_cali_handle_t s_cali[CC_PINS];

static esp_err_t init_pin(size_t which) {
	adc_unit_t unit;
	ESP_RETURN_ON_ERROR(adc_oneshot_io_to_channel(PINS[which], &unit, &s_channel[which]), TAG, "CC pin");
	ESP_RETURN_ON_FALSE(unit == ADC_UNIT_1, ESP_ERR_INVALID_ARG, TAG, "CC pin is not on ADC1");
	adc_oneshot_chan_cfg_t channel = {.atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT};
	ESP_RETURN_ON_ERROR(adc_oneshot_config_channel(s_unit, s_channel[which], &channel), TAG, "CC channel");
	adc_cali_curve_fitting_config_t cali = {
	    .unit_id = ADC_UNIT_1,
	    .chan = s_channel[which],
	    .atten = ADC_ATTEN_DB_12,
	    .bitwidth = ADC_BITWIDTH_DEFAULT,
	};
	return adc_cali_create_scheme_curve_fitting(&cali, &s_cali[which]);
}

esp_err_t cc_sense_init(void) {
	adc_oneshot_unit_init_cfg_t unit = {.unit_id = ADC_UNIT_1};
	ESP_RETURN_ON_ERROR(adc_oneshot_new_unit(&unit, &s_unit), TAG, "ADC1");
	for (size_t which = 0; which < CC_PINS; which++) {
		ESP_RETURN_ON_ERROR(init_pin(which), TAG, "CC%u", (unsigned)which + 1);
	}
	return ESP_OK;
}

uint32_t cc_sense_read_mv(void) {
	uint32_t highest = 0;
	for (size_t which = 0; which < CC_PINS && s_cali[which] != NULL; which++) {
		int mv;
		if (adc_oneshot_get_calibrated_result(s_unit, s_cali[which], s_channel[which], &mv) == ESP_OK && mv > 0 &&
		    (uint32_t)mv > highest) {
			highest = (uint32_t)mv;
		}
	}
	return highest;
}
