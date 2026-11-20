// SPDX-License-Identifier: MIT
// The credential store seam (spec 8.2, 10; D8; R1): the OBS password and the Wi-Fi passphrase in
// their own partition, `cred`, apart from the config slots of store.h. The port puts plain NVS
// behind it (`nvs_flash_init_partition("cred")`). Pure C, no SDK headers.
//
// Secrets go in through put only, from SET_CREDENTIAL. get is for the port's Wi-Fi join and the
// OBS log-in, never for a frame, a log line or the display. Wipe a get buffer after use.
#pragma once

#include "link.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// An implementation embeds cred_t as its first member and casts the pointer back.
typedef struct cred cred_t;
struct cred {
	// Stores `len` bytes (1..LINK_CREDENTIAL_MAX) as the secret of `kind`, over any value it held.
	// The caller has checked kind and bytes (spec 8.2). False when the write failed; the stored
	// value is then as it was.
	bool (*put)(cred_t *cred, enum link_credential_kind kind, const uint8_t *bytes, size_t len);
	// True when a secret of `kind` is stored (INFO `obs_password_set`, `wifi_psk_set`).
	bool (*is_set)(cred_t *cred, enum link_credential_kind kind);
	// Copies the secret of `kind` into `out` and returns its length; 0 when none is stored or it
	// does not fit in `cap`.
	size_t (*get)(cred_t *cred, enum link_credential_kind kind, uint8_t *out, size_t cap);
	// Erases the whole partition: both secrets and every stale copy a key overwrite left behind
	// (CLEAR_CREDENTIALS, FACTORY_RESET, BOOTLOADER, the clear key combination). False when the
	// erase failed.
	bool (*erase_all)(cred_t *cred);
};
