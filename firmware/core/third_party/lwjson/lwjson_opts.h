// SPDX-License-Identifier: MIT
// This project's LwJSON options. Not an upstream file: src/include/lwjson/lwjson_opt.h includes it.
// core/json.h names these four as its limits. They size json_reader_t, which json.c caps.
#pragma once

// One entry per object, member name and list on the way down. A GetInputList reply needs 9 and
// an InputVolumeMeters event 11 (docs/research/04-mcu-and-firmware-stack.md, [X2]).
#define LWJSON_CFG_STREAM_STACK_SIZE 16
// The longest member name the reader holds. The OBS and config names in use stay under 24 bytes.
#define LWJSON_CFG_STREAM_KEY_MAX_LEN 32
// A string of this many bytes or more is cut. An OBS_ITEM name is at most 219 bytes.
#define LWJSON_CFG_STREAM_STRING_MAX_LEN 256
// The longest number literal. A double written with 17 digits and an exponent takes 24 bytes.
#define LWJSON_CFG_STREAM_PRIMITIVE_MAX_LEN 32
