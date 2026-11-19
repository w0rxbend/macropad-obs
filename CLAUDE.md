# macropad-obs

`board.toml` is the pin and mechanical source of truth. `tools/check_pins.py` binds `firmware/esp32s3/main/pins.h` and `host/obs_core/src/protocol.rs` to it. `docs/spec/layout-v2.toml` feeds `board.toml`; no board order while `tools/check_measure.py` exits 1.

`just test` is gcc ASan, `cargo` in `host/`, and python3. It does not build `app/src-tauri`, does not import KiCad or the Pico SDK, and does not need `cad/.venv`.

Protocol changes update `firmware/core/link.c`, `host/obs_core/src/protocol.rs`, `firmware/test/vectors.txt` and `docs/protocol.md` together.

`LICENSE` is MIT for `firmware/`, `host/`, `app/`, and `tools/`. `LICENSE.cern-ohl-s` is CERN-OHL-S-2.0 for `pcb/` and `cad/`.

No SK6812. LCSC cells stay `UNVERIFIED`.

The OBS password and any Wi-Fi passphrase cross the CDC link only in `SET_CREDENTIAL`, app to device. No device-to-host frame, log line, display, readback or test vector carries a secret or a value derived from one. The device stores secrets in their own flash partition and erases it on `CLEAR_CREDENTIALS`, on the clear key combination, and before a host-requested download mode.
