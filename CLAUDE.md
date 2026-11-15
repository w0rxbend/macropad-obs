# macropad-obs

`board.toml` is the pin and mechanical source of truth. `tools/check_pins.py` binds `firmware/pins.h` and `host/src/protocol.rs` to it.

`just test` is gcc ASan, `cargo` in `host/`, and python3. It does not build `app/src-tauri`, does not import KiCad or the Pico SDK, and does not need `cad/.venv`.

Protocol changes update `firmware/link.c`, `host/src/protocol.rs`, `firmware/test/vectors.txt`, and `docs/protocol.md` together.

`LICENSE` is MIT for `firmware/`, `host/`, `app/`, and `tools/`. `LICENSE.cern-ohl-s` is CERN-OHL-S-2.0 for `pcb/` and `cad/`.

No SK6812. No OBS password in a CDC frame. LCSC cells stay `UNVERIFIED` except RP2040 `C2040`, W25Q128JVSIQ `C97521`, and FH12-20S-0.5SH(55) `C596730`.
