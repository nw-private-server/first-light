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
