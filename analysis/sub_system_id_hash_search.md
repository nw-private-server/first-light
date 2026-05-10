# `sub_system_id` ↔ class name hash search (wake 122)

## Hypothesis tested

The 11 distinct `sub_system_id` values from the captured replay
(see `identity_bundle_correlation.md`) might be deterministic
hashes of class names, in which case computing the hash of each
of the 312 named registry entries should yield matches for some
of the captured sub_system_ids.

## Method

For each combination of:

- **312 named registry entries** + **3,487 registry UUIDs** (as
  byte sources)
- **8 string permutations** per name (raw, lowercase, uppercase,
  leaf-after-`::`, leaf-lowercase, whitespace-stripped-lowercase,
  with `Javelin::` namespace prefix, with full
  `Javelin::ClientMessagesTrait::` prefix, with/without `Msg`
  suffix)
- **7 hash functions** (FNV-1a-64, SHA-1[first 8], SHA-1[last 8],
  SHA-256[first 8], MD5[first 8], MD5[last 8], double-CRC32 over
  forward + reversed bytes)
- **Both byte orderings** of the hash output (BE / LE swap)

…compare against the 11 captured sub_system_ids:
`16009918b041c1f9, 180f8d4e573697c6, 288c27b1a6be71cc,
4c0c0ed6478a69da, 93a3e477cb5fd51e, 95a5a80aa54288d1,
9e921a154971f6b7, ce81136a2b7ad33e, d1a94ccc870660b0,
db84a5d631d9b33a, f8cbed57c68b18f4, fbde4b9a600d428f`.

## Result

**Zero matches**, across all combinations (7 hashes × 8
permutations × 2 byte orderings × 312 names + 3,487 uuids =
~110,000 hash invocations checked).

## What this rules out

- Simple class-name → 64-bit hash via the tested functions
  (FNV-1a-64, SHA-1, SHA-256, MD5, double-CRC32).
- Hash of registry UUID bytes via the same functions.

## What this does NOT rule out

The experiment was bounded by:

1. **Limited hash function set**. The Python stdlib doesn't
   include CityHash, MurmurHash, xxhash, FarmHash, or AzCore's
   own `AZ::Hash64` / `AZ::TypeInfo` hash. Any of those could
   still produce the captured sub_system_ids. Re-running with
   `pip install xxhash mmh3` and adding those is an obvious
   follow-up.
2. **Limited name corpus**. Only 312 of 3,487 registry entries
   have a populated `name` field. The other 91% are unnamed in
   the registry — so even a working hash would miss any
   sub_system_id whose class is in the unnamed group. A wider
   corpus (RTTI strings from the binary, or unnamed-entry-name
   recovery via the wake 90-97 typename mapping work) would
   tighten this.
3. **Hash of indirect data**. The sub_system_id might be a hash
   of a value we don't have access to — e.g. the runtime vtable
   pointer, an AzCore `TypeInfo` struct, or a process-internal
   pointer. None of those are recoverable from static data.

## What now points to "session-scoped allocation"

With the simple-hash hypothesis weakened, the most likely
remaining hypothesis is **session-scoped allocation**: the
sub_system_ids are runtime-derived per-session, possibly random
or derived from process startup state. The decisive test is
**a second session capture**:

- If the same wire-type carries a *different* sub_system_id in a
  second capture → session-scoped allocation confirmed. The
  sub_system_id is then useful only as an in-session correlation
  key, not a cross-session class identifier.
- If the *same* sub_system_id appears for the same wire-type in
  the second capture → some deterministic derivation (likely a
  hash function we haven't tested), and a more thorough hash
  search becomes worthwhile.

The cheapest path to that test is the same path the project's
already on: a real-GPU host running the game produces a fresh
capture; comparing identity-bundle bytes between captures
answers the question in seconds.

## Cross-correlation findings stand independently

Regardless of which hypothesis turns out right, the wake-121
finding that **7 of 11 sub_system_ids span multiple wire-types**
remains valid as an in-session correlation. Those wire-type
groupings tell us "these messages belong to the same sub-system
within this session", and that's useful for any same-session
analysis (the captured replay) even without a class-name
mapping.
