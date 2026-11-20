// SPDX-License-Identifier: MIT
// padsim: the whole firmware core on the host (spec 9). The CDC link is a pseudo-terminal, the
// OBS link a POSIX TCP socket, the flash a NOR image file, the panels RAM models fed through the
// CASET/RASET/RAMWR window the port would send. There is no radio: padsim boots as if the stored
// SSID joined at once, and the `wifi` command feeds every later driver event.
//
//   padsim --nor IMAGE [--obs IP:PORT] [--cut-after N]
//
// stdout, one line each, flushed: `pty <path>` first, then the replies to the commands below.
// stdin, one command a line:
//   key N | button N        press and release key 0..8 or button 0..3
//   knob N push | knob N D  press knob 0..2, or turn it D detents (+ clockwise, 1..100 either way)
//   wifi EVENT              no_ssid, bad_key, no_ap or up, into fw-wifi
//   dump [DIR]              writes DIR/main.rgb565 and DIR/strip.rgb565 (visible pixels,
//                           big-endian RGB565), then `dumped DIR bad_windows=N line=TEXT`
//   wait-idle               `idle` once no input, OBS read, knob window, frame or tile waits
// A bad command gets `error <command>`. End of stdin ends padsim with 0; BOOTLOADER prints
// `bootloader` after its reply and ends with 0. `--cut-after N` kills padsim with SIGKILL when
// flash program call N begins (nor_file.h). No line on stdout or stderr carries a secret (R1).
#define _POSIX_C_SOURCE 200809L
#include "nor_file.h"
#include "panel_model.h"
#include "posix_stream.h"
#include "pty.h"
#include "view.h"

#include "actions.h"
#include "device.h"
#include "input.h"
#include "link.h"
#include "obs.h"
#include "obs_state.h"
#include "panels.h"
#include "render.h"
#include "store.h"
#include "ui.h"
#include "wifi.h"

#include <arpa/inet.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

// Longer than INPUT_DEBOUNCE_MS, so the press and the release each get through the debounce.
#define PRESS_MS 30
#define DETENTS_MAX 100
#define POLL_MS 1
#define COMMAND_MAX 256
#define REQUEST_MAX 320
// What the fake radio reports on `wifi up`.
#define SIM_RSSI_DBM (-50)

static const char FW_VERSION[] = "padsim";

static const link_info_t IDENTITY = {
    .keys = INPUT_KEYS,
    .buttons = INPUT_BUTTONS,
    .knobs = INPUT_KNOBS,
    .main_display = {320, 480},
    .strip_display = {142, 428},
    .fw_version = {.bytes = (const uint8_t *)FW_VERSION, .len = sizeof FW_VERSION - 1},
};

typedef struct {
	const char *nor_path;
	bool has_obs;
	uint8_t obs_ip[4];
	uint16_t obs_port;
	uint32_t cut_after;
} options_t;

// The controls a command holds down, and the knob counts the next sample carries.
typedef struct {
	uint16_t held; // bit row * INPUT_COLS + col
	uint32_t release_ms;
	int16_t knob_counts[INPUT_KNOBS];
} controls_t;

// What decides which document the panels and the map follow.
typedef struct {
	store_state_t state;
	uint32_t seq;
	bool trying;
} document_key_t;

typedef struct {
	nor_file_t nor;
	nor_file_part_t slot_a, slot_b;
	nor_file_cred_t cred;
	pty_t pty;
	link_rx_t rx;
	posix_stream_t stream;
	device_t device;
	wifi_t wifi;
	obs_t obs;
	obs_state_t obs_state;
	input_t input;
	actions_t actions;
	ui_model_t ui;
	render_t render;
	panel_model_t panels[UI_DISPLAYS];
	action_map_t map;
	view_labels_t labels;
	document_key_t shown;
	bool shown_once; // `shown` holds the key of a document applied since boot
	uint8_t stored[CONFIG_MAX_BYTES];
	char password[LINK_CREDENTIAL_MAX + 1];
	controls_t controls;
	bool wait_idle;
	uint32_t next_action_id;
	uint32_t random_state;
	char line[COMMAND_MAX];
	size_t line_len;
} padsim_t;

static padsim_t sim;

static uint32_t now_ms(void) {
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	return (uint32_t)((uint64_t)now.tv_sec * 1000u + (uint64_t)now.tv_nsec / 1000000u);
}

// xorshift32: the WebSocket masks need no strength, only change.
static uint32_t next_random(void) {
	uint32_t x = sim.random_state;
	x ^= x << 13;
	x ^= x >> 17;
	x ^= x << 5;
	sim.random_state = x;
	return x;
}

static void say(const char *format, ...) __attribute__((format(printf, 1, 2)));
static void say(const char *format, ...) {
	va_list args;
	va_start(args, format);
	vprintf(format, args);
	va_end(args);
	putchar('\n');
	fflush(stdout);
}

// ---- Options ----

static bool parse_number(const char *text, long min, long max, long *out) {
	char *end;
	errno = 0;
	long value = strtol(text, &end, 10);
	if (errno != 0 || end == text || *end != '\0' || value < min || value > max) {
		return false;
	}
	*out = value;
	return true;
}

static bool parse_address(const char *text, options_t *options) {
	char host[INET_ADDRSTRLEN];
	const char *colon = strrchr(text, ':');
	long port;
	if (colon == NULL || (size_t)(colon - text) >= sizeof host) {
		return false;
	}
	memcpy(host, text, (size_t)(colon - text));
	host[colon - text] = '\0';
	if (inet_pton(AF_INET, host, options->obs_ip) != 1 || !parse_number(colon + 1, 1, 65535, &port)) {
		return false;
	}
	options->obs_port = (uint16_t)port;
	options->has_obs = true;
	return true;
}

static bool parse_options(int argc, char **argv, options_t *options) {
	*options = (options_t){.cut_after = NOR_FILE_NO_CUT};
	for (int i = 1; i + 1 < argc; i += 2) {
		long cut;
		if (strcmp(argv[i], "--nor") == 0) {
			options->nor_path = argv[i + 1];
		} else if (strcmp(argv[i], "--obs") == 0 && parse_address(argv[i + 1], options)) {
			continue;
		} else if (strcmp(argv[i], "--cut-after") == 0 && parse_number(argv[i + 1], 1, INT_MAX, &cut)) {
			options->cut_after = (uint32_t)cut;
		} else {
			return false;
		}
	}
	return argc % 2 == 1 && options->nor_path != NULL;
}

// ---- The CDC link ----

static void send_frame(const link_frame_t *frame) {
	uint8_t bytes[LINK_MAX_FRAME];
	size_t len = link_encode(frame, bytes, sizeof bytes);
	pty_send(&sim.pty, bytes, len);
}

static link_span_t current_document(void) {
	link_span_t draft = device_draft(&sim.device);
	const store_t *store = &sim.device.store;
	if (draft.len > 0) {
		return draft;
	}
	if (store->state == STORE_LOADED && store_read(store, 0, sim.stored, store->doc.len)) {
		return (link_span_t){.bytes = sim.stored, .len = store->doc.len};
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

// The factory defaults are an empty map and black panels: no document defines more yet.
static void apply_document(link_span_t doc) {
	ui_layout_t layouts[UI_DISPLAYS];
	memset(&sim.map, 0, sizeof sim.map);
	memset(&sim.labels, 0, sizeof sim.labels);
	memset(layouts, 0, sizeof layouts);
	if (doc.len > 0) {
		if (!actions_parse(&sim.map, doc.bytes, doc.len)) {
			memset(&sim.map, 0, sizeof sim.map);
		}
		if (!ui_parse(layouts, doc.bytes, doc.len)) {
			memset(layouts, 0, sizeof layouts);
		}
		view_labels_parse(&sim.labels, doc.bytes, doc.len);
	}
	actions_init(&sim.actions, &sim.map);
	ui_apply(&sim.ui, layouts);
	for (size_t knob = 0; knob < INPUT_KNOBS; knob++) {
		obs_state_watch(&sim.obs_state, knob, sim.map.knobs[knob].input);
	}
	obs_state_show_meters(&sim.obs_state, layout_shows_meter(&layouts[UI_MAIN]) ||
	                                          layout_shows_meter(&layouts[UI_STRIP]));
}

static bool same_key(const document_key_t *a, const document_key_t *b) {
	return a->state == b->state && a->seq == b->seq && a->trying == b->trying;
}

static void follow_document(void) {
	const store_t *store = &sim.device.store;
	document_key_t key = {
	    .state = store->state,
	    .seq = store->state == STORE_NONE ? 0 : store->doc.seq,
	    .trying = device_draft(&sim.device).len > 0,
	};
	if (!sim.shown_once || !same_key(&key, &sim.shown)) {
		sim.shown = key;
		sim.shown_once = true;
		apply_document(current_document());
	}
}

static void on_frame(const link_frame_t *frame, uint32_t now) {
	link_frame_t reply;
	if (device_handle(&sim.device, now, frame, &reply)) {
		send_frame(&reply);
	} else {
		fprintf(stderr, "padsim: no reply could be encoded for type 0x%02x\n", frame->type);
	}
	follow_document();
	if (device_bootloader_asked(&sim.device)) {
		say("bootloader");
		exit(0);
	}
}

static void serve_link(uint32_t now) {
	uint8_t bytes[LINK_MAX_FRAME];
	size_t got = pty_recv(&sim.pty, bytes, sizeof bytes);
	size_t pushed = 0;
	link_frame_t frame;
	do {
		pushed += link_rx_push(&sim.rx, bytes + pushed, got - pushed);
		link_status_t status;
		while ((status = link_pull(&sim.rx, &frame)) != LINK_EMPTY) {
			if (status == LINK_FRAME) {
				on_frame(&frame, now);
			} else {
				send_frame(&frame);
			}
		}
	} while (pushed < got);
}

// ---- Controls ----

static void press(uint32_t now, unsigned row, unsigned col) {
	sim.controls.held |= (uint16_t)(1u << (row * INPUT_COLS + col));
	sim.controls.release_ms = now + PRESS_MS;
}

static void send_request(const action_request_t *request) {
	char text[REQUEST_MAX];
	if (sim.obs.status != OBS_UP) {
		return;
	}
	uint32_t id = sim.next_action_id++;
	int len = request->data[0] == '\0'
	              ? snprintf(text, sizeof text, "{\"op\":6,\"d\":{\"requestType\":\"%s\",\"requestId\":\"a%" PRIu32 "\"}}",
	                         request->type, id)
	              : snprintf(text, sizeof text,
	                         "{\"op\":6,\"d\":{\"requestType\":\"%s\",\"requestId\":\"a%" PRIu32 "\",\"requestData\":%s}}",
	                         request->type, id, request->data);
	if (len > 0 && (size_t)len < sizeof text) {
		ws_send_text(&sim.obs.ws, text, (size_t)len);
	}
}

static void on_input_event(const input_event_t *event, uint32_t now) {
	link_frame_t frame;
	action_request_t request;
	if (!device_input(&sim.device, event)) {
		fprintf(stderr, "padsim: the clear combination could not erase the flash\n");
	}
	follow_document();
	if (device_input_frame(event, &frame)) {
		send_frame(&frame);
	}
	if (actions_on_input(&sim.actions, &sim.obs_state, event, now, &request)) {
		send_request(&request);
	}
}

static void sample_controls(uint32_t now) {
	controls_t *controls = &sim.controls;
	if (controls->held != 0 && (int32_t)(now - controls->release_ms) >= 0) {
		controls->held = 0;
	}
	input_sample_t sample = {.now_ms = now};
	for (unsigned row = 0; row < INPUT_ROWS; row++) {
		sample.cols_low[row] = (uint8_t)((controls->held >> (row * INPUT_COLS)) & 0xF);
	}
	memcpy(sample.knob_counts, controls->knob_counts, sizeof sample.knob_counts);
	memset(controls->knob_counts, 0, sizeof controls->knob_counts);
	input_event_t events[INPUT_MAX_EVENTS];
	int count = input_step(&sim.input, &sample, events);
	for (int i = 0; i < count; i++) {
		on_input_event(&events[i], now);
	}
}

static void poll_actions(uint32_t now) {
	action_request_t request;
	while (actions_poll(&sim.actions, &sim.obs_state, now, &request)) {
		send_request(&request);
	}
}

// ---- Panels ----

static void push_to_panel(void *context, ui_display_t display, ui_rect_t window, const uint16_t *pixels) {
	static uint8_t bytes[RENDER_BAND_WIDTH * UI_TILE * 2];
	panel_model_t *model = &((panel_model_t *)context)[display];
	panel_window_t span;
	if (!panel_window(model->panel, (panel_rect_t){window.x, window.y, window.w, window.h}, &span)) {
		model->bad_windows++;
		return;
	}
	size_t count = (size_t)window.w * window.h;
	for (size_t i = 0; i < count; i++) {
		bytes[2 * i] = (uint8_t)(pixels[i] >> 8);
		bytes[2 * i + 1] = (uint8_t)pixels[i];
	}
	panel_model_send(model, PANEL_CASET, span.caset, sizeof span.caset);
	panel_model_send(model, PANEL_RASET, span.raset, sizeof span.raset);
	panel_model_send(model, PANEL_RAMWR, bytes, count * 2);
}

static void render_panels(void) {
	render_view_t view;
	view_source_t source = {
	    .map = &sim.map,
	    .labels = &sim.labels,
	    .obs = &sim.obs_state,
	    .obs_status = sim.obs.status,
	    .wifi = sim.wifi.status.state,
	};
	view_build(&view, &source);
	render_display(&sim.render, &sim.ui, UI_MAIN, &view);
	render_display(&sim.render, &sim.ui, UI_STRIP, &view);
}

// The failure the strip line names: Wi-Fi first, since OBS cannot be reached without it.
static const char *strip_line(void) {
	const char *wifi = wifi_strip_line(sim.wifi.status.state);
	const char *obs = obs_strip_line(sim.obs.status);
	return wifi != NULL ? wifi : obs != NULL ? obs : "";
}

static void dump(const char *dir) {
	static const char *const NAMES[UI_DISPLAYS] = {"main.rgb565", "strip.rgb565"};
	render_panels();
	for (int display = 0; display < UI_DISPLAYS; display++) {
		char path[PATH_MAX];
		int len = snprintf(path, sizeof path, "%s/%s", dir, NAMES[display]);
		if (len < 0 || (size_t)len >= sizeof path || !panel_model_dump(&sim.panels[display], path)) {
			say("error dump %s", dir);
			return;
		}
	}
	say("dumped %s bad_windows=%" PRIu32 " line=%s", dir,
	    sim.panels[UI_MAIN].bad_windows + sim.panels[UI_STRIP].bad_windows, strip_line());
}

// ---- Commands ----

static bool feed_wifi(const char *name, uint32_t now) {
	static const struct {
		const char *name;
		wifi_event_kind_t kind;
	} EVENTS[] = {
	    {"no_ssid", WIFI_EVT_NO_SSID},
	    {"bad_key", WIFI_EVT_BAD_KEY},
	    {"no_ap", WIFI_EVT_NO_AP},
	    {"up", WIFI_EVT_UP},
	};
	for (size_t i = 0; i < sizeof EVENTS / sizeof EVENTS[0]; i++) {
		if (strcmp(name, EVENTS[i].name) == 0) {
			wifi_event_t event = {.kind = EVENTS[i].kind, .rssi_dbm = SIM_RSSI_DBM, .ip = {127, 0, 0, 1}};
			wifi_on_event(&sim.wifi, &event, now); // the fake radio takes no join or leave
			return true;
		}
	}
	return false;
}

static bool knob_command(long knob, const char *what, uint32_t now) {
	long detents;
	if (strcmp(what, "push") == 0) {
		press(now, (unsigned)knob, INPUT_COLS - 1);
		return true;
	}
	if (!parse_number(what, -DETENTS_MAX, DETENTS_MAX, &detents) || detents == 0) {
		return false;
	}
	sim.controls.knob_counts[knob] += (int16_t)(detents * INPUT_COUNTS_PER_DETENT);
	return true;
}

static bool run_command(char *line, uint32_t now) {
	char *rest;
	const char *verb = strtok_r(line, " \t\r", &rest);
	const char *arg = strtok_r(NULL, " \t\r", &rest);
	const char *arg2 = strtok_r(NULL, " \t\r", &rest);
	long n;
	if (verb == NULL) {
		return true;
	}
	if (strcmp(verb, "key") == 0 && arg != NULL && parse_number(arg, 0, INPUT_KEYS - 1, &n)) {
		press(now, (unsigned)n / 3, (unsigned)n % 3);
	} else if (strcmp(verb, "button") == 0 && arg != NULL && parse_number(arg, 0, INPUT_BUTTONS - 1, &n)) {
		press(now, INPUT_ROWS - 1, (unsigned)n);
	} else if (strcmp(verb, "knob") == 0 && arg != NULL && arg2 != NULL &&
	           parse_number(arg, 0, INPUT_KNOBS - 1, &n)) {
		return knob_command(n, arg2, now);
	} else if (strcmp(verb, "wifi") == 0 && arg != NULL) {
		return feed_wifi(arg, now);
	} else if (strcmp(verb, "dump") == 0) {
		dump(arg != NULL ? arg : ".");
	} else if (strcmp(verb, "wait-idle") == 0) {
		sim.wait_idle = true;
	} else {
		return false;
	}
	return true;
}

static void on_line(char *line, uint32_t now) {
	char copy[COMMAND_MAX];
	snprintf(copy, sizeof copy, "%s", line);
	if (!run_command(line, now)) {
		say("error %s", copy);
	}
}

// False at the end of stdin.
static bool read_commands(uint32_t now) {
	ssize_t got = read(STDIN_FILENO, sim.line + sim.line_len, sizeof sim.line - 1 - sim.line_len);
	if (got == 0) {
		return false;
	}
	if (got < 0) {
		return errno == EINTR || errno == EAGAIN;
	}
	sim.line_len += (size_t)got;
	char *end;
	while ((end = memchr(sim.line, '\n', sim.line_len)) != NULL) {
		*end = '\0';
		on_line(sim.line, now);
		size_t used = (size_t)(end - sim.line) + 1;
		memmove(sim.line, end + 1, sim.line_len - used);
		sim.line_len -= used;
	}
	if (sim.line_len == sizeof sim.line - 1) {
		say("error line longer than %d bytes", COMMAND_MAX - 1);
		sim.line_len = 0;
	}
	return true;
}

// ---- The main loop ----

static bool is_idle(void) {
	bool windows_open = false;
	for (size_t knob = 0; knob < INPUT_KNOBS; knob++) {
		windows_open |= sim.actions.volume[knob].window_open || sim.controls.knob_counts[knob] != 0;
	}
	bool controls_still = sim.controls.held == 0 && sim.input.closed == 0 && sim.input.unsettled == 0;
	bool obs_settled = sim.obs.status != OBS_CONNECTING &&
	                   (sim.obs.status != OBS_UP || obs_state_is_current(&sim.obs_state));
	return controls_still && !windows_open && obs_settled && sim.rx.len == 0;
}

static void report_status(void) {
	link_frame_t frame;
	if (device_status(&sim.device, obs_link_state(sim.obs.status), &sim.wifi.status, &frame)) {
		send_frame(&frame);
	}
}

static void run_pass(uint32_t now) {
	serve_link(now);
	sample_controls(now);
	wifi_tick(&sim.wifi, now); // the fake radio takes no join
	obs_poll(&sim.obs, now);
	poll_actions(now);
	device_tick(&sim.device, now);
	follow_document();
	report_status();
	render_panels();
	if (sim.wait_idle && is_idle()) {
		sim.wait_idle = false;
		say("idle");
	}
}

static void boot_wifi(uint32_t now) {
	wifi_event_t joined = {.kind = WIFI_EVT_UP, .rssi_dbm = SIM_RSSI_DBM, .ip = {127, 0, 0, 1}};
	wifi_init(&sim.wifi);
	wifi_on_event(&sim.wifi, &(wifi_event_t){.kind = WIFI_EVT_SSID_SET}, now);
	wifi_on_event(&sim.wifi, &joined, now);
}

static void start_obs(const options_t *options, uint32_t now) {
	size_t len = sim.cred.cred.get(&sim.cred.cred, LINK_CREDENTIAL_OBS_PASSWORD, (uint8_t *)sim.password,
	                               sizeof sim.password - 1);
	obs_start(&sim.obs, options->obs_ip, options->obs_port, len > 0 ? sim.password : NULL, len, now);
}

static bool boot(const options_t *options) {
	uint32_t now = now_ms();
	sim.random_state = (uint32_t)getpid() ^ now ^ 0x9E3779B9u;
	if (!nor_file_open(&sim.nor, options->nor_path, options->cut_after) || !pty_open(&sim.pty) ||
	    !panel_model_init(&sim.panels[UI_MAIN], &panel_main) ||
	    !panel_model_init(&sim.panels[UI_STRIP], &panel_strip)) {
		return false;
	}
	sim.slot_a = (nor_file_part_t){.file = &sim.nor, .base = 0, .size = STORE_SLOT_BYTES};
	sim.slot_b = (nor_file_part_t){.file = &sim.nor, .base = STORE_SLOT_BYTES, .size = STORE_SLOT_BYTES};
	nor_file_cred_init(&sim.cred, &sim.nor);
	link_rx_init(&sim.rx);
	posix_stream_init(&sim.stream);
	obs_state_init(&sim.obs_state);
	obs_init(&sim.obs, &sim.stream.stream, next_random);
	obs_attach_state(&sim.obs, &sim.obs_state);
	device_port_t port = {
	    .identity = &IDENTITY,
	    .cred = &sim.cred.cred,
	    .flash = &NOR_FILE_FLASH,
	    .slot_a = &sim.slot_a,
	    .slot_b = &sim.slot_b,
	    .obs_state = &sim.obs_state,
	};
	device_init(&sim.device, &port);
	input_init(&sim.input);
	ui_init(&sim.ui);
	render_init(&sim.render, (render_sink_t){push_to_panel, sim.panels});
	follow_document();
	boot_wifi(now);
	if (options->has_obs) {
		start_obs(options, now);
	}
	say("pty %s", sim.pty.path);
	return true;
}

int main(int argc, char **argv) {
	options_t options;
	signal(SIGPIPE, SIG_IGN);
	if (!parse_options(argc, argv, &options)) {
		fprintf(stderr, "usage: padsim --nor IMAGE [--obs IP:PORT] [--cut-after N]\n");
		return 2;
	}
	if (!boot(&options)) {
		return 1;
	}
	struct pollfd watch[2] = {{.fd = sim.pty.master, .events = POLLIN}, {.fd = STDIN_FILENO, .events = POLLIN}};
	for (;;) {
		poll(watch, 2, POLL_MS);
		uint32_t now = now_ms();
		if ((watch[1].revents & (POLLIN | POLLHUP)) != 0 && !read_commands(now)) {
			return 0;
		}
		run_pass(now);
	}
}
