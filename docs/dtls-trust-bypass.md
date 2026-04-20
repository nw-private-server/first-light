# DTLS Trust Bypass

Runtime-only workaround for the current REP/DTLS blocker.

## Problem

The client now reaches `StartREPConnection` and performs a real DTLS handshake
against our local probe, but fails with:

- `@mm_csdkerr_transport_security_error (2)` in `Game.log`
- fatal DTLS alert `unknown ca` in the probe

So the blocker is **certificate trust**, not queue/login JSON.

## Ghidra findings

### DTLS driver init

`FUN_145dce750` is the `Javelin_SecureSocketDriver_Initialize` equivalent.

Relevant logic:

```c
bVar8 = (char)param_1[0x4e] != '\0';
if (param_1[0x51] == 0) {
    FUN_1478eff50(param_1[0x1a], bVar8 + 1, FUN_1402a1a70);
}
else {
    ...
    FUN_1478eff50(param_1[0x1a], bVar8 + 1, 0);
}
```

`FUN_1402a1a70` is the verify callback:

```c
undefined8 FUN_1402a1a70(void)
{
    return 1;
}
```

Meaning:

- when `param_1[0x51] == 0`, the DTLS layer accepts any cert
- when `param_1[0x51] != 0`, it builds a CA bundle and enforces normal OpenSSL
  certificate validation

### Embedded cert

The gridmate-udp transport constructor path (`FUN_146b6a270 -> FUN_146b34780`)
passes an embedded PEM blob at `0x149f80d90`. That PEM is the real self-signed
`CN=New World` certificate. So the REP trust path is effectively bundled/pinned
inside the client transport setup.

## Runtime patch strategy

Instead of modifying `NewWorld.exe` on disk, patch the branch in memory so the
driver always takes the permissive callback path.

### Patch point

Function VA:

- `0x145dce750`

Branch site:

- `0x145dce8b5`

Original branch:

```asm
145dce8ad: CMP qword ptr [RDI + 0x288],0x0
145dce8b5: JZ  0x145dce9d4
```

If the field is zero, the code jumps to the permissive `FUN_1402a1a70` path.
Otherwise it builds the CA list and calls `SSL_CTX_set_verify(..., 0)`.

### Recommended runtime patch

Force the jump unconditionally:

- original bytes at `0x145dce8b5`: `0F 84 19 01 00 00`
- patched bytes: `E9 19 01 00 00 90`

This converts the conditional `JZ` into an unconditional `JMP` to the same
target, skipping CA-bundle validation and always using the permissive callback.

## Tooling in this repo

- `tools/frida_dtls_trust_patch.js`
- `tools/frida_dtls_trust_patch.py`

Use the Python wrapper to attach to a running `NewWorld.exe` and apply the
in-memory patch after EAC init but before clicking `Play`.

## Caveat

This is a runtime patch against a live EAC-protected game process. It avoids
on-disk EXE modification, but it still carries anti-cheat risk.
