# Wrapper-setter and dispatcher decompiles — overview

Companion to `state_machine_summary.md` and
`connection_lifecycle_decompiles.md`. Covers the remaining
decompile files that didn't fit either of those writeups —
mostly the per-substate wrapper writers, the response-side
RTTI handlers, and a small set of yet-uncharacterized
function-IDs. Surfaces enough context that the wake-129
dashboard cross-link pass picks these up.

## Wrapper substate writers (the +0xfa* / +0xa0 family)

The connection wrapper struct has several "substate" byte
fields the binary keeps in sync. Per
`state_machine_summary.md`, the primary state field is at
`wrapper+0xa0` (the int the wake-111 state-10→11 predicate
reads). The wrapper-setter functions below all write related
fields.

### `wrapper_setter_fa80`

One of the substate-setter triplet
(`fa10` / `fa30` / `fa80`). Mirrors the structure of
`wrapper_setter_fa10` and `wrapper_setter_fa30` from
`state_machine_summary.md`; the offset name reflects the
field offset (`wrapper + 0xfa80` in the outer-struct frame).
Each member of the triplet flips a different sub-step flag;
all three fire from the substate-dispatch path.

### `wrapper_state10_entry`

The entry-point for state 10, called immediately before
`wrapper_state10_setup` (which sets the substate counter to
`1`). Distinct from the predicate
(`state_advance_predicate`) — entry runs once when the state
transitions in, setup runs every tick while in the state.

### `wrapper_state12_gate_writer`

Companion to `wrapper_state12_gate` (already cross-linked from
`state_machine_summary.md`). The gate function reads a flag;
this writer is what flips it.

### `wrapper_substate_xref_caller_1` and `wrapper_substate_xref_caller_2`

Two xref sources for the wrapper-substate-setter chain. Useful
when triangulating which higher-level paths feed into the
substate machine — the wake-95 xref hunting work captured
these as the two distinct callers that route into the setter
candidate. Both eventually invoke
`wrapper_substate_setter_candidate` from
`state_machine_summary.md`.

### `wrapper_switchD8_check`

A predicate gate at `wrapper + 0xd8`. Returns a small int that
selects between the three wrapper setters. Mentioned here so
the wrapper-state-machine decomp set is fully indexed; the
exact dispatch table isn't yet RE'd.

## State-13 writers (per-substate writers)

`state_machine_summary.md` cross-links `state13_writer_a`. The
two siblings:

### `state13_writer_b` and `state13_writer_c`

Same shape as `state13_writer_a` — each writes a different
sub-field during state 13. The trio together completes the
state-13 substate machine. They run sequentially during the
state-13 tick chain.

## State-11 dispatcher

### `state11_dispatcher`

The dispatcher invoked when the connection enters state 11
(after the wake-111 predicate at `wrapper+0xa0 == 2` fires).
Reads the substate counter, routes to the right per-step
handler. The state-11 dispatch sequence is what produces the
post-V3 message stream the captured replay records starting
around seq 7-10 (per the dashboard's session-timeline scatter
chart).

## Destroy / fail dispatch

### `destroy_dispatcher`

The fail-path equivalent of `state11_dispatcher`. Routes to the
right destroy handler when the connection's
`destroy_flag_writer` fires (cross-linked from
`state_machine_summary.md`). Used in the chain that fires when
the post-V3 state-machine doesn't advance within the timeout
window. The state-10→11 mechanism itself is RE'd
(wake 111-112) — the destroy trigger writer
(`FUN_146b3c250 + 0x58f`) is the remaining open static-RE
question on this chain (still finds what writes `[R13+0xfd]`).

## Response handlers (server → client)

### `response_typeinfo`

The AzCore RTTI registration for the V3 RegistrationResponse
message type. Sibling to `clientconnectionmsg_typeinfo` from
`connection_lifecycle_decompiles.md` but on the response
direction.

### `response_unmarshal`

The body-parser for the server's V3 RegistrationResponse
message. Read by the client when it receives the response from
the server. The Python `serialize_v3_request` in
`server/javelin/v3_request.py` produces what
`response_unmarshal` parses on the client side — they're
encode↔decode siblings across the wire.

## Uncharacterized FUN_* decompiles

Three decompiles were captured early in the RE work but their
purpose hasn't been confirmed beyond their RVAs. They're kept
in the decomp catalog because they appeared on the xref path
to characterized functions and may yield more context when
revisited.

### `FUN_146240d70`, `FUN_1462419c0`, `FUN_1462426b0`

A small cluster of functions adjacent in `.text` (around
RVA `0x06241000`-`0x06242800`). Likely a related family
(consecutive RVAs in this region tend to be siblings) but the
specific role isn't pinned down. Candidates for a future
RE wake to characterize.

## Why this writeup exists

Wake 129 wired decomp → analysis-doc cross-links into the
dashboard's Decompiles tab. Wake 130 covered the connection
lifecycle. This wake covers the remaining 15 unreferenced
decompiles in their natural functional grouping so the wake-129
annotation pass picks them all up. After this writeup lands,
the dashboard cross-link density should reach **39/39 (100%)**
— every decomp has at least one analysis doc that mentions
it by stem name.

If the FUN_* uncharacterized cluster gets characterized later,
this doc can be updated with their new names.
