# macropad-obs: `just` lists the recipes.
# `just test` is gcc, cargo, and python3. It does not build the window or the PCB.

root := justfile_directory()

default:
    @just --list

test: test-firmware test-host check numbers cad-check pcb-test

test-firmware:
    mkdir -p {{root}}/.build
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -DVECTORS='"{{root}}/firmware/test/vectors.txt"' \
        {{root}}/firmware/core/link.c {{root}}/firmware/test/test_link.c \
        -o {{root}}/.build/test_link
    {{root}}/.build/test_link
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core \
        {{root}}/firmware/core/crypto.c {{root}}/firmware/test/test_crypto.c \
        -o {{root}}/.build/test_crypto
    {{root}}/.build/test_crypto
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/test \
        {{root}}/firmware/core/crypto.c {{root}}/firmware/core/ws.c \
        {{root}}/firmware/test/fake_stream.c {{root}}/firmware/test/test_ws.c \
        -o {{root}}/.build/test_ws
    {{root}}/.build/test_ws
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/core/third_party/lwjson \
        -I{{root}}/firmware/core/third_party/lwjson/src/include \
        -DFIXTURES='"{{root}}/firmware/test/fixtures"' \
        {{root}}/firmware/core/json.c {{root}}/firmware/core/third_party/lwjson/src/lwjson/lwjson_stream.c \
        {{root}}/firmware/test/test_json.c -o {{root}}/.build/test_json
    {{root}}/.build/test_json
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/test -I{{root}}/firmware/core/third_party/lwjson \
        -I{{root}}/firmware/core/third_party/lwjson/src/include \
        -DFAKE_OBS='"{{root}}/tools/fake_obs.py"' \
        {{root}}/firmware/core/crypto.c {{root}}/firmware/core/ws.c {{root}}/firmware/core/json.c \
        {{root}}/firmware/core/third_party/lwjson/src/lwjson/lwjson_stream.c {{root}}/firmware/core/obs.c \
        {{root}}/firmware/core/obs_state.c \
        {{root}}/firmware/test/posix_stream.c {{root}}/firmware/test/test_obs_handshake.c \
        -o {{root}}/.build/test_obs_handshake
    {{root}}/.build/test_obs_handshake
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/test -I{{root}}/firmware/core/third_party/lwjson \
        -I{{root}}/firmware/core/third_party/lwjson/src/include \
        -DFAKE_OBS='"{{root}}/tools/fake_obs.py"' \
        {{root}}/firmware/core/crypto.c {{root}}/firmware/core/ws.c {{root}}/firmware/core/json.c \
        {{root}}/firmware/core/third_party/lwjson/src/lwjson/lwjson_stream.c {{root}}/firmware/core/obs.c \
        {{root}}/firmware/core/obs_state.c \
        {{root}}/firmware/test/posix_stream.c {{root}}/firmware/test/test_obs_state.c \
        -o {{root}}/.build/test_obs_state
    {{root}}/.build/test_obs_state
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core \
        {{root}}/firmware/core/input.c {{root}}/firmware/test/test_input.c \
        -o {{root}}/.build/test_input
    {{root}}/.build/test_input
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core \
        {{root}}/firmware/core/panels.c {{root}}/firmware/test/test_panels.c \
        -o {{root}}/.build/test_panels
    {{root}}/.build/test_panels
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core \
        {{root}}/firmware/core/wifi.c {{root}}/firmware/test/test_wifi.c \
        -o {{root}}/.build/test_wifi
    {{root}}/.build/test_wifi
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/core/third_party/lwjson \
        -I{{root}}/firmware/core/third_party/lwjson/src/include \
        -DCONFIG_VECTORS='"{{root}}/firmware/test/config_vectors"' \
        {{root}}/firmware/core/config.c {{root}}/firmware/core/json.c \
        {{root}}/firmware/core/third_party/lwjson/src/lwjson/lwjson_stream.c \
        {{root}}/firmware/test/test_config.c -o {{root}}/.build/test_config
    {{root}}/.build/test_config
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/core/third_party/lwjson \
        -I{{root}}/firmware/core/third_party/lwjson/src/include \
        -DCONFIG_VECTORS='"{{root}}/firmware/test/config_vectors"' \
        {{root}}/firmware/core/ui.c {{root}}/firmware/core/config.c {{root}}/firmware/core/json.c \
        {{root}}/firmware/core/third_party/lwjson/src/lwjson/lwjson_stream.c \
        {{root}}/firmware/test/test_ui.c -o {{root}}/.build/test_ui
    {{root}}/.build/test_ui
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/core/third_party/lwjson \
        -I{{root}}/firmware/core/third_party/lwjson/src/include \
        {{root}}/firmware/core/actions.c {{root}}/firmware/core/obs_state.c {{root}}/firmware/core/config.c \
        {{root}}/firmware/core/json.c {{root}}/firmware/core/third_party/lwjson/src/lwjson/lwjson_stream.c \
        {{root}}/firmware/test/test_actions.c -o {{root}}/.build/test_actions
    {{root}}/.build/test_actions
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/core/third_party/lwjson \
        -I{{root}}/firmware/core/third_party/lwjson/src/include \
        -DGOLDEN='"{{root}}/firmware/test/golden"' \
        {{root}}/firmware/core/ui.c {{root}}/firmware/core/json.c \
        {{root}}/firmware/core/third_party/lwjson/src/lwjson/lwjson_stream.c {{root}}/firmware/core/render.c \
        {{root}}/firmware/core/font_noto14.c {{root}}/firmware/core/font_noto20.c {{root}}/firmware/core/font_noto28.c \
        {{root}}/firmware/test/test_render.c -o {{root}}/.build/test_render
    {{root}}/.build/test_render
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/core/third_party/lwjson \
        -I{{root}}/firmware/core/third_party/lwjson/src/include \
        -DGOLDEN='"{{root}}/firmware/test/golden"' \
        {{root}}/firmware/core/ui.c {{root}}/firmware/core/json.c \
        {{root}}/firmware/core/third_party/lwjson/src/lwjson/lwjson_stream.c {{root}}/firmware/core/render.c \
        {{root}}/firmware/core/font_noto14.c {{root}}/firmware/core/font_noto20.c {{root}}/firmware/core/font_noto28.c \
        {{root}}/firmware/test/test_render_strip.c -o {{root}}/.build/test_render_strip
    {{root}}/.build/test_render_strip
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/test \
        {{root}}/firmware/core/store.c {{root}}/firmware/test/nor_model.c \
        {{root}}/firmware/test/test_store.c -o {{root}}/.build/test_store
    {{root}}/.build/test_store
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/test -I{{root}}/firmware/core/third_party/lwjson \
        -I{{root}}/firmware/core/third_party/lwjson/src/include \
        {{root}}/firmware/core/device.c {{root}}/firmware/core/link.c {{root}}/firmware/core/store.c \
        {{root}}/firmware/core/input.c {{root}}/firmware/core/config.c {{root}}/firmware/core/json.c \
        {{root}}/firmware/core/third_party/lwjson/src/lwjson/lwjson_stream.c \
        {{root}}/firmware/test/nor_model.c {{root}}/firmware/test/test_device.c \
        -o {{root}}/.build/test_device
    {{root}}/.build/test_device
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/test -I{{root}}/firmware/core/third_party/lwjson \
        -I{{root}}/firmware/core/third_party/lwjson/src/include \
        {{root}}/firmware/core/device.c {{root}}/firmware/core/link.c {{root}}/firmware/core/store.c \
        {{root}}/firmware/core/input.c {{root}}/firmware/core/config.c {{root}}/firmware/core/json.c \
        {{root}}/firmware/core/obs_state.c {{root}}/firmware/core/wifi.c \
        {{root}}/firmware/core/third_party/lwjson/src/lwjson/lwjson_stream.c \
        {{root}}/firmware/test/nor_model.c {{root}}/firmware/test/test_device_obs.c \
        -o {{root}}/.build/test_device_obs
    {{root}}/.build/test_device_obs

# The whole firmware core on the host, ASan/UBSan: CDC on a pty, OBS over TCP, flash in a file.
padsim-build:
    mkdir -p {{root}}/.build
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware/core -I{{root}}/firmware/test -I{{root}}/firmware/core/third_party/lwjson \
        -I{{root}}/firmware/core/third_party/lwjson/src/include \
        {{root}}/firmware/padsim/main.c {{root}}/firmware/padsim/pty.c {{root}}/firmware/padsim/panel_model.c \
        {{root}}/firmware/padsim/nor_file.c {{root}}/firmware/padsim/view.c {{root}}/firmware/test/posix_stream.c \
        {{root}}/firmware/core/device.c {{root}}/firmware/core/link.c {{root}}/firmware/core/store.c \
        {{root}}/firmware/core/config.c {{root}}/firmware/core/json.c \
        {{root}}/firmware/core/third_party/lwjson/src/lwjson/lwjson_stream.c \
        {{root}}/firmware/core/crypto.c {{root}}/firmware/core/ws.c {{root}}/firmware/core/obs.c \
        {{root}}/firmware/core/obs_state.c {{root}}/firmware/core/wifi.c {{root}}/firmware/core/input.c \
        {{root}}/firmware/core/actions.c {{root}}/firmware/core/ui.c {{root}}/firmware/core/render.c \
        {{root}}/firmware/core/panels.c {{root}}/firmware/core/font_noto14.c \
        {{root}}/firmware/core/font_noto20.c {{root}}/firmware/core/font_noto28.c \
        -lm -o {{root}}/.build/padsim

# padsim answers INFO, reaches tools/fake_obs.py, takes its stdin commands, dies at --cut-after.
padsim-smoke: padsim-build
    python3 {{root}}/tools/padsim_smoke.py {{root}}/.build/padsim

# The padsim e2e tests (host/obs_core/tests/padsim_e2e.rs) run the padsim this builds.
test-host: padsim-build
    cd {{root}}/host && PADSIM={{root}}/.build/padsim cargo test && cargo clippy --all-targets -- -D warnings && cargo fmt --check

check:
    python3 {{root}}/tools/check_pins.py
    python3 {{root}}/tools/test_check_pins.py
    python3 {{root}}/tools/check_partitions.py
    python3 {{root}}/tools/test_check_partitions.py
    python3 {{root}}/tools/test_docs.py

numbers:
    python3 {{root}}/tools/check_numbers.py
    python3 {{root}}/tools/test_check_numbers.py
    python3 {{root}}/tools/test_check_measure.py

# Stdlib python3 only, no cad/.venv: the case params read board.toml, no layout literal in cad/.
cad-check:
    python3 {{root}}/cad/obs_case/test_spec.py

# Not on the test chain. Needs cad/.venv (build123d). No STEP runs every step; `just cad body`
# builds the style A top shell and runs its geometry checks.
cad *STEP:
    {{root}}/cad/.venv/bin/python {{root}}/cad/build.py {{STEP}}

# Plain python3 over pcb/gen: no Docker, no KiCad symbol libraries.
pcb-test:
    python3 -B -m unittest discover -s {{root}}/pcb/gen -p 'test_*.py'

# Not on the test chain. Board-order gate (spec 9 step 6): exits 1 while board.toml carries an
# open MEASURE on a gated entry. No board order while it exits 1.
gate:
    python3 {{root}}/tools/check_measure.py

# Not on the test chain. Needs webkit2gtk-4.1. A missing library fails this recipe.
# Fails until task 3.6: task 1.6a deleted the v1 bridge that src/session.rs still imports.
app:
    cd {{root}}/app/src-tauri && cargo build

# Not on the test chain. No sudo and no host library: the same build in an image made from the
# local kicad/kicad:10.0.7 (app/check/Dockerfile), with the host's Rust toolchain mounted
# read-only. Then it passes when the window "macropad-obs" shows under Xvfb within 10 s and is
# alive 5 s later. It proves the build and the window, not the pad. Fails until task 3.6, as `app`.
app-check:
    docker build --quiet --tag macropad-obs-app-check {{root}}/app/check
    mkdir -p {{root}}/.build/app-check
    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp \
        -e CARGO_HOME={{root}}/.build/app-check/cargo \
        -e CARGO_TARGET_DIR={{root}}/.build/app-check/target \
        -v "$(rustc --print sysroot):/opt/rust:ro" \
        -v "{{root}}:{{root}}" -w "{{root}}/app/src-tauri" macropad-obs-app-check \
        sh -c 'cargo build --locked && xvfb-run --auto-servernum --server-args="-screen 0 1280x1024x24" \
            {{root}}/app/check/window.sh "$CARGO_TARGET_DIR/debug/macropad-obs"'

# Not on the test chain. ESP-IDF v6.1.1 in Docker (spec 10). Checks partitions.csv and
# sdkconfig.defaults, builds into .build/esp32s3, reads the built partition table and sdkconfig
# back against them, and writes the merged image .build/esp32s3/macropad-obs-merged.bin
# (bootloader at 0x0, table at 0x8000, app at 0x10000).
firmware:
    python3 {{root}}/tools/check_partitions.py
    mkdir -p {{root}}/.build/esp32s3 {{root}}/.build/idf-home
    docker run --rm -u "$(id -u):$(id -g)" -e HOME={{root}}/.build/idf-home \
        -v "{{root}}:{{root}}" -w "{{root}}/firmware/esp32s3" espressif/idf:v6.1.1 \
        idf.py -B {{root}}/.build/esp32s3 -D SDKCONFIG={{root}}/.build/esp32s3/sdkconfig \
        build merge-bin -o macropad-obs-merged.bin
    python3 {{root}}/tools/check_partitions.py --built {{root}}/.build/esp32s3

# Not on the test chain. KiCad 9.0.9 in Docker. No STEP runs the whole pipeline (today: erc, place);
# `just pcb erc` writes the schematic, runs ERC at all severities and checks it is byte-repeatable;
# `just pcb place` writes the unrouted board to pcb/kicad and checks it against board.toml.
# Does not claim Gerbers exist until the pipeline has a fab step and exits 0.
pcb *STEP:
    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp \
        -v "{{root}}:{{root}}" -w "{{root}}" kicad/kicad:9.0.9 \
        python3 -B pcb/gen/build.py {{STEP}}
