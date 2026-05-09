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

## `0x1a59` — 45-byte W session-subkey beacon (3 occurrences)

All 3 messages 45 bytes, share the same W-direction envelope
shape: `[client_hash:4][len_BE:4][session_uuid:16][type_hdr:4]
[payload]`. The payload (17 bytes) is:

```
+0x00  u8x16  subkey            f8 cb ed 57 c6 8b 18 f4
                                bf 85 31 4b bc 4a 95 1a
+0x10  u8     counter           02 / 03 / 04 across 3 captures
```

The 16-byte subkey is **byte-identical to the first 16 bytes of
0x18a6's body** (first_uuid_half + session_uuid_lower). So 0x1a59
is the W-direction "client confirms session subkey, counter=N"
beacon paired with the R-direction `0x18a6` server-to-client.

Counter values 2, 3, 4 align with the 0x18a6 R-direction counter
sequence — this is a paired R/W counter dance.

Codec: `server/javelin/session_subkey_1a59.py`.

## `0x5b2` — 45 / 93-byte W identity-fingerprint set (4 occurrences)

3 of 4 messages are **byte-identical 45-byte messages** including
the 4-byte client_hash (`f9 b3 ea 55`) — this is the same logical
message resent at the wire level (reliable-delivery
retransmission, or periodic "no fingerprints to report" beacon).
The 4th message is 93 bytes, carrying 6 fingerprints.

Wire layout (variable; `total = 45 + 8*count`):

```
[envelope: 28 bytes]
+0x00  u8x8   second_id              18 0f 8d 4e 57 36 97 c6
+0x08  u8x8   session_uuid_lower     bf 85 31 4b bc 4a 95 1a
+0x10  u8     count                  0..N (1 byte)
+0x11  u8x(8*count)  fingerprints   opaque 8-byte values
```

The `second_id` here is **distinct** from the `second_id` carried
by `0x18a6` and `0x635`. So this message references a different
identity surface — perhaps a fingerprint-bundle origin or a
sub-system instance ID.

Codec: `server/javelin/identity_fingerprint_5b2.py`.

## `0x635` — 93..153-byte W action-history beacon (5 occurrences)

Each new 0x635 message **adds exactly 15 bytes at the tail** while
keeping all previous content intact. So this is a client-side
reliable input/action queue: each message increments a u8 counter
and appends another "history record" for the new action; older
unacknowledged actions get re-broadcast.

Captured pattern across the 5 messages:

| Seq | Counter | History records | Total bytes |
|---|---|---|---|
| 0x6e | 1 | 0 | 93 |
| 0x6f | 2 | 1 | 108 |
| 0x70 | 3 | 2 | 123 |
| 0x71 | 4 | 3 | 138 |
| 0x72 | 5 | 4 | 153 |

Wire layout (envelope + 65 fixed body bytes + N×15 history bytes):

```
[envelope: 28 bytes]
+0x00  u8x8   second_id              fb de 4b 9a 60 0d 42 8f
+0x08  u8x8   session_uuid_lower     bf 85 31 4b bc 4a 95 1a
+0x10  u8x4   first_send_flag        00 01 00 00 on first message
                                     00 00 00 00 thereafter
+0x14  u8x4   const_a                91 02 06 00
+0x18  u8x12  const_b                00 01 01 00 00 00 00 00
                                     00 00 00 01
+0x24  u8x4   second_id_b            20 07 19 4b
+0x28  u8x6   const_c                00 00 00 ac 0f 01
+0x2e  u8     counter_u8             1, 2, 3, ...
+0x2f  u8     const_d                01
+0x30  u32 BE counter_u32            equals counter_u8
+0x34  u8x13  trailer                c0 80 20 00 80 80 80 80
                                     03 00 00 00 01

Then 0..N history records (15 bytes each), in DESCENDING counter
order — message with counter=N carries records for counters
N-1, N-2, ..., 1:
+0x00  u8x4   record_prefix          00 00 00 00
+0x04  u8     record_counter         u8
+0x05  u8     record_infix           00
+0x06  u8x9   record_tail            80 80 80 80 03 00 00 00 01
```

The trailer `c0 80 20 00 ...` and per-record `80 80 80 80
03 00 00 00 01` patterns clearly encode some structured value (not
random noise) — but without semantic context we treat them as
constants the captured session happened to use.

Codec: `server/javelin/action_history_635.py`.

## Cross-codec invariants in the captured session

The captured session weaves three different identity surfaces
across the codecs:

| ID | Length | Used by | Notes |
|---|---|---|---|
| `1a 95 4a bc 4b 31 85 bf be 37 c3 d8 59 26 18 e0` | 16 | session_uuid in 0x1a59, 0x5b2, 0x635 envelopes; `0xa4` body | full session UUID |
| `bf 85 31 4b bc 4a 95 1a` | 8 | session_uuid_lower in 0x18a6, 0x1a59 subkey, 0x5b2, 0x635, 0x663, 0x1b88 | lower half — appears EVERYWHERE |
| `f8 cb ed 57 c6 8b 18 f4` | 8 | first_uuid_half in 0x18a6, 0x1a59 subkey | session subkey upper |
| `9c fa 58 61 78 14 69 f2` | 8 | second_id in 0x18a6, 0x663 | metadata-block second id |
| `fb de 4b 9a 60 0d 42 8f` | 8 | second_id in 0x635 | distinct from 0x18a6's |
| `18 0f 8d 4e 57 36 97 c6` | 8 | second_id in 0x5b2 | yet another |

So the session has **(at least) three different "second ID"
surfaces**, each tied to a specific message family. This is
consistent with each major sub-system (session manager, action
queue, fingerprint reporter) carrying its own opaque
identity-bundle ID alongside the shared session UUID.

## Next message types worth a similar pass

- `0x16a0` (2 R, 153 / 99819 bytes) — small one is tractable; the
  ~98KB chunk is the chunked-replay path we already characterize
  in `wire.py`'s `chunk_replay_payload`.
- Singleton W messages (`0x40a`, `0x1be`, etc., 76 bytes) — useful
  as known wire-shape entries even though variant analysis isn't
  possible from a single sample.
- `0x08` R (79 occurrences, 78..46423 bytes) — the continuous
  entity-state stream. Variable size needs an actual parser
  (probably a TLV stream); can't characterize from byte patterns
  alone but worth surveying the lengths to see if there are
  natural cluster sizes.

Adding these to the inventory needs comparable variant data;
ideally another capture or two from different sessions to
cross-validate.
