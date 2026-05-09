# Static-RE investigation note: 0x1033 Merkle-shape blob

> **Status**: open question, no static-RE attempted yet. Logged
> wake 85 so future RE work has a starting point.

## What we know from byte patterns

Single 498-byte capture (seq 0x26, R direction). Body shape:

```
+0x00  u8x4     type_header        [00 01 b3 40] = type 0x1033
+0x04  u8x16    identity_uuid      lower 8 = session_uuid_lower
+0x14  u8x478   payload            no obvious top-level structure
                                   from byte patterns alone
```

The 478-byte payload has **strong evidence of a "chunked
content hash table" / deduplicated-pool structure** — wake 85
verified this empirically.

### Finding 1 (wake 74): one 8-byte repeat

The 8-byte sequence `43 1d f4 ea 8a 9c fc ac` appears in the
payload at exactly **two offsets: +5 and +450**. The only
non-trivial 8-byte run that repeats. So the bytes at +5..+12 of
the payload are duplicated near the end (at +450..+457).

### Finding 2 (wake 85): the trailing 40 bytes are an index

The trailing 40 bytes of the payload (offsets +438..+477)
decompose into **ten 4-byte chunks**, and **9 of those 10
chunks reappear elsewhere in the body** at specific earlier
offsets:

| Index chunk (4 bytes) | Found earlier at |
|---|---|
| `b1 87 3b 49` | +13 |
| `1c 07 87 5d` | +1 |
| `c4 c6 38 1e` | +17 |
| `43 1d f4 ea` | +5 |
| `8a 9c fc ac` | +9 |
| `58 29 a8 8f` | +73 |
| `4a 3c 5e 77` | +333 |
| `92 c4 5c e5` | +369 |
| `1c 1b 71 59` | +253 |
| `5a 09 81 ef` | (not found earlier — terminator?) |

The first 5 chunks point at offsets {1, 5, 9, 13, 17} — a
4-byte-aligned strip in the **opening 21 bytes** of the
payload. The next 5 point at offsets {73, 253, 333, 369} —
scattered through the middle. The 10th chunk doesn't appear
elsewhere and may serve as a terminator or a final-summary
hash.

### Finding 3: opening 21 bytes look like a header of 4-byte hashes

The first 21 bytes of the payload break cleanly into:

```
+0   1 byte  `6d`           probably a header byte (count? version?)
+1   4 bytes `1c 07 87 5d`   hash A
+5   4 bytes `43 1d f4 ea`   hash B
+9   4 bytes `8a 9c fc ac`   hash C
+13  4 bytes `b1 87 3b 49`   hash D
+17  4 bytes `c4 c6 38 1e`   hash E
```

So bytes +1..+20 carry **5 distinct 4-byte hashes**, all of
which are referenced again in the trailing 40-byte index. The
remainder of the payload (bytes +21..+437, 417 bytes) contains
larger structures that include the hashes at offsets +73,
+253, +333, +369.

## Hypothesis: deduplicated-chunk pool with index

The structure looks like a **content-addressed chunk pool**:

- Body contains a fixed-size table of "leaf chunks" near the
  start (5 chunks × 4 bytes at +1..+20).
- Larger objects in the middle (+21..+437) reference some of
  those leaves by **inlining the same 4-byte hash** wherever
  the chunk's content is needed.
- The trailing 40-byte index is a **manifest** listing 10
  distinct hashes that were referenced anywhere in the body
  — with a terminator at the end.

This is a **deduplication scheme**: when a 4-byte content hash
appears multiple times in the data, the wire format uses the
hash directly rather than re-emitting the chunk content. The
trailing manifest then enumerates the distinct hashes used.

Plausible interpretation in game terms: this is an **asset
manifest** where small content (item IDs, ability hashes, perk
identifiers) is hash-keyed and the message body references
each unique hash once via the leading table while the inline
manifest lists which hashes apply.

## What static-RE would resolve

To confirm the hypothesis and pin down the schema, the next
step is:

### Step 1: Find the deserializer

Locate the **handler-side function** that consumes type 0x1033.
The deserializer almost certainly:
1. Extracts the 16-byte identity_uuid
2. Walks the body extracting hashes / referenced objects
3. Builds an in-memory structure (likely an
   `AZStd::unordered_map<u32, X>` or similar) keyed by the
   4-byte hashes

Cross-referencing the captured bytes against decompiled
handler code would let us see:
- The exact layout of the leading hash table (count? aligned
  array? variable-length?)
- The interpretation of bytes +21..+437 (one big record? many
  records? what does each record reference?)
- Whether the trailing 40 bytes are an index, a checksum, or
  both

Recommended Ghidra approach:
1. Find the dispatcher for type 0x1033 (likely a switch
   statement in `Carrier::DispatchMessage`); trace from there
   to the per-type handler
2. In the handler, identify the loop that walks the payload —
   how many iterations? what offset increments?
3. Map the captured bytes against the loop's offset progression

### Step 2: Identify the hash function (if any)

If the 4-byte values are **content hashes** (rather than
external identifiers), the hash function must be invertible
from external state — e.g. `crc32(asset_name)` or
`fnv1a_32(asset_id)`. Static-RE on the hash-computation site
would name the function.

If the values are **external identifiers** (e.g. asset
catalog IDs), they're opaque from the binary's perspective and
need to be sourced from server-side game data.

### Step 3: Validate against more captures

A second 0x1033 capture from a different session would
distinguish:
- "Session-stable identity" hashes (would change per session)
- "Catalog ID" hashes (would be stable across sessions)
- "Per-message random" hashes (would change per emission within
  a session)

In the current capture all 4-byte values look random-uniform —
i.e. they're hashes, not catalog IDs in the open. So either
catalog IDs are hashed for transport, or this is per-session
state.

## Why this matters for the emulator

If the hypothesis is correct, an emulator emitting 0x1033 needs
to either:

1. **Pre-compute** a small static manifest at server startup
   (matching the captured shape) and re-emit it verbatim — the
   single-capture-replay approach today's `rep_responder.py`
   uses. Sufficient for the current scope.
2. **Generate fresh manifests** from server-side state — needs
   the hash function (step 2 above) plus the catalog of items
   to be encoded.

For a private server **that doesn't need to expose dynamic
asset content** (i.e. just gets the player into the world),
option 1 is sufficient. Option 2 is only required if the server
needs to vary the manifest per-session or per-map.

## Cross-references

- Codec status: no codec yet — the structure is documented in
  [`analysis/replay_message_inventory.md`](replay_message_inventory.md#0x1033--498-byte-r-hashmerkle-like-payload-singleton-not-yet-codecd)
  but the per-byte semantics aren't recoverable from one
  capture
- Related static-RE notes:
  [`analysis/static_re_handshake_signing.md`](static_re_handshake_signing.md)
  (handshake-family signing trailer)
- Worklog: wake 74 (initial Merkle finding), wake 85 (trailing
  40-byte index identified)
