#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Usage: window.sh COMMAND [ARG...]
# Starts COMMAND on the current X display. Exits 0 when a window titled "macropad-obs" is visible
# within 10 s, and 5 s later COMMAND still runs and the window is still up. Exits 1 otherwise.
# `just app-check` runs it under xvfb-run in the app-check image. Needs xdotool.
set -Eeuo pipefail

readonly TITLE_PATTERN='^macropad-obs$'
readonly VISIBLE_WITHIN_S=10
readonly ALIVE_FOR_S=5

fail() {
    printf 'app-check: %s\n' "$1" >&2
    exit 1
}

(($# > 0)) || fail 'usage: window.sh COMMAND [ARG...]'

# WebKit's accelerated compositing needs a GPU, and Xvfb has none (docs/research/gap-2.md).
WEBKIT_DISABLE_COMPOSITING_MODE=1 "$@" &
readonly app_pid=$!
trap 'kill "$app_pid" 2>/dev/null || true' EXIT

timeout "$VISIBLE_WITHIN_S" xdotool search --sync --onlyvisible --name "$TITLE_PATTERN" >/dev/null \
    || fail "no visible window within ${VISIBLE_WITHIN_S} s"
sleep "$ALIVE_FOR_S"
kill -0 "$app_pid" 2>/dev/null || fail "the app exited within ${ALIVE_FOR_S} s of showing its window"
xdotool search --onlyvisible --name "$TITLE_PATTERN" >/dev/null \
    || fail "the window closed within ${ALIVE_FOR_S} s of showing"
printf 'app-check: window visible within %s s, alive %s s later\n' "$VISIBLE_WITHIN_S" "$ALIVE_FOR_S"
