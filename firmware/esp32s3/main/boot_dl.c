// SPDX-License-Identifier: MIT
// Register names are those of the IDF v6.1.1 headers: soc/esp32s3/register/soc/rtc_cntl_reg.h
// (RTC_CNTL_USB_CONF_REG, RTC_CNTL_OPTION1_REG) and usb_serial_jtag_reg.h
// (USB_SERIAL_JTAG_CONF0_REG). The order follows spec 8.2 and Arduino-ESP32
// usb_switch_to_cdc_jtag / usb_persist_restart (R18 [E15]). Not run on hardware yet (task 4.8).
#include "boot_dl.h"

#include "usb_port.h"

#include "esp_err.h"
#include "esp_private/periph_ctrl.h"
#include "esp_system.h"
#include "hal/usb_wrap_ll.h"
#include "soc/rtc_cntl_reg.h"
#include "soc/soc.h"
#include "soc/usb_serial_jtag_reg.h"

static void gate_usb_otg(void) {
	PERIPH_RCC_ATOMIC() {
		usb_wrap_ll_reset_register();
		usb_wrap_ll_enable_bus_clock(false);
	}
}

// The ROM download stack runs on the USB-Serial/JTAG over the internal PHY (R18 section 8).
static void hand_phy_to_serial_jtag(void) {
	CLEAR_PERI_REG_MASK(RTC_CNTL_USB_CONF_REG,
	                    RTC_CNTL_SW_HW_USB_PHY_SEL | RTC_CNTL_SW_USB_PHY_SEL | RTC_CNTL_USB_PAD_ENABLE);
	SET_PERI_REG_MASK(USB_SERIAL_JTAG_CONF0_REG, USB_SERIAL_JTAG_USB_PAD_ENABLE);
}

bool boot_dl_enter(cred_t *cred) {
	// device.c erased cred before it asked for this. The erase is here too, so no caller can
	// reach download mode with a secret left in flash.
	if (!cred->erase_all(cred)) {
		return false;
	}
	ESP_ERROR_CHECK(usb_port_stop());
	gate_usb_otg();
	hand_phy_to_serial_jtag();
	SET_PERI_REG_MASK(RTC_CNTL_OPTION1_REG, RTC_CNTL_FORCE_DOWNLOAD_BOOT);
	esp_restart();
}
