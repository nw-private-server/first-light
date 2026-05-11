# State 13 → 14 writer — investigation log

**Wake**: 241  |  **Type**: investigation, not a finding (yet)

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
