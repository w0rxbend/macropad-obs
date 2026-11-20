// SPDX-License-Identifier: MIT
// config.c is a stub until task 2.9, so every vector must come back CONFIG_UNIMPLEMENTED.
// Task 2.9 replaces this test with one that holds each verdict and path against verdicts.txt.
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

static void check_stub_verdict(const char *name) {
	static uint8_t doc[VECTOR_CAP];
	config_result_t result = config_validate(doc, read_vector(name, doc));
	if (result.verdict != CONFIG_UNIMPLEMENTED || result.path[0] != '\0') {
		fprintf(stderr, "%s: verdict %d, path \"%s\"\n", name, (int)result.verdict, result.path);
		failures++;
	}
	vector_count++;
}

static void test_the_stub_answers_unimplemented_for_every_vector(void) {
	FILE *table = open_in_vectors("verdicts.txt");
	char line[256];
	while (fgets(line, sizeof line, table)) {
		const char *name = strtok(line, " \t\n");
		if (name != NULL && name[0] != '#') {
			check_stub_verdict(name);
		}
	}
	fclose(table);
	if (vector_count == 0) {
		die("no vector in", "verdicts.txt");
	}
}

int main(void) {
	test_the_stub_answers_unimplemented_for_every_vector();
	if (failures) {
		fprintf(stderr, "%d vector(s) failed\n", failures);
		return 1;
	}
	printf("config: stub answers unimplemented for all %zu vectors\n", vector_count);
	return 0;
}
