# Gap 1: D1 hides that report 03 disagrees, and that C adds a PC daemon

Research only, 2026-11-18. Nothing built. The spec was not edited.

## Resolution

Keep C as the recommendation, but D1 must state the disagreement and the cost in plain words.
Report 03 recommends USB networking (CDC-NCM + lwIP) and names the relay only as its fallback (d2).
Under C, a second PC program the owner never asked for, `obs-link`, must run beside the Tauri app.
So trace row 12 and Objective 3 are met only if the owner accepts C in D1. The spec should say so.

## Evidence

1. **Report 03 recommends NCM, not the relay.** "Make the pad a USB composite device: CDC-ACM for
   configuration and CDC-NCM for networking. The firmware runs lwIP and opens the obs-websocket 5
   connection itself" (`docs/research/03-connectivity.md:9-11`). The relay is "the nearest
   fallback ... option (d2)" (`03-connectivity.md:32-33`). Its options table rates (d2) as honouring
   the owner's words "in part" (`03-connectivity.md:64`), because "the firmware speaks
   obs-websocket to that URL, but through the PC" (`03-connectivity.md:159-163`). (verified, read)
2. **Report 03's reason.** NCM is the only option where the firmware alone reaches OBS on one cable
   with no PC process; obs-websocket binds every interface and has no client filter
   (`03-connectivity.md:17-18`). Its cost is one sudo firewall rule (ufw drops incoming 4455) and
   untested NetworkManager behaviour (`03-connectivity.md:13-14, 20-22`). (verified, read)
3. **Report 03 names when the relay wins.** No sudo step accepted, no NetworkManager, the password
   rule kept as written, or a failed NCM spike (`03-connectivity.md:207-215`). (verified, read)
4. **The vote.** Arch-A picks NCM (`arch-A.md:15-16`). Arch-B picks a relay inside the app
   (`arch-B.md:10-15`). Arch-C picks the `obs-link` relay and calls it "option (d2) of R03,
   promoted to the first choice" (`arch-C.md:16`). No file under `docs/` records the judges'
   ballots, so "two of three judges" has no source in the repo. (verified: `grep -rni judge docs/`)
5. **C adds a resident PC daemon.** The spec's own module table lists `obs-link` as a "headless
   relay, optional challenge answer, systemd user unit, udev rule" (`spec-v2.md:278`), and success
   criterion 2 needs "`obs-link` and OBS 30.1+ running" (`spec-v2.md:410`). It is started by udev
   `SYSTEMD_USER_WANTS=`, which "user service manager instances" read (`man systemd.device`, read
   on this machine; verified for the man text, not run). If that fails, the fallback is the app
   starting it plus an XDG autostart entry (`spec-v2.md:433`).
6. **"No sudo" is not C's edge.** Every option needs one sudo install: the udev rule for the config
   port, since `ttyACM*` is group `uucp` and the user is not in it (`13-app-and-config.md:245-252`;
   `id -nG` today shows no `uucp`). Under A the ufw line joins that same sudo step. C's real edge is
   no firewall rule: the relay dials loopback, and ufw accepts `lo` (`/etc/ufw/before.rules:21-22`,
   verified on this machine). C's other edge is OBS on another PC (`arch-C.md:39`).

## Exact text for the spec

**Objective 3**, replace with:

> 3. The firmware is the obs-websocket 5 client. It holds the session, requests and events itself.
>    Under D1 = C its TCP bytes pass through `obs-link` on the PC; under D1 = A they do not.

**Trace row 12**, third cell, replace with:

> Met under the owner's D1 answer. The firmware does the WebSocket upgrade, auth, Identify,
> requests and events. Under C (recommended) its bytes reach OBS through `obs-link`, a PC daemon
> besides the Tauri app; report 03 rates this "in part". Under A (USB networking) no PC process
> runs. See decision 1.

**D1, "Why C"**, replace with:

> - **Why C.** Arch-C picked it, and the spec follows it; arch-A picked A and arch-B a relay inside
>   the app. (The judges' ballots are not filed in `docs/`.) **Report 03 disagrees: it recommends A**,
>   because only A lets the firmware reach OBS with no PC process, and it rates C as honouring the
>   owner's sentence "in part" (R03, Recommendation and Options compared). C is picked here for
>   fewer host-specific failure points (no firewall rule, no reliance on untested NetworkManager
>   behaviour) and because OBS may run on another PC.
> - **What C costs.** Besides the Tauri app, C adds a second PC program the owner did not ask for:
>   `obs-link`, a resident daemon, plus a systemd user unit and a udev rule that starts it. It must
>   run whenever the pad is used. Both A and C need one sudo install (the udev rule for the config
>   port); A adds one ufw line to that step.
> - **If the owner reads "firmware on the device should be communicating" as "no PC process at
>   all", C fails that reading and A is the answer, on the same board.**

**Section 5, first line**, append: "Report 03 recommends the NCM path (alternate A); see D1."

## Not checked

1. The judges' ballots: not found in the repo, so the "two of three" claim was not verified.
2. `SYSTEMD_USER_WANTS` starting a user unit from udev: man page only, not run.
3. NetworkManager bringing an NCM link up unattended: still unrun, as report 03 says.
