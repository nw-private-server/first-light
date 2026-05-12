# Handoff — 2026-05-12 (post-autonomous-session)

## TL;DR

The 2026-05-06 → 2026-05-12 autonomous `/loop` session ran wakes 254
through 333 on `claude/vacation-2026-05-06`. The arc closed the
**post-V3 state-machine RE** at static-RE level, surfaced a
**destroy-event broadcast model** that fundamentally reshapes the
"30s session destroy" picture, and produced **24 dashboard Findings
cards + 19 cross-check tests + 56 Ghidra decompiles** all current.

**Runtime trace on a real-GPU Windows host with Frida is now the
single highest-leverage unblocker.** Three open questions (V3 retry
root cause, NewProxy/replica wire-type ID, `0xFE476177` event name)
all share that one experiment as their resolution path. Static-RE
is genuinely exhausted across every angle the loop has access to.

The 2026-05-06 version of this doc lives at the **bottom of this
file** under "## Previous handoff (2026-05-06 — pre-autonomous-
session)" for context on what was open going in.

## What got resolved during the autonomous session

**State-10 → 11 RE closure (wake 111-112)** — the wall the previous
handoff named as "the exact open question" is closed at static-RE
level. The transition is gated by `*(int*)(wrapper + 0xa0) == 2`
(corrected from the earlier `+0x130` hypothesis), and the value 2 is
written only on receipt of `PlayerManagerSelfIdentificationMsg`
(wire-type `0x5d1`, registry UUID `60A51DFC-8745-4276-976D-8808EF52CD77`).
Captured replay doesn't contain `0x5d1` so pure replay can't drive
the transition. The codec is wire-bound in
`server/javelin/self_ident.py` and ready for runtime test.

**Full post-V3 state-spawn ladder mapped** — all 4 transitions
through state 14 (`InGame`) have writers + trigger chains identified:

| Transition | Predicate | Writer | Trigger |
|---|---|---|---|
| 10 → 11 | `(int)(wrapper+0xa0) == 2` | `FUN_145a87010` | `PlayerManagerSelfIdentificationMsg` (`0x5d1`) |
| 11 → 12 | inverted check on same field | auto-fires | (none — same field) |
| 12 → 13 | `(u8)(wrapper+0xbc8) != 0` | `FUN_146446800` (LevelInfoChanged direct force) + `FUN_14645c660` (soft path via `FUN_145a9fa00`) | `LevelInfoChangedMsg` (primary), `RemoteConfigChangedMsg`-class (secondary) |
| 13 → 14 | `(u8)(wrapper+0x252) != 0` | `FUN_142ffbc50` | (runtime — likely GridMate `NewProxy`, see wake-252 wall) |

MVP server-side message set is **3 messages**: `SelfIdent` +
`LevelInfoChanged` + a replica-creation message (likely GridMate
`NewProxy`).

**Destroy-event family reframed (wakes 278-282)** — the wake-8 finding
that `[R13+0xfd]` is the destroy flag, written by `FUN_140fb3560:452`
gated by `AZ::Crc32(0xFE476177)`, is now part of a much broader
picture:

- **4 emitter sites** all use pattern `local=0xFE476177; vt+0x608(&local, DAT_147efa330)`:
  `FUN_1402af830` (wake 9), `FUN_140fb84b0`, `FUN_146b64550`, `FUN_1471f4260`
- **5 subscribers** each write a distinct Carrier-state flag in
  response to event `0xFE476177`:
  - `FUN_140fb3560` → `[+0xfd]` (the wake-8 destroy flag)
  - `FUN_146b621c0` → `[+0xda]`
  - `FUN_1471f15d0` → `[+0xcd]`
  - `FUN_146074880` → `[+0xcf]`
  - `FUN_1402a6310` → `[+0x179]`
- **~50-hash event family** dispatched via the same EBus
- `DAT_147efa330` is a float-pool entry of `1.5f/2.0f`; surrounding
  table has `0.5, 0.75, 1.5, 2.0, 6.0, 8.0, 30.0, 60.0, 120.0`
- **High-confidence inference (wake 282)**: `vtable+0x608` is a
  "schedule event in N seconds" call. The 30.0 entry maps neatly
  to the observed "~30s session destroy" symptom.
- **`0xFE476177` is likely** an `OnDisconnect` /
  `OnConnectionLost` / similar Carrier broadcast lifecycle event,
  with the destroy flag being **one subscriber response among
  many**, not the event's primary purpose.

**Hash brute-force exhausted** (wakes 9 / 277 / 278 / 279 / 280) —
**~340 candidate strings × 7 algorithm variants ≈ 1300+ CRC
computations** against the constrained 50-hash family. No match.
AzCore CRC32 verified to use polynomial `0xEDB88320` (same as zlib).
The brute-force script at `analysis/crc32_FE476177_brute_force.py`
is self-contained + extensible — any future contributor with O3DE
source access can extend the candidate list and re-run.

**Static-RE limit pattern documented** (wakes 252 / 276 / 283) —
**3 indirect-vtable walls** all share the same shape: function chain
→ shim → vtable → ?. For this codebase's GridMate RPC subsystem,
any `(*vtable+offset)(...)` call is a likely static-RE limit. New
Findings card "Indirect-vtable wall pattern" surfaces this on the
dashboard.

## What works (updated)

Everything in the previous handoff's "What works" list, plus:

- **Codec library wire-complete** at 40/40 captured wire-types,
  central dispatcher byte-equivalent round-trips, **456 tests
  passing** (+1 skipped) — was 84 in previous handoff.
- **Live dashboard** at https://nw-private-server.github.io/first-light/
  surfaces 24 Findings cards across 4 categories + 36/40 captured
  wire-types decodable in the Explore tab (90.0% by wake-221
  design floor decision).
- **`rep_responder` ↔ central-dispatcher integration foundation**
  shipped behind two feature flags (wakes 204/208):
  `heartbeat_use_dispatcher` (emission swap) +
  `heartbeat_advance_counter` (counter mutation). Both default off,
  byte-equivalent to captured replay path, awaiting real-GPU
  validation.
- **Cross-check graph**: 19 pytest invariants across 3 buckets pin
  dashboard + workflow drift. Self-referential 5-pin cluster on the
  wake-210 meta-card.
- **Worklog split** at wake 261 — wakes 1-253 in
  `autonomous_worklog_through_253.md` (sealed archive),
  wakes 254+ in active `autonomous_worklog.md`.

## What doesn't (updated)

- **Gate-2 retry loop is still the active blocker**. V3 response
  accepted, `rep.ready` flips 0→1, client re-sends V3 every ~500ms
  and the session destroys after ~30s. **What's changed from the
  previous handoff**: we now know that the state-10→11 transition
  itself is RE'd, so the retry-loop cause is NOT state-10 advance
  failure — it's something else in the post-V3 state coordinator.
- **The 30s destroy** is now understood as the 30.0 entry in the
  float-delay table firing `0xFE476177` through the broadcast event
  scheduler. Resolving the event name (or hooking the
  `vtable+0x608` call site live) would identify which Carrier
  subsystem is initiating the disconnect.
- **NewProxy / replica-creation wire-type ID** — the third MVP
  message. The wake-252 indirect-vtable wall stops static-RE on
  this question.

## The exact open question (updated)

**What server message satisfies the post-V3 "registration complete"
predicate that stops the V3 retry loop?**

External fresh-eyes review (recorded at wakes 275-276) reframed this
as "two registered concepts": the REP/V3 parser accepts the response
(rep.ready=1) but the higher-level session coordinator never sees
its expected completion. The retry loop is keyed on the second
predicate, not the first.

Static-RE on the **send side** (wake 276) traced builder
`FUN_146b66820` → sender `FUN_146aaa130` → shim `FUN_146b11020` →
**16-entry GridMate RPC vtable at `14858b2b0`**. The retry watchdog
is invoked through this vtable's dispatcher, not by direct call.
**This is the wake-276 wall**: static-RE on the send-scheduler path
needs either full RTTI/typeinfo recovery or runtime tracing.

## Three concrete next experiments

### 1. Real-GPU Windows host with Frida (the highest-leverage one)

Spin up an AWS `g4dn.xlarge` (Tesla T4, Windows Server, ~$0.75/hr)
or physical Windows host. The SSH-driven infrastructure from the
UTM/Parallels work (cert install, hosts redirects, portproxy, SCP
game-dir push, Frida hooks) transfers verbatim. Hooks to load:

- **`FUN_140fb3560` entry** — log the event-id arg structure at
  call time. This reveals `0xFE476177`'s string name (the question
  the wake-9 + wake-277 brute-force ~1300 CRC attempts couldn't
  reverse).
- **`FUN_142ffbc50` callers** — wake-249 identified 5 of them. Any
  one of these caught at runtime resolves the NewProxy /
  replica-creation wire-type question.
- **`vtable+0x608` dispatcher on the V3-send path** — log the
  caller object's vtable identity. Identifies the type that owns
  the retry watchdog.

One real-GPU Frida session resolves all three open questions.

### 2. Phase-2D feature flag validation (already shipped, awaiting flip)

`heartbeat_use_dispatcher=on` + `heartbeat_advance_counter=on` route
the heartbeat emission through the central dispatcher with byte-
identical output to captured replay, but the counter advances
per-call. Both default off; flipping them on a real-GPU host and
observing the gate-2 retry-loop behavior tests whether dispatched
emission affects the loop at all.

### 3. O3DE corpus brute-force for `0xFE476177` (parallel attempt)

If runtime trace is delayed, the wake-277 brute-force script
(`analysis/crc32_FE476177_brute_force.py`) takes a wordlist of
candidate names. Hand-curated lists at ~340 candidates didn't match
the constrained 50-hash family; a comprehensive grep of public
O3DE source for `AZ_CRC` / `AZ_CRC_CE` / `Crc32(...)` callsites
would produce a much larger corpus. If any one hash in the family
matches a known O3DE event name, the EBus is identified and the
other 49 hashes constrain to the same event class.

Two attempts already made in the loop (the Codex review fired at
wake 286 never returned — likely OpenAI content policy filter
dropping the binary-RE context silently; documented at wake 312).
For future cross-model reviews, hand-paste into a fresh ChatGPT/
Claude/Gemini session yourself so refusals surface directly.

## Files to read first in next session

1. `analysis/state_machine_summary.md` — the canonical state-
   machine RE doc. § 1 has the 4-transition predicate table, § 4½
   has the secondary 12→13 writer, § 5 has the destroy mechanism,
   § 8 has the open-questions table including A3.1 (the
   `0xFE476177` hash question with full 50-hash family).
2. `analysis/session_retrospective_253.md` — fourth-stretch retro
   covering the state-machine RE closure arc (wakes 228-253).
3. `analysis/autonomous_worklog.md` (active) — wakes 254 → 333.
   Wake-284 has a comprehensive pause-reflection on the 267-283
   arc summarizing the destroy-event family findings + 5
   methodological filings. Wake-294 was the explicit loop stop;
   wakes 295-332 were post-stop signaling heartbeats while the
   user kept firing /loop.
4. `analysis/autonomous_worklog_through_253.md` (archive, sealed) —
   wakes 1-253. Look here for early state-machine findings (wakes
   8-13), V3-retry breakthrough context (wakes 1-50), and the
   wake-247 → 252 state-13→14 arc.
5. `analysis/state_13_14_writer_investigation.md` — the
   candidate-triage methodology log that wake-247 used to find
   `FUN_142ffbc50`. Pattern is reusable.
6. `analysis/crc32_FE476177_brute_force.py` — self-contained
   brute-force script ready for O3DE-corpus extension. 50-hash
   target dictionary embedded.
7. The live dashboard's Findings tab — 24 cards, particularly the
   wake-280 "Destroy-event scheduler" card and the wake-283
   "Indirect-vtable wall pattern" card surface the
   most-substantive arc findings in visitor-discoverable form.

## Frida hooks currently active

Per `tools/client-hooks/frida_dtls_hook.js` (unchanged during the
autonomous session — no hooks added, the loop is static-only).
The previous handoff's list (8 hooks) is current.

## Run commands (unchanged)

Same as the previous handoff. The replay-after-v3 pipeline +
heartbeat path are unchanged; the autonomous session didn't touch
the runtime code.

## Session stats (2026-05-06 → 2026-05-12)

- **Wakes**: 254 → 333 (~80 wakes, 7 days)
- **Commits to `claude/vacation-2026-05-06`**: ~80 (one per wake)
- **Branch**: still `claude/vacation-2026-05-06`, not yet merged
  to main — the maintainer can review the diff and choose to merge,
  rebase, or cherry-pick.
- **Tests**: 456 passing (+1 skipped), up from 84 at the start of
  the autonomous session
- **Decompiles**: 56, up from ~12
- **Findings cards**: 24 across 4 categories
- **Cross-check tests**: 19 in `CROSS_CHECK_MANIFEST` (55 total
  cross-check test functions)
- **Worklog files**: 2 — `autonomous_worklog_through_253.md`
  (sealed archive, 19476 lines) +
  `autonomous_worklog.md` (active, ~3000 lines for wakes 254-333)
- **Retrospectives**: 4 chained (150 / 196 / 227 / 253). No 5th
  retro yet — the 254-333 stretch is summarized in the wake-284
  pause-reflection inside the active worklog.
- **README "Recent milestones"**: 5 bullets newest-first, with
  the destroy-event sub-arc as the 5th (most-recent) entry.

## Open work-stream summary

| Work-stream | Status | Unblocker |
|---|---|---|
| Static-RE on post-V3 state machine | ✅ Complete through state 14 (static-RE limit hit at wake 252) | — |
| Codec library (40/40 captured) | ✅ Complete | — |
| `0xFE476177` event name | 🟡 ~1300 hash attempts no-match | O3DE corpus OR runtime trace |
| V3 retry root cause | 🟡 Send-scheduler vtable wall (wake 276) | Runtime trace |
| NewProxy / replica wire-type | 🟡 Indirect-vtable wall (wake 252) | Runtime trace |
| Phase-2D dispatched emission validation | 🟡 Shipped behind flags, untested live | Real-GPU host |
| Multi-peer support in `rep_responder.py` | 🟡 Not started | (Python work, no RE needed) |
| Carrier-level reliable ACK on V3 request | 🟡 5-line experiment, not yet tried | (Python work, no RE needed) |

Three of the static-RE items share **one unblocker**: real-GPU
Windows host with Frida. That session would resolve all three at
once.

---

## Previous handoff (2026-05-06 — pre-autonomous-session)

The version of this doc that set up the autonomous session has been
moved here for context. Skip to the relevant sections if you want
to see what was open at the start of the vacation.

### TL;DR

The V3 retry wall is broken (#5), the replay pipeline is complete
(substitution + DTLS-safe chunking + post-replay heartbeat — #7, #11,
#13, #15), and the connection now holds indefinitely after V3.

Wall now: **REP wrapper stays at state 10 forever.** Game shows a
black screen post-character-creation; no SM_DISCONNECT; client just
carrier-acks heartbeats. The wrapper-tick (`FUN_14644a070`) reads
some property of the GameConnection per-tick to decide when to
advance from state 10 to 11; the property it reads is unknown.

### The exact open question (as of 2026-05-06)

**Why doesn't the wrapper advance from state 10 to state 11?**

— Resolved during the autonomous session. See "What got resolved
during the autonomous session" above. The state-10→11 transition
is gated by `*(int*)(wrapper + 0xa0) == 2`, written on
`PlayerManagerSelfIdentificationMsg` (`0x5d1`) delivery.

### Frida hooks active as of 2026-05-06

8 hooks per `tools/client-hooks/frida_dtls_hook.js`. Unchanged
during the autonomous session (the loop is static-only).
