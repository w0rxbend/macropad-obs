# 01. Prior art in the owner's earlier macropad projects

Research only, 2026-11-17. This file is the only file written. Confidence tags: **verified** (read or
run today in the primary source), **likely** (stated in a project document, not re-run), **unverified**.

## Recommendation

Rebuild this repo on the `macropad-greycode` PCB generator and process, add the case extras from
`macropad`, and take the two-display firmware pattern and the export formats from `macropad-nyxilab`.
Do not extend this repo's `pcb/gen`: it has no router, no schematic writer and no DRC step.

Next action: get the owner's answer to open questions 1 and 2 (licence of the sibling code, and the
OBS password rule). Both block the first build slice.

Three findings carry the recommendation.

1. **Copper was really routed, twice, by an in-repo Python grid router.** No autorouter program, no
   hand routing. I re-ran KiCad 9.0.9 DRC today on scratch copies of both boards: 0 violations,
   0 unconnected, 0 schematic parity issues, each. (verified)
2. **`macropad-nixylab` exists. It is spelled `macropad-nyxilab`.** Path
   `/home/worxbend/Projects/macropad-nyxilab`. A search for `*nixylab*` finds nothing. It is the only
   earlier project with two colour displays, one of them a tall narrow bar. (verified)
3. **No earlier project reached hardware, and no Tauri window was ever built.** Every claim in the
   three repos is a design-file claim. (verified for the statements; see section 3)

## The four projects

| | macropad | macropad-greycode | macropad-nyxilab | macropad-obs (here) |
|---|---|---|---|---|
| Controls | 12 MX, 2 EC11 | 3x3 MX, 1 EC11 | 12 MX matrix, stick or knob | 3x3 MX, 1 EC11 |
| Display | nice!view 160x68 | 1.3" OLED 128x64 | 1.9" 170x320 + 2.25" 76x284 ST7789 | 2.4" 240x320 ST7789 |
| MCU | RP2354A | RP2040 + W25Q128JVS | Pico 2 module | RP2040 + W25Q128JVSIQ |
| PCB | 4 layers, 827 tracks | 4 layers, 892 tracks | none, hand-wired | outline and 4 holes, 0 tracks |
| Case exports | STEP, STL, SVG, PDF, DXF | STEP, STL | STEP, STL, 3MF, GLB, FCStd, SVG, PDF | STEP, STL, 3MF |
| Firmware | Rust, embassy | QMK/Vial + pure C link | C++, Arduino-Pico, PlatformIO | C, Pico SDK, TinyUSB |
| Host | none | Rust daemon + Tauri configurator | Rust daemon | Tauri 2 + obws |
| Commits | 20 | 1 design commit | 43 | 29 |

Sources: each repo's `README.md`, `board.toml`, `git log`; track counts by `grep -c '(segment'` on
`pcb/kicad/*.kicad_pcb` (827, 892, 0). All verified today.

## 1. The build process to copy

The process is recorded in three places: the commit history, the repo rules (`CLAUDE.md`), and the
workflow scripts that built `macropad` and `macropad-greycode`. The scripts are session artefacts
outside the repos (paths in Sources). Copy the pattern into this repo's plan, because those files can
be deleted at any time.

### Phase A. Lock the decisions before any agent builds

1. Ask the owner the layout, MCU, firmware stack, host and slice order. Write the answers down.
   greycode did this on 2026-11-14, one day before the build. (verified: greycode memory note)
2. Write `board.toml` first. It holds pins, positions and the mechanical contract between `pcb/`
   and `cad/`. (verified: `macropad-greycode/board.toml` `[pcb]` and `[case]` tables)
3. Write the wire format document and the shared test vectors before the two parsers.
   (verified: `macropad-greycode/docs/protocol.md`, `firmware/test/vectors.txt`)
4. Write the repo rules: generated files are never hand-edited, never weaken a check, keep `MEASURE`,
   status numbers come from command output. (verified: both `CLAUDE.md` files)

### Phase B. Build in slices that own disjoint directories

1. One build agent per slice, in parallel: case, PCB, firmware, host or app. Each agent writes only in
   its own directories. (verified: `greycode-roadmap` script, `SLICES`)
2. Shared files (`README.md`, `justfile`, `board.toml`, `CLAUDE.md`) are off limits. A slice returns
   `requested_changes`, `readme_section` and `justfile_recipes` as data. The orchestrator applies them.
3. Each brief names the sibling code to read first and says "adapt, do not copy blindly".
4. Each brief says what is not installed (for example `webkit2gtk-4.1`) and forbids installing it.
5. Each agent returns a schema: files changed, each check command with its real output, open points,
   what was not verified.

### Phase C. Verify, then fix

1. A fresh read-only reviewer per slice re-runs every check and tries to prove the work wrong:
   faked requirements, checks that cannot fail, numbers that do not match output, values duplicated
   out of `board.toml`. Findings carry a severity and file evidence.
2. A fix agent runs only when a finding is high or medium (blocker or major). It returns the full
   report again, not a delta.
3. A docs agent runs after the areas finish. It copies numbers from the reports into `README.md`.
4. A read-only final check runs the top-level test and compares the result with the plan, item by item.
   (verified for all four steps: `macropad-prototype-ready` script, phases Implement, Review, Fix,
   Docs, Final check)

### Phase D. Harden the firmware in review loops

nyxilab ran this twice, five loops each: three fresh reviewers with one lens each, one sceptic per
finding who tries to refute it, one implementer who writes the test first, one gate agent who reviews
the loop diff, runs the tests and commits locally. Each round carried a list of handled and rejected
findings into the next. (verified: both `*review-loops*` scripts)

### Phase E. Stage the prototype with a pass test per step

`macropad/docs/prototype.md` is the model: A measure the bought parts, B order the PCB, C print
coupons and then a case, D bring up the board, E gate before paying for CNC. The owner's words here
("prototype that will be printed and then CNC") match it step for step. (verified)

### The PCB method in detail

| Step | Tool | Source | Conf. |
|---|---|---|---|
| Netlist as Python, with a self-check | `pcb/gen/circuit.py` | greycode `pcb/README.md` | verified |
| Place, planes, keep-outs, rules | `pcb/gen/layout.py`, pcbnew in Docker `kicad/kicad:9.0.9` | `pcb/kicad.sh` | verified |
| Route | `pcb/gen/router.py`: A* on a 0.1 mm grid, F.Cu and B.Cu only, 45° moves, no rip-up | file docstring | verified |
| Routing order | `route.py` plan plus `route_order.txt`, found by `build.py order` (10 to 12 min, can fail) | both `pcb/README.md` | likely |
| Schematic | written from `circuit.py` with KiCad's own symbols; ERC; netlist compared pin by pin | `schematic.py` | likely |
| DRC | `kicad-cli pcb drc --severity-error --schematic-parity --exit-code-violations` | `pcb/Makefile` | verified, re-run today |
| Board against `board.toml` | `contract.py`, 8 groups | greycode `pcb/README.md` | likely |
| Byte-repeatable rebuild | `make -C pcb repeat`, seeded KiCad UUIDs | `pcb/Makefile`, `build.py` `KIID_SEED` | likely |
| Order files | 11 Gerbers, PTH and NPTH drill, BOM, placement, `board-sha256.txt`, cross-checked | `fab.py`, `git ls-files pcb/fab` | verified |

Inner layers are planes only: In1 is 5 V with 3.3 V and 1.1 V islands, In2 is ground. Every
machine-placed part is on the bottom face. (verified: both `pcb/README.md`)

Freerouting was the first plan in `macropad` (version 2.5.0, in a Java container). One day later the
commit "Route the board in code" replaced it with the grid router. No reason is recorded.
(verified: `git show 6a202e7:Makefile`, commit `9978369`)

The plain generator tests pass today without Docker: 48 in greycode, 37 in macropad. (verified:
`python3 -B -m unittest discover -s pcb/gen -p 'test_*.py'`)

### The case method in detail

1. build123d model in a `uv` venv. `spec.py` holds case-only numbers; board numbers are read from
   `board.toml` at run time. (verified: greycode `cad/README.md`)
2. `build.py check | export | render | draw | all`. `check` writes `exports/checks.json` and exits 1
   on a failure. (verified: `macropad/cad/build.py`)
3. Checks: a self-test that feeds known-bad shapes to the checks, pairwise interference, named
   clearances, wall thickness, CNC tool reach and inside-corner radius, layer-by-layer print bridges.
   (likely: `macropad/README.md` "What is checked")
4. Every exported STEP and STL is read back and compared with the solid. This check exists because
   OCCT once wrote `base.step` as an open shell while the solid in memory was sound.
   (verified: `macropad/cad/macropad_case/roundtrip.py` docstring)
5. Print and CNC are two variants of one model. Laser artwork is flat DXF, not geometry.
   (verified: `macropad/cad/macropad_case/spec.py`, `signature.py`, `drawings.py`)

### Test discipline

- `just test` or `make test` needs no Docker and no hardware. Docker steps are separate recipes.
- Protocol logic is pure C or C++ with no SDK headers, built natively under ASan and UBSan.
- One vector file feeds both parsers. nyxilab goes further: `host/tests/interop.rs` compiles the
  firmware parser and runs it against the Rust encoder.
- A pin check script binds firmware and host constants to `board.toml`.
- A docs check fails when a Markdown file names a file that does not exist.

(verified: `macropad-greycode/justfile`, `macropad-nyxilab/Makefile`, `macropad/Makefile`)

## 2. Reusable assets

All paths are read-only references. Copying needs the owner's licence decision (open question 1).

### PCB generator. Base: `/home/worxbend/Projects/macropad-greycode/pcb/`

| Path | Use | Change needed |
|---|---|---|
| `gen/router.py`, `gen/test_router.py` | Grid router and its 15 tests. Differs from macropad's by 2 lines | none |
| `gen/circuit.py` | RP2040, W25Q128JVS, crystal, USB-C, ESD, fuse, AP2112K, BOOT, RESET, probe pads | drop the SK6812 and level-shifter blocks; add displays, 3 encoders, tact row |
| `gen/layout.py` | Planes, hole keep-outs, exposed-pad paste windows, placement checks | new plane islands |
| `gen/route.py`, `gen/route_order.txt` | Routing plan | rewrite the plan; keep the helpers and length checks |
| `gen/schematic.py`, `sheet_layout.py`, `symlib.py`, `sexpr.py` | Schematic writer and 19 tests | new sheet layout |
| `gen/contract.py`, `gen/fab.py`, `gen/build.py`, `Makefile`, `kicad.sh` | Contract, order files, build steps | new contract groups |
| `lib/greycode.pretty/MX_Hotswap.kicad_mod`, `Hole_M2.kicad_mod`, `QFN-56-...ViaWindows.kicad_mod`, `lib/SOURCES.txt` | Footprints with provenance | pad pattern of the socket is MEASURE |

Take four more things from `/home/worxbend/Projects/macropad/pcb/gen/`: the PCBWay centroid and BOM
writer and the do-not-populate check in `fab.py`; `build.py:_check_rules_reach_drc`; the plated
ground-bond hole (`Hole_M2_Ground.kicad_mod`, `layout.py:check_ground_bond`); `test_order_files.py`.

### Case

| Path | Use |
|---|---|
| `macropad/cad/macropad_case/checks.py`, `measure.py`, `selftest.py`, `roundtrip.py`, `printsim.py` | Check suite, self-test, export read-back, print simulation |
| `macropad/cad/macropad_case/coupons.py` | Print coupons cut from the real parts |
| `macropad/cad/macropad_case/drawings.py`, `signature.py` | CNC sheets (SVG, PDF) and laser DXF with `MARK` and `REF` layers |
| `macropad-greycode/cad/greycode_case/checks.py`, `spec.py` | CNC-only checks; reads `board.toml` at run time |
| `macropad-nyxilab/common/cad/macropad_cad/export.py`, `freecad_doc.py`, `fit_tests.py` | 3MF, GLB and FreeCAD export; fit tests |
| `macropad-nyxilab/common/cad/macropad_cad/params.py` (`Display19`, `DisplayBar`) | Module sizes of the two ST7789 displays. Every value is MEASURE for this project |

`params.py` gives the bar module as 73.15 x 21.08 mm with a 55.29 x 14.80 mm active area, 76 x 284
pixels, ST7789P3. I did not read a datasheet for it. MEASURE. (likely)

### Firmware

| Path | Use |
|---|---|
| `macropad-obs/firmware/link.c`, `link.h`, `test/vectors.txt`, `host/src/protocol.rs` | Framed CDC codec, CRC-16/MODBUS, session rule. Holds up as the configuration transport |
| `macropad-obs/firmware/input.c`, `st7789.c`, `font8x16.c` and their tests | Debounce, quadrature, ST7789 command builder. Sized for 9 keys, 1 knob, 1 panel |
| `macropad-nyxilab/common/firmware/lib/nyx_ui/src/ui/` | Two panels on two SPI buses, off-screen canvases, only changed rows pushed |
| `macropad-nyxilab/rotary/firmware/src/quad_decoder.h`, `tools/ui_sim/`, `common/firmware/host_tests/` | Detent-synchronised decoder, UI simulator on the PC, mocked TinyUSB tests |
| `macropad/firmware/core/src/quadrature.rs`, `hardware_test.rs`; `macropad/tools/check_hid.py` | EC11E18244AU A-edge decoder, bring-up test mode, HID descriptor check |

### Host and app

| Path | Use |
|---|---|
| `macropad-obs/host/src/` (`obs_core`, 22 tests) | Config file with `0600` and `Secret`, paging, volume gate, `Bridge<P: Port>` |
| `macropad-obs/app/src-tauri/src/session.rs`, `docs/obs.md` | obws 0.15 connect sequence and event list. Never compiled here |
| `macropad-greycode/configurator/core/` (32 tests) | Edit, validate, conflict check, atomic save, with no Tauri runtime |
| `macropad-greycode/configurator/ui/`, `src-tauri/` | No-build HTML and ES modules tested with `node --test`; thin shell with bundling off |
| `macropad-nyxilab/host/tests/interop.rs`, `host/tests/peer.cpp` | Cross-language protocol test |

### Documents and CI

- `macropad/docs/prototype.md`, `ordering.md`, `assembly.md`, `parts.md`, `flashing.md`.
- `macropad/.github/scripts/check_docs.py`.
- `macropad-nyxilab/.github/workflows/ci.yml`, `release.yml`, `.github/requirements/*.txt`
  (hash-locked, wheel-only Python tools).

## 3. What failed or stayed unfinished

### macropad

| Finding | Source | Conf. |
|---|---|---|
| Nothing built: no board, print or flash | `README.md` Status | verified |
| Freerouting dropped after one day | commits `6a202e7`, `9978369` | verified |
| Router has no rip-up. Moving R4 beside pin 60 failed three times | `pcb/README.md` | likely |
| Design rules did not reach `kicad-cli` DRC until the generator wrote `.kicad_pro` | `pcb/README.md` Design rules | likely |
| `base.step` was written as an open shell; found only by the read-back check | commit `82ffde8`, `roundtrip.py` | verified |
| Knob could not seat (shaft flat is 10 mm, MEASURE, not full length); decoder lost clicks | `macropad-prototype-ready` script, CAD task 1, firmware task 1 | verified |
| Four WIP commits hold unchecked files from a running workflow. Two of them record a PC reset or shutdown mid-run | commits `90f7918`, `6a0b16b`; `9206641`, `07ec37a` | verified |
| Bottom-side placement rotation not settled; no licence file; CI never ran on GitHub | `README.md` | verified |

### macropad-greycode

| Finding | Source | Conf. |
|---|---|---|
| Nothing built. All slices landed in one commit of 199 files | `git log`, `README.md` | verified |
| Tauri window never built: `webkit2gtk-4.1` missing | `configurator/README.md` | verified |
| Two length checks were loosened after the first route (USB mismatch 2.0 to 3.0 mm, stub 6 to 8 mm) | `pcb/README.md` Open points | verified |
| Mechanical values lived outside `board.toml` (BOOT and RESET holes, OLED module size, USB overhang) | `pcb/README.md`, greycode status note | verified |
| LED current about 0.9 A at full white behind a 500 mA fuse | `pcb/README.md` | likely |
| Case brief asked for four M2.5 corner screws; the geometry forced seven M2 | `cad/README.md` | verified |
| OLED row 7 bug open; UI font glyphs are GPL-2.0; add-on never run in FreeCAD | `configurator/README.md`, `README.md` | verified |
| QMK build needs a 1 GB clone and the unpinned image `ghcr.io/qmk/qmk_cli:latest` | `justfile` | verified |

### macropad-nyxilab

| Finding | Source | Conf. |
|---|---|---|
| No PCB at all. Nothing to reuse for copper | `README.md` | verified |
| Host bridge "Not tested on real hardware"; fix commits say "Not tested on hardware" | `docs/host-bridge.md:166`, commit `64cbcee` | verified |
| Module sizes came from photos; 16 `MEASURE` tags in `params.py` | `docs/design.md`, `grep -c` | verified |
| `app.cpp` glue has no native test | `firmware-review-loops-round-2` script, `PRIOR` | verified |
| FreeCAD export needs `freecadcmd`; renders need EGL. `freecadcmd` and `pio` are not on this machine | `CLAUDE.md`, `command -v` | verified |
| Working tree has 11 modified files today. It is in use; treat it as moving | `git status` | verified |

### macropad-obs: the plan here and where it left the sketch

`docs/design.md` (2026-11-15) is the original plan. It was built in five commits inside three minutes
(22:36 to 22:38), one per planned pull request. The 22 commits after 2026-11-16 09:37 touch only
`cad/`, `docs/` and `.grok/`: three `.grok/workflows/*.rhai` loops that restyled and audited the case
until a "clean agent" accepted it. Firmware, host, app and PCB did not change again. (verified)

| Owner's words or sketch | `docs/design.md` and the tree | Source |
|---|---|---|
| "2 displays one bigger and one longer" | One 2.4" panel. "2.8 inch and larger: Rejected" | `design.md:688` |
| Three rotary knobs with push | One EC11 | `board.toml [knob]` |
| "one tray of buttons", 4 small tactile buttons | None. Only BOOT and RESET under the floor | `board.toml [pcb]` |
| "firmware on the device should be communicating with this websocket OBS url" | "The pad never opens a socket". App holds obws. "Wi-Fi on the pad: Rejected" | `design.md:14`, `:680` |
| "bidirectional configuration" stored on the device | Config is a TOML file on the PC. No frame reads config back | `docs/protocol.md` |
| "3x3 keys matrics" | Direct GPIO. "Rejected a matrix" | `design.md:700` |
| "4layers or more PCB" | 4 layers declared, 0 tracks, 0 vias, 4 footprints | `pcb/kicad/macropad-obs.kicad_pcb` |
| "all the export format", print then CNC, laser engraving | STEP, STL, 3MF. No DXF, no drawings, no coupons, no print or CNC variant | `cad/exports/` |

Also unfinished here: the firmware was never cross-compiled (`just firmware` not run, no
`arm-none-eabi-gcc`), the app was never built, and PID `1209:4F42` is not registered.
(verified: `README.md`, `command -v`)

### Work no earlier project covers

1. Two FPC display connectors on a routed board. Every earlier display sat on a pin header.
2. Three encoders, a tact-button row, or a diode key matrix on a PCB.
3. Any network path from firmware to OBS, and any WebSocket client in firmware.
4. Configuration stored on the device and read back by an app.
5. A built Tauri window, and any hardware bring-up.

## Repo rules that meet the owner's words

Flagged, not decided.

1. **"No OBS password in a CDC frame."** If the firmware talks to OBS itself and OBS authentication
   is on, the device needs the password. The rule and the working reading cannot both hold as written.
2. **LCSC exception `FH12-20S-0.5SH(55)` `C596730`.** It was chosen for the 20-pin 2.4" panel. A
   different display may need a different connector, and the exception then names an unused part.
3. **`tools/check_pins.py` binds `firmware/pins.h` and `host/src/protocol.rs`.** The rule holds in
   spirit. The file names change if the firmware stack changes.
4. **"No SK6812."** No conflict. The LED blocks in the sibling generators must be removed on import.

## Not checked

- I did not re-run ERC, the `board.toml` contract, the byte-repeat build, `make cad` or any firmware
  build in the sibling repos. Those results are "likely".
- I did not run `just test` here; the task brief states it passes.
- Risk: the router has only been proven on boards with one MCU, header-mounted displays and no
  fine-pitch connector besides the QFN. A denser board may not reach 0 unrouted.

## Sources

Process:
- `~/.claude/projects/-home-worxbend-Projects-macropad/2fcd5683-c96b-4b59-b94a-6faa240582f5/workflows/scripts/macropad-prototype-ready-wf_cea2afa7-7c5.js`
- `~/.claude/projects/-home-worxbend-Projects-macropad-greycode/8217369e-254e-4440-845a-050855448a74/workflows/scripts/greycode-roadmap-wf_1c90e02c-6bf.js`
- `~/.claude/projects/-home-worxbend-Projects-macropad-nyxilab/44ae9fe7-286c-4936-b353-76d9ded3cb1d/workflows/scripts/` (two `*review-loops*` scripts)
- `~/.claude/projects/-home-worxbend-Projects-macropad-greycode/memory/greycode-design-decisions.md`, `greycode-status.md`

`/home/worxbend/Projects/macropad`:
- `README.md`, `CLAUDE.md`, `Makefile`, `board.toml`, `git log` (20 commits, tags `v0.1.0`, `v0.2.0`)
- `pcb/README.md`, `pcb/gen/*.py`, `pcb/routing.txt`, `pcb/kicad/macropad.kicad_pcb`, `pcb/lib/SOURCES.txt`
- `cad/README.md`, `cad/build.py`, `cad/macropad_case/*.py`
- `docs/prototype.md`, `docs/ordering.md`

`/home/worxbend/Projects/macropad-greycode`:
- `README.md`, `CLAUDE.md`, `justfile`, `board.toml`, `docs/architecture.md`, `docs/protocol.md`
- `pcb/README.md`, `pcb/Makefile`, `pcb/gen/*.py`, `pcb/kicad/greycode.kicad_pcb`
- `cad/README.md`, `configurator/README.md`

`/home/worxbend/Projects/macropad-nyxilab`:
- `README.md`, `CLAUDE.md`, `Makefile`, `.github/workflows/ci.yml`, `release.yml`
- `docs/host-bridge.md`, `docs/design.md`, `common/firmware/README.md`
- `common/cad/macropad_cad/params.py`, `export.py`, `rotary/firmware/include/config.h`

`/home/worxbend/Projects/macropad-obs`:
- `docs/design.md`, `docs/protocol.md`, `docs/obs.md`, `docs/images/sketch.jpg`
- `README.md`, `CLAUDE.md`, `board.toml`, `justfile`, `git log` (29 commits)
- `.grok/workflows/case-apple-form.rhai`, `case-industrial.rhai`, `case-assembly.rhai`

Commands run today:
- `kicad-cli pcb drc --severity-error --schematic-parity --exit-code-violations` in
  `kicad/kicad:9.0.9`, on scratch copies of both sibling `pcb/` trees
- `python3 -B -m unittest discover -s pcb/gen -p 'test_*.py'` in both sibling repos
- `command -v` for the tool list; `pkg-config --exists webkit2gtk-4.1` (missing)

## Open questions

Blocking the first build slice:

1. The three sibling repos have no licence file. This repo's design said that is why it vendors
   nothing (`docs/design.md`, key decision 16). May their generators, footprints and case code be
   copied here under MIT and CERN-OHL-S-2.0? The owner owns all four.
2. What replaces "No OBS password in a CDC frame" if the firmware talks to OBS: authentication off
   in OBS, a different transport for the secret, or the rule retired?

Not blocking:

1. Was a `macropad-nyxilab` unit ever printed and wired? If yes, its display modules can be measured
   now and several MEASURE tags closed before layout.
2. Does "3x3 keys matrics" mean an electrical diode matrix, or only a 3 x 3 grid? No sibling PCB has
   a matrix.
3. The small-button row in `docs/images/sketch.jpg` appears to show five or six cells (my count on a
   rough pencil sketch). The owner's answer is four. Confirm four.
4. Should the board house be PCBWay (as in `macropad`) or JLCPCB (as in greycode)? The two need
   different BOM and placement files.
5. Why was Freerouting dropped in `macropad`? If it was only a tooling problem, it stays a fallback
   for a board the grid router cannot finish.
