# SPDX-License-Identifier: MIT
# The pure C core (firmware/core) as an IDF component. The core has no IDF header (spec 5) and
# keeps the host build's -Wextra -Werror here.
set(core ${CMAKE_CURRENT_LIST_DIR}/../../../core)
set(lwjson ${core}/third_party/lwjson)
idf_component_register(
    SRCS ${core}/actions.c ${core}/config.c ${core}/crypto.c ${core}/device.c
         ${core}/font_noto14.c ${core}/font_noto20.c ${core}/font_noto28.c ${core}/input.c
         ${core}/json.c ${core}/link.c ${core}/obs.c ${core}/obs_state.c ${core}/panels.c
         ${core}/render.c ${core}/store.c ${core}/ui.c ${core}/wifi.c ${core}/ws.c
         ${lwjson}/src/lwjson/lwjson_stream.c
    INCLUDE_DIRS ${core} ${lwjson} ${lwjson}/src/include)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wextra -Werror)
