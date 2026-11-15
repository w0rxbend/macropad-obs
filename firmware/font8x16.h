// SPDX-License-Identifier: MIT
#pragma once

#include <stdint.h>

#define FONT8X16_FIRST 0x20
#define FONT8X16_LAST 0x7E
#define FONT8X16_COUNT 95
#define FONT8X16_ROWS 16
#define FONT8X16_BYTES (FONT8X16_COUNT * FONT8X16_ROWS)

extern const uint8_t font8x16[FONT8X16_COUNT][FONT8X16_ROWS];
