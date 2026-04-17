# Ghidra MCP Findings — Live Javelin Binary Analysis

> First session of interactive Ghidra analysis via GhidraMCP.
> Date: 2026-04-17. Ghidra project: `analysis/ghidra_project/NewWorld.gpr`.
>
> All addresses are virtual (image base `0x140000000`). Function renames
> made here persist in the Ghidra project only — save the project in
> Ghidra to keep them. This file captures the structural findings so
> they survive outside Ghidra.

---

## 1. DTLS initialization — fully mapped

### `Javelin_SecureSocketDriver_Initialize` @ `0x145dce750`

The `SecureSocketDriver::Initialize` equivalent. Single xref — called from
one call site inside module init. Struct layout discovered:

| Slot offset | Size | Meaning                          |
|-------------|------|----------------------------------|
| `[0x00]`    | ptr  | vtable (parent `SocketDriver`)   |
| `[0x18]`    | ptr  | `SSL*` — certificate loaded      |
| `[0x19]`    | ptr  | `EVP_PKEY*` — private key        |
| `[0x1a]`    | ptr  | `SSL_CTX*` (critical!)           |
| `[0x4e]`    | u8   | verify mode flag                 |
| `[0x4f]`    | ptr  | "has private key" indicator      |
| `[0x50]`    | ptr  | "has certificate" indicator      |
| `[0x51]`    | ptr  | CA bundle list                   |

### OpenSSL API wrappers (all confirmed)

| VA           | Original       | Renamed                              |
|--------------|----------------|--------------------------------------|
| `0x1478f6110`| `FUN_...`      | `openssl_DTLSv1_2_method`            |
| `0x1478ef900`| `FUN_...`      | `openssl_SSL_CTX_new`                |
| `0x1478efe40`| `FUN_...`      | `openssl_SSL_CTX_set_cipher_list`    |
| `0x1478eff40`| `FUN_...`      | `openssl_SSL_CTX_set_options`        |
| `0x1478f4f80`| `FUN_...`      | `openssl_SSL_CTX_use_PrivateKey`     |
| `0x1478f4e00`| `FUN_...`      | `openssl_SSL_CTX_use_certificate`    |
| `0x1478eff50`| `FUN_...`      | `openssl_SSL_CTX_set_verify`         |
| `0x1402a1a70`| `FUN_...`      | `Javelin_SSL_verify_callback`        |

### Cert/key loader wrappers (TBD)

- `FUN_145dc91f0` — loads private key from config, returns `EVP_PKEY*`
- `FUN_145dc9860` — loads certificate from config, returns `SSL*`-like
- `FUN_1406ccf20` — called when CA list (`[0x51]`) is present; builds CA bundle
- `FUN_14777d770` — called in a loop to `SSL_add_client_CA` each CA

### Cipher string confirmed

VA `0x147fbec70` in `.rdata`: `"ECDHE-RSA-AES256-GCM-SHA384"`. Single xref
from `Javelin_SecureSocketDriver_Initialize`. Matches GridMate
`SecureSocketDriver::Initialize` exactly (§9.1 step 1 of `gridmate-reference.md`).

---

## 2. Carrier — TWO constructor variants

GridMate was apparently compiled twice with different allocator templates.
Both constructors are ~line-identical but use different allocator names:

### `Javelin_Carrier_ctor` @ `0x140f4c5a0`

- Allocator literal: `"OSAllocator"`
- Nested-object vtable: `0x147fbe6e8`
- Top-level vtable: `0x147fbe410`
- Thread function pointer stored: `0x140f82340` (label, not yet decompiled)
- Thread descriptor vtable: `0x147f4ea80`

### `Javelin_Carrier_ctor_GMAlloc` @ `0x145dbae90`

- Allocator literal: `"GridMateAllocatorMP"` (the stock GridMate allocator)
- Top-level vtable: `0x148480670`
- Thread function pointer: `0x145ddab20` (label, not yet decompiled)
- Thread descriptor vtable: `0x147f4ea80` (same as above)

### State struct shape (both constructors)

| Offset          | Purpose                                                  |
|-----------------|----------------------------------------------------------|
| `[0x0]`         | vtable (`Carrier` base class)                            |
| `[0x5]`         | `param_3` — a user context pointer                       |
| `[0xb..0xd]`    | intrusive list head                                      |
| `[0x36..0x40]`  | SRWLock + 2nd list head                                  |
| `[0x68..0x7a]`  | **Channel 0** state (allocator ref, list, SRWLock)       |
| `[0x7c..0x8e]`  | **Channel 1** state                                      |
| `[0x90..0xa2]`  | **Channel 2** state                                      |
| `[0xa3..0x31d]` | Channel 3 (system channel) + more                        |
| `[0x59b..0x59d]`| Thread handle + started-flag                             |
| `[0x59f]`       | Target tick interval                                     |
| `[0x5a0]`       | Nested object vtable (`Handshake`-layer?)                |
| `[0x5a5..0x25a7]` | Large buffer (~0x2000 u64 slots = 16KB) — send buffer |

**Three replicated channel blocks (`[0x68]`, `[0x7c]`, `[0x90]`) in identical
layout** confirms GridMate's `k_maxNumberOfChannels = 4` (3 user channels +
channel 3 as system), exactly as documented in `gridmate-reference.md` §1.3.

### Thread spawn pattern (identical in both constructors)

```c
local_98 = 0;
local_90 = 0xffffffff;           // priority or affinity mask
local_88 = 1 << cpu_id;          // CPU affinity (-1 = no affinity)
local_80 = 1;
local_78 = "GridMate-Carrier";   // thread name

// Allocate 0x18 (24) byte thread descriptor
puVar10 = FUN_141499110(..., 0x18, 8, 0);
*puVar10        = &PTR_FUN_147f4ea80;   // thread-fn vtable
puVar10[1]      = &LAB_140f82340;       // pump function (member method ptr?)
puVar10[2]      = param_1;              // 'this' pointer

// Create AZStd::thread
FUN_14149c930(&local_98, puVar10, ...);
```

---

## 3. Session → Carrier → ReplicaManager hierarchy (discovered)

### `Javelin_Session_Init_and_Event` @ `0x140f72d30`

Top-level state-machine function. Dispatches on `*param_3`:

| Event | Meaning |
|-------|---------|
| `-1`  | Initial setup — allocates SessionInfo, CarrierImpl, ReplicaManager |
| `5`   | Peer connection event (uses `[0x42]` as peer state) |

Allocations done at event `-1`:

```c
// SessionInfo (0x120 = 288 bytes)
obj = alloc(0x120); Javelin_SessionInfo_ctor(obj, param_1[0x1b], param_1+0x18);
param_1[0x11] = obj;  param_1[0x29] = obj;

// CarrierImpl (0x218 = 536 bytes, wrapper around 77KB Carrier)
obj = alloc(0x218); Javelin_CarrierImpl_ctor(obj, param_1+0xf, param_1[0x45]);
param_1[0x27] = obj;

// ReplicaManager (0x9a8 = 2472 bytes)
obj = alloc(0x9a8); Javelin_ReplicaManager_ctor(obj);
param_1[0x28] = obj;
```

String literals in this function: `"GridSession"`, `"SessionStateInfo"` —
canonical GridMate names.

### `Javelin_CarrierImpl_ctor` @ `0x140f4bfe0`

The 536-byte wrapper. Key action: allocates **77KB (`0x12d50`)** for the
real `Carrier` (the worker that owns the thread, channels, buffers) and
stores it at `this[0x26]`.
- Its own vtable: `0x147fbe718`
- Wraps a nested 16-byte object at `0x147fbe3c8` (traffic-control?) if no
  user-provided one.

### `Javelin_Carrier_ctor` @ `0x140f4c5a0` (renamed; was FUN_140f4c5a0)

The 77KB "work horse":
- 3 identical channel blocks at `[0x68]/[0x7c]/[0x90]` (channels 0/1/2;
  channel 3 is system)
- ~16KB send buffer at `[0x5a5..0x25a7]`
- Spawns `"GridMate-Carrier"` thread via AZStd::thread wrapper; thread
  body address `0x140f82340` (not yet defined as function in Ghidra)
- Nested sub-object vtable at `[0x5a0] = 0x147fbe6e8`
- Main class vtable at `[0x0] = 0x147fbe410`

### `Javelin_Carrier_ctor_GMAlloc` @ `0x145dbae90`

Near-identical duplicate of the above but uses `"GridMateAllocatorMP"`
instead of `"OSAllocator"`, with thread body `0x145ddab20`. Classic
GridMate template-instantiation pattern.

### `Javelin_ReplicaManager_ctor` @ `0x140f51620`

2472-byte setup routine. Creates multiple nested allocator-tracked
containers for datasets, chunks, etc. **Does not register chunks
inline** — chunk registration happens via global/static constructors
that run at module load (each `ReplicaChunkDescriptor::Register` is a
static initializer). Finding those is next-session work.

Main vtable: `0x147fbf3a8`. Sub-object vtables: `0x147fbf1e8`, `0x147fbf280`.

---

## 3H. DTLS state handlers — fully decompiled

Handler event codes (all state handlers take `(driver, state_ctx, *event)`):
  - `-2` = state exit (cleanup)
  - `-1` = state entry (setup)
  - `1`  = periodic tick
  - `2,3` = state-specific external events

Transitions are performed by `Javelin_StateMachine_Transition(ctx, new_state_id)` @ `0x141480b10`.

### SSL state struct key offsets (observed in handlers)

| Offset | Meaning |
|-------:|---------|
| `+0x10` | state entry timestamp (ns) |
| `+0x18` | connect timeout (seconds) |
| `+0x48` | (cleared on SSL_free — raw read buffer pointer?) |
| `+0x50` | packet queue base (for draining post-handshake packets) |
| `+0x78` | (cleared on SSL_free — peer address copy?) |
| `+0x2058` | SSL* pointer |
| `+0x2060` | peer address |
| `+0x2068` | pending-work queue |
| `+0x2074` | last SSL error code |
| `+0x2080` | absolute deadline for next send (ns) |
| `+0x2088` | current retransmit interval (ms, doubles each send) |
| `+0x2090` | absolute handshake deadline (ns) |
| `+0x20dc` | retransmit counter |

### OpenSSL wrappers identified in state handlers

| VA | Renamed | Purpose |
|----|---------|---------|
| `0x1478f1c80` | `openssl_SSL_set_connect_state` | Put SSL into connect mode |
| `0x1478f1a00` | `openssl_SSL_set_accept_state` | Put SSL into accept mode |
| `0x1478f0210` | `openssl_SSL_connect` | Drive client handshake |
| `0x1478effb0` | `openssl_SSL_accept` | Drive server handshake |
| `0x1478f0e10` | `openssl_SSL_get_error` | Translate handshake error |
| `0x1478f0710` | `openssl_SSL_free` | Destroy SSL object |
| `0x145dc99b0` | `Javelin_SecureSocketDriver_CreateSSL` | Allocate new SSL from context |
| `0x145dda0d0` | `Javelin_SecureSocketDriver_SendRawPacket` | Bypass-SSL raw UDP send |
| `0x141480b10` | `Javelin_StateMachine_Transition` | Set next state id |

### Each state handler in one line

| State | ID | Handler | Behavior |
|-------|---:|---------|----------|
| CS_TOP | 0 | sentinel | never dispatched |
| CS_ACTIVE | 1 | @`0x145dd22d0` | **Entry**: capture timestamp + call CreateSSL. **Tick**: if handshake timeout exceeded → transition to CS_DISCONNECTED (10) |
| CS_ACCEPT | 2 | @`0x145dd2180` | **Entry**: `SSL_set_accept_state`. **Tick**: `SSL_accept`, then drain post-handshake queued packets. Success → CS_ESTABLISHED (9); error → CS_SSL_ERROR (11) |
| CS_WAIT_FOR_STATEFUL_HANDSHAKE | 3 | @`0x145dd3280` | **Entry**: retransmit interval = 1000ms. **Tick**: if past deadline, manually build + send HelloVerifyRequest (25 bytes, DTLS 1.0 legacy wire format), double backoff. **Event 2** (cookie received) → CS_SSL_HANDSHAKE_ACCEPT (4) |
| CS_SSL_HANDSHAKE_ACCEPT | 4 | (mis-identified earlier) | Not yet decompiled cleanly — Ghidra's signature inference got confused. TODO revisit. |
| CS_CONNECT | 5 | @`0x145dd2440` | **Entry**: `SSL_set_connect_state`. **Tick**: `SSL_connect`, handle result. Success → CS_ESTABLISHED (9); error → CS_SSL_ERROR (11); timeout → CS_HANDSHAKE_RETRY (8) |
| CS_COOKIE_EXCHANGE | 6 | @`0x145dd25c0` | **Entry**: set handshake deadline = now + `[+0x18]*1000`. **Event 3** → CS_SSL_HANDSHAKE_CONNECT (7) |
| CS_SSL_HANDSHAKE_CONNECT | 7 | @`0x145dd3220` | **Entry**: `SSL_free` old SSL, `CreateSSL`, `SSL_set_connect_state`. Drives same loop as CS_CONNECT. |
| CS_HANDSHAKE_RETRY | 8 | @`0x145dd2e00` | **Entry**: rebuild SSL + set connect state. **Tick**: → CS_COOKIE_EXCHANGE (6) |
| CS_ESTABLISHED | 9 | label only | encrypted traffic phase |
| CS_DISCONNECTED | 10 | label only | terminal |
| CS_SSL_ERROR | 11 | label only | terminal |

### Client-side connect path (what our captures show)

```
(external: client instantiates SecureSocketDriver)
  ↓
CS_ACTIVE  [entry]
  ↓
CS_CONNECT  [entry: SSL_set_connect_state]
  ├── tick → SSL_connect() returns WANT_READ
  │   (client sends ClientHello, waits for HelloVerifyRequest)
  ├── tick → SSL_connect() returns WANT_WRITE
  │   (client sends ClientHello2 with cookie)
  ├── tick → SSL_connect() returns 1
  │   (handshake complete, session keys derived)
  ↓
CS_ESTABLISHED

(on timeout between any ticks: → CS_HANDSHAKE_RETRY → CS_COOKIE_EXCHANGE → CS_SSL_HANDSHAKE_CONNECT → back to CS_CONNECT)
(on SSL error: → CS_SSL_ERROR → CS_DISCONNECTED)
```

### Server-side accept path (what our stub server must implement)

```
(external: server's SocketDriver sees new peer with packets waiting)
  ↓
CS_ACTIVE
  ↓
CS_WAIT_FOR_STATEFUL_HANDSHAKE
  ├── tick after 1s → manually send HelloVerifyRequest (~25 bytes)
  ├── (exponential backoff on retransmit)
  ├── event 2 (cookie-bearing ClientHello2 received)
  ↓
CS_SSL_HANDSHAKE_ACCEPT  (implementation TBD)
  ↓
CS_ACCEPT  [entry: SSL_set_accept_state]
  ├── tick → SSL_accept() returns WANT_READ/WRITE
  ├── tick → SSL_accept() returns 1
  │   (handshake complete)
  ↓
CS_ESTABLISHED
```

**Critical insight for stub server**: the SERVER manually constructs HelloVerifyRequest and injects it via `SendRawPacket` without using OpenSSL. This is fine for our stub — we can either replicate this or use `DTLSv1_listen` which does the same thing natively.

---

## 3B. SecureSocketDriver state machine (complete enumeration)

`Javelin_SecureSocketDriver_StateDispatch` @ `0x145dce4c0` registers
all 12 DTLS connection states with their handler functions. This is
the complete lifecycle:

| ID | State                             | Handler       | Can enter from | Next (typical) |
|---:|-----------------------------------|---------------|---------------:|---------------:|
| 0  | `CS_TOP`                          | sentinel      | — | 1 |
| 1  | `CS_ACTIVE`                       | `FUN_145dd22d0` | 0 | (dynamic) |
| 2  | `CS_ACCEPT`                       | `FUN_145dd2180` | 1 | 3 |
| 3  | `CS_WAIT_FOR_STATEFUL_HANDSHAKE`  | `FUN_145dd3280` | 2 | 0xff |
| 4  | `CS_SSL_HANDSHAKE_ACCEPT`         | (decompiler-confused) | 2 | 0xff |
| 5  | `CS_CONNECT`                      | `FUN_145dd2440` | 1 | 6 |
| 6  | `CS_COOKIE_EXCHANGE`              | `FUN_145dd25c0` | 5 | 0xff |
| 7  | `CS_SSL_HANDSHAKE_CONNECT`        | `FUN_145dd3220` | 5 | 0xff |
| 8  | `CS_HANDSHAKE_RETRY`              | `FUN_145dd2e00` | 5 | 0xff |
| 9  | `CS_ESTABLISHED`                  | `LAB_145dd2630` | 1 | 0xff |
| 10 | `CS_DISCONNECTED`                 | `LAB_145dd2620` | 0 | 0xff |
| 11 | `CS_SSL_ERROR`                    | `LAB_145dd31a0` | 0 | 0xff |

**Client-side connect flow** (what we see in our captures):

```
CS_ACTIVE (1)
  → CS_CONNECT (5)
  → CS_COOKIE_EXCHANGE (6)          [DTLS HelloVerifyRequest exchange]
  → CS_SSL_HANDSHAKE_CONNECT (7)    [full DTLS handshake]
  → CS_ESTABLISHED (9)              [session keys negotiated]
  → (on error) CS_SSL_ERROR (11) or CS_HANDSHAKE_RETRY (8)
  → (on disconnect) CS_DISCONNECTED (10)
```

This maps exactly to the captured DTLS handshake sequence in
`capture/20260416_222545_second_capture/` — confirming Javelin's
SecureSocketDriver is GridMate's with states unchanged.

## 3C. Other anchors mapped this session

| VA           | Renamed                         | Notes |
|--------------|---------------------------------|-------|
| `0x140f69c00`| `Javelin_CarrierThread_Spawn`  | Where `"GridMate-Carrier Packet Send Thread"` is used as thread name at CreateThread site |
| `0x140f76d60`| `Javelin_ConnectionStats_Dump` | Prints `conn.dataSend =`, `conn.packetLost =`, etc. |

---

## 3D. CarrierThread worker loop (fully mapped)

```
Javelin_CarrierThread_ThreadPump (0x140f82340)
├─ Driver::Update               [vtable *param_1[0x25a9] + 8]
├─ ProcessInternalMessageQueue  (inline in pump)
│    types: 0=NewConn, 1=Heartbeat, 2=RemoveConn, 3=DriverEvent
├─ CheckConnectionTimeouts       (0x140f777f0)  - per-tick watchdog
├─ Driver::Update(check)         [*param_1[2] + 0x90]
├─ Per-connection: Driver::Send  [*param_1[2] + 0x98]
├─ Per-connection: Driver::Recv  [*param_1[2] + 0xa8]
├─ Driver::Flush                 [*param_1[6] + 0x40]
├─ ReceiveLoop                   (0x140f898e0)  ← see 3E
├─ Carrier::UpdateBase           [*param_1[0] + 8]
├─ SendLoop                      (0x140f8ab70)  ← see 3F
└─ Sleep(targetInterval - elapsed) or SwitchToThread()
```

Connection struct is **5064 bytes (0x13c8)**. Key offsets: `+0x1300` lastActivityTime, `+0x1308` minRtt, `+0x1310` heartbeat-needed flag, `+0x1311` timeout-reported flag, `+0x1318` timeout-send-queued flag, `+0x131b` disconnect flag, `+0x131b-d` connection state bits, `+0x13bc` heartbeat counter, `+0x13c4` reliability/flag byte.

## 3E. ReceiveLoop (`Javelin_CarrierThread_ReceiveLoop` @ `0x140f898e0`)

The actual datagram ingress:

```c
while (driver_has_incoming_packet) {
    raw_bytes = Driver::Receive()          // [*param_1[0] + 0x58]
    flags    = raw_bytes[0]

    if (flags & 0x80 && (flags & 0x7e) == 0) {
        // Connection-request handshake path
        // - Validate cookie / allow-new-connection
        // - If accepted AND DTLS bit set (flags & 1):
        //     plaintext = DTLS_DecryptDataGram(ciphertext)  [*param_1[5] + 0x30]
        // - Javelin_Carrier_CreateConnection(...)
        // - Carrier::ParseMessages(param_1, conn, hdr, bitstream)
    } else {
        // Not a connection request, and not from known conn -> ignore
        // or queue a "ConnectionRejected" (type 0xb) notification
    }
}
```

**DTLS decrypt entry point confirmed**: `*param_1[5] + 0x30` — this is the
SecureSocketDriver's `DecryptDataGram` method. `param_1[5]` is the driver
pointer; vtable offset `0x30` is the decrypt routine.

## 3F. SendLoop (`Javelin_CarrierThread_SendLoop` @ `0x140f8ab70`)

Mirror of receive. Per-connection build-and-send. Calls:
- `Driver::IsConnectionSendable` [*param_1[2] + 0x50]
- `Driver::HasSendBudget`        [*param_1[2] + 0x58]
- Build send-buffer via `FUN_140f8ba70` (marshal pending messages)
- **DTLS encrypt**: `*param_1[5] + 0x28` — SecureSocketDriver's `EncryptDataGram`
- `Driver::SendDataGram`         [*param_1[2] + 0x48]

## 3G. ReadMessageHeader & message parsing (`Javelin_Carrier_ParseMessages` @ `0x140f77eb0`)

**CRITICAL: Javelin uses BIT STREAMS, not byte-aligned reads.** The GridMate
reference's `ReadMessageHeader` has been restructured to use
`Javelin_BitStream_ReadBits` for every field read. This is why our `0x42`
scan found nothing — the header validation is implicit, not a single mask.

### Parse loop (per message record in a datagram)

```c
while (!bitstream_error) {
    msg_rec = alloc(0x38)                    // 56-byte MessageRecord

    flags = ReadBits(8)                      // flags byte
    size  = ReadBits(16) [BE byteswap]       // payload size (in bytes? bits?)

    msg_rec.reliable    = flags & 0x01
    if (flags & 0x20)   channel    = ReadBits(8)  else inherit_prev
    if (channel > 3)    corruption -> break
    if (flags & 0x04)   numChunks  = ReadBits(16) [BE] else 1
    if (!(flags & 0x08)) seq       = ReadBits(16) [BE] else per_channel_counter++
    if (!(flags & 0x10)) relSeq    = ReadBits(16) [BE] else (if reliable) relCounter++
    msg_rec.connecting = (flags >> 7) & 1

    if (channel == 3) {
        // System message: msgId at END of payload
        msgId = payload[size - 1]
        if (msgId == 6)  HandleAckVector(...)       // SM_CT_ACKS
        else if (msgId == 7) HandleConnControl(...) // SM_CT_CONN_CONTROL
        // other msgIds consumed/ignored
    } else {
        // User channel (0..2): insert msg_rec into per-channel priority queue
        // (sequenced insert, duplicate detection)
        // Linked list heads at conn + 0x40 + channel * 8
        // Per-channel inbound counters at conn + 0x88 + channel * 0x40
    }
}
```

### Flag bits (matches GridMate reference 2.2 exactly)

| Bit | Mask | Name | Meaning |
|----:|-----:|------|---------|
| 0 | 0x01 | MF_RELIABLE | Reliable-ordered delivery |
| 1 | 0x02 | (reserved, unused) | |
| 2 | 0x04 | MF_CHUNKS | numChunks > 1 (multi-chunk message) |
| 3 | 0x08 | MF_SQUENTIAL_ID | Sequence number = prev+1 (omitted from wire) |
| 4 | 0x10 | MF_SQUENTIAL_REL_ID | Reliable seq = prev+1 (omitted) |
| 5 | 0x20 | MF_DATA_CHANNEL | Channel byte is present; else inherit |
| 6 | 0x40 | (reserved, unused) | |
| 7 | 0x80 | MF_CONNECTING | Handshake/connection-request packet |

### MessageRecord struct (0x38 / 56 bytes)

| Offset | Size | Field | Notes |
|-------:|-----:|-------|-------|
| `+0x14` | u32 | `m_reliable` | from flag bit 0 |
| `+0x18` | u8 | `m_channel` | 0..3 |
| `+0x1a` | u16 | `m_numChunks` | `1` or from wire |
| `+0x1c` | u16 | `m_sequenceNumber` | per-channel |
| `+0x1e` | u16 | `m_reliableSequence` | only meaningful if reliable |
| `+0x28` | u16 | `m_payloadSize` | from wire |
| `+0x2a` | u8 | `m_connecting` | bit 7 |

### BitStream (`Javelin_BitStream_ReadBits` @ `0x140f7c420`)

Struct layout (5 × u64 = 40 bytes):

| Offset | Size | Field |
|-------:|-----:|-------|
| `+0x00` | u64 | `m_basePtr` |
| `+0x08` | u64 | `m_startBitOffset` |
| `+0x10` | u64 | `m_cursorBits` |
| `+0x18` | u64 | `m_endBits` |
| `+0x20` | u8 | `m_errorFlag` |

`ReadBits(stream, out, nBits)` either fast-path memcpy (byte-aligned
case) or shift-and-mask byte-by-byte for mid-byte reads.

### System message IDs seen in the dispatch

| ID | Name (GridMate) | Notes |
|---:|-----------------|-------|
| 6  | `SM_CT_ACKS`   | handled by `Javelin_Carrier_HandleAckVector` @ `0x140f7bdd0` |
| 7  | `SM_CT_CONN_CONTROL` | reads u32 value, calls a virtual on a component |

Message types 1..5, 8 not explicitly seen in this function — likely in
Carrier init path or handled elsewhere. Pattern suggests full GridMate
enumeration is preserved.

---

## 4. Chunk descriptor pattern (discovered)

### Two confirmed chunks

| Init function | VA | Chunk name | String VA |
|---------------|----|------------|-----------|
| `Javelin_TransformReplicaChunk_descriptor_init` | `0x1462abe00` | `TransformReplicaChunk` | `0x1484ee530` |
| `Javelin_TriggerAreaChunk_descriptor_init`      | `0x140a23590` | `TriggerAreaChunk`       | (nearby)   |

### Canonical pattern (byte-identical across chunk types, template-instantiated)

```c
void Chunk_descriptor_init(this, desc_ptr_ptr) {
    if (desc.registered_flag == 0) {
        desc.name = "ChunkNameString";
        class_id = Javelin_ReplicaChunkClassId_FromName(&result, desc.name);
        Javelin_ReplicaChunkDescriptor_Register(
            this + 0x180, &local_58, &class_id, ...);

        // ...install 3 function vtables at desc + 0xa8, 0xf8, 0x120
        // (likely: serialize, unmarshal, spawn)
        // Each vtable is 3 function pointers (0x10 bytes apart)

        desc.class_id = class_id;
    }
}
```

### Helper functions identified

| VA | Renamed | Role |
|----|---------|------|
| `0x140ad2870` | `Javelin_ReplicaChunkDescriptor_Register` | Creates a registry entry |
| `0x1412f4730` | `Javelin_ReplicaChunkClassId_FromName` | CRC-hashes the chunk name to a class ID |

### The compiler duplicated helper functions per chunk

Each chunk init calls its OWN instance of some helpers (e.g., Transform calls
`FUN_146277a90` where Trigger calls `FUN_140925ea0` for the "install
descriptor" step). This is template monomorphization. Consequence: we can't
find ALL chunks via xrefs to a single register function. Instead, run
`tools/ghidra_scripts/FindChunkRegistrations.py` — walks `.rdata` for all
`*Chunk` strings, finds their xrefs, and outputs the full init-function
catalog to `analysis/ghidra_chunks.txt`.

---

## 5. Still to map (next-session queue)

### High priority
- **Pump function at `0x140f82340` / `0x145ddab20`** — not auto-classified as
  function. Need to force-define via Ghidra (`F` key on the address) or query
  disassembly. This IS the GridMate `CarrierThread::ThreadPump` main loop.
- **`ReadMessageHeader`** — search for `AND/TEST immediate 0x42`. Our
  pre-existing `JavelinHunt.py` script does this; user can run it now.
- **Carrier vtable demangling** at `0x147fbe410` — 20+ virtual method slots.
  Labeling each gives us `Send`, `Disconnect`, `Update`, etc.

### Medium priority
- `TransformReplicaChunk` chunk registration chain (VA `0x1484ee539` had
  no xrefs — probably the string is mid-structure, not a standalone
  literal; try the start of the actual string data).
- Cert/key loader helper functions (`FUN_145dc91f0`, `FUN_145dc9860`).
- System message dispatch function (reads byte at `buffer[size-1]` to
  dispatch `SM_CT_*` — §2.5 of GridMate reference).

### Low priority (can wait until after a stub server exists)
- Replica dispatcher (`ReplicaManager::_Unmarshal` equivalent — switch on
  a 1-byte cmdhdr with cases 1-5 for `Cmd_*`).
- Per-chunk `ReplicaChunkDescriptor` registration enumeration.
