# 17. Style directions for the case

Research only, 2026-11-18. This file is the only file written. Tags: **verified** (read in a local
report or file in this pass), **likely** (reasoned from those facts), **unverified** (a design
judgement or a guess). **MEASURE** marks a size that no datasheet drawing gives. No part was
modelled, printed, milled or lasered. Sources are the owner's sketch and reports 06, 07, 08, 11
and 12. This report adds no new web facts.

Next action: the owner picks one direction (A, B or C) and answers open question 1, the anodise
colour.

## Recommendation

**Direction A, "Channel strip".** It is a flat slab with a 45 degree perimeter chamfer, in black
bead-blasted 6061 with Type II anodise. The engraving borrows from a mixing desk: scales round
the knobs, a hairline from each knob to its row on the narrow display, and small index marks on
the deck. It is the closest to the sketch. It needs only 2.5D toolpaths in the three setups that
report 11 already plans. Black gives the strongest laser contrast. Its one bold element is the
engraved channel line from knob to display. Everything else stays quiet.

B is the choice if the owner wants a soft, premium object and will pay for 3D surfacing. C is the
choice if the owner wants the body itself to be the visual statement and accepts a deeper cavity
and a fourth setup.

## What every direction keeps

All three keep the sketch's arrangement (verified, `docs/images/sketch.jpg`):

```
 +-------------------------------+
 | +-------------------+  +----+ |
 | |                   |  |    | |
 | |   big display     |  |bar | |
 | |   (portrait)      |  |    | |
 | |                   |  |    | |
 | +-------------------+  +----+ |
 | +-----+-----+-----+     (O)   |
 | |     |     |     |           |
 | +-----+-----+-----+     (O)   |
 | |  3 x 3 MX keys  |           |
 | +-----+-----+-----+     (O)   |
 | |     |     |     |           |
 | +-----+-----+-----+           |
 |  [o]  [o]  [o]  [o]           |
 +-------------------------------+
```

Fixed inputs, from earlier reports:

1. Body about 93 x 175 x 16 mm without knobs: MEASURE (report 11, section 2). Nothing is placed yet.
2. Big panel 54.46 x 82.94 mm, bar module 24.38 x 69.43 mm, key block 57.15 mm (verified, reports
   06, 07, 08).
3. Four small buttons (the owner's answer). The sketch draws about five cells. Four is used here.
4. Tub top shell, flat bottom plate, lenses on ledges, bought DSA keycaps, turned knobs and button
   caps, legends as flat DXF sketches, laser last (verified, report 11).
5. CNC rules: hidden corners R = depth / 3, walls 2.0 mm or more, no undercut, MX holes 14.00
   +0.05 / 0 with dog-bones, laser strokes 0.2 mm or more and text 2.0 mm or more (verified,
   report 11, sections 3 and 7).
6. Knob tops land near 26 mm above the PCB, about 8 mm above the keycaps (likely, report 11).
7. Engrave only what never changes. Keys and knobs are remapped in the app (report 11, item 7.5).
   So no direction engraves key legends.

## Direction A: "Channel strip" (recommended)

The pad reads as one channel strip pulled out of a broadcast desk. The face is plain. The
engraving carries the identity.

**Form and silhouette.** A flat slab, as drawn. Vertical side walls. One 45 degree chamfer, 1.5 mm
wide, runs round the top edge. The bottom edge gets a 0.5 mm break. Plan corners are R 6 (a free
choice, unverified). The two lens windows sit flush in their recesses: the lens top is 0.07 mm
below the deck (report 11 stack). A 0.5 mm chamfer frames each window and the key well. The key
well and the window chamfers echo the outer chamfer at a smaller size. The web between the two
displays is 3 mm, so they read as two windows in one face. For a tilt, use a separate engraved
tilt bar under the back edge. The body stays flat.

**Material and finish.** 6061, #120 bead blast, black Type II anodise (verified as offered by both
shops, report 12). The bead blast hides fingerprints and milling marks. The chamfer is cut after
the blast in setup 2, so it shows bright, then anodised. Order this as "chamfer machined after
blast" on the drawing. Whether a shop will sequence it that way is unverified. The bottom plate is
the same black.

**Knobs.** Turned cylinders, 18 mm diameter, 14 mm tall (unverified sizes; settle on the print).
They have a straight knurl on the lower two thirds, a plain band at the top, and a flat top with
one engraved index line. That is a mixing-desk pot cap. The bore is 6 mm with an M3 set screw on
the shaft flat (report 11). The knurl is a lathe operation, cheap on a turning shop.

**Keycaps and button caps.** Nine blank DSA caps in a dark grey, with no legends. The big display
labels them. The four button caps are turned 6061, flanged under the deck, black anodised with the
shell batch. Each has a flat top and a 0.3 mm edge break. Cap diameter is 8 mm: MEASURE against
the deck hole and a 14.3 mm pitch (57.15 / 4).

**Laser engraving.**

1. Round each knob: a 270 degree tick scale, 11 ticks, the ends longer. It is a fixed graphic and
   says nothing about the mapped function.
2. From each knob a 0.25 mm hairline runs left and up to its row on the narrow display. The bar
   shows source name, level and mute for the three knobs (the owner's answer). The line ties each
   knob to its row. This is the direction's one bold element. Exact routing depends on the bar
   rows' pixel positions (report 14): MEASURE once the UI layout is fixed.
3. Under the button row: four small dots, not words, because the buttons are remappable.
4. Top left of the deck, above the big window: a small wordmark, 2.5 mm cap height.
5. Underside: model, serial field, licence line, a "prototype" note, and the screw map.
6. On the tilt bar, if made: nothing, or one line.

Type: one sans with open counters, named by file in the repo (report 11 says `font="Arial"`
silently becomes DejaVu Sans). Good candidates are DIN-like faces such as "Barlow" or "D-DIN"
(licence and stroke not checked: unverified). Sentence case, no tracked capitals.

**FDM prototype.** Matte black PETG or PLA. Printed on its side, as report 11 says. The chamfer
prints well at 45 degrees (report 11, overhangs clean to 45 degrees). Do not laser the print.
Print the legend PDF at 1:1 on paper and lay it on the deck to judge tick length and line weight.
Knobs and caps in resin, painted black. The print shows the proportions honestly, because A
depends on flat faces and lines, not on surface quality.

**Cost drivers and risks.**

1. Cheapest of the three. Everything is 2.5D: pockets, profiles, one chamfer tool pass in setup 2.
   No extra setup (likely).
2. The laser area is small: lines and ticks, no fills. Laser time is low (likely).
3. Risk: a 0.25 mm hairline across a bead-blasted surface may look ragged. Ask the shop for a test
   mark on a blasted black coupon (report 12 already asks for a photo).
4. Risk: a bright chamfer after blast needs the shop to accept an order of operations on the
   drawing. If not, the chamfer is matte black like the rest. That still works.

## Direction B: "Pebble"

The pad reads as a soft, heavy object, like a premium audio interface. Nothing is engraved on the
face but small indices.

**Form and silhouette.** A low wedge: the top face slopes 4 degrees, front edge 14 mm, back edge
about 26 mm (unverified, from 175 mm length). The wedge is cut into the top shell's outer
surface; the bottom plate stays flat. All top edges get an R 5 fillet. One lens across both
displays is out, because report 11 says a 90 mm lens flexes. So there are two flush lenses with
R 2.0 corners. The 3 mm web between them sits 0.3 mm lower, so the pair reads as one dark field.
Plan corners R 10.

Faithfulness: the wedge changes the side view, not the face. The sketch shows only the face.

**Material and finish.** 6061, fine bead blast, then grey or natural ("clear") Type II anodise.
Clear gives low laser contrast (verified, report 11 open question 3). That suits a direction with
almost no engraving.

**Knobs.** Smooth turned cylinders, 20 mm diameter, with a 0.5 mm deep concave dish on top and
a single small dot as the index. No knurl. Grip comes from a fine bead blast on the side. Same bore
and set screw.

**Keycaps and button caps.** DSA blanks in a light grey to match clear anodise, or white. Button
caps turned, domed tops (R 8 sphere, unverified), clear anodised with the shell.

**Laser engraving.** Minimal: one index dot per knob on the deck at the zero position, a wordmark
on the underside, and the underside label. Nothing joins the knobs to the bar. The display UI
carries all meaning.

**FDM prototype.** The wedge prints fine on its side. The R 5 fillets show layer stepping on a
side-printed part. Expect to sand or prime. Grey PLA reads close to clear anodise. Resin knobs
sand well to a smooth finish. The print will look worse than A's, because B depends on surface
quality.

**Cost drivers and risks.**

1. The R 5 top-edge fillet and the sloped top need 3D toolpaths with a ball or bull-nose cutter
   and small step-over. That is the main cost driver, and the main time driver (likely). A
   corner-rounding cutter can make a quarter-round on a flat top; on a sloped top it cannot follow
   in 2.5D.
2. The sloped top means the key well, both lens recesses and the knob holes are cut normal to a
   tilted face. That needs a tilted fixture or a 4th axis, or the features are cut vertical in a
   tilted part. Either way it is one more fixture (likely).
3. The MX plate must stay parallel to the PCB. With a wedge top, the plate is either tilted with
   the board (a wedge board stack) or the deck thickness varies along its length. This touches the
   height stack in report 11. Risk to the schedule.
4. Clear anodise shows every machining mark and every batch shift (report 12 says colour varies
   between batches).

## Direction C: "Terrace"

The pad reads as a machined part that shows how it was made. The face steps down in levels, one
level per function.

**Form and silhouette.** A flat slab with a stepped face, three levels:

```
 side view, front at left
           _________________   display plateau, deck +0
          |
 _________|                    key and knob level, deck -2.0
|_______________________________   button ledge, deck -3.5
```

1. Display plateau: both windows on one raised level at the back.
2. Key and knob level: 2.0 mm lower. The step face is a vertical wall with an R 1.6 inside corner.
3. Button ledge: a further 1.5 mm lower, a strip across the front.

Edges are sharp with a 0.3 mm break. Plan corners square with R 3. The steps make the sketch's
three bands (displays, keys, buttons) into geometry. The heavy frame in the sketch becomes a 4 mm
flat border at full deck height round the whole face.

**Material and finish.** Two tones. The shell is bead blast and black anodise. Knobs and button
caps get a second colour: red or orange anodise, the on-air colour. That makes two colour batches.
Two options were rejected. Milling the step faces bright after anodising leaves bare aluminium that
needs a clear coat. Laser-filling the step walls is a large, slow fill.

**Knobs.** Fluted cylinders, 16 mm diameter, 12 flutes, red anodised. Flutes need a milling
operation with indexing, either on a 4th axis or a mill-turn lathe (likely).

**Keycaps and button caps.** DSA blanks in black. Button caps red anodised to match the knobs,
square with R 1 corners, set into square holes (square holes need inside-corner radius R 0.5 or
more: verified rule, report 11).

**Laser engraving.**

1. Fine contour lines across the border, like a topographic map, about 0.2 mm strokes at 1.5 mm
   pitch (unverified look; needs a test mark).
2. Knob index dots on the knob level.
3. The wordmark on the border at the bottom right.
4. Underside label.

**FDM prototype.** Steps print cleanly face up or on the side. A face-up print hides the steps'
layer lines on vertical walls. Red PLA for knobs and caps makes the prototype read close to the
final. C looks best of the three as a print.

**Cost drivers and risks.**

1. Two more face levels in setup 2: more pocket area, more cycle time (likely).
2. Each step lowers the deck locally, so the key well and button holes move down. The stack in
   report 11 has 2.0 mm of deck and a 1.2 mm lens recess. A 3.5 mm step at the button ledge eats
   the deck there. The cap flange room (2.6 mm, report 11) shrinks. Either the bottom plate drops
   or the body grows 3.5 mm thicker. Risk to the height stack: MEASURE.
3. Fluted knobs cost more than knurled ones.
4. Two anodise colours are two batches, and report 12 warns colour varies between batches. Order
   all red parts together.
5. Contour-line artwork over a large area is slow to laser and hard to keep even on a blasted
   surface (likely).

## Side by side

| | A Channel strip | B Pebble | C Terrace |
|---|---|---|---|
| Silhouette | Flat slab, 45 degree chamfer | 4 degree wedge, R 5 fillets | Flat slab, three stepped levels |
| Sketch fit | Exact | Face exact, side changed | Face exact, bands become steps |
| Finish | Blast, black | Fine blast, clear or grey | Blast, black, red parts |
| Knobs | Knurled, index line | Smooth, dished, dot | Fluted, red |
| Laser | Scales, knob-to-bar lines | Dots only | Contour field, dots |
| Toolpaths | 2.5D | 3D surfacing, tilted features | 2.5D, more levels |
| Setups | 3 (report 11 plan) | 3 + a tilted fixture | 3 |
| Height stack | Unchanged | Changes | Changes at the ledge |
| Laser contrast | High | Low | High |
| Print looks like final | Yes | No, needs sanding | Yes |
| Relative cost | Lowest | Highest | Middle |

Cost order is likely, from toolpath type and setups. No shop quoted any of them.

## Not checked, and the risk

1. No quote. The cost order is reasoned, not priced. Report 12's next action (two live quotes)
   should send A's shell first.
2. No laser test on blasted black anodise. Fine hairlines and contour fields may look ragged.
3. Knob, cap and chamfer sizes are design guesses. They need the printed coupons from report 11.
4. Typefaces named in A were not checked for licence or stroke width at 2.5 mm.
5. Whether a shop will cut the chamfer after the blast was not asked.
6. The wedge in B and the steps in C were not run through report 11's height stack. Both move it.

## Sources

Local, read in this pass:

- `/home/worxbend/Projects/macropad-obs/docs/images/sketch.jpg`
- `/home/worxbend/Projects/macropad-obs/docs/research/11-case-cad.md` (stack, CNC rules, laser
  rules, knob and cap design, print rules)
- `/home/worxbend/Projects/macropad-obs/docs/research/12-fabrication.md` (shops, anodise colours,
  batch colour shift, laser file rules)
- Digests of reports 06, 07, 08 and 14 in the task brief (panel, bar, key block and UI sizes)

## Open questions

For the owner:

1. Which direction: A, B or C?
2. Anodise colour: black (high laser contrast), clear or grey (low contrast), or black plus a red
   accent for knobs and caps?
3. Flat body with a separate tilt bar, or a wedge built into the shell?
4. Engrave the knob-to-display lines (A), or keep the face bare?
5. Wordmark: is there a name or logo to engrave? Report 11 leaves the content to the owner.
6. Keycap colour: dark grey, black, or light grey?

Next action: the owner picks a direction and a colour.
