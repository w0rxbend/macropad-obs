# Build guide: buy, make, assemble

How to get every part of a macropad-obs: what a fab builds turnkey, what you buy on the side, what
you print, laser-cut or mill, and how it goes together.

**Nobody has built one yet.** Every step below comes from the design files, not from a finished
pad. Values marked MEASURE are unchecked until a part is in hand (README "MEASURE and UNVERIFIED").
Read "Before you order anything" first.

The release assets carry the files (the latest GitHub release):

| Asset | Holds |
| --- | --- |
| `macropad-obs-pcb-<tag>.zip` | KiCad project, footprint library, JLCPCB Gerber/drill/BOM/CPL set, board STEP |
| `macropad-obs-case-<tag>.zip` | every case export (`cad/exports/`), the CNC drawing pack (`cnc-pack/`) and the renders |
| `macropad-obs-firmware-<tag>.zip` | the ESP32-S3 image |
| `macropad-obs-app-<tag>-linux-x86_64.tar.gz` | the Linux app and the udev rule |

## 1. Before you order anything

These gaps block a complete pad today. Each one is open in the tree, not just in this guide.

1. **The PCB is provisional.** The two FPC connectors (J3, J4) are placeholder footprints until the
   panels are calipered (task 5.12). `just gate` exits 1 with 18 open MEASURE tags. Do not order
   boards until it exits 0.
2. **LCSC numbers are UNVERIFIED.** Every BOM cell must be matched to a real part at order time.

Order of work that the design expects:

1. Buy the two displays and the hand parts first (section 3).
2. Print the coupons (section 4.1), caliper both panels, and record the results.
3. Close task 5.12 and the MEASURE tags, until `just gate` exits 0.
4. Order the boards (section 2). Print the full case (section 4.2).
5. Mill the case only after the printed case closes on real parts (section 4.4).

## 2. Turnkey: PCB with SMT assembly (JLCPCB)

All SMT parts sit on the bottom face, so the order is one-face assembly. Recommended fab:
JLCPCB Standard PCBA (`docs/research/12-fabrication.md`). PCBWay turnkey is the second source; no
PCBWay file set is written yet.

**Board options**

| Option | Value | Source |
| --- | --- | --- |
| Layers | 4 (signal, GND, power, signal) | `board.toml` `[pcb] layers` |
| Size | 91.6 x 167.7 mm, corner R 4.0 | `board.toml` `[pcb]` |
| Thickness | 1.6 mm | `board.toml` `[pcb]` |
| Stackup | the fab's default (JLC04161H-7628) | report 12 |
| Surface finish | ENIG | report 12 |
| Impedance control | none (USB full speed) | report 12 |
| Smallest track / gap / via | 0.127 / 0.127 mm, via 0.45 mm pad, 0.3 mm drill | `pcb/gen/layout.py` `DRC_RULES` |
| Quantity | 5 (the fab's minimum) | report 12 |

**Assembly options**

- PCBA type: **Standard**. The Kailh hot-swap socket is "Standard only" at JLCPCB.
- Side: **bottom** only.
- Edge rails and fiducials: ask the fab to add them. Note that the USB-C mouth overhangs one edge.
- Files from `pcb/fab-provisional/` in the PCB zip: `macropad-obs-gerbers.zip`,
  `bom-jlcpcb.csv`, `cpl-jlcpcb.csv`.
- Check every part's position and polarity in the fab's preview. The bottom-face rotations have not
  been checked against a fab preview.

**What the fab places (80 parts, bottom face)**

| Ref | Part | Qty |
| --- | --- | --- |
| U1 | Espressif ESP32-S3-WROOM-1-N16R2 | 1 |
| U2, L1 | TI TLV62569DBV buck, 2.2 µH inductor | 1 + 1 |
| U3 | ST USBLC6-2SC6 USB ESD | 1 |
| U4, U5 | Diodes BCR421UW6 backlight sinks | 2 |
| J1 | GCT USB4216-03-A USB-C | 1 |
| J2 | JST SM03B-SRSS-TB debug UART | 1 |
| J3 | Hirose FH12-40S-0.5SH(55), big panel (placeholder footprint) | 1 |
| J4 | Hirose FH12-10S-0.5SH(55), strip panel (placeholder footprint) | 1 |
| SW1 to SW9 | Kailh CPG151101S11-1 MX hot-swap sockets | 9 |
| SW20, SW21 | TS-1187A tact switches, BOOT and RESET | 2 |
| D1 to D16 | onsemi BAT54T1G matrix diodes | 16 |
| F1 | PPTC fuse, 0.75 A hold | 1 |
| R, C | 0402/0805 resistors and capacitors (see `bom-jlcpcb.csv`) | 42 |

Cost (report 12, estimates, no live quote): about 230 to 340 USD for 5 assembled boards with
express shipping, before import tax. Lead time 2 to 3 weeks when every part is in stock; a part
JLCPCB must buy in adds 9 to 20 business days.

## 3. Buy separately

**Hand-soldered on the board.** These are through-hole parts on the top face and are not in the
JLCPCB BOM. Solder them yourself, or pay JLCPCB's hand-soldering option (about 6.61 USD for 5
boards, report 12).

| Ref | Part | Per pad | Notes |
| --- | --- | --- | --- |
| SW10 to SW13 | Omron B3F-1060, 6x6 mm tact, round 3.5 mm plunger | 4 | B3F-1050 (square stem) fits as the alternate (open question 2) |
| SW14 to SW16 | Alps EC11E18244AU encoder with push, 6 mm flat shaft | 3 | 36 detents, 18 pulses |

**Plug-in and fit-by-hand parts**

| Part | Per pad | Notes |
| --- | --- | --- |
| Focus LCDs E35GH-I-RW300-N, 3.5" 320x480 IPS, ST7796U, 40-pin 0.5 mm FPC | 1 | about USD 40 from Focus direct, also DigiKey (report 06). Fallback: Displaytech DT035CTFT-IPS-SHB, which needs a new footprint |
| Wisevision N279-1428KIWIG01-C10, 2.79" 142x428 IPS, NV3007, 10-pin 0.5 mm FPC | 1 | by quote from Wisevision, MOQ 1. BuyDisplay ER-TFT2.79-1/-2 may be the same glass: check the 10-pin table first (report 07) |
| MX-style 5-pin switches | 9 | any MX-compatible switch; plate hole 14.0 mm |
| DSA keycaps, 1u, blank | 9 | the big display labels the keys; DSA seat MEASURE |
| Black foam sheet, 0.5 mm | 1 small sheet | laser-cut into two frames (section 4.3). Part not picked; compressed 20 % to 0.4 mm |
| Acrylic sheet, 1.0 mm, clear or tinted | 1 small sheet | laser-cut into two lenses (section 4.3) |
| Double-sided tape, 0.13 mm | a strip | holds each lens on its ledge |
| M3 set screws | 3 | one per knob, on the shaft flat. Length MEASURE |
| ISO 10642 M2 x 12 countersunk hex socket screws, A2 stainless | 6 | close the case from below (`board.toml` `[screws]`) |
| M2 x 3.0 heat-set inserts, brass, knurled | 6 | printed case only; the CNC case is tapped M2. Pocket 3.2 x 4.0, check it on the `insert-boss` coupon |
| USB-C cable, data | 1 | power and configuration |

**Tools for the build and bring-up**

- Soldering iron for the 7 through-hole parts, and a heat-set insert tip for the printed case.
- 1.25 mm hex key for the ISO 10642 M2 screws.
- Calipers, for the panels and the coupons.
- Multimeter; bench supply with a current limit; USB power meter (bring-up steps 1, 2, 9).
- A 3.3 V USB-UART adapter for the debug JST (optional; UART0 on IO43/IO44).
- A pin or paperclip for the BOOT and RESET pinholes in the bottom plate.

## 4. Make: print, laser, mill

The case exists in two variants from one source, `print` and `cnc` (`board.toml` `[variants]`).
They differ only in fits: the print variant gives lenses 0.15 mm a side and cap holes 0.3 mm, the
CNC variant 0.10 and 0.10.

### 4.1 Coupons first

Print `cad/exports/coupons/` before the case. Each coupon checks one fit that is MEASURE:

| Coupon | Checks |
| --- | --- |
| `mx-cutout` | an MX switch clips into the 14.0 mm plate hole |
| `cap-hole` | a B3F cap moves freely in its deck hole |
| `knob-hole` | the EC11 bushing passes the deck hole |
| `knob-bore` | the knob bore grips the 6 mm D shaft |
| `fpc-big`, `fpc-narrow` | each panel tail folds through its board slot |
| `usb-base`, `usb-top` | the USB4216 and a cable plug fit the opening |
| `module-stack` | the module stack clears the plate (0.9 mm) |
| `insert-boss` | a bought M2 heat-set insert presses into its pocket, and an M2 screw holds in it |

Write each result into the hardware record (`docs/bringup.md`).

### 4.2 3D-printed prototype (print variant)

| Part | File | Qty | Notes |
| --- | --- | --- | --- |
| Top shell | `print/shell.3mf` (or `.stl`, `.step`) | 1 | deck, key well, MX plate, display pockets |
| Bottom plate | `print/plate.3mf` | 1 | standoffs, key ribs, encoder posts, BOOT/RESET pinholes |
| Antenna insert | `print/insert.3mf` | 1 | the back-wall window for the Wi-Fi antenna; no metal |
| Knob dial | `knob/dial.3mf` | 3 | resin prints the flutes cleaner than FDM |
| Button cap | `b3f-cap/print.3mf` | 4 | press-on cap on the B3F plunger |
| Display carriers | `carriers/big.3mf`, `carriers/narrow.3mf` | 1 + 1 | stand on the PCB and hold each panel up; height MEASURE from the calipered panel |

Print notes (`docs/research/11-case-cad.md` section 4):

- Print in black. Light filament glows through thin walls around the displays.
- FDM holds about 0.2 mm; the print fits allow for it.
- Printed face down, the MX plate is a 60 mm roof. The orientation is not settled; the earlier
  `macropad` project printed its top shell on its side.
- The longest part is 173.5 mm. Check the bed size (open question 5).
- Press the 6 M2 heat-set inserts into the shell's boss pockets with a soldering iron, flush with
  the boss foot, before assembly.
- A print service such as JLC3DP takes STL, STEP and 3MF: 48 to 120 hours plus shipping, about 15 to
  50 USD (report 12, unverified).

### 4.3 Laser-cut parts

| Part | File | Material | Qty |
| --- | --- | --- | --- |
| Big lens | `2d/lens-big.dxf` | 1.0 mm acrylic | 1 |
| Strip lens | `2d/lens-narrow.dxf` | 1.0 mm acrylic | 1 |
| Big foam frame | `2d/foam-big.dxf` | 0.5 mm black foam | 1 |
| Strip foam frame | `2d/foam-narrow.dxf` | 0.5 mm black foam | 1 |

The files are 1:1 in mm, layer `CUT`. SVG and PDF copies sit beside each DXF. The lens outlines fit
the CNC recess; in the print case the recess is 0.05 mm wider a side. The narrowest foam strips are
1.0 mm wide.

### 4.4 CNC case (after the printed case fits)

| Part | File | Process |
| --- | --- | --- |
| Top shell | `cnc/shell.step` (AP214) or `cnc/shell.ap242.step` | 6061 aluminium, 2 setups |
| Bottom plate | `cnc/plate.step` | 6061 aluminium, 1 setup |
| Antenna insert | `cnc/insert.step` | black PC or POM, never metal |
| Knob dial | `knob/dial.step` | turned 6061, M3 set screw on the flat |
| Button cap | `b3f-cap/cnc.step` | floating cap, flange under the deck |

Order notes (report 12):

- Send each part as its own file and order line. A multi-body STEP waits for manual review.
- Add the A3 PDF drawing from the CNC pack (`cnc-pack/shell.pdf`, `cnc-pack/plate.pdf` in the case
  zip). It tolerances the MX holes at 14.0 ± 0.05 mm; the default ISO 2768-m is too loose for them.
- Threads: the shell has 6 blind M2 holes, 4.0 deep thread on a 1.6 x 5.0 drill (row T1). Tick
  "Threads-YES". Tap after anodise, or mask the holes. The plate's 6 holes are countersunk 90 x 4.0
  on the outer face, which needs a second setup.
- Finish: bead blast, then black Type II anodise. Order all anodised parts in one batch, since the
  colour shifts between batches. Name the rack-mark faces.
- Shops: JLCCNC (from 3 business days) or PCBWay. About 130 to 380 USD for one machined case with
  laser mark and shipping, before import tax (estimate from two anecdotes).

**Laser engraving** runs last, after anodising. File: `laser/deck.dxf` (layer `MARK` engraves,
layer `REF` only registers). It marks a tick scale round each knob, the knob digits 1 to 3, a dot
in front of each button, and the `macropad-obs` wordmark. Print `laser/deck.pdf` at 1:1 on paper
and lay it on the deck first, then ask the shop for a test mark on a blasted black coupon.

## 5. Assembly

The order below follows the stack in `board.toml` `[stack]` and report 11 section 5. It is
unchecked on real parts.

1. **Board.** Solder the 4 B3F buttons and 3 EC11 encoders on the top face. Do bring-up steps 1 to
   5 (`docs/bringup.md`) before anything goes into the case.
2. **Flash the firmware** (section 6) while the board is bare and the BOOT and RESET switches are
   easy to reach.
3. **CNC case only:** drop the 4 floating button caps into their deck holes from inside the shell.
   Their flanges sit under the deck, so they must go in before the board.
4. **Shell face down.** Lay a foam frame on the deck underside in each display pocket.
5. **Panels.** Lay each panel face down on its foam, inside the pocket walls. The tail edge faces
   the keys (big panel) or the knobs (strip). Set a carrier on each panel.
6. **Board in.** Thread each panel tail through its board slot, then lower the board onto the
   carriers with the encoder bushings through their deck holes. Each carrier now holds its panel
   against the foam. No glue anywhere.
7. **Tails.** Plug each tail into its FH12 connector on the board's bottom face.
8. **Antenna insert.** Fit it in the back wall at x 56.0 to 87.6. Its tongue fills the plate cut
   under the antenna. The insert's fixing is MEASURE.
9. **Bottom plate.** Close the case with the plate. Its standoffs sit under the board's 6 holes, and
   its ribs and posts back the key sockets and encoders. Drive the 6 M2 x 12 countersunk screws up
   through plate, standoffs and board into the bosses (tapped in the CNC case, inserts in the
   printed one). Snug only: the bosses clamp the board, and over-tightening strips a printed boss.
10. **Switches.** Press the 9 MX switches into the plate from the top. Their pins go into the
    hot-swap sockets.
11. **Caps and knobs.** Fit the 9 DSA keycaps. Print case: press the 4 button caps onto the
    plungers. Fit the 3 knob dials on the shafts with the index slot on the flat side, and tighten
    each M3 set screw.
12. **Lenses.** Tape each lens onto its ledge in the deck top.

## 6. Firmware

The image is `macropad-obs-merged.bin` in the firmware zip (or `.build/esp32s3/` after `just
firmware`). It flashes at offset 0x0.

1. Install the udev rule once (README "udev").
2. Enter the ROM loader: hold BOOT, tap RESET, release BOOT. In the closed case, use the two
   pinholes in the bottom plate (BOOT at x 40.0, RESET at x 52.0). `lsusb` should list 303a:1001.
3. Flash: `just flash /dev/ttyACM0` from the repo (esptool in the ESP-IDF image), or esptool
   directly: `esptool --chip esp32s3 write-flash 0x0 macropad-obs-merged.bin`.
4. Tap RESET. `lsusb` should list 1209:4f42.

Later updates can go through the app's firmware page.

## 7. App and OBS setup

1. Unpack the app tarball. It needs `webkit2gtk-4.1` on the system. Install the udev rule from the
   same tarball.
2. In OBS (30.1 or newer, obs-websocket 5.4.0 or newer): Tools > WebSocket Server Settings, enable
   the server, keep port 4455, and set a password.
3. Give the OBS PC a fixed LAN address. The pad accepts only `ws://<private IPv4>[:port]`: no host
   name, no `wss://`, no path (`docs/config.md` "URL rule").
4. Let the pad reach port 4455 on the OBS PC through its firewall.
5. Plug in the pad and start the app. On the "Wi-Fi and OBS password" page, set the 2.4 GHz SSID,
   its passphrase and the OBS password. On the mapping page, set the WebSocket URL, then map keys,
   buttons and knobs to scenes and inputs. The display page sets what each screen shows.
6. The passwords go to the pad only. The app never reads them back (`CLAUDE.md`).

`docs/obs.md` covers the connection and the error lines the strip shows.

## 8. Cost summary

All figures are estimates from `docs/research/12-fabrication.md`, before import tax, with no live
quote.

| Item | USD |
| --- | --- |
| 5 assembled boards, JLCPCB Standard, express shipping | 230 to 340 |
| Big display | about 40 |
| Strip display | by quote |
| 9 switches, 9 keycaps, 7 hand parts, foam, acrylic, 6 screws, 6 inserts | not priced |
| Printed case, at home | under 5 |
| Printed case, service | 15 to 50 |
| Machined case, anodised, laser marked, shipped | 130 to 380 |

## 9. Rebuild the files yourself

From a clone of the repo:

| Command | Writes |
| --- | --- |
| `just pcb` | KiCad project in `pcb/kicad/`, fab set in `pcb/.build/fab/` |
| `just pcb step` | board STEP in `pcb/.build/step/` |
| `just cad` | `cad/exports/`, the renders, and the CNC pack in `.build/cad/cnc/` |
| `just firmware` | `.build/esp32s3/macropad-obs-merged.bin` |
| `just gate` | lists open MEASURE tags; exit 0 means the board may be ordered |

`just cad` needs `cad/.venv`: create it with `uv` from `cad/pyproject.toml`. The PCB and firmware
steps run in Docker.
