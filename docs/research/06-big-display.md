# 06. The big display

Research only, 2026-11-18. Second pass: the first draft was re-read against its sources and cut.
Tags: **verified** (read today in the primary source), **likely**, **unverified**. **MEASURE** marks
a size or a face not read in a datasheet drawing. Keys such as `[D1]` point into Sources. No panel
was on the desk.

Next action: the owner buys one E35GH-I-RW300-N and looks at which face of its tail has the contacts.

## Recommendation

**Pick: Focus LCDs E35GH-I-RW300-N.** 3.5 inch, 320 x 480, IPS, ST7796U, 40-pin 0.5 mm plug-in
tail. Strap IM2, IM1 and IM0 high for 4-wire SPI `[D1]`.

**Alternate, same footprint: Winstar WF35UTYAIDNN0#.** The same 40-pin tail, pin for pin, with an
ILI9488 `[D2]`. It is a weak alternate; see flag 5. Not a drop-in on the straps: its only
documented SPI mode is 3-line, 9-bit (IM = 101), so IM1 must be changeable and firmware needs a
second SPI path (skeptic pass, `[D2]` page 28).

**Fallback, new footprint: Displaytech DT035CTFT-IPS-SHB.** Same driver family, 183 in stock `[D6]`.

Five findings carry the pick.

1. **It is the owner's size.** Outline 54.46 x 82.94 mm, active area 48.96 x 73.44 mm, 3.47 inch.
   The 3x3 block spans 57.15 mm at 19.05 mm pitch: the module is 1.35 mm narrower on each side.
   (verified, `[D1]` `[L3]`)
2. **It sits flush with the bar display.** 2.15 mm thick against 2.1 mm. Pixel pitch 0.153 mm
   against 0.1498 mm. (verified `[D1]`; the bar numbers are likely, `[L1]`)
3. **Two makers draw this tail.** One pin order, one 20.50 mm tail, one 51.96 x 80.22 mm glass.
   (verified, `[D1]` `[D2]`)
4. **ST7796U takes 16-bit pixels on SPI.** The ILI9488 in the alternate is driven with 18-bit
   pixels. A full frame is 66 ms against 98 ms at 37.5 MHz. (verified, `[C1]` `[D2]` `[C3]`)
5. **It can be bought today.** USD 40.35 from Focus, 19 in stock, "Recommended for New Designs".
   (likely, `[W1]`)

The price of this choice: about USD 40, one seller, 350 cd/m2, no tearing-effect pin.

## Candidates

All five are 320 x 480 with a 48.96 x 73.44 mm active area and 0.153 mm pixel pitch. All are IPS,
viewing direction "ALL" (Winstar: "Wide View", 80 degrees each way). Every tail leaves one short
edge. Mounted as in the sketch, that edge faces the keys.

| Part | Controller | SPI selection | Outline mm, W x H x T | cd/m2 |
|---|---|---|---|---|
| Focus E35GH-I-RW300-N `[D1]` | ST7796U | IM2..0 = 111 (4-line), 101 (3-line). Also 8080 8/9/16/18-bit | 54.46 x 82.94 x 2.15 | 350 |
| Winstar WF35UTYAIDNN0# `[D2]` | ILI9488 | Datasheet lists 101 (3-line) only. The chip has 111 `[C2]` | 54.50 x 83.00 x 2.46 | 600 |
| Focus E35RM-I-XS800-N `[D3]` | ST7796SI | 111 (4-wire), 101 (3-wire). Also 8080 and RGB | 55.50 x 84.96 x 2.50 | 800 |
| Displaytech DT035CTFT-IPS-SHB `[D6]` | ST7796UI-G5 | Fixed 4-line SPI, no IM pins. Also 16-bit RGB | 54.40 x 86.24 x 3.50 | 1000 |
| QDtech QD3525 `[D5]` | ST7796U | IM pins on the tail. Also 8080 and RGB | 55.50 x 84.96 x 2.50 | 300 |

| Part | FPC | Backlight | Sold at |
|---|---|---|---|
| E35GH-I-RW300-N | 40 pin, 0.5 mm, plug-in, tail 20.50 wide | 6 LEDs parallel, one A and one K, 120 mA, 2.8 to 3.4 V | Focus direct USD 40.35, 19 in stock. DigiKey USD 44.63, the same 19, shipped by Focus (likely `[W1]` `[W2]`) |
| WF35UTYAIDNN0# | Same tail, 20.50 wide | One group, one A and one K, 160 mA, 2.7 to 3.4 V | CPC Farnell SC15722, GBP 34.60 before VAT, 2 in stock (unverified `[W6]`) |
| E35RM-I-XS800-N | 50 pin, 0.5 mm, plug-in, tail 25.50 wide | 8 LEDs, common A, 8 K pins, 160 mA, 3.2 V | Focus direct USD 27.72, 5 in stock (likely `[W3]`) |
| DT035CTFT-IPS-SHB | 39 pin, 0.3 mm, plug-in, tail 12.00 wide, FH26-39S-0.3SHW | 6 LEDs, 60 mA, 11.4 to 13.4 V. The drawing says "2*3", which does not fit 12 V: string count **MEASURE** | DigiKey USD 33.73, 183 in stock (likely `[W4]`). Mouser lists the family (unverified `[W7]`) |
| QD3525 | 48 pin, 0.8 mm, solder-on, tail 43.21 wide | 6 LEDs, common A, 6 K pins, 90 mA | Only on the LCDWiki MSP3525 board. No bare price found |

Rows 1, 2 and 4 were re-read today in the drawings (verified). Rows 3 and 5: outline, controller
and pin list re-read; the QD3525 backlight current is carried from the first pass (likely).

| Part | Pin order |
|---|---|
| E35GH-I-RW300-N and WF35UTYAIDNN0# | 1 LEDK, 2 LEDA, 3 to 5 IM0 to IM2, 6 RESET, 7 to 10 NC (Winstar: sync and clock inputs), 11 to 28 DB17 to DB0, 29 SDA, 30 RD, 31 WR(SCL), 32 D/C, 33 CS, 34 IOVCC, 35 VCI, 36 GND, 37 to 40 NC |
| E35RM-I-XS800-N | 1 GND, 2 to 5 touch, 6 IOVCC, 7 VCC, 8 to 10 IM0 to IM2, 11 RESET, 12 to 15 VSYNC, HSYNC, PCLK, DE, 16 to 33 DB17 to DB0, 34 SDO, 35 SDA, 36 RD, 37 WR(SCL), 38 RS, 39 CS, 40 GND, 41 to 48 LEDK8 to LEDK1, 49 LEDA, 50 GND |
| DT035CTFT-IPS-SHB | 1 RESET, 2 CSX, 3 DCX, 4 SCK, 5 MOSI, 6 MISO, 7 to 10 VSYNC, HSYNC, DE, DOTCLK, 11 to 26 DB15 to DB0, 27 and 28 VDD, 29 GND, 30 to 37 NC, 38 LED-A, 39 LED-K |
| QD3525 | 1 to 4 touch, 5 VDD, 6 IOVCC, 7 TE, 8 CSX, 9 DCX, 10 WRX/SCL, 11 RD, 12 SDA, 13 SDO, 14 GND, 15 to 32 DB0 to DB17, 33 GND, 34 to 37 DEN, PCLK, HSYNC, VSYNC, 38 RESET, 39 to 41 IM, 42 LEDA, 43 to 48 LEDK |

(verified, pin lists in `[D1]` `[D2]` `[D3]` `[D5]` `[D6]`)

Not found: a Mouser listing for Focus or Winstar, any LCSC listing, an AliExpress listing with a pin
table. Read and left out: DisplayModule DM-TFT35-431, its own 50-pin order `[D4]`.

### Why the others lose

1. **3.2 inch, QDtech QD-TFT3202.** 240 x 320, 125 pixels per inch against 166, 12 o'clock view.
   At 55.04 mm it is no narrower than the pick. (verified, `[D7]`)
2. **E35RM-I-XS800-N.** Brighter and USD 12.63 cheaper. A 50-pin order no second maker shares,
   eight cathode pins, 0.4 mm thicker than the bar.
3. **DT035CTFT-IPS-SHB.** Best stocked and brightest. Its glass stands 1.4 mm above the bar's. It
   needs a 0.3 mm connector and a 12 V boost.
4. **QD3525.** The only one with a TE pin. Its tail is soldered: 48 joints at 0.8 mm. It is the
   bench part, on the MSP3525 board, for firmware work before the PCB exists.

## Refresh time over SPI

One frame is 153,600 pixels. ST7796U takes RGB565 on 4-line SPI: 307,200 bytes `[C1]`. Winstar
documents only 3-bit and 18-bit pixels on SPI, and TFT_eSPI sets 18-bit for ILI9488 on SPI: 460,800
bytes `[D2]` `[C3]`. (verified)

The ILI9488 column assumes 4-line SPI (IM = 111, 8-bit bytes). Winstar documents only 3-line SPI
(IM = 101), which sends 9 bits per byte with D/C inline and has a 66 ns (15 MHz) write cycle on
paper: 276 ms a frame at 15 MHz, 111 ms at 37.5 MHz `[D2]` `[C2]` page 330. (verified, skeptic pass)

| SPI clock | ST7796U, 16-bit | ILI9488, 18-bit, 4-line | Where the clock comes from |
|---|---|---|---|
| 15 MHz | 164 ms | 246 ms | ST7796U limit on paper: 66 ns write cycle at 1.8 V I/O `[C1]` |
| 25 MHz | 98 ms | 147 ms | RP2350 step. ILI9488 4-line limit on paper is 20 MHz (50 ns); 3-line is 15 MHz `[C2]` pages 330 to 331 |
| 37.5 MHz | 66 ms | 98 ms | RP2350 step: what a request for 40 MHz gives `[S1]` |
| 75 MHz | 33 ms | 49 ms | RP2350 top step. Report 04 rates the chip at 70.5 Mb/s `[L2]` |
| 80 MHz | 31 ms | 46 ms | ESP32-S3 ceiling `[L2]` |

1. **RP2350 hardware SPI moves in steps.** The rate is 150 MHz / (even prescale x post-divide):
   75, 37.5, 25, 18.75, 15 MHz. (verified, Pico SDK 2.3.0 source `[S1]`)
2. **Plan on 37.5 MHz: 15 full frames a second.** Anything above 15 MHz is outside the datasheet
   table. It needs a bench test at 3.3 V. (verified for the table, `[C1]` page 54)
3. **The pad does not need full frames.** A 96 x 96 key tile is 18,432 bytes: 3.9 ms at 37.5 MHz.
   A 320 x 24 status strip is 3.3 ms. (arithmetic)
4. **No TE pin on the pick.** Full-screen wipes can tear. Redraw tiles, not the screen. (verified,
   `[D1]`)

## Numbers for the PCB and the case

For E35GH-I-RW300-N, re-read today in `[D1]` unless a line says otherwise.

1. **Window.** The active area sits 2.75 mm from each long edge, 2.35 mm from the far short edge
   and 7.15 mm from the tail edge. Open the lens to 49.76 x 74.24 mm. That is Winstar's viewing
   area for this glass `[D2]`; Focus draws none (likely for Focus).
2. **Pocket.** 55.0 x 83.5 mm takes both makers at their largest: 54.61 x 83.09 (Focus, +/- 0.15
   drawn) and 54.80 x 83.30 (Winstar, a +/- 0.3 tolerance assumed, not read: likely).
   Depth is 2.15 mm for Focus and 2.46 mm for Winstar, tape excluded.
3. **Tail.** 20.50 mm wide, 24.50 +/- 0.5 mm long when flat. Centred by eye on the drawing; no
   dimension gives the offset: **MEASURE**. Winstar draws its tail 23.94 +/- 0.5 mm long, 0.56 mm
   shorter `[D2]` page 31. Folded under the panel, the Focus end lands 22.50 mm in from the tail
   edge. 40 pads of 0.35 x 3.50 mm at 0.50 mm. The stiffened end is 0.30 mm thick.
4. **Straps.** IM0 to IM2 and RD to IOVCC. DB17 to DB0 and pins 7 to 10 to ground `[C1]` page 93.
   The MCU gives SCL, SDA, CS, D/C, RESET and one backlight pin. There is no SDO pin on the tail,
   though the drawing's IM table names "SDA, SDO": read-back shares SDA, which the ST7796U read
   timing drives as an output `[C1]` page 95. Fitting the Winstar alternate in its documented mode
   needs IM1 low (101), so put IM1 on a 0 ohm link or a GPIO, not a hard strap.
5. **Backlight.** 120 mA at 2.8 to 3.4 V; Winstar wants 160 mA. A 3.3 V rail has no headroom. From
   5 V, 15.8 ohm drops 1.9 V and burns 0.23 W. The datasheet suggests constant-current drive. With
   the bar this is 220 mA (likely, `[L1]`).

## Conflicts and flags

1. **Which face holds the contacts.** The front and rear views draw the pads on the rear face, and
   Winstar agrees. The Focus side view labels the other face "contact side". The datasheet names
   FH12S-40S-0.5SH(55), bottom contact; the product page names FH12A-40S-0.5SH(55), top contact
   `[D1]` `[W1]` `[W5]`. Read as rear-face contacts (likely). **MEASURE** on a sample.
2. **Pin 29.** Both drawings print it "NC (SDA)". Both pin tables call it the serial data pin
   `[D1]` `[D2]`. Read as SDA (likely). Prove it with a read-ID command on the bench.
3. **Repo rules.** `CLAUDE.md` locks `FH12-20S-0.5SH(55)` `C596730`, 20 pins. This panel needs the
   40-pin part; its LCSC cell stays `UNVERIFIED`. `board.toml` `[display]` still describes the
   2.8 inch Raystar panel. Neither file was changed `[L3]`.
4. **Width and shape.** The brief asks for 55 to 58 mm; the pick is 54.46 mm, and no 3.5 inch
   part read is wider than 55.50 mm. The sketch draws the big window about 0.85 wide to high
   `[L1]`; this panel is 0.667. The pick follows the owner's answer, not the pencil ratio.
5. **The alternate is weak.** Winstar promises 3-line SPI only, the ILI9488 costs 1.5 times the
   bytes, and a shop snippet reports the part "no longer manufactured" (unverified, `[W6]`). Its
   value is proof that the 40-pin order is not one maker's invention.

## Not checked

- No panel in hand. Risk: the contact face, pin 29, and any clock above 15 MHz.
- BuyDisplay answered HTTP 403 and I did not work around it. A snippet gives its ER-TFT035IPS-6 as
  ILI9488, 50 pins, about USD 9 (unverified, `[B1]`). Risk: a cheap part from the bar's shop was
  not compared.
- Farnell timed out and the Hirose drawings were not read. Risk: Winstar status and the connector
  facts rest on snippets. Shop prices came through a summarising fetch tool and change daily.

## Sources

Panel datasheets in the table, read today:

- `[D1]` Focus LCDs E35GH-I-RW300-N, rev 1.0, 2020-12-01. https://focuslcds.com/wp-content/uploads/Specs/E35GH-I-RW300-N_Spec.pdf
- `[D2]` Winstar WF35UTYAIDNN0#, 33 pages, drawing on page 31. https://www.farnell.com/datasheets/3161419.pdf
- `[D3]` Focus LCDs E35RM-I-XS800-N, rev 1.0, 2020-09-17. https://focuslcds.com/wp-content/uploads/Specs/E35RM-I-XS800-N_Spec.pdf
- `[D5]` QDtech QD3525, rev A, 2023-01-05. https://www.lcdwiki.com/res/MSP3525_MSP3526/QD3525-Specifications-A.pdf
- `[D6]` Displaytech DT035CTFT-IPS-SHB, V1.1, 2025-07-11. https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/7157/DT%20Spec%20-%20DT035CTFT-IPS-SHB%20V1.1.pdf

Also read today:

- `[D4]` DisplayModule DM-TFT35-431. https://cdn.shopify.com/s/files/1/0264/7629/files/DM-TFT35-431_Datasheet.pdf
- `[D7]` QDtech QD-TFT3202, v1.1, 2018-03-28. https://www.lcdwiki.com/res/MSP3218/QD-TFT3202%20specification_v1.1.pdf

Controller datasheets and source code, read today:

- `[C1]` Sitronix ST7796U, V1.0, 2020-02: IM table page 42, 4-SPI timing page 54, 4-line interface pages 93 to 96. https://focuslcds.com/wp-content/uploads/Drivers/ST7796U.pdf
- `[C2]` ILITEK ILI9488, V100: IM table 1, SPI timing pages 330 to 331. https://www.lcdwiki.com/res/MSP3520/ILI9488%20Data%20Sheet.pdf
- `[C3]` TFT_eSPI, `0x3A` set to `0x66` for ILI9488 on SPI and `0x55` for ST7796. https://raw.githubusercontent.com/Bodmer/TFT_eSPI/master/TFT_Drivers/ILI9488_Init.h and https://raw.githubusercontent.com/Bodmer/TFT_eSPI/master/TFT_Drivers/ST7796_Init.h
- `[S1]` Pico SDK 2.3.0, local copy under `~/.platformio/packages/framework-arduinopico/pico-sdk/src/`: `rp2_common/hardware_spi/spi.c` (`spi_set_baudrate`), `rp2_common/pico_runtime_init/runtime_init_clocks.c` (clk_peri = clk_sys), `rp2350/hardware_regs/include/hardware/platform_defs.h` (150 MHz)

Shop pages read today through a fetch tool:

- `[W1]` Focus LCDs, E35GH-I-RW300-N. https://focuslcds.com/product/E35GH-I-RW300-N/
- `[W2]` DigiKey, E35GH-I-RW300-N. https://www.digikey.com/en/products/result?keywords=E35GH-I-RW300-N
- `[W3]` Focus LCDs, E35RM-I-XS800-N. https://focuslcds.com/product/E35RM-I-XS800-N/
- `[W4]` DigiKey, DT035CTFT-IPS-SHB. https://www.digikey.com/en/products/detail/displaytech/DT035CTFT-IPS-SHB/26772451

Not read; search-engine snippets only:

- `[W5]` DigiKey, FH12S-40S-0.5SH(55) and FH12A-40S-0.5SH(55). https://www.digikey.jp/en/products/detail/hirose-electric-co-ltd/FH12S-40S-0-5SH-55/1110355
- `[W6]` CPC Farnell, WF35UTYAIDNN0#, order code SC15722. https://cpc.farnell.com/winstar/wf35utyaidnn0/tft-display-3-5in-320x480-ips/dp/SC15722
- `[W7]` Mouser, Displaytech DT035CTFT family. https://www.mouser.com/c/?marcom=179192537
- `[B1]` BuyDisplay ER-TFT035IPS-6. https://www.buydisplay.com/3-5-inch-ips-320x480-tft-lcd-display-capacitive-touch-screen

Local files:

- `[L1]` `docs/research/07-long-display.md`
- `[L2]` `docs/research/04-mcu-and-firmware-stack.md`, "Parts compared", the SPI master row
- `[L3]` `board.toml` lines 12 to 40 and `CLAUDE.md`

## Open questions

1. Which face of the E35GH-I-RW300-N tail carries the contacts? This picks FH12 or FH12A and
   blocks the connector footprint.
2. Does the owner accept about USD 40 for a documented panel? If not, the owner opens the
   ER-TFT035IPS-6 datasheet in a browser and reads its pin table `[B1]`.
3. Does this glass run clean at 37.5 MHz and at 75 MHz from an RP2350 at 3.3 V? The datasheet
   promises 15 MHz.
4. Is 350 cd/m2 enough on the owner's desk? If not, E35RM-I-XS800-N gives 800 and Displaytech
   1000. Both cost a different connector.
5. Is the Winstar part still made, and does it answer on 4-line SPI with IM = 111? If not, the
   design has no drop-in alternate.

This report answers question 3 of `07-long-display.md`: the big display is 3.5 inch.

Next action: question 1.

## Verification

Skeptic pass, 2026-11-18. Each source was downloaded and opened again (PDFs read with `pdftotext`
and the drawing pages rendered and viewed). Verdict: **corrected**. The pick holds; the alternate is
weaker than the first text said.

| # | Claim | Source opened | Result |
|---|---|---|---|
| 1 | E35GH outline 54.46 x 82.94 x 2.15 mm, glass 51.96 x 80.22, active 48.96 x 73.44, pitch 0.153 | `[D1]` page 2 table and page 3 drawing | Holds |
| 2 | 40 pins at 0.50 mm, pads 0.35 x 3.50, tail 20.50 wide, 24.50 +/- 0.5 long, 22.50 folded, 0.30 thick | `[D1]` page 3 drawing | Holds. "Centred" has no dimension: now **MEASURE** |
| 3 | Pin order 1 LEDK ... 29 SDA ... 36 GND, no TE, no SDO | `[D1]` page 5 table and page 3 pin list | Holds. Drawing prints 29 as "NC(SDA)", 33 as "CS(NCS)" |
| 4 | IM2..0 = 111 selects 4-line SPI on ST7796U | `[C1]` page 42 pin table, page 61 section 8.1, page 93 section 8.4.2 | Holds. Page 93 also says unused DB[17:0] go to GND |
| 5 | ST7796U accepts RGB565 on 4-line SPI | `[C1]` page 96, section 8.4.2.3 "4-SPI Color format", 3Ah = 05h | Holds |
| 6 | ST7796U 4-SPI write cycle 66 ns (15 MHz) | `[C1]` page 54 table | Holds |
| 7 | Winstar is pin for pin the same, ILI9488, 54.5 x 83.0 x 2.46, 160 mA, 600 cd/m2, SPI only as 3-line | `[D2]` pages 8, 9, 26 to 28, 31 | Holds. **Correction:** 3-line is 9-bit with D/C inline, so the same IM straps (111) are undocumented for this module; tail length is 23.94, not 24.50 |
| 8 | ILI9488 SPI limit 20 MHz | `[C2]` pages 330 to 331 | **Corrected:** 20 MHz (50 ns) is 4-line only; the 3-line mode Winstar documents is 66 ns, 15 MHz. Refresh note added |
| 9 | TFT_eSPI sets 0x3A = 0x66 for ILI9488 on SPI, 0x55 for ST7796 | `[C3]` both files, fetched from GitHub | Holds |
| 10 | DT035CTFT-IPS-SHB: ST7796UI-G5, 4-line SPI and 16-bit RGB, 39 pins at 0.3 mm, FH26-39S-0.3SHW, tail 12.00, 54.40 x 86.24 x 3.50, 60 mA at 11.4 to 13.4 V, 1000 cd/m2 | `[D6]` pages 3, 5 and 16 drawing | Holds. The drawing's "2*3 = 6 LEDs" conflicts with 12 V: **MEASURE** |
| 11 | RP2350 SPI steps 75, 37.5, 25, 18.75, 15 MHz; 40 MHz request gives 37.5 | `[S1]` `spi_set_baudrate` and `platform_defs.h` (150 MHz), run by hand: prescale 2, postdiv 2 | Holds |
| 12 | Frame and tile times (66 ms, 98 ms, 3.9 ms, 3.3 ms) and the 15.8 ohm, 0.23 W backlight figure | Arithmetic redone | Holds |

Fit to the owner's words and sketch:

- "Big display about 3.2 to 3.5 inch, about as wide as the 3x3 block": 3.5 inch, 54.46 mm against
  57.15 mm. Holds.
- Sketch: the big window sits above the keys, about 0.85 wide to high. The pick is portrait at
  0.667, so the body grows about 83 mm above the keys. Flag 4 already says so; the owner should
  confirm the taller body before the case is drawn.
- Not re-checked: shop stock and prices (`[W1]` returned a 1.4 kB block page to a plain fetch), the
  connector contact face (flag 1), and the Hirose drawings. They stay as tagged.
