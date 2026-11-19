# Gap 5: layout-v2.toml has no display carriers, foam frames or z-levels

Research only, 2026-11-18. The spec and layout-v2.toml were not edited.

## Resolution

Add three tables to `docs/spec/layout-v2.toml`: `[stack]`, `[display_carrier]` and `[foam_frame]`.
Add one rule to `[pcb]`: no part and no hole on the PCB top face under a carrier. Then change the list
in spec section 7 so that these tables are among those that replace `board.toml` `[case]`.

One change to report 11: the panel face moves from z 5.5 to z 5.6. Report 11 puts 0.5 mm of foam in
a 0.5 mm gap (deck underside 6.0, panel face 5.5). That is 0 % compression, so nothing holds the panel
down. A 0.5 mm foam pressed to 0.4 mm (20 %) has a preload and stays under Rogers' 25 % limit. The
carrier heights follow from that: 3.45 mm for the big panel and 3.50 mm for the narrow one. They are
not the hint's 3.35.

A check (script in a scratch dir, run against today's layout-v2.toml) found nothing under either
carrier footprint. No hole keep-out, slot, key, cap, button, encoder or knob lies there. The closest
items are listed below.

## Text for layout-v2.toml

```toml
[stack]
# z above the PCB top face (z = 0), mm. Report 11 section 2, except where marked.
deck_top = 8.0                 # design (report 11): show face, 3.0 mm key well
lens_top = 7.93                # report 11: 1.0 lens on 0.13 tape in a 1.2 recess
lens_recess_floor = 6.8        # deck_top - [window] lens_recess_depth
deck_underside = 6.0           # design (report 11): 2.0 deck, 0.8 lens ledge
panel_face = 5.6               # = deck_underside - [foam_frame] installed. Report 11 had 5.5
mx_plate_top = 5.0             # datasheet (Cherry, report 08)
mx_plate_underside = 3.5       # mx_plate_top - 1.5 plate
ec11_body_top = 4.5            # datasheet (Alps, report 08)
b3f_body_top = 3.4             # datasheet (Omron, report 08)
pocket_skirt_bottom = 2.0      # design: the pocket walls reach down to here (see [display_carrier])
pcb_top = 0.0
pcb_bottom = -1.6
bottom_plate_inside = -5.6     # MEASURE (report 11): 4.0 for sockets and leads

[foam_frame]
# Black foam between the deck underside and each panel face. Closed ring, no glue (report 11 s5).
thickness = 0.5                # design; stock thickness MEASURE on the bought sheet
installed = 0.4                # design: 20 % compression. Rogers: above 25 % speeds stress relaxation
outer = "module outline"       # [big_display].outline, [narrow_display].outline
inner = "lens_opening"         # never over the active area
# Ring widths that follow: big 2.35 long sides, 6.75 tail edge, 1.95 far edge;
# narrow 1.15 long sides, 3.49 tail edge, 1.00 far edge. The 1.0 mm strips are cut by laser (MEASURE).

[display_carrier]
# A printed ring that stands on the PCB top face and holds the panel up against the foam.
# Located sideways by the pocket walls, which reach down to stack.pocket_skirt_bottom.
# Height = stack.panel_face - panel thickness. Calipered panel thickness replaces the nominal one
# (narrow 2.1 +/- 0.1 per the drawing): MEASURE.
clearance = 0.15               # design: carrier outer = pocket - 0.15 a side
wall = 2.0                     # design: 5 perimeters at 0.4
big = { outer = [3.30, 79.15, 54.70, 83.20], inner = [5.30, 81.15, 50.70, 79.20], height = 3.45, tail_gap = [19.9, 79.15, 21.5, 2.0] }
narrow = { outer = [63.66, 91.69, 24.68, 69.73], inner = [65.66, 93.69, 20.68, 65.73], height = 3.50, tail_gap = [72.75, 91.69, 6.5, 2.0] }   # tail_gap x MEASURE, as the tail offset
# Top-face keep-out = each carrier outer rectangle, z 0 to its height: no part, no THT lead,
# no hole or hole keep-out, no slot, no test pad. Copper, vias and silkscreen under solder mask are fine.
# Pocket skirt: a 1.0 band outside each pocket, from z 2.0 up. Top-face parts there stay under 2.0.
```

Add to `[pcb]`: `top_keepout = "every [display_carrier] outer rectangle"`. Then `tools/check_pins.py`
(or the `numbers` test, report 11 s9 item 1) can check four things:
1. `panel_face = deck_underside - installed`.
2. Carrier height = `panel_face` minus the panel thickness.
3. Compression = `1 - installed/thickness` is between 10 % and 25 %.
4. No hole keep-out, slot or top-face part rectangle overlaps a carrier rectangle.

## Text for spec section 7

Change "its tables replace `board.toml` `[pcb]`, `[case]`, `[display]`, `[keys]`, `[knob]`" to:
"its tables replace `board.toml` `[pcb]`, `[case]` (with `[body]`, `[stack]`, `[foam_frame]`,
`[display_carrier]`, `[window]`, `[bottom_plate]`), `[display]`, `[keys]`, `[knob]`".

## Evidence

1. **Report 11 relies on carriers and foam.** It lists "Two display carriers, foam frames ... They
   hold the panels up" (`docs/research/11-case-cad.md:70`). It also says "A printed carrier stands on
   the PCB and holds the panel up. No glue" (`11-case-cad.md:166-167`). Its stack: deck 8.0,
   underside 6.0, panel face 5.5 "under 0.5 mm of foam", MX plate 5.0 (`11-case-cad.md:81-91`).
   (verified, read)
2. **layout-v2.toml has none of this.** It has no `carrier`, `foam` or z-level key. The only
   z-values are in comments (`docs/spec/layout-v2.toml`, `[bottom_plate]` and `[usb]` comments).
   Section 7 still says its tables replace `[case]` (`docs/spec/spec-v2.md:181-185`). (verified, grep)
3. **Report 11's foam has no squeeze.** 6.0 - 5.5 = 0.5, and the foam is 0.5 thick, so the
   compression is 0 % (arithmetic). Rogers: "Compressing a material greater than 25% will accelerate
   the relaxation, leading to a greater loss in force" (Rogers, PORON and BISCO Technical Sealing
   Guide, page 14. I read it as text extracted from the PDF hosted by a distributor:
   https://www.modusadvanced.com/hubfs/Brochures-Guides/Poron-and-Bisco-Technical-Sealing-Guide.pdf.
   Verified for the quote. The Rogers-hosted copy returned 403). The 20 % target is a design choice
   inside that limit, not a Rogers number.
4. **Panel thicknesses.** Big 2.15 (`06-big-display.md:24`, `[D1]`). Narrow: 2.1 +/- 0.1 in the
   drawing and 2.15 in the table (`07-long-display.md:149, 230`). The heights use 2.15 and 2.10.
   With a fixed carrier, the narrow tolerance alone swings the gap from 0.3 to 0.5 mm, which is
   0 % to 40 % compression. So the carrier height is set from a calipered panel: MEASURE.
   (verified, read)
5. **Footprints are clear.** A scratch script (`python3 -I`, tomllib on today's layout-v2.toml)
   tested each carrier rectangle against the hole keep-outs (diameter 5.0), board slots, key
   housings, keycaps, B3F bodies, EC11 bodies and 18 mm knobs. Nothing overlaps. The closest gaps:
   - Big carrier: 1.15 to the (3.0, 75.5) and (3.3, 166.0) keep-outs, and 1.55 to the big tail slot.
   - Narrow carrier: 2.08 to the (88.3, 166.0) keep-out, and 1.49 to the bar tail slot.
   - Both carriers lie inside the PCB and inside their pockets. Each overhangs the module outline by
     0.12 to 0.15 a side.

   The only skirt overlap is the big pocket's skirt with the (3.3, 166.0) boss keep-out. That boss is
   shell material, and the skirt merges into it. (verified, experiment)
6. **The top face is otherwise free there.** All SMT is on the bottom face (`layout-v2.toml`
   `[bottom_side]`, report 12). The FPC connectors are on the bottom (`[fpc.big]`, `[fpc.narrow]`).
   No THT part sits under a display. (verified, read)

## Not checked

- Which way the tails leave the panels. Each carrier's `tail_gap` is a cheap guard in case a tail or
  stiffener leaves low on the front edge: MEASURE on a sample.
- Foam stock. No 0.5 mm black foam part number was picked or checked. The force at 20 % compression
  was not read from a CFD curve.
- The FDM layer height. A 3.45 mm carrier needs a 0.15 layer or a sanded top.
- That a 1.0 mm skirt prints and mills cleanly. The CNC inside-corner rules are in report 11 s3.
