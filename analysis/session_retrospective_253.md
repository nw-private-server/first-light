# Wakes 228-253 — fourth-stretch milestones (state-machine closure arc)

A 26-wake continuation of the
[wake-150](session_retrospective_150.md),
[wake-196](session_retrospective_196.md), and
[wake-227](session_retrospective_227.md) retrospectives. Where
wakes 197-227 grew the cross-check graph and pushed live-
decoder coverage to 90%, wakes 228-253 **closed the post-V3
state-machine RE question at the static-RE level**. The
write-ups for all 4 state-spawn transitions (10→11, 11→12,
12→13, 13→14) now have writers, predicates, and trigger
chains identified; the remaining open thread (specific
replica-creation wire-type) is documented as runtime-dependent.
Each wake is a single commit; the per-wake trail lives in
[`autonomous_worklog.md`](autonomous_worklog.md).

## Snapshot (as of wake 253)

- **456 tests passing** (+1 skipped), unchanged from wake 227.
  The structural-pinning growth observed wakes 207-227
  (cross-check graph 9 → 18) settled at 19 with the wake-231
  decision-doc README invariant.
- **State-machine RE arc closed at static-RE level**:
  - 10 → 11: `wrapper[+0xa0] == 2`, `PlayerManagerSelfIdentificationMsg`
    (wake 112).
  - 11 → 12: auto-fires once 10 → 11 lands (inverted check
    on same field).
  - 12 → 13: `wrapper[+0xbc8] != 0`, `LevelInfoChangedMsg`
    direct force OR `FUN_14645c660` soft writer (wake
    232/234).
  - 13 → 14: `wrapper[+0x252] != 0`, `FUN_142ffbc50` writer
    (wake 247), 5 local replica-system handlers as
    trigger chain (wake 249), upstream hits indirect-vtable
    wall at `0x14816cec0` (wake 252).
- **MVP server-side estimate**: 3 messages minimum
  (SelfIdent + LevelInfoChanged + replica-creation, the
  third being TBD-pending-runtime per wake 252).
- **21 Findings cards** on the curated tab, up from 17 at
  wake 227. Research closure now at 10 cards (the dominant
  bucket grew with the wake-251 methodology card).
- **19 cross-check tests** organized into the wake-218
  manifest. Stable at 19 since wake 231.
- **Convergence claim** (wake 252/253): phase-2D real-GPU
  validation AND NewProxy wire-type identification are both
  blocked on the same Frida-on-real-GPU step. Single
  unblocker.
- **Live dashboard** at
  https://nw-private-server.github.io/first-light/. README
  Gate-2 row updated through wake 253; 6 dashboard surfaces
  consistent on the wake-252 closure state.

## Phase A: Doc-freshness pass + analysis-doc typology (wakes 235-239, 244-246, 252)

The wake-227 retrospective implicitly assumed the project's
analysis docs were current. Reviewing them surfaced ~5 stale
docs (`queued_work.md` from wake-83 era, `ghidra_hunt_list.md`
from wake-109 era, etc.). Eight consecutive doc-freshness
wakes (235-239 + 244-246) refreshed every major analysis doc
+ introduced two reusable patterns:

| Wake | Commit | Doc | Pattern |
|---|---|---|---|
| 235 | `9fc6d67` | `queued_work.md` | "Major progress since wake N" header + strike-through closures |
| 236 | `9e9664c` | `ghidra_hunt_list.md` | Same pattern; surfaces state 13 → 14 as carry-over |
| 237 | `205c69e` | `state_machine_summary.md` | Cross-references between §§ 1, 4, 4½ |
| 238 | `cee85e9` | `MORNING_BRIEF.md` | Historical-snapshot header (frozen) |
| 239 | `e010bcb` | `integration_status.md` | Phase-2D update (rolling) |
| 244 | `5fed6d7` | wake-228 skeleton card | Drift correction + investigation-log genre |
| 245 | `9b3aaff` | `state_10_unblock_synthesis.md` | Forward-references footer (frozen) |
| 246 | `8c50620` | `selfident_wire_format.md` + `sub_system_id_hash_search.md` | Same pattern, 2 docs |

**Two patterns crystallized**:
- **Rolling-status docs** (`queued_work`, `integration_status`):
  refresh in place with strike-through closures + "Major
  progress since wake N" sections. Avoid delta-callouts
  (proven drift-prone at wake 229).
- **Snapshot docs** (`state_10_unblock_synthesis`,
  `selfident_wire_format`, `sub_system_id_hash_search`,
  `MORNING_BRIEF`): keep body frozen, add dated forward-
  references footer.

The decision criterion is documented in the wake-238
worklog: snapshot vs rolling depends on whether the doc
represents point-in-time decision support or a current-state
claim.

**Wake 252 added a 4th doc-genre** — "wall" (static-RE limit
reached, runtime handoff necessary). With existing genres
(finding / decision / investigation), the project now has a
4-genre RE artifact typology.

## Phase B: State-machine RE closure arc (wakes 232, 234, 241, 247, 249, 252)

The wake-227 retrospective's open item ("real-GPU runtime
test for state-10 unblock") was unblocked by static-RE
during this stretch. The arc had two distinct sub-arcs:

### Sub-arc B1: State 12 → 13 surfacing + correction (232, 234)

| Wake | Commit | Step |
|---|---|---|
| 232 | `79b68e1` | Surfaced the buried wake-13 state-12 finding (`wrapper[+0xbc8]` writer = `FUN_145a9fa00` called from `FUN_14645c660`) into `state_machine_summary.md` § 4½. **First substantive non-infrastructure wake since wake 217.** |
| 234 | `b93427f` | Caught and corrected wake-232's state-numbering error (it's the 12 → 13 gate, not 11 → 12 — surfaced by mining the worklog for the state-name table). Self-correction documented publicly. |

### Sub-arc B2: State 13 → 14 candidate-triage → Ghidra arc (241, 247, 249, 252)

The candidate-triage pattern made its first appearance and
proved its value.

| Wake | Commit | Step |
|---|---|---|
| 241 | `8f931b4` | Shipped `state_13_14_writer_investigation.md` — full candidate triage (4 tiers, ~18 functions ranked), alt hypothesis ("MVP may only need 2 messages"), 5 concrete next-step Ghidra actions. Broke the 10-wake deferral cycle. |
| 247 | `218254f` | **MAJOR**: Ghidra session decompiled the top-2 candidates. Tier-A (`FUN_146c60830`) was a false-positive constructor; **tier-B `FUN_142ffbc50` IS the writer**. Walks `wrapper[+0x1b8..+0x1c0]`, predicate match, notification callback. |
| 249 | `81b5ada` | **MAJOR**: Ghidra session decompiled all 5 caller xrefs. **Trigger chain identified**: callers are local replica-system handlers; `FUN_142ff8940` explicitly copies a 0x70-stride collection from `param_2[+0x7d0]` into the wrapper. MVP estimate revised: **3 server messages minimum** (SelfIdent + LevelInfoChanged + replica-creation, likely GridMate `NewProxy`). |
| 252 | `efa5cd1` | Upstream trace hits indirect-vtable wall at `0x14816cec0` — identifying the specific NewProxy wire-type is now runtime-dependent. Static-RE arc closed. |

**3 substantive Ghidra-driven RE findings in 12 wakes** —
the candidate-triage pattern + the writer-found update +
the caller analysis + the documented wall together form a
complete static-RE arc on a single high-priority question.

## Phase C: Dashboard cascade (Findings cards + cross-card sync)

Each RE finding propagated to multiple dashboard surfaces.
By the end of this stretch, 6 surfaces narrate the same
state-machine picture in increasing detail.

| Wake | Commit | Action |
|---|---|---|
| 230 | `daa1312` | Architecture card #2: "Three-retrospective session-arc skeleton" |
| 233 | `2907eb9` | RE breakthrough card for wake-232 state-12 → 13 finding |
| 240 | `36b15dc` | RE breakthrough card synthesizing all 4 state-spawn transitions |
| 242 | `cdda3ec` | wake-240 card updated to surface wake-241 alt hypothesis |
| 243 | `4d673fa` | README Gate-2 row gains the alt-hypothesis claim |
| 247 | `218254f` | wake-240 card updated: "writer NOT yet identified" → "writer identified" |
| 248 | `cf314aa` | README + wake-240 card propagation of wake-247 finding |
| 250 | `019f8c9` | wake-240 card final update: wake-249 trigger chain prose |
| 251 | `061a306` | Research closure card #10: methodology pattern (candidate-triage proven) |
| 253 | `44a3c33` | README Gate-2 row: wake-252 static-RE-exhausted + runtime-convergence claim |

The wake-240 synthesis card was updated **5 times** during
active RE — the highest edit-frequency Findings card so far.
That pattern (focal synthesis card during active research +
multiple discrete cards for results vs methodology vs walls)
worked well.

**Findings tab grew from 17 to 21 cards**:
- Research closure: 9 → 10 (+1: methodology card)
- Wire-level finding: 5 (unchanged)
- RE breakthrough: 2 → 4 (+2: wake-232 12→13, wake-240
  synthesis)
- Architecture: 1 → 2 (+1: skeleton card)

## Phase D: Cross-check graph + README maintenance (wakes 231, 226-243)

The wake-227 retrospective ended at 18 cross-checks. Wake
231 added the 19th (decision-doc README link, symmetric to
wake-207 retrospective ↔ README) and the graph has been
stable at 19 since.

| Wake | Commit | Cross-check |
|---|---|---|
| 231 | `3b335d7` | 19th: every decision doc has a README link |
| (none) | — | Graph stable at 19 wakes 231-253 |

README maintenance wakes (date refresh + state-machine row):

| Wake | Commit | Action |
|---|---|---|
| 226 | `470d293` | Current Status date 2026-05-05 → 2026-05-11 + phase-2D infrastructure note |
| 243 | `4d673fa` | Gate-2 row: wake-241 alt hypothesis surfaced |
| 248 | `cf314aa` | Gate-2 row: wake-247 writer-found |
| 249 | `81b5ada` | Gate-2 row: wake-249 trigger chain (3-message MVP estimate) |
| 253 | `44a3c33` | Gate-2 row: wake-252 static-RE-exhausted + convergence claim |

**6 Gate-2 row updates** during the state-machine arc —
matches the wake-240 synthesis card's 5 updates. Both
surfaces have been "the current state of the state-machine
question" anchor; after wake 253 both should be stable.

## Mid-stretch course-corrections

- **Wake 234** — state-numbering error in wake 232 (the
  surfaced finding is the 12 → 13 gate, not 11 → 12).
  Documented publicly rather than papered over.
- **Wake 241 → wake 249 → wake 252** — the alt hypothesis
  ("MVP may only need 2 messages") was directionally
  right but quantitatively off; revised to 3 messages
  after the caller analysis surfaced the replica-creation
  step. Each refinement shipped as a doc update on the
  same surfaces.
- **Wake 229** — collapsed the wake-196 retrospective
  delta callout to a forward-pointer at the wake-227 retro.
  Established the rule: when a doc has a "current state"
  mirror that's structurally redundant with a newer doc,
  collapse it.

## Open items as of wake 253

- **Real-GPU runtime path** — the single gating blocker.
  Both phase-2D validation (heartbeat emission swap) AND
  NewProxy wire-type identification require Frida on a
  real-GPU Windows host. Same Frida session resolves both.
- **NewProxy wire-type identification** — the only
  remaining static-RE-untouchable question. The wake-252
  wall report documents this; future Frida trace catches
  the call site immediately.
- **3rd capture target** — the wake-200 / wake-221
  decision doc's 0x065c reversal criteria still call out
  a second-capture comparison. Independent of the
  state-machine arc.

## See also

- [`analysis/session_retrospective_150.md`](session_retrospective_150.md)
  — wakes 1-150 (codec library + dispatcher + dashboard).
- [`analysis/session_retrospective_196.md`](session_retrospective_196.md)
  — wakes 151-196 (rep_responder ↔ dispatcher integration
  foundation).
- [`analysis/session_retrospective_227.md`](session_retrospective_227.md)
  — wakes 197-227 (90% live-decoder coverage + phase-2D arc).
- [`analysis/state_13_14_writer_investigation.md`](state_13_14_writer_investigation.md)
  — the wake-241 → 252 search log capturing the
  methodology + the wall.
- [`analysis/autonomous_worklog.md`](autonomous_worklog.md)
  — full per-wake trail.
