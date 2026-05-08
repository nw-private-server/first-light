# Autonomous worklog — extended session starting 2026-05-07

This file is appended to by an autonomous Claude session running in `/loop`
self-paced mode. Each entry is a single wake-up cycle: what was attempted,
what was found, what's next. Read top-down to follow progress; the **task
queue** at the top reflects current priority.

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
- [x] **A2.6.** Trace xrefs to `FUN_145a87010` to find what *invokes* the
      ConnectionSuccess handler. **DONE 2026-05-07** — `FUN_146454c00` is
      the `PlayerManagerSelfIdentification` message handler; it
      unconditionally calls `FUN_145a87010` on success. RTTI string at
      `0x14a153fd0` gives us the C++ type:
      `Javelin::ClientMessagesTrait::PlayerManagerSelfIdentificationMsg`.
- [x] **A2.7.** Cross-reference the literal `"ConnectionSuccess"` string
      in the binary. **DONE 2026-05-07** — the wrapper's
      `FUN_145a87010` (which writes substate=2) is one of two layers.
      At the **JavelinGame layer**, two sibling handlers exist:
      `FUN_14103b570` = `JavelinGame::OnConnectionSucceed` and
      `FUN_14103b1a0` = `JavelinGame::OnConnectionFail`. They use the
      same AzCore observer-broadcast pattern (iterate
      `puVar8[+0x60..+0x68]`, call `FUN_1461ae980` per observer). Fail
      handler logs "Lost connection to REP. Exiting..." on a specific
      branch (`param_2 == 0`). See worklog wake 14.
- [x] **A2.8.** Find the wire format for `PlayerManagerSelfIdentificationMsg`.
      **PARTIAL 2026-05-07** — handler-side field shapes mapped via the
      three wrapper setters (`FUN_145a9fa10/30/80`); see worklog wake 5.
      Wire-format decode (the actual byte layout) still pending — needs
      dispatcher path to find serializer.
- [~] **A2.9.** Find the dispatcher / serializer for
      `PlayerManagerSelfIdentificationMsg`. **PARTIAL 2026-05-07** — the
      thunk at `0x146454bec..0x146454bf3` is a MSVC virtual-base `this`
      adjustment thunk (`MOVSXD; SUB; JMP`), NOT a deserializer.
      Dispatch-table layout at `0x14abcc15c` not fully decoded — values
      like `0x09cc1c44` look like data-segment RVAs but don't match
      zlib CRC32 of any candidate message name. See worklog wake 6.
- [ ] **A2.9b.** Find a different anchor into the deserializer chain.
      Approaches to try: (a) decompile the OTHER vtable entry where
      `FUN_145a87010` was referenced (the DATA xref at `0x14ab72930`);
      (b) look for `Reflect()` methods of `PlayerManagerSelfIdentificationMsg`
      — Lumberyard's serializer uses the AZ EditContext / SerializeContext
      reflection registered there; (c) search for the message size /
      `OnReceived` in the class's static methods.
- [ ] **A2.9c.** If dispatch decoding stays hard from the binary alone,
      switch to a runtime approach: write a Frida hook (in
      `tools/client-hooks/`) that traps `FUN_146454c00` invocation to
      log the args at runtime. Marked as queued-for-maintainer because
      it requires the live game client.
- [~] **A2.10.** Decompile `PlayerManagerRejectedMsg` handler.
      **PARTIAL 2026-05-07** — handler not yet found. The literal
      `"PlayerManagerRejected"` does not appear as a log string anywhere,
      and the 9 handlers logging on `"GameMessagePort"` don't include it.
      Mapped the full GameMessagePort handler set instead (see wake 7).
      Next: search xrefs of `FUN_141721c20` (the trace logger used by
      SelfIdentification) for siblings, and check other log channels
      ("Javelin", "ClientHub", etc.).
- [ ] **A2.11.** Map xrefs to `FUN_141721c20` to find siblings of
      SelfIdentification logged on the same trace channel. The Rejected
      handler may live there.
- [ ] **A2.12.** Decompile `FUN_146448cd0` ("LoadContextAndLevel failed -
      no self identification"). This function complains when self-id is
      missing and likely runs in the same tick that watches the destroy
      flag — could resolve A3 as a side-effect.
- [x] **A3.** Decompile `FUN_146b3c250 + 0x58f` — find what writes
      `[R13+0xfd]`. **DONE 2026-05-07** — `FUN_146b3c250` is
      `TransportLayerGridMateTickThread`; `[+0xfd]` is a skip-timeout-
      and-flush flag on the GridMate Carrier. Sole writer is
      `FUN_140fb3560:452` gated by event-id `0xFE476177` (likely an
      AZ::Crc32 hash of some teardown event name). See worklog wake 8.
- [~] **A3.1.** Identify the AZ::Crc32 string for `0xFE476177`.
      **PARTIAL 2026-05-07** — 65 candidate names tried (lifecycle /
      network / Carrier / GridMate / Replica), no match in zlib CRC32
      or its lowercased variant. Binary contains 29 references to the
      32-bit constant `0xFE476177` (across 28 functions) and one is
      the writer site we already know. The hash literal appears bare
      (no adjacent source string), consistent with **release-build
      AZ::Crc32 with the string stripped** — a common Lumberyard
      pattern. Static reversal looks impractical without a wordlist
      from the original source. See worklog wake 9.
- [ ] **A3.1b.** If A3.1 stays static-blocked: defer to runtime —
      write a Frida hook on `FUN_140fb3560` to log the event-id arg
      structure when called. Already queued for maintainer as part of
      A2.9c; this would be a same-hook second-purpose use.
- [x] **A4.** Trace xrefs to `FUN_14645fd70` (the state setter) to confirm
      no other code paths advance state past 10 outside of `FUN_14644a070`.
      **DONE 2026-05-07** — found 4 distinct callers of the raw setter,
      5 distinct callers of a public wrapper `FUN_146466650`, AND
      recovered the full state-name table at `0x1484f9ff0`. Notably:
      `LevelInfoChanged` handler (`FUN_146446800`) directly forces state
      to 13 — so `LevelInfoChangedMsg` is **also** required in the
      post-V3 server message sequence (not just SelfIdent). See
      `analysis/state_machine_summary.md` updated tables. See worklog
      wake 11.
- [x] **A4.1.** Trace writers of `wrapper[+0xbc8]` (the state-12 gate).
      **DONE 2026-05-07** — single hit: `FUN_145a9fa00` (one-line
      setter) called from `FUN_14645c660`, which is itself a message
      handler in the same dispatch table as
      `PlayerManagerSelfIdentification` (DATA xref at `0x14abcc45c`).
      So another `ClientMessagesTrait` message advances the state-12
      gate. See worklog wake 12.
- [~] **A4.2.** Trace writers of `wrapper[+0x252]` (the state-13 gate).
      **PARTIAL 2026-05-07** — 3 imm=1 hits but all in unrelated
      classes (UI, Wwise audio, JSON). Real wrapper writer must use
      a non-immediate store pattern. Different scan approach needed.
- [~] **A4.3.** Identify which message is handled by `FUN_14645c660`.
      **PARTIAL 2026-05-07** — message catalog is much bigger than
      `ClientMessagesTrait` (3482 `InstallRegistrationHook<T>` types),
      and the handler RVA has only one reference (the dispatch entry
      itself), so no static Register-by-name site exists. Strong
      candidates by name: `OnHubConnectionChangedMsg@PlayerManagerTrait`,
      `ActorInitializedMessage@Hub`, `OnPlayerActorStatusChangedMsg`.
      Static identification impractical; Frida hook (already queued
      for maintainer) resolves it cleanly. See worklog wake 13.
- [~] **A2.11.** Map xrefs to `FUN_141721c20` to find siblings of
      SelfIdentification. **DEFERRED 2026-05-07** — 99 callers in the
      binary, no obvious filter pattern that would surface
      PlayerManagerRejected; nothing in the SelfIdent address
      neighborhood except the SelfIdent handler itself. Static path
      to find the Rejected handler is exhausted; runtime hook (already
      queued) is the only feasible route.
- [x] **A5.** Update `analysis/ghidra_findings.md` with the consolidated
      state-machine map. **DONE 2026-05-07** — written as
      `analysis/state_machine_summary.md` (cleaner standalone doc;
      `ghidra_findings.md` is older session-specific notes and should
      stay as-is). Synthesizes A1–A3 into one maintainer-friendly
      writeup with end-to-end protocol diagram.
- [ ] **B1.** Once A1–A5 give a confident hypothesis: implement & test the
      "Carrier-level reliable ACK on V3 request" experiment in
      `server/rep_responder.py`. Run `pytest`. Do **not** ship if tests fail
      or if the change touches more than ~10 lines without a separate writeup.

## Queued for maintainer (blocks on you)

- **TOP PRIORITY (sharpened wake 26): does `FUN_146454c00` fire
  for the seq 0x7 message during a live replay?** The byte-level
  capture audit confirmed there is NO `00 01 91 17` (community
  dump's Phase 9b SelfIdent signature) anywhere in the captured
  session. The only `0x91`-prefixed frame is `00 01 91 19` at
  seq 0x7 (4 bytes, type 0x651) — which the community dump labels
  Phase 5 INIT, not Phase 9b SelfIdent. Two possibilities:
  - **(A)** The capture genuinely doesn't contain SelfIdent →
    fix requires a fresh capture with the SelfIdent message.
    No amount of server-side tuning advances state 10→11.
  - **(B)** This build's SelfIdent is `0x91(0x19)` (= type 0x651)
    and the community dump's `0x91(0x17)` is from a different
    build → seq 0x7 IS the SelfIdent already in our replay
    window, and the stall is from substitution / seq ordering /
    ack shape.

  The Frida hook on `FUN_146454c00 (0x146454c00)` resolves it
  in one observation: hook at function entry, log when fires,
  run a replay session and watch. If it fires when seq 0x7
  arrives, (B) is correct and we chase substitution. If never,
  (A) is correct and we need new captures.
- **A2.9c (Frida hook for FUN_146454c00 args).** Static decoding of the
  Javelin dispatch table entry at `0x14abcc15c` is harder than expected
  (the wire-format / message-ID column doesn't decode as zlib CRC32 of
  any candidate name). When you next have the live client running, a
  Frida hook on `FUN_146454c00 (0x146454c00)` that logs the seven
  in-args (especially `param_6` and `param_7`) would give us the full
  byte layout from a single capture session. Roughly 30 lines of Frida
  in the style of `tools/client-hooks/frida_capture.py`.
- **`PlayerManagerSelfIdentificationMsg` in fact decoded?** The wire
  format is not yet known. Until A2.9 / A2.9b lands, the server cannot
  *send* this message — only know that it should. Don't merge any
  server-side experiment that pretends to send it.

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

---

### 2026-05-07 — wake 4: A2.6 — message name pinpointed

**Did:**
- Wrote a generic `tools/ghidra_scripts/FindXrefs.py` (takes function
  address + optional output path).
- Ran it for `FUN_145a87010`. Two refs: a vtable DATA entry at
  `0x14ab72930` and one direct call from `FUN_146454c00` at `0x14645563f`.
- Decompiled `FUN_146454c00` (477 lines).
- Wrote `tools/ghidra_scripts/FindStringXrefs.py` for literal-string xref
  hunts (had to fix a Jython `unicode()` issue on first run).
- Ran it for `"PlayerManagerSelfIdentification"` to corroborate.

**Found (A2.6):** `FUN_146454c00` is the **`PlayerManagerSelfIdentification`
message handler**. Smoking-gun evidence:

1. The function's **first action** is a structured logger call:
   ```c
   FUN_141721c20("GameMessagePort", "PlayerManagerSelfIdentification");
   ```
   It logs the message name on the `GameMessagePort` channel — this is
   how Lumberyard message handlers identify themselves.

2. The handler reads field values from the message body (`param_6`),
   stores them onto the GameConnection via offsets `-0x7e8`, `-0x7e0`,
   `-0x7c0`, `-0x7bc`, `-0x7b4`, then resolves the wrapper sub-object:
   ```c
   lVar14 = pGame[+0x1e0][clientSdk[+0x10]] + 0x130;   // = wrapper
   ```
   and calls three wrapper setters with message fields:
   ```c
   FUN_145a9fa10(wrapper, param_3);
   FUN_145a9fa30(wrapper, param_7);
   FUN_145a9fa80(wrapper, param_4);
   ```

3. **At the very end of any success path** (line 474 of the decomp):
   ```c
   FUN_145a87010(local_c0);   // = onConnectionSuccess(wrapper)
   ```
   No conditions on the call. Reaching the end of the handler ⇒
   substate=2 ⇒ state-10→11 advance. There's also an early-success goto
   `LAB_14645563b` at line 395 that skips the final `FUN_14167c060`
   payload step but still reaches the ConnectionSuccess call.

4. Bonus confirmation from RTTI: a defined string at `0x14a153fd0` is
   the demangled-form fragment of a mangled type name:
   ```
   .?AV<lambda_1>@?1???$InstallRegistrationHook
       @VPlayerManagerSelfIdentificationMsg@ClientMessagesTrait@Javelin@@@Hub@Amazon...
   ```
   So the C++ class is **`Javelin::ClientMessagesTrait::PlayerManagerSelfIdentificationMsg`**,
   registered via a template `Javelin::Hub::Amazon::...::InstallRegistrationHook<T>`.

**This is a brand-new finding for the project.** A grep across `docs/`,
`analysis/`, and `info/` found zero prior mentions of
`PlayerManagerSelfIdent*` or `ClientMessagesTrait`. The maintainer's
existing notes say "V3 response accepted, rep.ready flips 0→1, then the
session is destroyed after ~30s" — the missing piece between those two
events is **the server failing to send a `PlayerManagerSelfIdentificationMsg`
after V3**. The client waits for that message, doesn't get it, sits in
state 10, and eventually gets torn down.

**The message body shape** (inferred from the handler's reads of `param_6`):
- `param_6[0]` (4 bytes) — copied to `GameConnection-0x7e8` (some int id)
- `param_6[2]..` — passed to `FUN_1402d13a0` for setup at `-0x7e0`
- `param_6[10]` (1 byte) — flag, stored at `-0x7c0`; non-zero triggers the
  debug-virtual-slice spawn-position branch
- `param_6[0xb]` (8 bytes) — copied to `-0x7bc`
- `param_6[0xd]` (4 bytes) — copied to `-0x7b4`
- `param_3`, `param_4`, `param_7` — additional setter args (likely
  player name strings, character data, world id)

So the field layout is roughly: `int id; <handle>; bool debugFlag; long
something; int something; string name; ...; string something`. Need to
decompile `FUN_145a9fa10/30/80` to fully decode.

**Why the project's V3 response alone isn't enough:** The V3 path only
gets the wrapper through state-10 *entry* (substate=1). The actual
"connection succeeded" semantic event lives in a separate, named message
(`PlayerManagerSelfIdentificationMsg`) sent later. Without it, the
connection appears half-formed — the client knows it has a session but
not which player the session is for, so the wrapper's onConnectionSuccess
handler never fires.

**The new state of "what does the server need to do":**

1. ✅ HTTPS / OmniSDK auth
2. ✅ Javelin REP DTLS handshake
3. ✅ V3 RegistrationRequest accepted, V3 RegistrationResponse sent
4. ⏳ **Server must send a `PlayerManagerSelfIdentificationMsg`** with
   the player's identity info. Wire format TBD (A2.8).
5. (Then state advances 10→11 and post-V3 message path begins.)

**Next** (A2.7 + A2.8 added to queue):
- A2.8 (the headline next task): figure out the wire format of
  `PlayerManagerSelfIdentificationMsg`. Best approach: decompile
  `FUN_145a9fa10`/`30`/`80` to see exact field shapes; cross-reference
  with the project's `docs/gridmate-reference.md` for chunk/message
  serialization conventions.
- A2.7: scan for sibling lifecycle strings.
- A3: destroy trigger.

**Blockers:** None. A2.6 marked done. Two new tasks on queue.

---

### 2026-05-07 — wake 5: A2.8 partial — handler fields + sibling message inventory

**Did:**
- Decompiled the three wrapper setters consumed by
  `PlayerManagerSelfIdentification` (`FUN_145a9fa10`, `FUN_145a9fa30`,
  `FUN_145a9fa80`).
- Searched the binary for `"PlayerManager*"` strings via `FindStringXrefs`.
- Searched for `"ClientMessagesTrait"` to enumerate sibling messages.
- Cross-referenced with the project's existing `analysis/javelin_chunks.txt`
  and `analysis/javelin_classes.txt` to see what's already cataloged.

**Found (A2.8 partial — handler-side):** All three setters are simple
struct-copy operations. The message handler signature reduces to:

```
PlayerManagerSelfIdentification(
  GameConnection *gc,           // param_1
  ?,                            // param_2  -- not used in the path that
                                //             reaches FUN_145a87010
  Tuple36 *param_3,             // -> wrapper[+0xaf8..+0xb18] (5 fields:
                                //   8+8+8+8+4 = likely uuid+uuid+int)
  Tuple36 *param_4,             // -> wrapper[+0xb84..+0xba4] (same shape)
  ?,                            // param_5
  MsgBody *param_6,             // 28-byte inline header read into
                                //   gc[-0x7e8..-0x7b4]
  StringPlus17 *param_7         // AZStd::string + (8+8+1) tail
);
```

`param_6` field map (offsets relative to `param_6` base, byte-precise):

| Bytes | wrapper field | Likely meaning |
|---|---|---|
| `[0..4]` | `gc[-0x7e8]` (int) | id / sequence number |
| `[8..]` (via FUN_1402d13a0) | `gc[-0x7e0]` | sub-struct, possibly a handle |
| `[10*8 = 0x50, 1B]` | `gc[-0x7c0]` (bool) | debug-virtual-slice flag |
| `[0xb*8 = 0x58, 8B]` | `gc[-0x7bc]` | long (timestamp? token?) |
| `[0xd*8 = 0x68, 4B]` | `gc[-0x7b4]` | int |

Note: `param_6[N]` is `param_6 + N*8` because Ghidra typed it as
`undefined4 *` — those are pointer-array indices, not byte offsets, so
the actual struct is sparser than it looks.

**Found (A2.8 BIG):** The full sibling message list of `ClientMessagesTrait`
came back from the string scan. The trait registers exactly five `Msg`
subclasses via `InstallRegistrationHook<T>` (mangled-name fragments at
`0x14a153xxx`):

1. `DebugCommandResponseMsg` (string at `0x14a153610`)
2. `RemoteConfigChangedMsg` (`0x14a153890`)
3. `LevelInfoChangedMsg` (`0x14a153b20`)
4. **`PlayerManagerRejectedMsg`** (`0x14a153db0`) ← rejection-path sibling
5. **`PlayerManagerSelfIdentificationMsg`** (`0x14a153fd0`) ← our target

Plus a `State` enum (`0x14a154860`), the trait itself (`0x14a154a80`),
and a constructor instantiation (`0x14a1551e0`). The project's existing
chunk inventory in `analysis/javelin_chunks.txt` only knew about
`Javelin::BehaviorTreeComponentClientMessages` — it scanned for the
wrong namespace. **`ClientMessagesTrait` is the entire client-side
message catalog and was previously uncataloged.**

**Implications for the protocol model:**

The server's V3 RegistrationResponse leaves the client in state 10 with
substate=1, *waiting on a follow-up message from `ClientMessagesTrait`*.
The trait has exactly two outcomes for player registration:

- `PlayerManagerSelfIdentificationMsg` → success → state advances to 11
- `PlayerManagerRejectedMsg` → failure → likely fires the destroy loop

This **also probably resolves task A3** (find what writes `[R13+0xfd]`
in the destroy path). `PlayerManagerRejectedMsg`'s handler is the strong
candidate — it would write a "rejected" flag the destroy poll watches.
A2.10 added to the queue to verify.

The other three messages (`DebugCommandResponse`, `RemoteConfigChanged`,
`LevelInfoChanged`) are post-registration, post-state-11 traffic — not
needed for MVP "enter a static world" but useful for full session
fidelity.

**Wire-format decode (still pending):**

The handler-side field shape doesn't tell us how the bytes arrive over
DTLS. The serializer/dispatcher path is needed for that. Two leads:

1. The DATA xref of `FUN_146454c00` at `0x14abcc15c` is a dispatch-table
   entry. Looking at neighboring entries (same fixed stride) should
   reveal the message ID column. A2.9 picks this up.
2. The `?` caller at `0x146454bf3` (13 bytes before `FUN_146454c00`) is
   probably a thunk that converts raw chunk bytes to typed args before
   calling the handler. Decompiling whatever function contains that
   address will show the deserialization step.

**Next** (A2.9 + A2.10 added to queue):
- A2.9: decode dispatch-table entry at `0x14abcc15c` and read `0x146454bf3`'s
  enclosing function for the deserializer.
- A2.10: locate `PlayerManagerRejectedMsg` handler (corroborates A3).

**Blockers:** None. A2.8 marked partial-done; two new tasks queued.

---

### 2026-05-07 — wake 6: A2.9 — dispatch table inspected, layout not decoded

**Did:**
- Wrote `tools/ghidra_scripts/DumpDataWindow.py` (qword-wise data dump
  with xref hints) and `tools/ghidra_scripts/DumpInstructionsWindow.py`
  (walks instruction list around an address since Ghidra hadn't
  auto-recognized this region as a function).
- Dumped data around `0x14abcc15c` (the DATA xref of `FUN_146454c00`).
- Disassembled around `0x146454bf3` (the "?" UNCONDITIONAL_CALL).
- Tested the CRC32-message-id hypothesis against several candidate
  strings (zlib CRC32 of e.g. `"PlayerManagerSelfIdentificationMsg"`,
  case variants, fully-qualified names).

**Found (A2.9 partial):**

1. **The "?" caller at `0x146454bf3` is a MSVC virtual-base thunk**, not
   a dispatcher:
   ```
   146454bec  MOVSXD RAX, dword ptr [RCX + -0x4]
   146454bf0  SUB RCX, RAX
   146454bf3  JMP 0x146454c00
   ```
   This is a standard `this`-pointer adjustment thunk for virtual
   inheritance. It implies `FUN_146454c00` is a method of a class with
   a multi-base layout, and dispatch through one of the bases needs
   to subtract a vbtable offset before calling.

2. **The dispatch table at `0x14abcc15c` stores 32-bit RVAs**, not
   full pointers. The 32-bit value at `0x14abcc15c` is `0x06454c00`
   (= image_base + this = `0x146454c00` = `FUN_146454c00`). The 32-bit
   value 4 bytes earlier (`0x14abcc158 = 0x09cc1c44`) was suspected to
   be the message ID, but **CRC32 didn't match** any candidate name:
   ```
   PlayerManagerSelfIdentificationMsg               -> 0x1f79112b
   PlayerManagerSelfIdentification                  -> 0xad1c494e
   ClientMessagesTrait::PlayerManagerSelfIdent...   -> 0x8abf028d
   ```
   None match `0x09cc1c44`. The values at those positions look more
   like RVAs into the `.rdata` segment (image_base + 0x09cc1c44 =
   `0x149cc1c44`, which contains binary blob data — could be vtables,
   reflection metadata, or AZ TypeIds).

3. **Also seen in the table**: `0x06454bec` (the address of the thunk
   itself) appears at `0x14abcc154`, just before the data RVA at
   `0x14abcc158` and the handler RVA at `0x14abcc15c`. So adjacent
   columns appear to be `(thunk_or_alt_handler, data_blob_rva, handler)`
   — a 12-byte triple? But surrounding rows don't follow that stride
   cleanly. The layout is more complex than a simple `(id, fn)` table.

**Why progress stalled:** Static decoding of Javelin's dispatch table
from raw bytes is high-effort because the structure isn't a plain
flat array. It looks like an AZ-style typed registry (probably with
TypeId-keyed lookup) rather than a numeric ID table. Resolving it
fully needs either (a) a deeper class-hierarchy walk in Ghidra, or
(b) a runtime sample showing what value the dispatcher uses for the
lookup. Both are doable, but (b) is faster — hence the
queued-for-maintainer Frida task.

**Pivoting tasks for next iteration:**
- A2.9b: try the OTHER vtable xref of `FUN_145a87010` (at `0x14ab72930`).
  That's a separate anchor — if it's a vtable for a registration class,
  walking its slots may show the deserializer entry alongside the
  handler.
- A2.9c (queued for maintainer): Frida hook to log args at the live
  call site. Single fastest path to wire format if the static path
  stays dead-end.
- A2.10 stays high priority — if `PlayerManagerRejectedMsg` is the
  destroy trigger, finding its handler resolves task A3 simultaneously.

**Blockers:** None for the loop, but one item moved to "Queued for
maintainer" (A2.9c — Frida runtime hook).

---

### 2026-05-07 — wake 7: A2.10 — full GameMessagePort handler set mapped

**Did:**
- Searched for `"PlayerManagerRejected"` literal — only the RTTI mangled
  string matched; no plain log line. Searched for `"Rejected"` broadly:
  21 hits, none in `Javelin::ClientMessagesTrait` namespace.
- Probed adjacent code RVAs in the dispatch table around `FUN_146454c00`
  (`FUN_146455680`, `FUN_146455820`) thinking they might be sibling
  handlers; they're not — one is a thread-task-queue flush, the other
  is a render-math helper.
- Pivoted: searched for `"GameMessagePort"` literal xrefs to enumerate
  the entire set of handlers logging on that channel.

**Found (A2.10 partial):** Nine functions reference `"GameMessagePort"`
as a log argument:

| Address | First identifying string | Role |
|---|---|---|
| `FUN_146454c00` | `"PlayerManagerSelfIdentification"` | ✅ KNOWN — success handler |
| **`FUN_146446800`** | `"LevelInfoChanged"` | **NEW** — sibling trait message handler |
| **`FUN_146448cd0`** | `"LoadContextAndLevel failed - no self identification"` | **NEW** — failure-detect helper |
| `FUN_14644b280` | `"Switch coming from clientContextInstanceId..."` | Context switch |
| `FUN_14644d960` | `"Attempted to reset region interest..."` | Region/Coatlicue util |
| `FUN_146463540` | `"Reset"` | Some reset handler |
| `FUN_14643e7b0` | `"MayHandleReplicationUnreliable() returning false..."` | Replication check |
| `FUN_146455e90` | `"ProcessPendingReliableMsgQueue processing %zu..."` | Reliable-msg queue |
| `FUN_14103d820` | `"Attempted to reset region interest..."` | Region/Coatlicue util |

**Implications:**

1. **`LevelInfoChangedMsg` handler is `FUN_146446800`** — confirms one of
   the five `ClientMessagesTrait` siblings inferred from RTTI. The
   project now has handler addresses for two of the five.

2. **`PlayerManagerRejectedMsg` handler is NOT in this set.** Possible
   reasons: (a) it logs on a different channel ("Javelin",
   "ClientFlow", etc.), (b) it doesn't log at all, (c) the trace logger
   used (`FUN_141721c20`) is different from the GameMessagePort log
   functions and the Rejected handler uses only the trace path.

3. **`FUN_146448cd0` is a high-value lead for A3 (destroy trigger).**
   Its log line `"LoadContextAndLevel failed - no self identification"`
   says "I'm checking if self-id happened, and it didn't." That's
   exactly the polled-each-tick check that would write the destroy
   flag at `[R13+0xfd]`. Strong candidate for A3 resolution.

**Why static-only RE on the Rejected handler is hard:** the trait
template `InstallRegistrationHook<T>` instantiates a lambda per-message,
and lambdas are anonymous functions Ghidra labels as `FUN_*`. Without
a unique log string or RTTI cross-link, distinguishing Rejected from
the other ClientMessagesTrait handlers requires walking the dispatch
table — which we already established is tricky to decode statically.

**Next** (queued):
- A2.11: enumerate xrefs to `FUN_141721c20` (the specific trace logger
  used by SelfIdent) and look at the second argument string of each
  call site. Sibling handlers using the same trace channel will surface
  there.
- A2.12: decompile `FUN_146448cd0` — likely resolves A3 (destroy
  trigger) by showing what flag is set on the "no self identification"
  failure path.

**Blockers:** None.

---

### 2026-05-07 — wake 8: A2.12 partial + A3 SOLVED

**Did:**
- Decompiled `FUN_146448cd0` (the "no self identification" check from
  wake 7's GameMessagePort scan).
- Decompiled `FUN_146b3c250` (the destroy-loop function from
  `docs/next-session.md`).
- Built a generalized writer-hunt script
  (`tools/ghidra_scripts/FindOffsetWrites.py`) and scanned for
  `MOV [reg + 0xfd], 1` across the whole binary.
- Decompiled the unique hit and identified the gating condition.

**Found (A2.12 outcome):** `FUN_146448cd0` is *not* the destroy trigger.
It's `LoadContextAndLevel` — a function that pre-checks self-id and
LevelInfo flags before initializing the client context. Three failure
paths log on `"GameMessagePort"`:
- `[gc+0x1a0] == 0` → "no self identification"
- `[gc+0x190] == 0` → "missing LevelInfo"
- `pGame == nullptr` → "pGame is nullptr"

Useful side find: `gc[+0x1a0]` is the "self-id received" flag (set by
the SelfIdentification handler somewhere — corroborates A2.6).
`gc[+0x1a1]` is set on successful `LoadContextAndLevel` completion.

**Found (A3 — solved):** The destroy flag at `[+0xfd]`:

1. `FUN_146b3c250` is **`TransportLayerGridMateTickThread`** — the
   GridMate Carrier tick thread. Identified via line 116 string literal
   passed to a thread-name setter.
2. The check at `FUN_146b3c250+0x58f` (line 333 of the decomp):
   ```c
   if (*(char *)(param_1 + 0xfd) == '\0') {
       if (currentTime <= queueItemTimestamp + delayMs) break;
   }
   processItem();
   ```
   So `[+0xfd] != 0` doesn't directly *destroy* — it tells the tick
   loop to **skip the timeout check** and force-process all queued
   items before destruction. Effectively a "shutdown is happening,
   flush" flag.
3. **Sole writer** found via instruction scan: `MOV [reg + 0xfd], 1`
   matched **exactly one** instruction across all 32M instructions.
   It's at line 452 of `FUN_140fb3560`:
   ```c
   else {
       if (iStack_38 != -0x1b89e89) return;  // 0xFE476177
       *(undefined1 *)(param_4 + 0xfd) = 1;
   }
   ```
4. So the chain is: some component dispatches event with id `0xFE476177`
   to `FUN_140fb3560` → carrier flush flag set → next tick force-flushes
   → destruction follows.

**Outer dispatch context (FUN_140fb3560):** function takes
`(param_1, param_2, param_3, param_4=carrier?, param_5=event)`. It
dispatches based on `*(param_5 + 0x28)` (outer event type) and a nested
`iStack_38` (sub-event type). Magic constants seen, all looking like
AZ::Crc32 hashes:
- Outer key: `-0xc98de07` = `0xF36721F9`
- Sub-event keys: `0x578a1f75`, `0x20edcd6c`, `-0xd2f448c` =
  `0xF2D0BB74`, `-0x1b89e89` = `0xFE476177` (← destroy-flag key)

**Why this is good news for the project:** the ~30s session destroy
isn't actively triggered by the server. It's a **client-side timer**
that eventually dispatches event `0xFE476177` to the carrier. The fix
is delivering `PlayerManagerSelfIdentificationMsg` *before* whatever
internal timer reaches the destroy event.

**Two new generic offset-writer hunts now possible** with the new
`FindOffsetWrites.py` script — useful for any "what writes this byte"
question in the future.

**Next** (A3.1 added; queue now): A3.1 (Crc32 reversal of `0xFE476177`
to discover the event name), A2.11 (FUN_141721c20 trace-logger xrefs
for Rejected handler), A4 (FUN_14645fd70 setter xrefs), A5
(consolidated state-machine doc).

**Blockers:** None.

---

### 2026-05-07 — wake 9: A3.1 — CRC reversal blocked by stripped strings

**Did:**
- Tried `0xFE476177` against 65 candidate strings (lifecycle / Carrier /
  GridMate / Replica / network / common Lumberyard idioms). Both raw
  CRC32 and lowercased CRC32 attempted. **Zero matches.**
- Wrote `tools/ghidra_scripts/FindConstant.py` and searched the binary
  for the 32-bit pattern `0xFE476177`. **29 hits across 28 functions**
  including the writer site we already had at `FUN_140fb3560`.
- Decompiled one of the new sites (`FUN_1402af830`) to see the constant
  in context. Pattern looks like `AZ::Crc32` / `AZ::Name`-style struct
  construction:
  ```c
  local_60 = &PTR_LAB_147ef8d50;     // suspected AZ::Name vtable
  local_58 = 0xfe476177;             // hash
  local_54 = 0; local_4c = 0; local_4a = 0;
  (**(code **)(*param_4 + 0x608))(param_4, &local_60, DAT_147efa330, 0);
  ```
  `param_4+0x608` is some vtable method on a registry-like object;
  initially looked like an Ebus subscribe with handler.
- Resolved `DAT_147efa330` thinking it was a handler pointer.

**Found (anti-finding):** `DAT_147efa330` is **not** a handler pointer.
It's a float constant pool entry — 516 xrefs across the binary, and the
bytes are `400000003fc00000` (= the floats `1.5f` followed by `2.0f`).
So `+0x608` is some math / weight-tuned method, not a subscribe call.
The initial "this is a register-handler call" interpretation was wrong.

**Why static CRC reversal looks impractical:**

The constant `0xFE476177` appears bare in the binary with no adjacent
source string literal at any of the 29 hit sites. This is consistent
with Lumberyard's `AZ::Crc32` compile-time evaluation: when AZ_CRC is
used in a release build, the compiler folds the `Crc32(string)`
constructor into a literal `uint32_t` and the source string is stripped
from the binary. There's no way to reverse this from static analysis
without:
- a wordlist of all possible event names (CRC32 brute-force is
  computationally expensive even for short strings — `0xFE476177` would
  need ~2^32 attempts at worst, and meaningful name-shaped strings are
  a tiny fraction of that space), or
- a debug build / matching PDB (we have neither), or
- a runtime capture (Frida hook).

**A3.1 decision:** Marked as PARTIAL. Will not pursue further static
reversal in the loop. Recommended to the maintainer that any future
Frida hook (already queued under A2.9c) also log the event id at
`FUN_140fb3560` entry to identify the event name from the live game.

**A3.1b queued** to capture the runtime path explicitly when the
maintainer runs that Frida session.

**Did not waste the iteration:** A new generic tool now exists
(`FindConstant.py`) for any future "find this 32-bit value in the
binary" need. And we now know the broad pattern of where these CRC
hashes are constructed (the `local_60 = &PTR_LAB_147ef8d50; local_58 =
<hash>` idiom, used 29+ times for `0xFE476177` alone — so probably
the entire codebase uses this for its hashed identifiers).

**Next** (A2.11, A4, A5 from existing queue):
- A2.11: trace logger (`FUN_141721c20`) xref scan for the missing
  PlayerManagerRejected handler.
- A4: xrefs of `FUN_14645fd70` (state setter) to confirm no other
  paths advance the GameConnection state.
- A5: consolidated state-machine writeup that synthesizes A1–A3 into
  a single document for the maintainer.

**Blockers:** None for the loop. The Crc32 reversal is genuinely a
static-analysis dead end given the binary configuration.

---

### 2026-05-07 — wake 10: A5 — synthesis document

**Did:**
- Surveyed existing `analysis/*.md` for style conventions
  (`ghidra_findings.md`, `ctd_investigation.md`).
- Wrote `analysis/state_machine_summary.md` — a single
  maintainer-friendly synthesis of the morning's work (A1, A2, A2.5,
  A2.6, A2.8, A3, A3.1).

**Found (A5 outcome):** Nothing new — pure consolidation. The doc:

- Opens with a TL;DR identifying
  `Javelin::ClientMessagesTrait::PlayerManagerSelfIdentificationMsg`
  as the single missing message, and noting that the ~30s session
  death is a client-side timer (`0xFE476177` event), not server-driven.
- Tables out the full state-10→14 transition predicates with their
  exact wrapper-offset checks.
- Documents the substate-field semantics (0/1/2) and identifies the
  unique `FUN_145a87010` writer (the `onConnectionSuccess` handler).
- Catalogs the full `ClientMessagesTrait` class set (5 messages).
- Diagrams the end-to-end protocol — both the failure case (current)
  and the desired case (with SelfIdent inserted).
- Lists what the server still needs to know (wire format, timing).
- Calls out remaining open questions (A2.7, A2.9, A2.10, A2.11, A3.1,
  A4) so the maintainer knows where the loop left off.

**Why now:** After 9 wakes the worklog has accumulated enough findings
that a phone-only reader needs a single document to see the picture
without scrolling through wake-by-wake narrative. The synthesis is also
useful internally for the loop — future wakes can reference one doc
instead of replaying the whole worklog.

**Length / scope:** ~250 lines, one ASCII protocol diagram, four tables.
Stays at the level the maintainer can read from a phone in a few
minutes.

**Filename choice:** `state_machine_summary.md` rather than appending
to the older `analysis/ghidra_findings.md`. The old file is dated
session-specific notes from 2026-04-17 with its own format and
narrative. Mixing in 2026-05-07 findings would obscure both. Cleaner to
have a focused new doc and let the older one remain a snapshot of its
session.

**Next** (A2.11, A4 from queue):
- A2.11: trace-logger xref scan to find the still-missing
  `PlayerManagerRejectedMsg` handler.
- A4: confirm `FUN_14645fd70` (state setter) has no callers other than
  `FUN_14644a070` — closes the question of whether *other* code paths
  could advance state past 10.

**Blockers:** None.

---

### 2026-05-07 — wake 11: A4 done + state-name table; A2.11 deferred

**Did:**
- Ran `FindXrefs` on `FUN_14645fd70` (state setter from
  `next-session.md`). 4 distinct callers, not just the state machine.
- Followed up with `FindXrefs` on `FUN_146466650` (a state-setter
  wrapper that surfaced as a caller).
- Decompiled the three non-state-machine callers and read the
  state-name string-pool array at `0x1484f9ff0`.
- Tried `FindXrefs` on `FUN_141721c20` (trace logger) for A2.11.
  99 callers, no clean filter; only one in the SelfIdent neighborhood
  and that's the SelfIdent handler itself.

**Found (A4):**

1. **The state machine has a public wrapper.** Most state changes go
   through `FUN_146466650(gc, newState)` which logs
   `"Update state %s to new state %s"` then calls the raw setter
   `FUN_14645fd70`. Tracing the raw setter alone undercounts.
2. **Distinct callers of `FUN_14645fd70` (raw):** 4 functions —
   `FUN_14644a070` (state machine), `FUN_146466650` (wrapper),
   `FUN_146446800` (LevelInfoChanged handler), `FUN_14642d2d0`
   (Disconnected helper).
3. **Distinct callers of `FUN_146466650` (wrapper):** 5 functions —
   `FUN_14644a070`, `FUN_146425cb0`, `FUN_14642d950`, `FUN_14645ca20`,
   `FUN_146468370`. New names worth investigating if mapping the
   full state-change graph.
4. **`FUN_146446800` (LevelInfoChanged handler) directly sets state
   to 0xd = 13** (`WaitingForPlayerSpawn`). So
   `LevelInfoChangedMsg` *also* advances the state machine, not just
   `PlayerManagerSelfIdentificationMsg`. The post-V3 server message
   sequence requires both.
5. **`FUN_14642d2d0` is a Disconnected helper** — sets state to 0 on
   teardown.
6. **Full state-name table recovered.** Array at `0x1484f9ff0`:

   ```
   0  Disconnected
   1  QueryGameUpdateCheck
   2  WaitingForGameUpdateCheck
   3  QueueGameLogin
   4  WaitingForQueuedLogin
   5  QueryForRemoteConfigClass
   6  WaitingForRemoteConfigClass
   7  ObtainREPRequirements
   8  WaitingForREPRequirements
   9  StartREPConnection
   10 WaitingForREPConnection         <- where we sit
   11 WaitingForActorGameConnection   <- what SelfIdent unlocks
   12 WaitingForSpawnPoint
   13 WaitingForPlayerSpawn           <- forced by LevelInfoChanged
   14 InGame
   ```

   `analysis/state_machine_summary.md` updated with this table and
   the LevelInfoChanged-forces-13 note.

**Why this matters for the server:**

```
state 10 (REP)  -- PlayerManagerSelfIdentificationMsg --> 11 (Actor)
state 11        -- ?                                  --> 12 (SpawnPoint)
state 12        -- LevelInfoChangedMsg                --> 13 (PlayerSpawn)
state 13        -- ?                                  --> 14 (InGame)
```

The MVP target is state 14 (`InGame`). Server needs **at minimum**
SelfIdent + LevelInfoChanged. The 11→12 and 13→14 transitions are
gated by wrapper flags (`+0xbc8`, `+0x252`) whose writers haven't
been traced — those may need additional server messages.

**A2.11 deferred:** 99 trace-logger callers, no static filter,
runtime hook (queued for the maintainer) is the practical answer.

**Next** (queue updated, two new tasks):
- A4.1: trace writers of `wrapper[+0xbc8]` (the state-12 gate). What
  produces this byte = 1?
- A4.2: trace writers of `wrapper[+0x252]` (the state-13 gate).
- A2.7 still queued (sibling lifecycle handlers in the observer
  table that `FUN_145a87010` walks).

**Blockers:** None.

---

### 2026-05-07 — wake 12: A4.1 done, A4.2 partial, second message handler exposed

**Did:**
- Ran `FindOffsetWrites 0xbc8 0x1` (state-12 gate) — 1 hit in 32M
  instructions.
- Ran `FindOffsetWrites 0x252 0x1` (state-13 gate) — 3 hits, all
  unrelated classes.
- Decompiled the state-12 writer and its single caller.
- `FindXrefs` on the caller.

**Found (A4.1 — clean win):**

1. **`FUN_145a9fa00`** is a 9-line single-purpose setter:
   ```c
   void FUN_145a9fa00(longlong param_1) {
       *(undefined1 *)(param_1 + 0xbc8) = 1;
   }
   ```
   Located adjacent to the other wrapper public methods
   (`FUN_145a9fa10/30/80`).

2. **One caller**: `FUN_14645c660`, a tiny bridge:
   ```c
   void FUN_14645c660(longlong param_1) {
       lVar1 = FUN_1406d97d0(param_1 + -0x930);
       if (pGame != 0) {
           FUN_145a9fa00(
               pGame[+0x1e0][clientSdk[+0x10] * 8] + 0x130   // wrapper
           );
       }
   }
   ```
   Same wrapper-resolution expression as the SelfIdent handler.

3. **`FUN_14645c660` itself is a message handler.** Xrefs:
   - DATA at `0x14abcc45c` — same dispatch table as
     `FUN_146454c00` (SelfIdent at `0x14abcc15c`), 0x300 bytes away.
   - Thunk JMP at `0x14645c65b`, same MSVC virtual-base
     `this`-adjustment pattern.

   So `FUN_14645c660` handles **another `ClientMessagesTrait`
   message** — name TBD (queued as A4.3).

**Found (A4.2 partial):** 3 hits for `MOV [reg+0x252], 1`:
- `FUN_143dd6b20` — UI/text helper (`{value}/{maxCount} - %s`).
- `FUN_1473ed090` — Wwise audio plugin (`AkSoundSeedWoosh`).
- `FUN_14752dcd0` — JSON-ish helper (`caseId`/`context`).

All look like unrelated classes. The real wrapper writer must use
a non-immediate store pattern (register-based, struct-copy, or
memcpy). Need a different scan.

**Implications for the protocol:**

The post-V3 server message sequence is **at least three messages**
(possibly four):

```
state 10 → 11   PlayerManagerSelfIdentificationMsg   (FUN_146454c00)
state 11 → 12   ?  another trait msg                  (FUN_14645c660)
                   sets wrapper[+0xbc8] = 1
state 12 → 13   LevelInfoChangedMsg                   (FUN_146446800)
state 13 → 14   ?  TBD via A4.2 follow-up
```

Earlier picture said "two messages." Today's finding moves it to
"three or four." The state-machine summary doc should be updated
once A4.3 names the new message.

**Why this iteration was efficient:** the `FindOffsetWrites` script
has now nailed three single-writer findings (substate=2 for state
10→11, the destroy-flush flag, and now state-12 gate). The state-13
gate is the first false-result; informative — the script's
immediate-store assumption doesn't always hold.

**Next** (queue updated):
- A4.3: identify the `ClientMessagesTrait` message handled by
  `FUN_14645c660`. Same approach as A2.6 — examine surrounding
  dispatch table layout and any log strings near the function entry.
- A4.2 follow-up: scan for register-based / memcpy writes to the
  wrapper's `+0x252` field.

**Blockers:** None.

---

### 2026-05-07 — wake 13: A4.3 partial — dispatch is table-driven, runtime needed

**Did:**
- Got DATA xrefs for both known message handlers in the dispatch
  table: LevelInfoChanged at `0x14abcbb74`, SelfIdent at
  `0x14abcc15c`. Compared to state-12 trigger at `0x14abcc45c`.
- Dumped windows around all three to infer table layout.
- Searched the binary for the literal RVA `0x0645c660`
  (= `FUN_14645c660`) to find any register-by-pointer site.
- Searched the full binary for `InstallRegistrationHook<T>` mangled
  type names to enumerate the message catalog.

**Found (A4.3 — partial):**

1. **Dispatch table layout** is consistent across rows: 16-byte
   stride with columns `(thunk_a, thunk_b, metadata_rva, handler_rva)`.
   For SelfIdent and LevelInfoChanged the metadata column points
   into the `0x149cc xxxx` region (`.rdata` AZ-RTTI metadata).
   For state-12 trigger the metadata column is `0x0977d3f0`,
   pointing into a *different* `.rdata` segment (`0x140977 xxxx`),
   suggesting a different message-type category in the same table.

2. **The handler RVA `0x0645c660` has exactly one reference** — the
   dispatch table entry itself. So there's no `Register("Name",
   handler)` style registration site discoverable from static
   analysis. The dispatch is purely table-driven (probably built
   at compile time from the `InstallRegistrationHook<T>` template
   instantiations).

3. **The full message catalog is enormous.** A `FindStringXrefs` for
   `"InstallRegistrationHook"` matched **3482** mangled type names.
   Beyond `ClientMessagesTrait` (5 messages) there are at least:
   - `PlayerManagerTrait` — 28 messages (BanPlayer, KickAllPlayers,
     OnHubConnectionChanged, OnPlayerActorStatusChanged,
     OnPublishedCharacterMetadata, ProcessSpawnQueue,
     ReceiveCharacterMetadata, etc.)
   - `Hub*` — 20+ messages (ActorInitializedMessage,
     ActorStatusNotificationMessage, etc.)
   - `HubLifecyclePeeringTrait`, `HubEndpointSharingTrait`,
     `HubLifecycleStateListenerTrait`, etc.
   - `ActorMover`, `ServerContext`, `EbusMessage`, hundreds of
     component-facet messages in `ClientMessages`.

4. **Strong candidates by semantic name** for what the state-12
   trigger message could be:
   - `ActorInitializedMessage@Hub` — fits "actor game connection
     established" semantics of state 11 → 12.
   - `OnHubConnectionChangedMsg@PlayerManagerTrait` — same general
     fit.
   - `OnPlayerActorStatusChangedMsg@PlayerManagerTrait`.
   These can't be confirmed without identifying the
   metadata-column entry at `0x140977d3f0` or via runtime capture.

**Conclusion:** Static A4.3 hits the same wall as A3.1 and A2.10 — the
binary's release-build configuration has stripped enough metadata
that name-level identification of arbitrary handlers from a
table-only registration is impractical. The Frida hook on
`FUN_14645c660` (or the dispatcher itself) would log the message
name + body in a single live capture session. Same hook setup as
the A2.9c task already queued for the maintainer.

**Project picture stable:** even without the message name, the
*existence* of a third post-V3 trigger is established. The
maintainer now knows to:
- Send `PlayerManagerSelfIdentificationMsg` (state 10→11).
- Send *some* message handled by `FUN_14645c660` (state 11→12; one
  of the candidates above).
- Send `LevelInfoChangedMsg` (state 12→13).
- Send *something* that flips `wrapper[+0x252]` (state 13→14, A4.2
  follow-up).

**Next** (queue rotates):
- A2.7: scan the observer table that `FUN_145a87010` walks for
  sibling lifecycle handlers — may surface other client-side
  events worth knowing about.
- A4.2 follow-up: register-based-store scan for `wrapper[+0x252]`
  (probably extending FindOffsetWrites with a "MOV-then-MOV"
  detector).
- B1 (server experiment) is still gated behind wire-format
  decoding which is gated behind the Frida hook.

**Blockers:** None for the loop. Three tasks (A2.10, A3.1, A4.3)
all converge on the same maintainer-queued action: a Frida hook on
`FUN_146454c00` *and* `FUN_14645c660` *and* `FUN_140fb3560` to
capture message names and event ids at runtime. Logging a few
messages from a live session would resolve all three at once.

---

### 2026-05-07 — wake 14: A2.7 — sibling lifecycle handlers found at JavelinGame layer

**Did:**
- Searched for plausible sibling lifecycle strings: `ConnectionFailed`,
  `ConnectionClosed`, `ConnectionLost`, `ConnectionAborted`,
  `ConnectionDisconnected`, `ConnectionRejected`, `OnDisconnect`. Most
  came back with zero hits. `OnDisconnect` had 4 hits (one for
  `Popup_OnDisconnection`, one for `'OnDisconnected'` event, one for
  `CGame::OnDisconnection`, plus an EOSSystemComponent RTTI string).
- Searched broadly for `"Connection"` — 195 hits, scanning showed
  the smoking gun: **`'JavelinGame::OnConnectionSucceed'`** at
  `0x147fc8998` and **`'JavelinGame::OnConnectionFail'`** at
  `0x147fc89d0` (adjacent — clearly a Succeed/Fail pair).
- Single xref each: Succeed → `FUN_14103b570`, Fail → `FUN_14103b1a0`.
- Decompiled both.

**Found (A2.7):**

The connection-lifecycle event flow has **two layers**:

1. **Wrapper layer** (`FUN_145a87010`, mapped on 2026-05-06):
   logs `"ConnectionSuccess"` on the wrapper's own logger, walks the
   wrapper's observer list, then writes
   `*(int *)(wrapper + 0xa0) = 2`. There's only one handler at this
   layer — no `Failed`/`Lost` counterparts on the wrapper (failure
   on the wrapper is detected by the substate going back to 0, not
   by a sibling event).

2. **JavelinGame layer** (`FUN_14103b570` and `FUN_14103b1a0`,
   adjacent in the binary):
   - `FUN_14103b570` = `JavelinGame::OnConnectionSucceed` — uses the
     same AzCore observer-broadcast structure as the wrapper's
     handler, severity=3 (debug-level trace).
   - `FUN_14103b1a0` = `JavelinGame::OnConnectionFail` — same pattern
     but severity=1 (error). Takes
     `(this, param_2, reasonStruct *param_3, retryCount param_4)`,
     emits `"JavelinGame::OnConnectionFail: Reason: <reason>"`,
     iterates the same `puVar8[+0x60..+0x68]` observer list. Has
     branches based on `param_2 == 0` and `*(this+0x3d8) != '\0'`:
     - One path logs `"Lost connection to REP. Exiting..."` and
       calls a vtable method on a global at `DAT_14a7ba0e0+0x78`
       — likely the UI popup trigger.
     - Other paths inspect retry vars (`shouldRetryConnect`,
       `isErrorRetryable`, `currentRetryCount`).

**What this clarifies / closes:**

- **The wrapper's onConnectionSuccess (`FUN_145a87010`) and JavelinGame's
  OnConnectionSucceed (`FUN_14103b570`) are layered**, not redundant.
  The wrapper handles the substate transition; JavelinGame handles
  the higher-level UI / retry / lifecycle event broadcast.
- The "Lost connection to REP. Exiting..." log site is in
  `FUN_14103b1a0`. This is likely close to where the carrier-destroy
  event (CRC `0xFE476177` from A3) gets dispatched — but I didn't
  trace the dispatch chain from this function this iteration.

**What this does NOT solve:**

- The PlayerManagerRejected handler (A2.10) is still unmapped. The
  rejection-side handler probably lives in the same `Hub` /
  `JavelinGame` namespace but doesn't use the
  `JavelinGame::OnConnection*` log signature.
- The "Lost connection to REP" branch of `FUN_14103b1a0` is a strong
  candidate for being the source of the destroy CRC `0xFE476177`,
  but confirming that needs another pass tracing the vtable[+0x120]
  call on the `DAT_14a7ba0e0+0x78` object.

**Other findings from the broad `"Connection"` scan worth noting:**

- `'GameConnectionWrapper: spawn point found'` at `0x1484fea88` — log
  for the state-12→13 transition success (when `wrapper[+0xbc8]`
  flips). Useful breadcrumb if traced to a writer.
- `'Popup_OnConnectionFail_MainMenu'` and `'Popup_OnConnectionFail_InWorld'`
  at `0x147fc7e80/0x147fc7ea0` — UI popup names triggered by the fail
  path. Could be useful for client-side state inspection.
- `'CGame::OnDisconnection'` at `0x1484fd118` — global disconnect
  handler reference. Different layer again.

**Next** (queue still has plenty):
- A4.2 follow-up (register-based-store scan for `wrapper[+0x252]`).
- Trace the "Lost connection to REP" path in `FUN_14103b1a0` to see
  if it dispatches the destroy CRC `0xFE476177` (A3 follow-up;
  closes the loop on the destroy mechanism).
- B1 (server-side experiment) is still gated on knowing wire format.

**Blockers:** None for the loop. The runtime-hook items remain queued
for the maintainer.

---

### 2026-05-07 — wake 15: destroy-trigger trace partial; OnConnectionFail "exiting" is a separate UI-quit path

**Did:**
- Got xrefs of `FUN_140fb3560` (the unique destroy-flag writer from
  A3): exactly one direct caller, `FUN_140fadbc0`.
- Decompiled `FUN_140fadbc0` — a 2-line vtable adapter:
  ```c
  void FUN_140fadbc0(p1, longlong *param_2, p3, p4) {
      uVar1 = (**(code **)(*param_2 + 0x60))(param_2);
      uVar2 = (**(code **)(*param_2 + 0x70))(param_2);
      FUN_140fb3560(uVar1, param_2, p3, uVar2, p4);
  }
  ```
  So `param_2` is a callable object with vtable methods at `+0x60`
  and `+0x70`, and the adapter resolves them before forwarding to
  the writer.
- The DATA xref of `FUN_140fadbc0` is at `0x147fc3708` — inside a
  function-pointer table starting around `0x147fc36c8`. The table
  has 8-byte rows of mixed function pointers (some repeated,
  including helpers like `FUN_14029e6a0` appearing twice). Looks
  like a callback table (e.g., handler entries indexed by event id).
- Tried `FindConstant 0x147fc36c8` to find what references the
  table base — **0 hits**. The table is referenced internally and
  the address isn't materialized as a constant elsewhere; it's
  reached as the vtable of an object whose pointer is loaded from
  somewhere else.
- Side investigation of `&DAT_147fc88d8` (the arg in `FUN_14103b1a0`'s
  "Lost connection to REP" branch). The bytes there are
  `71 75 69 74 00` — the ASCII string **`"quit"`**. So the
  vtable[+0x120] call at the OnConnectionFail "exiting" path is
  literally `console.execute("quit", 0, 0)` — UI-level full app
  shutdown via the console, **not** the carrier-destroy event.

**Found / closed loops:**

1. The OnConnectionFail "Lost connection to REP. Exiting..." branch
   triggers a **console quit** (different mechanism from the carrier
   destroy-flush flag at `+0xfd`). They're related conceptually
   (both happen on terminal failure) but distinct:
   - Carrier `+0xfd = 1` → tick loop force-flushes pending data
     (early phase of shutdown).
   - Console `quit` → process exits (final phase, UI-side).

2. The destroy-flag writer (`FUN_140fb3560`) is reached via:
   ```
   ??? --(vtable[+0xN])--> FUN_140fadbc0 --(direct)--> FUN_140fb3560
   ```
   The `???` is the originating dispatcher — it has the vtable
   pointer in some object. Not statically discoverable as a constant.

**Why static path is exhausted:** the destroy event is dispatched via
indirect vtable calls on objects whose vtable pointers are stored on
the heap and assigned at runtime. From a static analysis standpoint,
"who calls FUN_140fb3560" devolves into "who builds the dispatcher
object" — and the constructor flow for these AzCore-style event
broadcasters is itself table-driven and hard to follow without
runtime context.

**Bottom line:** A3 was already solved (writer + condition). Trying
to identify the *origin* of the dispatch turned up two interesting
distinctions:

- "Lost connection to REP" → quit-via-console (FUN_14103b1a0).
- Carrier destroy flag → indirect vtable dispatch (FUN_140fadbc0).
- These are separate paths; the project's ~30s session death is the
  carrier path, not the console-quit path.

For the maintainer, the practical implication is unchanged: send
the required messages (SelfIdent + others) before the timeout, and
the destroy chain never fires.

**Next** (queue):
- A4.2 follow-up: register-based-store scan for `wrapper[+0x252]`
  (state-13 gate, the immediate-store scan missed it).
- A2.10 still needs runtime — queued for maintainer.

**Blockers:** None for the loop.

---

### 2026-05-07 — wake 16: A4.2 follow-up — broad scan; static origin still hidden

**Did:**
- Wrote `tools/ghidra_scripts/FindOffsetReferences.py` — broader than
  `FindOffsetWrites`: catches ANY operand with the target displacement
  (read or write, any opcode, any value), with optional address-range
  filter.
- Ran with offset `0x252` filtered to wrapper class neighborhood
  (`145a` prefix) — only one hit, the gate reader `FUN_145a923c0`
  (which we already had). **No wrapper-class writer of `+0x252`
  exists statically.**
- Ran without filter — 45 hits across 33 functions, all in unrelated
  classes (UI code, audio, render math, etc.). The byte field
  `+0x252` is too generic.
- Tried gc-relative offset `0x382` (= `0x130 + 0x252`, since wrapper
  is embedded at `gc+0x130`) — 25 hits. Filtered to the Javelin/
  GameConnection address range (`0x146x`): 2 candidates writing 1.
- Decompiled both:
  - `FUN_146cd5780`: CGF (CryGame Format) model loader — references
    "Node chunk", "PhysicsProxy", "$collision", etc. **Unrelated.**
  - `FUN_146d0bbe0`: a constructor that does `operator_new(0x1050)`
    and pre-initializes a `+0x382` byte to 1 along with other
    fields. The 0x1050-byte object is *not* a GameConnection
    (GameConnection is much larger). **Unrelated.**

**Found (A4.2 follow-up — exhausted):**

The state-13 gate flag (`wrapper[+0x252]` = `gc[+0x382]`) is **not
written by any immediate-store instruction in the binary** — neither
through the wrapper pointer nor through gc-relative arithmetic. The
writer must use one of:
- **memcpy / struct copy** from a source object (e.g. zeroing
  during construction, or copying spawn-data into wrapper fields).
- **Register-based store with the value computed earlier** (e.g.
  `MOV BPL, AL; MOV [RBP+0x252], BPL` — the AL came from somewhere
  upstream).
- A different intermediate pointer (not wrapper or gc directly,
  e.g. `MOV [RAX+SOMETHING], 1` where RAX was loaded from some
  field at a known offset).

For comparison, the **state-12 gate writer** (`wrapper[+0xbc8]`)
was findable because it had:
- A direct `MOV [reg+0xbc8], 1` immediate store (FindOffsetWrites
  caught it).
- A 9-line wrapper-class setter that exists *because* the trigger
  is set explicitly by another message handler.

The state-13 gate's absence of a similar setter pattern suggests
its semantics differ — the flag may flip as a side-effect of some
larger spawn-state copy, rather than being toggled by a discrete
event handler.

**Why this is fine for the project:** the maintainer's MVP target
is reaching state 14 (`InGame`). Knowing *which* server message or
internal trigger flips `+0x252` is helpful but not blocking — the
state advances 13→14 once spawn data is delivered, regardless of
whether there's a discrete "spawn complete" message or whether it
falls out of `LevelInfoChangedMsg` processing.

**Conclusion:** A4.2 marked DONE-WITH-CAVEAT. The static path is
genuinely exhausted. Like A2.10, A3.1, A4.3, the path forward is
runtime — a Frida hook on `FUN_145a923c0` (the gate reader) at
state-13 transition time would log who wrote the byte.

**Static-RE summary at end of day 1:**

| Question | Answer | How |
|---|---|---|
| What gates state 10→11? | `wrapper[+0xa0] == 2` | static, A1 |
| What writes `wrapper[+0xa0] = 2`? | `FUN_145a87010` (`onConnectionSuccess`) | static, A2.5 (single hit in 32M instructions) |
| What invokes `onConnectionSuccess`? | `FUN_146454c00` = PlayerManagerSelfIdent handler | static, A2.6 |
| What gates state 12→13? | `wrapper[+0xbc8] != 0`; also forced state 13 by LevelInfoChanged | static, A1 + A4 |
| What writes `wrapper[+0xbc8] = 1`? | `FUN_145a9fa00` called from `FUN_14645c660` | static, A4.1 (single hit in 32M instructions) |
| What is the message at `FUN_14645c660`? | TBD — same dispatch table as SelfIdent, name unrecoverable from static | runtime needed, A4.3 |
| What gates state 13→14? | `wrapper[+0x252] != 0` | static, A1 |
| What writes `wrapper[+0x252] = 1`? | TBD — no immediate store exists in binary | runtime needed, A4.2 |
| What's the destroy event id? | AZ::Crc32 `0xFE476177` | partial, A3 |
| What is the source string for `0xFE476177`? | TBD — release-build strip | runtime needed, A3.1 |
| Where is PlayerManagerRejected handler? | TBD — no GameMessagePort log signature | runtime needed, A2.10 |

**Five tasks (A4.3, A4.2, A3.1, A2.10, A2.9c) all converge on Frida.**
A single targeted runtime capture session would unblock them all.

**Next** (queue):
- B1 — **DON'T START** until either runtime data lands OR the
  maintainer explicitly directs the loop to attempt a server-side
  experiment with the partial knowledge we have. Per
  `project_autonomous_session_plan.md`, server code changes need a
  confident hypothesis first. Without wire-format byte layouts, any
  server-side attempt is guessing.
- A2.7-followup (sibling lifecycle handlers in observer table that
  `FUN_145a87010` walks) — this might surface other useful handlers,
  but the practical payoff is small now that the synthesis is
  written.

**Blockers:** Loop has hit static-RE exhaustion on the player-spawn
path. Continuing iterations risk diminishing returns. Suggest
either: (a) the loop pauses now and the maintainer triggers a
runtime capture session, (b) the loop pivots to other parts of the
codebase the project might benefit from (e.g. characterizing the
`PlayerManagerTrait` messages, or the `Hub*` message family).

---

### 2026-05-07 — wake 17: A4.3 vtable-correlation attempt — also a dead end

**Did:**
- One more clever-angle attempt to identify `FUN_14645c660`'s message
  name. Searched for log-form (non-mangled) string literals matching
  the strong candidates from A4.3. Hits:

| Candidate | Log-form string? | Mangled-only? |
|---|---|---|
| ActorInitializedMessage | YES — `'ActorInitializedMessage'` at `0x14857f768` | also has mangled |
| ActorStatusNotificationMessage | YES — at `0x14857e840` | also has mangled |
| OnHubConnectionChanged | no | mangled only |
| OnPlayerActorStatusChanged | no | mangled only |
| OnPublishedCharacterMetadata | no | mangled only |
| ReceiveCharacterMetadata | no | mangled only |

- For each log-form string, the DATA xref was a 2-instruction
  trampoline (`LEA RAX, [string]; RET`) — these are AZ::TypeId
  name-getters. `0x146aef990` returns "ActorInitializedMessage";
  `0x146aef9f0` returns "ActorStatusNotificationMessage".
- Found the vtable that contains these getters (e.g. the
  `ActorInitializedMessage` class vtable around
  `0x148583f10-0x148583fb0`) — confirmed via the embedded UUID
  text and adjacent name-getter slot.
- Searched both vtables for `FUN_14645c660`'s RVA. **Not present.**

**Found (A4.3 — confirmed exhausted):**

`FUN_14645c660` does not appear in any AZ-RTTI class vtable I can
find. Its only reference in the entire binary is the dispatch table
entry at `0x14abcc45c`. So the message name cannot be confirmed
through vtable correlation either — there is no static linkage
between the handler function and the message-class metadata.

The dispatch table is built at compile time from
`InstallRegistrationHook<T>` template instantiations. Each
instantiation produces (a) a lambda handler (which becomes
`FUN_14645c660` and friends) and (b) a row in the dispatch table.
The C++ template name `T` is preserved only in mangled RTTI form
in the binary, not as a runtime-accessible string from inside the
handler. So a release-build static analysis simply cannot recover
the `T → handler` mapping without runtime data.

**This is the final word on A4.3 from a static angle.** The Frida
runtime hook (queued for the maintainer) is the only path forward.

**This is also a useful negative result for the project's docs:**
the maintainer can stop trying to statically reverse handler-to-name
mappings for this dispatch system. The general pattern for any
`ClientMessages` / `*Trait` message handler is the same: handler
function + dispatch-table entry, with no other backlink to the
type name in release builds.

**Decision: recommend pausing the loop.**

After 17 wakes (2 hours of autonomous time), the player-spawn
investigation has reached genuine exhaustion. Five separate threads
(A2.10, A3.1, A4.2, A4.3, A2.9c) all converge on the same single
runtime-hook session. Continuing more static iterations is
diminishing returns.

Productive options if the maintainer wants the loop to keep running:

1. **Pivot to other unrelated subsystems.** Characterize
   `PlayerManagerTrait` (28 messages) or `Hub*` families to expand
   the project's chunk/message inventory. Useful for long-term
   protocol completeness, less urgent for MVP.
2. **Documentation pass.** Write a `tools/ghidra_scripts/README.md`
   inventorying the 9 generic Ghidra scripts created today
   (`HeadlessDecompile`, `FindXrefs`, `FindStringXrefs`, etc.)
   with usage examples. Pure docs, zero new RE.
3. **Stop and wait** for the maintainer to do a runtime capture
   session, then resume the loop with the resulting data.

I'll schedule one more wake at the standard interval but mark this
as the explicit decision point. If the maintainer doesn't redirect
before then, the next wake will pick option (1) or (2) — likely
(2), since the docs pass is high-value and risk-free.

**Blockers:** None for the loop, but the loop has hit its
intended useful range on the player-spawn protocol path.

---

### 2026-05-07 — wake 18: tooling documentation pass

**Did:**
- Wrote `tools/ghidra_scripts/README.md` — a comprehensive index of
  the analysis tooling. Documents the `tools/ghidra` CLI wrapper
  plus 11 Jython scripts (9 new this session + 2 pre-existing
  `JavelinHunt`, `FindChunkRegistrations`).

**Why:** Per the recommendation in wake 17, the player-spawn static
investigation has reached genuine exhaustion. With five threads
queued for the maintainer's runtime hook session, the loop is in
its diminishing-returns phase. A documentation pass on the tooling
is high-value, risk-free, and makes the scripts re-usable for
future investigations of other parts of the binary.

**README content:**
- Setup notes (script-path registration, Jython 2.7 quirks).
- CLI wrapper subcommand reference.
- Script index table.
- Per-script sections: purpose, args, example usage, what it was
  used for in this investigation.
- Output naming conventions.
- A how-to-add-a-new-script template.

**Next** (queue is light):
- One more useful angle if the loop continues:
  `'GameConnectionWrapper: spawn point found'` log literal at
  `0x1484fea88` — finding its callers could reveal how the
  state-12→13 transition is observed (and indirectly hint at the
  `wrapper[+0x252]` writer mechanism for A4.2).
- Otherwise the loop is at a natural pause point; recommend the
  maintainer either trigger a runtime-hook session or redirect
  the loop to other subsystems.

**Blockers:** None. The loop has now produced everything statically
recoverable on the V3-to-spawn protocol path; further iterations
are choosing between low-yield static angles and a runtime
hand-off.

---

### 2026-05-07 — wake 19: final static-path checks; loop pausing

**Did:**
- Searched for the `"spawn point found"` log literal — single
  reference, from `FUN_14644a070` (the state machine itself, the
  state-12→13 transition log). Not a writer.
- Searched for the `"player spawn succeeds, in game"` log literal —
  single reference, also from `FUN_14644a070` (state-13→14 log).
  Also not a writer.
- Confirmed: log-literal-trace approach can't recover the
  `wrapper[+0x252]` writer because there isn't one with a
  semantically-distinct log. The state machine *observes* the byte
  via `FUN_145a923c0`; whoever flips it does so silently or as a
  side-effect of larger state copy.

**Decision:** I'm pausing the autonomous loop here. After 19 wakes
(2.5 hours autonomous) the player-spawn investigation has produced
everything recoverable from static analysis. The remaining open
items (A2.10, A3.1, A4.2, A4.3) all need runtime data.

**State of the project at pause time:**

- Branch `claude/vacation-2026-05-06` has 28 commits.
- `analysis/state_machine_summary.md` is the consolidated
  maintainer-facing doc.
- `tools/ghidra_scripts/README.md` documents the 11 analysis
  scripts.
- 5 tasks queued for the maintainer (4 of them resolvable by a
  single Frida hook session).
- The MVP fix scope is bounded: server needs to send
  `PlayerManagerSelfIdentificationMsg`, `LevelInfoChangedMsg`, and
  whatever message `FUN_14645c660` handles. Wire formats need
  runtime capture.

**To resume the loop:** invoke `/loop` again. I'll re-read this
worklog and either continue from the queued tasks (mostly
runtime-blocked) or pivot to a new direction the maintainer points
at — e.g. characterize `PlayerManagerTrait` server-side messages,
walk the `Hub*` lifecycle messages, or document a different
subsystem.

**Blockers:** Static path exhausted on the player-spawn protocol.

---

### 2026-05-07 — scope expansion: from player-spawn to broad RE

The maintainer expanded the loop's mandate from "player-spawn
protocol path" to broad RE of the binary across roughly 6 days of
autonomous time. The player-spawn investigation is complete and
documented; the loop now pivots to adjacent subsystems.

**Updated task queue (long-horizon, exploratory):**

- [ ] **C1.** Server-side code audit. Read `server/rep_responder.py`,
      `server/auth_mock.py`, `server/javelin/*`. Map existing
      implementation vs. static findings. Surface concrete
      implementation gaps.
- [ ] **C2.** `PlayerManagerTrait` characterization (28 messages,
      server-side). Enumerate handlers via FindXrefs of each
      mangled-name string; decompile a representative sample to
      establish field-shape patterns.
- [ ] **C3.** Remaining `ClientMessagesTrait` handlers
      (DebugCommandResponse, RemoteConfigChanged, plus the
      by-elimination identification of FUN_14645c660).
- [ ] **C4.** `Hub*` family — ActorInitialized,
      ActorStatusNotification, HubLifecyclePeeringTrait,
      HubEndpointSharingTrait, HubLifecycleStateListenerTrait, etc.
      ~30+ messages.
- [ ] **C5.** Replica chunk inventory expansion. Extend
      `FindChunkRegistrations.py` and `analysis/javelin_chunks.txt`
      to include all chunk-flavored traits the existing scan missed.
- [ ] **C6.** Cross-trait analysis: in-game message ordering. Pull
      from logs / strings showing message sequence in observed
      sessions; back-fill `docs/connection-flow.md`.
- [ ] **C7.** Final consolidation: comprehensive protocol map
      document tying everything together, with residual runtime-only
      gaps explicitly listed.

The earlier player-spawn-path tasks (A1–A5, plus B1) are either
complete, runtime-blocked, or out-of-scope without runtime data —
left in the queue above as historical record.

**Discipline carried forward:** ~30 min per iteration, commit per
wake, push to origin, no personal framing in committed artifacts,
neutral commit-message language. The repo is public.

**Resuming the loop now.** First iteration: C1 (server-side audit).

---

### 2026-05-07 — wake 20: C1 audit + MAJOR find — runtime data already exists in info/

**Did:**
- Inventoried `server/` (~6.3k lines Python). Read `rep_responder.py`,
  `v3_response.py`, replay system pieces.
- Surveyed `info/` directory.

**Found — server architecture:**

The server uses a **replay-and-substitute** strategy, not
generate-from-scratch:

1. V3 RegistrationRequest received → V3 RegistrationResponse sent
   (working — the response template is at `v3_response.py` based on
   bytes captured from a real successful login at
   `info/nw-login-safe-20260502-153840/messages-redacted.txt`).
2. After V3, `_start_replay()` queues the captured post-V3 messages
   (seq 0x2..0x24) for paced replay.
3. `SubstitutionContext` patches redacted spans (player UUIDs,
   session token, character name) with the current session's
   identity before each replay message ships.
4. After the queue drains, `PingMsg` (type 0x15d) heartbeats keep
   the connection alive past the captured-session length.

So the server **is** sending the captured `PlayerManagerSelfIdentificationMsg`
already — but the client doesn't accept it. Today's static findings
explain *why*: the substituted fields don't match what the wrapper
setters expect, OR the seq numbering breaks the carrier reliable
ordering, OR the wire-format byte layout in the captured replay
diverges from what this build of the binary parses.

**Found — INFO/ HAS RUNTIME DATA WE THOUGHT WE NEEDED FRIDA FOR:**

`info/typeregistry.json` is a **runtime-extracted type registry**
(80,207 lines, 3,487 named types). Each entry has:
- The type's UUID
- The type's name (e.g. `ConfigOverridesDebugTrait::State`)
- Heap-relative vtable addresses
- **First 8 bytes of `Marshal` and `Unmarshal` opcodes** for each type

The 3,487 types in the registry correlates almost exactly with the
3,482 `InstallRegistrationHook<T>` mangled-name strings I counted
earlier — this registry IS the runtime-equivalent dump of the
dispatch system.

**The opcode prefixes are the key.** They're 8 unique bytes from
each Marshal/Unmarshal function's prologue. Grepping the binary's
code section for those byte sequences will reveal the actual
function addresses. That gives us a **type-name → handler-address
mapping** without needing a new Frida session.

This unblocks several of the 5 "runtime-needed" tasks statically:
- A4.3 (FUN_14645c660 message name)
- A2.10 (PlayerManagerRejected handler)
- Even maybe A3.1 (the destroy-event AZ::Crc32 might map to a
  registry UUID).

Also `info/community_22_phase_in_game_dump.txt` (85 lines) and
`info/wireshark_carrier_handshake_redacted_session1.txt` exist —
worth examining for in-world traffic snapshots beyond the
20260502-153840 capture.

**This is a sharp pivot in the loop's value.** Pre-typeregistry
discovery, the loop was queueing tasks for the maintainer's runtime
hook session. Post-discovery, we may be able to resolve most of
them statically by correlating with the registry. Next iterations
will:

- C1.1: Build a script that maps `typeregistry.json` Marshal/Unmarshal
  opcode prefixes to actual function addresses in the binary by
  byte-pattern search. Output: a `type_name → (marshal_addr,
  unmarshal_addr)` table.
- C1.2: With that table, look up FUN_14645c660 (or its containing
  vtable) → resolve A4.3.
- C1.3: Also resolve A2.10 by looking up PlayerManagerRejectedMsg
  in the registry.

**C1 conclusion:** server-side audit produced two outputs of unequal
weight:
- Architecture documentation (the replay-substitute strategy) —
  modest value, mostly already implicit in the README/CONTRIBUTING.
- Discovery of `typeregistry.json` as a static-analysis-unblocking
  asset — **major** value, completely changes the rest of the
  multi-day plan.

**Next** (queue updated):
- C1.1, C1.2, C1.3 as above.
- C2 (PlayerManagerTrait characterization) — also benefits from the
  registry now.

**Blockers:** None.

---

### 2026-05-07 — wake 21: typeregistry mapping fails BUT community dump is a goldmine

**Did:**
- Built `tools/ghidra_scripts/UuidAtAddress.py` — read 16 bytes at
  an address and look up against a UUID-to-name map derived from
  `info/typeregistry.json` (312 named UUIDs after deduplication).
- Tested against the dispatch table metadata addresses:
  `0x149cc1c44`, `0x149cc1b64` (both for known SelfIdent /
  adjacent), and `0x140977d3f0` (the FUN_14645c660 metadata).
- Examined `info/community_22_phase_in_game_dump.txt`.

**Found (typeregistry mapping — partial dead end):**

The dispatch-table metadata RVAs are NOT pointers to AZ::TypeId
UUIDs. Bytes at `0x149cc1c44` are `11 15 09 00 15 54 17 00 15 34
16 00 15 01 12 00` — packed pairs of small uint16 values that
look like a serialization schema (field tag/offset table), not a
UUID. The `0x140977d3f0` value isn't even a valid memory address
in the binary's mapped image. So my "dispatch metadata = UUID
pointer" hypothesis was wrong.

The typeregistry's opcode prefixes (Marshal/Unmarshal first 8
bytes) are also not unique enough to byte-pattern-match — they're
mostly generic MSVC function prologues like
`48 89 5C 24 08` (`MOV [RSP+8], RBX`).

So the runtime registry doesn't directly give us the
type→handler mapping. **312 of 3,487 named types have full
handler data, and PlayerManagerSelfIdentification, Rejected,
LevelInfoChanged, ConnectionSuccess are NOT in the named-with-
handler subset** — the registry seems to only contain types
active at the runtime moment of capture.

**Found (community dump — extraordinary):**

`info/community_22_phase_in_game_dump.txt` (85 lines) is a
reverse-engineered **22-phase post-V3 message sequence** from
another team that got further than this project. Direct quotes
from the dump:

- DTLS framing: `[prefix:u16BE][dgramSeq:u16BE][messages...]`,
  `0x8001` uncompressed / `0x8101` LZ4-body, dgramSeq starts at 2.
- NW protocol wrapper inside ch0/ch1 carrier payloads:
  `[PackedSize_LE(innerLen)][0x00][0x01][type:u8][data...]`.
- Message flag bits: `MF_RELIABLE 0x01`, `MF_CHUNKS 0x04`,
  `MF_SEQUENTIAL_ID 0x08`, `MF_SEQUENTIAL_REL_ID 0x10`,
  `MF_DATA_CHANNEL 0x20`, `MF_CONNECTING 0x80`.

The 22 phases (from their reproduction):

| Phase | +Delay | Message | Size |
|---|---|---|---|
| 1 | 0ms | VERSION (0x03) | 89B |
| 2 | 50ms | HEARTBEAT 0x9d | 13B |
| 3 | 80ms | INIT 0x8a + 0xbe | 154B |
| 4 | 140ms | WORLD DATA 0x9c chunked (12 segments) | 12.7KB |
| 5 | 200ms | INIT 0x91(0x19) | 21B |
| 6 | 220ms | SESSION A4 large | 75B / 195B retail |
| 7 | 250ms | HEARTBEAT 0x8f | 13B |
| 8 | 280ms | A6 + 0x88 x2 | ~120B |
| 9 | 300ms | 0x88 + small A4 | ~60B |
| **9b** | **310ms** | **SelfIdentification 0x91(0x17)** | **4B** |
| 10 | 320ms | 0x88 x20 in one datagram | ~840B |
| 11 | 400ms | SESSION AA (0xaa) | 29B |
| 11a | 420ms | A4 + WORLD SPAWN A3 + HB 0x8f | ~130B |
| 11b | 460ms | CH1 burst, 47 units | 285KB |
| 12 | 1500ms | SESSION AE (trail=0x02) | 22B |
| 13 | 3000ms | SESSION AE (trail=0x00) | 22B |
| 14 | 450ms | ENTITY DEFS 0x95 + 0x9d-large + 0xa0 | 2.5KB |
| 15 | 800ms | GAME DATA 0xb3 + VIVOX URL 0xa7 | 3KB |
| 16 | 1200ms | SPAWN 0x96 + 0x97 | 160B |
| 17 | 1400ms | continuous 0x08 entity stream | varies |
| 18 | 2000ms | Player data 0xa0 burst #1 (210 seg) | 233KB |
| 19 | 800ms | Player data 0xa0 burst #2 (154 seg) | 171KB |
| 20 | 7000ms | Entity 0xac chunked | 2.6KB |
| 21 | continuous | Heartbeats 0x8f/0x9d alternating @ 500ms | 13B |
| 22 | 10s | continuous ch0 loop | varies |

**Key insights:**

1. **The SelfIdent message we've been hunting is type
   `0x91(0x17)`, just 4 bytes, sent ~310ms after V3 response.**
   That's wire-format-precise — bypasses everything we've been
   trying to recover statically.

2. The community team hit a *different* stall — state 13
   (WaitingForPlayerSpawn) — because they were sending the full
   22-phase sequence and got further. Our stall at state 10
   (WaitingForREPConnection) means we're failing to even send
   Phase 9b correctly.

3. Their stall resolution: a DLL patch forcing `isMasterPlayer=1`
   in `sub_145A85940 case 0` plus a predicate-vtable patch on the
   bundle handler at `0x1717fc0`. **`sub_145A85940` is in our
   binary's wrapper-class neighborhood** (0x145a85940 — between
   the wrapper methods we've been characterizing).

4. The dump documents wire-format gotchas the project should
   know:
   - "NO post-connect extra byte" in carrier messages.
   - `flags=0x88` does NOT set `MF_SEQUENTIAL_REL_ID`, so relSeq
     must be written.
   - Real-server SM_CONNECT_ACK shape (`0x21/relSeq=0`)
     instant-disconnects on the test path; the test-39 form
     `0xa0/relSeq=0xffff` is what works.
   - `0xa3 WorldSpawn` map path must be exactly
     `"coatlicue/NewWorld_VitaeEterna"`.
   - `CH1 unit[0]` (~47KB init burst) is mandatory.

**This dump dramatically updates the project picture.** The
five-questions-for-Frida list mostly evaporates:
- A2.10 (PlayerManagerRejected handler) — still TBD but lower
  priority since we now know the success path's wire format.
- A3.1 (CRC for destroy) — still TBD.
- A4.3 (FUN_14645c660 message name) — still TBD.
- A4.2 (wrapper[+0x252] writer) — likely a side-effect of one of
  the post-Phase-16 spawn messages.
- Wire formats — **mostly answered by the dump**.

**This data has been in the repo the whole time.** The project's
own `info/` directory contained the answer, and the static-RE work
this morning was solving a problem the community had already
solved at a higher level. That's a humbling but very useful
realization.

**Immediate next priority** (queue updates):

- C1.4 (NEW): write up the community dump's findings as a proper
  protocol document (`docs/post-v3-sequence.md` or similar)
  cross-linking to `state_machine_summary.md` and to the static
  function addresses we've identified.
- C1.5 (NEW): cross-reference `sub_145A85940` (their isMasterPlayer
  blocker) against our wrapper-class characterization. It's in
  the same address neighborhood as `FUN_145a87010` etc.
- C2 (PlayerManagerTrait) deferred — much lower priority now that
  the post-V3 sequence is documented from another angle.

**Blockers:** None for the loop.

---

### 2026-05-07 — wake 22: docs/post-v3-sequence.md written + sub_145A85940 located

**Did:**
- Wrote `docs/post-v3-sequence.md`. Synthesizes the community
  22-phase dump with our state-machine map and static handler
  identifications. Sections cover: wire format recap, the 22-phase
  table with delays/sizes/channels, cross-link to GameConnection
  state machine, C→S direction, wire-format gotchas, static-RE
  handler addresses, community-team stall observations,
  implementation file references, and what's still missing.

- Probed `sub_145A85940` (the community team's `isMasterPlayer=0`
  blocker) against our binary. Result: `0x145a85940` is **not** a
  function entry in our binary's analysis — it's inside
  `FUN_145a85760` at offset `+0x1e0`. Documented in the new
  protocol doc.

**Found (C1.4 outcome):**

The new doc is positioned in `docs/` (not `analysis/`) because it's
a maintainer-facing protocol reference, not a session note. It
explicitly cross-links to:
- `analysis/state_machine_summary.md` for the state-machine and
  static-RE findings
- `info/community_22_phase_in_game_dump.txt` for the canonical
  community RE
- `server/javelin/*` files for the existing implementation

This matters because previously the community dump was buried in
`info/` (~85 lines, no doc index entry, easy to miss). Now anyone
landing on the project can read `docs/post-v3-sequence.md` and
get the protocol shape immediately.

**Concrete things now visible from the doc that weren't before:**

1. **The replay store covers seq 0x2..0x24, which is Phase 1
   through partway into Phase 11 of the 22.** Phases 12–22 are
   not delivered by the existing server. That's a clear scope
   for "new captures needed" — extending coverage past 0x24
   matters more than nailing Phase 9b's wire format (since
   replay already covers Phase 9b).

2. **The community team's stall (state 13) is past ours (state
   10).** Their bypass (DLL patch forcing isMasterPlayer=1)
   suggests the project will hit the same stall once it gets
   past Phase 9b. Worth flagging as a future blocker.

3. **The CH1 init burst at Phase 11b (~47 units, ~285KB) is
   mandatory** per the community team. NW_HYBRID_INIT bisection
   shows 67 units → loading circle, 68 → black screen (game
   world). This is the most likely candidate for the next
   significant server-side work after the replay extends
   past seq 0x24.

**Sub_145A85940 deeper probe:**

Tried decompiling the address directly — Ghidra returned
`FUN_145a85760` (the containing function), confirming
`sub_145A85940` is at `+0x1e0` inside that function. This
function is likely the wrapper's state-handling tick or
similar, located in the wrapper-class address neighborhood
(`0x145a8xxxx-0x145a9xxxx`). Not decompiled fully this
iteration — flagged in the doc for future investigation when
the project reaches the state-13 stall.

**Next** (queue):
- C5: replica chunk inventory expansion. Now that the protocol
  doc is in place, expanding `analysis/javelin_chunks.txt` and
  `FindChunkRegistrations.py` to cover the broader trait/component
  facet space is a clean next step.
- C6: cross-trait analysis — back-fill `docs/connection-flow.md`
  with the Phase 9b+ details now that they're documented.
- C2 (PlayerManagerTrait) — keep deferred unless a specific
  question surfaces.

**Blockers:** None.

---

### 2026-05-07 — wake 23: full message inventory + A4.3 refinement

**Did:**
- Parsed the cached `FindStringXrefs InstallRegistrationHook` output
  (`/tmp/all_install_hooks.txt`, 541KB from earlier wake) with a
  Python regex into `(namespace, type)` pairs. Result: **2,025
  unique typed messages across 174 namespaces.**
- Cross-referenced with the `info/typeregistry.json` named types.
- Wrote `analysis/message_inventory.md` (2,632 lines) — a
  comprehensive catalog organized by topical bucket then by
  namespace, with typeregistry coverage marked.
- Wrote `tools/build_message_inventory.py` so the doc is
  regeneratable when binaries / typeregistry refresh.

**Found (C5 outcome):**

The project's prior chunk inventory was two orders of magnitude
narrower than the actual surface:

| Inventory | Count |
|---|---|
| `analysis/javelin_chunks.txt` (prior) | 2 components |
| `analysis/chunk_names.txt` (prior) | 17 chunk names |
| `analysis/javelin_classes.txt` (prior) | 730 Javelin::* class names |
| `analysis/message_inventory.md` (new) | **2,025 messages, 174 namespaces** |

Top namespaces by message count:
- `Javelin` (519, top-level catch-all)
- `Javelin::ClientMessages` (487, the per-component facet messages)
- `Amazon::Hub` (118, 78 in typeregistry)
- `MB` (107, replicated state)
- `Aoi::PhysicsTrait` (76)
- `Aoi::PlayerManagerTrait` (28, server-side player ops)
- `Amazon::IPC` (28, 27 in typeregistry)
- `ActorMover` (20, 19 in typeregistry)

**typeregistry coverage pattern:** the 312 named types with full
handler data in `info/typeregistry.json` cover `Amazon::Hub`,
`Amazon::IPC`, `ActorMover` heavily but **zero** of `Javelin::*`,
`Aoi::*`, `MB`, `ChatBroker`. So those two layers are different
serialization systems — the registry is the AZ-RTTI / persistence
layer, while `Javelin::*` is the RPC handler layer. They don't
share the type metadata.

**A4.3 refinement** (the unidentified state-12 trigger handled by
`FUN_14645c660`):

The full inventory shows `Javelin::ClientMessagesTrait` has **6
messages**, not the 5 I previously catalogued:

1. `DebugCommandResponseMsg`
2. `LevelInfoChangedMsg`
3. `PlayerManagerRejectedMsg`
4. `PlayerManagerSelfIdentificationMsg`
5. `RemoteConfigChangedMsg`
6. **`State`** ← previously missed

The `State` member is a trait-level state-machine message. By
elimination (SelfIdent and LevelInfoChanged are mapped, Rejected is
the failure path, RemoteConfigChanged and DebugCommandResponse
don't fit the "advance state to spawn-point-ready" semantic), the
likely candidate for `FUN_14645c660` is **`State`** — a generic
state-update message. That fits the dispatcher pattern of using
*the same handler bridge* (`FUN_14645c660`) for whatever state
update arrives.

Not 100% confirmed without runtime data, but a much sharper
hypothesis than the long candidate list from wake 13.

**Other notable findings from the inventory pass:**

- `Aoi::PlayerManagerTrait` (28 messages) is the server-side
  counterpart to `ClientMessagesTrait`. Notable members:
  `OnHubConnectionChangedMsg`, `OnPlayerActorStatusChangedMsg`,
  `OnFirstTerritoryForPlayerMsg`, `ProcessSpawnQueueMsg`,
  `RequestRejectClientConnectionMsg` (the *server*'s reject
  request that produces the client's `PlayerManagerRejectedMsg`).
- `MB` namespace is the **MarshalByValue** replicated state system
  — 107 message types, all 0 in typeregistry. This is the GridMate
  ReplicaChunk dimension, distinct from the trait-RPC dimension.
- Several smaller traits worth noting for future work:
  `Javelin::CharacterServiceProxyTrait` (17 msgs),
  `OrchestrationTrait` (12), `ChatBroker` (18).

**Next** (queue):
- C6: cross-trait analysis — back-fill `docs/connection-flow.md`
  with the post-V3 protocol now that `docs/post-v3-sequence.md`
  and `analysis/message_inventory.md` provide the data.
- C7: final consolidation — comprehensive protocol map doc.

**Blockers:** None.

---

### 2026-05-07 — wake 24: SM_CONNECT_ACK shape investigation + replay-vs-dump type mismatch

**Did:**
- Pivoted from C6 to a directly-actionable check: does the project's
  `send_connect_ack` use the form the community dump documented as
  working, or the form documented as instant-disconnecting?
- Read `server/rep_responder.py:send_connect_ack` (line 799+).
- Cross-referenced `docs/progress.md` for prior testing notes.
- Listed all messages in the captured replay
  (`info/nw-login-safe-20260502-153840/messages-redacted.txt`)
  and compared to the community dump's 22-phase type IDs.

**Found 1 — both ack-forms already implemented as a CLI option:**

`send_connect_ack` already has both forms behind `--ack-form
{mn,alt}`:

- `mn` (default, "Mixed Nuts" form): `flags=0x21`, seq=0,
  rel_seq=0. Annotated as **"real-server form, byte-identical to
  Mixed Nuts' Wireshark dissector capture"**.
- `alt` (community dump form): `flags=0xa0`, seq=current,
  rel_seq=0xFFFF. Annotated with the community team's note:
  **"the 0x21/0 form instant-disconnects on their path"**.

The two reversers disagree on which form the real server uses. Per
`docs/progress.md` 2026-05-04: the maintainer chose `mn` because
that form **made the client send the V3 request in the first place**
(real progress signal), and noted "falling back to `0xa0/0xffff` is
the obvious next experiment if the next attempt regresses."

So both possibilities are a CLI flag away. This is *not* the active
blocker — the project has already moved past the ACK-shape question
in their testing.

**Found 2 — captured-replay type IDs don't match community dump's
phase types:**

The capture at
`info/nw-login-safe-20260502-153840/messages-redacted.txt` covers
seq 0x0..0x24 and beyond. Listing the types:

```
seq=0x0 type=0x13   W
seq=0x1 type=0x3    R   <- Phase 1 VERSION (matches 0x03)
seq=0x2 type=0x15d  R   <- HEARTBEAT (community 0x9d, 2-byte encoded)
seq=0x4 type=0x40a  R
seq=0x5 type=0x1be  R
seq=0x6 type=0x65c  R
seq=0x7 type=0x651  R
seq=0x8 type=0xa4   R   <- Phase 8 0xa4 (community matches!)
seq=0x9 type=0xca4  R
seq=0xa type=0x14f  R   <- different HEARTBEAT
seq=0xb type=0x18a6 R
seq=0xc..0x18 type=0x1b88 R  <- chunked, 14× same type
seq=0x25 type=0x8 R     <- Phase 17 entity stream (matches!)
```

The community dump's Phase 9b SelfIdent claim is `type 0x91(0x17)`,
which under the project's typed-stream encoding `[(type_id & 0x3F)
| 0x80, (type_id >> 6) & 0xFF]` would either decode to type 0x5d1
(if 0x17 is the high subtype byte) or 0x91 itself (if single-byte).
**Neither 0x5d1 nor 0x91 appears in the captured replay's seq
0x2..0x24.**

So either:

- The community dump and the captured-replay use different type-ID
  encoding conventions, and the SelfIdent message *is* in the
  capture under a different ID label.
- OR the captured replay doesn't actually contain the
  state-10→11-triggering SelfIdent message.

**This is a potentially-significant gap.** If the replay doesn't
contain the message that's supposed to advance state, then the
server's current replay-substitute strategy can't possibly drive
the state machine forward — regardless of how good the ack shape
or substitution is.

**The ambiguity is resolvable** but not from static RE alone:

1. Decode the actual byte sequences at seq 0x2..0x24 in the
   capture against the community dump's wire-format spec
   (`[PackedSize_LE][0x00][0x01][type:u8][data...]`) to confirm
   each frame's message type.
2. Hook `FUN_146454c00` (the SelfIdent handler) at runtime to see
   if it actually fires during a replay session.
3. Find a different captured session that's known to include
   PlayerManagerSelfIdentificationMsg as identified by Frida.

**This is now the most important question** for moving past the
state-10 stall. Recommended for the maintainer: take one captured
session through the existing Frida hooks and verify whether
`FUN_146454c00` fires during the replay.

**Next** (queue):
- **Q-MAINTAINER**: verify whether the replay actually delivers
  PlayerManagerSelfIdent via existing Frida hooks. This is the
  single most important question for the state-10 blocker. Added
  to "Queued for maintainer".
- C6 (back-fill connection-flow.md) deferred — the post-V3 doc
  this morning is sufficient for now.
- C7 (final consolidation) — closer to ready now.

**Blockers:** None for the loop.

---

### 2026-05-07 — wake 25: parallel-agent audit of a related public repo

**Did:**
- Cloned a publicly-shared related private-server simulator (Rust,
  separate codebase) to a sibling directory (kept outside this
  repo's tree). Dispatched two parallel general-purpose agents,
  each read-only:
  - Agent A: protocol-implementation audit. Read protocol-notes/,
    docs/, crates/. Looked for SM_CONNECT_ACK, V3 response, post-V3
    sequence, and wire-format rationale.
  - Agent B: tasks-history audit. Read the numbered tasks
    chronologically (001..104+) for the development arc and any
    fix that closed a V3 retry / state-10 stall.

**Found (both agents converged):**

The other project hasn't actually connected a real client, and by
its own design policy it never will until it has synthetically
reproduced everything in a fake-protocol harness first. Specifically:

- Their "real protocol adapter" is a non-operational stub: every
  inbound/outbound function rejects input or returns nothing. The
  only executable protocol path in their runtime is a JSON-over-UDP
  fake.
- Their "static world entry" milestone (referenced in recent
  commits) is an in-process synthetic harness, not real-client
  connectivity. Their MVP-1.5 readiness review explicitly states:
  "The bytes on the wire are fake-protocol JSON. The real
  Javelin/REP frame format is not implemented or even parsed."
- Their tasks (001..104+) contain zero references to V3 retry,
  state 10, REP-channel acceptance, session teardown, or any of
  the symptoms we're stuck on.
- Their protocol docs explicitly forbid adopting real opcodes,
  message IDs, ACK encoding bytes, etc. as "facts" until
  reproduced synthetically. Examples of their stance:
  - "Specific channel IDs / message IDs / opcodes — Unverified —
    Not listed here on purpose. Not facts."
  - "Specific keepalive intervals, replay-window sizes, or ACK
    encoding bytes. Intentionally not catalogued as facts."

**Most important note:** their evidence docs **cite this repo
(`nw-private-server/first-light`) as the upstream source** for
their post-V3 understanding. Both agents independently recommended:
"skip the other project and read `nw-private-server/first-light`
directly." We are the upstream they're holding at low confidence —
not the other way around.

**Conclusion:** the other project is not a useful cross-reference
for the state-10 / V3-retry stall. It's at a different layer
(synthetic-protocol authoritative-server runtime) and would need
to do significant real-protocol work to even share a problem space
with us.

**Why this finding is still valuable:**

- We now know definitively that there is no shortcut from studying
  the other project. Time spent there would be wasted.
- The loop's earlier conclusion stands: the most promising next
  static-RE move is byte-decoding the captured replay's seq 0x14
  area to confirm whether the gating SelfIdent message is actually
  in the bytes being replayed.
- The runtime-hook items remain the long-term answer, but they
  needed the project's own captures + Frida session, not someone
  else's code.

**Next** (queue unchanged):
- Byte-level decode of `info/nw-login-safe-20260502-153840/`
  seq 0x14 (Phase 9b candidate slot) to verify SelfIdent presence.
- C7: final consolidation across what's been learned.

**Blockers:** None for the loop.

---

### 2026-05-07 — wake 26: byte-decoded the captured replay — SelfIdent NOT in capture window

**Did:**
- Inspected the captured replay
  (`info/nw-login-safe-20260502-153840/messages-redacted.txt`)
  byte-level, looking for the community-dump Phase 9b SelfIdent
  signature `00 01 91 17` (= NW-protocol-wrapper marker `00 01`
  followed by 2-byte type `0x91 0x17`).
- Searched for all `0x91`-prefixed frames in the entire capture.
- Listed every small (≤20-byte) message in the capture by seq, type
  and direction.

**Found:**

1. **The community-dump Phase 9b signature does NOT appear anywhere
   in the capture.** Zero hits for `00 01 91 17`.

2. **The only `0x91`-prefixed frame is `00 01 91 19`** at seq `0x7`
   — that's a 4-byte type `0x651` message. The community dump labels
   `0x91(0x19)` as Phase 5 INIT (part of a 21B grouped record:
   4B `0x91(0x19)` + 17B small `0xa4`).

3. **All small messages in the capture window** (seq 0x0..0x24
   range, plus heartbeats afterward):

   | Seq | Type | Size | Likely phase |
   |---|---|---|---|
   | 0x2 | 0x15d | 12B | HEARTBEAT 0x9d (Phase 2) |
   | 0x7 | 0x651 | 4B | INIT 0x91(0x19) (Phase 5) |
   | 0x8 | 0xa4 | 20B | small 0xa4 (Phase 5 grouped) |
   | 0xa | 0x14f | 12B | HEARTBEAT 0x8f (Phase 7) |
   | 0xf | 0xa4 | 20B | small 0xa4 (Phase 9 candidate) |
   | 0x27+ | mixed | 12B | post-replay heartbeats |

   **No 4-byte SelfIdent message after seq 0xf.** The capture
   transitions from Phase 5/6/7-shape messages directly into the
   chunked WORLD DATA (seq 0xc..0x24, all type 0x1b88 = `0x9c`)
   and then to entity-stream traffic.

**Two possible interpretations:**

**(A) The captured session simply doesn't contain SelfIdent.**
This would happen if:
- The capture was filtered or truncated before SelfIdent could
  be observed.
- The captured session was a special form (editor login,
  developer-mode bypass) that doesn't generate SelfIdent.
- The community dump's 22-phase sequence is from a DIFFERENT
  point in the connection than what this capture covers — e.g.
  this capture is post-V3 actor-game-connection traffic, not
  the immediate post-V3 lifecycle messages.

If (A) is correct, **no amount of server-side replay tuning,
substitution refinement, or ack-shape adjustment can advance
state 10→11**. The gating message simply isn't in the bytes
being replayed. The fix path requires a fresh capture that
includes SelfIdent.

**(B) The build version disagrees with the community dump on
sub-IDs.** If this game build's SelfIdent is actually
`0x91(0x19)` (matching seq 0x7) and the community dump's
`0x91(0x17)` claim is from a different build version, then:
- Seq 0x7 IS the SelfIdent message.
- The replay window already covers it (seq 0x2..0x24 includes
  seq 0x7).
- The state-10 stall is from something else — substitution,
  seq numbering, ack shape, or a downstream issue.

**How to distinguish (A) vs (B):**

Run the existing Frida hook on `FUN_146454c00` (the SelfIdent
handler at `0x146454c00`) during a live replay session. If
that handler fires when seq 0x7 reaches the client, (B) is
correct and we should chase substitution / ordering issues. If
it never fires regardless of how many seq 0x7-shaped messages
arrive, (A) is correct and we need a fresh capture.

This is the **single most important question** for the V3-retry
blocker. Already promoted to top of the maintainer queue in
wake 24; this iteration adds the byte-level evidence that makes
the question precise: "does FUN_146454c00 fire on the seq 0x7
message in our capture, or not?"

**Bonus finding — confirmation of community-dump notation:**

The notation `0x91(0xNN)` in the community dump means "first
wire byte 0x91, second wire byte 0xNN" (after the `00 01`
marker). The decoded type ID under the project's typed-stream
encoding `[(t & 0x3F) | 0x80, (t >> 6) & 0xFF]` is then:

- `0x91(0x19)` → low6=0x11 + (0x19<<6)=0x640 → type 0x651
- `0x91(0x17)` → low6=0x11 + (0x17<<6)=0x5C0 → type 0x5d1
- `0x9c` → (presumably single-byte? or `0x9c(0x02)`?) → 0x9c
  itself (since 0x9c & 0x3F = 0x1c, |0x80 = 0x9c, so wire
  byte 0 = 0x9c with no second byte, decoded = 0x1c, but
  community calls it "0x9c"). Inconsistent.

The single-byte vs 2-byte type encoding is itself a wire-
format ambiguity worth resolving more thoroughly. For now the
above finding stands without depending on type-ID decoding —
direct byte search for `00 01 91 17` returns no hits, period.

**Next** (queue):
- Top maintainer-queue item remains: Frida-verify whether
  `FUN_146454c00` fires for the seq 0x7 message in the
  current replay. Resolves the (A) vs (B) ambiguity and
  identifies the actionable fix.
- C7 (final consolidation) — the project picture is now sharp
  enough to write the master synthesis.

**Blockers:** None for the loop. The state-10 root cause has
narrowed to two specific possibilities, distinguishable by a
single Frida observation.

---

### 2026-05-07 — wake 27: Mixed Nuts C↔S framing spec + correlation_uuid hypothesis

**Did:**
- Documented a 2026-05-07 wire-format spec received from a separate
  reverser (Mixed Nuts) covering the asymmetric C↔S application-layer
  framing.
- Compared the spec against the project's existing V3 request decode
  (`server/javelin/v3_request.py` and
  `analysis/v3_request/{HEADER,BODY}_DECODE.md`).
- Updated `docs/post-v3-sequence.md` to include the C↔S framing
  asymmetry section.

**Found (Mixed Nuts spec):**

```
C → S  [crc32:u32 BE][payload_size:u32 BE][correlation_uuid:16][typed_envelope]
       crc32 covers (correlation_uuid + envelope)
       payload_size = 16 + len(envelope)

S → C  [message_size:VLQ32][typed_envelope]
```

The 16-byte `correlation_uuid` matches the community dump's
`session:8B + peer:8B` decomposition — same wire layout, two
different naming conventions across independent reversers.

**Where the project's parser stands today:**

The project's V3 request pipeline strips an 11-byte (retry) or
16-byte (first-attempt) header before passing the 832-byte
"AzCore body" to `parse_v3_request`. That header is decoded as
**carrier-record framing** (flags, channel, sequence acks,
msgID), not as Mixed Nuts's `[crc32][size][correlation]`
24-byte prefix.

So Mixed Nuts's spec describes either:
- A different protocol layer than what the project observes
  (likely an outer DTLS-decrypted-datagram structure that gets
  stripped before the carrier-record splitting).
- Or the correlation_uuid is hidden inside the V3 body's "prelude"
  (33 bytes opaque at body[0..0x21], which contains "u64/handle"
  at +6..13 and "CRC32-shaped" at +0x14..0x1b — together 16 bytes
  if read across the 6-byte unknown sub-header gap).

The session_uuid string at body[0xa8] (currently echoed into the
response's 32-byte session field) is *probably* the correlation
referent for client request-response matching, just embedded as
an AzCore string element rather than at the framing layer.

**The actionable hypothesis for the V3 retry blocker:**

The V3 RegistrationResponse template currently in `v3_response.py`
has an opaque `[8B mystery]` field that's zero-filled. If the
client expects this field to mirror the first 8 bytes of the
correlation_uuid (the "u64/handle" at body[6..13] of the request),
that would explain the V3 retry: the client's request-response
correlator never matches and it retries indefinitely.

**Concrete next experiment for the maintainer**: take the first 8
bytes of the V3 request's prelude (the "u64/handle" at body[6..13])
and stuff them into the response's `[8B mystery]` field instead of
zero-filling. ~2-line change in `v3_response.py`. If the V3 retry
stops, this is the V3-retry root cause.

**Why this is a strong hypothesis** (not just a guess):

1. The community dump explicitly says the C→S framing has a
   correlation field, and Mixed Nuts independently confirms it as
   16 bytes. Two reversers agree.
2. Mixed Nuts also says S→C has no correlation in the framing —
   so if correlation matters for response identity, it must
   appear inside the response body somewhere.
3. The V3 response body has exactly one currently-opaque field
   (`[8B mystery]`) — and 8 bytes is half of a UUID, plausibly
   the most-significant or signature half.
4. The other framing details (CRC32 over correlation+msg in C→S)
   the project doesn't currently validate or compute, but those
   are server-side concerns; the client doesn't care.

**Why it might NOT be the answer:**

1. The correlation_uuid might not be required for response
   correlation at all — maybe the carrier reliable-sequence
   layer handles request matching (each V3 request has a unique
   `msg_seq`/`rel_seq`, server's response is on the same channel).
2. The 8-byte "mystery" field might be something completely
   different (a pad, a flag, a result code, an opaque cookie).

Either way, the test is cheap (~2 lines, single live run).

**Adjacent useful surface from Mixed Nuts's spec:**

The CRC32 covers (correlation + msg). The project's server
currently doesn't validate incoming CRC32 on V3 requests — it
just trusts the bytes. Validating the CRC32 would let the server
reject malformed requests cleanly. This is a *defensive* fix,
not a project-blocker.

**Updated maintainer queue:**

Top item now reads: try the correlation echo experiment in
`v3_response.py`. If it fixes V3 retry → root cause confirmed,
state-10 should advance immediately on next request (since
SelfIdent or whatever Phase 9b is in this build is already in the
replay window per wake 26's interpretation B). If it doesn't fix
V3 retry → either (a) wake 26's interpretation A is right and the
replay genuinely lacks SelfIdent, or (b) the V3 retry is from
something else entirely and we need the Frida hook on
`FUN_146454c00` to disambiguate.

**Next** (queue):
- C7 (final consolidation) — picture is now sharp enough to
  write the master synthesis tying state-machine map +
  protocol layers + open questions into one coherent doc.
- The maintainer-queued correlation experiment is the highest-
  value live test once they're at a real keyboard.

**Blockers:** None for the loop.

---

### 2026-05-07 — wake 28: C7 done — master synthesis doc written

**Did:**
- Wrote `docs/protocol-overview.md` (~250 lines) as the maintainer-
  facing master synthesis. Sections: where the project is (state
  table), layered protocol map (5 layers from HTTPS auth down to
  typed messages), state-machine ladder, 22-phase summary, what
  the server does today, open questions with leading hypotheses,
  comprehensive file index, three-tiered "what good progress
  looks like" roadmap.
- Updated `README.md` "Key protocol references" section to point
  at the new doc as the starting point, and added cross-references
  to `post-v3-sequence.md`, `state_machine_summary.md`,
  `message_inventory.md`.

**Why this doc:**

After 27 wakes the project's docs/ and analysis/ directories
contain a lot of detail (state-machine map, protocol sequence,
message inventory, captured replay, community findings, framing
spec) but no single entry point. A new contributor — or the
maintainer returning after time away — needed to know which
file to open first.

`protocol-overview.md` is that entry point. It uses the master
diagram pattern (5 nested layers from HTTPS down to typed
messages) so anyone can place a question at the right layer
and find the relevant detail doc.

**Layer diagram introduced:**

```
HTTPS auth (auth_mock.py)
    │
DTLS 1.2 / Javelin REP (rep_responder.py)
    │
GridMate Carrier datagram (frame.py)
    │
Application-layer message (Mixed Nuts asymmetric framing)
    │
Typed messages (2,025 InstallRegistrationHook<T> instantiations)
```

This was previously implicit; making it explicit lets the
maintainer point reviewers / contributors / commenters at the
correct depth for any question.

**Three-tier roadmap section** added:

1. **Resolve V3 retry** (small, fast — correlation-echo
   experiment in v3_response.py).
2. **Extend replay coverage past seq 0x24** (medium, needs new
   captures — particularly Phase 11b CH1 init burst).
3. **Implement Phase 16 SPAWN** (larger, requires runtime
   verification — once delivered, state 14 = MVP).

The path from "today" to "MVP" is now bounded with specific
testable next steps rather than open-ended mysteries.

**Loop's overall arc complete:**

What started as static-RE on a single function (FUN_14644a070)
to find the state-10→11 gate has become:

- Full state-machine map (states 0–14 with names + predicates)
- Identification of the SelfIdent message and its handler chain
- Discovery of two community-shared resources already in the
  repo (typeregistry.json, 22-phase dump) that significantly
  expand the picture
- Comprehensive 2,025-message inventory across 174 namespaces
- Mixed Nuts wire-format spec integrated
- Specific testable hypothesis for the V3 retry blocker
- Master synthesis doc making it all navigable

Every static-RE thread that was open at start of day has either
been resolved or narrowed to a specific testable hypothesis.

**Next** (queue is light):
- Could still characterize PlayerManagerTrait / Hub* families
  for orthogonal long-term value (C2/C4 from the original
  multi-day plan).
- Could deepen any single area (e.g., Frida-script template for
  the correlation-echo experiment so the maintainer just runs
  it).
- Or pause until the maintainer runs the correlation experiment
  and feeds back results.

Recommend the loop pauses for a few wakes pending the user's
direction; the highest-value static work has landed.

**Blockers:** None for the loop. The static-RE picture is now
comprehensively documented and the project's path to MVP is
bounded by 1–3 testable experiments.

---

### 2026-05-07 — wake 29: ready-to-apply patch for the correlation experiment

**Did:**
- Read `server/javelin/v3_response.py` in full to understand the
  `mystery8` field's current state. **Important correction**:
  `mystery8` is NOT zero-filled (as I'd written earlier) — it
  defaults to specific captured bytes (`0b 88 8d 68 70 6c 41 5b`)
  from Mixed Nuts's real successful login.
- Wrote `analysis/proposed_patches/correlation_echo_v3_response.md`
  — a comprehensive proposed patch document.

**Why "patch document" not "applied patch":**

Per `project_autonomous_session_plan.md`, server code changes need
a confident hypothesis first AND maintainer approval. The
correlation-echo hypothesis is sharp but untested. Writing the
change as a reviewable proposed patch (with diff, test plan,
revert plan) gives the maintainer a one-step apply-and-test
workflow when they're at a real keyboard.

**Mystery8 finding sharpens the hypothesis:**

The current `mystery8` default is bytes captured from Mixed Nuts's
real successful login. Those bytes WORKED for that captured
session — which is consistent with them being a correlation
echo for *that* session's correlation_uuid. For new sessions
with different correlation_uuids, the bytes are wrong, the
client's correlator never matches, and V3 retries forever.

This is a *much* stronger hypothesis than "the field is zero-
filled and might need to mirror something" — the field is
actively hardcoded to one specific session's value.

**Patch shape** (~10 lines + CLI flag, default unchanged):

- Add `--mystery-source {captured,echo-prelude}` CLI flag, default
  `captured` (= current behavior, no regression).
- When `echo-prelude`, set `mystery8 = m.payload[6:14]` (the V3
  request body's "u64 / handle" 8-byte field per
  `analysis/v3_request/BODY_DECODE.md`).
- Threading through `PeerSession.__init__` to make the flag
  reachable in `_handle_v3_data_record_inner`.

**Test workflow** documented inline:
1. Run with default → confirm baseline V3 retry symptom.
2. Run with `--mystery-source echo-prelude` → look for one of:
   - Server log: V3 RegistrationRequest count stops climbing.
   - Server log: "replay queue armed" firing.
   - Frida log: "actor game connection succeeds" trace.
3. If V3 retry continues → hypothesis wrong, next step is Frida
   hook on `FUN_146454c00`.

**Why this is worth doing first** (compared to the Frida hook):

- 1 server-side flag toggle vs writing a Frida script + Frida
  setup against EAC.
- ~10 LoC vs an unbounded read-only client-side instrumentation.
- Single live run resolves either way (success or null result).

**Patch is intentionally NOT applied:**

The maintainer's discipline is to gate server-code changes
behind explicit testing intent. The patch doc gives them a
review-and-apply workflow; the loop stays on its read-and-
document discipline.

**Other refinements possible later:**

- If `mystery8 = body[6:14]` doesn't work, alternative candidates
  (CRC32-shaped bytes at body[0x14:0x1c], hash transformations)
  are documented in the patch's "Failure signal" section.
- A second proposed patch could add server-side CRC32 validation
  of incoming C→S records (defensive — not project-blocking but
  good hygiene). Not written yet.

**Next** (queue):
- C2 (PlayerManagerTrait characterization) — orthogonal long-term
  value. Could pick up next iteration.
- Or: write a second proposed-patch doc for the Frida hook (the
  fallback if correlation-echo doesn't work) so the maintainer
  has both experiments staged ready-to-go.
- Or: pause the loop pending the maintainer's run of the
  correlation experiment and route results into the next
  iteration's direction.

The loop is now firmly in "polish + ready-to-apply deliverable"
mode rather than "uncover new findings" mode.

**Blockers:** None for the loop.

---

### 2026-05-07 — wake 30: Frida hook script staged for the SelfIdent diagnostic

**Did:**
- Read existing `tools/client-hooks/frida_dtls_hook.js` and
  `frida_capture.py` for project Frida convention.
- Wrote `tools/client-hooks/frida_self_ident_hook.js` — a focused
  hook script that targets `FUN_146454c00` (SelfIdent handler) and
  `FUN_145a87010` (onConnectionSuccess wrapper-substate writer).

**Why this hook:**

It's the second of the two staged experiments for resolving the
state-10 stall:

1. **Correlation-echo patch** (already staged at
   `analysis/proposed_patches/correlation_echo_v3_response.md`) —
   the cheaper test, 10-line server-side change with a CLI flag.
2. **Frida hook on SelfIdent handler** (this iteration) — the
   fallback diagnostic if (1) doesn't resolve the V3 retry.

The hook resolves wake 26's interpretation A vs B in a single
observation:
- If `FUN_146454c00` fires during a replay session: interpretation
  B is correct (the captured seq 0x7 IS the SelfIdent for this
  build) and the stall is downstream of the handler.
- If it never fires: interpretation A is correct (capture lacks
  SelfIdent) and the project needs new captures.

**What it logs:**

For each handler invocation, the seven in-args plus hex dumps of
the pointer-shaped struct args:
- `param_3` (Tuple36) — 36 bytes — likely uuid+uuid+int
- `param_4` (Tuple36) — 36 bytes — same shape
- `param_6` (MsgBody) — 28 bytes — message header fields
- `param_7` (StringPlus17) — AZStd::string + tail, decoded
  inline using SSO-aware logic

Plus a separate hook on `FUN_145a87010` (onConnectionSuccess) so
the maintainer can tell whether the substate=2 write is happening:
- SelfIdent fires + onConnectionSuccess fires → state 10→11 should
  advance, project past the blocker.
- SelfIdent fires + onConnectionSuccess does NOT fire → handler is
  bailing mid-execution (substitution / field-shape issue, but
  message ARRIVING is fine).
- Neither fires → message isn't arriving at all.

Three distinct outcomes, three distinct fix directions.

**Why this is a NEW file** (not an addition to the existing
`frida_dtls_hook.js`):

- The existing hook is a comprehensive observation suite with many
  hooks for the broader DTLS / REP / transport-state work.
- This new hook is a focused diagnostic with two Interceptor.attach
  calls. Keeping it separate lets the maintainer load JUST this
  one without the heavier observation overhead, and revert by
  not loading it.
- Doesn't change any existing project behavior.

**Usage** (documented in the file header):

```bash
frida -p <NewWorld_PID> -l tools/client-hooks/frida_self_ident_hook.js
```

Or add to the script-loading list in `frida_capture.py`. Output
goes through the standard `{type:"log", text:...}` channel so it
shows up alongside the main hook logs.

**Three open questions resolvable in one Frida session now:**

1. Does SelfIdent handler fire during replay?
2. Does onConnectionSuccess fire after SelfIdent?
3. What are the actual byte layouts of the seven in-args?

The third item alone resolves the wire-format gap that's been
the runtime-needed bottleneck for multiple queued tasks (A2.9c,
A4.3, etc.).

**Pair with the correlation-echo patch:**

The maintainer's keyboard-time workflow is now:
1. Apply the correlation-echo patch (file 1).
2. Run server with `--mystery-source echo-prelude`.
3. Run client with this Frida hook loaded.
4. Watch for HANDLER FIRED + connectionSuccess FIRED logs.
5. If both fire → V3 retry resolved + state advancing.
6. If only HANDLER FIRED → patch worked but substitution broken.
7. If neither → patch didn't resolve V3 retry; switch direction.

Three distinct success/failure states, three distinct next
moves. The project's path past the V3 retry is now a decision
tree with bounded branches.

**Next** (queue):
- C2 (PlayerManagerTrait characterization) — orthogonal long-term
  value, ~28 server-side messages to enumerate.
- Consider any "polish" improvements to existing docs based on
  the deeper understanding now in place.

**Blockers:** None.

---

### 2026-05-07 — wake 31: namespace-convention notes added to message_inventory

**Did:**
- Considered C2 (PlayerManagerTrait deep characterization) but
  realized most of those 28 messages are server-side INTERNAL
  bus messages, not on-wire types. Their handlers are in the
  server side (which the project IS implementing); the project
  doesn't need to *catalog* them in detail because it's writing
  them, not reverse-engineering them.
- Pivoted to a smaller polish: added a "Namespace conventions
  (which side of the wire?)" section to
  `analysis/message_inventory.md` documenting which namespace
  prefixes correspond to on-wire vs internal-bus messages.

**Found (sharper namespace-pattern interpretation):**

The pair `Aoi::PlayerManagerTrait::RequestRejectClientConnectionMsg`
+ `Javelin::ClientMessagesTrait::PlayerManagerRejectedMsg` shows
the project's two-namespace pattern:

- `Aoi::*Trait::*` = server-side internal request/notify bus.
  Server components send these to each other; effects propagate
  to clients via the corresponding ClientMessagesTrait message.
  NOT on the wire.
- `Javelin::ClientMessagesTrait::*Msg` = canonical server→client
  on-wire message types. ON the wire.
- `Javelin::ClientMessages::*` = component-facet messages
  (both directions). ON the wire.
- `MB::*` = MarshalByValue replicated state. ON the wire (replica
  state stream).
- `Amazon::IPC::*` = inter-process scaffolding. NOT on wire (but
  registered in same dispatch system, hence catalog match).
- `ActorMover::*` = movement messages. ON the wire (high freq).

**Rule of thumb for the project**: when looking for what the
server needs to SEND, look in `Javelin::ClientMessagesTrait::*`
and `Javelin::ClientMessages::*`. When tracing where a server-
side action originates, look in `Aoi::*Trait::*`. The two halves
typically pair up by name (`RequestRejectClientConnection` →
`Rejected`).

**Why this matters:**

It saves future investigators time. Without this convention note,
someone looking at PlayerManagerTrait's 28 messages might think
all 28 are on-wire types the server needs to encode. They're not
— most are server-side internal events that produce ZERO direct
wire traffic. The on-wire counterpart for the project to deliver
is whatever ClientMessagesTrait message gets dispatched in
response.

**Why this is a polish iteration not a deep dive:**

Static-RE on the 28 PlayerManagerTrait handlers wouldn't surface
new actionable info for the V3-retry blocker (which is the
project's immediate concern). The namespace note is the high-
leverage takeaway from the inventory; longer trait-by-trait
characterization waits until the project has a runtime data
source to validate against.

**Next** (queue):
- Possible next polish: cross-link `analysis/message_inventory.md`
  back into `docs/protocol-overview.md` so readers find the
  namespace conventions on first browse.
- Or wait for the maintainer's correlation-echo experiment
  results and pivot based on outcome.

**Blockers:** None.

---

### 2026-05-07 — wake 32: protocol-overview cross-link to namespace conventions

**Did:**
- Added a "Namespace convention (which side of the wire?)" subsection
  in `docs/protocol-overview.md` directly under the layered-protocol
  diagram, with a worked example pair and a deep-link to the full
  table in `analysis/message_inventory.md`.

**Why this place:**

The protocol-overview's layered diagram introduces the concept of
"typed messages" (the bottom layer of the stack) but the diagram
itself doesn't disambiguate on-wire vs internal. A first-time reader
who lands on protocol-overview will see the message catalog count
(2,025) and immediately benefit from knowing the heuristic for
which slice is on-wire.

The example pair `RequestRejectClientConnectionMsg` →
`PlayerManagerRejectedMsg` was chosen because it's directly relevant
to the project's V3-retry investigation (the rejection path) and
the cross-namespace pairing is unambiguous.

**Next** (queue):
- Could add a similar cross-link from `docs/post-v3-sequence.md` to
  the wire format details if there's a duplication worth resolving.
- Or pause polish work and wait for maintainer correlation-experiment
  results.

**Blockers:** None.

---

### 2026-05-07 — wake 33: third V3-retry hypothesis — stubbed character_uuid

**Did:**
- Read `server/javelin/replay_substitution.py` to look for
  substitution-side issues that could explain the V3 retry
  blocker.

**Found:**

The `SubstitutionContext.character_uuid_bytes` is a **deterministic
UUID5 stub derived from `persona_id`**, not the real character
UUID from the client's auth flow:

```python
# Character UUID: stub from persona unless caller provided auth_state
# with a real value (forward-compat hook).
if auth_state and isinstance(auth_state.get("character_uuid"), uuid.UUID):
    character_uuid = auth_state["character_uuid"]
else:
    character_uuid = _stub_character_uuid_from_persona(persona_id_text)
    warnings.append(
        "character UUID stubbed from persona-id "
        "(no auth-state bridge available)"
    )
```

The `auth_state` parameter is comments-described as
"reserved for a future bridge to the auth-mock state (so we can
pull a real character_id once the responder shares state with the
HTTPS mock). Pass None for now."

`rep_responder.py:_handle_v3_data_record_inner` calls
`SubstitutionContext.from_v3_and_session(req=req,
session_token=token, character_display_name=...)` — **with no
auth_state argument**, so the stub path runs.

**Why this could be the V3 retry root cause:**

The client knows its real character UUID from the auth flow (the
auth_mock issued it during character creation / login). When the
server replays post-V3 messages with the character UUID
substituted to the UUID5 stub, the client may see a UUID it
doesn't recognize for "its" character and reject the post-V3
sequence.

That rejection might *look* like a V3-acceptance failure (because
the replay starts immediately after V3 and the client never
"completes" the post-V3 phase), causing V3 retry — even though
V3 itself was technically accepted.

**This is a THIRD hypothesis** for the V3 retry, distinct from:

1. **Correlation-echo** — response's mystery8 field doesn't echo
   the request's correlation_uuid. (Patch staged at
   `analysis/proposed_patches/correlation_echo_v3_response.md`.)
2. **Missing SelfIdent** — capture genuinely lacks the gating
   message. (Diagnostic Frida hook staged at
   `tools/client-hooks/frida_self_ident_hook.js`.)
3. **Stubbed character_uuid mismatch** (this iteration) — replay
   substitution uses fake character UUID; client sees mismatch
   and rejects post-V3 traffic.

All three are plausible. They're distinguishable:
- Hypothesis 1: V3 retries continue regardless of replay quality.
  Stops only when correlation echo is fixed.
- Hypothesis 2: V3 stops retrying but state never advances past
  10 because the gating message simply isn't being sent.
- Hypothesis 3: V3 stops retrying after correlation fix but state
  *still* doesn't advance because client rejects substituted
  identity.

**The Frida hook** (wake 30) actually disambiguates all three:
- If `FUN_146454c00` (SelfIdent handler) NEVER fires →
  hypothesis 2 (capture lacks SelfIdent).
- If it fires but `FUN_145a87010` (onConnectionSuccess) doesn't →
  hypothesis 3 (handler bails on identity check). The SelfIdent
  handler decomp shows it iterates an observer list before
  setting substate=2; if any observer rejects the substituted
  identity, that path skips onConnectionSuccess.
- If both fire → V3 retry was hypothesis 1, now resolved.

So the staged experiments cover all three possibilities. Adding
this hypothesis to the queue documentation makes the maintainer's
keyboard-time decision tree complete.

**Useful refinement to the patch document:**

`analysis/proposed_patches/correlation_echo_v3_response.md`'s
"Failure signal" section should mention hypothesis 3 as another
possibility if the patch alone doesn't resolve V3 retry. (I'll
leave updating that as a follow-up; the patch doc is already
written.)

**Bridging the auth_mock to the rep_responder** is the
project-side fix for hypothesis 3:
- Auth_mock generates / stores a real character UUID at
  character-creation time, keyed by persona_id.
- Rep_responder loads that character UUID and passes it via
  `auth_state={"character_uuid": ...}` when building the
  substitution context.
- Then `replay_substitution.py` uses the real value instead of
  the stub.

This is a small change but spans two server modules. Marking it
as a low-priority server-experiment task for the maintainer.

**Next** (queue):
- Could update the proposed_patches/ doc to note hypothesis 3.
- Could write a sketch of the auth-state bridge.
- Otherwise, polish well is genuinely shallow now; pause until
  the maintainer's experiment results.

**Blockers:** None for the loop.

---

### 2026-05-07 — wake 34: server-side verification stood up; client-side blocked by EAC

**Did:**
- Surveyed feasibility of running NewWorld.exe locally for in-world
  verification of state transitions. Concluded: not reachable from
  this Mac.
- Stood up Python 3.12 venv (`.venv/`, gitignored) with pytest +
  pyOpenSSL deps.
- Ran the project's pytest suite with a 30s per-test timeout:
  **84 tests passed in 0.32s** (codecs, parser, replay
  substitution, captures, chunking, vlq32). Excluded
  `server/test_client.py` from collection because it `sys.exit(1)`s
  on import when `python3-dtls` isn't installed — that's a manual
  integration script, not a unit test.
- Ran `server.test_loopback` standalone with 30s shell timeout:
  full SM_CONNECT_REQUEST → SM_CONNECT_ACK round-trip works
  in-process without DTLS. Server-side parser + marshaler + handler
  paired correctly.

**What can't be verified locally** (and why):

NewWorld.exe is Windows-only and EAC-protected. Three layered
blocks:

1. **Apple Silicon Mac** — runs Windows ARM64 in Parallels / UTM /
   VMware Fusion, and Windows ARM64 runs x64 binaries via Microsoft
   Prism, but...
2. **EAC detects VMs.** Hypervisor-detection in current EAC builds
   refuses to launch the game in any detected VM. Evasion is an
   arms race.
3. **Project's bypass requires the non-EAC archived build.** Per
   `tools/client-hooks/README.md`: "The live Steam build rejects
   all runtime instrumentation due to Easy Anti-Cheat. Requires
   the archived/non-EAC build." The project's Frida cert-pinning
   bypass operates *after* the game process starts — EAC's
   launcher-time checks kick before any of those hooks load.

So local in-world verification needs:
- A Windows machine (or VM with EAC evasion that the maintainer
  can maintain), AND
- The non-EAC archived build (which the maintainer doesn't have
  remote access to).

Neither is reachable from this Mac. The static-RE picture +
84-test verified server is the binding bound until either changes.

**What IS verifiable locally** (and just was):

| Test | Status | Coverage |
|---|---|---|
| `pytest --ignore=server/test_client.py` | ✅ 84/84 pass | parser / marshaler / replay substitution / captures / chunking / vlq32 |
| `python -m server.test_loopback` | ✅ pass | in-process SM_CONNECT_REQUEST → SM_CONNECT_ACK round-trip |

Both run with strict timeouts (30s pytest per-test, 30s shell-level
for the loopback). No long-running risk.

**Reproducible verification commands:**

```bash
# One-time setup
python3.12 -m venv .venv
.venv/bin/pip install -q pytest pytest-timeout pyOpenSSL

# Run the unit suite (exclude the manual integration script)
.venv/bin/pytest --timeout=30 --ignore=server/test_client.py

# Run the loopback smoke test
timeout 30 .venv/bin/python -m server.test_loopback
```

The `.venv/` directory is gitignored. No source changes required to
run these.

**Why this matters:**

When the maintainer applies the staged correlation-echo patch
(`analysis/proposed_patches/correlation_echo_v3_response.md`), they
should re-run the unit suite first to confirm the patch doesn't
regress server-side correctness. The 84-test bar is now an
explicit pre-condition.

**Next** (queue):
- Could update `docs/protocol-overview.md` with the verification
  commands so they're discoverable.
- Or pause until the maintainer's experiment results.

**Blockers:** None.

---

### 2026-05-07 — wake 35: verification commands surfaced in protocol-overview

**Did:**
- Added a "Local verification" section to
  `docs/protocol-overview.md` between "Open questions" and
  "File index". Documents the pytest + loopback commands with
  strict timeouts, what coverage they provide, and what they
  explicitly DON'T cover (client-side / in-world state).

**Why:**

After standing up the verification environment in wake 34, the
commands lived only in the worklog narrative. Surfacing them in
the maintainer-facing overview means anyone landing on the
project sees the regression bar (84 tests, 0.3s) at the same
place they read the open-questions list.

**Pause state:**

VM-setup-for-Windows work is on hold pending explicit user OK
to install UTM. The user said "Slow iteration is fine as long
as it's constant" — so the loop continues on its 240s cadence
with polish work, but anything requiring software installation
on the host machine waits for explicit go.

**Next** (queue):
- Could write a short doc on the Phase 1–6 VM setup plan as a
  "ready-to-go when authorized" deliverable so the maintainer
  has the steps documented when they choose to proceed.
- Or continue polish work on existing docs.

**Blockers:** Unilateral software installation paused awaiting
maintainer OK on UTM.

---

### 2026-05-07 — wake 36: the "non-EAC archive" trick is just don't run the launcher

**Did:**
- Re-read `tools/client-hooks/frida_capture.py:249-275`,
  `tools/client-hooks/README.md`, and `docs/non-eac-capture-plan.md`
  to figure out what the existing setup actually does to bypass EAC.
- Verified the contents of the SteamCMD-downloaded game directory.

**Found:**

The "archived non-EAC build" the project's docs reference is **just
a copy of the game directory** with one configuration trick — there's
no patched binary, no community-sourced alternate version, no EAC
removal. The full mechanism, recovered from existing code:

1. Copy the game directory anywhere (the project's own
   `frida_capture.py` only cares about the `--exe` path).
2. Create a `steam_appid.txt` containing `1063730` next to
   `NewWorld.exe` — `frida_capture.py:251` does this automatically
   on every spawn so it's self-contained.
3. Have Steam running and logged in (provides the Steam launch-context
   the game checks at startup).
4. Spawn `NewWorld.exe` directly via `frida.spawn(GAME_EXE)` instead
   of running `NewWorldLauncher.exe`.
5. Frida attaches before the main thread runs and injects the
   trust-patch + hooks scripts.

**EAC is a wrapper, not an integrated check.** It bootstraps from
`NewWorldLauncher.exe` → `EasyAntiCheat_Launcher.exe` →
`NewWorld.exe`. By skipping the launcher chain entirely (just
spawning `NewWorld.exe` directly), EAC's process-injection and
anti-tamper layer never activates. The game proceeds because
`steam_appid.txt` + a running Steam process satisfy its other
launch-context checks.

**What this means for the VM:**

The 71 GB game directory we already have at
`~/SteamLibrary/NewWorld/` (downloaded via SteamCMD on 2026-05-06)
is functionally identical to what would live in
`G:\NewWorldArchive\GameClient\` on a Windows host running the
existing setup. The full path forward is:

| Phase | What | Needs maintainer? |
|---|---|---|
| A. Install UTM, download Windows 11 ARM64 ISO | brew install + ISO download | ✅ user OK to install UTM |
| B. Create VM, install Windows | UTM GUI walks through install | partially — Windows install dialog |
| C. Install Steam in VM, log in | Steam installer, user credentials | ✅ Steam login |
| D. Copy `~/SteamLibrary/NewWorld/` into VM (or via shared folder) | UTM shared folder feature | no |
| E. Install Python 3.11 + Frida 16+ in VM | Python installer, `pip install frida-tools` | no |
| F. Run `frida_capture.py --exe "C:\NewWorldArchive\Bin64\NewWorld.exe"` against our local server | runs the exact same flow as the existing home setup | no |

**No EAC strip needed.** No archive sourcing needed. No multi-week
RE project needed. The game directory we have on disk is the
"archive" once it's in a Windows VM environment with Steam logged
in.

**One real risk: VM detection.** EAC's wrapper would detect a VM if
it ran. But since we're skipping the wrapper entirely, EAC never
runs and never gets a chance to detect the VM. The game's own
internal checks (if any) are configured by `steam_appid.txt` +
Steam process to look like a normal Steam launch. The community
22-phase dump (`info/community_22_phase_in_game_dump.txt`) shows
others have done this on Windows hosts; the VM extension is
plausible.

**One performance concern:** Windows ARM64 + x64 emulation via
Microsoft Prism + Apple Hypervisor framework is going to be slow.
"Boot the game far enough to see state advance" might be feasible
even at low FPS; "play the game" almost certainly isn't. For our
purposes (verify state machine + capture wire bytes), low FPS is
fine.

**Next** (queue):
- Awaiting maintainer's `go` on UTM install (Phase A).
- All subsequent phases documented above; can run them autonomously
  except for Steam login + Windows install dialog clicks.

**Blockers:** Phase A still gated on user OK.

---

### 2026-05-07 — wake 37: VM setup — Phase A already done; Phases B–F documented

**Did:**
- Verified UTM 4.7.5 is already installed on the host (an existing
  Linux VM lives in the UTM data directory; the maintainer has used
  UTM before).
- Wrote `analysis/proposed_patches/vm_setup_steps.md` —
  comprehensive step-by-step for Phases B–G covering Windows ISO
  acquisition, VM creation, Windows install, dependency setup
  (Steam + Python 3.11 + Frida), game-directory copy options
  (shared folder vs external drive), project clone, and the
  `frida_capture.py` invocation.

**What's reachable autonomously vs needs maintainer:**

- Phase A (UTM install): ✅ already done (no work needed).
- Phase B (Windows 11 ARM64 ISO download): needs maintainer at the
  keyboard — Microsoft's download URL uses session-based tokens
  that aren't scriptable. ~10–30 min in a browser.
- Phase C (create VM in UTM): needs maintainer — UTM's GUI is the
  natural interface; ~5 min of clicking through.
- Phase D (Windows install): needs maintainer — interactive
  installer; ~30 min wall-clock with breaks for unattended waits.
- Phase E (Steam + Python + Frida): partially needs maintainer
  (Steam login w/ Steam Guard code); rest is `winget` / `pip`
  one-liners.
- Phase F (copy game directory, clone project): autonomous once
  shared folder is configured.
- Phase G (run frida_capture.py): autonomous; produces
  `capture/<ts>_vm_test/packets.jsonl`.

**Doc covers fallbacks:**

- VM detection (other than EAC, which isn't running) — switch to
  physical Windows host.
- Frida 16 incompatibility on Windows ARM64 — fall back to the
  project's existing `d3d11_proxy` DLL injection path.
- Game refusing to launch despite `steam_appid.txt` — Steam needs
  to be actively running, not just installed.

**The unlock:**

Once the VM setup is complete, the staged
`tools/client-hooks/frida_self_ident_hook.js` (from wake 30)
becomes runnable. That resolves the three V3-retry hypotheses in
one observation, AND captures the wire-format byte layouts for the
seven SelfIdent in-args — multiple "runtime-needed" questions
collapse to a single live session.

**Next** (queue):
- Mostly waiting on the maintainer for Phase B–E hands-on steps.
- Could pre-build a shared-folder script that exports
  `~/SteamLibrary/NewWorld/` on Mac side as soon as the VM is up.
- Or write a host-side script that runs the local server stub
  with arguments preset for VM access (bind to all interfaces,
  not just loopback).

**Blockers:** None for the loop. Phase B (Windows ISO download)
is the maintainer's next step at a real keyboard.

---

### 2026-05-07 — wake 38: VM networking section + verify host bind

**Did:**
- Verified `server/rep_responder.py` defaults to bind `0.0.0.0:23971`
  (line 60), with `--bind-host` / `--bind-port` flags. Reachable
  from the VM out of the box.
- Verified `server/auth_mock.py` defaults to bind `::` dual-stack
  IPv4+v6 with `--rep-host` and `--rep-port` flags for the
  client-facing REP address it advertises in login tickets
  (default 127.0.0.1, will need to be the Mac's VM-side IP for
  the VM scenario).
- Verified `tools/setup_hosts.py` accepts `--target-ip` for the
  redirect target and is hard-coded to the Windows hosts path —
  meant to run inside the VM.
- Updated `analysis/proposed_patches/vm_setup_steps.md` with a
  new Phase G (Networking) and renumbered the "run the existing
  setup" content as Phase H.

**The Phase G section covers:**

1. Finding the Mac's IP from the VM's perspective (default gateway
   in UTM's NAT, typically `192.168.64.1`).
2. Running `auth_mock` with `--rep-host MAC_IP_FROM_VM` so the
   client connects back to the Mac's IP, not localhost.
3. Running `rep_responder` (binds 0.0.0.0 by default, no flag
   needed for VM access).
4. Running `setup_hosts.py --apply --target-ip MAC_IP_FROM_VM`
   inside the VM to redirect Amazon hostnames at the Mac.

**Phase H** also adds a separate `frida` invocation for the
SelfIdent diagnostic hook on top of `frida_capture.py`'s default
hooks.

**Why this matters:**

The original Phase G was a placeholder; without the networking
section, the maintainer would hit "client can't reach server"
errors on first attempt. This makes the doc end-to-end runnable.

**Status of staged deliverables:**

| Deliverable | File | Status |
|---|---|---|
| Correlation-echo patch | `analysis/proposed_patches/correlation_echo_v3_response.md` | ready |
| SelfIdent Frida hook | `tools/client-hooks/frida_self_ident_hook.js` | ready |
| VM setup A→H steps | `analysis/proposed_patches/vm_setup_steps.md` | ready |
| Master synthesis | `docs/protocol-overview.md` | ready |
| Worklog narrative | `analysis/autonomous_worklog.md` | live |

The maintainer's next physical-keyboard activity is Phase B
(Windows ISO download). Everything else is staged.

**Next** (queue):
- The polish well is genuinely getting deep — most things landed.
- Could write a quick FAQ doc consolidating the questions surfaced
  in the live conversation (Prism viability, Windows x64 on
  Apple Silicon, EAC bypass mechanism). Useful for future
  contributors who hit the same questions.

**Blockers:** None.

---

### 2026-05-07 — wake 39: VM setup FAQ written; Phase B complete (ISO landed)

**Did:**
- Wrote `analysis/proposed_patches/vm_setup_faq.md` with calibrated
  answers to seven recurring VM-setup questions: Prism viability,
  why not Windows x64, EAC bypass mechanism, VM detection,
  fallbacks, the 71 GB game-dir transfer, total time estimate, and
  Frida-on-ARM64 fallback to `d3d11_proxy/`.

**Phase B complete:** maintainer reported
`Win11_25H2_English_Arm64_v2.iso` finished downloading. Phase C
(create VM in UTM) is now active.

**Status of staged deliverables:**

| Deliverable | Status |
|---|---|
| Correlation-echo patch | ✅ ready |
| SelfIdent Frida hook | ✅ ready |
| VM setup A→H steps | ✅ ready |
| VM setup FAQ | ✅ ready (this iteration) |
| Master synthesis | ✅ ready |
| 84-test verification | ✅ runs |

**Next** (Phase C is interactive — maintainer at keyboard):
- UTM Create New VM walkthrough
- Resource allocation (8 GB RAM, 4 cores, 100 GB storage)
- Shared folder setup pointing at `~/SteamLibrary/NewWorld/`

**Blockers:** None for the loop. Phase C unblocked, will be walked
through interactively via chat.

---

### 2026-05-07 — wake 40: minimum-game-dir experiment scoped (not feasible statically)

**Did:**
- Inspected `~/SteamLibrary/NewWorld/` layout to assess whether a
  subset of the 71 GB game directory could replace the full
  transfer in Phase F.

**Found:**

Top-level layout:
- `Bin64/` — 268 MB (engine binaries, NewWorld.exe, DLLs)
- `_CommonRedist/` — 136 MB (Visual C++ + DirectX redists)
- `EasyAntiCheat/` — 35 MB (we skip the launcher, so likely not needed)
- `assets/` — **71 GB** (almost everything)
- `bootstrap.cfg` (4 KB) — points at `Assets` folder + `Javelin` DLL
- `PaksList.lst` — manifest of 127 PAK files
- `NewWorldLauncher.exe` — 3.7 MB (we skip this)
- `shaderlist_pc.txt` — 24 MB

Inside `assets/`: 127 PAK files, mostly 1 GB each:
- `DataStrm.pak` + 52 parts (most of the world data)
- `VegetationStrm.pak` + 4 parts
- `SharedDataStrm` parts (some 1.2 GB, others 4 KB stubs)
- `CoatlicueStrm.pak` (233 MB — the world / map data)
- `shadersbin_d3d12.pak` (1.4 GB)
- `localization/` (2 GB)
- `shadercachestartup.pak` (516 KB)

**Verdict:** can't determine the minimum-loading subset from static
inspection. The launcher reads `PaksList.lst` and expects all 127
PAKs to exist (validates against the manifest). Whether they're
eagerly loaded vs lazy-loaded is an engine implementation detail
that needs runtime testing.

**Recommendation:** for first attempt at Phase F, copy the full
71 GB. Once a working baseline is established (game launches +
fires SelfIdent handler), an experiment can subtract individual
PAKs and observe what breaks. That's a cheap iteration once a
working baseline exists.

**Why this matters minimally:** the 30–60 min transfer cost is
real but one-time. Optimizing for a minimum subset first is
optimization without a baseline — likely to spend more wall-clock
time debugging "missing PAK" errors than the transfer would have
cost.

**Phase status update:**

- Phase B: ✅ done (ISO downloaded)
- Phase C: in progress (UEFI shell hiccup resolved with manual
  `BOOTAA64.EFI` invocation)
- Phase D: in progress (Windows install)

**Next** (queue):
- Wait on maintainer's Phase D/E progress.
- When Phase F starts, the full-transfer recommendation stands
  unless they choose otherwise.

**Blockers:** None.

---

### 2026-05-07 — wake 41: VM-host-IP helper added; Phase G IP made concrete

**Did:**
- Inspected the host's network interfaces. Confirmed UTM's default
  Shared Network bridge is `bridge100` with the host at
  `192.168.64.1` (subnet `192.168.64.0/24`).
- Wrote `tools/show_vm_host_ip.sh` — a small helper that auto-detects
  the right bridge interface and prints the host's IP as seen from
  a UTM VM. Verified: outputs `192.168.64.1`.
- Updated `analysis/proposed_patches/vm_setup_steps.md` Phase G
  "Find the Mac's IP" subsection to reference the helper script and
  use the verified IP rather than "typically 192.168.64.1."

**Why:**

When the maintainer reaches Phase G, they need the host IP for two
flags: `auth_mock.py --rep-host` and `setup_hosts.py --target-ip`.
The original doc said "typically 192.168.64.1" — fine for guidance,
not great for automation. The helper script removes the manual
detection step and works regardless of UTM version (auto-finds the
bridge by inspecting interface names + RFC1918 IPs).

The script is also useful in shell pipelines, e.g.:

```bash
sudo python -m server.auth_mock --port 443 \
    --rep-host "$(tools/show_vm_host_ip.sh)" --rep-port 24083
```

**Status:**

VM setup phase board:
- A ✅ UTM was already installed
- B ✅ Windows ARM64 ISO downloaded
- C in progress (got past the UEFI shell hiccup)
- D in progress (Windows install)
- E pending (Steam, Python, Frida)
- F pending (game directory transfer, ~71 GB)
- G pending (networking — host IP now scripted at
  `tools/show_vm_host_ip.sh`)
- H pending (run NewWorld via Frida)

**Next** (queue):
- Wait on Phase D / E progress.
- Could write the same kind of helper for "IP that auth_mock should
  bind to" if needed, but `0.0.0.0` is fine.

**Blockers:** None.

---

### 2026-05-07 — wake 42: pre-flight sanity checks for VM Phase H

**Did:**
- Inspected `tools/client-hooks/frida_capture.py` for hardcoded
  paths that would break in the VM environment.
- Inspected `tools/client-hooks/frida_dtls_trust_patch.js` for
  hardcoded RVAs that depend on a specific binary build version.

**Found — no action needed:**

`frida_capture.py` is already VM-friendly:
- Default `GAME_EXE` =
  `C:\Program Files (x86)\Steam\steamapps\common\New World\Bin64\NewWorld.exe`
  (line 54-57)
- Override via `--exe` CLI flag (line 331) — this is what the
  VM scenario uses, pointing at `C:\NewWorldArchive\Bin64\NewWorld.exe`
- Override via `NW_GAME_EXE` env var as alternative

`frida_dtls_trust_patch.js` hardcodes `RVA_SECURE_INIT = 0x5dce750`
(= `FUN_145dce750` = `Javelin_SecureSocketDriver_Initialize`).
This RVA matches the binary we downloaded via SteamCMD on
2026-05-06 — verified during today's static-RE work which
identified `FUN_145dce750` at the same offset.

**Conclusion:** existing tools work as-is for the VM scenario
when pointed at the SteamCMD-downloaded game directory. No script
modifications needed for Phase H.

**The only realistic risk** is if the VM somehow ends up running
a *different* build of NewWorld.exe than what we have on disk
(e.g., via Steam-in-VM auto-updating it). Mitigation: don't let
Steam-in-VM update the game; we explicitly point Frida at our
copy under `C:\NewWorldArchive\` rather than at any
Steam-managed install path. The doc already says this.

**Why this matters:**

The trust-patch is the load-bearing piece of the existing
runtime instrumentation. If its hardcoded RVA missed, cert
pinning wouldn't be bypassed and the client would refuse our
self-signed cert. Confirming the RVA matches before Phase H
runs eliminates one class of "why isn't it working" debugging.

**Next** (queue):
- Wait on Phase D / E / F progress.
- Could write a Phase E one-liner script (Python + Frida install
  via winget + pip in PowerShell) but it's small enough that the
  doc commands suffice.

**Blockers:** None.

---

### 2026-05-07 — wake 43: Phase G one-shot launcher script

**Did:**
- Wrote `tools/serve_for_vm.sh` — auto-detects the VM-side IP via
  `show_vm_host_ip.sh`, launches both `auth_mock.py` and
  `rep_responder.py` with the correct flags (auth_mock with
  `--rep-host` set to the VM-side IP), traps SIGINT for clean
  shutdown of both PIDs.
- Updated Phase G in `vm_setup_steps.md` to recommend the
  one-shot launcher with the manual two-terminal flow as
  fallback.

**Why:**

The maintainer reported finishing UTM Windows install. Phase E
(Steam + Python + Frida) is in flight; Phase G (networking) comes
right after Phase F. Pre-staging the launcher means when they
hit Phase G, they run one command instead of remembering the
flag combo.

**Script accepts:**

- `--no-auth` — skip auth_mock (e.g. for re-using one already
  running)
- `--no-rep` — skip rep_responder
- `--auth-port`, `--rep-port` — override defaults
- `--help` — usage extracted from the comment block

Verified `--help` runs without launching.

**Status:**

VM phase board:
- A ✅ UTM was already installed
- B ✅ Windows ARM64 ISO downloaded
- C ✅ VM created (UEFI shell hiccup → manual BOOTAA64.EFI worked)
- D ✅ Windows installed
- E in progress — Steam + Python 3.11 (x64) + Frida + UTM Tools
- F pending — game directory transfer (~71 GB)
- G pending — `tools/serve_for_vm.sh` ready to go
- H pending — `frida_capture.py --exe ...` against
  `C:\NewWorldArchive\Bin64\NewWorld.exe`

**Next:**

Wait on maintainer's Phase E progress. When they're ready for
Phase F, the doc covers shared-folder vs external-drive
options. Phase G is now one command away once F is done.

**Blockers:** None.

---

### 2026-05-07 — wake 44: SSH access into VM established; Phase F approach pivots to run-direct-from-share

**Did:**

- Maintainer enabled OpenSSH server in the VM, added our public
  key to `C:\ProgramData\ssh\administrators_authorized_keys`
  (Windows-OpenSSH-specific override required for admin accounts),
  and shared user/IP. SSH from the Mac to the VM now works
  end-to-end with PowerShell-via-stdin scripting.
- Cloned `first-light` into `C:\first-light` on branch
  `claude/vacation-2026-05-06`. Repo now lives in the VM with
  all 51+ commits ready for Phase G/H tooling.
- Probed shared-folder mount, dependency installs, and disk space.

**Found:**

1. **The shared folder shows up as `Z:\`, not `\\Mac\Home\...`.**
   UTM uses SPICE WebDAV (`\\localhost@9843\DavWWWRoot`) which
   gets auto-mapped to drive `Z:`. The `\\Mac\Home\` path the
   docs cited is Parallels/VMware terminology and doesn't apply.
   `Z:\Bin64\NewWorld.exe`, `Z:\assets\`, etc. are all directly
   readable from the VM.

2. **Disk-space constraint blocks the planned full robocopy.**
   The 100 GB VM has only ~69 GB free after Windows install +
   dependencies; the game directory is ~71 GB (assets/ alone is
   70.85 GB). The full copy from the Phase F doc would have
   failed with "disk full" partway through.

3. **Subdirectory sizes:**
   - `assets/`: 70.85 GB
   - `Bin64/`: 268 MB
   - `_CommonRedist/`: 136 MB
   - `EasyAntiCheat/`: 35 MB
   - root files (engine.json, bootstrap.cfg, etc.): tiny

4. **VM environment:**
   - Python 3.11.9 ✓ (x64)
   - Frida 17.9.6 ✓
   - Git 2.54.0.windows.1 ✓
   - Steam process running ✓
   - SPICE WebDAV daemon running ✓
   - UTM Guest Tools mounted but not installed — not blocking
     anything since the share already works via spice-webdavd

**Action — `vm_setup_steps.md` rewritten for Phase F:**

Three options documented, ordered by friction:

- **F-0 (recommended first try)**: run NewWorld directly from
  `Z:\Bin64\NewWorld.exe` via Frida — zero copy, zero disk used.
  Risk: SPICE WebDAV is slow for asset PAK reads.
- **F-1 (full copy)**: documented but flagged "won't fit on a
  100 GB VM."
- **F-2 (hybrid)**: copy `Bin64/`, `EasyAntiCheat/`,
  `_CommonRedist/`, root files locally (~430 MB), then
  `mklink /D C:\NewWorldArchive\assets Z:\assets`. Fallback if
  F-0 fails because Steam objects to non-local game dir.
- **F-3 (external drive)**: kept but renumbered.

Phase H example command updated to default to the F-0 path.

**Why this matters:**

1. The VM is now remotely drivable. Future loop iterations can
   execute `frida_capture.py` and read `capture/<timestamp>/`
   results without the maintainer at the keyboard.
2. Phase F goes from "30–60 min wait" to "0 min" — direct from
   share is the new fast path.
3. Disk-full failure caught before the copy ran.

**Next** (queue, in priority order):

1. Phase G client-side: `python tools\setup_hosts.py` in the VM
   to redirect Amazon hostnames to 192.168.64.1.
2. Phase G host-side: `tools/serve_for_vm.sh` on the Mac. This
   is sudo + foreground, so it likely needs an explicit
   maintainer ack or a backgroundable variant.
3. Phase H smoke test: `frida_capture.py --exe Z:\Bin64\NewWorld.exe`
   with the SelfIdent diagnostic hook. Read results back.
4. Resolve V3-retry hypothesis tree from the captured trace.

**Blockers:**

`tools/serve_for_vm.sh` runs auth_mock with sudo (port 443) —
not autonomously startable. Maintainer needs to launch the
host-side servers OR auth_mock could move to a non-privileged
port with the VM's hosts file doing redirection. Latter is a
small follow-up if the simple path is too friction-heavy.

---

### 2026-05-07 — wake 45: First end-to-end smoke test — game launches, all hooks load, GPU detection is the blocker

**Did:**

1. Resized VM partition (dropped recovery part #4, extended C: to 119.79 GB).
2. Established the Phase F pivot we couldn't predict from desk research:
   **SPICE WebDAV (drive Z:) silently truncates reads on files >100 MB**
   with `ERROR 223 (0x000000DF)`. NewWorld.exe (171 MB) and 76 asset PAKs
   (70.67 GB total) are unreadable through the share. Z: is unusable for
   the actual game data.
3. Pushed full game directory (~71 GB) from Mac to VM via SCP through
   the existing SSH channel. Throughput ~95 MB/s; total ~12 minutes.
4. Refactored `tools/serve_for_vm.sh` for unprivileged operation
   (auth_mock on :4443, no sudo) and wrote `tools/setup_vm_portproxy.ps1`
   to forward 127.0.0.1:443 → MAC_IP:4443 inside the VM via
   `netsh interface portproxy`. This unblocks autonomous Phase G.
5. Set up the VM client side end-to-end:
   - Trusted regenerated `newworld_ca.crt` in `Cert:\LocalMachine\Root`
     (`certutil -addstore`).
   - Ran `setup_hosts.py --apply --target 127.0.0.1` (28 hostnames
     redirected).
   - Ran `setup_vm_portproxy.ps1` (proxy installed, verified).
   - Verified reachability: `Test-NetConnection 127.0.0.1 :443 = True`,
     `Test-NetConnection 192.168.64.1 :4443 = True`.
6. Started auth_mock + rep_responder on Mac (background, unprivileged).
7. **Ran the smoke test** with 240s hard timeout, aggressive process
   kill, full log capture.

**Found — the test outcome:**

- ✅ **Frida spawn worked** — `frida.spawn(C:\NewWorldArchive\Bin64\NewWorld.exe)`
  succeeded; PID 8316 spawned suspended, attached, resumed.
- ✅ **DTLS trust patch loaded at the expected RVA**:
  `secure_init=0x7ff75f4ae750` = base `0x7ff7596e0000` + `0x5dce750`,
  exactly matching `frida_dtls_trust_patch.js`'s hardcoded RVA. This
  validates that the binary in the VM (downloaded via SteamCMD on the
  Mac on 2026-05-06) is the same build the existing tooling targets.
- ✅ **All 12 internal_* hooks installed** — every static-RE finding
  from earlier wakes (`internal_rep_secure_init`, `internal_gameconn_state`,
  `internal_carrier_send_sysmsg`, `internal_gridmate_destroy`, etc.)
  resolved to the right address and hooked successfully.
- ✅ **All RVA-validate stamps matched** — including the FUN_146b6f190
  ready_setter "[KNOWN]" tag.
- ✅ **Steam initialized**: `[steam] SteamAPI_Init -> 0` (success).
- ✅ **ConnectEx + DisconnectEx hooked dynamically** via SIO_GET_EXTENSION_FUNCTION_POINTER.
- ❌ **Game terminated at GPU detection** before reaching network init:
  ```
  [ui] MessageBoxW caption=AZoth text=Your graphics card does not
       support all the DirectX 12 features we require. Falling back
       to DirectX 11.
  [ui] MessageBoxW caption=AZoth text=Unsupported video card detected!
       Continuing to run might lead to unexpected results or crashes.
       Please check the manual for further information on hardware
       requirements.

  "" [vendor id = 0x0000, device id = 0x0000]
  [!] Session detached: process-terminated
  ```
- 0 packets captured. Game exited ~76 seconds after launch (most of
  that on Frida hook installation, then Steam init at 22:13:42, then
  GPU MessageBoxes at 22:13:44, then process-terminated at 22:13:44.485).

**Why the GPU check fails:**

UTM uses `virtio-gpu` for graphics virtualization. virtio-gpu doesn't
expose a real DXGI adapter with valid Vendor ID / Device ID; the
game's DXGI enumeration returns blanks. The first MessageBox warns
about DX12 fallback, the second warns about an unsupported card,
and after both auto-dismiss the game calls its own self-termination
path (we see `TerminateProcess` was hooked; the game uses it to
exit cleanly).

This matches the FAQ's prediction (`vm_setup_faq.md`,
"Q: Will Microsoft Prism actually run NewWorld.exe?"): GPU
virtualization quality was the #1 listed risk. The 40-60% estimate
for "starts and reaches network init under UTM" landed on the low
end.

**Why this is still a huge result:**

The infrastructure is *fully proven*:

- SSH-driven VM control loop (we ran a full E2E test autonomously
  while the maintainer was asleep)
- Full game directory transfer via SCP works (12 min, 95 MB/s)
- Frida spawn + attach + script load on x64 NewWorld.exe under
  Microsoft Prism on Apple Silicon — confirmed working
- All 25+ Frida hooks load successfully — validates the entire
  pipeline of static-RE → RVA hardcoding → runtime instrumentation
- Mac-side server stack (auth_mock + rep_responder) reachable from
  VM via portproxy chain
- All cert/hosts plumbing works

**What now blocks**: pure GPU adapter spoofing. Three paths:

1. **Frida hook on DXGI adapter enumeration / `IDXGIAdapter::GetDesc`**
   to return fake VendorId/DeviceId values. Effort: medium — needs
   to find the COM vtable slots and patch them. The game then thinks
   it has a real GPU and continues.
2. **Find and bypass the "GPU-not-supported -> exit" code path in
   NewWorld.exe with a Frida hook.** Effort: small if we can identify
   the function quickly via static-RE; the game probably has a
   `void CheckGPU()` that aborts on bad descriptors.
3. **Switch to Parallels Desktop** — FAQ flagged as the obvious
   fallback; better D3D virtualization and DXGI exposure.

**Next** (queue):

1. Static-RE hunt for the GPU-validation function in NewWorld.exe.
   Searches: cross-references to "Unsupported video card detected"
   string, `IDXGIAdapter::GetDesc` callers, `D3D11CreateDevice`
   callers, the abort path that follows the second MessageBox.
2. Once identified, write a Frida hook to either: (a) lie to the
   GPU-info getter, or (b) skip the abort.
3. Re-run the smoke test with the new hook; observe how far the
   game gets.

If GPU spoofing turns out to be too deep a rabbit hole or the
hook can't get past the issue, the queue's escalation is Parallels
Desktop trial + retest. Both paths preserve the rest of the
infrastructure built tonight.

**Blockers:**

GPU virtualization. The Frida hook attempt is the next iteration's
focused work.

**Audit trail (this session's commits):**

- `8a2ad15` — tools(vm): unprivileged-mode serve_for_vm.sh + setup_vm_portproxy.ps1
- (this commit) — wake 45 worklog + Phase F doc fix for the WebDAV size cap

**Capture artifact:**

`C:\first-light\capture\20260507_221218_vm_smoke_001\` in the VM
contains:
- `session.log` (13.5 KB) — every hook installation + UI events
- `hooks.log` (4.3 KB) — pass/fail summary of every hook attempt
- `packets.jsonl` (0 bytes) — empty, expected since game terminated
  before network init

---

### 2026-05-07 — wake 46: GPU validation function identified, hooked, succeeds — but game still dies in a silent exit path

**Did:**

1. Static-RE: located the "Unsupported video card detected" string at
   `0x1485e5d10` via a new wide-string xref helper
   (`tools/ghidra_scripts/FindWideStringXrefs.py` — companion to
   FindStringXrefs.py for UTF-16LE strings, which Win32 *W APIs use).
   Single xref, from `0x147143d2b` inside FUN_147143960.
2. Decompiled FUN_147143960 (RVA 0x7143960). Found the gate:
   ```
   iVar3 = MessageBoxW((HWND)0, text, L"AZoth", 0x20131);
   if (iVar3 == 2) { /* "User chose to cancel" */ return 0; }
   ```
   `0x20131 = MB_OKCANCEL | MB_ICONWARNING | MB_DEFBUTTON2 | MB_SYSTEMMODAL`,
   so Cancel is the default button.
3. Wrote `tools/client-hooks/frida_gpu_spoof.js` with two layered hooks:
   (a) MessageBoxW interceptor forcing IDOK=1 on AZoth-captioned
       dialogs;
   (b) FUN_147143960 onLeave forcing retval=1 even on internal failure
       (in case render-module init was the actual gate).
4. Wired up `frida_capture.py --gpu-spoof` flag (default OFF; physical
   hosts don't need it).
5. Ran four smoke iterations (`vm_smoke_002` through `vm_smoke_006`),
   each diagnosing and fixing a layer.

**Found — three Frida 17 / pipeline bugs caught in sequence:**

- `Module.findExportByName` is gone in Frida 17. Other scripts in this
  repo use `Module.getExportByName`. (caught vm_smoke_002)
- Even `Module.getExportByName(string, string)` static form throws
  "TypeError: not a function" in Frida 17. The working form is
  `Process.getModuleByName("user32.dll").findExportByName("MessageBoxW")`
  — i.e. the per-module instance method. The main hook gets away with
  the static form because it always uses an IAT-walking primary path
  with the static form as fallback inside try/catch. (caught vm_smoke_004)
- `console.log` from a Frida script doesn't reach
  `frida_capture.py`'s on_message handler (which only routes
  `message["type"] == "send"`). Other hook scripts use a
  `send({type:"log",text:...})` helper. Without this, the gpu_spoof
  hook was running but its diagnostic logs never appeared in
  session.log. (caught vm_smoke_003 → vm_smoke_004)

**Found — the actual GPU dynamics:**

- The first MessageBoxW (DX12 fallback warning) is `uType=0x20030`
  = `MB_OK | MB_ICONWARNING | MB_SYSTEMMODAL` — informational only,
  always returns IDOK=1. Not a gate.
- The second MessageBoxW (Unsupported video card) is `uType=0x20131`
  with MB_DEFBUTTON2 = Cancel default. **But Frida's hook
  side-effect on Windows-ARM64-Prism causes both dialogs to
  auto-return IDOK=1** before our hook can intervene. So MB_DEFBUTTON2
  isn't actually the gate in this environment.
- FUN_147143960 (the GPU-validation function) **returns 1 (success)
  naturally** — even with VendorId=0, DeviceId=0, render-module init
  apparently completes (or is skipped via the
  `if (param_2 != 5) goto LAB_147143f23` path).
- Despite GPU-validate succeeding, **the game terminates ~332 ms
  later in a silent path** that none of our hooked exits
  (TerminateProcess, abort, RaiseFailFastException, RtlExitUserProcess,
  ExitProcess) intercept. The session.log has no events between
  `FUN_147143960 returned 1` and `[!] Session detached: process-terminated`.

**Conclusion:**

The MessageBoxW dialog is a red herring. The real abort is downstream
of FUN_147143960. Most likely candidates for the silent exit path:

1. **Access violation in subsequent renderer code.** Once GPU-validate
   returns 1, the engine assumes a working renderer exists and
   dereferences something that's null — Windows kills the process
   without going through any hooked exit.
2. **`NtTerminateProcess` directly via syscall**, bypassing the
   `kernel32!TerminateProcess` wrapper we hooked. (TerminateProcess
   is hooked successfully but never fires.)
3. **An SEH / VEH unhandled-exception filter** that Windows handles
   internally.

**Three commits this iteration:**

- `018d286` — initial gpu_spoof hook + FindWideStringXrefs.py
- `85a2a0b` — Frida 17 fix (`getExportByName`)
- `e3a93de` — `send({type:"log",...})` for Frida-routed logging
- `30db860` — `Process.getModuleByName(...).findExportByName(...)` form
- `bdaa0ef` — layered hook on FUN_147143960 onLeave forcing retval=1

The hook itself is sound. The remaining problem is identifying the
silent exit path so we can hook *that* too — or, alternatively,
finding the upstream code that triggers the bad post-validate
behavior and short-circuiting it earlier.

**Next** (queue, in priority order):

1. Hook `ntdll!NtTerminateProcess` (low-level syscall stub — catches
   any TerminateProcess flavor including direct syscall use). Also
   hook `RaiseException`, `RtlRaiseStatus`, `KiUserExceptionDispatcher`
   to catch hardware-exception driven exits.
2. Once the silent exit path is hooked, the stack trace at the call
   site identifies which engine subsystem is the actual abort source.
3. From there, decide: short-circuit that path with a higher-level
   hook, or pivot to a different host (Parallels Desktop's better
   D3D virtualization may make all of this moot).

**Time-wise**: this was the first wake to do real iterative
debugging on a runtime hook — three pipeline bugs caught and fixed.
Each smoke run is ~70s wall-clock with the 90s timeout cap, so the
fix-test loop is fast enough to iterate productively.

**Blockers:**

The silent exit is the new blocker; the GPU dialog isn't (it always
returned IDOK in our environment). Next wake's task is to identify
where the silent exit originates and either hook around it or make
a hardware-host pivot decision.

---

### 2026-05-07 — wake 47: silent abort identified — access-violation-equivalent in a vtable callback during GPU/scene init

**Did:**

1. Wrote `tools/client-hooks/frida_exit_trap.js` — hooks every plausible
   exit/abort entry point (NtTerminateProcess, RtlExitUserProcess,
   ZwTerminateProcess, KiUserExceptionDispatcher, RtlDispatchException,
   UnhandledExceptionFilter (KernelBase + kernel32), RaiseException,
   abort, _exit, exit, _CxxThrowException) and dumps a 32-frame
   backtrace via `Thread.backtrace` + `DebugSymbol.fromAddress` when
   any of them fires.
2. Special-cased KiUserExceptionDispatcher: reads EXCEPTION_RECORD via
   rcx (x64 ABI for the dispatcher) and CONTEXT.Rip via rdx+0xf8.
3. Wired a `--exit-trap` flag into `frida_capture.py`.
4. Re-ran smoke test (vm_smoke_007 / vm_smoke_008) with both
   `--gpu-spoof` and `--exit-trap`.

**Found — the silent exit path:**

```
EXCEPTION code=0xc00000aa flags=0x0
addr=0x7ff7607b11b5 (NewWorld.exe +0x10d11b5)
CONTEXT.Rip = 0x7ff7607b11b5
```

- Exception code `0xc00000aa` (raised through KiUserExceptionDispatcher)
- Faulting RIP at `RVA 0x10d11b5`, which lives at offset `0x95` inside
  function `FUN_1410d1120` (Ghidra address `0x1410d1120`).
- Frida's `DebugSymbol.fromAddress` picked the closest exported symbol
  (`AK::WriteBytesBuffer::Clear`) which is **misleading** — the exported
  symbol is the nearest *named* thing in the address space; the actual
  function `FUN_1410d1120` is unnamed.

**Decompiling FUN_1410d1120** (the actual crash site) shows it's a
spatial/scene query routine:

- Takes `param_1` (some scene-graph/manager struct), `param_2` (4D
  vector / AABB), `param_3` (output struct).
- Computes `param_2[4] - *param_2` (AABB extent), uses `rcpps` and
  `movmskps` (SIMD math).
- Walks pointer chains: `*(param_1+0x40) -> +0x30`, `lVar10+200`,
  `lVar10+0x88`, etc.
- Calls FUN_1414186c0 / FUN_1414190a0 (likely AABB-vs-grid or
  ray-vs-grid intersection helpers).
- The crash at offset 0x95 happens during one of those pointer chases
  — likely a NULL dereference where one of the chained pointers is
  uninitialized.

**Xref to FUN_1410d1120:** referenced as DATA from `0x147fdba28` —
that's a **vtable / function-pointer table entry**, not a direct call.
So the function is invoked indirectly through some object's vtable as
a virtual method or callback. The caller can't be statically
identified from this xref alone; needs either a Frida hook on
FUN_1410d1120 itself to capture the call stack at runtime, or a
broader caller-tree search starting from likely renderer/scene init
functions.

**Earlier C++ throws (caught) before the fatal exception:**

Three `KernelBase!RaiseException` events with code `0xe06d7363` (the
MS C++ exception magic, "msc\0" + 'E') fire before the access
violation. FUZZY backtrace shows frames at:
- frame 0: 0x7fffbb379a3c (in some library, near `isatty`)
- frame 10: 0x7fffbf4c81a4 (in ntdll, RtlRaiseException)

These look like cleanly-thrown-and-caught C++ exceptions — probably
`std::runtime_error` or similar inside the engine's GPU/audio/scene
enumeration code. They're not the root cause; the access violation
is.

**Why this matters:**

The crash isn't in an obviously-GPU function. It's in scene-graph /
spatial-query code that depends on some upstream subsystem (likely
either the renderer or another engine module that wasn't fully
initialized because of the GPU situation). Cascading failure pattern
is consistent with the broader picture: virtio-gpu's empty
VendorId/DeviceId leaves engine subsystems in a half-initialized
state, and the first one to dereference a stale pointer crashes.

**Strategic decision point — queued for maintainer:**

The Frida-based bypass is becoming a long tail. Each "fix" reveals
another cascading failure:

- wake 45: GPU MessageBox cancel path — fixed
- wake 46: FUN_147143960 retval — wasn't actually the gate
- wake 47: scene-graph FUN_1410d1120 access violation — current
- (likely future): every other engine subsystem that touches the
  broken GPU state

Two paths forward:

1. **Continue Frida bypass.** Keep adding hooks. Estimated 3-6 more
   wakes to reach network init, with no guarantee any of them
   succeed (some may need real GPU memory / textures).

2. **Pivot to Parallels Desktop.** $100/yr (free trial first), much
   better D3D virtualization. From the FAQ: "Game starts and reaches
   network init under Parallels: 80%+". Probably 1-2 wakes to set
   up the alternate VM, then a single smoke test that should clear
   all of these issues at once.

Recommendation: **Parallels.** The Frida bypass path is becoming a
yak-shave; even if we get past this crash, there'll be others
upstream of network init. Parallels' real D3D11 device should make
all of these issues go away simultaneously.

**Files this iteration:**

- `tools/client-hooks/frida_exit_trap.js` (new) — exit/exception
  catcher with EXCEPTION_RECORD decoding
- `tools/client-hooks/frida_capture.py` — `--exit-trap` flag wiring
- This worklog entry

**Commits:**

- `328d200` — initial frida_exit_trap.js
- `10458a1` — read EXCEPTION_RECORD + faulting RIP

**Next** (queue, in priority order):

1. **Decision pending from maintainer:** Frida bypass vs Parallels.
   Default if no answer: try one more Frida iteration (hook
   FUN_1410d1120 onEnter to identify the caller via stack trace),
   then if that doesn't break the loop, pivot to documenting the
   Parallels setup as a structured proposal.

2. **If Frida bypass:** hook FUN_1410d1120 entry to grab the call
   stack at the moment of crash. The 9 hidden frames between
   exception dispatcher and frame 10 contain the answer.

3. **If Parallels:** new doc `analysis/proposed_patches/parallels_setup.md`
   walking through trial install, Windows VM creation, and the
   minimal-friction path to reusing the existing infrastructure
   (SCP, hooks, Phase G, etc.).

**Blockers:**

Waiting on strategic direction (Frida vs Parallels). Current Frida
path is producing diagnostic info but no resolution; each iteration
narrows the cause but adds another hook to write.
