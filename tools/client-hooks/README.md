# client-hooks — capturing decrypted packets from a running game

Runtime instrumentation tools that attach to a New World game binary and
write decrypted DTLS / Javelin packets to a local capture session.

**These tools are for research use only, with a legitimately-owned copy of
the game.** They do not modify any files on disk. They do not exfiltrate
data. Their sole purpose is to observe the game's network behaviour and
bypass certificate pinning so the client will connect to a *local test
server* — the same goal as a `hosts` file redirect, just at the TLS layer.

---

## Contents

| File | What it does |
|------|-------------|
| `frida_capture.py` | Spawns or attaches to the game with the trust-bypass and observation hooks loaded. **This is the entry point** — everything else is a script it loads. |
| `frida_dtls_trust_patch.js` | `onEnter` hook on `FUN_145dce750` (`Javelin_SecureSocketDriver_Initialize`). Nulls the CA-bundle pointer so the DTLS driver takes its permissive verify-callback path and accepts our self-signed cert. |
| `frida_dtls_hook.js` | Full observation hook. Instruments `WSASocketW`, the REP state machine, transport constructors, and Javelin vtable methods. Produces the session log used for protocol reconstruction. |
| `frida_probe.js` | Lightweight probe used for one-off function observation. |
| `d3d11_proxy/` | In-process DLL that applies the same trust-bypass patch from inside the process (used when Frida remote injection is blocked). Not needed when Frida works. |

---

## Requirements

- **Windows, x64.** The captured-packets workflow targets the Windows build.
- **A non-EAC build of New World.** The live Steam build refuses runtime
  instrumentation due to Easy Anti-Cheat. "Non-EAC build" here means any
  copy of `NewWorld.exe` you launch directly via
  `frida.spawn(NewWorld.exe)` instead of through `NewWorldLauncher.exe`
  → `EasyAntiCheat_Launcher.exe`. Skipping the launcher chain skips EAC
  entirely. There is no patched binary; same bytes Steam ships.
- **Steam running and logged in.** The game still calls `SteamAPI_Init`;
  it just doesn't need EAC to be alive.
- **Python 3.11 or 3.12.** Python 3.13 has a broken `python3-dtls`.
- **Frida 16+.** `pip install frida-tools`.
- **OpenSSL on PATH.** Needed once to generate the self-signed CA the
  trust patch installs.
- **Admin Windows shell** for `certutil` and the hosts-file edit. The
  Frida launch itself does not need admin.

---

## End-to-end capture walkthrough

This is the full sequence from a clean clone to a `capture/<session>/`
directory full of decrypted packets.

### 1. One-time setup (do this once per machine)

```powershell
# From the repo root in an Administrator PowerShell:

# 1.1 — Create a Python venv with the right interpreter
python3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install frida-tools pyOpenSSL pytest pytest-timeout

# 1.2 — Generate the self-signed CA + auth cert that the trust patch
#       routes to. This writes:
#         server/certs/newworld_ca.crt   (CA — install in OS trust store)
#         server/certs/newworld_ca.key   (CA private key — never commit)
#         server/certs/auth.crt          (TLS server cert)
#         server/certs/auth.key          (TLS server private key)
python tools\generate_auth_certs.py
python tools\generate_cert.py        # rep_responder uses server.crt/.key

# 1.3 — Trust the CA so the game's HTTPS client accepts our auth_mock.
certutil -addstore -f "ROOT" server\certs\newworld_ca.crt
# Verify:
Get-ChildItem Cert:\LocalMachine\Root | Where-Object Subject -Match "NewWorldPrivate"
```

### 2. Per-session setup

```powershell
# 2.1 — Redirect Amazon's auth hostnames to your local auth_mock.
#       Default --target is 127.0.0.1 (i.e. auth_mock running on the
#       same machine). Reverts cleanly with --revert.
python tools\setup_hosts.py --apply
# Verify (any one of the redirected hostnames should resolve to 127.0.0.1):
nslookup d3bj4csovi1fe8.cloudfront.net

# 2.2 — Confirm Steam is running + logged in. The game checks for an
#       active Steam session and aborts otherwise.
Get-Process steam
```

### 3. Start the local server stack

In **two separate terminals** (both in the project root, both with the
venv activated):

```powershell
# Terminal A — HTTPS auth mock on port 443 (needs admin to bind 443)
python -m server.auth_mock --port 443

# Terminal B — DTLS REP server on UDP 24083
python -m server.rep_responder
```

Wait until both print their "ready / listening" lines. Test connectivity
from yet another shell:

```powershell
Test-NetConnection 127.0.0.1 -Port 443     # should be True
```

### 4. Launch the game with Frida

In a **third terminal** (also venv-activated):

```powershell
python tools\client-hooks\frida_capture.py `
    --exe "C:\path\to\NewWorld\Bin64\NewWorld.exe" `
    --name session1
```

What this does:

1. Creates `capture/<timestamp>_session1/` with empty `packets.jsonl`,
   `session.log`, and `hooks.log`.
2. Calls `frida.spawn(NewWorld.exe)` — the process starts suspended,
   bypassing the EAC launcher chain.
3. Loads `frida_dtls_trust_patch.js` first, so the trust bypass is in
   place before the DTLS driver initializes.
4. Loads `frida_dtls_hook.js` — installs ~25 hooks on networking and
   Javelin functions.
5. Resumes the process. The game window appears.
6. Streams hook events, each captured packet, and console summaries
   into the session directory.

You should see in the terminal:

```
[+] Spawned PID: <pid> (suspended)
[+] Attached to PID <pid>
[+] Trust patch loaded (frida_dtls_trust_patch.js)
[+] Hook script loaded (frida_dtls_hook.js)
[+] Process resumed -- game is starting
[*] Capturing packets. Press Ctrl+C to stop.
  [DTLS] -> #000001  ...  bytes  000001_write_dtls.bin
  [DTLS] <- #000002  ...  bytes  000002_read_dtls.bin
  ...
```

Press **Ctrl+C** when you've captured enough. The session dir is
self-contained from there.

### 5. What the session directory looks like

```
capture/20260518_143012_session1/
    packets/                        # one binary file per packet
        000001_write_dtls.bin
        000002_read_dtls.bin
        ...
    packets.jsonl                   # one JSON object per packet (metadata + filename)
    session.log                     # human-readable timeline of all events
    hooks.log                       # which hooks installed (success / not_found / error)
```

For protocol analysis you usually want `session.log` (everything in order)
and either `packets.jsonl` or specific files in `packets/`.

---

## Common workflow variants

### Attach to an already-running game

If you want to skip past EAC initialization manually and only attach
later:

```powershell
python tools\client-hooks\frida_capture.py --attach --name late_attach
# Or by PID:
python tools\client-hooks\frida_capture.py --attach --pid 12345
```

The trust patch can't take effect retroactively (the DTLS driver has
already initialized), so this mode is for hooking AFTER a known-good
trust bypass — useful for debugging specific later phases without
restarting the game.

### Skip the trust patch (baseline against the real server)

```powershell
python tools\client-hooks\frida_capture.py --exe ... --name baseline --no-patch-trust
```

Useful for capturing the game talking to Amazon's real servers (no
hosts-file redirect, no `auth_mock` running). Don't use this with the
hosts redirect active — the game will fail TLS validation against your
local mock.

### Run only the trust patch

If you just want a way for the game to accept the mock cert without
the heavy observation hook:

```powershell
python tools\client-hooks\frida_capture.py --exe ... --name trust_only
# (Edit frida_capture.py's HOOK_SCRIPT load step to skip — or
#  use frida directly with just the trust patch JS.)
```

For most users the default flow (trust patch + observation hook) is
what you want.

---

## Common gotchas

**Steam launch-context error / game crashes immediately.** The game
reads `steam_appid.txt` next to `NewWorld.exe` to know its app ID
when launched without going through Steam's normal flow.
`frida_capture.py` writes this file automatically on every spawn —
so this only fails if the executable directory is read-only. Check
that it's writable.

**`hooks.log` shows `not_found` for several entries.** Some of the
hook target names are tried against multiple modules and only one
should match. `not_found` for `ws2_socket` (lowercase) is normal —
that's a Linux-style export name that Windows doesn't have.

**`Frida cannot find user32.dll!MessageBoxW`** or similar
"`TypeError: not a function`" errors. Frida 17 changed the static
`Module.findExportByName(name, exp)` form — the working pattern is
`Process.getModuleByName(name).findExportByName(exp)`. The shipped
hook scripts already handle this, but if you write your own scripts
keep the API change in mind.

**Crashpad warning `SendToCrashHandlerServer ... CreateFile failed`**
appears once per spawn in stderr. It's a benign result of the game's
crash reporter not finding its handler server — no action needed.

**`FUN_145dce750` not found / RVA mismatch.** The trust patch
hardcodes RVA `0x5dce750` from the binary downloaded via SteamCMD on
2026-05-06. If you have a different game build, the function moved
and you need to update the constant in `frida_dtls_trust_patch.js`.

**Game launches, hooks load, but nothing in `packets.jsonl`.** Most
likely the game is stalling before reaching network init. Common
causes: missing assets, GPU virtualization issues if you're in a VM
(see `docs/non-eac-capture-plan.md`), missing `steam_appid.txt`. Check
`session.log` for the last event before the silence.

---

## Submitting captures

Once you have a `capture/` session, see
[../../docs/capture-guide.md](../../docs/capture-guide.md) for the
project's submission workflow:

- What to redact before sharing (Steam tickets, persona IDs, session
  tokens, Steam ID 64s)
- The directory layout the project uses for community-shared captures
  (`info/<capture-name>/`)
- The `messages-redacted.txt` xxd-style format
- The README template for your capture

The capture-guide doc also lists the highest-priority capture targets:
extended in-world sessions (past the existing baseline's seq `0xb0`)
are the most valuable.

---

## Why this directory is separate from the rest of `tools/`

The files here interact directly with the game binary. The rest of
the project (`server/`, most of `tools/`) is a clean independent
reimplementation and has no dependency on a New World installation.
Keeping the boundary explicit means:

- You can run the server stack and analyse captures without these
  tools at all.
- A fork that doesn't want to ship game-binary-touching tooling can
  exclude this directory completely.

There is intentionally no `from tools.client_hooks import ...` in
the rest of the codebase.
