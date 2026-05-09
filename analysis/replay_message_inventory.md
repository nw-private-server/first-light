# Replay-message wire-format inventory

> Byte-level analysis of message types in the existing capture
> `info/nw-login-safe-20260502-153840/messages-redacted.txt`. Compiled
> from a fresh frequency survey + per-type byte comparison in worklog
> wake 66 (2026-05-08).
>
> **Scope**: this file documents what we can recover from byte
> patterns alone (variant analysis across multiple captured messages
> of the same type, structural shape, shared identity fields).
> Handler-side semantic decode (parameter access patterns from the
> binary's deserializer/handler) is documented separately in
> `clientmessagestrait_wire_formats.md` for the two ClientMessagesTrait
> messages that reach static-RE.
>
> **All bodies are length-prefixed by a 4-byte typed envelope header**:
> `[0x00, 0x01, (type & 0x3F) | 0x80, (type >> 6) & 0xFF]`. The
> "payload" sizes below exclude this 4-byte header.

## Replay frequency table

177 messages total in the capture (seq 0x0..0xb0). Top types by
frequency:

| Type | Count | Body sizes | Direction | Notes |
|---|---|---|---|---|
| `0x08` | 79 | 78..46423 (variable) | R | Continuous entity-state stream (Phase 17). Variable size. |
| `0x1b88` | 23 | 42 (fixed) | R | **Identical bytes across all 23.** Looks like a periodic identity beacon. See below. |
| `0x15d` | 20 | 12 or 36 | RW | Bidirectional. Variable. |
| `0x635` | 5 | 93..153 | W | Client-side. |
| `0x14f` | 4 | 12 (fixed) | R | Periodic — payload contains a session-clock prefix shared with V3 response's `mystery8`. See below. |
| `0x18a6` | 4 | 40 (fixed) | R | Each message identical except a trailing 1-byte counter. See below. |
| `0x5b2` | 4 | 45 or 93 | W | Client-side. |
| `0x1a59` | 3 | 45 (fixed) | W | Client-side. |
| `0xa4` | 2 | 20 (fixed) | R | Phase 5 SESSION small per `docs/post-v3-sequence.md`. See below. |
| `0x663` | 2 | 110 (fixed) | R | |
| `0x16a0` | 2 | 153 or 99819 | R | One small + one ~98KB chunk. |
| various | 1 each | various | R/W | Singletons; less useful for variant analysis. |

## Shared 16-byte identity field (recurring across `0x1b88`, `0xa4`, `0x18a6`)

The same 16-byte sequence (or a permutation of it) appears in all
three message types. Bytes (in canonical order from the `0xa4` body):

```
1a 95 4a bc 4b 31 85 bf be 37 c3 d8 59 26 18 e0
```

This is **almost certainly a UUID** (16 raw bytes, displayed mixed-
endian per Microsoft's GUID convention or raw per RFC 4122).

| Type | Where it appears in the payload |
|---|---|
| `0xa4` | bytes 0..15 of payload (whole payload after 4-byte type header) |
| `0x1b88` | bytes 0..15 of payload, with 22 zero bytes following |
| `0x18a6` | bytes 0..15 of payload, in **reversed-half order** — first 8 bytes are `f8 cb ed 57 c6 8b 18 f4` (different UUID half), then `bf 85 31 4b bc 4a 95 1a` (same lower half as `0xa4` but reversed within itself) |

**Interpretation**: this UUID is probably the **session UUID** the
server assigns at registration. It gets echoed in:

- `0xa4` (Phase 5 SESSION) as a "session-id confirmation" beacon
- `0x1b88` (periodic identity) every few seconds
- `0x18a6` (Phase 11-ish init) bundled with another UUID half

## `0x14f` — 12-byte session-clock beacon (4 occurrences)

| Seq | Bytes |
|---|---|
| `0xa`  | `00 01 8f 05  0b 88 8d 68  7b 13 00 1a` |
| `0x27` | `00 01 8f 05  0b 88 8d 68  81 41 ab b4` |
| `0x3c` | `00 01 8f 05  0b 88 8d 69  36 5c c1 e0` |
| `0x54` | `00 01 8f 05  0b 88 8d 69  e9 2f 11 ff` |

**Payload layout (8 bytes after type header):**

```
+0x00  u32 BE  session_clock     (0x0b888d68 → 0x0b888d69 between seq 0x3c)
+0x04  u32     nonce / hash      (random-looking, distinct each msg)
```

**Big finding — links to V3 response `mystery8`:**

`server/javelin/v3_response.py` carries a hardcoded `mystery8` field
captured from this same session:

```python
DEFAULT_MYSTERY8 = bytes.fromhex("0b888d68706c415b")
```

The first 4 bytes (`0b 88 8d 68`) are **exactly** the `0x14f`
session-clock value at seq 0xa. So `mystery8`'s first 4 bytes are a
session-clock value the server starts at registration; the next 4
bytes (`70 6c 41 5b` in this capture) are likely a per-session nonce.

This means the V3 response's `mystery8` is no longer a complete
mystery: bytes 0..3 are a session clock that increments slowly
(monotonically non-decreasing across the session), and bytes 4..7
are a per-session nonce/hash. Server-side encoder can be updated:

- `mystery8[0..4]` = `int(session_start_time_or_session_clock).to_bytes(4, "big")`
- `mystery8[4..8]` = `os.urandom(4)` or a deterministic stub

## `0x18a6` — 40-byte init beacon with 1-byte counter (4 occurrences)

All 4 messages are identical except the final byte, which increments
1 → 2 → 3 → 4. Layout:

```
+0x00  u8x8   first UUID half        f8 cb ed 57 c6 8b 18 f4
+0x08  u8x8   shared session UUID    bf 85 31 4b bc 4a 95 1a
                                      (matches the lower half of the 0xa4 UUID)
+0x10  u8x4   flags                  01 01 00 00
+0x14  u8x8   second UUID/hash       9c fa 58 61 78 14 69 f2
+0x1c  u32 LE build version         65 03 00 00 = 0x365 = **869** —
                                      matches the docs' game version
                                      "[RETAIL].Javelin.1.365.…"
+0x20  u8x3   reserved/padding       00 00 02
+0x23  u8     counter                01 / 02 / 03 / 04 across the 4 messages
```

Total: 36 bytes payload.

**Server-side implication**: each of these matters for replay
fidelity:

- The first UUID half + shared session UUID identify the session
- The build version 0x365 must match the running game version
- The counter increments per "init beacon round" — if the server
  re-sends to the same client, this should restart at 1 or
  continue monotonically depending on client expectations.

## `0x1b88` — 42-byte session-identity beacon (23 occurrences, ALL identical)

```
+0x00  u8x16  shared session UUID    e2 64 0b 7c e5 40 80 36
                                      bf 85 31 4b bc 4a 95 1a
+0x10  u8x22  zero padding           all 00 bytes
```

The session UUID's lower 8 bytes (`bf 85 31 4b bc 4a 95 1a`) match
the same lower 8 we see in `0xa4` and `0x18a6`. The upper 8 bytes
(`e2 64 0b 7c e5 40 80 36`) are different from `0xa4`'s upper half
(`1a 95 4a bc 4b 31 85 bf` — which is itself a reversed copy) and
from `0x18a6`'s upper half. Three different 16-byte values share a
common 8-byte lower half.

Possible interpretation: **the lower 8 bytes are a shared
"connection family" identifier** (server cluster ID, region UUID,
etc.) and the upper 8 bytes are session-specific. We can't fully
disambiguate without additional captures.

For an encoder: send a fixed 42-byte payload with the connection's
session UUID at +0x00 and 22 zero bytes filler. The 23 identical
copies in the replay suggest this is a **periodic re-broadcast** of
the same session identity (a "yes I'm still here" message).

## `0xa4` — 20-byte SESSION small (2 occurrences, identical)

Per `docs/post-v3-sequence.md` Phase 5 — "INIT 0x91(0x19) + small
0xa4". The 0xa4 here is the small session message:

```
+0x00  u8x16  shared session UUID    1a 95 4a bc 4b 31 85 bf
                                      be 37 c3 d8 59 26 18 e0
```

Total 16 bytes payload. Just the UUID, no padding, no flags.

## Why this matters

For each of these types, the project now has enough byte-level
characterization to:

1. **Build a skeleton encoder** that produces matching wire bytes
   for replay — set the session UUID, set the build version, fill
   counters and clock fields.
2. **Validate the V3 response's `mystery8` semantically** — bytes
   0..3 are a session clock matching `0x14f` payload bytes 0..3.
3. **Cross-check captured-vs-live byte streams field-by-field** in
   future runtime sessions.

The remaining unknowns (handler addresses, the deserializer layout
for the type IDs above, the exact meaning of `0x18a6`'s `01 01 00 00`
flag word and `02` byte before the counter) need either more captures
to vary against, or static-RE on the binary's dispatch table — the
latter being blocked at the moment per wake 59.

## Next message types worth a similar pass

- `0x15d` (20 occurrences, 12 or 36 bytes, RW) — bidirectional, two
  size classes; probably a small request/response or two distinct
  variants under one type-id.
- `0x635` (5 W, 93..153 bytes) — client-side, variable size; likely
  request encoding worth comparing across multiple captures.
- `0x663` (2 R, 110 bytes fixed) — small enough to characterize.
- `0x40a`, `0x1be` (1 each, 76 bytes) — singletons; not great for
  variant analysis but useful as known wire-shape entries.

Adding these to the inventory needs comparable variant data;
ideally another capture or two from different sessions.
