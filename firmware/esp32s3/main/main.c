// SPDX-License-Identifier: MIT
// Entry point (task 4.7): the ports, the task layout, the task watchdog and the power cap.
//
// Tasks. One app task owns every core module (link, device and store, wifi, obs, actions, ui,
// render), as padsim's one loop does, so the core needs no lock. It runs on core 1. The ports keep
// their own tasks: input_scan (1 kHz, input_port.c) above the app task, TinyUSB (esp_tinyusb),
// and the IDF Wi-Fi, lwIP and event tasks, which sit on core 0.
//
// Watchdog. The task watchdog watches the app task and both idle tasks and panics, so the pad
// restarts, after WATCHDOG_MS without a pass. The next boot logs the reset reason (task 4.8).
//
// Power (power.h). Backlights and Wi-Fi stay off until USB configures, or POWER_ENUMERATION_WAIT_MS
// pass with no configuration (a charger). Then both backlights run under the board.toml cap, and a
// 1.5 A CC advert lifts it. The cap is MEASURE until S.3 records the 3V3 current.
//
// No log line carries a secret or the SSID (R1, CLAUDE.md).
#include "backlight.h"
#include "boot_dl.h"
#include "cc_sense.h"
#include "cred_nvs.h"
#include "input_port.h"
#include "lcd_port.h"
#include "pins.h"
#include "power.h"
#include "settings.h"
#include "store_flash.h"
#include "stream_lwip.h"
#include "usb_port.h"
#include "wifi_port.h"

#include "actions.h"
#include "device.h"
#include "link.h"
#include "obs.h"
#include "obs_state.h"
#include "render.h"
#include "ui.h"
#include "view.h"
#include "wifi.h"

#include "esp_app_desc.h"
#include "esp_check.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#define APP_CORE 1
#define APP_PRIORITY 5
#define INPUT_PRIORITY (APP_PRIORITY + 1)
// Holds the core's working buffers that live on the stack (layouts, view, request text).
#define APP_STACK 16384
// One FreeRTOS tick at CONFIG_FREERTOS_HZ 100: the app task blocks on the CDC this long when the
// host is quiet, so core 1's idle task runs and the watchdog sees it.
#define PASS_MS 10
// Above the longest pass: a 3 s stream connect plus a 3 s send (stream_lwip.c), a partition
// erase, a full frame of both panels at 13.3 MHz. A host that holds the port open and never
// reads blocks usb_port_send (spec 8.1) and trips it too: the pad then restarts. Design value.
#define WATCHDOG_MS 10000
#define REQUEST_MAX 320

static const char *TAG = "macropad-obs";

// What decides which document the panels and the map follow.
typedef struct {
	store_state_t state;
	uint32_t seq;
	bool trying;
} document_key_t;

typedef struct {
	link_info_t identity;
	cred_nvs_t cred;
	store_flash_slots_t slots;
	link_rx_t rx;
	stream_lwip_t stream;
	device_t device;
	power_t power;
	power_grant_t grant;
	uint16_t backlight[UI_DISPLAYS];
	wifi_t wifi;
	bool radio_allowed;
	obs_t obs;
	obs_state_t obs_state;
	bool obs_dirty; // the OBS address, auth mode or password changed since the last obs_start
	actions_t actions;
	ui_model_t ui;
	render_t render;
	action_map_t map;
	view_labels_t labels;
	settings_t settings;
	document_key_t shown;
	bool shown_once;
	uint8_t stored[CONFIG_MAX_BYTES];
	char password[LINK_CREDENTIAL_MAX + 1]; // only for obs_start; wiped when cred is erased
	uint32_t next_action_id;
} pad_t;

static pad_t pad;

static uint32_t now_ms(void) {
	return (uint32_t)(esp_timer_get_time() / 1000);
}

static uint32_t next_random(void) {
	return esp_random();
}

static void send_frame(const link_frame_t *frame) {
	if (!usb_port_send(frame)) {
		ESP_LOGD(TAG, "frame 0x%02x dropped: the port is closed", frame->type);
	}
}

// ---- Network: fw-wifi and fw-obs follow the document and the credentials ----

static void wifi_do(wifi_action_t action) {
	if (action == WIFI_ACT_NONE) {
		return;
	}
	esp_err_t err = wifi_port_act(action, pad.settings.ssid, &pad.cred.cred);
	if (err != ESP_OK) {
		ESP_LOGW(TAG, "wifi action %d: %s", action, esp_err_to_name(err));
	}
}

// Tells fw-wifi the SSID now in the document, or that there is none. Also re-joins after a new
// passphrase. Held until the power cap lets the radio run.
static void wifi_select(uint32_t now) {
	if (!pad.radio_allowed) {
		return;
	}
	wifi_event_kind_t kind = pad.settings.ssid[0] != '\0' ? WIFI_EVT_SSID_SET : WIFI_EVT_NO_SSID;
	wifi_do(wifi_on_event(&pad.wifi, &(wifi_event_t){.kind = kind}, now));
}

static void serve_wifi(uint32_t now) {
	if (!pad.radio_allowed && pad.grant.radio) {
		pad.radio_allowed = true;
		wifi_select(now);
	}
	if (!pad.radio_allowed) {
		return;
	}
	wifi_event_t event;
	while (wifi_port_next_event(&event, 0)) {
		wifi_do(wifi_on_event(&pad.wifi, &event, now));
	}
	wifi_do(wifi_tick(&pad.wifi, now));
}

static void start_obs(uint32_t now) {
	const settings_t *s = &pad.settings;
	size_t len = 0;
	memset(pad.password, 0, sizeof pad.password);
	if (s->obs_auth) {
		len = pad.cred.cred.get(&pad.cred.cred, LINK_CREDENTIAL_OBS_PASSWORD, (uint8_t *)pad.password,
		                        sizeof pad.password - 1);
	}
	if (obs_start(&pad.obs, s->obs_ip, s->obs_port, len > 0 ? pad.password : NULL, len, now)) {
		pad.obs_dirty = false;
	}
}

// A changed address, auth mode or password stops the client, retrying or up, and starts it on
// the new ones. Without Wi-Fi or an OBS entry it stays idle; it starts when both are back. A
// stopped client (wrong password, too old, refused, kicked) waits for a change.
static void serve_obs(uint32_t now) {
	bool wanted = pad.wifi.status.state == LINK_WIFI_UP && pad.settings.has_obs;
	if (!wanted || pad.obs_dirty) {
		obs_stop(&pad.obs);
	}
	if (wanted && pad.obs.status == OBS_IDLE) {
		start_obs(now);
	}
	obs_poll(&pad.obs, now);
}

// cred was erased: drop the RAM copy of the password, join and log in again without them.
static void on_credentials_erased(uint32_t now) {
	memset(pad.password, 0, sizeof pad.password);
	pad.obs_dirty = true;
	wifi_select(now);
}

// A new passphrase joins again; a new password logs in again on the next pass.
static void on_credential_stored(enum link_credential_kind kind, uint32_t now) {
	if (kind == LINK_CREDENTIAL_OBS_PASSWORD) {
		pad.obs_dirty = true;
	} else if (kind == LINK_CREDENTIAL_WIFI_PASSPHRASE) {
		wifi_select(now);
	}
}

static bool same_network(const settings_t *a, const settings_t *b) {
	return strcmp(a->ssid, b->ssid) == 0;
}

static bool same_obs(const settings_t *a, const settings_t *b) {
	return a->has_obs == b->has_obs && memcmp(a->obs_ip, b->obs_ip, sizeof a->obs_ip) == 0 &&
	       a->obs_port == b->obs_port && a->obs_auth == b->obs_auth;
}

// ---- The document: map, layouts, labels and settings ----

static link_span_t current_document(void) {
	link_span_t draft = device_draft(&pad.device);
	const store_t *store = &pad.device.store;
	if (draft.len > 0) {
		return draft;
	}
	if (store->state == STORE_LOADED && store_read(store, 0, pad.stored, store->doc.len)) {
		return (link_span_t){.bytes = pad.stored, .len = store->doc.len};
	}
	return (link_span_t){.bytes = NULL, .len = 0};
}

static bool layout_shows_meter(const ui_layout_t *layout) {
	for (size_t w = 0; w < layout->count; w++) {
		const ui_widget_t *widget = &layout->widget[w];
		for (size_t part = 0; widget->kind == UI_KIND_STRIP && part < widget->item_count; part++) {
			if (widget->items[part] == UI_PART_METER) {
				return true;
			}
		}
	}
	return false;
}

// The factory defaults are an empty map and black panels, as in padsim.
static void apply_layouts(link_span_t doc) {
	static ui_layout_t layouts[UI_DISPLAYS];
	memset(&pad.map, 0, sizeof pad.map);
	memset(layouts, 0, sizeof layouts);
	if (doc.len > 0) {
		if (!actions_parse(&pad.map, doc.bytes, doc.len)) {
			memset(&pad.map, 0, sizeof pad.map);
		}
		if (!ui_parse(layouts, doc.bytes, doc.len)) {
			memset(layouts, 0, sizeof layouts);
		}
		view_labels_parse(&pad.labels, doc.bytes, doc.len);
	} else {
		memset(&pad.labels, 0, sizeof pad.labels);
	}
	actions_init(&pad.actions, &pad.map);
	ui_apply(&pad.ui, layouts);
	for (size_t knob = 0; knob < INPUT_KNOBS; knob++) {
		obs_state_watch(&pad.obs_state, knob, pad.map.knobs[knob].input);
	}
	obs_state_show_meters(&pad.obs_state,
	                      layout_shows_meter(&layouts[UI_MAIN]) || layout_shows_meter(&layouts[UI_STRIP]));
}

static void apply_settings(link_span_t doc, uint32_t now) {
	settings_t before = pad.settings;
	settings_parse(&pad.settings, doc.bytes, doc.len);
	if (!same_obs(&before, &pad.settings)) {
		pad.obs_dirty = true;
	}
	if (!same_network(&before, &pad.settings)) {
		wifi_select(now);
	}
}

static bool same_key(const document_key_t *a, const document_key_t *b) {
	return a->state == b->state && a->seq == b->seq && a->trying == b->trying;
}

static void follow_document(uint32_t now) {
	const store_t *store = &pad.device.store;
	document_key_t key = {
	    .state = store->state,
	    .seq = store->state == STORE_NONE ? 0 : store->doc.seq,
	    .trying = device_draft(&pad.device).len > 0,
	};
	if (pad.shown_once && same_key(&key, &pad.shown)) {
		return;
	}
	pad.shown = key;
	pad.shown_once = true;
	link_span_t doc = current_document();
	apply_layouts(doc);
	apply_settings(doc, now);
}

// ---- The CDC link ----

// SET_CREDENTIAL, CLEAR_CREDENTIALS and FACTORY_RESET reply CRED_STATUS; only `ok` changed cred.
// BOOTLOADER also erases cred, but the pad leaves the app right after.
static void follow_credentials(const link_frame_t *frame, const link_frame_t *reply, uint32_t now) {
	bool ok = reply->type == LINK_CRED_STATUS && reply->length == 1 && reply->payload[0] == LINK_CRED_OK;
	if (!ok) {
		return;
	}
	if (frame->type == LINK_SET_CREDENTIAL) {
		on_credential_stored((enum link_credential_kind)frame->payload[0], now);
	} else if (frame->type == LINK_CLEAR_CREDENTIALS || frame->type == LINK_FACTORY_RESET) {
		on_credentials_erased(now);
	}
}

static void enter_download_mode(void) {
	ESP_LOGI(TAG, "BOOTLOADER: erasing cred, then ROM download mode");
	if (!boot_dl_enter(&pad.cred.cred)) {
		ESP_LOGE(TAG, "BOOTLOADER: cred erase failed, staying in the app");
	}
}

static void on_frame(const link_frame_t *frame, uint32_t now) {
	link_frame_t reply;
	if (!device_handle(&pad.device, now, frame, &reply)) {
		ESP_LOGE(TAG, "no reply could be encoded for type 0x%02x", frame->type);
		return;
	}
	send_frame(&reply);
	follow_document(now);
	follow_credentials(frame, &reply, now);
	if (device_bootloader_asked(&pad.device)) {
		enter_download_mode();
	}
}

static void serve_link(uint32_t now) {
	usb_port_feed(&pad.rx, PASS_MS);
	link_frame_t frame;
	link_status_t status;
	while ((status = link_pull(&pad.rx, &frame)) != LINK_EMPTY) {
		if (status == LINK_FRAME) {
			on_frame(&frame, now);
		} else {
			send_frame(&frame);
		}
	}
}

static void report_status(void) {
	link_frame_t frame;
	if (device_status(&pad.device, obs_link_state(pad.obs.status), &pad.wifi.status, &frame)) {
		send_frame(&frame);
	}
}

// ---- Controls and actions ----

static void send_request(const action_request_t *request) {
	char text[REQUEST_MAX];
	if (pad.obs.status != OBS_UP) {
		return;
	}
	uint32_t id = pad.next_action_id++;
	int len = request->data[0] == '\0'
	              ? snprintf(text, sizeof text, "{\"op\":6,\"d\":{\"requestType\":\"%s\",\"requestId\":\"a%" PRIu32 "\"}}",
	                         request->type, id)
	              : snprintf(text, sizeof text,
	                         "{\"op\":6,\"d\":{\"requestType\":\"%s\",\"requestId\":\"a%" PRIu32 "\",\"requestData\":%s}}",
	                         request->type, id, request->data);
	if (len > 0 && (size_t)len < sizeof text) {
		ws_send_text(&pad.obs.ws, text, (size_t)len);
	}
}

static void on_input_event(const input_event_t *event, uint32_t now) {
	link_frame_t frame;
	action_request_t request;
	if (!device_input(&pad.device, event)) {
		ESP_LOGE(TAG, "the clear combination could not erase the flash");
	} else if (event->source == INPUT_SOURCE_CLEAR) {
		on_credentials_erased(now);
	}
	follow_document(now);
	if (device_input_frame(event, &frame)) {
		send_frame(&frame);
	}
	if (actions_on_input(&pad.actions, &pad.obs_state, event, now, &request)) {
		send_request(&request);
	}
}

static void serve_input(uint32_t now) {
	input_event_t event;
	while (input_port_next_event(&event, 0)) {
		on_input_event(&event, now);
	}
	action_request_t request;
	while (actions_poll(&pad.actions, &pad.obs_state, now, &request)) {
		send_request(&request);
	}
}

// ---- Panels and backlights ----

static void render_panels(void) {
	static render_view_t view;
	view_source_t source = {
	    .map = &pad.map,
	    .labels = &pad.labels,
	    .obs = &pad.obs_state,
	    .obs_status = pad.obs.status,
	    .wifi = pad.wifi.status.state,
	};
	view_build(&view, &source);
	render_display(&pad.render, &pad.ui, UI_MAIN, &view);
	render_display(&pad.render, &pad.ui, UI_STRIP, &view);
}

static void serve_backlights(void) {
	uint16_t wanted = (uint16_t)(pad.settings.brightness_percent * (POWER_PERMILLE_FULL / 100));
	uint16_t level = power_backlight(pad.grant, wanted);
	for (int display = 0; display < UI_DISPLAYS; display++) {
		if (level != pad.backlight[display] && backlight_set((ui_display_t)display, level) == ESP_OK) {
			pad.backlight[display] = level;
		}
	}
}

// ---- The app task ----

static void run_pass(uint32_t now) {
	serve_link(now);
	serve_input(now);
	pad.grant = power_step(&pad.power, now, usb_port_configured(), cc_sense_read_mv());
	serve_wifi(now);
	serve_obs(now);
	device_tick(&pad.device, now);
	follow_document(now);
	report_status();
	serve_backlights();
	render_panels();
}

static void app_task(void *arg) {
	(void)arg;
	ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
	follow_document(now_ms());
	for (;;) {
		esp_task_wdt_reset();
		run_pass(now_ms());
	}
}

// ---- Boot ----

static esp_err_t start_watchdog(void) {
	esp_task_wdt_config_t config = {
	    .timeout_ms = WATCHDOG_MS,
	    .idle_core_mask = (1u << portNUM_PROCESSORS) - 1u,
	    .trigger_panic = true,
	};
	esp_err_t err = esp_task_wdt_reconfigure(&config);
	return err == ESP_ERR_INVALID_STATE ? esp_task_wdt_init(&config) : err;
}

// INFO's fixed fields: the first 4 bytes of the commit (GIT_HASH, main/CMakeLists.txt), the
// unique id the USB serial number spells, and the IDF app version as fw_version.
static esp_err_t fill_identity(void) {
	static const uint32_t COMMIT = GIT_HASH;
	const esp_app_desc_t *app = esp_app_get_description();
	link_info_t *id = &pad.identity;
	id->keys = INPUT_KEYS;
	id->buttons = INPUT_BUTTONS;
	id->knobs = INPUT_KNOBS;
	id->main_display = (link_size_t){320, 480};
	id->strip_display = (link_size_t){142, 428};
	for (size_t i = 0; i < LINK_GIT_HASH_LEN; i++) {
		id->git_hash[i] = (uint8_t)(COMMIT >> (8 * (LINK_GIT_HASH_LEN - 1 - i)));
	}
	id->fw_version = (link_span_t){.bytes = (const uint8_t *)app->version,
	                               .len = strnlen(app->version, LINK_FW_VERSION_MAX)};
	return usb_port_unique_id(id->unique_id);
}

static esp_err_t start_store(void) {
	device_port_t port = {.identity = &pad.identity, .obs_state = &pad.obs_state};
	ESP_RETURN_ON_ERROR(cred_nvs_init(&pad.cred), TAG, "cred");
	ESP_RETURN_ON_ERROR(store_flash_bind(&port, &pad.slots, &pad.cred), TAG, "cfg slots");
	device_init(&pad.device, &port);
	return ESP_OK;
}

static void start_core(void) {
	link_rx_init(&pad.rx);
	stream_lwip_init(&pad.stream);
	obs_state_init(&pad.obs_state);
	obs_init(&pad.obs, &pad.stream.stream, next_random);
	obs_attach_state(&pad.obs, &pad.obs_state);
	pad.obs_dirty = true;
	wifi_init(&pad.wifi);
	ui_init(&pad.ui);
	render_init(&pad.render, (render_sink_t){lcd_port_push, NULL});
	power_init(&pad.power, now_ms());
}

// Backlights first and off; PCNT before any other PCNT user; the radio stays off (power.h).
static esp_err_t start_ports(void) {
	ESP_RETURN_ON_ERROR(backlight_init(), TAG, "backlights");
	ESP_RETURN_ON_ERROR(start_store(), TAG, "store");
	ESP_RETURN_ON_ERROR(usb_port_start(), TAG, "USB");
	ESP_RETURN_ON_ERROR(fill_identity(), TAG, "identity");
	ESP_RETURN_ON_ERROR(input_port_start(INPUT_PRIORITY), TAG, "input");
	ESP_RETURN_ON_ERROR(lcd_port_start(), TAG, "panels");
	ESP_RETURN_ON_ERROR(wifi_port_init(), TAG, "Wi-Fi");
	if (cc_sense_init() != ESP_OK) {
		ESP_LOGW(TAG, "CC sense is off: the backlight cap stays at %d permille", POWER_BACKLIGHT_CAP_PERMILLE);
	}
	return ESP_OK;
}

// The size and free-RAM report; `just firmware` prints the static one (idf.py size).
static void log_memory(void) {
	ESP_LOGI(TAG, "RAM free: internal %u B (largest block %u B), PSRAM %u B, lowest since boot %u B",
	         (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
	         (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
	         (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM), (unsigned)esp_get_minimum_free_heap_size());
	ESP_LOGI(TAG, "pad state %u B static; app task stack %u B", (unsigned)sizeof pad, (unsigned)APP_STACK);
}

void app_main(void) {
	const esp_app_desc_t *app = esp_app_get_description();
	esp_reset_reason_t reason = esp_reset_reason();
	ESP_LOGI(TAG, "%s %s, link protocol %d, reset reason %d%s", app->project_name, app->version, LINK_VERSION,
	         reason, reason == ESP_RST_TASK_WDT ? " (task watchdog)" : "");
	ESP_ERROR_CHECK(start_watchdog());
	start_core();
	ESP_ERROR_CHECK(start_ports());
	log_memory();
	BaseType_t made = xTaskCreatePinnedToCore(app_task, "app", APP_STACK, NULL, APP_PRIORITY, NULL, APP_CORE);
	if (made != pdPASS) {
		ESP_LOGE(TAG, "no room for the app task");
		abort();
	}
}
