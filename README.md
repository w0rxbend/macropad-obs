# macropad-obs

An 8° wedge for OBS. Nine MX keys, one knob, and a 2.4" ST7789 TFT sit on the same face. The front edge is the low edge. The whole body rises toward the USB side. The glass is flush with the keys.

The pad speaks USB CDC. A Linux app holds the OBS WebSocket, the URL, and the password. The password never goes to the pad.

![Mesh render of the 8 degree case, screen, nine key holes, and knob](docs/images/case.png)

That picture is a mesh render from `just cad`. It is not a photograph. Nothing in it has been printed, assembled, or flashed.

## Files you can open

| Path | What it is |
| --- | --- |
| `cad/exports/*.step` | Top, base, glass, knob, and the four-solid assembly |
| `cad/exports/*.stl` | Same parts, for a slicer |
| `cad/exports/*.3mf` | Same meshes again |
| `docs/images/case.png` | The render above |
| `pcb/kicad/macropad-obs.kicad_pcb` | Outline, four M2 holes, silkscreen |
| `pcb/fab/gerbers/` | Gerbers and drills from KiCad 9.0.9 |
| `pcb/fab/bom-pcbway.csv` | BOM rows, including parts still at (0, 0) |
| `pcb/fab/cpl-pcbway.csv` | Pick-and-place rows |
| `pcb/fab/hand.csv` | The TFT, which is soldered by hand |

`just cad` on 2026-11-16 wrote the case files and printed `exported 4 parts plus assembly ... 0 faults`. Each STEP reopened as a valid solid. Each STL was watertight. The largest STL volume error was the knob, `4.1e-04`.

The board is the mechanical drawing. `just pcb` on 2026-11-16 exited 0 and printed `wrote .../pcb/kicad/macropad-obs.kicad_pcb`. Copper gerbers contain a header and no draws. `macropad-obs-PTH.drl` has no hits. `macropad-obs-NPTH.drl` has four 2.2 mm holes. Nets are not routed. This is not a board to order as a working circuit.

The `.kicad_pcb` stores `board.toml` Y as a positive number. KiCad's Gerber and Excellon files store that same distance as a negative Y. Greycode's plot files do the same.

## Flash

USB-C, device mode. A blank RP2040 enumerates as the drive `RPI-RP2`. Drop a UF2 on that drive.

The floor has a BOOT hole and a RESET hole. Hold BOOT while plugging in, or double-tap RESET inside 500 ms. `firmware/CMakeLists.txt` sets `PICO_BOOTSEL_VIA_DOUBLE_RESET` and `PICO_BOOTSEL_VIA_DOUBLE_RESET_TIMEOUT_MS=500`.

`just firmware` is the Docker recipe that would write `firmware/dist/macropad-obs.uf2`. It has not been run. There is no UF2 in the tree. No board has been flashed.

## Commands

| Command | What it does |
| --- | --- |
| `just test` | Native checks only. No Docker, no UF2, no Tauri window |
| `just cad` | STEP, STL, 3MF, and `docs/images/case.png`. Needs `cad/.venv` |
| `just pcb` | KiCad 9.0.9 in Docker. Writes the board and `pcb/fab/` |
| `just firmware` | Pico SDK image. Not part of `just test` |
| `just app` | Tauri shell. Needs `webkit2gtk-4.1`. Not part of `just test` |

`cad/.venv` is local and gitignored. Create it with `uv` from `cad/pyproject.toml` if `just cad` cannot find the interpreter.

## Status

`just test` on 2026-11-16 exited 0:

- `link: all tests pass`
- `input: all tests pass`
- `st7789: all tests pass`
- host: 22 passed, 0 failed, then `cargo clippy --all-targets -- -D warnings` and `cargo fmt --check`
- `check_pins: 6 checks match board.toml`
- pcb: 6 tests, OK
- `cad/build.py check` printed no problems. With `cad/.venv` present it does not print `cad check skipped`, and it does not rebuild the solids

`just app` was not run. This machine has no `webkit2gtk-4.1`. The window has not been opened.

VID `0x1209` PID `0x4F42` is not registered with pid.codes.

## udev

```text
sudo cp app/udev/70-macropad-obs.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger
```

The rule is `TAG+="uaccess"`, VID `1209`, PID `4f42`, symlink `macropad-obs`. There is no `plugdev` group and no `MODE`.

## License

`LICENSE` is the MIT License for `firmware/`, `host/`, `app/`, and `tools/`.

https://opensource.org/license/mit

`LICENSE.cern-ohl-s` is CERN-OHL-S-2.0 for `pcb/` and `cad/`. Hardware sources are not MIT.

https://cern.ch/cern-ohl

## MEASURE

Left as tagged, not measured on a sample:

- `board.toml`: `pulses_per_detent`, `fpc_edge`, `bushing_hole`, `encoder_pocket`, `knob_lift`, `keycap`, `switch_housing`, `encoder_body`, `tact_body_mm`
- `MADCTL` `0x00` in `firmware/st7789.h`
- FH12 courtyard `(15.0, 5.0)` in `pcb/gen/circuit.py`
- USB mouth in the case, 14 mm by 7 mm, in `cad/obs_case/geometry.py`
- Bottom-side CPL rotation is KiCad's angle and is unverified against a PCBWay preview

The glass solid is 2.25 mm thick, the datasheet typical. The pocket depth in `board.toml` is 2.35 mm. The plate web is 1.5 mm, so the glass hangs below the plate. Retention in the model is the pocket, not a lip over the glass.

## UNVERIFIED

LCSC cells stay `UNVERIFIED` except RP2040 `C2040`, W25Q128JVSIQ `C97521`, and FH12-20S-0.5SH(55) `C596730`. That includes USB-C, AP2112K-3.3, USBLC6-2SC6, TS-1187A, the Abracon crystal, the backlight FET, the passives, the polyfuse, the MX sockets, the Alps EC11, and the Raystar glass.

Passives whose netlist position is `(0, 0)` are absent from the silkscreen. Their BOM and CPL rows remain at the origin until a layout pass moves them.
