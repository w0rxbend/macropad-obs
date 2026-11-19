# Owner decisions on spec v2

Recorded 2026-11-18. These answers override the recommendations in `spec-v2.md` where they differ.

| Id | Question | Answer |
|---|---|---|
| D1 | How does the pad reach OBS? | **W: Wi-Fi.** ESP32-S3 module with an external antenna. The firmware dials the OBS WebSocket itself. No PC process at runtime. |
| D2 | Where does the OBS password live? | **The pad stores it.** The app writes it once and can never read it back. Rule R1 replaces "No OBS password in a CDC frame". |
| D3 | Layout and style | **Approve `layout-v2` and style A**: flat slab, chamfered edges, bead blast, black anodise, laser-engraved ticks. |
| D4 | Narrow panel for the spike | Not asked. The default is the recommendation: Wisevision N279 by quote. |
| D5 | Reuse earlier repos and Freerouting | **Allow.** Copy the greycode PCB generator, the nyxilab exporters and the macropad CNC drawings, relicensed MIT and CERN-OHL-S. Freerouting 2.5.0 is fetched by sha256. |

D1 = W changes the spec: the MCU moves from RP2350B to an ESP32-S3 module, and the board needs a buck regulator, an antenna path out of the metal case, and Wi-Fi credential provisioning from the app.

## Second round, 2026-11-18

| Id | Question | Answer |
|---|---|---|
| D7 | How does the Wi-Fi antenna get out of the aluminium case? | **A non-metal insert in the back wall**, with an internal antenna behind it. Needs its own clearance check. |
| D8 | Burn the HMAC eFuse key to encrypt stored secrets? | **No burn.** The OBS password and the Wi-Fi key are stored in plain NVS. Anyone holding the pad can read them with esptool. D2 stands: the pad still stores the password and the app never reads it back over USB. |
| USB-C | The rear stakes of the USB-C socket sit under the big display carrier | **Use a socket with surface-mount shell tabs.** |
| Spec | Approve spec v2 and start? | **Approved: plan and build.** |
| G-rules | May `CLAUDE.md` be rewritten with rules R1 to R6 of spec section 12? | **Approved, all six** (2026-11-19). |

## Third round, 2026-11-19

| Id | Question | Answer |
|---|---|---|
| G-deps | New dependencies: LwJSON v1.10.1 (vendored), `espflash` 4.7.0, `cc`, `serialport`, a 4 bpp font source | **Approved, all.** |
| G-docker | Pull `espressif/idf:v6.1.1` (4.2 GB); build the `app-check` image from the local `kicad/kicad:10.0.7` with apt packages | **Approved, both.** |
| G-git | How is the work committed? | **Always commit and push to `main`.** |
| G-parallel | How many agents at once? | **8.** |
