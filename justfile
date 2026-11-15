# macropad-obs: `just` lists the recipes.
# `just test` is gcc, cargo, and python3. It does not build the window, the PCB, or the UF2.

root := justfile_directory()

default:
    @just --list

test: test-firmware test-host check pcb-test cad-check

test-firmware:
    mkdir -p {{root}}/.build
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware -DVECTORS='"{{root}}/firmware/test/vectors.txt"' \
        {{root}}/firmware/link.c {{root}}/firmware/test/test_link.c \
        -o {{root}}/.build/test_link
    {{root}}/.build/test_link
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware \
        {{root}}/firmware/input.c {{root}}/firmware/test/test_input.c \
        -o {{root}}/.build/test_input
    {{root}}/.build/test_input
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware \
        {{root}}/firmware/st7789.c {{root}}/firmware/font8x16.c {{root}}/firmware/test/test_st7789.c \
        -o {{root}}/.build/test_st7789
    {{root}}/.build/test_st7789

test-host:
    cd {{root}}/host && cargo test && cargo clippy --all-targets -- -D warnings && cargo fmt --check

check:
    python3 {{root}}/tools/check_pins.py

pcb-test:
    cd {{root}}/pcb/gen && python3 -m unittest

cad-check:
    python3 {{root}}/cad/build.py check

# Not on the test chain. Needs webkit2gtk-4.1. A missing library fails this recipe.
app:
    cd {{root}}/app/src-tauri && cargo build

# Not on the test chain. KiCad 9.0.9 in Docker. Does not claim Gerbers exist until this exits 0.
pcb:
    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp \
        -v "{{root}}:{{root}}" -w "{{root}}" kicad/kicad:9.0.9 \
        python3 pcb/gen/build.py place

# Not on the test chain. Ubuntu 24.04 image, pico-sdk commit in firmware/Dockerfile.
firmware:
    #!/usr/bin/env bash
    set -euo pipefail
    docker build -t macropad-obs-fw -f {{root}}/firmware/Dockerfile {{root}}/firmware
    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e PICO_SDK_PATH=/opt/pico-sdk \
        -v "{{root}}:{{root}}" -w {{root}}/firmware macropad-obs-fw \
        bash -lc 'cmake -S . -B .build -DPICO_BOARD=pico && cmake --build .build && mkdir -p dist && cp .build/macropad-obs.uf2 dist/macropad-obs.uf2'

# Geometry only. Needs cad/.venv. Not on the test chain.
cad:
    {{root}}/cad/.venv/bin/python {{root}}/cad/build.py geometry
