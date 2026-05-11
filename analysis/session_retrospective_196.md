# Wakes 151-196 — second-stretch milestones

A 46-wake continuation of the [wake-150 milestone
retrospective](session_retrospective_150.md). Where wakes
1-150 built the codec library + the wire-complete dispatcher
+ initial dashboard, wakes 151-196 turned the dashboard into
a navigable visitor surface, extended the live decoder to
cover 80% of captured wire-types, started consuming the
dispatcher from `rep_responder.py`, and grew a 7-test cross-
check graph that pins the dashboard's structural invariants.
Each wake is a single commit; the per-wake trail lives in
[`autonomous_worklog.md`](autonomous_worklog.md).

## Snapshot (as of wake 196)

> **Post-wake-196 deltas (as of wake 206)**: this doc was
> written at wake 197 and reflects the state at wake 196.
> The autonomous session continued past it; key deltas:
> tests **437** (+phase-2D swap lockdown), live decoder
> coverage **85% (34/40)** with the wake-200 explainer
> card surfacing why the remaining 6 stay uncovered,
> Findings tab **15 cards** (7 Research closures — the
> dominant bucket now), **9 cross-check tests**
> (+wake-201 badge-color thresholds, +wake-202 api-ref
> idempotency), and **phase-2 arc complete**: wake 204
> shipped the actual heartbeat emission swap behind
> `heartbeat_use_dispatcher` (default off). The Phase 2
> table below has been extended to include wake 204.

- **430 tests passing** (+1 skipped), up from 346 at wake
  149. The growth is mostly cross-check + lockdown tests,
  not new codec tests — the 40/40 captured-wire-types
  coverage held steady throughout.
- **Live decoder addresses 32 of 40 captured wire-types
  (80%)**, plus the synthesized 0x5d1 state-10 trigger.
  Two visitor-facing string-decoders (0x1067 VivoxConfig,
  0x663 LevelDescriptor) surface real captured strings
  inline (e.g. `"https://nwxp.www.vivox.com/api2/"`,
  `"NewWorld_VitaeEterna"`).
- **13 Findings cards** on the curated tab, up from 7 at
  wake 149. Five Research closures, five Wire-level
  findings, two RE breakthroughs, one Architecture
  decision.
- **7 dashboard cross-check tests** form a "structural
  invariants" graph: every dashboard surface that could
  drift between source-of-truth code and rendered output
  is pinned by a test that names what would break.
- **`rep_responder.py` ↔ dispatcher integration foundation
  proven safe**: inbound shadow decode + 9-test lockdown
  + outbound encode-validation probe + 8-test lockdown.
  A future wake can swap one outbound type to dispatcher-
  encoded emission with full confidence.
- **Live dashboard** still at
  https://nw-private-server.github.io/first-light/. README
  now carries **5 badges** (Tests + Pages deploy + Test count
  + Codecs + **NEW: Live decoder**).

## Phase 1: Dashboard ergonomics (wakes 151-156, 159)

Polish the existing dashboard surfaces so visitors can
find things.

| Wake | Commit | Shipped |
|---|---|---|
| 151 | `5935962` | Analysis-doc category grouping on Findings tab (5 categories from 33 flat docs). |
| 152 | `68aa47e` | Inline live-decoder (4 simple codecs). |
| 153 | `cebe231` | Doc-staleness audit round 1 — 3 docs refreshed. |
| 154 | `1a58638` | README retrospective-link + InitMessage18A6 in live decoder. |
| 155 | `ef181c8` | Identity-bundle hash hunt v2 — 246,220 invocations × 0 matches. **Definitive close** of the deterministic-hash hypothesis. |
| 156 | `683f5b9` | Hash-hunt + state-10 promoted to Findings cards. |
| 159 | `1108930` | Wire-type families drill-down on Overview tab. |

Highlights: wake 155's hash-hunt closure is one of the
strongest research outputs of the session — it converted a
wake-122 "negative but not definitive" into a definitive
ruled-out hypothesis across 13 hash families × 2 byte
orderings × 9,470 byte-inputs.

## Phase 2: rep_responder ↔ dispatcher integration (wakes 157, 158, 187, 188, 204)

Two-step "shadow → lockdown" pairs on both directions of the
responder ↔ dispatcher boundary, followed by the actual swap
behind a feature flag. The conservative pattern is
deliberate: the responder's behavior matters for a real
client, so each integration step ships logging-only or
default-off and gets pinned by ≥6 tests before any flip.

| Wake | Commit | Step |
|---|---|---|
| 157 | `909706b` | Inbound shadow decode: every received record routes through `dispatch.decode_replay_message` at debug-log level. No behavior change. |
| 158 | `b34a1f7` | 9 lockdown tests for the inbound shadow path. Covers round-trip, silent-skip (3 shapes), unsupported-type-id, codec-failure-without-propagation. |
| 187 | `3bf8ec6` | Outbound encode-validation probe: at startup, decode + re-encode the cached 0x15d heartbeat through the dispatcher, assert byte-equality. Logs INFO when safe. |
| 188 | `c04054a` | 8 lockdown tests for the encode validation. Same shape as wake 158. |
| **204** | `402bd62` | **Actual emission swap behind `heartbeat_use_dispatcher` (default off)**. When the flag is on, `_send_dispatched_heartbeat()` re-encodes the cached decoded heartbeat via `dispatch.encode_replay_message` and routes through the existing `_send_replay_message` plumbing. First emission logs at INFO, subsequent at DEBUG. Runtime-failure fallback keeps the heartbeat stream alive if the dispatcher raises. 3 lockdown tests: byte-equality against captured replay, log-level progression, fallback safety net. |

The captured-replay path remains the safe default. Flipping
`heartbeat_use_dispatcher=True` activates the dispatcher
path; the operator-visible signal is the `[phase-2D] first
dispatcher-encoded heartbeat sent` INFO line. A future wake
can mutate `decoded.counter`/`nonce` between sends to make
heartbeats actually advance (closer to real server behavior).

The wake-196 meta-invariant test ensures the shadow→lockdown
pattern stays mandatory: any future `_shadow_*` or
`_validate_*` helper in `rep_responder.py` must have a
≥6-test lockdown file, or the build fails.

## Phase 3: Generated docs + audit pass (wakes 160, 161, 165)

| Wake | Commit | Shipped |
|---|---|---|
| 160 | `24559c5` | Doc-staleness audit round 2 (8 more docs); 2 Ghidra-snapshot docs get forward-pointer banners. |
| 161 | `a9a5124` | `tools/build_api_reference.py` + generated `analysis/public_api.md` (55 exports + 6 dispatcher entries). Idempotent — re-run after any `__init__.py` change. |
| 165 | `f429c1d` | 4 class docstrings patched; `PlayerManagerSelfIdentificationMsg` entry now leads with "Wire type 0x5d1 — the state-10 → 11 unblock trigger" instead of a field dump. |

The wake-161 generator script means future contributors adding
a codec only need to write a class docstring and re-run the
script; the API reference doc never falls behind the live code.

## Phase 4: Live-decoder coverage push (wakes 152, 154, 171, 173, 174, 175, 176, 179, 183, 190, 191, 192)

The most-paid-attention-to arc. 6→32 captured wire-types
addressable from the dashboard's Explore tab.

| Wake | Codecs added | Coverage |
|---|---|---:|
| 152 | 0x15d ping/ack, 0x14f, 0x651 | 4/40 |
| 154 | 0x18a6 InitMessage | 5/40 |
| 171 | 0x1b88 SessionIdentityBeacon | 6/40 |
| 173 | subkey_beacon family (14 wire-types!) | 20/40 |
| 174 | 0x1097, 0x136a, 0x1096 | 23/40 |
| 175 | (coverage indicator added — UI only) | 22/40 |
| 176 | 0x5d1 PlayerManagerSelfIdent (synthesized, not captured) | 22/40 |
| 179 | 0x8e6, 0x40a/0x1be (HandshakeBlob76), 0x9fc | 26/40 |
| 183 | 0xa4, 0x1033 | 28/40 |
| 190 | 0x5b2, 0xa95 | 30/40 |
| 191 | 0x1067 VivoxConfig | 31/40 |
| 192 | 0x663 LevelDescriptor | **32/40 (80%)** |

Notable: wake 173's subkey_beacon family decoder reads the
inner type_header at +0x18 and recovers the type_id from the
body itself — one DECODERS entry covers 14 wire-types. The
wake-191/192 string-decoders (VivoxConfig / LevelDescriptor)
surface actual captured strings (production Vivox URLs,
level names like `"NewWorld_VitaeEterna"`) inline — most
visually informative decoders so far.

## Phase 5: Dashboard cross-check test graph (wakes 162, 166, 172, 178, 184, 185, 196)

Each wake added one structural invariant pinning a different
dashboard property. Together they form a graph: code →
data → prose → conventions, all auto-validated.

| Wake | Cross-check |
|---|---|
| 162 | `categorize_doc`, `_enrich_families` pure helpers (24 tests). |
| 166 | `parse_sections` covers every `__all__` export. |
| 172 | Every live-decoder preset hex round-trips through the matching Python codec. |
| 178 | JS `TYPE_ID_TO_LDTYPE` ↔ Python `LDTYPE_TO_TYPE_IDS` agree in both directions. |
| 184 | Every 3+ char `0xNNN` in "How it works" prose is in `LDTYPE_TO_TYPE_IDS`. |
| 185 | Every covered ldtype has at least one preset button. |
| 196 | Every `_shadow_*` or `_validate_*` helper in `rep_responder.py` has a ≥6-test lockdown file. |

A typo or drift anywhere in this graph fails loudly with a
precise pointer at the broken row. The wake-179 worklog
documents the cross-check catching a real 1-byte preset typo
*before* commit.

## Phase 6: Findings tab evolution (wakes 156, 163, 180, 189, 193, 194)

7 → 13 cards across 4 themed categories.

| Wake | Card |
|---|---|
| 156 | (hash-hunt closure + state-10 promotion — 2 cards) |
| 163 | (categorization itself — Wire-level finding / Research closure / RE breakthrough / Architecture) |
| 180 | Sub-system families (wake-121 cross-correlation). |
| 189 | Codec audit arcs both closed at 0 gaps. |
| 193 | 80% live-decoder coverage. |
| 194 | rep_responder integration foundation proven safe. |

Final card distribution: 5 Wire-level findings, 5 Research
closures, 2 RE breakthroughs, 1 Architecture. The wake-180
through wake-194 cards prove the "zero new infrastructure"
property — each is a single dict entry in `load_findings()`,
auto-rendered + auto-linkified + auto-categorized + auto-
validated by the existing dashboard machinery.

## Phase 7: Cross-tab linkify (wakes 177, 181, 182, 184, 186)

Every covered wire-type mention on the dashboard — JS-
rendered or static HTML — became a one-click link to the
live decoder.

| Wake | Surface |
|---|---|
| 177 | Findings cards (regex-replace 0xNNN mentions). |
| 181 | Wire Types catalog cells + document-wide click handler. |
| 182 | Recent-activity strip wake titles. |
| 184 | DOM walker for static "How it works" prose. |
| 186 | Wire-type family notes, analysis-doc summaries, decompile signatures, FAQ. |

After this arc, the same wire-type ID (e.g. 0x1033) is
clickable from 4-5 different dashboard places — visitors
hitting any of them reach the live decoder in one click.

## Phase 8: README badges + retrospective (wakes 168, 170, 195)

| Wake | Shipped |
|---|---|
| 168 | Recent-activity strip on Overview — last 6 wake headlines. |
| 170 | Deep-link Recent-activity rows to worklog line anchors via `?plain=1#L<line>`. |
| 195 | 3rd shields.io endpoint badge (live-decoder coverage). |

## What's still open

The codec library + dispatcher remain steady at 40/40 captured-
type coverage; the live decoder, dashboard cross-check graph,
and Findings tab are mature. The remaining open work falls
into three buckets:

1. **The actual emission swap** (phase 2D from the
   rep_responder arc). Wakes 187/188 proved it's safe; a
   future wake replaces `_send_replay_message(_heartbeat_msg)`
   with dispatcher-encoded fresh bytes, gated behind a feature
   flag. Requires runtime validation on a real-GPU host.
2. **The remaining 8 uncovered captured types** (0x0003,
   0x0008, 0x0013, 0x0635, 0x065c, 0x0ca4, 0x12f6, 0x16a0).
   Each has a real structural reason: encoder-only, meta-
   codec (chunked stream), or substantial variable-length-
   records complexity.
3. **State-10 runtime test** — same as wake 150 retro
   item #1. The wake-112 RE finding pins the predicate
   (`*(int*)(wrapper+0xa0) == 2`) and trigger (wire type
   0x5d1, codec wire-bound wake 112); the wake-176
   addition makes it inspectable on the dashboard. The
   actual test still needs a real-GPU host.

## Working style notes

- All wakes still cap at ~30 min and produce one commit. The
  wake-150 retrospective's notes still apply.
- The 7 cross-check tests changed the workflow's risk
  profile: coverage growth (live decoder, codecs, etc.) is
  now near-zero-risk because the tests catch every typo /
  drift mode automatically.
- The "shadow → lockdown" pattern from wakes 157/158 +
  187/188 is now a tested invariant (wake 196). Any future
  rep_responder integration step that doesn't follow it
  fails the build.
- Findings cards remain "zero new infrastructure" —
  each is a single dict entry. The wake-180-onward additions
  prove the dashboard machinery scales for curated-narrative
  maintenance.
