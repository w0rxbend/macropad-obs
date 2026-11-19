# 15. Verification strategy without hardware

Research only, 2026-11-18. Second pass: the interrupted draft's four findings were re-checked and
kept. This file is the only file written. Experiments ran in `mktemp -d` directories outside the repo.
Tags: **verified** (read or run today in a primary source), **likely** (reasoned from a verified fact,
not run), **unverified**. Keys such as `[W1]` point into Sources. No size here comes from a part, so
none needs MEASURE. No hardware was used.

## Recommendation

Prove each module on the host, not in an emulator. Keep this repo's pattern and grow it: every piece
of firmware logic that has no SDK header (frame parser, config store, input, display renderer, the
WebSocket client, the JSON reader, SHA-1, SHA-256, base64) builds with gcc and ASan/UBSan inside
`just test`. It runs against a stdlib-only fake OBS server and, by hand, against a real OBS on this
machine. KiCad in Docker judges the PCB. build123d plus trimesh judge the case. GitHub Actions runs
the same `just` recipes. Emulators are not worth using: none models USB CDC-NCM for the chosen
chips.

Next action: add `.github/workflows/ci.yml` that runs `just test` and the Docker PCB gate, and put
`rtree` in `cad/pyproject.toml` so the wall-thickness gate can run. Both are build tasks for a later
run, not this one.

Five findings carry the recommendation.

1. **The host pattern already works and is cheap.** `just test` passes in 0.66 s wall time: three C
   test binaries under ASan/UBSan, the Rust crate with clippy and fmt, `check_pins.py` (6 checks), 6
   PCB generator tests. (verified, run today `[L1]`)
2. **A fake OBS is about 50 lines of stdlib Python.** One written today did the WebSocket upgrade with
   the `obswebsocket.json` subprotocol, sent `Hello` with a challenge, checked the client's
   `base64(sha256(base64(sha256(password+salt))+challenge))`, answered `Identified` and one request.
   Node 26's built-in WebSocket client completed the round trip. (verified, run today `[X1]`)
3. **No emulator covers the device's USB network link.** Upstream QEMU 11.1.3 has no RP2040 or
   RP2350 machine. Espressif's QEMU marks USB, GP SPI and Wi-Fi as not emulated on ESP32-S3. A
   community Renode RP2040 model marks USB not implemented. Wokwi runs RP2350 with USB CDC serial only.
   (verified `[X2]` `[W1]` `[W2]` `[W3]`)
4. **KiCad 9.0.9 in Docker has every PCB gate as an exit code.** `kicad-cli pcb drc` takes
   `--schematic-parity` and `--exit-code-violations` and writes JSON. `sch erc` takes
   `--exit-code-violations`. `sch export netlist` writes `kicadxml`. (verified, run today `[X3]`)
5. **A real OBS is installed, but the owner's copy is running now.** OBS Studio 33.0.1 Flatpak runs as
   PID 3649717 since 2026-11-17 16:37, and nothing listens on 4455. Its stored config has
   `server_enabled: false`. This run did not start a second instance or change that config.
   (verified `[X4]`)

## Module by module

### Firmware core on the host

What exists: `link.c`, `input.c` and `st7789.c` build with
`gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined` and run as plain test binaries
(`justfile` `test-firmware`). (verified `[L1]`)

What to add, in order:

1. **Seam rule.** Any module that `#include`s a Pico SDK, TinyUSB or lwIP header is a thin adapter.
   All decisions live behind it in SDK-free C. `just test` compiling the core with host gcc is the
   proof that the seam holds. (likely, carried from report 04)
2. **New core units**, each with a host test: config store (encode, decode, version check, CRC, a
   power-cut in the middle of a write simulated by truncating the flash image), keymap and action
   dispatch, encoder acceleration, knob-to-OBS mapping, the two display layouts rendered into a RAM
   framebuffer.
3. **Golden frames for the displays.** Render each screen state into a buffer at panel resolution
   (320 x 480 and 142 x 428, from reports 06 and 07), write it as a PPM, and compare a hash with a
   committed file. A changed hash prints the path to the new picture for a human to look at. This
   proves layout, fonts, clipping and level bars. It does not prove the panel init sequence.
4. **Fuzzing.** clang 23 with `-fsanitize=fuzzer,address` builds and runs a libFuzzer target here
   (verified, 1000 runs today `[X5]`). Fuzz the CDC frame parser, the config decoder, the WebSocket
   frame reader and the JSON reader. Keep a short run (for example `-runs=200000`) in CI and commit
   each crash input as a regression vector.
5. **valgrind and clang-tidy** are installed (verified `[X5]`). valgrind adds little over ASan for this
   code. clang-tidy with `bugprone-*` and `cert-*` is cheap to add.

Unproven until hardware: SDK init, clock and flash timing, XIP behaviour while writing flash, PIO or
SPI DMA timing to the panels, USB enumeration, real debounce on real switches.

### OBS client on the device side (fake OBS server)

The device client (WebSocket, streaming JSON, SHA-256, auth, reconnect) is SDK-free C, so it can be
linked on the host against a 40-line POSIX socket shim in place of lwIP. Test it three ways.

1. **Scripted fake server** (Python stdlib, `asyncio`; no `websockets` package is installed on host
   `python3` 3.14, verified `[X1]`). Each test is a script of expected client messages and server
   replies. Cover: Hello with and without `authentication`; wrong secret closes with 4009; unknown op;
   a 64 kB event the client must skip without buffering; a frame split across every byte boundary;
   ping, close, server restart mid-request; `Reidentify` adding 65536 for meters; the reconnect rule
   from report 05 (never replay a command, re-read state after `Identified`).
2. **Schema check.** obs-websocket publishes `docs/generated/protocol.json` (verified `[W5]`). A test
   checks that every request type and field name the firmware sends exists in that file at the pinned
   version (5.7.6 per report 05). This catches typos without OBS.
3. **Real OBS by hand** (next section).

Unproven until hardware: lwIP on the RP2350 with TinyUSB NCM, DHCP from the pad, NetworkManager's
handling of the link, the host firewall rule (report 03).

### Emulators

| Emulator | Candidate chip | USB | SPI | Network | Verdict |
|---|---|---|---|---|---|
| QEMU 11.1.3 (upstream, installed) | RP2040, RP2350 | no machine | no machine | n/a | not usable (verified `[X2]`) |
| Espressif QEMU fork (not installed) | ESP32-S3 | not emulated | GP SPI not emulated | OpenCores Ethernet only | only for the second-choice chip's lwIP path (verified `[W2]`) |
| Renode (not installed) | RP2040 (community model) | not implemented | loopback only | none | not usable; no RP2350 model found (verified `[W3]`, `[W6]`) |
| Wokwi (cloud CLI) | RP2350, ESP32-S3 | CDC serial only | master | none for NCM | optional smoke test only (verified `[W1]` `[W4]`) |

Wokwi runs in the cloud; the free plan gives 50 simulation minutes per rolling 30 days and 5 minutes
per session (verified `[W4]`). The firmware is uploaded to its server. It could prove "the UF2 boots
and prints a banner on CDC" for RP2350. That is worth a few minutes a month at most, and it is not
needed for done.

### Protocol vectors shared by C and Rust

Keep the existing pattern: `firmware/test/vectors.txt` lines of `name hex...`, read by
`test_link.c` and by `host/src/protocol.rs` through `include_str!` (verified `[L2]`). Extend it when
the protocol grows (report 13: request ids, chunked config):

1. Every message type gets at least one good vector, one bad-CRC vector and one truncated vector.
2. A chunked config transfer gets vectors for first, middle, last and out-of-order chunks.
3. A round-trip property test in Rust (proptest or a hand loop) encodes random messages, and the C
   side decodes the same corpus from a generated file in `.build/`. Only `vectors.txt` is committed.
4. Rule from CLAUDE.md: a protocol change edits `link.c`, `protocol.rs`, `vectors.txt` and
   `docs/protocol.md` in one commit. A CI step greps the diff and fails if one of the four is missing.

### Configuration app (Tauri)

1. **Core crate without Tauri** (report 13's split): config model, validation, device protocol, port
   discovery. `cargo test` with a fake serial port (a `Read + Write` pair in memory) that speaks the
   vectors. This is most of the app's logic, and it runs in `just test`.
2. **UI model in plain ES modules**, tested with `node --test` (Node 26 is installed). No browser.
3. **Tauri shell** builds only where webkit2gtk-4.1 exists. Tauri's Linux prerequisites are
   `libwebkit2gtk-4.1-dev` and others on Ubuntu, `webkit2gtk-4.1` on Arch (verified `[W7]`). The
   package is missing here, and this run may not install it. Build the shell in CI on
   `ubuntu-24.04`.
4. **WebDriver end to end** is possible on Linux: "only Windows and Linux are supported on desktop"
   for `tauri-driver` (verified `[W8]`). Defer it. A smoke test that launches the built app under
   `xvfb-run` (installed) and checks that it exits cleanly is enough for done.

### PCB gates

All run in `kicad/kicad:9.0.9` in Docker, as `just pcb` already does.

| Gate | Command | Pass |
|---|---|---|
| ERC | `kicad-cli sch erc --format json --exit-code-violations` | exit 0, 0 errors |
| DRC | `kicad-cli pcb drc --format json --schematic-parity --severity-error --exit-code-violations` | exit 0 |
| Zero unconnected | parse the DRC JSON `unconnected_items` | empty list |
| Parity | same JSON, `schematic_parity` | empty list |
| Netlist vs board.toml | `kicad-cli sch export netlist --format kicadxml`, then a Python check | every MCU pin net in board.toml matches the netlist, and the reverse |
| Repeatable | build twice, compare sha256 of the board file | equal |

Flags verified today `[X3]`. The JSON key names and the byte-identical rebuild are from report 09,
which ran them on the sibling board (likely here; this board has no copper yet). The netlist check
extends `tools/check_pins.py`, so board.toml stays the one source of truth. Fabrication outputs
(Gerber, drill, position, BOM) are read back: count layers in the Gerber job file (4), check the BOM
has an LCSC cell for every placed part, and that every cell except the three CLAUDE.md names is
`UNVERIFIED`.

Unproven until hardware: impedance of the USB pair, the stackup the fab actually builds, assembly
yield, the backlight current, thermal behaviour.

### CAD gates

Run with `cad/.venv` (build123d 0.13.0, OCP, trimesh 5.2.1, scipy). Tested today on a test shell with
2 mm walls (verified `[X6]`):

1. **Valid solid.** `shape.is_valid` True, exactly one solid per part. Passed.
2. **Interference with the PCB.** Load the KiCad STEP of the board, intersect with each case part,
   require total volume 0. On the test shell: a PCB that fits gave 0.0 mm³, one 1 mm too wide gave
   182.4 mm³. The check works and its number is exact for boxes.
3. **Watertight meshes.** Export STL and 3MF, reload with trimesh, require `is_watertight` and
   `is_winding_consistent`. Passed (Euler number 2).
4. **Wall thickness.** Not run: trimesh ray casting needs `rtree`, which `cad/.venv` lacks, and
   voxelising failed on the test mesh (`max_iter exceeded`). Two ways forward: add `rtree` and cast
   inward rays from sampled surface points (fail below 2.0 mm per report 11), or classify points with
   OCP's `BRepClass3d_SolidClassifier` and erode with scipy. (unverified)
5. **Machinability** (the `cnc` variant), from report 11's rules: every inside vertical edge has a
   fillet of at least the tool radius; no face whose normal points between up and down unless it is
   vertical (no undercut from top or bottom); every pocket depth is at most 3 x its narrowest width;
   holes are standard drill sizes. Each is a loop over faces and edges in build123d. (likely)
6. **Fit gates from board.toml.** Switch plate holes 14.0 mm, plate top 5.0 mm above the PCB, encoder
   shaft positions and button stem positions match board.toml within 0.05 mm. (likely)
7. **Exports read back.** Each of the 11 formats in report 11 is reopened and its bounding box
   compared with the solid's. (verified in report 11)

Unproven until hardware: print tolerances on the owner's printer, heat-set insert fit, keycap and
knob feel, light leakage round the displays, anodise and laser results.

### End to end against a real OBS

OBS 33.0.1 is installed as a Flatpak (verified `[X4]`). obs-websocket reads `--websocket_port`,
`--websocket_password` (which forces auth on) and `--websocket_debug` from the command line (verified
`[W9]`). `obs --help` lists `--multi`, `--profile`, `--collection` and `--safe-mode`; safe mode turns
WebSockets off, so never use it here (verified `[X4]`).

Manual recipe, not run today because the owner's OBS is open:

1. Use a throwaway config, never `~/.var/app/com.obsproject.Studio/config`. Override
   `XDG_CONFIG_HOME` for the Flatpak and pre-write `plugin_config/obs-websocket/config.json` with
   `server_enabled: true`. (unverified: whether the Flatpak honours the override)
2. `xvfb-run flatpak run com.obsproject.Studio --multi --websocket_port 4456 --websocket_password <test>`.
   Port 4456 keeps clear of the owner's 4455.
3. Run the host build of the device client against `ws://127.0.0.1:4456`: identify, list scenes,
   switch scene, toggle mute on one input, read a volume, receive the matching events.
4. Run the same script against the fake server. Any difference is a fake-server bug to fix.

This stays manual. It is not in CI: GitHub runners have no OBS and installing it per run is slow.

### CI on GitHub Actions

No `.github/` exists yet (verified `[L1]`). Public repositories run standard runners free; a private
repo on GitHub Free gets a monthly dollar allowance instead of a fixed count of minutes (verified
`[W10]`). One workflow, three jobs, all calling `just` so local and CI agree:

1. `test` on `ubuntu-24.04`: gcc, clang fuzz smoke, cargo test/clippy/fmt, python3 checks.
   Target under 2 minutes.
2. `pcb` in `container: kicad/kicad:9.0.9`: build the board, ERC, DRC, netlist check. Upload the DRC
   JSON and Gerbers as artifacts.
3. `build` on `ubuntu-24.04`: firmware UF2 through `firmware/Dockerfile`, the Tauri shell after
   installing the apt list, the CAD exports with the case gates. Upload the UF2, the app bundle and
   the CAD files.

Pin actions by commit SHA, `permissions: contents: read`, no secrets (nothing needs one).

## Definition of done per module

| Module | Done when (all without hardware) |
|---|---|
| Firmware core | Every SDK-free unit has host tests under ASan/UBSan in `just test`; fuzz targets for parser, config, WS and JSON run 200k inputs clean; golden frames for each screen state committed. |
| Firmware image | `just firmware` builds the UF2 for RP2350B with `-Werror`; size report under flash and RAM budget; CI uploads it. |
| OBS client | Passes every fake-server script; every request type it sends exists in the pinned `protocol.json`; one manual real-OBS run logged in `docs/`. |
| Protocol | C and Rust both pass every line of `vectors.txt`; `docs/protocol.md` lists every message; CI checks the four files move together. |
| Config app core | Read config, edit, write, read back equals, against the fake port; malformed and partial replies rejected; `cargo test` and clippy clean. |
| App shell | Builds in CI on Ubuntu 24.04; launches under xvfb and exits 0. |
| board.toml binding | `check_pins.py` checks firmware, host and the KiCad netlist. |
| PCB | 4 layers; ERC 0 errors; DRC 0 errors; 0 unconnected; 0 parity issues; two builds byte-identical; Gerber set and BOM read back. |
| CAD | Every part valid and single-solid; 0 mm³ interference with the PCB STEP; meshes watertight; min wall 2.0 mm; CNC variant passes the machinability loop; all exports reopen. |
| CI | All three jobs green on `main`; artifacts attached. |

## Bring-up checklist for the first hardware

Do these in order. Stop at the first failure.

1. **Bare board, unpowered.** Visual check; ohmmeter: 5 V to GND and 3V3 to GND not shorted.
2. **Current-limited power.** Bench supply 5 V, limit 100 mA, on VBUS. Measure 3V3 (3.3 V ± 3 %).
   Idle current recorded.
3. **Boot ROM.** Hold BOOTSEL, plug USB: the RP2350 mass-storage drive appears (`lsusb`, `dmesg`).
4. **Flash.** Copy a blink-and-banner UF2. CDC-ACM appears; the banner prints the flash JEDEC ID
   (W25Q128JV is `EF 40 18`, check against its datasheet).
5. **Debug port.** SWD connects (debug probe or a second Pico running debugprobe); read the chip id.
6. **Inputs.** A test image prints each event: 9 keys, 4 buttons, 3 encoders both ways, 3 pushes.
   Press every key with others held to prove the diode matrix has no ghosting.
7. **Displays.** Init each panel; draw colour bars and the golden frames; compare by eye with the
   committed PPMs. Measure backlight current at full and dimmed.
8. **Config link.** The app finds the pad, reads its config, writes a change, power-cycles, reads it
   back equal.
9. **Network link.** CDC-NCM interface comes up on the PC; the pad gets a DHCP lease; `ping` works;
   the firewall rule from report 03 is added once.
10. **OBS.** The pad identifies with OBS, switches a scene, mutes an input, shows source names and
    levels on the narrow display. Unplug and replug OBS and USB; the pad reconnects without
    replaying a command.
11. **Soak.** 8 hours connected with meters on; no reset, no heap growth on the CDC stats line.
12. **Case.** The PCB drops into the printed case without force; keys, buttons and knobs clear their
    holes; USB plug seats fully.

## Skipped or not checked, and the risk

- Wall-thickness gate not run (`rtree` missing in `cad/.venv`). Risk: a thin wall reaches the CNC
  shop. Fix before the first CNC quote.
- Real-OBS run not done (owner's OBS open). Risk: a fake-server mismatch with OBS 33. Low; the fake
  follows protocol.json, and report 05 read the source.
- Wokwi, Renode and Espressif QEMU not run. Risk: none for done; they are not in the plan.
- USB NCM, lwIP on target and the firewall stay unproven until a dev board runs report 03's spike.

## Sources

- `[L1]` `/home/worxbend/Projects/macropad-obs/justfile`; `just test` run 2026-11-18 (0.66 s); no
  `.github/` directory.
- `[L2]` `firmware/test/vectors.txt`, `host/src/protocol.rs:267`, `:342`.
- `[X1]` Fake OBS experiment, `/tmp/tmp.DhJ7y0t295/fake_obs.py` and `client.mjs` (scratch, outside
  the repo).
- `[X2]` `qemu-system-arm -machine help`, `qemu-system-xtensa -machine help` (QEMU 11.1.3, local).
- `[X3]` `docker run kicad/kicad:9.0.9 kicad-cli pcb drc --help`, `sch erc --help`,
  `sch export netlist --help`.
- `[X4]` `flatpak list`, `ps -p 3649717`, `ss -ltnp`, `obs --help` via `flatpak run --command=obs`,
  `~/.var/app/com.obsproject.Studio/config/obs-studio/plugin_config/obs-websocket/config.json`
  (read only).
- `[X5]` clang libFuzzer smoke run; `which xvfb-run valgrind clang-tidy shellcheck`.
- `[X6]` CAD gate experiment, `/tmp/tmp.ywJXfBbVV6/gate.py` with `cad/.venv/bin/python`.
- `[W1]` Wokwi, board-pi-pico-2 reference: https://docs.wokwi.com/parts/board-pi-pico-2
- `[W2]` Espressif QEMU docs: https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/README.md
  and https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/esp32s3/README.md
- `[W3]` Community Renode RP2040 feature coverage:
  https://xiao-seeed-rp2040-renode.readthedocs.io/en/latest/FEATURE_COVERAGE/
- `[W4]` Wokwi CI getting started: https://docs.wokwi.com/wokwi-ci/getting-started
- `[W5]` obs-websocket generated docs: https://github.com/obsproject/obs-websocket/tree/master/docs/generated
- `[W6]` Renode supported boards: https://renode.readthedocs.io/en/latest/introduction/supported-boards.html
  (first 100 kB read; no RP2040, RP2350 or ESP32 entry)
- `[W7]` Tauri 2 prerequisites: https://v2.tauri.app/start/prerequisites/
- `[W8]` Tauri 2 WebDriver: https://v2.tauri.app/develop/tests/webdriver/
- `[W9]` obs-websocket `src/Config.cpp`:
  https://raw.githubusercontent.com/obsproject/obs-websocket/master/src/Config.cpp
- `[W10]` GitHub Actions billing: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- Reports 03, 04, 05, 06, 07, 09, 11, 13 in `docs/research/`.

## Open questions

1. May a CI job and the manual E2E use a throwaway OBS instance on this machine while the owner's OBS
   runs, on port 4456? Or only when the owner's OBS is closed?
2. Is the repo public on GitHub? It sets the CI cost (free on public, an allowance on private).
3. May `rtree` (or `manifold3d`) be added to `cad/pyproject.toml` for the wall-thickness gate?
4. Is a cloud simulator (Wokwi) acceptable at all, given it uploads the firmware to a third party? This
   report does not need it.
5. Does the Flatpak OBS honour an `XDG_CONFIG_HOME` override, so the E2E never touches the real
   config? Must be tried once with the owner's OBS closed.
6. Which debug probe will the owner use for step 5 of bring-up?
