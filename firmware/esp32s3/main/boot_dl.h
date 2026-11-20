// SPDX-License-Identifier: MIT
// BOOTLOADER: the pad leaves the app for ROM download mode over USB (spec 8.2, R18 section 8).
#pragma once

#include "cred.h"

#include <stdbool.h>

// Erases `cred`, then detaches, hands the USB PHY to the USB-Serial/JTAG, sets the force-download
// bit and restarts. Send the BOOTLOADER reply first. Returns false, with nothing else done, when
// the erase failed: no download mode with a secret still in flash (CLAUDE.md, R1). Does not
// return otherwise; it aborts if the detach fails, since the PHY would be in no known state.
bool boot_dl_enter(cred_t *cred);
