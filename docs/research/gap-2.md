# Gap 2: the Tauri app has no build-and-run criterion

## Recommendation

Do both. They cost little and check different things.

1. **Owner action, once:** install `webkit2gtk-4.1` and `xdotool` with pacman. Only this proves the
   owner's deliverable: a Linux window on this PC that talks to the pad.
2. **No-sudo gate, now:** add `just app-check`. It builds `app/src-tauri` in a container made from
   the local `kicad/kicad:10.0.7` image. Then it opens the window under Xvfb. It needs no sudo and
   no new base image. It does need apt packages inside the container, and that counts as a new
   dependency under "Ask first".

Today's experiment found a second reason the gap matters: **the current `app/src-tauri` does not
compile.** It has three defects, listed below. No criterion would have caught them, because nothing
has ever built the shell.

## Evidence

### What is on this machine (verified, `pacman -Q` / `pacman -Si`, 2026-11-18)

- Missing: `webkit2gtk-4.1` (extra 2.54.2-1, 141 MiB installed), `xdotool` (extra 4.20260303.1-1),
  and `libappindicator-gtk3` (tray only).
- Present: `base-devel`, `curl`, `wget`, `file`, `openssl`, `appmenu-gtk-module`, `librsvg`, `gtk3`,
  `libsoup3`, `xorg-server-xvfb` (`/usr/sbin/Xvfb`).
- Tauri's Arch list is `webkit2gtk-4.1 base-devel curl wget file openssl appmenu-gtk-module
  libappindicator-gtk3 librsvg xdotool`. The Debian list is `libwebkit2gtk-4.1-dev
  build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev`.
  Source: https://v2.tauri.app/start/prerequisites/ (verified).
- Report 13 names `libayatana-appindicator` for the tray. Tauri's Arch list names
  `libappindicator-gtk3` instead. Neither is installed. The spec should use Tauri's name.
  (verified against the page above; which of the two libraries Tauri's tray actually loads on Arch
  is unverified)

### A cheap experiment: a container build with no sudo (verified, scratch dir `/tmp/tmp.EWEOvXYdbH`)

- Local images checked: `kicad/kicad:9.0.9` (Debian 12) has no WebKit. `kicad/kicad:10.0.7`
  (Debian 13) already ships `libwebkit2gtk-4.1-0` 2.54.0, `libgtk-3-0t64` 3.24.49 and
  `libsoup-3.0-0` 3.6.5. It has no `-dev` package and no `.pc` file. `fr-xvfb:latest`
  (Ubuntu 26.04) has Xvfb but no WebKit.
- The scratch image was `FROM kicad/kicad:10.0.7` plus
  `apt-get install --no-install-recommends libwebkit2gtk-4.1-dev build-essential pkg-config
  libssl-dev libxdo-dev libudev-dev librsvg2-dev xvfb xauth xdotool x11-utils ca-certificates`.
  It built in under 10 minutes. A dry-run install of the full Tauri set planned 209 packages.
- Cargo ran in the container from the host's `~/.rustup` (read-only mount), with `CARGO_HOME` and
  `CARGO_TARGET_DIR` in scratch. The repo was copied, never mounted for writing.
- **Unpatched copy of today's `app/src-tauri`: the build fails.** These are the defects, each
  confirmed by a compiler error:
  1. `capabilities/default.json` lists `allow-get-state` and six more. The build stops with
     `Permission allow-get-state not found`. `build.rs` calls plain `tauri_build::build()`, so
     Tauri never generates permissions for the app's own commands. Fix: call
     `tauri_build::try_build(Attributes::new().app_manifest(AppManifest::new().commands(&[...])))`.
     That API is documented at https://v2.tauri.app/security/capabilities/ (verified).
  2. `main.rs:70`: `app.manage(...)` fails with E0599 because the `tauri::Manager` trait is not
     imported.
  3. `generate_context!()` panics with `icon .../icons/32x32.png is not RGBA`. All three icons are
     8-bit RGB (`file icons/*.png`).
- **Patched in scratch** (the three fixes above; tauri 2.12.5 from `Cargo.lock`): `cargo build`
  finishes and gives `target/debug/macropad-obs`, 253 MB, debug.
- **The window opens.** Run under `xvfb-run -a -s "-screen 0 1280x1024x24"` with
  `WEBKIT_DISABLE_COMPOSITING_MODE=1`, `xdotool search --onlyvisible --name '^macropad-obs$'` found
  the window within 1 s. `xwininfo` reported 980 x 760 and `IsViewable`, which matches
  `tauri.conf.json`. The process was still alive 4 s later. Whether the HTML rendered is
  unverified: the image had no screenshot tool (`xwd` is in x11-apps).
- After the run, the probe image was removed (`docker rmi`). Nothing in the repo changed.

### What the container cannot prove

It cannot prove a native window under the owner's Wayland session, or a USB CDC port seen by the
app. `docker run --device` could pass a port through, but that is not how the owner will run the
app. So reading, editing and writing the config on the dev board stays a host check after the
pacman install. (likely)

## Text the spec should carry

**Section 3, new item "D6. Install the Tauri window libraries (owner, once)":**

> Run `sudo pacman -S --needed webkit2gtk-4.1 xdotool` (about 142 MiB). Add `libappindicator-gtk3`
> only if the tray icon ships. Everything else on Tauri's Arch list is already installed. Until
> this is done, `just app` fails and the app is proven only in the container (`just app-check`) and
> against padsim.

**Section 10, commands:**

```
just app         # cargo build in app/src-tauri on the host; needs D6
just app-check   # no sudo: image FROM local kicad/kicad:10.0.7 + Tauri's Debian -dev list,
                 # cargo build, then xvfb-run: window "macropad-obs" visible within 10 s, alive 5 s
```

**Section 11, replace the `app` row:**

> | `app` | core tests pass against padsim; read-edit-write round trip keeps unknown fields; export has
> no secret; `just app-check` exits 0; after D6, `just app` exits 0 and the window opens on the
> owner's desktop |

**Section 11, add a row:**

> | `app-shell` (first task) | the three known build defects are fixed: `build.rs` declares the
> app commands through `AppManifest::commands`, `main.rs` imports `tauri::Manager`, icons are RGBA
> PNG |

The new design replaces the seven old commands, so the `AppManifest::commands` list must track
whatever `generate_handler!` lists.

**Section 12, "Ask first":** add "the apt packages in the `app-check` image (Tauri's Debian list
plus `xvfb xauth xdotool pkg-config libudev-dev`, fetched from Debian mirrors on top of the local
`kicad/kicad:10.0.7`)".

**Section 13, new criterion 13:**

> 13. On this machine after D6: `just app` exits 0. The window opens. With the dev board on USB, the
>     app finds the pad without a fixed device path. It reads the document, changes one key mapping
>     and the OBS URL, and writes it. A restart of the app and a second read show the change with
>     `seq + 1`. Before D6, `just app-check` exits 0. That covers the build and the window only,
>     not the pad.

**Section 15, item 6:** add "Is the CI that `app-check` stands in for wanted (public repo)? If so, it
is the same recipe on `ubuntu-24.04` with Tauri's Debian list."

## Not checked

- Whether the UI HTML renders inside the window. There was no screenshot tool in the image.
- A native Wayland run. Xvfb is X11 only.
- A release build and its size.
- Which tray library (`libappindicator-gtk3` or the ayatana one) Tauri loads on Arch.
- The run time of `app-check` from a cold cargo cache. Today's build used a warm registry, and the
  image layer took the longest.
