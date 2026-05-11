# Contributing to New World: First Light

Thanks for wanting to help. This project succeeds only if more people contribute — the work is too large for any one person and the window before server shutdown is finite.

This document covers: quick start, work areas, how to contribute captures, code style, and how to coordinate so people don't duplicate effort.

**Public dashboard:** [nw-private-server.github.io/first-light](https://nw-private-server.github.io/first-light/) — the friendly project overview, captured-traffic charts, connection-state diagram, and codec/decompile catalog. Read this first to get the lay of the land.

---

## Quick start (code contributors)

```sh
# 1. Clone
git clone https://github.com/nw-private-server/first-light.git
cd first-light

# 2. Set up the venv
python3 -m venv .venv
source .venv/bin/activate
pip install pytest typer

# 3. Run the test suite
pytest server/javelin/
# expect 450+ passing (+1 skipped); the suite is the single source of
# truth for codec correctness. Scans the whole server/javelin/ dir, so
# it picks up the codec tests, the wake-157 shadow-decode tests, and
# the wake-162 build-tools tests at once. Use `server/javelin/` rather
# than bare `pytest`; root-level discovery picks up `server/test_client.py`,
# a CLI script that calls sys.exit on import without args.

# 4. Eyeball a captured message hands-on
python3 tools/decode_message.py --type 0x15d --replay-index 0 --direction R
# prints the decoded HeartbeatPing15D dataclass

# 5. (Optional) Browse the dashboard locally
python3 tools/build_site.py     # regenerate site/data.json
cd site && python3 -m http.server 8000
# then open http://localhost:8000
```

**Reference docs to read before opening a PR**:
- [analysis/public_api.md](analysis/public_api.md) — single-page API reference for `server.javelin` (auto-generated from `__init__.py`'s `__all__` + dispatcher; re-generate with `tools/build_api_reference.py`).
- [analysis/codec_library_overview.md](analysis/codec_library_overview.md) — layered architecture of `server/javelin/`, per-type module table, and a "how to add a new codec" walkthrough.
- [analysis/session_retrospective_253.md](analysis/session_retrospective_253.md) — most recent session retrospective (wakes 228-253: state-machine RE closure arc; all 4 post-V3 state-spawn transitions now have writers + trigger chains at static-RE level). Earlier retros in the README's "Recent milestones" section.
- [docs/post-v3-sequence.md](docs/post-v3-sequence.md) — the post-V3 message phases the captured replay covers.
- [analysis/state_machine_summary.md](analysis/state_machine_summary.md) — current state of the GameConnection state-machine RE: predicate table, trigger writers, and the wake-252 indirect-vtable wall that marks the static-RE limit. The state-10 unblock work (wakes 111-112) is now closed; the active blocker is runtime-side (real-GPU host with Frida).
- [analysis/autonomous_worklog.md](analysis/autonomous_worklog.md) — the active wake-by-wake working journal (wake 254 onwards). Earlier wakes (1-253) in [analysis/autonomous_worklog_through_253.md](analysis/autonomous_worklog_through_253.md). Long but searchable; tells you what's been tried.

**Quick on-ramp paths** (see also the "Want to contribute? Pick a path." section on the [dashboard's "How it works" tab](https://nw-private-server.github.io/first-light/)):
- **Add a new codec** — copy `server/javelin/session_clock_beacon.py` (fixed-shape) or `asset_blob_16a0.py` (variable-length). Register it in `server/javelin/dispatch.py`'s `DECODERS`/`ENCODERS`. Add a structural-rejection test + populated round-trip test to `test_codecs.py`. The dispatcher full-replay test auto-catches missed type-ids.
- **Add a test** — codec-level: round-trip + structural-rejection pattern in `test_codecs.py`. Wider coverage: `test_shadow_decode.py` (mock-self pattern with recording log handler) or `test_build_tools.py` (pure-helper unit tests). Run `.venv/bin/pytest server/javelin/ -q`.
- **Refresh the dashboard** — `.venv/bin/python3 tools/build_site.py` rebuilds `site/data.json` + shields.io badges. Pages auto-deploys on every push to the working branch. The public-API reference regenerates via `tools/build_api_reference.py` — re-run after touching `__init__.py` or a class docstring.

---

## Where to plug in

Pick the area that matches your skills. These are genuinely parallel workstreams — you do not need to understand the whole project to contribute to one.

### 1. Traffic capture (high urgency — servers are still up)

No coding required. If you can run the game, you can contribute.

What we have: one full login-to-state=53 capture in `info/nw-login-safe-20260502-153840/` (177 messages, `0x0..0xb0`, character successfully spawned in-world). That is the baseline reference. What we still need is **variety** (different regions, characters, scenarios) and **depth** (longer in-world sessions).

See **[docs/capture-guide.md](docs/capture-guide.md)** for the exact capture procedure and submission format.

Priority captures right now:
- **Extended in-world sessions.** Movement, combat, NPC interaction, zone transitions, inventory use — anything that exercises the post-spawn protocol. Our existing capture stops shortly after spawn.
- **Different regions** (eu-central-1, sa-east-1, ap-southeast-2). Cross-region comparisons reveal which fields are region-specific vs. global.
- **Different character states.** A character with significant inventory / quest progress / housing produces different StateBundle content than a fresh one.
- **Edge cases.** Login failures, queue arrivals, mid-session disconnects, character creation flow.
- **Additional happy-path logins** are still useful as cross-validation against the existing baseline, especially if from a different account.

### 2. Reverse engineering (static-RE largely complete; runtime is the next leg)

The Gate-2 retry loop — the client re-sending V3 every ~500ms after our server accepts the response — is still the active gate. The post-V3 state-machine RE has progressed substantially though:

- **State-10→11**: wake 111-112 closed it. Trigger is `PlayerManagerSelfIdentificationMsg` (wire type `0x5d1`); predicate is `*(int*)(wrapper + 0xa0) == 2`. Codec wire-bound in `server/javelin/self_ident.py`; awaiting runtime test.
- **State-11→12**: auto-fires once 10→11 lands (no separate trigger).
- **State-12→13**: wake 232/234 — `LevelInfoChangedMsg` primary path identified.
- **State-13→14**: wake 247/249 — writer `FUN_142ffbc50` fires from 5 local handlers; one copies a 0x70-stride collection into `wrapper[+0x1b8]`. Wake 252's upstream trace hit an **indirect-vtable wall at `0x14816cec0`** — the static-RE limit on this question.

Remaining static-RE worth pursuing:
- **`FUN_146b3c250 + 0x58f`** — the destroy trigger. Find what writes to `[R13+0xfd]` (the byte that fires the session-destroy loop). This may be the V3-retry root cause and is independent of the state-spawn ladder.
- **NewProxy / GridMate replica wire-type identification** — the wake-252 analysis estimates the MVP server-side message set as SelfIdent + LevelInfoChanged + a replica-creation message. The third is currently hypothesized as GridMate `NewProxy`; runtime trace is the natural confirmation.

If you do RE work, drop findings in `analysis/` as a new `.md` file. See [`state_13_14_writer_investigation.md`](analysis/state_13_14_writer_investigation.md) for the candidate-triage methodology used to identify FUN_142ffbc50.

Tools already set up:
- Ghidra scripts: `tools/ghidra_scripts/JavelinHunt.py`, `tools/ghidra_scripts/FindChunkRegistrations.py`
- Frida hooks: `tools/client-hooks/frida_dtls_hook.js` (the currently active hook list is captured in [docs/next-session.md](docs/next-session.md), which the maintainer keeps current)

### 3. Python / server implementation

Once RE identifies the post-V3 message sequence, someone needs to implement it in `server/rep_responder.py`. The file already handles the V3 registration exchange and replay of early captured messages — the next step is implementing whatever the client waits for after that.

Other server work that doesn't require RE breakthroughs:
- **rep_responder ↔ dispatcher integration phase-2.** The wake-157 shadow-decode scaffold routes every inbound record through `server/javelin/dispatch.py` at debug-log level; wake 204 promoted 0x15d (heartbeat) to authoritative dispatcher emission behind the `heartbeat_use_dispatcher` flag (default off, proven byte-equivalent to the captured replay path). Wake 208 added counter-advance under `heartbeat_advance_counter` so dispatched heartbeats progress like a real server. Both flags are awaiting real-GPU runtime validation to observe whether they affect the gate-2 retry loop. Next wire-type promotion candidate: any inbound type that lockdown tests already pin against the shadow-decode log (search `_shadow_decode_record` callers in `test_shadow_decode.py`).
- **Carrier-level reliable ACK on the V3 request** — currently we don't send one in the same envelope as the V3 response. Mixed Nuts' working impl does (`flag=0x18` piggyback). May or may not be the entire fix for the V3 retry loop; ~5 lines of code to test.
- **Multi-peer support** in `rep_responder.py` (currently single-peer only).
- **Capture replay validation.** Make `_pump_replay` more configurable from the CLI (timing jitter, drop simulations) so we can stress-test the replay path.

### 4. Documentation

Anything that reduces the ramp-up time for the next contributor is valuable. If you spent time figuring something out, write it down in `docs/` or `analysis/` so the next person doesn't have to.

---

## Coordination — avoiding duplicated effort

Before starting on something non-trivial, check if someone else is already working on it. The best place to announce what you're picking up is the community channel where you found this project. If you're opening a PR, the PR description is enough.

The maintainer keeps `docs/next-session.md` and `docs/progress.md` current as a working journal across Claude Code sessions. They're the most accurate "current state" reference for the active gate, so read them before starting RE or server work. You don't need to update them — that's a maintainer task. Your contribution belongs in code, tests, captures, or `analysis/` notes.

---

## Submitting a capture

See [docs/capture-guide.md](docs/capture-guide.md). Short version:
- Export as a redacted xxd-style dump (sensitive fields replaced with `XX`)
- Include a `README.md` in the submission folder describing what game state was captured
- Open a PR adding it under `info/<capture-name>/`

---

## Code style

The codebase is Python 3.11+. There is no linter or formatter enforced yet, but follow what you see:

- **Type hints on all function signatures.** `from __future__ import annotations` at the top of each file.
- **Dataclasses for wire structs.** See `MessageRecord`, `V3RegistrationRequest`, `ReplayMessage` for the pattern.
- **No comments explaining what code does.** Only add a comment when the *why* would surprise a reader: a hidden constraint, a protocol quirk discovered by RE, a workaround for a specific observed client behavior.
- **Protocol decisions belong in comments or docs, not just in code.** If you add a magic constant because of something you saw in Ghidra, say so: `# Carrier byte 0x80 = plaintext envelope per field observed at FUN_140f77eb0+0x3c`.
- **Tests for new codec code.** If you add or change parsing/serialization logic in `server/javelin/`, add a corresponding test. Follow the pattern in `server/javelin/test_codecs.py` — plain `test_*` functions discovered by pytest. Run the suite with `pytest`; CI will run it on your PR automatically.
- **One thing per PR.** A protocol fix, a new test suite, a new analysis document — not all three. Easier to review, easier to pick up if the author disappears.

---

## RE findings format

When documenting a Ghidra finding, use this structure so it's searchable later:

```
## FunctionName (RVA 0xXXXXXXXX)  — date

**What it does:** one sentence

**Key fields / offsets:**
- `struct+0xNN` — what this field means
- ...

**Implication for server:** what we need to send / handle differently
```

Save it as a new file in `analysis/` (e.g. `analysis/state10_dispatcher.md`). Longer decomps can live in their own subdirectory like `analysis/v3_request/`.

---

## Single points of failure

The project deliberately tries to avoid knowledge living only in one person's head:

- Every significant finding goes into a file in this repo, not just a chat message. `analysis/` for RE notes, `docs/` for protocol or process documentation, `info/` for shared captures.
- The `info/` directory is the long-term home for community-shared captures — if you have data, put it here so it doesn't disappear if you step away.
- If you are the only person who understands a particular module, please write a short doc-comment at the top of that file explaining what it does and why it's shaped the way it is.
