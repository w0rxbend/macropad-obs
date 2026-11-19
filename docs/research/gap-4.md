# Gap 4: big-display redraw time vs. the ST7796U SPI rating

## Recommendation

Make success criterion 7 depend on the SPI clock the spike bench proves. The default is the
datasheet clock, 15 MHz. At 15 MHz: one 96 x 96 key cell in 17 ms or less, full screen in 170 ms or
less. A faster target applies only after the bench records a pass at a faster RP2350 step. Also
require SPI mode 3 (CPOL = 1, CPHA = 1). The current firmware's mode 0 adds a frame-select pulse
between words.

## Text the spec should carry

Section 13, replace criterion 7 with:

> 7. The big display redraws one 96 x 96 key cell in 17 ms or less, and the full 320 x 480 screen
> in T_full or less. Both are timed from the first CASET byte to the end of the last RAMWR byte, with
> DMA, RGB565, and SPI mode 3. The clock is f_bus, the fastest RP2350 SPI step that passed the
> panel bench (section 14). T_full is 170 ms at 15 MHz, 137 ms at 18.75 MHz, 104 ms at 25 MHz and
> 70 ms at 37.5 MHz. Until the bench records a pass above 15 MHz, f_bus is 15 MHz and T_full is
> 170 ms. The 15 MHz figure is in the datasheet. Every faster step is unverified until the bench
> passes it.

Section 14, add a risk row:

> | ST7796U above its 15 MHz write rating (66 ns, rated at VDDI 1.8 V only) | panel bench in spike step 1: at each step from 18.75 MHz up, write 1000 full pseudo-random frames, read each back with RAMRD at 6.25 MHz, zero mismatches, at 3.3 V IOVCC on the real FPC length. The fastest step that passes is f_bus. No pass means f_bus = 15 MHz and the 170 ms target. |

Section 14, "Unproven until hardware" keeps "SPI above 15 MHz". Add "PL022 inter-word gap
(MEASURE)".

Section 11 or the `fw-ui` row: SPI runs in mode 3 (`spi_set_format(spi, 8, SPI_CPOL_1,
SPI_CPHA_1, SPI_MSB_FIRST)`). UI design rule: at 15 MHz a full-screen change takes about 164 ms. Page
changes redraw only the tiles that changed. Full-screen animation is out of scope.

Report 06, item 2 ("Plan on 37.5 MHz"), should read: "Design for 15 MHz. Run at the fastest step
the bench proves."

## Evidence

1. **The 15 MHz ceiling holds, and it is rated at 1.8 V only.** ST7796U V1.0, page 54, "4-SPI
   Interface Timing Characteristics", shows TSCYCW (write) at 66 ns minimum, TSHW and TSLW at 15 ns,
   and TSCYCR (read) at 150 ns. The only listed condition is "VDDI=1.8V, VDDA=2.8V". The datasheet
   has no table at 3.3 V I/O. Source: https://focuslcds.com/wp-content/uploads/Drivers/ST7796U.pdf
   (verified, read today with pdftotext). The 15 ns pulse widths leave room for a faster clock. Only
   the 66 ns cycle limit stops it, so an overclock is plausible but not promised (likely).
2. **Bus time (arithmetic, verified).** Full frame: 320 x 480 x 16 = 2,457,600 bits. Key cell: 96 x
   96 x 16 = 147,456 bits. CASET, RASET and RAMWR add 11 bytes, which is negligible.

   | f_bus | full frame | 96 x 96 cell | T_full (about 4 % margin) |
   | --- | --- | --- | --- |
   | 15 MHz | 163.8 ms | 9.83 ms | 170 ms |
   | 18.75 MHz | 131.1 ms | 7.86 ms | 137 ms |
   | 25 MHz | 98.3 ms | 5.90 ms | 104 ms |
   | 37.5 MHz | 65.5 ms | 3.93 ms | 70 ms |

   At 15 MHz the 17 ms cell budget leaves 7.2 ms for rendering. The old "70 ms at 37.5 MHz" figure
   had 4.5 ms margin, and only with a gapless bus.
3. **The RP2350 hits 15 MHz exactly.** `spi_set_baudrate` uses an even prescale from 2 to 254 and a
   post-divide from 1 to 256, from clk_peri at 150 MHz. The steps are 150 / 2n: 75, 37.5, 25, 18.75,
   15, 12.5, 6.25 MHz. 15 MHz is prescale 2, post-divide 5. Source: Pico SDK,
   `~/.platformio/packages/framework-arduinopico/pico-sdk/src/rp2_common/hardware_spi/spi.c`
   (verified). 6.25 MHz (160 ns) is the fastest step inside the 150 ns read cycle, so the bench reads
   back at 6.25 MHz.
4. **Mode 0 is not gapless.** RP2350 datasheet, section 12.3.4 (PL022): with SPH = 0, "in the case of
   continuous back-to-back transmissions, the SSPFSSOUT signal pulse HIGH between each data word
   transfer". With SPO = 1 and SPH = 1, "the SSPFSSOUT pin is held LOW between successive data
   words". Source: https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf (verified, read
   today). The datasheet does not give the gap's length. If it is one bit time per byte, a 15 MHz
   frame is 184 ms and fails 170 ms; 16-bit words give 174 ms (arithmetic, gap MEASURE). The
   ST7796U latches SDA on the rising SCL edge (datasheet section 8.4, "samples the SDA ... at the
   rising edges"). Mode 3 also samples on the rising edge, so mode 3 suits the panel (likely; bench
   confirms). The repo's `firmware/src/panel.c:35` calls `spi_init`, and `spi_init` sets
   `SPI_CPOL_0, SPI_CPHA_0` (SDK `spi.c`). That is mode 0 (verified).
5. **Overclocks work on other boards, but that is not proof for this glass.** LovyanGFX ships the
   WT32-SC01 (ST7796S on direct SPI) at a 40 MHz write clock and a 16 MHz read clock:
   https://raw.githubusercontent.com/lovyan03/LovyanGFX/master/src/lgfx/v1_autodetect/LGFX_AutoDetect_ESP32_all.hpp,
   `_detector_WT32_SC01_t` (verified as library config; likely for the ST7796 family; unverified for
   the ST7796U on the E35GH). TFT_eSPI's ST7796 setups say "80MHz is OK". That figure is for an
   "RPi ST7796 MH4.0 display", likely behind a shift-register bridge, so it is not evidence here.
   Source: TFT_eSPI `User_Setups/Setup27_RPi_ST7796_ESP32.h`.

## Skipped or not checked, and risk

- I did not measure the PL022 inter-word gap. No board or analyser. Tagged MEASURE.
- I did not check whether RAMRD on 4-line SPI with shared SDA reads back cleanly on the E35GH. If it
  does not, the bench falls back to a visual check and a CRC from a logic analyser. That is weaker
  evidence, so the default stays 15 MHz.
- Raising clk_sys above 150 MHz would change the steps. Not considered.
- Risk: if the bench proves only 15 MHz and mode 3 still shows gaps, 170 ms fails. In that case, use
  PIO SPI (no inter-word gap) or relax T_full. The cell target (9.8 ms of bus time against 17 ms)
  holds in every case.
