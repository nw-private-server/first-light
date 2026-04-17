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

## 3. Still to map (next-session queue)

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
