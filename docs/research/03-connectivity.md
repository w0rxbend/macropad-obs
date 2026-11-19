# 03. How the device reaches the OBS WebSocket

Research only, 2026-11-18. This file is the only file written. Confidence tags: **verified** (read or
run today in a primary source), **likely** (reasoned from a verified fact, not run), **unverified**.
Keys such as `[O1]` point into the Sources list. No hardware was used.

## Recommendation

Make the pad a USB composite device: CDC-ACM for configuration and CDC-NCM for networking. The
firmware runs lwIP and opens the obs-websocket 5 connection itself, over the one USB cable, to OBS on
the host PC. No radio and no second connector.

Next action: run the one-afternoon spike in "Validation" on any RP2040 dev board. It settles the two
things this report could not run: how NetworkManager treats the link, and the firewall step.

Five findings carry the recommendation.

1. **OBS is reachable over a USB network link.** obs-websocket listens on every interface and does
   not filter client addresses. (verified, `[O1]` `[O3]`)
2. **Every device-side design meets the host firewall.** The owner's PC runs ufw with incoming DROP
   and no user rules. A pad on Wi-Fi, Ethernet or USB networking gets no answer from port 4455 until
   one rule is added with sudo. Only a host bridge avoids this. (verified on this machine, `[L1]`)
3. **A metal case and an internal antenna do not mix.** "The antenna must not be covered by a
   metallic enclosure completely." Wi-Fi needs a plastic window or an external antenna. (verified,
   `[H1]`)
4. **The parts for USB networking already ship in the Pico SDK.** The TinyUSB NCM class, lwIP, a DHCP
   server and mbedTLS are in the local SDK copy. A WebSocket client is not. (verified, `[L3]`)
5. **The password rule decides how much the direct link is worth.** If the device may not hold the
   OBS password, the app must be running at every OBS start, and a simpler relay does the same job.
   (verified for the mechanism, `[O1]`)

The working reading is practical. The nearest fallback that still honours "firmware on the device
should be communicating with this websocket OBS url" is the byte relay, option (d2) below.

## What OBS does

1. **Bind address.** `_server.listen(conf->ServerPort, errorCode)` calls websocketpp
   `listen(uint16_t port)`, which binds `tcp::v6()`: "The IPv6 protocol with mapped IPv4 for dual
   stack hosts will be used". That is `[::]:4455`, every interface, IPv4 and IPv6. The flag
   `--websocket_ipv4_only` gives `0.0.0.0:4455`. The config has no bind-address field, so
   loopback-only is not an option. If IPv6 is not supported, OBS falls back to `tcp::v4()`
   (`WebSocketServer.cpp:109-111`). Dual stack needs `net.ipv6.bindv6only = 0`, which is the value
   on this PC. (verified in source, `[O1]` `[O2]` `[O3]`, and `sysctl`; not observed on a running
   OBS)
2. **No client filter.** `onValidate` picks a subprotocol and returns `true`. Nothing checks the
   remote address. (verified, `[O1]`)
3. **Defaults.** `ServerEnabled = false`, `ServerPort = 4455`, `AuthRequired = true`,
   `Ipv4Only = false`. (verified, `[O2]`)
4. **Authentication.** The client sends `base64(sha256(base64(sha256(password + salt)) +
   challenge))`. The salt is made in `WebSocketServer::Start()`, so it changes at every server
   start. The challenge is made per session. (verified, `[O1]` lines 85-86 and 254, `[O4]`)
5. **No TLS.** The server type is `websocketpp::config::asio` from `asio_no_tls.hpp`. `wss://` needs
   a proxy in front of OBS. (verified, `[O2]`)

On the owner's PC: OBS Studio 33.0.1 is a Flatpak with `shared=network`, so it listens in the host
network namespace. Its obs-websocket config has `server_enabled: false`, `auth_required: true`,
`server_port: 4455`. The owner must enable the server in OBS under Tools. (verified, `[L4]`; the
password field was not read out)

## Options compared

| | (a) Wi-Fi MCU | (b) USB CDC-NCM + lwIP | (c) Ethernet, W5500 | (d) Host bridge |
| --- | --- | --- | --- | --- |
| Owner's words | honoured | honoured | honoured | (d1) no, (d2) in part |
| Host network setup | none | NetworkManager: none (likely). networkd: one file | none | none |
| Host firewall | open 4455 to the LAN | open 4455 to the pad only | open 4455 to the LAN | nothing to open |
| OBS on the same PC | yes | yes | yes | yes |
| OBS on another PC | yes | no, needs a relay or NAT on the host | yes | yes |
| CNC metal case | window or external antenna | no effect | no effect | no effect |
| Where the session travels | radio and LAN, plaintext | the cable only | LAN, plaintext | loopback |
| Secrets on the device | Wi-Fi key and OBS password | OBS password | OBS password | none |
| Extra current | 88 mA receive, 340 mA peaks | none | 128 to 132 mA | none |
| Extra hardware | radio module, antenna path | none | W5500, RJ45, magnetics, second cable | none |
| Firmware work | high | high | high | low |
| Test without hardware | logic yes, radio no | logic yes, host side with root | logic yes, chip unverified | yes, 22 host tests exist |

### (a) Wi-Fi microcontroller

1. **Parts.** ESP32-S3-WROOM-1U "comes with an external antenna connector", compatible with Hirose
   U.FL. (verified, `[H3]`) Raspberry Pi RM2 puts the Pico W radio (CYW43439) beside an RP2040 over
   SPI, with "an on-board 2.4GHz antenna" and no connector in the brief. (verified, `[H4]`) Both are
   2.4 GHz only. (verified, `[H2]` `[H4]`)
2. **Case.** With a PCB antenna the case needs a non-metal window over the antenna and "at least
   15 mm" clearance "in all directions". (verified, `[H1]` `[H5]`) The 1U variant needs a bulkhead
   antenna on a machined, engraved case. Range through a window is unverified until a prototype
   exists.
3. **Power.** ESP32-S3 peaks at 340 mA (802.11b, 1 Mbps, 21 dBm) and draws 88 mA receiving, at 3.3 V.
   (verified, `[H2]` Table 5-7) RM2: 271 mA transmit, 43 mA receive. (verified, `[H4]`) A USB 2.0 port
   gives 500 mA at 5 V. (likely, USB 2.0 specification, not re-read) Two backlights share that budget.
4. **The cable stays.** The requirements name no battery. The pad still needs USB for power and for
   the configuration app. The radio only replaces a data path that the cable already offers.
5. **Software.** Espressif's `esp_websocket_client` component supports `ws`, `wss` and a subprotocol
   field. (verified, `[H6]`) Wi-Fi adds SSID and key entry in the app, a second stored secret, and
   reconnect handling. The same chip can also do (b): ESP32-S3 has full-speed USB OTG, and
   esp_tinyusb lists NCM and composite devices. (verified, `[H2]` `[H7]`)

The old design rejected Wi-Fi on the pad (`docs/design.md:680-682`). (verified, `[L5]`)

### (b) USB network gadget

Host side:

1. **Driver and NetworkManager.** The kernel `cdc_ncm` module matches any interface of class 02,
   subclass 0D. (verified, `[L2]`) "NetworkManager creates a temporary wired connection for any
   Ethernet device that is managed". (verified, `[N1]`) Its unmanaged list here covers VM bridges,
   veth and the gadget side only. (verified, `[L2]`) That profile asks for DHCP. (likely)
   NetworkManager 1.58.1 is active on the owner's PC and systemd-networkd is not. (verified, `[L2]`)
2. **The pad must run the DHCP server.** TinyUSB ships one (`lib/networking/dhserver.c`). It sends the
   router option only when `router.addr != 0` and the DNS option only when `dns.addr != 0`. Send
   neither: the PC then adds no default route and no DNS server through the pad. (verified in code,
   `[L3]`; likely for the host effect)
3. **systemd-networkd only.** A link with no matching `.network` file is not brought up or
   configured. (verified, `[N3]`) Such hosts need one shipped file with `DHCP=ipv4`, installed as root.
4. **Firewall.** ufw's stock rules accept DHCP replies (`before.rules:46`) and drop a new TCP
   connection to 4455. (verified, `[L1]`) firewalld's `public` zone admits only `ssh` and
   `dhcpv6-client`. (verified, `[N4]`) Fedora Workstation's own zone opens ports 1025 to 65535.
   (likely, `[N5]`, a magazine article) The interface name follows the USB port under the default
   path-based naming policy, so the rule should match the pad's source address. (verified, `[L2]`)
5. **Another PC.** The link reaches the host only. NetworkManager's `shared` method can share the
   PC's uplink (`[N2]`). The polkit default for changing a system connection is `auth_admin_keep`,
   but `/usr/share/polkit-1/rules.d/org.freedesktop.NetworkManager.rules` returns `YES` for a local
   member of `wheel`, and the owner's account is in `wheel`. So on this PC no admin prompt is
   expected from a local session. (verified for the files and the group, `[L2]`; not run;
   `/etc/polkit-1/rules.d/` was unreadable and may override it) Sharing still adds NAT and a
   second host config. The cheaper path is the relay in (d2).

Device side:

1. **Firmware parts.** The SDK copy holds `class/net/ncm_device.c`, the `net_lwip_webserver` example
   (lwIP with `NO_SYS 1`, DHCP server, 192.168.7.1), lwIP 2.2.1 and mbedTLS. (verified, `[L3]`) lwIP's
   apps are HTTP, MQTT, mDNS, SNTP and others. None is a WebSocket client. (verified, `[L3]`)
2. **Why NCM.** The NCM build of that example has one USB configuration. The ECM and RNDIS build
   carries two, one per host family. (verified, `[L3]`)
3. **Composite.** TinyUSB keeps separate class-driver entries for CDC and for the network class
   (`usbd.c:157`, `:287`). RP2040 has 16 endpoints. CDC-ACM plus NCM uses 6 endpoint addresses
   besides endpoint 0. (verified for the files, `[L3]`; likely that the pair works together, not
   compiled) Caveat: `netd_open` (`ncm_device.c:810`) does not check the interface class or
   subclass. It relies on the CDC driver, which sits earlier in the table and checks for the ACM
   subclass (`cdc_device.c:310`), to claim the ACM interface first. Keep that driver order.
   (verified in code)
4. **MAC address.** The example uses the constant `02:02:84:6A:96:00`. Two pads would collide. Derive
   it from the flash unique ID. (verified for the constant, `[L3]`; likely for the fix)

### (c) Wired Ethernet

1. W5500: hardwired TCP/IP, 8 sockets, SPI, 10/100 PHY, "Not supports IP Fragmentation". It draws
   128 mA on a 100M link and 132 mA transmitting, at 3.3 V. (verified, `[H8]`)
2. It adds an RJ45 jack with magnetics, a second cable, and a free switch port. The pad then takes
   its address from the LAN. Nothing is configured on the PC except the firewall.
3. It is the cleanest answer for OBS on another PC. It is the heaviest answer for OBS on the same PC:
   two cables to reach a program that sits at the other end of the first cable.

### (d) Host bridge

1. **(d1) Logic bridge, the current design.** The app holds the socket through `obws`. The pad gets
   display frames. The password stays in a `0600` file on the PC. `just test` passed on 2026-11-17.
   (verified in `[L5]`, not re-run) It does not honour the owner's sentence: the firmware never
   talks to OBS.
2. **(d2) Byte relay.** The firmware keeps the whole OBS client: WebSocket handshake, authentication,
   requests, events. A small host process opens the TCP socket and copies bytes to a second CDC-ACM
   port. No lwIP, no DHCP, no firewall rule, and OBS may be anywhere the PC can reach. The process
   must be running. It honours the sentence in part: the firmware speaks obs-websocket to that URL,
   but through the PC. (likely; a design, nothing built)

## The recommended design

1. **USB.** One composite device with an interface association descriptor: CDC-ACM for the framed
   configuration link that exists today, CDC-NCM for the network. Configuration stays on CDC-ACM so
   that it works while the network link is down or blocked.
2. **Addressing.** The pad takes a fixed private address and leases exactly one address to the PC.
   No router option, no DNS option, no HTTP server, no listening TCP port on the pad. The lease is
   the address the firmware dials.
3. **URL.** Store the URL as the owner typed it. A loopback host (`localhost`, `127.0.0.1`, `::1`)
   means "the PC on the other end of the cable" and resolves to the lease. Any other host is
   unreachable over the cable until the relay exists, and the display says so.
4. **Firewall, one sudo step at install.** For ufw: `sudo ufw allow proto tcp from <pad-address> to
   any port 4455`. It sits next to the udev rule that already needs root
   (`app/udev/70-macropad-obs.rules`). The app detects the blocked case (OBS answers on loopback, the
   pad reports a connect timeout) and shows this command. (rule form verified in `man ufw`; not run)
5. **Transport seam.** The OBS client talks to a four-call byte-stream interface: connect, send,
   receive, close. lwIP TCP implements it on the device. A POSIX socket implements it in native
   tests. The (d2) relay is a third implementation, added only when a need for it is shown.

Estimated new firmware: NCM and lwIP glue about 300 lines, WebSocket client about 500, OBS session
and JSON about 800. These are estimates, not measurements. obs-websocket also offers
`obswebsocket.msgpack`, which may be easier to parse than JSON on the device. (verified that it
exists, `[O4]`)

## Rule conflicts for the owner

1. **"No OBS password in a CDC frame" against a device that logs in by itself.** Three ways out:
   - **Amend the rule.** The password crosses once in a write-only configuration message and is
     stored in the pad's flash. The pad never sends it back. This is the only choice that lets the
     pad work with the app closed. Whoever holds the pad can read its flash. (likely)
   - **Keep the rule.** At each OBS start the pad sends the salt to the app, and the app answers
     with `base64(sha256(password + salt))`, valid until the obs-websocket server restarts
     (`Start()` makes a new salt). That secret is password-equivalent for that server run, so the
     owner must decide whether it also falls under the CDC rule. The app must be running each
     time OBS starts. Then (d2) gives the same result with less firmware.
   - **Turn OBS authentication off.** Not advised: OBS says "It is highly recommended to keep
     obs-websocket protected with a password". (verified, `[O5]`)
2. **Loopback and `wss://` policy.** `host/src/config.rs:215-216` refuses a non-loopback `ws://` URL.
   The pad is never on loopback and OBS has no TLS. That check cannot carry over. (verified, `[L5]`)
3. **The four-file protocol rule stays in force.** Configuration remains framed CDC, so `link.c`,
   `protocol.rs`, `vectors.txt` and `docs/protocol.md` still change together.

## What would change the recommendation

1. **OBS usually runs on another PC, or the pad sits away from the OBS PC.** Then choose Ethernet, or
   Wi-Fi on ESP32-S3-WROOM-1U with an external antenna.
2. **The owner will not accept a sudo step, or the hosts have no NetworkManager.** Then (d2) becomes
   the primary design.
3. **The password rule stays as written.** Then (d2) becomes the primary design.
4. **The spike fails.** NetworkManager does not bring the link up by itself, or CDC-ACM plus NCM is
   unstable on the chosen MCU. Then (d2).
5. **The MCU topic picks ESP32-S3 for other reasons.** Keep (b) as the primary path because of the
   metal case. Wi-Fi then costs an antenna path and a settings page, and can come later.

## Validation

The spike needs one RP2040 dev board and an ARM toolchain. The toolchain is not on this machine.

1. Build TinyUSB `net_lwip_webserver` for NCM with the router and DNS options off. Plug it in.
   Record whether NetworkManager activates a profile, how long it takes, and that `ip route` keeps
   its default route.
2. Enable the OBS server. Run `ss -ltn` and confirm the listener on port 4455 is a wildcard address.
3. Add a `tcp_connect` to the leased address, port 4455, and print the `Hello` message. Expect a
   timeout with ufw on, and `Hello` after the rule.
4. Add CDC-ACM to the descriptors. Confirm `/dev/ttyACM*` and the network interface both appear.

Tests that need no hardware:

1. The WebSocket client, the authentication string and the OBS session, compiled natively behind the
   transport seam with gcc ASan, against recorded transcripts and a fake transport with short reads
   and writes. This matches the repo's present firmware tests.
2. lwIP's unix port with `tapif` (`contrib/ports/unix`), inside `unshare -Urn`. Creating a tap device
   there without sudo works on this machine. (verified, `[L2]`; the lwIP build was not run)
3. The kernel's `dummy_hcd` and `usb_f_ncm` modules are installed, so the plug-in can be rehearsed
   with a software gadget. Loading them needs root. (verified present, `[L2]`; not run)

## Not checked

1. No hardware and no running OBS. NetworkManager's treatment of the pad's link and the listener
   address were not observed. Risk: the link needs a hand-made profile.
2. CDC-ACM plus NCM was not compiled for RP2040 (no `arm-none-eabi-gcc`). The files were read in SDK
   2.3.0 with TinyUSB 0.18.0. The repo's Dockerfile pins pico-sdk 2.1.1.
3. Windows and macOS hosts were ignored. The owner asked for a Linux app.
4. No power budget is totalled. The backlight currents belong to the display topic.
5. ESP32-S3 flash encryption as a place for the password, and simulators for the W5500, were not
   researched. (unverified)

## Sources

This machine and this repo:

- `[L1]` ufw: `systemctl is-active ufw` (active), `/etc/default/ufw` (`DEFAULT_INPUT_POLICY="DROP"`),
  `/etc/ufw/user.rules` (no user tuples), `/etc/ufw/before.rules:46`, `man ufw`
- `[L2]` `nmcli --version` (1.58.1), `/usr/lib/udev/rules.d/85-nm-unmanaged.rules`,
  `modinfo cdc_ncm` (alias `ic02isc0D`), `modinfo dummy_hcd usb_f_ncm`,
  `/usr/lib/systemd/network/99-default.link`,
  `pkaction --verbose --action-id org.freedesktop.NetworkManager.settings.modify.system`,
  `unshare -Urn sh -c 'ip tuntap add dev tap0 mode tap && ip addr add 192.168.7.2/24 dev tap0'`
- `[L3]` `~/.platformio/packages/framework-arduinopico/pico-sdk/` (SDK 2.3.0):
  `lib/tinyusb/src/class/net/ncm_device.c`, `ncm.h`, `lib/tinyusb/src/device/usbd.c`,
  `lib/tinyusb/lib/networking/dhserver.c:197-224`,
  `lib/tinyusb/examples/device/net_lwip_webserver/src/`, `lib/lwip/src/apps/`, `lib/mbedtls/`,
  `src/rp2040/hardware_structs/include/hardware/structs/usb_dpram.h:23`
- `[L4]` `flatpak list`, `flatpak info --show-permissions com.obsproject.Studio`,
  `~/.var/app/com.obsproject.Studio/config/obs-studio/plugin_config/obs-websocket/config.json`
- `[L5]` `docs/design.md:14`, `:680-682`, `docs/obs.md`, `docs/protocol.md`,
  `host/src/config.rs:207-216`, `app/udev/70-macropad-obs.rules`, `docs/research/02-repo-inventory.md`

obs-websocket, master at `e28f849` (2026-10-08):

- `[O1]` <https://raw.githubusercontent.com/obsproject/obs-websocket/master/src/websocketserver/WebSocketServer.cpp>
- `[O2]` <https://raw.githubusercontent.com/obsproject/obs-websocket/master/src/websocketserver/WebSocketServer.h>
  and <https://raw.githubusercontent.com/obsproject/obs-websocket/master/src/Config.h>
- `[O3]` <https://raw.githubusercontent.com/zaphoyd/websocketpp/master/websocketpp/transport/asio/endpoint.hpp>
- `[O4]` <https://raw.githubusercontent.com/obsproject/obs-websocket/master/docs/generated/protocol.md>
- `[O5]` <https://raw.githubusercontent.com/obsproject/obs-websocket/master/README.md>

Linux networking:

- `[N1]` <https://networkmanager.dev/docs/api/latest/NetworkManager.conf.html> (`no-auto-default`)
- `[N2]` <https://networkmanager.dev/docs/api/latest/settings-ipv4.html> (`method`)
- `[N3]` <https://www.freedesktop.org/software/systemd/man/latest/systemd.network.html> (`Unmanaged=`)
- `[N4]` <https://raw.githubusercontent.com/firewalld/firewalld/main/config/zones/public.xml>
- `[N5]` <https://fedoramagazine.org/control-the-firewall-at-the-command-line/> (weak, via search)

Antennas and radio parts:

- `[H1]` Infineon AN91445, section 12:
  <https://www.infineon.com/dgdl/Infineon-AN91445_Antenna_Design_and_RF_Layout_Guidelines-ApplicationNotes-v09_00-EN.pdf?fileId=8ac78c8c7cdc391c017d073e054f6227>
- `[H2]` ESP32-S3 datasheet v2.2, Table 5-7 and section 4.2.1.7:
  <https://documentation.espressif.com/esp32-s3_datasheet_en.pdf>
- `[H3]` ESP32-S3-WROOM-1 and 1U datasheet v1.8, sections 1 and 10.2:
  <https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf>
- `[H4]` Raspberry Pi Radio Module 2 product brief, September 2025:
  <https://datasheets.raspberrypi.com/rm2/rm2-product-brief.pdf>
- `[H5]` <https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html>

Vendor software and Ethernet:

- `[H6]` <https://docs.espressif.com/projects/esp-protocols/esp_websocket_client/docs/latest/index.html>
- `[H7]` <https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_device.html>
- `[H8]` W5500 datasheet v1.1.0, Features and section 5.4:
  <https://docs.wiznet.io/img/products/w5500/W5500_ds_v110e.pdf>

## Open questions

1. Does the owner amend "No OBS password in a CDC frame" so the pad can store the password, or keep
   it and accept the app at every OBS start?
2. Is OBS on another PC a real use for this pad? If yes: the relay through the app, Ethernet, or a
   radio with an antenna on the case?
3. Is one sudo step at install acceptable (the firewall rule, plus a `.network` file on hosts
   without NetworkManager)?
4. Which MCU carries this: RP2040 with the Pico SDK, or ESP32-S3? Both can do NCM. Only the second
   keeps Wi-Fi open without a second module. This belongs to the MCU topic.
5. Which private subnet does the pad use, and may the app change it when it collides with the
   owner's LAN? The TinyUSB example's 192.168.7.0/24 is a common choice and a likely collision.

## Verification

Skeptic pass, 2026-11-18. Each claim was re-checked in the primary source named, opened today.
Verdict: **corrected**. One fact was wrong (polkit prompt); two caveats were added. The
recommendation stands.

| # | Claim | Source opened | Result |
| --- | --- | --- | --- |
| 1 | obs-websocket binds `tcp::v6()` on all interfaces; `--websocket_ipv4_only` gives v4 | `WebSocketServer.cpp:103-112`, `Config.cpp` flag handling, websocketpp `endpoint.hpp:520-538` (obs-websocket master `e28f849`, 2026-10-08) | Holds. Added the IPv4 fallback and `bindv6only = 0` on this PC. |
| 2 | `onValidate` does not filter the remote address | `WebSocketServer.cpp:204-216` | Holds. It only picks `obswebsocket.json` or `obswebsocket.msgpack` and returns `true`. |
| 3 | Defaults: disabled, port 4455, auth on, IPv4-only off; no bind-address field | `Config.h:36-43` | Holds. |
| 4 | Salt made in `Start()`, challenge per session; auth string formula | `WebSocketServer.cpp:85-86`, `:254-258`; `docs/generated/protocol.md:101-104` | Holds. Added that the per-run secret is password-equivalent. |
| 5 | No TLS in OBS | `WebSocketServer.h:27`, `:93` (`asio_no_tls.hpp`, `config::asio`) | Holds. |
| 6 | Owner's OBS: Flatpak 33.0.1, `shared=network`, server disabled, auth on | `flatpak list`, `flatpak info --show-permissions`, obs-websocket `config.json` (password key not printed) | Holds (`shared=ipc;network;`). |
| 7 | ufw active, input DROP, no user rules, DHCP reply accepted at `before.rules:46` | `systemctl`, `/etc/default/ufw`, `user.rules` and `user6.rules` (0 tuples each), `before.rules:45-46` | Holds. |
| 8 | Host `cdc_ncm` matches class 02 subclass 0D; NM 1.58.1 active, networkd inactive; NM unmanaged list | `modinfo cdc_ncm` (generic alias `usb:v*p*...ic02isc0Dip00in*`), `nmcli --version`, `systemctl is-active systemd-networkd`, `85-nm-unmanaged.rules` | Holds. The alias also requires protocol 00. |
| 9 | Changing a system NM connection needs an admin prompt on this PC | `pkaction`, `/usr/share/polkit-1/rules.d/org.freedesktop.NetworkManager.rules`, `id -nG` | **Wrong.** The rule returns `YES` for local `wheel` members; the owner is in `wheel`. Corrected in (b) item 5. |
| 10 | TinyUSB `dhserver.c` sends router and DNS only when non-zero; example uses `NO_SYS 1`, 192.168.7.1, MAC `02:02:84:6A:96:00` | `dhserver.c:197-224`, example `main.c:72-91`, `lwipopts.h:36` | Holds. Note the example sets `.dns = 192.168.7.1` and runs a DNS server, so "send neither" is a change to the example. |
| 11 | SDK 2.3.0, TinyUSB 0.18.0, lwIP 2.2.1, no WebSocket client in lwIP apps | `pico_sdk_version.cmake`, `tusb_option.h:33-35`, `lwip/init.h:53-57`, `ls lib/lwip/src/apps` | Holds. |
| 12 | RP2040 16 endpoints; CDC and NET are separate driver entries; NCM example has one configuration, ECM/RNDIS two | `usb_dpram.h:23`, `usbd.c:157`, `:287`, example `usb_descriptors.c:60-65`, `:144-180` | Holds. Added the `netd_open` class-check caveat (`ncm_device.c:810`). |
| 13 | ESP32-S3: 340 mA TX peak (802.11b 1 Mbps 21 dBm), 88 mA RX | ESP32-S3 datasheet v2.2, Table 5-7 | Holds. |
| 14 | WROOM-1U external connector, U.FL compatible | ESP32-S3-WROOM-1/1U datasheet, section 10.2 | Holds. |
| 15 | RM2: on-board antenna, 271 mA TX, 43 mA RX | RM2 product brief | Holds. |
| 16 | W5500: 128 mA 100M link, 132 mA TX, no IP fragmentation | W5500 datasheet v1.1.0, Features and 5.4 | Holds. |
| 17 | Antenna quotes: "must not be covered by a metallic enclosure completely"; "at least 15 mm ... in all directions" | AN91445 PDF text; Espressif ESP32-S3 PCB layout guide | Holds. |
| 18 | NM creates a temporary wired connection for a managed Ethernet device | NetworkManager.conf `no-auto-default` | Holds. |
| 19 | firewalld `public` zone: `ssh`, `dhcpv6-client` only | firewalld `config/zones/public.xml` (main) | Holds. |
| 20 | Repo: Wi-Fi rejected at `docs/design.md:680-682`; `config.rs` refuses non-loopback `ws://` | Files read | Holds. In code: with `allow_non_loopback` set, `ws://` is refused (`config.rs:215-216`). |

Against the owner's words. "firmware on the device should be communicating with this websocket OBS
url": (b) does this for OBS on the same PC. A URL naming another host does not work over (b)
without the relay or NM sharing; the report says so. "pass websocket url" and "bidirectional
configuration" ride the CDC-ACM link and are unaffected. The sketch and the no-battery reading do
not conflict with a single USB cable. The password rule conflict is real and stays an owner
decision.

Not checked in this pass: NM behaviour on a real NCM plug-in, TinyUSB CDC-ACM plus NCM compiled for
RP2040, esp_websocket_client subprotocol detail beyond the section heading, Fedora zone `[N5]`.
