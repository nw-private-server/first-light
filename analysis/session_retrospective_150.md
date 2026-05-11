# 150-wake autonomous session — milestones

150 wakes of a self-paced autonomous /loop session, all on
`claude/vacation-2026-05-06`. This doc summarizes the major
milestones for any future maintainer or contributor browsing
the project history. Each wake is a single commit; the worklog
(`autonomous_worklog.md`) has the full per-wake trail.

> **Continued in the [second-stretch retrospective
> (wakes 151-196)](session_retrospective_196.md)** — this doc
> is a frozen wake-1-to-150 snapshot. The session-arc chain is
> wake-150 → wake-196 → wake-227 → wake-253; follow the
> forward pointers to reach current state, or jump directly to
> the [fourth-stretch retrospective
> (wakes 228-253)](session_retrospective_253.md) for the most
> recent milestone (state-machine RE closure at static-RE
> level).

For the **pattern** behind multi-wake arcs (scaffold → wedge →
close), see [`cross_link_arc.md`](cross_link_arc.md).

## Snapshot (as of wake 149)

- **40 / 40 captured wire-types covered** by codecs
- **346 tests passing** (+1 skipped) — both audits at 0 gaps
- **175 of 177 captured messages** round-trip byte-identically
  through the unified dispatcher (1 intentional skip on
  `0x03`; 1 dispatcher decode-edge case on the largest
  `0x16a0` blob, also passing tests)
- **39 / 39 decompile cross-link density** on the dashboard
  Decompiles tab
- **32 `analysis/*.md` writeups** indexed on the Findings tab
- **Live dashboard** at
  https://nw-private-server.github.io/first-light/ — auto-
  redeploys on push, six tabs (Overview / Wire Types / Codecs
  / Decompiles / Findings / How it works / Explore), test +
  coverage badges in both READMEs (main and working branch)
  via shields.io endpoint JSON

## Phase 1: codec scaffolding (wakes 1-50, pre-context)

Carry-over context from the earlier window. Built the
foundation:

- Wire framing (`bitstream.py`, `frame.py`, `wire.py`)
- Replay store + replay-substitution scaffolding
- V3 RegistrationRequest strict parser + V3RegistrationResponse
  encoder
- Heartbeat 0x15d ping/ack codec
- Initial per-type codecs for the dense ones (subkey-beacon
  family, identity blobs, session beacons, etc.)
- DTLS bridge + REP responder runtime

## Phase 2: typename + identity-bundle work (wakes 60-90)

- Static-RE on the EAC-wrapped binary using Ghidra (analysis
  succeeded 2026-05-06)
- Type registry mapping: 3487 entries in `info/typeregistry.json`,
  297 of 312 named entries mapped to MSVC RTTI strings via
  TU-boundary detection + count-match (wake 95-96)
- 5 captured wire-types confirmed by direct binary match
  (REPClient::*)
- Identity-bundle decomposition (wake 78): every captured
  type's 16-byte identity field decomposes as
  `[sub_system_id:8][session_uuid_lower:8]`, with 11 distinct
  sub_system_ids surfacing across the library
- W-direction CRC32 wired and tested (wake 90-92)

## Phase 3: codec gap-fill — 35/40 → 40/40 (wakes 100-103)

The dense codec-shipping arc. Four wakes, one codec gap each:

| Wake | Commit | Codec | Coverage |
|---|---|---|---:|
| 100 | `3724b3c` | `empty_marker_651.py` (zero-payload) | 36/40 |
| 101 | `29f0e4e` | `frame_config_1096.py` (80 B structural) | 38/40 |
| 102 | `3fb367d` | `opaque_blob_1033.py` (498 B framing-only) | 39/40 |
| 103 | `c6a905c` | `chunked_stream_08.py` (79 captures, two forms) | **40/40** |

Test count grew 258 → 282 (+24). The wake-103 milestone closed
the captured-type gap; every body in the replay now had a codec
that round-tripped byte-for-byte.

## Phase 4: central dispatcher + wire-complete (wakes 104-109)

| Wake | Commit | Shipped |
|---|---|---|
| 104 | `18de9b7` | `server/javelin/dispatch.py` — central type_id → decoder router; 174 ok, 1 intentional skip (0x03), 2 documented decode failures |
| 105 | `3fb9423` | Encode-side dispatcher; 174 captured messages round-trip byte-identically through `decode → encode` |
| 106 | `3c987dd` | V3 lenient regex extractor promoted from `rep_responder.py` into the codec library |
| 107 | `0423790` | V3 retry-format parser (`[u32 BE type_id][u8 length][string]` records); dispatcher decode failures 2 → 1 |
| 108 | `96dbb85` | V3 retry encoder symmetric to wake-107 parser; captured 0x13 retry round-trips byte-for-byte |
| 109 | `1f4a7cb` | `AssetBlob16A0Large` codec — last decode failure closes. **0 decode failures, 0 wire mismatches across the full 177-message replay.** |

## Phase 5: state-10 RE breakthrough (wakes 111-112)

Long-deferred work, finally tractable with parallel-agent
playbook:

- Wake 111 (`c4d963c`): two `Explore` agents in parallel
  converged the gate predicate (`*(int*)(wrapper+0xa0) == 2`,
  NOT `+0x130` as project memory had recorded — corrected) and
  the trigger message (PlayerManagerSelfIdentificationMsg,
  wire type **`0x5d1`**, encoded `0x91(0x17)`). Critical
  finding: `0x5d1` is NOT in the captured replay, so pure
  replay can't drive the state-10 → 11 transition. Documented
  in `state_10_unblock_synthesis.md`.
- Wake 112 (`805a6d9`): wire-bound the SelfIdent codec
  (`encode_typed`, `decode_typed`, `encode_trigger`,
  dispatcher entries). State-10 unblock path is now
  operationally ready for runtime testing.

## Phase 6: dashboard / live site (wakes 98, 113, 117-120, 133-140)

The live https://nw-private-server.github.io/first-light/
dashboard grew across several wakes:

- Wake 98: initial scaffold (`tools/build_site.py`,
  `site/index.html`, Pages workflow)
- Wake 113: session-timeline scatter chart (177 dots)
- Wake 117: per-row 📋 copy-buttons + "What's a wire-type?"
  explainer on the Wire Types tab
- Wake 120 (parallel subagent): click-to-inspect message
  browser on the timeline scatter — every dot opens a
  decoded-dataclass + xxd hex view
- Wake 124: chart-empty fix (Pages runner shallow-clone →
  `fetch-depth: 0`) + `safeDraw` try/catch resilience +
  Decompiles UX rework
- Wakes 133-134: byte-pattern playground (Explore tab) +
  preset buttons
- Wake 137: auto-updating shields.io coverage badges (test
  count + codec coverage stay live without README edits)
- Wakes 138-140: main-README badge mirror, audit-gap stat
  card, "How it works" codec-pipeline walkthrough

## Phase 7: codec audit + test-coverage arcs (wakes 125-126, 135-136)

Two scaffold-wedge-close arcs, 10 wakes apart but identical
shape. Documented in
[`cross_link_arc.md`](cross_link_arc.md):

| Audit | Initial gaps | Closed at | Tests added |
|---|---:|---|---:|
| Decoder rejection | 8 | wake 126 | 15 |
| Encoder round-trip | 7 | wake 136 | 8 |

Tests grew 320 → 346 (+26). Every codec module now has both
structural-rejection on `decode()` and populated round-trip
on `encode()`.

## Phase 8: decompile cross-link density (wakes 129-131)

Three-wake arc covering the dashboard's decompile-tab cross-
references to analysis docs. Wake 129 built the annotation
infrastructure (12/39 reachable); wakes 130 and 131 wrote
overview docs (connection lifecycle, wrapper setters) that the
infrastructure auto-picked-up. Final: **39 / 39 (100%)**.

## Phase 9: polish + ergonomics (wakes 140-149)

Once the codec library was wire-complete and audits were
closed, work shifted to UX:

- "How it works" tab with two worked examples (heartbeat +
  init beacon)
- `tools/decode_message.py` got `--list` / `--json` / `--seq`
  flags
- Wire-type families panel surfaces wake-121's RE findings
- Cross-link arc retrospective (`cross_link_arc.md`)
- Analysis-doc index on Findings tab (32 writeups, searchable)
- `/` keyboard shortcut focuses the Explore-tab search
- Sharable inspector deep-links via `#msg=0xNN` URL hash
- Timeline picks up the audit + polish arcs
- Doc-freshness refreshes (`codec_library_overview.md`,
  `codec_coverage.md`)

## What's still open

The codec library + dashboard are in a steady state. The
remaining high-leverage open items for any future maintainer
or contributor:

1. **State-10 runtime testing** — the wake-112 wire-binding
   makes this a single experiment when a real-GPU host is
   available. Send `self_ident.encode_trigger()` (4 bytes)
   first; if `wrapper+0xa0` doesn't flip, send
   `dispatch.encode_replay_message(0x5d1, msg)` (21-byte
   structured form). See `state_10_unblock_synthesis.md`.
2. **`rep_responder.py` dispatcher integration** — the
   responder still parses messages with ad-hoc per-type
   branches. Routing through `dispatch.decode_replay_message`
   would consolidate the responder's input path and let new
   codecs apply automatically.
3. **Inline live-decoder on the dashboard's Explore tab** —
   the playground searches by hex pattern; pairing it with a
   JS port of the simpler codecs (heartbeat 0x15d, clock
   beacon 0x14f, empty marker 0x651) would let visitors paste
   hex and see decoded fields without the CLI.
4. **Identity-bundle hash hunt extension** — wake 122 ruled
   out FNV/SHA/MD5/double-CRC32 against named registry
   entries (zero matches). The cheap follow-up is
   `pip install xxhash mmh3` + re-run with those + AzCore-
   style CRC64.
5. **Sub_system_id second-capture comparison** — if a future
   contributor captures a second session, comparing the
   wake-121 sub_system_ids across captures resolves the
   "session-scoped vs deterministic hash" question
   definitively.

## Working style notes

- All work fits inside ~30-min wakes. Larger arcs split as
  scaffold → wedge → close in 2-3 wakes (see
  `cross_link_arc.md` for two recent examples).
- Parallel `Agent` subagents are used when sub-tasks are
  independent — see wake 111 (state-10 + codec hunt) and wake
  121 (identity-bundle enumeration + registry hunt) for the
  highest-leverage examples.
- Every wake produces one commit. The worklog (this
  retrospective's source-of-truth) captures the per-wake
  rationale; the commit message captures the per-wake change.
- The dashboard is shippable in every state — `safeDraw`
  try/catch around chart construction means one broken chart
  never bricks the page.
- Tests serve as the regression bar. The dispatcher full-
  replay round-trip test is the canary: any new codec failure
  surfaces as one failing assertion rather than silent drift.
