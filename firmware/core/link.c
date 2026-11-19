// SPDX-License-Identifier: MIT
#include "link.h"

#include <string.h>

#define VERSION_AT 1
#define TYPE_AT 2
#define ID_AT 3
#define LENGTH_AT 4
// A RESULT from the codec stores nothing: seq 0 and no path follow the code byte.
#define RESULT_LEN 5

static const char V2_ONLY[] = "protocol v2 only";

void link_rx_init(link_rx_t *rx) {
	memset(rx, 0, sizeof(*rx));
}

size_t link_rx_push(link_rx_t *rx, const uint8_t *data, size_t n) {
	size_t room = sizeof rx->buf - rx->len;
	size_t taken = n < room ? n : room;
	memcpy(rx->buf + rx->len, data, taken);
	rx->len += taken;
	return taken;
}

uint16_t link_crc(const uint8_t *data, size_t len) {
	uint16_t crc = 0xFFFF;
	for (size_t i = 0; i < len; i++) {
		crc ^= data[i];
		for (int bit = 0; bit < 8; bit++) {
			if (crc & 1u) {
				crc = (uint16_t)((crc >> 1) ^ 0xA001u);
			} else {
				crc = (uint16_t)(crc >> 1);
			}
		}
	}
	return crc;
}

static uint16_t read_u16(const uint8_t *src) {
	return (uint16_t)(src[0] | ((uint16_t)src[1] << 8));
}

static void write_u16(uint8_t *dst, uint16_t value) {
	dst[0] = (uint8_t)(value & 0xFFu);
	dst[1] = (uint8_t)(value >> 8);
}

size_t link_encode(const link_frame_t *frame, uint8_t *dst, size_t cap) {
	if (frame->length > LINK_MAX_PAYLOAD) {
		return 0;
	}
	size_t crc_at = (size_t)LINK_HEADER_LEN + frame->length;
	if (cap < crc_at + LINK_CRC_LEN) {
		return 0;
	}
	dst[0] = LINK_SOF;
	dst[VERSION_AT] = LINK_VERSION;
	dst[TYPE_AT] = frame->type;
	dst[ID_AT] = frame->id;
	write_u16(dst + LENGTH_AT, frame->length);
	memcpy(dst + LINK_HEADER_LEN, frame->payload, frame->length);
	write_u16(dst + crc_at, link_crc(dst + VERSION_AT, crc_at - VERSION_AT));
	return crc_at + LINK_CRC_LEN;
}

static void drop_bytes(link_rx_t *rx, size_t n) {
	rx->len -= n;
	memmove(rx->buf, rx->buf + n, rx->len);
}

static void drop_to_sof(link_rx_t *rx) {
	const uint8_t *sof = memchr(rx->buf, LINK_SOF, rx->len);
	drop_bytes(rx, sof == NULL ? rx->len : (size_t)(sof - rx->buf));
}

static link_status_t refuse_with_notice(link_rx_t *rx, link_frame_t *out) {
	out->type = LINK_NOTICE;
	out->id = 0;
	out->length = (uint16_t)strlen(V2_ONLY);
	memcpy(out->payload, V2_ONLY, out->length);
	drop_bytes(rx, 1);
	return LINK_REPLY;
}

static link_status_t refuse_with_result(link_rx_t *rx, link_frame_t *out, uint8_t code) {
	out->type = LINK_RESULT;
	out->id = rx->buf[ID_AT];
	out->length = RESULT_LEN;
	memset(out->payload, 0, RESULT_LEN);
	out->payload[0] = code;
	drop_bytes(rx, 1);
	return LINK_REPLY;
}

link_status_t link_pull(link_rx_t *rx, link_frame_t *out) {
	drop_to_sof(rx);
	if (rx->len <= VERSION_AT) {
		return LINK_EMPTY;
	}
	if (rx->buf[VERSION_AT] != LINK_VERSION) {
		return refuse_with_notice(rx, out);
	}
	if (rx->len < LINK_HEADER_LEN) {
		return LINK_EMPTY;
	}
	uint16_t length = read_u16(rx->buf + LENGTH_AT);
	if (length > LINK_MAX_PAYLOAD) {
		return refuse_with_result(rx, out, LINK_RESULT_TOO_BIG);
	}
	size_t crc_at = (size_t)LINK_HEADER_LEN + length;
	if (rx->len < crc_at + LINK_CRC_LEN) {
		return LINK_EMPTY;
	}
	if (read_u16(rx->buf + crc_at) != link_crc(rx->buf + VERSION_AT, crc_at - VERSION_AT)) {
		return refuse_with_result(rx, out, LINK_RESULT_BAD_CRC);
	}
	out->type = rx->buf[TYPE_AT];
	out->id = rx->buf[ID_AT];
	out->length = length;
	memcpy(out->payload, rx->buf + LINK_HEADER_LEN, length);
	drop_bytes(rx, crc_at + LINK_CRC_LEN);
	return LINK_FRAME;
}

#define INFO_OBS_PASSWORD_SET 0x01u
#define INFO_WIFI_PSK_SET 0x02u
#define INFO_FLAGS (INFO_OBS_PASSWORD_SET | INFO_WIFI_PSK_SET)
#define CFG_BEGIN_TRY_ONLY 0x01u

// Payload cursor. A read past the end gives 0 and clears `ok`, so a decoder checks once.
typedef struct {
	const uint8_t *at;
	size_t left;
	bool ok;
} reader_t;

static uint8_t take_u8(reader_t *r) {
	if (r->left == 0) {
		r->ok = false;
		return 0;
	}
	r->left--;
	return *r->at++;
}

static uint16_t take_u16(reader_t *r) {
	uint16_t low = take_u8(r);
	return (uint16_t)(low | ((uint16_t)take_u8(r) << 8));
}

static uint32_t take_u32(reader_t *r) {
	uint32_t low = take_u16(r);
	return low | ((uint32_t)take_u16(r) << 16);
}

static void take_array(reader_t *r, uint8_t *dst, size_t n) {
	for (size_t i = 0; i < n; i++) {
		dst[i] = take_u8(r);
	}
}

static link_size_t take_size(reader_t *r) {
	link_size_t size;
	size.width = take_u16(r);
	size.height = take_u16(r);
	return size;
}

static link_span_t take_rest(reader_t *r) {
	link_span_t rest = {.bytes = r->at, .len = r->left};
	r->at += r->left;
	r->left = 0;
	return rest;
}

// A write past the payload cap is not stored. `length` still counts it, so the caller sees it.
static void put_u8(link_frame_t *frame, uint8_t byte) {
	if (frame->length < LINK_MAX_PAYLOAD) {
		frame->payload[frame->length] = byte;
	}
	if (frame->length <= LINK_MAX_PAYLOAD) {
		frame->length++;
	}
}

static void put_u16(link_frame_t *frame, uint16_t value) {
	put_u8(frame, (uint8_t)(value & 0xFFu));
	put_u8(frame, (uint8_t)(value >> 8));
}

static void put_u32(link_frame_t *frame, uint32_t value) {
	put_u16(frame, (uint16_t)(value & 0xFFFFu));
	put_u16(frame, (uint16_t)(value >> 16));
}

static void put_bytes(link_frame_t *frame, const uint8_t *src, size_t n) {
	for (size_t i = 0; i < n && frame->length <= LINK_MAX_PAYLOAD; i++) {
		put_u8(frame, src[i]);
	}
}

static void put_size(link_frame_t *frame, link_size_t size) {
	put_u16(frame, size.width);
	put_u16(frame, size.height);
}

static bool printable(link_span_t text) {
	for (size_t i = 0; i < text.len; i++) {
		if (text.bytes[i] < 0x20 || text.bytes[i] > 0x7E) {
			return false;
		}
	}
	return true;
}

static bool decode_empty(reader_t *r, link_msg_t *msg) {
	(void)r;
	(void)msg;
	return true;
}

static void encode_empty(const link_msg_t *msg, link_frame_t *frame) {
	(void)msg;
	(void)frame;
}

static bool decode_cfg_read(reader_t *r, link_msg_t *msg) {
	msg->as.cfg_read.offset = take_u16(r);
	msg->as.cfg_read.len = take_u8(r);
	return msg->as.cfg_read.len >= 1 && msg->as.cfg_read.len <= LINK_CFG_DATA_MAX;
}

static void encode_cfg_read(const link_msg_t *msg, link_frame_t *frame) {
	put_u16(frame, msg->as.cfg_read.offset);
	put_u8(frame, msg->as.cfg_read.len);
}

static bool decode_cfg_begin(reader_t *r, link_msg_t *msg) {
	msg->as.cfg_begin.base_seq = take_u32(r);
	msg->as.cfg_begin.total = take_u16(r);
	msg->as.cfg_begin.crc32 = take_u32(r);
	uint8_t flags = take_u8(r);
	msg->as.cfg_begin.try_only = (flags & CFG_BEGIN_TRY_ONLY) != 0;
	return (flags & ~CFG_BEGIN_TRY_ONLY) == 0;
}

static void encode_cfg_begin(const link_msg_t *msg, link_frame_t *frame) {
	put_u32(frame, msg->as.cfg_begin.base_seq);
	put_u16(frame, msg->as.cfg_begin.total);
	put_u32(frame, msg->as.cfg_begin.crc32);
	put_u8(frame, msg->as.cfg_begin.try_only ? CFG_BEGIN_TRY_ONLY : 0);
}

static bool decode_cfg_chunk(reader_t *r, link_msg_t *msg) {
	msg->as.cfg_chunk.offset = take_u16(r);
	msg->as.cfg_chunk.bytes = take_rest(r);
	return msg->as.cfg_chunk.bytes.len >= 1;
}

static void encode_cfg_chunk(const link_msg_t *msg, link_frame_t *frame) {
	put_u16(frame, msg->as.cfg_chunk.offset);
	put_bytes(frame, msg->as.cfg_chunk.bytes.bytes, msg->as.cfg_chunk.bytes.len);
}

static bool decode_cfg_data(reader_t *r, link_msg_t *msg) {
	msg->as.cfg_data.seq = take_u32(r);
	msg->as.cfg_data.total = take_u16(r);
	msg->as.cfg_data.offset = take_u16(r);
	msg->as.cfg_data.bytes = take_rest(r);
	return true;
}

static void encode_cfg_data(const link_msg_t *msg, link_frame_t *frame) {
	put_u32(frame, msg->as.cfg_data.seq);
	put_u16(frame, msg->as.cfg_data.total);
	put_u16(frame, msg->as.cfg_data.offset);
	put_bytes(frame, msg->as.cfg_data.bytes.bytes, msg->as.cfg_data.bytes.len);
}

static bool decode_result(reader_t *r, link_msg_t *msg) {
	msg->as.result.code = take_u8(r);
	msg->as.result.seq = take_u32(r);
	msg->as.result.path = take_rest(r);
	return msg->as.result.code <= LINK_RESULT_INVALID && msg->as.result.path.len <= LINK_PATH_MAX &&
	       printable(msg->as.result.path);
}

static void encode_result(const link_msg_t *msg, link_frame_t *frame) {
	put_u8(frame, msg->as.result.code);
	put_u32(frame, msg->as.result.seq);
	put_bytes(frame, msg->as.result.path.bytes, msg->as.result.path.len);
}

static bool decode_info(reader_t *r, link_msg_t *msg) {
	link_info_t *info = &msg->as.info;
	info->proto = take_u8(r);
	uint8_t flags = take_u8(r);
	info->obs_password_set = (flags & INFO_OBS_PASSWORD_SET) != 0;
	info->wifi_psk_set = (flags & INFO_WIFI_PSK_SET) != 0;
	info->schema_min = take_u16(r);
	info->schema_max = take_u16(r);
	info->max_doc_bytes = take_u16(r);
	info->keys = take_u8(r);
	info->buttons = take_u8(r);
	info->knobs = take_u8(r);
	info->main_display = take_size(r);
	info->strip_display = take_size(r);
	info->capabilities = take_u32(r);
	info->board_rev = take_u8(r);
	take_array(r, info->git_hash, sizeof info->git_hash);
	take_array(r, info->unique_id, sizeof info->unique_id);
	info->fw_version = take_rest(r);
	return (flags & ~INFO_FLAGS) == 0 && info->fw_version.len <= LINK_FW_VERSION_MAX &&
	       printable(info->fw_version);
}

static void encode_info(const link_msg_t *msg, link_frame_t *frame) {
	const link_info_t *info = &msg->as.info;
	put_u8(frame, info->proto);
	put_u8(frame, (uint8_t)((info->obs_password_set ? INFO_OBS_PASSWORD_SET : 0) |
	                        (info->wifi_psk_set ? INFO_WIFI_PSK_SET : 0)));
	put_u16(frame, info->schema_min);
	put_u16(frame, info->schema_max);
	put_u16(frame, info->max_doc_bytes);
	put_u8(frame, info->keys);
	put_u8(frame, info->buttons);
	put_u8(frame, info->knobs);
	put_size(frame, info->main_display);
	put_size(frame, info->strip_display);
	put_u32(frame, info->capabilities);
	put_u8(frame, info->board_rev);
	put_bytes(frame, info->git_hash, sizeof info->git_hash);
	put_bytes(frame, info->unique_id, sizeof info->unique_id);
	put_bytes(frame, info->fw_version.bytes, info->fw_version.len);
}

static bool all_hex(link_span_t text) {
	for (size_t i = 0; i < text.len; i++) {
		uint8_t c = text.bytes[i];
		bool digit = c >= '0' && c <= '9';
		bool letter = (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
		if (!digit && !letter) {
			return false;
		}
	}
	return true;
}

static uint8_t wifi_passphrase_status(link_span_t text) {
	if (text.len < LINK_WIFI_PASSPHRASE_MIN || text.len > LINK_WIFI_PSK_HEX_LEN) {
		return LINK_CRED_BAD_LEN;
	}
	bool allowed = text.len == LINK_WIFI_PSK_HEX_LEN ? all_hex(text) : printable(text);
	return allowed ? LINK_CRED_OK : LINK_CRED_BAD_VALUE;
}

static uint8_t set_credential_status(link_span_t payload) {
	if (payload.len == 0) {
		return LINK_CRED_BAD_LEN;
	}
	uint8_t kind = payload.bytes[0];
	link_span_t secret = {.bytes = payload.bytes + 1, .len = payload.len - 1};
	if (kind != LINK_CREDENTIAL_OBS_PASSWORD && kind != LINK_CREDENTIAL_WIFI_PASSPHRASE) {
		return LINK_CRED_BAD_KIND;
	}
	if (secret.len == 0) {
		return LINK_CRED_BAD_LEN;
	}
	return kind == LINK_CREDENTIAL_WIFI_PASSPHRASE ? wifi_passphrase_status(secret) : LINK_CRED_OK;
}

uint8_t link_credential_check(const link_frame_t *frame) {
	if (frame->length > LINK_MAX_PAYLOAD) {
		return LINK_CRED_BAD_LEN;
	}
	if (frame->type == LINK_CLEAR_CREDENTIALS) {
		return frame->length == 0 ? LINK_CRED_OK : LINK_CRED_BAD_LEN;
	}
	link_span_t payload = {.bytes = frame->payload, .len = frame->length};
	return set_credential_status(payload);
}

static bool decode_set_credential(reader_t *r, link_msg_t *msg) {
	link_span_t payload = {.bytes = r->at, .len = r->left};
	msg->as.set_credential.kind = take_u8(r);
	msg->as.set_credential.bytes = take_rest(r);
	return set_credential_status(payload) == LINK_CRED_OK;
}

static void encode_set_credential(const link_msg_t *msg, link_frame_t *frame) {
	put_u8(frame, msg->as.set_credential.kind);
	put_bytes(frame, msg->as.set_credential.bytes.bytes, msg->as.set_credential.bytes.len);
}

static bool decode_cred_status(reader_t *r, link_msg_t *msg) {
	msg->as.cred_status.code = take_u8(r);
	return msg->as.cred_status.code <= LINK_CRED_STORE_FAIL;
}

static void encode_cred_status(const link_msg_t *msg, link_frame_t *frame) {
	put_u8(frame, msg->as.cred_status.code);
}

static bool decode_status(reader_t *r, link_msg_t *msg) {
	msg->as.status.obs_state = take_u8(r);
	msg->as.status.wifi_state = take_u8(r);
	msg->as.status.rssi_dbm = (int8_t)take_u8(r);
	take_array(r, msg->as.status.ip, sizeof msg->as.status.ip);
	return msg->as.status.obs_state <= LINK_OBS_UP && msg->as.status.wifi_state <= LINK_WIFI_UP;
}

static void encode_status(const link_msg_t *msg, link_frame_t *frame) {
	put_u8(frame, msg->as.status.obs_state);
	put_u8(frame, msg->as.status.wifi_state);
	put_u8(frame, (uint8_t)msg->as.status.rssi_dbm);
	put_bytes(frame, msg->as.status.ip, sizeof msg->as.status.ip);
}

static bool is_obs_list(uint8_t list) {
	return list >= LINK_LIST_SCENES && list <= LINK_LIST_TRANSITIONS;
}

static bool decode_obs_list(reader_t *r, link_msg_t *msg) {
	msg->as.obs_list.list = take_u8(r);
	msg->as.obs_list.index = take_u16(r);
	return is_obs_list(msg->as.obs_list.list);
}

static void encode_obs_list(const link_msg_t *msg, link_frame_t *frame) {
	put_u8(frame, msg->as.obs_list.list);
	put_u16(frame, msg->as.obs_list.index);
}

static bool decode_obs_item(reader_t *r, link_msg_t *msg) {
	msg->as.obs_item.list = take_u8(r);
	msg->as.obs_item.index = take_u16(r);
	msg->as.obs_item.total = take_u16(r);
	take_array(r, msg->as.obs_item.uuid, sizeof msg->as.obs_item.uuid);
	msg->as.obs_item.name = take_rest(r);
	return is_obs_list(msg->as.obs_item.list);
}

static void encode_obs_item(const link_msg_t *msg, link_frame_t *frame) {
	put_u8(frame, msg->as.obs_item.list);
	put_u16(frame, msg->as.obs_item.index);
	put_u16(frame, msg->as.obs_item.total);
	put_bytes(frame, msg->as.obs_item.uuid, sizeof msg->as.obs_item.uuid);
	put_bytes(frame, msg->as.obs_item.name.bytes, msg->as.obs_item.name.len);
}

static bool decode_input(reader_t *r, link_msg_t *msg) {
	msg->as.input.source = take_u8(r);
	msg->as.input.index = take_u8(r);
	msg->as.input.value = (int8_t)take_u8(r);
	uint8_t source = msg->as.input.source;
	int8_t value = msg->as.input.value;
	if (source == LINK_INPUT_KNOB_TURN) {
		return value != 0;
	}
	return source >= LINK_INPUT_KEY && source <= LINK_INPUT_KNOB_PUSH && (value == 0 || value == 1);
}

static void encode_input(const link_msg_t *msg, link_frame_t *frame) {
	put_u8(frame, msg->as.input.source);
	put_u8(frame, msg->as.input.index);
	put_u8(frame, (uint8_t)msg->as.input.value);
}

static bool decode_factory_reset(reader_t *r, link_msg_t *msg) {
	(void)msg;
	return take_u32(r) == LINK_FACTORY_RESET_MAGIC;
}

static void encode_factory_reset(const link_msg_t *msg, link_frame_t *frame) {
	(void)msg;
	put_u32(frame, LINK_FACTORY_RESET_MAGIC);
}

static bool decode_bootloader(reader_t *r, link_msg_t *msg) {
	(void)msg;
	return take_u32(r) == LINK_BOOTLOADER_MAGIC;
}

static void encode_bootloader(const link_msg_t *msg, link_frame_t *frame) {
	(void)msg;
	put_u32(frame, LINK_BOOTLOADER_MAGIC);
}

// One row per typed message. A new type is a new row and its two functions.
typedef struct {
	uint8_t type;
	bool (*decode)(reader_t *r, link_msg_t *msg);
	void (*encode)(const link_msg_t *msg, link_frame_t *frame);
} msg_codec_t;

static const msg_codec_t MSG_CODECS[] = {
	{LINK_INFO_GET, decode_empty, encode_empty},
	{LINK_CFG_READ, decode_cfg_read, encode_cfg_read},
	{LINK_CFG_BEGIN, decode_cfg_begin, encode_cfg_begin},
	{LINK_CFG_CHUNK, decode_cfg_chunk, encode_cfg_chunk},
	{LINK_CFG_COMMIT, decode_empty, encode_empty},
	{LINK_SET_CREDENTIAL, decode_set_credential, encode_set_credential},
	{LINK_CLEAR_CREDENTIALS, decode_empty, encode_empty},
	{LINK_OBS_LIST, decode_obs_list, encode_obs_list},
	{LINK_FACTORY_RESET, decode_factory_reset, encode_factory_reset},
	{LINK_BOOTLOADER, decode_bootloader, encode_bootloader},
	{LINK_RESULT, decode_result, encode_result},
	{LINK_INFO, decode_info, encode_info},
	{LINK_CFG_DATA, decode_cfg_data, encode_cfg_data},
	{LINK_CRED_STATUS, decode_cred_status, encode_cred_status},
	{LINK_STATUS, decode_status, encode_status},
	{LINK_OBS_ITEM, decode_obs_item, encode_obs_item},
	{LINK_INPUT, decode_input, encode_input},
};

static const msg_codec_t *codec_for(uint8_t type) {
	for (size_t i = 0; i < sizeof MSG_CODECS / sizeof MSG_CODECS[0]; i++) {
		if (MSG_CODECS[i].type == type) {
			return &MSG_CODECS[i];
		}
	}
	return NULL;
}

bool link_msg_decode(const link_frame_t *frame, link_msg_t *msg) {
	const msg_codec_t *codec = codec_for(frame->type);
	if (codec == NULL || frame->length > LINK_MAX_PAYLOAD) {
		return false;
	}
	reader_t reader = {.at = frame->payload, .left = frame->length, .ok = true};
	msg->type = frame->type;
	bool in_range = codec->decode(&reader, msg);
	return in_range && reader.ok && reader.left == 0;
}

bool link_msg_encode(const link_msg_t *msg, uint8_t id, link_frame_t *frame) {
	const msg_codec_t *codec = codec_for(msg->type);
	if (codec == NULL) {
		return false;
	}
	frame->type = msg->type;
	frame->id = id;
	frame->length = 0;
	codec->encode(msg, frame);
	// The rules live in the decoders only: what was written must read back.
	link_msg_t read_back;
	return frame->length <= LINK_MAX_PAYLOAD && link_msg_decode(frame, &read_back);
}
