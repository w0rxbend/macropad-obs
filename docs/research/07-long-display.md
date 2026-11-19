# 07. The long, narrow display

Research only, 2026-11-18. This file is the only file written. An earlier run drafted it. This run
re-read the load-bearing sources, fixed what was wrong and cut the rest. Tags: **verified** (read
today in a primary source), **likely**, **unverified**. **MEASURE** marks a size not read in a
datasheet drawing. Keys such as `[D1]` point into Sources. No panel was on the desk.

## Recommendation

Use the 2.79 inch 142 x 428 IPS bar panel with the NV3007 controller on 4-wire SPI. Design to
Wisevision **N279-1428KIWIG01-C10**: I read its datasheet and drawing `[D1]`. Buy at retail from
BuyDisplay: EastRising ER-TFT2.79-1 or ER-TFT2.79-2, whichever shows the same 10-pin table.
Snippets give ER-TFT2.79-2 the same outline and active area (unverified `[B1]`).

Alternate: QDtech **TFT1901**, 1.9 inch 170 x 320, ST7789 `[D2]`. The owner's `macropad-nyxilab`
already runs this glass on an MSP1901 board `[L2]` `[W8]`.

Next action: the owner opens both BuyDisplay datasheets in a browser and reads each FPC pin table
`[B1]`. BuyDisplay answers this tool with a Cloudflare challenge (HTTP 403). I did not work around
it.

Five findings carry the pick.

1. **It is the only SPI candidate shaped like the sketch.** The sketch strip scales to about
   20 x 67 mm. This active area is 21.28 x 64.14 mm. The 1.9 inch panel is 42.72 mm tall.
   (verified, `[L1]` `[D1]` `[D2]`)
2. **It fits beside the chosen big panel.** 64.14 mm against 73.44 mm of active height: 0.87.
   (verified, `[D1]` `[L3]`)
3. **Text is the same physical size on both screens.** Pixel pitch 0.1498 mm against 0.153 mm. The
   1.9 inch panel is 0.1335 mm. (verified, `[D1]` `[D2]` `[L3]`)
4. **The two glass faces sit level.** 2.1 mm against 2.15 mm. The 1.9 inch panel is 1.43 mm: a
   0.72 mm step. (verified, `[D1]` `[D2]` `[L3]`)
5. **It costs one init table, not a second driver.** See "Driver". (verified, `[C1]` `[C2]` `[C4]`)

The price: NV3007 is outside the ST7789 and ST7796 family the brief prefers, I found one retail
shop, and I read no NV3007 datasheet.

## What the sketch shows

I rotated `docs/images/sketch.jpg` upright and read the pencil lines by eye, twice `[L1]`. Error is
about 10%.

- The narrow window is 0.93 to 0.99 times as tall as the big window. It is not two thirds.
- Its top edge sits about 7% lower than the big window's top edge. The bottom edges are level.
- Scaled by the 3x3 block (57.15 mm), the narrow window is 19 to 22 mm wide and about 67 mm tall.
- Each knob is drawn about as wide as the narrow window: 17 to 19 mm.

## Candidates

"Ratio" is active height over 73.44 mm, the big panel `[L3]`. "Strip" is one of three stacked cells.

| Candidate | Part | Pixels | Active mm | Outline mm, W x H x T | Ratio | Strip px | Tag |
|---|---|---|---|---|---|---|---|
| 2.79" bar | Wisevision N279-1428KIWIG01-C10 `[D1]` | 142 x 428 | 21.28 x 64.14 | 24.38 x 69.43 x 2.1 | 0.87 | 142 x 142 | verified |
| 1.9" | QDtech TFT1901 `[D2]` | 170 x 320 | 22.695 x 42.72 | 25.8 x 49.72 x 1.43 | 0.58 | 170 x 106 | verified |
| 2.25" bar | EastRising ER-TFT2.25-1 `[B3]` `[L2]` | 76 x 284 | 14.80 x 55.29 | 17.90 x 62.50 x 2.36 | 0.75 | 76 x 94 | likely, MEASURE (sizes are the owner's `params.py`, not a datasheet) |
| 1.47" | Limito LBS147TC-IG01 `[D4]` | 172 x 320 | 17.39 x 32.35 | 19.39 x 36.28 x 1.46 | 0.44 | 172 x 106 | verified |
| 1.14" | QDtech TFT1141 `[D5]` | 135 x 240 | 14.86 x 24.91 | 17.6 x 31.0 x 1.6 | 0.34 | 135 x 80 | verified |
| 3.49" bar | none; Waveshare board `[W5]` | 172 x 640 | about 22.6 x 84.0 | not found | 1.14 | 172 x 213 | unverified, MEASURE |
| 3.12" OLED | Newhaven NHD-3.12-25664UCB2 `[D7]` | 64 x 256 | 19.18 x 76.78 | 44.00 x 89.20 x 6.0 max (PCB) | 1.05 | 64 x 85 | verified (drawing dated 2024-08-25) |

| Candidate | Controller | Interface | FPC | Backlight | Source and price |
|---|---|---|---|---|---|
| 2.79" bar | NV3007A, RAM 168 x 428 (likely: Arduino_GFX `NV3007_TFTWIDTH`, no datasheet read) | 4-wire SPI | 10 pin, 0.50 pitch, 5.50 wide, 60.00 long, leaves a short edge | 5 LEDs parallel, 3.2 V, 100 mA | Wisevision: MOQ 1, by quote `[W1]`. BuyDisplay: US$3.49 to 3.89 (unverified `[B1]`) |
| 1.9" | ST7789, RAM 240 x 320 | 4-wire SPI or 8080 8-bit, set by IM1 and IM2 | 30 pin, 0.5 pitch, 15.5 wide, 36.6 long, leaves a short edge | 4 LEDs, one anode pin, four cathode pins, 3.0 V, 80 mA | Bare price not found. Sold on the LCDWiki MSP1901 board `[W8]` |
| 2.25" bar | ST7789P3 on one listing, NV3023B on another (unverified) | 4-wire SPI | 8 pin, 0.5 pitch (unverified) | not found | BuyDisplay, price not read |
| 1.47" | ST7789V3 | 4-wire SPI | 12 pin, pitch not read | 3 LEDs parallel, 3.0 V, 60 mA | not checked |
| 1.14" | ST7789V | 4-wire SPI | 13 pin, solder type | 1 LED, 3.0 V, 20 mA | not checked |
| 3.49" bar | AXS15231B | QSPI | not found | not found | Sold only as an ESP32-S3 board |
| 3.12" OLED | SSD1322 | 4-wire SPI or 8-bit parallel | 20 pin header | none | not checked |

Why the others lose.

1. **1.9 inch.** Best documented, in the preferred family, already used by the owner. It is a short
   rectangle (1 : 1.9), not a strip. It is the alternate.
2. **2.25 inch.** Right shape, ST7789 family, also used by the owner `[L2]`. It is 76 pixels wide.
   "Desktop Audio" needs 104 pixels in the repo's 8 x 16 font `[L5]`. No datasheet read.
3. **1.47 and 1.14 inch.** Under half the big panel's height.
4. **3.4 to 3.5 inch QSPI bars.** Taller than the big panel, a third controller, QSPI, and no
   bare-panel datasheet found.
5. **Long OLEDs.** One colour and a 44 mm wide module. Newhaven rates 10,000 to 20,000 hours to
   half brightness and warns of burn-in `[D7]`. A fixed level meter is the worst case. (verified
   for the lifetime)

Two searches found no narrow ST7796 panel. ST7789 RAM is 240 x 320 `[D9]`, so no ST7789 panel is
taller than 320 pixels. (verified for the RAM)

## Driver

One driver core serves the big panel and the bar. Only the init table and the column offset differ.

- LVGL builds its NV3007, ST7789 and ST7796 drivers on one function,
  `lv_lcd_generic_mipi_create`. Each file adds only an init list. (verified, `[C1]` `[C2]` `[C3]`)
  The NV3007 driver first ships in v9.4.0, under `src/drivers/display/nv3007/`. v9.6.0 and master
  move it to `src/drivers/display/mipi/`. Pin LVGL 9.4 or later. (verified, GitHub raw paths per tag)
- Arduino_GFX sets the NV3007 window with `0x2A`, `0x2B`, then `0x2C`, as ST7789 does. The NV3007
  list sets pixel format `0x3A` to `0x05`, 16-bit. (verified, `[C1]` `[C4]`)
- The 2.79 inch glass needs column offset 12 at rotation 0 and 14 at rotation 180: 12 + 142 + 14 =
  168. The 1.9 inch glass needs 35. (verified, `[C5]`)
- The NV3007 list is 114 register writes between an unlock (`0xFF 0xA5`) and a lock (`0xFF 0x00`).
  The ST7789 list is 8. All 103 single-byte entries equal Arduino_GFX's 2.79 inch table, not its
  1.65 inch one. LVGL is MIT. (verified by script, `[C1]` `[C4]`)
- ST7789 and ST7796 need separate init lists too. An ST7789 bar would not remove the per-panel
  table. (verified, `[C2]`)

A full frame is 142 x 428 x 2 = 121,552 bytes: 49 ms at 20 MHz. A 120 x 10 pixel meter bar is
2,400 bytes, about 1 ms. No frame buffer is needed. (arithmetic; the NV3007 clock limit is not read)

## Numbers for the PCB and the case

All from the Wisevision drawing `[D1]`, verified. For either EastRising part they are **MEASURE**
until its own datasheet is read.

1. **Window.** Active area sits 1.55 mm from each long edge, 1.40 mm from the far short edge and
   3.89 mm from the FPC edge. Open the case to the active area plus 0.3 mm a side for a foam
   gasket, 0.4 mm for a cover lens: 21.88 x 64.74 or 22.08 x 64.94 mm.
2. **Placement.** Both FPC edges face the keys. With the active tops level, the bar module's top
   edge sits 0.95 mm below the big module's. Its FPC edge ends 12.56 mm above the big module's.
   The two modules total 78.84 mm of width before gaps. (arithmetic, `[D1]` `[L3]`)
3. **Tail.** 10 pads, 0.30 x 3.00 mm at 0.50 pitch, 0.30 mm thick at a 4.00 mm stiffener. It
   leaves the short edge off centre; the offset is not dimensioned. The drawing shows the pads on
   the display face and the stiffener on the rear (likely). **MEASURE** both on a sample.
4. **Pins.** 1 SDA, 2 SCL, 3 RS, 4 RESET (RSTB in the pin table), 5 CS, 6 TE (FMARK/TE on the
   drawing), 7 VDD, 8 LEDK, 9 LEDA, 10 GND. SCL and SDA are
   shared with the big panel. The bar adds CS, RS and a backlight pin. TE may stay open.
5. **Supply.** The DC table gives VCC 2.5 to 3.3 V, typical 2.8. The pin table says "VDD(3.3V)".
   A 3.3 V rail sits on the table's maximum; absolute maximum is 4.6 V. Backlight is 100 mA at
   3.2 V: feed it from 5 V through the sink in report 10.

Alternate, TFT1901 `[D2]`: active area 1.55 mm from each long edge. Tie IM1 and IM2 high and RD
low for 4-wire SPI. Its tail is 0.3 mm thick with 0.35 mm pads. The same glass ships with other
tails, 12 pin and 24 pin, and one maker wires the LEDs in series for 10.8 to 13.2 V `[D3]` `[D8]`
(likely, earlier run). A footprint fits one maker only.

## Conflicts and flags

1. **The brief says the narrow display is about two thirds as tall as the big one.** I measure 0.93
   to 0.99. The pick follows the sketch. If the owner meant two thirds, take the alternate (0.58)
   or the 2.25 inch (0.75).
2. **The brief prefers ST7796 or ST7789 for both panels.** The pick is NV3007. If the owner rejects
   that, take the alternate.
3. **`CLAUDE.md` locks one FPC connector, `FH12-20S-0.5SH(55)` `C596730`, 20 pins.** The bar needs
   10 pins and the alternate 30. Either LCSC cell is `UNVERIFIED`. `[L4]`
4. **`board.toml` has one `[display]` table, for the old 2.8 inch panel.** Two panels need two
   tables. Not written in this run. `[L4]`
5. **The brief says no `macropad-nixylab` exists.** The directory is spelled `macropad-nyxilab`
   `[L2]`. I read it and changed nothing.

The Wisevision table gives thickness 2.15 mm and the drawing 2.1 +/- 0.1 mm. The product page prints
the model as N279-1442 and the datasheet as N279-1428 `[D1]` `[W1]`.

## Not checked

- No BuyDisplay page or PDF. Every ER-TFT fact is a search-engine snippet. Risk: pin count, pin
  order and price are wrong, or the EastRising glass differs from the Wisevision drawing.
- The NV3007 datasheet `[B4]`. Risk: the SPI clock limit is unknown.
- Stock and shipping to the owner. No AliExpress, LCSC or DigiKey listing was found for this glass.
- Colour and brightness match with the big panel. Wisevision's page says 350 cd/m2; the datasheet
  leaves luminance blank `[D1]` `[W1]`.
- OLEDs other than one Newhaven part. `[D3]`, `[D8]` and the OLED drawing were not re-read today.

## Sources

Panel datasheets read today:

- `[D1]` Wisevision N279-1428KIWIG01-C10, Ver A, drawing dated 2024-05-10. https://www.jx-wisevision.com/uploads/N279-1428KIWIG01-C101.pdf
- `[D2]` QDtech TFT1901, rev 1.0. https://www.lcdwiki.com/res/MSP1901/TFT1901-SPEC_V1.0.pdf
- `[D4]` Limito LBS147TC-IG01, rev A. https://files.waveshare.com/upload/c/c5/SPEC_LBS147TC-IG01_VER_A.pdf
- `[D5]` QDtech TFT1141, rev 1.0. https://www.lcdwiki.com/res/MSP1141/TFT1141-SPEC_V1.0.pdf
- `[D7]` Newhaven NHD-3.12-25664UCB2. https://newhavendisplay.com/content/specs/NHD-3.12-25664UCB2.pdf
- `[D9]` Sitronix ST7789P3, Waveshare copy. https://files.waveshare.com/wiki/common/ST7789P3.pdf

Read by the earlier run, not today:

- `[D3]` CDTech S019BQ01HN, V2.0. https://www.cdtech-display.com/wp-content/uploads/2025/07/S019BQ01HN-V2.0-Specification2.pdf
- `[D8]` Waveshare 1.9inch LCD Module schematic. https://files.waveshare.com/upload/7/7f/1.9inch_LCD_Module.pdf

Driver source code and documentation read today:

- `[C1]` LVGL `lv_nv3007.c`, master. https://github.com/lvgl/lvgl/blob/master/src/drivers/display/mipi/lv_nv3007.c
- `[C2]` LVGL `lv_st7789.c` and `lv_st7796.c`, master. https://github.com/lvgl/lvgl/tree/master/src/drivers/display/mipi
- `[C3]` LVGL NV3007 page. https://lvgl.io/docs/open/9.5/integration/external_display_controllers/nv3007
- `[C4]` Arduino_GFX `Arduino_NV3007.h` and `.cpp`, master. https://github.com/moononournation/Arduino_GFX/blob/master/src/display/Arduino_NV3007.h
- `[C5]` Arduino_GFX `Arduino_GFX_display.h`, lines 99 to 103 and 156. https://github.com/moononournation/Arduino_GFX/blob/master/examples/PDQgraphicstest/Arduino_GFX_display.h

Web pages read today through a fetch tool:

- `[W1]` Wisevision 2.79 inch product page. https://www.jx-wisevision.com/2-79-small-size-142rgbx428-dots-tft-lcd-display-module-screen-product/
- `[W5]` Waveshare ESP32-S3-Touch-LCD-3.49. https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-3.49
- `[W8]` LCDWiki 1.9 inch IPS module, MSP1901. https://www.lcdwiki.com/1.9inch_IPS_Module

BuyDisplay, not read (HTTP 403); search-engine snippets only:

- `[B1]` ER-TFT2.79-2: https://www.buydisplay.com/download/manual/ER-TFT2.79-2_Datasheet.pdf and https://www.buydisplay.com/2-79-inch-142x428-resolution-ips-tft-lcd-display-nv3007-4-wire-spi. ER-TFT2.79-1: https://www.buydisplay.com/wide-angle-2-79-inch-142x428-color-ips-tft-display-nv3007-controller
- `[B3]` ER-TFT2.25-1. https://www.buydisplay.com/2-25-inch-tft-serial-spi-76x284-lcd-display-module-w-st7789p3
- `[B4]` NV3007 datasheet, V1.0, 2024-06. https://buydisplay.com/download/ic/NV3007.pdf

Local files:

- `[L1]` `docs/images/sketch.jpg`
- `[L2]` `/home/worxbend/Projects/macropad-nyxilab/common/cad/macropad_cad/params.py`, `Display19` and `DisplayBar`
- `[L3]` `docs/research/06-big-display.md`: Focus E35GH-I-RW300-N, 54.46 x 82.94 x 2.15 mm, active 48.96 x 73.44 mm
- `[L4]` `board.toml` lines 24 to 40 and `CLAUDE.md`
- `[L5]` `firmware/font8x16.h`

## Open questions

1. Which EastRising part carries the Wisevision 10-pin table: ER-TFT2.79-1 or ER-TFT2.79-2?
   Snippets link a 10-pin connector drawing to the first and give 12 pins for the second. This
   blocks the connector footprint.
2. Does the owner accept an NV3007 panel, and a strip as tall as the sketch, over the ST7789
   family and the brief's two thirds?
3. Do the active tops line up, as the brief says, or the bottoms, as the sketch draws? The gap is
   9.30 mm either way.
4. Does LVGL's init list drive the bought glass, and at what SPI clock? A breakout, ER-TFTM2.79-2,
   is listed for a bench test before the PCB order (unverified `[B1]`).
5. Does the FPC edge point at the knobs or at the top of the body? Rotation by 180 degrees is free
   in software. The 60 mm tail and the first encoder decide it.

Next action: question 1.

## Verification

A skeptic pass, 2026-11-18. I opened each source myself: PDFs through `pdftotext` and rendered
drawing pages, source code from GitHub raw, local files with `grep`. I wrote scripts to count init
lists. Verdict: **corrected**. The pick holds. Three small facts changed and one tag went down.

| # | Claim | Source opened | Result |
|---|---|---|---|
| 1 | N279 bar: 142 x 428, NV3007, SPI 4, module 24.38 x 69.43, active 21.28 x 64.14, pitch 0.1498 | `[D1]` general spec and drawing, page 6 | Holds. The table gives 2.15 mm thick and the drawing 2.1 +/- 0.1 mm, as the report says |
| 2 | Window 1.55 / 1.40 / 3.89 mm, FPC 10 pin at 0.50, 5.50 wide, 60.00 long, pads 0.30 x 3.00, 4.00 stiffener, tail 0.3 thick | `[D1]` drawing, page 6 | Holds. 3.89 is 69.43 - 64.14 - 1.40. The FPC offset along the short edge is not dimensioned |
| 3 | Pin order 1 SDA to 10 GND; VCC 2.5 to 3.3 V, typ 2.8; abs max 4.6 V; 5 LEDs parallel, 3.2 V, 100 mA | `[D1]` pin table, DC table, backlight note | Holds. Pin names corrected in place: 4 is RSTB/RESET, 6 is FMARK/TE |
| 4 | TFT1901: 170 x 320, ST7789, 25.8 x 49.72 x 1.43, active 22.695 x 42.72, 30 pins at 0.5, 15.5 wide, IM1 = IM2 = 1 for 4-line SPI, RD to ground, 4 LEDs, 3.0 V, 80 mA | `[D2]` pages 4 to 5 and drawing | Holds. The pin-7 and pin-8 text in the QDtech table is swapped against its own SPI use. Wire it to the ST7789 manual, not to that prose |
| 5 | LVGL builds NV3007, ST7789 and ST7796 on `lv_lcd_generic_mipi_create`; NV3007 list is 114 writes in an `0xFF 0xA5` / `0xFF 0x00` unlock; ST7789 list is 8 | `[C1]` `[C2]`, parsed by script | Holds: 114 entries, 103 of them single-byte, and 8. Added: the driver first ships in v9.4.0 under `nv3007/` and moves to `mipi/` in v9.6.0 |
| 6 | All 103 single-byte LVGL entries equal Arduino_GFX `nv3007_279_init_operations`, not the default table | `[C1]` `[C4]`, compared by script | Holds: 103 of 103 match the 2.79 table and 37 of 103 match the default table |
| 7 | Window set by `0x2A`, `0x2B`, `0x2C`; `0x3A` = `0x05`; offsets 12 and 14 for the 2.79 inch, 35 for the 1.9 inch | `[C4]` `.cpp` lines 25 to 34, `[C5]` lines 99 to 103 and 156 | Holds. 12 + 142 + 14 = 168 matches `NV3007_TFTWIDTH` |
| 8 | NV3007A RAM is 168 x 428 | `[C4]` header only | **Downgraded to likely.** It is a driver constant, not a datasheet value. `[B4]` is still behind HTTP 403 |
| 9 | ST7789 RAM is 240 x 320 | `[D9]` Sitronix ST7789P3, feature list | Holds: "240RGB x 320 dot", RAM 240x320x18 bits |
| 10 | Big panel active 48.96 x 73.44, 2.15 thick; AA 2.35 mm from the far short edge, so the bar top sits 0.95 mm lower | `[L3]` lines 22 and 117 | Holds by arithmetic: 2.35 - 1.40 = 0.95; 82.94 - 0.95 - 69.43 = 12.56; 54.46 + 24.38 = 78.84 |
| 11 | 2.25 inch bar outline 17.90 x 62.50 x 2.3 | `[L2]` `DisplayBar` | **Corrected to 2.36 mm thick** (`lcm_t`). AA 14.80 x 55.29 is also from that file, so it stays MEASURE |
| 12 | Newhaven OLED 44.00 x 89.20 x 6.0, active 19.18 x 76.78, 10,000 to 20,000 h to half brightness, burn-in warning | `[D7]` drawing page 4 and lifetime table | Holds. **Upgraded from likely to verified.** The 44 mm is the carrier PCB. The bezel is 29.60 x 89.00 |
| 13 | Wisevision page: model N279-1442, 350 cd/m2, MOQ 1, 10 pins | `[W1]` fetched with curl | Holds. The page also gives 1.65 to 3.3 V analog supply and -40 to +85 C operating temperature. Both disagree with `[D1]`. Trust the datasheet |
| 14 | `macropad-nyxilab` exists and uses a 1.9 inch MSP1901-type board and a 2.25 inch bar | `ls /home/worxbend/Projects`, `[L2]` | Holds. `Display19` says "MSP1901-compatible, FPC T190X7-C30", an 8-pin carrier board |
| 15 | Sketch: the narrow window is 0.93 to 0.99 of the big window's height, its top is about 7% lower and the bottoms are level | `[L1]`, read by eye after rotating about 20 degrees | Holds within the stated 10%. I read the width as about 17 to 19 mm, not 19 to 22. Treat both as rough |

Not refuted, still unverified: every BuyDisplay fact `[B1]` `[B3]` `[B4]`. The datasheet URL
returns HTTP 403 to curl today. I did not try to get past it.

Check against the owner's words. The owner asked for "2 displays one bigger and one longer". The
bar is a 1 : 3 strip, and its height is 0.87 of the big panel's, so it is the "longer" shape the
sketch draws. It is not longer in millimetres than the big panel. The two-thirds height and the
ST7789/ST7796 preference come from the research brief, not from the owner's quoted requirement.
They do not overrule the sketch. The owner's answer says the strip shows source name, level and
mute for three knobs. 142 px is 17 columns of the 8 x 16 font, and 428 px splits into three
142 px cells. That fits. The recommendation stands. Its open risk is the retail part's FPC
(question 1), not the design data.
