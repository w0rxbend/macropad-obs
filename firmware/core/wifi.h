// SPDX-License-Identifier: MIT
// Wi-Fi station state machine: the five STATUS states of spec 8.2, the retry backoff, and one
// strip line per failure (criterion 9). Pure C, no SDK headers. The port owns the radio: it feeds
// events in and does what each call returns. No SSID byte and no passphrase byte passes through
// here, so no state and no line can carry one (R1).
#pragma once

#include "link.h"

#include <stdbool.h>
#include <stdint.h>

// What happened. The first two come from the config document and the credential store, the rest
// from the radio driver. The port does not feed the disconnect that its own join or leave causes.
typedef enum {
	WIFI_EVT_SSID_SET, // wifi.ssid is not empty, and it or the passphrase is new
	WIFI_EVT_NO_SSID,  // wifi.ssid is empty, or there is no document
	WIFI_EVT_UP,       // joined, with an IPv4 lease
	WIFI_EVT_BAD_KEY,  // the AP refused the key
	WIFI_EVT_NO_AP,    // no AP with this SSID answered
	WIFI_EVT_LOST,     // the link dropped, or a join failed for any other reason
} wifi_event_kind_t;

typedef struct {
	wifi_event_kind_t kind;
	int8_t rssi_dbm; // WIFI_EVT_UP only
	uint8_t ip[4];   // WIFI_EVT_UP only: IPv4, network order
} wifi_event_t;

// What the port must do now.
typedef enum {
	WIFI_ACT_NONE,
	WIFI_ACT_JOIN,  // drop any link, then join with the stored SSID and passphrase
	WIFI_ACT_LEAVE, // drop the link and stay off the air
} wifi_action_t;

// The Wi-Fi fields of STATUS (spec 8.2). RSSI and IP are 0 unless the state is up.
typedef struct {
	enum link_wifi_state state;
	int8_t rssi_dbm;
	uint8_t ip[4]; // IPv4, network order
} wifi_status_t;

// Read `status`. The retry fields belong to wifi.c.
typedef struct {
	wifi_status_t status;
	bool retry_pending;
	uint8_t retry_step;
	uint16_t retry_wait_ms;
	uint32_t retry_wait_started_ms;
} wifi_t;

// Starts in no_ssid, off the air.
void wifi_init(wifi_t *wifi);

// Takes one event. The state is the last word of the driver:
//   WIFI_EVT_SSID_SET  connecting. Gives WIFI_ACT_JOIN. The retry waits start again.
//   WIFI_EVT_NO_SSID   no_ssid. Gives WIFI_ACT_LEAVE.
//   WIFI_EVT_UP        up, with the RSSI and IP of the event. The retry waits start again.
//   WIFI_EVT_BAD_KEY   bad_key.
//   WIFI_EVT_NO_AP     no_ap.
//   WIFI_EVT_LOST      connecting.
// In no_ssid every event but WIFI_EVT_SSID_SET is stale: it changes nothing and gives nothing.
// Each of the last three starts a retry wait: 1, 2, 4, 8 s, then 8 s each time. wifi_tick gives
// the join when the wait ends. A failure that comes during a wait changes the state only. A
// failure state stays through its retries, so STATUS and the strip line do not flicker.
// The 8 s cap leaves 22 s of criterion 3 (AP restart, 30 s) for the join itself. The join time
// is a spike item (spec 9 step 1) and is not measured yet.
wifi_action_t wifi_on_event(wifi_t *wifi, const wifi_event_t *event, uint32_t now_ms);

// Call on every pass of the main loop. Gives WIFI_ACT_JOIN once when a retry wait runs out.
// `now_ms` may wrap.
wifi_action_t wifi_tick(wifi_t *wifi, uint32_t now_ms);

// The strip line of a failure state: fixed printable ASCII. NULL for connecting, for up and for
// a value outside the enum.
const char *wifi_strip_line(enum link_wifi_state state);
