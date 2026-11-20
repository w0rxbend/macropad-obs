# SPDX-License-Identifier: MIT
# macropad-obs pad firmware on ESP-IDF v6.1.1 (spec section 10). `just firmware` builds it in
# espressif/idf:v6.1.1. components/fw_core links firmware/core, which has no IDF header.
cmake_minimum_required(VERSION 3.22)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(macropad-obs)
