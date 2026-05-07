# Autonomous worklog — vacation 2026-05-07 → ~2026-05-12

This file is appended to by an autonomous Claude session running in `/loop`
self-paced mode while the maintainer is on vacation. Each entry is a single
wake-up cycle: what was attempted, what was found, what's next. Read top-down
to follow progress; the **task queue** at the top reflects current priority.

## How to read this

- Latest entry is at the bottom. Add new entries; do not edit prior ones except
  to mark a task done in the queue.
- Every commit on this branch (`claude/vacation-2026-05-06`) corresponds to one
  or more worklog entries. `git log --oneline claude/vacation-2026-05-06` is
  the fastest way to scan.
- "Blocked on user" items get pulled out into the **Queued for maintainer**
  section. Run those when you check in.

## Task queue (priority order)

Rooted in the 2026-05-06 decomp finding: state-10→11 is gated by
`FUN_145a92370(param_1 + 0x130)`, where `+0x130` is a `GameConnectionWrapper`
sub-object. The whole vtable on that sub-object drives states 10→14.

- [x] **A1.** Decompile `FUN_145a92370`. What does it actually check? This is
      the immediate state-advance predicate. **DONE 2026-05-07** — it's
      `*(int *)(wrapper+0xa0) == 2`. See
      `analysis/decomp_state_advance_predicate.txt`.
- [ ] **A2.** Decompile siblings on `param_1+0x130` — `FUN_145a92380`,
      `FUN_145a905c0`, `FUN_145a905d0`, `FUN_145a923c0`, `FUN_145a8d150`,
      `FUN_1402a1750` — to characterize the `GameConnectionWrapper` interface.
- [ ] **A3.** Decompile `FUN_146b3c250 + 0x58f` — find what writes
      `[R13+0xfd]` (the byte that triggers the destroy loop, per
      `docs/next-session.md`).
- [ ] **A4.** Trace xrefs to `FUN_14645fd70` (the state setter) to confirm
      no other code paths advance state past 10 outside of `FUN_14644a070`.
- [ ] **A5.** Update `analysis/ghidra_findings.md` with the consolidated
      state-machine map.
- [ ] **B1.** Once A1–A5 give a confident hypothesis: implement & test the
      "Carrier-level reliable ACK on V3 request" experiment in
      `server/rep_responder.py`. Run `pytest`. Do **not** ship if tests fail
      or if the change touches more than ~10 lines without a separate writeup.

## Queued for maintainer (blocks on you)

*(empty — populate as the loop runs)*

## Hard rules (durable for this loop)

- Never push to `main`. Never open a PR. Never force-push.
- Never edit files outside this repo.
- Never run any process that survives the loop (no detached daemons, no
  background `caffeinate`, no Frida).
- After every meaningful change: commit on this branch and push to origin.
  Commit messages should be self-contained — the maintainer reads them on
  their phone.
- If a Ghidra job runs longer than 5 minutes for a single decompile, kill it
  and write up the partial finding instead.
- If unsure whether an action is in scope: write the question into
  "Queued for maintainer" and move on.

## Wake log

(entries appended below by each loop iteration)

---

### 2026-05-07 — kickoff (manual, before /loop)

**Did:**
- Created branch `claude/vacation-2026-05-06`.
- Committed the `tools/ghidra` wrapper + `HeadlessDecompile.py` from yesterday's setup.
- Decompiled task **A1**: `ghidra decompile 0x145a92370 --out analysis/decomp_state_advance_predicate.txt`.

**Found (A1):** The state-10→11 predicate is a one-line check:

```c
bool FUN_145a92370(GameConnectionWrapper *this) {
    return *(int *)(this + 0xa0) == 2;
}
```

So the gate is: `GameConnection.wrapper[+0x130].field[+0xa0] == 2`. State stays at 10 until *something else* writes `2` to that offset on the wrapper. The wrapper sub-object is GameConnection-relative `+0x130`, so the absolute offset on GameConnection is `+0x1d0`.

**Implications:**
- We now have a precise hunt target: find the writer of `[wrapper+0xa0]`. That writer is what the V3 response is *supposed* to trigger and apparently isn't.
- The siblings (`FUN_145a905c0`, `FUN_145a923c0`, etc.) likely test the same field with different values (e.g., 3, 4) for the subsequent state transitions — A2 will confirm.
- Once A2 is done, an xref hunt on writes-of-2-to-`[+0xa0]`-on-this-class is the path to "what message advances the wrapper substate."

**Next** (the /loop will pick up from here):
- A2: decompile the wrapper-vtable siblings to map the substate→state-transition table.
- Then: find writers of `wrapper+0xa0`. May need a small Ghidra script (xref by offset on a class, since we don't have a typed class yet).

**Blockers:** None. Marking A1 done in the queue.
