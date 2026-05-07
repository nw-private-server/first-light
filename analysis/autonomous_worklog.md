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
