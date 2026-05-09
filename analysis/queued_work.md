# Queued / deferred work

> Consolidates "next steps" and "deferred" items mentioned across
> wakes 66-83 in `analysis/autonomous_worklog.md`. Updated wake 83.
>
> Items are organized by theme so the worklog narrative isn't the
> only place they live. Mark items done in this file when shipped;
> add new ones at the top of the matching theme.

## Runtime / VM (blocked on hardware)

- **Real GPU testing path** — both UTM and Parallels Desktop on
  Apple Silicon were definitively ruled out at wake 70: virtio-style
  GPU virtualization presents `VendorId = DeviceId = 0` to DXGI,
  which the game rejects. Next escalation: physical Windows host
  (Bootcamp / spare PC) or AWS Windows-Gaming GPU VM. Maintainer
  decision needed; the SSH-driven infrastructure built for UTM /
  Parallels transfers verbatim — only the VM creation step changes.
- **Phase 9b SelfIdent integration** — deferred since wakes 51-63.
  Wire-vs-in-memory size conflict for `PlayerManagerSelfIdentificationMsg`
  (handler reads from a 56-byte in-memory struct; captured Phase 9b
  body is described as 4 bytes). Resolution needs either a captured
  Phase 9b or static-RE on the deserializer. Encoder lives at
  `server/javelin/self_ident.py` but is not yet wired into emission.

## Codec library — content-stream gaps

- **`0x08` entity-state TLV stream** (79 captures, 78–46423 B) —
  needs handler-side static-RE on the 0x08 dispatcher to characterize
  the per-frame TLV format. The 24 byte-identical 46407-B snapshots
  are pure transport-layer resends (sha256 confirms); the smaller
  frames have a per-stream sub-counter at payload offset +1.
- **`0x1033` Merkle-shape blob** (498 B singleton) — repeated
  8-byte sequence at offsets 5 and 450, trailing 40 bytes decompose
  into ten 4-byte chunks where at least one reappears in the opening
  16 bytes. Suggests a Merkle-tree-style hash structure but
  cannot be modeled confidently from one capture.
- **`0x16a0` large variant** (~99 KB chunked-replay) — handled by
  `wire.py`'s `chunk_replay_payload`; no codec needed.
- **`0x1096` spawn-position floats** (80 B singleton) — paired with
  0x1097 by shared identity_uuid; the 60-byte float payload looks
  like position + rotation but per-byte semantics aren't recoverable
  from a single capture.
- **`0x65c` 224-byte fixed-record content** — structural codec
  shipped wake 81 (records as `(data, ff_padding)` pairs); the
  semantic interpretation of each record's data bytes still needs
  more captures or static-RE.

## Codec library — additional cross-replay validation

- **Multi-capture comparison** would resolve several "single-capture
  uncertainty" items:
  - `0x12f6` keybinding-config: a different user's bindings would
    pin down the per-binding-slot vs free-list semantics in the
    26-byte state region.
  - `0x65c` WORLD-DATA: a second capture would validate the
    fixed-vs-variable record assumption and surface session-stable
    vs per-message fields.
  - `0x1033` Merkle-shape: a second capture would let us compare
    chunk values and identify the hash function.
  - All identity-bundle uppers (currently named in the cross-codec
    map) — a fresh capture would confirm whether they're per-session
    or per-cluster.

## Codec library — small enhancements

- ~~Encoder-side `make_*` factories for high-frequency types
  (`make_session_clock_beacon`, `make_session_identity_beacon`,
  `make_session_message_a4`)~~ — **shipped wake 83**.
- ~~Higher-level `SessionState` dataclass for tracking counters /
  identities / clocks across emissions~~ — **shipped wake 83 as a
  structure-only sketch in `server/javelin/session_state.py`**.
  Still pending: methods on `SessionState` (`advance_18a6_counter`,
  `mint_session_clock`, etc.) — deferred until integration day.
- **More factory helpers**: `make_handshake_blob_76(type_id,
  blob, *, sub_id=DEFAULT, shared_trailer=DEFAULT)` would simplify
  building 0x40a / 0x1be. Same shape as existing helpers.

## Documentation polish

- ~~Cross-link `0x03` R from inventory to `v3_response.py`~~ —
  **shipped wake 74**.
- ~~Cross-codec identity-bundle map at top of inventory~~ —
  **shipped wake 78**.
- ~~Codec coverage table~~ — **shipped wake 80**.
- ~~`docs/post-v3-sequence.md` codec column on the phase table~~ —
  **shipped wake 75**.
- ~~Server↔client counter pair docs in post-v3-sequence.md~~ —
  **shipped wake 78**.
- ~~Integration status doc~~ — **shipped wake 82**.
- **`docs/post-v3-sequence.md` updates** when new structural
  findings surface (e.g. the 0x65c handshake-trailer link from
  wake 75 isn't yet reflected in the post-v3 phase 4 row).

## Static-RE follow-ups (lower priority)

- **0x65c handshake-family signing scheme** — three R messages
  carry the same 36-byte signing trailer (0x40a, 0x1be, 0x65c).
  Static-RE on the verifier would reveal the signing algorithm
  and let us compute fresh trailers for emulator emission.
- **0x1033 Merkle structure** — would benefit from static-RE on
  the receive handler to understand the chunk-aggregation rule.
- **0x9fc receipt-handshake state block** — the 26-byte middle
  section's per-byte semantics are unclear; static-RE on the
  client-side encoder would resolve it.

## Long-running maintenance

- **Worklog grooming** — entries 66-83 are dense. A periodic
  consolidation into themed sub-docs (this file is one) keeps
  the worklog readable as it grows past ~80 entries.
- **Cert regeneration noise** — `server/certs/{auth.crt,server.crt,
  newworld_ca.crt}` get regenerated by `auth_mock` startup;
  modifications appear in `git status` between wakes but aren't
  meaningful changes. Currently filtered out of commits manually;
  consider gitignoring the regenerable subset.

## Done in wakes 66-83 (high-level)

- **Codec library**: 22 dedicated codecs + 1 generic (14-type) +
  6 factory helpers (3 wake 81-82, 3 wake 83); 248 tests passing
- **Type coverage**: ~35 of 40 captured type-IDs covered
- **Documentation**: inventory, codec coverage map, integration
  status, R/W counter-pair docs, identity-bundle map, post-v3
  cross-links
- **Cross-codec invariants**: counter pairs, hash echoes, signing
  trailer family — all validated via cross-replay tests
- **Build infrastructure**: SSH-driven UTM + Parallels VM setup,
  SCP-pushed game directory, Mac-side servers, portproxy — all
  working end-to-end. Apple-Silicon-hosted VM ruled out for game
  launch (paravirtualized GPU rejected by client)
