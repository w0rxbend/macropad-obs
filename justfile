# macropad-obs: `just` lists the recipes.
# `just test` is gcc, cargo, and python3. It does not build the window or the PCB.

root := justfile_directory()

default:
    @just --list

test: test-firmware test-host check numbers

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
        -I{{root}}/firmware \
        {{root}}/firmware/st7789.c {{root}}/firmware/font8x16.c {{root}}/firmware/test/test_st7789.c \
        -o {{root}}/.build/test_st7789
    {{root}}/.build/test_st7789

test-host:
    cd {{root}}/host && cargo test && cargo clippy --all-targets -- -D warnings && cargo fmt --check

check:
    python3 {{root}}/tools/check_pins.py
    python3 {{root}}/tools/test_check_pins.py
    python3 {{root}}/tools/test_docs.py

numbers:
    python3 {{root}}/tools/check_numbers.py
    python3 {{root}}/tools/test_check_numbers.py
    python3 {{root}}/tools/test_check_measure.py

# Not on the test chain. Board-order gate (spec 9 step 6): exits 1 while board.toml carries an
# open MEASURE on a gated entry. No board order while it exits 1.
gate:
    python3 {{root}}/tools/check_measure.py

# Not on the test chain. Needs webkit2gtk-4.1. A missing library fails this recipe.
# Fails until task 3.6: task 1.6a deleted the v1 bridge that src/session.rs still imports.
app:
    cd {{root}}/app/src-tauri && cargo build

# Not on the test chain. KiCad 9.0.9 in Docker. Does not claim Gerbers exist until this exits 0.
# Fails until task 5.6: task 1.4b retired pcb/gen with the old wedge.
pcb:
    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp \
        -v "{{root}}:{{root}}" -w "{{root}}" kicad/kicad:9.0.9 \
        python3 pcb/gen/build.py place
