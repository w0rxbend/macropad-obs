# 16. Security: a device that holds OBS credentials

Research only, 2026-11-18. This file is the only file written. No hardware was used. Confidence
tags: **verified** (read today in a primary source or on this machine), **likely** (reasoned from a
verified fact), **unverified**. Keys such as `[R1]` point into the Sources list. No mechanical size
appears here, so nothing needs a MEASURE tag.

## Recommendation

Let the pad store the OBS password, write-only, and amend the repo rule to say so. Treat the pad as
a device that anyone holding it can read. Make that cheap to accept: use the long random password
OBS generates, reach OBS only over the USB link, and never let a secret leave the pad again.

Next action: the owner picks between the two rule texts in "The rule". Text 1 (store the password)
matches the owner's words "firmware on the device should be communicating with this websocket OBS
url". Text 2 keeps today's rule and needs the app running at every OBS start (reports 05 and 13).

Six findings carry the recommendation.

1. **A salt-bound secret does not survive an OBS restart.** OBS makes a new salt on every server
   start, so a stored `base64(sha256(password + salt))` dies with it. Only the password, or auth
   off, lets the pad log in alone after OBS restarts. (verified in report 05, `[O1]`)
2. **No candidate MCU keeps a flash secret from a person who holds the pad, by default.** RP2040
   and RP2350 run from plain external QSPI flash, and the UF2 boot drive is in ROM. RP2350 can lock
   this down with secure boot, OTP keys and debug disable, but the procedure is "irreversible", and
   a signing key then gates every firmware update. (verified for RP2350, `[R1]`; likely for RP2040)
3. **Even locked-down RP2350 falls to a lab.** The 2025 hacking challenge read the OTP secret with
   supply glitching (E16, E21), laser faults (E24) and a FIB. A3 and A4 steppings mitigate these.
   (verified, `[R2]` `[R1]` appendix C)
4. **OBS generates a 16-character random alphanumeric password on first load.** About 95 bits.
   Offline guessing from a sniffed handshake or a stolen hash is then out of reach. A human-chosen
   password is not. (verified, `[O2]`)
5. **Any process of the logged-in user can open the pad.** The udev rule uses `TAG+="uaccess"`,
   which grants the seat's active user an ACL on the node. The same process can also read the
   desktop keyring. A config write is not a privilege boundary beyond the user session. (verified,
   `[L1]` `[L2]`)
6. **The app can store nothing.** If the pad lists scenes and inputs for the mapping editor, the app
   takes the password once, writes it to the pad, and forgets it. If the app keeps its own OBS
   session, use the keyring: `keyring` 4.2.0 defaults to Secret Service over zbus on Linux, and this
   machine has KWallet's Secret Service shim. (verified, `[K1]` `[L3]`)

## Threat model

Assets, highest first: the OBS password (controls OBS: start a stream, change scenes, set source
settings); a Wi-Fi passphrase, only if a radio is fitted; the pad's mapping (low value).

| Threat (STRIDE) | Path | Control |
|---|---|---|
| Information disclosure: flash read-out | BOOTSEL drive, SWD, desoldered flash | Accept. Random OBS password. Option: RP2350 lock-down later |
| Information disclosure: frame sniffing | Another process reads the CDC node | The password goes app to pad only, once. Never pad to app |
| Information disclosure: handshake sniffing | Plain `ws://` on a shared LAN | Use the USB link, not Wi-Fi or LAN. Random password |
| Spoofing: redirect | A config write points the pad at a hostile server | The pad sends only `sha256(secret + challenge)`. With a random password the server learns nothing useful |
| Tampering: hostile firmware | A UF2 that reads flash and exfiltrates the password | Wipe credentials before a host-requested BOOTSEL. Physical BOOTSEL stays open (accepted) |
| Elevation: OBS reachable by the LAN | obs-websocket binds `[::]:4455` | Firewall: allow 4455 only on the pad's USB interface |
| Disclosure: logs and screens | Debug print, display, readback | No secret is ever printed, drawn, echoed or read back |

## What the pad stores, and how

**Password, not a derived secret.** The derived secret is password-equivalent until OBS restarts,
then useless (finding 1). It buys no protection on the pad and costs a tray daemon. If the owner
keeps the app running anyway, store nothing on the pad and use Text 2.

**Where.** A credential record in its own flash sector, apart from the mapping document. Reasons:
the mapping can be read back in full, and an erase of the credential cannot touch the mapping.
Readback returns only `obs_password_set: true|false`. No hash, no length, no fingerprint.

**Flash read-out by MCU.**

| MCU | Read-out by holder | Lock-down available | Cost of lock-down |
|---|---|---|---|
| RP2040 | Yes: BOOTSEL loads any UF2, SWD open, QSPI flash plain | None known to this report | n/a (likely, not re-read) |
| RP2350 | Yes by default | Secure boot (secp256k1 signed images), keys in OTP, page locks per Secure, Non-secure and bootloader, `CRIT1.DEBUG_DISABLE`, glitch detector, encrypted boot into SRAM | Irreversible OTP writes; every update must be signed; E21 mitigation turns off USB BOOTSEL (`DISABLE_BOOTSEL_USB_PICOBOOT_IFC`, `_MSD_IFC`) |
| ESP32-S3 | Yes by default | Flash encryption plus Secure Boot v2. NVS is not covered by flash encryption; it needs NVS encryption | eFuse burns; release mode cannot be undone |

(RP2350 verified `[R1]` sections 10.1, 10.5, 10.8, 10.9; ESP32-S3 verified `[E1]`.)

Encrypted boot on RP2350 decrypts the code image into SRAM. It does not cover a data sector the
firmware writes at run time. To protect the stored password the firmware must encrypt it itself,
with a key in an OTP page that is hard-locked against the bootloader and Non-secure code. That only
helps with secure boot on, or an attacker's own UF2 reads the key. The SDK ships
`pico_encrypt_binary` in 2.3.0. (verified, `[R1]` 10.1.2, `[L4]`)

Verdict: do not plan secure boot for the printed prototype. Keep the option open for a CNC unit by
choosing RP2350 A4 or later, and by keeping the credential format ready for an AES-wrapped blob.
(likely)

## The USB configuration channel

1. **Who may write.** Anyone with the seat ACL (finding 5). `ttyACM*` otherwise gets group `uucp`
   (report 13). Keep `uaccess`. Do not add `MODE="0666"`.
2. **Credential write is one message, app to pad, write-only.** The pad acks with a status byte. No
   frame from the pad carries it. Test vectors use a fixed sample password only.
3. **Clear.** A `CLEAR_CREDENTIALS` message, and a long-press combination on the pad itself, both
   erase the credential sector.
4. **Firmware update.** A host request to enter BOOTSEL first erases the credential sector, then
   reboots. The app warns that the password must be entered again. The physical BOOTSEL button
   cannot be guarded; that is the accepted physical-access risk. Do not ship the Pico SDK USB reset
   interface that lets `picotool` reboot the pad to BOOTSEL without that wipe. (likely)
5. **Optional, not in the first cut:** require a key press on the pad to accept a change of URL or
   password. It stops a silent redirect by a user-level process. That process can already read the
   keyring, so the gain is small. (likely)

## Network

1. **Plain `ws://` is the only transport.** obs-websocket has no TLS server (report 05). Auth is
   challenge-response, so the password itself never crosses the wire. Everything after auth is
   readable and injectable by anyone on the path. (verified, `[O1]`)
2. **Over the USB link the path is one cable.** The NCM link is point to point between the pad and
   the PC (report 03). This is the strongest reason to prefer it over Wi-Fi. (likely)
3. **OBS is exposed beyond loopback.** It binds every interface and does not filter clients. The
   firewall rule the design needs anyway (report 03) should name the USB interface and the port,
   not open 4455 to the LAN. The interface name varies per pad (`enx` plus MAC), so the app should
   show the exact command. (verified bind, `[O1]`; interface naming unverified)
4. **The old host check does not carry over.** `host/src/config.rs` refuses non-loopback `ws://`.
   The pad is never loopback, so replace that check with: accept `ws://` only to a private,
   link-local or USB-link address; refuse `wss://` (OBS has none); refuse userinfo, path and query.
   (verified, `host/src/config.rs:207-220`)
5. **OBS connect strings** have the form `obsws://<ip>:<port>/<password>`. The app must split that
   string and never store or frame it whole. (verified in report 05, `[O1]`)

## Wi-Fi, if a radio is fitted

The passphrase is a second credential with the same rules: write-only, own sector, cleared with
the OBS password, never read back. On ESP32-S3, NVS encryption with an HMAC eFuse key protects it
without full flash encryption (report 04 `[E8]`). It also puts the plain `ws://` session on a
shared medium, which is the main reason this report prefers the cable. (likely)

## Logs and displays

1. Firmware: no `printf` of any config field typed secret. The UI layer has no API that takes the
   credential record. The display shows "password: set" or "not set".
2. App: keep the `Secret` newtype (`Debug` and `Display` print `***`) and the log redaction in
   `app/src-tauri/src/logbuf.rs`. The password field in the UI is write-only and is cleared after
   the write. (verified in files)
3. Tests: keep the existing "encoded bytes do not contain the password" tests, and add one that a
   full readback document never contains it. (verified that the first kind exists,
   `firmware/test/test_link.c:73`, `host/src/protocol.rs:295`)

## How the app stores secrets

| Option | At rest | Fits when |
|---|---|---|
| Store nothing (recommended with Text 1) | Nowhere. Entered, written to pad, dropped | The pad lists scenes and inputs for the editor |
| Desktop keyring via `keyring` 4.2.0 | Secret Service collection, encrypted by the wallet | The app keeps its own OBS session, or Text 2 |
| `0600` file (current) | Plain text in `$XDG_CONFIG_HOME` | Never as a silent fallback. Only by explicit choice |

If the keyring is not reachable, fail with a message. Do not fall back to the file quietly.
`keyring` default feature `v1` pulls `zbus-secret-service-keyring-store` on Linux. (verified,
`[K1]`) KWallet's `org.kde.secretservicecompat` is activatable on this machine; whether its
collection is unlocked at login was not checked. (verified present, `[L3]`)

## The rule

Today: "No OBS password in a CDC frame." Reports 05 and 13 keep it with a salt-bound secret. That
secret is password-equivalent, so the rule already has a carve-out in spirit. Pick one text.

**Text 1, the device logs in by itself (recommended):**

> The OBS password and any Wi-Fi passphrase cross the CDC link only in `SET_CREDENTIAL`, app to
> device. No device-to-host frame, log line, display, readback or test vector carries a secret or a
> value derived from one. The device stores secrets in their own flash sector and erases it on
> `CLEAR_CREDENTIALS`, on the clear key combination, and before a host-requested BOOTSEL.

**Text 2, keep the app in the loop:**

> No OBS password in a CDC frame. The only secret on the link is the salt-bound
> `base64(sha256(password + salt))`, app to device, in `AUTH_SECRET`. The device holds it in RAM
> only. No device-to-host frame, log line or display carries it.

Either text adds new messages, so the four-file protocol rule applies: `firmware/link.c`,
`host/src/protocol.rs`, `firmware/test/vectors.txt`, `docs/protocol.md` together.

## Options compared

| Option | Pad works after OBS restart, app closed | Secret on pad | Risk |
|---|---|---|---|
| A. Password on pad, write-only (Text 1) | Yes | Password, flash | Read-out by holder. Small with a random password and USB-only reach |
| B. Salt-bound secret from app (Text 2) | No, app must run | Derived, RAM | Tray daemon needed; same power as the password while it lives |
| C. OBS auth off | Yes | None | Anything that reaches 4455 controls OBS. OBS advises against it |
| D. A plus RP2350 secure boot and OTP-wrapped key | Yes | Encrypted blob | Irreversible; signed updates; lab attacks remain (E16 to E24) |

## Not checked

1. No hardware. No secure boot was enabled; no OTP was written.
2. RP2040 datasheet not re-read today; its row rests on report 04 and general knowledge.
3. Keyring behaviour under KWallet at login, and in a Flatpak or AppImage build.
4. Chromium Web Serial can also open the CDC node after a user prompt. Not tested. (unverified)

## Sources

- `[R1]` RP2350 datasheet RP-008373-DS-3, sections 10.1, 10.1.2, 10.5, 10.8, 10.9, appendix C.2 and
  C.3, `BOOT_FLAGS0`:
  <https://pip-assets.raspberrypi.com/categories/1214-rp2350/documents/RP-008373-DS-3-rp2350-datasheet.pdf>
  (verified, read in full text today)
- `[R2]` Raspberry Pi, "Security through transparency: RP2350 Hacking Challenge results are in":
  <https://www.raspberrypi.com/news/security-through-transparency-rp2350-hacking-challenge-results-are-in/>
  (verified)
- `[E1]` ESP-IDF, ESP32-S3 flash encryption:
  <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/security/flash-encryption.html>
  (verified)
- `[O1]` obs-websocket 5.7.6 source and protocol, as read in reports 03 and 05:
  <https://github.com/obsproject/obs-websocket/tree/5.7.6> (verified there)
- `[O2]` obs-websocket 5.7.6 `src/Config.cpp:79-86` (FirstLoad generates a password),
  `src/utils/Crypto.cpp:74-85`, `src/utils/Crypto.h:30` (length 16):
  <https://github.com/obsproject/obs-websocket/blob/5.7.6/src/Config.cpp> (verified)
- `[K1]` `keyring` 4.2.0 features from <https://crates.io/api/v1/crates/keyring> and
  <https://docs.rs/keyring/latest/keyring/> (verified)
- `[L1]` `app/udev/70-macropad-obs.rules` (verified)
- `[L2]` `/usr/lib/udev/rules.d/73-seat-late.rules:16` on this machine, the `uaccess` builtin
  (verified)
- `[L3]` `busctl --user list` on this machine: `org.kde.kwalletd6`, `org.kde.secretservicecompat`
  activatable (verified)
- `[L4]` Pico SDK 2.3.0, `tools/CMakeLists.txt:496-527`, `pico_encrypt_binary`, under
  `~/.platformio/packages/framework-arduinopico/pico-sdk` (verified)
- Repo: `host/src/config.rs`, `app/src-tauri/src/logbuf.rs`, `firmware/test/test_link.c`,
  `host/src/protocol.rs`, reports 03, 04, 05, 13 (verified in files)

## Open questions

1. Text 1 or Text 2? That is: may the pad hold the OBS password so it works with the app closed?
2. Does the pad or the app list scenes and inputs for the mapping editor? If the pad, the app
   stores no secret at all.
3. Is the OBS password the one OBS generated, or a human one? A human one makes handshake sniffing
   and a hostile redirect an offline-guessing risk.
4. Is a radio ever fitted? If yes, Wi-Fi brings a second secret and a shared medium for `ws://`.
5. Is secure boot wanted on the CNC unit, with the owner holding a signing key for every update?
6. Should a change of URL or password need a key press on the pad?
