// SPDX-License-Identifier: MIT
// The pad's controls on GPIO and PCNT (spec pin budget, R08, R18). A scan task samples the 4x4
// matrix and the three PCNT units every 1 ms and runs fw-input (input.h) on each sample.
#pragma once

#include "input.h"

#include "esp_err.h"
#include "freertos/FreeRTOS.h"

#include <stdbool.h>
#include <stdint.h>

// Sets up the row, column and encoder pins, PCNT units 0-2 and the 1 kHz scan task at `priority`.
// Call once, before any other PCNT user, so the knobs get units 0, 1 and 2 in order.
esp_err_t input_port_start(UBaseType_t priority);

// Takes the next fw-input event, waiting up to `timeout_ms`. False when none came. The scan task
// waits while the queue is full, so no event is lost; the knob counts keep adding up in PCNT.
bool input_port_next_event(input_event_t *out, uint32_t timeout_ms);
