# V3 RegistrationRequest Header Decode

`analysis/v3_request/all_v3_request_retries.hex`: line 1 first attempt (848 B),
lines 2-10 retries (843 B). Body after header is the SAME 832 B in every line.

## Retry header (11 B): `e0 20 00 02 03 00 XX ff ff 20 06`

| Off | Hex   | Field                                              |
|-----|-------|----------------------------------------------------|
| 0   | `e0`  | flags = `MF_CONNECTING(0x80) | 0x40 | MF_DATA_CHANNEL(0x20)` |
| 1-3 | `20 00 02` | sub-header: `[stream-flag=0x20][msg-class BE=0x0002]` |
| 4   | `03`  | ChannelID = 3 (sysmsg) |
| 5-6 | `00 XX` | InboundAck u16 BE; XX varies +9 per retry (0x0e..0x56) |
| 7-8 | `ff ff` | RelSeqAck u16 BE sentinel ("no rel ack")           |
| 9   | `20`  | inner-record / msg-class flag (unknown)             |
| 10  | `06`  | msgID = 6 (likely `SM_REGISTRATION_REQUEST_V3`; matches msgID family 6/7 in `FUN_140f80770`) |
| 11+ | ...   | 832 B AzCore-serialized body                        |

## First-attempt header (16 B): `f0 03 20 00 06 03 00 05 ff ff 40 00 03 00 02 06`

Same shape plus a 5 B CONNECT-INIT extension when bit `0x10` is set:

| Off  | Hex          | Field                          |
|------|--------------|--------------------------------|
| 0    | `f0`         | flags `0x80|0x40|0x20|0x10`    |
| 1-4  | `03 20 00 06`| sub-header (4 B vs 3)          |
| 5    | `03`         | ChannelID = 3                  |
| 6-7  | `00 05`      | InboundAck = 5                 |
| 8-9  | `ff ff`      | RelSeqAck sentinel             |
| 10-14| `40 00 03 00 02` | CONNECT-INIT blob          |
| 15   | `06`         | msgID = 6                      |

## `0x40` bit hypothesis

Likely `MF_HAS_MSGID_IN_HEADER` / `MF_HANDSHAKE_RECORD`. When set, last header
byte is msgID and body length is IMPLICIT (UDP remainder), instead of sysmsg
form (`length=u16` at 1-2, `msgid=payload[-1]`). Set in every record.

## Size encoding -- there isn't one

Every reading of bytes 1-2 fails:

| Reading         | Value | Verdict     |
|-----------------|-------|-------------|
| u16 BE bytes    | 8192  | too big     |
| u16 BE bits     | 1024  | too big     |
| u16 LE          | 32    | too small   |
| LEB128 / top-bit| 32    | too small   |
| flag low 5 bits | 0     | doesn't fit |

11 B header + 832 B body = 843 B = full datagram. When `0x40` is set, length
is IMPLICIT. Bytes 1-3 are sub-header, not length. Parser should branch on
`flags & 0x40` and skip the u16-length read.

## Trailing `00 43 02 80 00 00 00 00 00 00 00 00`

Not a second record. As a header: flag `0x00`, length `0x4302` BE / `0x0243`
LE, both larger than the 9 B left. So decode-as-record fails.

This 12 B tail is AzCore SerializeContext close: `0x00` = element terminator;
`0x43 0x02 0x80` = class-close marker (`0x80` = AzCore end-of-element high-bit
tag); eight `0x00` = 8-byte alignment padding. The full 832 B is one
AzCore-serialized `RegistrationRequestV3Msg` plus its close block.

## The 5-byte difference

Pre-`ff ff`: first 8 B, retry 7 -> +1 B before ChannelID. Post-`ff ff` before
msgID: first has `40 00 03 00 02` (5 B), retry has `20` (1 B) -> +4 B. Total
+5 B = CONNECT-INIT blob only in attempt 1.

Flag delta is exactly bit `0x10` -- so here `0x10` is NOT
`MF_SEQUENTIAL_REL_ID`; it is `MF_FIRST_CONNECT_ATTEMPT` /
`MF_HAS_INIT_OPTIONS`. Blob reads as `[option-tag 0x4000][version 3.0.2]`,
unconfirmed.

## Unknowns

- Semantics of sub-header bytes 1-3 and byte 9.
- Why InboundAck increments by 9 per retry (likely intervening inbound packets
  being acknowledged).
- Whether `0x40` means more than "implicit length / msgID in header".
