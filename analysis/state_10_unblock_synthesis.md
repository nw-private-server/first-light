# State-10→11 gate — unblock synthesis (wake 111)

## TL;DR

**The state-10→11 gate is a 4-byte int comparison at `wrapper+0xa0 == 2`.
The message that writes `2` there is `PlayerManagerSelfIdentificationMsg`
(wire type `0x5d1`). 0x5d1 is NOT in the captured replay, which is why
the pure-replay server can't drive the client past state 10. Unblocking
requires the server to construct and emit a synthetic 0x5d1 message.**

## The predicate (verified)

`analysis/decomp_state_advance_predicate.txt`:

```c
// FUN_145a92370 @ 145a92370
bool FUN_145a92370(longlong param_1) {
    return *(int *)(param_1 + 0xa0) == 2;
}
```

`param_1` here is the inner `GameConnectionWrapper` sub-object passed
in by the outer state-machine via `param_1 + 0x130`. State counter
sequence inside the wrapper:

| Value at `wrapper+0xa0` | Meaning |
|---|---|
| `0` | Pre-state-10 |
| `1` | State 10 entered (set by setup code) |
| `2` | Gate open for state 10→11 |

The setup function (`analysis/decomp_wrapper_state10_setup.txt`)
sets `wrapper+0xa0 = 1` on entry; the predicate checks for `2`.

## What writes `2`

`Javelin::ClientMessagesTrait::PlayerManagerSelfIdentificationMsg`
handler (`FUN_146454c00`). Per worklog wake 3 task A2.5, this was
identified as the writer. The handler is invoked when the client
receives a SelfIdentification message from the server.

## Wire-type encoding

The protocol's typed-envelope encoding is:

```
byte 2 = (type_id & 0x3f) | 0x80
byte 3 = (type_id >> 6) & 0xff
```

For `0x91(0x17)` (the form used in `docs/post-v3-sequence.md`):

```
type_id = (0x91 & 0x7f) | (0x17 << 6) = 0x11 | 0x5c0 = 0x5d1
```

So **the SelfIdent wire type is `0x5d1`**. Full type header on the
wire: `00 01 91 17`.

## Why the captured replay can't drive it

The replay's 40 captured wire-types are listed in `site/data.json`
and the dashboard. **`0x5d1` is not among them.** A grep over the
replay's 177 messages finds zero bodies starting with the
`00 01 91 17` header.

This is consistent with the captured login session ending before
the server emitted a SelfIdent message, OR the message being
filtered out. Either way, the post-V3 replay never delivers the
gate trigger, so `wrapper+0xa0` stays at `1` and state-10 never
advances.

## Unblock plan

The unblock has two pieces:

### 1. Wire-bind the existing codec

`server/javelin/self_ident.py` already has the body encoder for
`PlayerManagerSelfIdentificationMsg`, but it doesn't emit a
typed-envelope header (the codec is module-level only — no
`TYPE_HEADER` constant, no dispatcher binding). Add:

```python
TYPE_ID = 0x5d1
TYPE_HEADER = bytes((0x00, 0x01, 0x91, 0x17))
```

…and wire it into `dispatch.py`'s ENCODERS table.

### 2. Resolve the body size

`docs/post-v3-sequence.md` gives two conflicting answers about the
on-wire body size:

- **4-byte** estimate (header-only trigger, no payload). This
  matches Phase 9b's "Size" column in the post-V3 table.
- **21+ byte** estimate (5 fields read by `FUN_146454c00`). This
  matches the handler's actual reads.

If the wire body is 4 bytes, the handler must be sourcing the 21
bytes from session state — not from the wire. If the wire body is
21+ bytes, the doc's "Size" column is a stale pre-RE estimate.

**This is genuinely unresolved without runtime data.** The cheapest
experiment when a real-GPU host is available:

1. Send a 4-byte SelfIdent (header only). If `wrapper+0xa0` flips
   to `2`, that's the answer.
2. If not, send the 21-byte structured body per `self_ident.py`'s
   current encoder.
3. If still not, the handler may require non-zero values in
   specific fields (m_field0, m_field2C, m_field34) — which would
   need further static-RE on the handler's read paths.

## What this wake's analysis settled

- The predicate is `wrapper[+0xa0] == 2` (4-byte int compare). An
  earlier project memory record had this offset wrong as `+0x130`;
  that was a confusion between the outer struct's wrapper-pointer
  offset and the wrapper-internal field. **Memory now corrected.**
- The trigger message is wire-type `0x5d1`. The codec name is
  `PlayerManagerSelfIdentificationMsg`. Both confirmed via
  cross-reference of the wake-3 worklog finding and the wire-id
  encoding in `docs/post-v3-sequence.md`.
- The captured replay does not contain a `0x5d1` message — zero
  bodies start with the `00 01 91 17` header. The unblock cannot
  be achieved by replay alone.

## What this wake's analysis did NOT settle

- The exact wire-body size (4 vs 21+ bytes).
- The exact value of any required body fields (m_field0, etc.).
- The timing — at what point in the post-V3 sequence does the
  client expect the SelfIdent? Phase 9b per the doc, but the
  precise tick relative to the captured replay is unverified.

These three need runtime testing.

## Forward references (added wake 245)

This doc was the wake-111 deep-dive on the state-10 → 11 gate.
It remains accurate as that wake's snapshot. Later wakes
extended the state-machine picture; current state is in:

- [`state_machine_summary.md`](state_machine_summary.md) — full
  predicate table (states 10 → 14), the ClientMessagesTrait
  catalog, § 4½ on the wake-232 12→13 second-writer finding,
  and the § 1 trigger/writer column added at wake 237.
- [`state_13_14_writer_investigation.md`](state_13_14_writer_investigation.md)
  — wake-241 search log for the lone remaining unknown writer.
  Includes the substantive alt hypothesis that **MVP may only
  need SelfIdent + LevelInfoChanged** (state 13 → 14 may be
  set by client-side actor-spawn-complete, not a server
  message).
- [`session_retrospective_227.md`](session_retrospective_227.md)
  — third-stretch retrospective covering wakes 197-227
  including the state-machine surfacing arc.

The wake-204 phase-2D heartbeat-emission infrastructure (default
off) + the wake-208 counter-advance extension are the runtime-
emit scaffolding needed for the 0x5d1 SelfIdent synthesis once
real-GPU validation flips the flags. The three "needs runtime
testing" items above are still legitimately open.
