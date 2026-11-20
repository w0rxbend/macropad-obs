// SPDX-License-Identifier: MIT
//! Builds the preview (`src/preview.c`) with the firmware's `fw-ui` core through `cc`, the same
//! C sources and C standard padsim compiles, so the preview draws the pad's own pixels (R13).

use std::path::PathBuf;

const CORE: &[&str] = &[
    "ui.c",
    "render.c",
    "font_noto14.c",
    "font_noto20.c",
    "font_noto28.c",
    "actions.c",
    "obs_state.c",
    "config.c",
    "json.c",
    "third_party/lwjson/src/lwjson/lwjson_stream.c",
];

fn main() {
    let firmware = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../firmware");
    let core = firmware.join("core");
    // padsim's view mapping: what each widget shows, from the document and the OBS state.
    let padsim = firmware.join("padsim");
    let mut build = cc::Build::new();
    build
        .std("c11")
        .warnings(true)
        .extra_warnings(true)
        .warnings_into_errors(true)
        .include(&core)
        .include(core.join("third_party/lwjson"))
        .include(core.join("third_party/lwjson/src/include"))
        .include(&padsim)
        .files(CORE.iter().map(|file| core.join(file)))
        .file(padsim.join("view.c"))
        .file("src/preview.c");
    build.compile("fw_ui_preview");
    println!("cargo:rerun-if-changed=src/preview.c");
    println!("cargo:rerun-if-changed={}", core.display());
    println!("cargo:rerun-if-changed={}", padsim.join("view.c").display());
    println!("cargo:rerun-if-changed={}", padsim.join("view.h").display());
}
