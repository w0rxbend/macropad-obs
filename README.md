# macropad-obs

USB CDC macropad for OBS Studio. The pad does not open a socket and does not store the OBS password.

## Status

`just test` on 2026-11-15, with gcc ASan, cargo, and python3. This commit is the frame codec.

- `link: all tests pass`
- host: 6 passed, 0 failed
- `check_pins: 6 checks match board.toml`

The window is not in this PR. The PID is not registered. Nothing has been built or flashed.

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
