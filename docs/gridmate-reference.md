# GridMate Protocol Reference (Javelin Analog)

> Deep-read of Lumberyard `Code/Framework/GridMate/GridMate/` at
> `C:\Users\charl\Programs\lumberyard\dev\Code\Framework\GridMate\`
> (sparse shallow clone of `aws/lumberyard`, MIT-licensed).
>
> **Why this doc exists.** A binary scan of NewWorld.exe (see
> `analysis/` + `docs/progress.md`) found **zero** matches on AzNetworking
> class markers but **5001** matches on `Javelin::*` and **30** on the
> string `"GridMate"`. Amazon's New World networking library ("Javelin")
> is a forked/rebranded descendant of **Lumberyard GridMate**, not a
> descendant of the open-source O3DE AzNetworking stack. New World
> development started ~2017 which predates AzNetworking.
>
> This document is the protocol map we expect to match when Ghidra
> auto-analysis of NewWorld.exe completes. `docs/aznetworking-reference.md`
> remains useful only as a conceptual comparison — Amazon carried some
> ideas forward to O3DE, but the *wire format* and *class names* track
> GridMate, not AzNetworking.
>
> Every claim below cites Lumberyard source `file:line`. "TBD (needs
> Ghidra)" marks anything the source alone can't settle — typically
> NW-specific divergence from stock GridMate.

---

## Contents

1. [Carrier datagram header wire format](#1-carrier-datagram-header-wire-format)
2. [Channel and message framing](#2-channel-and-message-framing)
3. [Reliability and ack vector format](#3-reliability-and-ack-vector-format)
4. [DTLS integration (SecureSocketDriver)](#4-dtls-integration-securesocketdriver)
5. [Replica system](#5-replica-system)
6. [RPC mechanism](#6-rpc-mechanism)
7. [Session / Carrier handshake](#7-session--carrier-handshake)
8. [Identifiable strings and UUIDs](#8-identifiable-strings-and-uuids)
9. [GridMate → Javelin class mapping](#9-gridmate--javelin-class-mapping)

---

## 1. Carrier datagram header wire format

GridMate's Carrier layer is the transport (equivalent of O3DE's
`UdpPacketHeader` + reliability layer). Unlike AzNetworking's rich fixed
header, the **Carrier datagram header is just 2 bytes**, and almost all
of the protocol state lives in per-message headers (§2) and in a separate
`SM_CT_ACKS` system message (§3).

### 1.1 Endianness

All multi-byte integers on the wire are **big-endian**. Hardcoded at the
carrier level: `static const EndianType kCarrierEndian = EndianType::BigEndian;`
— `Carrier.cpp:58`.

### 1.2 Datagram wrapper layout

Two cases depending on whether a compressor is configured
(`CarrierDesc::m_compressionFactory`):

#### Without compressor (default, no `MultiplayerCompressor`):

| Off | Size | Field           | Source |
|----:|-----:|-----------------|--------|
| 0   | 2    | `SequenceNumber` (datagram id, big-endian u16) | `Carrier.cpp:2869–2874`, `TrafficControl.h:25` |
| 2   | …    | Message records (see §2)                       | `Carrier.cpp:3147–3273` |

`GetDataGramHeaderSize()` returns exactly `sizeof(SequenceNumber)` = **2
bytes** (`Carrier.cpp:2565–2573`).

#### With compressor:

| Off | Size | Field                                                   | Source |
|----:|-----:|---------------------------------------------------------|--------|
| 0   | 1    | compression hint (`0x00`=uncompressed, `0x01`=compressed) | `Carrier.cpp:62–64`, `2080–2090` |
| 1   | 2    | `SequenceNumber`                                         | same |
| 3   | …    | messages (possibly compressed as one blob after byte 0) | `Carrier.cpp:2101–2155` |

The compression hint byte is written to an **outer** buffer before the
datagram is composed; when the `0x01` path is taken, bytes 1..end are the
compressed form of everything the non-compressed layout would contain.
`IsConnectRequestDataGram` at `Carrier.cpp:2892–2919` documents the read
order: if compressor, read the hint byte; then skip `sizeof(SequenceNumber)`
to reach the first message header. Ghidra hint: a function that does
`Read(u8) → Skip(2) → parse message` is this.

### 1.3 Size constants

- `k_maxNumberOfChannels = 4` (`Carrier.cpp:60`).
- `k_systemChannel = 3` (`Carrier.cpp:61`) — channel reserved for Carrier
  system messages. User data uses channels 0..2.
- Datagram size limit: driver-dependent
  (`CarrierThread::m_maxDataGramSizeBytes = m_driver->GetMaxSendSize()`
  at `Carrier.cpp:1284`). For UDP, typically ~1400 for internet MTU; for
  LAN mode (`m_driverIsFullPackets=true`) up to ~64KB.
- `SequenceNumber = AZ::u16`, `SequenceNumberMax = 0xFFFF`,
  `SequenceNumberHalfSpan = 0x7FFF` (`TrafficControl.h:25–32`). Sequence
  comparisons use the half-span trick (`SequenceNumberLessThan`,
  `SequenceNumberGreaterThan`, `TrafficControl.h:190–211`).

### 1.4 What's NOT in the datagram header

Unlike AzNetworking's `UdpPacketHeader`, there is **no packet-type
field, no ack vector, no sequence window, no packet-flags byte** at the
datagram level. Those are either:

- **Per-message**: reliability, channel, message sequence number — in the
  message header, §2.
- **Out-of-band**: acks are sent as a separate `SM_CT_ACKS` system
  message on `k_systemChannel`, not riding on every datagram. See §3.

This is a *major* difference vs AzNetworking — expect Ghidra to show a
tiny fixed-offset parse function for incoming datagrams (2 or 3 byte
preamble), followed by a loop that parses variable-length message headers.

---

## 2. Channel and message framing

### 2.1 Message record layout

Each datagram carries 1..N message records. Each record begins with a
flags byte, then conditionally-present fields. Written by
`CarrierThread::WriteMessageHeader` (`Carrier.cpp:3491–3542`), parsed by
`ReadMessageHeader` (`Carrier.cpp:3548–3627`).

| Off | Size | Field / Condition                                                                 |
|----:|-----:|-----------------------------------------------------------------------------------|
| 0   | 1    | `flags` byte (see 2.2)                                                            |
| 1   | 2    | `m_dataSize` (u16, big-endian) — payload size of this message                     |
| +2  | 1    | `channel` (u8) — **only present if `MF_DATA_CHANNEL` set**                        |
| +1  | 2    | `m_numChunks` (u16) — **only if `MF_CHUNKS` set** (multi-chunk message); implicit 1 otherwise |
| +2  | 2    | `m_sequenceNumber` (u16) — **only if `MF_SQUENTIAL_ID` is NOT set**; otherwise prev+1 per channel |
| +2  | 2    | `m_sendReliableSeqNum` (u16) — **only if `MF_SQUENTIAL_REL_ID` is NOT set**       |
| …   | N    | `m_data` (payload, `m_dataSize` bytes — the actual marshaled message)             |

The "sequential ID" flags are a size optimization: when the sender knows
the receiver can derive the ID (it's `prev + 1`), it omits the 2-byte
field and sets the flag. Channel is similarly omitted when it matches the
previous message in the datagram.

### 2.2 Message flags (the first byte of each message)

From `Carrier.cpp:84–94`:

```
enum MessageFlags
{
    MF_RELIABLE         = (1 << 0),   // 0x01 — reliable-ordered delivery
    MF_CHUNKS           = (1 << 2),   // 0x04 — more than 1 chunk follows (m_numChunks present)
    MF_SQUENTIAL_ID     = (1 << 3),   // 0x08 — m_sequenceNumber is prev+1 (omit from wire)
    MF_SQUENTIAL_REL_ID = (1 << 4),   // 0x10 — m_sendReliableSeqNum is prev+1 (omit from wire)
    MF_DATA_CHANNEL     = (1 << 5),   // 0x20 — channel byte follows (else = previous channel, or 0 for first)
    MF_CONNECTING       = (1 << 7),   // 0x80 — this message is part of the connection handshake
    MF_UNUSED_FLAGS     = ((1<<1) | (1<<6)) // 0x42 — if any set, stream is corrupt
};
```

Receiver aborts the datagram if either of the unused bits is set
(`Carrier.cpp:3555–3559`).

### 2.3 Channels

Fixed at 4 channels (`k_maxNumberOfChannels = 4`), of which channel 3
(`k_systemChannel`) is reserved for Carrier system messages
(see 2.5). Channels 0..2 are user channels and are independent
reliable-ordered streams — reliable messages on channel 0 do not block
reliable messages on channel 1.

### 2.4 Chunked messages

When a user's `Send()` payload exceeds `m_maxMsgDataSizeBytes`
(`maxDataGramSize - GetDataGramHeaderSize() - GetMaxMessageHeaderSize()`,
`Carrier.cpp:1285`), the Carrier splits into multiple messages with
`MF_CHUNKS` set and `m_numChunks > 1`. Chunks are reassembled in order on
the receiver. **Unreliable payloads exceeding the MTU get upgraded to
reliable** (`Carrier.h:122–123`). Note: `Carrier.cpp:87` comment flags
`MF_CHUNKS` as "more than 1 (default chunks) to form the full message"
— so `MF_CHUNKS=1` means "multi-chunk".

### 2.5 System messages (channel 3)

The first byte of a system message's payload is the `SystemMessageId`
enum (`Carrier.cpp:626–639`, u8 value cast to enum):

| Id | Name                | Purpose                                   |
|---:|---------------------|-------------------------------------------|
| 1  | `SM_CONNECT_REQUEST`| Session connect with welcome data         |
| 2  | `SM_CONNECT_ACK`    | Reply accepting the session connect       |
| 3  | `SM_DISCONNECT`     | Graceful disconnect notification          |
| 4  | `SM_CLOCK_SYNC`     | Carrier-level clock sync                  |
| 5  | `SM_CT_FIRST`       | sentinel, not a real msg id               |
| 6  | `SM_CT_ACKS`        | Datagram ack vector (also keepalive)      |
| 7  | `SM_CT_CONN_CONTROL`| Connection control (window size etc.)     |
| 8  | `SM_CT_BANDWIDTH`   | Connection bandwidth info                 |

The msgId byte sits at the **end** of the message payload, not the start
— see `Carrier.cpp:2909–2913`, `2994` where the parser subtracts 1
(plus optional 4-byte CRC) from `m_dataSize` to reach it. This is
counterintuitive. **Ghidra hint: a function that reads `buffer[size-1]`
to dispatch is a system-message handler.**

With `GM_CARRIER_MESSAGE_CRC` build flag, the last 4 bytes before the
msgId are a CRC32 of the message body — `Carrier.cpp:2985–2990`.
Production builds rarely have this. **TBD (needs Ghidra)** — check for
CRC tail pattern.

---

## 3. Reliability and ack vector format

### 3.1 Reliability is per-message, not per-datagram

Each message carries its own reliability in the flags byte:
`MF_RELIABLE` → `Carrier::SEND_RELIABLE`; otherwise
`Carrier::SEND_UNRELIABLE` (`Carrier.cpp:3567–3574`). There are only **two
reliability modes** in stock GridMate:
- `SEND_UNRELIABLE` — fire-and-forget; out-of-order arrivals are dropped
  ("unreliable ordered" — `Carrier.h:61`).
- `SEND_RELIABLE` — reliable ordered.

There is **no** "UnreliableOrdered" or "ReliableUnordered" variant at
the Carrier level.

Priority is separate from reliability: `PRIORITY_SYSTEM / HIGH / NORMAL /
LOW / MAX` (`Carrier.h:47–55`) — controls send-queue ordering only.

### 3.2 Reliable ordering enforcement

Every channel maintains:
- `prevMsgSeqNum[channel]` — last message seq per channel
  (`Carrier.cpp:3597–3605`)
- `prevReliableMsgSeqNum[channel]` — last reliable seq per channel
  (`Carrier.cpp:3607–3622`)

Unreliable messages carry the **reliable** sequence number of their
channel, so they can be **reordered with respect to unreliable
siblings but cannot jump ahead of a reliable message that hasn't been
delivered** (`Carrier.cpp:3607–3622` comment). This is the "unreliable
ordered" guarantee.

### 3.3 Ack vector format (`SM_CT_ACKS`)

Acks do not ride on every datagram. Instead, `WriteAckData`
(`Carrier.cpp:2579–2687`) builds a dedicated ack message and sends it as
`SM_CT_ACKS` on channel 3 periodically (when the traffic controller says
so, or when the ack window is full). Format:

| Off | Size | Field                                                              |
|----:|-----:|--------------------------------------------------------------------|
| 0   | 1    | `ackFlags` byte (see below)                                        |
| 1   | 2    | `lastToAck` — most recent datagram seq number being acked (u16 BE) |
| …   | …    | Depending on flags: bit vector OR first-to-ack seq OR nothing      |

`AckHistoryFlags` (`Carrier.cpp:647–652`):
```
AHF_BITS           = (1 << 7)   // 0x80 — bits 0..6 = byte count of ack bitmap that follows
AHF_CONTINUOUS_ACK = (1 << 6)   // 0x40 — there is a 'firstToAck' seq following 'lastToAck'
AHF_KEEP_ALIVE     = (1 << 5)   // 0x20 — empty ack payload, keep-alive only
```

Three cases:

- **Empty / keepalive** — `ackFlags = 0x20`, nothing after.
  `Carrier.cpp:2681–2684`.
- **Single or range ack (continuous)** — if all unacked datagrams are
  contiguous, `ackFlags |= AHF_CONTINUOUS_ACK`, followed by a
  `firstToAck` u16. `Carrier.cpp:2673–2676`. Range is `[firstToAck,
  lastToAck]`.
- **Sparse ack (bitfield)** — `ackFlags = 0x80 | numHistoryBytes`
  where `numHistoryBytes ∈ [0, 64]`. Bits 0–6 of the flag byte encode
  that count. Followed by `numHistoryBytes` raw bytes of bit-per-datagram
  ack bitmap, starting from `lastToAck - 1` going backwards
  (`Carrier.cpp:2646–2656`: `dist = lastToAck - currentToAck; dist--; bit
  at byte `dist/8`, offset `dist%8`).

History window size: `DataGramHistoryList::m_datagramHistoryMaxNumberOfBytes
= 64` → **512 datagrams of history** (`Carrier.cpp:156`). Each datagram
is acked up to 3 times (`m_datagramHistoryMaxNumberOfAck = 3`,
`Carrier.cpp:154`) before dropping from the history.

### 3.4 Duplicate detection

`Carrier.cpp:2941–2952`: datagrams are inserted into the received history
ring buffer; duplicates raise `SecurityError::EC_SEQUENCE_NUMBER_DUPLICATED`
and are discarded. This will fire in captures if our stub replays
datagrams.

---

## 4. DTLS integration (SecureSocketDriver)

`SecureSocketDriver` sits **below** Carrier — it inherits from
`SocketDriver` and replaces the raw UDP I/O path with an encrypted one
(`SecureSocketDriver.h:105–107`). The Carrier sees the same API as plain
UDP and does not know DTLS is involved.

### 4.1 OpenSSL specifics

`SecureSocketDriver::Initialize` (`SecureSocketDriver.cpp:1459–1566`):

- **DTLS version**: `DTLSv1_2_method()` → DTLS 1.2 mandatory
  (`:1472`).
- **Cipher suite** (single, forced): `"ECDHE-RSA-AES256-GCM-SHA384"`
  (`:1494`). Same string as AzNetworking. This matches the captured
  New World cert/cipher behavior.
- `SSL_OP_NO_QUERY_MTU` set (`:1479`) — MTU is set explicitly per
  connection via `SSL_set_mtu(m_ssl, m_mtu)` (`:1075`).
- `SSL_CTX_set_ecdh_auto(ctx, 1)` (`:1500`) — auto-select ECDH curve.
- Client auth:
  - `m_authenticateClient == false` (default): `SSL_VERIFY_PEER`
    (server-only auth).
  - `m_authenticateClient == true`: `SSL_VERIFY_FAIL_IF_NO_PEER_CERT`
    → mutual auth. Matches New World's captured DTLS handshake which
    includes a Certificate Request.
- `m_certificateAuthorityPEM == nullptr` path uses a custom
  `VerifyCertificate` callback (`:1552–1553`) — self-signed-permitting.
- Cookie exchange: DTLS-native, `GenerateCookie` / `VerifyCookie`
  (`SecureSocketDriver.h:239–240`, 16-byte secret, rotated via
  `RotateCookieSecret`).

### 4.2 Per-connection state machine

`SecureSocketDriver::Connection::ConnectionState` is a hierarchical state
machine (`SecureSocketDriver.h:129–140`):

```
CS_TOP
├── CS_ACTIVE
│   ├── CS_SEND_HELLO_REQUEST   (server: waiting for client to initiate)
│   ├── CS_ACCEPT               (server: DTLS handshake accepting)
│   ├── CS_COOKIE_EXCHANGE      (client: DTLS HelloVerifyRequest loop)
│   ├── CS_CONNECT              (client: DTLS handshake connecting)
│   └── CS_ESTABLISHED          (both: handshake done; ciphertext flows)
└── CS_DISCONNECTED
```

Transitions use AzCore's `AZ::HSM` (hierarchical state machine) — calls
like `OnStateActive`, `OnStateAccept`, etc.
(`SecureSocketDriver.h:182–189`).

### 4.3 Handshake → Carrier handoff

Key detail for our stub: DTLS and Carrier operate independently. The
driver queues **plaintext** datagrams from Carrier onto
`m_outboundPlainQueue` (`SecureSocketDriver.h:210`). During handshake,
these stay queued until `CS_ESTABLISHED`. Once established:
- outgoing plaintext → `SSL_write` → `m_outDTLSBuffer` → socket send
  (`SecureSocketDriver.cpp:987`).
- incoming ciphertext → `m_inDTLSBuffer` → `SSL_read` → global in-queue
  → Carrier `Receive()` (`:968`).

The Carrier's `SM_CONNECT_REQUEST` message (§2.5, §7) is the **first
user-level** packet sent *after* DTLS completes. There is **no** overlap
of the DTLS handshake and the Carrier handshake — they run sequentially,
unlike AzNetworking where `InitiateConnectionPacket` carries the DTLS
ClientHello inside itself. **This is the single biggest architectural
difference from AzNetworking.**

### 4.4 Record format

Standard DTLS 1.2 records (13-byte DTLS header + GCM-encrypted payload).
No GridMate-specific framing inside the DTLS record — the record payload
*is* the Carrier datagram from §1.2.

---

## 5. Replica system

GridMate's replica system is the game-state-replication layer on top of
Carrier. This is the part most aggressively extended by New World.

### 5.1 Terminology

- **Replica** — a network-replicated entity. Container of one or more
  chunks. Has a `ReplicaId` (u32).
- **ReplicaChunk / ReplicaChunkBase** — the unit of behavior. One
  Replica has up to `GM_MAX_CHUNKS_PER_REPLICA = 64` chunks
  (`ReplicaCommon.h:27`). A chunk exposes **DataSets** (state) and
  **RPCs** (calls). In New World terms: expect `*ComponentClientFacet` /
  `*ComponentServerFacet` to be chunk subclasses.
- **Master / Proxy** — each Replica has exactly one authoritative Master
  instance on the owning peer; every other peer has a Proxy copy
  (`Replica.h:65–77`).
- **Peer** — a participant (host or client). Identified by `PeerId` (u32,
  Crc32-derived, `ReplicaDefs.h:39`).
- **DataSet** — templated typed state member; Master-writes propagate to
  Proxies. Marked dirty per-field via a bitset, up to
  `GM_MAX_DATASETS_IN_CHUNK = 32` per chunk (`ReplicaCommon.h:28`).
- **RPC** — remote call. See §6.

### 5.2 ReplicaChunkClassId — how chunks identify themselves

`typedef AZ::Crc32 ReplicaChunkClassId;` (`ReplicaDefs.h:38`).
Every concrete chunk class must define `static const char* GetChunkName()`
returning a *string*. The class id is `AZ::Crc32(GetChunkName())`. The
system uses this Crc32 to dispatch unmarshaling.

Known stock chunk names (`grep -r 'GetChunkName'`):
- `"GridMateReplicaStatus"` — `ReplicaStatus.h:37` (per-replica status).
- `"GridMateReplicaSessionInfo"` — `SystemReplicas.h:51` (session-wide
  singleton).
- `"GridMatePeerReplica"` — `SystemReplicas.h:100` (per-peer replica).
- `"BitmaskInterestChunk"` — `BitmaskInterestHandler.h:141`.
- `"ProximityInterestChunk"` — `ProximityInterestHandler.h:173`.

**Every New World replica chunk class will have its own string name.**
These will be the single most valuable strings in the Javelin binary:
every `*Facet`, `*Messages`, etc. class registers itself with a chunk
name. **Hunt list for Ghidra**: functions returning a constant `const
char*` whose only callsite is a `ReplicaChunkDescriptorTable::RegisterChunkType`
wrapper. That's your chunk-name registry.

### 5.3 Top-level replica command byte

The replica stream sits inside a reliable message on a user channel.
Every replica record starts with a **`CmdId` byte** — `typedef ReplicaId
CmdId; // u32`, but on the wire the dispatcher uses the first byte-worth
in practice (see below).

Reserved command ids (`ReplicaDefs.h:41–58`):

| Id | Name                  | Semantic |
|---:|-----------------------|----------|
| 0  | `Invalid_Cmd_Or_Id`   | invalid |
| 1  | `Cmd_Greetings`       | first message after Carrier connect; exchanges PeerIds |
| 2  | `Cmd_NewProxy`        | instantiate a new proxy (ctor + datasets + rpcs) |
| 3  | `Cmd_DestroyProxy`    | destroy a proxy |
| 4  | `Cmd_NewOwner`        | ownership transfer; recipient becomes Master |
| 5  | `Cmd_Heartbeat`       | empty keep-alive |
| 6  | `Cmd_Count`           | sentinel |
| 7  | `RepId_SessionInfo`   | fixed id of the SessionInfo replica |
| 8  | `Max_Reserved_Cmd_Or_Id` | anything ≥ this is a real `ReplicaId` |

**Dispatcher trick** (`ReplicaMgr.cpp:1232–1241`): if `cmdhdr >=
Cmd_Count` the receiver interprets the *cmd byte itself* as the
`ReplicaId` and dispatches as an "update existing replica" — saves a
byte per update packet. Proxy creation / destruction / heartbeat use
dedicated small ids; plain updates inline the ReplicaId as the dispatch
key.

### 5.4 Outer frame from `ReplicaManager::_Unmarshal`

`ReplicaMgr.cpp:1005–1286`:

```
[u32]       timestamp                                 (ReplicaMgr.cpp:1021)
loop until empty:
  [CmdId]   cmdhdr (1 byte for reserved commands; or u32 for replicaId updates)
  switch(cmdhdr):
    case Cmd_Greetings:     → PeerId(u32), bool peerIsHost, optional RepIdSeed(u32)
    case Cmd_Heartbeat:     → (no further data, just resets timeout)
    case Cmd_NewOwner:
    case Cmd_NewProxy:
        [bool]   isSyncStage         (1 byte)
        [bool]   isMigratable        (1 byte)
        [u32]    createTime
        [u32]    ownerSeq
        [u32]    repId
        [PackedSize] chunkSize       (VLQ — see §5.7)
        [bytes]  replicaPayload       (chunkSize bytes)
    case Cmd_DestroyProxy:
        [u32]    repId
    default (treated as existing replicaId update):
        [PackedSize] chunkSize
        [bytes]  replicaPayload
```

`replicaPayload` is then decoded by `Replica::Unmarshal`
(`Replica.cpp:644–718`):

```
[u64 VLQ]  chunkManifest bits          (up to GM_MAX_CHUNKS_PER_REPLICA = 64 chunks)
for each bit set in manifest:
  [PackedSize] chunkSize
  [bytes]  chunk payload, length-prefixed so skip-on-unknown-chunk is possible
    if hasCtorData (i.e. Cmd_NewProxy/Cmd_NewOwner path):
      [u32 Crc32] replicaChunkClassId     (VLQ-encoded as u32; see 5.5)
      [bytes]     ctor-data              (per-chunk-type, opaque)
    chunk.Unmarshal:
      MarshalDataSets:
        [u32 VLQ]  dirtyDataSetMask bits  (one bit per dataset in the chunk)
        for each bit set:
          [bytes]  dataset value (raw per-field marshaler output)
      MarshalRpcs:
        [u32 VLQ]  rpcCount
        for rpcCount times:
          [u8]  rpcIndex                  (index into descriptor's VRT)
          [rpc marshal body]              (see §6)
```

### 5.5 Per-chunk payload

From `ReplicaChunkBase::MarshalDataSets` / `MarshalRpcs`
(`ReplicaChunk.cpp:339–499`):

- **Dataset change bitmap**: written as a **VLQ-u32** at the start of the
  chunk payload. Bit `i` set means dataset index `i` is in the stream
  that follows. `*m_reliableDirtyBits.data()` is cast to u32.
- **Dataset values**: for each set bit, the raw marshaled bytes of that
  dataset's marshaler output (no per-field length prefix — so the
  reader must know the marshaler exactly; this is why
  `ReplicaChunkClassId` must match for dispatch).
- **RPC count**: VLQ-u32.
- **RPCs**: each RPC is `{u8 rpcIndex, [rpc body]}`. `rpcIndex` is into
  the chunk's RPC table (VRT), capped at
  `GM_MAX_RPCS_DECL_PER_CHUNK = 32` (`ReplicaCommon.h:29`). Since
  `rpcIndex` is 8-bit, effectively indices 0–31 are used. RPC body shape
  in §6.

### 5.6 Update vs NewProxy differences

- **`Cmd_NewProxy` / `Cmd_NewOwner`**: `IncludeCtorData` flag is set,
  every chunk emits its `ReplicaChunkClassId` + `MarshalCtorData` before
  its dataset/RPC stream. These are **reliable** messages
  (`ReplicaMarshalTasks.cpp:119` uses `GetReliableOutBuffer`).
- **Regular updates** (ReplicaId cmd byte): no ctor data. Datasets can
  ride on either the reliable or unreliable buffer depending on which
  datasets changed and their throttle policies (`ReplicaMgr.cpp` writes
  both `m_reliableOutBuffer` and `m_unreliableOutBuffer`).
- **`Cmd_DestroyProxy`**: just the ReplicaId — no payload.

### 5.7 `PackedSize` / VLQ encoding

Sizes are VLQ-encoded. `VlqU32Marshaler` (`CompressionMarshal.h:345–420`)
uses a "1's prefix" format:

| First byte | Total bytes | Max value     |
|-----------:|------------:|--------------:|
| `0xxxxxxx` | 1           | 127           |
| `10xxxxxx` | 2           | ~16K          |
| `110xxxxx` | 3           | ~2M           |
| `1110xxxx` | 4           | ~256M         |
| `11110xxx` | 5           | ~4B (u32 max) |

Layout for multi-byte: low bits of value spread across bytes, little-end
first (see `Marshal()` at `CompressionMarshal.h:350–388`). **This is not
protobuf varint** — the bit pattern is inverted (leading 1s count the
*extra* bytes) and is little-endian-byte-order within the VLQ. Any
Ghidra function that does `if (b < 0x80) return b; else if (b < 0xc0)
...` on the first byte is this. **Critical for field extraction.**

`VlqU64Marshaler` uses 1..9 bytes with the same pattern extended
(`CompressionMarshal.h:433+`).

### 5.8 PeerId / HostId

- `PeerId = AZ::u32 = AZ::Crc32` of some host-unique string
  (`ReplicaDefs.h:39`).
- `RepIdSeed = ReplicaId` — hosts hand out blocks of
  `GM_REPIDS_PER_BLOCK = 1<<25` (~33M) replica ids per block,
  `GridMate/Replica/ReplicaCommon.h:32`.

---

## 6. RPC mechanism

### 6.1 Declaration style

`GridMate/Replica/RemoteProcedureCall.h` defines the `Rpc<>` template.
RPCs are **members of a chunk class** and bind to a method:

```cpp
Rpc<RpcArg<PeerId>>::BindInterface<
    MyChunk, &MyChunk::OnFoo, RpcAuthoritativeTraits> m_fooRpc;
```

Traits (`RemoteProcedureCall.h:40–60`):
- `RpcDefaultTraits`: reliable, postAttached, allowNonAuth req + relay.
- `RpcAuthoritativeTraits`: reliable, disallow non-auth requests.
- `RpcUnreliable`: unreliable variant of default.

### 6.2 Wire format

From `RpcBindBase::Marshal` (`RemoteProcedureCall.h:403–416`) and
`MarshalRpcs` (`ReplicaChunk.cpp:472–480`):

```
[u8]                 rpcIndex                           — index into chunk's RPC table
[u32]                m_timestamp                         — RpcContext.m_timestamp
[bool→u8]            m_authoritative                     — true if Master-originated (§5.7)
[u32, optional]      m_sourcePeer    — only if Traits::s_alwaysForwardSourcePeer
[variadic args...]                    — each marshaled by its type's Marshaler<T>
```

The `rpcIndex` byte is the chunk-local index — lookup via
`ReplicaChunkDescriptor::GetRpc(base, index)`
(`ReplicaChunkDescriptor.h:74`). Resolution is chunk-type-dependent, so
the receiver MUST have dispatched the enclosing chunk update to a chunk
of the right `ReplicaChunkClassId` first.

### 6.3 Parameter marshaling

Each arg uses `Marshaler<T>` (`DataMarshal.h`). Defaults:

- Fundamental ints (u8/s8..u64/s64): raw bytes, endian-swapped to
  big-endian on send (`DataMarshal.h:80–92`).
- `bool`: **packed as 1 bit, NOT a byte**, via `WriteRawBit` /
  `ReadRawBit` (`DataMarshal.h:109–121`). This is different from
  AzNetworking. Bits pack into bytes across sequential bool writes in
  the buffer.
- Enums: written as their underlying type (`DataMarshal.h:128–148`).
- Vec2/Vec3/Quaternion: raw 3/4 floats (`CompressionMarshal.h:72–240`)
  OR compressed variants (`Float16Marshaler`, `Vec3CompMarshaler`,
  `QuatCompNormMarshaler`, etc.) if the programmer picks a compressor
  marshaler explicitly.
- `VlqU32Marshaler` / `VlqU64Marshaler`: as in §5.7.
- User types must provide `Marshaler<T>` specializations.

**Consequence for binary analysis:** bit-packed booleans will show up in
Ghidra as an 8-bit running buffer with a bit index. Unlike AzNetworking,
which always writes 1 byte per bool.

### 6.4 Queue and invocation

`operator()` on the Rpc binding (`RemoteProcedureCall.h:364–394`):

1. If caller is Master: invoke locally immediately (forward handler),
   then maybe queue a copy for serialization to Proxies.
2. If caller is not Master: queue with `m_authoritative = false` — will
   be sent *upstream* to Master; Master decides to relay.

RPC reliability is encoded in `Traits::s_isReliable` and chooses
reliable vs unreliable outbound buffer. Reliability is **not** serialized
(`NetworkEntityRpcMessage.cpp:174` comment equivalent at
`RemoteProcedureCall.h:390`).

---

## 7. Session / Carrier handshake

There are **three layers** of handshake, run in order:

### 7.1 Layer 1: DTLS handshake

Standard DTLS 1.2, driven by `SecureSocketDriver::Connection` state
machine (§4.2). All Carrier traffic is blocked until `CS_ESTABLISHED`.

### 7.2 Layer 2: Carrier handshake

After DTLS, the Carrier sends the first user-level packets. Driven by
`Handshake` interface (`Handshake.h`). Default implementation
(`DefaultHandshake.cpp`):

```
Client                                 Server
------                                 ------
SM_CONNECT_REQUEST (SEND_UNRELIABLE)   →
  payload = Handshake::OnInitiate
            = [VersionType m_version]
                                       ← OnReceiveRequest writes
                                         [VersionType m_version] back
                                       ← SM_CONNECT_ACK (SEND_RELIABLE)
OnReceiveAck (verifies)                →
                                         state = CST_CONNECTED,
                                         OnConnectionEstablished event
state = CST_CONNECTED
```

Key details:
- `SM_CONNECT_REQUEST` is sent **unreliable with exponential backoff retry**
  by the client (`Carrier.cpp:4396–4407`). Retries start at
  `m_connectionRetryIntervalBase = 10ms`, doubling up to
  `m_connectionRetryIntervalMax = 1000ms`.
- `SM_CONNECT_REQUEST` sets the `MF_CONNECTING` flag (bit 7) on the
  message header — this is how the receiver distinguishes it from normal
  traffic before any connection exists.
- `VersionType` is the `CarrierDesc::m_version` (u32 by default, but
  templated — `Carrier.h:278`). Mismatch → `VERSION_MISMATCH` →
  `DISCONNECT_VERSION_MISMATCH`.
- `SM_CONNECT_ACK` is `SEND_RELIABLE` (`Carrier.cpp:4453`).
- Handshake buffer (`Handshake::OnInitiate`) is a `WriteBuffer` — the
  game-specific Handshake subclass can stuff **arbitrary auth data**
  into it. **This is almost certainly where New World sends its login
  ticket** (from the REP "registration" phase in `docs/connection-flow.md`).
  Look for a Handshake subclass whose `OnInitiate` writes a
  UUID-string-sized blob plus version.

### 7.3 Layer 3: Replica handshake

After Carrier completes, if this peer participates in replica
replication, it sends `Cmd_Greetings` on a user channel
(`ReplicaMgr.cpp:1423`):

```
peer->GetReliableOutBuffer().Write(Cmd_Greetings);
  then: PeerId(u32), bool peerIsHost, optional RepIdSeed(u32) if host
```

This is what provisions the PeerId and optionally hands out the
first block of replica ids (host only). Only after this does normal
replica streaming begin.

### 7.4 Disconnect

Three paths:

- Local graceful: `Disconnect(id)` → `SM_DISCONNECT` (SEND_RELIABLE) →
  peer receives, transitions to `CST_DISCONNECTED`.
  `Carrier.cpp:3836–3854`.
- Timeout: no packets for `m_connectionTimeoutMS` (default 5000ms) → 
  `DISCONNECT_BAD_CONNECTION`. `Carrier.cpp:1975`.
- DTLS failure: surfaces as driver error → `DISCONNECT_DRIVER_ERROR`.

All disconnect reasons: `CarrierDisconnectReason`
(`Carrier.h:377–397`): `USER_REQUESTED, BAD_CONNECTION, BAD_PACKETS,
DRIVER_ERROR, HANDSHAKE_REJECTED, HANDSHAKE_TIMEOUT,
WAS_ALREADY_CONNECTED, SHUTTING_DOWN, DEBUG_DELETE_CONNECTION,
VERSION_MISMATCH`.

### 7.5 Clock sync

`SM_CLOCK_SYNC` (channel 3, system msg id 4) is sent periodically from
the peer with clock authority (`Carrier.cpp:4786–4788`,
`StartClockSync`). Default interval 1000ms. Allows ~100–250ms-accuracy
shared clock — see `Carrier.h:188–204`.

---

## 8. Identifiable strings and UUIDs

### 8.1 AZ_TYPE_INFO / AZ_RTTI UUIDs

Unlike AzNetworking, GridMate has **relatively few** type-info GUIDs —
the Carrier/Replica machinery mostly uses runtime CRC32s
(`ReplicaChunkClassId`), not GUIDs. But the Marshalers do, and they'll
show up in `.rdata`:

| Marshaler                   | UUID |
|-----------------------------|------|
| `Marshaler<fundamental>`    | `1AE954E2-67E8-4EDC-A16A-577411F5B876` (legacy template) |
| `Marshaler<bool>`           | `8F3A6078-DE15-4D3F-8795-6FFAF1275AF1` (legacy template) |
| `Float16Marshaler`          | `CEC3001A-3DE2-42A7-BCCB-38F61477237D` |
| `HalfMarshaler`             | `A11F3B68-423A-472D-8D8C-6A2923ECB155` |
| `Vec2CompMarshaler`         | `7BB471FB-1A1F-47BD-A599-C23417FEEDE0` |
| `Vec3CompMarshaler`         | `F20132F4-CA69-4F6F-A379-0BCF990E6672` |
| `Vec3CompRangeMarshaler`    | `F972DD2D-19A1-4D0C-A0A3-BC84A3C73341` |
| `Vec3CompNormMarshaler`     | `80A7F05E-2F24-4CF4-AC91-C1C683D7CB2B` |
| `QuatCompMarshaler`         | `21C83ED8-5E0E-4A5E-862D-9F1EBBD0CF4C` |
| `QuatCompNormMarshaler`     | `8C39D143-F64E-45A8-B135-E10A06923CD2` |
| `QuatCompNormQuantizedMarshaler` | `D4318C51-839B-40BE-9850-417177AC9B22` |
| `TransformCompressor`       | `30E9BADC-2CC3-46AF-B472-5A97E1FEC7EE` |
| `VlqU32Marshaler`           | `BD9A38BB-713E-44FD-A517-8B3B782BDAAF` |
| `VlqU64Marshaler`           | `F1141AF7-499D-4A75-A35E-8325B2EB182B` |
| `GridMateAllocator`         | `BB127E7A-E4EF-4480-8F17-0C10146D79E0` |
| `GridMateAllocatorMP`       | `FABCBC6E-B3E5-4200-861E-A3EC22592678` |

**TBD (needs Ghidra)**: verify these survive into NewWorld.exe `.rdata`.
If Amazon forked GridMate pre-2017, the UUIDs may be the **same** (and
match the binary) or may have been rerolled when they rebranded to
Javelin. The absence of `"GridMate"` as a log tag in the 5001 Javelin
classes but presence of 30 `"GridMate"` string hits suggests some
infrastructure kept the name.

### 8.2 Stock chunk-name strings

Each of these is a `const char*` literal that becomes a CRC32 at runtime
— and will be in `.rdata` verbatim:

- `"GridMateReplicaStatus"`
- `"GridMateReplicaSessionInfo"`
- `"GridMatePeerReplica"`
- `"BitmaskInterestChunk"`
- `"ProximityInterestChunk"`

Javelin will have **renamed these to "Javelin*"** (consistent with the
5001 `Javelin::` class hits vs 0 `GridMate::` class hits). Expect
strings like `"JavelinReplicaStatus"`, `"JavelinReplicaSessionInfo"`,
`"JavelinPeerReplica"` — high-value hunting targets. New World-specific
chunks will use application-specific names (e.g.,
`"PlayerComponentServerFacet"` etc. — **every such string in the binary
is a chunk name** and each one corresponds to a Javelin class that
defines datasets and RPCs we need to map).

### 8.3 Log tags / AZ_TracePrintf categories

- `"GridMate"` — the primary log tag for nearly all traces
  (`Carrier.cpp:1302`, `1327`, `1975`, `2010`, `2042`, `2198`,
  `2249`, `2256`, `2266`, `2289`, ...). 30 hits in the NW binary likely
  come from these — would strongly suggest the log tag was preserved.
- `"GridMateSecure"` — `SecureSocketDriver.cpp:1455`, `1552`, `1558`.
- `"Carrier"` — `Carrier.cpp:2198` (single-string tag).

### 8.4 Distinctive log message templates

Unique enough to fingerprint even if slightly edited:

- `"We have NOT received packet from %s for %d ms. Connection is lost!"`
  — `Carrier.cpp:1975`
- `"Handshake to %s did not complete within %d ms!"` — `Carrier.cpp:2010`
- `"bad traffic conditions to %s !"` — `Carrier.cpp:2042`
- `"Carrier was NOT updated for >%u ms, you should call Update() regularly!"`
  — `Carrier.cpp:2256`
- `"Thread connection to %s already exists!"` — `Carrier.cpp:2289`
- `"Packet appears to be corrupted or stream is misaligned, ignoring rest of stream."`
  — `Carrier.cpp:3557`
- `"Decompress failed with error %d this will lead to data read errors!"`
  — `Carrier.cpp:1709`
- `"Received replica, id 0x%x, with old ownerSeq. Discarding %d bytes"`
  — `ReplicaMgr.cpp:1162` (commented out by default, may not be present)
- `"Cannot find descriptor for rpcIndex %hhu!"` —
  `ReplicaChunk.cpp:522`
- `"Failed to unmarshal RPC <%s>!"` — `ReplicaChunk.cpp:530`
- `"Discarding authoritative RPC <%s> from %p because it did not come from the expected upstream hop"`
  — `ReplicaChunk.cpp:539`
- `"Replica type %s(0x%x) already registered. New registration ignored."`
  — `ReplicaChunkDescriptor.h:169`
- `"Cannot find replica chunk descriptor for %s. Did you remember to register the chunk type?"`
  — `ReplicaFunctions.h:32`, `ReplicaFunctions.inl:62`
- `"GridMate-Carrier"` — the carrier thread name
  (`Carrier.cpp:1314`). Thread names often survive into release
  builds via `SetThreadDescription`.

### 8.5 OpenSSL hints

- Cipher string: `"ECDHE-RSA-AES256-GCM-SHA384"` — exact literal at
  `SecureSocketDriver.cpp:1494`. Same string as AzNetworking; matches
  what we see in the New World DTLS handshake capture.
- Cookie secret: `COOKIE_SECRET_LENGTH = 16` (`SecureSocketDriver.h:55`);
  `MAX_COOKIE_LENGTH = 255` (`:56`).

### 8.6 Compile-time constants

Distinctive enough for memcmp scans:

- `k_maxNumberOfChannels = 4`
- `k_systemChannel = 3`
- `GM_MAX_CHUNKS_PER_REPLICA = 64`
- `GM_MAX_DATASETS_IN_CHUNK = 32`
- `GM_MAX_RPCS_DECL_PER_CHUNK = 32`
- `GM_REPIDS_PER_BLOCK = 1<<25 = 33554432`
- `SequenceNumberMax = 0xFFFF`, `SequenceNumberHalfSpan = 0x7FFF`
- Default `m_connectionTimeoutMS = 5000`
- `m_datagramHistoryMaxNumberOfBytes = 64`, max history 512 datagrams

---

## 9. GridMate → Javelin class mapping

Our binary scan shows 730 `Javelin::*` class strings. Based on the
observed naming (`*ComponentClientFacet`, `*ComponentServerFacet`,
`*ComponentClientMessages`, `*ComponentServerMessages`), the Javelin
renaming appears to be:

- `GridMate::` prefix → `Javelin::` prefix (almost certainly a global
  namespace rename)
- `ReplicaChunk` with RPCs → split into two parallel chunks:
  - `*Facet` — the DataSet half (property replication), one per peer role
  - `*Messages` — the RPC half, one per peer role
- Role suffix `Client` / `Server` instead of GridMate's
  master/proxy / authoritative terminology

This is consistent with GridMate pattern but is a **New World-specific
architectural split**. Stock GridMate puts datasets + rpcs in the same
chunk class. Javelin appears to separate them so that a component's
state machine and its RPC surface are independently versioned.

Predicted mapping (best-effort; confirm in Ghidra):

| Stock GridMate class              | Likely Javelin equivalent(s) |
|-----------------------------------|-------------------------------|
| `GridMate::Carrier`               | `Javelin::Carrier` (possibly `NetworkCarrier`) |
| `GridMate::CarrierImpl`           | `Javelin::CarrierImpl` |
| `GridMate::CarrierThread`         | `Javelin::CarrierThread` |
| `GridMate::SocketDriver`          | `Javelin::SocketDriver` |
| `GridMate::SecureSocketDriver`    | `Javelin::SecureSocketDriver` (or `DTLSDriver`) |
| `GridMate::DefaultHandshake`      | `Javelin::DefaultHandshake` or NW-specific (see 7.2) |
| `GridMate::DefaultTrafficControl` | `Javelin::DefaultTrafficControl` |
| `GridMate::Handshake` interface   | `Javelin::Handshake` / `INetworkHandshake` |
| `GridMate::Replica`               | `Javelin::Replica` |
| `GridMate::ReplicaManager`        | `Javelin::ReplicaManager` / `Javelin::ReplicaMgr` |
| `GridMate::ReplicaChunkBase`      | `Javelin::ReplicaChunkBase` or split into Facet/Messages base pair |
| `GridMate::ReplicaChunkDescriptor`| `Javelin::ReplicaChunkDescriptor` |
| `GridMate::ReplicaChunkDescriptorTable` | `Javelin::ReplicaChunkDescriptorTable` |
| `GridMate::DataSet<T>`            | `Javelin::DataSet<T>` (template) |
| `GridMate::RpcBase` / `Rpc<>`     | `Javelin::RpcBase` / `Javelin::Rpc<>` |
| `GridMate::Replica` (system) `SessionInfo` | `Javelin::SessionInfo` (chunk name `"JavelinReplicaSessionInfo"`? **TBD**) |
| `GridMate::ReplicaInternal::PeerReplica` | `Javelin::PeerReplica` (chunk name `"JavelinPeerReplica"`? **TBD**) |
| `GridMate::ReplicaStatus`         | `Javelin::ReplicaStatus` (chunk name `"JavelinReplicaStatus"`? **TBD**) |
| `GridMate::ReplicaChunk` subclass | `*ComponentClientFacet` / `*ComponentServerFacet` (data) + `*ComponentClientMessages` / `*ComponentServerMessages` (RPCs) — **New World extension** |
| `GridMate::InterestManager`       | likely `Javelin::InterestManager`; AOI streaming is critical for a seamless MMO |
| `GridMate::BitmaskInterestHandler` | possibly replaced by spatial/zone-based handler (NW world is huge) |
| `GridMate::Session`               | `Javelin::Session` or equivalent |
| `GridMate::WriteBuffer` / `ReadBuffer` | `Javelin::WriteBuffer` / `ReadBuffer` |
| `GridMate::Marshaler<T>`          | `Javelin::Marshaler<T>` |

### 9.1 What to look for first in Ghidra

Priority order for mapping the Javelin binary to GridMate:

1. **Find the cipher string `"ECDHE-RSA-AES256-GCM-SHA384"`.** Its xref
   gives you `SecureSocketDriver::Initialize` equivalent — that function
   is the root of the entire network stack. From there, virtual destructor
   xrefs identify the `SecureSocketDriver` vtable. Every function in
   that vtable is a one-to-one with `SecureSocketDriver.h`.

2. **Find `"GridMate"` / `"GridMateSecure"` / `"GridMate-Carrier"`
   strings** (scan found 30 hits). Their xrefs land in log-statement call
   sites — you can fingerprint ~15 distinct Carrier functions by the
   surrounding format string (see 8.4).

3. **Find calls to `SSL_read` / `SSL_write` / `DTLSv1_2_method` /
   `SSL_set_mtu`.** These cluster in exactly the functions listed in §4.

4. **Find the small function that reads `u16` (sequence number) from a
   buffer and returns it.** That's `ReadDataGramHeader`. Its single
   caller is `OnReceivedIncomingDataGram` — the main receive path.

5. **Find a function reading a 1-byte flag field, validating `(flags &
   0x42) == 0`**, then conditionally reading u16/u8/u16/u16 based on
   flag bits 5,2,3,4. That's `ReadMessageHeader`. Exactly these bit
   masks — `Carrier.cpp:3555` and `3576`/`3588`/`3597`/`3607`.

6. **Find any function that writes a u32 `timestamp` then enters a
   switch on a 1-byte `cmdhdr`** — that's `ReplicaManager::_Unmarshal`
   (§5.4). Its switch table directly enumerates the `Cmd_*` values
   1..5.

7. **Harvest chunk-name strings.** Every `const char*` literal passed
   to a call that resolves to `ReplicaChunkDescriptorTable::RegisterChunkType`
   is a New World chunk name. These are the payloads we need to decode.
   With the 730 `Javelin::` class strings, there may be 100–300 unique
   chunk names.

8. **Map `Cmd_Greetings` / `Cmd_NewProxy` / `Cmd_DestroyProxy` cases.**
   The `Cmd_NewProxy` branch reads the exact tuple `{bool, bool, u32,
   u32, u32, PackedSize, bytes}` (§5.4). That byte-sequence signature is
   a strong fingerprint.

### 9.2 What will NOT match stock GridMate

Confidence based on New World's scale and MMO requirements:

- **Much larger AOI / replication-window system.** Stock GridMate's
  `BitmaskInterestHandler` / `ProximityInterestHandler` are toy
  implementations for small sessions. Javelin almost certainly has
  grid/octree/voxel-based interest management for the seamless world.
  Expect **many** NW-specific classes here.
- **Additional handshake payload.** The Handshake layer (§7.2) likely
  carries NW's login ticket (UUID from the HTTPS gateway) + character
  id + world id. Stock GridMate just sends a version u32.
- **Non-default traffic control.** `DefaultTrafficControl` is simple
  AIMD-style; MMO servers often ship with custom bandwidth management.
- **Chunk-type versioning.** If shipped as stock, `ReplicaChunkClassId =
  Crc32(name)` has no explicit version — any string change breaks
  compat. NW likely added a per-chunk version field or embedded a hash
  of the field layout in the chunk name itself.
- **Custom RPC traits** beyond the three stock ones. New World has
  latency-sensitive abilities, physics sync, etc. — expect 5–10 custom
  trait structs.
- **Possibly different datagram compression.** Stock ships a
  MultiplayerCompressor (LZ4-based usually); NW may have added its own
  dictionary. Compression hint byte position (§1.2) is still our
  fingerprint.

### 9.3 What almost certainly IS intact

Stuff the developers don't rewrite when rebranding:

- Big-endian on the wire (no reason to change).
- 2-byte SequenceNumber, half-span comparison semantics.
- Message flags byte layout (bits 0,2,3,4,5,7 as described in §2.2).
- System message ids 1..8 (`SM_CONNECT_REQUEST` etc.).
- DTLS 1.2 + the exact cipher string.
- `Cmd_*` reserved ids at the start of the replica dispatch switch.
- VLQ encoding format.
- 4-channel limit with channel 3 reserved for system.

---

## Appendix: Source file index

All paths relative to `C:\Users\charl\Programs\lumberyard\dev\Code\Framework\GridMate\`.

| Concern | File |
|---------|------|
| Carrier interface | `GridMate/Carrier/Carrier.h` |
| Carrier impl + wire format | `GridMate/Carrier/Carrier.cpp` (esp. 600–700, 2576–2687, 2866–3627) |
| Traffic control + SequenceNumber | `GridMate/Carrier/TrafficControl.h`, `.cpp`, `DefaultTrafficControl.*` |
| Handshake interface | `GridMate/Carrier/Handshake.h` |
| Default handshake | `GridMate/Carrier/DefaultHandshake.cpp` |
| DTLS driver | `GridMate/Carrier/SecureSocketDriver.h`, `.cpp` |
| Base socket driver | `GridMate/Carrier/SocketDriver.h`, `.cpp` |
| Simulator (for testing lossy conditions) | `GridMate/Carrier/DefaultSimulator.*` |
| Replica interface | `GridMate/Replica/Replica.h`, `.cpp` |
| Chunk | `GridMate/Replica/ReplicaChunk.h`, `.cpp` |
| Chunk descriptor + class id registry | `GridMate/Replica/ReplicaChunkDescriptor.h`, `.cpp` |
| Dataset | `GridMate/Replica/DataSet.h`, `.cpp` |
| RPC | `GridMate/Replica/RemoteProcedureCall.h`, `.cpp` |
| Replica manager (top-level dispatcher) | `GridMate/Replica/ReplicaMgr.h`, `.cpp` (esp. 945–1286) |
| System replicas (SessionInfo, PeerReplica) | `GridMate/Replica/SystemReplicas.h`, `.cpp` |
| Reserved ids (`Cmd_*`) | `GridMate/Replica/ReplicaDefs.h` |
| Replication window | `GridMate/Replica/Interest/*` |
| Marshal tasks (outgoing frame build) | `GridMate/Replica/Tasks/ReplicaMarshalTasks.cpp` |
| Buffer primitives | `GridMate/Serialize/Buffer.h`, `.cpp` |
| Fundamental marshalers | `GridMate/Serialize/DataMarshal.h` |
| VLQ, quantized vec/quat | `GridMate/Serialize/CompressionMarshal.h` |
| Session service | `GridMate/Session/Session.h`, `.cpp` |
| Top-level module | `GridMate/GridMate.cpp`, `GridMate.h` |
