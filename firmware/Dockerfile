# SPDX-License-Identifier: MIT
# pico-sdk 2.1.1, commit bddd20f928ce76142793bef434d4f75f4af6e433.
FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake gcc-arm-none-eabi libnewlib-arm-none-eabi \
        git python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/raspberrypi/pico-sdk.git /opt/pico-sdk \
    && git -C /opt/pico-sdk fetch --depth 1 origin bddd20f928ce76142793bef434d4f75f4af6e433 \
    && git -C /opt/pico-sdk checkout bddd20f928ce76142793bef434d4f75f4af6e433 \
    && git -C /opt/pico-sdk submodule update --init --depth 1

ENV PICO_SDK_PATH=/opt/pico-sdk
WORKDIR /src
