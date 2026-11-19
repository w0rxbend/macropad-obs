# Tasks: macropad-obs v2

Next action: 1.9 (config schema and vectors); 3.1 runs beside it.
Plan, lanes and gates: `tasks/plan.md`.

Definition of done for every task: `just test` exits 0. No test or check is weakened. The four
protocol files change together from 1.2 on, and the four config files from 1.9 on (R3; 1.9 lands a
stub `firmware/core/config.c` so all four arrive together). Sizes that come from no datasheet stay
MEASURE. No secret appears in a vector, log or export. A new C test adds its gcc line to the
`test-firmware` recipe (the `justfile` edit is implied). Size: S is 1-2 files, M is 3-5.

Tags: **[P]** can run beside the other [P] tasks of its lane (see the plan). **[HW]** needs real
hardware in the owner's hands: no agent marks it done; the owner records the measured value.
**[owner]** needs an owner action or approval. **provisional** means the result stands on
placeholder FPC footprints until S.3 exits, and is re-run in 5.12.

## Phase 0: Spike (spec 9 build order step 1)

- [ ] **S.1 Spike firmware on the DevKitC-1 (M) [HW, owner].** A throwaway IDF project in
  `espressif/idf:v6.1.1` (**gated on the image approval**). It covers each spec 9 step 1 item: CDC
  enumerates; Wi-Fi association time; Hello/Identify against a throwaway OBS on 4456, auth off;
  `BOOTLOADER` register sequence (spec 8.2) to the ROM port; each panel's ID read; SPI step bench
  logging `spi_device_get_actual_freq()` at each exact 80 MHz / n; the ST7796U bench of spec 14
  (each step from 16 MHz up, 1000 pseudo-random full frames, RAMRD read-back, zero mismatches,
  3.3 V IOVCC, real FPC length). The kit's RGB LED net (GPIO38 on v1.1, GPIO48 on v1.0, `[E7]`)
  moves to IO42, and the kit revision is logged.
  - Accept: it builds; every item above prints one log line with yes/no plus a value.
  - Verify: `just spike` (build); the owner's run on the kit gives the log S.3 copies.
  - Deps: the IDF image approval. Files: `firmware/spike/CMakeLists.txt`,
    `firmware/spike/main/spike.c`, `firmware/spike/sdkconfig.defaults`, `justfile`.
- [ ] **S.2 Printed slab mock-up with the insert (S) [owner prints].** A build123d slab from the
  `cad` params: deck, walls, back-wall insert gap at x 56.0 to 87.6 (spec 7). The owner prints it,
  tapes deck and walls in aluminium and leaves the insert bare (spec 9 step 1, D7).
  - Accept: the STL reads back watertight; its outline equals `board.toml` within 0.05 mm.
  - Verify: `cad/.venv/bin/python cad/obs_case/mockup.py`. Deps: 6.1. Files:
    `cad/obs_case/mockup.py`, `cad/obs_case/test_mockup.py`.
- [ ] **S.3 Spike results record (S).** One row per spec 9 step 1 item: yes/no, value, method,
  date. Copy each value into `board.toml` and clear its MEASURE tag only where it was measured:
  3V3 peak and 100 ms average current (mA), f_bus (fastest clean step, actual MHz), tail offset x,
  tail contact face, FH12 vs FH12A, antenna feed side, ROM VID/PID, RSSI and Hello/Identify in the
  mock-up against open air at the same spot (dBm, ms).
  - Accept: **exit condition:** a narrow panel in hand, its pin table read and its outline
    calipered. Until then the narrow pocket and FPC footprint stay open. An RSSI fail goes back to
    the owner (spec 14). `check_measure.py` lists fewer open items, never more.
  - Verify: `just test`; `just gate` output diffed against the last run.
  - Deps: S.1, S.2, 1.3, 1.4a. Files: `docs/spike.md`, `board.toml`.

## Phase 1: Contracts

Gate **G-rules [owner]:** approved, all six rule texts of spec 12, on 2026-11-19
(`docs/spec/decisions-v2.md`). A `CLAUDE.md` edit still needs the owner in session. Each
rule lands with the task that makes its paths true: R3 protocol half in 1.2, R6 in 1.3, R5 in
1.5, R3 config half in 1.9, R1 and R2 in 1.10, R4 in 2.18.

- [x] **1.1 Retire the Pico SDK build (S).** Delete the never-built RP2040 firmware.
  `check_pins.py` stops reading `CMakeLists.txt`. The `firmware` recipe (justfile lines 51-58,
  firmware/Dockerfile, pico-sdk, PICO_BOARD) goes.
  - Accept: `firmware/src/`, `firmware/CMakeLists.txt` and `firmware/Dockerfile` are gone. No
    recipe or script names them: `tools/test_docs.py` reads these three names and the Verify grep
    from this card.
  - Verify: `just test`; `grep -rn 'CMakeLists\|pico' justfile tools/` is empty.
  - Deps: none. Files: `firmware/src/*` (delete), `firmware/CMakeLists.txt`, `firmware/Dockerfile`,
    `tools/check_pins.py`, `justfile`.
- [x] **1.2 Move to the spec's paths (M).** `git mv` the core to `firmware/core/`. Make `host/` a
  Cargo workspace with the `host/obs_core/` member. Point the app at it. Apply the R3 protocol half
  to `CLAUDE.md` and fix the `protocol.rs` path in its `check_pins.py` sentence (G-rules; the rest
  of R6 waits for 1.3). Behaviour stays the same. Do not tick this task before the `CLAUDE.md` edit.
  - Accept: `link.*` and `input.*` are under `firmware/core/`; `host/obs_core/src/protocol.rs`
    exists; all 22 Rust tests and the C tests still run. `app/src-tauri/Cargo.toml` has
    `obs_core = { path = "../../host/obs_core" }`. Every path in `CLAUDE.md` exists.
  - Verify: `just test`; the 3.1 probe
    (`cd app/src-tauri && CARGO_TARGET_DIR=<scratch> cargo check --offline --keep-going`) shows no
    new failure that names `obs_core`;
    `grep -o '`[^`]*/[^`]*`' CLAUDE.md | tr -d '`' | xargs -n1 test -e`.
  - Deps: 1.1, G-rules. Files: `justfile`, `host/Cargo.toml`, `host/obs_core/Cargo.toml`,
    `tools/check_pins.py`, `app/src-tauri/Cargo.toml`, `CLAUDE.md`, moved sources.
- [x] **1.3 Pin map and check_pins v2 (M).** Add a `[gpio]` table to `board.toml` with the pins in
  spec section 7, after 1.4a (1.4a owns every other `board.toml` edit in Phase 1). Add the
  strapping allow-list. Generate `firmware/esp32s3/main/pins.h`. Apply R6 to `CLAUDE.md`.
  USB VID/PID stay at their current values, tagged pending pid.codes.
  - Accept: `check_pins.py` binds `pins.h` and `protocol.rs` to `board.toml`. It rejects a
    duplicate GPIO, any net on IO3/IO45/IO46, and any net but BOOT on IO0. There is one pass vector
    (the spec table) and one fail vector per rule.
  - Verify: `just check`; `python3 -m unittest tools/test_check_pins.py`.
  - Deps: 1.4a, 1.6b (reads `USB_VID`/`USB_PID` from the new `protocol.rs`). Files: `board.toml`,
    `tools/check_pins.py`, `tools/test_check_pins.py`, `tools/pin_vectors/*.toml`,
    `firmware/esp32s3/main/pins.h` (delete `firmware/pins.h`), `CLAUDE.md`.
- [x] **1.4a Layout rev 3 and the geometry tables (M).** Bump `docs/spec/layout-v2.toml` to rev 3
  with `[stack]`, `[foam_frame]`, `[display_carrier]` and `[pcb] top_keepout` (spec 7 "Revision 3",
  spec 9 `contracts`). Redraw `docs/images/layout-v2.png` with `tools/draw_layout.py`. Port rev 3
  into `board.toml` (R5: the layout feeds `board.toml`).
  - Accept: `tools/check_numbers.py` checks panel_face 5.6, both carrier heights, foam squeeze 10
    to 25 %, no keep-out under a carrier, six holes, and that every shared value in `board.toml`
    equals `layout-v2.toml` rev 3. Every non-datasheet value keeps its MEASURE tag.
  - Verify: `just test` (a new `numbers` recipe joins it); `python3 tools/check_numbers.py`;
    `python3 tools/draw_layout.py` exits 0.
  - Deps: 1.2. Files: `docs/spec/layout-v2.toml`, `docs/images/layout-v2.png`, `board.toml`,
    `tools/check_numbers.py`, `tools/test_check_numbers.py`, `justfile`.
- [x] **1.4b Retire the old wedge (M).** Delete `pcb/gen`, `pcb/kicad`, `pcb/fab`, `cad/exports`,
  `cad/obs_case/geometry.py` and `numbers.py`. Their tests cover only the deleted wedge. Cut
  `cad/build.py` (line 9 imports `obs_case.numbers`) to a file that imports cleanly and exits 2 with
  "no case body until 6.2a" on every step. Drop `from .geometry import ...` (line 11) from
  `cad/obs_case/export.py`. Remove the `pcb-test`, `cad-check` and `cad` recipes from `justfile` and
  from `test`; 5.1, 6.1 and 6.2a bring them back.
  - Accept: `python3 cad/build.py check` exits 2, not with an ImportError. `just --list` names no
    removed recipe. A reviewer confirms the removed tests touched only deleted code.
  - Verify: `just test`; `python3 cad/build.py check; test $? -eq 2`.
  - Deps: 1.4a. Files: `justfile`, `cad/build.py`, `cad/obs_case/export.py`, the deleted trees.
- [x] **1.5 Board-order gate (S).** Write `tools/check_measure.py` as spec 9 step 6 describes.
  Apply R5 to `CLAUDE.md`.
  - Accept: it lists every MEASURE on the named tables and exits 1 today with the spec's list. Its
    unit test passes on a clean fixture and fails on a tagged one. `just gate` runs the real check.
    `just test` runs only the unit test.
  - Verify: `python3 -m unittest tools/test_check_measure.py`; `just gate` exits 1.
  - Deps: 1.4a. Files: `tools/check_measure.py`, `tools/test_check_measure.py`, `justfile`,
    `CLAUDE.md`.
- [x] **1.6a Delete the v1 bridge (S).** `host/obs_core/src/bridge.rs` is the in-memory v1 port
  (`encode_hello_ack`, `encode_page`, `BIND`, `PROFILE`). Under D1 there is no PC process: delete it
  and its 2 tests (the plan allows deleting tests with the code they test).
  - Accept: no file names `bridge`. The other Rust tests still pass.
  - Verify: `just test-host`. Deps: 1.2. Files: `host/obs_core/src/bridge.rs` (delete),
    `host/obs_core/src/lib.rs`.
- [x] **1.6b Frame codec v2 (M) [P].** Use `0xA5`, version `0x02`, type, id, u16 length 0..240, and
  CRC-16/MODBUS. Add a pull-style `link_pull`. A v1 frame gets `NOTICE`. An oversize frame gets
  `RESULT too_big`. Add the same codec in Rust. The `USB_VID`/`USB_PID` constants that check_pins
  binds stay in `protocol.rs`.
  - Accept: every vector decodes in both C and Rust. A split at all 64 read alignments works. An
    oversize frame and a bad CRC each get a reply and are never dropped. The 247-byte lost-head case
    from R02 passes.
  - Verify: `just test-firmware`; `just test-host`.
  - Deps: 1.6a. Files: `firmware/core/link.[ch]`, `host/obs_core/src/protocol.rs`,
    `firmware/test/vectors.txt`, `docs/protocol.md`, `firmware/test/test_link.c`.
- [x] **1.7 Config messages (M).** Add `INFO_GET`/`INFO`, `CFG_READ`/`CFG_DATA` (offset, `seq`),
  `CFG_BEGIN` (base_seq, total, CRC-32, try-only flag), `CFG_CHUNK`, and `CFG_COMMIT`/`RESULT`
  (ok, busy, stale_seq, bad_crc, too_big, invalid, plus the first bad path).
  - Accept: each type has encode and decode vectors that C and Rust share. `INFO` carries
    `obs_password_set` and `wifi_psk_set` as bits only.
  - Verify: `just test`.
  - Deps: 1.6b. Files: the four protocol files and `test_link.c`.
- [x] **1.8 Provisioning and status messages (M).** Add `SET_CREDENTIAL{kind, bytes}` (the reply
  is a status byte; limits and codes in spec 8.2), `CLEAR_CREDENTIALS` (no payload, clears both,
  status byte reply), `STATUS` (OBS state, Wi-Fi state `no_ssid`,
  `connecting`, `bad_key`, `no_ap` or `up`, RSSI, IP), `OBS_LIST`/`OBS_ITEM`, `INPUT`, and
  `FACTORY_RESET`/`BOOTLOADER` with a 32-bit magic each.
  - Accept: shared vectors. A test asserts that no device-to-host type has a field derived from a
    credential: its value, its length or its hash (R1). The `INFO` git hash and the `CFG_DATA`
    document bytes are the two checked exceptions: the test names both and shows that neither is fed
    by `cred`. A wrong magic is refused. `SET_CREDENTIAL` has one reject vector per rule of spec
    8.2, shared by C and Rust: an empty payload and a kind with no bytes (`bad_len`), kind 0 and
    kind 3 (`bad_kind`), a Wi-Fi passphrase of 7 and 65 bytes (`bad_len`), a 63-byte passphrase
    with one byte outside `0x20`-`0x7E` and a 64-byte one that is not hex (`bad_value`). An
    OBS password of 239 bytes is accepted; 240 cannot be framed and gets `RESULT too_big` (8.1).
    `CLEAR_CREDENTIALS` with no payload is the accept vector (`ok`); with one payload byte it is
    the reject vector (`bad_len`, spec 8.2).
    Vector credentials are dummy strings, never a real secret.
  - Verify: `just test`.
  - Deps: 1.7, 1.10 (R1 replaces "No OBS password in a CDC frame" first). Files: the four protocol
    files and `test_link.c`.
- [ ] **1.9 Config schema, vectors, Rust document, C stub (M) [P].** Write `docs/config.md` (layout
  names, try-only revert). Add `firmware/test/config_vectors/` with valid and invalid files and their
  expected verdicts. Add `host/obs_core/src/document.rs`: types, validator, unknown fields kept, and
  migrations by `schema`. Add a stub `firmware/core/config.c` that returns `unimplemented` for every
  vector, with a test that expects exactly that (2.9 replaces both). Apply the R3 config half to
  `CLAUDE.md`. The four R3 config files land together, so this task may exceed 5 files.
  - Accept: Rust matches every vector verdict. The URL rule accepts only `ws://<private IPv4>[:port]`
    and rejects loopback, public, `wss://`, userinfo, path and query. Two overlapping widgets give
    `invalid` with the second widget's path. The 16 KiB cap holds. The C stub test passes.
    `config_vectors` hold one file each for `schema` missing, too old (min - 1) and too new
    (max + 1); each gives `invalid` with path `schema` (spec 8.2). One Rust test runs a migration
    round trip: a document one schema step old migrates, validates, keeps its unknown fields and
    `seq`, and serialises with the new `schema`. One Rust test has the pad max below the app's
    schema: the write is refused with `update firmware` and builds no `CFG_BEGIN`. `docs/config.md`
    states the same schema rule, the boot rule for a stored `schema` below min, and that refusal
    (spec 8.2).
  - Verify: `just test`.
  - Deps: 1.2. Files: `docs/config.md`, `firmware/test/config_vectors/*`,
    `host/obs_core/src/document.rs`, `host/obs_core/src/config.rs`, `host/obs_core/src/lib.rs`,
    `firmware/core/config.[ch]`, `firmware/test/test_config.c`, `CLAUDE.md`.
- [x] **1.10 Repo rules R1 and R2 (S).** Apply the spec 12 R1 and R2 texts to `CLAUDE.md`
  (G-rules).
  - Accept: R1 and R2 match spec 12 word for word. Every path in `CLAUDE.md` exists.
  - Verify: `just test`; `grep -o '`[^`]*/[^`]*`' CLAUDE.md | tr -d '`' | xargs -n1 test -e`.
  - Deps: 1.2, G-rules. Must land before 1.8. Files: `CLAUDE.md`.

### Checkpoint 1
- [ ] `just test` exits 0. `just gate` exits 1 with the spec's MEASURE list.
- [ ] All protocol vectors give the same verdict in C and Rust; config vectors pass in Rust and the
  C stub reports `unimplemented`.
- [ ] Owner review of `board.toml` v2, `layout-v2.toml` rev 3 and the protocol v2 doc.

## Phase 2: Firmware core (SDK-free, `firmware/core/`, gcc ASan/UBSan in `just test`)

- [ ] **2.1 fw-crypto (S) [P, lane A].** SHA-1, SHA-256, base64.
  - Accept: the NIST vectors pass. The R05 obs-websocket auth example gives the published string.
  - Verify: `just test-firmware`. Deps: 1.2. Files: `core/crypto.[ch]`, `test/test_crypto.c`.
- [ ] **2.2 fw-json (M) [P, lane B].** Vendor LwJSON v1.10.1 (MIT; **new dependency, ask first**).
  Add a streaming wrapper.
  - Accept: 500-scene and 500-input fixtures parse in bounded RAM under ASan. A split at any byte
    gives the same result.
  - Verify: `just test-firmware`. Deps: 1.2. Files: `core/third_party/lwjson/*`, `core/json.[ch]`,
    `test/test_json.c`, `test/fixtures/obs_500_*.json`.
- [ ] **2.3 fw-input (M) [P, lane C].** Scan the 4x4 matrix with 16-bit debounce. Add 3 quadrature
  decoders fed by counts, and the B1 + B4 clear combination (an event; 2.11a wires the erase).
  - Accept: ghosting cases, debounce, and 2 turns/s with bounce all pass. Holding 5.0 s raises the
    clear event; 4.9 s does not.
  - Verify: `just test-firmware`. Deps: 1.3. Files: `core/input.[ch]`, `test/test_input.c`.
- [ ] **2.4 fw-wifi state machine (S) [P, lane D].** States, backoff, and one strip line per
  failure. No IDF headers.
  - Accept: every state and backoff step runs on a fake event feed. Each failure maps to its line.
    No line holds a secret.
  - Verify: `just test-firmware`. Deps: 1.8. Files: `core/wifi.[ch]`, `test/test_wifi.c`.
- [ ] **2.5 fw-stream and fw-ws (M) [lane A].** Write the TCP seam (open, send, recv, close) and an
  RFC 6455 client: masking, fragments, ping on idle, close codes.
  - Accept: a fake transport with 1-byte reads, fragments, ping and close passes. The upgrade key
    check uses SHA-1 and base64.
  - Verify: `just test-firmware`. Deps: 2.1. Files: `core/stream.h`, `core/ws.[ch]`,
    `test/test_ws.c`, `test/fake_stream.[ch]`.
- [ ] **2.6 tools/fake_obs.py (M) [P, lane E].** A stdlib-only obs-websocket 5 server: Hello,
  Identify, auth on or off, scripted state from `ui_state.json`, a request log, modes for
  4009/4010/4011, a 500-scene collection, and a throttled 75 kB reply.
  - Accept: its self-test drives a handshake with a Python client and checks the log format that
    criterion 4c uses.
  - Verify: `python3 -m unittest tools/test_fake_obs.py`. Deps: none. Files: `tools/fake_obs.py`,
    `tools/test_fake_obs.py`, `tools/fixtures/ui_state.json`.
- [ ] **2.7 fw-obs handshake (M).** Hello, Identify (subscriptions 1118), auth, `rpcVersion` 1,
  the 5.4.0 floor, no retry on 4009/4010/4011, and reconnect backoff.
  - Accept: the test runs the core over a POSIX stream against `fake_obs.py`, with auth on and off,
    a wrong password and a too-old OBS. Each one ends in its strip state.
  - Verify: `just test-firmware`. Deps: 2.2, 2.5, 2.6. Files: `core/obs.[ch]`,
    `test/posix_stream.c`, `test/test_obs_handshake.c`, `justfile`.
- [ ] **2.8 fw-obs requests and events (M).** One request in flight. A full re-read after
  `Identified`. State for scenes, inputs, mute, volume and outputs (RESUMED counts as active). Meters
  through `Reidentify` 65536 only while a meter shows. Port the logic of `host/obs.rs`, then delete
  it.
  - Accept: out-of-order replies are matched. 500 scenes load in bounded RAM. Event updates reach
    the state.
  - Verify: `just test`. Deps: 2.7. Files: `core/obs_state.[ch]`, `test/test_obs_state.c`,
    `host/obs_core/src/obs.rs` (delete), `host/obs_core/src/lib.rs`.
- [ ] **2.9 fw-config (M).** The C document codec and validator over `fw-json`. Replaces the 1.9
  stub and its `unimplemented` test.
  - Accept: every `config_vectors/` file gives the same verdict as Rust (1.9), and the same first
    bad path.
  - Verify: `just test`. Deps: 1.9, 2.2. Files: `core/config.[ch]`, `test/test_config.c`.
- [ ] **2.10 fw-store (M).** Two raw slots, header written last, a NOR flash model, and a
  credential store seam.
  - Accept: a power cut after every program call boots the old or the new document, never a mix.
    No credential byte reaches `CFG_DATA`. Clear erases the credential partition model: with
    both dummy secrets stored, after clear a raw dump of the model holds no byte run of either.
    A slot with a good header and a stored `schema` below min survives boot: the slot bytes are
    unchanged, the loader reports no document, and a raw read returns the bytes, `schema` and `seq`
    (spec 8.2).
  - Verify: `just test-firmware`. Deps: 2.9. Files: `core/store.[ch]`, `core/cred.h`,
    `test/nor_model.[ch]`, `test/test_store.c`.
- [ ] **2.11a Device link dispatcher: config and credentials (M).** Wire `CFG_*`, `INFO`,
  `SET_CREDENTIAL`, `CLEAR_CREDENTIALS`, `FACTORY_RESET` and `BOOTLOADER` to config, store and cred,
  with one reply per id. Wire the 2.3 clear event to the same erase path as `FACTORY_RESET`: `cred`
  first, then both cfg slots (spec 8.2, R1).
  - Accept: a fixed byte sequence of a whole read, edit and commit returns `seq + 1`. A stale write
    gets `stale_seq`. A try-only write reverts after 30 s of model time. After B1 + B4 held 5.0 s the
    model shows `cred` and both slots empty; after 4.9 s, untouched. With a stored `schema` below
    min, `CFG_READ` returns the stored bytes and `seq`, and a commit of the migrated document with
    that `base_seq` returns `seq + 1`. `CLEAR_CREDENTIALS` with one payload byte replies `bad_len`
    and leaves `cred` untouched.
  - Verify: `just test-firmware`. Deps: 1.8, 2.3, 2.10. Files: `core/device.[ch]`,
    `test/test_device.c`.
- [ ] **2.11b Device link: OBS lists, status and input (S).** Serve `OBS_LIST`/`OBS_ITEM` from
  `obs_state`. Send `STATUS` from fw-wifi and fw-obs on each change. Send `INPUT` on each input
  event (the app's "press to select").
  - Accept: a 500-scene state comes back as 500 `OBS_ITEM` frames in order. A Wi-Fi or OBS state
    change gives one `STATUS`. Each key, button, knob step and push gives one `INPUT`.
  - Verify: `just test-firmware`. Deps: 2.4, 2.8, 2.11a. Files: `core/device.[ch]`,
    `test/test_device_obs.c`.
- [ ] **2.12 fw-actions (M).** Map inputs to OBS requests. Port `keymap.rs` and `volume.rs`, then
  delete the old Rust logic (`lib.rs` Core, `keymap`, `paging`, `profile`, `volume`).
  - Accept: each mapped action gives the expected request JSON, including the 4c sequence. Knob
    steps clamp.
  - Verify: `just test`. Deps: 2.3, 2.8, 2.9. Files: `core/actions.[ch]`, `test/test_actions.c`,
    the deleted `host/obs_core/src/*.rs`.
- [ ] **2.13 fw-ui model (S).** The widget model from `main_display` and `strip_display`, and the
  tile grid.
  - Accept: the overlap check agrees with the validator. A config edit dirties only its widgets'
    tiles.
  - Verify: `just test-firmware`. Deps: 2.9. Files: `core/ui.[ch]`, `test/test_ui.c`.
- [ ] **2.14a fw-ui renderer and big-panel goldens (M).** A 16-line band renderer into a test
  framebuffer and 4 bpp Latin fonts (**font source and licence: ask first**). Golden frames for the
  big panel.
  - Accept: the frames match the committed goldens byte for byte (big-endian RGB565, 307,200 B).
    Only changed tiles are pushed.
  - Verify: `just test-firmware`. Deps: 2.13. Files: `core/render.[ch]`, `core/font_*.c`,
    `test/test_render.c`, `test/golden/main_*`.
- [ ] **2.14b Strip goldens, R14 mock-ups, retire st7789 (M).** Golden frames for the strip and the
  three R14 mock-ups. Delete `st7789.*`, `font8x16.*` and `test_st7789.c`.
  - Accept: the strip frames match byte for byte (121,552 B). The R14 mock-ups match.
  - Verify: `just test-firmware`. Deps: 2.14a. Files: `test/test_render_strip.c`,
    `test/golden/strip_*`, `test/golden/r14_*`, the deleted files.
- [ ] **2.15 Panel init tables as data (S).** ST7796U and NV3007 init sequences, and the
  CASET/RASET/RAMWR builder.
  - Accept: the tables match vectors cited to the R06 and R07 datasheets. The NV3007 table is
    marked unverified until S.3 records the panel ID read and a drawn frame.
  - Verify: `just test-firmware`. Deps: 1.2. Files: `core/panels.[ch]`, `test/test_panels.c`.
- [ ] **2.16 padsim (M).** The whole core on one PTY plus a POSIX TCP stream. A panel model with
  window and offset. A file-backed NOR image that survives a kill. A `--cut-after N` switch that
  kills the process at program call N. stdin commands `key`, `button`, `knob`, `dump`,
  `wait-idle`, and `wifi <event>` feeding fw-wifi (`no_ssid`, `bad_key`, `no_ap`, `up`).
  - Accept: it starts, answers `INFO` over the PTY, and connects to `fake_obs.py`. A run with
    `--cut-after 3` exits at call 3 and the next start reads the same NOR file. `wifi bad_key` gives
    the bad-key `STATUS`.
  - Verify: `just padsim-smoke`. Deps: 2.4, 2.11b, 2.12, 2.14b. Files: `firmware/padsim/main.c`,
    `padsim/pty.c`, `padsim/panel_model.c`, `padsim/nor_file.c`, `justfile`.
- [ ] **2.17a padsim e2e: criteria 4 and 4c (M).** A Rust test harness (host codec) drives padsim
  and `fake_obs.py`.
  - Accept: criterion 4 (read, edit, write, `seq + 1`, stale) and 4c (exact request log) pass.
  - Verify: `just test`. Deps: 2.16. Files: `host/obs_core/tests/padsim_e2e.rs`,
    `host/obs_core/tests/common/mod.rs`, `justfile`.
- [ ] **2.17b padsim e2e: criteria 5, 8 and 9 (M).**
  - Accept: 50 `--cut-after` kills during commit leave the old or the new document (5). 500 scenes
    load and 500 come back over `OBS_LIST` (8). `wifi` events and fake_obs modes for no SSID, bad
    key, no AP, OBS unreachable, bad password, OBS too old and factory each give their strip line
    (9). `just test` stays under 60 s.
  - Verify: `just test`. Deps: 2.17a. Files: `host/obs_core/tests/padsim_faults.rs`.
- [ ] **2.18 Repo rule R4 (S).** Apply the spec 12 R4 text to `CLAUDE.md` (G-rules), now that
  `just test` runs padsim end to end.
  - Accept: R4 matches spec 12 word for word. Every path in `CLAUDE.md` exists (the 1.10 loop).
  - Verify: `just test`. Deps: 2.17b. Files: `CLAUDE.md`.

### Checkpoint 2
- [ ] `just test` exits 0 under 60 s, with padsim e2e.
- [ ] No IDF header in `firmware/core/`:
  `grep -rnE '#include *[<"](esp_|freertos/|driver/|sdkconfig)' firmware/core` is empty.
- [ ] Owner review of the golden frames against R14.

## Phase 3: App

- [ ] **3.1 app-shell build defects (M) [P with Phase 1].** `build.rs` declares the commands
  through `AppManifest::commands`. `main.rs` imports `tauri::Manager`. The icons are RGBA.
  - Accept: the `macropad-obs` build script raises no ACL error. Today it raises "Permission
    allow-get-state not found" (reproduced in review).
  - Verify: `cd app/src-tauri && CARGO_TARGET_DIR=<scratch> cargo check --offline --keep-going`;
    the `webkit2gtk-sys` failure is expected before D6 and is not a pass or a fail of this task.
    After D6, `just app`.
  - Deps: none. Files: `app/src-tauri/build.rs`, `src/main.rs`, `capabilities/default.json`,
    `icons/*`.
- [ ] **3.2 App core: discovery and config session (M).** A Tauri-free crate. It finds the pad by
  VID/PID and serial, not a fixed path. It handles `INFO`, read until total, write with `base_seq`,
  and a diff on stale. Adapt `pad.rs`. **Ask first:** `serialport` moving into the `host/`
  workspace brings libudev into `just test`.
  - Accept: the round trip keeps unknown fields. Stale shows a diff. Tests run against padsim.
  - Verify: `cargo test -p app_core` (in `just test`). Deps: 2.17a. Files:
    `host/app_core/src/*.rs` (3-4), `host/Cargo.toml`.
- [ ] **3.3 App core: provisioning and export (S).** `SET_CREDENTIAL` from `Secret`, fields cleared
  after the write, `CLEAR_CREDENTIALS`, and Wi-Fi `STATUS`.
  - Accept: the export has no secret. In a capture of the padsim traffic, no device-to-host frame
    holds a password or PSK byte, and no host-to-device frame other than the `SET_CREDENTIAL`
    payload does (criterion 12, host side). The test checks both directions.
  - Verify: `just test`. Deps: 3.2. Files: `host/app_core/src/provision.rs`, its test.
- [ ] **3.4 App core: preview and criterion 4b (M).** Build `fw-ui` through `cc` (**new
  dependency, ask first**). Render the preview from the same state.
  - Accept: 4b passes byte for byte against the padsim dumps. Changed pixels stay inside the two
    edited widgets. An overlap write gets `invalid` and the frames stay unchanged.
  - Verify: `just test`. Deps: 2.14b, 3.2. Files: `host/app_core/build.rs`, `src/preview.rs`,
    `tests/criterion_4b.rs`.
- [ ] **3.5 App core: firmware update (M).** `BOOTLOADER`, wait for 303a:1001 within 10 s,
  `espflash` 4.7.0 as a library (**ask first**), hard reset, check the new git hash in `INFO`.
  - Accept: the state machine passes on a fake port: timeouts, wrong PID, flash error. The real run
    is 4.9. It drops if the owner says no to the in-app update.
  - Verify: `just test`. Deps: 3.2. Files: `host/app_core/src/update.rs`, its test, `Cargo.toml`.
- [ ] **3.6 Tauri commands over the core (M). Blocked: needs D6 or the 3.9 image approval.**
  Replace `session.rs` and the seven old commands. Keep `logbuf.rs`.
  - Accept: each command is a thin call into `app_core`. Errors reach the UI as values. No `unwrap`.
    Picker and URL logic lives in `app_core` (Rust tests), not in JS.
  - Verify: after 3.9, `just app-check`; after D6, `just app`. Deps: 3.1-3.5, 3.9 or D6. Files:
    `app/src-tauri/src/main.rs`, `commands.rs`, `session.rs` (delete), `Cargo.toml`.
- [ ] **3.7 UI: mapping editor (M).** A no-build HTML and ES module UI for keys, buttons and knobs,
  with OBS pickers from `OBS_LIST`, plus the URL field. The UI stays thin: form state, URL rule and
  stale diff are `app_core` functions with Rust tests. `node --test` only if the owner approves Node
  as a new toolchain.
  - Accept: the picker model takes a 500-item `OBS_LIST` (criterion 8) in a Rust test. After D6 the
    picker shows all 500 by eye.
  - Verify: `just test`; after 3.9, `just app-check`. Deps: 3.6. Files: `app/ui/index.html`,
    `ui/mapping.js`, `ui/api.js`, `host/app_core/src/forms.rs`.
- [ ] **3.8 UI: display, Wi-Fi and firmware pages (M).** A layout editor with the preview, SSID
  plus write-only passphrase and password, and the update page.
  - Accept: secret fields never fill from a read and clear after a write (a Rust test on the
    command layer, and a look after D6).
  - Verify: `just test`; after 3.9, `just app-check`. Deps: 3.7. Files: `ui/display.js`,
    `ui/wifi.js`, `ui/update.js`, `host/app_core/src/forms.rs`.
- [ ] **3.9 app-check and udev (S).** A `just app-check` image built from the local
  `kicad/kicad:10.0.7` with Tauri's Debian list (**apt packages: ask first**), and `xvfb-run`. Add
  the 303a:1001 ROM port to the udev rule (check_pins is not touched).
  - Accept: the 3.1 shell compiles and the window "macropad-obs" is visible within 10 s and alive
    for 5 s.
  - Verify: `just app-check`. Deps: 3.1. Files: `app/check/Dockerfile`, `justfile`,
    `app/udev/70-macropad-obs.rules`.

### Checkpoint 3
- [ ] `just test` includes 4b and 4c.
- [ ] `just app-check` exits 0 once approved, then 3.6 to 3.8 verify through it. After D6, 4.9.

## Phase 4: ESP-IDF port (`espressif/idf:v6.1.1` in Docker, pulled only after owner approval)

- [ ] **4.1 IDF project and `just firmware` (M).** `firmware/esp32s3/`: CMake, `sdkconfig.defaults`
  (no NVS encryption, no flash encryption, no secure boot), a partition table (`nvs`, `cred`,
  `cfg_a`, `cfg_b`), esp_tinyusb 3.0.1. The core links as a component.
  - Accept: `just firmware` writes a merged image. The partition table is checked against the spec.
  - Verify: `just firmware`. Deps: Checkpoint 2, approval. Files: `esp32s3/CMakeLists.txt`,
    `main/CMakeLists.txt`, `sdkconfig.defaults`, `partitions.csv`, `main/idf_component.yml`.
- [ ] **4.2 USB CDC port and BOOTLOADER (M) [P].** One CDC-ACM port. Writes block on back-pressure.
  A pull read feeds the link. The serial number comes from the MAC. The BOOTLOADER register
  sequence follows spec 8.2. `cred` is erased first.
  - Accept: it builds. The register names match the IDF v6.1.1 headers. A host test covers the
    write loop's back-pressure path.
  - Verify: `just firmware`; `just test`. Deps: 4.1. Files: `main/usb_port.c`, `main/boot_dl.c`,
    `core/link_tx.c`, `test/test_link_tx.c`.
- [ ] **4.3 Wi-Fi, stream and cred port (M) [P].** `esp_wifi` STA with `WIFI_STORAGE_RAM` set after
  init and before `set_config`. The PSK loads from `cred` on each boot. An lwIP socket `stream`.
  `cred_nvs.c` owns `nvs_flash_init_partition("cred")` and `nvs_flash_erase_partition("cred")`.
  - Accept: it builds. `grep` finds `WIFI_STORAGE_RAM` before `esp_wifi_set_config` in the source.
  - Verify: `just firmware`. Deps: 4.1. Files: `main/wifi_port.c`, `main/stream_lwip.c`,
    `main/cred_nvs.c`.
- [ ] **4.4 Config slot port (S).** `esp_partition` backend for `cfg_a`/`cfg_b` behind the
  `fw-store` NOR seam. Calls the 4.3 cred erase; does not edit `cred_nvs.c`.
  - Verify: `just firmware`. Deps: 4.3. Files: `main/store_flash.c`.
- [ ] **4.5 Input port (S) [P].** A matrix GPIO scan task. PCNT units 0-2 with glitch filter on the
  spec's pins.
  - Verify: `just firmware`; `just check` (pins from `pins.h`). Deps: 4.1. Files:
    `main/input_port.c`.
- [ ] **4.6 Display port (M) [P].** Two `esp_lcd` SPI IO handles on SPI2, the big panel first
  (CS0 on IO10). DMA band push. LEDC backlights. `spi_device_get_actual_freq()` logged. f_bus comes
  from S.3 (13.3 MHz if no higher step passed).
  - Verify: `just firmware`. Deps: 4.1, 2.15, S.3. Files: `main/lcd_port.c`, `main/backlight.c`.
- [ ] **4.7 Main, watchdog and power cap (M).** The task layout and the watchdog. Backlights and
  Wi-Fi stay off until USB configures, or for 2 s with no enumeration. The cap comes from
  `board.toml`, and a 1.5 A CC advert lifts it. Add the `just flash` recipe.
  - Accept: the image builds. The size and free-RAM report is logged. The cap values are cited to
    the S.3 3V3 current.
  - Verify: `just firmware`. Deps: 4.2-4.6, S.3. Files: `main/main.c`, `main/power.c`, `justfile`,
    `board.toml`.
- [ ] **4.8 Dev kit acceptance (M) [HW].** The spec 11 `fw-port-esp32s3` row and criteria 3 and 12
  on the DevKitC-1. Use throwaway test secrets kept outside the repo in a secrets file. `esptool`
  runs in the IDF image; offsets and sizes come from `partitions.csv`.
  - Accept, each with its command and value in `docs/devkit.md`:
    - Re-associates after an AP restart within 30 s (criterion 3): `python3 tools/soak.py --watch-status`
      logs the `STATUS` times.
    - 8 h soak with no reset (R15): `python3 tools/soak.py --hours 8` polls `INFO` uptime every
      10 s and fails on any drop.
    - Watchdog test: a build with the watchdog self-test flag blocks a task; the next boot logs the
      task-watchdog reset reason.
    - After a Wi-Fi join, `nvs` holds no secret: `esptool.py --chip esp32s3 read_flash <nvs off>
      <size> nvs.bin; ! grep -a -F -q -f secrets.txt nvs.bin`.
    - After `CLEAR_CREDENTIALS`, after the clear key combination, and after `BOOTLOADER`, the same
      dump of `cred` matches no secret (R1, criterion 12).
    - The UART log captured during join and provisioning matches no secret
      (`! grep -a -F -q -f secrets.txt uart.log`, criterion 12, logs).
  - Verify: `python3 -m unittest tools/test_soak.py` (fake port, in `just test`); the owner's run.
  - Deps: 4.7, 2.11b. Files: `tools/soak.py`, `tools/test_soak.py`, `docs/devkit.md`.
- [ ] **4.9 Real app and firmware update (S) [HW, owner].** Gated on D6 and on the open question
  about the in-app update (drops if the owner says no).
  - Accept: criterion 13 steps with `just app` on the dev kit. Then criterion 14: `BOOTLOADER`,
    ROM port within 10 s, `espflash` writes, hard reset, the new git hash in `INFO`, all within
    30 s. Then a `cred` dump (4.8 command) matches no secret.
  - Verify: the owner's run, recorded in `docs/devkit.md`. Deps: D6, Checkpoint 4, 3.5, 3.8, 4.8.
    Files: `docs/devkit.md`.

### Checkpoint 4
- [ ] `just firmware` exits 0 and writes a merged image. `just test` is still green.
- [ ] 4.8 recorded: CDC enumerates, Wi-Fi associates and re-associates, both panels draw, 8 h soak,
  watchdog, `nvs`, `cred` and UART dumps hold no secret.

## Phase 5: PCB (local `kicad/kicad:9.0.9`, `10.0.7-full` for STEP; `just pcb`)

- [ ] **5.1 Copy the greycode writer core (M) [P].** Copy `sexpr`, `symlib`, `schematic` and
  `sheet_layout` from `macropad-greycode/pcb/gen/` with their tests, with CERN-OHL-S-2.0 headers
  (D5). `test_schematic.py` gets a small local fixture circuit, not greycode's `circuit.py` (it
  carries SK6812). Bring back `pcb-test` (`unittest discover` over `pcb/gen`) and add it to
  `just test`.
  - Accept: the copied plain tests pass in `just pcb-test` without Docker. No file names SK6812.
  - Verify: `just test`. Deps: 1.4b. Files: `pcb/gen/{sexpr,symlib,schematic,sheet_layout}.py`,
    their tests, `pcb/gen/fixture_circuit.py`, `justfile`.
- [ ] **5.2 Copy the layout, router, contract and fab helpers (M) [P].** Copy `layout`, `router`,
  `contract`, `fab` and `build` from greycode, plus macropad's `_check_rules_reach_drc`.
  `test_order_files.py` waits for 5.10 (it reads `pcb/routing.txt`, the board sha256 and Gerbers).
  - Accept: the copied tests pass. `contract.py` reads `board.toml`.
  - Verify: `just pcb-test`. Deps: 5.1. Files: `pcb/gen/{layout,router,contract,fab,build}.py` and
    tests.
- [ ] **5.3a Footprint library without FPC (M) [P].** WROOM-1, USB4216-03-A (rev A2), MX_Hotswap
  (copied), B3F, EC11, Hole_M2 and the ground-bond hole. Two FPC footprints named `PLACEHOLDER_*`.
  `SOURCES.txt` cites each drawing.
  - Accept: each footprint's provenance is cited. The antenna feed side is read from the WROOM
    footprint and recorded in `board.toml`. A test fails if a `PLACEHOLDER_*` footprint reaches
    `pcb/fab/`.
  - Verify: `just pcb-test`. Deps: 5.1. Files: `pcb/lib/macropad-obs.pretty/*`,
    `pcb/lib/SOURCES.txt`, `pcb/gen/test_footprints.py`.
- [ ] **5.3b FPC footprints from the calipered panels (S).** FH12 or FH12A per S.3, tail contact
  face and offset from S.3.
  - Accept: no `PLACEHOLDER_*` remains. `[fpc.*]` positions lose their MEASURE tags only where S.3
    measured them.
  - Verify: `just pcb-test`; `just gate` lists fewer items. Deps: S.3, 5.3a. Files:
    `pcb/lib/macropad-obs.pretty/FPC_*`, `pcb/lib/SOURCES.txt`, `board.toml`.
- [ ] **5.4 Netlist: power, MCU and USB (M).** Module, TLV62569 buck, USB4216, ESD, PPTC, 5.1 k
  CC resistors, CC sense, BOOT/RESET, debug JST, BCR421 x2.
  - Accept: the self-check finds no open pin and every IC power pin tied. LCSC cells stay
    UNVERIFIED. No SK6812. The rule tests from `git show d3f75a2:pcb/gen/test_circuit.py` are
    carried over.
  - Verify: `just pcb-test`. Deps: 5.2, 1.3. Files: `pcb/gen/circuit_power.py`,
    `pcb/gen/test_circuit.py`.
- [ ] **5.5 Netlist: HMI (M).** The 4x4 matrix with BAT54 x16, MX x9, B3F x4, EC11 x3 with RC
  filters, and the FPC 40 and 10 nets.
  - Accept: the nets match `[gpio]` in `board.toml`. `check_pins` agrees.
  - Verify: `just pcb-test`; `just check`. Deps: 5.4. Files: `pcb/gen/circuit_hmi.py`, test.
- [ ] **5.6 Placement from board.toml (M) [provisional].** Turn `pcb` into `pcb *STEP` (no step:
  the whole pipeline). The outline with the 33.0 x 6.0 antenna cut, 6 holes, every part at its
  `board.toml` position, bottom-face parts mirrored.
  - Accept: the contract passes: no copper in the antenna keep-out, no top part or hole under a
    carrier, top parts under 2.0 mm within 1.0 mm of a pocket. Provisional until S.3; done only
    after 5.12.
  - Verify: `just pcb place`. Deps: 5.1-5.5 (final run: S.3 via 5.12). Files: `pcb/gen/place.py`,
    `test_place.py`, `justfile`.
- [ ] **5.7 Schematic and ERC (S) [provisional].** Write the sheets and run ERC in
  `kicad/kicad:9.0.9`.
  - Accept: ERC is clean and the output is byte-repeatable.
  - Verify: `just pcb erc`. Deps: 5.6. Files: `pcb/gen/sheets.py`, `justfile`.
- [ ] **5.8 Locked critical copper (M) [provisional].** The USB pair, the buck loop, module GND
  vias, the inner plane islands, and the plane edge at the antenna, all in code.
  - Accept: the length and clearance checks pass. The copper is locked before routing.
  - Verify: `just pcb route-critical`. Deps: 5.6. Files: `pcb/gen/route.py`, `route_order.txt`,
    `test_route.py`, `justfile`.
- [ ] **5.9 Freerouting and DRC (M) [provisional].** Fetch 2.5.0 by sha256
  `f6f51bb02245e8e717f9359bd260cc9c5c0b1bc0acc8b7cb2cd5b8ffeb5de3c7` (R09 `[F1]`) into an ignored
  cache. DSN out and SES in, with outer layers only, in `eclipse-temurin:25-jre --network none`.
  - Accept: KiCad DRC at error severity gives 0 violations, 0 unconnected and 0 parity, with 4
    copper layers and every net routed (criterion 10). A wrong sha256 stops the run.
  - Verify: `just pcb`. Deps: 5.8. Files: `pcb/gen/freeroute.py`, `pcb/outer.rules`, `.gitignore`,
    `justfile`.
- [ ] **5.10 Fab outputs (M) [provisional].** The JLCPCB Gerber, drill, BOM and CPL set. Bring in
  greycode's `test_order_files.py` here.
  - Accept: the outputs are byte-repeatable. Locally, every BOM reference matches a CPL line and a
    board footprint, and back. The JLCPCB upload is F.1 [owner]. `just gate` (1.5) still decides on
    ordering.
  - Verify: `just pcb fab`. Deps: 5.9. Files: `pcb/gen/fab.py`, `test_fab.py`,
    `pcb/gen/test_order_files.py`, `pcb/fab/*`, `justfile`.
- [ ] **5.11 Board STEP (S) [provisional].** `kicad-cli` in the local `kicad/kicad:10.0.7-full`
  (it has `RF_Module.3dshapes/ESP32-S3-WROOM-1.step`, `Connector_USB` and `Button_Switch` models;
  plain `10.0.7` has no `/usr/share/kicad/3dmodels`). MX and EC11 come from the `cad` envelopes.
  - Accept: the STEP reads back with its solid count recorded in the manifest. The manifest lists
    which parts come from KiCad models and which from `cad` envelopes.
  - Verify: `just pcb step`. Deps: 5.9. Files: `pcb/gen/step.py`, `justfile`.
- [ ] **5.12 Re-run on the real FPC footprints (S).** After 5.3b, run 5.6 to 5.11 again.
  - Accept: DRC 0/0/0, ERC clean, fab and STEP rebuilt, and no `PLACEHOLDER_*` in any output.
  - Verify: `just pcb`; `just pcb step`; `just gate`. Deps: S.3, 5.3b, 5.11. Files: `pcb/fab/*`,
    generated outputs.

### Checkpoint 5
- [ ] DRC 0/0/0 and ERC clean, from the real command output, after 5.12.
- [ ] `just gate` output is reviewed with the owner. No board order while it exits 1.

## Phase 6: Case (`cad/.venv`, build123d 0.13.0; `just cad`)

D5 copies: never edit the sibling repos. Each copied file carries
`# SPDX-License-Identifier: CERN-OHL-S-2.0` under `cad/` and names its source path in its header.

- [ ] **6.1 Params from board.toml (S) [P].** `cad/obs_case/spec.py` reads `board.toml` at run time
  (greycode pattern). No layout literal stays in `cad/`. Bring back `cad-check` running
  `test_spec.py` with the stdlib only, in `just test`.
  - Verify: `just test`. Deps: 1.4b. Files: `cad/obs_case/spec.py`, `test_spec.py`, `justfile`.
- [ ] **6.2a Style A slab and deck (M).** A flat slab with chamfered edges, windows, lens recesses,
  the key well, button and knob holes. `cad/build.py` runs the new body; the `cad *STEP` recipe
  returns and passes the step to `build.py`.
  - Accept: the geometry checks pass. A failed cut is a fault (no `_keep()` swallow).
  - Verify: `just cad`. Deps: 6.1. Files: `cad/obs_case/body.py`, `deck.py`, `checks.py`,
    `cad/build.py`, `justfile`.
- [ ] **6.2b Display carriers and foam frames (S).**
  - Accept: carrier heights and foam squeeze match `check_numbers.py`.
  - Verify: `just cad`. Deps: 6.2a. Files: `cad/obs_case/carriers.py`, `checks.py`.
- [ ] **6.3 Back-wall insert and bottom plate (M).** The insert from x 56.0 to 87.6, full wall
  height, with the floor tongue, `antenna_relief`, the bottom plate and 6 holes. Insert colour per
  open question 1 (default black).
  - Accept: no metal solid in the antenna board cut. The insert fit stays MEASURE.
  - Verify: `just cad`. Deps: 6.2b. Files: `cad/obs_case/insert.py`, `bottom.py`, `checks.py`.
- [ ] **6.4 Print and CNC variants, CNC pack (M).** Variant tolerances. CNC-only checks. Copy the
  drawing writer from `macropad/cad/macropad_case/drawings.py` and CNC checks from `checks.py`.
  - Accept: both variants build. The CNC pack holds STEP, PDF and DXF. The PDF carries tolerances,
    the D3 style A finish callout (bead blast, black anodise) and the engrave layer.
  - Verify: `just cad`. Deps: 6.3. Files: `cad/obs_case/variants.py`, `drawings.py`, `checks.py`.
- [ ] **6.5 3D exports with read-back (M).** STEP AP214 (master), AP242, BREP, IGES, STL, native
  3MF and GLB. Copy `_write_3mf`, `assembly` and the GLB path from
  `macropad-nyxilab/common/cad/macropad_cad/export.py` into `cad/obs_case/export.py`. The STEP
  header is deterministic.
  - Accept: the solid count is exact, B-rep volume within 1e-4, mesh within 0.1 %, and meshes are
    watertight. A second run leaves git clean.
  - Verify: `just cad`; `git status --short cad/exports`. Deps: 6.4. Files:
    `cad/obs_case/export.py`, `manifest.py`.
- [ ] **6.6 2D exports, FCStd and part envelopes (M).** DXF, SVG, PDF, and one envelope STEP per
  bought part. Copy `macropad-nyxilab/common/cad/macropad_cad/freecad_doc.py`. FCStd needs FreeCAD
  (**not installed; ask first**).
  - Accept: each export reads back. FCStd is reopened, or it is marked not built in the manifest.
  - Verify: `just cad`. Deps: 6.5. Files: `cad/obs_case/export2d.py`, `envelopes.py`,
    `freecad_doc.py`.
- [ ] **6.7 Laser engraving sheets (M).** Legends from `[ui_mirror]`, ticks and the logo (open
  question 5), on `MARK`/`REF` layers. Copy the DXF engraving writer from
  `macropad/cad/macropad_case/drawings.py` (`engraving_underside.dxf` path).
  - Accept: `ezdxf` audit (1.4.5 in `.venv`) shows 0 errors. Strokes are at least 0.2 mm and cap
    height at least 2.0 mm. The outline matches the deck 1:1 within 0.05 mm.
  - Verify: `just cad laser`. Deps: 6.2a. Files: `cad/obs_case/laser.py`, `test_laser.py`,
    `cad/build.py`, `justfile`.
- [ ] **6.8 Interference with the board STEP (S).** Check the case, plate, insert and caps against
  the 5.11 STEP and the module, plus the module stack (0.9 to the plate) and the USB shell.
  - Accept: 0 interferences. Gaps are reported against MEASURE. Provisional until 5.12.
  - Verify: `just cad fit`. Deps: 5.11, 6.3, 6.10. Files: `cad/obs_case/fit.py`, `cad/build.py`,
    `justfile`.
- [ ] **6.9 Coupons and renders (S).** Print coupons for the module stack, USB4216, keys and FPC
  tail. Copy `macropad/cad/macropad_case/coupons.py`. Regenerate `docs/images/*.png` with
  `render.py`.
  - Verify: `just cad`. Deps: 6.4. Files: `cad/obs_case/coupons.py`, `render.py`.
- [ ] **6.10 Knob dial and B3F caps (S).** Port the dial (EC11 shaft seat, index, set screw,
  flutes) from `git show d3f75a2:cad/obs_case/geometry.py` (`_knob`, `_knob_seat`, `_knob_grooves`,
  `_knob_pointer`). Add the B3F cap: press-on printed or machined floating (spec 6), plunger per
  open question 2. Keycaps are bought DSA (spec 6).
  - Accept: both read back. The shaft fit and cap fit stay MEASURE.
  - Verify: `just cad`. Deps: 6.2a. Files: `cad/obs_case/knob.py`, `cad/obs_case/b3f_cap.py`.

### Checkpoint 6
- [ ] `just cad` exits 0. All exports read back. Fit has 0 interferences.

## Phase 7: Docs

- [ ] **7.1 Docs path check (S) [owner: only if wanted].** `tools/check_docs.py` fails on a named
  file that does not exist, in `just test`. If the owner says no, 7.2 uses the 1.10 `test -e` loop.
  - Verify: `just test`. Deps: none. Files: `tools/check_docs.py`, `justfile`.
- [ ] **7.2 Design, OBS, config and bring-up docs (M).** Replace `docs/design.md` and
  `docs/obs.md` from the spec and the code as built. Keep `docs/config.md` current. Write
  `docs/bringup.md` (R15 order, stop at the first fail).
  - Accept: every fact carries a source or a MEASURE tag. Hardware facts not yet measured say
    "pending S.3", "pending 4.8" or "pending H.x". No RP2040 text remains.
  - Verify: `just test`. Deps: 7.1, the code lines of Checkpoints 1, 2, 3, 5 and 6. Files:
    `docs/design.md`, `docs/obs.md`, `docs/config.md`, `docs/bringup.md`.
- [ ] **7.3 README status table (S).** A hand-written table: each command, its last exit code and
  date. A gated command says "not run: gated" and never counts as pass.
  - Verify: each row against a fresh run of its command. Deps: 7.2. Files: `README.md`.

### Checkpoint 7
- [ ] The README table matches a fresh run. Owner review.

## Phase 8: Fab and hardware (spec 9 step 6: boards, print case, bring-up, `cad` cnc, `fab`)

Every result goes into `docs/hardware.md`: value, method, date. A fail stops the phase and goes to
the owner.

- [ ] **F.1 JLCPCB quote upload, no order (S) [owner].** Upload the 5.12 Gerber, drill, BOM and CPL
  to the JLCPCB quote page.
  - Accept: 0 unmatched BOM lines. The CPL rotation preview matches the STEP for each part.
  - Verify: the owner's screenshots. Deps: Checkpoint 5. Files: `docs/hardware.md`.
- [ ] **F.2 CNC pack quote (S) [owner].** Submit STEP, the PDF with tolerances and finish, and the
  DXF to one shop's quote form.
  - Accept: the form accepts the pack (criterion 11). Record the shop and any rejected item.
  - Verify: the owner's record. Deps: Checkpoint 6. Files: `docs/hardware.md`.
- [ ] **F.3 Print the case (S) [owner, HW].** Gated on open question 5 (bed size; longest part
  about 170 mm).
  - Accept: every print-variant part printed. Verify: the owner's record. Deps: Checkpoint 6.
    Files: `docs/hardware.md`.
- [ ] **H.1 Order the boards (S) [owner].** Gated on `just gate` exit 0.
  - Verify: `just gate` exits 0 on the commit ordered. Deps: F.1, 5.12. Files: `docs/hardware.md`.
- [ ] **H.2 Assemble and bring up (S) [HW].** Run `docs/bringup.md` in R15 order, stop at the first
  fail: no rail short; at 5 V, 100 mA limit, 3V3 = 3.3 V +/- 3 %; UART0 boot log; ROM port with
  BOOT held; CDC enumerates; each panel draws the test pattern; every key, button and knob reports
  `INPUT`; Wi-Fi up.
  - Verify: each line pass/fail with its value. Deps: H.1, 7.2, Checkpoint 4.
- [ ] **H.3 Criterion 2: input to scene change under 100 ms (S) [HW].** Method: a key mapped to a
  scene; `tools/latency.py` timestamps the `INPUT` frame on CDC and `CurrentProgramSceneChanged`
  on its own obs-websocket session, one clock; 20 presses. Pass: max < 100 ms.
  - Deps: H.2. Files: `tools/latency.py`, `docs/hardware.md`.
- [ ] **H.4 Criterion 3: reconnect (S) [HW].** Restart OBS: `STATUS` OBS up within 5 s. Restart the
  AP: within 30 s. App closed; `tools/soak.py --watch-status` logs the times.
  - Deps: H.2, 4.8.
- [ ] **H.5 Criterion 5 on the real pad (S) [HW].** 50 unplugs during `CFG_COMMIT` while a script
  loops commits. After each replug `CFG_READ` gives the old or the new `seq` and document.
  - Deps: H.2.
- [ ] **H.6 Criterion 6: strip within 200 ms (S) [HW].** Change name, level and mute in OBS for 3
  inputs; a camera at 120 fps or more films the OBS mixer and the strip. 20 changes. Pass: max
  <= 200 ms.
  - Deps: H.2.
- [ ] **H.7 Criterion 7: redraw timing (S) [HW].** A logic analyser on SCLK, CS and DC from the
  first CASET byte to the last RAMWR byte, at f_bus from S.3 (actual frequency from the log). Pass:
  one 96x96 cell <= 17 ms, full screen <= T_full for that f_bus.
  - Deps: H.2.
- [ ] **H.8 Criterion 15: VBUS and charger path (S) [HW].** A USB power meter or shunt in VBUS,
  Wi-Fi TX and both backlights at the firmware cap. Record peak and 100 ms average. Pass: peak
  <= 500 mA. On a charger with no host: Wi-Fi up after 2 s at the cap.
  - Deps: H.2.
- [ ] **H.9 Manual row (S) [HW, owner].** Owner's OBS closed, a throwaway OBS on 4456 (R15). The 4b
  layout on both real panels compared with the app preview by eye; a photo of each.
  - Deps: H.2, 4.9 or `app-check`.
- [ ] **H.10 Print case: fit and RF (S) [HW].** The board in the F.3 case. Fit with no sanding
  (criterion 11), yes or no per part. RSSI (dBm) and Hello/Identify (ms) in the case against open
  air at the same spot (spec 14 stage 2, D7). A fail goes back to the owner.
  - Deps: F.3, H.2.
- [ ] **H.11 CNC case: fit and RF (S) [HW, owner orders the milling].** The same fit and RF
  comparison in the milled case (spec 14 stage 3). A fail goes back to the owner.
  - Deps: F.2, H.10.

### Checkpoint 8
- [ ] Every spec 11 bring-up and manual line, and criteria 2, 3, 5, 6, 7, 11 and 15, has a measured
  value in `docs/hardware.md`.
