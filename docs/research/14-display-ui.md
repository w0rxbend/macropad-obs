# 14. What the two displays show and how the firmware draws it

Research only, 2026-11-18. This file is the only file written. An earlier run saved first findings;
this run re-read them, kept them, and finished the report. Tags: **verified** (read or run today in
a primary source), **likely** (reasoned from a verified fact, or two sources agree), **unverified**.
**MEASURE** marks a size not read in a datasheet drawing. Keys such as `[L1]` point into Sources.
No panel was on the desk.

Next action: the owner answers open question 1 ("level" means the fader setting, the live meter,
or both). It decides whether the pad subscribes to `InputVolumeMeters`.

## Recommendation

**Draw widgets, not screens. No frame buffer.** Each display holds a short list of widgets (kind,
rectangle, binding). The firmware redraws a widget only when the values it shows change. It
renders that widget into a 16-line band buffer, background and text together, and sends the band by
DMA in one burst. Two band buffers ping-pong: 20 kB of RAM for the big panel, against 307 kB for a
full frame. Text is anti-aliased: 4 bits per pixel glyphs made at build time by `lv_font_conv`
(MIT), from an OFL face with Latin and Cyrillic. The renderer is plain C with no SDK headers, so
`just test` builds it with gcc and checks rendered bands by hash, as the current tests check SPI
bytes.

**The app edits the widget list.** It ships three presets (A, B, C below). The owner moves,
resizes, adds or removes widgets and chooses what each one shows. The device stores the list in
the config document from report 13, checks it, and returns it on read-back.

**Not LVGL, for now.** LVGL 9 has drivers for both chosen controllers and is MIT. It fits a
free-form UI better. This pad has a fixed set of seven widget kinds, and a hand-written band
renderer is smaller, deterministic and testable byte for byte. LVGL stays the fallback if the
widget set grows past what the band renderer can hold.

Five findings carry the pick.

1. **A full frame does not fit beside the network stack.** 320 x 480 x 2 = 307,200 bytes; the bar
   adds 121,552. RP2350 has 520 kB; report 04 puts USB and network state at 33 kB and does not fit
   both frames. (verified arithmetic, `[R4]`)
2. **Small redraws do not tear in practice; full ones do.** The pick has no TE pin `[R6]`. The
   ST7796 family scans at about 60 Hz `[C1]`. A 104 x 104 key cell is 4.6 ms on the wire at
   37.5 MHz: less than one 16.7 ms scan. A full frame is 66 ms: about four scans, seen as a wipe.
   (likely: arithmetic on verified rates)
3. **The panel cannot be read back.** The pick's 4-line SPI has no SDO line `[R6]`. Blending must
   happen over a background the firmware knows. A widget always paints its own background, so it
   always does. (verified for the pin; design consequence)
4. **Scene names are UTF-8 with no length limit** `[R5]`. The current ASCII font prints `?` for
   every Cyrillic letter (`firmware/st7789.c:32-37`). Fonts must carry Cyrillic. (verified)
5. **The owner's earlier pad already proved "redraw only what changed"** with row hashes over a
   full canvas (`dirty_rows.h`) and a PC build of the drawing code that writes PNGs
   (`tools/ui_sim/run.py`) `[P1]`. Widget-level dirty flags give the same result without the
   canvas. (verified by reading)

The price: the renderer, text layout and UTF-8 handling are new C code (estimate 1,000 to 1,500
lines), and a page change shows a 66 ms wipe.

## What exists and what can be reused

Read today: `firmware/st7789.c` (196 lines), `firmware/src/panel.c` (113 lines),
`firmware/font8x16.c`. `[L1]`

| Piece | Reuse? | Why |
|---|---|---|
| `st_build_init` op list, command constants | Idea only | It is an ST7789 table. The picks are ST7796U and NV3007, each with its own init list `[R7]` |
| `st_op_t` trace and host test of SPI bytes | Yes, as a pattern | Keep "test the bytes without a panel". Test rendered bands by hash instead of a 4-byte-per-SPI-byte trace |
| `st_draw_glyph` | No | Every glyph goes to the same window, columns 0 to 7, rows 0 to 15 (`st7789.c:74-83`) |
| `play()` | No | Toggles CS and calls `spi_write_blocking` once per byte (`panel.c:20-32`). The trace buffer is `st_op_t ops[8192]`, 32 kB (`panel.c:110`) |
| Skip-if-unchanged in `st_draw_status` | Yes, generalised | Becomes the per-widget value hash |
| `st_fit_host` truncation | Idea only | Truncate by glyph advance and add an ellipsis, not by byte count |
| `font8x16.c` | No | "Glyphs are a generated bitmap, not a licensed face". ASCII, 1 bit per pixel |
| RGB565 sent high byte first | Yes | `st7789.c:89-90`. Both picks take RGB565 on SPI `[R6]` `[R7]` |

## What the screens show

Data comes from obs-websocket 5 `[R5]` `[O1]`:

- Program and preview scene: `CurrentProgramSceneChanged`, `CurrentPreviewSceneChanged`, studio
  mode from `StudioModeStateChanged`.
- REC and LIVE: `RecordStateChanged`, `StreamStateChanged` carry `outputActive` and
  `outputState` only. Elapsed time is `outputTimecode` and `outputDuration` in `GetRecordStatus`
  and `GetStreamStatus`. Read it once on each state change and count locally; re-read every 30 s.
  (verified, `[O1]`)
- Knob channels: `inputVolumeDb` (-100 to 26), `inputMuted`, and optionally
  `InputVolumeMeters`, one event every 50 ms, 2.4 kB for 10 stereo inputs `[R5]`.
- Connection: the firmware's own state (USB link, network, OBS session identified, OBS error).
- Wall clock: OBS sends none. The app can send the time over CDC on connect. See open question 3.

### Big display, 320 x 480 portrait

Physical: 0.153 mm pitch, 48.96 x 73.44 mm active `[R6]`. 104 px is 15.9 mm. The key block is
57.15 mm wide, so the mirror is a scaled map of the keys, not a window over them.

Cell states use two cues, so they read without colour:

- Program: red fill, white text, a "PGM" tag.
- Preview: 4 px green border, a "PVW" tag.
- Idle scene key: dark fill. A non-scene key (mute, record, hotkey) shows its action word small
  above the label.
- Unbound key: empty outline. A key whose scene no longer exists in OBS: grey text with a dashed
  outline.

### Narrow display, 142 x 428 portrait (alternate 170 x 320)

Three strips, one per knob, top to bottom in knob order. Each shows the source name, the level, and
mute, as the owner asked. Muted: the strip turns deep red, the dB number is replaced by "MUTED".
The fader bar is the OBS volume setting. The meter bar is the live peak, shown only when meters
are on.

## Mock-ups at real pixel sizes

Grid unit 4 px. Every rectangle below is a widget. Coordinates are x, y, w, h in pixels.

### A. "Mirror" (default preset)

```
320 x 480                                                          widget       x   y   w   h
+------------------------------------------------------------+
| (o) OBS ok        REC 00:12:41          LIVE 01:02:13      |    status       0   0 320  36
+-------------------+--------------------+-------------------+
| SCENE             | SCENE              | MUTE              |    key 0        0  40 104 104
|                   |####################|                   |    key 1      108  40 104 104
| Intro             |#Desk wide #########| Mic               |    key 2      216  40 104 104
| card              |#############  PGM #|                   |
|                   |####################|                   |
+-------------------+--------------------+-------------------+
|+=================+| SCENE              | SCENE             |    key 3        0 148 104 104
||Screen share     || Guest              | Game              |    key 4      108 148 104 104
||            PVW  ||                    |                   |    key 5      216 148 104 104
|+=================+|                    |                   |
+-------------------+--------------------+-------------------+
| REC               | STREAM             | HOTKEY            |    key 6        0 256 104 104
| Record            | Go live            | Replay            |    key 7      108 256 104 104
|                   |                    | save              |    key 8      216 256 104 104
+-------------------+--------------------+-------------------+
| PGM  Desk wide                                             |    scene_line   0 364 320  24
| PVW  Screen share                                          |    scene_line   0 388 320  24
+--------------+--------------+--------------+--------------+
|   Studio     |    Cut       |    Fade      |   Page 2/3   |    legend 0..3  x=0,81,162,243
|   mode       |              |              |              |                 y=416 w=77 h=64
+--------------+--------------+--------------+--------------+
```

`####` is the red program fill. `+===+` is the green preview border. Key text: action word at
14 px, label at 20 px on up to two lines (about 8 characters a line in a 96 px inner width,
MEASURE until the face is chosen), tag at 14 px bottom right.

### B. "On air" preset: the program scene large, stream health below

```
320 x 480                                                          widget       x   y   w   h
+------------------------------------------------------------+
| (o) OBS ok        REC 00:12:41          LIVE 01:02:13      |    status       0   0 320  36
+------------------------------------------------------------+
|  PROGRAM                                                   |    scene_line   0  40 320  80
|  Desk wide                                    (28 px)      |    (program, large)
|  next: Screen share                           (14 px)      |
+-------------------+--------------------+-------------------+
| Intro             |#Desk wide #########| Mic               |    key 0..8     cells 104 x 72
+-------------------+--------------------+-------------------+                 rows y=124,200,276
| Screen share PVW  | Guest              | Game              |                 cols x=0,108,216
+-------------------+--------------------+-------------------+
| Record            | Go live            | Replay save       |
+--------------+--------------+--------------+--------------+
|   Studio     |    Cut       |    Fade      |   Page 2/3   |    legend 0..3  y=352 w=77 h=56
+--------------+--------------+--------------+--------------+
| Dropped 0 / 81,204 frames         Congestion [###.......]  |    text (stream) 0 412 320 68
+------------------------------------------------------------+
```

Key labels shrink to one line at 20 px. The stream line needs `GetStreamStatus` every 2 s while
live (`outputSkippedFrames`, `outputTotalFrames`, `outputCongestion` `[O1]`).

### C. "Idle" preset, used after the idle timeout (both panels at 15% backlight)

```
320 x 480                                  142 x 428
+------------------------------+           +----------------+
|                              |           | 1  Mic         |   strip 0  0   0 142 140
|          REC                 |           |    -12 dB      |   (name and number only,
|        00:12:41   (28 px)    |           +----------------+    no bars)
|                              |           | 2  Desktop     |   strip 1  0 144 142 140
|          LIVE                |           |    MUTED       |
|        01:02:13              |           +----------------+
|                              |           | 3  Music       |   strip 2  0 288 142 140
|     (o) OBS ok               |           |    -30 dB      |
+------------------------------+           +----------------+
```

Any key, button or knob, or any OBS state change, restores the active preset at once.

### Narrow strips (presets A and B)

```
142 x 428 (preferred)                         170 x 320 (alternate)
x 0..141, three strips 140 tall, 4 gap        three strips 104 tall, 4 gap
+--------------------------------+            +--------------------------------------+
| 1  VOL                  (14px) | y+0        | 1  Mic                  -12.4 dB     | y+0   name 20, dB 20
| Mic                     (20px) | y+18       | [##########---------------]  fader   | y+30  158 x 10
| (2nd line if needed)           | y+42       | [######|......]              meter   | y+44  158 x 6
|   -12.4 dB              (28px) | y+70       | push: mute               (14 px)     | y+80
| [##########---------]  fader   | y+104  126 x 10        +--------------------------------------+
| [######|.....]         meter   | y+118  126 x 6
| push: mute              (14px) | y+126
+--------------------------------+
```

Fader bar: -60 to 0 dB, linear in dB, empty below -60 (a design choice, not the OBS fader curve;
open question 4). Meter bar: green to -20 dB, yellow to -9, red above; the tick is the peak hold
for 1 s.

## The widget model the app edits

Seven kinds cover every mock-up. A widget is one record; a display is a list of at most 16.

| Kind | Argument | Shows |
|---|---|---|
| `status` | field set: link, rec, live, clock | Connection dot and word, REC and LIVE with elapsed time |
| `key` | key index 0 to 8 | Label, action word, PGM or PVW state |
| `legend` | button index 0 to 3 | Label of that small button's action |
| `scene_line` | program or preview; size small or large | Scene name |
| `strip` | knob 0 to 2; parts: name, db, fader, meter, push | One channel |
| `text` | a fixed string (up to 32 UTF-8 bytes) or one binding: stream health, page, host | Text |
| `clock` | 24 h or 12 h | Wall clock, if the app sent the time |

As the app holds it (TOML, as `host/src/config.rs` already does):

```toml
[display.big]
preset = "mirror"           # what "reset" returns to
idle_preset = "idle"
[[display.big.widget]]
kind = "status"; x = 0; y = 0; w = 320; h = 36; fields = ["link", "rec", "live"]
[[display.big.widget]]
kind = "key"; x = 0; y = 40; w = 104; h = 104; key = 0
# ...
[display.bar]
[[display.bar.widget]]
kind = "strip"; x = 0; y = 0; w = 142; h = 140; knob = 0; parts = ["name", "db", "fader", "push"]

[theme]
program = "#C8102E"; preview = "#2E9E4F"; text = "#F2F2F2"; panel = "#1C1F24"; muted = "#5A0F14"
brightness = 80            # percent
idle_dim_after_s = 120; idle_brightness = 15; idle_off_after_s = 1800
```

On the device each widget packs into 12 bytes: kind (1), x, y, w, h (2 each), argument (1), parts
or flags (1), colour override (1). 16 widgets are 192 bytes, plus up to 32 bytes per `text`
string. The record goes inside the config document of report 13; this report adds no frame type.

Rules both sides enforce, with shared test vectors:

1. Rectangle inside the panel, x, y, w, h multiples of 4, w and h at least 24.
2. No two widgets overlap. (No z-order: overlap would make "redraw one widget" wrong.)
3. Each `key`, `legend` and `strip` argument at most once per display.
4. Unknown kind or bad field: the device rejects the whole layout and keeps the stored one. It
   reports the first bad widget's index in the reply. It never shows half a layout.
5. A key's label defaults to the scene name when the key's action is a scene; the layout does not
   repeat it.

Read-back is the same record list. The app shows a preview from the same C renderer: built for
the host and called from the Tauri Rust side through `cc`, so the preview matches the panel
pixel for pixel (likely; this is the `ui_sim` pattern of `[P1]`).

## How the firmware draws it

### Options compared

| Option | RAM, big panel | Pros | Cons |
|---|---|---|---|
| 1. Widget bands, no frame buffer (pick) | 2 x 320 x 16 x 2 = 20,480 B | Small, deterministic, gcc-testable, redraw cost known per widget | New renderer and text code; layouts limited to the 7 kinds |
| 2. LVGL 9 partial mode | 1/10 screen buffers recommended: 30,720 B each; about 100 kB RAM and 200 to 300 kB flash for a typical UI `[V1]` `[V2]` | MIT, NV3007 and ST7796 drivers in tree, UTF-8, 1 to 8 bpp fonts, free-form widgets `[V1]` `[V3]` | Large dependency, its own object model to map the layout onto, harder byte-exact tests |
| 3. Full frame + dirty rows (`macropad-nyxilab`) | 307,200 B (+121,552 for the bar) | Any drawing, simplest mental model | Does not fit both frames in 520 kB; needs the optional PSRAM `[R4]` |

### Drawing rules

1. **Never draw on the panel piece by piece.** The current code sends each glyph straight to the
   panel. Instead fill a band with the widget's background, draw its shapes and text into the
   band, then send the band. One CASET, RASET, RAMWR per band. This removes build-up flicker.
2. **Dirty by value.** Each widget keeps a 32-bit hash of what it last showed (strings, numbers,
   state, theme version). An event updates the model; the draw loop walks the widgets and redraws
   those whose hash changed. A timer marks the timecode text once a second.
3. **Primitives:** filled rectangle, 4 px rounded rectangle, 1 to 4 px border, horizontal bar,
   glyph run. All clip to the band. That is all seven kinds need.
4. **Text:** 4 bpp alpha glyphs. Blend each glyph over the known widget colour with a 16-entry
   RGB565 lookup per colour pair. Truncate by glyph advance and end with an ellipsis. Missing glyph:
   draw a box. Sizes 14, 20 and 28 px. Glyph set: ASCII, Latin-1, Cyrillic U+0400 to U+045F.
   Flash estimate: about 115 kB for the three sizes (unverified: 4 bpp at roughly 100 bytes a glyph
   at 20 px; measure with `lv_font_conv` output). Face: Inter, OFL, with tabular figures so the
   timecode does not jitter `[F1]`; Cyrillic coverage is likely, not checked.
5. **SPI by DMA, 16-bit frames.** Set the SPI to 16-bit data for pixels, so an RGB565 word goes out
   high byte first with no byte swap (likely). Render band n+1 while band n is sent.
6. **Order.** Draw top to bottom, the panel's scan direction, so a full-screen change reads as one
   wipe, not a scramble. Status first, then the widget the user just pressed.

### Wire time at 37.5 MHz (the RP2350 step report 06 plans on)

| Region | Bytes | Time |
|---|---|---|
| Full big frame 320 x 480 | 307,200 | 65.5 ms |
| Key cell 104 x 104 | 21,632 | 4.6 ms |
| Status bar 320 x 36 | 23,040 | 4.9 ms |
| Timecode text 100 x 28 | 5,600 | 1.2 ms |
| Full bar frame 142 x 428 | 121,552 | 25.9 ms |
| Strip 142 x 140 | 39,760 | 8.5 ms |
| Meter bar 126 x 6, three of them | 4,536 | 1.0 ms |

Arithmetic: bytes x 8 / 37.5 MHz. A scene switch redraws two cells, two scene lines and maybe the
status: about 16 ms. Meters at 20 Hz cost 1 ms of every 50. If report 07 is right that both panels
share SCK and MOSI, the meters wait at most one band (a few ms) behind the big panel; report 04
gives each panel its own bus. Either works with bands; see open question 5. The NV3007 clock
limit is not read `[R7]`.

### Tearing

The ST7796S datasheet states its electrical tables at "Frame rate = 60Hz" and gives the frame rate
as 10^7 / ((168 + RTNA + 32 x (15 - FRS)) x (480 + VFP + VBP)) `[C1]`. TEON (35h) drives a TE pin
`[C1]`, but the E35GH tail has no TE pin `[R6]`. With no TE, a cell written in 4.6 ms can show one
16.7 ms frame half old, half new. That is below notice for a state change (likely). A full-screen
change takes four scans and shows as a 66 ms top-down wipe; accept it. The NV3007 bar has a TE pad
(pin 6) `[R7]`: wire it to a GPIO if one is free, and start bar writes on its edge.

### Dimming and idle

- Backlight by PWM on a low-side switch, about 20 kHz so it neither flickers on camera nor whines.
  The earlier pad used 20 kHz, 8-bit `[P1]`. Brightness from the theme, 0 to 100%.
- Idle after `idle_dim_after_s` with no input and no OBS change: switch to the idle preset at
  `idle_brightness`. After `idle_off_after_s`: backlight off, panel stays awake. **Never go dark
  while REC or LIVE is on**: the pad then stays at idle brightness. Wake on any input or change.
- Controller idle mode (IDMON, 39h) cuts colour to 8 and changes the frame rate `[C1]`. The
  backlight dominates power, so the gain is small; not used.
- On boot: backlight off, init, paint every widget once, then backlight on. No white flash.
- On lost OBS link: the status widget shows the reason ("No network", "OBS refused", "Wrong
  password", "Connecting"), key states keep the last value in grey. No modal screen.

## Repo rules

- No conflict found. The layout is part of the config document; when that document's frame type
  lands, `firmware/link.c`, `host/src/protocol.rs`, `firmware/test/vectors.txt` and
  `docs/protocol.md` change together, plus layout vectors for the rules above.
- `docs/protocol.md` says text is printable ASCII. Scene names and widget text need UTF-8. That
  rule must change (report 05 says the same) `[R5]`.
- The new panel pins (two CS, DC, RESET, two backlight PWM, optional TE) go into `board.toml` first.

## Skipped or not checked

- No panel was driven. Tearing visibility, the wipe, and 37.5 MHz on either glass are untested.
- Inter's Cyrillic coverage and the font flash size are not measured.
- The band renderer's line count is an estimate. LVGL's real RAM on this layout was not measured.
- Risk: if the owner wants free-form layouts (images, arbitrary shapes), option 1 runs out and
  option 2 becomes the better base.

## Sources

- `[L1]` `firmware/st7789.c`, `firmware/src/panel.c`, `firmware/font8x16.c` in this repo, read today.
- `[P1]` `/home/worxbend/Projects/macropad-nyxilab/common/firmware/lib/nyx_ui/src/ui/dirty_rows.h`,
  `display.cpp` (canvas plus changed rows, 20 kHz PWM backlight), `tools/ui_sim/run.py`. Read today.
- `[R4]` `docs/research/04-mcu-and-firmware-stack.md`: RP2350 520 kB, 33 kB USB and network state, separate buses.
- `[R5]` `docs/research/05-obs-websocket.md`: events, meters every 50 ms, UTF-8 names, ASCII rule.
- `[R6]` `docs/research/06-big-display.md`: E35GH-I-RW300-N, ST7796U, no TE pin, no SDO, 37.5 MHz step.
- `[R7]` `docs/research/07-long-display.md`: N279-1428KIWIG01-C10, NV3007, TE on pin 6, shared SCL/SDA.
- `[C1]` Sitronix ST7796S V1.0, 2014-11: FRMCTR1 (B1h) frame-rate formula p. 213, TEON (35h) p. 181,
  IDMON (39h) p. 188, "Frame rate = 60Hz" test condition. https://dl.espressif.com/dl/schematics/ST7796S_SPEC_V1.0.pdf
  (verified for the S part; the U part in `[R6]` is the same family, likely the same)
- `[O1]` obs-websocket 5.7.6 `protocol.json`: fields of GetRecordStatus, GetStreamStatus,
  RecordStateChanged, StreamStateChanged. https://github.com/obsproject/obs-websocket/blob/5.7.6/docs/generated/protocol.json (verified by script)
- `[V1]` LVGL master, commit 2ee5654 (2026-11-17), `docs/src/main-modules/display/setup.mdx`
  (partial mode, 1/10 buffer), `docs/src/main-modules/fonts/overview.mdx` (1, 2, 3, 4, 8 bpp),
  `src/drivers/display/mipi/` (lv_nv3007.c, lv_st7796.c, lv_st7789.c). Latest tag v9.6.0. https://github.com/lvgl/lvgl (verified)
- `[V2]` LVGL README: MIT; 32 kB RAM minimum, about 100 kB RAM and 200 to 300 kB flash typical. https://github.com/lvgl/lvgl/blob/master/README.md (verified)
- `[V3]` `lv_font_conv` 1.5.3, MIT. https://github.com/lvgl/lv_font_conv (verified)
- `[F1]` Inter, SIL OFL 1.1, tabular numbers. https://github.com/rsms/inter (verified for licence and tabular figures; Cyrillic unverified)

## Open questions

1. "Level" on the narrow display: the fader setting (`inputVolumeDb`), the live meter, or both?
   Meters cost a 65536 subscription and 2.4 kB of JSON 20 times a second `[R5]`.
2. Should the big display mirror the keys of the current page only, and what does the 4th small
   button do (the mock-ups assume "page")?
3. Wall clock in the status bar: is "time" the REC and LIVE elapsed time, or the time of day? The
   second needs the app (or SNTP over the network) to set it.
4. Fader bar scale: linear dB from -60 to 0, or OBS's own fader curve? The OBS curve was not read.
5. One shared SPI bus (report 07) or two (report 04)? Bands work either way; the board needs one
   answer in `board.toml`.
6. Does the owner want free-form layouts (images, logos) on the displays? If yes, LVGL (option 2).
7. Is Cyrillic enough, or are other scripts needed in scene names?
