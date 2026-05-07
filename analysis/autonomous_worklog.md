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
- [x] **A2.** Decompile siblings on `param_1+0x130` — `FUN_145a92380`,
      `FUN_145a905c0`, `FUN_145a905d0`, `FUN_145a923c0`, `FUN_145a8d150`,
      `FUN_1402a1750` — to characterize the `GameConnectionWrapper` interface.
      **DONE 2026-05-07** — wrapper substate at `+0xa0` has three known
      values (0 fail / 1 in-progress / 2 ready); see worklog entry 2.
- [x] **A2.5.** Find code that writes `2` to `wrapper[+0xa0]`. **DONE
      2026-05-07** — `FUN_145a87010` is `onConnectionSuccess`: logs
      `"ConnectionSuccess"`, emits events, then writes substate=2. See
      `analysis/decomp_wrapper_substate_setter_candidate.txt`.
- [ ] **A2.6.** Trace xrefs to `FUN_145a87010` to find what *invokes* the
      ConnectionSuccess handler. That's the chain the V3-response path is
      supposed to trigger and apparently isn't.
- [ ] **A2.7.** Cross-reference the literal `"ConnectionSuccess"` string in
      the binary — there may be other Connection lifecycle handlers
      (`ConnectionFailed`, `ConnectionClosed`, etc.) that share the same
      registration mechanism. Mapping the full event table will tell us
      what flavor of message we need to send.
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

---

### 2026-05-07 — wake 2: A2 wrapper-vtable characterization

**Did:** Sequentially decompiled six wrapper-vtable siblings via
`ghidra decompile`. Outputs in `analysis/decomp_wrapper_*.txt`.

**Found (A2):** The `GameConnectionWrapper` (at GameConnection+0x130) has a
small, well-defined interface around a substate field at `+0xa0`. Five of
the six sibling functions are trivial accessors; the sixth is the state-10
setup. Concrete signatures:

| Function | Returns | Body |
|---|---|---|
| `FUN_145a92370` | bool | `*(int *)(this + 0xa0) == 2` — **state 10→11 gate (A1)** |
| `FUN_145a92380` | bool | `*(int *)(this + 0xa0) == 0` — "substate == 0" predicate |
| `FUN_1402a1750` | int* | `this + 0xa0` — getter, returns &substate |
| `FUN_145a905c0` | u8 | `*(u8 *)(this + 0xbc8)` — state 12 gate flag |
| `FUN_145a923c0` | u8 | `*(u8 *)(this + 0x252)` — state 13 gate flag |
| `FUN_145a8d150` | void* | `this + 0xbf8` — getter for some sub-object |
| `FUN_145a905d0(this, p2, p3)` | void | state-10 setup; **writes substate = 1**, initializes four list-like substructs at `+0x20`/`+0x48`/`+0x70`/`+0x98`, copies p3 fields into `+0xcb8..+0xcd0`, registers `"client-connection.retry-connection-till-server-ready"` listener at `+0xbf1` |

**Substate (`wrapper[+0xa0]`) lifecycle, derived from the above + yesterday's
FUN_14644a070 decomp:**

```
state 10 entry → FUN_145a905d0 sets substate = 1   (in-progress)
                 ???                  substate = 2 → FUN_145a92370 returns true → state 11
                 (failure)            substate = 0 → destroy path fires
```

So GameConnection state 10 holds until *some other code* writes `2` to
`wrapper[+0xa0]`. That writer is the post-V3 step the project is missing.
The destroy loop the maintainer is also chasing is the same field reverting
to 0 (via `FUN_1402a1750` getter + `*piVar8 == 0` check in FUN_14644a070).

**Cross-check with FUN_14644a070 (yesterday's decomp):** the substate-as-int
read used `FUN_1402a1750` — it's not a vtable thunk, it's a typed accessor
that returns &substate so the caller can deref or write. This matters for
A2.5: callers that write substate=2 may go through this accessor or may
write directly. Need to check both.

**Other interesting offsets surfaced:**
- `wrapper+0xa8` — assigned `param_2` of FUN_145a905d0 (callback or object ptr).
- `wrapper+0xb0` — vtable pointer that gets called as `(*(code *)**(...))()`
  immediately after substate=1 assignment.
- `wrapper+0xbc8`, `wrapper+0xbf0` — flag bytes initialized to 0 in setup.
- `wrapper+0xbf1` — feature-flag listener for retry-till-ready.
- `wrapper+0xc08`, `+0xcb8..+0xcd0`, `+0xcd8`, `+0xd68`, `+0xdd8` — payload
  buffers / nested structs initialized from p3.

**Next** (queued as A2.5):
- Find writers of `wrapper[+0xa0]` setting value 2. Likely a small Ghidra
  script doing instruction-pattern scan for `MOV [Rxx+0xa0], 2` is faster
  than chasing FUN_1402a1750 xrefs. Also check who calls `FUN_145a92370`
  (the gate) — anyone reading it might also be able to write it.
- After A2.5: A3 (destroy trigger at `FUN_146b3c250+0x58f`).

**Blockers:** None. Marking A2 done; A2.5 added to queue.

---

### 2026-05-07 — wake 3: A2.5 substate=2 writer found

**Did:**
- Wrote `tools/ghidra_scripts/FindWrapperSubstateWriters.py` — pattern-scans
  the binary for `MOV [reg + 0xa0], imm` instructions (grouped by imm value)
  and lists xrefs to `FUN_1402a1750` (the &substate accessor).
- Ran it via `ghidra script FindWrapperSubstateWriters analysis/decomp_substate_writers.txt`.
- Strategy 1 (pattern scan) returned 549 imm=2 hits — too noisy because many
  unrelated classes have a `+0xa0` field.
- Strategy 2 (FUN_1402a1750 xrefs) returned 3 callers; decompiled the two
  non-state-machine ones (`FUN_1426eb150`, `FUN_1426edaa0`). Both treat the
  returned `&substate` as an opaque identity token (passed to
  `FUN_14141c2b0` and `FUN_141681b00`), not as a writable substate pointer.
  **Strategy 2 was a dead end** — the accessor is being repurposed as a
  per-object key.
- Pivoted to filtering the 549 candidates by address range, restricting to
  the wrapper class neighborhood (`0x145a8xxxx` / `0x145a9xxxx`, since all
  known wrapper methods cluster from `0x145a8d150` to `0x145a923c0`).
  **One** hit in that region: `FUN_145a87010` at `0x145a87170`,
  `MOV dword ptr [R14 + 0xa0], 0x2`.
- Decompiled it.

**Found (A2.5):** `FUN_145a87010` is the **`onConnectionSuccess` handler** for
the wrapper. Body:

```c
void FUN_145a87010(GameConnectionWrapper *this) {
    /* logger setup */
    log("CJavelinActorGame", severity=3, ...);
    log("ConnectionSuccess");
    /* iterate observer collection from puVar8[0xc]..puVar8[0xd], emit events */
    *(int *)(this + 0xa0) = 2;   // <- the missing write
    return;
}
```

The `"ConnectionSuccess"` literal is the smoking gun — this is the success
callback for the wrapper's connection lifecycle. When invoked, it walks the
wrapper's observer/listener list emitting events, then advances substate to
2, which on the next GameConnection tick advances the state machine 10→11.

**The protocol picture is now:**

1. Client sends V3 RegistrationRequest.
2. Server sends V3 RegistrationResponse.
3. Client's response handler validates the response and calls some chain
   that ends at `FUN_145a87010(wrapper)`.
4. `FUN_145a87010` sets substate=2 + emits a `ConnectionSuccess` event.
5. Next GameConnection tick: `FUN_145a92370(wrapper)` returns true →
   `FUN_14645fd70(this, 0xb)` sets state=11 → log
   `"GameConnectionWrapper: actor game connection succeeds"`.

**The current server's V3 response is being accepted (per docs/next-session.md
"V3 response accepted by client; rep.ready flips 0→1") but step 3 is not
firing.** A2.6 (xref `FUN_145a87010`) will identify exactly which condition
gates the call.

**Why this matters for the server:** once we know what triggers
`FUN_145a87010`, we know what *additional* server-side message or response
shape is required. The README's "5-line Carrier reliable-ACK experiment" may
or may not be the right fix; A2.6 will tell us.

**Other interesting offsets surfaced:**
- `FUN_145a87010` calls `FUN_146161960` and `FUN_146165ff0` for severity
  filtering — typical AzCore/Lumberyard logging pattern.
- `FUN_1461aab40(puVar8)` followed by
  `FUN_1402b6e60(local_30, "ConnectionSuccess")` is the event emitter
  signature — the local_30 handle is then passed to `FUN_1461ae980`
  for each observer in the iteration.
- `puVar8[0xc]` / `puVar8[0xd]` (offsets 0x60/0x68) are the begin/end
  iterators of the observer list on the AzCore event broadcaster.

**Next** (A2.6 + A2.7 added to queue):
- A2.6: xref `FUN_145a87010` callers — find what invokes ConnectionSuccess.
  Add a small Ghidra script (`FindXrefs.py` taking an address arg).
- A2.7: cross-reference the `"ConnectionSuccess"` string for sibling
  handlers — there's almost certainly a `"ConnectionFailed"` etc. nearby,
  and mapping them tells us the full lifecycle event table.
- Then A3: destroy trigger.

**Blockers:** None. A2.5 marked done. Two new tasks on queue.
