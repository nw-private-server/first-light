# Ghidra Hunt List — Javelin / GridMate fingerprints in NewWorld.exe

> Consolidated targets discovered via static scan. Use these the moment
> Ghidra auto-analysis completes (and GhidraMCP is enabled). All VAs are
> for the retail build at `<archive-game-exe>`.
>
> PE image base: `0x0000000140000000`
> Last updated: 2026-04-17 (initial scan). Ghidra static-RE on the
> EAC-wrapped binary succeeded 2026-05-06 — for current findings see
> [`ghidra_findings.md`](ghidra_findings.md) and the wakes-90-onward
> entries in [`autonomous_worklog.md`](autonomous_worklog.md). Many of
> the targets below have since been classified by name (see the
> `name`/`uuid` columns in `info/typeregistry.json`) or wired up in
> `server/javelin/` codecs — 40 / 40 captured wire-types now have
> codec coverage as of wake 109.

---

## Tier 1 — String anchors (guaranteed hits)

These are confirmed present in the binary. Cross-referencing each string gives
the function(s) that use it; from there we demangle and map back to GridMate.

| String                                | Section | File offset  | VA                     | Target function                          |
|---------------------------------------|---------|--------------|------------------------|------------------------------------------|
| `ECDHE-RSA-AES256-GCM-SHA384`         | .rdata  | `0x07fbd470` | `0x147fbec70`          | `SecureSocketDriver::Initialize` equiv.  |
| `GridMate-Carrier Packet Send Thread` | .rdata  | `0x07fbcfe8` | `0x147fbe7e8`          | Carrier thread-creation site             |
| `GridMateAllocatorMP`                 | .rdata  | `0x07f67ff8` | `0x147f697f8`          | Allocator registration                   |
| `TransformReplicaChunk`               | .rdata  | `0x084ecd39` | `0x1484ee539`          | `ReplicaChunkDescriptor::Register` call  |
| `CS_DISCONNECTED`                     | .rdata  | `0x07fbd450` | `0x147fbec50` (approx) | Connection-state-name table              |
| `conn.dataSend`                       | .rdata  | `0x07fbd000` | `0x147fbe800` (approx) | Stats dump function                      |
| `connect request`                     | .rdata  | `0x07fd8315` | `0x147fd9b15`          | **false positive** — Vivox, ignore       |

Cluster around the cipher string (all in `.rdata` near `0x147fbec50`):
- `CS_DISCONNECTED` → `CS_SSL_ERROR` → `CONNECTING` → `CONNECT` — the
  SecureSocketDriver state enum's name table. Ghidra will type this as a
  `char* []` array. Array index → enum value.

Cluster around `GridMate-Carrier`:
- `conn.dataSend`, `conn.dataReceived`, `conn.dataResend`, `conn.dataAcked`,
  `conn.packetSend`, `conn.packetReceived`, `conn.packetLost`, `conn.packetAcked`
  — all stats field names, printed by one `LogStats()` function.

---

## Tier 2 — Bit-pattern fingerprints (no strings needed)

From `docs/gridmate-reference.md` §9.1. Search for these in Ghidra's decompiled view.

### 2A. `ReadMessageHeader` — *the* message parser

Unique signature: reads 1 byte, then `AND`s it with `0x42` and branches to
error if non-zero.

```
flags = *buf++;
if ((flags & 0x42) != 0) { /* corrupt stream */ return ...; }
size = read_u16_be(buf); buf += 2;
if (flags & 0x20) { channel = *buf++; }
if (flags & 0x04) { numChunks = read_u16_be(buf); buf += 2; }
if (!(flags & 0x08)) { sequenceNumber = read_u16_be(buf); buf += 2; }
if (!(flags & 0x10)) { reliableSeqNum = read_u16_be(buf); buf += 2; }
```

The **`0x42` immediate** is the key — no other function in the binary should
AND a flags byte with exactly `0x42` (bits 1 and 6, both reserved).

**Ghidra action:** Search > For Scalars > 0x42, filter to `.text`, check each
for the surrounding structure above.

### 2B. `ReadDataGramHeader` — tiny, just reads a u16

Reads 2 bytes big-endian (sequence number) and returns. Called from the UDP
receive path. Look for a function with body essentially:

```
u16 seq = (buf[0] << 8) | buf[1];
return seq;
```

### 2C. `ReplicaManager::_Unmarshal` — the dispatcher

Writes a `u32 timestamp` to a field, then switches on a **1-byte** `cmdhdr`:

- `case 1:` Greetings
- `case 2:` NewProxy  (reads `{bool, bool, u32, u32, u32, VLQ, bytes}`)
- `case 3:` DestroyProxy
- `case 4:` NewOwner
- `case 5:` Heartbeat
- `default:` interpret the byte as a ReplicaId

### 2D. Compression hint byte

At the very start of `OnReceivedIncomingDataGram`: reads `buf[0]`, checks
if it's `0x01`, and if so calls a decompressor on `buf+1` (or `buf+3` after
the sequence number). If `0x00`, proceeds directly to message parsing.
Distinct pattern of `cmp byte, 1` early in a function that takes a datagram.

---

## Tier 3 — Component/chunk catalog (discovered)

### Confirmed ReplicaChunk types (strings found)

- `TransformReplicaChunk` — fields: `ParentId`, `LocalTranslationData`,
  `LocalRotationData`, `LocalScaleData`, `IsStatic`, `LocalTransform`
- `ScriptComponentReplicaChunk` — stock GridMate, probably unused in NW
- `NetBindingComponentChunk` — stock GridMate's CryEngine integration

Most NW gameplay chunks are named via the `*Component*` pattern (no literal
"*Chunk" suffix). See `analysis/javelin_classes.txt` for all 730 candidates.

### Javelin components with visible Facet / Messages strings

Most facet/message class names were stripped. Survivors (from
`analysis/javelin_chunks.txt`):

- `PlayerTutorialsComponent` — has both Client + Server Facet strings
- `WarboardComponent` — has both
- `BehaviorTreeComponent` — has `ClientMessages` + `ServerMessages`
- `GuildsComponent` — ClientFacet (with RPC method names like
  `RequestCreateGuildInvite`, `RequestDepositGuildTreasuryFunds`, etc.)
- `InventoriesComponent`, `HouseDataComponent`, `ItemManagementComponent`,
  `ActionListComponent`, `ReusableScoreboardComponent` — ServerFacet strings
- `S2STokenRefreshMessages`, `EntitlementRemoteMessages`,
  `IPlayerRemoteMessages`, `IPlayerDebugMessages`,
  `SiegeWarfareDataComponentServerMessages` — RPC groups

Full registered-chunk catalog will come from §9.1 step 7 (xref
`RegisterChunkType` equivalent in Ghidra).

---

## Tier 4 — Javelin class name corpus

- `analysis/javelin_classes.txt` — all 730 unique `Javelin::*` class names
- These are the *universe* of NW components. Not all will be networked.
- Cross-reference against Ghidra's symbol table once analysis completes.

---

## Recommended Ghidra workflow

Once auto-analysis finishes and GhidraMCP is enabled:

1. **Start at cipher string VA `0x147fbec70`.** Jump there, find xref →
   that's the `SecureSocketDriver::Initialize` equivalent. Walk backwards
   to the vtable.
2. **Jump to `GridMate-Carrier Packet Send Thread` VA `0x147fbe7e8`.**
   Its xref hits `CreateThread(..., this string, ...)`. The thread
   function is Carrier's pump loop.
3. **Search scalars for `0x42`.** The hit in a function doing a flags
   validation followed by conditional `u16` reads is `ReadMessageHeader`.
4. **Jump to `TransformReplicaChunk` VA `0x1484ee539`.** Xref → the chunk
   registration call site. Walk callers back to see where ALL chunks are
   registered during module init. Each registration call's first string
   argument is a chunk name.
5. **Enumerate state enum.** At the `CS_DISCONNECTED` cluster
   (`0x147fbec50`-ish), Ghidra should auto-detect the `char*[]` table.
   Right-click → create data type. This gives us the full
   `SecureSocketDriver::ConnState` enum labels.
6. **Enumerate stats struct.** At `conn.dataSend` cluster — the strings
   are arguments to one `LogStats()` function. The function's body will
   read from a `ConnectionStats` struct at known offsets; Ghidra's
   decompiler will lay it out for us.

---

## Deliberately NOT hunted yet

Too speculative without post-analysis symbol resolution:

- Opcode table / dispatcher for gameplay messages
- AOI / replication-window implementation
- Custom RPC trait structs
- Compression algorithm (might be LZ4 + dictionary or custom)
- Server-side Carrier handshake (most of what we capture is client-side)
