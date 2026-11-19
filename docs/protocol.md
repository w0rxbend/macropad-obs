# CDC frames

Version 2 (spec 8.1, `docs/spec/spec-v2.md`). Transport is USB CDC ACM, VID `0x1209`, PID `0x4F42`. Baud is ignored. Byte order is little-endian. The app asks, the pad answers.

```text
0        SOF          0xA5
1        version      0x02
2        type         u8
3        id           u8, set by the sender of a request, echoed in the reply
4..5     length       u16, payload bytes, 0..240
6..      payload      length bytes
end-2    crc          CRC-16/MODBUS, low byte first
```

The largest frame is 6 + 240 + 2 = 248 bytes.

CRC-16/MODBUS: reflected poly `0xA001`, init `0xFFFF`, xorout `0x0000`, over version through the end of the payload. Not over SOF. ASCII `123456789` → `0x4B37`.

Type `0x7F`, id `0x09`, payload `01 02 03`, CRC `0x2D1B` (`payload_3` in `firmware/test/vectors.txt`):

```text
a5 02 7f 09 03 00 01 02 03 1b 2d
```

## Types

Pad-to-app types have bit 7 set. The frame codec sends `NOTICE` and `RESULT` by itself. `WIFI_SCAN` is [later] in spec 8.2 and has no type yet.

| Type | Name | Direction | Payload |
|---|---|---|---|
| `0x01` | INFO_GET | app to pad | empty |
| `0x02` | CFG_READ | app to pad | `u16 offset`, `u8 len` |
| `0x03` | CFG_BEGIN | app to pad | `u32 base_seq`, `u16 total`, `u32 crc32`, `u8 flags` |
| `0x04` | CFG_CHUNK | app to pad | `u16 offset`, then 1..238 document bytes |
| `0x05` | CFG_COMMIT | app to pad | empty |
| `0x06` | SET_CREDENTIAL | app to pad | `u8 kind`, then the secret (1..239 bytes). See Credentials |
| `0x07` | CLEAR_CREDENTIALS | app to pad | empty |
| `0x08` | OBS_LIST | app to pad | `u8 list`, `u16 index` |
| `0x09` | FACTORY_RESET | app to pad | `u32 magic` `0x45504957`: ASCII `WIPE` on the wire |
| `0x0A` | BOOTLOADER | app to pad | `u32 magic` `0x544F4F42`: ASCII `BOOT` on the wire |
| `0x80` | NOTICE | pad to app | printable ASCII text, the whole payload |
| `0x81` | RESULT | pad to app | `u8 code`, `u32 seq`, then the path of the first bad field (0..48 bytes) |
| `0x82` | INFO | pad to app | 34 fixed bytes, then the firmware version (0..32 bytes). See below |
| `0x83` | CFG_DATA | pad to app | `u32 seq`, `u16 total`, `u16 offset`, then 0..232 document bytes |
| `0x84` | CRED_STATUS | pad to app | `u8 status`, nothing else |
| `0x85` | STATUS | pad to app | `u8 obs_state`, `u8 wifi_state`, `i8 rssi_dbm`, 4 IPv4 bytes |
| `0x86` | OBS_ITEM | pad to app | `u8 list`, `u16 index`, `u16 total`, 16 UUID bytes, then the name (0..219 bytes) |
| `0x87` | INPUT | pad to app | `u8 source`, `u8 index`, `i8 value` |

`RESULT` codes (spec 8.2): 0 `ok`, 1 `busy`, 2 `stale_seq`, 3 `bad_crc`, 4 `too_big`, 5 `invalid`. A `RESULT` from the codec has `seq` 0 and no path: it stored nothing.

The frame codec does not judge the type and does not read the payload. Every frame with a good CRC goes to the caller.

## Messages

The fields are those of spec 8.2 and of the message table in `docs/research/13-app-and-config.md` ("Protocol v2 sketch"). The type numbers, the field widths of `INFO` and the reserved-bit rule are set here (task 1.7): no earlier document fixes them. The same holds for the types from `0x06` and from `0x84` (task 1.8): spec 8.2 names their fields, and this page sets the numbers, widths, state codes and magic values. They are proposals until the owner reviews this page (checkpoint 1).

A second layer reads the payload. C: `link_msg_decode` and `link_msg_encode` in `firmware/core/link.h`. Rust: `Message::decode` and `Message::encode` in `host/obs_core/src/protocol.rs`. Both hold the same rules, and both encoders refuse what the decoders refuse.

The decoder refuses an unknown type, a payload of the wrong length, and each case in the table. This layer does not pick the reply to a refused message. That is the job of the handler that calls it (tasks 2.x), and spec 8.1 still holds there: no frame is dropped without a reply.

| Message | Rule | Refused |
|---|---|---|
| INFO_GET, CFG_COMMIT | no payload | any payload byte |
| CFG_READ | exactly 3 bytes. `len` is 1..232, the most one `CFG_DATA` holds (240 - 8) | `len` 0, `len` 233 or more |
| CFG_BEGIN | exactly 11 bytes. `flags` bit 0 = try only: RAM, 30 s, nothing stored (spec 8.2). Bits 1..7 are 0 | a reserved flag bit |
| CFG_CHUNK | 1..238 document bytes after the offset (240 - 2). Idempotent by offset | no document byte |
| CFG_DATA | 8 fixed bytes. Zero document bytes is legal: no document, or an offset at the end | fewer than 8 bytes |
| RESULT | 5 fixed bytes. `seq` is the stored `seq` after the request: the new one after a commit. The path is printable ASCII (`0x20`-`0x7E`), at most 48 bytes (R13) | a code above 5, a longer path, a byte outside the set |
| INFO | see below | a reserved flag bit, a version above 32 bytes or with a byte outside `0x20`-`0x7E` |
| SET_CREDENTIAL, CLEAR_CREDENTIALS | see Credentials | every frame whose status is not `ok` |
| CRED_STATUS | exactly 1 byte | a status above 4 |
| OBS_LIST | exactly 3 bytes. `list` is 1 scenes, 2 inputs, 3 transitions | `list` 0, `list` 4 or more |
| OBS_ITEM | 21 fixed bytes, then the name. Same `list` values | fewer than 21 bytes, a `list` outside 1..3 |
| STATUS | exactly 7 bytes. Both states are 0..4 | a state above 4 |
| INPUT | exactly 3 bytes. `source` is 1..4. `value` is 0 or 1, and for a turn it is not 0 | any other `source` or `value` |
| FACTORY_RESET, BOOTLOADER | exactly 4 bytes: the magic of that type | any other value, the other type's magic |

The codec does not check `total` against the 16 KiB cap, or an offset against `total`. The config handler does, and answers `RESULT too_big` or `invalid`.

### INFO

```text
0        proto            u8, 2
1        flags            bit 0 obs_password_set, bit 1 wifi_psk_set, bits 2..7 are 0
2..3     schema_min       u16
4..5     schema_max       u16
6..7     max_doc_bytes    u16, 16384 (spec 8.2: cap 16 KiB)
8        keys             u8
9        buttons          u8
10       knobs            u8
11..14   main display     u16 width, u16 height
15..18   strip display    u16 width, u16 height
19..22   capabilities     u32, no bit is defined yet
23       board_rev        u8
24..27   git hash         first 4 bytes of the commit hash
28..33   unique id        6 bytes
34..     fw version       printable ASCII, 0..32 bytes, the rest of the payload
```

`INFO` says two things about the credentials: `obs_password_set` and `wifi_psk_set`, one bit each. It carries no credential value, length or hash (R1). Both test suites flip each field and count the changed payload bits: one.

### Credentials

Spec 8.2 sets the rules, the sources of the Wi-Fi limits and the status codes. `SET_CREDENTIAL` is the only frame that carries a secret, and it goes app to pad (R1).

```text
0        kind             u8: 1 OBS password, 2 Wi-Fi passphrase
1..      secret           the rest of the payload
```

| Kind | Secret |
|---|---|
| 1 OBS password | 1..239 opaque bytes. 239 = the 240-byte payload cap less the kind byte |
| 2 Wi-Fi passphrase | 8..63 bytes, each `0x20`-`0x7E`, or exactly 64 hex digits (the raw PSK) |

The reply to `SET_CREDENTIAL` and to `CLEAR_CREDENTIALS` is `CRED_STATUS`: one status byte and nothing else.

| Status | Name | Case |
|---|---|---|
| 0 | `ok` | stored, or both erased |
| 1 | `bad_kind` | a kind other than 1 or 2 |
| 2 | `bad_len` | no payload, no byte after the kind, a kind 2 length outside 8..64, any payload byte in `CLEAR_CREDENTIALS` |
| 3 | `bad_value` | a kind 2 byte outside the allowed set |
| 4 | `store_fail` | the NVS write or the erase failed |

The checks run in this order: no payload (`bad_len`), kind (`bad_kind`), no secret byte (`bad_len`), then the kind 2 length and bytes. So kind 3 with no byte after it is `bad_kind`. The order is set here: spec 8.2 lists the cases and no order.

C: `link_credential_check`. Rust: `credential_status`. Both give the status for a frame before the pad stores or erases anything, and a refused write leaves the stored value as it was. They never give `store_fail`: only the store knows that. The typed decoder takes a credential frame only when the status is `ok`.

An OBS password of 240 bytes needs a 241-byte payload. It cannot be framed, and the frame codec answers the header with `RESULT` `too_big` (spec 8.1).

`CLEAR_CREDENTIALS` erases both secrets. There is no mask and no one-credential clear (spec 8.2).

In Rust the secret sits in `Secret`, and its `Debug` output prints no byte of it.

### FACTORY_RESET and BOOTLOADER

Each carries a 32-bit magic, so one flipped bit cannot erase the pad (`docs/research/13-app-and-config.md`, message table). The decoder refuses every other value. Both suites flip each of the 32 bits and see a refusal. The two magic values differ, so one type with the other's magic is refused too. What the pad erases, and in what order, is in spec 8.2.

### STATUS

Sent by the pad on a change, with id 0. No secret, no length of one and no hash (spec 8.2).

```text
0        obs_state        u8: 0 idle, 1 connecting, 2 refused, 3 auth_failed, 4 up
1        wifi_state       u8: 0 no_ssid, 1 connecting, 2 bad_key, 3 no_ap, 4 up
2        rssi_dbm         i8, 0 unless Wi-Fi is up
3..6     ip               IPv4, network order, 0.0.0.0 unless Wi-Fi is up
```

The Wi-Fi states are those of spec 8.2. The OBS states follow the reasons the status widget shows in `docs/research/14-display-ui.md` ("OBS refused", "Wrong password", "Connecting"); `idle` means the pad is not trying: no Wi-Fi or no URL. The codec checks the two state ranges. It does not check that RSSI and IP are 0 while Wi-Fi is down.

### OBS_LIST and OBS_ITEM

The app reads the pad's own scene, input and transition lists one item at a time: `OBS_LIST(list, index)` gets one `OBS_ITEM` with the same `list` and `index`. `total` is the item count of the list. The app starts at index 0 and stops at `total`.

```text
0        list             u8: 1 scenes, 2 inputs, 3 transitions
1..2     index            u16
3..4     total            u16
5..20    uuid             16 bytes, the OBS UUID in the order of its text form
21..     name             UTF-8 from OBS, 0..219 bytes, the rest of the payload
```

With `total` 0, or an index at or past `total`, the UUID is all zero and there is no name. The codec does not check the name's UTF-8 and does not check `index` against `total`. Cutting a name above 219 bytes is the job of the handler (tasks 2.x).

### INPUT

One event of a control, for "press to select" in the app (spec 8.2).

```text
0        source           u8: 1 key, 2 button, 3 knob push, 4 knob turn
1        index            u8, 0-based within its source
2        value            i8: 1 down, 0 up. For a turn: detents, + clockwise, never 0
```

The codec does not check `index` against the counts in `INFO`.

### Config flow

Spec 8.2: `INFO` -> `CFG_READ` until `total` -> edit -> `CFG_BEGIN(base_seq)` -> `CFG_CHUNK`... -> `CFG_COMMIT` -> `RESULT`. `crc32` in `CFG_BEGIN` is the CRC-32 of the whole document (ASCII `123456789` -> `0xCBF43926`). One reply per id.

## Refused frames

No frame is dropped without a reply. The parser scans for `0xA5` and skips bytes that are not SOF. It then refuses a frame in this order:

| Case | Reply | Reply id |
|---|---|---|
| version is not `0x02` (a v1 frame) | `NOTICE` with the text `protocol v2 only` | 0, v1 has no id |
| length above 240 | `RESULT` `too_big` | id of the refused header |
| bad CRC | `RESULT` `bad_crc` | id of the refused header |

A v1 frame is not parsed past its version byte. A bad CRC is known only when `length + 8` bytes are in the buffer.

After each refusal the parser drops the SOF byte only and scans on. So a frame that follows a cut frame is still found: the cut frame gets `bad_crc`, and the next frame is delivered. The bytes of a refused frame are scanned too. If they hold `0xA5`, one refused frame can give more than one reply.

## Pull API

The receiver pushes bytes and pulls frames. C: `link_rx_push` and `link_pull` in `firmware/core/link.h`. Rust: `LinkRx::push` and `LinkRx::pull` in `host/obs_core/src/protocol.rs`.

1. Push the bytes read from USB. In C the buffer is one largest frame (248 bytes). `link_rx_push` returns how many bytes it took and never overwrites a buffered byte.
2. Pull until the parser is empty. Each pull gives one frame, or one reply to send.
3. Push the rest of the read.

A full buffer always gives a frame or a reply, so the loop cannot stall. The pull caller sets the pace. Nothing is lost when a 248-byte frame has traffic behind it, or when a burst holds more frames than one call can take. Both were v1 defects (`docs/research/02-repo-inventory.md`, verified there).

## Vectors

`firmware/test/vectors.txt` is shared by `firmware/test/test_link.c` and the Rust tests. A `refuse_<x>` line is refused with the frame on the `reply_<x>` line. Every other line is a good frame: it decodes, and encoding it again gives the same bytes. Both test suites feed every line alone, then all lines as one stream at each of the 64 offsets of a 64-byte read, then one byte at a time.

A `msg_<x>` line is a typed message. Both suites decode it into the same named fields and encode the fields back to the same bytes. A `bad_<x>` line is a good frame that the typed decoder refuses in both languages. Every type in the table above has a `msg_` or a `cred_ok_` line.

A `cred_<status>_<x>` line is a `SET_CREDENTIAL` or `CLEAR_CREDENTIALS` frame, and `<status>` is the status both languages must give it: `ok`, `bad_kind`, `bad_len` or `bad_value`. There is one line per rule of spec 8.2. The typed decoder takes the `ok` lines and refuses the rest.

No vector carries a real credential. The `cred_` lines hold dummy strings such as `dummy-obs-password`.

## No credential comes back (R1)

No pad-to-app type has a field made from a credential: not its value, not its length, not its hash. Both suites check this at the codec:

1. The pad-to-app types are a closed list: `RESULT`, `INFO`, `CFG_DATA`, `CRED_STATUS`, `STATUS`, `OBS_ITEM`, `INPUT`. Any other type with bit 7 set is refused. `NOTICE` is the frame codec's own fixed text.
2. Each listed type has its fixed bytes and at most one named byte run after them. One byte less is refused. One byte more is refused where no run is named.
3. `CRED_STATUS` is the same single byte for an accepted secret of 8, 63, 64 and 239 bytes.
4. `INFO` says "set" or "not set" with one bit per credential.

Two fields look like a hash or an opaque run and are the checked exceptions. The `INFO` git hash is the four bytes the caller gives, whatever the two credential bits say. The `CFG_DATA` bytes are the caller's document bytes and nothing else: that message has no credential input.

This is a codec check. It cannot see what a handler puts into a field. The handler tasks (2.x) and the `cred` dump check of spec 11 cover that.
