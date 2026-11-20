# SPDX-License-Identifier: MIT
idf_component_register(SRCS main.c usb_port.c boot_dl.c
    wifi_port.c stream_lwip.c cred_nvs.c store_flash.c input_port.c
    lcd_port.c backlight.c
    PRIV_REQUIRES fw_core espressif__esp_tinyusb esp_hal_usb esp_hw_support esp_system
    esp_wifi esp_netif esp_event nvs_flash lwip esp_partition
    esp_driver_gpio esp_driver_pcnt esp_timer esp_rom
    esp_lcd esp_driver_spi esp_driver_ledc)
