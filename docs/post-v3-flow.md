# Post-V3 wire flow — current understanding

This is the canonical reference for **what happens after the DTLS handshake
completes**, up to (and including) the state-10 wall that's the active blocker.
For the high-level user-side flow (Steam auth → world selection → REP IP),
see [connection-flow.md](connection-flow.md). For the wire framing primitives
(envelope, channels, ack vectors, MF_* flags), see
[gridmate-reference.md](gridmate-reference.md).

> **Source of truth for what's *currently* deployed and what's broken:**
> [next-session.md](next-session.md). This doc captures the durable
> understanding; the handoff captures the rolling state.

---

## 0. Layering (top-down)

```
+-----------------------------------------------------------+
|  Application: Javelin typed messages (RegistrationRequestV3,
|  PingMsg, TimeSynchMsg, StateBundles, RPCs, ...)
+-----------------------------------------------------------+
|  Carrier: per-record reliability + per-channel sequencing.
|  Channel 0..2 = data; channel 3 = system messages
|  (SM_CONNECT_REQUEST/ACK, SM_CT_ACKS, SM_DISCONNECT, ...).
+-----------------------------------------------------------+
|  Envelope: 4 bytes — `[0x80|0x81] 0x01 [seq:u16 BE]`.
|  Bit 0 of byte 0 = encrypted/compressed flag (always 0x80
|  on this code path). seq is a per-direction monotonic u16.
+-----------------------------------------------------------+
|  DTLS 1.2 record layer (AES256-GCM-SHA384).
+-----------------------------------------------------------+
|  UDP.
+-----------------------------------------------------------+
```

Wire format details: [gridmate-reference.md §1–§3](gridmate-reference.md).

---

## 1. DTLS handshake

Self-signed ECDHE-RSA cert; the Frida `verifyField` null patch on
`FUN_145dce750` tells the client to accept it
([dtls-trust-bypass.md](dtls-trust-bypass.md)). After CipherSpec change the
Carrier sees a plain UDP API and doesn't know DTLS is involved
(`SecureSocketDriver.h:105–107`).

---

## 2. Connect-ack loop (`SM_CONNECT_REQUEST` ↔ `SM_CONNECT_ACK`)

Per `Carrier.cpp:626–639`, the first user-level packet after DTLS is the
`SM_CONNECT_REQUEST` (sysmsg id 1) on **channel 3**. The client retries
this every ~500 ms, **and the body grows by one trailing `0x01` byte per
retry**:

```
env_seq=2  [sysmsg=1 payload=0000000501]                     [sysmsg=6 payload=2006]
env_seq=3  [sysmsg=1 payload=000000050101]                   [sysmsg=6 payload=2006]
env_seq=4  [sysmsg=1 payload=00000005010101]                 [sysmsg=6 payload=400001000006]
...
```

Each datagram bundles an `SM_CT_ACKS` (sysmsg id 6) with whatever the client
last received from us. The growth-by-`0x01` is a Carrier internal — appears
to be a retry-count tag. The server replies with `SM_CONNECT_ACK` (sysmsg
id 2) on channel 3. Several reply shapes were tried during bring-up (mirror,
empty, echo, v0, v3_min, v3_full, dynamic) — see `ACK_VARIANTS` in
`server/rep_responder.py`. The Mixed Nuts shape (flag 0x21, rel_seq=0) is
what we ship in production.

---

## 3. V3 RegistrationRequest arrives

Once the connect-ack loop closes, the client's per-tick state-10 dispatcher
takes BRANCH B (`gw[0x160]==1`) and queues a `RegistrationRequestV3Msg`
(typeIndex 0x13, body 0x470 bytes). It lands as a single Carrier record
with `flags & MF_NO_LENGTH (0x40)` set
([analysis/v3_request/HEADER_DECODE.md](../analysis/v3_request/HEADER_DECODE.md)).

`server/javelin/v3_request.py::parse_v3_request` decodes it into a
`V3RegistrationRequest` dataclass. The fields we currently extract:
`session_uuid` (the 32-char hex form is also the *session token* the
client expects back at vt[0x110]), `persona_id`, and the tail
`character_display_name` slot. See
[analysis/v3_request/BODY_DECODE.md](../analysis/v3_request/BODY_DECODE.md).

> **First-attempt edge:** the live first-attempt body is 835 B, not the
> strict 832 B `parse_v3_request` accepts. `_lenient_v3_extract` falls back
> to a regex scan for the persona-id + session-UUID. Subsequent retries are
> always 832 B and parse cleanly.

---

## 4. V3 RegistrationResponse + piggyback ACK

We reply with a `RegistrationResponseMsg` (typeIndex 0x3, body 88 B) on
**channel 0**, wrapped as `[VLQ32 size][typed envelope]`. Wrap parameters
are configurable (`--v3-resp-flag`, `--v3-resp-channel`,
`--v3-resp-subheader`); the production combo is `flag=0x21, ch=0` matching
the Mixed Nuts working sample.

The `session_token` field of the response is the **32-char hex form of the
client's `session_uuid`** echoed back. The client's
`vtable[0x110]` setter (mis-named "SetVersionString" in the decomp) stores
exactly this string when the response deserializes successfully.

**Bundled in the same datagram**: a Carrier-level `SM_CT_ACKS` record on
channel 3 (`build_sm_ct_acks_record` in `server/rep_responder.py`)
acknowledging the inbound envelope-seq range we've received. This is the
fix that broke the V3 retry storm in PR #5. As of [commit a93e0b0]
the ACK now rides on **every outbound carrier datagram** (replay records,
chunked first chunks, post-replay heartbeats), not just the V3 reply, so
post-V3 reliable client traffic keeps getting acked.

---

## 5. Replay window (`seq 0x2..0xb0`)

Immediately after the V3 reply ships, `_start_replay()` queues every
R-direction record from `info/nw-login-safe-20260502-153840/` with seq
`0x2..0xb0` and paces them every 50 ms. The replay covers the **entire**
captured session — there is no tail of "captured but unreplayed" records.

- 138 R-direction messages total in the dump
- Most are typeIndex 0x0008 (anonymous StateBundle channel; sub-types
  named in `state-bundles-0x80-0xb0.txt` as `StateBundleFragment0xNNN`)
- 5 named top-level types only: RegistrationResponseMsg,
  RegistrationRequestV3Msg, ClientAddEntryMsg, TimeSynchMsg, PingMsg
- Replay pipeline: `replay_substitution.SubstitutionContext` fills XX
  spans with values from the live V3 request
  ([analysis/replay_substitution_design.md](../analysis/replay_substitution_design.md))
- Records >14 KB are split via `MF_CHUNKS` at 1100 B/chunk
  ([analysis/replay_chunking_design.md](../analysis/replay_chunking_design.md));
  the DTLS 1.2 plaintext cap (`SSL3_RT_MAX_PLAIN_LENGTH = 16 384`) is the
  binding constraint, not Carrier's u16 record-size cap

For a full registry-vs-capture diff:
[analysis/typeregistry_vs_replay.md](../analysis/typeregistry_vs_replay.md).

---

## 6. Heartbeat (post-replay PingMsg loop)

After the queue drains, `_pump_replay()` switches to sending the captured
PingMsg (typeIndex 0x15d, 12 B body) every 500 ms. Without it, the client
emits a clean `SM_DISCONNECT reason=0` ~9 s after the burst ends. With it,
the connection holds **indefinitely** and the client just keeps emitting
bare `SM_CT_ACKS` keepalives (sysmsg=6, payload `2006`) back at us.

---

## 7. Game-side state machine (the wall)

Three layers of state are easy to confuse:

| Layer | Where it lives | What it counts |
|---|---|---|
| Carrier connection state | `Carrier.h:367–375` | `CST_CONNECTING/CONNECTED/DISCONNECTING/DISCONNECTED` |
| `rep.ready` flag | A boolean on the GridMate REP client | 1 = client accepted V3 response |
| **REP wrapper state** | `JavelinGameConnectionWrapper` per-tick | 9 → 10 → 11 → ... → in-world |

The wrapper state is what the live debugging cares about. Confirmed:

- **State 9 → 10**: DTLS up, V3 sent. Crossed in 2026-04-23.
- **State 10**: V3 accepted (`rep.ready=1`), session_token stored. Wrapper
  is here right now, indefinitely. Game UI is black post-character-creation.
- **State 10 → 11**: per-tick dispatcher polls *some* property of the
  GameConnection. The property is unknown. Decompiling `FUN_14644a070`
  (gameconn_state, RVA `0x0644a070`) is the cheapest way to find it.

What's been ruled out as the gate:

- `gw[0x160]==1` — confirmed already true in BRANCH B
- `vtable[0x110]` storing the session token — confirmed by Frida
- `rep.ready=1` — confirmed held throughout

What's still unexplained:

- **The 63-second mystery.** ~63 s after V3 accept, `vtable[0x110]` is
  written *again* with an empty string. Source unknown but reproducible.
  63 s is much longer than GridMate's 5 s `m_connectionTimeoutMS`
  default — almost certainly an application-level New World timeout.

Open conjecture (one of these or something else entirely):

1. The state-advance gate reads a fragment-level field inside the
   StateBundle stream (`0x0008`). Our replay ships the bytes but maybe a
   substitution is wrong, or fragment-level rel_seq math is off.
2. A reliable client→server message in the post-V3 phase isn't being
   acknowledged, so the client retransmits up to 3 times then drops it
   (`Carrier.cpp:154`). The generalized SM_CT_ACKS piggyback is a
   targeted fix for this, awaiting live verification.
3. Replay timing matters — fragments must arrive within T of V3 accept,
   and our 50 ms pacing is wrong by enough to matter.

The argument against "we're missing a named top-level message we forgot to
send" is in [analysis/typeregistry_vs_replay.md](../analysis/typeregistry_vs_replay.md):
the live session that actually went in-world wrote zero `SpawnActorsMsg`
at the top level — the in-world RPCs ride as fragment records inside
the `0x0008` channel.

---

## 8. Where to look in code

| File | Role |
|---|---|
| `server/rep_responder.py` | Main DTLS-terminating loop. `PeerSession` is per-peer state. |
| `server/javelin/frame.py` | `parse_envelope`, `parse_datagram`, `marshal_datagram` |
| `server/javelin/v3_request.py` | V3 RegistrationRequest decoder |
| `server/javelin/v3_response.py` | V3 RegistrationResponse encoder |
| `server/javelin/replay_store.py` | Loads `info/<capture>/messages-redacted.txt` |
| `server/javelin/replay_substitution.py` | Fills XX spans with live values |
| `tools/typeregistry_diff.py` | Wire-types-observed vs. registry diff |

## 9. Where to look in docs

| Doc | Use it when... |
|---|---|
| [next-session.md](next-session.md) | You need today's status / open question |
| [gridmate-reference.md](gridmate-reference.md) | You need the wire-format ground truth |
| [connection-flow.md](connection-flow.md) | You need the user-side high-level flow |
| [dtls-trust-bypass.md](dtls-trust-bypass.md) | You need to understand the cert hack |
| [capture-guide.md](capture-guide.md) | You're producing a fresh capture |
| [analysis/typeregistry_vs_replay.md](../analysis/typeregistry_vs_replay.md) | You're hunting for a named message we might be missing |
| [handoff_state10_question.md](handoff_state10_question.md) | Historical: the original "what is state 10" writeup |
