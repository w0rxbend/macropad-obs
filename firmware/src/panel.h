// SPDX-License-Identifier: MIT
#pragma once

#include "link.h"

#include <stdbool.h>
#include <stdint.h>

void panel_init(void);
void panel_on_frame(const link_frame_t *frame, uint32_t now_ms);
void panel_poll(uint32_t now_ms, bool link_up);
void panel_backlight(bool on);
