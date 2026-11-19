# 10. Block-level electrical design

Research only, 2026-11-18. This file is the only file written. Confidence tags: **verified** (read
today in a primary source, or run today), **likely** (reasoned from a verified fact, read in a copy
that is not the maker's own, or carried from another report and not re-read), **unverified**.
**MEASURE** marks a size I did not read in a datasheet drawing. Keys such as `[R2]` point into the
Sources list. No hardware was used. No schematic was drawn.

## Recommendation

Keep the USB and power blocks of the owner's earlier boards and put them round RP2350B, the first
choice of report 04: USB-C, 5.1 kΩ on each CC pad, an ESD part, a fuse, and AP2112K-3.3 with its
enable pin tied to its input. Add six new blocks: two constant-current backlight sinks fed from
5 V, a 40-pin and a 10-pin 0.5 mm FPC connector, a 4 x 4 Schottky-diode matrix, filtered encoder
inputs and a 3-pin debug connector.

If the ESP32-S3 module is chosen instead, change two things: a buck converter in place of the
linear regulator, and a firmware limit on current.

Next action: the owner answers question 1 of report 04, "Must Wi-Fi ever work?". The answer picks
the regulator here.

Five findings carry the recommendation.

1. **A radio does not fit a linear regulator on USB power.** The RP2350B design draws about 310 mA
   from VBUS. An ESP32-S3 module peaks at 355 mA on 3.3 V `[E1]`; with 220 mA of backlight that is
   about 615 mA through a linear regulator and about 510 mA through a buck. USB 2.0 allows 500 mA
   `[U2]`. (verified inputs; the sums are arithmetic)
2. **Both backlights must run from 5 V.** The panels need 2.8 to 3.4 V and 3.2 V across their LEDs
   `[L5]` `[D2]`. A 3.3 V rail leaves no headroom. The datasheets ask for constant current `[D1]`.
   (verified for the bar and for QD3525; the big panel's numbers are from report 06)
3. **No display tail fits the repo's locked 20-pin connector.** The big panel has 40 pins, the bar
   10 or 12 `[L5]`. The 3.5 inch QD3525 that report 07 used as a reference has a solder tail:
   "P0.8*47=37.60" `[D1]`. (verified for QD3525 and the bar; likely for the rest)
4. **Every contact wants about 1 mA, and a silicon diode then eats the logic-low margin.** Alps
   rates the encoder at "10mA/1mA" maximum and minimum `[P9]`. A 1N4148W drops up to 0.715 V at
   1 mA `[P6]`. Logic low ends at 0.8 V on RP2350 `[R3]` and 0.825 V on ESP32-S3 `[E1]`. A BAT54
   drops 0.32 V `[P7]`. Report 08 reached the same pick. (verified)
5. **`pcb/gen/circuit.py` describes a board that would not start.** The regulator enable pin is
   open and the part pulls it low. The crystal has one connected pad. The USB-C connector has no
   ground. (verified: run today, `[L1]` `[P1]` `[R1]`)

Full-speed USB on the default 4-layer stackups needs no paid impedance control. A 0.22 mm track
with a 0.15 mm gap lands within 10% of 90 Ω at both fabs. (likely, `[X1]`)

## The owner's words that drive this topic

- "I want 4layers or more PCB, with 3x3 keys matrics, MX switches"
- "also 2 displays one bigger and one longer, also one tray of buttons [...] small buttons"
- "firmware on the device should be communicating with this websocket OBS url"

The owner's answers add three encoders with push, four tact buttons, and a big display of about
3.2 to 3.5 inch. Report 04 names RP2350B first and ESP32-S3-WROOM-1-N16R8 second. Report 06 picks
the Focus E35GH-I-RW300-N. Report 07 picks a 2.79 inch bar. Report 08 picks the input parts. `[L5]`

## Options compared

| Option | For | Against |
| --- | --- | --- |
| A. RP2350B + AP2112K | About 310 mA on VBUS. Regulator, ESD part and fuse are on two sibling boards | Core inductor with a fixed orientation. Crystal and flash on our board. No radio |
| B. ESP32-S3-WROOM-1 + buck (TLV62569 class) | Radio inside. No crystal, flash or RF parts on our board | About 510 mA peak: needs a firmware cap. Inductor and 5 more parts. Antenna keep-out |
| C. ESP32-S3-WROOM-1 + AP2112K | Fewest parts | About 615 mA peak. Up to 0.67 W in a SOT-25. Rejected |
| Backlight: constant-current sink (BCR421U class) | What the panel datasheets ask for. PWM on the enable pin | Needs about 1.4 V of headroom; dims at low VBUS with a high-Vf panel |
| Backlight: N-FET + resistor | Two cheap parts | Current moves with VBUS (4.4 to 5.25 V) and Vf (2.8 to 3.4 V). Fallback only |
| Matrix diode: BAT54 class | 0.32 V at 1 mA; about 0.5 V of margin | Needs 4 pull-up resistors |
| Matrix diode: 1N4148W | Common. Same SOD-123 pads | 0.715 V at 1 mA; under 0.1 V of margin |

## The blocks

### 1. USB-C device port

1. **Receptacle.** A 16-pad USB 2.0 Type-C part. Pads: A1/B12 and B1/A12 (GND), A4/B9 and B4/A9
   (VBUS), A5 and B5 (CC1, CC2), A6 and B6 (D+), A7 and B7 (D-), A8 and B8 (unused). (verified on
   the GCT USB4105 drawing, `[P10]`)
2. **CC.** One 5.1 kΩ resistor from each CC pad to ground, never shared. With ±10% parts the device
   may also read the source's current offer; with ±20% it may not. (verified, `[U1]` table 4-28)
3. **D+ and D-.** Join A6 to B6 and A7 to B7 at the pads. "The maximum shorting trace length should
   not exceed 3.5 mm." (verified, `[U1]`)
4. **Shell.** Tie it straight to the ground plane. The Raspberry Pi minimal design does `[R1]`
   figure 4. The cable already joins shield and ground inside each plug `[U1]`. (verified)
5. **Protection.** A fuse in VBUS, then a low-capacitance ESD part on D+ and D- at the connector,
   with a clamp to VBUS. (likely: the sibling boards' circuit, `[L3]`)

Two USB 2.0 limits shape the rest. (verified, `[U2]`)

- VBUS may carry 1 to 10 µF of bypass in total (table 7-7 and the Device Capacitance ECN). Larger
  capacitors go behind the regulator.
- A device may draw 100 mA until it is configured and 500 mA after. Backlights and any radio stay
  off until then.

Optional, 2 ADC pins: CC1 and CC2 through 100 kΩ each to the MCU. A source that offers 1.5 A or
3 A shows 0.746 V or more on CC (`[U1]` table 4-36, verified). The firmware could then lift its
cap. The 100 kΩ value is mine. (likely)

### 2. 3.3 V regulation and the power budget

| Load | Rail | Current | Source | Conf. |
| --- | --- | --- | --- | --- |
| RP2350 running USB | 3.3 V | 16 mA (52.7 mW) | `[R3]` table 1693 | verified |
| Flash, and PSRAM if fitted | 3.3 V | 30 mA | allowance | unverified |
| Two panels, logic | 3.3 V | 30 mA | allowance; `[D2]` says "TBD" | unverified |
| 4 sense pull-ups, 6 encoder pull-ups | 3.3 V | 0 to 9 mA | arithmetic | verified |
| ESP32-S3 module, Wi-Fi transmit | 3.3 V | 355 mA peak | `[E1]` table 6-4 | verified |
| ESP32-S3 module, Wi-Fi receive | 3.3 V | 95 to 97 mA | `[E1]` table 6-4 | verified |
| ESP32-S3 module, radio off, 240 MHz | 3.3 V | 33 to 108 mA | `[E1]` table 6-6 | verified |
| Big backlight, Focus panel | 5 V | 120 mA | `[L5]` report 06 | likely |
| Bar backlight | 5 V | 100 mA | `[D2]`, `[L5]` report 07 | verified |

VBUS current. A linear regulator passes its load 1:1. A buck at 90% passes 0.73 of it.

| Design | Steady | Peak | Against 500 mA |
| --- | --- | --- | --- |
| A. RP2350B + linear | about 310 mA | about 310 mA | fits |
| B. ESP32-S3 + buck | about 350 mA | about 510 mA | fits only with a cap on brightness or transmit power |
| C. ESP32-S3 + linear | about 390 mA | about 615 mA | does not fit |

The steady figures for B and C assume 170 mA on 3.3 V. That number is mine. (unverified)

1. **AP2112K-3.3.** 600 mA, 250 mV dropout at 600 mA, 1 µF in and out, 184 °C/W in SOT-25. Pin 3
   is the enable pin and has a 3 MΩ pull-down: tie it to VIN. At 86 mA the part burns 0.15 W,
   about 27 °C of rise. At the ESP32-S3 peak it would burn 0.67 W. (verified, `[P1]`)
2. **TLV62569, design B only.** 2 A synchronous buck, 2.5 to 5.5 V in, "up to 95% efficiency",
   SOT-23-5, soft start. Typical circuit: 2.2 µH, 4.7 µF in, 10 µF out. Feedback is 0.6 V, so the
   divider ratio is 4.5 for 3.3 V. (verified, `[P2]`)
3. **Espressif, design B only.** "the output current is no less than 500 mA". 22 µF and 0.1 µF at
   the module's 3V3 pin. "an ESD protection diode and at least 10 μF capacitor" where power
   enters. (verified, `[E2]`, `[E1]` figure 9-1)
4. **Fuse.** The sibling's 0.5 A hold part suits design A. Design B needs about 0.75 A hold.
   (likely; no fuse datasheet read)
5. **RM2 radio footprint on design A.** Report 04 keeps it as an option. I did not read its
   current. If it is fitted, size the regulator as for design B. (unverified)

The bar and QD3525 list 3.3 V as the top of their recommended logic supply `[D1]` `[D2]`. Set the
rail to 3.3 V nominal.

### 3. MCU block, RP2350B (first choice)

From "Hardware design with RP2350" `[R2]` unless tagged. (verified)

1. **Decoupling.** "a 100 nF capacitor per power pin". The QFN-80 has 8 IOVDD and 3 DVDD pins,
   plus QSPI_IOVDD, USB_OTP_VDD and ADC_AVDD. (pin count read off the pinout figure of `[R3]`:
   likely)
2. **Core regulator.** L1 is Abracon AOTA-B201610S3R3-101-T: 3.3 µH, 2.0 x 1.6 x 1.0 mm, with a
   polarity dot `[P11]`. Three 4.7 µF capacitors. 33 Ω and 4.7 µF as a filter on VREG_AVDD. The
   inductor's orientation is part of the design. `macropad` already checks it in code `[L5]`.
3. **Crystal.** Abracon ABM8-272-T3, 12 MHz. One 15 pF capacitor at each crystal pad. 1 kΩ between
   the crystal and XOUT. Pads 2 and 4 to ground.
4. **Flash and boot.** W25Q128JVSIQ with its own 100 nF. QSPI_SS goes to the flash, to a 10 kΩ
   pull-up footprint (not fitted) and through 1 kΩ to the BOOT button. RUN goes to the RESET button.
5. **USB.** 27 Ω in series with each data pin, "placed close to the chip".

Optional PSRAM sits on the second chip select and needs a pull-up, because "GPIOs default to
pull-downs at power-up" `[R2]`. Erratum E9 affects stepping A2; "The pad pull-up still works"
`[R3]`. This design has pull-ups only.

### 4. MCU block, ESP32-S3-WROOM-1 (second choice)

From Espressif's guidelines `[E2]` `[E3]` and the module datasheet `[E1]`. (verified)

1. **No crystal, no flash, no RF matching on our board.** They are inside the module.
2. **EN.** "R = 10 kΩ and C = 1 μF" as a power-up delay. The RESET button pulls EN to ground.
3. **BOOT.** A button from IO0 to ground, with a pull-up. "Do not add high-value capacitors at
   GPIO0". IO3, IO45 and IO46 are also strapping pins: keep them off the matrix.
4. **USB.** IO19 is D-, IO20 is D+. "reserve series resistors (initial value can be 22/33 Ω) and
   capacitors to ground"; the capacitors start unfitted.
5. **UART0.** IO43 and IO44 to the debug connector, with 499 Ω in series with TX.

IO1 to IO14 and IO17 glitch low for 60 µs at power-up. IO18, IO19 and IO20 also glitch high
`[E2]`. Put each backlight enable on a pin that only glitches low.

### 5. Backlight drivers

1. Feed both anodes from 5 V, after the fuse.
2. One sink per panel. Each panel has one anode and one cathode pin. Set 120 mA for the big panel
   and 100 mA for the bar. (`[L5]` reports 06 and 07; `[D2]` verified)
3. **Sink.** Diodes BCR421U: 10 to 350 mA set by one resistor, an enable pin that "can be
   pulse-width modulated (PWM) up to 25kHz", 1.4 V minimum across the part, 1 W in SOT-26. 5.1 Ω
   gives 150 mA. The resistor for 100 and 120 mA comes off the datasheet curve and a bench check.
   (likely: read in a Rev. 4 copy on a reseller's site, `[P4]`)
4. **Default off.** 100 kΩ from each enable pin to ground. PWM near 20 kHz.
5. Each sink burns about 0.2 W at full brightness.

Fallback: AO3400A (threshold 0.65 to 1.45 V, under 48 mΩ at a 2.5 V gate; verified `[P5]`) with
15 Ω for the big panel and 18 Ω for the bar.

### 6. Display connectors

| Panel | Tail | Signals to wire | Conf. |
| --- | --- | --- | --- |
| Big: Focus E35GH-I-RW300-N | 40 pins, 0.5 mm pitch, plug-in | SCL, SDA, CS, D/C, RESET, IOVCC, VCI, LEDA, LEDK | likely, report 06 |
| Bar: Wisevision N279 | 10 pins, 0.5 mm pitch | SDA, SCL, RS, RESET, CS, TE, VDD, LEDK, LEDA, GND | verified `[D2]` |
| Bar: EastRising ER-TFT2.79-2 | 12 pins reported | not read | unverified, report 07 |
| Not picked: QDtech QD3525 | 48 pads, 0.8 mm pitch, 0.40 mm pads, solder type, 6 LED cathodes | | verified `[D1]` |

1. **Big panel straps** (report 06): IM0 to IM2 and RD to IOVCC; DB0 to DB17 and pins 7 to 10 to
   ground. It has no tearing-effect pin.
2. **Connector class.** 0.5 mm ZIF, Hirose FH12: FH12-40S-0.5SH(55) and FH12-10S-0.5SH(55). I could
   not read the Hirose catalog (HTTP 403). Pin counts on offer and mounted height are unverified.
3. **Contact face.** Open for both tails. Report 06 reads the big panel's contacts as on the rear
   face and tags it MEASURE.
4. **Fold.** Report 12 puts every SMT part on the bottom face `[L5]`. Each tail must then reach the
   bottom, round the board edge or through a slot. That is a case question.
5. **Shared pins.** SCL, SDA, D/C and RESET may be shared. Each panel needs its own CS and its own
   backlight pin. Report 04 leaves one bus or two open.

### 7. Switch matrix

Part picks and the scan are in report 08. This is the electrical summary.

1. **Size.** 4 drive lines and 4 sense lines, 16 contacts: 9 MX keys, 4 tact buttons, 3 encoder
   pushes. 8 GPIO.
2. **Diodes.** One per contact. Contact to the sense line, diode anode to the contact, cathode to
   the drive line. One drive line is low at a time; the others float.
3. **Pull-ups.** 4.7 kΩ to 3.3 V on each sense line: 0.64 mA through a closed contact. The EC11
   push needs "500µA 5V DC min" `[P9]`. The Omron B3F is rated "1 to 50 mA, 3 to 24 VDC", with a
   reference minimum load of 10 µA `[P8]`. (verified)
4. **Diode type.** BAT54 class in SOD-123. Sense low is then about 0.3 V against a limit of 0.8 V.
   (verified, `[P7]` `[R3]` `[E1]`; I read the Diodes Inc. sheet, report 08 the onsemi one)
5. **No pull-downs anywhere.** Safe on every RP2350 stepping `[R3]`.

Bounce is 5 ms at most on the B3F `[P8]`.

### 8. Encoder inputs

1. Part: Alps EC11E18244AU. 36 detents, 18 pulses, push switch. (verified, `[P9]`)
2. Terminal C to ground. A and B each to its own GPIO: 6 GPIO.
3. Per phase: 3.3 kΩ pull-up to 3.3 V, 10 kΩ in series, 10 nF to ground (report 08). The pull-up
   gives 1 mA, the rated minimum. The sibling `macropad` uses the same 3.3 kΩ `[L4]`. (verified
   for the rating; likely for the filter values)
4. "At R=5kΩ Chattering: 3ms max. Bounce: 2ms max." `[P9]`. The filter time constant is 0.1 ms.
   It removes spikes, not chatter. The decoder in firmware must take the rest.
5. Push contacts go into the matrix. The two mounting lugs go to ground.

### 9. Debug connector and test pads

1. One 3-pin JST-SH, 1.0 mm pitch: SM03B-SRSS-TB (side) or BM03B-SRSS-TB (top). Same footprint and
   place for both MCU choices. (verified, `[R4]`)
2. RP2350B: pin 1 SWCLK, pin 2 GND, pin 3 SWDIO. `[R4]` also asks for 100 Ω in series at the
   target's pins. (verified)
3. ESP32-S3: pin 1 RX, pin 2 GND, pin 3 TX, on UART0. Once the firmware runs TinyUSB the built-in
   USB debug port is gone, so UART0 is the log path. (likely, report 04)
4. Test pads: 5 V, 3.3 V, GND, RESET (RUN or EN) and BOOT. On RP2350B also 1.1 V.
5. Both buttons, BOOT and RESET, stay on the board in either design.

### 10. Stackup, layers and the USB pair

Default 1.6 mm 4-layer stackups. (verified, `[F1]` `[F2]`)

| Fab | Outer copper | Prepreg, outer to inner | Inner copper | Core |
| --- | --- | --- | --- | --- |
| JLCPCB JLC04161H-7628, also "No requirement" | 0.035 mm | 7628, 0.2104 mm, Dk 4.4 | 0.0152 mm | 1.065 mm, Dk 4.6 |
| PCBWay, 1 oz inner, 70% copper | 0.0175 mm plated to 1 oz | 7628, 0.196 mm raw, 0.1855 mm pressed, Dk 4.74 | 0.035 mm | 1.03 mm, Dk 4.6 |

Layer assignment:

1. F.Cu: hand-soldered parts (encoders, tact buttons), ground pour, few tracks.
2. In1.Cu: power. A 5 V plane with a 3.3 V island.
3. In2.Cu: solid ground. No tracks.
4. B.Cu: every machine-placed part and most tracks.

Ground sits next to the face that carries the parts and the USB pair. `macropad-greycode` is built
this way `[L3]`. Espressif states the rule from the other face: the layer next to the parts is
ground, with "No signal traces here" `[E3]`. (verified)

USB pair for 90 Ω differential on an outer layer over the next plane, with solder mask. The values
come from my own 2D field solver. It reads 49.0 Ω on a single line that the Hammerstad formula
puts near 50 Ω. (likely, `[X1]`)

| Track / gap | JLCPCB 7628 | PCBWay 7628 |
| --- | --- | --- |
| 0.20 / 0.15 mm | 95 Ω | 90 Ω |
| 0.22 / 0.15 mm | 92 Ω | 87 Ω |
| 0.25 / 0.15 mm | 88 Ω | 82 Ω |
| 0.28 / 0.20 mm | 90 Ω | 84 Ω |

Rules for the pair:

1. Target 90 Ω. USB 2.0 gives the cable ±15%, 76.5 to 103.5 Ω `[U2]`. Espressif asks ±10% on the
   board `[E3]`. Use 0.22 / 0.15 mm at either fab. (verified limits)
2. Route on B.Cu only, over unbroken ground. If a via cannot be avoided, "add a pair of ground
   return vias" `[E3]`.
3. Series resistors at the MCU pins. ESD part at the connector, with the tracks running through
   its pads.
4. Keep the two lengths within 3 mm. This is the sibling board's number, not a datasheet's `[L3]`.
   At 12 Mbit/s, 3 mm is about 20 ps against an 83 ns bit. (likely)
5. Do not pay for controlled impedance. "USB FS can be quite forgiving" `[R1]`. Report 12 agrees.

### 11. Antenna keep-out (ESP32-S3 only)

1. Put the module at a board edge with the antenna outside the outline. Or put the feed point at
   the edge and cut the board away beside and under the antenna. (verified, `[E3]`)
2. No copper on any layer under the antenna. (likely: `[E3]` shows it in figures I did not open)
3. "A clearance of at least 15 mm is recommended in all directions" to the housing. (verified)
4. Keep "the USB port, USB-to-serial chip, UART signal lines" as far from the antenna as possible.
   (verified, `[E3]`)
5. A machined aluminium case blocks the antenna. Then use the WROOM-1U with an external antenna,
   or leave the radio off and take the USB network path of report 03.

Design A has no radio and no keep-out.

## Part classes and candidates

LCSC cells follow the repo rule: `UNVERIFIED` except the three locked numbers. "Conf." is for the
electrical facts used above, not for stock or price. Design A is RP2350B, B is ESP32-S3.

| Class | Candidate | Package | LCSC | Design | Conf. |
| --- | --- | --- | --- | --- | --- |
| MCU | RP2350B | QFN-80 | UNVERIFIED | A | verified `[R3]` |
| MCU module | ESP32-S3-WROOM-1-N16R8; 1U for a metal case | 18 x 25.5 mm module | UNVERIFIED | B | verified `[E1]` |
| Flash | W25Q128JVSIQ | SOIC-8 208 mil | C97521 | A | verified `[P12]` |
| Crystal | Abracon ABM8-272-T3, 12 MHz | 3.2 x 2.5 mm, 4 pads | UNVERIFIED | A | verified `[R2]` |
| Core inductor | Abracon AOTA-B201610S3R3-101-T | 2.0 x 1.6 mm | UNVERIFIED | A | verified `[P11]` |
| USB-C receptacle | HRO TYPE-C-31-M-12 (sibling boards) or GCT USB4105 | 16 pads | UNVERIFIED | both | GCT verified `[P10]`; HRO likely `[L3]` |
| CC resistors | 5.1 kΩ 1%, 2 off | 0402 | UNVERIFIED | both | verified `[U1]` |
| USB ESD | ST USBLC6-2SC6 (sibling boards) or TI TPD2E2U06 | SOT-23-6 or 5-pin SOT | UNVERIFIED | both | TI verified `[P3]`; ST likely `[L3]` |
| Fuse | PPTC, 0.5 A hold (A) or 0.75 A hold (B) | 1206 | UNVERIFIED | both | unverified |
| USB series resistors | 27 Ω (A); 22 Ω footprint (B); 2 off | 0402 | UNVERIFIED | both | verified `[R2]` `[E2]` |
| 3.3 V regulator | Diodes AP2112K-3.3TRG1 | SOT-25 | UNVERIFIED | A | verified `[P1]` |
| 3.3 V regulator | TI TLV62569DBV and a 2.2 µH inductor | SOT-23-5 | UNVERIFIED | B | verified `[P2]` |
| Backlight sink | Diodes BCR421UW6, 2 off | SOT-26 | UNVERIFIED | both | likely `[P4]` |
| Backlight fallback | AO3400A and a resistor, 2 off | SOT-23 | UNVERIFIED | both | verified `[P5]` |
| Matrix diode | BAT54 class (onsemi BAT54T1G), 16 off | SOD-123 | UNVERIFIED | both | verified `[P7]`; report 08 |
| Sense pull-ups | 4.7 kΩ, 4 off | 0402 | UNVERIFIED | both | report 08 |
| Encoder network | 3.3 kΩ, 10 kΩ, 10 nF; 6 off each | 0402 | UNVERIFIED | both | verified `[P9]`; report 08 |
| MX socket | Kailh CPG151101S11, 9 off | SMT, bottom | UNVERIFIED | both | report 08 |
| Tact button | Omron B3F-1050, 4 off | through-hole | UNVERIFIED | both | verified `[P8]` |
| Encoder | Alps EC11E18244AU, 3 off | through-hole | UNVERIFIED | both | verified `[P9]` |
| BOOT, RESET | TS-1187A class SMT tact, 2 off | SMT | UNVERIFIED | both | unverified |
| Big panel connector | Hirose FH12-40S-0.5SH(55) class | 0.5 mm ZIF, 40 pins | UNVERIFIED | both | likely, report 06 |
| Bar connector | Hirose FH12-10S-0.5SH(55) class | 0.5 mm ZIF, 10 pins | UNVERIFIED | both | unverified |
| Debug connector | JST SM03B-SRSS-TB | 1.0 mm, 3 pins | UNVERIFIED | both | verified `[R4]` |
| Capacitors | 15 pF, 10 nF, 100 nF, 1 µF, 4.7 µF, 10 µF, 22 µF | 0402 to 0805 | UNVERIFIED | both | verified `[R2]` `[E1]` |

The sibling repos hold LCSC numbers for several of these parts `[L3]`. Under this repo's rule they
stay `UNVERIFIED` here.

## What `pcb/gen/circuit.py` got wrong

I loaded the module and ran `circuit.build(board_toml)` without writing a file `[L1]`. It makes 47
parts and 45 nets.

| # | Fault | Evidence | Effect |
| --- | --- | --- | --- |
| 1 | U3 AP2112K has only IN, OUT and GND tied. EN is open | `[P1]`: "EN Pull Down Resistor", 3.0 MΩ | 3.3 V never comes up |
| 2 | Y1 has one tied pad. R5 pin 2 sits alone on a net named `Y1`. C23 is on the XOUT pin, not at the crystal | run output; `[R1]` figure 8 | no clock, so no USB |
| 3 | J1 USB-C has no GND pad and no shell. D+ and D- are one name each; the part has A6, B6, A7, B7 | run output; `[P10]` | no return path |
| 4 | U4 USBLC6-2 has its VBUS pin open. Its pins are named `D+` and `D-`, not numbered | run output; the sibling ties pins 1+6, 3+4, 2 and 5 `[L3]` | no clamp to VBUS; no run-through routing |
| 5 | SWCLK and SWDIO reach no pad and no connector | run output: two single-pin nets | no debug access |
| 6 | U2 flash has no decoupling capacitor and no pull-up footprint on QSPI_SS | run output; `[R1]` section 2.2 | against the vendor guide |
| 7 | Q1 has `UNVERIFIED` as its part number. R21 is sized for the old panel | file lines 220 to 225 | cannot be ordered |
| 8 | 26 of 45 machine-placed parts sit at (0, 0). The "planned routes" are literals | run output; file lines 25 to 36 | no placement, no routing |
| 9 | Encoder A and B rely on internal pull-ups of 32 to 86 kΩ | `[R3]`; `[P9]`: 1 mA minimum | contacts run under their rated current |
| 10 | It is the wrong device: 9 direct keys, 1 encoder, 1 display, no diodes, no tact row, RP2040 | the owner's words; report 04 rules out RP2040 | full rewrite |

What it got right: 27 Ω on the data pins, 5.1 kΩ on each CC pad, the 1 kΩ BOOT resistor and the
flash pin order (checked against `[P12]`). Its RP2040 pad tables match the pinout as I know it;
I did not re-read that datasheet today. (likely)

Re-checked in a second pass the same day against the source: lines 331 to 333 tie only Y1 pad 1
and put R5 pin 2 on a net named `Y1`; lines 346 to 350 give U3 only IN, OUT and GND; line 186
gives J1 one `D+` and one `D-` pad and no ground. Faults 1 to 3 stand. (verified, `[L1]`)

Report 02 already marks this file "replace". The netlist in
`/home/worxbend/Projects/macropad-greycode/pcb/gen/circuit.py` has none of faults 1 to 5, and it
has the flash capacitor `[L3]`. It is the better base.

## Conflicts and flags

Flagged, not decided.

1. **Locked LCSC list.** `C2040` (RP2040) and `C596730` (20-pin FH12) have no use in this design.
   `C97521` (flash) is used in design A only.
2. **Layer order.** Report 12 writes "signal, ground, power, signal". With all SMT on the bottom,
   ground must be the third layer, not the second. This report puts power on In1 and ground on In2.
3. **Panel supply.** The bar gives 3.3 V as the maximum recommended logic voltage and 4.6 V as the
   absolute maximum `[D2]`. A regulator at +2% is 3.37 V. Likely fine. Not checked for the Focus
   panel.
4. **USB suspend.** A suspended device may draw 500 µA, or 2.5 mA if it is high-power and a
   wake-up source `[U2]`. This design does not meet that. I did not design for it.
5. **`board.toml`.** It needs a matrix table, three encoder tables, two display tables and a power
   table. Not written in this run.

## Not checked

- No schematic and no netlist. Nothing here has passed ERC or DRC.
- These datasheets: ST USBLC6-2 (the server timed out), Hirose FH12 (HTTP 403), HRO
  TYPE-C-31-M-12, any PPTC fuse, the RM2. Their rows are tagged.
- The Focus panel datasheet. Its numbers come from report 06.
- The JLCPCB impedance calculator. The pair widths come from my solver, not from the fab.
- The BCR421U set resistor, and the backlight level at 4.4 V VBUS.
- Panel logic current. Flash and PSRAM current.
- EMC. Nothing was tested or simulated beyond the USB pair.

Risk: design B is 10 mA over the USB limit on paper before any cap, and two rows of its budget are
allowances. Measure it on a dev board before a PCB order. Design A has about 190 mA of margin.

## Sources

Raspberry Pi, read today:

- `[R1]` Hardware design with RP2040. <https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf>
- `[R2]` Hardware design with RP2350. <https://datasheets.raspberrypi.com/rp2350/hardware-design-with-rp2350.pdf>
- `[R3]` RP2350 datasheet: pinout figure 3, pull resistance and input level tables, table 1693, erratum E9. <https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf>
- `[R4]` Raspberry Pi 3-pin Debug Connector Specification. <https://datasheets.raspberrypi.com/debug/debug-connector-specification.pdf>

Espressif, read today:

- `[E1]` ESP32-S3-WROOM-1 and WROOM-1U datasheet v1.8: tables 6-2, 6-3, 6-4, 6-6, figure 9-1. <https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf>
- `[E2]` ESP Hardware Design Guidelines, schematic checklist. <https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html>
- `[E3]` ESP Hardware Design Guidelines, PCB layout design. <https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html>

USB-IF, read today:

- `[U1]` USB Type-C Cable and Connector Specification, Release 2.5, March 2026: tables 4-28 and 4-36, the receptacle notes in chapter 3. <https://www.usb.org/sites/default/files/USB%20Type-C%202.5%20Release%20202603.zip>
- `[U2]` USB 2.0 Specification and its Device Capacitance ECN: sections 7.2.1, 7.2.3 and 7.2.4.1, table 7-7, the cable impedance row. <https://www.usb.org/sites/default/files/usb_20_20250603.zip>

Part datasheets, read today:

- `[P1]` Diodes AP2112. <https://www.diodes.com/assets/Datasheets/AP2112.pdf>
- `[P2]` TI TLV62569. <https://www.ti.com/lit/ds/symlink/tlv62569.pdf>
- `[P3]` TI TPD2E2U06. <https://www.ti.com/lit/ds/symlink/tpd2e2u06.pdf>
- `[P4]` Diodes BCR420UW6 / BCR421UW6, Rev. 4, a copy on a reseller's site. <https://pdf.direnc.net/upload/bcr420uw6-bcr421uw6-led-driver-led-surucu-datasheet.pdf>
- `[P5]` Alpha and Omega AO3400A. <https://www.aosmd.com/pdfs/datasheet/AO3400A.pdf>
- `[P6]` Diodes 1N4148W. <https://www.diodes.com/assets/Datasheets/ds30086.pdf>
- `[P7]` Diodes BAT54 /A /C /S. <https://www.diodes.com/assets/Datasheets/ds11005.pdf>
- `[P8]` Omron B3F. <https://omronfs.omron.com/en_US/ecb/products/pdf/en-b3f.pdf>
- `[P9]` Alps Alpine EC11E18244AU product page. <https://tech.alpsalpine.com/e/products/detail/EC11E18244AU/>
- `[P10]` GCT USB4105 drawing. <https://gct.co/files/drawings/usb4105.pdf>
- `[P11]` Abracon AOTA-B201610S3R3-101-T. <https://abracon.com/datasheets/AOTA-B201610S3R3-101-T.pdf>
- `[P12]` Winbond W25Q128JV, Rev. I. <https://www.winbond.com/resource-files/W25Q128JV%20RevI%2008232021%20Plus.pdf>

Panels, read today:

- `[D1]` QDtech QD3525, 3.5 inch, ST7796U: electrical tables, pin table, outline drawing. <https://www.lcdwiki.com/res/MSP3525_MSP3526/QD3525-Specifications-A.pdf>
- `[D2]` Wisevision N279-1428KIWIG01-C10: pin table and DC tables. <https://www.jx-wisevision.com/uploads/N279-1428KIWIG01-C101.pdf>

Fabs, read today:

- `[F1]` JLCPCB impedance and stackup page. <https://jlcpcb.com/impedance>
- `[F2]` PCBWay multilayer laminated structure page: 4 layers, 1.6 mm, entry 1. <https://www.pcbway.com/multi-layer-laminated-structure.html>

Not read (failed or refused; both retried in the second pass: ST timed out again, Hirose's
catalog document URL returned HTTP 403):

- ST USBLC6-2 datasheet. <https://www.st.com/resource/en/datasheet/usblc6-2.pdf>
- Hirose FH12 series page. <https://www.hirose.com/en/product/series/FH12>

Local files:

- `[L1]` `pcb/gen/circuit.py`, loaded and run read-only with `python3 -B`
- `[L2]` `board.toml`, `CLAUDE.md`, `docs/images/sketch.jpg`
- `[L3]` `/home/worxbend/Projects/macropad-greycode/pcb/gen/circuit.py`, `pcb/gen/layout.py`, `pcb/README.md`
- `[L4]` `/home/worxbend/Projects/macropad/pcb/gen/circuit.py`, lines 397 to 400
- `[L5]` `docs/research/`: `02-repo-inventory.md`, `03-connectivity.md`, `04-mcu-and-firmware-stack.md`, `06-big-display.md`, `07-long-display.md`, `08-input-parts.md`, `12-fabrication.md`

Experiment:

- `[X1]` A 2D finite-difference solver for an edge-coupled microstrip pair with solder mask. Written
  in a scratch directory and run with the Python of `cad/.venv` (numpy and scipy). Inputs: the
  stackup numbers of `[F1]` and `[F2]`, mask Dk 3.8, 0.035 mm copper. Not kept.

## Open questions

Blocking the schematic:

1. Must Wi-Fi ever work? (Report 04, question 1.) It picks design A or B, and so the regulator,
   the fuse and the antenna keep-out.
2. Which face of each display tail carries the contacts? It picks the connector type. (Reports 06
   and 07 ask the same.)
3. Do the tails reach the bottom face round the board edge or through a slot?
4. Is the bar the 10-pin Wisevision part or the 12-pin EastRising part?
5. May the locked LCSC list change? Two of its three numbers have no use here.

Not blocking:

1. Should design A carry the RM2 radio footprint? If yes, its current must be read first.
2. Should the firmware read CC to find a 1.5 A or 3 A source? It costs two ADC pins.
3. Should the case be bonded to ground at one mounting hole, as on `macropad`?
4. One SPI bus for both panels, or one each? (Report 04, question 7.)
5. JLCPCB or PCBWay first? The best pair width differs by 0.02 mm between them.

Next action: blocking question 1.
