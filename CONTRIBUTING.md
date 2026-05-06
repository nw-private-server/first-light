# Contributing to NWPrivateServer

Thanks for wanting to help. This project succeeds only if more people contribute — the work is too large for any one person and the window before server shutdown is finite.

This document covers: work areas, how to contribute captures, code style, and how to coordinate so people don't duplicate effort.

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

### 2. Reverse engineering (current blocker)

The current blocker is understanding why the client keeps retrying the V3 registration after our server responds with an accepted reply. The answer is inside two functions:

- **`FUN_14644a070`** (`gameconn_state`, RVA `0x0644a070`) — drives state-10→11 transition. Decompile this in Ghidra. Find what condition it checks to decide whether to advance state past 10.
- **`FUN_146b3c250 + 0x58f`** — the destroy trigger. Find what writes to `[R13+0xfd]` (the byte that fires the session-destroy loop).

If you do RE work, drop findings in `analysis/` as a new `.md` or `.txt` file. Use a descriptive name (`analysis/state10_dispatcher.md`, `analysis/v3_request/BODY_DECODE.md` — see existing entries for the pattern). Include the function RVA, what you found, and what it implies for the server behavior.

Tools already set up:
- Ghidra scripts: `tools/ghidra_scripts/JavelinHunt.py`, `tools/ghidra_scripts/FindChunkRegistrations.py`
- Frida hooks: `tools/client-hooks/frida_dtls_hook.js` (the currently active hook list is captured in [docs/next-session.md](docs/next-session.md), which the maintainer keeps current)

### 3. Python / server implementation

Once RE identifies the post-V3 message sequence, someone needs to implement it in `server/rep_responder.py`. The file already handles the V3 registration exchange and replay of early captured messages — the next step is implementing whatever the client waits for after that.

Other server work that doesn't require RE breakthroughs:
- **Carrier-level reliable ACK on the V3 request** — currently we don't send one in the same envelope as the V3 response. Mixed Nuts' working impl does (`flag=0x18` piggyback). May or may not be the entire fix for the V3 retry loop; ~5 lines of code to test.
- **Multi-peer support** in `rep_responder.py` (currently single-peer only).
- **More codec coverage.** `test_codecs.py` covers the V3 round-trip; `frame.py`'s parse/marshal paths for the chunked / multi-record cases have less coverage.
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
