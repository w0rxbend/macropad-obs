// SPDX-License-Identifier: MIT
// Both panels on SPI2 through two esp_lcd SPI IO handles (spec 5, R18 "Display plan"): the big
// ST7796U on CS0 (IO10), attached first, then the NV3007 strip on IO13. DC and RESET are shared.
// The init tables come from the core (panels.h); the pixels come from fw-ui's band renderer.
#pragma once

#include "ui.h"

#include "esp_err.h"

#include <stdint.h>

// Sets up SPI2 with DMA, adds the big panel's IO handle and then the strip's, logs the bus clock
// from spi_device_get_actual_freq(), pulses the shared RESET and sends both init tables. The
// backlights are not touched (backlight.h). Call once, before the first lcd_port_push.
esp_err_t lcd_port_start(void);

// A render_sink_t push (render.h): sends `window` of `display` and its pixels, `window.w` to a
// row, RGB565 high byte first. Returns once the band is copied to the DMA buffer and queued, so
// the renderer paints the next band while this one goes out. A window that leaves the panel or
// holds more than one band is logged and dropped. `context` is unused.
void lcd_port_push(void *context, ui_display_t display, ui_rect_t window, const uint16_t *pixels);
