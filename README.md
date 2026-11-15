# macropad-obs

USB CDC macropad for OBS Studio. The pad does not open a socket and does not store the OBS password.

## Status

`just test` on 2026-11-15, with gcc ASan, cargo, and python3:

- `link: all tests pass`
- `input: all tests pass`
- `st7789: all tests pass`
- host: 22 passed, 0 failed
- `check_pins: 6 checks match board.toml`
- pcb: 6 tests, OK
- `cad check skipped: no cad/.venv`

The window was not launched. The PID is not registered. Nothing has been built or flashed.

`just app` was not run. It builds `app/src-tauri` and needs `webkit2gtk-4.1`. This machine does not have that package. A missing WebKit fails `just app` and does not fail `just test`.

`just pcb` was not run. It uses Docker image `kicad/kicad:9.0.9`. There are no Gerbers and no `board-sha256.txt`.

`just firmware` was not run. The image is Ubuntu 24.04 from `firmware/Dockerfile`, with pico-sdk commit `bddd20f928ce76142793bef434d4f75f4af6e433` (tag 2.1.1). There is no UF2.

## Flash

`firmware/CMakeLists.txt` sets both of these:

- `PICO_BOOTSEL_VIA_DOUBLE_RESET=1`
- `PICO_BOOTSEL_VIA_DOUBLE_RESET_TIMEOUT_MS=500`

Hold BOOT and plug in, or double-tap RESET inside that 500 ms window. The ROM drive is `RPI-RP2`. No firmware has been copied onto a board.

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
- Bottom-side CPL rotation is KiCad's rotation and is unverified against a PCBWay preview

## UNVERIFIED

LCSC cells stay `UNVERIFIED` except RP2040 `C2040`, W25Q128JVSIQ `C97521`, and FH12-20S-0.5SH(55) `C596730`. That includes USB-C, AP2112K-3.3, USBLC6-2SC6, TS-1187A, the Abracon crystal, the backlight FET, the passives, the polyfuse, the MX sockets, the Alps EC11, and the Raystar glass.
