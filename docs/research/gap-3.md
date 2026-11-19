# Gap 3: success criteria for display layout edits and input remaps

## Recommendation

Keep criterion 4 as it is. Add criteria 4b and 4c below to section 13. Both run in padsim inside
`just test`, so they need only gcc, cargo and python3 (spec section 10, R4). Neither one adds a
port 0 frame type, so the four-file protocol rule is not touched. The screenshot is a padsim
stdin command. It is not a device frame.

Why: today the `fw-ui` golden PNGs call the renderer straight. They do not prove three things:
the app's edit survives `CFG_COMMIT` and the validator; the stored layout is what the pad draws;
and the band and address-window path writes the right pixels. The `fw-actions` row proves the
mapping table, not that a mapping written by the app reaches OBS.

## Text for section 13

> **4b. Display layout round trip.** padsim runs against `tools/fake_obs.py` loaded with
> `firmware/test/ui_state.json`. The app core reads the document. It changes the string of one
> `text` widget in `main_display` to `Тест 1` and drops `fader` from the parts of the knob 1
> `strip` widget in `strip_display`. It renders its preview from that draft and the same state
> file. Then it writes the document and gets `RESULT ok`. After padsim reports `idle`, its panel
> dumps are byte-equal to the preview: `main.rgb565` 307,200 bytes (320 x 480) and `strip.rgb565`
> 121,552 bytes (142 x 428), both big-endian RGB565, tolerance 0. Every pixel that differs from
> the dump taken before the write lies inside the two edited widgets' rectangles. A third write
> with two overlapping widgets gets `RESULT invalid` and the path of the second widget, and the
> next dumps are byte-equal to the ones before that write.
>
> **4c. Input remap round trip.** The app core sets small button 1 to `toggle_record`. It sets
> knob 0 to input `U_B`, step 2 dB, push `toggle_mute`, and writes the document. padsim then gets
> on stdin one press and release of button 1, one clockwise detent of knob 0, and one push of
> knob 0. `fake_obs.py` logs exactly these three requests, in this order, with `requestId`
> ignored:
> `{"requestType":"ToggleRecord"}`,
> `{"requestType":"SetInputVolume","requestData":{"inputUuid":"U_B","inputVolumeDb":-18}}`
> (`U_B` starts at -20 dB in the state file),
> `{"requestType":"ToggleInputMute","requestData":{"inputUuid":"U_B"}}`.
> No request names the old input `U_A`. The same three events sent before the write produce the
> old mapping's requests. The knob 0 strip shows `U_B`'s name after the write.

Both criteria count toward the 60 s budget of criterion 1.

## What the spec must define so 4b and 4c can run

1. **padsim panel model.** On the POSIX side of the display seam, padsim keeps panel RAM. It
   applies `0x2A`/`0x2B` (column and row window) and `0x2C` (pixel write) to that RAM. The bar
   uses RAM 168 x 428 with column offset 12, so the dump is columns 12 to 153. (R07: the 142 x 428
   size is verified from the N279 drawing. The 168 width and offsets 12/14 are likely, from
   Arduino_GFX source, not from a datasheet.) This model is what makes 4b test more than the
   golden PNGs. The preview writes a framebuffer directly. The pad goes band, then window, then
   SPI words.
2. **padsim stdin commands** (R13 already says "scripted key and knob events come from stdin").
   Name them:
   - `dump <dir>`: writes both `.rgb565` files.
   - `wait-idle`: returns once the full OBS state re-read after `Identified` is done and no widget
     is dirty.
   - `button <i> down|up`, `key <i> down|up`, `knob <i> cw|ccw|push|release`.

   Inject the events as raw matrix levels and A/B phases, so debounce and quadrature are in the
   path. How many quadrature states make one detent comes from `board.toml` (EC11 variant:
   MEASURE).
3. **Determinism.** `firmware/test/ui_state.json` is one OBS state: scenes, program and preview,
   three inputs with UUID, name, dB and mute, record and stream off. `fake_obs.py` serves it, and
   the app passes the same file as `sample_state` to `ui_render`. padsim runs with a fixed clock
   (`--epoch`). No meter part sits in the test layouts, because meters need event 65536 and live
   levels.
4. **Byte equality is the right bar.** Both sides compile the same `fw-ui` C with the same host gcc
   (R14 "pixel for pixel", likely; R13 preview via `cc`). A tolerance would hide offset or
   byte-order bugs. Those are the bugs 4b is meant to catch.

## Section 11 rows to amend

- `padsim`: add "panel model with window and offset; `dump`, `wait-idle` and input commands on
  stdin".
- `app`: add "preview frames byte-equal to padsim dumps for every committed config vector that
  has a layout (4b); remap round trip (4c)".
- `manual`: add "on the dev board, the 4b layout is drawn on both panels and matches the preview
  by eye". A real panel cannot be compared byte for byte.

## Inconsistencies found while reading (contracts must fix)

1. Layout names do not match. Spec 8.2 uses `main_display` / `strip_display`. R14 uses
   `[display.big]` / `[display.bar]` with `widget` lists. R13 uses a `layout` string. The criteria
   above use the spec names. `docs/config.md` must pick one set.
2. Try-only revert does not match. Spec 8.2 says "RAM, 30 s". R13 also reverts on `CFG_READ`.
   If try-only stays, add a padsim `tick <ms>` command and one line to 4b: "a try-only write
   matches the preview, and after 30 s of padsim clock the dumps equal the stored layout".
   I left it out of the criterion text to keep 4b small.

## Evidence

- `SetInputVolume` takes `?inputUuid` and `?inputVolumeDb` (range -100 to 26). `ToggleInputMute`
  takes `?inputUuid`. `ToggleRecord` has no request fields. Verified in
  https://raw.githubusercontent.com/obsproject/obs-websocket/master/docs/generated/protocol.md
  (master, read 2026-11-18). The floor of 5.4.0 is from spec 8.3. I did not check in which
  version each UUID field was added.
- Panel sizes and byte counts: `docs/research/06-big-display.md` and `07-long-display.md`. The
  arithmetic is verified: 320 x 480 x 2 = 307,200 and 142 x 428 x 2 = 121,552.
- Widget kinds and the rules (no overlap, first bad index reported, never half a layout):
  `docs/research/14-display-ui.md`, "The widget model the app edits".
- padsim stdin events and the `cc` preview: `docs/research/13-app-and-config.md`, "Testing
  without hardware" and "Live preview".

Not checked: I ran no experiment. Nothing exists yet to run it against: there is no padsim, no
`fw-ui` and no fake OBS in the tree. The -18 dB value assumes the knob sends absolute
`current + step`. That holds if `fw-actions` ports `host` volume logic as spec 9 says. Confirm
it when that module exists.
