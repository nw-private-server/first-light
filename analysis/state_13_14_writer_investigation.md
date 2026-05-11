# State 13 → 14 writer — investigation log

**Wake**: 241 (initial); **247** (writer identified via Ghidra)
&nbsp;|&nbsp; **Type**: investigation → partial finding

## Wake-247 update — writer identified: `FUN_142ffbc50`

A Ghidra session at wake 247 decompiled the top-2 candidates
from the wake-241 triage and found:

- **`FUN_146c60830` is NOT the writer** (was wake-241 tier A).
  Decompile (`decomp_FUN_146c60830.txt`) shows it's a 2680-byte-
  struct constructor that **zeros** `[+0x252]` along with hundreds
  of other fields. The struct contains `"AZStd::allocator"` string
  pointers and animation-shaped float defaults (1.0f, 2.0f) —
  it's some game-object (Actor / Player?) initializer, not the
  connection-wrapper writer. The wake-13 scan's 0x252-offset
  collision was a false positive: a different struct that
  coincidentally has a byte field at the same offset.

- **`FUN_142ffbc50` IS the writer** (was wake-241 tier B). The
  decompile (`decomp_FUN_142ffbc50.txt`) reveals the structure:

```c
void FUN_142ffbc50(longlong param_1, undefined8 param_2) {
    // ... cleanup ...
    cVar8 = '\0';  // gate value default
    // ... loop checking some state ...
    // walk a list at [param_1+0x1b8..param_1+0x1c0] in 0x70-byte strides
    for (lVar7 = *(param_1+0x1b8); lVar7 != *(param_1+0x1c0); lVar7 += 0x70) {
        if (FUN_1434b0940(lVar6) && FUN_1434985c0(lVar6, param_2)) {
            cVar8 = '\x01';  // match found
            break;
        }
    }
    if (cVar8 != *(char *)(param_1 + 0x252)) {
        *(char *)(param_1 + 0x252) = cVar8;  // <-- WRITE STATE-13 GATE
        // emit notification via FUN_142759320 with callback FUN_140571474
        ...
    }
}
```

**What the writer does**: walks a collection at
`wrapper[+0x1b8..+0x1c0]` (linked list / vector of 0x70-byte
entries), tests each entry against `param_2` via two predicates
(`FUN_1434b0940` then `FUN_1434985c0`). If any entry matches:
set `wrapper[+0x252] = 1`. If the value changes, emit a
notification callback.

**Xrefs**: 8 references total (3 data, **5 unconditional calls**
from sibling functions in the 0x142ff8-0x142ffc range —
`FUN_142ff8940`, `FUN_142ffb2f0`, `FUN_142ffb340`,
`FUN_142ffb880`, `FUN_142ffc0b0`). The 5-caller pattern
suggests this is a **recompute / observer-notify function**
called whenever one of several state-mutation events fires.

## What this means for the alt hypothesis

The wake-241 alt hypothesis ("MVP may only need SelfIdent +
LevelInfoChanged; state 13 → 14 is set by client-side actor-
spawn-complete callback") needs **refinement**, not closure:

- The writer is **in the wrapper / connection-system namespace**
  (0x142ff range, adjacent to other GameConnection code), not
  in actor-spawn-system code. That's a partial counter to the
  alt hypothesis — the writer is closer to network-state-machine
  code than to a pure actor callback.
- But `param_2` is passed in by the callers; the callers are
  what determine whether this is server-driven or local. The
  function itself reacts to whatever event the caller dispatches.
- The **list-walk + predicate-match** pattern strongly suggests
  this is checking "is the player's actor present and ready in
  some replica collection?" The collection at `wrapper[+0x1b8]`
  is replica/actor-shaped (0x70 stride = ~112 bytes per entry,
  consistent with a replica descriptor).

**Updated hypothesis** (wake 247): state 13 → 14 fires when a
specific actor/replica satisfies a predicate in a per-connection
collection. The trigger could be EITHER:
1. A replica-creation message from the server (extends the
   collection at +0x1b8; the writer fires; the predicate
   matches; gate opens).
2. A local event (e.g. animation-init or asset-load completes
   on an existing entry; the writer fires; predicate now
   matches; gate opens).

To definitively distinguish: decompile the **5 callers** and
see what kind of events trigger them. This is the next
concrete static-RE step.

## Wake-249 update — 5 callers decomp'd, trigger context resolved

Wake 249 ran Ghidra decomps on all 5 unconditional-call xrefs:
`FUN_142ff8940`, `FUN_142ffb2f0`, `FUN_142ffb340`, `FUN_142ffb880`,
`FUN_142ffc0b0`. Decomps stored at
`analysis/decomp_FUN_142ff*.txt`. Summary:

**The 5 callers are NOT message handlers** — they're local
state-update functions. Each builds (or receives) a
vtable-wrapped predicate object and passes it to
`FUN_142ffbc50` as `param_2`. The vtables observed:

- `PTR_LAB_148089ff0` (callers: FUN_142ffb2f0,
  FUN_142ffc0b0-true-branch)
- `PTR_LAB_14808a050` (callers: FUN_142ffb880,
  FUN_142ff8940, FUN_142ffc0b0-false-branch)
- `PTR_LAB_1480b77c8` (caller: FUN_142ffb340)

These look like **visitor/predicate** implementations
(classic Observer pattern). The writer's predicate-match loop
is type-polymorphic on `param_2`'s vtable.

**The smoking gun: FUN_142ff8940** is the most informative
caller (58 lines). Its body:

```c
void FUN_142ff8940(longlong param_1, longlong param_2) {
    cVar1 = (**(code **)(*(longlong *)(param_2 + 0x7c0) + 0x60))();
    if (cVar1 != '\0') {
        // copy collection from param_2 INTO wrapper[+0x1b8..+0x1c0]
        *(undefined8 *)(param_1 + 0x1c0) = *(undefined8 *)(param_1 + 0x1b8);
        FUN_14300eb70(param_1 + 0x1b8,
                      (*(longlong *)(param_2 + 0x7d8) - *(longlong *)(param_2 + 2000)) / 0x70);
        FUN_142fe5870(param_1 + 0x1b8, param_2 + 2000);
        // ... build predicate ...
        FUN_142ffbc50(param_1, uVar3);  // re-evaluate gate
    }
}
```

The function **explicitly populates `wrapper[+0x1b8..+0x1c0]`
from `param_2[+0x7d0..+0x7d8]`** (param_2 + 2000 == param_2 +
0x7d0). So:

- `param_2` is some upstream container that holds the
  0x70-stride entries (replicas? player entries?).
- The collection at `param_2[+0x7d0]` is the source.
- This function copies it into the wrapper, then re-evaluates
  the state-13 gate.

**Trigger chain confirmed (validates the wake-241 alt
hypothesis)**:

1. Some upstream system adds 0x70-stride entries to the
   container at `param_2[+0x7d0]`. The most likely source is
   the **replica system** (GridMate replica creation reacts
   to server-side `NewProxy` messages).
2. Each caller of FUN_142ffbc50 fires when this container
   changes. The callers all wrap the call in
   `FUN_142ffbc50(wrapper-or-subobject, predicate_object)`.
3. FUN_142ffbc50 walks the wrapper's local copy of the
   collection (which the upstream copy populated), tests each
   entry against the predicate, and sets the gate byte if
   any match.

**So state 13 → 14 is set by the local replica system reacting
to server-side `NewProxy` (or equivalent) messages**, not by
a dedicated ClientMessagesTrait handler. The MVP server-side
implication:

- `SelfIdent` (10→11 + 11→12) ✓
- `LevelInfoChanged` (12→13 force) ✓
- **Plus a `NewProxy` / replica-creation message** carrying
  the player's actor replica. Once the replica lands, the
  client's replica system copies it into `wrapper[+0x7d0]`,
  the writer fires, the predicate matches (the player's own
  actor), and the gate opens.

This is **3 server messages minimum** for MVP, not 2 as the
wake-241 alt hypothesis tentatively claimed. The wake-241
hypothesis was directionally right (local-system-driven, not
direct-message-driven) but quantitatively off (the actor-
spawn-complete IS triggered by a server message, just not
a `ClientMessagesTrait` one).

**Caveats**:
- The above is a static-RE interpretation; the exact wire-
  format of the actor-spawn / replica-creation message hasn't
  been characterized. It may be the GridMate `NewProxy`
  command (`cmdhdr` switch case 2 per
  `ghidra_hunt_list.md` § 2C).
- A runtime trace would confirm both the trigger chain and
  whether all 5 callers fire or only specific ones during
  the post-V3 sequence.

## Wake-241 original investigation (preserved below)

## Question

The state 13 → 14 transition (`WaitingForPlayerSpawn` → `InGame`,
the MVP target) is gated by `*(u8 *)(wrapper + 0x252) != 0` per
the state-machine summary § 1 predicate table. Reader is
`FUN_145a923c0` (returns the byte). **Who sets the byte to 1?**

## What's been tried

### Wake-13 (autonomous loop, 2026-05-07): immediate-1 scan

Ran `FindOffsetWrites 0x252 0x1` — looks for `MOV byte ptr
[reg + 0x252], 0x1` immediate stores. Result: **3 hits**, all in
unrelated classes per wake-13 analysis:

- `FUN_143dd6b20` — UI / text helper (`{value}/{maxCount} - %s`).
- `FUN_1473ed090` — Wwise audio plugin (`AkSoundSeedWoosh`).
- `FUN_14752dcd0` — JSON-ish helper (`caseId`/`context`).

None touch the connection wrapper. Wake-13 concluded the real
writer must use a non-immediate-store pattern (register-based,
struct-copy, OR-store, or memcpy from a constant-1 source).

### Wake-13 also ran the broader scan (this doc surfaces it)

`find_offset_252_all.txt` (in this repo) — scanned **all
instructions with operand displacement 0x252**. Result: **45
hits across 33 unique functions**. The 3 immediate-1 writes
above are a subset. The rest are register-based or struct-copy
patterns:

- 3 immediate-1 writes (already screened, unrelated).
- 2 immediate-0 writes (`FUN_143fe1a30`, `FUN_147142310`,
  `FUN_1479b6d00`) — clear-the-flag operations, would advance
  state 13 → 14 backwards (force into 13 by clearing). Plausible
  if the gate is cleared on state-13 entry then set by the
  transition trigger.
- 1 immediate-0 write specifically interesting: `FUN_147142310`
  has CMP + MOV pattern, suggesting "if non-zero, clear to zero"
  — possibly the state-13-entry clear.
- ~15 register-based writes (most write `AL`, `CL`, `DIL`,
  `R15B`, `BPL`, `XMM0` ...) — value depends on register, can't
  be screened by scan alone.
- Several struct-copy patterns (`MOVZX EAX, byte ptr [src+0x252];
  MOV byte ptr [dst+0x252], AL`) — these are wrapper-to-wrapper
  copies (e.g. struct cloning), not new sets.

### Wake-13 third scan: `0x145a`-prefix filter

`find_offset_252_wrapper_only.txt` — same scan but limited to
functions whose entry address starts with `0x145a` (the wrapper-
setter family region per `state_machine_summary.md`).

Result: **1 hit — the reader `FUN_145a923c0` only**. The state-13
writer is **not in the wrapper-setter namespace** unlike the
state-12 gate (whose writer `FUN_145a9fa00` lives at 0x145a9fa00,
in this exact range).

So the writer is somewhere outside `0x145a`. The wake-13 finding
holds: the state-13 gate is set via a different pattern from
the state-10 and state-12 gates.

## Most promising remaining candidates

From the unscreened hits in `find_offset_252_all.txt`, ranked by
likelihood of being the connection-wrapper writer:

### Tier A — adjacent to message-handler namespace (0x146xxxxxx)

- **`FUN_146c60830`** @ `0x146c60830` — writes `DIL` (a function
  param register, 8-bit form of `RDI`). Pattern: `MOV byte ptr
  [RBX + 0x252], DIL`. The 0x146cxxxxx range is in the
  message-handler-adjacent code space (cf. `FUN_146446800`
  = LevelInfoChanged handler at 0x146446800, `FUN_146454c00`
  = SelfIdent handler, `FUN_14645c660` = the 12→13 second writer).
  **If `FUN_146c60830` takes a bool param via DIL and a wrapper
  pointer via RBX**, it could be the dedicated state-13 setter.
  Next step: decomp `FUN_146c60830`, check xrefs.

### Tier B — register-based with adjacent CMP/LEA (suggests setter pattern)

- **`FUN_142ffbc50`** @ `0x142ffbc50` — CMP + MOV `R15B` + LEA
  `&gate` pattern:
  ```
  142ffbe4d  CMP R15B,byte ptr [RSI + 0x252]
  142ffbe5d  MOV byte ptr [RSI + 0x252],R15B
  142ffbe84  LEA R8,[RSI + 0x252]
  ```
  Could be a "set-if-not-already" pattern, with the LEA passing
  the gate address to another function. Next step: decomp +
  identify the LEA-target call.

### Tier C — single-byte writers in adjacent namespaces

- **`FUN_145dbae90`** @ `0x145dbae90` — writes `AL`. In the
  `0x145d` range (adjacent to wrapper namespace `0x145a`, could
  be `GameConnection` itself or a helper).
- **`FUN_140f4c5a0`** @ `0x140f4c5a0` — writes `AL`. Lower address
  space, possibly engine-side code that touches wrappers
  indirectly.
- **`FUN_142fdf450`** @ `0x142fdf450` — writes `CL`. Similar.

### Tier D — wrapper-to-wrapper struct copies (less likely to be NEW sets)

`FUN_142fdec20`, `FUN_142fdf050`, `FUN_143fe1300`,
`FUN_143fe1690`, `FUN_147525900`, `FUN_147525ee0`,
`FUN_147526270` all match the `MOVZX EAX, byte [src+0x252];
MOV byte [dst+0x252], AL` pattern. These propagate the byte
value across struct instances — they don't establish a new
value. **Unless** one of them is the message-deserializer
copying from a network buffer to the wrapper.

## Hypothesis: it might not be a single writer

The state-machine pattern for 10→11 and 12→13 was:
1. Reader function in wrapper namespace (`FUN_145a92370`,
   `FUN_145a905c0`).
2. Writer function in wrapper namespace, single immediate
   store, single xref (`FUN_145a87010` for state-10,
   `FUN_145a9fa00` for state-12).
3. Caller is a ClientMessagesTrait dispatch entry.

State 13 → 14 breaks this pattern:
- Reader exists at `FUN_145a923c0` (✓).
- Writer is **not** in the wrapper namespace.
- The trigger may not be a dedicated trait message.

**Alternative hypothesis**: state 13 → 14 may be **timer-driven
or implicit**. Once state 13 is entered (via LevelInfoChanged or
FUN_14645c660 setting `wrapper[+0xbc8] = 1`), the actor system
needs time to spawn the player; the gate byte at `+0x252` may
be set by the actor-spawn-complete callback rather than a
network message.

Evidence for this hypothesis:
- The state name `WaitingForPlayerSpawn` suggests the wait is
  for a local event (spawn-complete), not a server message.
- No catalogued `ClientMessagesTrait` class has an obvious
  "SpawnComplete"-like semantic — the 5 known are SelfIdent,
  Rejected, LevelInfoChanged, RemoteConfigChanged,
  DebugCommandResponse.

If this hypothesis is correct, **the server doesn't need to
send a message to advance 13 → 14**. The MVP server just needs
to ship state 10 → 11 (SelfIdent) and 12 → 13 (LevelInfoChanged
or the 4½ alternative); state 13 → 14 fires from the client's
actor-spawn-complete callback once the level data is loaded.

This would explain why no clean single-writer exists: the gate
is set by actor-system code (which lives in a different
namespace — likely `0x146cxxxxx` or similar engine code) rather
than connection-wrapper code.

## Concrete next-step Ghidra actions

For a future Ghidra session (or autonomous wake with GhidraMCP
running):

1. **Decompile `FUN_146c60830`** (Tier A candidate). Check
   whether its param signature matches `void
   setStateThirteenToFourteenGate(wrapper, bool)`. Check xrefs —
   should be called from an actor-spawn-complete handler if the
   alternative hypothesis is correct.

2. **Decompile `FUN_142ffbc50`** (Tier B candidate). Trace
   what calls it; the LEA pattern suggests this is part of a
   higher-level write helper.

3. **Search for actor-spawn-complete strings**: grep for
   `Spawn`, `ActorSpawn`, `OnSpawnComplete`, `PlayerSpawn`
   in the binary's `.rdata` near the message-handler code
   region (0x146xxxxx). Each hit's xref should land on actor-
   system code that may write to `wrapper[+0x252]`.

4. **Cross-reference the LevelInfoChanged handler's call graph**:
   `FUN_146446800` forces state to 13. What does the state-13
   entry code do? Does it install a callback that eventually
   writes to `wrapper[+0x252]`? Walk the state-13 setter's
   callees.

5. **Frida hook on the reader `FUN_145a923c0`**: log every
   call + the byte value. When the byte transitions 0 → 1,
   the previous instruction (in the calling thread's stack) is
   the writer. This is the runtime equivalent of the static
   scan; bypasses all the namespace heuristics.

## What this investigation costs not to resolve

Until 13 → 14 writer is identified, the static-RE picture of
the post-V3 state-spawn ladder is **incomplete on the last
step**. This is the surfaced carry-over the wake-240 Findings
card explicitly names. The cost is:

1. The MVP server can't be **certain** it has all required
   server-side messages. Plausibly only `SelfIdent` +
   `LevelInfoChanged` are needed (per the alt hypothesis); but
   the static-RE can't confirm.
2. A real-GPU runtime trace (eventually) on the gate-byte
   transitions will resolve the question definitively.

For now: the state-13 → 14 writer remains the documented
open question. This investigation log captures the search-
space and the most-promising-candidate triage so that a future
Ghidra session can pick up from this point rather than re-deriving
the scan.

## See also

- [`state_machine_summary.md`](state_machine_summary.md) § 1
  predicate table.
- [`ghidra_hunt_list.md`](ghidra_hunt_list.md) — open RE-hunt
  index, carry-over section.
- [`find_offset_252_all.txt`](find_offset_252_all.txt) — the
  raw scan output (45 hits, 33 functions).
- [`find_offset_252_wrapper_only.txt`](find_offset_252_wrapper_only.txt)
  — the namespace-filtered scan (1 hit, reader-only).
