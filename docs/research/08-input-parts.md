# 08. Switches, small buttons, encoders and the matrix

Research only, 2026-11-18. This file is the only file written. Second pass: the first draft was
re-read against its sources and cut by a quarter. Tags: **verified** (read in this pass in the primary
source or a local file), **likely** (reasoned, or carried from the first pass and not re-read),
**unverified**. MEASURE marks a size that no datasheet drawing gives. Heights are above the PCB top
face. The board is 1.6 mm. Keys such as `[A1]` point into Sources.

## Recommendation

1. **Keys.** 9 MX switches, 5-pin, in Kailh CPG151101S11-1 hot-swap sockets on the bottom face. The
   top is the switch plate: 14.0 mm square holes in a 1.5 mm web, web top 5.0 mm above the PCB.
   Keycaps: blank DSA.
2. **Small buttons.** 4 Omron B3F-1050: 6 x 6 mm, through-hole, 0.98 N, 1,000,000 presses, 2.4 mm
   square stem at 7.3 mm. The round black plunger of the owner's picture is the B3F-1060 (7.0 mm)
   or B3F-1020 (5.0 mm). All three use the same holes.
3. **Knobs.** 3 Alps EC11E18244AU: 36 detents, 18 pulses, push, 6 mm flat shaft. Held by its solder
   joints. The top gets a 7.4 mm clearance hole, no nut.
4. **Matrix.** 4 drive lines by 4 sense lines, one Schottky diode per contact, 16 contacts: 9 keys,
   4 buttons, 3 knob pushes. Encoder A and B go on 6 dedicated GPIO with an RC filter each.
   14 GPIO in all.
5. **Firmware.** One 1 kHz tick scans the matrix and samples the six encoder pins. Debounce 10 ms.
   Count edges of A only.

Next action: the case report (11) takes the height tables below. Three of its numbers change, see
"Conflicts".

## Heights

Keys:

| Level | mm | Source | Conf. |
| --- | --- | --- | --- |
| Plate top, the switch seat. Plate 1.5 +0.1 thick, hole 14.0 ±0.05, corner R 0.3 max | 5.0 | `[C1]` | verified |
| Housing top, 15.6 square | 11.6 | `[C1]` | verified |
| Stem top, not pressed. Travel 4.0 -0.4 | 15.2 | `[C1]`, 11.6 + 3.6 | verified |
| DSA cap top. Cap 7.39 tall, 18.4 base, 12.7 top | about 18, MEASURE | `[S1]`; seat depth is not drawn | cap size verified, height unverified |
| Under the board: switch pins 1.7, socket 1.85 ±0.1 | below | `[C1]` `[K1]` | verified |

Small buttons:

| Level | mm | Source | Conf. |
| --- | --- | --- | --- |
| B3F body top, 6.0 x 6.0 ±0.2 | 3.4 | `[O1]` p. 4 | verified |
| B3F-1050 stem top. Stem 2.4 x 2.4 ±0.1, 1.8 tall | 7.3 ±0.2 | `[O1]` p. 5 | verified |
| Round flat plunger top, 3.5 dia: -1000, -1020, -1060, -1070 | 4.3, 5.0, 7.0, 9.5 | `[O1]` p. 4, 5 | verified |
| B3F-1050 with a B32 cap. Panel top 1.0 to 2.0 below the cap top | 10.0 ±0.4 | `[O2]` p. 2 | verified |
| Under the board: leads 1.9 (3.5 from the seat) | below | `[O1]` | verified |

Encoder and diode:

| Level | mm | Source | Conf. |
| --- | --- | --- | --- |
| EC11E body top, 11.7 x 12.0 frame | 4.5 | `[A1]` drawing No. 2 | verified |
| Bushing top. 7 dia, plain, no thread | 11.5 | `[A1]` `[A2]` | verified |
| Shaft end. 6.0 -0.05 dia, flat 4.5 -0.1 across from 14.5 up. Push travel 0.5 ±0.3 | 24.5 | `[A1]` `[A2]` | verified |
| Under the board: terminals 1.9 (3.5 from the seat) | below | `[A1]` | verified |
| SOD-123 diode, bottom face | 1.35 max | `[D2]` | verified |

Keep 2.5 mm free under the board, or trim the leads. (likely)

## 1. MX keys

1. **Socket.** Bosses of 2.90 mm sit in two 3.00 mm holes, 6.35 and 2.54 mm apart. Pads 2.55 x
   2.5 mm. 12 V, 10 mA. The 2021 drawing of the -1 part says 5000 cycles. The older spec of the
   part without the suffix says 100. (verified, `[K1]` `[K2]`)
2. **Footprint.** KiCad ships none. Copy `MX_Hotswap.kicad_mod` from macropad-greycode with its
   line in `SOURCES.txt`. Its holes and pads match the Kailh drawing. Kailh does not dimension the
   pad centres: MEASURE. (verified by comparing the numbers, `[L1]` `[L4]`)
3. **The plate holds the switch. The socket holds only the pins.** A printed top will not hold
   ±0.05 mm: print a one-hole coupon first. A milled top needs dog-bone corners or a 0.5 mm cutter
   for R 0.3. 5-pin switches add two pegs that locate the switch on the PCB. (hole verified,
   `[C1]`; advice likely)
4. **Keycaps.** DSA is one uniform profile: all nine caps are the same part. The big display labels
   the keys, so blank caps fit. Signature Plastics also lists a 1 x 1 relegendable cap. (cap data
   verified, `[S1]`; the choice is the owner's)
5. **Electrical.** 12 V and 10 mA max, 10 µA min, bounce 5 ms max, pitch 19.05 mm. (verified,
   `[C1]`)

## 2. Small buttons

| Option | Force, life | Top above PCB | Cap | Verdict |
| --- | --- | --- | --- | --- |
| Omron B3F-1050, square stem | 0.98 N, 1,000,000 | 7.3 mm | Omron B32, or custom | chosen |
| Omron B3F-1060 or -1020, round black plunger | 0.98 N, 1,000,000 | 7.0 or 5.0 mm | floating cap, trapped under the top | the owner's picture, same holes |
| Omron B3F-1052 | 1.47 N, 300,000 | 7.3 mm | as the -1050 | firmer |
| Alps SKPMAPE010, SMD, "Soft feeling type" | 2.45 N, 100,000, travel 1.3 mm | 5.0 mm | none listed | softer, short life |
| C&K PTS645, E-Switch TL1105, MEC Multimec 5G | 100,000 (MEC 10,000,000) | 4.3 mm and up | square stems, MEC snap-on caps | second sources, not re-read: likely |

(verified: `[O1]` `[A4]`)

1. **One hole pattern.** Every 6 x 6 mm B3F uses four 1.0 mm holes at 6.5 x 4.5 mm. The stock
   footprint `SW_TH_Tactile_Omron_B3F-100x` has exactly these. No footprint is named for the 105x.
   (verified, `[O1]` `[L1]`)
2. **Ratings.** Bounce 5 ms max. Pretravel 0.25 mm. 1 to 50 mA at 3 to 24 V DC, minimum load 10 µA
   at 1 V. (verified, `[O1]` p. 3)
3. **Stock caps stand proud.** B32-1010 (black, 4 x 4 mm, panel hole 4.2 mm square) and B32-2010
   (black, 6 mm round, hole 6.5 mm) need a top face 8.0 to 9.0 mm above the PCB. (verified, `[O2]`)
4. **A flush cap, two ways on the same switch.** Printed: a press-on cap with the B32 socket, 2.5 mm
   square and 2.8 mm deep. Machined: a floating cap with a round 3.6 mm bore and a flange under the
   top. The stem diagonal is 3.39 mm, so the round bore clears it. Report 11 draws the floating cap.
   (socket verified, `[O2]`; fits MEASURE)
5. **Through-hole, not SMD.** Four legs take the press force and the side load of a tall cap. The
   encoders need hand soldering anyway. No datasheet gives a sound level. (likely)

## 3. Encoders

1. **Detents.** 36 detents and 18 pulses give 2 edges per detent: one of A, one of B. Sister parts:
   30 and 15 (EC11E15244G1), 18 and 9 (EC11E09244BS). Each also exists with a 1.5 mm push. All
   have a flat shaft of 20 mm. (verified, `[A1]`)
2. **B is not settled at a detent.** Alps: "The stable detent position cannot be identified in
   phase B." Count debounced edges of A and read B for the direction. The owner's
   `quadrature.rs` already does this (`Detents::PerEdgeOfA`). (verified, `[A2]` `[L3]`)
3. **Ratings.** Contacts 10 mA 5 V DC, "10mA/1mA" max and min. Chattering 3 ms max, bounce 2 ms
   max. Life 15,000 cycles. Push: 6 N (+2.5, -2), 20,000 presses, 0.1 A 5 V DC, 500 µA min.
   Terminals D and E are separate from A, B and C, so the push sits in the matrix. (verified,
   `[A2]`)
4. **Mounting.** Five 1.0 mm holes and two lug slots. Push-pull strength 100 N. Every press puts
   6 N into the board: put a PCB support near each encoder. (verified, `[A1]` `[A2]`; support
   advice likely)
5. **Knob.** Bore 6 mm, M3 set screw on the flat. The flat is 10 mm long. Over a deck at 8 mm the
   bushing stands 3.5 mm proud: the knob needs an 8 mm counterbore and a 1.0 mm gap to the deck.
   The knob top lands near 26 mm above the PCB. (arithmetic on verified sizes)

| Part | Body | Shaft end | Detents / pulses | Life: turns, presses | Fit |
| --- | --- | --- | --- | --- | --- |
| Alps EC11E15244G1 | 4.5 mm | 24.5 mm | 30 / 15 | 15,000, 20,000 | same footprint, coarser step |
| Bourns PEC11L-4x15F-S, "Low Profile" | 4.5 mm | 19.5 mm (24.5 with the 20 mm shaft) | 20 / 20, 30 / 15, 18 / 9 | 100,000, 100,000 | the upgrade. Signal pins match, lugs 12.8 mm apart: own footprint. M7 x 0.75 thread |
| Bourns PEC11R-4x20F-S | 6.5 mm | 20 mm from the PCB (likely) | 18 / 18, 24 / 24, 24 / 12 | 30,000, 20,000 | taller body, own footprint. M7 x 0.75 thread |
| Alps EC12E | not read | 15 to 30 mm shafts | 12 / 12, 24 / 24 | 30,000 | rejected: no push switch in the list, insulated shaft, rated 0.5 mA |

(verified: `[B1]` `[B2]` `[A3]`. KiCad has no PEC11L or PEC11R footprint, `[L1]`.)

Clone "EC11" parts often have a 6.5 mm body: MEASURE any part that is not from Alps. (unverified)

## 4. Matrix

| | SENSE0 | SENSE1 | SENSE2 | SENSE3 |
| --- | --- | --- | --- | --- |
| DRIVE0 | key 1 | key 2 | key 3 | knob 1 push |
| DRIVE1 | key 4 | key 5 | key 6 | knob 2 push |
| DRIVE2 | key 7 | key 8 | key 9 | knob 3 push |
| DRIVE3 | button 1 | button 2 | button 3 | button 4 |

1. Each contact: one terminal to its SENSE line, the other to a diode anode, the cathode to its
   DRIVE line. QMK calls this `COL2ROW`: "the black mark on your diode is facing to the rows".
   (verified, `[Q1]`)
2. SENSE pins are inputs with pull-ups. One DRIVE pin at a time is an output at low. The other
   three are inputs. (verified, `[Q1]` `matrix.c`) No pull-downs anywhere: the rule is from
   report 04.
3. One diode per contact: no ghost keys, any number of keys held.
4. Encoder lugs and terminal C go to ground.

### Diode

**Pick: a Schottky in SOD-123 (onsemi BAT54T1G class) with 4.7 kΩ pull-ups on the four SENSE
lines.** Footprint `Diode_SMD:D_SOD-123`, symbol `Device:D_Schottky`. The 1N4148W fits the same
pads.

| | BAT54T1G, 4.7 kΩ pull-ups | 1N4148W, internal pull-ups |
| --- | --- | --- |
| Forward voltage | 0.32 V max at 1 mA | 0.715 V max at 1 mA |
| Input-low limit | RP2350 0.8 V, ESP32-S3 0.825 V | same |
| Contact current | 0.64 mA | 0.03 to 0.09 mA |
| Extra parts | 4 resistors | none |

(verified: `[D1]` `[D2]` `[M1]` `[M2]`. Internal pull-ups: RP2350 32 to 86 kΩ, ESP32-S3 45 kΩ.)

1. The 1N4148W works and most keyboards use it. Its worst-case margin is under 0.1 V. Its contact
   current is under the 500 µA minimum of the EC11 push.
2. The Schottky meets that minimum. Set the RP2350 DRIVE pins to 12 mA: four held keys sink
   2.6 mA, and the 0.5 V output-low limit is quoted at the set current. The sense low is then about
   0.45 V. (likely: arithmetic on verified limits)
3. Put the 16 diodes on the bottom face with the sockets.

### Scan and debounce

1. **Tick.** 1 kHz. Per DRIVE line: pull low, wait, read four pins, release. QMK waits 30 µs by
   default. Four waits cost 0.12 ms, 12 % of the tick. A 100 pF line on 4.7 kΩ settles in 0.5 µs,
   so 5 µs should do: MEASURE on a scope. (30 µs verified, `[Q1]`; 100 pF is a guess)
2. **Debounce.** Keep `INPUT_DEBOUNCE_MS 10`. Cherry MX and B3F both give 5 ms max. QMK defaults to
   5 ms. The key loop in `firmware/input.c` already takes a 16-bit mask: `INPUT_KEYS` goes from 9
   to 16. (verified, `[C1]` `[O1]` `[Q1]` `[L2]`)
3. **Push bounce** of the EC11 is not in the Alps data. 10 ms is assumed to cover it. (unverified)

### Encoder A and B

1. **Dedicated GPIO: six pins.** A scanned line cannot carry an RC filter. Route each pair to
   adjacent pins: the Pico PIO decoder reads `IN PINS, 2`. (verified, `[P1]`; the filter point is
   reasoning)
2. **Filter per phase.** Alps and Bourns draw the same network: 10 kΩ pull-up to 5 V, 10 kΩ in
   series, 0.01 µF to ground. At 3.3 V use a 3.3 kΩ pull-up for the 1 mA minimum, 10 kΩ and 10 nF.
   Time constant 100 µs falling, 133 µs rising. 18 parts. Up to 2 mA standing per encoder.
   (network verified, `[A2]` `[B1]`; the 3.3 V values are likely)
3. **Sample, do not interrupt.** Read all six pins in the tick. Accept an A edge after 3 equal
   samples. With 3 ms of chatter that follows about 2 turns per second: at 1 turn per second the
   edges are 13.9 ms apart. For faster spins sample at 4 kHz. MEASURE. (arithmetic)
4. **The encoder half of `firmware/input.c` is a rewrite.** It handles one knob, counts both
   phases and has no debounce. (verified, `[L2]`)

## KiCad footprints

All exist in `kicad/kicad:9.0.9` and `kicad/kicad:10.0.7`. (verified, `[L1]`)

| Use | Library:footprint | Note |
| --- | --- | --- |
| MX in a socket | none in stock | project `MX_Hotswap`, copied from macropad-greycode |
| MX soldered | `Button_Switch_Keyboard:SW_Cherry_MX_1.00u_PCB` | `_Plate` has no peg holes |
| Small button | `Button_Switch_THT:SW_TH_Tactile_Omron_B3F-100x` | holes 6.5 x 4.5 mm, drill 1.0 mm |
| Small button, generic | `Button_Switch_THT:SW_PUSH_6mm_H7.3mm` | same pattern, drill 1.1 mm |
| Small button, SMD | `Button_Switch_SMD:SW_SPST_Omron_B3FS-105xP` | not chosen |
| Encoder | `Rotary_Encoder:RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm` | symbol `Device:RotaryEncoder_Switch_MP` |
| Diode | `Diode_SMD:D_SOD-123` | symbol `Device:D_Schottky` |

The encoder footprint puts the lug slots 11.2 mm apart. The Alps drawing gives 11.0 mm (12.5 mm
over the outer edges, 1.5 mm slots). Check one part on a 1:1 print: MEASURE.
`..._CircularMountingHoles` has round 2.6 mm lug holes and needs no slot milling. (verified,
`[L1]` `[A1]`)

## Conflicts

Flagged, not changed.

1. **`pulses_per_detent = 4`** in `board.toml [knob]`. The part gives 2 edges per detent, and Alps
   warns against counting B at rest. (verified)
2. **Encoder and button heights.** `board.toml` has `encoder_body = [12.0, 12.0, 6.5]`. Report 11
   uses a 6.5 mm body, an "M7 x 0.75" bushing and a 3.5 mm tact body. Alps gives 4.5 mm and a plain
   7 mm bushing. Omron gives 3.4 mm. (verified)
3. **Direct key GPIO** in `board.toml [keys]`, and `docs/design.md` rejects a matrix. The owner
   wrote "3x3 keys matrics". This report follows the task's 4 x 4 reading. Report 01 still asks
   whether the owner means a diode matrix.
4. **LCSC.** None of these parts is on the locked list. Every LCSC cell stays `UNVERIFIED`.
5. **Read-only sibling.** `macropad-greycode/board.toml:19` says "18 detents" for the same part.
   Alps says 36. Not edited.

## Sources

Read in this pass:

- `[A1]` Alps EC11E catalog, Update 2510: <https://tech.alpsalpine.com/cms.media/product_catalog_ec_01_ec11e_en_611f078659.pdf>
- `[A2]` Alps EC11E18244AU page and its figures: <https://tech.alpsalpine.com/e/products/detail/EC11E18244AU/>
- `[A3]` Alps EC12E catalog: <https://tech.alpsalpine.com/cms.media/product_catalog_ec_02_ec12e_en_83b4ff2fe9.pdf>
- `[A4]` Alps SKPMAPE010: <https://tech.alpsalpine.com/e/products/detail/SKPMAPE010/>
- `[O1]` Omron B3F: <https://omronfs.omron.com/en_US/ecb/products/pdf/en-b3f.pdf>
- `[O2]` Omron B32 key tops: <https://omronfs.omron.com/en_US/ecb/products/pdf/en-b32.pdf>
- `[K1]` Kailh drawing KHA-PG1511-319EN, CPG151101S11-1, on a distributor's server: <https://atta.szlcsc.com/upload/public/pdf/source/20221101/4EDD6C60B6ADE24F38491FFDD9B635E1.pdf>
- `[K2]` Kailh spec KH-PS1607-10, CPG151101S11, same server: <https://atta.szlcsc.com/upload/public/pdf/source/20220228/B04A6FE76F6176D3365CC186B3035FED.pdf>
- `[C1]` Cherry "Keymodule" brochure, on a distributor's server: <https://www.farnell.com/datasheets/16916.pdf>
- `[B1]` Bourns PEC11L, Rev. 04/26: <https://www.bourns.com/docs/Product-Datasheets/PEC11L.pdf>
- `[B2]` Bourns PEC11R: <https://www.bourns.com/docs/Product-Datasheets/PEC11R.pdf>
- `[D1]` onsemi BAT54T1/D, Rev. 12: <https://www.onsemi.com/pdf/datasheet/bat54t1-d.pdf>
- `[D2]` Diodes Inc. 1N4148W: <https://www.diodes.com/assets/Datasheets/ds30086.pdf>
- `[M1]` RP2350 datasheet, table 1683: <https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf>
- `[M2]` ESP32-S3 datasheet: <https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf>
- `[Q1]` QMK `docs/config_options.md`, `docs/feature_debounce_type.md`, `quantum/matrix.c`, `quantum/matrix_common.c`: <https://github.com/qmk/qmk_firmware/tree/master>
- `[P1]` Pico examples, `quadrature_encoder.pio`: <https://github.com/raspberrypi/pico-examples/tree/master/pio/quadrature_encoder>
- `[S1]` Signature Plastics DSA family: <https://pimpmykeyboard.com/template/images/DSAFamily.pdf>
- `[L1]` KiCad libraries in the local images `kicad/kicad:9.0.9` and `kicad/kicad:10.0.7`
- `[L2]` `/home/worxbend/Projects/macropad-obs/board.toml`, `firmware/input.h`, `firmware/input.c`
- `[L3]` `/home/worxbend/Projects/macropad/firmware/core/src/quadrature.rs`
- `[L4]` `/home/worxbend/Projects/macropad-greycode/pcb/lib/greycode.pretty/MX_Hotswap.kicad_mod`, `pcb/lib/SOURCES.txt`, `board.toml`

Read in the first pass only:

- C&K PTS645: <https://docs.rs-online.com/f61e/0900766b815a8e5f.pdf>
- E-Switch TL1105: <https://www.e-switch.com/wp-content/uploads/2022/06/TL1105.pdf>
- MEC Multimec 5E/5G: <https://cdn.soselectronic.com/productdata/80/f6/aabf7be6/5gth9358222.pdf>

## Open questions

1. Does the owner want hot-swap sockets? The requirement says "MX switches" only. Both earlier
   boards use sockets.
2. Button caps: stock Omron B32 caps that stand 1 to 2 mm proud, or custom flush caps? Must the
   plunger be round and black as in the picture (B3F-1060)? The answers set the deck height.
3. Alps lists 1 mA minimum for the encoder contacts, yet its example circuit gives 0.5 mA. Is a
   3.3 kΩ pull-up needed, or is 10 kΩ enough?
4. Are the owner's EC11E18244AU parts from Alps, or clones with a 6.5 mm body? Is 15,000 turns
   enough? If not, the Bourns PEC11L needs its own footprint.
5. MEASURE list: seated keycap height, printed plate fit, cap fit on the stem, matrix settle time,
   fast-spin tracking. Is switch noise near a microphone a concern?

Not checked: prices, stock, LCSC numbers, sound levels, low-profile SMD encoders, the PEC11R shaft
datum. Risk: the 3.3 V filter values and the 2 turns per second limit are arithmetic, not bench
results.
