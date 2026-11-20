# SPDX-License-Identifier: MIT
# view.c is padsim's document-to-widget glue (padsim/view.h); the port shows the same view.
set(padsim ${CMAKE_CURRENT_LIST_DIR}/../../padsim)
idf_component_register(SRCS main.c usb_port.c boot_dl.c
    wifi_port.c stream_lwip.c cred_nvs.c store_flash.c input_port.c
    lcd_port.c backlight.c power.c settings.c cc_sense.c ${padsim}/view.c
    PRIV_INCLUDE_DIRS ${padsim}
    PRIV_REQUIRES fw_core espressif__esp_tinyusb esp_hal_usb esp_hw_support esp_system
    esp_wifi esp_netif esp_event nvs_flash lwip esp_partition
    esp_driver_gpio esp_driver_pcnt esp_timer esp_rom
    esp_lcd esp_driver_spi esp_driver_ledc esp_adc esp_app_format heap)

# INFO git_hash: the first 4 bytes of the commit (docs/protocol.md). 0 outside a git checkout.
# Configure runs again when HEAD moves, so a rebuild after a commit carries the new hash.
execute_process(COMMAND git rev-parse --short=8 HEAD
    WORKING_DIRECTORY ${CMAKE_CURRENT_LIST_DIR}
    OUTPUT_VARIABLE git_hash OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET RESULT_VARIABLE git_status)
execute_process(COMMAND git rev-parse --path-format=absolute --git-path logs/HEAD
    WORKING_DIRECTORY ${CMAKE_CURRENT_LIST_DIR}
    OUTPUT_VARIABLE git_log OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
if(NOT git_status EQUAL 0 OR NOT git_hash MATCHES "^[0-9a-f]+$")
    message(WARNING "no git commit: INFO git_hash is 0")
    set(git_hash 0)
endif()
if(EXISTS "${git_log}")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${git_log})
endif()
target_compile_definitions(${COMPONENT_LIB} PRIVATE GIT_HASH=0x${git_hash}u)
