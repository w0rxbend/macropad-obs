// SPDX-License-Identifier: MIT
// CC1 and CC2 sense on ADC1 (spec 7 pin budget: IO1, IO2 through 100 k each). The source's
// current advert sets the CC voltage across the pad's 5.1 k Rd (USB Type-C table 4-36, report 10).
// The 100 k series resistor against the ADC's sampling input is not measured: MEASURE in bring-up
// against a known 1.5 A source. A reading that fails counts as 0 mV, which keeps the cap.
#pragma once

#include "esp_err.h"

#include <stdint.h>

// Sets up ADC1 one-shot on both pins, 12 dB attenuation, with curve-fitting calibration.
esp_err_t cc_sense_init(void);

// The higher of the two CC voltages, mV: only the CC pin the cable connects carries the advert.
uint32_t cc_sense_read_mv(void);
