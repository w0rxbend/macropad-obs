# 12. Fabrication constraints and ordering

Research only, 2026-11-18. Second pass: the first draft was re-read against its sources, corrected
and cut. This file is the only file written. Tags: **verified** (read in this pass on the
fab's own page or in a local file), **likely** (reasoned, or carried from the first pass and not
re-read), **unverified** (my estimate, or one maker's anecdote). **MEASURE** marks a size not read
in a datasheet drawing. Keys such as `[J4]` point into Sources. No order was placed. No live quote
was run.

Next action: the owner runs two live quotes. One at JLCPCB: a 90 x 160 mm 4-layer board with
Standard PCBA. One at JLCCNC: `cad/exports/base.step`, the old shell. It is the wrong device but
the right size class: 93.6 x 155.6 x 33.3 mm (run today). Two real prices replace my weakest
numbers.

## Recommendation

**Boards:** JLCPCB, Standard PCBA. 4 layers, 1.6 mm, default stackup, ENIG, every SMT part on the
bottom face. Solder the 4 tact buttons and 3 encoders by hand. Keep a PCBWay file set as the second
source.

**Case:** print it at home first. Mill it only after the printed case closes on real parts: two
6061 shells, bead blast, black Type II anodise, laser mark last.

Five findings carry it.

1. **The hot-swap socket forces the dearer assembly tier. The MCU does not.** JLCPCB lists Kailh
   CPG151101S11-1 as "Standard Only". RP2350B is "Economic and Standard". Economic PCBA opens only
   if the owner solders the sockets, and then saves 10 to 55 USD. (verified listings, `[J16]`
   `[J17]`; the saving is computed)
2. **One-face SMT saves 33.77 USD.** Standard setup is 25.56 USD for one face and 51.12 USD for
   two. The stencil is 8.21 or 16.42 USD. Sockets sit on the bottom, so all SMT goes there.
   (verified, `[J4]`)
3. **Plain design rules fit both fabs with no surcharge.** 0.15 mm track and gap, 0.3 mm via
   drill. (verified, `[J1]` `[J9]` `[P1]`)
4. **A CNC shop needs three file kinds. The repo writes one.** STEP for the solid, a PDF drawing
   for threads and tolerances, DXF for the laser mark. `cad/exports/` holds STEP, STL and 3MF only.
   (verified, `[C1]` `[C3]` `[P6]` `[L3]`)
5. **Money: about 230 to 340 USD for 5 assembled boards and about 130 to 380 USD for one machined
   case, before import tax.** The assembly fees are computed from a public table. The rest is
   estimate. (see "Cost and lead time")

The working reading of the connectivity sentence meets no fabrication obstacle. Report 04's first
choice has no radio, so a metal case costs nothing. Wi-Fi would need a plastic window or an antenna
connector (report 03).

## The owner's words

1. "I want 4layers or more PCB, with 3x3 keys matrics, MX switches". Four layers meet it. The board
   has no BGA and no fast bus. Six layers buy nothing.
2. "one tray of buttons [...] should be such or similar, small buttons". That is a through-hole
   6 x 6 mm part. A fab solders it by hand for a fee, or the owner does.
3. "I need all the export format for 3d cad case, I will start with prototype that will be printed
   and then CNC, and laser engraving to be stalish." The shops read STEP, PDF and DXF. The other
   formats serve the owner's own tools (report 11).

## Options compared

| Option | For | Against |
|---|---|---|
| JLCPCB Standard PCBA (pick) | Public fee table. Places the sockets. Any finish. Pin pitch to 0.35 mm. | Fees about 115 USD for 5 boards. Rails and fiducials required. 4 days or more. |
| JLCPCB Economic PCBA | Setup 8.18 USD, stencil 1.53 USD, 1 to 3 days. Takes RP2350B. | One face. Refuses the socket. ENIG only on some 1.6 mm boards. 0.4 mm pin pitch is its floor and the QFN-80 sits on it. Extended parts cost 3.07 USD a line. |
| PCBWay turnkey | Buys any manufacturer part number. Takes customer parts. Mills and prints too. The owner's `macropad` ordering guide is written for it. | No public fee table. "Our minimum is as low as 5 pieces." Slower. |
| Bare boards, all by hand | Cheapest. | A 0.4 mm QFN-80 and a 40-pin 0.5 mm connector by hand. |

Sources: `[J3]` `[J4]` `[P3]` `[L1]` (verified).

## 4-layer board rules

| Rule | JLCPCB | PCBWay | Design to |
|---|---|---|---|
| Track / gap, 1 oz | 0.09 / 0.09 mm | 0.1 mm | 0.15 / 0.15 mm floor, 0.2 / 0.2 mm default |
| Via drill / pad | 0.15 / 0.25 mm | 0.15 mm; extra charge under 0.2 mm | 0.3 / 0.7 mm; 0.3 / 0.6 mm is the floor |
| Annular ring | 0.15 mm limit, 0.20 mm recommended | 0.15 mm on vias | 0.20 mm |
| Plated slot width | 0.35 mm | 0.5 mm, length at least 2 x width | 0.6 mm |
| Plated hole to track | 0.28 mm limit, 0.35 mm recommended | not stated | 0.35 mm |
| Outline tolerance | ± 0.2 mm (± 0.1 mm option) | ± 0.2 mm | case pocket 0.4 mm clear per side |
| Thickness tolerance | ± 10% | ± 10% | 1.6 ± 0.16 mm in the case stack |
| Impedance | ± 10% | ± 10% | none needed |

Sources: `[J1]` `[P1]` (verified). The "design to" column is my choice (likely).

**Stackup: take each fab's default.** Layer order: signal, ground, power, signal. (verified,
`[J2]` `[P2]`)

- JLCPCB "No requirement" stackup, the same as JLC04161H-7628: outer copper 0.035 mm, 7628 prepreg
  0.2104 mm (Dk 4.4), inner copper 0.0152 mm, core 1.065 mm (Dk 4.6).
- PCBWay 1.6 mm entries 1 to 3: 1 oz outer and inner, 7628 prepreg 0.196 mm before lamination
  (Dk 4.74), core 1.03 mm (Dk 4.6).

**Impedance control: not needed.** USB is full speed. Report 10 gives the pair geometry for both
default stackups. The owner's `macropad` order made the same call (verified, `[L1]` line 65).

**Price traps at JLCPCB.** (verified, `[J9]`)

1. The special price ends at 102 x 102 mm. This board is larger.
2. "Keyboard design": 16.41 USD + 49.25 USD/m². The page gives no threshold. About 20 USD here.
3. Holes under 0.3 mm cost more.
4. Multilayer track or gap of 3.0 to 3.5 mil: + 20% of the order.

## Assembly

| Part | Finding | Tag |
|---|---|---|
| MX hot-swap socket, 9 | Kailh CPG151101S11-1: Extended, SMT, "Standard Only", MSL 5. Bottom face. | verified `[J17]` |
| RP2350B | Extended, QFN-80-EP 10 x 10, "Economic and Standard", MSL 1. Pitch 0.4 mm (report 04). | verified `[J16]` |
| FPC connectors, 40-pin and 10-pin, 0.5 mm | Inside both tiers: Economic places to 0.4 mm pin pitch, Standard to 0.35 mm. | verified `[J3]` |
| Tact button, 4, and EC11 encoder, 3 | Through-hole. The fab solders its "wave soldering" library parts by hand: 3.58 USD per order + 0.0164 USD per joint, one more day. 37 joints per board. | verified `[J4]` `[J5]`; library stock not checked |
| Display panels | No fab places them. Plug-in tails, fitted by hand. | likely |

Rules that shape the layout:

1. Standard PCBA needs edge rails, 5 mm or more, and fiducials. Boards ship with the rails on.
   (verified, `[J3]` `[J6]`)
2. Three or four fiducials: 1 mm copper, 2 mm mask opening. One page says 3.35 mm from the edge,
   another 3.85 mm. Use 3.85 mm. (verified, `[J6]` `[J7]`)
3. "The distance between the body of the components and the edge of the board must be equal or
   greater than 2.5mm." The USB-C mouth breaks this on one edge; a rail there restores it.
   (verified, `[J8]`; the rail remedy is likely)
4. The customer checks placement and polarity in the fab's preview. `pcb/gen/fab.py` says its
   bottom rotation "is not verified against PCBWay's preview". (verified, `[J8]` `[L3]`)
5. Through-hole parts sit on top, SMT on the bottom. No page says whether JLCPCB counts that as
   one face or two. So the first batch solders them by hand.

## Files each fab needs

| File | JLCPCB | PCBWay |
|---|---|---|
| Board | Gerber zip with drill files | Gerber RS-274X. For assembly at least copper, silkscreen and paste layers |
| BOM | `.csv`, `.xls`, `.xlsx`. Columns Comment, Designator, Footprint | Same file types. Line, quantity, designator, part number, description, package, type. Turnkey adds manufacturer, manufacturer part number, distributor number |
| Placement | Designator, Mid X, Mid Y, Layer (Top or Bottom), Rotation. mm. Positive is counter-clockwise | Designator, X, Y, rotation, side. "Only surface mounting parts are listed" |
| Extra | none | Assembly drawing, notes, photos: "strongly recommend" |

Sources: `[J10]` `[J11]` `[P4]` (verified). The JLCPCB board row is likely: its capability page
says only "Gerber files".

`pcb/gen/fab.py` already writes the JLCPCB columns (verified, `[L3]`). `macropad` writes both sets
and a polarity drawing (verified, `[L1]`). Do the same here.

## CNC machining and laser marking

Report 11 holds the design rules. This section holds what an order needs.

| | JLCCNC | PCBWay |
|---|---|---|
| 3D file | `.step`, `.stp`, mandatory | STEP, IGES, X_T, SLDPRT, under 200 MB, no ZIP. "STL files are not suitable for CNC machining." |
| 2D file | `.pdf`, `.dwg`, `.dxf` | DWG, DXF, PDF |
| Default tolerance | ISO 2768 class m | ± 0.005 inch (0.127 mm) |
| Tight option | to ± 0.02 mm, only on features the drawing marks | to ± 0.01 mm |
| Wall, metal | 0.8 mm | 0.8 mm |
| Pockets | depth 2 to 3 x tool diameter; over 5 x is special | depth to 4 x tool diameter; inside radius at least depth / 3 |
| Anodise | anodise, hardcoat, conductive; black, red and gold named | Type II and III. #120 blast + Type II: clear 8 to 12 µm, colour 4 to 8 µm. "Black, clear or any RAL code or Pantone number" |
| Lead time | from 3 business days | "10-12 Days" on the quote page, "from 5 days" on the milling page |

Sources: `[C1]` `[C2]` `[P5]` `[P6]` `[P7]` (verified).

1. **The default tolerance is too loose for a switch.** Class m is ± 0.2 mm from 6 to 30 mm and
   ± 0.5 mm from 120 to 400 mm (likely, `[X2]`). The MX hole is 14.0 ± 0.05 mm with corners of
   R 0.3 at most (report 08). Put that hole on the PDF with its tolerance and a dog-bone relief.
2. **Threads live on the drawing.** Model the hole at tap-drill size. Tick "Threads-YES". State
   size, pitch and depth. Keep depth within 3 x diameter. (verified, `[C1]` `[C2]`)
3. **Every shell is its own file and order line.** A multi-body STEP waits for manual review:
   "Please split your project and submit separate files for each individual part." (verified,
   `[C1]`)
4. **Anodise leaves marks and shifts colour.** "Small rack/contact marks are inevitable". Colours
   "may vary slightly between different production batches". Bead blast is a separate option.
   Name the rack faces and order every anodised part in one batch. (verified, `[C1]`)
5. **Laser mark: DWG or DXF at 1:1 with position dimensions.** One tone, recess 0.03 to 0.1 mm,
   3 mm margin, no minimum line stated. PCBWay lists laser engraving and gives no rules. Ask for a
   photo of the mark on the chosen colour. (verified, `[C3]` `[P5]`)

## Printed prototype

Print at home first. The owner's `macropad` plan does it: fit coupons, then the case, then a gate
before paying for CNC (verified, `[L2]`). If a service prints it (verified, `[D1]` `[D2]`):

1. JLC3DP takes STL, STEP, 3MF, OBJ and AMF. Lead 48 to 120 hours.
2. Tolerance over 100 mm: SLA ± 0.3%, MJF, SLS and FDM ± 0.4%. On 170 mm that is ± 0.5 to
   ± 0.7 mm.
3. Wall for a 200 mm part: 2.0 mm, FDM 2.5 mm.
4. Assembly clearance 0.2 mm, FDM 0.5 mm. Hole tolerance ± 0.3 mm, FDM ± 0.4 mm.
5. "The minimum recommended thread for printing is M6." Use heat-set inserts.

## Cost and lead time

Assumptions: board 90 x 160 mm (MEASURE: no outline exists yet), 30 BOM lines, 350 SMT joints per
board, case envelope 100 x 170 x 25 mm (MEASURE: the task's round figure), two shells.

**Five assembled boards, JLCPCB Standard, one-face SMT.**

| Line | USD | Tag |
|---|---|---|
| Setup 25.56, stencil 8.21, two fixtures 16.42, handling 14.93 | 65.12 | verified `[J4]` |
| Feeder loading, 30 lines at 1.53 | 45.90 | verified rate, my line count |
| 1750 SMT joints at 0.0016, packing, placement check | about 4 | verified rates |
| Assembly fees, sum | about 115 | computed |
| Five bare boards, ENIG | 40 to 80 | unverified |
| Parts for five boards | 50 to 100 | unverified |
| Express shipping | 25 to 45 | unverified |
| **Total before import tax** | **about 230 to 340** | |

Extras: two-face SMT + 33.77. Tact buttons and encoders soldered by the fab + 6.61 (3.58 + 185
joints). "Keyboard design" fee + about 20 if applied. Economic PCBA with hand-soldered sockets:
fees of 60 to 105 USD in place of 115, by the count of Extended lines. PCBWay: by quote.

Not in the sum, bought apart: two displays (the big panel is about 40 USD, report 06), 9 switches,
9 keycaps, 3 knob caps.

**One case.**

| Line | USD | Tag |
|---|---|---|
| Printed at home | under 5 | unverified |
| Printed by a service | 15 to 50 | unverified |
| Two milled 6061 shells, bead blast, anodise, tapped | 100 to 300 | unverified |
| Laser mark, shipping | 30 to 80 | unverified |
| **Machined case, landed, before import tax** | **about 130 to 380** | |

Evidence for the milled price is two anecdotes. A two-half handheld case at PCBWay in 2022: auto
quote about 45 USD, about 75 USD after review (`[X6]`). A keyboard case at JLCPCB's CNC service in
2024: "under $100.00 including shipping" (`[X4]`). Neither states a size.

EU delivery since 2026-07-01: consumer parcels up to 150 EUR pay 3.00 EUR duty per line item.
JLCPCB collects the import VAT, not the duty. (verified, `[J15]`)

| Step | Time | Tag |
|---|---|---|
| JLCPCB 4-layer board, 5 pieces | 2 to 5 days (stated for HASL, up to 100 x 100 mm) | verified `[J12]` |
| JLCPCB Standard assembly | 4 days or more; through-hole by the fab adds 1 day | verified `[J3]` `[J5]` |
| A part JLCPCB must buy in | 9 to 20 business days more | verified `[J14]` |
| PCBWay assembly | "24 Hours to a few weeks" after parts and files are in | verified `[P3]` |
| CNC shells with anodise | 2 to 4 weeks with shipping | likely `[C2]` `[P6]` |
| Printed case | 1 day at home; 48 to 120 hours plus shipping at JLC3DP | verified `[D1]` |

Boards land in 2 to 3 weeks when every part is in stock, 5 to 7 weeks when one is not (likely).

## What should change in the design

Board:

1. **All SMT on the bottom face.** Each display tail must reach the bottom, through a slot or
   round an edge (report 10, question 3). A connector on top makes the order two-face.
2. **Plan for Standard PCBA.** Three fiducials on the SMT face. Rails by the fab, with a note that
   the USB-C mouth overhangs one edge. `macropad/docs/ordering.md` has the wording.
3. **Adopt the "design to" column.** Via pad 0.7 mm where room allows.
4. **Decide who solders the sockets.** The fab: Standard tier. The owner: Economic is possible.
5. **Write two BOM and placement sets**, one per fab.

Case:

1. **Two shells, two STEP files, two PDF drawings, one DXF per marked face.**
2. **Corner radius depends on the shop.** Report 11 draws R 2.0 in a 12 mm cavity, to JLCCNC's
   rule. PCBWay asks for depth / 3, which is R 4. Pick the shop first, or draw R 4.
   (verified, `[P7]`; report 11)
3. **Tolerance the switch holes on the drawing.** The default class does not hold them.

Anodise masks, the ground contact and the print and milled variants are in report 11.

## Repo rules that meet this topic

1. **LCSC cells.** The listings `C5184526` and `C42415655` were read as evidence. That does not
   verify a BOM cell. Both stay `UNVERIFIED`.
2. **Conflict, for the owner.** `CLAUDE.md` exempts RP2040 `C2040` and FH12-20S-0.5SH(55)
   `C596730`. Reports 04 and 10 replace both parts. The exemption list then names parts the board
   does not carry.
3. **PCBWay naming.** `README.md`, `docs/design.md` and `pcb/gen/fab.py` name PCBWay as the
   assembler. This report puts JLCPCB first. No rule forbids it. The owner decides.
4. **MEASURE.** The board outline and the case envelope used for costing are not design values.
5. No finding touches the SK6812, password or licence rules.

## Not checked

- No live quote. Risk: the bare-board, parts and CNC lines can be off by 2 x.
- JLCPCB library stock of the tact button, the encoder and both FPC connectors.
- No fab engineer has seen a file. Rail, rotation and surcharge answers come only with an order.
- PCBWay's CNC default tolerance was re-read on `[P5]` in a third pass: "+/- 0.005”", no ISO
  2768 class named, "as tight as ±0.01 mm". The JLCPCB fee table `[J4]` was re-read too, same
  figures, still dated 2026-10-22. Through-hole joints are billed as manual joints (0.0164 USD)
  plus 3.58 USD hand-soldering labour per order.
- PCBWay's hot-swap socket stock and through-hole fee: not read. PCBWay quotes them per order.

## Sources

JLCPCB (read 2026-11-18):

- `[J1]` PCB capabilities: <https://jlcpcb.com/capabilities/pcb-capabilities>
- `[J2]` Impedance stackups: <https://jlcpcb.com/impedance>
- `[J3]` Assembly capabilities: <https://jlcpcb.com/capabilities/pcb-assembly-capabilities>
- `[J4]` Assembly price table, updated 2026-10-22: <https://jlcpcb.com/help/article/pcb-assembly-price>
- `[J5]` Assembly FAQ: <https://jlcpcb.com/help/article/pcb-assembly-faqs>
- `[J6]` Edge rails and fiducials: <https://jlcpcb.com/help/article/how-to-add-edge-rails-fiducials-for-pcb-assembly-order>
- `[J7]` Process edges and positioning holes: <https://jlcpcb.com/help/article/specifications-for-adding-process-edges-and-positioning-holes>
- `[J8]` Assembly terms: <https://jlcpcb.com/help/article/terms-and-conditions-of-jlcpcb-assembly-service>
- `[J9]` Extra charges: <https://jlcpcb.com/help/article/in-what-cases-will-there-be-charged-extra>
- `[J10]` BOM file: <https://jlcpcb.com/help/article/bill-of-materials-for-pcb-assembly>
- `[J11]` Placement file: <https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly>
- `[J12]` Board production time, updated 2026-11-10: <https://jlcpcb.com/help/article/PCB-Fabrication-Services-and-Production-Time>
- `[J14]` Global sourcing: <https://jlcpcb.com/help/article/How-to-use-JLCPCB-Global-Sourcing-Parts-Service>
- `[J15]` EU customs notice: <https://jlcpcb.com/news/eu-customs-reform-2026>
- `[J16]` Listing, RP2350B: <https://jlcpcb.com/partdetail/RaspberryPi-RP2350B/C42415655>
- `[J17]` Listing, Kailh CPG151101S11-1: <https://jlcpcb.com/partdetail/Kailh-CPG151101S111/C5184526>

PCBWay (read 2026-11-18):

- `[P1]` PCB capabilities: <https://www.pcbway.com/capabilities.html>
- `[P2]` Multilayer stackups: <https://www.pcbway.com/multi-layer-laminated-structure.html>
- `[P3]` Assembly capabilities: <https://www.pcbway.com/assembly-capabilities.html>
- `[P4]` Assembly file requirements: <https://www.pcbway.com/assembly-file-requirements.html>
- `[P5]` CNC milling: <https://pcbway.com/rapid-prototyping/CNC-machining/CNC-Milling.html>
- `[P6]` CNC quote page: <https://pcbway.com/rapid-prototyping/manufacture/?type=3>
- `[P7]` CNC cost and design: <https://www.pcbway.com/helpcenter/cnc_engineering_questions/How_to_Reduce_CNC_Machining_Costs_with_Better_Part_Design.html>

JLCCNC and JLC3DP (read 2026-11-18):

- `[C1]` CNC ordering guidelines: <https://jlccnc.com/help/article/cnc-machining-ordering-guidelines>
- `[C2]` CNC capabilities: <https://jlccnc.com/capabilities/cnc-machining-service>
- `[C3]` UV print and laser mark design: <https://jlccnc.com/help/article/uv-printing-laser-marking-design>
- `[D1]` 3D printing capabilities: <https://jlc3dp.com/capabilities/3d-printing-service>
- `[D2]` 3D printing design guideline: <https://jlc3dp.com/help/article/3D-Printing-Design-Guideline>

Other:

- `[X2]` ISO 2768-1 table, a transcription, first pass only: <https://amesweb.info/fits-tolerances/iso-2768-linear-dimensions-tolerances.aspx>
- `[X4]` One maker's aluminium case order, 2024-03-26: <https://green-keys.info/en/talk-about-ordering-aluminum-keyboard-parts-from-jlcpcb/>
- `[X6]` One maker's two-half aluminium case, 2022-08-14: <https://hackaday.io/project/184924/log/209793-aluminium-enclosure-for-a-handheld-version-from-pcbway>

Local files:

- `[L1]` `/home/worxbend/Projects/macropad/docs/ordering.md`
- `[L2]` `/home/worxbend/Projects/macropad/docs/prototype.md`
- `[L3]` This repo: `cad/exports/` (36 files: 12 each of STEP, STL, 3MF), `pcb/gen/fab.py`
  lines 3 to 9
- Reports 03, 04, 06, 08, 10 and 11 in `docs/research/`

## Open questions

For the owner:

1. Which country receives the parcels? It sets import tax and the EU 3.00 EUR duty per line.
2. Which anodise colour? Both shops offer black. It also sets the laser mark contrast.
3. Who solders the 9 sockets: the fab (Standard tier) or the owner (Economic possible)?
4. Assemble all 5 boards, or 2 of 5 as the `macropad` plan did? Fees are fixed; only parts scale.
5. Is there a printer at hand, and what is its bed size? The longest part is about 170 mm.

For a fab, at quote time:

1. Does JLCPCB count top-face through-hole parts plus bottom-face SMT as one-face assembly?
2. Does the "keyboard design" fee apply to a 9-key board?
3. Does JLCPCB stock the chosen tact button, encoder and FPC connectors?
4. Does PCBWay still require 5 pieces for assembly? The `macropad` guide orders 2.
5. What colour is a laser mark on the chosen anodise? Ask for a photo.

Next action: the two live quotes named at the top.
