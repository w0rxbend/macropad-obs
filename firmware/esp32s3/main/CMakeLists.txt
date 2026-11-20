# SPDX-License-Identifier: MIT
idf_component_register(SRCS main.c usb_port.c boot_dl.c
    PRIV_REQUIRES fw_core espressif__esp_tinyusb esp_hal_usb esp_hw_support esp_system)
