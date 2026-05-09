# Post-V3 Message Sequence Reference

> Synthesizes the 22-phase post-V3 server→client message sequence from
> `info/community_22_phase_in_game_dump.txt` (community-shared RE
> notes from a separate effort) with the static-RE findings in
> `analysis/state_machine_summary.md`. Source addresses cited as RVAs
> from image base `0x140000000` against the live Steam build.

## What this document is

After V3 RegistrationResponse is accepted, the server must drive the
client through a 22-phase sequence of typed messages on the Carrier
data channels (`ch=0` mostly, with a `ch=1` burst and `ch=3` keepalive
ACKs) before the client reaches `state 14 = InGame`. Each phase has a
specific message-type byte, expected size envelope, and inter-phase
delay.

Most of this sequence has already been captured in
`info/nw-login-safe-20260502-153840/messages-redacted.txt` and is
replayed by `server/rep_responder.py:_pump_replay`, but the captured
session covers seq 0x2..0x24 only and the project still needs more
in-world traffic to extend the replay coverage. This doc is the
human-readable index of the protocol shape.

## Wire format recap

DTLS Application Data → GridMate Carrier datagram → NW protocol
messages, wrapped as:

```
[prefix:u16BE]              0x8001 uncompressed | 0x8101 LZ4-body
[dgramSeq:u16BE]            starts at 2 (S→C); per-stream monotonic
[message records...]        each prefixed with header flags
```

Message header flag bits (carrier layer, see
`server/javelin/frame.py`):

| Flag | Bit | Meaning |
|---|---|---|
| `MF_RELIABLE` | 0x01 | Requires ACK; relSeq present in header |
| `MF_CHUNKS` | 0x04 | Chunks countdown u16BE present |
| `MF_SEQUENTIAL_ID` | 0x08 | seq is implied prev+1 (omit from header) |
| `MF_SEQUENTIAL_REL_ID` | 0x10 | relSeq is implied prev+1 |
| `MF_DATA_CHANNEL` | 0x20 | channel u8 follows |
| `MF_CONNECTING` | 0x80 | handshake-phase marker |

NW-protocol payload (inside ch=0/ch=1 carrier records):

```
[PackedSize_LE(innerLen)]   LE-VLQ size prefix (0xxxxxxx 1B, 10xxxxxx 2B, ...)
[0x00] [0x01]               constant marker
[type:u8]                   message type byte
[data...]                   type-specific body
```

Some messages use a sub-type extension:
`[type:u8] = (subtype & 0x3F) | 0x80; [(subtype >> 6) & 0xFF]`
(e.g. SelfIdentification is `0x91, 0x17` ⇒ subtype 0x17).

### Application-layer C↔S framing (Mixed Nuts spec)

The DTLS-decrypted application bytes are asymmetric between
directions. Per a 2026-05-07 spec confirmation from a separate
reverser:

```
C → S  [crc32:u32 BE][payload_size:u32 BE][correlation_uuid:16][typed_envelope...]
       crc32 covers (correlation_uuid + typed_envelope)
       payload_size is len(correlation_uuid + typed_envelope) = 16 + len(envelope)

S → C  [message_size:VLQ32][typed_envelope...]
       no CRC, no correlation echoed at the framing layer.
```

The 16-byte `correlation_uuid` matches what the community dump
(`info/community_22_phase_in_game_dump.txt`) decomposes as
`session:8B + peer:8B`. Same wire layout, different naming
conventions across reversers.

**Implication for V3 RegistrationResponse:** the asymmetry means
the server's response framing is purely `[VLQ32 size][envelope]`
— matching what `server/javelin/v3_response.py` already produces.
The correlation_uuid is **not** echoed at the framing layer.
**Open question** (not yet tested): does the response's typed
envelope need to include the correlation_uuid in one of its fields
(e.g. the 8-byte "mystery" field at offset +8 of the V3
RegistrationResponse body) to satisfy the client's request-response
matching? See `analysis/autonomous_worklog.md` wake 27 for the
reasoning.

## The 22 phases

All delays are relative to the prior phase. Sizes vary by retail vs.
test-39 build. `dgramSeq` increments per datagram regardless of
channel.

**Codec column**: when we've shipped a Python codec for the
type, the row links to the module under `server/javelin/`.
Codecs round-trip vs the captured bytes; encoders are usable
for emulator emission. Inventory of all known type-ids and
their byte-level structure: `analysis/replay_message_inventory.md`.

| # | +Δ | Type | Channel | Size | Notes | Codec |
|---|---|---|---|---|---|---|
| 1 | 0ms | VERSION `0x03` | 0 | 89B | first post-V3 | [`v3_response.py`](../server/javelin/v3_response.py) |
| 2 | 50ms | HEARTBEAT `0x9d` | 0 | 13B | | [`heartbeat_15d.py`](../server/javelin/heartbeat_15d.py) (R+W) |
| 3 | 80ms | INIT `0x8a` + `0xbe` | 0 | 154B | grouped, 1 carrier msg | [`handshake_blob_76.py`](../server/javelin/handshake_blob_76.py) (both 76B) |
| 4 | 140ms | WORLD DATA `0x9c` | 0 | 12.7KB | chunked, 12 segs ~1115B each; type 0x65c carries the same `handshake_blob_76` shared_trailer at offset +64 — see inventory | — |
| 5 | 200ms | INIT `0x91(0x19)` + small `0xa4` | 0 | 21B | bundled into Phase 4 tail. `0x91(0x19)` = type 0x651 (a 4-byte type-header-only signal). | small `0xa4` → [`session_message_a4.py`](../server/javelin/session_message_a4.py) |
| 6 | 220ms | SESSION `0xa4` large | 0 | 75B / 195B retail-shape | | [`session_message_a4.py`](../server/javelin/session_message_a4.py) |
| 7 | 250ms | HEARTBEAT `0x8f` | 0 | 13B | type 0x14f session-clock beacon | [`session_clock_beacon.py`](../server/javelin/session_clock_beacon.py) |
| 8 | 280ms | `0xa6` + `0x88`x2 | 0 | ~120B | grouped | `0xa6` → [`init_message_18a6.py`](../server/javelin/init_message_18a6.py); `0x88` → [`session_identity_beacon.py`](../server/javelin/session_identity_beacon.py) |
| 9 | 300ms | `0x88` + small `0xa4` | 0 | ~60B | grouped | as above |
| **9b** | **310ms** | **SelfIdentification `0x91(0x17)`** | **0** | **4B¹** | **state 10→11 trigger** | [`self_ident.py`](../server/javelin/self_ident.py) (encoder, not yet wired) |
| 10 | 320ms | `0x88` x20 | 0 | ~840B | one carrier datagram | [`session_identity_beacon.py`](../server/javelin/session_identity_beacon.py) |
| 11 | 400ms | SESSION AA `0xaa` | 0 | 29B | | — |
| 11a | 420ms | `0xa4` + WORLD SPAWN `0xa3` + HB `0x8f` | 0 | ~130B | retail dseq=26; `0xa3` = type 0x663 LevelDescriptor | `0xa3` → [`level_descriptor_663.py`](../server/javelin/level_descriptor_663.py) |
| 11b | 460ms | CH1 init burst, 47 units | 1 | 285KB | paced 3/batch w/ 300ms gaps; **mandatory** | — |
| 12 | 1500ms | SESSION AE `0xae` (trail=`0x02`) | 0 | 22B | | — |
| 13 | 3000ms | SESSION AE `0xae` (trail=`0x00`) | 0 | 22B | | — |
| 14 | 450ms | ENTITY DEFS `0x95` + `0x9d`-large + `0xa0` | 0 | ~2.5KB | | `0x9d`-large → [`heartbeat_15d.py`](../server/javelin/heartbeat_15d.py) |
| 15 | 800ms | GAME DATA `0xb3` + VIVOX URL `0xa7` | 0 | ~3KB | `0xa7` = type 0x1067 Vivox voice config | `0xa7` → [`vivox_config_1067.py`](../server/javelin/vivox_config_1067.py) |
| 16 | 1200ms | SPAWN `0x96` + `0x97` | 0 | ~160B | spawn-position floats + companion result token; documented inline in inventory | — |
| 17 | 1400ms | continuous `0x08` entity-state stream | 0 | varies | ~30/s; 24 byte-identical 46407-byte snapshots are pure transport-layer resends — see inventory | — |
| 18 | 2000ms | Player data `0xa0` burst #1 | 0 | 234KB | paced, 210 segments |
| 19 | 800ms | Player data `0xa0` burst #2 | 0 | 171KB | paced, 154 segments |
| 20 | 7000ms | Entity `0xac` chunked | 0 | 2.6KB | |
| 21 | continuous | Heartbeats `0x8f`/`0x9d` alternating @ 500ms | 0 | 13B | |
| 22 | 10s+ | Continuous ch0 loop `0x94`/`0xa5`/`0xac`/`0x9a` | 0 | varies | |

¹ **Phase 9b size note:** the 4-byte figure dates from before
wake 51's wire-format work. Static-RE on the SelfIdent handler
(`FUN_146454c00`) shows it reads from a 56-byte in-memory struct
(see `analysis/clientmessagestrait_wire_formats.md`), so either
the wire body is much larger than 4 bytes, OR the 4-byte body is
a trigger/signal that prompts the client to source identity from
session state. Unresolved without a captured Phase 9b — the
hypothesized 21+ byte encoder lives at `server/javelin/self_ident.py`
but is not yet wired into emission.

## Server↔client counter pairs

Replay-mining (worklog wakes 66-78) surfaced several
**counter-coupled R/W pairs** where the server emits a message
of one type and the client immediately replies with another type
echoing or incrementing a counter. Server-side replay code that
re-emits the R messages must mirror these exact counter
sequences to satisfy the client's request-response matching.

| R type (server → client) | W type (client → server) | Counter behavior | Codecs |
|---|---|---|---|
| `0x18a6` (40 B) | `0x1a59` (45 B) | Server emits 0x18a6 with a u8 counter; client replies 0x1a59 with the same counter. Captured sequence: 1 → 2 → 3 → 4. The 16-byte subkey in 0x1a59's payload is identical to the first 16 bytes of 0x18a6's body (both encode `[first_uuid_half:8][session_uuid_lower:8]`). | [`init_message_18a6.py`](../server/javelin/init_message_18a6.py) ↔ [`session_subkey_1a59.py`](../server/javelin/session_subkey_1a59.py) (R/W pair, cross-codec test) |
| `0x15d` ping | `0x15d` ack | Server emits `HeartbeatPing15D` (12 B) with `(counter, nonce)`; client replies `HeartbeatAck15D` (36 B) **wrapping the ping body verbatim** at offset +0x18 in the ack. Server replay can verify the ack's `echoed_ping` byte-matches the sent ping. | [`heartbeat_15d.py`](../server/javelin/heartbeat_15d.py) (single module, R+W) |
| `0x14f` periodic | (none observed) | Server emits a 12-byte session-clock beacon; the captured replay shows 4 of these but no W reply. The clock value (`0x0b888d68`) matches `mystery8`'s first 4 bytes in the V3 RegistrationResponse — same session clock baseline. | [`session_clock_beacon.py`](../server/javelin/session_clock_beacon.py) |
| `0x8e6` blob | `0x9fc` echo | Server emits a 42-byte 0x8e6 with a 16-byte `opaque_blob`; client's 0x9fc reply (102 B) carries that same 16-byte hash at its tail. Cross-codec invariant for replay fidelity. | [`identity_blob_8e6.py`](../server/javelin/identity_blob_8e6.py) ↔ no codec yet for 0x9fc |

The 0x1a59↔0x18a6 pair is the most explicitly counter-coupled.
Server-side emission for an emulator must:
1. Emit 0x18a6 with `counter=N` (`init_message_18a6.encode`)
2. Wait for 0x1a59 with matching `counter=N`
3. Emit 0x18a6 with `counter=N+1` (...)

If the server sends `counter=N+1` before receiving the
client's ack at `counter=N`, the client may reject the message
or reset its state. The captured replay shows clean monotonic
1→2→3→4 increments with no gaps, suggesting the client
acknowledges promptly and the server only increments on receipt.

## Cross-link to the GameConnection state machine

From `analysis/state_machine_summary.md`:

| State | Name | Phase that advances it |
|---|---|---|
| 10 | `WaitingForREPConnection` | **Phase 9b** (`0x91(0x17)` SelfIdentification) → state 11 |
| 11 | `WaitingForActorGameConnection` | one of Phases 10–11 (handler `FUN_14645c660` sets `wrapper[+0xbc8] = 1`; identity TBD) |
| 12 | `WaitingForSpawnPoint` | **Phase 14 / 15** (LevelInfoChangedMsg via `FUN_146446800`) → forces state 13 |
| 13 | `WaitingForPlayerSpawn` | **Phase 16** (`SPAWN 0x96/0x97`) — gates on the wrapper flag at `+0x252` written by some Phase 16-or-later message |
| 14 | `InGame` | reached after Phase 16 if all gates pass |

## C→S after handshake

The community dump also documents the inverse direction:

```
LZ4-compressed 0x8101 datagrams:
  [crc32:4B][size:4B][session:8B][peer:8B][0x0001:2B][type:1B][data...]
  Inner: [prefix:1B][entity_hash:8B][session_id:8B][...]
```

Server echoes `entity_hash + session_id` in template responses (14
type mappings). Fire-and-forget C→S types: `0x82 0x83 0x9a 0x9d 0x94
0xa6 0xb0 0xb4 0xb9 0xbd 0xbf`.

## Wire-format gotchas

Captured from the community team's testing — these are landmines our
server replay must avoid:

- **NO post-connect extra byte.** Adding any byte after `[ch:u8]`
  shifts the NW payload by one and the server emits "server data
  error" then disconnects.
- **`flags=0x88` (`MF_CONNECTING|MF_SEQUENTIAL_ID`) does NOT also
  set `MF_SEQUENTIAL_REL_ID`.** relSeq must be written. Missing it
  → BAD_PACKETS.
- **Real-server `SM_CONNECT_ACK` shape `0x21/relSeq=0` instant-
  disconnects on the test-39 path.** The form that works is
  `flags=0xa0/relSeq=0xffff` (test-39 form). Documented in
  `server/rep_responder.py:send_connect_ack`.
- **`0xa3 WORLD SPAWN` map path must be exactly
  `"coatlicue/NewWorld_VitaeEterna"`.** Truncation → infinite
  loading circle.
- **`0x8001` prefix is safe S→C** (real server uses `0x8101` LZ4 for
  ~59% of datagrams, but uncompressed works fine).
- **CH1 `unit[0]` (the ~47KB init burst) is mandatory.** Without it
  the client freezes at the loading circle. NW_HYBRID_INIT
  bisection: 67 units → loading circle, 68 units → black screen
  (game world).

## Static-RE handler addresses

Cross-references between phase types and the binary's handler
functions (recovered statically; see `analysis/state_machine_summary.md`
for the methodology):

| Phase / Type | Handler | Address (RVA) |
|---|---|---|
| Phase 9b SelfIdentification `0x91(0x17)` | `PlayerManagerSelfIdentification` | `FUN_146454c00` |
| (Phase 10/11) substate=2 writer | `onConnectionSuccess` (wrapper) | `FUN_145a87010` |
| (Phase 11→12) wrapper substate writer | `markSpawnPointReady` | `FUN_145a9fa00` (called from `FUN_14645c660`) |
| (Phase 14/15) LevelInfoChanged | `LevelInfoChanged` handler | `FUN_146446800` |
| (Phase 16) SPAWN handler | TBD | TBD |
| Carrier destroy-flush flag writer | flush trigger | `FUN_140fb3560:452` (CRC `0xFE476177`) |
| Carrier tick thread | `TransportLayerGridMateTickThread` | `FUN_146b3c250` |

## Known stall points (community-team observations)

The community team documented their stall point past where this
project currently sits:

> On our path the equivalent is GCW state 13 (WaitingForPlayerSpawn).
> Gate is: SelfIdentification `0x91(0x17)` → handler `sub_1464537E0`
> → StackConfig `"javelin.NWLDebug-virtual-slice-mode"` →
> CreateVirtualSlicesFromStream `(sub_1416A14E0)`. `isMasterPlayer=0`
> from dispatch context `sub_145A85940 case 0` blocks the spawn. We
> bypass it with a DLL patch that forces `isMasterPlayer=1` + a
> predicate-vtable patch on the bundle handler at `0x1717fc0`.

In our binary's analysis:

- `sub_145A85940` lives inside `FUN_145a85760` at offset `+0x1e0`
  (Ghidra didn't auto-create a function at the inner address). This
  is in the wrapper-class neighborhood; worth an isolated decomp
  if/when this project reaches the same stall.
- `sub_1464537E0` would be `FUN_1464537e0` in our naming — likely
  the SelfIdent dispatcher one level up from `FUN_146454c00`.
- `sub_1416A14E0` would be `FUN_1416a14e0` — the
  CreateVirtualSlicesFromStream entry.
- The `0x1717fc0` bundle-handler vtable address is a runtime heap
  address from their build; not directly transferable without
  rebasing.

## Implementation references in this repo

| Implementation | File | Notes |
|---|---|---|
| V3 RegistrationRequest parser | `server/javelin/v3_request.py` | |
| V3 RegistrationResponse encoder | `server/javelin/v3_response.py` | 88-byte body template based on captured session |
| Carrier framing parse + marshal | `server/javelin/frame.py` | Implements all 6 message-flag bits |
| Replay store | `server/javelin/replay_store.py` | Loads captured messages from `info/nw-login-safe-*` |
| Replay substitution | `server/javelin/replay_substitution.py` | Patches redacted spans with current session identity |
| REP responder main loop | `server/rep_responder.py` | DTLS termination + V3 handling + replay pump |

## What this project is currently missing

Per `analysis/autonomous_worklog.md` end-of-day-1 summary:

- **The replay path covers seq 0x2..0x24** — that's roughly Phase
  1 through partway into Phase 11. Phases 12–22 are not in the
  captured replay and therefore not delivered. New captures with
  in-world traffic would extend coverage.
- **Phase 9b (SelfIdentification) wire format** — type `0x91(0x17)`
  4-byte body — should be reconstructable from captures and
  matched against `FUN_146454c00`'s handler reads (mapped in
  `state_machine_summary.md`).
- **Phase 11b CH1 init burst** is the largest single gap (47
  units, ~285KB). This is what the community team identified as
  mandatory.
- **State 13 stall** the community team hit — ours is earlier
  (state 10) so this hasn't surfaced yet, but expect it once we
  push past Phase 9b.

## Open questions still worth runtime data (low priority now)

These can be answered from a Frida session if the static work
hasn't surfaced them by then. Listed in `state_machine_summary.md`
§ 8 and the worklog's end-of-day summary:

- The PlayerManagerRejected handler (the failure-path counterpart
  to SelfIdentification).
- The source string of AZ::Crc32 `0xFE476177` (the carrier
  destroy event id).
- The exact wrapper class field that gates state 13→14
  (`wrapper[+0x252]`).

The 22-phase sequence above suggests the answer to the third one
is buried in Phase 14–16 (LevelInfoChanged → SPAWN) message
processing.
