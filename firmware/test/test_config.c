// SPDX-License-Identifier: MIT
// Every file in config_vectors/ must give the verdict and the first bad path that verdicts.txt
// lists for it. host/obs_core/src/document.rs holds the same table, so C and Rust agree (R3).
#include "config.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// One byte past the largest vector, so a file that does not fit is seen and not cut short.
#define VECTOR_CAP (CONFIG_MAX_BYTES + 2)

static int failures;
static size_t vector_count;

static void die(const char *what, const char *name) {
	fprintf(stderr, "%s %s\n", what, name);
	exit(2);
}

static FILE *open_in_vectors(const char *name) {
	char path[512];
	int n = snprintf(path, sizeof path, "%s/%s", CONFIG_VECTORS, name);
	if (n < 0 || (size_t)n >= sizeof path) {
		die("path too long for", name);
	}
	FILE *f = fopen(path, "rb");
	if (f == NULL) {
		die("cannot open", path);
	}
	return f;
}

static size_t read_vector(const char *name, uint8_t *bytes) {
	FILE *f = open_in_vectors(name);
	size_t len = fread(bytes, 1, VECTOR_CAP, f);
	if (ferror(f) || len == VECTOR_CAP) {
		die("cannot read all of", name);
	}
	fclose(f);
	return len;
}

// The verdict and path of one verdicts.txt line after its file name. NULL words read as missing.
static config_result_t expected_result(const char *verdict, const char *path, const char *name) {
	config_result_t expected = {.verdict = CONFIG_INVALID};
	if (verdict == NULL) {
		die("no verdict for", name);
	}
	if (strcmp(verdict, "valid") == 0) {
		expected.verdict = CONFIG_VALID;
	} else if (strcmp(verdict, "too_big") == 0) {
		expected.verdict = CONFIG_TOO_BIG;
	} else if (strcmp(verdict, "invalid") != 0) {
		die("unknown verdict for", name);
	}
	if (path != NULL) {
		if (expected.verdict != CONFIG_INVALID || strlen(path) > CONFIG_PATH_MAX) {
			die("bad path for", name);
		}
		strcpy(expected.path, path);
	}
	return expected;
}

static void check_vector(const char *name, config_result_t expected) {
	static uint8_t doc[VECTOR_CAP];
	config_result_t got = config_validate(doc, read_vector(name, doc));
	if (got.verdict != expected.verdict || strcmp(got.path, expected.path) != 0) {
		fprintf(stderr, "%s: expected verdict %d path \"%s\", got verdict %d path \"%s\"\n", name,
		        (int)expected.verdict, expected.path, (int)got.verdict, got.path);
		failures++;
	}
	vector_count++;
}

static void test_every_vector_gives_its_verdict_and_path(void) {
	FILE *table = open_in_vectors("verdicts.txt");
	char line[256];
	while (fgets(line, sizeof line, table)) {
		const char *name = strtok(line, " \t\n");
		if (name == NULL || name[0] == '#') {
			continue;
		}
		const char *verdict = strtok(NULL, " \t\n");
		const char *path = strtok(NULL, " \t\n");
		check_vector(name, expected_result(verdict, path, name));
	}
	fclose(table);
	if (vector_count == 0) {
		die("no vector in", "verdicts.txt");
	}
}

// A document cut short at any byte is no JSON object. Under ASan this also walks every partial
// state of the read pass.
static void test_every_cut_of_a_valid_document_is_invalid_with_an_empty_path(void) {
	static uint8_t doc[VECTOR_CAP];
	size_t len = read_vector("valid_full.json", doc);
	for (size_t cut = 0; cut < len; cut++) {
		config_result_t got = config_validate(doc, cut);
		if (got.verdict != CONFIG_INVALID || got.path[0] != '\0') {
			fprintf(stderr, "valid_full.json cut at %zu: verdict %d path \"%s\"\n", cut, (int)got.verdict, got.path);
			failures++;
		}
	}
}

int main(void) {
	test_every_vector_gives_its_verdict_and_path();
	test_every_cut_of_a_valid_document_is_invalid_with_an_empty_path();
	if (failures) {
		fprintf(stderr, "%d of %zu vector(s) failed\n", failures, vector_count);
		return 1;
	}
	printf("config: all %zu vectors give their verdict and path\n", vector_count);
	return 0;
}
