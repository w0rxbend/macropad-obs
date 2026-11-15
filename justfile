# macropad-obs: `just` lists the recipes.

root := justfile_directory()

default:
    @just --list

test: test-firmware test-host check

test-firmware:
    mkdir -p {{root}}/.build
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I{{root}}/firmware -DVECTORS='"{{root}}/firmware/test/vectors.txt"' \
        {{root}}/firmware/link.c {{root}}/firmware/test/test_link.c \
        -o {{root}}/.build/test_link
    {{root}}/.build/test_link

test-host:
    cd {{root}}/host && cargo test && cargo clippy --all-targets -- -D warnings && cargo fmt --check

check:
    python3 {{root}}/tools/check_pins.py
