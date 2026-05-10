# Wire-type 0x1033 — structural investigation

## Capture profile

- **Direction**: R (server → client)
- **Captures**: 1
- **Body size**: 498 bytes
- **Replay seq**: 0x62
- **Has redaction**: no

## Confirmed layout

```
+0x00..0x03  type header   00 01 b3 40
                            (0x1033 → byte2=(0x33|0x80)=0xb3, byte3=(0x1033>>6)=0x40)
+0x04..0x0b  sub_system_id              ce 81 13 6a 2b 7a d3 3e
+0x0c..0x13  session_uuid_lower         bf 85 31 4b bc 4a 95 1a
+0x14..0x1f1 opaque payload (478 bytes)
```

The first 20 bytes match the project-standard identity-bundle
prefix (wake 78, see codec library). `session_uuid_lower` is
identical to the value we see in the captured `0x1096` body
(wake 101) and other identity-bundle messages in the same
session — confirming both messages belong to the same session.

## Why no structural codec beyond "opaque tail"

478 bytes of payload, 478 mod 4 = 2 (no clean 4-byte grid).
Visual analysis of the 478 bytes shows:

- **No recognizable floats** (no IEEE-754 bit patterns at any
  4-byte offset that match common values like `40c00000`/6.0,
  `bf800000`/-1.0, or the 1/6, 5/6 ratios that surfaced in 0x1096)
- **No 32-bit duration constants** (no occurrences of e.g.
  `00000e10`/3600 or `00000708`/1800)
- **No long zero runs** (which would indicate sparse fields or
  reserved zero-pads — common in the project's other codecs)
- **High byte entropy** with no obvious periodicities
- **No discernible substring boundaries** that would split the
  blob into named records

This is the byte profile of either:

1. **Encrypted or signed material**. The blob is likely a single
   crypto blob — for example, a signed authorization token, a
   key-exchange envelope, or AES-encrypted state.
2. **Compressed material**. Less likely — at 478 bytes a Zstd or
   Deflate envelope would still expose the magic bytes
   (`28 b5 2f fd` for Zstd, `78 9c`/`78 da` for Deflate); none
   appear at the start.

Without either a second capture (to compare for structural
commonalities) or runtime context (the binary code that emits
this message would name its components), guessing at sub-fields
inside the 478 bytes would be speculation.

## Codec status

`server/javelin/opaque_blob_1033.py` exposes:

- `OpaqueBlob1033(sub_system_id, session_uuid_lower, opaque)`
- `encode()` / `decode()` round-trip the captured body bytes-for-
  bytes, asserting the type header and minimum-size invariants.
- The codec deliberately accepts variable opaque-tail lengths —
  one capture is not enough to claim the size is fixed at 478
  bytes.

This brings captured-type codec coverage to **39/40**. The only
remaining gap is `0x08` (the high-volume chunked stream — 79
captures, sizes 78 B – 46 KB).

## What would unblock a richer 0x1033 codec

Any of the following:

1. **A second capture** of `0x1033` from a different session.
   Comparing the two opaque tails byte-for-byte will reveal
   whether (a) every byte differs (per-session random, likely
   encrypted), or (b) the first N bytes match (a fixed-length
   header before the encrypted body — that header would then
   be structurally codec-able).
2. **Runtime trace** of the function that emits this type. The
   typeIndex 0x1033 corresponds to a registered AZ::TypeInfo
   entry in the binary; a Frida hook on
   `AZ::SerializeContext::Register<T>()` would yield the type
   name and then the message struct fields are usually named
   in the binary (see `analysis/typename_unblock_spec.md`).
3. **Static-RE on the type's CreateInstance fingerprint** in
   `info/typeregistry.json`. Wakes 93-97 attempted this
   methodology against other types; depending on this type's
   handler-fingerprint xref count, it may or may not be
   tractable.

Until then, the opaque-blob codec covers the type at the
identity-bundle level — sufficient for replay round-trip,
insufficient for emulation.
