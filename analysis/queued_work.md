# Queued / deferred work

> Consolidates "next steps" and "deferred" items mentioned across
> wakes 66-83 in
> [`analysis/autonomous_worklog_through_253.md`](autonomous_worklog_through_253.md)
> (the wake-261 archive split — wakes 1-253 are there; wakes 254+
> are in the active `autonomous_worklog.md`). Last bulk update
> wake 83; targeted closures + the "Major progress since wake 83"
> section below were added at wake 235.
>
> Items are organized by theme so the worklog narrative isn't the
> only place they live. Mark items done in this file when shipped;
> add new ones at the top of the matching theme.

## Major progress since wake 83 (as of wake 235)

For a structured narrative of the 150+ wakes that followed, see:
- [Wake-150 retrospective](session_retrospective_150.md) — wakes
  1-150: codec library + central dispatcher + state-10 RE
  breakthrough + 100% decompile cross-link density.
- [Wake-196 retrospective](session_retrospective_196.md) — wakes
  151-196: dashboard navigation, rep_responder ↔ dispatcher
  integration foundation.
- [Wake-227 retrospective](session_retrospective_227.md) — wakes
  197-227: live-decoder coverage to 90.0% (with the wake-221 floor
  decision), phase-2D emission swap + counter-advance extension,
  cross-check graph 9 → 18 invariants with 5 self-referential pins.

Major individual closures relevant to this doc's open items:
- **State-10 → 11 gate** found at wake 112
  (`*(int*)(wrapper+0xa0) == 2`, trigger 0x5d1
  PlayerManagerSelfIdentificationMsg).
- **State-12 → 13 second writer** surfaced at wake 232 / corrected
  at wake 234 (`FUN_14645c660` ClientMessagesTrait entry sets
  `wrapper[+0xbc8] = 1`; LevelInfoChanged is the primary force-
  advance path). See `state_machine_summary.md` § 4½.
- **0x065c live-decoder** explicitly deferred at wake 221 with
  criteria + reversal conditions documented in
  `decision_0x065c_live_decoder.md`.

## Runtime / VM (blocked on hardware)

- **Real GPU testing path** — both UTM and Parallels Desktop on
  Apple Silicon were definitively ruled out at wake 70: virtio-style
  GPU virtualization presents `VendorId = DeviceId = 0` to DXGI,
  which the game rejects. Next escalation: physical Windows host
  (Bootcamp / spare PC) or AWS Windows-Gaming GPU VM. Maintainer
  decision needed; the SSH-driven infrastructure built for UTM /
  Parallels transfers verbatim — only the VM creation step changes.
- ~~**Phase 9b SelfIdent integration** — deferred since wakes 51-63.
  Wire-vs-in-memory size conflict for `PlayerManagerSelfIdentificationMsg`
  (handler reads from a 56-byte in-memory struct; captured Phase 9b
  body is described as 4 bytes).~~ — **resolved wakes 112 + 204**:
  static-RE found the state-10 → 11 gate predicate
  (`wrapper[+0xa0] == 2`) and the wire-type trigger (0x5d1, not in
  captured replay, server synthesizes). Codec exists at
  `server/javelin/self_ident.py`; phase-2D infrastructure
  (`heartbeat_use_dispatcher`, default off) is in place. Real-GPU
  runtime validation is the next step.

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
  - ~~`0x65c` WORLD-DATA: a second capture would validate the
    fixed-vs-variable record assumption and surface session-stable
    vs per-message fields.~~ — **partly addressed wake 221**:
    decision doc declared 0x065c stays out of the live decoder
    (`decision_0x065c_live_decoder.md`); a second capture is one
    of the explicit reversal criteria. Still a worthwhile capture
    target.
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
- ~~`make_handshake_blob_76`, `make_result_token_136a`,
  `make_result_token_1097`~~ — **shipped wake 84**.

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
- ~~`docs/post-v3-sequence.md` updates for new structural
  findings (0x65c handshake-trailer link, Phase 16 codec link)~~
  — **shipped wake 85**.

## Static-RE follow-ups (lower priority)

- **0x65c handshake-family signing scheme** — three R messages
  carry the same 36-byte signing trailer (0x40a, 0x1be, 0x65c).
  Static-RE on the verifier would reveal the signing algorithm
  and let us compute fresh trailers for emulator emission.
  **Investigation note**:
  [`analysis/static_re_handshake_signing.md`](static_re_handshake_signing.md)
  (wake 84) — formulates two hypotheses (session-derived constant
  vs truncated MAC) and lists the Ghidra approach that would
  distinguish them.
- **0x1033 Merkle structure** — would benefit from static-RE on
  the receive handler to understand the chunk-aggregation rule.
  **Investigation note**:
  [`analysis/static_re_1033_merkle.md`](static_re_1033_merkle.md)
  (wake 85) — wake 85 found that 9 of the trailing 40 bytes'
  ten 4-byte chunks reappear at specific earlier offsets in the
  body. Strong evidence of a deduplicated content-hash pool with
  trailing manifest. Hypothesis + Ghidra approach laid out.
- **0x9fc receipt-handshake state block** — the 26-byte middle
  section's per-byte semantics are unclear; static-RE on the
  client-side encoder would resolve it.

## Long-running maintenance

- ~~**Worklog grooming** — entries 66-83 are dense. A periodic
  consolidation into themed sub-docs (this file is one) keeps
  the worklog readable as it grows past ~80 entries.~~ —
  **resolved**: 3 retrospective docs now span the
  wake-1-to-wake-227 arc (see "Major progress since wake 83"
  above). The worklog stays as the per-wake trail; retrospectives
  consolidate.
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
