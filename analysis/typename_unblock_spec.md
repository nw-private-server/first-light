# Type-name extraction: what's needed for further progress

> Spec for unblocking the **35 captured wire-types** that remain
> unclaimed after wakes 90-97. Five (0x03, 0x13, 0xa4, 0x14f,
> 0x15d) are confirmed by direct static-only matching; the rest
> need runtime data.

## Current state (wake 97)

- **Static methodology limits reached**. The protocol type registry
  in `info/typeregistry.json` (3487 entries) maps `typeIndex` to
  `(uuid, handler_fingerprint, ...)` but only 312 entries have a
  populated `name` field — the remaining 3175 have `name=""`.
- **Type names ARE in the binary** as MSVC RTTI strings:
  - 3482 `InstallRegistrationHook<T>` lambda typeinfos in `.data`
    near 0x14a134000+ region
  - Multiple per-type RTTI strings in `.data` near 0x14a134000-0x14a266000
- **The link from typeIndex → class-name in static binary is missing**:
  - typeinfo strings exist
  - but the binding (which lambda registers which typeIndex) is only
    made at runtime via `AZ::SerializeContext::Register<T>()`
- **Cross-correlation strategies all failed**:
  - Wake 93: handler fingerprint scan — most types share generic
    stubs (e.g. `b928000000e976e2` is shared by 15 types and has
    1019 xref sources)
  - Wake 94: 3482 typeinfo strings located, but the link from
    string-address to typeIndex is non-trivial
  - Wake 95: name-aware tail matching surfaced 297/312 named entries
    but interpolation was noisy
  - Wake 96: tightened algorithm (TU detection + count-match check)
    — 5 captured types confirmed, 35 unclaimed (honest)
  - Wake 97: low-xref unique stubs (0x8, 0x635, 0x12f6) checked —
    `.rdata` neighborhood doesn't contain the type's class name

## What WOULD unblock the remaining 35

### Option A (best): Frida hook on `AZ::SerializeContext::Register`

When the game registers a type, log `(typeIndex, type_name)`. The
registration call is invoked thousands of times at startup; ~2-3
seconds of capture covers all types.

**Frida sketch**:

```javascript
// Find the Register function (export or pattern)
const az = Module.getModuleByName("NewWorld.exe");
const registerSym = az.findExportByName("?Register@?$Class@VFoo@@@SerializeContext@AZ@@QEAAXXZ");
// Or: scan for the function pattern; signatures vary

Interceptor.attach(registerAddr, {
  onEnter: function (args) {
    // typeIndex is typically a class member; type name is rcx vtable -> typeid
    const ctx = args[0];           // SerializeContext*
    const type_id = args[1];       // u32 typeIndex
    const name_str = args[2];      // const char* class name
    send({
      typeIndex: type_id.toInt32(),
      name: Memory.readUtf8String(name_str),
    });
  }
});
```

Output: a JSON file with all `(typeIndex, name)` pairs. Cross-
joined with `info/typeregistry.json` and our wake-95 partial
mapping, this resolves all 35 unclaimed captured types AND fills
in the 3175 unnamed entries.

**Effort**: ~30 min once a real-GPU host is available (the
runtime must be reachable). The hook target's exact signature
needs static-RE first to pick the right function, but the
behavior is straightforward.

### Option B: Better captured runtime registry dump

The current `info/typeregistry.json` is a partial dump. A more
complete dump that walks ALL runtime AZ::TypeInfo entries and
extracts the `name` from each would give us names for all 3487
entries directly.

**Effort**: depends on the dumping tool. If the maintainer has
the dumper script, just re-run with the populate-name flag. If
not, write a Frida script that walks the runtime
`AZ::SerializeContext::m_classes` map and extracts names.

### Option C: Static-RE on `InstallRegistrationHook<T>` body

Each `InstallRegistrationHook<T>` instantiation has the same
basic shape:
1. Constructs an AZ::TypeInfo handler for T
2. Registers it via `SerializeContext::RegisterClass(name, handler)`
3. Reads back the assigned typeIndex

If we decompile ONE instantiation, we can identify the call
sequence pattern (which function takes the name and stores the
typeIndex). Then pattern-match across all 2025+ instantiations
to extract `(name_addr, typeIndex_storage_addr)` pairs.

**Effort**: 1-2 wakes of focused Ghidra work. Less reliable than
runtime tracing but doable autonomously.

## What we know with high confidence

These 5 captured wire-types have **authoritative** names from
direct typeregistry → typeinfo string match (wake 96):

| Wire | Full name |
|---|---|
| `0x03` | `REPClient::RegistrationResponseMsg` |
| `0x13` | `REPClient::RegistrationRequestV3Msg` |
| `0xa4` | `ClientActorRoutingAuthorizationTrait::ClientAddEntryMsg` |
| `0x14f` | `REPClient::TimeSynchMsg` |
| `0x15d` | `REPClient::PingMsg` |

Plus (from earlier wakes):
- `0x18a6 ↔ 0x1a59` are a counter-coupled R/W pair (likely
  `*::InitMessage` and `*::SubkeyResponse` or similar — verified
  by structural analysis but not by name match)
- `0x40a + 0x1be` are the handshake-blob_76 family (matched by
  shared `sub_id = 58 61 78 14` and 36-byte signing trailer)
- `0x65c` is in the same handshake family (carries the same
  trailer at offset +0x39)
- `0x8e6 ↔ 0x9fc` are paired by a 16-byte hash echo

## The 35 unclaimed captured types

With wake-97 status:

```
0x0008  0x01be  0x040a  0x05b2  0x0635  0x0651  0x065c  0x0663
0x066b  0x08e6  0x09d3  0x09fc  0x0a95  0x0ca4  0x0f7f  0x101a
0x101d  0x102e  0x102f  0x1033  0x1067  0x1096  0x1097  0x1098
0x10b0  0x12f6  0x136a  0x143d  0x16a0  0x187c  0x187f  0x18a6
0x192c  0x1a59  0x1b88
```

All have UUID + handler fingerprint in `info/typeregistry.json`.
None have a usable name string in static-binary analysis.

## Recommendation

**Pursue Option A (Frida hook) when the maintainer reaches a
real-GPU host.** It's the cheapest path with the highest
information yield. The other options remain viable but cost
more wakes.

Until then, the **5 confirmed names** plus the **byte-level
codec library** are sufficient for the captured-replay use
case. The unclaimed type names are useful for
"semantically-aware emulation" but not for replay fidelity.
