# 11. Case CAD: print first, then CNC, then laser engraving

Research only, 2026-11-18. Third pass: CNC Kitchen re-read and local claims spot-checked
(`_keep()` at `geometry.py` 174, `export_to_pcbway` at `exporters3d.py` 580, build123d 0.13.0).
Second pass: the first draft was re-read against its sources, corrected
with reports 06, 07 and 08, and cut by 30 %. The export experiments were run again. This file is
the only file written. Tags: **verified** (read or run in this pass, in a primary source or a local
file), **likely** (reasoned, or carried from the first pass and not re-read), **unverified**.
**MEASURE** marks a size that no datasheet drawing gives. Heights are above the PCB top face. Keys
such as `[J1]` point into Sources. Nothing was printed, milled, anodised or lasered.

Next action: the owner answers open questions 1 to 3. They fix the solids before any code is written.

## Recommendation

1. **One build123d source, two variants per part: `print` and `cnc`.** Rebuild `cad/` on the layout
   of `macropad/cad/macropad_case` `[L2]`. Do not extend `cad/obs_case`: it is the old device, and
   its `_keep()` helper hides failed cuts `[L1]`.
2. **A tub-shaped top shell, a flat bottom plate, two cover lenses, turned knobs and caps.** Keycaps
   are bought. Every shell feature is reachable from straight above or straight below.
3. **Design to the CNC rules, then relax for print.** Hidden inside corners get a radius of a third
   of the pocket depth; shallow show-face pockets get R 1.6. Walls 2.0 mm or more. No undercut.
   Blind M2 or M2.5 threads. The print variant swaps threads for heat-set inserts and widens fits.
4. **Legends and artwork are flat sketches, never cut into the solids.** They leave as DXF with a
   `MARK` layer and a `REF` layer, plus SVG and PDF. The laser runs last, after anodising.
5. **Export eleven formats and a manifest. Read every file back. Promote only what passes.** STEP
   AP214 is the master for shops. All eleven ran on this machine in this pass (section 8).

## Flags and conflicts

No repo rule contradicts the owner's words: "I need all the export format for 3d cad case, I will
start with prototype that will be printed and then CNC, and laser engraving to be stalish."

1. **`board.toml` is stale.** `[case]`, `[pcb]` and `[display]` describe the old device.
   `encoder_body` says 6.5 mm; Alps draws 4.5 mm `[L8]`. Not edited. (verified)
2. **The reports disagreed on corner radius.** The first pass used R 2.0 in a 12 mm cavity; report
   12 asks for R 4. Three shops give three rules (section 3). This pass takes the strictest for
   hidden pockets. The PCB corners are R 2.0 in `board.toml`: raise them or relieve the pocket.
3. **build123d is not pinned.** `cad/pyproject.toml` asks for `build123d>=0.13`, with no lock file.
   The AP242 recipe uses a private function. Pin 0.13.0. (verified `[L1]`)
4. **Privacy trap.** build123d 0.13.0 has `export_to_pcbway()`. It posts the STEP file to
   `pcbway.com` and opens a browser `[L7]`. The build must never call it. (verified)
5. **Radio.** An aluminium shell blocks a module antenna (reports 03, 04). The first-choice MCU is
   wired. A Wi-Fi build needs a plastic window or an antenna hole in the shell. (likely)

## 1. What to reuse

1. `cad/obs_case/numbers.py`: the idea only. Number checks import no build123d, so `just test`
   needs no venv. Drop `_keep()` in `geometry.py` (lines 174-180). (verified `[L1]`)
2. `macropad`: `spec.py` (variants, part numbers in the STEP product name) and `roundtrip.py` (STEP
   and STL read-back, sliver limits). (verified `[L2]` `[L3]`)
3. `macropad`: tool-reach check, print check, fit coupons, shop sheets, laser DXF. (likely `[L4]`)
4. `macropad-nyxilab`: 3MF through `Mesher`, GLB, FCStd through `freecadcmd`. (likely `[L6]`)

The `macropad` README says "No license file yet" `[L5]` (verified). See open question 5.

## 2. Parts

Body estimate: about 93 x 175 x 16 mm, flat, without knobs. It follows from the big panel pocket of
55.0 x 83.5 mm, the bar module of 24.38 x 69.43 mm, the 57.15 mm key block `[L8]`, 3 mm webs and
2.5 mm walls. Nothing is placed yet: MEASURE.

| Part | Prototype | Final | Notes |
|---|---|---|---|
| Top shell: deck, MX plate, walls, bosses | FDM | 6061, 2 setups | Lens recesses, key well, 4 cap holes, 3 bushing holes |
| Bottom plate, 2.5 mm | FDM | 6061, 1 setup | Counterbores and foot recesses outside |
| Two cover lenses, 1.0 mm | Laser-cut acrylic | Tinted acrylic or glass | Outline leaves as DXF |
| Three knobs | FDM or resin | Turned 6061 | 6 mm bore, M3 set screw on the flat |
| Four button caps | Resin | Turned 6061 | Flanged, trapped under the deck |
| Two display carriers, foam frames | FDM, cut foam | The same | Hidden. They hold the panels up |
| Nine DSA keycaps, screws, feet | Bought | Bought | Reference solids for the clash check |

Shell split:

| Option | For | Against |
|---|---|---|
| **A. Tub top, flat bottom plate (recommended)** | One complex part. The seam is under the body. | An 11.6 mm deep cavity. The USB opening is a notch in the rim. |
| B. Top shell and base tray, as in `macropad` `[L5]` | Code and checks exist. | Two complex parts, four setups, a seam on every side. |
| C. Plate, frame, plate | Every part is flat. | Two seams a side. A third part to colour-match. |

Height stack. Part sizes are verified in reports 06, 07 and 08 `[L8]`. Chosen values are estimates.

| Level | mm | Basis |
|---|---|---|
| Deck top, the show face. The lens top sits 0.07 lower | 8.0 | Chosen: a 3.0 mm key well |
| Deck underside. The lens ledge is 0.8 thick | 6.0 | Chosen: 2.0 mm deck, 1.2 mm lens recess |
| Panel face, under 0.5 mm of foam. Panels are 2.15 and 2.1 thick | 5.5 | Reports 06, 07 |
| MX plate top. Web 1.5 +0.1 | 5.0 | Cherry drawing, report 08 |
| EC11E body top. Bushing top 11.5, shaft end 24.5 | 4.5 | Alps drawing, report 08 |
| B3F body top. Square stem top 7.3, round plunger 7.0 | 3.4 | Omron drawing, report 08 |
| Inside face of the bottom plate | -5.6 | 1.6 mm board, 4.0 mm for sockets and leads: MEASURE |

The raised deck hides the encoder body, so only a 7.4 mm hole shows. It gives a cap flange 2.6 mm
between the switch body and the deck. It costs one printed carrier per display. (likely)

## 3. Design-for-CNC rules

All shop rules in this table are verified.

| Topic | Shop rule | Use here |
|---|---|---|
| Inside corner radius | JLCCNC: depth / 10 + 0.5, and R 0.5 only to 3 mm deep `[J1]`. SendCutSend: 1.587 mm, and 1/5 of the wall height `[S1]`. PCBWay: 1/3 of the depth `[P2]` | R 4.0 in the cavity, R 1.6 in the key well, R 2.1 for a lens of R 2.0 |
| Pocket depth | JLCCNC: best at 2 to 3 tool diameters `[J1]`. PCBWay: 4, at most 6 `[P2]` | The cavity is 1.5 diameters of an 8 mm tool |
| Walls | Metal 0.8 mm `[J1]` `[P2]`. SendCutSend: 1/8 of the height `[S1]`. JLCCNC: above 1.5 mm for bead blast `[J2]` | Walls 2.5, deck 2.0, plate web 1.6, ledge 0.8 |
| Threads | At most 3 diameters long; a blind hole keeps half a diameter plain `[J1]`. SendCutSend: model a plain hole `[S1]` | Blind, from below. Callout on the sheet |
| Tolerance | JLCCNC: +/-0.1 mm or worse with no drawing `[J1]`. PCBWay: to +/-0.01 mm on request `[P1]` | A 2D sheet for the fits: cut-outs 14.00 +0.05 / 0 after anodise |
| Finish | JLCCNC: Ra 3.2, strict Ra 1.6 `[J2]`. PCBWay: #120 bead blast, then Type II `[P1]` | Ra 1.6 on show faces, bead blast, anodise |

Setups:

1. Top shell, underside up: cavity, bosses, tap drills, through cuts, the USB notch.
2. Top shell, face up: key well, lens recesses, rim chamfer.
3. Bottom plate, outer face up: outline, counterbores, foot recesses.
4. The plate closes the USB notch. A rounded slot needs a third setup. The plug overmould was not
   read: MEASURE. (likely)
5. No undercut. `macropad` proves that from the model with a tool-reach check `[L4]`. (likely)

The MX cut-out needs corners of R 0.3 or less `[L8]`; JLCCNC mills R 0.5 at best `[J1]`. Use
dog-bone reliefs, as `macropad` did `[L5]`. (verified)

Anodising, from MIL-A-8625F `[M1]` (verified in the text layer of the scan):

1. Type II runs 0.00007 to 0.0010 inch (1.8 to 25 um). PCBWay quotes 8 to 12 um clear, 4 to 8 um
   colour `[P1]`.
2. Each coated surface grows by half the coat. At 10 um a 14.00 mm cut-out closes by 10 um.
3. A 60 degree thread changes 4 times that growth on its pitch diameter. JLCCNC leaves threads
   below M5 bare `[J2]`. At another shop, mask or chase them.
4. Sharp edges and inside corners coat badly: radius them first.
5. JLCCNC allows up to 4 rack marks and picks the places unless the drawing names them `[J2]`. Name
   them inside the cavity.

Colour varies between batches `[J2]`: anodise shells, knobs and caps together. The coat insulates:
mask one boss face for the case ground, as `macropad` did `[L5]`. (verified; the ground is likely)

## 4. How the same model stays printable

A `variant` argument changes only three things. Screw holes: a tap drill for `cnc`, a heat-set
insert pocket in the same boss for `print`. Fits: lens +0.10 mm a side against +0.15; cap holes
0.1 mm radial against 0.3. Bridges: `print` adds 0.2 mm skins under ledges, cut out afterwards `[L2]`.

1. FDM is accurate to about 0.2 mm. Moving parts need 0.3 mm. Overhangs print clean to 45 degrees.
   Walls come in steps of 0.45 mm `[U1]`. (verified)
2. Resin (Form 2, Clear, 0.1 mm layers): walls 0.4 mm, clearance 0.5 mm, holes 0.8 mm `[F1]`. Use
   resin for caps and knobs. (verified)
3. Heat-set inserts: "A blind hole should be slightly deeper than the length of the insert (approx.
   1 mm)" `[K1]`. The page gives no M3 hole size and no wall minimum in its text; it says to fit the
   bore to the insert bought and test it. Its M3 test part spans 4.0 to 4.4 mm holes: MEASURE.
   (verified)
4. Printed face down, the MX plate is a 60 mm roof. `macropad` printed its top on its side `[L2]`.
   Print in black: light filament glows through thin walls. (likely)
5. Print coupons first: an MX cut-out, a lens corner, an insert boss, a knob bore, a cap hole.

## 5. Displays: retention, window, light leaks

| Option | For | Against |
|---|---|---|
| Bare panel flush in an open pocket (the old design) | No extra part | The border and the backlight edge show. |
| **Lens on a ledge, panel under the ledge (recommended)** | The metal frames the picture. The lens needs no printed mask. | A 1.4 mm air gap. |
| Lens on a ledge, panel up through the window | A 0.3 mm air gap | The lens needs a black mask. |
| One lens across both displays | One part | A 90 mm lens flexes. Not what the sketch shows. |

1. **Recess.** A 1.0 mm lens on 0.13 mm tape in a 1.2 mm recess, ledge 2 mm wide. `macropad` marks
   these values as guesses `[L2]`. (likely)
2. **Window.** Active area plus 0.4 mm a side: 49.76 x 74.24 mm and 22.08 x 64.94 mm `[L8]`.
   Newhaven asks for 1.0 mm `[N1]`. The bar has only 1.55 mm of border. Settle it on the print.
3. **Retention.** A black foam frame sits between the ledge and the panel. A printed carrier stands
   on the PCB and holds the panel up. No glue. Newhaven: gaskets seal, they do not set the spacing
   `[N1]`. (verified)
4. **Tail.** Each tail passes through a board slot to a connector on the underside, plugged in
   before the bottom plate goes on. The big tail is 24.5 mm long `[L8]`. The bar tail: MEASURE.
5. **Light leaks.** A foam frame round each active area, a web between the displays, a wall between
   the display bay and the key bay, flanges on the caps. The print is not opaque; the metal is.

## 6. Knobs, keycaps and button caps

1. **Knobs.** The shaft is 6.0 mm with a flat from 14.5 mm up. The plain 7 mm bushing stands 3.5 mm
   proud of the deck. Push travel is 0.5 +/-0.3 mm `[L8]`. The CNC knob is turned: 6 mm bore, 8 mm
   counterbore, M3 set screw, knurl or flutes, 1.3 mm of air under it. Its top lands near 26 mm,
   8 mm above the keycaps. The print knob uses a D bore `[L2]`. (likely)
2. **Keycaps.** Buy nine blank DSA caps `[L8]`. The big display labels the keys. (likely)
3. **Button caps.** A floating cap: body through a deck hole, a 1.0 mm flange under the deck, a
   3.6 mm round bore. The bore takes the 2.4 mm square stem (diagonal 3.39 mm) and the 3.5 mm round
   plunger `[L8]`. Nothing is pressed or glued. (arithmetic on verified sizes; fits MEASURE)

## 7. Laser engraving on anodised aluminium

The laser removes the dyed coat. Protocase: the mark is light, and strongest on dark colours `[C1]`.
JLCCNC: one tone, "determined by the material and surface treatment", 0.03 to 0.1 mm deep `[J3]`.
No shop states the mark colour: ask for a photo. (verified)

1. **Files.** JLCCNC: DWG or DXF, CAD-exported, 1:1, with a 3 mm margin `[J3]`. Xometry: a vector
   file such as DXF, the font and character height, and a 2D drawing with the place `[X1]`.
   Protocase: minimum font 4 pt (1.42 mm) `[C1]`. (verified)
2. **Line width.** No shop states a laser minimum. JLCCNC's floor for UV print is 0.176 mm lines and
   2.117 mm text `[J3]`. Use strokes of 0.2 mm or more and text of 2.0 mm or more. DejaVu Sans at
   `font_size` 2.5 measured a mean stroke of 0.22 mm; bold 0.38 mm. (verified; the rule is chosen)
3. **One source.** A module returns one flat `Sketch` per face from `board.toml` positions. Each
   exports DXF (`MARK` shapes, `REF` outline and holes), SVG, and PDF at 1:1.
4. **Fonts.** Use `Text(..., font_path=...)` with a font file named in the repo. `font="Arial"` came
   out as DejaVu Sans here with no Python warning. (verified)
5. **Content.** Engrave only what never changes: a logo, knob index lines, the underside label. Keys
   and knobs are remapped in the app.

`ExportDXF` writes R2013 in millimetres and keeps the layers. Text arrives as `LINE` and `SPLINE`.
R12 fails: "SPLINE requires DXF R2000". The SVG and PDF hold outlines only. (verified)

## 8. Export formats, checks and pipeline

Run in this pass with build123d 0.13.0 and OCP 8.0.1.1 in `cad/.venv`, on a scratch tub (1 solid,
58 faces) outside the repo. All verified.

| Format | For | How | Read-back check | Result |
|---|---|---|---|---|
| STEP AP214 | Shops | `export_step` | Solids, `BRepCheck_Analyzer`, volume, product name, `FILE_SCHEMA` | Volume error 1e-14 |
| STEP AP242 | Newer CAD | Own writer, below | The same | Two runs byte-identical |
| BREP | Test cache | `export_brep` | `import_brep`, volume | Error 0 |
| IGES | Legacy CAM | OCP `IGESControl_Writer("MM", 1)` | `IGESControl_Reader` | 1 solid. Mode 0: 58 loose faces |
| STL | Slicers | `BRepTools.Clean_s`, `export_stl` | trimesh: watertight, winding, bodies, volume | Error 1e-5 |
| 3MF | Slicers | `Mesher().add_shape`, `.write` | `Mesher().read`: count, labels, unit | 2 parts, mm, labels back |
| GLB | Web viewer | `export_gltf(binary=True)` | Node names; extents x 1000 | Metres, Y up, open meshes |
| DXF | Laser, lens outlines | `ExportDXF` with layers | ezdxf `audit()`, layers, `$INSUNITS` 4 | 0 errors |
| SVG | Sheets | `ExportSVG`, `project_to_viewport` | `import_svg`: count, no `<text>` | 4 shapes back |
| PDF | Sheets, 1:1 templates | `rsvg-convert -f pdf` | `pdfinfo` size, `pdffonts` empty | A3, no fonts |
| FCStd | FreeCAD users | `FreeCADCmd` worker: read STEP, save, reopen | Solids, volume, valid, closed | 1.1.4: equal volume |

Limits to start from: solid count exact, B-rep volume within 1e-4, mesh volume within 0.1 %, no
face under 0.05 mm2 in a CNC STEP `[L3]`. Not worth writing: OBJ, AP203, Parasolid, SLDPRT.
SendCutSend takes only `.step` and `.stp`, one part per file `[S1]` (verified).

Five traps, each reproduced in this pass:

1. **AP242.** `export_step` writes AP214 even with `write.step.schema` set to `AP242DIS`. The
   writer below makes the header after the transfer. Then the file is AP242.
2. **Assemblies.** `export_step(part)` raises `RuntimeError: Failed to write STEP file` once `part`
   is a child of a `Compound`. Export the parts first.
3. **STL.** A shape keeps its finest mesh: fine then coarse gave 4056 triangles twice, and 448
   after `BRepTools.Clean_s`. `tolerance` is relative, not millimetres. Judge by volume error.
4. **Sections.** A section at Z 5.5 exports with the warning "Exporting non-planar shape to 2D
   format". Move it to Z 0 first.
5. **FreeCAD Flatpak.** The sandbox cannot see `/tmp`. Pass `--filesystem=<job folder>`. End the
   worker with `os._exit(0)` `[L6]`.

```python
from build123d.exporters3d import _create_xde   # private in 0.13.0: pin the version
STEPCAFControl_Controller.Init_s()
Interface_Static.SetCVal_s("write.step.schema", "AP242DIS")
writer = STEPCAFControl_Writer(XSControl_WorkSession(), False)
writer.SetColorMode(True); writer.SetLayerMode(True); writer.SetNameMode(True)
writer.Transfer(_create_xde(part, Unit.MM, auto_naming=True), STEPControl_StepModelType.STEPControl_AsIs)
header = APIHeaderSection_MakeHeader(writer.Writer().Model())   # after Transfer, not before
header.SetName(TCollection_HAsciiString(part.label))
header.SetTimeStamp(TCollection_HAsciiString(timestamp))
ok = writer.Write(str(path)) == IFSelect_ReturnStatus.IFSelect_RetDone
Interface_Static.SetCVal_s("write.step.schema", "AP214IS")       # the setting is global: reset it
```

The AP242 file holds the same B-rep and no tolerances: send AP214 unless a shop asks. The FCStd
holds one `Part::Feature` per solid and no feature tree. (verified)

Drawings: port `macropad/drawings.py` `[L4]`. Its SVG uses `<text>` with a font family (line 32):
outline the text or pin the font before the PDF step. (verified by reading)

Pipeline, one gate per step:

1. `numbers`: pure Python, runs in `just test`. Stack, fits, MEASURE tags present.
2. `geometry`: build both variants. Any exception fails. Each part is one valid closed solid.
3. `fit`: every pair of solids that must stay clear. A missing size stays "unverified equipment".
4. `rules`: tool reach from both sides, corner radius against depth, thinnest wall, print layers.
5. `export`: write under `.build/`, read back, replace `cad/exports/` in one move, write
   `manifest.json` with SHA-256 and tool versions. A skipped FreeCAD run is recorded as skipped.

## Not checked, and the risk

1. Nothing was built for this device. Every chosen case size is an estimate until the board is
   placed.
2. No shop was asked. Mark colour, laser accuracy and bead blast on a 1.6 mm web are open. Risk: a
   rejected file or a warped plate web.
3. Not re-read in this pass: the bodies of the `macropad` check modules. Their claims are tagged
   likely. CNC Kitchen was re-read in the third pass.
4. Every read-back used OCCT. No commercial CAM opened the AP242 or IGES file. No laser software
   opened the DXF.
5. Only STEP was tested for byte-identical rebuilds. The AP242 writer breaks if build123d renames
   `_create_xde`.

## Sources

Local:

- `[L1]` `/home/worxbend/Projects/macropad-obs/cad/obs_case/`,
  `/home/worxbend/Projects/macropad-obs/cad/pyproject.toml`, `/home/worxbend/Projects/macropad-obs/board.toml`
- `[L2]` `/home/worxbend/Projects/macropad/cad/macropad_case/spec.py`, `solids.py`
- `[L3]` `/home/worxbend/Projects/macropad/cad/macropad_case/roundtrip.py`
- `[L4]` `/home/worxbend/Projects/macropad/cad/macropad_case/drawings.py`, `signature.py`,
  `checks.py`, `printsim.py`, `coupons.py`
- `[L5]` `/home/worxbend/Projects/macropad/cad/README.md`, `/home/worxbend/Projects/macropad/README.md`
- `[L6]` `/home/worxbend/Projects/macropad-nyxilab/common/cad/macropad_cad/export.py`,
  `freecad_doc.py`. The brief spells the directory "macropad-nixylab".
- `[L7]` `/home/worxbend/Projects/macropad-obs/cad/.venv/lib/python3.12/site-packages/build123d/exporters3d.py`
- `[L8]` `/home/worxbend/Projects/macropad-obs/docs/research/06-big-display.md`,
  `07-long-display.md`, `08-input-parts.md`, `12-fabrication.md`
- `/home/worxbend/Projects/macropad-obs/docs/images/sketch.jpg`

Experiments: five scripts in a `mktemp -d` folder outside the repo, run with
`cad/.venv/bin/python -B`. The folder is temporary. Section 8 names every call.

Web, re-read in this pass unless marked:

- `[J1]` JLCCNC design guideline: https://jlccnc.com/help/article/CNC-Machining-Design-Guideline
- `[J2]` JLCCNC appearance standard: https://jlccnc.com/help/article/appearance-standard-guidelines
- `[J3]` JLCCNC laser marking: https://jlccnc.com/help/article/uv-printing-laser-marking-design
- `[P1]` PCBWay CNC milling: https://www.pcbway.com/rapid-prototyping/cnc-machining/CNC-Milling.html
- `[P2]` PCBWay design for cost: https://www.pcbway.com/helpcenter/cnc_engineering_questions/How_to_Reduce_CNC_Machining_Costs_with_Better_Part_Design.html
- `[S1]` SendCutSend CNC guidelines: https://sendcutsend.com/guidelines/cnc-machining/
- `[M1]` MIL-A-8625F, section 6.10 and Table IV: https://www.ibiblio.org/apollo/Documents/assist.dla.mil/MIL_A_8625F.pdf
- `[X1]` Xometry part marking: https://www.xometry.com/ultimate-guide/direct-part-marking/
- `[C1]` Protocase laser marking: https://www.protocase.com/products/graphics-markings/laser-marking/
- `[F1]` Formlabs design specs: https://formlabs.com/support/Design-Specs/
- `[U1]` Prusa, modelling for print: https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135
- `[N1]` Newhaven, mounting a TFT: https://newhavendisplay.com/blog/how-to-mount-a-tft-display/
- `[K1]` CNC Kitchen, threaded inserts (re-read in the third pass): https://www.cnckitchen.com/blog/tipps-amp-tricks-fr-gewindeeinstze-im-3d-druck-3awey

## Open questions

For the owner:

1. Shell split: a tub top with a flat bottom plate, or two shells with a shadow gap as in `macropad`?
2. A flat slab, as the sketch shows, or a wedge? A tilt bar under a flat body keeps the shells simple.
3. Anodise colour. Dark gives light laser marks. Clear gives low contrast.
4. What is engraved, and on which faces?
5. May code from `macropad` and `macropad-nyxilab` be copied here? Neither has a licence file.

Settled by a shop or a sample:

1. Which shop mills, anodises and lasers? Corner radius, file and thread rules differ by shop.
2. Are 26 mm tall knobs acceptable, or should the encoder be the 19.5 mm Bourns PEC11L (report 08)?
3. M2 or M2.5 screws, how many, and which heat-set insert in the print?
4. Lens: acrylic or glass, clear or tinted, and who cuts it?
5. Is an FCStd with plain solids enough, or does the owner expect an editable FreeCAD model?

Next action: the owner answers the first three questions.
