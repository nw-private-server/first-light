# Static-RE investigation note: handshake-family signing scheme

> **Status**: open question, no static-RE attempted yet. Logged
> wake 84 so future RE work has a starting point.

## What we know from byte patterns

Three captured R-direction messages carry an **identical 36-byte
"shared_trailer"** at distinct offsets within their bodies:

```
cb d4 a1 8a 40 42 c7 ee
a4 62 98 c7 49 9b a8 26
ef 53 39 aa 29 70 e2 83
fc f3 4b 6f 8f 07 86 d6
8b f3 ae 45
```

The three messages:

| Type | Size | Trailer offset | sub_id at | When sent |
|---|---|---|---|---|
| `0x40a` | 76 B | +0x28 | +0x04 | seq 0x4 — right after V3 RegistrationResponse |
| `0x1be` | 76 B | +0x28 | +0x04 | seq 0x5 — paired with 0x40a |
| `0x65c` | 12706 B | +0x39 | +0x15 | seq 0x6 — Phase 4 WORLD DATA blob |

All three also carry a **constant 4-byte `sub_id`** =
`58 61 78 14`, which interestingly is bytes 2..5 of the 8-byte
`9c fa 58 61 78 14 69 f2` metadata-block second_id used by
0x18a6 + 0x663. So the sub_id appears to be a 4-byte excerpt
identifying "the session's metadata-bundle parent."

The non-trailer content of each message:

- **0x40a**: 32-byte ephemeral block (per-message random-looking bytes)
- **0x1be**: 32-byte ephemeral block (different random-looking bytes)
- **0x65c**: 32-byte ephemeral block + 16 zero bytes + the
  large records section (which doesn't participate in signing
  if our hypothesis is right)

## Hypothesis: trailer is a session-stable signature/MAC

The fact that the trailer is **byte-identical across three
messages** with **different ephemeral content** in each is
strong evidence the trailer is **NOT** a per-message signature
over the body — if it were, the trailer would differ
across messages (because the bodies differ).

### Wake 86 update: H1's hardcoded-constant sub-case is ruled out

Static-RE attempt: `FindByteLiteralXrefs` on the first 4 bytes
of the trailer (`cbd4a18a`) returned **0 hits**. Three more
4-byte slices (`8a4042c7`, `a46298c7`, `8bf3ae45`) also
returned 0 hits. The same pattern holds for the 4-byte sub_id
(`58617814`).

A broader scan via `FindBytesAnywhere` (which checks **all
loaded memory blocks**, including data sections) confirmed
this: neither `58 61 78 14` (sub_id) nor `cb d4 a1 8a 40 42
c7 ee` (first 8 bytes of trailer) appear **anywhere** in the
binary — not as immediate operands, not as data constants.

So both the sub_id and the trailer are **constructed at
runtime**. This rules out the simplest H1 sub-case (a baked-in
constant trailer) entirely. The trailer must be either
session-derived (still H1's broader case — a value computed
once per session and cached) or per-message-derived from a
session-stable input (H2).

Two viable hypotheses:

### H1: Session-derived constant ("certificate")

The trailer is a **session-stable certificate** issued at
session start. All three messages of the handshake family
include it as proof-of-session-validity. The client validates
the trailer once per session and treats it as a constant
afterwards.

**Implication for emulator**: a private server can:
- Either **issue its own constant trailer** at session start and
  use it consistently across all handshake-family messages
- Or **echo back** a trailer the client provides somewhere
  earlier in the handshake

### H2: Truncated MAC over a fixed prefix

The trailer is the MAC of some **fixed-prefix data** (e.g. the
session_uuid, build_version, or sub_id) — not the per-message
ephemeral content. Since the prefix is session-stable, the MAC
is too.

**Implication for emulator**: a private server needs to know:
- The MAC algorithm (HMAC-SHA256 truncated to 36 bytes? CMAC?
  or something custom?)
- The signing key (server-side secret? derived from session_uuid?)
- The exact data being signed

## What static-RE would resolve

To distinguish H1 from H2 (and pin down the algorithm if H2),
the most useful next step is:

### Step 1: Find the verifier in the binary

Locate the **handler-side function** that consumes a 0x40a /
0x1be / 0x65c message. The deserializer almost certainly:
1. Extracts the 36-byte trailer from a known offset
2. Either (H1) compares it to a session-cached value, or
   (H2) computes a fresh MAC over some prefix and compares

Cross-referencing the captured bytes against decompiled handler
code would let us see:
- What memory address holds the "cached trailer" (H1) — if any
- What hashing/MAC code path runs (H2) — and what data goes in

Recommended Ghidra approach:
1. Search for the byte string `cb d4 a1 8a` (first 4 bytes of
   the trailer) as an immediate constant — would surface
   hardcoded references if any exist
2. Find the dispatcher for type 0x40a (likely a switch
   statement in a `Carrier::DispatchMessage`-style function);
   trace from there to the per-type handler
3. In the handler, look for one of: a memcmp against a fixed
   buffer (H1), or a call to a hash/MAC routine (H2)

### Step 2: Recover the signing key (if H2)

If H2 wins, the signing key is server-side. Possible sources:
- Embedded in the V3 RegistrationResponse (one of the unparsed
  fields — probably **not** the redacted 32-byte `session_token`,
  which the captured replay shows the client uses elsewhere)
- Derived from `mystery8` = `[session_clock:4][nonce:4]`
- Derived from a hardcoded server constant + a session-specific
  parameter

The 32-byte ephemeral_block in 0x40a / 0x1be is a candidate for
"transport for the session signing key" — the field is exactly
the right size for an AES-256 key or a 256-bit HMAC key. But
without RE on the verifier we can't confirm.

### Step 3: Validate against more captures

If we get additional captures from the same session at later
times, the trailer should be **identical** (H1 or H2 with
session-stable inputs). If we get captures from a **different
session** (different player login), the trailer should
**change** (H1 with fresh session cert, or H2 with
session-derived MAC). Either way, comparison resolves several
ambiguities.

## Why this matters for the emulator

If H1: an emulator can pick its own 36-byte constant per
session and the client will accept it (trailers don't need to
match a cryptographic specification, just "be the same value
the server sent earlier").

If H2: an emulator must replicate the MAC algorithm + key
derivation. This is **significantly more work** — it likely
needs handler-side static-RE on the verifier code path, plus
either reverse-engineering the key derivation or extracting the
key from a captured runtime memory dump.

The captured-replay path (today's `rep_responder.py`) sidesteps
both by **forwarding the captured trailer verbatim** — it works
for a single replayed session but not for multi-session
emulation. This is one of the gaps documented in
`analysis/integration_status.md`.

## Cross-references

- Codecs:
  [`server/javelin/handshake_blob_76.py`](../server/javelin/handshake_blob_76.py)
  + [`server/javelin/world_data_blob_65c.py`](../server/javelin/world_data_blob_65c.py)
- Inventory:
  [identity-bundle map](replay_message_inventory.md#cross-codec-identity-bundle-map)
  + [0x65c structural skeleton](replay_message_inventory.md#0x065c--127-kb-r-blob-224-byte-fixed-record-table-singleton)
- Worklog: wake 75 (initial finding), wake 80 (codec coverage),
  wake 81 (0x65c structural codec)
- Tests: `test_hsb_round_trip_both_singletons` cross-validates
  the trailer match between 0x40a and 0x1be
