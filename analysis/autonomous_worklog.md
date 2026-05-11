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
