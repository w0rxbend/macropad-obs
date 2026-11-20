# Config document

Schema 1 (spec 8.2, `docs/spec/spec-v2.md`). One document describes the whole pad. It lives on the pad. The app reads it with `CFG_READ`, edits it and writes it back with `CFG_BEGIN`, `CFG_CHUNK` and `CFG_COMMIT` (`docs/protocol.md`).

Four files hold this contract and change together (R3): `firmware/core/config.c`, `host/obs_core/src/document.rs`, `firmware/test/config_vectors/` and this file. Both validators run the same rules in the same order and give the same verdict and path for every vector.

The document carries no secret. The OBS password and the Wi-Fi passphrase go only in `SET_CREDENTIAL` (R1).

## Form

Compact UTF-8 JSON, one object, at most 16384 bytes (16 KiB, spec 8.2). A longer document gets `RESULT too_big`. Bytes that are not one JSON object get `RESULT invalid` with an empty path. So does a number too large for a double, such as `1e400`, wherever it sits. A member name that appears twice in one object: the last one counts, and nothing of the first is kept.

```json
{"schema":1,"seq":17,
 "obs":{"url":"ws://192.168.1.20:4455","auth_mode":"stored"},
 "wifi":{"ssid":"studio"},
 "keys":[{"do":"scene","uuid":"0b0e6b1c-7f0a-4a55-9a43-1f2d3c4b5a69","label":"Cam"}],
 "buttons":[{"do":"toggle_record"}],
 "knobs":[{"input":{"uuid":"6d1f0c52-93a7-4a0e-8f0b-52c1e7a9d340","label":"Mic"},"step_db":1,"push":{"do":"toggle_mute"}}],
 "main_display":{"widgets":[{"kind":"text","x":0,"y":0,"w":320,"h":40,"text":"Test 1"}]},
 "strip_display":{"widgets":[{"kind":"strip","x":0,"y":0,"w":142,"h":140,"knob":0,"parts":["name","db","fader"]}]},
 "ui":{"brightness":80}}
```

The example is cut short: `keys` holds 9 actions, `buttons` 4 and `knobs` 3.

## Layout names

Spec 8.2, R13 and R14 name the display part three ways (`docs/research/gap-3.md`, "Inconsistencies", item 1). This file fixes one set:

| Name | Panel | Pixels |
|---|---|---|
| `main_display` | big panel, ST7796U | 320 x 480 |
| `strip_display` | strip panel, NV3007 | 142 x 428 |

Each is an object with one list, `widgets`. The names are those of spec 8.2 and of criteria 4b and 13. The sizes are those of criterion 4b. R14's `display.big` and `display.bar` and R13's `layout` string are not used: a document describes widgets, not a named layout. A preset is an app feature that fills `widgets`; the pad never sees its name.

## Fields

An integer is a JSON number with no fraction and no exponent. A length is in UTF-8 bytes. Every field in this table is required.

| Path | Rule | Source |
|---|---|---|
| `schema` | integer; see "Schema rule" | spec 8.2 |
| `seq` | integer 0..4294967295 (`u32 base_seq` of `CFG_BEGIN`) | `docs/protocol.md` |
| `obs.url` | see "URL rule" | spec 8.2 |
| `obs.auth_mode` | `stored` or `none` | spec 8.2 |
| `wifi.ssid` | string, 0..32 bytes; empty means no SSID | IEEE Std 802.11-2016 9.4.2.2, SSID element 0..32 octets (cited, not re-read here) |
| `keys` | list of exactly 9 actions | R13 `INFO` counts |
| `buttons` | list of exactly 4 actions | R13 `INFO` counts |
| `knobs` | list of exactly 3 knobs | R13 `INFO` counts |
| `main_display.widgets`, `strip_display.widgets` | see "Widgets" | R14 |
| `ui.brightness` | integer 0..100, percent | R13, R14 |

An OBS reference is `uuid` plus `label` (spec 8.2). `uuid` is 1..36 bytes, each `0x21`-`0x7E`: 36 is the length of a UUID in text form, and criterion 4c writes the short test value `U_B`. `label` is a string of 0..48 bytes (R13, "48-byte labels"); the display shows it while OBS is away.

An action is an object with `do`:

| `do` | Also needs | Request (criterion 4c, R13 item 3) |
|---|---|---|
| `none` | nothing | none |
| `scene` | `uuid`, `label` | set the program scene |
| `toggle_mute` | `uuid`, `label`; neither as a knob's `push` | `ToggleInputMute` |
| `toggle_record` | nothing | `ToggleRecord` |
| `toggle_stream` | nothing | `ToggleStream` |
| `transition` | nothing | run the current transition |

The action names follow criterion 4c (`toggle_record`, `toggle_mute`), not R13 (`record_toggle`). R13's `source_visibility`, `hotkey` and `page` are not in schema 1: paging is later (spec 9), and no task draws or sends the other two.

A knob is an object:

- `input`: an OBS reference, or `null` for a knob with no input.
- `step_db`: a number above 0 and at most 6, in dB per detent. R13 shows `1.0`, criterion 4c uses 2. The bound of 6 is set here (design choice); no earlier document gives one.
- `push`: an action. `toggle_mute` here acts on the knob's own `input` and carries no `uuid` (criterion 4c).

## Widgets

A display holds at most 16 widgets (R14). A widget is an object with `kind`, `x`, `y`, `w`, `h` and the fields of its kind. `x`, `y`, `w`, `h` are integers in pixels, origin top left.

| `kind` | Fields | Shows (R14) |
|---|---|---|
| `status` | `fields`: 1..3 of `link`, `rec`, `live`, none twice | link state, REC, LIVE |
| `key` | `key`: integer 0..8 | that key's label and state |
| `legend` | `button`: integer 0..3 | that button's action |
| `scene_line` | `scene`: `program` or `preview`; `size`: `small` or `large` | a scene name |
| `strip` | `knob`: integer 0..2; `parts`: 1..5 of `name`, `db`, `fader`, `meter`, `push`, none twice | one channel |
| `text` | `text`: string, 0..32 bytes | a fixed string |

Rules (R14, "Rules both sides enforce"):

1. `w` and `h` are at least 24.
2. The rectangle lies inside the panel: `x + w` at most the width, `y + h` at most the height.
3. No `key`, `legend` or `strip` argument (`key`, `button`, `knob`) appears twice on one display.
4. No two widgets on one display overlap. Sharing an edge is not an overlap.
5. An unknown `kind` is refused. The pad never shows half a layout.

Three points of R14 are left out of schema 1, each for a stated reason:

- The `clock` kind and the `clock` status field: protocol v2 has no message that gives the pad the time.
- The `text` bindings (stream health, page, host): paging is later (spec 9) and `STATUS` has no stream health field.
- "x, y, w, h multiples of 4": the strip is 142 pixels wide, and R14's own strip example has `w = 142`.

## Unknown fields

A member this file does not name is not checked and is kept. The app keeps the whole JSON value it read and changes only the fields the user touched (R13, "Read-modify-write", item 2). The app writes members in sorted order; the order carries no meaning.

## Order of the checks and the path

The validator stops at the first failure and reports its path in `RESULT` (at most 48 bytes, `docs/protocol.md`). Both validators check in this order, so both report the same path:

1. Size, then JSON, then the root object.
2. `schema`, `seq`, `obs` (`url`, `auth_mode`), `wifi` (`ssid`).
3. `keys`, `buttons`, `knobs`: the list and its count, then each entry in order. An action: `do`, `uuid`, `label`. A knob: `input`, `step_db`, `push`.
4. `main_display`, then `strip_display`: `widgets` and its count, then each widget in order: `kind`, `x`, `y`, `w`, `h`, rule 2, the fields of the kind, then rules 3 and 4 against the widgets before it.
5. `ui` (`brightness`).

A path joins names with `.` and adds a list index as `[n]`, counted from 0: `obs.url`, `keys[2].do`, `strip_display.widgets[0].parts[1]`. A missing field, a wrong type and a bad value all give the field's own path. A list entry that is not an object reads as an object with no members, so it gives the path of its first field: `buttons[3].do`. A wrong count gives the list's path (`keys`, `main_display.widgets`). Rules 2, 3 and 4 give the widget's path. For rules 3 and 4 that is the later widget of the pair: two overlapping widgets at index 0 and 1 give `main_display.widgets[1]` (criterion 4b).

## URL rule

`obs.url` is `ws://<private IPv4>[:port]` and nothing else (spec 8.2).

- The address is four decimal numbers 0..255 with no leading zero, inside `10.0.0.0/8`, `172.16.0.0/12` or `192.168.0.0/16` (RFC 1918 section 3, cited, not re-read here).
- The port is optional: 1..65535, digits only, no leading zero. With no port the pad uses 4455 (spec section 5 diagram).
- Refused, each with path `obs.url`: loopback (`127.0.0.1`), a public address, link-local (`169.254.0.0/16`), a host name, `wss://` (obs-websocket has no TLS, R05), userinfo (`user@`), a path (a trailing `/` too), a query, a fragment.

## Schema rule

The pad accepts exactly the `schema` values from `INFO` `schema_min` to `schema_max`. A document whose `schema` is missing, is not an integer, or lies outside that range gets `RESULT invalid` with path `schema`, and nothing is stored (spec 8.2). Firmware for schema 1 reports min 1 and max 1.

**Boot rule.** At boot, a stored document with a good slot header and a `schema` below the pad's min is not loaded and not erased. The pad runs as it does with no document and shows the factory strip line with the words `update config`. `CFG_READ` still serves the stored bytes as they are, with their `schema` and `seq`. The app migrates them and commits with that `seq` as `base_seq` (spec 8.2).

**Migrations** run in the app only, one function per schema step (R13, "Read-modify-write", item 5). A step changes what its schema change needs and leaves `seq` and unknown fields alone. Schema 1 is the first schema, so the app ships no step yet.

**App and pad of different ages** (spec 8.2):

| Pad `schema_max` | The app |
|---|---|
| equal to the app's schema | reads and writes |
| above the app's schema | opens the document read-only and says `update the app` |
| below the app's schema | writes nothing and says `update firmware`. No `CFG_BEGIN` is built. There is no downgrade migration |

## Try-only revert

Spec 8.2 and R13 differ on when a try-only draft ends (`docs/research/gap-3.md`, "Inconsistencies", item 2). This file fixes it:

1. `CFG_BEGIN` with `flags` bit 0 set, then the chunks and `CFG_COMMIT`: the pad validates the draft as it does a stored write, holds it in RAM and draws it. It writes no flash and does not change the stored `seq`.
2. The pad goes back to the stored document on the first of: 30 s after the commit (spec 8.2), a `CFG_READ` (R13, "Try on the device"), a new `CFG_BEGIN`, or a reset.
3. `CFG_READ` always serves the stored document, never the draft. That is why it ends the draft: the app never edits one document while the panels show another.
4. A draft that fails validation gets `RESULT invalid` with its path, and the panels do not change.

## Vectors

`firmware/test/config_vectors/` holds one file per case, the raw bytes of a document. `verdicts.txt` in that directory lists each file with its verdict: `valid`, `too_big`, or `invalid` and the path (no path means the empty path). The pad range for every vector is min 1, max 1.

The Rust test gives every file to the validator and compares the verdict and the path. A second Rust test fails when a file is missing from `verdicts.txt` or listed there without a file. The C test (`firmware/test/test_config.c`) holds `firmware/core/config.c` to the same table.

## Open points

- Two limits of the pad's JSON reader (`firmware/core/json.h`) are not rules of the Rust validator: a number literal longer than 32 bytes and nesting deeper than 16 stack entries make the pad answer `invalid` with the empty path. No document the app writes comes near either; the owner decides whether `document.rs` adopts them.
- `uuid` takes any 1..36 printable bytes because criterion 4c uses `U_B`, while `OBS_ITEM` carries 16 raw UUID bytes. The owner picks one form before task 2.12.
