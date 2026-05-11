# Codec ↔ server integration status

> Snapshot of how much of the codec library
> (`server/javelin/*`, **40 / 40 captured type-IDs covered** as of
> wake 109, plus a central dispatcher in
> [`server/javelin/dispatch.py`](../server/javelin/dispatch.py))
> is currently consumed by the runtime server-side code.
> Originally compiled wake 82; codec-side counts refreshed wake
> 153; integration arc updates added at wake 239 (covering
> the phase-2D work shipped at wakes 204/208). The integration
> tl;dr below ("mostly decoupled") still holds for the **default
> code path** — `rep_responder.py` continues to drive runtime
> from raw replay bytes — but the dispatcher is now wired in
> with two default-off feature flags that route 0x15d heartbeats
> through it. See "Post-wake-153 update" below for the full arc.

## Post-wake-153 update: phase-2D integration foundation (wakes 157-208)

A 6-step arc closed the rep_responder ↔ dispatcher integration
gap behind feature flags. From wake-227 retrospective:

| Wake | Step |
|---|---|
| 157 | Inbound shadow-decode (every received record routes through dispatcher at debug level, no behavior change) |
| 158 | 9-test lockdown of the inbound shadow path |
| 187 | Outbound encode-validation probe (startup-time byte-equality check on cached 0x15d) |
| 188 | 8-test lockdown of the outbound probe |
| 204 | **Actual heartbeat emission swap** behind `heartbeat_use_dispatcher` flag (default off, byte-equivalent to captured replay) |
| 208 | **Counter-advance extension** behind `heartbeat_advance_counter` flag — mutates `_heartbeat_decoded.counter / nonce` per call so dispatched heartbeats genuinely progress |

The wake-204/208 flags compose:
- `off / off` (default) = captured replay path, identical to pre-wake-157 behavior.
- `on / off` = dispatcher-encoded emission, byte-identical to captured replay.
- `on / on` = dispatcher-encoded emission with counter advancement
  per call (closest to a real server).

All three modes are pinned by tests; real-GPU validation is the
next step (current blocker — see
[`MORNING_BRIEF.md`](MORNING_BRIEF.md) for the runtime-host
status as of wake 70 + the wake-227 retrospective for the
current static-RE state).

What this means for the original tl;dr:
- "**mostly decoupled**" — still accurate for the default off/off
  mode. The codec library remains a schema + invariant test bed
  + future-emission scaffolding for that path.
- The shadow-decode + probe paths (157/187) consume the
  dispatcher even at the default code path, but only for
  validation/logging; no behavior change.
- When `heartbeat_use_dispatcher = True` is flipped, the
  heartbeat emission path **does** route through the codec
  library (specifically `heartbeat_15d` via the central
  dispatcher).

## tl;dr

The codec library and the server (`server/rep_responder.py`)
are **mostly decoupled**. The responder uses **raw replay-message
bytes** (with redaction-span substitution for live values) for
all post-V3 traffic. Only the V3 RegistrationRequest / Response
codecs are integrated into the runtime path; everything else is
"shipped but not wired."

This is **largely correct for replay fidelity**: forwarding
captured bytes verbatim is the safest way to satisfy a strict
client when the captured session was known to succeed. The
codec library serves three other purposes that the responder
doesn't currently exercise:

1. **Protocol reverse-engineering** — round-trip tests verify
   our byte-level understanding.
2. **Cross-codec invariant validation** — catches drift between
   the server's outputs and the documented runtime invariants.
3. **Emulator emission** — when a future server needs to generate
   fresh messages (multi-session, dynamic state, etc.) rather
   than replay a single capture.

(3) is the "real" integration gap. Today's responder cannot
serve a session whose values diverge from the captured replay
beyond the redacted-span substitutions.

## What the responder currently consumes

| Module | Use | Path |
|---|---|---|
| `frame.py` | parse incoming Carrier datagrams + records (low-level wire framing) | runtime |
| `dispatch.py` (added wake 157) | central dispatcher — shadow-decodes inbound records (default), validates outbound 0x15d at startup (default), emits outbound 0x15d when `heartbeat_use_dispatcher=True` (wake 204+) | runtime |
| `replay_store.py` | load the captured `messages-redacted.txt` and surface `ReplayMessage` objects | replay setup |
| `replay_substitution.py` | fill XX redacted spans with live session_uuid / persona_id values | replay emission |
| `v3_request.py` | parse the client's V3 RegistrationRequest | runtime |
| `v3_response.py` | encode the server's V3 RegistrationResponse | runtime |
| `wire.py` | `encode_vlq32`, `chunk_replay_payload` for the chunked-replay path | replay emission |

Total: **7 of the 23+ javelin modules** are imported by
`rep_responder.py` (was 6 pre-wake-157; the dispatcher landed
during the phase-2D arc).

## What's shipped but unused at runtime

All 22 typed codecs **except** `v3_response.py` and
`v3_request.py` are not currently consumed by the responder.
Specifically:

- All R-direction codecs (`session_message_a4`,
  `session_clock_beacon`, `heartbeat_15d` ping,
  `session_identity_beacon`, `init_message_18a6`,
  `level_descriptor_663`, `identity_blob_8e6`,
  `vivox_config_1067`, `asset_count_table_ca4`,
  `asset_blob_16a0`, `result_token_136a`, `result_token_1097`,
  `handshake_blob_76`, `world_data_blob_65c`)
- All W-direction codecs (`session_subkey_1a59`,
  `identity_fingerprint_5b2`, `action_history_635`,
  `permission_bitmap_a95`, `receipt_handshake_9fc`,
  `keybinding_config_12f6`)
- The generic `subkey_beacon` (covers 14 W-direction types)
- The two AzCore-style codecs (`level_info_changed`,
  `self_ident`)

The captured-bytes path emits these messages verbatim (modulo
substitutions); their typed codecs are only exercised by the
test suite, not by the runtime.

## Where each codec WOULD be useful in the responder

| Codec | If integrated, would let the responder... | Priority |
|---|---|---|
| `init_message_18a6` (R) + `session_subkey_1a59` (W) counter pair | Drive the 0x18a6→0x1a59 counter dance from session state rather than replay; advance counter only on observed ack | **high** — load-bearing runtime invariant |
| `heartbeat_15d` ping/ack pair | Generate fresh ping nonces and validate ack echoes against them | **high** |
| `session_clock_beacon` (`0x14f`) | Mint fresh session-clock beacons with a real-time clock value | medium |
| `session_identity_beacon` (`0x1b88`) | Re-broadcast the periodic identity beacon (currently relies on captured replay) | medium |
| `level_descriptor_663` | Customize level/zone for a fresh session | medium |
| `vivox_config_1067` | Override the captured Amazon NA Vivox config with private-server config | low (constant strings work today) |
| `keybinding_config_12f6` (W decode) | Validate and log incoming client keybindings | low |
| `permission_bitmap_a95` (W decode) | Inspect / log client-reported permission bitmap | low |
| `receipt_handshake_9fc` (W decode) | Validate the 0x8e6→0x9fc hash echo (catch invariant violations) | low |
| `world_data_blob_65c` | Build a fresh WORLD DATA blob for non-captured zones (would need handler-side info too) | future |
| AzCore-style (`level_info_changed`, `self_ident`) | ~~Already deferred per worklog wakes 51-63; needs static-RE~~ — **partly resolved at wake 112**: state-10 gate found (`wrapper[+0xa0] == 2`), 0x5d1 trigger identified. Runtime emission still gated on real-GPU validation per phase-2D arc. | now ready for runtime |

## What integration would look like, concretely

Today's responder code (paraphrased):

```python
# replay loop, captured-bytes path
msg = self.replay_queue.pop(0)
body_bytes = (
    self.substitution_ctx.apply(msg) if msg.has_redaction else msg.body
)
self.send_app(self.wrap_envelope(body_bytes))
```

A counter-coupled future variant for 0x18a6/0x1a59:

```python
# server side: emit the next 0x18a6 with the live counter
from server.javelin import InitMessage18A6, encode
msg = InitMessage18A6(
    first_uuid_half=self.session_state.subkey_upper_8,
    session_uuid_lower=self.session_state.session_uuid[8:],
    second_id=self.session_state.metadata_block_second_id,
    counter=self.session_state.next_18a6_counter,
)
self.send_app(self.wrap_envelope(encode(msg)))

# client side: validate the 0x1a59 ack matches
from server.javelin import session_subkey_1a59
ack = session_subkey_1a59.decode(payload)
assert ack.counter == self.session_state.next_18a6_counter
self.session_state.next_18a6_counter += 1
```

This kind of state-driven emission is what the codec library
unlocks once the responder is ready to leave the captured-bytes
path. Until then the codecs serve as **a documented schema +
invariant checker** — no integration work needed for replay
fidelity itself.

## Recommendation

**Do not eagerly integrate codecs into the responder.** The
captured-bytes + substitution path is correct for the current
scope (single-session replay against a known-good capture). The
codec library should be viewed as:

- A **schema** for protocol semantics (the source of truth for
  byte layout)
- An **invariant test bed** (tests catch drift early)
- A **future emission scaffolding** (when multi-session or
  dynamic state becomes a goal)

The right time to wire codecs into the responder is when the
project graduates from "replay one captured session" to
"emulate multiple fresh sessions." At that point the codec
library is ready to slot in directly; the helpers (e.g.
`make_subkey_beacon` from wake 81) are already shaped for
that use case.

## Files reviewed

- `server/rep_responder.py` (1064 lines, runtime DTLS responder)
- `server/javelin/replay_substitution.py` (XX → live-value mapping)
- `server/javelin/replay_store.py` (capture parser)
- `server/javelin/v3_request.py` + `v3_response.py` (the
  integrated pair)
- `server/javelin/wire.py` (VLQ32 + chunked-replay helpers)

Library inventory: see `analysis/codec_coverage.md` for the
type-ID → codec module map.
