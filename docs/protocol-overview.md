# New World Protocol — State of the Picture

> Master synthesis of what's known about the client↔server protocol,
> tying together state-machine RE, message-catalog inventory,
> wire-format specs, and known open questions. Read this first when
> approaching the project; deeper docs are linked at each section.

## Where the project is

The MVP target is **GameConnection state 14 (`InGame`)** — the client
has accepted V3 RegistrationResponse, completed actor-game-connection
setup, received world / spawn data, and is in-game.

Current actual state of the server's interaction with a real client:

```
State                          Achieved?  Notes
─────────────────────────────  ─────────  ────────────────────────────
0..9 (login / REP setup)         ✅       auth_mock + DTLS + V3 setup work
10 WaitingForREPConnection       ⏳       client retries V3 every ~500ms,
                                          tears down at ~30s. Active blocker.
11 WaitingForActorGameConnection (—)
12 WaitingForSpawnPoint          (—)
13 WaitingForPlayerSpawn         (—)
14 InGame                        (—)      MVP target
```

The state-10 stall has been narrowed to a small set of testable
hypotheses (see § "Open questions" below). Two specific experiments
are queued for the maintainer at a real keyboard.

## Layered protocol map

```
┌──────────────────────────────────────────────────────────────────────┐
│ HTTPS auth (OmniSDK / CloudFront)                                    │
│   server/auth_mock.py — mocks Steam → OmniSDK → AWS-credentials flow │
│   Custom CA at server/certs/newworld_ca.key                          │
│   Client trust: Frida cert-pinning bypass (docs/dtls-trust-bypass.md)│
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ DTLS 1.2 (Javelin REP)                                               │
│   Server cert: server/certs/server.key                               │
│   Standard 6-flight handshake (UDP 24083)                            │
│   server/rep_responder.py — DTLS termination                         │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ GridMate Carrier datagram                                            │
│   [prefix:u16BE][dgramSeq:u16BE][message records...]                 │
│   Prefix: 0x8001 uncompressed | 0x8101 LZ4-compressed body           │
│   Per-channel reliable / unreliable sequencing (ch 0 / 1 / 3 / 4)    │
│   server/javelin/frame.py — parse + marshal                          │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Application-layer message (asymmetric framing per Mixed Nuts)        │
│   C → S  [crc32:4][payload_size:4][correlation_uuid:16][envelope]    │
│   S → C  [message_size:VLQ32][envelope]                              │
│   Envelope: [0x00][0x01][type:u8][optional 2-byte subtype][data]     │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Typed messages                                                       │
│   2,025 InstallRegistrationHook<T> instantiations                    │
│   174 namespaces (Javelin::ClientMessages, Aoi::PlayerManagerTrait,  │
│   Amazon::Hub, MB, ActorMover, etc.)                                 │
│   Full inventory: analysis/message_inventory.md                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Namespace convention (which side of the wire?):** the message
catalog mixes on-wire types with server-side internal-bus types in
the same dispatch system. Heuristic for telling them apart:

- `Javelin::ClientMessagesTrait::*Msg` — **on-wire**, server→client
- `Javelin::ClientMessages::*` — **on-wire**, both directions, per-component
- `MB::*` — **on-wire**, MarshalByValue replicated state
- `ActorMover::*` — **on-wire**, high-frequency movement
- `Aoi::*Trait::*` — **server-side internal**; effects reach clients
  via the corresponding `ClientMessagesTrait` message
- `Amazon::IPC::*` — **not on-wire**, IPC scaffolding

Example pair: `Aoi::PlayerManagerTrait::RequestRejectClientConnectionMsg`
(server-internal request) → server emits
`Javelin::ClientMessagesTrait::PlayerManagerRejectedMsg` (on-wire) →
client handles it. Full table:
[`analysis/message_inventory.md` § "Namespace conventions"](../analysis/message_inventory.md#namespace-conventions-which-side-of-the-wire).

## The state-machine ladder

The GameConnection state field at `gc[+0x1530]` is a 0–14 enum with
human-readable names recovered from the binary's log-format string
table at `0x1484f9ff0`. The advance gates and triggers (mostly
recovered statically; some still TBD):

| State | Name | Advance trigger |
|---|---|---|
| 10 | `WaitingForREPConnection` | `wrapper[+0xa0] == 2`, written by `FUN_145a87010` (`onConnectionSuccess`), invoked by `FUN_146454c00` = PlayerManagerSelfIdentification handler |
| 11 | `WaitingForActorGameConnection` | wrapper substate not 0; transitional |
| 12 | `WaitingForSpawnPoint` | `wrapper[+0xbc8] != 0`, written by `FUN_145a9fa00` invoked by `FUN_14645c660` (another `ClientMessagesTrait` message — likely `State`) |
| 13 | `WaitingForPlayerSpawn` | `wrapper[+0x252] != 0` AND LevelInfoChanged seen — also forced state=13 by `FUN_146446800` directly |
| 14 | `InGame` | reached after Phase 16 SPAWN |

Full detail: [`analysis/state_machine_summary.md`](../analysis/state_machine_summary.md).

## The 22-phase post-V3 sequence

After V3 RegistrationResponse, the server delivers a 22-phase typed
message sequence. Phases 1–11 (seq 0x2..0x24-ish) are in the project's
captured replay; phases 12–22 are not yet captured.

Highlights:

- **Phase 9b (~+310ms)**: `SelfIdentification 0x91(0x17)`, 4 bytes —
  the message that advances state 10→11 (the project's current
  blocker).
- **Phase 11b**: CH1 init burst, 47 units, ~285KB. Mandatory per the
  community team's findings (without it the client freezes at the
  loading circle).
- **Phase 14**: ENTITY DEFS (`0x95` + `0x9d` + `0xa0`).
- **Phase 16**: SPAWN (`0x96` + `0x97`) — should advance state 13→14.

Full detail: [`docs/post-v3-sequence.md`](post-v3-sequence.md).

## What the server already does

The server uses a **replay-and-substitute** strategy, not message-by-
message generation:

1. Accepts V3 RegistrationRequest, sends V3 RegistrationResponse
   (88-byte body, byte-confirmed by Mixed Nuts against a real
   server's response).
2. After V3, queues captured post-V3 messages from
   `info/nw-login-safe-20260502-153840/` (seq 0x2..0x24) for paced
   replay.
3. Patches redacted spans (player UUIDs, session token, character
   name) with the current session's identity via
   `SubstitutionContext`.
4. After the queue drains, sends `PingMsg` (type `0x15d`) heartbeats
   to keep the connection alive past the captured-session length.

Implementation in [`server/rep_responder.py`](../server/rep_responder.py).

## Open questions

### V3 retry blocker (state 10 stall)

Symptom: client accepts V3 (rep.ready flips 0→1) but re-sends V3
every ~500ms anyway and the session tears down at ~30s.

Two leading hypotheses, in order of cheapness to test:

1. **Correlation echo missing.** Mixed Nuts's spec says C→S has
   `[crc32:4][payload_size:4][correlation_uuid:16][envelope]`. The
   server's V3 RegistrationResponse template has a currently-opaque
   `[8B mystery]` field that's zero-filled. If the client expects
   that field to mirror part of the request's correlation_uuid (e.g.
   the first 8 bytes of the request body's "u64/handle" at offset
   6..13), V3 retry would happen because the response's correlator
   never matches the client's expectation. **Test:** ~2-line change
   to `server/javelin/v3_response.py` — populate the mystery field
   with bytes 6..13 of the request prelude. Single live run resolves.

2. **Replay genuinely lacks SelfIdent.** Byte-level audit of the
   captured replay (wake 26) shows NO `00 01 91 17` (community-dump
   Phase 9b SelfIdent signature) anywhere. The only `0x91`-prefixed
   frame is `0x91(0x19)` at seq 0x7, which the community dump labels
   Phase 5 INIT (not SelfIdent). Either (a) the capture is from a
   build where SelfIdent is `0x91(0x19)` and seq 0x7 IS the trigger,
   or (b) the capture genuinely doesn't contain SelfIdent and a fresh
   capture is needed. **Test:** Frida hook on `FUN_146454c00` at
   `0x146454c00` during a replay — if it fires when seq 0x7 arrives,
   case (a); if it never fires, case (b).

### Smaller open questions

- **`FUN_14645c660`'s message name** (the state 11→12 trigger). By
  elimination of `Javelin::ClientMessagesTrait`'s 6 messages,
  most likely the trait's `State` member.
- **`wrapper[+0x252]` writer** (the state 13→14 gate). Not findable
  via immediate-store scan; likely flipped by a memcpy or struct-
  copy inside Phase 14–16 message handlers.
- **Source string of AZ::Crc32 `0xFE476177`** (the carrier destroy
  event). String stripped in release build. Not actively blocking.
- **`PlayerManagerRejectedMsg` handler address.** Not found
  statically; would inform server-side rejection-path testing.

## Local verification

Server-side correctness is verifiable locally without a live game
client. Commands run with strict per-test timeouts so they never hang.

```bash
# One-time setup (Python 3.11 or 3.12; python3-dtls is broken on 3.13+)
python3.12 -m venv .venv
.venv/bin/pip install -q pytest pytest-timeout pyOpenSSL

# Unit suite — 84 tests, ~0.3s. Pre-condition for any patch.
.venv/bin/pytest --timeout=30 --ignore=server/test_client.py

# In-process loopback — full SM_CONNECT_REQUEST → SM_CONNECT_ACK
# round-trip without DTLS. Verifies parser + marshaler + handler.
timeout 30 .venv/bin/python -m server.test_loopback
```

Coverage: parser/marshaler round-trips, replay-substitution span
rules, captured-message validation, chunk reassembly, VLQ32 codec.

`server/test_client.py` is a manual integration script (requires
`python3-dtls`, does a real DTLS handshake to a running stub
server). Excluded from the unit suite because it `sys.exit(1)`s on
import when the optional dep is missing — run it standalone when
you have the dep installed.

**What this doesn't cover:** anything client-side. Confirming "the
client accepted our V3 response" or "state advanced past 10"
requires a live New World client connecting to the stub server —
which needs a Windows host and the non-EAC archived build (per
`tools/client-hooks/README.md`). EAC blocks runtime instrumentation
on the live Steam build. Static-RE + the unit suite is the bound
on what's verifiable from a non-Windows / non-archive environment.

### Running the client in a Mac VM

If you don't have a physical Windows host, the project supports
driving a Windows VM on the Mac. Two backends documented:

- **UTM** (`virtio-gpu`, free): full setup walkthrough at
  [`analysis/proposed_patches/vm_setup_steps.md`](../analysis/proposed_patches/vm_setup_steps.md).
  Caveat: UTM's GPU virtualization may not expose enough D3D11
  features for the renderer to fully initialize — the game can
  crash during CryEngine renderer init before reaching network
  init. See worklog wakes 45-49 for the full diagnostic.
- **Parallels Desktop** (better D3D, $99.99/yr or 14-day free
  trial): pivot proposal at
  [`analysis/proposed_patches/parallels_setup.md`](../analysis/proposed_patches/parallels_setup.md).
  Substantially better D3D virtualization; FAQ-estimated 80%+
  probability of reaching network init vs UTM's 40-60%.

All other infrastructure (SCP-pushing the game directory, SSH
into the VM, `tools/serve_for_vm.sh` Mac-side launcher,
`tools/setup_vm_portproxy.ps1` for unprivileged auth_mock,
hosts-file redirection, CA install, Frida 17 capture) is
backend-agnostic.

## File index

### Maintainer-facing protocol docs

- [`README.md`](../README.md) — project overview, gates, status
- [`docs/connection-flow.md`](connection-flow.md) — full login →
  world-entry sequence from real game logs
- [`docs/post-v3-sequence.md`](post-v3-sequence.md) — 22-phase
  post-V3 message reference (wire format + community findings)
- [`docs/gridmate-reference.md`](gridmate-reference.md) —
  GridMate source deep-read; the Javelin wire-format reference
- [`docs/dtls-trust-bypass.md`](dtls-trust-bypass.md) — Frida
  cert-pinning bypass
- [`docs/aznetworking-reference.md`](aznetworking-reference.md) —
  AzNetworking layer notes
- [`docs/capture-guide.md`](capture-guide.md) — how contributors
  produce captures

### Static-RE findings

- [`analysis/state_machine_summary.md`](../analysis/state_machine_summary.md)
  — the GameConnection state machine map (states, predicates,
  handler addresses, end-to-end protocol diagram)
- [`analysis/message_inventory.md`](../analysis/message_inventory.md)
  — comprehensive catalog of 2,025 typed messages across 174
  namespaces
- [`analysis/v3_request/BODY_DECODE.md`](../analysis/v3_request/BODY_DECODE.md)
  — V3 RegistrationRequest 832-byte body field map
- [`analysis/v3_request/HEADER_DECODE.md`](../analysis/v3_request/HEADER_DECODE.md)
  — V3 RegistrationRequest 11/16-byte header map
- [`analysis/ghidra_findings.md`](../analysis/ghidra_findings.md)
  — earlier Ghidra session structural findings (DTLS init, V3
  vtable shape, etc.)
- [`analysis/autonomous_worklog_through_253.md`](../analysis/autonomous_worklog_through_253.md)
  + [`analysis/autonomous_worklog.md`](../analysis/autonomous_worklog.md)
  — chronological narrative of the autonomous static-RE session
  (multiple wakes; useful for "how did we get here" questions). The
  archive holds wakes 1-253; the active worklog holds wakes 254+.
  Split happened at wake 261.

### Tools

- [`tools/ghidra`](../tools/ghidra) — CLI wrapper for headless
  decompile + script execution
- [`tools/ghidra_scripts/README.md`](../tools/ghidra_scripts/README.md)
  — index of 11 analysis scripts
- [`tools/build_message_inventory.py`](../tools/build_message_inventory.py)
  — regenerator for `analysis/message_inventory.md`
- [`tools/client-hooks/`](../tools/client-hooks/) — Frida hook
  scripts for live capture / runtime inspection

### Server implementation

- [`server/auth_mock.py`](../server/auth_mock.py) — HTTPS auth
  gateway mock
- [`server/rep_responder.py`](../server/rep_responder.py) — DTLS-
  terminating Javelin REP server (the game server stub)
- [`server/javelin/frame.py`](../server/javelin/frame.py) —
  carrier-record parse / marshal
- [`server/javelin/v3_request.py`](../server/javelin/v3_request.py) —
  V3 request parser
- [`server/javelin/v3_response.py`](../server/javelin/v3_response.py) —
  V3 response encoder
- [`server/javelin/replay_store.py`](../server/javelin/replay_store.py) —
  loads captured messages from `info/nw-login-safe-*`
- [`server/javelin/replay_substitution.py`](../server/javelin/replay_substitution.py) —
  patches redacted spans with current session identity

### Captures

- [`info/nw-login-safe-20260502-153840/`](../info/nw-login-safe-20260502-153840/)
  — the canonical login-through-state-53 capture, redacted
- [`info/community_22_phase_in_game_dump.txt`](../info/community_22_phase_in_game_dump.txt)
  — community-shared post-V3 22-phase RE notes
- [`info/typeregistry.json`](../info/typeregistry.json) — runtime-
  extracted type registry (3,487 named types with handler vtable
  addresses + Marshal/Unmarshal opcode prefixes)

## What "good progress" looks like from here

Three levels of advance, ordered by effort:

1. **Resolve V3 retry** (small, fast). Run the correlation-echo
   experiment in `v3_response.py`. If it works → state-10 advances
   immediately.

2. **Extend replay coverage past seq 0x24** (medium, needs new
   captures). The captured session covers Phase 1 through partway
   into Phase 11; Phases 12–22 need additional capture sessions to
   fill in. Particularly: the CH1 init burst at Phase 11b (~285KB
   over 47 units) is mandatory per community team findings.

3. **Implement Phase 16 SPAWN** (larger, requires runtime
   verification). State 13→14 triggers off `wrapper[+0x252]`, which
   we believe gets set by Phase 14–16 messages. Once those phases
   are delivered correctly, the project hits MVP target (state 14
   = `InGame`).

The path from "today" to "MVP" is now mostly bounded — the static-RE
work has surfaced specific testable next steps rather than open-ended
mysteries.
