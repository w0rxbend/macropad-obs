// SPDX-License-Identifier: MIT
// CDC frame codec, protocol v2. Pure C, no SDK headers, so firmware/test runs it under ASan.
// Wire format: docs/protocol.md. The frame codec does not look inside a payload; link_msg_* does.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define LINK_SOF 0xA5
#define LINK_VERSION 0x02
#define LINK_HEADER_LEN 6
#define LINK_CRC_LEN 2
#define LINK_MAX_PAYLOAD 240
#define LINK_MAX_FRAME (LINK_HEADER_LEN + LINK_MAX_PAYLOAD + LINK_CRC_LEN)

// Largest byte run of CFG_CHUNK and CFG_DATA: the payload cap less their fixed fields.
#define LINK_CFG_CHUNK_MAX (LINK_MAX_PAYLOAD - 2)
#define LINK_CFG_DATA_MAX (LINK_MAX_PAYLOAD - 8)
#define LINK_PATH_MAX 48
#define LINK_FW_VERSION_MAX 32
#define LINK_GIT_HASH_LEN 4
#define LINK_UNIQUE_ID_LEN 6
// Longest secret of SET_CREDENTIAL: the payload cap less the kind byte (spec 8.2).
#define LINK_CREDENTIAL_MAX (LINK_MAX_PAYLOAD - 1)
#define LINK_WIFI_PASSPHRASE_MIN 8
#define LINK_WIFI_PSK_HEX_LEN 64
#define LINK_UUID_LEN 16
// ASCII "WIPE" and "BOOT" on the wire. FACTORY_RESET and BOOTLOADER carry nothing else.
#define LINK_FACTORY_RESET_MAGIC 0x45504957u
#define LINK_BOOTLOADER_MAGIC 0x544F4F42u

// Pad-to-app types have bit 7 set. The frame codec sends NOTICE and RESULT by itself.
enum link_type {
	LINK_INFO_GET = 0x01,
	LINK_CFG_READ = 0x02,
	LINK_CFG_BEGIN = 0x03,
	LINK_CFG_CHUNK = 0x04,
	LINK_CFG_COMMIT = 0x05,
	LINK_SET_CREDENTIAL = 0x06,
	LINK_CLEAR_CREDENTIALS = 0x07,
	LINK_OBS_LIST = 0x08,
	LINK_FACTORY_RESET = 0x09,
	LINK_BOOTLOADER = 0x0A,
	LINK_NOTICE = 0x80,
	LINK_RESULT = 0x81,
	LINK_INFO = 0x82,
	LINK_CFG_DATA = 0x83,
	LINK_CRED_STATUS = 0x84,
	LINK_STATUS = 0x85,
	LINK_OBS_ITEM = 0x86,
	LINK_INPUT = 0x87,
};

// First payload byte of RESULT (spec 8.2).
enum link_result {
	LINK_RESULT_OK = 0,
	LINK_RESULT_BUSY = 1,
	LINK_RESULT_STALE_SEQ = 2,
	LINK_RESULT_BAD_CRC = 3,
	LINK_RESULT_TOO_BIG = 4,
	LINK_RESULT_INVALID = 5,
};

// First payload byte of SET_CREDENTIAL (spec 8.2).
enum link_credential_kind {
	LINK_CREDENTIAL_OBS_PASSWORD = 1,
	LINK_CREDENTIAL_WIFI_PASSPHRASE = 2,
};

// The one payload byte of CRED_STATUS (spec 8.2).
enum link_cred_status {
	LINK_CRED_OK = 0,
	LINK_CRED_BAD_KIND = 1,
	LINK_CRED_BAD_LEN = 2,
	LINK_CRED_BAD_VALUE = 3,
	LINK_CRED_STORE_FAIL = 4,
};

enum link_obs_state {
	LINK_OBS_IDLE = 0, // not trying: no Wi-Fi or no URL
	LINK_OBS_CONNECTING = 1,
	LINK_OBS_REFUSED = 2,
	LINK_OBS_AUTH_FAILED = 3,
	LINK_OBS_UP = 4,
};

enum link_wifi_state {
	LINK_WIFI_NO_SSID = 0,
	LINK_WIFI_CONNECTING = 1,
	LINK_WIFI_BAD_KEY = 2,
	LINK_WIFI_NO_AP = 3,
	LINK_WIFI_UP = 4,
};

// Which OBS list an OBS_LIST request and its OBS_ITEM reply are about.
enum link_obs_list {
	LINK_LIST_SCENES = 1,
	LINK_LIST_INPUTS = 2,
	LINK_LIST_TRANSITIONS = 3,
};

// Which control an INPUT event comes from.
enum link_input_source {
	LINK_INPUT_KEY = 1,
	LINK_INPUT_BUTTON = 2,
	LINK_INPUT_KNOB_PUSH = 3,
	LINK_INPUT_KNOB_TURN = 4,
};

typedef enum {
	LINK_EMPTY, // no whole frame is buffered: push more bytes
	LINK_FRAME, // `out` is a frame that passed its CRC
	LINK_REPLY, // a frame was refused: `out` is the reply the caller must send
} link_status_t;

typedef struct {
	uint8_t type;
	uint8_t id;
	uint16_t length;
	uint8_t payload[LINK_MAX_PAYLOAD];
} link_frame_t;

typedef struct {
	uint8_t buf[LINK_MAX_FRAME];
	size_t len;
} link_rx_t;

void link_rx_init(link_rx_t *rx);

// Copies what fits and returns that count. It never overwrites a buffered byte. On a short
// count, call link_pull until LINK_EMPTY and push the rest.
size_t link_rx_push(link_rx_t *rx, const uint8_t *data, size_t n);

// Takes the next frame or reply out of the buffer. A full buffer never returns LINK_EMPTY.
// A version other than 2 gets NOTICE, a length above 240 gets RESULT too_big, a bad CRC gets
// RESULT bad_crc. Each refusal drops the SOF byte only and scans on.
link_status_t link_pull(link_rx_t *rx, link_frame_t *out);

// CRC-16/MODBUS over `data`. Check value: ASCII "123456789" -> 0x4B37.
uint16_t link_crc(const uint8_t *data, size_t len);

// Encode one frame. Returns the byte count, or 0 if it does not fit `cap` or the payload cap.
size_t link_encode(const link_frame_t *frame, uint8_t *dst, size_t cap);

// Bytes owned by someone else. After link_msg_decode they point into the decoded frame.
typedef struct {
	const uint8_t *bytes;
	size_t len;
} link_span_t;

typedef struct {
	uint16_t width;
	uint16_t height;
} link_size_t;

// The two credential fields are one bit each on the wire: set or not set, nothing else (R1).
typedef struct {
	uint8_t proto;
	bool obs_password_set;
	bool wifi_psk_set;
	uint16_t schema_min;
	uint16_t schema_max;
	uint16_t max_doc_bytes;
	uint8_t keys;
	uint8_t buttons;
	uint8_t knobs;
	link_size_t main_display;
	link_size_t strip_display;
	uint32_t capabilities;
	uint8_t board_rev;
	uint8_t git_hash[LINK_GIT_HASH_LEN];
	uint8_t unique_id[LINK_UNIQUE_ID_LEN];
	link_span_t fw_version; // printable ASCII, 0..LINK_FW_VERSION_MAX bytes
} link_info_t;

// One typed message of spec 8.2. `type` picks the member of `as`. INFO_GET, CFG_COMMIT,
// CLEAR_CREDENTIALS, FACTORY_RESET and BOOTLOADER have no fields: the codec checks the magic.
typedef struct {
	uint8_t type;
	union {
		link_info_t info;
		struct {
			uint16_t offset;
			uint8_t len; // 1..LINK_CFG_DATA_MAX
		} cfg_read;
		struct {
			uint32_t seq;
			uint16_t total;
			uint16_t offset;
			link_span_t bytes; // 0..LINK_CFG_DATA_MAX
		} cfg_data;
		struct {
			uint32_t base_seq;
			uint16_t total;
			uint32_t crc32;
			bool try_only;
		} cfg_begin;
		struct {
			uint16_t offset;
			link_span_t bytes; // 1..LINK_CFG_CHUNK_MAX
		} cfg_chunk;
		struct {
			uint8_t code; // enum link_result
			uint32_t seq;
			link_span_t path; // printable ASCII, 0..LINK_PATH_MAX bytes
		} result;
		struct {
			uint8_t kind;      // enum link_credential_kind
			link_span_t bytes; // the secret, 1..LINK_CREDENTIAL_MAX. Never log it (R1)
		} set_credential;
		struct {
			uint8_t code; // enum link_cred_status
		} cred_status;
		struct {
			uint8_t obs_state;  // enum link_obs_state
			uint8_t wifi_state; // enum link_wifi_state
			int8_t rssi_dbm;    // 0 unless Wi-Fi is up
			uint8_t ip[4];      // IPv4 in network order, 0.0.0.0 unless Wi-Fi is up
		} status;
		struct {
			uint8_t list; // enum link_obs_list
			uint16_t index;
		} obs_list;
		struct {
			uint8_t list; // enum link_obs_list
			uint16_t index;
			uint16_t total; // items in the list. 0: no item, nil UUID, no name
			uint8_t uuid[LINK_UUID_LEN];
			link_span_t name; // UTF-8 from OBS, not checked here
		} obs_item;
		struct {
			uint8_t source; // enum link_input_source
			uint8_t index;
			int8_t value; // 1 down, 0 up. For a turn: detents, never 0
		} input;
	} as;
} link_msg_t;

// Reads the payload of a frame that link_pull delivered. False for an unknown type and for a
// payload that breaks the type's rules (docs/protocol.md "Messages"). Trust boundary: every
// length and range is checked here. A false return leaves `msg` unspecified.
bool link_msg_decode(const link_frame_t *frame, link_msg_t *msg);

// The status the pad answers to a SET_CREDENTIAL or CLEAR_CREDENTIALS frame, before it stores or
// erases anything (spec 8.2). Call it for those two types only. It never gives store_fail: only
// the store knows that. link_msg_decode takes such a frame only when this gives LINK_CRED_OK.
uint8_t link_credential_check(const link_frame_t *frame);

// Writes `msg` as a frame with the given id. False for what link_msg_decode would refuse.
bool link_msg_encode(const link_msg_t *msg, uint8_t id, link_frame_t *frame);
