// SPDX-License-Identifier: MIT
// SHA-1, SHA-256 and base64 for the WebSocket upgrade and the obs-websocket log-in (spec 8.3).
// Pure C, no SDK headers, so firmware/test runs it under ASan.
#pragma once

#include <stddef.h>
#include <stdint.h>

#define CRYPTO_SHA1_LEN 20
#define CRYPTO_SHA256_LEN 32
#define CRYPTO_BLOCK_LEN 64
// Characters that base64 makes from `n` bytes: the padding counts, the NUL does not.
#define CRYPTO_BASE64_LEN(n) (((n) + 2) / 3 * 4)

// What either hash keeps between calls. Hold it as crypto_sha1_t or crypto_sha256_t.
typedef struct {
	uint32_t state[8]; // SHA-1 uses the first five words
	uint64_t byte_count;
	uint8_t block[CRYPTO_BLOCK_LEN];
} crypto_hash_t;

// One type per hash, so a SHA-1 context does not compile into a SHA-256 call.
typedef struct {
	crypto_hash_t hash;
} crypto_sha1_t;

typedef struct {
	crypto_hash_t hash;
} crypto_sha256_t;

// Call init, then update any number of times, then final. final writes the digest and wipes
// the context, because SHA-256 hashes the OBS password. Call init again before the next message.
void crypto_sha1_init(crypto_sha1_t *sha);
void crypto_sha1_update(crypto_sha1_t *sha, const void *data, size_t len);
void crypto_sha1_final(crypto_sha1_t *sha, uint8_t digest[CRYPTO_SHA1_LEN]);

void crypto_sha256_init(crypto_sha256_t *sha);
void crypto_sha256_update(crypto_sha256_t *sha, const void *data, size_t len);
void crypto_sha256_final(crypto_sha256_t *sha, uint8_t digest[CRYPTO_SHA256_LEN]);

// RFC 4648 section 4, with padding. Writes CRYPTO_BASE64_LEN(len) characters and a NUL.
void crypto_base64_encode(const uint8_t *bytes, size_t len, char *text);
