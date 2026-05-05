# Contributing to NWPrivateServer

Thanks for wanting to help. This project succeeds only if more people contribute — the work is too large for any one person and the window before server shutdown is finite.

This document covers: work areas, how to contribute captures, code style, and how to coordinate so people don't duplicate effort.

---

## Where to plug in

Pick the area that matches your skills. These are genuinely parallel workstreams — you do not need to understand the whole project to contribute to one.

### 1. Traffic capture (highest urgency — servers are still up)

No coding required. If you can run the game, you can contribute.

What we need: raw Javelin message dumps from as many players and game states as possible. Every unique session adds data we can use to reconstruct the protocol after shutdown.

See **[docs/capture-guide.md](docs/capture-guide.md)** for the exact capture procedure and submission format.

Priority captures right now:
- Any session that gets past the black screen into a loaded world
- Sessions with characters that have inventory items, quest state, or map progress
- Sessions from different regions (eu-central-1, sa-east-1, ap-southeast-2)
- Multiple login attempts from the same character on the same day (captures timing variance)

### 2. Reverse engineering (current blocker)

The current blocker is understanding why the client keeps retrying the V3 registration after our server responds with an accepted reply. The answer is inside two functions:

- **`FUN_14644a070`** (`gameconn_state`, RVA `0x0644a070`) — drives state-10→11 transition. Decompile this in Ghidra. Find what condition it checks to decide whether to advance state past 10.
- **`FUN_146b3c250 + 0x58f`** — the destroy trigger. Find what writes to `[R13+0xfd]` (the byte that fires the session-destroy loop).

If you do RE work, add findings as a dated entry in [docs/progress.md](docs/progress.md) or a new file under `analysis/`. Include the function RVA, what you found, and what it implies for the server behavior.

Tools already set up:
- Ghidra scripts: `tools/ghidra_scripts/JavelinHunt.py`, `tools/ghidra_scripts/FindChunkRegistrations.py`
- Frida hooks: `tools/client-hooks/frida_dtls_hook.js` (currently active hooks documented in [docs/next-session.md](docs/next-session.md))

### 3. Python / server implementation

Once RE identifies the post-V3 message sequence, someone needs to implement it in `server/rep_responder.py`. The file already handles the V3 registration exchange and replay of early captured messages — the next step is implementing whatever the client waits for after that.

Other server work that doesn't require RE breakthroughs:
- Tests for `server/javelin/v3_response.py`, `v3_request.py`, and `replay_store.py` (see [analysis of coverage gaps](docs/progress.md))
- Multi-peer support in `rep_responder.py` (currently single-peer only)
- SM_CT_ACKS reliable acknowledgment (currently not sent)

### 4. Documentation

Anything that reduces the ramp-up time for the next contributor is valuable. If you spent time figuring something out, write it down in `docs/` or `analysis/` so the next person doesn't have to.

---

## Coordination — avoiding duplicated effort

Before starting on something non-trivial, check if someone else is already working on it. The best place to announce what you're picking up is the community channel where you found this project. If you're opening a PR, the PR description is enough.

The session handoff notes (`docs/next-session.md`, `docs/handoff_*.md`) are written by whoever last made progress. They're the authoritative "current state" for the active gate. Read these before diving into RE or server work so you don't re-derive something already known.

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
- **Tests for new codec code.** If you add or change parsing/serialization logic in `server/javelin/`, add a corresponding test. The test files follow the pattern in `server/javelin/test_parser.py` — plain functions, no framework needed, run with `python -m`.
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

Add it to [docs/progress.md](docs/progress.md) under the relevant gate, or create a new file in `analysis/` for longer decomps.

---

## Single points of failure

The project deliberately tries to avoid knowledge living only in one person's head:

- Every significant finding goes into a file in this repo, not just a chat message.
- Session handoff notes (`docs/next-session.md`) are updated after each working session.
- The `info/` directory is for community-shared captures — if you have data, put it here so it doesn't disappear if you step away.
- If you are the only person who understands a particular module, please write a short doc-comment at the top of that file explaining what it does and why it's shaped the way it is.
