// SPDX-License-Identifier: MIT
// Calls are those of the IDF v6.1.1 headers esp_lcd_io_spi.h, esp_lcd_panel_io.h,
// driver/spi_master.h and driver/gpio.h. Pins come from pins.h only. Not run on hardware yet
// (task 4.8); two esp_lcd IO handles on one SPI host is unproven until then (spec 14).
//
// One DMA band buffer serves both panels. The band is byte-swapped into it, the window goes out as
// CASET and RASET, then RAMWR and the pixels are queued; the done callback frees the buffer. So
// the renderer paints band N+1 while band N is on the wire, and a band never overwrites pixels
// still in flight, whichever panel they go to.
#include "lcd_port.h"

#include "panels.h"
#include "pins.h"
#include "render.h"

#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_attr.h"
#include "esp_check.h"
#include "esp_lcd_io_spi.h"
#include "esp_lcd_panel_io.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#define LCD_HOST SPI2_HOST
// Provisional f_bus: 80 MHz / 6. Spec 13 criterion 7: until an S3 step above the ST7796U's 15 MHz
// write rating passes the spike bench, f_bus is 13.3 MHz. S.3 has no record yet (no hardware), so
// this stays until S.3 names the fastest clean step; request it as an exact 80 MHz / n, since IDF
// rounds to the nearest step, not down (R18).
#define LCD_PCLK_HZ (80 * 1000 * 1000 / 6)
#define LCD_SPI_MODE 3 // spec 13 criterion 7
#define LCD_CMD_BITS 8
#define LCD_PARAM_BITS 8
// One RAMWR in flight plus the command before it.
#define LCD_TRANS_QUEUE_DEPTH 2
#define BAND_PIXELS (RENDER_BAND_WIDTH * UI_TILE)
#define BAND_BYTES (BAND_PIXELS * sizeof(uint16_t))
#define WINDOW_PARAM_BYTES 4

static const char *TAG = "lcd_port";

// The big panel comes first: only the first device on a bus may use the CS0 pin (R18 [E14]).
static const ui_display_t ATTACH_ORDER[UI_DISPLAYS] = {UI_MAIN, UI_STRIP};
static const gpio_num_t CS_PINS[UI_DISPLAYS] = {[UI_MAIN] = PIN_LCD_CS_BIG,
						 [UI_STRIP] = PIN_LCD_CS_STRIP};
static const panel_t *const PANELS[UI_DISPLAYS] = {[UI_MAIN] = &panel_main,
						   [UI_STRIP] = &panel_strip};

static esp_lcd_panel_io_handle_t s_io[UI_DISPLAYS];
DMA_ATTR static uint16_t s_band[BAND_PIXELS];
static StaticSemaphore_t s_band_free_storage;
static SemaphoreHandle_t s_band_free;

// vTaskDelay can return up to one tick early, so one tick more keeps each wait at or over the
// datasheet's minimum at CONFIG_FREERTOS_HZ 100.
static void wait_at_least_ms(uint32_t ms) {
	vTaskDelay(pdMS_TO_TICKS(ms) + 1);
}

static bool IRAM_ATTR on_band_sent(esp_lcd_panel_io_handle_t io, esp_lcd_panel_io_event_data_t *edata,
				   void *user_ctx) {
	(void)io;
	(void)edata;
	(void)user_ctx;
	BaseType_t woken = pdFALSE;
	xSemaphoreGiveFromISR(s_band_free, &woken);
	return woken == pdTRUE;
}

static esp_err_t bus_init(void) {
	const spi_bus_config_t bus = {
		.mosi_io_num = PIN_LCD_MOSI,
		.miso_io_num = -1, // no MISO on the board (spec 7)
		.sclk_io_num = PIN_LCD_SCK,
		.quadwp_io_num = -1,
		.quadhd_io_num = -1,
		.max_transfer_sz = BAND_BYTES,
	};
	return spi_bus_initialize(LCD_HOST, &bus, SPI_DMA_CH_AUTO);
}

static esp_err_t io_add(ui_display_t display) {
	const esp_lcd_panel_io_spi_config_t config = {
		.cs_gpio_num = CS_PINS[display],
		.dc_gpio_num = PIN_LCD_DC,
		.spi_mode = LCD_SPI_MODE,
		.pclk_hz = LCD_PCLK_HZ,
		.trans_queue_depth = LCD_TRANS_QUEUE_DEPTH,
		.on_color_trans_done = on_band_sent,
		.lcd_cmd_bits = LCD_CMD_BITS,
		.lcd_param_bits = LCD_PARAM_BITS,
	};
	return esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)LCD_HOST, &config, &s_io[display]);
}

// The IO handle keeps its SPI device private. A device with the same clock settings and no CS gets
// the same divider from the driver, reports it, and leaves the bus again.
static esp_err_t log_bus_clock(void) {
	const spi_device_interface_config_t probe = {
		.flags = SPI_DEVICE_HALFDUPLEX,
		.clock_speed_hz = LCD_PCLK_HZ,
		.mode = LCD_SPI_MODE,
		.spics_io_num = -1,
		.queue_size = 1,
	};
	spi_device_handle_t device;
	ESP_RETURN_ON_ERROR(spi_bus_add_device(LCD_HOST, &probe, &device), TAG, "clock probe");
	int actual_khz = 0;
	const esp_err_t err = spi_device_get_actual_freq(device, &actual_khz);
	ESP_RETURN_ON_ERROR(spi_bus_remove_device(device), TAG, "clock probe removal");
	ESP_RETURN_ON_ERROR(err, TAG, "actual freq");
	ESP_LOGI(TAG, "SPI2 f_bus requested %d Hz, actual %d kHz (provisional until S.3)", LCD_PCLK_HZ,
		 actual_khz);
	return ESP_OK;
}

static esp_err_t reset_panels(void) {
	const gpio_config_t reset = {
		.pin_bit_mask = 1ULL << PIN_LCD_RESET,
		.mode = GPIO_MODE_OUTPUT,
		.pull_up_en = GPIO_PULLUP_DISABLE,
		.pull_down_en = GPIO_PULLDOWN_DISABLE,
		.intr_type = GPIO_INTR_DISABLE,
	};
	ESP_RETURN_ON_ERROR(gpio_config(&reset), TAG, "reset pin");
	ESP_RETURN_ON_ERROR(gpio_set_level(PIN_LCD_RESET, 0), TAG, "reset low");
	wait_at_least_ms(PANEL_RESET_LOW_MS);
	ESP_RETURN_ON_ERROR(gpio_set_level(PIN_LCD_RESET, 1), TAG, "reset high");
	wait_at_least_ms(PANEL_RESET_WAIT_MS);
	return ESP_OK;
}

static esp_err_t panel_init(ui_display_t display) {
	const panel_t *panel = PANELS[display];
	if (panel->init_unverified) {
		ESP_LOGW(TAG, "display %d: init table unverified until S.3", display);
	}
	for (size_t i = 0; i < panel->init_len; i++) {
		const panel_init_step_t *step = &panel->init[i];
		ESP_RETURN_ON_ERROR(esp_lcd_panel_io_tx_param(s_io[display], step->cmd, step->params,
							      step->param_len),
				    TAG, "display %d command 0x%02x", display, step->cmd);
		if (step->wait_ms > 0) {
			wait_at_least_ms(step->wait_ms);
		}
	}
	return ESP_OK;
}

esp_err_t lcd_port_start(void) {
	ESP_RETURN_ON_FALSE(s_band_free == NULL, ESP_ERR_INVALID_STATE, TAG, "already started");
	s_band_free = xSemaphoreCreateBinaryStatic(&s_band_free_storage);
	xSemaphoreGive(s_band_free);
	ESP_RETURN_ON_ERROR(bus_init(), TAG, "SPI2 bus");
	for (int i = 0; i < UI_DISPLAYS; i++) {
		ESP_RETURN_ON_ERROR(io_add(ATTACH_ORDER[i]), TAG, "IO for display %d", ATTACH_ORDER[i]);
	}
	ESP_RETURN_ON_ERROR(log_bus_clock(), TAG, "bus clock");
	ESP_RETURN_ON_ERROR(reset_panels(), TAG, "reset");
	for (int i = 0; i < UI_DISPLAYS; i++) {
		ESP_RETURN_ON_ERROR(panel_init(ATTACH_ORDER[i]), TAG, "init");
	}
	return ESP_OK;
}

static esp_err_t band_send(esp_lcd_panel_io_handle_t io, const panel_window_t *ram, size_t pixel_count) {
	ESP_RETURN_ON_ERROR(esp_lcd_panel_io_tx_param(io, PANEL_CASET, ram->caset, WINDOW_PARAM_BYTES),
			    TAG, "CASET");
	ESP_RETURN_ON_ERROR(esp_lcd_panel_io_tx_param(io, PANEL_RASET, ram->raset, WINDOW_PARAM_BYTES),
			    TAG, "RASET");
	return esp_lcd_panel_io_tx_color(io, PANEL_RAMWR, s_band, pixel_count * sizeof(uint16_t));
}

static esp_err_t band_push(ui_display_t display, ui_rect_t window, const uint16_t *pixels) {
	const panel_rect_t rect = {.x = window.x, .y = window.y, .w = window.w, .h = window.h};
	panel_window_t ram;
	if (!panel_window(PANELS[display], rect, &ram)) {
		return ESP_ERR_INVALID_ARG;
	}
	const size_t pixel_count = (size_t)window.w * window.h;
	if (pixel_count > BAND_PIXELS) {
		return ESP_ERR_INVALID_SIZE;
	}
	xSemaphoreTake(s_band_free, portMAX_DELAY);
	for (size_t i = 0; i < pixel_count; i++) {
		s_band[i] = __builtin_bswap16(pixels[i]);
	}
	const esp_err_t err = band_send(s_io[display], &ram, pixel_count);
	if (err != ESP_OK) {
		xSemaphoreGive(s_band_free); // nothing was queued, so no done callback frees the buffer
	}
	return err;
}

void lcd_port_push(void *context, ui_display_t display, ui_rect_t window, const uint16_t *pixels) {
	(void)context;
	const esp_err_t err = band_push(display, window, pixels);
	if (err != ESP_OK) {
		ESP_LOGE(TAG, "display %d band %ux%u at %u,%u dropped: %s", display, window.w, window.h,
			 window.x, window.y, esp_err_to_name(err));
	}
}
