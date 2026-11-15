// SPDX-License-Identifier: MIT
#include "tusb.h"

#include "pins.h"

#define USB_BCD 0x0200
#define CONFIG_TOTAL_LEN (TUD_CONFIG_DESC_LEN + TUD_CDC_DESC_LEN)

tusb_desc_device_t const desc_device = {
	.bLength = sizeof(tusb_desc_device_t),
	.bDescriptorType = TUSB_DESC_DEVICE,
	.bcdUSB = USB_BCD,
	.bDeviceClass = TUSB_CLASS_MISC,
	.bDeviceSubClass = MISC_SUBCLASS_COMMON,
	.bDeviceProtocol = MISC_PROTOCOL_IAD,
	.bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
	.idVendor = USB_VID,
	.idProduct = USB_PID,
	.bcdDevice = 0x0100,
	.iManufacturer = 0x01,
	.iProduct = 0x02,
	.iSerialNumber = 0x03,
	.bNumConfigurations = 0x01,
};

uint8_t const *tud_descriptor_device_cb(void) {
	return (uint8_t const *)&desc_device;
}

uint8_t const desc_configuration[] = {
	TUD_CONFIG_DESCRIPTOR(1, 2, 0, CONFIG_TOTAL_LEN, 0x00, 125),
	TUD_CDC_DESCRIPTOR(0, 4, 0x81, 8, 0x02, 0x82, 64),
};

uint8_t const *tud_descriptor_configuration_cb(uint8_t index) {
	(void)index;
	return desc_configuration;
}

enum { STR_LANG = 0, STR_MANUFACTURER, STR_PRODUCT, STR_SERIAL, STR_CDC };

static char const *words[] = {
	[STR_MANUFACTURER] = "worxbend",
	[STR_PRODUCT] = "macropad-obs",
	[STR_SERIAL] = "obs",
	[STR_CDC] = "CDC",
};

static uint16_t desc_str[32];

uint16_t const *tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
	(void)langid;
	uint8_t count;
	if (index == STR_LANG) {
		desc_str[1] = 0x0409;
		count = 1;
	} else {
		if (index >= sizeof words / sizeof words[0] || words[index] == 0) {
			return 0;
		}
		const char *text = words[index];
		count = 0;
		while (text[count] != '\0' && count < 31) {
			desc_str[1 + count] = (uint16_t)text[count];
			count++;
		}
	}
	desc_str[0] = (uint16_t)((TUSB_DESC_STRING << 8) | (2 * count + 2));
	return desc_str;
}
