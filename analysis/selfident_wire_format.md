# PlayerManagerSelfIdentificationMsg — wire/struct layout (partial)

> Static-RE finding from wake 51 (2026-05-08). Decoded by reading the
> handler `FUN_146454c00`'s parameter accesses, since each message
> field is read once before the success/abort branch. Caveats below.

## Summary

The handler signature (Ghidra view):

```c
void FUN_146454c00(
    longlong  param_1,        // GameConnection / context (gets fields written into)
    longlong  param_2,
    undefined8 param_3,       // -> wrapper setter FUN_145a9fa10
    undefined8 param_4,       // -> wrapper setter FUN_145a9fa80
    longlong  param_5,        // 16-byte struct at +0x4 (UUID-shaped)
    undefined4 *param_6,      // <-- THE MESSAGE BODY
    undefined8 param_7        // -> wrapper setter FUN_145a9fa30
);
```

The handler reads exactly four-and-a-fraction fields out of `param_6`
before any conditional branch, so the offsets are stable:

```c
*(uint32_t  *)(param_1 - 0x7e8) = *param_6;                           // field_00
FUN_1402d13a0(param_1 - 0x7e0, param_6 + 2);                          // field_08
*(uint8_t   *)(param_1 - 0x7c0) = *(uint8_t   *)(param_6 + 10);       // debug_flag
*(uint64_t  *)(param_1 - 0x7bc) = *(uint64_t  *)(param_6 + 0xb);      // field_2C  (unaligned)
*(uint32_t  *)(param_1 - 0x7b4) = param_6[0xd];                       // field_34
```

`param_6` is `uint32_t*`, so `param_6 + N` advances `4*N` bytes.

## Struct layout (in-memory, post-deserialize)

| Offset | Size | Field name (proposed) | Notes |
|---|---|---|---|
| `0x00` | 4 | `m_field0` | u32 scalar — purpose TBD (sequence, persona-id-half, op-code?) |
| `0x04` | 4 | `_pad0` | alignment for the vector that follows |
| `0x08` | `0x20` | `m_field08`: `AZStd::vector<u32>` | 32-byte container; copied via `FUN_1402d13a0` (vector<u32> copy) |
| `0x28` | 1 | `m_debugFlag` | `true` triggers a debug-only branch reading `g_debugPlayerPosition` / `g_debugPlayerRotation` |
| `0x29` | 3 | `_pad1` | |
| `0x2C` | 8 | `m_field2C` | u64; **stored at +0x2C, unaligned for 8-byte access** (compiler used 4-byte struct alignment for this region) |
| `0x34` | 4 | `m_field34` | u32 scalar |
| `0x38` | — | (end / next struct field) | unconfirmed; the handler doesn't read past 0x38 in the unconditional path |

Total minimum size: **`0x38` (56 bytes)**.

## How `FUN_1402d13a0` was identified as a vector<u32> copy

Decompiled body shows the canonical `AZStd::vector` copy idiom:

```c
uVar6 = param_2[1] - *param_2 >> 2;    // element count = (end - begin) / 4
...
pvVar3 = FUN_141499110(param_1 + 3, uVar6 * 4, 4, 0);   // alloc N*4 bytes, 4-byte align
*param_1 = (longlong)pvVar3;
memcpy(pvVar3, (void *)*param_2, sVar1);                // copy raw bytes
```

The `>> 2` and `* 4` arithmetic with `4` alignment to `FUN_141499110`
is the smoking gun for u32 elements. (Could equally be `vector<float>`
or `vector<int32_t>` — byte-level semantics are identical.)

## Wire format (proposed)

For an AZStd-style serializer the wire layout typically maps directly
to the struct except for the vector, which prepends a length:

```
+0x00  uint32_t  m_field0
+0x04  uint32_t  vector_len
+0x08  uint32_t[vector_len]    (variable-length payload)
+...   uint8_t   m_debugFlag
+...+1  3 padding bytes
+...   uint64_t  m_field2C     (unaligned)
+...   uint32_t  m_field34
```

So total wire size = `0x10 + vector_len*4 + remaining tail`. With
`vector_len = 0` (the simplest case) wire size is `0x18 + 5 = ~0x20`
bytes. For non-empty vectors it grows by `4` per element.

Note: this is **the AzCore wire convention**; the actual serializer
hasn't been decompiled yet (the dispatcher table at `0x14abcc15c`
is packed 4-byte RVAs but its layout isn't fully understood — see
worklog wake 6).

## Open questions

1. **Field semantics.** What does each field actually mean? The
   names in the Lumberyard source presumably are like `m_personaId`,
   `m_charactersOwned`, `m_serverIp`, etc., but we have no
   debug-symbol or PDB to confirm. The handler stores them at fixed
   offsets in `param_1` (the GameConnection) for use by later code:
   - field_00 → `gameConn[-0x7e8]` (u32)
   - field_08 → `gameConn[-0x7e0..-0x7c0]` (vector<u32>)
   - debug_flag → `gameConn[-0x7c0]` (u8)
   - field_2C → `gameConn[-0x7bc..-0x7b4]` (u64, unaligned)
   - field_34 → `gameConn[-0x7b4]` (u32)
2. **Sentinel for the unconditional path.** The 0x38 size is the
   minimum the handler reads; if the deserializer reads more bytes
   into the message struct (e.g., a trailing optional field), the
   handler ignores them. Need to find the deserializer to confirm.
3. **Wrapper setter args.** `FUN_145a9fa10/30/80` take param_3,
   param_4, param_7 from the dispatch's caller, not the message.
   These are probably the connection's identity tuple (sender ID,
   session UUID, etc.) provided by the dispatcher framework. Worth
   tracing.
4. **The 16-byte `param_5+4..0x14` struct.** Identity comparison
   `*(longlong *)(param_5 + 4) == *plVar8 && *(longlong *)(param_5
   + 0xc) == plVar8[1]`. Two qwords at +0x4 and +0xC suggest a
   UUID (split into lo/hi qwords) packed at 4-byte alignment. This
   is the **expected sender** ID; the handler short-circuits when
   it doesn't match.

## What this unblocks

The `server/javelin/v3_response.py` builder currently uses replay
bytes from Mixed Nuts's session as the V3 payload (worklog wake 26
+ wake 27). Once the SelfIdent message is reachable through the
post-V3 sequence (Phase 9b in `docs/post-v3-sequence.md`), the
server needs to encode this struct on the wire. With the layout
known we can:

- Encode an empty `m_field08` vector by sending `len=0` (no
  payload).
- Set `m_debugFlag = 0` to skip the debug-only branch.
- Tackle `m_field2C` / `m_field34` semantics as a follow-up — they
  may need to be filled with values copied from the V3 request or
  computed from session state.

That's enough to make a *syntactically valid* SelfIdent body. Whether
the client accepts it as semantically valid depends on field-meaning
work that needs runtime data we don't have yet (a captured session
log with the SelfIdent in it would resolve this in one observation).

## Lineage / next steps

- This finding sits at A2.8 (handler-side field shapes) → upgraded
  from "partial: needs wire-format decode" to "wire layout
  proposed; semantics open".
- A2.9 (the dispatcher) is still partial. The dispatch table at
  `0x14abcc15c` is packed 4-byte RVAs in pairs (handler RVA +
  thunk RVA) interleaved with what looks like type-info pointers
  (e.g. `0x09cc1c44`); the meaning of those pointers is the
  remaining unknown.
- A2.9b approach (a) — the vtable at `0x14ab72930` containing
  `FUN_145a87010` — turned out to be the same packed-RVA format,
  not an exploitable second anchor.

## Forward references (added wake 246)

This doc was a wake-51 deep-dive on SelfIdent's handler-side
field shapes. The wake-111/112 RE breakthrough confirmed the
state-10 → 11 gate predicate (`wrapper[+0xa0] == 2`) and the
wire-type trigger (`0x5d1`). Both findings are now canonical:

- [`state_machine_summary.md`](state_machine_summary.md) — full
  predicate table (states 10 → 14) including the trigger/writer
  column added at wake 237; § 3 details the SelfIdent handler.
- [`state_10_unblock_synthesis.md`](state_10_unblock_synthesis.md)
  — wake-111 synthesis of the state-10 unblock question; the
  wake-245 forward-references footer there points at current
  state.
- [`state_13_14_writer_investigation.md`](state_13_14_writer_investigation.md)
  — wake-241 investigation log for the lone remaining open
  question (state 13 → 14 writer + alt hypothesis that MVP may
  only need SelfIdent + LevelInfoChanged).

The "field-meaning work that needs runtime data" caveats above
remain legitimately open — the SelfIdent body's exact field
values can only be resolved via runtime trace (real-GPU host
required).
