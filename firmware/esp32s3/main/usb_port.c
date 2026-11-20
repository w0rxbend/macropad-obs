// SPDX-License-Identifier: MIT
#include "usb_port.h"

#include "link_tx.h"
#include "pins.h"

#include "esp_check.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "tinyusb.h"
#include "tinyusb_cdc_acm.h"
#include "tinyusb_default_config.h"

#include <stdio.h>

#define CDC_PORT TINYUSB_CDC_ACM_0
// One flush wait. A host that keeps the port open and does not read keeps the writer in its loop
// one slice after another; the slice only sets how often TinyUSB logs "Flush failed" on UART0.
#define DRAIN_SLICE_MS 1000
// Lets the last IN packet of the BOOTLOADER reply leave before the pad detaches. A guess, not
// measured: no hardware yet.
#define DETACH_SETTLE_MS 20

static const char *TAG = "usb_port";

static char s_serial[2 * LINK_UNIQUE_ID_LEN + 1];
static SemaphoreHandle_t s_rx_ready;
static SemaphoreHandle_t s_tx_lock;

static const tusb_desc_device_t DEVICE = {
	.bLength = sizeof(tusb_desc_device_t),
	.bDescriptorType = TUSB_DESC_DEVICE,
	.bcdUSB = 0x0200,
	// CDC-ACM sits behind an interface association, which needs the misc class (USB IAD ECN).
	.bDeviceClass = TUSB_CLASS_MISC,
	.bDeviceSubClass = MISC_SUBCLASS_COMMON,
	.bDeviceProtocol = MISC_PROTOCOL_IAD,
	.bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
	.idVendor = USB_VID,
	.idProduct = USB_PID,
	.bcdDevice = 0x0100,
	.iManufacturer = 1,
	.iProduct = 2,
	.iSerialNumber = 3,
	.bNumConfigurations = 1,
};

// Indices match DEVICE and esp_tinyusb's default CDC configuration descriptor (string 4).
static const char *STRINGS[] = {
	(const char[]){0x09, 0x04}, // English (US)
	"macropad-obs",
	"macropad-obs",
	s_serial,
	"macropad-obs link",
};

static void on_rx(int itf, cdcacm_event_t *event) {
	(void)itf;
	(void)event;
	xSemaphoreGive(s_rx_ready);
}

esp_err_t usb_port_unique_id(uint8_t out[LINK_UNIQUE_ID_LEN]) {
	return esp_read_mac(out, ESP_MAC_BASE);
}

esp_err_t usb_port_start(void) {
	uint8_t mac[LINK_UNIQUE_ID_LEN];
	ESP_RETURN_ON_ERROR(usb_port_unique_id(mac), TAG, "base MAC");
	snprintf(s_serial, sizeof s_serial, "%02X%02X%02X%02X%02X%02X", mac[0], mac[1], mac[2],
	         mac[3], mac[4], mac[5]);

	s_rx_ready = xSemaphoreCreateBinary();
	s_tx_lock = xSemaphoreCreateMutex();
	ESP_RETURN_ON_FALSE(s_rx_ready && s_tx_lock, ESP_ERR_NO_MEM, TAG, "semaphores");

	tinyusb_config_t config = TINYUSB_DEFAULT_CONFIG();
	config.descriptor.device = &DEVICE;
	config.descriptor.string = STRINGS;
	config.descriptor.string_count = sizeof STRINGS / sizeof STRINGS[0];
	ESP_RETURN_ON_ERROR(tinyusb_driver_install(&config), TAG, "TinyUSB install");

	const tinyusb_config_cdcacm_t acm = {.cdc_port = CDC_PORT, .callback_rx = on_rx};
	return tinyusb_cdcacm_init(&acm);
}

// 0 when nothing is buffered and when the port is not running (before start, after stop).
static size_t cdc_read(uint8_t *out, size_t cap) {
	size_t got = 0;
	if (tinyusb_cdcacm_read(CDC_PORT, out, cap, &got) != ESP_OK) {
		return 0;
	}
	return got;
}

size_t usb_port_feed(link_rx_t *rx, uint32_t timeout_ms) {
	uint8_t chunk[LINK_MAX_FRAME];
	size_t room = sizeof rx->buf - rx->len;
	size_t got = cdc_read(chunk, room);
	if (got == 0 && room > 0 && xSemaphoreTake(s_rx_ready, pdMS_TO_TICKS(timeout_ms)) == pdTRUE) {
		got = cdc_read(chunk, room);
	}
	return link_rx_push(rx, chunk, got);
}

// The host has the port open: DTR is set.
static bool host_listening(void) {
	return tud_cdc_n_connected(CDC_PORT);
}

static size_t cdc_queue(void *ctx, const uint8_t *bytes, size_t n) {
	(void)ctx;
	return host_listening() ? tinyusb_cdcacm_write_queue(CDC_PORT, bytes, n) : 0;
}

static bool cdc_drain(void *ctx) {
	(void)ctx;
	while (host_listening()) {
		if (tinyusb_cdcacm_write_flush(CDC_PORT, pdMS_TO_TICKS(DRAIN_SLICE_MS)) == ESP_OK) {
			return true;
		}
	}
	// No stale half frame waits in the FIFO for the next app that opens the port.
	tud_cdc_n_write_clear(CDC_PORT);
	return false;
}

static const link_tx_port_t CDC_TX = {.queue = cdc_queue, .drain = cdc_drain, .ctx = NULL};

bool usb_port_send(const link_frame_t *frame) {
	xSemaphoreTake(s_tx_lock, portMAX_DELAY);
	bool sent = link_tx_send(&CDC_TX, frame);
	xSemaphoreGive(s_tx_lock);
	return sent;
}

esp_err_t usb_port_stop(void) {
	vTaskDelay(pdMS_TO_TICKS(DETACH_SETTLE_MS));
	ESP_RETURN_ON_FALSE(tud_disconnect(), ESP_FAIL, TAG, "detach");
	ESP_RETURN_ON_ERROR(tinyusb_cdcacm_deinit(CDC_PORT), TAG, "CDC deinit");
	return tinyusb_driver_uninstall();
}
