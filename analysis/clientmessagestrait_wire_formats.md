# Javelin::ClientMessagesTrait — wire-format reference

> Static-RE inventory of message bodies the New World client expects
> on the post-V3 GameMessagePort channel. Compiled from handler
> decomps in worklog wakes 51, 53, 54, 57, 60, 63.

## Implementations

The two messages documented here have shipping Python encoders +
unit tests in `server/javelin/`:

| Message | Encoder | Tests |
|---|---|---|
| `PlayerManagerSelfIdentificationMsg` | [`server/javelin/self_ident.py`](../server/javelin/self_ident.py) | `test_codecs.py::test_self_ident_*` |
| `LevelInfoChangedMsg` | [`server/javelin/level_info_changed.py`](../server/javelin/level_info_changed.py) | `test_codecs.py::test_level_info_*` |

When updating the wire format here, update the encoder; when changing
the encoder, update this reference. They drift if maintained
independently.

> ⚠️ **SelfIdent wire-vs-in-memory conflict (open):** the doc
> [`docs/post-v3-sequence.md`](../docs/post-v3-sequence.md)'s phase
> table lists Phase 9b SelfIdent body as 4 bytes (footnote ¹). The
> handler reads from a 56-byte in-memory struct, hypothesizing a
> 21+ byte wire body. Either the wire body is a 4-byte trigger and
> the deserializer fills the rest from session state, OR the doc's
> 4B figure is stale. **Unresolved without runtime data** — see the
> "SECONDARY CAVEAT" in `self_ident.py`.
>
> **All offsets are within the message body struct** (the
> dispatcher unpacks the carrier and passes the body to the handler;
> see "Carrier framing" below). All fields are little-endian.
>
> **Caveat:** struct field semantics (names like `m_clientContextInstanceId`)
> are inferred from log strings the handler emits. Field types are
> inferred from access widths (`*(u8 *)`, `*(u32 *)`, etc.). Both
> may be wrong; treat as hypotheses verified by handler behavior,
> not authoritative reflection data.

## Convention shared by all ClientMessagesTrait handlers

(Confirmed across SelfIdent and LevelInfoChanged.)

- Handler logs first via `FUN_141721c20("GameMessagePort", "<MsgName>")`
  (or `FUN_14143e010` for some handlers — the same channel).
- Calls `FUN_1406d97d0(param_1 - 0x990)` to walk to a sub-object
  pointer at `+0x48` of the GameConnection-like outer struct.
- The state field is at `subObject + 0x1530` (state values 0..14
  per `analysis/state_machine_summary.md`).
- The state-machine entry to set state is `FUN_14645fd70(subObject,
  newState)` followed by direct write of `*(int *)(subObject + 0x1530)`.
- `param_1` itself is offset `0x990` bytes into the outer struct;
  state storage at `param_1 - 0x910 .. param_1 - 0x7b4` lives at
  `outer + 0x80 .. outer + 0x1DC`.

## PlayerManagerSelfIdentificationMsg

Handler: `FUN_146454c00` (with thunk at `FUN_146454bec`).
Dispatch entry: `0x14abcc150..0x14abcc15c` (4-RVA-tuple format).
RTTI: `Javelin::ClientMessagesTrait::PlayerManagerSelfIdentificationMsg`.

### Body layout

| Offset | Size | Field (proposed) | Notes |
|---|---|---|---|
| `0x00` | 4 | `m_field0` | u32 — purpose TBD |
| `0x04` | 4 | _pad_ | alignment |
| `0x08` | `0x20` | `m_field08` | `AZStd::vector<u32>` (32-byte container; copy via `FUN_1402d13a0` proves u32 elements) |
| `0x28` | 1 | `m_debugFlag` | `true` triggers debug-only path that reads CVars `g_debugPlayerPosition` / `g_debugPlayerRotation`; production servers send 0 |
| `0x29` | 3 | _pad_ | |
| `0x2C` | 8 | `m_field2C` | u64 — UNALIGNED 8-byte read; possibly an id |
| `0x34` | 4 | `m_field34` | u32 |
| `0x38` | — | _end_ | min 56 bytes |

### Wire format (proposed)

If the AzCore serializer copies fields straight (typical for
non-versioned typed messages), the wire layout maps the struct
with the vector prepended by its length:

```
+0x00  u32  m_field0
+0x04  u32  vector_length
+0x08  u32  vector[0]
...    u32  vector[N-1]    (N = vector_length)
+...   u8   m_debugFlag
+...+1 u8[3] _pad
+...   u64  m_field2C
+...   u32  m_field34
```

Empty-vector min size: ~32 bytes.

### Side-channel inputs

`param_3` / `param_4` / `param_7` (passed by the dispatcher framework,
not on the wire) are forwarded into the wrapper sub-object at
`outer+0x130` via setters `FUN_145a9fa10/30/80`. These are the
identity-tuple inputs (sender ID, session UUID, etc.).

`param_5` carries a UUID-shaped 16-byte struct at `+0x4..+0x14`
(two qwords at `+0x4` and `+0xC`, 4-byte aligned). The handler
short-circuits when the message's identity tuple does NOT match
this expected sender — sender-validation gate.

### Field semantic open questions

- `m_field0` u32 — likely a sequence number or persona-id-half.
- `m_field08` u32 vector — could be character IDs, channel IDs, or
  shader-set IDs.
- `m_field2C` u64 — possibly a session id or timestamp.
- `m_field34` u32 — maybe a flags field.

Resolving these needs either (a) one captured live observation of
the message, or (b) cross-references from other code that reads
these stored fields after the handler writes them.

## LevelInfoChangedMsg

Handler: `FUN_146446800`.
Per-handler info: caches the previous level's `m_clientContextInstanceId`
at `outer + 0x198` (i.e., `param_1 - 0x7f8`) and short-circuits when
the message's `+0xa8` matches.

### Body layout (full — extracted from copy constructor `FUN_1464027b0`)

| Offset | Size | Field (proposed) | Notes |
|---|---|---|---|
| `0x00` | `0x28` | `m_levelName` | `AZStd::string` (40-byte container in-memory; see "AZStd::string layout" below) — copy via `FUN_1402b0580` |
| `0x28` | `0x28` | `m_someOtherName` | `AZStd::string` (40 bytes; purpose TBD — could be region, instance id name) |
| `0x50` | 4 | `m_field50` | u32 (or float) |
| `0x54` | 4 | `m_field54` | u32 (or float) |
| `0x58` | 4 | `m_field58` | u32 (or float) |
| `0x5C` | 4 | `m_field5C` | u32 (or float) — pattern of 4 contiguous u32s suggests a 4-tuple (Vec4 / quat?) |
| `0x60` | 8 | `m_field60` | u64 |
| `0x68` | `0x38` | `m_extendedField` | **AZStd hash-container** (set or map; copy logic `(N-1)/7 + N` + power-of-2 bucket sizing in `FUN_1416074b0` confirms unordered associative). 56-byte in-memory layout: vtable ptr + 6 qwords of bookkeeping. Side-context at `+0x98` is the allocator/hasher snapshot. Internal self-reference at `+0x88` (within the container, used as a hashtable bucket sentinel — set to `(undefined1)param_1` on copy in `FUN_146410750`). Element type T not yet known. Wire encoding for an empty container is typically `[u32 count=0]`. |
| `0xA0` | 1 | `m_field_a0` | u8 |
| `0xA1` | 1 | `m_levelIsLoading` (?) | u8 — passed by-pointer to `FUN_1463e42b0` as opaque payload to a list-walking dispatcher. The dispatcher walks a thread-local list, invokes a callback (`FUN_14057143c`) per entry with `(entry+offset, &this_byte)`, and the callback's return value becomes the gate. So the gate isn't decided by `m_levelIsLoading` alone — it depends on the contents of the list at the moment of the call. For server-side encoding: setting `m_levelIsLoading = 0x01` is what wake-54's "production server" recipe assumes; non-zero values are likely fine, the gate's actual logic lives in `FUN_14057143c`. |
| `0xA2` | 1 | `m_isInGameTransition` (?) | u8 — gate for the state-14 → state-13 transition |
| `0xA3` | 1 | `m_field_a3` | u8 |
| `0xA4` | 4 | _pad_ | not copied by the constructor; structural alignment |
| `0xA8` | 8 | `m_clientContextInstanceId` | u64 — the message's identity; client filters duplicates by comparing to the cached `outer+0x198` |
| `0xB0` | — | _end of wire body_ | wire size = 176 bytes (matches `local_e8[176]` in handler) |

**Runtime-only field (NOT on the wire):** The handler's local
buffer extends past +0xB0 with an additional `u8` flag at offset
`+0xB0` that tracks whether the in-memory struct is initialized.
The handler sets this to `1` before calling `FUN_146410750`
(the storage helper). Per `FUN_146410750`'s branch logic:

```c
if (*(char *)(param_1 + 0xb0) == '\0') {
    if (*(char *)(param_2 + 0xb0) == '\0') return param_1;
    // ... fresh-copy branch (move-construct)
} else {
    if (*(char *)(param_2 + 0xb0) == '\0') {
        *(char *)(param_1 + 0xb0) = 0;     // clear flag
    }
    // ... assign branch (use FUN_1402b04f0 which is a different copy)
}
```

So the in-memory struct is 177+ bytes (bumped up to 0xB8 for
8-byte alignment), but only the first 176 bytes match the wire.

### Server-side implication

For the post-V3 sequence (where `LevelInfoChangedMsg` drives the
state transition that gets the client to state 13 / WaitingForPlayerSpawn,
per worklog wake 11), the server must:

1. Send a non-zero `m_clientContextInstanceId` at `+0xa8`.
2. Make sure that id **changes** between consecutive messages —
   otherwise the client's de-dup check (`*(qword *)(msg + 0xa8)
   == *(qword *)(outer + 0x198)`) makes the handler return early.
3. Set `+0xa1` and `+0xa2` such that both gates pass (specifics TBD;
   the handler uses both as guard conditions on the state-14 →
   state-13 path).
4. The two `AZStd::string` fields at `+0x00` and `+0x28` need to be
   wire-encoded. AzCore wire convention for AZStd::string is
   typically `[u32 length][bytes]`.
5. The 4-tuple at `+0x50..+0x5C` (likely a Vec4/quat) and the
   `+0x60` u64 are filler we can probably zero for an initial
   syntactically-valid message.
6. The container at `+0x68..+0xA0` (56 bytes) needs further analysis;
   wire encoding TBD.

### Total body size

176 bytes in-memory. On-wire size depends on string lengths and
container contents; minimum probably ~50-60 bytes (two zero-length
strings + scalar fields).

## Related but NOT a top-level handler

- `FUN_14644b280` — sequence-number / per-context-instance queue
  helper. NOT a message handler; called from another path. Wake 7
  thought it might be one (its log line "Switch coming from
  clientContextInstanceId..." matched the GameMessagePort channel),
  but its arg shape (5 args, not the 7-arg dispatched-handler shape
  or the 2-arg level-info shape) shows it's a sibling utility, not
  a wire-format owner.

## Carrier framing

The `param_2` parameter of `FUN_146446800` is read at offsets
`+0xa1`, `+0xa2`, `+0xa8` etc., suggesting the body is preceded by
a ~0xa0-byte header. **However:** the copy constructor
`FUN_1464027b0` copies fields starting at `+0x00`, meaning what
`FUN_146446800` calls `param_2` IS the body itself, just that the
constructor sees the body as a flat 176-byte struct while the
handler accesses some header-like prefix at the start.

In other words: the body has TWO `AZStd::string` fields at the very
beginning (`+0x00`, `+0x28`), and the handler's `param_2 + 0xa1`
indices land in the middle of the payload, NOT in a separate
"carrier header." There's no extra framing prefix on top of the
body.

This contrasts with the 0x68..0xa0 "container" which has internal
structure not yet decoded — that one might have header bytes
embedded.

## AZStd::string layout

Recovered from `FUN_1402b04f0` (the move-assign used in
`FUN_146410750`'s "both initialized" branch). Total in-memory size
is **40 bytes (0x28)**:

| Offset | Size | Field | Notes |
|---|---|---|---|
| `0x00` | 16 | data buffer (SSO) or data pointer | When `capacity <= 0xF`, this is the inline SSO buffer (first 16 chars). When `capacity > 0xF`, the first 8 bytes are a heap pointer |
| `0x10` | 8 | SSO continuation or metadata | Part of the SSO buffer when in SSO mode |
| `0x18` | 8 | `size_t m_size` | length in characters (not bytes including null) |
| `0x20` | 8 | `size_t m_capacity` | capacity; **`0x0F` is the SSO sentinel** (when in SSO mode) |

**SSO threshold**: 15 characters (capacity == `0xF` while SSO).
For strings longer than 15 chars, the buffer is heap-allocated and
`m_capacity > 0xF`.

**Move-assign behavior** (`FUN_1402b04f0`):

```c
// 1. Free destination's heap if it was non-SSO
if (capacity_dst > 0xF) free(data_dst);
// 2. Copy 32 bytes (data ptr/SSO + metadata + size + capacity) from source
memmove(dst, src, 16);  dst[2] = src[2];
dst.m_size = src.m_size;
dst.m_capacity = src.m_capacity;
// 3. Reset source to empty SSO
src.data_ptr = 0;  src[2] = 0;  src.m_size = 0xF;  // (size becomes capacity sentinel)
```

**Wire format implication**: the AzCore convention for `AZStd::string`
on the wire is **`[u32 length][bytes]`** — no SSO byte-pattern,
no allocator state, just length and raw bytes. The 40-byte
in-memory layout is purely for runtime; encoders write only the
length prefix and bytes.

For the LevelInfoChangedMsg encoder, both `m_levelName` and
`m_someOtherName` follow this convention. An empty string
encodes as `[0x00, 0x00, 0x00, 0x00]` (just the u32:0 length).

## How to add to this reference

When a new sibling handler is decompiled:

1. Note the handler RVA and the log channel + name string.
2. List every read of `param_N` (the message body parameter — usually
   the last positional one) with offset and access width.
3. If the handler calls a helper that takes `param_N` directly (like
   `FUN_1402d13a0` or `FUN_1464027b0`), decompile that helper to
   recover any structural fields the handler doesn't read.
4. Cross-check stored offsets in `param_1` against the existing
   `outer-struct map` in
   `analysis/autonomous_worklog_through_253.md` (in the wake-261
   archive — search for "param_1 offset"); add new offsets to
   the active `autonomous_worklog.md` if extending.
