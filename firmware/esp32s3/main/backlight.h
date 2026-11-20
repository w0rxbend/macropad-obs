// SPDX-License-Identifier: MIT
// The two backlight PWMs on LEDC (spec 7: IO47 BL_BIG, IO48 BL_STRIP, each the enable pin of a
// BCR421 sink with a 100 k pull-down). This sets duty only; the power cap that limits it while
// Wi-Fi is up lives in power.c (task 4.7).
#pragma once

#include "ui.h"

#include "esp_err.h"

#include <stdint.h>

#define BACKLIGHT_PERMILLE_MAX 1000

// Sets up the LEDC timer and both channels with the backlights off. Call once.
esp_err_t backlight_init(void);

// Sets one backlight to `permille` of full, from the next PWM period. ESP_ERR_INVALID_ARG above
// BACKLIGHT_PERMILLE_MAX. Not thread-safe (LEDC's own note): call it from one task only.
esp_err_t backlight_set(ui_display_t display, uint16_t permille);
