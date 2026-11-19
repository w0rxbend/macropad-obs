// SPDX-License-Identifier: MIT
#include "crypto.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;

#define CHECK(cond)                                                                          \
	do {                                                                                 \
		if (!(cond)) {                                                               \
			fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #cond);           \
			failures++;                                                          \
		}                                                                            \
	} while (0)

static void expect_text(const char *name, const char *got, const char *want) {
	if (strcmp(got, want) != 0) {
		fprintf(stderr, "%s: got %s, want %s\n", name, got, want);
		failures++;
	}
}

typedef struct {
	const char *bytes;
	size_t len;
	const char *text;
} base64_vector_t;

// RFC 4648 section 10, then three inputs that reach '+' and '/' with each padding length.
static const base64_vector_t BASE64_VECTORS[] = {
	{"", 0, ""},
	{"f", 1, "Zg=="},
	{"fo", 2, "Zm8="},
	{"foo", 3, "Zm9v"},
	{"foob", 4, "Zm9vYg=="},
	{"fooba", 5, "Zm9vYmE="},
	{"foobar", 6, "Zm9vYmFy"},
	{"\xfb\xff\xfe", 3, "+//+"},
	{"\xfb\xff", 2, "+/8="},
	{"\xff", 1, "/w=="},
};

// The buffer is exactly as long as the header promises, so ASan sees one byte too many.
static void test_base64_encodes_rfc_4648_vectors(void) {
	for (size_t i = 0; i < sizeof BASE64_VECTORS / sizeof BASE64_VECTORS[0]; i++) {
		const base64_vector_t *v = &BASE64_VECTORS[i];
		char *text = malloc(CRYPTO_BASE64_LEN(v->len) + 1);
		if (text == NULL) {
			abort();
		}
		crypto_base64_encode((const uint8_t *)v->bytes, v->len, text);
		expect_text(v->text, text, v->text);
		CHECK(strlen(text) == CRYPTO_BASE64_LEN(v->len));
		free(text);
	}
}

static void expect_hex(const char *name, const uint8_t *digest, size_t len, const char *want_hex) {
	char got_hex[2 * CRYPTO_SHA256_LEN + 1] = "";
	for (size_t i = 0; i < len; i++) {
		snprintf(got_hex + 2 * i, 3, "%02x", digest[i]);
	}
	expect_text(name, got_hex, want_hex);
}

#define MESSAGE_448_BITS "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"
#define MESSAGE_896_BITS                                                                     \
	"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopq"   \
	"klmnopqrlmnopqrsmnopqrstnopqrstu"
#define SHA1_OF_896_BITS "a49b2446a02c645bf419f995b67091253a04a259"
#define SHA256_OF_896_BITS "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1"

typedef struct {
	const char *name;
	const char *chunk; // the message is `chunk`, `repeat` times over
	size_t repeat;
	const char *sha1_hex;
	const char *sha256_hex;
} hash_vector_t;

static const hash_vector_t HASH_VECTORS[] = {
	// NIST: FIPS 180-2 appendix A (SHA-1) and appendix B (SHA-256).
	{"abc", "abc", 1, "a9993e364706816aba3e25717850c26c9cd0d89d",
	 "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"},
	{"448 bits", MESSAGE_448_BITS, 1, "84983e441c3bd26ebaae4aa1f95129e5e54670f1",
	 "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"},
	{"one million a", "a", 1000000, "34aa973cd4c4daa4f61eeb2bdbad27316534016f",
	 "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"},
	// NIST: CAVP short messages, Len = 0.
	{"empty", "", 1, "da39a3ee5e6b4b0d3255bfef95601890afd80709",
	 "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
	// Not NIST: digests from Python hashlib. 55 bytes is the longest message whose padding
	// fits its own block, and 64 bytes fills a block exactly.
	{"896 bits", MESSAGE_896_BITS, 1, SHA1_OF_896_BITS, SHA256_OF_896_BITS},
	{"55 a", "a", 55, "c1c8bbdc22796e28c0e15163d20899b65621d65a",
	 "9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318"},
	{"56 a", "a", 56, "c2db330f6083854c99d4b5bfb6e8f29f201be699",
	 "b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a"},
	{"63 a", "a", 63, "03f09f5b158a7a8cdad920bddc29b81c18a551f5",
	 "7d3e74a05d7db15bce4ad9ec0658ea98e3f06eeecf16b4c6fff2da457ddc2f34"},
	{"64 a", "a", 64, "0098ba824b5c16427bd7a1122a5a442a25ec644d",
	 "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb"},
	{"65 a", "a", 65, "11655326c708d70319be2610e8a57d9a5b959d3b",
	 "635361c48bb9eab14198e76ea8ab7f1a41685d6ad62aa9146d301d4f17eb0ae0"},
};
#define HASH_VECTOR_COUNT (sizeof HASH_VECTORS / sizeof HASH_VECTORS[0])

static void test_sha256_matches_nist_and_padding_vectors(void) {
	for (size_t i = 0; i < HASH_VECTOR_COUNT; i++) {
		const hash_vector_t *v = &HASH_VECTORS[i];
		crypto_sha256_t sha;
		uint8_t digest[CRYPTO_SHA256_LEN];
		crypto_sha256_init(&sha);
		for (size_t n = 0; n < v->repeat; n++) {
			crypto_sha256_update(&sha, v->chunk, strlen(v->chunk));
		}
		crypto_sha256_final(&sha, digest);
		expect_hex(v->name, digest, sizeof digest, v->sha256_hex);
	}
}

static void test_sha256_gives_one_digest_at_every_split(void) {
	const char *message = MESSAGE_896_BITS;
	size_t len = strlen(message);
	for (size_t split = 0; split <= len; split++) {
		crypto_sha256_t sha;
		uint8_t digest[CRYPTO_SHA256_LEN];
		char name[40];
		snprintf(name, sizeof name, "sha256 split at %zu", split);
		crypto_sha256_init(&sha);
		crypto_sha256_update(&sha, message, split);
		crypto_sha256_update(&sha, message + split, len - split);
		crypto_sha256_final(&sha, digest);
		expect_hex(name, digest, sizeof digest, SHA256_OF_896_BITS);
	}
}

static void test_sha256_final_wipes_the_context(void) {
	static const crypto_sha256_t WIPED;
	crypto_sha256_t sha;
	uint8_t digest[CRYPTO_SHA256_LEN];
	crypto_sha256_init(&sha);
	crypto_sha256_update(&sha, "abc", 3);
	crypto_sha256_final(&sha, digest);
	CHECK(memcmp(&sha, &WIPED, sizeof sha) == 0);
}

static void test_sha1_matches_nist_and_padding_vectors(void) {
	for (size_t i = 0; i < HASH_VECTOR_COUNT; i++) {
		const hash_vector_t *v = &HASH_VECTORS[i];
		crypto_sha1_t sha;
		uint8_t digest[CRYPTO_SHA1_LEN];
		crypto_sha1_init(&sha);
		for (size_t n = 0; n < v->repeat; n++) {
			crypto_sha1_update(&sha, v->chunk, strlen(v->chunk));
		}
		crypto_sha1_final(&sha, digest);
		expect_hex(v->name, digest, sizeof digest, v->sha1_hex);
	}
}

static void test_sha1_gives_one_digest_at_every_split(void) {
	const char *message = MESSAGE_896_BITS;
	size_t len = strlen(message);
	for (size_t split = 0; split <= len; split++) {
		crypto_sha1_t sha;
		uint8_t digest[CRYPTO_SHA1_LEN];
		char name[40];
		snprintf(name, sizeof name, "sha1 split at %zu", split);
		crypto_sha1_init(&sha);
		crypto_sha1_update(&sha, message, split);
		crypto_sha1_update(&sha, message + split, len - split);
		crypto_sha1_final(&sha, digest);
		expect_hex(name, digest, sizeof digest, SHA1_OF_896_BITS);
	}
}

static void test_sha1_final_wipes_the_context(void) {
	static const crypto_sha1_t WIPED;
	crypto_sha1_t sha;
	uint8_t digest[CRYPTO_SHA1_LEN];
	crypto_sha1_init(&sha);
	crypto_sha1_update(&sha, "abc", 3);
	crypto_sha1_final(&sha, digest);
	CHECK(memcmp(&sha, &WIPED, sizeof sha) == 0);
}

#define OBS_AUTH_LEN CRYPTO_BASE64_LEN(CRYPTO_SHA256_LEN)

// base64(sha256(head + tail)): one step of the obs-websocket 5 log-in (spec 8.3).
static void obs_auth_step(const char *head, const char *tail, char text[OBS_AUTH_LEN + 1]) {
	crypto_sha256_t sha;
	uint8_t digest[CRYPTO_SHA256_LEN];
	crypto_sha256_init(&sha);
	crypto_sha256_update(&sha, head, strlen(head));
	crypto_sha256_update(&sha, tail, strlen(tail));
	crypto_sha256_final(&sha, digest);
	crypto_base64_encode(digest, sizeof digest, text);
}

// docs/research/05-obs-websocket.md section 3. The password is the public example of the
// obs-websocket protocol document, not a credential. Salt and challenge are hashed as text.
static void test_obs_auth_example_gives_the_published_string(void) {
	char secret[OBS_AUTH_LEN + 1];
	char auth[OBS_AUTH_LEN + 1];
	obs_auth_step("supersecretpassword", "lM1GncleQOaCu9lT1yeUZhFYnqhsLLP1G5lAGo3ixaI=", secret);
	obs_auth_step(secret, "+IxH4CnCiqpX1rM9scsNynZzbOe4KhDeYcTNS3PDaeY=", auth);
	expect_text("obs secret", secret, "H1IfVz1pSREUQzbFTVnX/Tyb+gMhMik5x7yUBCY0PTs=");
	expect_text("obs auth", auth, "1Ct943GAT+6YQUUX47Ia/ncufilbe6+oD6lY+5kaCu4=");
}

int main(void) {
	test_base64_encodes_rfc_4648_vectors();
	test_sha256_matches_nist_and_padding_vectors();
	test_sha256_gives_one_digest_at_every_split();
	test_sha256_final_wipes_the_context();
	test_sha1_matches_nist_and_padding_vectors();
	test_sha1_gives_one_digest_at_every_split();
	test_sha1_final_wipes_the_context();
	test_obs_auth_example_gives_the_published_string();
	if (failures) {
		fprintf(stderr, "%d check(s) failed\n", failures);
		return 1;
	}
	puts("crypto: all tests pass");
	return 0;
}
