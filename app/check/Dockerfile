# SPDX-License-Identifier: MIT
# The image behind `just app-check`: the Tauri shell builds and opens its window with no sudo and
# no host package (docs/research/gap-2.md).
# Base: the local kicad/kicad:10.0.7. It is Debian 13 and ships the WebKitGTK 4.1 runtime.
# No `# syntax=` line: it would pull docker/dockerfile, which is not a local image.
# No Rust in the image: the recipe mounts the host toolchain read-only at /opt/rust.
FROM kicad/kicad:10.0.7

ARG DEBIAN_FRONTEND=noninteractive

# Tauri's Debian list (https://v2.tauri.app/start/prerequisites/), plus pkg-config and libudev-dev
# for the build, plus xvfb, xauth and xdotool for the window check.
USER root
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        curl \
        file \
        libayatana-appindicator3-dev \
        librsvg2-dev \
        libssl-dev \
        libudev-dev \
        libwebkit2gtk-4.1-dev \
        libxdo-dev \
        pkg-config \
        wget \
        xauth \
        xdotool \
        xvfb \
    && rm -rf /var/lib/apt/lists/*
USER kicad

ENV PATH=/opt/rust/bin:$PATH
