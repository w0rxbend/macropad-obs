# 02. Inventory of this repo: keep, adapt or replace

Research only, 2026-11-18. A run on 2026-11-17 was interrupted. This version re-read every cited line
and re-ran every probe. This file is the only file written. Confidence tags: **verified** (read or run
today in the primary source), **likely** (reasoned from a verified fact, not run), **unverified**.
Change shares and size classes are estimates from reading the code. They are not measurements.

## Recommendation

Keep the repo's process and its small pure cores. Replace everything that is specific to the old
device. By the shares in the tables below, about 1,800 of 7,055 source lines carry over, a quarter
(estimate).

Next action: decide how the pad reaches the network (open question 1). The current board has no
network path, and that choice fixes the firmware platform before any module is rewritten.

Five findings carry the recommendation.

1. **The process is sound and worth keeping.** `board.toml` as source of truth, `tools/check_pins.py`,
   one vectors file for two parsers, and a native `just test`. It exits 0 today. (verified)
2. **The display path is a placeholder.** Every glyph is drawn into the same 8x16 window at the top
   left corner. 93 of the 94 visible glyphs are hatch noise. After the first draw the status row
   never shows a new host and never clears a notice. The tests pass anyway. (verified by probe)
3. **All three known link risks are real.** One more exists: a large frame can lose its head. None
   bites the old device hard. All of them block config transfer. (verified by probe)
4. **The Tauri app does not build as committed.** Reproduced on a scratch copy: the build script
   stops at `Permission allow-get-state not found`, before WebKit matters. The app's job, holding the
   OBS socket, is also the job the owner moves into the firmware. (verified)
5. **The PCB has no copper.** 0 segments, 0 vias, 4 footprints, and a 2-layer stack although
   `board.toml:54` says `layers = 4`. The netlist has open pins. (verified)

## What the owner asked for

The words that drive every verdict below: "4layers or more PCB, with 3x3 keys matrics, MX switches,
also 2 displays one bigger and one longer, also one tray of buttons", "firmware on the device should
be communicating with this websocket OBS url", and "bidirectional configuration, mapping buttons,
configuring the outputs on the displays".

The owner's answers: the three round controls are rotary knobs with push. The small-button row has
4 tactile buttons. The big display is about 3.2 to 3.5 inch and about 57 mm wide. The narrow display
shows the three knobs' state: source name, level, mute.

Counts used below: 9 MX plus 4 tactile is 13 switches. With the 3 knob pushes that is 16 contacts,
which fills a 4x4 matrix exactly (likely; the electrical topic decides). The sketch draws the small
row with about five cells. The owner's answer of 4 is used. See open question 4.

## Test run today

`just test` exited 0. (verified, run 2026-11-18)

| Step | Result | What it does not prove |
| --- | --- | --- |
| `test-firmware` | link 7 tests, input 4, st7789 6, all pass under ASan and UBSan | `firmware/src/*.c` is never compiled. No UF2 was ever built (`README.md:37`: "It has not been run"). No display test checks where a glyph lands |
| `test-host` | 22 tests pass, clippy `-D warnings` clean, `cargo fmt --check` clean | Nothing in `app/` |
| `check` | 6 checks match `board.toml` | No duplicate-GPIO check exists |
| `pcb-test` | 6 tests pass | One test compares literals with literals (`pcb/gen/test_circuit.py:74`) |
| `cad-check` | no problems printed | Solids are not built. `check()` pins the old layout to literals (`cad/obs_case/numbers.py:167-201`) |

## Known risks: confirmed or refuted

I compiled the repo's own C files, unchanged, with gcc ASan/UBSan against stub SDK headers in a
scratch directory outside the repo. The stub TX FIFO follows TinyUSB 0.18.0. That is the version the
pinned pico-sdk 2.1.1 ships: the submodule commit `86ad6e56` is the `0.18.0` tag. (verified)

1. **`firmware/src/usb.c` drops bytes when the TinyUSB FIFO is full: confirmed.** `usb.c:56` ignores
   the return of `tud_cdc_write`. TinyUSB writes only what fits once DTR is set
   (`cdc_device.c:176-190`, `tusb_fifo.c:483-488`). Before DTR the FIFO overwrites its oldest bytes
   (`cdc_device.c:255`, `:418`). Probe: 60 KEY frames, host not draining. 540 bytes offered, 256
   accepted, 284 dropped. Impact today is low, because the pad sends 8 to 11 byte frames. It blocks
   reading a config back from the device. (verified)
2. **`main.c` ignores the result of `link_send`: confirmed, and checking it would not help.**
   `main.c:20`, `:36`, `:39`, `:42`. `usb_poll` empties the 1,024-byte link queue into
   `tud_cdc_write` on every pass, accepted or not (`usb.c:51-57`). In the probe above `link_send`
   refused 0 frames and the queue was empty afterwards. The loss in item 1 is invisible to
   `link_send`. Back-pressure has to live in `usb.c`. (verified)
3. **`link_feed` discards complete frames past the caller's cap: confirmed.** `link.c:121` copies a
   frame only when `produced < cap`. `link.c:129` drops it either way. No counter moves. Probe: 9
   frames with cap 8 returned 8 and left 0 bytes buffered. In the `usb.c` shape (64-byte reads, cap 8
   from `main.c:73-74`) a burst of 21 frames delivered 19 and a burst of 40 delivered 36. (verified)

Three more firmware defects turned up.

1. **A large frame loses its head.** `link.c:75-78` appends every incoming byte before it parses,
   into a 256-byte buffer, and drops the oldest byte when full. Probe: a 247-byte frame (the largest
   legal one) with traffic behind it was lost at 54 of 64 read alignments. Frames up to 193 bytes are
   safe. The largest frame in use is 172 bytes (PAGE_VIEW), so this is latent. (verified)
2. **The status row redraws once.** `panel.c:103-109` takes its label from the last drawn text, not
   from the last BIND. Probe: the redraw after the 1 s notice window wrote 0 SPI bytes, and so did a
   BIND with a new host. `docs/protocol.md:43` says the pad restores BIND. (verified)
3. **`main.c:47` calls `board_init()` with no declaration in scope.** TinyUSB declares it only in
   `hw/bsp/board_api.h:70`, which nothing includes. gcc 14 and later reject that. The pinned Ubuntu
   24.04 toolchain is older and should only warn. (verified for the missing include; likely for the
   toolchain)

## Inventory

Requirement codes: **M** 13 switches in a matrix, **E** 3 encoders, **D** 2 displays, **O** device-side
OBS client, **C** bidirectional configuration. "Change" is the share of current lines rewritten or
deleted.

### Repo level

| Module | Lines | Verdict | Hit by | Change | Evidence |
| --- | --- | --- | --- | --- | --- |
| `board.toml` | 92 | adapt | M E D O | 90% | Role stays. `[keys]` is 9 direct GPIOs, `[knob]` and `[display]` are single tables. All values are the old wedge |
| `tools/check_pins.py` | 84 | adapt | M E D | 70% | Hard-codes `PIN_KEY_0..8`, one knob, one display. Add a duplicate-GPIO check |
| `justfile` | 62 | adapt | all | 30% | Recipe shape stays. File lists change |
| `CLAUDE.md` | 11 | adapt | O D | owner | Two rules meet the owner's words. See "Repo rules" below |
| `LICENSE`, `LICENSE.cern-ohl-s` | 15 | adapt | none | small | Both are pointers with a URL. Neither holds the licence text or a copyright line |
| `.gitignore` | 11 | keep | none | 0% | |
| `.grok/workflows/` | 781 | remove | none | 100% | The other tool's supervisor loops. Gate scripts hold absolute session paths and `/tmp` handoff files |

### firmware/ (1,695 lines, C)

| Module | Lines | Verdict | Hit by | Change | Evidence |
| --- | --- | --- | --- | --- | --- |
| `link.c`, `link.h` | 252 | adapt | C | 60% | Keep SOF, version, type, length, CRC-16, encode, resync. Fix risk 3 and the lost head with a pull API and a larger buffer. No sequence number, no reply pairing. The message table goes |
| `input.c`, `input.h` | 152 | adapt | M E | 50% | The debounce loop takes a 16-bit mask, so 16 contacts fit after `INPUT_KEYS` changes (`input.h:9`). The quadrature table is correct. State is one encoder, not three. Push-to-page and the backlight gate leave |
| `st7789.c`, `st7789.h`, `font8x16.*`, `src/panel.*` | 526 | replace | D | 100% | Finding 2. `st_draw_glyph` hard-codes CASET 0..7 and RASET 0..15 (`st7789.c:74-83`). No clear, no fill, no cell drawing. The op trace costs 4 bytes of RAM per SPI byte (`panel.c:110`, 32 KB for one text row) and one SPI call plus one CS toggle per byte (`panel.c:20-32`; 3,738 calls for a 14-glyph row) |
| `src/usb.c`, `src/usb.h` | 69 | replace | C O | 90% | Risks 1 to 3. Needs back-pressure and a pull-style read |
| `src/main.c` | 97 | replace | M E D O C | 100% | One loop: direct GPIO per key, one knob, blocking draws, `sleep_ms(1)`. No flash store, no network |
| `src/usb_descriptors.c`, `src/tusb_config.h` | 83 | adapt | O C | 40% | CDC only. The serial string is the constant `"obs"` (`usb_descriptors.c:45`), so two pads collide |
| `pins.h` | 30 | replace | M E D | 100% | Regenerate from `board.toml` |
| `CMakeLists.txt`, `Dockerfile` | 55 | adapt | O | 50% | Never run. Links no network stack. Stays only if the Pico SDK stays |
| `test/` | 431 | adapt | all | 60% | Keep the CHECK harness and the vectors loader. Cases follow the modules. The C side reads 5 of the 7 vectors |

### host/ (1,736 lines, Rust crate `obs_core`)

| Module | Lines | Verdict | Hit by | Change | Evidence |
| --- | --- | --- | --- | --- | --- |
| `protocol.rs` | 350 | adapt | C | 50% | Framing, CRC and the shared-vector tests stay. `encode_page` demands 9 slots (`protocol.rs:195`). `Link::feed` uses `Vec::remove(0)` per dropped byte |
| `bridge.rs` | 172 | adapt | C | 60% | `Port` and `MemPort` are a good test seam. The frame senders go |
| `config.rs` | 397 | adapt | C O | 60% | Keep the 0600/0700 file checks, atomic save, `Secret` redaction and the URL parser. `[KeyAction; 9]` (`:60`) and `len() != 9` (`:113`) go. The loopback policy (`:174-186`) and the rule that a non-loopback URL must be `wss://` (`:215`) cannot hold. See "The working reading" |
| `lib.rs` (`Core`), `keymap.rs`, `paging.rs`, `profile.rs`, `volume.rs`, `obs.rs` | 768 | adapt: move to the device | O M E | 80% | Small pure functions with tests. This is the logic the owner moves into firmware. Port it, or share it if the firmware is Rust. `KEYS = 9` (`keymap.rs:5`) runs through it. One knob, one selected input |

Two behaviour bugs sit in this logic and its tests lock them in.

1. `output_is_on` treats `OBS_WEBSOCKET_OUTPUT_RESUMED` as off (`obs.rs:54`, test at `:97`).
   obs-websocket reports RESUMED as active (`EventHandler_Outputs.cpp:22-39`). A resumed recording
   shows as stopped. (verified)
2. The snapshot starts with stream and record off and discards the status it just read
   (`session.rs:548-559`). `obws` 0.15 does carry `active: bool`. A pad that connects during a live
   stream needs two presses to stop it. (verified by reading; likely for the two presses)

### app/ (1,116 lines, Tauri 2 + obws)

| Module | Lines | Verdict | Hit by | Change | Evidence |
| --- | --- | --- | --- | --- | --- |
| `src/session.rs` | 688 | replace | O C | 95% | Holds the OBS socket and translates pad events. That role moves to the device. `handle_cmd` takes 13 parameters. Every `bridge.*` result is ignored. The 20 ms tick is re-created on every loop pass (`:138`), so steady traffic can starve the heartbeat (likely). The `obws` list calls (about 60 lines) are reusable if the app lists scenes for the mapping editor |
| `src/main.rs` | 84 | replace | C | 90% | Seven commands for the old model |
| `src/pad.rs` | 60 | adapt | C | 40% | Serial thread with reopen and DTR. Opens a fixed `/dev/macropad-obs` (`:27`). A write waits up to 30 ms behind a blocking read |
| `src/logbuf.rs` | 79 | keep | none | 10% | Secret scrub, 0600, rotation |
| `ui/index.html` | 140 | replace | M E D C | 100% | One page, no layout editor. Sends `allow_non_loopback` (`:124`). Tauri expects `allowNonLoopback`, so Save fails, and no handler shows the error |
| `tauri.conf.json`, `capabilities/`, `build.rs`, `Cargo.toml`, icons | 64 | adapt | C | 50% | `capabilities/default.json:7-13` names `allow-get-state` and six more. `build.rs` declares no app commands, and no `permissions/` folder exists. `tauri-build` 2.7.4 stops the build (finding 4) |
| `udev/70-macropad-obs.rules` | 1 | keep | none | PID only | `uaccess`, no `plugdev`, no `MODE` |

### pcb/ (830 lines of generator, plus generated files)

| Module | Lines | Verdict | Hit by | Change | Evidence |
| --- | --- | --- | --- | --- | --- |
| `gen/kicad_board.py` | 181 | replace | M E D O | 100% | Outline, 4 NPTH holes, silkscreen boxes. Never sets a copper layer count. Plots `F_Cu` and `B_Cu` only (`:155-156`) |
| `gen/circuit.py` | 429 | replace | M E D O | 100% | A dict netlist. USB-C `J1` has no GND tie. `:333` creates a net named `Y1` that reaches only `R5`, so crystal pin 2 is open. The regulator enable pin and the ESD part's VBUS pin are not tied. 26 of the 45 machine-placed parts sit at (0, 0). "Planned routes" are literals (`:25-36`) |
| `gen/fab.py`, `gen/build.py` | 86 | replace | none | 80% | PCBWay column headers may carry over. `fab.py` says rotation is not verified against PCBWay. `build.py:write_hash` has no caller |
| `gen/test_circuit.py` | 134 | adapt | none | 70% | Carry over the rule tests: three locked LCSC numbers, `UNVERIFIED` elsewhere, no SK6812 |
| `kicad/`, `fab/` | generated | delete, regenerate | all | 100% | 0 segments, 0 vias, 4 footprints. The two earlier boards hold 827 and 892 segments on 4 copper layers |

Use the `macropad-greycode` generator as the base. `01-prior-art.md` gives the reasons.

### cad/ (1,440 lines, build123d 0.13.0)

| Module | Lines | Verdict | Hit by | Change | Evidence |
| --- | --- | --- | --- | --- | --- |
| `obs_case/export.py` | 98 | keep, extend | none | 30% | Writes STEP, STL and 3MF and reads each back: solid count, validity, volume, watertight. The owner asks for "all the export format". The installed build123d already has `export_brep`, `export_gltf`, `ExportDXF`, `ExportSVG` and a native 3MF `Mesher`. Today's 3MF is an STL re-export through trimesh (`:61-63`). The STEP header carries a timestamp, so every run dirties git |
| `obs_case/geometry.py` | 814 | replace | M E D | 80% | One wedge, one glass pocket, one knob, nine keys. Reusable: knob dial, D bore, keycap, standoffs, USB slot, the interference check. `_keep()` (`:174-180`) swallows a failed cut and keeps the old solid. The note is printed (`:128-129`), and `export.py` does not count it as a fault |
| `obs_case/numbers.py` | 325 | adapt | M E D | 70% | Screw, foot and knob maths carry over. `check()` pins the old layout to literals |
| `obs_case/render.py`, `build.py`, `pyproject.toml` | 202 | keep | none | 10% | Software rasteriser for the README picture. No GPU |
| `exports/` | generated | delete, regenerate | all | 100% | 12 stems in 3 formats, all of the old wedge |

### docs/

| Module | Lines | Verdict | Change | Evidence |
| --- | --- | --- | --- | --- |
| `docs/design.md` | 833 | replace | 100% | Its non-goals are the owner's goals: "Wi-Fi, Bluetooth, or any radio" (`:47`), "QMK, Vial, or a key matrix" (`:49`), "The pad never opens a socket and never stores the OBS password" (`:14`) |
| `docs/protocol.md`, `docs/obs.md` | 70 | replace | 100% | Version 1 messages describe a dumb pad and a host that owns OBS |
| `README.md` | 103 | replace | 100% | Honest about what was not built. Already stale: `:25` reports "exported 4 parts" and the folder holds 11 parts |
| `docs/images/*.png` | generated | regenerate | 100% | Renders of the old wedge |
| `docs/images/sketch.jpg` | image | keep | 0% | The owner's sketch. Untracked today |

## Change per requirement

Size classes for new or rewritten code: **S** under 200 lines, **M** 200 to 800, **L** over 800. All
estimates. PCB and case are full rewrites in every row, so the table names only what each
requirement adds to them.

| Requirement | firmware | host (`obs_core`) | app | pcb and cad |
| --- | --- | --- | --- | --- |
| M: 13 switches in a matrix | S. New scanner feeding the existing debounce. Direct-GPIO setup in `main.c` goes | S. `KEYS = 9`, `[KeyAction; 9]`, `len() != 9`, 9-slot `encode_page` | S. The key grid in the UI | 13 or 16 diodes, 4x4 nets, a 6x6 tactile footprint, 4 more cut-outs |
| E: 3 encoders | S to M. Three decoder states, sampled off the main loop. KNOB gains an encoder index. Push-to-page logic goes | S. One selected input becomes three bindings and three volume gates | S. A binding per knob | 3 EC11 footprints, 3 bushing holes, 3 knobs |
| D: 2 displays | L. New renderer, two panel drivers, a real font. Nothing carries over | M. A layout model for both panels in the config | M to L. The editor for "the outputs on the displays" | 2 FPC connectors, 2 backlight drivers, 2 windows |
| O: device-side OBS client | L. Network bring-up, WebSocket client, SHA-256, base64, JSON, reconnect, plus the ported 768 lines of `obs_core` logic | Logic moves down. Shared if the firmware is Rust | `session.rs` loses its OBS role (about 600 lines go) | Network hardware and its keep-out, if a radio or Ethernet is chosen |
| C: bidirectional configuration | M. Request and reply with a sequence number, chunking past 240 bytes, a flash store with a CRC and a version, back-pressure in `usb.c` | M. Config schema to wire form, version 2 messages, new vectors | M. Read, edit, write, verify. Replaces the seven commands | none |

Every protocol row also touches `firmware/test/vectors.txt` and `docs/protocol.md`, as `CLAUDE.md`
requires.

## New code with no counterpart here

These five pieces are the bulk of the work. Nothing in the repo can be adapted into them.

1. A network path on the device. `board.toml` says RP2040. `CMakeLists.txt` links `pico_stdlib`,
   `tinyusb_device`, `tinyusb_board`, `hardware_spi`, `hardware_gpio` and nothing else. (verified)
2. An OBS client in firmware: WebSocket client framing, SHA-256 and base64 for the handshake, JSON.
3. A config store in flash and a request/reply config protocol in both directions.
4. A matrix scanner and three encoder decoders that do not depend on a 1 ms main loop. One status
   row today blocks the loop for 3,738 single-byte SPI calls. (verified)
5. A renderer for two panels with a real font. The op-trace design cannot scale: a 320x480 repaint
   is 307,200 pixel bytes, which is 1.2 MB of trace at 4 bytes per SPI byte. (verified arithmetic;
   the panel size is the owner's range, not a chosen part)

## The working reading, seen from this repo

The reading is practical only after item 1 exists. Nothing here contradicts it, and nothing here
supports it yet. Three facts shape it.

1. **OBS speaks plain `ws://` only.** The obs-websocket server is built on websocketpp's
   `asio_no_tls` config (`WebSocketServer.h:27`). The device needs no TLS stack. The host rule that a
   non-loopback URL must be `wss://` (`config.rs:215`) can never be met by a stock OBS, and the
   device is never on loopback. (verified)
2. **Pin count is not the limit.** A 4x4 matrix takes 8 GPIOs, three encoders take 6, and two SPI
   panels take up to 10, against 28 RP2040 GPIOs once GP0 and GP1 stay test pads (likely; a
   parallel-bus panel would change this).
3. **A one-cable design exists on paper.** pico-sdk 2.1.1 ships lwIP as a submodule, and TinyUSB
   0.18.0 has USB network classes (`src/class/net/ncm_device.c`). The pad could appear as a USB
   network adapter and open the socket to the PC over the same cable. That keeps the owner's words
   without a radio. (verified that the files exist; unverified that it fits or works)

Choosing between that and a radio belongs to the MCU topic.

## Options compared

1. **Extend the tree in place.** Smallest diff per commit. Rejected: the display path, the PCB and
   the app session are placeholders or the wrong role, and patches would carry their tests' false
   comfort forward.
2. **Selective reuse (recommended).** Keep the process, the framing core, the config-file safety
   code, the export read-back and the test harness. Rewrite the device-specific three quarters.
3. **Clean slate.** No inherited bugs. Rejected: it throws away a green native test chain and the
   two-parser vector discipline that `CLAUDE.md` requires anyway.

## Repo rules that meet the owner's words

Neither is resolved here. The owner decides.

1. **"No OBS password in a CDC frame" against "firmware on the device should be communicating with
   this websocket OBS url".** obs-websocket 5 authentication needs the password:
   `base64(sha256(base64(sha256(password + salt)) + challenge))`. The salt is made once per OBS
   server start (`WebSocketServer.cpp:85`), the challenge once per connection (`:254`). (verified)
   Three ways out:
   1. Amend the rule. The app writes the password once, and the device stores it in flash.
   2. Turn OBS authentication off. No password exists anywhere.
   3. Keep the rule to the letter. The app sends the inner hash, `base64(sha256(password + salt))`.
      The device can then reconnect alone until OBS restarts and makes a new salt. After that it
      needs the app again. (likely; follows from the salt lifetime)
2. **The locked LCSC list names `FH12-20S-0.5SH(55)` `C596730`.** That is the old 20-pin FPC
   connector. Two new panels may need other connectors, and every new cell must stay `UNVERIFIED`
   unless the owner extends the list. (verified for the rule; unverified for the new panels)

The other rules hold as they are: `board.toml` as source of truth, four protocol files changed
together, no SK6812, `MEASURE` tags, and the licence split.

## Not checked

- `firmware/src/*.c` was not compiled for the RP2040. No `arm-none-eabi-gcc` here, and the firmware
  Docker image would need a pull. Risk: more defects in code that has never been built.
- Stack use on the target. `main()` holds about 3.3 KB of locals (`link_t` is 1,320 bytes and
  `frames[8]` is 1,952 bytes on the host build), and the SDK default `PICO_STACK_SIZE` is 0x800.
  Whether that overflows is unverified.
- The app beyond its build script. No `webkit2gtk-4.1` here, so the Rust sources were never type
  checked. The Save failure is read from `tauri-macros` 2.7.4 source, not reproduced.
- `just cad` and `just pcb` were not run. Both rewrite tracked files, which this task forbids.
- `geometry.py` was read in part (structure, `_keep`, the part list), not line by line.

## Sources

Repo files, all under `/home/worxbend/Projects/macropad-obs/`:

- `justfile`, `board.toml`, `tools/check_pins.py`, `CLAUDE.md`, `README.md`, `LICENSE`, `LICENSE.cern-ohl-s`
- `firmware/link.c`, `link.h`, `input.c`, `input.h`, `st7789.c`, `font8x16.c`, `src/main.c`,
  `src/usb.c`, `src/panel.c`, `src/usb_descriptors.c`, `CMakeLists.txt`, `Dockerfile`, `test/*`
- `host/src/*.rs`, `app/src-tauri/src/*.rs`, `app/src-tauri/capabilities/default.json`,
  `app/src-tauri/build.rs`, `app/ui/index.html`
- `pcb/gen/*.py`, `pcb/kicad/macropad-obs.kicad_pcb`, `pcb/fab/*.csv`
- `cad/obs_case/*.py`, `cad/exports/top.step`, `docs/design.md`, `docs/protocol.md`, `docs/obs.md`,
  `docs/images/sketch.jpg`, `docs/research/01-prior-art.md`

Third-party source read locally:

- TinyUSB 0.18.0: `~/.platformio/packages/framework-arduinopico/pico-sdk/lib/tinyusb/src/class/cdc/cdc_device.c`,
  `src/common/tusb_fifo.c`, `hw/bsp/board_api.h`, `src/class/net/`; upstream <https://github.com/hathach/tinyusb>
- `tauri-build` 2.7.4 `src/acl.rs:341-401`; `tauri-macros` 2.7.4 `src/command/wrapper.rs:51`,
  `:498-501`; `obws` 0.15.0 `src/responses/streaming.rs:8-11` (all in `~/.cargo/registry/src/`)
- build123d 0.13.0 in `cad/.venv` (exporter names checked with `hasattr`)
- Earlier boards, read only: `/home/worxbend/Projects/macropad/pcb/kicad/macropad.kicad_pcb`,
  `/home/worxbend/Projects/macropad-greycode/pcb/kicad/greycode.kicad_pcb`

Web, read today:

- obs-websocket protocol, "Creating an authentication string":
  <https://raw.githubusercontent.com/obsproject/obs-websocket/master/docs/generated/protocol.md>
- obs-websocket salt and challenge lifetime:
  <https://raw.githubusercontent.com/obsproject/obs-websocket/master/src/websocketserver/WebSocketServer.cpp>
- obs-websocket server without TLS:
  <https://raw.githubusercontent.com/obsproject/obs-websocket/master/src/websocketserver/WebSocketServer.h>
- obs-websocket `GetOutputStateActive`:
  <https://raw.githubusercontent.com/obsproject/obs-websocket/master/src/eventhandler/EventHandler_Outputs.cpp>
- pico-sdk 2.1.1 submodules (tinyusb `86ad6e56`, lwip, mbedtls, cyw43-driver, btstack):
  <https://api.github.com/repos/raspberrypi/pico-sdk/contents/lib?ref=bddd20f928ce76142793bef434d4f75f4af6e433>
- TinyUSB tag 0.18.0 is commit `86ad6e56`:
  <https://api.github.com/repos/hathach/tinyusb/git/ref/tags/0.18.0>

## Open questions

1. How does the pad reach OBS: a radio, USB networking over the one cable, or wired Ethernet? This
   decides whether `firmware/CMakeLists.txt`, the Dockerfile and the C sources stay at all, and
   whether configuration stays on framed CDC or rides the network link.
2. Which way out of "No OBS password in a CDC frame": amend the rule, turn OBS authentication off,
   or send only the salted hash and accept that the app is needed after each OBS restart?
3. Does the firmware stay C on the Pico SDK, or move to Rust? Rust lets the `obs_core` logic be
   shared with the app. C means porting 768 lines and keeping two copies in step.
4. Is the small-button row 4 buttons, as answered, although the sketch draws about five cells? Four
   fills a 4x4 matrix with the three knob pushes. Five does not.
5. May `.grok/workflows/` be deleted, and may the two licence files gain full texts and a copyright
   holder name?
