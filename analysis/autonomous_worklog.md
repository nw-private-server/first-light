# Autonomous worklog — extended session (wake 254 onwards)

This is the **active** worklog for the autonomous /loop session.
Earlier wakes (1-253) are archived in
[`autonomous_worklog_through_253.md`](autonomous_worklog_through_253.md);
each of the 4 retrospective docs ([wake 150](session_retrospective_150.md)
/ [wake 196](session_retrospective_196.md) /
[wake 227](session_retrospective_227.md) /
[wake 253](session_retrospective_253.md)) covers a coherent
multi-wake arc of that archive.

Split rationale: by wake 260 the worklog had grown to ~20,000
lines. Splitting at the wake-253 retrospective boundary
mirrors the retro-chain pattern — each retrospective marks
a natural arc closure, so wakes 254+ start a new arc whose
narrative will eventually be captured by a 5th retrospective.

Each wake is a single commit; the format mirrors the
archive's pattern: title + goal + built + verification +
blockers. Read top-down to follow progress.

---


## Wake 254 — fourth-stretch retrospective (wakes 228-253)

**Goal**: the state-machine RE arc is closed at
static-RE (wake 252 finding). The 26-wake stretch
from 228 (third-stretch retro shipped) to 253
(README final update) is a coherent arc — like
wakes 197-227 was a 31-wake arc captured at wake
228, this stretch deserves the same frozen-
snapshot treatment.

**Built**:

- **New file
  `analysis/session_retrospective_253.md`** (~200
  lines):
  - **Title**: "Wakes 228-253 — fourth-stretch
    milestones (state-machine closure arc)".
  - **Continuation** of the 3 existing retros
    (150 / 196 / 227); follows the established
    structure.
  - **Snapshot (as of wake 253)** — 5 bullets
    covering tests, state-machine arc closure, MVP
    server-side estimate, Findings tab growth
    (17→21), cross-check graph (stable at 19),
    convergence claim, dashboard.
  - **Phase A: Doc-freshness pass + analysis-doc
    typology** (wakes 235-239 + 244-246 + 252).
    Captures the rolling-status-vs-snapshot
    decision rule + the 4-genre RE artifact
    typology (finding / decision / investigation /
    wall) introduced at wake 252.
  - **Phase B: State-machine RE closure arc**
    (wakes 232/234/241/247/249/252). Split into
    two sub-arcs (B1 wake-12 → 13 surfacing +
    correction; B2 wake-13 → 14 candidate-triage
    → Ghidra arc → wall). Each row of each table
    has wake + commit + concrete step.
  - **Phase C: Dashboard cascade** (wakes
    230/233/240/242/243/247/248/250/251/253). The
    wake-240 synthesis card's 5 updates + the
    Findings tab growth + Gate-2 row's 6 updates.
  - **Phase D: Cross-check graph + README
    maintenance** (wakes 226/231/243/248/249/253).
    Documents the cross-check graph reaching its
    natural plateau at 19 (stable since wake 231).
  - **Mid-stretch course-corrections** (wakes 229
    / 234 / 241→249→252). Documents that
    corrections shipped publicly, not hidden.
  - **Open items**: the single real-GPU runtime
    blocker (which now serves both phase-2D AND
    NewProxy questions per wake-252 convergence),
    NewProxy specific wire-type, 3rd capture
    target.
  - **See also** section linking the 3 prior
    retros + the wake-241 investigation log +
    the worklog.

- **`README.md`** — new fourth-stretch retrospective
  link added in the Recent milestones section:
  > "Fourth-stretch retrospective (wakes
  > 228-253) — state-machine RE closure arc: all
  > 4 post-V3 state-spawn transitions ... have
  > writers + trigger chains identified at
  > static-RE level. Three Ghidra-driven findings
  > (wakes 232/247/249), one documented wall
  > (wake 252), and the candidate-triage
  > methodology pattern proven. MVP server-side
  > estimate: 3 messages minimum."

**Verification**:
- **wake-207 (retrospective ↔ README link)** test
  passes: all 4 retrospective files have README
  link entries ✓.
- **wake-225 (analysis-path existence)**: cited
  paths from the new doc all exist ✓ (the doc
  itself cites the 3 prior retros + the
  investigation log + the worklog).
- **`categorize_doc`** returns "Retrospective"
  for `session_retrospective_253.md` automatically.
- Tests **456 (+1 skipped)** — unchanged.

**Pattern note**: this is the **4th** session
retrospective. The session-arc skeleton card
(wake 228) said "Future arcs follow the same
pattern: ~30-50 wakes per retrospective, snapshot
+ 3-5 phases + open-items + forward pointer."
This retrospective covers **26 wakes**, slightly
under the predicted 30-50 range — but the arc has
a natural closure (state-machine RE done), so the
slightly-shorter stretch is justified by the
narrative.

**Cross-card maintenance**: the wake-228 session-
arc-skeleton Findings card already says "Three-
retrospective session-arc skeleton" with a "Future
arcs follow the same pattern" closing. That card
will need a tiny update at some future wake to
say "Four-retrospective" — but the prose's
"Future arcs follow ..." extensibility claim
already implicitly handles it. Deferring the
update unless the prose becomes load-bearing.

**Post-wake-253 forecast**:
- Real-GPU runtime work unblocks both phase-2D
  validation AND NewProxy wire-type ID
  simultaneously.
- After runtime data lands, expect a 5th-stretch
  retrospective covering the runtime-validation
  arc.
- Cross-check graph likely stays at 19 unless a
  new structural drift mode emerges.

**No new tests, no new code**. New retrospective
artifact + README link.

**Blockers:** None.

## Wake 255 — wake-228 skeleton card: 3-retro → 4-retro drift

**Goal**: the wake-254 fourth-stretch retrospective
landed but the wake-228 Architecture Findings card
still claims "Three-retrospective session-arc
skeleton". The wake-254 worklog noted "deferring
the update unless the prose becomes load-bearing".
The literal count claim in the title IS load-
bearing — a visitor lands on the card, reads
"Three-retrospective", but finds four
retrospectives linked from README. Direct drift,
correct.

**Built**:

- **`tools/build_site.py`** wake-228 skeleton card
  comprehensive update:
  - **Title**: "Three-retrospective session-arc
    skeleton" → "**Four-retrospective session-arc
    skeleton**".
  - **Opening**: "across three frozen
    retrospective documents" → "**across four
    frozen retrospective documents**".
  - **New 4th-retro entry** added with concrete
    summary:
    > "wakes 228-253
    > (`analysis/session_retrospective_253.md`) —
    > state-machine RE closure arc, all 4 post-V3
    > state-spawn transitions now have writers +
    > trigger chains identified at static-RE
    > level, with the wake-252 indirect-vtable
    > wall marking the static-RE limit (further
    > progress on NewProxy wire-type ID is
    > runtime-dependent)."
  - **"Future arcs" extensibility note** adjusted:
    "~30-50 wakes per retrospective" → "~25-50
    wakes per retrospective" (the wake-253 retro
    was 26 wakes, slightly below previous range).
    Explicit note on the wake-253 being slightly
    short + the state-machine closure providing
    a natural narrative anchor.
  - **4-genre artifact typology** surfaced
    explicitly in the prose:
    > "Three artifact genres now coexist:
    > retrospectives (frozen snapshots), decision
    > docs (closed questions, wake 221), and
    > investigation logs (search-in-progress
    > with candidate triage, wake 241). Wake 252
    > added a 4th genre: 'wall' — documented
    > static-RE limit, runtime handoff
    > necessary."

**Why this matters**: the card is the **Architecture-
bucket project-shape claim** for the dashboard. Its
content is load-bearing for visitors trying to
understand how the project documents its history.
Letting "Three-retrospective" sit while 4 exist
creates a credibility crack.

**Verification**:
- wake-225 (analysis-path existence): the card now
  cites all 4 retro paths; all 4 exist on disk ✓.
- wake-209 (paired card consistency): wake-188 +
  wake-204 pair unaffected.
- wake-218 (manifest citation): unaffected.
- Tests **456 (+1 skipped)** — unchanged.

**Pattern note**: this is the **2nd update** to
the wake-228 skeleton card (wake-244 was the
first — drift correction on cross-check count;
this is the second — count from 3 → 4 retros).
The wake-244 pattern ("describe by-wake-N state +
the since-then delta") was extended here with the
"slightly below the previous-arc range" comment —
giving the card a graceful-aging strategy for
future N-th retros.

**No new tests, no new code**. Single Findings
card prose extension.

**Blockers:** None.

## Wake 256 — wake-211 meta-card: "Stable at 19" annotation

**Goal**: cross-check graph has been at 19
invariants since wake 231 — 25 wakes of stability.
The wake-210 meta-pattern Findings card's prose
accurately reflects the wake-231 state but doesn't
signal that the graph has stabilized. Visitor
reading the card sees "19 invariants" + "becomes
test 20" but has no signal whether the graph is
actively growing.

**Built**:

- **`tools/build_site.py`** wake-210 meta-card
  closing line extended:
  - Added: "**Stable at 19 since wake 231** — no
    obvious structural drift mode remains
    unpinned in the current dashboard surface
    area; further cross-check additions would be
    incremental over-pinning without
    proportional value. The graph is now treated
    as essentially complete; future additions are
    expected only when a new structural surface
    (e.g. a new doc genre or a new generated-
    asset format) emerges."

**Why now**: also consistent with the wake-228
skeleton-card update at wake 255 ("4-genre artifact
typology established"). With the typology
explicit + the cross-check graph stable, the
dashboard's structural-pinning layer reads as
mature rather than active-growth.

**Verification**:
- wake-214 self-referential test (count): card
  claims 19 invariants, manifest sums to 19 ✓.
- wake-218 (citations): all 19 manifest wakes
  cited in card prose ✓.
- wake-222 (manifest uniqueness): unaffected.
- wake-224 (chart vs badge): unaffected.
- wake-225 (analysis-path existence): unaffected.
- wake-227 (manifest-vs-tests): unaffected.
- Tests **456 (+1 skipped)** — unchanged.

**Pattern note**: this is the 7th update to the
wake-210 meta-pattern card (initial creation
wake 211, count updates at 214/218/222/224/225/227/
231 as the graph grew). The "Stable at 19" line
is the **first stability annotation** on this
card — it marks the transition from
active-growth phase to maturity.

**Cross-card maturity signal**: combined with
wake-255's skeleton-card update ("Four-
retrospective" + 4-genre typology) and the
wake-253 retrospective's framing, the dashboard
now consistently signals **the project has
reached a static-RE plateau**. Future substantive
work is gated on runtime data (real-GPU host).

**No new tests, no new code**. Single Findings
card stability annotation.

**Blockers:** None.

## Wake 257 — Wall Findings card (22nd card, 4-genre typology completes)

**Goal**: the wake-252 indirect-vtable wall is the
4th-genre exemplar in the project's RE artifact
typology (finding / decision / investigation /
wall). The genre has been surfaced in:
- wake-252 worklog (where the typology was
  introduced)
- wake-255 skeleton card (4-genre typology made
  explicit)

But there's no dedicated Findings card for the wall.
The wake-251 methodology card sets precedent for
"genre exemplar" cards; the wall genre now has
enough grounding to merit its own card. Adding it
completes the 4-genre coverage on the Findings tab:
- Findings ⇄ result cards (e.g. wake-240 synthesis
  for state-machine RE).
- Decision ⇄ wake-200 update + the decision doc
  (no dedicated card, but the wake-200 card
  references it).
- Investigation ⇄ wake-251 methodology card.
- **Wall ⇄ this wake's card.**

**Built**:

- **`tools/build_site.py`** new Findings card
  inserted after the wake-251 methodology card:
  - **Title**: "Static-RE wall: indirect-vtable
    termination (NewProxy upstream case study)".
  - **Category**: Research closure (closes the
    question "how does static-RE terminate when a
    target isn't tractable?"). Not Architecture
    (that's project-shape); not RE breakthrough
    (no new finding). Research closure fits a
    pattern-documentation card.
  - **Wake**: 252.
  - **Summary** (~370 words): narrates the
    indirect-vtable termination at `0x14816cec0`,
    explains why walls are valuable (handoff
    points, not failures), explicitly establishes
    "wall" as the 4th RE artifact genre, and
    cross-references the wake-251 methodology
    card + the wake-228 skeleton (4-genre
    typology).
  - **Framing rule** stated: "Walls aren't
    failures — they're explicit handoff points
    to a different research method (here:
    runtime trace). Without a documented wall,
    future contributors might assume more
    static-RE could close the question; the
    wall card prevents wasted effort."

**Findings tab now**: **22 cards**:
- Research closure: 11 (+1) — still the
  dominant bucket.
- Wire-level finding: 5.
- RE breakthrough: 4.
- Architecture: 2.

**Verification**:
- wake-225 (analysis-path existence in card
  prose): cites
  `analysis/state_13_14_writer_investigation.md`
  + `ghidra_hunt_list.md` — both exist ✓.
- wake-218 (citations): unaffected.
- wake-227 (manifest-vs-tests): unaffected.
- wake-209 (paired card): unaffected.
- Tests **456 (+1 skipped)** — unchanged.

**Pattern note**: 15th Findings card added since
wake-163 categorization. The 4-genre exemplar
strategy:
- **Result cards** (RE breakthrough cluster):
  capture concrete RE findings.
- **Decision docs** (cross-referenced from
  Research closure cards): close specific
  questions with reversal criteria.
- **Investigation logs** (cross-referenced from
  Research closure methodology cards): document
  search-in-progress.
- **Wall cards** (Research closure): document
  static-RE termination + handoff to runtime.

Together the 4 genres cover the project's
research-product taxonomy. Each has at least one
exemplar Findings card on the dashboard now.

**Discoverability cascade**: a visitor scanning
Findings → Research closure now finds 11 cards
covering hypothesis closures (wake 155),
breakthrough surfacings (wake 192/200), pattern
docs (wake 210 meta, wake 251 methodology), and
the wake-257 wall card. The bucket is the most
varied in genres of any.

**No new tests, no new code**. Single Findings
card addition + worklog entry.

**Blockers:** None.

## Wake 258 — retrospective chain forward-pointers (wake-150, wake-227)

**Goal**: with 4 retrospectives in place (wake-150
/ 196 / 227 / 253), the wake-229 pattern of adding
"Continued in ..." pointers should extend to all
earlier retros. Wake-196 already has one (added at
wake 229 when wake-227 superseded its "current
state" framing). Wake-150 and wake-227 are missing.

A visitor landing on wake-150 currently has no
indication that 3 more retros exist downstream.
Same for wake-227 (the 4th retro at wake-253 isn't
mentioned in its "See also"). Drift correction.

**Built**:

- **`analysis/session_retrospective_150.md`** —
  "Continued in" pointer added after the
  introductory paragraph:
  - Mirrors the wake-196 pattern: callout block
    pointing to the IMMEDIATE next retro
    (wake-196) + naming the FULL chain
    (wake-150 → 196 → 227 → 253) + offering a
    direct jump to the latest (wake-253).
  - The wake-150 retro is the earliest; visitor
    landing there likely wants to fast-forward.
    Direct-jump option respects that.

- **`analysis/session_retrospective_227.md`** —
  "Continued in" pointer added after the
  introductory paragraph (above the snapshot
  block):
  - Mirrors the wake-196 pattern exactly: callout
    block pointing to wake-253 with a one-
    sentence summary (state-machine RE closure +
    wake-252 wall).
  - **"See also" section also updated**: dropped
    the wake-219 deltas-callout note for wake-196
    (it's now collapsed to a pointer per wake
    229) and added wake-253 as "the current-
    state-of-the-art retro".

**Chain consistency now**:
- **wake-150** → wake-196 (this wake's addition)
- **wake-196** → wake-227 (added wake 229)
- **wake-227** → wake-253 (this wake's addition)
- **wake-253** has no forward pointer (latest)

Visitor landing on any retro can follow the chain
forward, or jump to wake-253 directly from
wake-150's callout.

**Verification**:
- wake-207 (retrospective ↔ README link): all 4
  retros still linked from README ✓.
- wake-225 (analysis-path existence): the
  wake-150 callout cites
  `session_retrospective_196.md` and
  `session_retrospective_253.md`; the wake-227
  callout cites `session_retrospective_253.md`.
  All exist ✓.
- Tests **456 (+1 skipped)** — unchanged.

**Pattern note**: 4th iteration of the
"forward-pointer footer" pattern (others:
state_10_unblock_synthesis at wake 245,
selfident_wire_format + sub_system_id_hash_search
at wake 246). The pattern now covers BOTH
snapshot deep-dive docs AND chained retrospective
docs.

**Cross-card maintenance**: this completes the
forward-pointer cascade started at wake 229 (the
wake-196 retro's pointer-collapse). The
retrospective chain is now uniformly navigable
from any node.

**No new tests, no new code**. Two retrospective-
doc forward-pointer additions.

**Blockers:** None.

## Wake 259 — wake-228 skeleton card: explicit cross-links to genre exemplars

**Goal**: the wake-228 skeleton card mentions the
4-genre artifact typology (retrospective /
decision / investigation / wall) but doesn't
explicitly link to which Findings card surfaces
each genre. With the wake-257 wall card now
shipped, the 4-genre coverage is complete on the
Findings tab — but a visitor reading the skeleton
card has to discover the exemplars manually.

**Built**:

- **`tools/build_site.py`** wake-228 skeleton card
  closing paragraph rewritten to make genre →
  exemplar links explicit:
  - **Retrospectives**: "4 docs, this is their
    card".
  - **Decision docs**: "wake 221's 0x065c, cited
    from the wake-200 Findings card".
  - **Investigation logs**: "wake 241's
    state-13→14 search, surfaced via the wake-251
    methodology card".
  - **Walls**: "wake 252's indirect-vtable
    termination, surfaced via the wake-257 wall
    card".
  - Closing claim: "Each genre has at least one
    exemplar Findings card on the dashboard,
    completing the 4-genre coverage as of wake
    257."
  - "Three artifact genres now coexist" → "Four
    artifact genres now coexist on the Findings
    tab" — fixed the count (previously named 4
    genres but said "Three"; minor drift).

**Why this matters**: a visitor scanning the
dashboard sees Findings tab cards but has no
top-down map of "which Findings card represents
which artifact-genre". The skeleton card now
serves as that map. Each link is a wake-number
reference visitors can find via the Findings tab's
wake-number index.

**Verification**:
- wake-218 (wake-numbers cited in cross-check
  manifest card): unaffected; skeleton card isn't
  the meta-card.
- wake-225 (analysis-path existence): card prose
  still cites only the 4 retro paths (which
  exist); doesn't add new path references.
- wake-209 (paired card consistency): unaffected.
- Tests **456 (+1 skipped)** — unchanged.

**Pattern note**: this is the **3rd update** to
the wake-228 skeleton card (wake-244 cross-check-
count drift fix, wake-255 4-retro update, this
wake's cross-links). The card serves as the
"project-shape map" — its prose evolves as the
project grows.

**Drift surface evaluation**: this update relies
on the linked wake numbers (221, 200, 241, 251,
252, 257) being correct. If any of those cards
gets renamed/renumbered, this prose would drift.
The wake-218 + wake-225 cross-checks pin the
LATTICE of wake-numbers-in-card-prose for the
wake-210 meta-card; no analogous pin exists for
the wake-228 skeleton card. Adding one would be
a 20th cross-check (Doc/navigation drift bucket),
but feels premature with one card in this
specific class.

**No new tests, no new code**. Single Findings
card prose extension.

**Blockers:** None.

## Wake 260 — pause-reflection: what's left after 259 wakes

**Goal**: long-deferred pause-reflection wake. 259
wakes deep, the static-RE arc closed at wake 252
(documented wall), dashboard 4-genre typology
completed at wake 257, retrospective chain
uniformly navigable at wake 258, skeleton card a
project-shape map at wake 259. The recent pattern
has been small drift-correction wakes — each useful
but with diminishing marginal value. This wake
acknowledges the plateau and documents what
remains.

This entry is **a worklog reflection, not a code
change**. The loop's design accommodates this —
some wakes are stocktaking, not shipping. The
intention is to capture "where we are" so future
contributors (and future me) have a clear handoff
when runtime work resumes.

### Where we are

**The static-RE leg is genuinely complete.**

- **All 4 post-V3 state-spawn transitions** have
  writers + predicates + trigger chains:
  - 10 → 11: wake 112 (PlayerManagerSelfIdentificationMsg)
  - 11 → 12: auto-fires
  - 12 → 13: wake 232 (LevelInfoChangedMsg or
    second writer FUN_14645c660)
  - 13 → 14: wake 247 writer + wake 249 trigger
    chain + wake 252 wall.
- **40/40 captured wire-types** have Python
  codecs. 36/40 have JS live-decoder coverage
  (90.0% by design, per the wake-221 decision).
- **456 tests passing**, **19 cross-checks**
  organized into a 3-bucket manifest with 5
  self-referential pins on the wake-210
  meta-card.
- **Phase-2D infrastructure** (heartbeat emission
  swap behind 2 feature flags, both default off,
  proven byte-equivalent) ready for real-GPU
  flip.
- **22 Findings cards** across 4 categories
  covering all 4 RE artifact genres (finding /
  decision / investigation / wall).
- **4 retrospectives** chained forward
  (150 → 196 → 227 → 253).

### Where we're blocked

**One unblocker, two outcomes**: a real-GPU
Windows host running Frida traces would:
1. Flip the phase-2D feature flags and observe
   the gate-2 retry loop end-to-end (confirms or
   refutes the byte-equivalent-emission claim's
   runtime behavior).
2. Hook FUN_142ffbc50 or any of its 5 callers and
   catch the stack frame at call-time —
   identifies the specific replica-creation
   server message (the wake-252 wall's
   handoff-point).

These are NOT two separate unblockers — they're
the same Frida session producing both observables.
The convergence claim (wake 252/253) holds.

### What's left at static-RE

Almost nothing. Small follow-ups that don't
require runtime data:

1. **0x065c decision** (closed at wake 221) —
   could be revisited if a second capture lands,
   but that's a runtime artifact.
2. **Second-capture comparison** for
   identity-bundle persistence (called out in
   sub_system_id_hash_search) — also a runtime
   artifact.
3. **Cross-check graph** additions if a new
   structural drift mode emerges — the graph is
   marked stable at 19 since wake 231 per the
   wake-210 card's wake-256 annotation.

### What "completion" looks like

A natural stopping criterion for the static-RE
phase: **no concrete next-step questions a
contributor without runtime access could
productively investigate**. The wake-252 wall +
wake-258 chain + wake-259 skeleton-map signal
this state on the dashboard.

If a maintainer were resuming the project, the
clear next action is:
- Real-GPU Windows host or equivalent
  (Bootcamp / AWS Windows-Gaming / spare hardware
  per the wake-70 / wake-238 historical context).
- Frida session per `analysis/state_13_14_writer_investigation.md`
  wake-252 section ("A Frida hook on any of the
  5 callers catches the stack frame at call-time
  and resolves the question immediately").
- Flip `heartbeat_use_dispatcher = True` + observe
  the gate-2 retry loop.

### Reflections on the loop

- **Static-RE deferral cycles can be broken
  cheaply** via candidate-triage logs (wake 241
  → 247 → 249 pattern, surfaced as the wake-251
  methodology card). Worth shipping the log
  early when a question keeps deferring.
- **Dashboard surfaces compound** — by wake 253,
  6 surfaces consistently narrate the same
  state-machine claim. Each surface serves a
  different visitor lens (first-touch / Findings
  scan / deep-dive / chronological).
- **The 4-genre RE artifact typology** (finding
  / decision / investigation / wall) emerged
  bottom-up from the work, not top-down from
  planning. Wake 252 introduced "wall" because
  the wake-247/249 arc terminated in a way that
  didn't fit existing genres. Future wakes
  shouldn't pre-define genres; let them emerge.
- **Drift corrections compound favorably** in
  small wakes. The wake-258/259 retro-chain +
  cross-link work alone took ~2 wakes but
  produced a navigable structure. Spread over
  time, each step felt small.

### Forward-looking

If the loop continues past wake 260, the highest-
value targets are likely:
1. **Worklog file split** (deferred ~15 times)
   — the file is now ~1800+ lines. Splitting at
   wake 254 or wake 260 would mirror the
   retrospective-split pattern.
2. **Frame-budget for "no concrete drift to
   correct" wakes** — a soft policy like "if no
   substantive task fits the 30-min cap, write
   a reflection like this one instead of forcing
   small drift fixes" might be worth a Findings
   card.

But neither is urgent. The natural cadence may
shift toward longer wake intervals once the
loop's productive density drops.

**No code changes, no test changes, no doc
updates outside this worklog entry.** Pure
reflection. Tests **456 (+1 skipped)** unchanged.

**Blockers:** None.

## Wake 261 — worklog file split (wakes 1-253 archived)

**Goal**: the wake-260 reflection explicitly flagged
worklog-split as the highest-leverage carry-over
infrastructure task. The file had grown to
**~20,155 lines**. With 4 retrospectives in place
covering wakes 1-253, the wake-253 boundary is the
natural split point — mirrors the retrospective-
chain pattern.

**Built**:

- **`analysis/autonomous_worklog_through_253.md`**
  — new file containing the frozen wakes 1-253
  history (19,476 lines). Retains the original
  header ("extended session starting 2026-05-07")
  and content verbatim. This is the **archive**.
- **`analysis/autonomous_worklog.md`** — replaced
  with a new ~700-line active file:
  - New header explains the split + links the
    archive + names the 4 retrospectives that
    narrate the archived arcs.
  - Body continues from wake 254 onwards (wakes
    254-260 inherited from the archive split,
    plus this wake 261 entry).
- **`tools/build_site.py`** — `EXCLUDED` set
  extended to include
  `autonomous_worklog_through_253.md` in both
  `load_analysis_docs` and
  `load_decompile_annotations`.

**Verification**:
- `load_recent_wakes` scanner: still finds 6
  wakes (255-260) in the active file — the
  recent-activity strip works correctly ✓.
- wake-225 (analysis-path existence): no cards
  cite `autonomous_worklog.md` directly;
  unaffected.
- Tests **456 (+1 skipped)** — unchanged.

**Deferred drift-correction**: DASHBOARD.md,
CONTRIBUTING.md, and several analysis docs
(`ghidra_hunt_list.md`, `queued_work.md`,
`codec_coverage.md`, `state_machine_summary.md`,
`session_retrospective_196.md`) cite
`autonomous_worklog.md` for wake-N entries where
N < 254. The semantic target is now in the
archive. Fixing all of these is a batch drift-
correction worth a dedicated wake; not done here
to keep this commit reviewable.

**Why split now**: wake-260 reflection said
"file is now ~1800+ lines" — actually 20,155.
That 10x undercount was itself a signal the file
had crossed the readability threshold a while
ago.

**Pattern note**: 5th project-shape doc to be
split or archived (others: 4 retrospectives + the
wake-196 deltas-callout simplification at wake
229 + wake-238 MORNING_BRIEF historical-snapshot
header). "Freeze when it ages, fresh file when it
grows past readability" is now the project's
standard for accumulating-state docs.

**Blockers:** None.

## Wake 262 — wake-261 deferred drift: batch fix worklog references

**Goal**: the wake-261 worklog split left 7 docs
citing `autonomous_worklog.md` for wake-N entries
where N < 254. Those references semantically point
at the archive now. The wake-261 worklog explicitly
deferred the batch fix to a follow-up wake; this is
that wake.

**Built**: 7 doc references updated:

- **`DASHBOARD.md`** line 172: split-aware
  description "Active wake-by-wake history (wake
  254 onwards). Earlier wakes (1-253) in
  [archive]."
- **`CONTRIBUTING.md`** line 46: same pattern —
  "active ... onwards" + archive link.
- **`analysis/ghidra_hunt_list.md`** "wake-90-
  onward entries" pointer redirected to archive
  (wake 90 is pre-254).
- **`analysis/queued_work.md`** "wakes 66-83 in
  ..." pointer redirected to archive.
- **`analysis/codec_coverage.md`** "wakes 66-80"
  pointer redirected to archive.
- **`analysis/state_machine_summary.md`** "from
  the autonomous worklog" pointer redirected to
  archive.
- **All 4 retrospectives** (150 / 196 / 227 /
  253) "Each wake is a single commit; the per-
  wake trail lives in ..." pointers redirected
  to archive (since each retro's range is
  pre-254). The wake-253 retro's "See also"
  section also updated.

**Common pattern** used across all 7: cite the
archive as the primary target for pre-254 wakes,
with a parenthetical "wakes 254+ in active
`autonomous_worklog.md`" note. This preserves
both targets' discoverability.

**Verification**:
- wake-225 (analysis-path existence): card prose
  unaffected; this fix is on doc-to-doc links,
  not Findings-card prose.
- wake-207 (retrospective ↔ README): all 4
  retros still linked from README; this fix
  changes prose inside the retros, not their
  filename.
- Tests **456 (+1 skipped)** — unchanged.

**Remaining `autonomous_worklog.md` references**
(functional, NOT drift):
- `tools/build_site.py:191, 248`: EXCLUDED set
  entries (filter out the active worklog from
  doc indexing).
- `tools/build_site.py:442`: recent-wakes scanner
  reading the active worklog.

These are intentional — the active file should
NOT appear in the Findings-tab analysis-doc
index (it's append-only and refreshed every wake),
and the recent-wakes scanner should read the
active file (not the archive).

**Pattern note**: this is the 9th batch doc-
freshness wake (235/236/237/238/239 + 244/245/246
+ this wake's batch). The wake-261 split was the
infrastructure change; this wake propagates its
implications to all downstream references. After
this wake, "pre-254 worklog reference" is no
longer a drift mode anywhere in the repo.

**Cost summary**: 7 prose edits, each 1-3 lines.
Single batch commit.

**Blockers:** None.


## Wake 263 — archive header preamble (wake-261 follow-up)

**Goal**: the `autonomous_worklog_through_253.md`
archive (created at wake 261, references propagated
at wake 262) retained its original header
("Autonomous worklog — extended session starting
2026-05-07") which now reads as if the file is still
the active worklog. A visitor landing on the archive
directly — via a retrospective's "per-wake trail
lives in" pointer, for example — has no immediate
signal that this file is sealed history.

**Built**:

- **`analysis/autonomous_worklog_through_253.md`**
  — prepended an "Archive note" preamble:
  - **New title**: "Autonomous worklog — wakes
    1-253 (sealed archive)" (was "extended
    session starting 2026-05-07")
  - **Sealed-at-wake-261 callout** with the
    2026-05-11 split date.
  - **Forward pointer** to the active worklog
    + all 4 retrospectives as the recommended
    arc-level entry points.
  - **Frozen-state disclaimer**: the "Currently
    actionable" + "Task queue" sections below
    are historical record, not current
    priorities. Names the single current
    carry-over (real-GPU host).
  - **Original header preserved** below the
    preamble, separated by `---`, for
    historical context.

**Verification**:

- Read first 40 lines of the modified file — the
  new title appears at the top, the archive note
  is the first block of prose, the original
  header is preserved below the `---`.
- All existing links into the file (deep section
  references) remain valid: only the topmost
  H1 + intro block changed; no anchors below
  are affected.
- Tests **456 (+1 skipped)** — unchanged. No
  code, no `build_site.py` impact (archive isn't
  surfaced in the dashboard's Findings index,
  per wake-261's EXCLUDED set).

**Snapshot-doc scan (option e, opportunistic)**:
checked `frida_hook_audit.md` and
`community_archives_survey.md` as candidates from
the wake-263 menu's option (e). Both are
appropriately frozen: the Frida audit is a one-
shot suspicion-sort of `tools/frida_dtls_hook.js`,
and the community-archive survey is a wake-99
verdict ("not protocol-relevant") on five
maintainer-added archives. Neither is a rolling-
status doc; both are correctly frozen by nature.
**No drift to fix.**

**Pattern note**: this is the third wake in the
wake-261 cascade (261 split → 262 reference
propagation → 263 archive self-description). The
archive can now stand on its own — a visitor
arriving at it directly knows immediately what it
is, when it was sealed, and where to find current
state. After this wake, the worklog-split
infrastructure is fully self-describing.

The cascade also surfaces a small meta-finding:
when a file is split or archived, the **three
follow-on concerns** are (1) downstream
references, (2) the archive's own self-
description, (3) any tooling that indexed the
original. Wakes 261/262/263 hit (1) and (2);
(3) was solved at wake 261 itself via the
EXCLUDED-set update in `tools/build_site.py`.
That's a complete pattern — file it for any
future split (the worklog will inevitably need
another split around wake ~500 if the autonomous
mode continues).

**Cost summary**: 1 file edit, ~25 lines of new
prose. Single targeted commit.

**Blockers:** None.


## Wake 264 — README "Recent milestones" reorder (newest-first)

**Goal**: the README's "Recent milestones" list
had been chronological (wakes 1-150 first, 228-
253 last) since the first retrospective shipped.
For a return visitor — the dominant audience for
this section, since first-time readers go to
"Current status" or the live dashboard — the
most recent achievement is the most useful
"where are we now" signal. Long-deferred minor
drift fix, finally landing.

**Built**:

- **`README.md`** — reversed the 4-bullet
  Recent milestones list:
  - **Now first**: Fourth-stretch retro (228-
    253) — state-machine closure.
  - **Then**: Third-stretch (197-227) — 90%
    live-decoder + cross-check graph.
  - **Then**: Second-stretch (151-196) —
    dispatcher integration foundation.
  - **Last**: 150-wake retro (1-150) — codec
    coverage + dispatcher build.
  - Header relabeled "**Recent milestones**
    (newest first)" so the ordering convention
    is explicit and survives future additions.

**Verification**:

- All 4 retrospective links unchanged — wake-207
  cross-check ("every retrospective doc must
  have a README link") still satisfied.
- Wake-225 cross-check (analysis-path existence)
  unaffected — same paths, same files.
- `.venv/bin/python3 tools/build_site.py`
  re-ran clean.
- `pytest server/javelin -q` → **456 passing,
  1 skipped** (unchanged).

**Pattern note**: this is a small UX
correction, not a doc-freshness wake. The
question wasn't "is the content stale" — it was
"is the ordering optimal for the actual reader
flow". The header annotation ("newest first")
is the structural fix: future arc-closures
(fifth-stretch retro etc.) will naturally land
at the top without needing to remember a
convention.

**Why this ordering benefits return visitors**:
the wake-228-253 retrospective is the surface
that explains the most recent state-machine
RE arc + the static-RE limit (wake 252's
indirect-vtable wall). That's the *current*
status of the most active work-stream — far
more relevant to "what should I work on" than
the wake-1-to-150 codec-build narrative, which
is now stable infrastructure.

**Cost summary**: 1 prose reorder, ~10 lines
diff. Single targeted commit. Smallest possible
change to address a long-recognized minor
issue.

**Blockers:** None.


## Wake 265 — wake-200 Findings card cleanup

**Goal**: the wake-200 "Remaining 4 uncovered
wire-types" card had been updated several times
(216 after 0x0635 ship, 217 after 0x12f6 ship,
221 after the decision doc) and the prose
accumulated meta-commentary about its own
update history — "Updated wakes 216, 217, and
221; this card now tracks the current count
rather than the wake-200 snapshot of 6". That
sentence is process-narration; the card should
just present current state. The change history
belongs in git + worklog, not in the visitor-
facing card.

**Built**:

- **`tools/build_site.py`** — rewrote the
  wake-200 card summary (~33 lines → ~28 lines):
  - **Removed**: meta-commentary about update
    wakes ("Updated wakes 216, 217, and 221;
    this card now tracks...").
  - **Restructured**: clearer three-block
    organization with **bold labels** —
    "**Three are structurally unable to add**"
    (lists 0x0003, 0x0008, 0x0013 with their
    structural reasons) → "**The fourth is a
    deliberate decision**" (0x065c + decision-
    doc pointer) → complexity reference
    (wake 213's 0x0635 + wake 217's 0x12f6 as
    upper-end comparators).
  - **Preserved**: the decision-doc path
    citation (wake-225 cross-check), the
    "90.0% is the floor by design, not by
    accident" closer, and all the technical
    details (record counts, byte sizes,
    structural categorization).

**Verification**:

- `.venv/bin/python3 tools/build_site.py` →
  clean (decompiles 46, replay_decoded 177).
- `pytest server/javelin -q` → **456 passing,
  1 skipped** — unchanged.
- Wake-225 cross-check: `analysis/decision_
  0x065c_live_decoder.md` citation preserved;
  cross-check still satisfied.
- Wake-218 cross-check (manifest-wake citation
  in wake-210 card): wake-200 is not a
  manifest wake, no impact.
- `grep -rn "wake-200 snapshot\|Updated wakes
  216"` confirmed no other code depends on
  the removed phrasing (only one stale
  worklog-archive entry references it as
  historical context, which is correct).

**Pattern note**: this is a *prose-cleanup*
wake, not a content-update wake. The card's
information content is unchanged; what
shifted is the signal-to-noise ratio. The
removed meta-commentary was a fossil from the
period when the card was actively being
amended — once the answer stabilized (wake
221's decision doc fixed the 0x065c question
definitively), the update trail became
clutter.

**General principle (worth recording)**:
visitor-facing prose should describe *what
is true*, not *how the truth was
established*. The latter belongs in commits +
worklog. When prose accumulates an "Updated
wakes X, Y, Z" tail, that's a signal the
content has stabilized and the tail can be
removed. Filing this as a Findings-card
hygiene heuristic for future cleanup passes.

**Cost summary**: 1 file edit (~30-line prose
rewrite). Single targeted commit. The
information content + critical citations are
preserved; only the meta-commentary was
removed.

**Blockers:** None.


## Wake 266 — wake-225 docstring extension

**Goal**: bring the wake-225 cross-check test's
docstring up to the "**Drift mode:** … /
**Remediation:** …" convention already
established by wake-218 (concrete drift example
with named files) and wake-231 (explicit
labeled sections). The wake-225 test had a
reasonable docstring but lacked both a concrete
drift example and an explicit Remediation line.

**Built**:

- **`server/javelin/test_build_tools.py:979`**
  — rewrote
  `test_findings_card_analysis_doc_references_exist`
  docstring (~16 lines → ~28 lines):
  - **Added concrete drift example** in the
    "Drift mode:" paragraph: hypothetical
    rename of
    `decision_0x065c_live_decoder.md` →
    `decision_0x065c.md`, illustrating exactly
    how the wake-200 card prose would silently
    desync from the file system.
  - **Added explicit Remediation paragraph**
    naming `tools/build_site.py` as the card-
    prose location (so a failing test points
    the reader at the right file to edit).
  - **Clarified scope of the regex**: the
    original docstring claimed paths without
    the `.md` suffix were also matched
    ("with the .md inferred") — the regex
    `r"analysis/[A-Za-z0-9_./-]+\.md"` actually
    requires the suffix. Replaced the inaccurate
    parenthetical with a correct one explaining
    the deliberate scope choice (suffix-less
    references would be ambiguous between file
    and directory paths).
  - **Preserved** the symmetric-counterpart
    framing (wake-207 pins file → mention;
    wake-225 pins mention → file).

**Verification**:

- `pytest server/javelin/test_build_tools.py::
  test_findings_card_analysis_doc_references_exist`
  → 1 passed.
- `pytest server/javelin -q` → **456 passing,
  1 skipped** — unchanged.
- No `build_site.py` impact (docstring-only
  edit, no code path change).

**Pattern note**: this completes the docstring-
convention parity across the three "self-
referential" cross-check tests in the
Doc/navigation bucket (218 / 225 / 231). All
three now have:
1. A `wake N` opening identifier.
2. A "Drift mode:" paragraph with a concrete
   named-example.
3. A description of the assertion mechanism.
4. An explicit "Remediation:" paragraph (or
   embedded remediation in the assertion
   message — 218/225 now both; 231 has it
   embedded only).

A future drift mode worth pinning would be
"every cross-check test has a 'Drift mode:'
labeled paragraph", but with only 18-19 tests
in CROSS_CHECK_MANIFEST this is overengineering
— spot-check by convention rather than test
enforcement. Filing the heuristic only.

**Why this matters less than it sounds**: the
wake-225 test was already passing and protecting
against the drift. The change is purely
documentation — a future maintainer reading the
docstring at the moment of failure now gets a
concrete mental model of the drift in 3 seconds
instead of having to reconstruct it from the
assertion message + minimal context. Net cost
~10 minutes of docstring work; net benefit
distributed across every future test failure.

**Cost summary**: 1 docstring rewrite, ~28 lines
of new prose. Single targeted commit. No code-
behavior change.

**Blockers:** None.


## Wake 267 — DASHBOARD.md deprecation + CONTRIBUTING.md drift fixes

**Goal**: the wake-267 forward menu listed
"DASHBOARD.md / CONTRIBUTING.md drift scan —
both touched at wake 262 but only the worklog-
pointer line; quick read for anything else that
aged out." The actual finding was much worse
than a scan was sized for: DASHBOARD.md hasn't
been substantively updated since wake 90
(2026-05-09 stamp at top), and CONTRIBUTING.md
had multiple severely stale "current blocker"
sections describing closed work as still open.

**Built**:

**DASHBOARD.md** — added a **deprecation
preamble** rather than refreshing the body. The
wake-90 content (258 tests, 35/40 codecs, state-
10 RE picture) is severely out of date, but the
file isn't actually the canonical project status
anymore — the auto-generated live dashboard at
`nw-private-server.github.io/first-light` is.
The preamble:
- Warns the file is a wake-90 snapshot, no
  longer maintained.
- Points to the live dashboard as the
  canonical surface for current numbers.
- Points to the README "Recent milestones"
  section + 4 retrospectives for narrative.
- Notes the wake-252 state-machine progression
  the wake-90 content predates.
- Preserves the wake-90 body for historical
  context (CRC32 finding + typeregistry mapping
  are still substantive findings worth
  preserving in their original framing).

Rationale: refreshing DASHBOARD.md would
duplicate effort with the live dashboard
forever (every codec ship, every test count
shift, every state-machine update). Deprecation
+ pointer is one-shot.

**CONTRIBUTING.md** — 4 targeted prose fixes:

1. **Line ~25 (Quick start test count)**:
   "410+ passing" → "450+ passing". Added a
   tip about why `pytest server/javelin/` not
   bare `pytest` (the `server/test_client.py`
   sys.exit-on-import issue we hit at wake
   264).

2. **Reference docs section (line ~43-45)**:
   replaced the wake-150 retrospective pointer
   with the wake-253 retrospective (newest is
   more useful for return visitors per the
   wake-264 ordering decision). Replaced the
   stale `state_10_unblock_synthesis.md` pointer
   with `state_machine_summary.md`, noting that
   the state-10 work is now closed and the
   active blocker is runtime-side.

3. **Section "2. Reverse engineering" header +
   intro (line ~74-82)**: rewrote the framing.
   The old prose said "the current blocker is
   understanding why the client retries V3 …
   decompile FUN_14644a070" — that decompile
   has been done. New framing notes all 4
   post-V3 state-spawn transitions are now
   RE'd at static level (cites wakes 111-112,
   232/234, 247/249, 252), names the wake-252
   indirect-vtable wall, and pivots to the
   remaining static-RE worth pursuing
   (`FUN_146b3c250 + 0x58f` destroy trigger;
   NewProxy / GridMate replica identification).
   Points to
   `state_13_14_writer_investigation.md` for
   the candidate-triage methodology.

4. **Section "3. Python/server" rep_responder
   bullet (line ~92)**: rewrote. The old prose
   said "promote one wire-type at a time to
   authoritative dispatcher consumption.
   0x15d (heartbeat) is the obvious first
   candidate" — wake 204 SHIPPED that. New
   prose acknowledges wake 204's emission swap
   + wake 208's counter-advance, notes both are
   awaiting real-GPU validation, and renames
   the open question to "Next wire-type
   promotion candidate" with a concrete way to
   find candidates (search `_shadow_decode_record`
   callers in `test_shadow_decode.py`).

**Verification**:

- `.venv/bin/python3 tools/build_site.py` →
  clean.
- `pytest server/javelin -q` → **456 passing,
  1 skipped** — unchanged.
- Wake-225 cross-check (analysis-path
  existence): all new
  `analysis/state_machine_summary.md` and
  `analysis/state_13_14_writer_investigation.md`
  references resolve to actual files.
- Wake-207 cross-check (retrospective README
  link): unaffected, README links unchanged.
- Wake-231 cross-check (decision-doc README
  link): unaffected.

**Pattern note**: this is the largest single-
wake doc-freshness fix in the wake 235+ doc-
freshness pass family. CONTRIBUTING.md drifted
more than expected because it was last
substantively edited at wake 167 (per `git log`)
and the state-machine RE arc + dispatcher
integration arc both happened *after* that
edit. The "current blocker" framing was the
most-misleading single piece of prose in the
repo as of this wake's start.

**Why DASHBOARD.md got deprecation instead of
refresh**: the cost-benefit math. Refreshing
would mean every codec ship, every state-
machine update, every test-count shift needs a
DASHBOARD.md edit *in addition to* the
auto-regenerated live dashboard. That's
duplicate maintenance with zero net visitor
benefit (the live dashboard is what visitors
actually consume). The deprecation preamble
solves the drift permanently — future visitors
land on a clearly-marked snapshot and are
routed to the live source.

**Generalizable principle (worth recording)**:
when a manually-maintained doc is superseded
by an auto-generated equivalent, *deprecate*
the manual version with a pointer rather than
refreshing it. The auto version will always
win the freshness contest; trying to keep the
manual version in sync forever is a
maintenance trap. This is the same logic that
drove the wake-261 worklog split (freeze the
large file, fresh file for new work) but
applied to a "is it the canonical source"
distinction rather than a size distinction.

**Cost summary**: 5 file edits across 2 files
(1 DASHBOARD.md preamble, 4 CONTRIBUTING.md
section rewrites). Largest doc-freshness wake
in months; touched the two highest-leverage
"first impression" docs after README.

**Blockers:** None.


## Wake 268 — Findings-card prose-tail scan (wake-265 hygiene heuristic applied)

**Goal**: follow the wake-265 hygiene principle
("visitor-facing prose describes what is true,
not how the truth was established") across the
remaining Findings cards. The wake-265 cleanup
caught the wake-200 card; this wake checks
whether the same pattern recurs elsewhere.

**Found**: 2 cards with prose-tail accumulation
+ 1 card with stale count drift (caught by the
scan but not the cross-check graph because it
was a parenthetical, not a primary claim):

1. **Wake-192 card** ("Live decoder addresses
   90%..."): closed with
   "Updated wake 219 after wake-217's 90.0%
   crossing; the original wake-192 snapshot was
   80% (32/40)." — update-trail meta-commentary.
   Also contained
   "(now 14 tests after wakes 207/209/210/214/218)"
   referring to the cross-check graph — actual
   manifest now at **19 tests**, not 14. Stale
   parenthetical not caught by wake-214 (which
   pins the wake-210 card, not other cards'
   references to the same count).

2. **Wake-228 card** ("Four-retrospective
   session-arc skeleton"): contained
   "(which the wake-227 retro captured at 18
   invariants; the graph has since grown to 19
   with five self-referential pins on the meta-
   pattern card itself)" — same drift mode as
   above. Also contained
   "the wake-196 doc's post-snapshot deltas
   callout was trimmed at wake 229 from a
   verbose state-mirror to a one-line pointer
   once the wake-227 doc superseded it" — pure
   process-narration; the trimmed result is
   what visitors see today, the trim event is
   irrelevant.

**Built**:

**`tools/build_site.py`** — three prose edits:

- **Wake-192 card**:
  - Removed "Wake-192-era additions render..."
    → "Captured-string rendering surfaces..."
    (the wake-192 era specificity wasn't doing
    work; the *what* is what matters).
  - Replaced "(now 14 tests after wakes
    207/209/210/214/218)" with "(see the
    wake-210 cross-check meta-pattern card for
    the full graph)" — indirects the count
    through the wake-214-pinned card so it
    stays current automatically.
  - Removed the "Updated wake 219..." tail
    entirely — terminal sentence ("upper-end
    complexity shapes covered to date") now
    leads into the cross-check parenthetical
    cleanly.

- **Wake-228 card** (cross-check parenthetical):
  - Replaced "(which the wake-227 retro
    captured at 18 invariants; the graph has
    since grown to 19 with five self-
    referential pins on the meta-pattern card
    itself)" with "(see the wake-210
    meta-pattern card for current count, with
    five self-referential pins on the meta-
    card itself)".

- **Wake-228 card** (wake-229 trimming
  narration):
  - Removed "the wake-196 doc's post-snapshot
    deltas callout was trimmed at wake 229
    from a verbose state-mirror to a one-line
    pointer once the wake-227 doc superseded
    it." Sentence boundary now connects "...
    forward pointer to the next." directly to
    "The wake-207 cross-check pins each doc..."

**Verification**:

- `.venv/bin/python3 tools/build_site.py` →
  clean.
- `pytest server/javelin -q` → **456 passing,
  1 skipped** — unchanged.
- Wake-214 cross-check (wake-210 card count
  matches manifest): not touched, still
  satisfied.
- Wake-218 cross-check (wake-210 card cites
  every manifest wake): not touched, still
  satisfied.
- Wake-225 cross-check (analysis paths exist):
  no analysis-path edits, no impact.

**Pattern reinforced**: the wake-265 hygiene
heuristic is now demonstrably useful. Three
cards (200/192/228) had the same accumulation
pattern; the heuristic produced cleaner prose
in all three with no information loss. Filing
the heuristic into the Findings-card writing
convention by reference rather than as a new
test (over-pinning concern from wake-227's
"graph is essentially complete" note).

**Second-order observation**: cards that
reference *other* cards' numeric claims should
indirect through the canonical card rather
than restating the number. The wake-214 cross-
check protects the wake-210 card's count; any
card that *cites* the count without going
through wake-210 becomes a drift target
unprotected by the cross-check graph. The
indirection pattern ("see the wake-210
meta-pattern card") solves this without adding
another cross-check (which would itself need
maintenance).

**Cost summary**: 3 prose edits in one file
(`tools/build_site.py`). Modest change but
applies the wake-265 principle systematically.
Two cards now tighter + one parenthetical
drift fixed.

**Blockers:** None.


## Wake 269 — wake-218 + wake-231 docstring symmetry with wake-225 convention

**Goal**: bring the wake-218 and wake-231 cross-
check test docstrings up to the explicit
"Drift mode: … / Asserts: … / Remediation: …"
labeled-section convention that wake-225 was
brought to at wake 266. Convention parity
across all three "self-referential / symmetric"
Doc/navigation tests means a future reader hits
the same shape regardless of which test fires
first.

**Built**:

**`server/javelin/test_build_tools.py`** — two
docstring rewrites:

- **wake-218
  (`test_findings_meta_card_cites_every_manifest_wake`)**:
  - Restructured into explicit labeled
    paragraphs (Drift mode / Asserts /
    Remediation).
  - Replaced the stale "keep the total count at
    14, and pass wake-214's test" with the
    generic "keeping the total count consistent
    with the manifest size" (the manifest is
    currently at 19; the 14 was the wake-218
    write-time count). Drift-mode prose now
    survives manifest growth.
  - Added explicit Remediation paragraph
    naming `tools/build_site.py` as the prose
    location.
  - Also: updated an inline `#` comment from
    "(14 invariants, &lt;30 lines, ~320 lines,
    etc)" to "(invariant count, line-length
    numbers, etc.)" — drift-resilient phrasing.

- **wake-231
  (`test_every_decision_doc_has_readme_entry`)**:
  - Already had explicit "Drift mode:" label
    (added when the test was written).
  - Added explicit "Asserts:" label (was just
    a paragraph break).
  - Added explicit "Remediation on failure:"
    paragraph naming the README "Design
    decisions" section as the edit target.
  - Extended drift-mode example with concrete
    failure consequence ("a fresh decision doc
    can sit in `analysis/` indefinitely without
    any reader landing on it from the project
    entry surface") — same hygiene principle
    as wake-225's wake-266 extension.

**Verification**:

- `pytest server/javelin/test_build_tools.py
  -q` → **55 passing** — both edited tests
  still passing.
- `pytest server/javelin -q` → **456 passing,
  1 skipped** — unchanged. Pure docstring
  changes, no behavior diff.
- No `tools/build_site.py` edits needed
  (docstrings don't surface in the dashboard).

**Convention parity now achieved across all
three Doc/navigation cross-check tests with
labeled sections** (wakes 218 / 225 / 231):

| Wake | Labels present |
|---|---|
| 218 | Drift mode / Asserts / Remediation ✓ |
| 225 | Drift mode / Asserts / Remediation ✓ |
| 231 | Drift mode / Asserts / Remediation ✓ |

The wake-207 (retrospective ↔ README link)
test is the natural next candidate to extend
this pattern to — its docstring is older and
uses prose paragraphs without labels. But
wake-207 predates the labeled-section
convention and lives in the Doc/navigation
bucket alongside the now-parity-converged
trio; extending the convention to it would be
a 4th iteration of the same pattern, not new
value. Filing the heuristic only.

**Pattern note**: this completes the "docstring
hygiene" mini-arc that started at wake 266
(wake-225 docstring extension) and continued
at wake 268's filing of the indirection
principle for numeric references. All three
self-referential tests now describe their
drift mode + remediation in a uniform shape —
a future maintainer reading any one of them
at test-failure time gets the same mental
model.

**Generalizable principle**: when one test in
a family is brought to a documentation
convention, the cost of extending the
convention to its siblings is small but the
value is uniform contributor experience.
Avoid letting docstring-convention parity slip
across test families — it's harder to fix
once the family has grown.

**Cost summary**: 2 docstring rewrites + 1
inline-comment fix in one file. Pure
documentation; no behavior diff.

**Blockers:** None.


## Wake 270 — 4-genre Findings card audit (caught wake-228 broken cross-link)

**Goal**: the wake-228 narrative card claims
"4 artifact genres now coexist on the Findings
tab" with named exemplars for each genre. This
wake verifies each named exemplar actually
exists on the dashboard, per the wake-225
cross-check principle but applied at the
narrative-prose level rather than the file
level.

**Found**: 3 of 4 genre claims hold up; **1
broken cross-link**:

| Genre | Claim | Status |
|---|---|---|
| retrospectives | "4 docs, this is their card" (= wake-228 itself) | ✓ |
| decision docs | "wake 221's 0x065c, cited from the wake-200 Findings card" | ✓ |
| investigation logs | "wake 241's state-13→14 search, surfaced via the wake-251 methodology card" | ✓ |
| walls | "wake 252's indirect-vtable termination, surfaced via the wake-257 wall card" | ✗ |

The wall card's `wake` field in `tools/
build_site.py` is **252**, not 257 — meaning
visitors looking at the dashboard see it as a
wake-252 card. There is no wake-257 card on
the dashboard at all. The git log shows the
wall Findings card was *created* at wake 257
(commit `2e5e46d`, "wall Findings card #22"),
but the data was stamped with `wake=252` (the
underlying finding wake). So the wake-228
prose was referring to the creation wake while
the dashboard surfaces the finding wake.

Also: "completing the 4-genre coverage as of
wake 257" is a stale date stamp — by the
wake-265 hygiene heuristic, this is
process-narration that aged out (the
completion is what visitors see today; the
date the milestone landed is not visitor-
relevant).

**Built**:

**`tools/build_site.py`** — wake-228 card
prose edit (~5 lines):

- **walls bullet**: replaced "wake 252's
  indirect-vtable termination, surfaced via the
  wake-257 wall card" with "wake 252's
  indirect-vtable termination, surfaced via
  its own wake-252 Findings card on this tab".
  This makes the cross-link discoverable for
  any visitor reading the wake-228 card (they
  can now look for and find the wake-252
  card).
- **investigation logs bullet** (minor): tweaked
  "wake 241's state-13→14 search" to "wake
  241's state-13→14 investigation doc" — the
  word "search" was vague; "investigation
  doc" parallels the other genre exemplar
  language and matches the actual artifact
  type (an analysis/`.md` doc).
- **Closing sentence**: removed "as of wake
  257" date stamp; closing sentence now reads
  "Each genre has at least one exemplar
  Findings card on the dashboard, completing
  the 4-genre coverage."

**Verification**:

- `.venv/bin/python3 tools/build_site.py` →
  clean.
- `pytest server/javelin -q` → **456 passing,
  1 skipped** — unchanged.
- Manual audit pass: all 4 genre exemplars
  now point to wake numbers that have actual
  Findings cards on the dashboard:
  - retrospectives: wake-228 (self) ✓
  - decision docs: wake-221 (decision doc on
    disk) cited from wake-200 card ✓
  - investigation logs: wake-241 (doc on
    disk) surfaced by wake-251 card ✓
  - walls: wake-252 doc + wake-252 card ✓

**Pattern note**: the wake-225 cross-check
pins **analysis-path** existence in Findings
prose, but not **wake-number** consistency
across cards. The wake-218 cross-check pins
manifest-wake citations in the wake-210 card
specifically. Neither catches the wake-228
broken cross-link because it's prose citing
*another card's wake number*, not a path or a
manifest wake.

**Could this become a cross-check?** Tempting,
but per the wake-227 "graph is essentially
complete" principle, the cost of pinning every
narrative cross-reference outweighs the
benefit. The wake-228 card's drift was caught
by a focused audit pass (~15 min). Future
cards' similar drift would be caught by
similar audits. Filing the audit pattern as a
periodic hygiene exercise rather than a
new test.

**Discrepancy filed**: the wake-228 card has a
`wake=228` field but mentions a "wake-257 wall
card" — the underlying genuine ambiguity is
that "wake N" can mean either (a) the wake
where the underlying finding happened or (b)
the wake where the Findings card was created.
For most cards these coincide; for the wall
card they don't. The fix establishes that
dashboard cards should be referenced by
`wake` field (= visitor-discoverable
identifier), not by creation wake.

**Cost summary**: 1 prose edit (~5 lines in
the wake-228 card). Audit-driven fix; the
audit itself was the higher-cost work.

**Blockers:** None.


## Wake 271 — README "What the project needs most right now" rewrite

**Goal**: wake-271 menu offered a README
"Current status" Gate-2 row scan. Reading the
Gate-2 row showed it was actually accurate
(state-machine picture labeled "wake 252
update" — stable since wake 252's static-RE
exhaustion). But scanning the **adjacent
"What the project needs most right now"
section** surfaced severe drift identical to
what CONTRIBUTING.md had pre-wake-267:

**"Reverse engineering — top priority":**
"`FUN_14644a070` drives the state-10→11
transition. Decompile it and find what
condition advances state past 10 after the V3
response is accepted." This decompile was done
at wake 111-112. The state-10→11 work has been
closed for 158+ wakes.

**"Python/server contributors":** "Once RE
identifies the post-V3 message sequence,
`server/rep_responder.py` needs to send it."
The post-V3 sequence was substantially
identified at wake 252 (3-message MVP
estimate: SelfIdent + LevelInfoChanged +
NewProxy replica-creation). SelfIdent codec
wired at wake 112. Phase-2D dispatcher
emission shipped at wake 204/208.

Wake-267 fixed this drift in CONTRIBUTING.md
but missed the parallel section in README.md.
Drift-fix incompleteness — exactly the kind
of issue the wake-270 audit pattern is meant
to catch.

**Built**:

**`README.md`** — rewrote "What the project
needs most right now" section (3 items → 4
items, complete reframe):

1. **Was**: "Reverse engineering — top
   priority. FUN_14644a070 drives state-10→11.
   Decompile it..."
   **Now**: "Real-GPU Windows host with Frida
   — the single highest-leverage unblocker."
   Cites the Gate-2 row above for context,
   explains both phase-2D validation and
   NewProxy ID need runtime traces, names
   AWS g4dn.xlarge as the recommended path.

2. **Captures with in-world traffic** —
   unchanged. Still valid open ask.

3. **Was**: implicit in item 1's "sibling
   target FUN_146b3c250 + 0x58f"
   **Now**: separate item 3 — "Remaining
   static-RE worth pursuing":
   `FUN_146b3c250 + 0x58f` destroy trigger.
   Preserved the V3-retry-root-cause framing.

4. **Was**: "Python/server contributors. Once
   RE identifies the post-V3 message
   sequence..."
   **Now**: lists SelfIdent already wired,
   wake-204/208 flags awaiting validation,
   names the remaining server work
   (multi-peer, carrier-level ACK,
   next-wire-type promotion candidate with a
   concrete way to find candidates).

**Verification**:

- `.venv/bin/python3 tools/build_site.py` →
  clean.
- `pytest server/javelin -q` → **456 passing,
  1 skipped** — unchanged.
- Wake-225 cross-check (analysis-path
  existence): no new analysis paths in the
  edit, no impact.
- Wake-207 cross-check (retrospective ↔
  README link): unaffected.
- Wake-231 cross-check (decision-doc README
  link): unaffected.

**Pattern note (drift-fix incompleteness)**:
this is the second time a stale-blocker
framing was caught in a doc *after* the
parallel framing was fixed in the sibling
doc. Wake 267 fixed CONTRIBUTING.md's "current
blocker = decompile state-10" framing but
missed the README's identical text. The
**audit pattern**: when fixing a stale-framing
issue in one doc, grep for the same framing
across the repo to catch parallel staleness in
sibling docs. The shared pattern this time
was the "current blocker = decompile
FUN_14644a070" wording; a `grep -r
'FUN_14644a070' --include='*.md'` after the
wake-267 fix would have caught the README
parallel.

**Generalizable principle**: drift fixes
should be applied *across all docs that share
the framing*, not just the doc that surfaced
the drift. The cost of a quick grep is
minutes; the cost of the second-doc miss is
the second visitor reading stale prose and
losing trust in the project status reporting.

**Discrepancy between Gate-2 row and "What
the project needs"**: prior to this wake, the
Gate-2 row described the state-machine work
as substantially complete (wake-252 update)
while the immediately-adjacent "What the
project needs most right now" #1 framed
state-10 decompile as the top priority. A
visitor reading top-to-bottom would
encounter the contradiction within a single
screen. Internal-consistency drift is more
embarrassing than absolute staleness because
it's clearly self-contradictory rather than
"hasn't been touched in a while".

**Filing for future hygiene**: when updating
one doc, *always* grep for the specific
strings being replaced (function names, RVAs,
state numbers) across the repo. The local
edit may be correct in isolation; the global
state may still drift.

**Cost summary**: 1 large prose rewrite in
README.md (~3 lines → ~4 paragraphs, dense
information). Single targeted commit.
Highest-leverage doc-freshness fix since
wake 267 because the README is the
first-impression surface.

**Blockers:** None.


## Wake 272 — parallel-staleness sweep (closes the wake-271 pattern)

**Goal**: apply the wake-271 cross-doc grep
principle to find sibling staleness across the
repo. Wake 271 filed: drift fixes should be
applied across all docs that share the framing.
This wake executes the sweep on the two stale
framings wake-271 caught:

1. `FUN_14644a070` / `state-10→11` references
   (the "decompile in Ghidra" framing).
2. "Once RE identifies the post-V3 message
   sequence" (the implementation-blocked-on-RE
   framing).

**Found**: 4 sibling drift sites:

1. **`CONTRIBUTING.md:97`** — section intro
   for "3. Python / server implementation":
   "Once RE identifies the post-V3 message
   sequence, someone needs to implement it
   in `server/rep_responder.py`." Wake 267
   fixed the BULLETS inside this section but
   missed the section intro paragraph.

2. **`tools/build_site.py:1669`** — live
   dashboard's How-it-works state-machine
   diagram, state 11 description: "Open
   thread — the gate from 10 to 11 is the
   current blocker." **This is visitor-
   facing** — the live dashboard's How-it-
   works tab renders this directly. Every
   visitor reading the state-machine diagram
   was being told state-10→11 is the current
   blocker.

3. **`tools/build_site.py:1689`** — live
   dashboard's FAQ answer to "Can I play on
   it?": "the connection state machine has
   an open blocker at the 10→11 transition."
   Also visitor-facing on the FAQ tab.

4. **`analysis/wrapper_setter_decompiles.md:94`**
   — "Used in the chain that fires when
   state-10→11 doesn't advance within the
   timeout window — the project's current
   blocker." Analysis doc; less visitor-
   facing but factually wrong.

**Built**:

**`CONTRIBUTING.md:97`** — rewrote the section
intro to acknowledge the post-V3 sequence is
substantially identified (3-message MVP
estimate: SelfIdent + LevelInfoChanged +
replica-creation, all named in
state_machine_summary.md), names SelfIdent
codec wired at wake 112, frames "the next
implementation step is sending whatever the
runtime trace reveals" as the open question.

**`tools/build_site.py:1669`** — rewrote state
11 description: "All 4 in-binary transitions
(10→14) RE'd at static-RE level through wake
252; runtime validation on a real-GPU host is
the pending step to verify the messages drive
them." Keeps BLOCKER_STATE = 11 (state 11 is
still where progress is currently stuck — we
know the mechanism but not yet the runtime
trigger) but updates the comment to
"static-RE closes at substate setup; runtime
is the next leg."

**`tools/build_site.py:1689`** — rewrote FAQ
answer: now acknowledges codec library
completeness + state-machine RE through state
14 + phase-2D infrastructure wired, frames
the runtime gap as awaiting validation on
real-GPU Windows host with Frida.

**`analysis/wrapper_setter_decompiles.md:94`**
— rewrote: state-10→11 mechanism is RE'd
(wake 111-112); the destroy trigger writer
(`FUN_146b3c250 + 0x58f`) is the remaining
open static-RE question on this chain.

**Sweep methodology** (worth recording):

- `grep -rln 'FUN_14644a070\|state-10→11\|
  state-10->11'` returned 13 files.
- Filtered out: archive (`autonomous_worklog_
  through_253.md`), worklog (current
  references in wake entries — historical),
  maintainer working notes
  (`docs/progress.md`, `docs/next-session.md`,
  `docs/handoff_*` — per CONTRIBUTING "don't
  worry about updating them"), code identifier
  references (e.g. self_ident.py).
- Read remaining files for context: caught
  `tools/ghidra_scripts/README.md` (descriptive
  uses, no drift),
  `analysis/codec_library_overview.md`
  (descriptive use, no drift),
  `analysis/state_machine_summary.md` (RE
  internals, no drift),
  `analysis/state_10_unblock_synthesis.md`
  (the actual wake-111/112 doc, by definition
  describes that work, no drift).

- A SECOND grep for "current blocker / active
  blocker / top priority / main blocker"
  surfaced the build_site.py + wrapper_setter
  hits that the first grep missed.

- A THIRD grep for "Once RE identifies" /
  "the next step is" found CONTRIBUTING.md:97
  + a few descriptive uses in
  static_re_handshake_signing.md and
  tools/dtls_probe.py (both fine — they're
  about specific sub-tasks, not project-level
  framing).

**Verification**:

- `.venv/bin/python3 tools/build_site.py` →
  clean.
- `pytest server/javelin -q` → **456 passing,
  1 skipped** — unchanged.
- All cross-checks unaffected.
- Live dashboard will redeploy on push; the
  How-it-works state-machine + FAQ updates
  become visible to visitors automatically.

**Pattern reinforced**: this is the 3rd wake
in the wake-267 / wake-271 / wake-272
parallel-staleness arc. Cross-doc greps caught
4 additional sites that the earlier wakes
missed. Two of them were visitor-facing on
the live dashboard.

**Generalizable principle now well-supported
by 3 data points**: when fixing a stale
framing, *always* run cross-doc greps on the
specific strings being replaced before
declaring done. Each wake of "incomplete
sweep" carries forward the same stale framing
to additional visitors until the next sweep
catches it.

**Filing for future hygiene** (now a hard
rule, not just a heuristic): drift-fix wakes
must include at least one cross-doc grep
phase before commit. The wake-272 sweep took
~10 minutes; finding the build_site.py
visitor-facing drift before this wake would
have meant visitors saw stale FAQ + state-
diagram content for an unknown number of days.

**Cost summary**: 4 file edits across 3 files
(CONTRIBUTING.md section intro, build_site.py
state-diagram + FAQ, wrapper_setter_decompiles
chain description). Plus the sweep
methodology itself, recorded in the worklog
for future application.

**Blockers:** None.


## Wake 273 — snapshot-doc scan (codec_library_overview + integration_status)

**Goal**: per the wake-272 worklog note that
`codec_library_overview.md` had a per-type
codec count drift ("22 modules" claimed in
diagram vs 28 actual on disk) and
`integration_status.md` had an "as of wake 70"
stale date stamp, this wake closes both.

**Found**:

1. **`codec_library_overview.md` diagram
   (line 24-26)**: per-type codec layer shows
   "(22 modules)" but actual count is 28.
   Drift accumulated as codec additions
   shipped post-wake-109 (the original "40/40
   covered" milestone): self_ident (wake 112),
   asset_blob_16a0 + asset_count_table_ca4
   (wakes 198-199), action_history_635
   (wake 213), keybinding_config_12f6
   (wake 217), level_info_changed (wake 232),
   world_data_blob_65c (added later) — all
   shipped after the wake-109 milestone the
   doc references. The diagram's count was a
   wake-109-era snapshot that nobody updated
   as new codecs landed.

   Also: "Generic-purpose helpers (4
   modules)" label didn't map cleanly to any
   layer in the doc body. Layer 5 ("Supporting
   modules") in the doc text lists 3 modules
   (replay_store, replay_substitution,
   session_state).

2. **`integration_status.md` line 37-41**:
   real-GPU-validation framing referenced two
   stale pointers: (a) `MORNING_BRIEF.md` for
   "runtime-host status as of wake 70" —
   MORNING_BRIEF itself is already marked as
   a wake-70 historical snapshot (per its
   wake-238 preamble), so linking to it for
   "current status" was misleading. (b)
   "wake-227 retrospective for the current
   static-RE state" — the wake-253
   retrospective is now the current-state-of-
   the-art retro (covers wakes 228-253
   state-machine RE closure arc through wake
   252).

**Built**:

**`analysis/codec_library_overview.md`** —
diagram count fix:
- "Per-type codecs (22 modules)" → "(28
  modules)".
- "Generic-purpose helpers (4 modules)" →
  "Supporting modules (3 modules)" (matches
  Layer 5 in the doc body).

**`analysis/integration_status.md`** —
real-GPU-validation pointer rewrite:
- Removed the MORNING_BRIEF.md reference
  entirely (it's a frozen snapshot per its
  own header).
- Updated retrospective pointer wake 227 →
  wake 253 (current-state retro).
- Added a pointer to the README's Gate-2 row
  as the canonical runtime-host situation.

**Verification**:

- `.venv/bin/python3 tools/build_site.py` →
  clean.
- `pytest server/javelin -q` → **456 passing,
  1 skipped** — unchanged.
- Cross-doc sweep on "wake-227 retrospective
  for" / "as of wake 70" / "MORNING_BRIEF"
  found only the wake-253 retro mentioning
  MORNING_BRIEF as a documented historical-
  snapshot example — that's a valid use, not
  drift.

**Pattern note**: this completes the
**7-wake doc-freshness arc** that opened with
wake-267's DASHBOARD/CONTRIBUTING rewrite.
Wakes 267 / 268 / 269 / 270 / 271 / 272 /
273 each closed a different drift surface,
and the wake-272 cross-doc-grep methodology
was tested + reinforced across the arc.

**Arc summary**:
- 267: DASHBOARD.md deprecation +
  CONTRIBUTING.md 4-item rewrite.
- 268: prose-tail scan, 3 Findings-card
  cleanups, indirection pattern filed.
- 269: docstring-convention parity for
  cross-check tests (218/231 → wake-225
  shape).
- 270: 4-genre Findings card audit, broken
  wake-228 cross-link fixed.
- 271: README "What the project needs most"
  rewrite, drift-fix carry-over from 267
  caught.
- 272: parallel-staleness sweep, 4 sibling
  drift sites found (including 2 visitor-
  facing on the live dashboard).
- 273: snapshot-doc scan, count drift +
  date-stamp drift closed.

**Total cost**: ~7 wakes × ~30 min = ~3.5
hours of doc-freshness work. Across that arc,
the visitor-facing first-impression surfaces
(README, live dashboard's How-it-works tab +
FAQ, CONTRIBUTING.md) are now coherent with
the current state through wake 272. Two
methodological principles filed:
(1) deprecate-don't-refresh for superseded
auto-generated docs (wake 267), and
(2) cross-doc grep before declaring
drift-fix done (wakes 271/272). Both
principles are well-supported by their
in-arc data points.

**Should the loop pause now?** The drift
arc has clearly bottomed out — the remaining
forward-menu items are increasingly marginal
(low-priority docstring extensions, more
snapshot scans of less-trafficked docs).
After 7 wakes of doc work with 6+ days of
no static-RE breakthroughs and runtime
genuinely gated on a host change, this
might be the natural pause point. Will
flag this in the wake-274 menu and let the
next iteration decide between a pause and
continuing to peel doc-drift.

**Cost summary**: 2 file edits (diagram
counts + retrospective pointer). Small
final-wake-of-arc fix.

**Blockers:** None.


## Wake 274 — destroy-trigger framing fix (catches wake-271/272 self-introduced drift)

**Goal**: wake-274 menu offered substantive RE
pivot (option b) to the destroy-trigger writer
hunt — listed as remaining static-RE in
README + CONTRIBUTING + wrapper_setter docs.
Started the pivot by reading prior work in the
worklog archive **and discovered the hunt was
already DONE at wake 8 (2026-05-07)**.

The README/CONTRIBUTING/wrapper_setter framings
of "FUN_146b3c250 + 0x58f as remaining static-
RE" are **self-introduced drift** that I shipped
across wakes 267 (CONTRIBUTING section 2 rewrite)
and 271 (README rewrite), reaffirmed at wake 272
(wrapper_setter update). At no point in that arc
did I grep the worklog archive for the function
name to verify it was actually still open.

This is exactly the cross-doc-grep failure mode
the wake-272 sweep was meant to prevent — but
applied to citing closed work as open, rather
than the more common pattern of citing open work
as if it were the current blocker.

**Wake-8 finding (resurrected from the
worklog archive)**:
- `FUN_146b3c250 + 0x58f` is the **READER** of
  `[R13+0xfd]` (the spot in
  `TransportLayerGridMateTickThread` that
  triggers destroy when the flag is set).
- The **WRITER** is `FUN_140fb3560:452`.
- The write is **gated by an event-id of
  `0xFE476177`** — an `AZ::Crc32` hash whose
  source string was **stripped from the
  release build** (29 references to the
  constant, 0 adjacent string literals).
- Static-RE is therefore **complete** on this
  chain. Identifying the specific lifecycle
  event name behind `0xFE476177` requires a
  **runtime trace** (Frida hook on
  `FUN_140fb3560` to log the event-id
  argument structure).
- This is documented in
  `analysis/state_machine_summary.md` at §
  A3.1, and the wake-8/9 worklog entries in
  the archive.

**Built**:

**`README.md`** — rewrote "What the project
needs most right now" item 3:
- **Was**: "Remaining static-RE worth
  pursuing. FUN_146b3c250 + 0x58f — find what
  writes to [R13+0xfd]..."
- **Now**: "Runtime trace on FUN_140fb3560 to
  identify the destroy-trigger event name." +
  full context (writer identified at wake 8,
  event-id is AZ::Crc32(0xFE476177), release-
  build stripped the string, Frida hook would
  resolve, pointer to state_machine_summary
  § A3.1).

**`CONTRIBUTING.md`** — rewrote "Remaining
static-RE worth pursuing" → "Remaining open
RE questions (both gated on real-GPU host +
Frida, not on more static analysis)":
- Replaced the "FUN_146b3c250 + 0x58f"
  bullet with "Destroy-trigger event name
  (0xFE476177)" — names FUN_140fb3560:452
  as the writer, frames the Frida hook as
  the resolution path.
- Kept the NewProxy/GridMate bullet
  unchanged (still genuinely runtime-
  dependent open question).

**`analysis/wrapper_setter_decompiles.md`** —
rewrote the destroy-chain paragraph:
- **Was**: "destroy trigger writer
  (FUN_146b3c250 + 0x58f) is the remaining
  open static-RE question on this chain"
  (my wake-272 edit, factually wrong).
- **Now**: "destroy-trigger writer is RE'd
  too (wake 8): [R13+0xfd] is a skip-timeout-
  and-flush flag on GridMate Carrier, with
  sole writer FUN_140fb3560:452 gated by
  AZ::Crc32(0xFE476177). Static-RE on this
  chain is therefore complete."

**Verification**:

- `.venv/bin/python3 tools/build_site.py` →
  clean.
- `pytest server/javelin -q` → **456 passing,
  1 skipped** — unchanged.
- Cross-doc sweep on `FUN_146b3c250` /
  `FUN_140fb3560` / `0xFE476177` to verify
  consistency:
  - `state_machine_summary.md` has the
    canonical writeup (wake-8 finding intact
    + § A3.1 documenting the static-blocked
    secondary question).
  - `autonomous_worklog_through_253.md` has
    the original A3/A3.1 task entries
    (archive — historical record).
  - No other docs cite the function names.

**Pattern note (significant)**: this is the
first time the cross-doc-grep sweep has been
applied to *closed work* (verifying a cited
"remaining" task is actually still open),
not just *open work* (catching parallel stale
framing of open issues). The wake-272 pattern
covered the second; **the first is a new
failure mode**: drift fixes can introduce
drift by citing already-resolved work as
open.

**Updated cross-doc-grep methodology**: when
a drift fix cites a *new* technical task
(function name, RVA, specific question) as
"remaining" or "open", also grep the worklog
archive for the same identifier to verify
the task hasn't been previously resolved.
A 1-second grep would have caught this drift
at wake 267 before it propagated through
wakes 271 / 272 / 273.

**This is the second worth-recording failure
mode in the doc-freshness arc** — the first
was "cross-doc grep needed for parallel
staleness" (wakes 267/271/272), now the
second is "cross-doc grep also needed to
verify currently-cited 'remaining' work
hasn't been resolved earlier". Both should
be in any drift-fix wake's pre-commit
checklist.

**Substantive RE outcome**: the wake-274
"substantive RE pivot" picked option (b)
expecting to attempt the destroy-trigger
writer hunt cold. Instead the wake produced
a **prior-work-recovery** finding: wake 8's
resolution had been buried in the archive
and wasn't surfaced in any visitor-facing
doc. After this wake, the destroy-trigger
RE state is correctly reflected across
README + CONTRIBUTING + wrapper_setter +
state_machine_summary.

**Meta-finding**: the worklog archive (sealed
at wake 261) contains substantive findings
that are *not* discoverable from the
narrative docs. Visitor-facing prose has
been catching up — but verification against
the archive is a missing step in the
doc-freshness pass. A future wake could
audit all "remaining static-RE" claims
against the archive's resolved-task records.

**Cost summary**: 3 file edits (README +
CONTRIBUTING + wrapper_setter), each
~6-12 lines. Plus the methodology update
recorded in the worklog. **This is the
single most-substantive doc-freshness wake
of the arc** — surfaced a buried wake-8
finding to the README's "what the project
needs most" section, and corrected three
docs that had been quietly wrong since
wake 267 onward.

**Blockers:** None.


## Wake 275 — archive audit pass (catches state-13→14 drift in state_machine_summary)

**Goal**: per wake-274's meta-finding that
the worklog archive (sealed wake 261)
contains substantive findings not
discoverable from narrative docs, audit
remaining live-doc claims against the
archive's [x] DONE and [~] PARTIAL entries.
The wake-274 fix surfaced the wake-8
destroy-trigger resolution; this wake checks
whether any other resolved tasks are still
framed as open in current docs.

**Method**:

1. **List archive [x] DONE entries** —
   `grep -n "^- \[x\]"
   analysis/autonomous_worklog_through_253.md`
   returned ~10 tasks (A1, A2, A2.5–2.8, A3,
   A4, A4.1, A5).
2. **List archive [~] PARTIAL entries** —
   ~4 tasks (A2.9, A2.10, A3.1, A4.2, A4.3,
   A2.11).
3. **For each, grep live docs for the cited
   function name / RVA / question** to check
   surface status.
4. **Look for stale TBD / "not started" /
   "still open" markers** across live
   analysis docs.

**Findings**:

✓ **Most archive [x] tasks are properly
surfaced** in current docs:
- A2.5 (writers of `wrapper[+0xa0]`) →
  state_machine_summary § 1 + Findings card.
- A3 (destroy trigger) → fixed wake 274.
- A4 (FUN_14645fd70 xrefs + state-name
  table) → state_machine_summary § 2.
- A4.1 (state-12 gate writer FUN_145a9fa00 +
  caller FUN_14645c660) →
  state_machine_summary § 4½ + Findings card.

✗ **One substantive drift found**:
`state_machine_summary.md:285` (§ 4½ closing
paragraph) said "State 13 → 14 (entering
InGame) is still TBD — `wrapper[+0x252]` is
its gate but the writer scan
(`FindOffsetWrites 0x252 0x1`, see worklog
A4.2) found no clean single-writer; that may
be a register-based or memcpy write." But
wake 247 resolved this — writer is
`FUN_142ffbc50` walking
`wrapper[+0x1b8..+0x1c0]`. The "still TBD"
prose was left over from before wake 247.

Drift was NOT caught by:
- Wake-225 cross-check (analysis-path
  existence in Findings prose) — this is a
  state-machine-doc paragraph, not Findings
  prose.
- Wake-218 cross-check (manifest wake
  citations in wake-210 card) — also out of
  scope.
- Wake-272 sweep methodology (greps on
  specific stale strings) — the stale prose
  doesn't share text patterns with the
  wake-271 framings.

✓ **Minor consistency fix**: A2.11 entry in
state_machine_summary's "Open questions"
table said "not started", but the archive
records it as "DEFERRED — 99 callers, static
path exhausted, runtime needed." Updated
the live table to match archive truth:
"static-exhausted — 99 callers, no filter
pattern surfaces PlayerManagerRejected;
runtime hook is the practical path."

**Built**:

**`analysis/state_machine_summary.md`** — two
edits:

1. **§ 4½ closing paragraph (line 285)**:
   replaced the "still TBD" / "writer scan
   found no clean single-writer" prose with
   the wake-247/249/252 resolution: writer is
   `FUN_142ffbc50`, 5 callers decompiled at
   wake 249 are local state-update handlers
   copying a 0x70-stride collection from an
   upstream container; wake 252's upstream
   trace hit an indirect-vtable wall at
   `0x14816cec0`. Pointer to
   `state_13_14_writer_investigation.md`
   for the full arc.

2. **§ 8 Open questions table, A2.11 row**:
   "not started" → "static-exhausted — 99
   callers, no filter pattern surfaces
   `PlayerManagerRejected`; runtime hook is
   the practical path" (matches archive's
   wake-9 DEFERRED status).

**Verification**:

- `.venv/bin/python3 tools/build_site.py` →
  clean.
- `pytest server/javelin -q` → **456 passing,
  1 skipped** — unchanged.
- All other [x] DONE archive tasks verified
  to be surfaced correctly in live docs (no
  additional drift found in this pass).

**Meta-pattern reinforced**: the wake-274
"cross-doc grep against archive for cited
'remaining' work" methodology, applied
proactively, caught one substantive drift
(state-13→14 TBD framing) that had been
present since pre-wake-247. This validates
the archive-audit pattern as a *periodic
hygiene exercise* — not every wake, but
worth running every ~50 wakes after
significant new findings ship.

**Drift age estimate**: the
state_machine_summary.md "13→14 still TBD"
prose has been wrong since wake 247
(2026-05-something). It propagated through
wakes 247/249/252's findings being shipped
to the Gate-2 row and Findings cards
without the § 4½ closing paragraph being
updated. That's ~25 wakes of stale prose in
a canonical analysis doc.

**Generalizable principle**: when shipping a
significant finding (like "the state-13
writer was identified"), the cross-doc
grep should include *the previously open
question's framing* — e.g. grep for "13→14"
+ "TBD" + "writer scan" after shipping a
13→14 writer finding. The wake-247 commit
updated the Gate-2 row and added Findings
cards but didn't touch state_machine_summary
§ 4½ which had been written with the older
"TBD" framing in place.

**Cost summary**: 2 file edits in
`state_machine_summary.md` (§ 4½ paragraph +
§ 8 A2.11 row). Plus the audit methodology
notes recorded here. Modest change but
closes a real drift in the canonical state-
machine analysis doc.

**Blockers:** None.


## Wake 276 — V3 send-scheduler hunt (external-review-driven pivot)

**Goal**: external review (delivered between
wakes 275 and 276) reframed the V3 retry
question as "what predicate cancels the next
V3 send?", not "what does rep.ready=1 mean?".
Their strongest concrete suggestion: hunt the
V3 *send scheduler* statically — find the
function that arms the ~500ms retry interval,
and decompile its "done" predicate. If
findable, that predicate is the boolean we
need to satisfy server-side.

**Method**: classic call-chain hunt from the
known V3 RegistrationRequest builder
(`FUN_146b66820`) upward.

**Findings**:

1. **`FUN_146b66820`** (V3 builder, already
   RE'd at connection_lifecycle_decompiles.md
   line 46) constructs `RegistrationRequestV3Msg`
   in memory.

2. **`FUN_146aaa130`** (`clientconnectionmsg_sender`)
   is the V3 sender wrapper. Returns `200`
   on success (logs "ClientConnectionMsg sent")
   or `400` on missing character_id ("Missing
   character id"). Single direct caller found:
   `FUN_146b11020` at instruction `146b11047`.
   Also one DATA xref at `14ac102d4` (= a
   vtable slot).

3. **`FUN_146b11020`** (decompiled at this wake)
   is a **3-line dispatch shim**:
   ```c
   uVar1 = FUN_140fe8e30(local_20, param_3);
   FUN_146aaa130(param_1 + 8, param_2, uVar1);
   return param_2;
   ```
   No retry logic. No state check. Just
   deserializes param_3 and forwards.

4. **`FUN_146b11020` xrefs**: **0 direct calls,
   2 DATA xrefs from `14858b2b0`**. The shim
   is reachable ONLY through a vtable.

5. **Vtable `14858b2b0`** is a **16-entry RPC
   interface vtable** with `FUN_146b11020` at
   slot [0]. The other 15 slots contain
   `FUN_146b13380`, `FUN_146b10110`,
   `FUN_14046dc90`, ..., all in the
   `0x146axxxxx`-`0x146bxxxxx` range
   (REPClient region). This is a GridMate RPC
   binding (likely `RpcBindInterface` or
   similar AzCore-style RPC binding pattern).

**Conclusion (negative result, with positive
implication)**: the V3 send path **walls at the
same indirect-vtable pattern as the wake-252
state-13→14 upstream trace**. The retry loop
is NOT inline in any function reachable by
direct call-chain traversal from `FUN_146aaa130`
— it's invoked through an RPC binding the
client itself drives via its own state.

**This validates the external review's
prediction** that runtime tracing is the path:
the "registration watchdog" they hypothesized
exists, but it's behind the vtable wall.
Hooking the vtable slot dispatch (or
`FUN_146aaa130` directly) at runtime would
identify the calling state-machine; static-RE
cannot.

**What this DOESN'T close**: the external
review's suggestion to **brute-force `0xFE476177`
against the O3DE public source corpus**
remains a tractable static-RE thread that's
been incompletely tried. Wake 9's attempt used
~65 hand-picked names against zlib CRC32; the
review correctly notes (a) AzCore uses its own
CRC32 polynomial, not zlib's, and (b) the
right corpus is `AZ_CRC` / `Crc32(...)` /
`AZ_CRC_CE` callsites in O3DE source, not
hand-picked names. That's a future wake's
work — needs O3DE checkout + AzCore Crc32
algorithm extraction + bulk computation.

**Built**:

- `analysis/decomp_FUN_146b11020_v3_caller.txt`
  — the 3-line shim decomp.
- `analysis/xrefs_FUN_146aaa130_v3_sender.txt`
  — xref dump showing single direct caller.
- `analysis/xrefs_FUN_146b11020.txt` — xref
  dump showing only DATA refs from vtable.
- `analysis/vtable_dump_14858b2b0.txt` — 16-
  entry vtable contents.

**Verification**:

- `.venv/bin/python3 tools/build_site.py` →
  not run (no doc changes; pure analysis
  artifacts).
- `pytest server/javelin -q` → unchanged
  (no code changes).

**Pattern note**: this is now the **second
static-RE thread that hits the indirect-
vtable wall** (first was wake 252 on
state-13→14 upstream). Pattern: RPC-message
dispatch and timer-driven state machines both
use vtable indirection in AzCore/GridMate
patterns, so any "what calls this" hunt that
needs to cross the message-dispatch boundary
hits this wall. **Generalizable**: for this
codebase, static-RE on call paths above a
vtable boundary is not productive without
either (a) the vtable's full RTTI/typeinfo
to recover the interface type, or (b)
runtime tracing.

**Cost summary**: 4 small Ghidra runs
(FindXrefs × 2, HeadlessDecompile × 1,
DumpVtable × 1), 4 analysis artifacts saved.
No doc updates beyond this worklog entry —
the wake-271 README/CONTRIBUTING framing
("real-GPU host with Frida is the single
highest-leverage unblocker") is reinforced
by this finding rather than changed.

**Forward implications for the loop**:

1. The destroy-trigger writer hunt is closed
   (wake 274 surfacing).
2. The state-13→14 question is closed at
   static-RE limit (wake 252).
3. The V3 send-scheduler hunt is now also at
   the static-RE limit (this wake).
4. The remaining tractable static-RE thread
   is the O3DE corpus brute-force for
   `0xFE476177` — that's a future wake.
5. Runtime trace on a real-GPU host with
   Frida resolves the V3-retry root cause
   (predicate of the registration watchdog),
   the NewProxy wire-type ID (state-13→14),
   and the `0xFE476177` event name —
   **three blockers resolved by one
   experiment**.

**External-review value confirmed**: the
review's reframing of "two registered
concepts" (REP/V3 parser accepts vs login/
session coordinator considers complete) is
consistent with this finding — the
registration watchdog is in the "session
coordinator" layer that the REP-level
rep.ready=1 doesn't satisfy.

**Blockers:** None.


## Wake 277 — O3DE corpus brute-force attempt for AZ::Crc32(0xFE476177)

**Goal**: external review (post wake-275)
suggested wake-9's CRC reversal attempt was
incomplete because the wordlist was too small
+ the AzCore CRC32 algorithm might differ
from zlib. Wake-9 tried 65 candidates against
zlib CRC32 (raw + lowercased). This wake
extends with broader wordlist + algorithm
variants.

**Method**:

1. **Verify AzCore CRC32 algorithm**:
   Computed `zlib.crc32(b"GameEntityContextRequests")`
   = `0xD8984A98`. AzCore's `Crc32` class in
   public O3DE source uses polynomial
   `0xEDB88320` (same as zlib). The wake-9
   algorithm choice was correct.

2. **Broader wordlist**: 187 additional
   candidates focusing on GridMate Carrier
   tear-down / flush / disconnect / timeout
   events, AZ EBus naming patterns, and
   Lumberyard/O3DE component lifecycle names.

3. **Algorithm variants** (7): raw, raw+null,
   lowercased, lowercased+null, uppercased,
   raw inverted (`^ 0xFFFFFFFF`), lowercased
   inverted.

**Result**: **no match**. Total across wakes
9 + 277: ~252 unique candidate strings ×
multiple variants ≈ 1300+ CRC computations.
The release-build string stripping is real;
hand-curated wordlists are too sparse to hit
the specific tear-down event name.

**Built**:

- **`analysis/crc32_FE476177_brute_force.py`**
  — self-contained reproducible brute-force
  script with the combined wordlist + 7
  algorithm variants. Future contributors with
  access to O3DE source can extend the
  `candidates` list and re-run.
- **`analysis/state_machine_summary.md`
  § 8 A3.1 row** — updated to note: AzCore
  CRC32 verified to match zlib, two brute-
  force attempts exhausted, next static thread
  is O3DE corpus grep.

**Verification**:

- `pytest server/javelin -q` → not run (no
  code-path changes; pure analysis artifacts +
  one doc update).
- `.venv/bin/python3 tools/build_site.py` →
  will run pre-commit.

**Static-RE conclusion for `0xFE476177`**:

Three thresholds for resolution have now been
identified:

1. **Hand-curated wordlist** (wake 9 + 277):
   exhausted. ~252 candidates × variants. Dead
   end for further iteration.
2. **O3DE source corpus brute-force** (not yet
   attempted): requires cloning public O3DE
   repo, grepping every `AZ_CRC` /
   `AZ_CRC_CE` / `Crc32(...)` callsite,
   computing each. Tractable but requires
   external repo access outside the loop. The
   `crc32_FE476177_brute_force.py` script is
   ready to take an extended wordlist.
3. **AZ::Name string-internment table hunt**
   (alternative static thread, not yet
   attempted): AZ::Name in O3DE uses a hash
   → string lookup table at runtime. If the
   binary preserves any of this table, the
   string for `0xFE476177` might be reachable
   through it. The wake-9 notes mention
   `PTR_LAB_147ef8d50` as a suspected AZ::Name
   vtable. Finding the consumers of that
   vtable might surface the table. This is a
   different static-RE thread that's never
   been hunted.
4. **Runtime trace** (canonical path): Frida
   hook on `FUN_140fb3560` logs the event-id
   argument structure at call time. Resolves
   the question definitively.

**Negative-result value**: this wake confirms
the wake-9 conclusion was correct and adds a
larger-wordlist + multi-variant data point.
The wake-9 archive entry now has a directly-
linked extension. Also: the
`crc32_FE476177_brute_force.py` script makes
the brute-force trivially extensible for any
future contributor with O3DE source access.

**Methodological note**: this wake is the
third in a row to produce a substantive
negative result that *advances* the question
(wake 274 surfaced wake-8 resolution; wake 275
surfaced wake-247 closure; wake 276 + 277 hit
new walls). Three negative-result wakes in a
row, each producing forward-progress
documentation, is a different mode from the
"shipping a fix" wakes that dominated wakes
267-273. Worth tracking — substantive
negative results have been *higher*-value
than the doc fixes in the recent arc.

**Forward implications**: with this wake, the
static-RE toolkit on the destroy-trigger
question is genuinely exhausted from the loop.
The two remaining tractable static threads
(O3DE corpus + AZ::Name table) both require
either external source-tree access or a more
elaborate Ghidra session. Either could
plausibly be pursued in a future wake; both
have a meaningful chance of producing a
single-shot answer.

**Cost summary**: 1 brute-force script
authored + 187 additional candidates tested,
1 doc row updated in
`state_machine_summary.md`. Negative result
documented + future-extensible script left
behind. ~25 minutes.

**Blockers:** None.


## Wake 278 — AZ::Name table hunt finds a sibling dispatcher (FUN_146b621c0)

**Goal**: external review's first-priority
remaining static thread was the AZ::Name
string-internment table hunt — find consumers
of `PTR_LAB_147ef8d50` (wake-9-suspected
AZ::Name vtable) and look for a hash→string
lookup table that might contain `0xFE476177`.

**Method**:

1. Xref `PTR_LAB_147ef8d50` → **41,245
   references**. Too broad for direct
   enumeration — AZ::Name is one of the most
   commonly-used utility types in
   Lumberyard/O3DE.
2. **Pivot**: instead of broad table hunt,
   re-examine the 29 hit sites for
   `0xFE476177` from wake 9. Wake 9 had a
   Ghidra script bug that prevented capturing
   context bytes, so only one site
   (`FUN_1402af830`) was actually examined. The
   other 28 sites' patterns were never
   verified to match the "bare constant"
   conclusion.
3. Decompile `FUN_146b621c0` (sites 25 + 26
   in the hit list, suggesting it does
   something specific with the constant).

**Finding**: `FUN_146b621c0` is **a
previously-undocumented multi-event
dispatcher** for the same event family as
`FUN_140fb3560` (the wake-8 destroy writer).
Structure:

```c
if (event_id == 0x53E4E683) { ... call vtable+0x360 + 0x628 ... }
if (event_id == 0xDECE4567) { ... call vtable+0x360 + 0x628 ... }
if (event_id == 0xAD273586) {
    *(byte *)(carrier + 0xd9) = 1;
    ... call vtable+0x628 ...
}
if (event_id == 0xF2D0BB74) { ... 3-name setup + 3 vtable calls ... }
if (event_id == 0xFE476177) {           // OUR TARGET
    *(byte *)(carrier + 0xda) = 1;       // NOTE: +0xda, not +0xfd
    local_28 = 0xFE476177;
    (**(code **)(*param_3 + 0x628))(param_3, &local_30);
}
if (event_id == 0x8E281F3D) { ... call vtable+0x360 + 0x628 ... }
```

**Three-flag pattern surfaces**: `[+0xd9]`,
`[+0xda]`, `[+0xfd]` are related Carrier
state flags. The destroy chain we already
knew (wake 8) sets `[+0xfd]` via the
`FUN_140fb3560:452` writer. This newly-
documented handler sets `[+0xda]` for the
**same event** (0xFE476177). Two handlers
respond to the same event in EBus style —
typical Lumberyard subscriber pattern.

**Wake-8 archive cross-reference**: the
wake-8 entry already documented
`FUN_140fb3560`'s sub-event keys as
`0x578a1f75, 0x20edcd6c, 0xF2D0BB74,
0xFE476177` and outer key `0xF36721F9`.
These match the hashes in `FUN_146b621c0`,
confirming both functions handle the same
EBus.

**The constrained event family** (19 hashes
total, now documented in
`crc32_FE476177_brute_force.py`):

- 6 outer event ids: 0xFE476177, 0xF2D0BB74,
  0xF36721F9, 0x53E4E683, 0xDECE4567,
  0xAD273586, 0x8E281F3D
- 3 shared AZ::Name namespace/type IDs:
  0x7FABBDE8, 0xBF83FB18, 0xB2B878F9
- 2 shared sub-actions: 0x578A1F75,
  0x20EDCD6C
- 7 branch-specific sub-names: 0x9CCD4435,
  0xF3B2D8C3, 0xFAF3C240, 0x671C7858,
  0x82219416, 0x6606A5ED, 0x08495DFC

**Implication for the brute-force**: if a
future contributor matches **any one** of
these 19 hashes to a known O3DE event name,
the EBus domain is identified. The other 18
hashes constrain to the same event class — a
single match unlocks the family.

**Brute-force extension run this wake**:
87 GridMate-focused candidates × 2 variants
against all 19 hashes. **Still no match.**
But the wordlist gap is now narrower:
candidates that fail across 19 unrelated
hashes are unlikely to match any one;
candidates that fail against the constrained
family hashes confirm those particular names
aren't in this EBus.

**Built**:

- **`analysis/decomp_FUN_146b621c0_fe476177_2hits.txt`**
  — full decomp of the newly-documented
  dispatcher.
- **`analysis/xrefs_AZ_Name_vtable_147ef8d50.txt`**
  — 41,245-line xref dump (proves the vtable
  IS the AZ::Name vtable — too broadly used
  to enumerate, but the count itself is
  evidence).
- **`analysis/crc32_FE476177_brute_force.py`**
  — extended with the 19-hash event-family
  set as target dictionary + GridMate-focused
  candidate additions.

**Verification**:

- `pytest server/javelin -q` → not re-run
  (no code-path changes).
- `tools/build_site.py` → will run
  pre-commit.

**Pattern note**: this wake produced the
*reverse* of the typical pattern in recent
wakes. Where wakes 274/275 surfaced existing
findings into visitor docs, **wake 278
surfaced a previously-unfound static
finding** (FUN_146b621c0 dispatcher and its
event family). The static-RE wall is real,
but it's not at the level wake-9 declared —
the wake-9 conclusion ("29 hits, all bare
constants, dead end") was correct only for
the single hit it examined. The other 28
hits were never examined and one of them
(FUN_146b621c0) yields substantive structure.

**Generalizable principle**: when a tool bug
prevents capturing context (as in wake-9's
Ghidra `getBytes()` error), re-running with
a fixed approach is high-value when the
question has remained open for ~270 wakes.

**Forward implications**:

1. The brute-force script now has a 19-hash
   target dictionary — any future contributor
   running it against O3DE-corpus AZ_CRC
   callsites has 19× the surface area to hit
   a match.
2. Runtime trace on either `FUN_140fb3560`
   OR `FUN_146b621c0` would log all 19+
   event/name hashes from the live Carrier
   event stream. The Carrier-event class is
   the unblock target.
3. The `[+0xd9]`, `[+0xda]`, `[+0xfd]`
   triplet is a new RE artifact — there are
   likely more handlers in the same EBus
   family that respond to other events and
   set other flags. A future wake could
   enumerate the remaining 28-1 = 27 hit
   sites of `0xFE476177` and map the
   complete handler structure.

**Cost summary**: 1 Ghidra decompile + 1
Ghidra xref + 1 brute-force run + 2 file
updates. **The most substantive static-RE
wake since wake 252** — produced a new
dispatcher finding, expanded the event-
family target set 1 → 19 hashes, and proved
the wake-9 dead-end declaration was
premature (other hit sites have richer
structure).

**Blockers:** None.


## Wake 279 — hit-site enumeration: 3 more dispatchers + 5-flag Carrier state map

**Goal**: extend wake-278's enumeration of
0xFE476177 hit sites. Wake 278 examined 1 of
the 28 unexamined sites (FUN_146b621c0) and
found a new dispatcher. This wake samples 3
more diverse sites to characterize how widely
the event-handler pattern repeats.

**Sites examined**:

1. **FUN_140fb84b0** (sibling of the wake-8
   destroy writer FUN_140fb3560):
   - Conditional handler reading `[+0xfc]` —
     **another Carrier state flag** in the
     same byte-range as `[+0xfd]`.
   - Path A (failure): uses hash `0xc739f1c5`
     in AZ::Name construction.
   - Path B (success after `vtable+0xc18`
     query): uses `0xFE476177` + new hash
     `0xe9e5887`, calls `vtable+0x608` with
     `DAT_147efa330` (float constant pool
     entry — same pattern wake 9 documented).
   - **New flag offset**: `[+0xfc]` is
     read+cleared at entry, separate from
     `[+0xfd]` destroy flag.

2. **FUN_1461361f0** (the dual-hit function,
   sites 17+18):
   - Multi-event dispatcher with 6+ branches.
   - Branch `0x400b5e61` uses 0xFE476177 as
     a sub-name (not the outer event id) —
     `local_28 = 0xFE476177` then call to
     `vtable+0x608` with `DAT_147f400f4`
     (another float constant).
   - Branch `0xFE476177` itself: calls
     `vtable+0xb18` (different slot than
     others).
   - **8 new event hashes**: 0x3c337259,
     0x700ecf92, 0x6d65d99b, 0x400b5e61,
     0xbd1ed24d (=`-0x42e12db3`),
     0x931f6da6, 0xd8bbfb1b, 0x79f85ed7,
     0x309c0901.

3. **FUN_1471f15d0** (high-address-range
   dispatcher):
   - 10+ event branches handling diverse
     events.
   - Branch for 0xFE476177 writes
     `[+0xcd] = 1` — **third distinct Carrier
     flag offset set by the same event**.
   - **13+ new event hashes**: 0x3b8c658a,
     0x68163e0e, 0xefb0f54d (=-0x104f0ab3),
     0xa5dc2231, 0xab331fa6, 0x4eeb9932,
     0x323a4e1c, 0xd0191b5f, 0x03d5c4b4,
     0x453d7e8a, 0x82b91ef0,
     0xcf228906 (=-0x30dd76fa),
     0xbb3d64d8 (=-0x44c29b28),
     0xe8a73f5c (=-0x1758c0a4).

**The "Carrier state flag map" surfaces in
full** — Carrier maintains at least **5
related lifecycle flags** in the `[+0xcd]` →
`[+0xfd]` byte-range:

| Offset | Writer | Event id |
|---|---|---|
| `[+0xcd]` | FUN_1471f15d0 | 0xFE476177 |
| `[+0xd9]` | FUN_146b621c0 | 0xAD273586 |
| `[+0xda]` | FUN_146b621c0 | 0xFE476177 |
| `[+0xfc]` | FUN_140fb84b0 (read+clear) | (event-conditional) |
| `[+0xfd]` | FUN_140fb3560:452 | 0xFE476177 |

**Critical observation**: event 0xFE476177
**triggers writes to THREE distinct Carrier
flags** (`[+0xcd]`, `[+0xda]`, `[+0xfd]`)
across THREE distinct handler functions. This
is a strong indicator that 0xFE476177 is a
high-impact lifecycle event (likely something
like "OnDisconnect" / "ConnectionLost" /
"PreShutdown") that multiple Carrier
subsystems care about and each needs to clean
up state for. **The event isn't a destroy-
trigger directly — it's a broadcast lifecycle
event whose third-tick consequence is the
[+0xfd]-driven destroy.**

This is **a fundamentally clearer model of
what 0xFE476177 is**, even without resolving
its string name:
- It's a Lumberyard EBus / event-handler
  broadcast event.
- 3+ Carrier subsystems subscribe to it.
- Setting `[+0xfd]` to 1 is the destroy-loop
  trigger, but the broadcast event itself is
  what FIRES the loop.
- Identifying it = identifying the broadcast
  that initiates Carrier teardown.

**Target hash family expanded again**: was 19
hashes (wake 278), now **~50 hashes**. Updated
the brute-force script with the new set.

**Built**:

- `analysis/decomp_FUN_140fb84b0_destroy_sibling.txt`
  (208 lines)
- `analysis/decomp_FUN_1461361f0_dual_hit.txt`
  (143 lines)
- `analysis/decomp_FUN_1471f15d0_high_range.txt`
  (294 lines)

**Verification**:

- `pytest server/javelin -q` → not re-run
  (analysis-only).
- `tools/build_site.py` → will run
  pre-commit. Decompiles 48 → 51.

**Pattern note**: wake-278's finding that
"wake-9's dead end was premature because the
tool bug prevented site enumeration" is
**reinforced by 3 more data points**. Each of
3 sampled sites yielded structurally
distinct, substantive content. The
remaining 24 unexamined sites likely contain
similar value.

**Forward implication**: a future wake could
do a sweep of all remaining sites in parallel
(via 3-4 Agent subagents, one per site
batch). Each finds new flag offsets, new
event hashes, new dispatcher structure.

**Pivot opportunity for the wordlist hunt**:
the broad "broadcast lifecycle event"
hypothesis suggests trying specific O3DE
event names like:

- `OnDisconnect` (already tried)
- `OnConnectionLost` (already tried)
- `OnPreDisconnect` (already tried)
- `OnDisconnectionDone` (NEW)
- `OnConnectionStateChanged` (already tried)
- `CarrierEventBus` event names from public
  O3DE GridMate source

But without external corpus access, this
remains the same dead-end the wake-9 + 277 +
278 wordlists hit.

**Substantive negative outcome with strong
positive direction**: the static-RE picture
of the destroy mechanism is now ~5x richer
than at wake start. The bottleneck remains
the same (runtime trace or O3DE corpus
grep), but a future contributor accessing
either path now has 50 hashes to query
instead of 1.

**Cost summary**: 3 sequential Ghidra
decompiles + analysis. **Continues the most
productive static-RE thread in months** —
wake-278 + 279 together expanded the
destroy-event picture from "one writer, one
hash, dead end" (wake-9 conclusion) to "5
flags, 4 handlers, ~50 related hashes, 3-
subscriber broadcast event pattern".

**Blockers:** None.


## Wake 280 — emitter / subscriber split surfaces (4 more dispatchers examined)

**Goal**: continue the hit-site enumeration
that wake-278 + 279 started. Sample 4 more
diverse 0xFE476177 hit sites and see if a
larger structural pattern surfaces.

**Sites examined**:

1. **FUN_1402a6310** (low-address range,
   584-line function — possibly base
   AzNetworking code):
   - Subscriber.
   - Branch `0xFE476177` writes `[+0x179] = 1`
     — **a far-away flag offset** (vs the
     0xcd-0xfd cluster).
   - Related event: 0xf09023c in adjacent
     branch.

2. **FUN_146074880** (REPClient range):
   - Subscriber.
   - Branch `0xFE476177` writes `[+0xcf] = 1`
     — a 5th distinct Carrier state flag.

3. **FUN_146b64550** (sibling of wake-278
   FUN_146b621c0):
   - **Emitter**, NOT a subscriber.
   - Uses pattern: `local=0xFE476177;
     vtable+0x608(arg, DAT_147efa330)`.
     Identical to FUN_140fb84b0 (wake 279)
     and FUN_1402af830 (wake 9).

4. **FUN_1471f4260** (sibling of wake-279
   FUN_1471f15d0):
   - **Emitter**, NOT a subscriber.
   - Same emitter pattern as #3.

**Major structural finding**: the hit sites
fall into **two clearly distinct buckets**:

**Bucket A — Emitters** (4 found so far,
likely more in the 17 unexamined sites). All
use identical pattern:
```c
local_NN = 0xFE476177;
(**(code **)(*vt + 0x608))(vt, &local, DAT_147efa330, 0);
```
DAT_147efa330 is the float constant pool entry
verified at wake 9 (1.5f, 2.0f) — likely an
EBus priority/weight argument.

| Function | Address range | Context |
|---|---|---|
| FUN_1402af830 | 0x140 | base AzCore (wake 9 known) |
| FUN_140fb84b0 | 0x140 | base AzNetworking |
| FUN_146b64550 | 0x146 | REPClient |
| FUN_1471f4260 | 0x147 | high range |

**Bucket B — Subscribers** (5 found so far,
each writes a distinct Carrier-state flag for
event 0xFE476177):

| Function | Flag offset | Address range |
|---|---|---|
| FUN_140fb3560:452 (wake 8) | `[+0xfd]` | 0x140 |
| FUN_1471f15d0 (wake 279) | `[+0xcd]` | 0x147 |
| FUN_146b621c0 (wake 278) | `[+0xda]` | 0x146 |
| FUN_146074880 (this wake) | `[+0xcf]` | 0x146 |
| FUN_1402a6310 (this wake) | `[+0x179]` | 0x140 |

**Carrier state flag map now spans 7 known
offsets** in the 0xcd → 0x179 range. Multiple
subscribers respond to the SAME event by
writing DIFFERENT state bytes, suggesting each
flag represents a distinct subsystem's
"acknowledged-disconnect" or "in-cleanup"
marker. The destroy flag at `[+0xfd]` is one
of these — not the primary purpose of the
event, just one subsystem's response.

**Critical implication for the question**:
this is a **general-purpose broadcast
lifecycle event**, fired from multiple emit
sites scattered across AzCore + AzNetworking +
REPClient code, received by multiple
subsystems. Strongly consistent with
"OnDisconnect", "OnConnectionLost",
"OnConnectionDestroying", or similar
fundamental Carrier event.

The wake-9 hand-curated wordlist tried many
candidates in this space ("OnDisconnect",
"OnConnectionLost", "Carrier::ConnectionLost",
etc.) and none matched. The string is
probably either:
- Internally-namespaced (e.g.
  `GridMate::CarrierConnection::OnDisconnect`)
- A specific event name we haven't tried
  (e.g. `OnLink Lost`, `ConnDestroying`)
- An AZ::Name custom event that O3DE source
  contains but isn't in our hand-curated set

Updated state_machine_summary.md § A3.1 row
with the emitter/subscriber split + 7-flag
list. Future contributor running the brute-
force script against O3DE corpus has the
complete target set now.

**Built**:

- `analysis/decomp_FUN_1402a6310_lowrange.txt`
  (584 lines — large multi-event handler)
- `analysis/decomp_FUN_146074880_repclient.txt`
  (214 lines)
- `analysis/decomp_FUN_146b64550_ebus_sibling.txt`
  (215 lines — emitter)
- `analysis/decomp_FUN_1471f4260_highrange.txt`
  (202 lines — emitter)

**Verification**:

- `pytest server/javelin -q` → not re-run.
- `tools/build_site.py` → will run pre-commit.
  Decompiles 51 → 55.

**Pattern note**: wakes 278-280 form a coherent
3-wake sub-arc that **fundamentally reshapes
our understanding of the destroy chain**:
- Before (wakes 8-9): "one writer (`FUN_140fb3560`)
  sets the destroy flag when event 0xFE476177
  fires; the event id can't be reversed
  statically; dead end."
- After (wakes 278-280): "0xFE476177 is a
  general-purpose lifecycle broadcast event
  fired from 4+ emitter sites, received by 5+
  subscribers each setting their own Carrier
  state flag (one of which is the destroy
  trigger); ~50 related hashes form the EBus's
  event family; runtime trace OR O3DE corpus
  grep would resolve the family."

**Forward implications**:

1. **A future parallel sweep** of the 17
   remaining unexamined sites (likely more
   emitters and subscribers) would complete
   the picture but is now low marginal value —
   the structural pattern is established.
2. **O3DE corpus brute-force** against the
   ~50-hash family is now a multi-prize hunt
   — any one match identifies the EBus and
   constrains the other 49.
3. **Runtime trace** would resolve 0xFE476177
   directly + log all related event names.

**Recommendation for next wake**: SURFACE
these findings to README + visitor docs (the
Gate-2 row mentions "30s destroy timer fires
0xFE476177" — that's now revealed to be more
nuanced). Or pause-reflection on the 14-wake
arc.

**Cost summary**: 4 Ghidra decompiles + 1 doc
update. **Closes the most productive static-
RE arc since wake 252** with a clean
structural model of the destroy-event family.
The 17 remaining unexamined sites are
predictable now (more emitters or
subscribers); the surface area for
mechanical enumeration is exhausted.

**Blockers:** None.
