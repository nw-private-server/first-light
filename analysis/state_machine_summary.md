# GameConnection State Machine — Synthesis (2026-05-07)

> Consolidates findings A1–A3 from the autonomous worklog
> ([`analysis/autonomous_worklog_through_253.md`](autonomous_worklog_through_253.md)
> — wake-261 archive split; wakes 254+ in active
> `autonomous_worklog.md`; branch `claude/vacation-2026-05-06`).
> Captures the post-V3 protocol picture in one place so the
> maintainer doesn't have to re-derive it from nine wake entries.
>
> All addresses are virtual (image base `0x140000000`) on the live
> Steam build downloaded 2026-05-06. RVAs in older Ghidra notes were
> derived from a non-EAC build — they may not match this binary
> exactly, so verify before reusing.

---

## TL;DR

After the V3 RegistrationResponse is accepted (already working — prior
project notes confirmed `rep.ready` flips 0→1), the client sits in
**GameConnection state 10** waiting on a single message the server is
**not** sending:

> **`Javelin::ClientMessagesTrait::PlayerManagerSelfIdentificationMsg`**

Without it, an internal client-side timer eventually dispatches event
`0xFE476177` to the GridMate Carrier, which sets a "skip-timeout, flush
queue" flag and the session is torn down ~30s after V3.

**The server's missing job** is delivering one
`PlayerManagerSelfIdentificationMsg` between accepting V3 and the
client's destroy timer firing. Wire format is partially known
(handler-side struct shape) but the byte-level layout still requires a
runtime hook (queued for the maintainer).

---

## 1. The state machine

The state machine lives in `FUN_14644a070` (the `gameconn_state`
function flagged in `docs/next-session.md`). It's a switch over
`gc[+0x1530]` (the int state field on the GameConnection) with cases
3–14.

The **state-name table** at `0x1484f9ff0` (recovered via the log
expression `(&PTR_s_Disconnected_1484f9ff0)[gc[+0x1530]]`):

| Value | Name |
|---|---|
| 0 | `Disconnected` |
| 1 | `QueryGameUpdateCheck` |
| 2 | `WaitingForGameUpdateCheck` |
| 3 | `QueueGameLogin` |
| 4 | `WaitingForQueuedLogin` |
| 5 | `QueryForRemoteConfigClass` |
| 6 | `WaitingForRemoteConfigClass` |
| 7 | `ObtainREPRequirements` |
| 8 | `WaitingForREPRequirements` |
| 9 | `StartREPConnection` |
| 10 | `WaitingForREPConnection` |
| 11 | `WaitingForActorGameConnection` |
| 12 | `WaitingForSpawnPoint` |
| 13 | `WaitingForPlayerSpawn` |
| 14 | `InGame` |

So the project's blocker is state `WaitingForREPConnection` →
`WaitingForActorGameConnection`, and the post-V3 ladder is
`WaitingForActorGameConnection` → `WaitingForSpawnPoint` →
`WaitingForPlayerSpawn` → `InGame`.

**Two state-setter functions exist**:

- `FUN_14645fd70(gc, newState)` — the low-level setter, writes
  `gc[+0x1530] = newState`.
- `FUN_146466650(gc, newState)` — the **public wrapper** that logs
  `"Update state %s to new state %s"` then calls the low-level
  setter. Most code uses this one for the logging.

Distinct callers of the low-level setter (4): `FUN_14644a070` (the
state machine), `FUN_146446800` (LevelInfoChanged handler — see § 4
below), `FUN_14642d2d0` (Disconnected helper), `FUN_146466650`
(public wrapper). Distinct callers of the wrapper (5): adds
`FUN_146425cb0`, `FUN_14642d950`, `FUN_14645ca20`, `FUN_146468370`
to the set, plus `FUN_14644a070` again.

States 10→11→12→13→14 form the player-spawn ladder. Each transition is
gated by a different read on the **`GameConnectionWrapper`** sub-object
at `gc + 0x130`:

| Transition | Predicate (Ghidra) | What it actually checks | Trigger / writer |
|---|---|---|---|
| 10 → 11 (`WaitingForREPConnection` → `WaitingForActorGameConnection`) | `FUN_145a92370(wrapper)` | `*(int *)(wrapper + 0xa0) == 2` | `PlayerManagerSelfIdentificationMsg` (§ 3) |
| 11 → 12 (`WaitingForActorGameConnection` → `WaitingForSpawnPoint`) | `FUN_145a92380(wrapper)` (inverted) | `*(int *)(wrapper + 0xa0) != 0` | auto-fires once 10 → 11 lands |
| 12 → 13 (`WaitingForSpawnPoint` → `WaitingForPlayerSpawn`) | `FUN_145a905c0(wrapper)` | `*(u8 *)(wrapper + 0xbc8) != 0` | **primary**: `LevelInfoChangedMsg` direct force (§ 4); **secondary**: `FUN_14645c660` soft writer (§ 4½) |
| 13 → 14 (`WaitingForPlayerSpawn` → `InGame`) | `FUN_145a923c0(wrapper)` | `*(u8 *)(wrapper + 0x252) != 0` | **writer + trigger chain identified (wakes 247, 249)**: `FUN_142ffbc50` walks `wrapper[+0x1b8..+0x1c0]` and sets gate on predicate match. The 5 callers (wake-249 decomps) are local state-update functions — `FUN_142ff8940` explicitly copies the 0x70-stride collection from an upstream container at `param_2[+0x7d0]` into the wrapper. So the trigger chain is **server replica-creation message → local replica system updates collection → caller fires → gate opens if predicate matches**. Likely `NewProxy` or equivalent GridMate replica command. See [`state_13_14_writer_investigation.md`](state_13_14_writer_investigation.md) for the full trace. |
| any → 0 (`Disconnected`) | direct call from `FUN_14642d2d0` | helper that resets state to 0 | teardown helper |

The `+0xa0` int on the wrapper is a substate field with three known
values:

```
0 = uninitialized / failed   (triggers destroy if state >= 11)
1 = in-progress              (set by FUN_145a905d0 on state-10 entry)
2 = ready                    (advances state 10 → 11)
```

So `FUN_14644a070` polls `wrapper[+0xa0]` each tick; when it sees 2,
it advances. There's only one writer of `wrapper[+0xa0] = 2` in the
binary.

## 2. The substate=2 writer = `onConnectionSuccess`

`FUN_145a87010` is the wrapper's `onConnectionSuccess` handler:

```c
void FUN_145a87010(GameConnectionWrapper *this) {
    log("CJavelinActorGame", severity=3, ...);
    log("ConnectionSuccess");                 // smoking-gun literal
    /* iterate observer collection at this->[0xc..0xd], emit events */
    *(int *)(this + 0xa0) = 2;                // <-- the gate write
}
```

The `"ConnectionSuccess"` string literal is what tied it to the
lifecycle event semantically. The function itself has only two refs:
this single direct call from `FUN_146454c00` (the message handler in
the next section), and a vtable entry at `0x14ab72930`.

## 3. The single direct caller = `PlayerManagerSelfIdentification`

`FUN_146454c00` is the **`PlayerManagerSelfIdentification` message
handler**. Identification:

1. The function's first action is a structured logger call:
   ```c
   FUN_141721c20("GameMessagePort", "PlayerManagerSelfIdentification");
   ```

2. RTTI string at `0x14a153fd0` confirms the C++ class:
   ```
   .?AV<lambda_1>@?1???$InstallRegistrationHook
       @VPlayerManagerSelfIdentificationMsg
       @ClientMessagesTrait@Javelin@@@Hub@Amazon@@YA_NXZ@
   ```
   So the type is
   `Javelin::ClientMessagesTrait::PlayerManagerSelfIdentificationMsg`,
   registered via `Javelin::Hub::Amazon::...::InstallRegistrationHook<T>`.

3. The handler unconditionally calls `FUN_145a87010(wrapper)` at line
   474 of the decomp on any success path.

**This is a brand-new finding for the project** — `PlayerManagerSelf*`
appears nowhere in `docs/`, `analysis/`, or `info/` prior to the
2026-05-07 autonomous loop.

### What the handler does with the message body

Handler signature:
```c
PlayerManagerSelfIdentification(
  GameConnection *gc,           // param_1
  ?,                            // param_2
  Tuple36 *p3,                  // -> wrapper[+0xaf8..+0xb18] (5 fields:
                                //    8+8+8+8+4 — likely uuid+uuid+int)
  Tuple36 *p4,                  // -> wrapper[+0xb84..+0xba4] (same shape)
  ?,                            // param_5
  MsgBody *p6,                  // 28-byte inline header read into
                                //    gc[-0x7e8..-0x7b4]
  StringPlus17 *p7              // AZStd::string + (8+8+1) tail
);
```

`p6` field map:

| Bytes | Goes to | Likely meaning |
|---|---|---|
| `[0..4]` | `gc[-0x7e8]` | int id / sequence |
| `[8..]` | `gc[-0x7e0]` (via `FUN_1402d13a0`) | sub-struct or handle |
| `[0x50, 1B]` | `gc[-0x7c0]` | debug-virtual-slice flag |
| `[0x58, 8B]` | `gc[-0x7bc]` | long (timestamp / token) |
| `[0x68, 4B]` | `gc[-0x7b4]` | int |

Wrapper setters that consume the message:

- `FUN_145a9fa10(wrapper, p3)` → 36-byte struct copy at `wrapper+0xaf8`
- `FUN_145a9fa30(wrapper, p7)` → AZStd::string copy + 17-byte tail at
  `wrapper+0xb20`
- `FUN_145a9fa80(wrapper, p4)` → 36-byte struct copy at `wrapper+0xb84`

Server-side responsibility: produce all of `p3`, `p4`, `p6`, `p7` with
shapes the client will accept. **Wire-format byte layout (how these
are serialized over DTLS) is not yet known statically** — see § 5.

## 4. The full `ClientMessagesTrait` catalog

The trait registers exactly five `Msg` classes via
`InstallRegistrationHook<T>`. RTTI mangled-name fragments at
`0x14a153xxx` enumerate them:

| Class | Address | Role |
|---|---|---|
| `PlayerManagerSelfIdentificationMsg` | `0x14a153fd0` | Success ladder — advances state 10→11 (and 11→12 auto-fires via inverted `wrapper[+0xa0]` check) |
| `PlayerManagerRejectedMsg`           | `0x14a153db0` | Failure path (handler not yet found) |
| `LevelInfoChangedMsg`                | `0x14a153b20` | Handler = `FUN_146446800` — **directly forces state to 13** (primary 12→13 path) |
| `RemoteConfigChangedMsg`             | `0x14a153890` | Post-registration; **candidate for the soft 12→13 path** (handler is `FUN_14645c660`, sets `wrapper[+0xbc8] = 1` — see § 4½) |
| `DebugCommandResponseMsg`            | `0x14a153610` | Post-registration; also a candidate for § 4½ |

The project's existing `analysis/javelin_chunks.txt` only knew about
`Javelin::BehaviorTreeComponentClientMessages` — `ClientMessagesTrait`
is the broader client message catalog and was previously uncataloged.

The "candidate for soft 12→13 path" note on the last two rows
narrows the **§ 4½** open question: that handler (`FUN_14645c660`)
must be one of the catalogued classes, and `SelfIdent` (10→11) +
`LevelInfoChanged` (12→13 force) are already accounted for. So the
"TBD" message is one of `PlayerManagerRejectedMsg`,
`RemoteConfigChangedMsg`, or `DebugCommandResponseMsg`. A runtime
Frida trace on `FUN_14645c660` resolves it definitively.

For MVP "enter a static world", only `PlayerManagerSelfIdentificationMsg`
is required. `LevelInfoChanged` is required for richer post-spawn
behavior; the other three are optional.

## 4½. State 12 → 13 — second writer path (LevelInfoChanged is the primary)

Per the § 1 predicate table, the state 12 → 13 transition is gated
by `*(u8 *)(wrapper + 0xbc8) != 0`. The § 4 catalog notes
LevelInfoChangedMsg's handler (`FUN_146446800`) **directly forces
state to 13** — that's the primary path. A separate scan
(`FindOffsetWrites 0xbc8 0x1`) found that there is **also a soft
writer** of the gate byte, which sets `wrapper[+0xbc8] = 1` without
force-advancing state. The state machine then advances 12 → 13 on
its next tick via the normal `wrapper[+0xbc8] != 0` predicate.

```
reader: FUN_145a905c0 — returns *(u8 *)(arg + 0xbc8)
writer: FUN_145a9fa00 — *(u8 *)(arg + 0xbc8) = 1
```

The writer has exactly **one xref**: an unconditional call from
`FUN_14645c660 @ 0x14645c660`. That bridge looks up the wrapper
pointer from a global container and passes `wrapper + 0x130` to the
gate writer:

```c
void FUN_14645c660(longlong param_1) {
    longlong lVar1 = FUN_1406d97d0(param_1 + -0x930);
    if (*(longlong *)(DAT_14a7ba0e0 + 0x60) != 0) {
        FUN_145a9fa00(*(longlong *)
                       (*(longlong *)(*(longlong *)(DAT_14a7ba0e0 + 0x60) + 0x1e0) +
                       (longlong)*(int *)(lVar1 + 0x10) * 8) + 0x130);
    }
}
```

`FUN_14645c660` itself has exactly one xref — the dispatch table entry
at `0x14abcc45c`, in the same `ClientMessagesTrait` dispatch table as
`PlayerManagerSelfIdentification` (entry at `0x14abcc15c`, 0x300 bytes
away). So `FUN_14645c660` is **another `ClientMessagesTrait` message
handler** — name not yet recoverable statically because the dispatch
table's metadata column for this row points into `0x140977xxxx`
(different `.rdata` segment from SelfIdent and LevelInfoChanged),
and there's no log-string or RTTI tag near the function entry.

**Open question**: which one of the 5 catalogued ClientMessagesTrait
classes is handled here? `PlayerManagerSelfIdentificationMsg`
(10→11), `LevelInfoChangedMsg` (12→13 force) and the assumed two
post-registration messages (`RemoteConfigChangedMsg`,
`DebugCommandResponseMsg`) are known by RTTI mangled-name fragments
at `0x14a153xxx`. The remaining candidates are
`PlayerManagerRejectedMsg`, `RemoteConfigChangedMsg`, and
`DebugCommandResponseMsg` — runtime Frida hook on `FUN_14645c660`
to log the incoming message body's RTTI tag is the practical
identifier.

**Why this matters**: server-side, this gives an alternative path
to advance state past 12 without sending `LevelInfoChanged`. If
the unknown trait message is small (e.g. a config-change broadcast)
it may be cheaper to synthesize than `LevelInfoChanged`'s full
level descriptor. The complete state-advance chain past gate-2
needs `SelfIdent` (10→11→12, since 11→12 uses inverted substate
predicate on the same `wrapper[+0xa0]` field that 10→11 already
set to 2) and *some* 12→13 trigger (LevelInfoChanged direct-force,
OR this soft-writer + a tick). State 13 → 14 (entering InGame) is
still TBD — `wrapper[+0x252]` is its gate but the writer scan
(`FindOffsetWrites 0x252 0x1`, see worklog A4.2) found no clean
single-writer; that may be a register-based or memcpy write.

The phase-2D + counter-advance infrastructure shipped at wakes
204/208 gets the heartbeat path going; this next-step server-
message sequence is what advances state past 12.

## 5. The destroy mechanism

`FUN_146b3c250` is the **`TransportLayerGridMateTickThread`** (named
via line 116 of its decomp where the thread name is set). It polls
the GridMate Carrier each tick:

```c
do {
    if (*(char *)(carrier + 0xfd) == '\0') {
        if (currentTime <= queueItem.timestamp + delayMs) break;
    }
    processItem();
    uVar15++;
} while (...);
```

So `carrier[+0xfd] != 0` means "skip the timeout check, flush all
queued items immediately" — a pre-shutdown flush flag.

**Sole writer in the entire 32M-instruction binary**: `FUN_140fb3560`
line 452. Only fires on one specific event:

```c
else {
    if (iStack_38 != 0xFE476177) return;
    *(undefined1 *)(carrier + 0xfd) = 1;
}
```

`0xFE476177` is an `AZ::Crc32` of some lifecycle event name, but the
source string was stripped from the binary at compile time (29 hits
of the constant in code, none with adjacent string literals). The
event name can only be recovered via a runtime hook (Frida) or a
debug build.

**Consequence for the project:** the ~30s session destroy is *not*
something the server triggers. It's an **internal client-side timer**.
If `PlayerManagerSelfIdentificationMsg` arrives before the timer
reaches the destroy event, the session lives. If not, it dies.

## 6. End-to-end protocol picture

```
┌────────────────────┐         ┌────────────────────┐
│      CLIENT        │         │      SERVER        │
└────────────────────┘         └────────────────────┘
        │                              │
        │   HTTPS auth (OmniSDK)       │
        │ ◄──────────────────────────► │   ✅ working
        │                              │
        │   DTLS handshake (Javelin)   │
        │ ◄──────────────────────────► │   ✅ working
        │                              │
        │   V3 RegistrationRequest     │
        │ ───────────────────────────► │
        │                              │
        │   V3 RegistrationResponse    │
        │ ◄─────────────────────────── │   ✅ accepted
        │                              │       (rep.ready 0→1,
        │                              │        wrapper substate→1,
        │                              │        gc state stays at 10)
        │                              │
        │                              │
        │   PlayerManagerSelfIdent.Msg │
        │ ◄─────────────────────────── │   ❌ NOT SENT — this is the
        │                              │       gap
        │                              │
        │   ─── ~30s later ───         │
        │   internal: dispatch         │
        │   AZ::Crc32(0xFE476177)      │
        │   to carrier                 │
        │                              │
        │   carrier[+0xfd] = 1         │
        │   → next tick force-flushes  │
        │   → session destroyed        │
        │                              │
```

If the server inserts a `PlayerManagerSelfIdentificationMsg` before the
internal timer fires:

```
        │   PlayerManagerSelfIdent.Msg │
        │ ◄─────────────────────────── │
        │                              │
        │   FUN_146454c00 fires        │
        │   wrapper substate := 2      │
        │   onConnectionSuccess emits  │
        │   "ConnectionSuccess"        │
        │                              │
        │   gc state 10 → 11           │
        │   logs:                      │
        │   "GameConnectionWrapper:    │
        │    actor game connection     │
        │    succeeds"                 │
        │                              │
        │   ─── continues to states    │
        │       12, 13, 14 (spawn) ─── │
```

## 7. What the server needs

To unblock state 10 → 11 (the project's stated MVP goal), the server
must send **one** message after V3 RegistrationResponse:

- **Message type**:
  `Javelin::ClientMessagesTrait::PlayerManagerSelfIdentificationMsg`
- **Required content** (for the client handler to reach the
  `onConnectionSuccess` call): five logical fields fitting the shapes
  in § 3 above.
- **Required wire format**: NOT YET KNOWN STATICALLY. Two ways to find
  it:
  1. **Runtime hook (recommended).** Frida hook on `FUN_146454c00`
     (`0x146454c00`) at entry, dump the seven in-args. ~30 lines in
     the style of `tools/client-hooks/frida_capture.py`. Single
     fastest path. Already queued for the maintainer in the worklog.
  2. **Find the `Reflect()` static.** `PlayerManagerSelfIdentificationMsg`
     is registered via `InstallRegistrationHook<T>`. The class will
     have a `static Reflect(SerializeContext*)` declaring the field
     order and types. Walking from the RTTI vtable might lead to it.
     Harder than the runtime path.
- **Timing constraint**: must arrive before ~30s post-V3 (when the
  internal carrier-destroy timer fires `0xFE476177`).

## 8. Open questions for future iterations

| ID | Question | Status |
|---|---|---|
| A2.7 | Are there sibling lifecycle handlers besides ConnectionSuccess (Failed, Closed, Lost)? | not started |
| A2.9 | What's the dispatch table layout at `0x14abcc15c` that picks `FUN_146454c00`? | partial — static decode hard, runtime is easier |
| A2.10 | Where is `PlayerManagerRejectedMsg` handler? | partial — not on `GameMessagePort` log channel |
| A2.11 | Trace logger (`FUN_141721c20`) xrefs — sibling-of-SelfIdent handler hunt | not started |
| A3.1 | What does `0xFE476177` hash to? | partial — string stripped, runtime needed |
| A4 | Are there *other* writers of `gc[+0x1530]` outside `FUN_14644a070`? | not started |

## 9. Files produced 2026-05-07

Generated by the autonomous loop on branch `claude/vacation-2026-05-06`:

- **Decomps**: `decomp_state_advance_predicate.txt`,
  `decomp_wrapper_state10_*.txt`, `decomp_wrapper_state12_gate.txt`,
  `decomp_wrapper_state13_gate.txt`, `decomp_wrapper_destroy_arg.txt`,
  `decomp_wrapper_substate_setter_candidate.txt`,
  `decomp_wrapper_setter_fa10/30/80.txt`,
  `decomp_connection_success_caller.txt`,
  `decomp_dispatcher_thunk.txt`,
  `decomp_loadcontext_no_selfid.txt`, `decomp_destroy_function.txt`,
  `decomp_destroy_flag_writer.txt`.
- **Cross-references**: `xrefs_FUN_145a87010_ConnectionSuccess.txt`,
  `xrefs_FUN_146454c00_PlayerSelfIdent.txt`,
  `xrefs_string_PlayerSelfIdent.txt`,
  `xrefs_string_ClientMessagesTrait.txt`,
  `xrefs_string_PlayerManagerRejected.txt`, `xrefs_string_Rejected.txt`,
  `xrefs_string_GameMessagePort.txt`.
- **Hunts**: `decomp_substate_writers.txt`,
  `find_destroy_flag_writers_0xfd_1.txt`,
  `find_constant_FE476177.txt`,
  `dump_dispatch_table_14abcc15c.txt`,
  `disasm_dispatcher_thunk.txt`.
- **New tools**: `tools/ghidra` (CLI wrapper),
  `tools/ghidra_scripts/HeadlessDecompile.py`,
  `tools/ghidra_scripts/FindXrefs.py`,
  `tools/ghidra_scripts/FindStringXrefs.py`,
  `tools/ghidra_scripts/FindWrapperSubstateWriters.py`,
  `tools/ghidra_scripts/FindOffsetWrites.py`,
  `tools/ghidra_scripts/FindConstant.py`,
  `tools/ghidra_scripts/DumpDataWindow.py`,
  `tools/ghidra_scripts/DumpInstructionsWindow.py`.
