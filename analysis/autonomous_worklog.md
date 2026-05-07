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
- [x] **A2.6.** Trace xrefs to `FUN_145a87010` to find what *invokes* the
      ConnectionSuccess handler. **DONE 2026-05-07** — `FUN_146454c00` is
      the `PlayerManagerSelfIdentification` message handler; it
      unconditionally calls `FUN_145a87010` on success. RTTI string at
      `0x14a153fd0` gives us the C++ type:
      `Javelin::ClientMessagesTrait::PlayerManagerSelfIdentificationMsg`.
- [ ] **A2.7.** Cross-reference the literal `"ConnectionSuccess"` string in
      the binary — there may be other Connection lifecycle handlers
      (`ConnectionFailed`, `ConnectionClosed`, etc.) that share the same
      registration mechanism. Mapping the full event table will tell us
      what flavor of message we need to send.
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
