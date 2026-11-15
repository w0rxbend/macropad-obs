# CDC frames

Version 1. Transport is USB CDC ACM, VID `0x1209`, PID `0x4F42`. Baud is ignored. Byte order is little-endian. Text is printable ASCII (`0x20`-`0x7E`). Any other byte is stored as `?`.

```text
0        SOF          0xA5
1        version      0x01
2        type         u8
3..4     length       u16, payload bytes, 0..240
5..      payload      length bytes
end-2    crc          CRC-16/MODBUS, low byte first
```

CRC-16/MODBUS: reflected poly `0xA001`, init `0xFFFF`, xorout `0x0000`, over version through the end of the payload. Not over SOF. ASCII `123456789` → `0x4B37`.

`KEY` index 3 down, CRC `0x82B8`:

```text
a5 01 02 02 00 03 01 b8 82
```

The parser scans for `0xA5`. A bad version, a length above 240, or a bad CRC drops one byte. An unknown type with a good CRC is dropped and counted. The link does not reset.

## Pad to host

| Type | Name | Payload |
|---|---|---|
| `0x01` | HELLO | `u8 proto`, `u8 keys=9`, `u16 features` (0 in v1) |
| `0x02` | KEY | `u8 index 0..8`, `u8 down` (1 pressed, 0 released) |
| `0x03` | KNOB | `i8 detents`, sent when the count is non-zero |
| `0x04` | PAGE | `i8 delta` (`+1` short push, `-1` long push) |

## Host to pad

| Type | Name | Payload |
|---|---|---|
| `0x10` | HELLO_ACK | `u8 proto` |
| `0x11` | HEARTBEAT | empty. The host sends one every 1 s |
| `0x12` | BIND | `u8 state`, `u16 port`, `u8 host_len`, host bytes (1..48). State: 0 down, 1 connecting, 2 auth failed, 3 connected, 4 connected non-loopback |
| `0x13` | PROFILE | `u8 len`, name bytes, 1..24 |
| `0x14` | PAGE_VIEW | `u8 page`, `u8 page_count`, `u8 flags`, then 9 times (`u8 slot_flags`, `u8 len`, 0..16 name bytes) |
| `0x15` | INPUT | `i8 db` (-100..26), `u8 muted`, `u8 len`, name bytes 0..24 |
| `0x16` | NOTICE | `u8 len`, text 0..32. The pad shows it for 1 s, then restores BIND |

`PAGE_VIEW` flags: bit0 studio, bit1 streaming, bit2 recording. Slot flags: bit0 occupied, bit1 program scene.

BIND carries host and port only. There is no password, path, or userinfo field. `firmware/test/vectors.txt` and the Rust tests reject a frame that contains a sample password.

`PAGE_VIEW` name bytes are at most 16. The glass draws them as two lines of at most 10 glyphs and does not draw a 17th byte. A name longer than 16 bytes is cut to 15 bytes plus `.` before it enters the frame.

BIND host bytes are at most 48. The status row draws at most 21 glyphs of `host:port` (168 px), then one space (8 px), then `REC` and `LIVE` adjacent (`RECLIVE`, 56 px). `168 + 8 + 24 + 32 = 232`. A longer host:port keeps 20 glyphs and a trailing `.`.

## Session

A session starts at USB configuration and again on every DTR rise (0 to 1). The pad clears the acked flag and sends HELLO within 100 ms, then every 1 s until `HELLO_ACK`. Until that ACK, every host frame except `HELLO_ACK` is rejected. A second ACK after the flag is set is an ordinary frame.

The shell asserts DTR on open, waits up to 2 s for HELLO, sends `HELLO_ACK`, then starts the 1 s heartbeat. A HELLO with `proto != 1` is refused. On websocket close the shell sends BIND state 0. Three missed heartbeats (3 s) set the status bar to `NO LINK` and keep the last page text.

`vectors.txt` names `page_view_empty`. After `link_session_reset` and before `HELLO_ACK`, that frame is rejected.
