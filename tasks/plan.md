# Build plan: macropad-obs v2

Next action: 3.6 (Tauri commands over the core), then 3.7, 3.8 and 3.9.

Source of truth, in this order: `docs/spec/decisions-v2.md` (owner, final), `docs/spec/spec-v2.md`
(approved 2026-11-18), `docs/spec/layout-v2.toml` rev 2c (rev 3 in 1.4a), `docs/research/`. Task
cards with acceptance, verification, dependencies and files are in `tasks/todo.md`.

## Overview

1. An ESP32-S3-WROOM-1-N16R2 pad that dials obs-websocket 5 over Wi-Fi (D1, D7).
2. 3x3 MX keys, 4 B3F buttons, 3 EC11 push encoders, a 3.5 in panel and a 142x428 strip.
3. Config over one USB CDC link, read and written both ways. Secrets go in, never out (D2, R1).
4. Secrets sit in plain NVS. No eFuse is burnt (D8).
5. Then a Tauri 2 app, a 4-layer routed board, and a style A case, printed first and then milled.

## Architecture decisions the plan rests on

| Decision | Source |
| --- | --- |
| Core C11 with no IDF headers, tested on the host; the IDF port is a thin layer | spec 5, 10 |
| Paths: `firmware/core/`, `firmware/test/`, `firmware/esp32s3/main/pins.h`, `host/obs_core/` | spec 12, R3 and R6 |
| The four protocol files and the four config files change together (config from 1.9, with a stub `config.c`) | spec 12, R3 |
| `just test` gains padsim end to end and stays without KiCad, IDF or `cad/.venv` | spec 12, R4 |
| `layout-v2.toml` rev 3 feeds `board.toml`; `tools/check_measure.py` exits 1 while a listed MEASURE is open: no board order | spec 7, 9 step 6, R5 |
| The spike (spec 9 step 1) is Phase 0 and its record S.3 feeds `board.toml` | spec 9, 14 |
| Greycode generator, nyxilab exporters and macropad CNC drawings get copied with MIT or CERN-OHL-S headers; the sibling repos are never edited | D5, spec 12 |
| Freerouting 2.5.0 is fetched by sha256 and never committed. It runs in local `eclipse-temurin:25-jre` with `--network none` | D5, R09 `[F1]` |
| KiCad uses the local `kicad/kicad:9.0.9` (generate, DRC) and `kicad/kicad:10.0.7-full` (STEP: the plain tag has no 3D models) | spec 10; `docker images`, 2026-11-19 |
| Hardware-only acceptance lives in [HW] tasks (S.1, 4.8, 4.9, Phase 8). No agent marks them done | spec 11, 13 |

## Dependency graph

```
spike S.1 + mock-up S.2 (needs 6.1) ─> S.3 record ─┬─> 4.6, 4.7 (f_bus, power cap)
                                                    ├─> 5.3b FPC footprints ─> 5.12 re-run
                                                    └─> board order (H.1)
contracts (P1) ─┬─> fw core (P2) ─┬─> padsim ─> app core (P3) ─> Tauri shell + UI (P3)
                │                 └─> IDF port (P4, needs the IDF image) ─> 4.8 dev kit [HW]
                ├─> pcb (P5): 5.1-5.11 provisional on placeholder FPC footprints after 1.4b
                │      └─> board STEP ─> case interference (P6)
                └─> case (P6): params and body after 1.4b
code checkpoints ─> docs (P7)
Checkpoints 5, 6 ─> fab quotes F.1, F.2, print F.3 ─> boards H.1 ─> bring-up and criteria H.2-H.11
D6 + Checkpoint 4 ─> 4.9 real app and firmware update
```

## Phases (counts, then where the cards are)

| Phase | Tasks | Cards | Checkpoint |
| --- | --- | --- | --- |
| 0. Spike | 3 | S.1-S.3 | S.3 exit: narrow panel in hand, pin table read, outline calipered |
| 1. Contracts | 12 | 1.1-1.10 (1.4a/b, 1.6a/b) | `just test` green; protocol vectors agree in C and Rust |
| 2. Firmware core | 21 | 2.1-2.18 (2.11a/b, 2.14a/b, 2.17a/b) | padsim e2e (criteria 4, 4c, 5, 8, 9) in `just test` |
| 3. App | 9 | 3.1-3.9 | 4b in `just test`; `just app-check` exits 0, once approved |
| 4. ESP-IDF port | 9 | 4.1-4.9 | merged image; 4.8 dev kit acceptance recorded |
| 5. PCB | 13 | 5.1-5.12 (5.3a/b) | DRC 0/0/0, ERC clean, fab set and STEP, after 5.12 |
| 6. Case | 11 | 6.1-6.10 (6.2a/b) | every export reads back; no interference with the board STEP |
| 7. Docs | 3 | 7.1-7.3 | README table matches a fresh run |
| 8. Fab and hardware | 14 | F.1-F.3, H.1-H.11 | criteria 2, 3, 5, 6, 7, 11, 15 and the bring-up and manual rows measured |
| **Total** | **95** | | |

## Parallel lanes

1. **Phase 0:** S.1 starts as soon as the IDF image is approved, beside Phase 1. S.2 needs 6.1.
   S.3 needs both, plus 1.3 and 1.4a.
2. **Phase 1:** G-rules is approved (2026-11-19). 1.1 and 1.2 go one after the other, because both move files.
   After 1.2, three lanes: (a) 1.4a, then 1.4b and 1.5 in parallel; (b) 1.6a, 1.6b, 1.7, then 1.8
   (the four protocol files, one task at a time); (c) 1.9 and 1.10. 1.3 joins (a) and (b): it runs
   after 1.4a (`board.toml`) and 1.6b (it reads `USB_VID`/`USB_PID` from `protocol.rs`). 1.10 lands
   before 1.8. **3.1 runs beside all of Phase 1**, as spec 9 step 2 says.
3. **Phase 2:** lane A is 2.1 then 2.5. Lanes B (2.2), C (2.3), D (2.4) and E (2.6, Python) are
   independent. They join at 2.7. 2.9, 2.10 and 2.11a form a lane after 2.2; 2.11b joins after
   2.8. 2.13, 2.14a and 2.14b form the UI lane after 2.9. 2.16, 2.17a, 2.17b and 2.18 come last.
4. **Phases 5 and 6** start beside Phase 2 once 1.4b lands. Inside Phase 5, 5.1 first (it brings
   back `pcb-test`), then 5.2 and 5.3a in parallel; 5.8 to 5.10 are sequential. 5.3b and 5.12 wait
   for S.3. Phase 6 runs 6.1 to 6.7 and 6.10 beside Phase 5. Only 6.8 waits for 5.11.
5. **Phase 4** waits for the IDF image approval and Checkpoint 2. 4.2, 4.3, 4.5 and 4.6 are
   parallel after 4.1; 4.4 follows 4.3 (`cred_nvs.c`). 4.6 and 4.7 also wait for S.3.
6. **Must stay sequential:** any two tasks that touch `board.toml`, `layout-v2.toml`,
   `vectors.txt`, `config_vectors/` or `CLAUDE.md`.

## What the old tree keeps, moves or deletes

Per `docs/research/02-repo-inventory.md`. A file is deleted only in the task that lands its
replacement. Tests are deleted only with the code they test.

| Path | Verdict | Task |
| --- | --- | --- |
| `firmware/src/*`, `firmware/CMakeLists.txt`, `firmware/Dockerfile`, the `firmware` recipe (Pico SDK, never built) | delete | 1.1 |
| `firmware/link.[ch]`, `firmware/input.[ch]`, `firmware/test/test_link.c`, `test_input.c`, `vectors.txt` | move to `firmware/core/`, adapt | 1.2, then 1.6b, 2.3 |
| `firmware/pins.h` | replace with `firmware/esp32s3/main/pins.h` | 1.3 |
| `firmware/st7789.*`, `font8x16.*`, `test/test_st7789.c` | delete when `fw-ui` lands | 2.14b |
| `host/src/protocol.rs`, `config.rs` | move to `host/obs_core/src/`, adapt. Keep `Secret`, 0600 and atomic save. Drop the `wss://`-only rule (`config.rs:215`) | 1.2, 1.6b, 1.9 |
| `host/src/bridge.rs` and its 2 tests (in-memory v1 port; no PC process under D1) | move, then delete | 1.2, 1.6a |
| `host/src/lib.rs`, `keymap.rs`, `paging.rs`, `profile.rs`, `volume.rs`, `obs.rs` | port to C `fw-actions` and `fw-obs`, then delete. Fix the RESUMED-as-off bug, do not port it | 2.8, 2.12 |
| `app/src-tauri/Cargo.toml` `obs_core` path | `../../host` becomes `../../host/obs_core` | 1.2 |
| `board.toml` | rewrite from `layout-v2.toml` rev 3 | 1.4a, then 1.3 |
| `docs/spec/layout-v2.toml`, `docs/images/layout-v2.png` | bump to rev 3, redraw | 1.4a |
| `tools/check_pins.py` | rewrite | 1.1, 1.3 |
| `justfile` | adapt. `pcb-test`, `cad-check` and `cad` leave in 1.4b and return in 5.1, 6.1 and 6.2a | each |
| `pcb/gen/*`, `pcb/kicad/*`, `pcb/fab/*` (0 copper) | delete; greycode generator replaces them. The `test_circuit.py` rules come back from `git show d3f75a2:pcb/gen/test_circuit.py` | 1.4b, 5.1, 5.4 |
| `cad/obs_case/geometry.py`, `numbers.py`, `cad/exports/*` (old wedge) | delete. The dial comes back from `git show d3f75a2:cad/obs_case/geometry.py` | 1.4b, 6.10 |
| `cad/build.py`, `cad/obs_case/export.py` | cut to import cleanly (no `numbers`, no `geometry`), then extend | 1.4b, 6.2a, 6.5 |
| `cad/obs_case/render.py`, `cad/pyproject.toml` | keep, extend | 6.9 |
| `app/src-tauri/src/session.rs`, `main.rs`, `app/ui/index.html` | replace | 3.6, 3.7 |
| `app/src-tauri/src/pad.rs` | adapt: find the port without a fixed path | 3.2 |
| `app/src-tauri/src/logbuf.rs`, `app/udev/70-macropad-obs.rules`, `.gitignore` | keep. The udev rule gains 303a:1001 | 3.9 |
| `docs/design.md`, `docs/protocol.md`, `docs/obs.md`, `README.md`, old `docs/images/*.png` | replace or regenerate | 1.6b, 7.2, 7.3, 6.9 |
| `docs/images/sketch.jpg`, `docs/spec/`, `docs/research/`, `tools/draw_layout.py` | keep (untracked today) | none |
| `.grok/workflows/` | remove. Ask first (spec 12) | owner |
| `LICENSE`, `LICENSE.cern-ohl-s` | add full texts and a holder. Ask first | owner |

## Gates that need the owner

| Gate | Blocks | Spec |
| --- | --- | --- |
| G-rules: the six rule texts of spec 12. **Approved 2026-11-19** (`decisions-v2.md`); each `CLAUDE.md` edit still needs the owner in session | 1.2 (R3 protocol), 1.3 (R6), 1.5 (R5), 1.9 (R3 config), 1.10 (R1, R2; before 1.8), 2.18 (R4) | 12 |
| D6: `webkit2gtk-4.1`, `xdotool`, udev rule, ufw rule (sudo) | `just app`, 3.6 (or 3.9), 4.9 (criteria 13, 14) | 3 |
| Pull `espressif/idf:v6.1.1` (4.2 GB) | S.1 and all of Phase 4 | 10, 12 |
| New dependencies: LwJSON v1.10.1, `espflash` 4.7.0, a 4 bpp font source, `cc`, `serialport` in the `host/` workspace (libudev in `just test`) | 2.2, 3.5, 2.14a, 3.4, 3.2 | 12 |
| Node as a toolchain for UI tests (default: no; logic is tested in Rust) | 3.7, 3.8 | 10, 12 |
| `app-check` apt packages in an image built from the local `kicad/kicad:10.0.7` | 3.9, then 3.6-3.8 | 10, 12 |
| `tools/check_docs.py` in `just test` (only if wanted) | 7.1 | none |
| FreeCAD for `FCStd` (not installed here; nyxilab's `freecad_doc.py` imports `FreeCAD`) | the FCStd part of 6.6 | R11 |
| pid.codes PID (until then VID/PID stay at their current values, tagged pending) | 1.3, 3.9, 4.2 | 12 |
| Hardware in hand: DevKitC-1, both panels, a printer, a logic analyser, a VBUS meter | S.1-S.3, 4.8, 4.9, Phase 8 | 9, 11, 14 |
| JLCPCB upload, CNC quote, board order, milling order | F.1, F.2, H.1, H.11 | 9 step 6 |

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| RF: metal is 0.4 to 9.0 mm from the antenna, against Espressif's 15 mm (spec 7, 14) | High | Three stages (spec 14): S.3 mock-up, H.10 print case, H.11 CNC case, each RSSI and Hello/Identify against open air. A fail goes back to the owner |
| The antenna feed side is MEASURE (the module is mirrored on the bottom face) | High | 5.3a reads the footprint; S.3 confirms. `check_measure.py` lists it |
| Narrow panel (N279) is by quote; its tail and FH12 vs FH12A are open | High | 5.3a places marked `PLACEHOLDER_*` FPC footprints; 5.6-5.11 are provisional; 5.3b and 5.12 redo them after S.3 |
| VBUS over 500 mA | Med | 4.7 sets the cap from S.3's 3V3 current. H.8 measures VBUS |
| Unbounded OBS JSON | Med | Streaming reader with 500-item fixtures (2.2) and a throttled 75 kB reply (2.17b) |
| Removing `pcb-test`, `cad-check` and `cad` in 1.4b looks like weakening `just test` | Med | They test only the deleted wedge. `check_numbers.py` lands in 1.4a. 5.1 and 6.1 bring the recipes back into `just test`. A reviewer confirms before merge |
| The app cannot be built before D6 (`webkit2gtk-sys` build script fails here) | Med | Core tests against padsim. 3.1 uses `cargo check --keep-going`. 3.6-3.8 verify through `app-check` once approved |
| Hardware criteria could be claimed from padsim | Med | [HW] tag; values only from the owner's measurement in `docs/devkit.md` or `docs/hardware.md` |

## Open questions (spec 15)

| # | Question | Blocks |
| --- | --- | --- |
| 1 | D6 (sudo installs) | 3.6 path, 4.9, `just app` |
| 1 | Fixed LAN address for the OBS PC, and a DHCP reservation for the pad? | 4.8, H.3, H.4 test setup; `obs.url` default in 1.9 |
| 1 | 2.4 GHz coverage where the pad sits? | H.10, H.11 test spot |
| 1 | Insert colour against the black anodise (default black)? | 6.3 |
| 2 | Plunger: B3F-1060 (default), -1020 or -1050? | 6.10 cap, 6.2a deck holes |
| 3 | Screws M2 or M2.5, how many, which heat-set insert? | hole table in 1.4a, 6.3 |
| 4 | Is 350 cd/m2 enough? | panel choice; H.9 by eye |
| 4 | Meters or fader dB; REC/LIVE time or clock? | 2.14a, 2.14b goldens |
| 4 | Cyrillic, 9 keys or key pages (button 4)? | [later] unless asked; 2.14a fonts, 2.12 |
| 4 | In-app firmware update wanted? If not, 3.5, 4.9's update half and criterion 14 drop | 3.5, 4.9 |
| 5 | Printer bed size (longest part about 170 mm)? | F.3, 6.4 print split |
| 5 | Country (import tax)? | F.1, F.2, H.1 |
| 5 | Logo to engrave? | 6.7 |
| 5 | Keycap colour? | DSA keycap purchase (spec 6) |
| 5 | Is the repo public? If so, CI runs `app-check` on `ubuntu-24.04` | 3.9 (CI half) |
