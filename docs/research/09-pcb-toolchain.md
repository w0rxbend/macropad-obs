# 09. A real routed 4-layer PCB from code

Research only, 2026-11-18. This file is the only file written. An earlier pass was interrupted. This
pass re-ran every experiment in a new scratch directory and kept only what reproduced. Confidence
tags: **verified** (run today, or read today in the primary source; web pages were read through a
fetch tool that returns extracted text), **likely**, **unverified**. Keys such as `[F2]` point into
the Sources list. No dimension in this report comes from a datasheet, so none carries MEASURE.

## Recommendation

Port the `macropad-greycode` PCB generator into `pcb/gen` and keep KiCad 9.0.9 in Docker as the
builder and the judge. Write the critical copper in code and lock it. Give the remaining signal nets
to Freerouting 2.5.0, headless, on the two outer layers only. Nothing is drawn in a GUI.

Next action: route a placement-only spike of the new board (RP2350B, the two FPC connectors, the 3x3
key matrix with its diodes, the RP2350 core-regulator loop, the three encoders and the four tact
buttons) through this pipeline. It is the one thing this report could not test. The greycode board
behind every routing number here is an RP2040 (QFN-56, internal LDO) with 9 direct-wired keys, one
encoder and no FPC, so none of those new parts has been routed by either tool.

Five findings carry the recommendation.

1. **The owner's generator already does this, repeatably.** A copy of `macropad-greycode/pcb` rebuilt
   its 4-layer board in 94 s: 96 footprints, 55 nets, 0 unrouted pads, ERC clean. The board file is
   byte-identical to the committed one (sha256 `17e881e9...`). (verified, `[X3]`)
2. **Freerouting works as the bulk router when the critical copper is locked first.** On that board,
   20 nets kept, 35 autorouted in 37 to 40 s. KiCad 9.0.9 and 10.0.7 both report 0 violations, 0
   unconnected, 0 parity issues. Two runs gave the same session file. (verified, `[X5]`)
3. **Freerouting alone fails.** Same board, no kept copper: 91 DRC errors, 9 unconnected, 179
   segments cut into the two plane layers. (verified, `[X5]`)
4. **pcbnew in Docker is the only headless board API today.** The IPC API needs a running GUI in
   KiCad 9 and 10: "Support for running in headless mode through `kicad-cli` was added for KiCad
   11." `[K3]` The pcbnew module carries a SWIG deprecation warning in both images (`pcbnew.py`
   line 63); it shows only when Python warnings are enabled (`-W always`), not on a plain import.
   (verified, `[K3]` `[X1]`, re-run in the Verification section)
5. **KiCad 10 is not a free upgrade.** The generator stops after 1 s on 10.0.7: the USB-C symbol
   lost pin `S1`. The 9.0.9 schematic gets 65 ERC warnings there. (verified, `[X3]` `[X4]`)

## The pipeline

One `just pcb` recipe, five stages. Each stage fails the build on its own gate.

1. **Netlist.** `circuit.py`: parts, nets and positions from `board.toml`. Pure Python, so its tests
   stay on `just test`.
2. **Schematic.** The s-expression writer draws `circuit.py` with KiCad's library symbols. Then
   `kicad-cli sch erc` and `kicad-cli sch export netlist`, compared pin by pin with `circuit.py`.
3. **Board.** pcbnew places every footprint, the outline, the planes, the rule areas and the design
   rules. `route.py` draws the critical copper and locks it.
4. **Bulk routing.** Export a Specctra DSN from a copy without the outer pours. Run Freerouting.
   Import the session with a seeded UUID generator. Add the pours, fill on a reloaded board.
5. **Judge and export.** `kicad-cli pcb drc`, the `board.toml` contract, then Gerbers, drill, BOM,
   placement list and STEP.

The Freerouting call that passed, in `eclipse-temurin:25-jre` with `--network none`:

```
java -jar freerouting-2.5.0.jar -de board.dsn -do board.ses -dr outer.rules -da \
  --gui.enabled=false --router.automatic_neckdown=false --user_data_path=<build dir>
```

`outer.rules` holds `(layer_rule In1.Cu (active off))` and the same for `In2.Cu` inside
`(autoroute_settings ...)`. Both settings are documented in `[F2]`. (verified, `[X5]`)

## Acceptance gates

| Gate | Pass condition | Command or check |
|---|---|---|
| Schematic | 0 errors, 0 warnings; netlist equals `circuit.py` | `kicad-cli sch erc --severity-all --exit-code-violations` |
| Connectivity | 0 unconnected, also on the copy without outer pours | `kicad-cli pcb drc --severity-error --exit-code-violations` |
| Rules | 0 violations, 0 parity issues; length and skew limits hold | add `--schematic-parity`; limits in `<board>.kicad_dru` |
| Contract | board equals `board.toml`; no track on In1 or In2; two builds byte-identical | pcbnew asserts, `cmp` |
| Outputs | order files match the board hash; STEP holds the expected solids | `fab.py`, count `CLOSED_SHELL` |

Four notes on the gates.

1. Outer ground pours hide a ground pad that has no via. `macropad-greycode` checks a pour-less copy
   first. Keep that. (verified in `build.py`, `[L1]`)
2. `kicad-cli` reads the rules from the `.kicad_pro` beside the board. `macropad-greycode` proves it
   on every build with a probe project that must fail. Keep that too. (verified, `[L1]`)
3. Length and skew can live in KiCad instead of Python. A `.kicad_dru` with `length` and `skew`
   constraints made `kicad-cli pcb drc` report `length_out_of_range` and `skew_out_of_range` in both
   images. (verified, `[X6]`) The manual says KiCad manages that file `[K4]`; a generated project
   writes it the same way it writes `.kicad_pro`.
4. The DRC gates run at `--severity-error`. At `--severity-all` the clean greycode board reports 64
   `lib_footprint_issues` warnings in the 9.0.9 image, because the container has no global
   footprint library table (the project table lists only `greycode`). A warning-free DRC gate needs a
   global `fp-lib-table` in the build container, or must stay at error severity. (verified, re-run
   in the Verification section)

## Who routes what

| Share | What | How |
|---|---|---|
| All footprints | Placement | Code. Keys, knobs, buttons, connectors and holes from `board.toml`; the rest in `circuit.py` |
| About a third of the nets, half of the copper | Supply pads to planes, decoupling, core regulator loop, crystal, USB pair, QSPI flash, backlight current | Code, locked. Limits in `.kicad_dru` |
| The rest | Matrix rows and columns, encoders, display SPI, buttons, debug | Freerouting, F.Cu and B.Cu only |
| None | GUI edits | A hand fix goes back into `route.py` as coordinates, or the next build loses it |

The shares are the greycode numbers: 20 of 55 nets and 586 of 1105 copper items were kept.
(verified, `[X5]`) The new board should land near them. (unverified: greycode has an RP2040 with an
internal LDO, so no core-regulator loop was kept, and its 9 keys are wired straight to GPIO with no
matrix and no diodes, `[L1]` `README.md` and `gen/circuit.py`. Two rows of this table, the core
regulator and the matrix, have no routed evidence yet.)

Antenna: none on the first-choice MCU, RP2350B over USB (report 04). If the ESP32-S3 module is
chosen, the antenna is on the module and the board needs only a keep-out rule area. (likely, not
re-read here)

## Options compared

Routing.

| Option | For | Against |
|---|---|---|
| A. Code for critical nets, Freerouting for the rest (recommended) | Clean on greycode in 40 s. Rip-up router. Deterministic | 64.6 MB GPL-3.0 jar and a JRE image. Two settings must be right |
| B. The owner's grid router for everything | Proven on two boards. No new tool. Byte-identical rebuild in 94 s | No rip-up. Moving parts can need `build.py order`, about 12 min by its README `[L1]` |
| C. Freerouting for everything | Least code | Fails: 91 errors, 9 unconnected |
| D. KiCadRoutingTools | MIT, CLI on `.kicad_pcb`, KiCad 9 and 10 `[O4]` | "No push-and-shove" `[O4]`. Not tested here |
| E. KiCad itself | Nothing to install | No batch autorouter. `kicad-cli pcb` has no route command in 9.0.9 or 10.0.7 `[X1]` |

Option B is the fallback if a GPL Java tool in the build is not wanted. The router code comes over
in either case: `route.py` draws the critical copper with it.

Netlist and schematic.

| Option | For | Against |
|---|---|---|
| Own Python netlist and schematic writer (recommended) | In hand, ERC clean, 272 pins checked against KiCad's netlist | Tied to the KiCad 9 symbol library |
| SKiDL | "SKiDL supports KiCad 5 through 10", own ERC `[O1]` | New dependency, absent from both images, not tested |
| atopile, circuit-synth | Circuit as code | Layout stays manual: "place and route in KiCad" `[O2]`, "PCB layout and routing with KiCad's tools" `[O3]` |
| KiCad IPC API | The supported future | Needs a GUI until KiCad 11; "only support IPC API plugins in the PCB Editor" `[K3]` |

## What the experiments showed

All run today in `/tmp/pcb09b.8divAS`, outside the repo, containers on `--network none`.

| Key | Run | Result |
|---|---|---|
| `[X1]` | Versions | `kicad-cli` 9.0.9 (Python 3.11.2) and 10.0.7 (3.13.5). Both have `ExportSpecctraDSN`, `ImportSpecctraSES`. No Java, no 3D models in either |
| `[X2]` | 10-footprint board from pcbnew only, DSN, Freerouting, SES, DRC | 0 violations, 0 unconnected in both images. 5 s. Default settings put 26 of 75 segments on the planes |
| `[X3]` | `build.py place` on a greycode copy | 9.0.9: 94 s, sha256 equal to the committed board. 10.0.7: `AssertionError`, USB-C symbol has no pin `S1` |
| `[X5]` | greycode, critical copper locked, Freerouting | Clean with the call above. Neck-down left on: 83 errors. Defaults: 67 errors, 7 unconnected, 252 plane segments |
| `[X7]` | Order files from the routed board | 11 Gerbers, PTH and NPTH drill, position CSV, BOM, IPC-D-356, IPC-2581: all written by `kicad-cli` 9.0.9 |

Pitfalls found on the way. Each is a build check, not a note.

1. **Freerouting's own verdict is not usable.** Exit code 0 with unrouted nets. On the clean run it
   still logged "2 unrouted" on `/USB_D_P`, a locked net that KiCad sees as connected. (verified)
2. **Neck-down breaks the minimum width.** It writes 0.10 and 0.12 mm tracks against a 0.127 mm
   rule. `--router.automatic_neckdown=false` fixes it. (verified)
3. **With the planes closed, Freerouting does not connect supply pads.** Every supply pad needs a
   via placed in code. (verified, `[X2]`)
4. **Lengths depend on who measures.** XOUT is 8.10 mm in the generator's report, 11.19 mm in KiCad
   9.0.9 and 11.25 mm in 10.0.7. Set limits against the pinned judge. (verified, `[X6]`)
5. **Board-edge clearance is not settled.** Freerouting's log shows a 0.25 mm edge clearance; the
   KiCad rule is 0.3 mm. Failed runs had 9 to 16 edge errors, the clean run none. Edge keep-out
   strips are the fix if it returns. (verified for the numbers; the fix is untested in this pass)

## STEP for the case

1. `kicad-cli pcb export step --subst-models` works, but exits 0 when every model is missing. The
   gate must count solids. (verified, `[X8]`)
2. The base images hold no 3D models. `kicad/kicad:10.0.7-full` does, and it resolves
   `${KICAD9_3DMODEL_DIR}` in a 9.0.9 board: 5 solids instead of 1. (verified, `[X8]`)
3. VRML block models do not reach the STEP. The greycode board exports as 1 solid and 81
   placements with no solid. (verified, `[X8]`)
4. The library has models for the 6 mm tact button and the FH12 10, 12, 20 and 40 pin connectors.
   It has none for MX switches, the EC11 encoder or a QFN-80. (verified in the image)
5. So `models.py` must write STEP blocks for those parts and for the two display modules. Report
   11 owns the choice between this STEP and a board solid built from `board.toml`.

## What to reuse

1. **Take from `macropad-greycode/pcb/gen`:** `build.py`, `layout.py`, `route.py`, `router.py`,
   `schematic.py` with its three helpers, `contract.py`, `fab.py`, and the tests. (verified, `[L1]`)
2. **Take from `macropad/pcb/gen`:** the core-regulator routing and its checks. That board has an
   RP2354A with the inductor loop, keep-outs and a 4 mm limit on `VREG_LX` in code. (verified, `[L2]`)
3. **Drop from this repo:** `pcb/gen/kicad_board.py`. Its board has 4 footprints, 0 tracks and
   two-layer Gerbers while `board.toml` says 4 layers. The "planned routes" in `circuit.py` are
   straight lines from the origin. (verified, `[L3]`)
4. **Keep from this repo:** the rule that `circuit.py` imports no pcbnew, so `just test` needs
   neither KiCad nor Java.

Conflicts with the repo rules. None is decided here.

1. The greycode netlist carries SK6812 LEDs and a level shifter. `CLAUDE.md` says no SK6812. They
   go on the port.
2. Its LCSC cells were checked in another repo. Here they return to `UNVERIFIED`, except the three
   locked ones.
3. Freerouting is GPL-3.0 `[F3]`. Fetch the jar by sha256 into `.build`; do not commit it beside MIT
   and CERN-OHL-S files.

## Not checked, and the risk

No part of the new board was placed or routed. RP2350B is a QFN-80 and the big display needs a
40-pin 0.5 mm connector; neither router has seen them. The Freerouting result is one board and one
placement. Freerouting's native CLI archive, SKiDL, KiCadRoutingTools and KiBot were read about, not
run. The jar was not downloaded in this pass: it is the earlier pass's download, and its sha256
equals the digest GitHub publishes for the release asset. (verified, `[F1]`)

## Sources

- `[K3]` KiCad developer documentation, IPC API for add-on developers:
  <https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/index.html>
- `[K4]` KiCad 10.0 PCB Editor manual, custom design rules and the actions reference:
  <https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html>
- `[F1]` Freerouting release v2.5.0, published 2026-10-05; `freerouting-2.5.0.jar`, 64 599 107
  bytes, sha256 `f6f51bb02245e8e717f9359bd260cc9c5c0b1bc0acc8b7cb2cd5b8ffeb5de3c7`:
  <https://github.com/freerouting/freerouting/releases/tag/v2.5.0>
- `[F2]` Freerouting 2.5.0 settings and command line:
  <https://raw.githubusercontent.com/freerouting/freerouting/v2.5.0/docs/settings.md>,
  <https://raw.githubusercontent.com/freerouting/freerouting/v2.5.0/docs/command_line_arguments.md>
- `[F3]` Freerouting README (Java 25, GPL-3.0): <https://github.com/freerouting/freerouting>
- `[O1]` SKiDL README: <https://github.com/devbisme/skidl>
- `[O2]` atopile README: <https://github.com/atopile/atopile>
- `[O3]` circuit-synth README: <https://github.com/circuit-synth/circuit-synth>
- `[O4]` KiCadRoutingTools README: <https://github.com/atomic14/KiCadRoutingTools>
- `[L1]` `/home/worxbend/Projects/macropad-greycode/pcb/` (`README.md`, `Makefile`, `gen/build.py`,
  `gen/contract.py`, `routing.txt`)
- `[L2]` `/home/worxbend/Projects/macropad/pcb/` (`README.md`, `gen/route.py`, `gen/layout.py`)
- `[L3]` `/home/worxbend/Projects/macropad-obs/pcb/` (`gen/kicad_board.py`, `gen/circuit.py`,
  `kicad/macropad-obs.kicad_pcb`, `fab/gerbers/`)
- `[X1]` to `[X8]` Scratch runs in `/tmp/pcb09b.8divAS` (scripts in `scripts/`, logs in `out/`).
  Images: `kicad/kicad:9.0.9`, `kicad/kicad:10.0.7`, `kicad/kicad:10.0.7-full`,
  `eclipse-temurin:25-jre`. `[X4]` is the baseline DRC and ERC of the greycode project in both
  images; `[X6]` the custom-rule run; `[X8]` the STEP exports. The directory is temporary.

## Open questions

1. Is a GPL-3.0 Java tool acceptable in the PCB build, fetched and not committed? "No" selects
   option B.
2. Stay on KiCad 9.0.9, or port the generator to 10.0.7 now? This report says stay, and use
   10.0.7-full only for the STEP.
3. Does the new placement route? Only the spike in "Next action" answers it.
4. Which limits go into `.kicad_dru`? Report 10 gives the USB pair geometry; the crystal, flash and
   regulator limits exist only as numbers in the two earlier generators.
5. Does the case CAD read the KiCad STEP, or build the board solid from `board.toml`? (report 11)

Next action: the placement-only spike of the new board.

## Verification

Skeptic pass, 2026-11-18. Each claim below was re-checked in a primary source or by a command run in
this pass, in a new `mktemp -d` directory outside the repo, containers on `--network none`. Verdict:
corrected. 14 claims checked: 12 hold, 2 corrected (rows 5 and 12); row 8 adds a gate note.

| # | Claim | Source used | Result |
|---|---|---|---|
| 1 | Freerouting v2.5.0, published 2026-10-05, jar 64 599 107 bytes, sha256 `f6f51bb0...` | `gh api repos/freerouting/freerouting/releases/tags/v2.5.0`; `sha256sum` of the scratch jar | Holds. Size, digest and date match |
| 2 | Freerouting is GPL-3.0 and needs Java 25 | GitHub license API (`GPL-3.0`); README "Choose version `25`"; jar manifest `Created-By: 25.0.4.1`, class file major version 69 | Holds |
| 3 | `-de -do -dr -da --gui.enabled=false --router.automatic_neckdown=false --user_data_path=` and `(layer_rule <layer> (active off))` in a `.rules` file are documented | `docs/command_line_arguments.md` and `docs/settings.md` at tag v2.5.0 (raw.githubusercontent.com) | Holds. `-da` disables analytics; `automatic_neckdown` sits directly under `router`; `(active on\|off)` listed under `layer_rule` |
| 4 | IPC API needs a running GUI in KiCad 9 and 10; headless via `kicad-cli` added for KiCad 11; IPC plugins only in the PCB Editor | `[K3]`, read this pass | Holds, quotes verbatim |
| 5 | pcbnew "prints a deprecation warning in both images" | `python3 -c 'import pcbnew'` and `-W always` in both images; `grep` of `pcbnew.py` | Corrected. The warning is in `pcbnew.py` line 63 of both, but a plain import prints nothing; it shows only with warnings enabled |
| 6 | `kicad-cli pcb` has no route command in 9.0.9 or 10.0.7 | `kicad-cli pcb --help` in both images | Holds. 9.0.9: `drc, export, render`. 10.0.7: `drc, export, import, render, upgrade` |
| 7 | greycode rebuild byte-identical, 96 footprints, 55 nets | `sha256sum` of the committed board and of the scratch rebuild (both `17e881e9...`); footprint and net count in the committed file; `gen-9.0.9.log` | Holds. 96 footprints; 56 named nets minus net 0 gives 55, plus 19 `unconnected-` singletons |
| 8 | Locked copper + Freerouting gives 0 errors, 0 unconnected, 0 parity; two runs give the same session | Re-ran `kicad-cli pcb drc --schematic-parity` on a copy of `hybA-routed`; diffed `hybA.ses` and `hybA2.ses` | Holds at error severity. The two sessions differ only in the session name on lines 1 and 2. At `--severity-all`: 64 `lib_footprint_issues` warnings, all from the missing global footprint table. Note added to the gates |
| 9 | Failure numbers: full 91 errors / 9 unconnected / 179 plane segments; neck-down 83; defaults 67 / 7 / 252 | Scratch logs `full.txt`, `hybA3.txt`, `hybD.txt` | Holds. 123 + 56 = 179 and 160 + 92 = 252 plane segments. Freerouting logs "started with 42 unrouted nets" against the report's 35 autorouted nets; it counts connections differently, not checked further |
| 10 | KiCad 10.0.7 run stops: USB-C symbol has no pin `S1` | `gen-10.0.7.log` | Holds: `AssertionError: J1: Connector:USB_C_Receptacle_USB2.0_16P has no pins ['S1']` |
| 11 | 10.0.7-full has models for the 6 mm tact switch and FH12 10/12/20/40, none for MX, EC11 or QFN-80 | `ls` and `find` in `/usr/share/kicad/3dmodels` of `kicad/kicad:10.0.7-full` | Holds. `SW_PUSH_6mm*.step` and `Hirose_FH12-{10,12,20,40}S-0.5SH...step` present; no file matching EC11, Cherry_MX, QFN-80 or RP2350 |
| 12 | Greycode shares predict the new board; RP2350B is a QFN-80; `macropad` has a 4 mm `VREG_LX` limit | greycode `README.md`, `gen/circuit.py`; Raspberry Pi silicon page (RP2350B: QFN-80, 10 x 10 mm, 48 GPIO); `macropad/pcb/gen/route.py` line 38 | Partly corrected. QFN-80 and the 4.0 mm `VREG_LX` limit hold. Greycode is an RP2040 (QFN-56, internal LDO) with 9 direct-wired keys and no diodes, so "should land near them" is downgraded to unverified and the core regulator and matrix rows have no routed evidence |
| | `.kicad_dru` `length` and `skew` constraints fire in both images | `dru-tight.kicad_dru` and both `drc-dru-tight.json` | Holds: 2 `length_out_of_range`, 1 `skew_out_of_range` in each |
| | greycode checks a pour-less copy and runs a rules probe that must fail | greycode `gen/build.py` lines 81, 180 to 202 | Holds |

Images used: `kicad/kicad:10.0.7-full` and `eclipse-temurin:25-jre` were already local (tagged
2026-11-12, `docker image inspect`); nothing was pulled in this pass.

Against the owner's requirements. Four layers: met, inner layers kept as planes. MX switches, the
6 x 6 mm tact row, three encoders and two FPC displays: in the part list, but none routed yet, and
MX, EC11 and the QFN-80 need STEP blocks written in code for the case export. STEP for the case: a
path exists, with the solid-count gate. The recommendation holds as a toolchain choice. Its evidence
is one simpler board, so the spike must include the parts named in the corrected Next action before
the toolchain is called proven.
