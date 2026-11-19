// SPDX-License-Identifier: MIT
// FIPS 180-4 for the two hashes, RFC 4648 for base64.
#include "crypto.h"

#include <string.h>

// The last 8 bytes of the final block hold the message length in bits.
#define BIT_COUNT_AT (CRYPTO_BLOCK_LEN - 8)

typedef void compress_fn(uint32_t state[8], const uint8_t block[CRYPTO_BLOCK_LEN]);

// A memset of memory that is never read again may be compiled out. This loop is not.
static void wipe(void *secret, size_t len) {
	volatile uint8_t *bytes = secret;
	for (size_t i = 0; i < len; i++) {
		bytes[i] = 0;
	}
}

static uint32_t rotate_left(uint32_t word, unsigned bits) {
	return (word << bits) | (word >> (32 - bits));
}

static uint32_t rotate_right(uint32_t word, unsigned bits) {
	return (word >> bits) | (word << (32 - bits));
}

static uint32_t read_be32(const uint8_t *src) {
	return ((uint32_t)src[0] << 24) | ((uint32_t)src[1] << 16) | ((uint32_t)src[2] << 8) | src[3];
}

static void write_be32(uint8_t *dst, uint32_t word) {
	dst[0] = (uint8_t)(word >> 24);
	dst[1] = (uint8_t)(word >> 16);
	dst[2] = (uint8_t)(word >> 8);
	dst[3] = (uint8_t)word;
}

static void hash_update(crypto_hash_t *hash, compress_fn *compress, const uint8_t *data,
			size_t len) {
	size_t fill = (size_t)(hash->byte_count % CRYPTO_BLOCK_LEN);
	hash->byte_count += len;
	for (size_t i = 0; i < len; i++) {
		hash->block[fill++] = data[i];
		if (fill == CRYPTO_BLOCK_LEN) {
			compress(hash->state, hash->block);
			fill = 0;
		}
	}
}

// Pads with 0x80, zeros and the bit count. The digest is the first `digest_len` state bytes.
static void hash_final(crypto_hash_t *hash, compress_fn *compress, uint8_t *digest,
		       size_t digest_len) {
	uint64_t bit_count = hash->byte_count * 8;
	size_t fill = (size_t)(hash->byte_count % CRYPTO_BLOCK_LEN);
	hash->block[fill++] = 0x80;
	if (fill > BIT_COUNT_AT) {
		memset(hash->block + fill, 0, CRYPTO_BLOCK_LEN - fill);
		compress(hash->state, hash->block);
		fill = 0;
	}
	memset(hash->block + fill, 0, BIT_COUNT_AT - fill);
	write_be32(hash->block + BIT_COUNT_AT, (uint32_t)(bit_count >> 32));
	write_be32(hash->block + BIT_COUNT_AT + 4, (uint32_t)bit_count);
	compress(hash->state, hash->block);
	for (size_t i = 0; i < digest_len / 4; i++) {
		write_be32(digest + 4 * i, hash->state[i]);
	}
	wipe(hash, sizeof *hash);
}

#define SHA1_ROUNDS 80
#define SHA1_STAGE_ROUNDS 20

static const uint32_t SHA1_STAGE_CONSTANTS[SHA1_ROUNDS / SHA1_STAGE_ROUNDS] = {
	0x5a827999,
	0x6ed9eba1,
	0x8f1bbcdc,
	0xca62c1d6,
};

// f of FIPS 180-4 section 4.1.1: Ch, Parity, Maj, Parity.
static uint32_t sha1_stage_mix(int stage, uint32_t b, uint32_t c, uint32_t d) {
	switch (stage) {
	case 0:
		return (b & c) ^ (~b & d);
	case 2:
		return (b & c) ^ (b & d) ^ (c & d);
	default:
		return b ^ c ^ d;
	}
}

// FIPS 180-4 section 6.1.2. Nothing is wiped: SHA-1 hashes only the public upgrade key.
static void sha1_compress(uint32_t state[8], const uint8_t block[CRYPTO_BLOCK_LEN]) {
	uint32_t w[SHA1_ROUNDS];
	for (int t = 0; t < 16; t++) {
		w[t] = read_be32(block + 4 * t);
	}
	for (int t = 16; t < SHA1_ROUNDS; t++) {
		w[t] = rotate_left(w[t - 3] ^ w[t - 8] ^ w[t - 14] ^ w[t - 16], 1);
	}
	uint32_t a = state[0], b = state[1], c = state[2], d = state[3], e = state[4];
	for (int t = 0; t < SHA1_ROUNDS; t++) {
		int stage = t / SHA1_STAGE_ROUNDS;
		uint32_t mixed = sha1_stage_mix(stage, b, c, d) + SHA1_STAGE_CONSTANTS[stage];
		uint32_t next_a = rotate_left(a, 5) + mixed + e + w[t];
		e = d;
		d = c;
		c = rotate_left(b, 30);
		b = a;
		a = next_a;
	}
	state[0] += a;
	state[1] += b;
	state[2] += c;
	state[3] += d;
	state[4] += e;
}

void crypto_sha1_init(crypto_sha1_t *sha) {
	sha->hash = (crypto_hash_t){
		.state = {0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0},
	};
}

void crypto_sha1_update(crypto_sha1_t *sha, const void *data, size_t len) {
	hash_update(&sha->hash, sha1_compress, data, len);
}

void crypto_sha1_final(crypto_sha1_t *sha, uint8_t digest[CRYPTO_SHA1_LEN]) {
	hash_final(&sha->hash, sha1_compress, digest, CRYPTO_SHA1_LEN);
}

static const uint32_t SHA256_ROUND_CONSTANTS[64] = {
	0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
	0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
	0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
	0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
	0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
	0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
	0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
	0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
	0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
	0xc67178f2,
};

// The message schedule W of FIPS 180-4 section 6.2.2 step 1.
static void sha256_expand(uint32_t w[64], const uint8_t block[CRYPTO_BLOCK_LEN]) {
	for (int t = 0; t < 16; t++) {
		w[t] = read_be32(block + 4 * t);
	}
	for (int t = 16; t < 64; t++) {
		uint32_t w15 = w[t - 15];
		uint32_t w2 = w[t - 2];
		uint32_t small_sigma0 = rotate_right(w15, 7) ^ rotate_right(w15, 18) ^ (w15 >> 3);
		uint32_t small_sigma1 = rotate_right(w2, 17) ^ rotate_right(w2, 19) ^ (w2 >> 10);
		w[t] = w[t - 16] + small_sigma0 + w[t - 7] + small_sigma1;
	}
}

// FIPS 180-4 section 6.2.2 steps 2 to 4. `v` holds the working variables a to h.
static void sha256_compress(uint32_t state[8], const uint8_t block[CRYPTO_BLOCK_LEN]) {
	enum { A, B, C, D, E, F, G, H };
	uint32_t w[64];
	uint32_t v[8];
	sha256_expand(w, block);
	memcpy(v, state, sizeof v);
	for (int t = 0; t < 64; t++) {
		uint32_t big_sigma1 =
			rotate_right(v[E], 6) ^ rotate_right(v[E], 11) ^ rotate_right(v[E], 25);
		uint32_t choice = (v[E] & v[F]) ^ (~v[E] & v[G]);
		uint32_t t1 = v[H] + big_sigma1 + choice + SHA256_ROUND_CONSTANTS[t] + w[t];
		uint32_t big_sigma0 =
			rotate_right(v[A], 2) ^ rotate_right(v[A], 13) ^ rotate_right(v[A], 22);
		uint32_t majority = (v[A] & v[B]) ^ (v[A] & v[C]) ^ (v[B] & v[C]);
		for (int i = H; i > A; i--) {
			v[i] = v[i - 1];
		}
		v[E] += t1;
		v[A] = t1 + big_sigma0 + majority;
	}
	for (int i = A; i <= H; i++) {
		state[i] += v[i];
	}
	// SHA-256 hashes the OBS password: `w` holds the message and `v` gives the digest.
	wipe(w, sizeof w);
	wipe(v, sizeof v);
}

void crypto_sha256_init(crypto_sha256_t *sha) {
	sha->hash = (crypto_hash_t){
		.state = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
			  0x1f83d9ab, 0x5be0cd19},
	};
}

void crypto_sha256_update(crypto_sha256_t *sha, const void *data, size_t len) {
	hash_update(&sha->hash, sha256_compress, data, len);
}

void crypto_sha256_final(crypto_sha256_t *sha, uint8_t digest[CRYPTO_SHA256_LEN]) {
	hash_final(&sha->hash, sha256_compress, digest, CRYPTO_SHA256_LEN);
}

void crypto_base64_encode(const uint8_t *bytes, size_t len, char *text) {
	static const char ALPHABET[] =
		"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
	for (size_t at = 0; at < len; at += 3) {
		size_t left = len - at;
		uint32_t group = (uint32_t)bytes[at] << 16;
		if (left > 1) {
			group |= (uint32_t)bytes[at + 1] << 8;
		}
		if (left > 2) {
			group |= bytes[at + 2];
		}
		*text++ = ALPHABET[group >> 18];
		*text++ = ALPHABET[(group >> 12) & 63];
		*text++ = left > 1 ? ALPHABET[(group >> 6) & 63] : '=';
		*text++ = left > 2 ? ALPHABET[group & 63] : '=';
	}
	*text = '\0';
}
