# AzNetworking Protocol Reference

> Deep-read of O3DE source at `C:\Users\<username>\Programs\o3de\`. All citations are
> against that tree. This is the reference we will use to match Ghidra
> findings against a known protocol when NewWorld.exe analysis completes.
>
> O3DE commit: whatever is checked out in that sparse clone (user did not
> specify — callers should record it before relying on line numbers).
>
> **Scope:** Everything below describes *stock O3DE AzNetworking + the
> Multiplayer Gem*. New World has almost certainly extended/replaced the
> Multiplayer Gem layer (NetworkEntityUpdateMessage, EntityUpdates packet,
> auth token in `Connect`, actor/GDE concepts, etc.). The AzNetworking
> transport layer (UdpPacketHeader, DTLS handoff, CorePackets 0–4) is
> likely intact or close to intact, since that's the fabric below the
> game layer. See Section 8 for which classes to expect New-World-specific
> behavior in.

---

## Table of contents

1. [UdpPacketHeader layout](#1-udppacketheader-layout)
2. [Serialization primitives](#2-serialization-primitives)
3. [IPacket interface & vtable](#3-ipacket-interface--vtable)
4. [Core packet type catalog](#4-core-packet-type-catalog)
5. [DTLS → AzNetworking handoff](#5-dtls--aznetworking-handoff)
6. [Connection state machine](#6-connection-state-machine)
7. [Identifiable strings](#7-identifiable-strings)
8. [Known New World extensions](#8-known-new-world-extensions)

---

## 1. UdpPacketHeader layout

After DTLS decrypt, every datagram begins with a packet-flags byte followed
by the serialized `UdpPacketHeader`. The framework reads these in **two
stages** (`UdpNetworkInterface.cpp:244–284`):

1. `SerializePacketFlags` reads the 1-byte flag bitset first.
   `UdpPacketHeader.cpp:88–91`.
2. `Serialize` reads the rest of the header fields.
   `UdpPacketHeader.cpp:69–86`.

### 1.1 Field order, sizes, endianness

| Off | Size | Field               | Encoding                                   | Source |
|----:|-----:|---------------------|--------------------------------------------|--------|
| 0   | 1    | `m_packetFlags`     | `FixedSizeBitset<1, uint8_t>` — 1 byte     | `IPacketHeader.h:28` / `UdpPacketHeader.cpp:90` |
| 1   | 2    | `m_packetType`      | `PacketType` = `uint16_t`, **network byte order** (htons) | `IPacket.h:19`, `NetworkInputSerializer.cpp:69` |
| 3   | 2    | `m_localSequence`   | `SequenceId` = `uint16_t`, htons           | `SequenceGenerator.h:15` |
| 5   | 2    | `m_remoteSequence`  | `SequenceId` = `uint16_t`, htons           | same |
| 7   | 4    | `m_sequenceWindow`  | `BitsetChunk` = `uint32_t`, htonl (ack vector) | `RingBufferBitset.h:17` |
| 11  | 1    | `isReliable`        | boolean serialized as 1 byte (0/1)         | `NetworkInputSerializer.cpp:31–35` |
| 12  | 2    | `m_reliableSequence`| **only present when `isReliable == 1`**; `SequenceId` = `uint16_t`, htons | `UdpPacketHeader.cpp:80–83` |

Header total size: **12 bytes (unreliable)** or **14 bytes (reliable)**. The
payload (the serialized `IPacket`) follows immediately.

Note on `m_localRolloverCount` (`uint16_t`, `NetworkCommon.h:22`): it is
**not** serialized — it's reconstructed locally from the sequence number for
`MakePacketId()`. See `UdpPacketHeader.inl:18–22`.

### 1.2 Packet flags byte (offset 0)

Only one flag is defined in stock O3DE: `PacketFlag::Compressed`
(`IPacketHeader.h:24–27`). The bitset uses 1 byte (`static_assert` at
`IPacketHeader.h:29`). Bit 0 = `Compressed`. Bits 1–7 reserved.

The flags byte is **never compressed, never encrypted at the AzNetworking
layer** (it sits inside the DTLS record, but it is not passed through the
`ICompressor`). This matters because the receiver has to read flags to know
whether to decompress the rest of the payload (`UdpNetworkInterface.cpp:244–267`).

### 1.3 Endianness summary

All multi-byte integers go through `htons`/`htonl`/`htonll` on send and
`ntohs`/`ntohl`/`ntohll` on receive. See `NetworkInputSerializer.cpp:158–171`
and `NetworkOutputSerializer.cpp:160–178`. **Everything is big-endian on the
wire.**

### 1.4 Identifiers

- `UdpPacketHeader` AZ_RTTI: `{21A11FF3-6829-4A59-9906-C06EF7F39AC1}`, base
  `IPacketHeader` (`UdpPacketHeader.h:30`).
- `IPacketHeader` AZ_TYPE_INFO: `{90A0EFE3-01A4-4F04-87CF-E98E94D49648}`
  (`IPacketHeader.h:50`).
- `IPacket` AZ_TYPE_INFO: `{1B33BFE8-8A4B-44E3-8C8D-3B924093227C}`
  (`IPacket.h:36`).

These UUIDs are **TBD whether they appear in the NewWorld.exe `.rdata`** —
AZ_TYPE_INFO only emits the UUID when reflection is used. Ghidra should
check for these as 16-byte constants.

---

## 2. Serialization primitives

All packet fields flow through `ISerializer`
(`Serialization/ISerializer.h:39`). Two concrete serializers matter on
the wire:

- `NetworkInputSerializer` — write mode (object → bytes).
  `Serialization/NetworkInputSerializer.cpp`.
- `NetworkOutputSerializer` — read mode (bytes → object).
  `Serialization/NetworkOutputSerializer.cpp`.

Naming is *not* a typo: input reads *from* the object, output writes *to*
the object (`ISerializer.h:19–23`, `NetworkInputSerializer.cpp:26–29`).

### 2.1 Scalar encoding

| Type         | Wire bytes | Notes |
|--------------|-----------:|-------|
| `bool`       | 1          | value > 0 → true. `NetworkInputSerializer.cpp:31–35` |
| `int8/uint8` | 1          | |
| `int16/uint16` | 2        | **htons on send, ntohs on recv** |
| `int32/uint32` | 4        | htonl |
| `long / unsigned long` | platform | Same helper, uses `htonl/htonll` depending on size |
| `int64/uint64` | 8        | htonll |
| `float`        | 4        | reinterpret as `uint32_t`, htonl. `NetworkInputSerializer.cpp:87–92` |
| `double`       | 8        | reinterpret as `uint64_t`, htonll. `NetworkInputSerializer.cpp:94–99` |

### 2.2 Bounded (variable-width) integer encoding

**This is the trick that makes the protocol compact.** Every
`Serialize(int32_t&, name, minValue, maxValue)` overload calls
`SerializeBoundedValue`, which picks the *smallest unsigned integer type*
that can hold `maxValue - minValue` and serializes only that many bytes
(`NetworkInputSerializer.cpp:131–151`):

```
uint64_t valueRange = maxValue - minValue;
if      (valueRange <= 0xFF)         → serialize 1 byte
else if (valueRange <= 0xFFFF)       → serialize 2 bytes
else if (valueRange <= 0xFFFFFFFF)   → serialize 4 bytes
else                                 → serialize 8 bytes
```

The wire value is `(input - minValue)` in the chosen width (network byte
order). On receive, the output serializer reads the same width and adds
`minValue` back (`NetworkOutputSerializer.cpp:137–158`).

When `Serialize(x, name)` is called **without** a min/max, the defaults
from `ISerializer.h:94` etc. are the full type range → bounded encoding
collapses to the full width. So unless the field was written with bounds,
it takes the full 1/2/4/8 bytes.

**Implication for Ghidra / packet decoding:** if you see functions with 3
integer arguments (`value, minValue, maxValue`) being inlined around
`htons`/`htonl`, you're looking at `SerializeBoundedValue` specializations.
Packet fields that were declared with explicit `Init="..."` or via
AutoComponent `Min`/`Max` attributes use narrower widths than a naive
`sizeof(field)` would suggest.

### 2.3 Strings

`AZStd::string` serializes as `uint32 size` + `size` raw bytes (no null
terminator) (`AzContainerSerializers.h:219–233`).

`AZStd::fixed_string<N>` uses the smallest unsigned int sufficient to hold
`N` for the size prefix
(`AzContainerSerializers.h:236–251`, via `AZ::RequiredBytesForValue<N>()`).

`LongNetworkString` = `AZ::CVarFixedString` (`MultiplayerTypes.h:71`). Its
capacity is defined by AzCore; it behaves as `fixed_string` with a CVar-sized
bound.

`AZ::Name` serializes only its 64-bit hash
(`AzContainerSerializers.h:461–474`) — the receiver looks up the string in
a local `NameDictionary`. **This means `AZ::Name` literals are only
recoverable if we have the dictionary or brute-force the hash.**

### 2.4 Containers (generic)

Iterable containers (vector, list, map, set, multimap, etc.) follow the
pattern `size(uint32) + element[0] + element[1] + ...`
(`AzContainerSerializers.h:36–69`). `AZStd::fixed_vector<T, N>` also writes
a size first (same `Size` label); capacity `N` comes from the template.

Fixed `AZStd::array<T, N>` writes only elements, no size
(`AzContainerSerializers.h:73–89`).

`AZStd::pair<K,V>` writes `key` then `value`
(`AzContainerSerializers.h:208–216`).

### 2.5 Math types

Packed as raw floats in field order (no size prefix):

| Type          | Fields serialized                             | Source |
|---------------|-----------------------------------------------|--------|
| `Vector2`     | x, y                                          | `AzContainerSerializers.h:264–276` |
| `Vector3`     | x, y, z                                       | `:278–291` |
| `Vector4`/`Quaternion` | x, y, z, w                           | `:293–307`, `:411–425` |
| `Matrix3x3`   | 9 floats, row-major                           | `:323–342` |
| `Matrix3x4`   | 12 floats, row-major                          | `:344–366` |
| `Matrix4x4`   | 16 floats, row-major                          | `:368–394` |
| `Transform`   | Vector3 translation + Quaternion rotation + float uniformScale | `:427–443` |
| `Aabb`        | Vector3 min + Vector3 max                     | `:445–458` |

Each float is htonl'd independently. **Transform is NOT a full Matrix4x4
on the wire** — it's T+R+S decomposed.

### 2.6 Enums & type-safe integrals

Enums serialize as their `underlying_type`
(`ISerializer.inl:134–158`). `AZ_TYPE_SAFE_INTEGRAL` types unwrap to their
raw integer and serialize with bounded encoding
(`ISerializer.inl:161–178`).

### 2.7 Objects & RTTI

Generic objects serialize via `value.Serialize(serializer)` wrapped by
`BeginObject(name)` / `EndObject(name)`
(`ISerializer.inl:117–132`). For `NetworkInputSerializer` /
`NetworkOutputSerializer`, `BeginObject`/`EndObject` are **no-ops that
always return true** (`NetworkInputSerializer.cpp:106–114`,
`NetworkOutputSerializer.cpp:112–120`). So there is **no framing between
fields on the wire** — just the concatenated field bytes in declared order.

`TypeValidatingSerializer` (optional, guarded by `net_validateSerializedTypes`
cvar, default off — `NetworkingSystemComponent.cpp:20`) prepends a type
hash per field for mismatch detection. **Default build: off, so no per-field
type headers on the wire.**

### 2.8 ByteBuffer / PacketEncodingBuffer

`ByteBuffer<SIZE>` (`DataStructures/ByteBuffer.h:18`) is a
fixed-capacity byte array that serializes as:

```
<size>      smallest unsigned int sufficient to hold SIZE   (e.g. SIZE=16384 → uint16)
<bytes>     size raw bytes
```

(`ByteBuffer.inl:90–104`.) Buffer capacity constants
(`ByteBuffer.h:88–102`):

- `MaxPacketSize = 16384`
- `MaxUdpTransmissionUnit = 1024` (stock default — may be overridden via
  `SetConnectionMtu`; see `UdpConnection.h:148`)
- `TcpPacketEncodingBuffer`, `UdpPacketEncodingBuffer`,
  `PacketEncodingBuffer` are all `ByteBuffer<16384>`.
- `ChunkBuffer = ByteBuffer<1024>` for fragment payloads.

So `UdpPacketEncodingBuffer` on the wire: 16-bit size (0..16384) + data.
`ChunkBuffer`: 16-bit size (0..1024) + data. Confirm in Ghidra that size
widths match what we see in captures.

---

## 3. IPacket interface & vtable

### 3.1 Base class

`IPacket` (`PacketLayer/IPacket.h:32`) has 3 pure virtual methods, in
declared order (which is the **vtable order**):

| Slot | Signature                                               |
|-----:|---------------------------------------------------------|
| 0    | virtual destructor                                      |
| 1    | `PacketType GetPacketType() const`                      |
| 2    | `AZStd::unique_ptr<IPacket> Clone() const`              |
| 3    | `bool Serialize(ISerializer& serializer)`               |

Source: `IPacket.h:38–51`. **When hunting IPacket subclasses in Ghidra, look
for a 4-slot vtable where slot 1 returns a 16-bit constant, slot 2 allocates
and returns a heap pointer, slot 3 walks the serializer.**

### 3.2 How packets identify themselves

Every auto-generated packet carries a `static constexpr PacketType Type`
derived from a per-group `AZ_ENUM_CLASS_WITH_UNDERLYING_TYPE(PacketType, int32_t, ...)`
(`AutoPackets_Header.jinja:21, 92–98`). `GetPacketType()` just returns
this constant (`AutoPackets_Source.jinja:30–33`). So the implementation is
a trivial inlined `return CONST`.

`PacketType` on the wire is `uint16_t` (see §1.1), but the enum underlying
type in C++ is `int32_t` — the cast happens at dispatch time
(`UdpNetworkInterface.cpp:296`, `AutoPacketDispatcher_Inline.jinja:7`).

### 3.3 Dispatcher

Generated from `AutoPacketDispatcher_Inline.jinja`. For each packet:

```cpp
case aznumeric_cast<int32_t>(PacketName::Type):
{
    PacketName packet;
    if (!serializer.Serialize(packet, "Packet")) return Failure;
    if (handler.HandleRequest(connection, packetHeader, packet))
        return Success;
    break;
}
```

Handshake gating: if **any** packet in the group is marked
`HandshakePacket="true"`, non-handshake packets are skipped with
`PacketDispatchResult::Skipped` until `handler.IsHandshakeComplete(connection)`
returns true (jinja lines 11–27).

### 3.4 Auto-generated packet class shape

Per `AutoPackets_Header.jinja:14–72`, every generated packet has:

- `static constexpr PacketType Type`
- Default ctor + explicit ctor taking each member
- `bool operator==` / `!=` (member-wise)
- Per-member `Set<Name>`, `Get<Name>` (const ref), `Modify<Name>`
  (non-const ref)
- Overrides of `GetPacketType() / Clone() / Serialize()`
- Private `m_<memberName>` fields with `Init=` defaults if specified

`Clone()` default-constructs an instance and assigns each member — so
`Clone()` in Ghidra appears as: `operator new` + memberwise copy + return
(`AutoPackets_Source.jinja:46–53`).

---

## 4. Core packet type catalog

Two packet groups exist in the stock codebase that matter for game
traffic: `CorePackets` (AzNetworking framework) and `MultiplayerPackets`
(Multiplayer gem). A third group, `MultiplayerEditorPackets`, is editor-only.

### 4.1 CorePackets (PacketType 0–4)

From `Code/Framework/AzNetworking/AzNetworking/AutoGen/CorePackets.AutoPackets.xml`.
`PacketStart="0"`, so the enum values are:

| Type id | Name                       | Fields (wire order)                                      |
|--------:|----------------------------|----------------------------------------------------------|
| 0       | `InitiateConnectionPacket` | `UdpPacketEncodingBuffer handshakeBuffer` (uint16 size + bytes, carries DTLS ClientHello-equivalent) |
| 1       | `ConnectionHandshakePacket`| `UdpPacketEncodingBuffer handshakeBuffer` (DTLS continuation data) |
| 2       | `TerminateConnectionPacket`| `DisconnectReason disconnectReason` (enum, stored as underlying int) |
| 3       | `HeartbeatPacket`          | `bool requestResponse` (1 byte) |
| 4       | `FragmentedPacket`         | `SequenceId unfragmentedSequence` (2B), `SequenceId fragmentSequence` (2B), `uint8_t chunkIndex`, `uint8_t chunkCount`, `ChunkBuffer chunkBuffer` (uint16 size + up to 1024 bytes) |
| 5       | `PacketType::MAX`          | Sentinel (not a packet) |

`DisconnectReason` enum values (`ConnectionEnums.h:37–64`):
`None, Unknown, StreamError, NetworkError, Timeout, ConnectTimeout,
ConnectionRetry, HeartbeatTimeout, TransportError, TerminatedByClient,
TerminatedByServer, TerminatedByUser, TerminatedByMultipleLogin,
RemoteHostClosedConnection, ReliableTransportFailure, ReliableQueueFull,
ConnectionRejected, ConnectionDeleted, ServerNoLevelLoaded, ServerError,
ClientMigrated, SslFailure, VersionMismatch, NonceRejected, DtlsHandshakeError`.
Serialized as its underlying int per `ISerializer.inl:134–158`. Default
underlying is `int` (4 bytes) unless the `AZ_ENUM_CLASS` macro specifies
otherwise. Bounded encoding applies if min/max are passed, but in the
packet Serialize() they aren't (see `AutoPackets_Source.jinja:55–61`).

Typical sizes (unreliable header 12B + payload):
- Heartbeat: 12 + 1 = **13 bytes** pre-DTLS
- InitiateConnection: 12 + 2 (size) + N (DTLS bytes, typically 100–200+ during handshake)

### 4.2 MultiplayerPackets (Multiplayer gem, PacketType starts at `CorePackets::PacketType::MAX` = 5)

From `Gems/Multiplayer/Code/Source/AutoGen/Multiplayer.AutoPackets.xml`.

| Type id | Name                 | Handshake? | Fields (wire order)                                   |
|--------:|----------------------|------------|-------------------------------------------------------|
| 5       | `Connect`            | yes        | `uint16 networkProtocolVersion`, `uint64 temporaryUserId`, `LongNetworkString ticket`, `HashValue64 systemVersionHash` |
| 6       | `Accept`             | yes        | `LongNetworkString map` |
| 7       | `VersionMismatch`    | yes        | `ComponentVersionMap componentVersions` (`unordered_map<AZ::Name, HashValue64>` → size + [nameHash + u64] pairs) |
| 8       | `ReadyForEntityUpdates` | no      | `bool readyForEntityUpdates` (1 byte) |
| 9       | `SyncConsole`        | no         | `fixed_vector<LongNetworkString, 32> commandSet` |
| 10      | `ConsoleCommand`     | no         | `LongNetworkString command` |
| 11      | `EntityUpdates`      | no         | `AZ::TimeMs hostTimeMs` (int64), `HostFrameId hostFrameId` (uint32), `NetworkEntityUpdateVector entityMessages` (fixed_vector cap 2048) |
| 12      | `EntityRpcs`         | no         | `NetworkEntityRpcVector entityRpcs` (fixed_vector cap 1024) |
| 13      | `RequestReplicatorReset` | no     | `NetEntityIdsForReset entityIds` (fixed_vector<NetEntityId, 2048>; `NetEntityId` = uint64 per public header, uint32 per internal source — see note below) |
| 14      | `ClientMigration`    | no         | `IpAddress remoteServerAddress` (2 × htonl: ipv4 + port), `uint64 temporaryUserIdentifier`, `ClientInputId lastClientInputId` (uint16) |

**Note on NetEntityId discrepancy:** Public header
`Gems/Multiplayer/Code/Include/Multiplayer/MultiplayerTypes.h:50` declares
`NetEntityId` as **uint64_t**. Internal copy at
`Gems/Multiplayer/Code/Source/MultiplayerTypes.h:26` declares it as
**uint32_t**. The public header is the one included by AutoPackets.xml via
`<Include File="Multiplayer/MultiplayerTypes.h" />` — which resolves to the
`Include/` copy based on normal CMake include order. **TBD (needs Ghidra)**
— confirm which size New World uses by looking at NetworkEntityUpdateMessage
vtable size and alignment.

Capacity constants (`MultiplayerTypes.h:38–44`):
- `MaxAggregateEntityMessages = 2048`
- `MaxAggregateRpcMessages = 1024`
- `MaxAggregateEntityResets = 2048`

### 4.3 NetworkEntityUpdateMessage wire format

Defined in `Gems/Multiplayer/Code/Source/NetworkEntity/NetworkEntityUpdateMessage.cpp:174–213`.
Field order:

1. `NetEntityId m_entityId` — uint64 (public) or uint32 (internal header).
2. `uint8 networkTypeAndFlags` — **packed byte**:
   - bit 6 (0x40): `m_isDelete`
   - bit 5 (0x20): `m_wasMigrated`
   - bit 4 (0x10): `m_hasValidPrefabId`
   - bits 0–3 (0x0F): `m_networkRole` as `NetEntityRole` (values
     0=InvalidRole, 1=Client, 2=Autonomous, 3=Server, 4=Authority;
     `MultiplayerTypes.h:87–94`)
3. `PrefabEntityId m_prefabEntityId` — **only if `hasValidPrefabId`
   bit was set**. `PrefabEntityId` = `AZ::Name m_prefabName` (u64 hash) +
   `uint32 m_entityOffset`. (`MultiplayerTypes.h:122–137`, `:196–201`.)
4. `PacketEncodingBuffer m_data` — uint16 size + raw serialized property
   bytes (up to 16384).

AZ_TYPE_INFO: `{CFCA08F7-547B-4B89-9794-37A8679608DF}`.

### 4.4 NetworkEntityRpcMessage wire format

`NetworkEntityRpcMessage.cpp:160–176`:

1. `RpcDeliveryType m_rpcDeliveryType` — uint8 (enum class with explicit
   `uint8_t` storage; `MultiplayerTypes.h:78–85`). Values:
   0=None, 1=AuthorityToClient, 2=AuthorityToAutonomous,
   3=AutonomousToAuthority, 4=ServerToAuthority.
2. `NetEntityId m_entityId` — u64/u32 (see discrepancy above).
3. `NetComponentId m_componentId` — uint16 (`MultiplayerTypes.h:59`).
4. `RpcIndex m_rpcIndex` — uint16 (`:63`).
5. `PacketEncodingBuffer m_data` — uint16 size + serialized RPC params.

`m_isReliable` is **NOT serialized** (comment at line 174).
AZ_TYPE_INFO: `{3AA5E1A5-6383-46C1-9817-F1B8C2325178}`.

### 4.5 MultiplayerEditorPackets (not relevant to retail client)

Editor-only; retail client will not have these. Listed for completeness
(`MultiplayerEditor.AutoPackets.xml`):

- `EditorServerReadyForLevelData` (no fields)
- `EditorServerLevelData` (`bool lastUpdate`, `ByteBuffer<16379> assetData`)
- `EditorServerReady` (no fields)

---

## 5. DTLS → AzNetworking handoff

The critical path is `UdpNetworkInterface::Update()`
(`UdpTransport/UdpNetworkInterface.cpp:174–359`). Per-packet flow:

```
UdpReaderThread.GetReceivedPackets()                      // raw sockets → queue
  ↓
UdpNetworkInterface::Update()                             // main thread, per-tick
  ↓
  lookup connection by (sourceIP, sourcePort)             // :204
  if (no connection) → AcceptConnection(packet)           // :207, :641
  ↓
  connection->GetDtlsEndpoint().DecodePacket(...)         // :227
    → BIO_write(readBio, encrypted, size)                 // DtlsEndpoint.cpp:119
    → SSL_read(sslSocket, outBuffer, size)                // DtlsEndpoint.cpp:126
    → returns decrypted payload pointer + size
  ↓
  UdpPacketHeader header;
  header.SerializePacketFlags(flagSerializer)             // :247 — reads 1 byte
  ↓
  if (header.IsPacketFlagSet(Compressed))                 // :257
    DecompressPacket(...)                                 // LZ4 etc.
  ↓
  serializer.Serialize(header, "Header")                  // :281 — rest of header
  ↓
  connection->ProcessReceived(header, ...)                // ack tracking, reliable dedup
  ↓
  if (packetType < CorePackets::MAX)
    connection->HandleCorePacket(...)                     // :298 (UdpConnection.cpp:243)
  else
    listener->OnPacketReceived(connection, header, ...)   // :302 — gem dispatch
```

### 5.1 Ownership

- One `UdpSocket` / `DtlsSocket` per `UdpNetworkInterface`
  (`UdpNetworkInterface.h:185`).
- **Each `UdpConnection` owns its own `DtlsEndpoint`** as a member
  (`UdpConnection.h:144`). Multiple connections multiplex onto a single
  DtlsSocket, but SSL state is per-connection.
- `DtlsEndpoint` stores `SSL*`, `BIO* readBio`, `BIO* writeBio`
  (`DtlsEndpoint.h:99–103`). The `writeBio` is drained in
  `PerformHandshakeInternal` at `DtlsEndpoint.cpp:197–203` and the bytes
  are sent out as `ConnectionHandshakePacket`s (`DtlsEndpoint.cpp:98–101`).

### 5.2 Handshake packets over DTLS

During DTLS handshake, raw OpenSSL handshake bytes are **wrapped in
`ConnectionHandshakePacket`s and sent unreliably** — `DtlsEndpoint::ProcessHandshakeData`
(`DtlsEndpoint.cpp:79–106`). This means: the initial `InitiateConnectionPacket`
is sent reliably and carries the first DTLS ClientHello blob inside
its `handshakeBuffer`; subsequent DTLS records ride inside
`ConnectionHandshakePacket`s until `SSL_is_init_finished()` returns true.

After handshake completion (`HandshakeState::Complete`), every
datagram is fully encrypted by OpenSSL — `DecodePacket` calls `SSL_read`
and the rest of the pipeline only sees plaintext
(`DtlsEndpoint.cpp:108–130`).

### 5.3 Constants to know

- DTLS1 record header: **13 bytes** — `DtlsPacketHeaderSize` at
  `UdpNetworkInterface.h:28`.
- IPv4 + UDP overhead: **28 bytes** — `UdpPacketHeaderSize` at
  `UdpNetworkInterface.h:27`.
- Cipher suite (default): `"ECDHE-RSA-AES256-GCM-SHA384"`
  (`EncryptionCommon.cpp:43`).
- Default DTLS cookies: **off** (`net_UseDtlsCookies = false`,
  `DtlsEndpoint.cpp:24`). New World likely turned this on — observed
  HelloVerifyRequest in captures would confirm.
- Self-signed allowed: **on** by default (`net_SslAllowSelfSigned = true`,
  `EncryptionCommon.cpp:49`). Matches what we see from New World's cert
  (`CN=New World`, self-signed).
- Cert pinning: **on** by default (`net_SslEnablePinning = true`,
  `EncryptionCommon.cpp:47`). If New World ships with this on, the client
  has a baked-in expected cert — we'd need to either use the same cert
  or patch the client.

---

## 6. Connection state machine

States (`ConnectionEnums.h:30–35`): `Disconnected, Disconnecting,
Connected, Connecting`.

### 6.1 Client-initiated flow (Connector)

`UdpNetworkInterface::Connect` (`UdpNetworkInterface.cpp:130–172`):

```
Disconnected
  → (Connect() called)
  → construct UdpConnection with role=Connector
  → m_socket->ConnectDtlsEndpoint(...) — creates SSL, starts client handshake
  → m_state = Connecting                                       [line 160]
  → SendReliablePacket(InitiateConnectionPacket{handshakeBuffer})   [:167]
  → OnConnect(connection) listener hook
  ← (wait for response)

Connecting
  → receive packet, DecodePacket pumps DTLS handshake bytes back via ConnectionHandshakePacket
  → on each received packet: if GetConnectionState()==Connecting
    AND !DtlsEndpoint.IsConnecting() → m_state = Connected     [:310–312]

Connected
  → dispatch packets to IConnectionListener::OnPacketReceived
  → HeartbeatPacket exchanged when unacked > net_UdpMaxUnackedPacketCount (default 10)
```

### 6.2 Server-initiated flow (Acceptor)

`UdpNetworkInterface::AcceptConnection` (`UdpNetworkInterface.cpp:641–706`):

```
Disconnected (implicit — no connection exists yet)
  → inbound datagram from unknown source
  → parse as InitiateConnectionPacket, validate header
  → m_connectionListener.ValidateConnect(...) → Accepted/Rejected    [:681]
  → if Accepted:
    - construct UdpConnection with role=Acceptor
    - m_socket->AcceptDtlsEndpoint(endpoint, address)
    - m_state = Connected (if DTLS finished immediately) OR Connecting  [:702]
    - OnConnect(connection) listener hook
```

### 6.3 Disconnect path

`UdpConnection::Disconnect` (`UdpConnection.cpp:117–145`):

```
Connected (or Connecting)
  → m_state = Disconnecting                                    [:128]
  → if TerminationEndpoint::Local AND reason is "graceful":
    SendUnreliablePacket(TerminateConnectionPacket{reason})    [:139–140]
  → m_networkInterface.RequestDisconnect(...) → queued for removal  [:143]
  → (next Update tick) OnDisconnect listener, connection deleted
  → m_state = Disconnected (via destructor or explicit)
```

"Graceful" reasons (those that send a Terminate packet): everything
**except** `NetworkError`, `DtlsHandshakeError`, `Unknown`,
`RemoteHostClosedConnection`, `TransportError`, `SslFailure`
(`UdpConnection.cpp:130–136`).

### 6.4 Remote-triggered disconnect

`UdpConnection::HandleCorePacket` → `TerminateConnectionPacket` case
(`UdpConnection.cpp:275–286`): parses reason, calls
`Disconnect(reason, TerminationEndpoint::Remote)`. Since endpoint is
Remote, no reply is sent.

### 6.5 Timeout path

Per-connection timeout at `net_UdpDefaultTimeoutMs = 10_000` default
(`UdpNetworkInterface.cpp:35`). If no packet arrives and heartbeats
expire, `HandleConnectionTimeout` disconnects with reason `Timeout`.

### 6.6 Handshake completion via ConnectionHandshakePacket

`UdpConnection::HandleCorePacket` → `ConnectionHandshakePacket` case
(`UdpConnection.cpp:254–273`): feeds bytes into `ProcessHandshakeData`;
if `Complete` returned, transitions `Connecting → Connected`.

### 6.7 Gem-layer states beyond the UdpConnection

The Multiplayer gem layers *game-level* handshake on top — the
`HandshakePacket="true"` flag on `Connect`/`Accept`/`VersionMismatch`
means the dispatcher gates all other game packets on
`handler.IsHandshakeComplete(connection)` returning true. So the actual
state machine the client experiences is:

```
UdpConnection=Connecting (DTLS pending)
  ↓
UdpConnection=Connected + Multiplayer handshake pending
  ↓ (Connect sent, Accept received)
UdpConnection=Connected + Multiplayer handshake complete
  ↓
Full game traffic (EntityUpdates / EntityRpcs / etc.)
```

New World's log phases (from `docs/connection-flow.md`):
`StartREPConnection → WaitingForREPConnection → WaitingForActorGameConnection →
WaitingForSpawnPoint → WaitingForPlayerSpawn → InGame` very likely map
onto this two-tier handshake, with the "actor game connection" phase
corresponding to the Multiplayer gem's `Connect/Accept` exchange (or a
New-World-specific subclass of it). **TBD (needs Ghidra)** — confirm
packet types 5 and 6 carry the auth ticket / map name seen in the log.

---

## 7. Identifiable strings

Strings to grep for in `NewWorld.exe` `.rdata`. All of these appear as
string literals in the O3DE source and, assuming debug logging wasn't
stripped, should appear in the binary.

### 7.1 AZ_RTTI / AZ_TYPE_INFO UUIDs (16-byte GUIDs in data section)

| Class                       | UUID |
|-----------------------------|------|
| `IPacket`                   | `1B33BFE8-8A4B-44E3-8C8D-3B924093227C` |
| `IPacketHeader`             | `90A0EFE3-01A4-4F04-87CF-E98E94D49648` |
| `UdpPacketHeader`           | `21A11FF3-6829-4A59-9906-C06EF7F39AC1` |
| `TcpPacketHeader`           | `6D92B9BE-C5E4-4571-B0FA-8F29042BE93B` |
| `INetworkInterface`         | `ECDA6FA2-4AA0-435E-881F-214C4B179A31` |
| `INetworking`               | `6E47367B-3AA5-4CB8-A691-4910168F287A` |
| `AzNetworkingModule`        | `4118D37D-233D-4CD5-ACE7-747FBAF2615D` |
| `IMultiplayer`              | `90A001DD-AD31-46C7-9FBE-1059AFB7F5E9` |
| `IMultiplayerSpawner`       | `E5525317-A476-4209-BE45-477FB9D96083` |
| `INetworkEntityManager`     | `109759DE-9492-439C-A0B1-AE46E6FD029C` |
| `INetworkTime`              | `7D468063-255B-4FEE-86E1-6D750EEDD42A` |
| `MultiplayerComponent`      | `B7F5B743-CCD3-4981-8F1A-FC2B95CE22D7` |
| `MultiplayerModule`         | `497FF057-6CE1-43D5-9A9F-D2B7ABF6D3A7` |
| `NetworkEntityUpdateMessage`| `CFCA08F7-547B-4B89-9794-37A8679608DF` |
| `NetworkEntityRpcMessage`   | `3AA5E1A5-6383-46C1-9817-F1B8C2325178` |
| `PrefabEntityId`            | `EFD37465-CCAC-4E87-A825-41B4010A2C75` |
| `NetworkSpawnable`          | `780FC028-25D7-4F70-A93F-D697820B76F8` |
| `NetEntityId`               | `05E4C08B-3A1B-4390-8144-3767D8E56A81` |
| `NetComponentId`            | `8AF3B382-F187-4323-9014-B380638767E3` |
| `PropertyIndex`             | `F4460210-024D-4B3B-A10A-04B669C34230` |
| `RpcIndex`                  | `EBB1C475-FA03-4111-8C84-985377434B9B` |
| `ClientInputId`             | `35BF3504-CEC9-4406-A275-C633A17FBEFB` |
| `HostFrameId`               | `DF17F6F3-48C6-4B4A-BBD9-37DA03162864` |

Ghidra byte search: GUIDs are stored as raw 16-byte structures (first
three groups little-endian per Windows GUID convention, last two groups
as bytes). For example, `{21A11FF3-6829-4A59-9906-C06EF7F39AC1}` on
Windows lays out as `F3 1F A1 21 29 68 59 4A 99 06 C0 6E F7 F3 9A C1`.

### 7.2 Network CVar names (always in rdata when AZ_CVAR is used)

These are the knobs the engine exposes; finding them confirms AzNetworking
is present:

- `net_UdpUseEncryption`, `net_UdpUseDtlsCookies` (`UseDtlsCookies`),
  `net_UdpTimeoutConnections`, `net_UdpPacketTimeSliceMs`,
  `net_UdpUnackedHeartbeats`, `net_UdpDefaultTimeoutMs`,
  `net_UdpMaxUnackedPacketCount`, `net_UdpSendBufferSize`,
  `net_UdpRecvBufferSize`, `net_UdpIgnoreWin10054`
- `net_MinPacketTimeoutMs`, `net_MaxTimeoutsPerFrame`,
  `net_RttFudgeScalar`, `net_FragmentedHeaderOverhead`,
  `net_FragmentsAlwaysReliable`, `net_UdpCompressor`,
  `net_SslInflationOverhead`, `net_UdpFragmentTimeoutMs`,
  `net_MaxReliablePacketsInWindow`, `net_UdpMaxReadTimeMs`
- `net_SslExternalCertificateFile`, `net_SslExternalPrivateKeyFile`,
  `net_SslExternalContextPassword`, `net_SslInternalCertificateFile`,
  `net_SslInternalPrivateKeyFile`, `net_SslInternalContextPassword`,
  `net_SslCertCiphers`, `net_SslMaxCertDepth`, `net_RotateCookieTimer`,
  `net_SslEnablePinning`, `net_SslValidateExpiry`, `net_SslAllowSelfSigned`
- `net_validateSerializedTypes`, `net_TcpUseEncryption`, `net_TcpCompressor`
- `net_rttIncreaseOnPacketLoss`, `net_maxPacketTrackTimeMs`
- Default cipher string: `ECDHE-RSA-AES256-GCM-SHA384`
- Default compressor name: `MultiplayerCompressor`

### 7.3 Log categories (AZLOG channel names)

These appear as the first argument to `AZLOG(...)` macros — they become
bare identifiers used in filters and sometimes end up as strings in
debug builds:

`NET_Debug`, `NET_Rtt`, `NET_Acks`, `NET_DebugDtls`, `NET_DebugPacketSend`,
`NET_CorePackets`, `Debug_DispatchPackets`, `Debug_UdpConnect`,
`TcpConnectionSet`.

### 7.4 Distinctive error/warning messages (AzNetworking)

- `"SSL handshake negotiation failed (%d), terminating connection"` —
  `DtlsEndpoint.cpp:178`
- `"dtls handshake is completed, unblocking connection for game traffic, prior state: %s"` —
  `DtlsEndpoint.cpp:191`
- `"An existing SSL socket was open during a call to connect, closing old socket"` —
  `DtlsEndpoint.cpp:136`
- `"Unacked packet count exceeded, sending client heartbeat (curr %u : max %u)"` —
  `UdpConnection.cpp:81`
- `"Disconnecting an already disconnecting connection due to %s"` —
  `UdpConnection.cpp:125`
- `"Processing time exceeded, discarding %d/%d received packets"` —
  `UdpNetworkInterface.cpp:199`
- `"Registering packetId %u with timeout %u"` — `UdpNetworkInterface.cpp:440`
- `"Accepted new Udp Connection"` — `UdpNetworkInterface.cpp:697`
- `"CIDR input string (%s) malformed, input should be formatted as aaa.bbb.ccc.ddd/mask"` —
  `CidrAddress.cpp:57`
- All the `SSL_ERROR_*` / `%X - ...` strings at `EncryptionCommon.cpp:66–100`
  (verbatim: `"%X - SSL_ERROR_NONE: ..."`, `"%X - SSL_ERROR_ZERO_RETURN: ..."`,
  `"%X - SSL_ERROR_WANT_READ: ..."`, `"%X - SSL_ERROR_WANT_WRITE: ..."`,
  `"%X - SSL_ERROR_WANT_CONNECT: ..."`, `"%X - SSL_ERROR_WANT_ACCEPT: ..."`,
  `"%X - SSL_ERROR_WANT_X509_LOOKUP: ..."`, `"%X - SSL_ERROR_SYSCALL: ..."`,
  `"%X - SSL_ERROR_SSL: lib %s, func %s, reason %s"`)
- `"OpenSSL preverification failed with (%d: %s)"` — `EncryptionCommon.cpp:257`
- `"net_SslAllowSelfSigned is *enabled*, clearing X509 certificate validation failure"` —
  `EncryptionCommon.cpp:265`
- `"Failed to decompress packet!"` — `UdpNetworkInterface.cpp:262`
- `"Decompress must consume entire buffer [%zu != %zu]!"` —
  `UdpNetworkInterface.cpp:467`

### 7.5 Multiplayer gem log messages

- `"New outgoing connection to remote address: %s"` —
  `MultiplayerSystemComponent.cpp:1187`
- `"New incoming connection from remote address: %s"` — `:1202`
- `"Multiplayer operating in %s mode"` — `:1417` (followed by
  agent-type enum string)
- `"Server did not provide a valid level to load! Make sure the server has a level loaded before connecting."` — `:1247`
- `"No IMultiplayerSpawner was available. Ensure that one is registered for usage on PlayerJoin."` — `:833`
- `"Migrating to new server shard"` — `:1066`
- `"Failed to connect to new host during client migration event"` — `:1070`
- `"Multiplayer component mismatch was found. Server configured to allow the player to connect anyways."` — `:1155`
- `"Missing connection data, likely due to a connection in the process of closing, entity updates size %u"` —
  `:987` / `:1021`
- `"Total networked entities: %llu"`, `"Total client connections: %llu"`,
  `"Total server connections: %llu"`, `"Total property updates sent: %llu"` —
  `:1561–1570`

### 7.6 Class names (useful for symbol demangling in Ghidra)

`UdpPacketHeader`, `UdpConnection`, `UdpConnectionSet`, `UdpNetworkInterface`,
`UdpSocket`, `DtlsSocket`, `DtlsEndpoint`, `UdpPacketTracker`,
`UdpReaderThread`, `UdpHeartbeatThread`, `UdpReliableQueue`,
`UdpFragmentQueue`, `UdpPacketIdWindow`, `ConnectionMetrics`,
`NetworkInputSerializer`, `NetworkOutputSerializer`, `TrackChangedSerializer`,
`TypeValidatingSerializer`, `HashSerializer`, `StringifySerializer`,
`DeltaSerializer`, `ByteBuffer`, `IpAddress`, `CidrAddress`,
`NetworkingSystemComponent`, `AzNetworkingModule`,
`MultiplayerSystemComponent`, `MultiplayerGem`, `MultiplayerModule`,
`NetworkEntityManager`, `NetworkEntityAuthorityTracker`,
`NetworkEntityTracker`, `NetworkEntityHandle`, `NetworkEntityUpdateMessage`,
`NetworkEntityRpcMessage`, `ClientToServerConnectionData`,
`ServerToClientConnectionData`, `NullReplicationWindow`,
`ServerToClientReplicationWindow`, `NetworkPrefabProcessor`,
`NetworkSpawnableLibrary`.

Packet class names (per auto-gen jinja, these become `namespace::ClassName`):
`CorePackets::InitiateConnectionPacket`,
`CorePackets::ConnectionHandshakePacket`,
`CorePackets::TerminateConnectionPacket`,
`CorePackets::HeartbeatPacket`, `CorePackets::FragmentedPacket`,
`MultiplayerPackets::Connect`, `MultiplayerPackets::Accept`,
`MultiplayerPackets::VersionMismatch`,
`MultiplayerPackets::ReadyForEntityUpdates`,
`MultiplayerPackets::SyncConsole`, `MultiplayerPackets::ConsoleCommand`,
`MultiplayerPackets::EntityUpdates`, `MultiplayerPackets::EntityRpcs`,
`MultiplayerPackets::RequestReplicatorReset`,
`MultiplayerPackets::ClientMigration`.

### 7.7 Field name strings (from Serialize calls)

Because each `serializer.Serialize(field, "Name")` passes a name string,
these literal names **will be in the binary** if not stripped:

- Header: `"PacketType"`, `"LocalSequence"`, `"RemoteSequence"`,
  `"SequenceWindow"`, `"IsReliable"`, `"ReliableSequence"`, `"PacketFlags"`,
  `"Header"`, `"Packet"`, `"Size"`, `"Buffer"`, `"String"`
- EntityUpdate: `"EntityId"`, `"TypeAndFlags"`, `"PrefabEntityId"`, `"Data"`
- EntityRpc: `"RpcDeliveryType"`, `"ComponentId"`, `"RpcIndex"`, `"data"`
- Math: `"xValue"`, `"yValue"`, `"zValue"`, `"wValue"`, `"Translation"`,
  `"Rotation"`, `"Scale"`, `"minValue"`, `"maxValue"`, `"NameHash"`
- CorePacket fields: `"handshakeBuffer"`, `"disconnectReason"`,
  `"requestResponse"`, `"unfragmentedSequence"`, `"fragmentSequence"`,
  `"chunkIndex"`, `"chunkCount"`, `"chunkBuffer"`
- MultiplayerPacket fields: `"networkProtocolVersion"`,
  `"temporaryUserId"`, `"ticket"`, `"systemVersionHash"`, `"map"`,
  `"componentVersions"`, `"readyForEntityUpdates"`, `"commandSet"`,
  `"command"`, `"hostTimeMs"`, `"hostFrameId"`, `"entityMessages"`,
  `"entityRpcs"`, `"entityIds"`, `"remoteServerAddress"`,
  `"temporaryUserIdentifier"`, `"lastClientInputId"`

---

## 8. Known New World extensions

Based on `docs/progress.md` and `docs/connection-flow.md`, New World
almost certainly diverges from stock O3DE in these places. Annotated
with what to expect when Ghidra finishes analyzing.

### 8.1 Likely intact (stock AzNetworking transport)

- **UdpPacketHeader layout** (§1). The game log shows heartbeats and reliable
  messaging behavior consistent with stock — it'd be a big undertaking to
  rewrite the header format. Our captures (38,845 packets) confirm DTLS
  1.2 + a post-decrypt framing layer; the framing should match §1.
- **CorePackets 0–4** (`InitiateConnectionPacket`, `ConnectionHandshakePacket`,
  `TerminateConnectionPacket`, `HeartbeatPacket`, `FragmentedPacket`). These
  are transport-level and are unlikely to be replaced. `HeartbeatPacket` in
  particular will be very frequent in the capture and is trivial to
  fingerprint (payload is 1 byte).
- **DTLS handoff path** (§5). The game's DTLS stack uses mutually-authenticated
  TLS (server sends Certificate Request), matching stock OpenSSL usage. Cipher
  suite `ECDHE-RSA-AES256-GCM-SHA384` is the default.
- **Serialization primitives** (§2). Big-endian, bounded integer encoding,
  and htonl-of-float pattern are fingerprintable even without symbols.

### 8.2 Likely subclassed or replaced (Multiplayer gem)

- **`MultiplayerPackets::Connect`** (§4.2). Stock fields: `uint16 protocolVersion,
  uint64 temporaryUserId, LongNetworkString ticket, HashValue64 systemVersionHash`.
  New World's log shows the client receives a login ticket
  (`eacab29f-f0eb-43b4-84ed-91c4861aefc0_a1683238-...`) and a character GUID —
  the `ticket` field probably carries the login ticket but the structure may
  also include the character GUID. **Look for a Connect-like handshake packet
  that references a UUID-sized string and the server version string
  `[RETAIL].Javelin.1.365.6031.6004151`.**
- **`MultiplayerPackets::Accept`** → corresponds to "received registration
  response from REP" in the log. Stock `Accept` just sends back a map name;
  New World's probably carries spawn point, world ID, and/or the actor
  configuration for the player's character.
- **`NetworkEntityUpdateMessage` → likely replaced by a New-World-specific
  "actor replication" message.** Game log mentions "actor game connection"
  and "spawn point" — these are O3DE-ish terms but the "actor" nomenclature
  differs from stock O3DE's "entity". Almost certainly a subclass or
  parallel class with richer fields. Look for a packet type that carries
  the capacity-2048 vector inside an EntityUpdates-like packet.
- **`NetworkEntityRpcMessage` → likely extended.** The RPC param buffer
  (`PacketEncodingBuffer m_data`, up to 16384 bytes) is probably used for
  combat / ability / inventory events. Vector capacity 1024 per packet is
  likely bumped.
- **`ClientMigration` / `RequestReplicatorReset` / `SyncConsole` /
  `ConsoleCommand`** — maybe stripped from retail, maybe kept. `SyncConsole`
  would be a security concern if present.
- **Auth ticket format.** The `ticket` field in `Connect` carries what the
  game's log calls the "REP login ticket". This ticket is issued by the
  HTTPS gateway after OmniSDK auth (see `docs/progress.md` §Gate 1). In
  our stub, we can issue any ticket and short-circuit validation — but
  the client will check `systemVersionHash` against its baked-in value
  (confirmed by `VersionMismatch` packet existing in stock).

### 8.3 Likely added (not in stock O3DE)

- **Actor/GDE system.** The log has `ActorContainerConnect`,
  `actor game connection`, `GDE actor IDs`. "GDE" is not an O3DE term; this is
  Amazon-specific layering on top of the entity replication. Expect:
  - A packet type beyond `PacketType::MAX` of the Multiplayer group
    (i.e. `packetType >= 15`) that handles actor-level game logic
    registration.
  - A second "handshake-like" exchange *inside* the Connected state,
    explaining the log sequence `WaitingForActorGameConnection →
    WaitingForSpawnPoint → WaitingForPlayerSpawn`.
- **Streaming world state / area-of-interest (AOI) replication.** Stock O3DE
  has `IReplicationWindow` / `ServerToClientReplicationWindow` but doesn't
  ship with dynamic area streaming. New World's world is seamless with
  chunk-based streaming; expect a custom `IReplicationWindow` subclass
  sending a distance-culled entity set.
- **Combat-specific RPC param structs.** Stock `IRpcParamStruct` is just
  an interface; NW will have its own derivatives covering ability casting,
  damage resolution, etc. **TBD (needs Ghidra)** — impossible to
  enumerate without binary analysis.
- **Voice chat / SIP integration.** Stock O3DE doesn't ship this; New
  World uses Vivox (`nwxp.vivox.com`) — it's out of AzNetworking's scope,
  separate SIP transport.

### 8.4 Hunt list for Ghidra

In priority order, once auto-analysis completes:

1. Find a vtable with exactly 4 slots whose second slot returns a small
   constant (`GetPacketType`) — that's an `IPacket` subclass. Enumerate
   all such vtables; the constant values should map to the PacketType
   enum. If we see values 0–4 we've found CorePackets. Values 5+ with
   gaps from stock enum will reveal NW's extensions.
2. Grep the binary for the cipher string `ECDHE-RSA-AES256-GCM-SHA384` or
   `DtlsEndpoint` / `UdpNetworkInterface` strings → you've found
   AzNetworking.
3. The function that calls `SSL_read` right after `BIO_write` is
   `DecodePacket` — its only caller is `UdpNetworkInterface::Update`'s
   receive loop (§5). That function is the **entry point for all decrypted
   game traffic** and is the single most important location to identify
   for stub server work.
4. Look for a function that does `serializer.Serialize(packetType); switch
   on packetType` — that's the gem's dispatcher. Cases after case 4 are
   NW's game packets. Each case will reference a unique packet class's
   `Serialize()` method.
5. Any function taking a pointer that starts with the
   `NetworkEntityUpdateMessage` field pattern (u64/u32 entityId, u8
   flags, optional PrefabEntityId, PacketEncodingBuffer) is an
   entity-update serializer. Its callers reveal the actor/replication
   subsystem.

---

## Appendix: Source file index

All paths relative to `C:\Users\<username>\Programs\o3de\`.

| Concern | File |
|---------|------|
| UdpPacketHeader | `Code/Framework/AzNetworking/AzNetworking/UdpTransport/UdpPacketHeader.{h,cpp,inl}` |
| IPacket / IPacketHeader | `Code/Framework/AzNetworking/AzNetworking/PacketLayer/IPacket.h`, `IPacketHeader.h` |
| Core packet XML | `Code/Framework/AzNetworking/AzNetworking/AutoGen/CorePackets.AutoPackets.xml` |
| Dispatcher templates | `Code/Framework/AzNetworking/AzNetworking/AutoGen/AutoPacketDispatcher_{Header,Inline}.jinja` |
| Packet class templates | `Code/Framework/AzNetworking/AzNetworking/AutoGen/AutoPackets_{Header,Source,Inline}.jinja` |
| NetworkInput/OutputSerializer | `Code/Framework/AzNetworking/AzNetworking/Serialization/Network{Input,Output}Serializer.{h,cpp}` |
| ISerializer + helpers | `Code/Framework/AzNetworking/AzNetworking/Serialization/ISerializer.{h,inl}` |
| AZ container serializers | `Code/Framework/AzNetworking/AzNetworking/Serialization/AzContainerSerializers.h` |
| ByteBuffer | `Code/Framework/AzNetworking/AzNetworking/DataStructures/ByteBuffer.{h,inl}` |
| UdpConnection + state | `Code/Framework/AzNetworking/AzNetworking/UdpTransport/UdpConnection.{h,cpp}` |
| UdpNetworkInterface (main recv loop) | `Code/Framework/AzNetworking/AzNetworking/UdpTransport/UdpNetworkInterface.{h,cpp}` |
| DTLS endpoint | `Code/Framework/AzNetworking/AzNetworking/UdpTransport/DtlsEndpoint.{h,cpp}` |
| DTLS socket / OpenSSL setup | `Code/Framework/AzNetworking/AzNetworking/UdpTransport/DtlsSocket.{h,cpp}`, `Utilities/EncryptionCommon.{h,cpp}` |
| Connection enums | `Code/Framework/AzNetworking/AzNetworking/ConnectionLayer/ConnectionEnums.h` |
| Multiplayer types | `Gems/Multiplayer/Code/Include/Multiplayer/MultiplayerTypes.h` (and mirror at `Code/Source/MultiplayerTypes.h` — note the `NetEntityId` width discrepancy) |
| Multiplayer packet XML | `Gems/Multiplayer/Code/Source/AutoGen/Multiplayer.AutoPackets.xml` |
| NetworkEntityUpdateMessage | `Gems/Multiplayer/Code/{Include/Multiplayer,Source}/NetworkEntity/NetworkEntityUpdateMessage.{h,cpp}` |
| NetworkEntityRpcMessage | `Gems/Multiplayer/Code/{Include/Multiplayer,Source}/NetworkEntity/NetworkEntityRpcMessage.{h,cpp}` |
| MultiplayerSystemComponent | `Gems/Multiplayer/Code/Source/MultiplayerSystemComponent.{h,cpp}` |
