// SPDX-License-Identifier: MIT
// The obs handshake over a POSIX TCP stream against tools/fake_obs.py, one server process per
// case. The clock is the real one plus a skew that a test moves to end a retry wait at once.
#define _POSIX_C_SOURCE 200809L
#include "obs.h"
#include "posix_stream.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

static const uint8_t LOOPBACK[4] = {127, 0, 0, 1};
// A test string, never a real password.
static const char PASSWORD[] = "dummy-obs-password";
#define PASSWORD_LEN (sizeof PASSWORD - 1)
static const char WRONG_PASSWORD[] = "dummy-wrong-password";
// Far longer than any step of a handshake on loopback.
#define SETTLE_MS 5000u
// Long enough for a retry that should not come to show up.
#define QUIET_MS 300u
#define NO_RETRY_SKEW_MS 60000u
#define LINE_MAX 64

static uint32_t clock_skew_ms;

static uint32_t now_ms(void) {
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	return (uint32_t)now.tv_sec * 1000u + (uint32_t)(now.tv_nsec / 1000000) + clock_skew_ms;
}

static void sleep_1_ms(void) {
	nanosleep(&(struct timespec){.tv_nsec = 1000000}, NULL);
}

static uint32_t ms_since(const struct timespec *start) {
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	return (uint32_t)((now.tv_sec - start->tv_sec) * 1000 + (now.tv_nsec - start->tv_nsec) / 1000000);
}

static bool line_is(obs_status_t status, const char *expected) {
	const char *line = obs_strip_line(status);
	return line != NULL && strcmp(line, expected) == 0;
}

static uint32_t next_random(void) {
	return (uint32_t)rand();
}

typedef struct {
	pid_t pid;
	int out_fd;
	uint16_t port;
} fake_obs_t;

// Reads the `listening <port>` line. 0 when it does not come within SETTLE_MS.
static uint16_t read_port(int fd) {
	char line[LINE_MAX] = {0};
	size_t len = 0;
	while (len < sizeof line - 1 && memchr(line, '\n', len) == NULL) {
		struct pollfd ready = {.fd = fd, .events = POLLIN};
		if (poll(&ready, 1, SETTLE_MS) != 1 || read(fd, line + len, 1) != 1) {
			return 0;
		}
		len++;
	}
	unsigned port = 0;
	return sscanf(line, "listening %u", &port) == 1 ? (uint16_t)port : 0;
}

// Runs tools/fake_obs.py on loopback `port` (0: a free one) with `args` (NULL-terminated, at
// most 4) after the common ones. Aborts the run when the server does not come up.
static fake_obs_t fake_obs_start(uint16_t port, const char *const args[]) {
	int out[2];
	if (pipe(out) != 0) {
		perror("pipe");
		exit(2);
	}
	char port_text[8];
	snprintf(port_text, sizeof port_text, "%u", port);
	const char *argv[12] = {"python3", FAKE_OBS, "--port", port_text, "--log", "/dev/null"};
	for (size_t i = 0; args[i] != NULL; i++) {
		argv[6 + i] = args[i];
	}
	pid_t pid = fork();
	if (pid == 0) {
		dup2(out[1], STDOUT_FILENO);
		close(out[0]);
		close(out[1]);
		execvp("python3", (char *const *)argv);
		_exit(127);
	}
	close(out[1]);
	fake_obs_t fake = {.pid = pid, .out_fd = out[0], .port = read_port(out[0])};
	if (pid < 0 || fake.port == 0) {
		fprintf(stderr, "tools/fake_obs.py did not start\n");
		exit(2);
	}
	return fake;
}

static void fake_obs_stop(fake_obs_t *fake) {
	kill(fake->pid, SIGTERM);
	waitpid(fake->pid, NULL, 0);
	close(fake->out_fd);
}

// A loopback port with no listener: a connect to it is refused.
static uint16_t free_port(void) {
	int fd = socket(AF_INET, SOCK_STREAM, 0);
	struct sockaddr_in address = {.sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
	socklen_t len = sizeof address;
	bind(fd, (struct sockaddr *)&address, len);
	getsockname(fd, (struct sockaddr *)&address, &len);
	close(fd);
	return ntohs(address.sin_port);
}

// Polls until the client reaches `status` or SETTLE_MS of real time pass.
static bool run_until(obs_t *obs, obs_status_t status) {
	struct timespec start;
	clock_gettime(CLOCK_MONOTONIC, &start);
	do {
		obs_poll(obs, now_ms());
		if (obs->status == status) {
			return true;
		}
		sleep_1_ms();
	} while (ms_since(&start) < SETTLE_MS);
	fprintf(stderr, "status %d, waited for %d\n", obs->status, status);
	return false;
}

static void run_for(obs_t *obs, uint32_t ms) {
	for (uint32_t i = 0; i < ms; i++) {
		obs_poll(obs, now_ms());
		sleep_1_ms();
	}
}

typedef struct {
	posix_stream_t posix;
	obs_t obs;
} client_t;

static void client_init(client_t *client) {
	posix_stream_init(&client->posix);
	obs_init(&client->obs, &client->posix.stream, next_random);
}

// One whole case: a fresh server with `args`, a client with `password` (NULL: none stored),
// and the state it settles in.
static obs_status_t handshake(const char *const args[], const char *password, client_t *client) {
	fake_obs_t fake = fake_obs_start(0, args);
	client_init(client);
	size_t password_len = password == NULL ? 0 : strlen(password);
	CHECK(obs_start(&client->obs, LOOPBACK, fake.port, password, password_len, now_ms()));
	struct timespec start;
	clock_gettime(CLOCK_MONOTONIC, &start);
	while (client->obs.status == OBS_CONNECTING && ms_since(&start) < SETTLE_MS) {
		obs_poll(&client->obs, now_ms());
		sleep_1_ms();
	}
	run_for(&client->obs, QUIET_MS); // a kick after Identified lands here
	fake_obs_stop(&fake);
	return client->obs.status;
}

// A stopped client does not dial again, however long it waits.
static void check_no_retry(client_t *client) {
	int opens = client->posix.open_calls;
	clock_skew_ms += NO_RETRY_SKEW_MS;
	run_for(&client->obs, QUIET_MS);
	CHECK(client->posix.open_calls == opens);
}

static void test_auth_off_is_up(void) {
	client_t client;
	CHECK(handshake((const char *const[]){NULL}, NULL, &client) == OBS_UP);
	CHECK(obs_link_state(client.obs.status) == LINK_OBS_UP);
	CHECK(obs_strip_line(client.obs.status) == NULL);
	CHECK(client.posix.open_calls == 1);
}

static void test_auth_off_with_a_stored_password_is_up(void) {
	client_t client;
	CHECK(handshake((const char *const[]){NULL}, PASSWORD, &client) == OBS_UP);
}

static void test_auth_on_with_the_password_is_up(void) {
	client_t client;
	const char *const args[] = {"--password", PASSWORD, NULL};
	CHECK(handshake(args, PASSWORD, &client) == OBS_UP);
	CHECK(client.posix.open_calls == 1);
}

static void test_a_wrong_password_stops_on_4009(void) {
	client_t client;
	const char *const args[] = {"--password", PASSWORD, NULL};
	CHECK(handshake(args, WRONG_PASSWORD, &client) == OBS_WRONG_PASSWORD);
	CHECK(obs_link_state(client.obs.status) == LINK_OBS_AUTH_FAILED);
	CHECK(line_is(client.obs.status, "Wrong OBS password"));
	check_no_retry(&client);
}

static void test_auth_on_with_no_stored_password_stops(void) {
	client_t client;
	const char *const args[] = {"--password", PASSWORD, NULL};
	CHECK(handshake(args, NULL, &client) == OBS_NO_PASSWORD);
	CHECK(obs_link_state(client.obs.status) == LINK_OBS_AUTH_FAILED);
	CHECK(line_is(client.obs.status, "OBS password not set"));
	check_no_retry(&client);
}

static void test_obs_websocket_below_5_4_0_is_too_old(void) {
	client_t client;
	const char *const args[] = {"--obs-websocket-version", "5.3.4", NULL};
	CHECK(handshake(args, NULL, &client) == OBS_TOO_OLD);
	CHECK(obs_link_state(client.obs.status) == LINK_OBS_REFUSED);
	CHECK(line_is(client.obs.status, "OBS too old, need 30.1"));
	check_no_retry(&client);
}

static void test_obs_websocket_5_4_0_and_5_10_0_are_up(void) {
	client_t client;
	const char *const floor[] = {"--obs-websocket-version", "5.4.0", NULL};
	CHECK(handshake(floor, NULL, &client) == OBS_UP);
	const char *const two_digit_minor[] = {"--obs-websocket-version", "5.10.0", NULL};
	CHECK(handshake(two_digit_minor, NULL, &client) == OBS_UP);
}

static void test_close_4010_stops(void) {
	client_t client;
	const char *const args[] = {"--close-code", "4010", NULL};
	CHECK(handshake(args, NULL, &client) == OBS_RPC_REFUSED);
	CHECK(obs_link_state(client.obs.status) == LINK_OBS_REFUSED);
	check_no_retry(&client);
}

static void test_close_4011_after_identified_stops(void) {
	client_t client;
	const char *const args[] = {"--close-code", "4011", NULL};
	CHECK(handshake(args, NULL, &client) == OBS_KICKED);
	CHECK(obs_link_state(client.obs.status) == LINK_OBS_REFUSED);
	check_no_retry(&client);
}

static void test_close_4009_mode_stops_with_auth_off(void) {
	client_t client;
	const char *const args[] = {"--close-code", "4009", NULL};
	CHECK(handshake(args, NULL, &client) == OBS_WRONG_PASSWORD);
	check_no_retry(&client);
}

// No server, then one comes up on the port: the next retry finds it. Then the server goes away
// while identified, and comes back: the client dials again on its own.
static void test_unreachable_then_reconnect_after_obs_restarts(void) {
	uint16_t port = free_port();
	client_t client;
	client_init(&client);
	CHECK(obs_start(&client.obs, LOOPBACK, port, PASSWORD, PASSWORD_LEN, now_ms()));
	CHECK(client.obs.status == OBS_UNREACHABLE);
	CHECK(obs_link_state(client.obs.status) == LINK_OBS_REFUSED);
	CHECK(line_is(client.obs.status, "OBS unreachable"));

	const char *const args[] = {"--password", PASSWORD, NULL};
	fake_obs_t fake = fake_obs_start(port, args);
	CHECK(run_until(&client.obs, OBS_UP));

	fake_obs_stop(&fake);
	CHECK(run_until(&client.obs, OBS_CONNECTING));
	fake = fake_obs_start(port, args);
	CHECK(run_until(&client.obs, OBS_UP)); // the real waits: 0.5, 1, 2 s at most
	fake_obs_stop(&fake);
}

// With no server every try fails at once, so a model clock walks the whole schedule.
static void test_retry_waits_are_0_5_1_2_s_then_2_s(void) {
	static const uint32_t WAITS_MS[] = {500, 1000, 2000, 2000, 2000};
	client_t client;
	client_init(&client);
	uint32_t clock = UINT32_MAX - 3000; // the waits cross the wrap
	CHECK(obs_start(&client.obs, LOOPBACK, free_port(), NULL, 0, clock));
	CHECK(client.posix.open_calls == 1);
	for (size_t i = 0; i < sizeof WAITS_MS / sizeof WAITS_MS[0]; i++) {
		int opens = client.posix.open_calls;
		clock += WAITS_MS[i] - 1;
		obs_poll(&client.obs, clock);
		CHECK(client.posix.open_calls == opens);
		clock += 1;
		obs_poll(&client.obs, clock);
		CHECK(client.posix.open_calls == opens + 1);
		CHECK(client.obs.status == OBS_UNREACHABLE);
	}
}

static void test_start_is_refused_while_running(void) {
	client_t client;
	client_init(&client);
	CHECK(obs_start(&client.obs, LOOPBACK, free_port(), NULL, 0, 0));
	CHECK(!obs_start(&client.obs, LOOPBACK, free_port(), NULL, 0, 0));
	CHECK(client.posix.open_calls == 1);
}

// A wrong address retries forever. Stop, then start on the right one: it is used at once.
static void test_stop_lets_a_retrying_client_take_a_new_address(void) {
	client_t client;
	client_init(&client);
	CHECK(obs_start(&client.obs, LOOPBACK, free_port(), NULL, 0, now_ms()));
	CHECK(client.obs.status == OBS_UNREACHABLE);
	obs_stop(&client.obs);
	CHECK(client.obs.status == OBS_IDLE);
	check_no_retry(&client);

	fake_obs_t fake = fake_obs_start(0, (const char *const[]){NULL});
	CHECK(obs_start(&client.obs, LOOPBACK, fake.port, NULL, 0, now_ms()));
	CHECK(run_until(&client.obs, OBS_UP));
	fake_obs_stop(&fake);
}

// A session that is up drops at once, and the next start dials and identifies again.
static void test_stop_while_up_lets_a_new_start_identify(void) {
	const char *const args[] = {"--password", PASSWORD, NULL};
	fake_obs_t first = fake_obs_start(0, args);
	client_t client;
	client_init(&client);
	CHECK(obs_start(&client.obs, LOOPBACK, first.port, PASSWORD, PASSWORD_LEN, now_ms()));
	CHECK(run_until(&client.obs, OBS_UP));
	obs_stop(&client.obs);
	CHECK(client.obs.status == OBS_IDLE);
	CHECK(client.posix.fd == -1);

	fake_obs_t second = fake_obs_start(0, args);
	CHECK(obs_start(&client.obs, LOOPBACK, second.port, PASSWORD, PASSWORD_LEN, now_ms()));
	CHECK(run_until(&client.obs, OBS_UP));
	CHECK(client.posix.open_calls == 2);
	fake_obs_stop(&second);
	fake_obs_stop(&first);
}

static void test_stop_on_an_idle_client_changes_nothing(void) {
	client_t client;
	client_init(&client);
	obs_stop(&client.obs);
	CHECK(client.obs.status == OBS_IDLE);
	CHECK(client.posix.open_calls == 0);
}

static void test_each_failure_has_its_own_printable_line_with_no_secret(void) {
	static const obs_status_t FAILURES[] = {OBS_UNREACHABLE, OBS_NO_PASSWORD, OBS_WRONG_PASSWORD,
	                                        OBS_TOO_OLD,     OBS_RPC_REFUSED, OBS_KICKED};
	size_t count = sizeof FAILURES / sizeof FAILURES[0];
	for (size_t i = 0; i < count; i++) {
		const char *line = obs_strip_line(FAILURES[i]);
		CHECK(line != NULL && line[0] != '\0');
		if (line == NULL) {
			continue;
		}
		for (const char *c = line; *c; c++) {
			CHECK(*c >= 0x20 && *c <= 0x7E);
		}
		CHECK(strstr(line, PASSWORD) == NULL);
		for (size_t j = 0; j < i; j++) {
			const char *other = obs_strip_line(FAILURES[j]);
			CHECK(other == NULL || strcmp(line, other) != 0);
		}
	}
	CHECK(obs_strip_line(OBS_IDLE) == NULL);
	CHECK(obs_strip_line(OBS_CONNECTING) == NULL);
	CHECK(obs_strip_line(OBS_UP) == NULL);
	CHECK(obs_strip_line((obs_status_t)99) == NULL);
	CHECK(obs_link_state(OBS_IDLE) == LINK_OBS_IDLE);
	CHECK(obs_link_state(OBS_CONNECTING) == LINK_OBS_CONNECTING);
}

int main(void) {
	signal(SIGPIPE, SIG_IGN);
	test_auth_off_is_up();
	test_auth_off_with_a_stored_password_is_up();
	test_auth_on_with_the_password_is_up();
	test_a_wrong_password_stops_on_4009();
	test_auth_on_with_no_stored_password_stops();
	test_obs_websocket_below_5_4_0_is_too_old();
	test_obs_websocket_5_4_0_and_5_10_0_are_up();
	test_close_4010_stops();
	test_close_4011_after_identified_stops();
	test_close_4009_mode_stops_with_auth_off();
	test_unreachable_then_reconnect_after_obs_restarts();
	test_retry_waits_are_0_5_1_2_s_then_2_s();
	test_start_is_refused_while_running();
	test_stop_lets_a_retrying_client_take_a_new_address();
	test_stop_while_up_lets_a_new_start_identify();
	test_stop_on_an_idle_client_changes_nothing();
	test_each_failure_has_its_own_printable_line_with_no_secret();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	puts("obs handshake: all tests pass");
	return 0;
}
