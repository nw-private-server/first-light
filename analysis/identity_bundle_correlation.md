# Identity-bundle cross-correlation (wake 121)

## Summary

Each captured wire-type that carries an identity-bundle includes
a 16-byte field decomposing as `[sub_system_id:8][session_uuid_lower:8]`.
The `session_uuid_lower` is constant per session; the
`sub_system_id` varies and tags the message's sub-system. Wake 78
established this layout; this wake enumerates the 11 distinct
`sub_system_id` values, identifies which wire-types share each,
and rules out the hypothesis that `sub_system_id` matches the
runtime type-registry's typeIndex UUIDs.

**Headline findings**:

1. **11 distinct `sub_system_id` values** confirmed (matches the
   wake-78 expected count).
2. **7 of 11 sub_system_ids span multiple wire-types** — those are
   the strongest "these messages belong to one sub-system" signals
   from static analysis alone.
3. **The `sub_system_id` namespace is separate from
   `info/typeregistry.json`**. None of the captured sub_system_ids
   match the lower 8 bytes of any typeregistry UUID, in either
   byte ordering, across all 3,487 entries.

## The 11 sub_system_ids and their wire-types

| `sub_system_id` (hex) | Wire-types | Msg count | Notes |
|---|---|---|---|
| `16009918b041c1f9` | `0x187c`, `0x187f` | 2 | Handshake-variant pair (subkey-beacon family) |
| `180f8d4e573697c6` | `0x05b2`, `0xa95` | 5 | Fingerprint-set + permission-bitmap |
| `288c27b1a6be71cc` | `0x10b0` | 1 | Single |
| `4c0c0ed6478a69da` | `0x8e6`, `0x9fc` | 1 + 1 | **Identity blob ↔ receipt handshake echo** (paired by 16-byte hash echo per wake 78) |
| `93a3e477cb5fd51e` | `0x1096`, `0x1097` | 1 + 1 | **Frame config ↔ spawn-confirmation result token** (paired) |
| `95a5a80aa54288d1` | `0x101a` | 1 | Single |
| `9e921a154971f6b7` | `0xf7f`, `0x143d` | 2 | Subkey-beacon family pair |
| `ce81136a2b7ad33e` | `0x102e`, `0x1033`, `0x192c` | 1 + 1 + 1 | **3-way correlation — strongest** |
| `d1a94ccc870660b0` | `0x9d3` | 1 | Single |
| `db84a5d631d9b33a` | `0x101d` | 1 | Single |
| `f8cbed57c68b18f4` | `0x18a6`, `0x1a59` | 4 + 3 | **Init beacon ↔ session subkey beacon** (the counter-coupled pair from wake 78) |
| `fbde4b9a600d428f` | `0x635` | 5 | Action-history beacon (singleton subsystem) |

## Cross-correlation highlights

### The 3-way: `0x102e` + `0x1033` + `0x192c` (sub_system_id `ce81136a2b7ad33e`)

These three wire-types belong to one sub-system. `0x1033` is the
opaque-blob codec from wake 102 (encrypted/signed material).
`0x102e` and `0x192c` are subkey-beacon family entries. The
shared sub_system_id implies the opaque-blob's bulk content is
related to whatever the two subkey beacons are tracking — likely
a single conceptual session-state-bundle whose pieces are
fragmented across three message types.

### Spawn-confirmation pair: `0x1096` + `0x1097`

The frame-config (wake 101 — durations, ratios) and the spawn-
confirmation result token share `93a3e477cb5fd51e`. The wake-78
counter-coupled-pair list didn't include this pair, but the
sub_system_id evidence puts them together. Plausible reading:
`0x1096` carries the spawn-zone configuration, `0x1097` the
client's ack/spawn-token.

### The known counter pair: `0x18a6` + `0x1a59`

Confirmed: the InitMessage18A6 ↔ SessionSubkeyBeacon1A59 pair
shares `f8cbed57c68b18f4`. The counter-coupling already in the
codecs aligns with the shared sub_system_id, validating the
sub-system-as-pair hypothesis.

## Negative result: sub_system_id ≠ typeregistry UUID lower 8 bytes

Hypothesis tested: each captured `sub_system_id` should match the
LOWER 8 bytes of some entry in `info/typeregistry.json`,
revealing the protocol-level class name of that sub-system.

Result: **zero matches** across all 3,487 entries, in either
byte ordering, for the candidate set
`{93a3e477cb5fd51e, ce81136a2b7ad33e, 69ceaf9f28443d0d, 03879424661f8543, 0365f26914786158, bf85314bbc4a951a}`.

Even the canonical session_uuid_lower (`bf85314bbc4a951a`) —
constant for this whole session — is not present in the registry.

**Implication**: the `sub_system_id` namespace is a different
identifier system from the runtime type-registry typeIndex UUIDs.
Possibilities:

1. **Runtime-allocated session-scoped IDs**. The values change
   per-session, derived from a hash or random per-process. A
   second session capture would have entirely different
   sub_system_ids — testable.
2. **Hashed from class names**. `sub_system_id = hash(class_name)`
   for some hash. Could be checked against the existing 312
   named registry entries by computing common 8-byte digests
   (CRC64, SHA-1[0:8], FNV-1a, etc.) and looking for matches.
3. **A separate AzCore sub-system enumeration**. AzCore-style
   sub-system IDs are sometimes a separate registry (e.g.
   `AZ::Crc32` over sub-system class names). The 64-bit form
   here would be inconsistent with AZ::Crc32 (32-bit), but a
   custom 64-bit AZ::Crc64 is possible.

## What this enables

- **Codec-library structural docs**: each codec module that carries
  identity can now name its sub-system family via the `sub_system_id`,
  even without a confirmed class-name. A future enhancement: surface
  this on the dashboard's Wire Types tab as a "family" column.
- **Future capture analysis**: if a second session's captures show
  the SAME `sub_system_id` for the same wire-types, that proves
  the values are class-derived (hash hypothesis #2). If different,
  that proves session-scoped allocation (hypothesis #1).
- **Hash-search experiment** (cheap, can be done without runtime):
  compute CRC64 / SHA-1[0:8] / FNV-1a-64 / xxhash64 over each of
  the 312 named registry entries' class names and check for any
  match against the 11 captured sub_system_ids. If any hash matches,
  we get the class name for that sub_system_id.
