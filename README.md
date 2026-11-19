# macropad-obs

An 8° wedge for OBS. Nine MX keys, one knob, and a 2.4" ST7789 TFT sit on the same face. The front edge is the low edge. The whole body rises toward the USB side. The glass is flush with the keys.

The pad speaks USB CDC. A Linux app holds the OBS WebSocket, the URL, and the password. The password never goes to the pad.

![Mesh render of the 8 degree case, screen, nine key holes, and knob](docs/images/case.png)

That picture is a mesh render of the retired v1 wedge. It is not a photograph. Nothing in it has been printed, assembled, or flashed.

## Commands

| Command | What it does |
| --- | --- |
| `just test` | Native checks only. No Docker, no Tauri window |
| `just gate` | Board-order gate. Lists each open MEASURE on a gated `board.toml` entry and exits 1 while one is open. Not part of `just test` |
| `just pcb` | KiCad 9.0.9 in Docker. Fails until task 5.6: task 1.4b retired the old generator |
| `just app` | Tauri shell. Needs `webkit2gtk-4.1`. Not part of `just test` |

`cad/.venv` is local and gitignored. Create it with `uv` from `cad/pyproject.toml`.

## Status

`just test` on 2026-11-16 exited 0:

- `link: all tests pass`
- `input: all tests pass`
- `st7789: all tests pass`
- host: 22 passed, 0 failed, then `cargo clippy --all-targets -- -D warnings` and `cargo fmt --check`
- `check_pins: 6 checks match board.toml`
- pcb: 6 tests, OK
- `cad/build.py check` printed no problems. With `cad/.venv` present it does not print `cad check skipped`, and it does not rebuild the solids

Task 1.3 has since replaced the RP2040 pins: `check_pins` now prints `check_pins: 30 nets, pins.h and protocol.rs match board.toml`.

Task 1.4b has since retired the old wedge: `pcb/gen`, `pcb/kicad`, `pcb/fab`, `cad/exports`, the pcb tests, and the cad check are gone. `python3 cad/build.py check` exits 2 with `no case body until 6.2a`. `tasks/todo.md` tasks 5.1, 6.1, and 6.2a bring them back.

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
- Bottom-side CPL rotation is KiCad's angle and is unverified against a PCBWay preview

The glass solid is 2.25 mm thick, the datasheet typical. The pocket depth in `board.toml` is 2.35 mm. The plate web is 1.5 mm, so the glass hangs below the plate. Retention in the model is the pocket, not a lip over the glass.

## UNVERIFIED

LCSC cells stay `UNVERIFIED` except RP2040 `C2040`, W25Q128JVSIQ `C97521`, and FH12-20S-0.5SH(55) `C596730`. That includes USB-C, AP2112K-3.3, USBLC6-2SC6, TS-1187A, the Abracon crystal, the backlight FET, the passives, the polyfuse, the MX sockets, the Alps EC11, and the Raystar glass.

Passives whose netlist position is `(0, 0)` are absent from the silkscreen. Their BOM and CPL rows remain at the origin until a layout pass moves them.
