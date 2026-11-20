// SPDX-License-Identifier: MIT
// The config store over the NOR model, and the cred seam over a fake of the port's NVS (spec 11,
// fw-store row).
#include "cred.h"
#include "nor_model.h"
#include "store.h"

#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

#define CRED_BYTES (2 * STORE_SECTOR_BYTES)
// The shortest run of secret bytes a dump check looks for.
#define SECRET_RUN 4

static nor_chip_t chip;
static nor_part_t slot_a = {.chip = &chip, .base = 0, .size = STORE_SLOT_BYTES};
static nor_part_t slot_b = {.chip = &chip, .base = STORE_SLOT_BYTES, .size = STORE_SLOT_BYTES};
static nor_part_t cred_part = {.chip = &chip, .base = 2 * STORE_SLOT_BYTES, .size = CRED_BYTES};

static const uint8_t OLD_DOC[] = "{\"schema\":1,\"seq\":7,\"obs\":{\"url\":\"ws://192.168.1.20:4455\"}}";
#define OLD_LEN ((uint32_t)sizeof OLD_DOC - 1)
// Longer than one sector, so the new body spans sectors the old one did not reach.
#define NEW_LEN 6000u
static uint8_t new_doc[NEW_LEN];

static const store_doc_t OLDEST = {.schema = 1, .seq = 6, .len = OLD_LEN};
static const store_doc_t OLD = {.schema = 1, .seq = 7, .len = OLD_LEN};
static const store_doc_t NEW = {.schema = 1, .seq = 8, .len = NEW_LEN};

static void make_new_doc(void) {
	static const char head[] = "{\"schema\":1,\"seq\":8,\"pad\":\"";
	memset(new_doc, 'n', NEW_LEN);
	memcpy(new_doc, head, sizeof head - 1);
	memcpy(&new_doc[NEW_LEN - 2], "\"}", 2);
}

static store_t mounted(void) {
	store_t store;
	store_mount(&store, &NOR_FLASH, &slot_a, &slot_b);
	return store;
}

// True when the store serves exactly `doc` with `body`.
static bool serves(const store_t *store, const store_doc_t *doc, const uint8_t *body) {
	static uint8_t got[CONFIG_MAX_BYTES];
	return store->state == STORE_LOADED && store->doc.schema == doc->schema &&
	       store->doc.seq == doc->seq && store->doc.len == doc->len &&
	       store_read(store, 0, got, doc->len) && memcmp(got, body, doc->len) == 0;
}

static void test_crc32_check_values(void) {
	CHECK(store_crc32((const uint8_t *)"123456789", 9) == 0xCBF43926u);
	CHECK(store_crc32((const uint8_t *)"{\"schema\":1,\"seq\":7}", 20) == 0xCA7AE782u);
	CHECK(store_crc32(NULL, 0) == 0);
}

static void test_an_erased_chip_has_no_document(void) {
	nor_chip_init(&chip);
	store_t store = mounted();
	uint8_t byte;
	CHECK(store.state == STORE_NONE);
	CHECK(!store_read(&store, 0, &byte, 1));
}

static void test_a_commit_survives_a_reboot(void) {
	nor_chip_init(&chip);
	store_t store = mounted();
	CHECK(store_commit(&store, &OLD, OLD_DOC) == STORE_OK);
	CHECK(serves(&store, &OLD, OLD_DOC));
	store_t rebooted = mounted();
	CHECK(serves(&rebooted, &OLD, OLD_DOC));
	CHECK(!chip.raised_a_bit);
}

static void test_a_commit_writes_the_other_slot(void) {
	nor_chip_init(&chip);
	store_t store = mounted();
	CHECK(store_commit(&store, &OLD, OLD_DOC) == STORE_OK);
	static uint8_t first_slot[STORE_SLOT_BYTES];
	memcpy(first_slot, &chip.bytes[slot_a.base], STORE_SLOT_BYTES);
	CHECK(store_commit(&store, &NEW, new_doc) == STORE_OK);
	CHECK(memcmp(first_slot, &chip.bytes[slot_a.base], STORE_SLOT_BYTES) == 0);
	CHECK(serves(&store, &NEW, new_doc));
	store_t rebooted = mounted();
	CHECK(serves(&rebooted, &NEW, new_doc));
}

static void test_refused_commits_write_nothing(void) {
	nor_chip_init(&chip);
	store_t store = mounted();
	CHECK(store_commit(&store, &OLD, OLD_DOC) == STORE_OK);
	int before = chip.mutations;
	store_doc_t same_seq = OLD;
	store_doc_t empty = NEW;
	empty.len = 0;
	store_doc_t too_long = NEW;
	too_long.len = CONFIG_MAX_BYTES + 1;
	CHECK(store_commit(&store, &same_seq, OLD_DOC) == STORE_STALE_SEQ);
	CHECK(store_commit(&store, &OLDEST, OLD_DOC) == STORE_STALE_SEQ);
	CHECK(store_commit(&store, &empty, new_doc) == STORE_BAD_LEN);
	CHECK(store_commit(&store, &too_long, new_doc) == STORE_BAD_LEN);
	CHECK(chip.mutations == before);
	CHECK(serves(&store, &OLD, OLD_DOC));
}

static void test_reads_past_the_body_fail(void) {
	nor_chip_init(&chip);
	store_t store = mounted();
	CHECK(store_commit(&store, &OLD, OLD_DOC) == STORE_OK);
	uint8_t got[OLD_LEN];
	CHECK(store_read(&store, OLD_LEN - 1, got, 1) && got[0] == '}');
	CHECK(store_read(&store, OLD_LEN, got, 0));
	CHECK(!store_read(&store, OLD_LEN, got, 1));
	CHECK(!store_read(&store, 1, got, OLD_LEN));
	CHECK(!store_read(&store, UINT32_MAX, got, 2));
}

// Brings the chip to a start state: none, or slot A with seq 6 and slot B (current) with seq 7.
static void start(bool with_documents) {
	nor_chip_init(&chip);
	if (with_documents) {
		store_t store = mounted();
		CHECK(store_commit(&store, &OLDEST, OLD_DOC) == STORE_OK);
		CHECK(store_commit(&store, &OLD, OLD_DOC) == STORE_OK);
	}
}

static int calls_one_commit_makes(bool with_documents) {
	start(with_documents);
	store_t store = mounted();
	int before = chip.mutations;
	CHECK(store_commit(&store, &NEW, new_doc) == STORE_OK);
	return chip.mutations - before;
}

// The header sector of `slot` as erase left it: nothing programmed there yet.
static bool header_is_erased(const nor_part_t *slot) {
	for (uint32_t at = 0; at < STORE_SECTOR_BYTES; at++) {
		if (chip.bytes[slot->base + at] != 0xFF) {
			return false;
		}
	}
	return true;
}

// Both start states commit the new document to slot A. After the cut: the old document (or
// none, from an empty chip) or the new one, never a mix, never the older seq 6.
static void check_boot_after_cut(bool with_documents, int calls, bool torn, int all_calls) {
	start(with_documents);
	store_t store = mounted();
	nor_chip_cut_after(&chip, calls, torn);
	store_status_t status = store_commit(&store, &NEW, new_doc);
	nor_chip_restore(&chip);
	store_t rebooted = mounted();
	bool booted_new = serves(&rebooted, &NEW, new_doc);
	bool booted_old = with_documents ? serves(&rebooted, &OLD, OLD_DOC)
					 : rebooted.state == STORE_NONE;
	CHECK(booted_new != booted_old);
	CHECK(calls < all_calls || (status == STORE_OK && booted_new));
	CHECK(calls > 0 || booted_old);
	CHECK(status == STORE_OK || serves(&store, &OLD, OLD_DOC) || store.state == STORE_NONE);
	CHECK(!chip.raised_a_bit);
	CHECK(calls != all_calls - 1 || torn || header_is_erased(&slot_a));
	if (booted_new == booted_old) {
		fprintf(stderr, "  cut after %d of %d calls, torn %d, documents %d\n", calls, all_calls,
			torn, with_documents);
	}
}

static void test_a_power_cut_after_every_call_boots_old_or_new(void) {
	for (int with_documents = 0; with_documents <= 1; with_documents++) {
		int all_calls = calls_one_commit_makes(with_documents);
		CHECK(all_calls >= 4); // two erases, the body, the header
		for (int calls = 0; calls <= all_calls; calls++) {
			check_boot_after_cut(with_documents, calls, false, all_calls);
			check_boot_after_cut(with_documents, calls, true, all_calls);
		}
	}
}

static void test_a_bad_slot_loses_to_the_good_one(void) {
	start(true);
	chip.bytes[slot_b.base + STORE_BODY_OFFSET + 3] ^= 0x01; // one body bit of seq 7
	store_t store = mounted();
	CHECK(store.state == STORE_LOADED && store.doc.seq == OLDEST.seq);
	start(true);
	chip.bytes[slot_b.base + 8] ^= 0x80; // one header bit of seq 7
	store = mounted();
	CHECK(store.state == STORE_LOADED && store.doc.seq == OLDEST.seq);
}

// Spec 8.2, criterion 14: new firmware over an old document.
static void test_a_schema_below_min_is_kept_and_served(void) {
	nor_chip_init(&chip);
	store_t store = mounted();
	store_doc_t old_schema = OLD;
	old_schema.schema = CONFIG_SCHEMA_MIN - 1;
	CHECK(store_commit(&store, &old_schema, OLD_DOC) == STORE_OK);
	static uint8_t before[NOR_CHIP_BYTES];
	memcpy(before, chip.bytes, sizeof before);
	int mutations = chip.mutations;

	store_t rebooted = mounted();
	CHECK(rebooted.state == STORE_UNLOADED);
	CHECK(rebooted.doc.schema == CONFIG_SCHEMA_MIN - 1 && rebooted.doc.seq == OLD.seq);
	CHECK(rebooted.doc.len == OLD_LEN);
	uint8_t got[OLD_LEN];
	CHECK(store_read(&rebooted, 0, got, OLD_LEN) && memcmp(got, OLD_DOC, OLD_LEN) == 0);
	CHECK(chip.mutations == mutations);
	CHECK(memcmp(before, chip.bytes, sizeof before) == 0);

	store_doc_t migrated = NEW;
	migrated.seq = OLD.seq + 1;
	CHECK(store_commit(&rebooted, &migrated, new_doc) == STORE_OK);
	CHECK(serves(&rebooted, &migrated, new_doc));
}

static void test_a_schema_above_max_is_not_loaded(void) {
	nor_chip_init(&chip);
	store_t store = mounted();
	store_doc_t new_schema = OLD;
	new_schema.schema = CONFIG_SCHEMA_MAX + 1;
	CHECK(store_commit(&store, &new_schema, OLD_DOC) == STORE_OK);
	CHECK(store.state == STORE_UNLOADED);
	store_t rebooted = mounted();
	CHECK(rebooted.state == STORE_UNLOADED && rebooted.doc.seq == OLD.seq);
}

static void test_erase_leaves_no_document(void) {
	start(true);
	store_t store = mounted();
	CHECK(store_erase(&store) == STORE_OK);
	CHECK(store.state == STORE_NONE);
	store_t rebooted = mounted();
	CHECK(rebooted.state == STORE_NONE);
	CHECK(store_commit(&rebooted, &OLDEST, OLD_DOC) == STORE_OK);
}

static void test_a_failed_erase_still_drops_the_document(void) {
	start(true);
	store_t store = mounted();
	nor_chip_cut_after(&chip, 0, false);
	CHECK(store_erase(&store) == STORE_FLASH_FAIL);
	CHECK(store.state == STORE_NONE);
	nor_chip_restore(&chip);
}

// A fake of the port's plain NVS in `cred_part`: a put appends [kind][len][bytes] and leaves the
// older copy in flash, as an NVS key overwrite can until page reuse (spec 8.2).
typedef struct {
	cred_t cred;
	nor_part_t *part;
} nvs_fake_t;

// Offset of the newest entry of `kind`, or -1. `*end` is where the next entry goes.
static long find_entry(nvs_fake_t *nvs, enum link_credential_kind kind, uint32_t *end) {
	long newest = -1;
	uint32_t at = 0;
	uint8_t head[2];
	while (at + 2 <= nvs->part->size && NOR_FLASH.read(nvs->part, at, head, 2) && head[0] != 0xFF) {
		if (head[0] == kind) {
			newest = (long)at;
		}
		at += 2u + head[1];
	}
	*end = at;
	return newest;
}

static bool nvs_put(cred_t *cred, enum link_credential_kind kind, const uint8_t *bytes, size_t len) {
	nvs_fake_t *nvs = (nvs_fake_t *)cred;
	uint32_t end;
	find_entry(nvs, kind, &end);
	uint8_t head[2] = {(uint8_t)kind, (uint8_t)len};
	return end + 2 + len <= nvs->part->size &&
	       NOR_FLASH.program(nvs->part, end + 2, bytes, (uint32_t)len) &&
	       NOR_FLASH.program(nvs->part, end, head, 2);
}

static size_t nvs_get(cred_t *cred, enum link_credential_kind kind, uint8_t *out, size_t cap) {
	nvs_fake_t *nvs = (nvs_fake_t *)cred;
	uint32_t end;
	long at = find_entry(nvs, kind, &end);
	uint8_t head[2];
	if (at < 0 || !NOR_FLASH.read(nvs->part, (uint32_t)at, head, 2) || head[1] > cap) {
		return 0;
	}
	return NOR_FLASH.read(nvs->part, (uint32_t)at + 2, out, head[1]) ? head[1] : 0;
}

static bool nvs_is_set(cred_t *cred, enum link_credential_kind kind) {
	uint32_t end;
	return find_entry((nvs_fake_t *)cred, kind, &end) >= 0;
}

static bool nvs_erase_all(cred_t *cred) {
	nvs_fake_t *nvs = (nvs_fake_t *)cred;
	return NOR_FLASH.erase(nvs->part, 0, nvs->part->size);
}

static nvs_fake_t nvs_fake(void) {
	return (nvs_fake_t){
		.cred = {.put = nvs_put, .is_set = nvs_is_set, .get = nvs_get, .erase_all = nvs_erase_all},
		.part = &cred_part,
	};
}

static const char OBS_PASSWORD[] = "dummy-obs-pw-Q7z!";
static const char OBS_PASSWORD_BEFORE[] = "first-obs-pw-K3v#";
static const char WIFI_PSK[] = "dummy-wifi-psk-W9x";

// True when `dump` holds SECRET_RUN or more bytes of `secret` in a row.
static bool holds_a_run_of(const uint8_t *dump, size_t dump_len, const char *secret) {
	size_t secret_len = strlen(secret);
	for (size_t from = 0; from + SECRET_RUN <= secret_len; from++) {
		for (size_t at = 0; at + SECRET_RUN <= dump_len; at++) {
			if (memcmp(&dump[at], &secret[from], SECRET_RUN) == 0) {
				return true;
			}
		}
	}
	return false;
}

static bool holds_any_secret(const uint8_t *dump, size_t dump_len) {
	return holds_a_run_of(dump, dump_len, OBS_PASSWORD) ||
	       holds_a_run_of(dump, dump_len, OBS_PASSWORD_BEFORE) ||
	       holds_a_run_of(dump, dump_len, WIFI_PSK);
}

static void put_secret(cred_t *cred, enum link_credential_kind kind, const char *secret) {
	CHECK(cred->put(cred, kind, (const uint8_t *)secret, strlen(secret)));
}

static void store_both_secrets(cred_t *cred) {
	put_secret(cred, LINK_CREDENTIAL_OBS_PASSWORD, OBS_PASSWORD_BEFORE);
	put_secret(cred, LINK_CREDENTIAL_OBS_PASSWORD, OBS_PASSWORD);
	put_secret(cred, LINK_CREDENTIAL_WIFI_PASSPHRASE, WIFI_PSK);
}

static void test_no_credential_byte_reaches_cfg_data(void) {
	nor_chip_init(&chip);
	nvs_fake_t nvs = nvs_fake();
	store_both_secrets(&nvs.cred);
	store_t store = mounted();
	CHECK(store_commit(&store, &OLD, OLD_DOC) == STORE_OK);
	CHECK(store_commit(&store, &NEW, new_doc) == STORE_OK);

	static uint8_t served[CONFIG_MAX_BYTES];
	uint32_t at = 0;
	while (at < store.doc.len) {
		uint32_t chunk = store.doc.len - at < LINK_CFG_DATA_MAX ? store.doc.len - at : LINK_CFG_DATA_MAX;
		CHECK(store_read(&store, at, &served[at], chunk));
		at += chunk;
	}
	CHECK(!holds_any_secret(served, store.doc.len));
	CHECK(!holds_any_secret(&chip.bytes[slot_a.base], 2 * STORE_SLOT_BYTES));
	CHECK(holds_any_secret(&chip.bytes[cred_part.base], CRED_BYTES));
}

static void test_clear_leaves_no_secret_byte_in_cred(void) {
	nor_chip_init(&chip);
	nvs_fake_t nvs = nvs_fake();
	store_both_secrets(&nvs.cred);
	const uint8_t *dump = &chip.bytes[cred_part.base];
	uint8_t got[LINK_CREDENTIAL_MAX];
	size_t got_len = nvs.cred.get(&nvs.cred, LINK_CREDENTIAL_OBS_PASSWORD, got, sizeof got);
	CHECK(got_len == strlen(OBS_PASSWORD));
	CHECK(memcmp(got, OBS_PASSWORD, strlen(OBS_PASSWORD)) == 0);
	CHECK(holds_a_run_of(dump, CRED_BYTES, OBS_PASSWORD_BEFORE)); // the stale copy a key erase keeps
	CHECK(holds_a_run_of(dump, CRED_BYTES, OBS_PASSWORD));
	CHECK(holds_a_run_of(dump, CRED_BYTES, WIFI_PSK));

	CHECK(nvs.cred.erase_all(&nvs.cred));
	CHECK(!holds_any_secret(dump, CRED_BYTES));
	CHECK(!nvs.cred.is_set(&nvs.cred, LINK_CREDENTIAL_OBS_PASSWORD));
	CHECK(!nvs.cred.is_set(&nvs.cred, LINK_CREDENTIAL_WIFI_PASSPHRASE));
}

int main(void) {
	make_new_doc();
	test_crc32_check_values();
	test_an_erased_chip_has_no_document();
	test_a_commit_survives_a_reboot();
	test_a_commit_writes_the_other_slot();
	test_refused_commits_write_nothing();
	test_reads_past_the_body_fail();
	test_a_power_cut_after_every_call_boots_old_or_new();
	test_a_bad_slot_loses_to_the_good_one();
	test_a_schema_below_min_is_kept_and_served();
	test_a_schema_above_max_is_not_loaded();
	test_erase_leaves_no_document();
	test_a_failed_erase_still_drops_the_document();
	test_no_credential_byte_reaches_cfg_data();
	test_clear_leaves_no_secret_byte_in_cred();
	if (failures != 0) {
		fprintf(stderr, "test_store: %d failed\n", failures);
		return 1;
	}
	printf("test_store: ok\n");
	return 0;
}
