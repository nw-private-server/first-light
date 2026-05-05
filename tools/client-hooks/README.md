# client-hooks

Runtime instrumentation tools that attach to or patch the New World game binary.

**These tools are for research use only, with a legitimately-owned copy of the game.**

They do not modify any files on disk. They do not exfiltrate data. Their sole purpose is to observe the game's network behaviour and bypass certificate pinning so the client will connect to a local test server instead of Amazon's live servers — the same goal as `hosts` file redirection, but at the TLS layer.

---

## Contents

| File | What it does |
|------|-------------|
| `frida_capture.py` | Spawns the game under Frida with the trust-bypass and hook scripts loaded. Main entry point for any capture session. |
| `frida_dtls_trust_patch.js` | Frida `onEnter` hook on `FUN_145dce750` (`Javelin_SecureSocketDriver_Initialize`). Nulls the CA-bundle pointer so the DTLS driver takes its permissive verify-callback path and accepts our self-signed cert. |
| `frida_dtls_hook.js` | Full observation hook. Instruments WSASocketW, the REP state machine, transport constructors, and all observable Javelin vtable methods. Produces the session logs used for protocol reconstruction. |
| `frida_probe.js` | Lightweight probe used for one-off function observation. |
| `d3d11_proxy/` | In-process DLL that applies the same trust-bypass patch from inside the process (for environments where Frida remote injection is blocked). Not needed when Frida works. |

---

## Requirements

- Frida 16+: `pip install frida-tools`
- The **archived / non-EAC build** of New World. The live Steam build rejects all runtime instrumentation due to Easy Anti-Cheat.
- Windows, x64.

---

## Usage

```powershell
python tools\client-hooks\frida_capture.py --exe "path\to\NewWorld.exe" --name session1
```

Add `--no-patch-trust` to disable the certificate bypass (useful for baseline captures against the real server).

---

## Why these are separated from the main tools/

The files in this directory interact directly with the game binary. The rest of the project (`server/`, most of `tools/`) is a clean independent reimplementation and carries no such dependency. Keeping them here makes the boundary explicit: you can run the server stack and analyse captures without these tools entirely.

If you are forking this project for a context where you want the server code without any game-binary-touching tooling, you can exclude this directory completely.
