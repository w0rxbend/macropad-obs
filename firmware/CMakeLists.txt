# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.13)

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(macropad-obs C CXX ASM)
pico_sdk_init()

add_executable(macropad-obs
    src/main.c
    src/usb.c
    src/panel.c
    src/usb_descriptors.c
    link.c
    input.c
    st7789.c
    font8x16.c
)

target_include_directories(macropad-obs PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/src
)

target_compile_definitions(macropad-obs PRIVATE
    PICO_BOOTSEL_VIA_DOUBLE_RESET=1
    PICO_BOOTSEL_VIA_DOUBLE_RESET_TIMEOUT_MS=500
    PICO_STDIO_USB=0
)

target_link_libraries(macropad-obs
    pico_stdlib
    tinyusb_device
    tinyusb_board
    hardware_spi
    hardware_gpio
)

pico_add_extra_outputs(macropad-obs)
