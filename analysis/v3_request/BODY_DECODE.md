# V3 RegistrationRequest -- AzCore body decode

832-byte body after the 11 B data-channel record header
(`HEADER_DECODE.md`). All 10 retries share this body byte-for-byte.
Anchor: retry 2 of `all_v3_request_retries.hex`.

## Top-level shape

```
[0x000..0x021]  prelude (33 B): type-id + AzCore class metadata
[0x021..0x15D]  12 length-prefixed AZStd::string elements with 1-31 B
                of inter-field framing between them
[0x15D..0x334]  Steam-auth blob (471 B): ticket + JWT (?), internal
                framing not fully reversed
[0x334..0x340]  trailer: `00 43 02 80` + 8 zero pad
```

## First 80 B byte-by-byte

```
off  bytes                                interpretation
000  21 03 c5 00 01 00                     prelude (unknown 6B)
006  80 3c 89 54 c1 00 00 03               u64 / handle
00e  bd 0c 00 09 02 00                     unknown sub-header
014  f0 0e 01 13 97 0c 0a 5d               CRC32-shaped
01c  06 00 00 00 04                        tag(?) + 3 zero pad + len
021  04 36 30 33 31                        STR len=4: "6031"
026  00 00 00 03                           gap (4B)
02a  03 34 30 30                           STR len=3: "400"
02e  00 00 00 02 01 0e 00 f0 05 01         gap (10B)
038  07 4a 61 76 65 6c 69 6e               STR len=7: "Javelin"
040  00 00 00 05                           gap (4B)
044  07 36 30 30 34 31 35 18               STR len=7: "600415\x18"
04c  00 f0 3f 00                           gap (4B)
050  08 5b 52 45 54 41 49 4c 5d            STR len=8: "[RETAIL]"
```

## All visible strings (anchored by content)

| Off   | Len | Field (best guess)                                       |
|-------|----:|----------------------------------------------------------|
| 0x021 |   4 | `6031` -- game build version                             |
| 0x02a |   3 | `400` -- unknown small int (branch? region?)             |
| 0x038 |   7 | `Javelin` -- SDK / network library tag                   |
| 0x044 |   7 | `600415` + `0x18` -- Javelin version + sub-byte          |
| 0x050 |   8 | `[RETAIL]` -- build flavor                               |
| 0x05a |  40 | `sig:fb79c7c4-3416-4158-bda8-7a11e6e27eb8` -- client sig |
| 0x083 |  15 | `127.0.0.1:23971` -- local client endpoint               |
| 0x0a8 |  36 | `4760baff-f4af-49ee-8875-3e0103c74b07` -- session UUID   |
| 0x0cd |  61 | `amzn1.developerPersonaId.4ee4810f-...-91e961054dce`     |
| 0x110 |  20 | `STEAM_APP_ID.1063730` -- platform/app key               |
| 0x144 |  17 | `76561198069524636` -- Steam SteamID64                   |
| 0x157 |   8 | len `0x08`, data `steam|14` -- name + spill into blob    |

The `worldId` UUID `b1a00000-...-000000000002` does **NOT appear
contiguously**. Literal `b1a00000-` sits at 0x95 followed by 11 B of
binary (`06 00 0b 05 00 03 02 00 ff 70 32`), not the expected 27 B
continuation. Either it's binary-encoded after the prefix, or gateway
login doesn't carry it (character-select happens later). The 21 B
region is preserved as `unknown_worldid_region`.

## Steam auth blob (0x15d..0x334, 471 B)

Begins `7c 31 34 e9 00` (`|14` then binary). Length-byte tags seen:
`f0/f1/f2 / a2 / 88 / 91 / a4 / c4 / af / e9`. Visible ASCII fragments:

`steam|14...` -> `d64f942e5a3c` -> `40989c288306010` -> `2bdbf869180` ->
`08c529a63672102f1c5e0d60003` -> `0005` -> `323b1000bc05ed184a00a8c2` ->
`6ff9f469efa8106a` -> `Pde5d0X` -> `600b05112+` -> `70b1` -> `E707d` ->
`C8f42` -> `C3e3c` -> `d3f783be9361e32859e8b1622bea2ab7f5` ->
`062b079b324556a9f1732607d3eba656206e3` -> 163 B hex tail
`48b54726aeb31e0067...c9895b7e7fac9722e`.

`Pde5d0X` / `E707d` / `C8f42` have uppercase letters that break the
"pure hex" hypothesis -- looks more like an **EOS / Steam
EAuthSessionTicket** hex-encoded with embedded 1-byte length markers
between sub-fields. Round-tripped verbatim as `auth_blob: bytes`.

## Tag conventions observed

`AZStd::string < 256 chars` IS `[u8 length][bytes]` -- holds for every
visible string. No `>= 256` examples in this body, so long-string
encoding is unverified.

Inter-field framing is NOT a clean per-element tag. Repeating
`00 00 00 NN` quartets early on look like BE u32 sequence indices.
`f0 0e 01 13 97 0c 0a 5d` near the start is CRC32-shaped, possibly an
`AZ_CRC` of the class type name (unvalidated). Inside the auth blob,
`0xf0..0xf2 / 0xa2 / 0x88 / 0x91 / 0xa4 / 0xc4 / 0xaf` all have the
high bit set -- consistent with GridMate's VLQ "1's prefix"
(`docs/gridmate-reference.md` §5.7) but lengths don't always equal the
following ASCII-run length, so a type bit must share the high nibble.

## Trailer: `00 43 02 80 00 00 00 00 00 00 00 00`

- `00` -- last-element terminator (zero-length string)
- `43 02 80` -- class-close marker; `0x80` = AzCore high-bit
  end-of-element tag
- 8 B zeros -- alignment pad to 8-byte boundary

Identical trailer expected on `RegistrationResponseMsg`
(see `server/javelin/v3_response.py`).

## Honest unknowns

- Type-id GUID in the prelude. `21 03 c5 00 01 00` doesn't match
  `RegistrationRequestV3Msg` GUID `0B826B33-89F5-49E0-B8CB-FE4433427778`
  in any obvious byte order.
- Semantics of inter-field gaps (`00 00 00 NN` quartets, `f0 NN 01`).
- High-bit tag family (`0x88..0xf2`) inside the auth blob.
- What `400` and `0x18` after `600415` mean.
- Whether the worldId is encoded in this packet at all.
