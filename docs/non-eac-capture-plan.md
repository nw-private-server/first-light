# Non-EAC Capture Plan

This file turns the current offline DTLS/Javelin findings into a concrete next
acquisition plan.

## Goal

Obtain **session secrets or decrypted DTLS traffic** for the earliest REP
registration/bootstrap window we already isolated offline:

- server application-data seq `1..3`
- especially the stable `len 139` server record aligned with the logged
  `received registration response from REP`

## Ranked routes

### 1. Archived / non-EAC-friendly game binary + Frida hook

Status: highest-value remaining route

Why:
- `tools/client-hooks/frida_capture.py` is the only in-repo path designed to capture
  decrypted TLS/DTLS bytes directly from the process.
- The live path failed because of EAC and one older stored hook attempt failed
  because `SSL_read` was not found.
- A non-EAC-friendly target is the best place to re-run this without fighting
  runtime protection first.

What changed to support this:
- `tools/client-hooks/frida_capture.py` now accepts:
  - `--exe`
  - `--process-name`

Suggested usage:

```powershell
python tools\client-hooks\frida_capture.py --exe "G:\Path\To\Archived\NewWorld.exe" --name archived_frida
```

or, if you must attach instead of spawn:

```powershell
python tools\client-hooks\frida_capture.py --attach --process-name ArchivedNewWorld.exe --name archived_attach
```

Success criteria:
- hook installation does not fail immediately
- `packets.jsonl` contains decrypted `tls` or `dtls` packets
- ideally the session reaches the same REP registration window as the real
  captures so we can align decrypted content with known encrypted lengths/times

Archived-binary note:
- The first direct archived launch reached Frida cleanly, but the process
  immediately surfaced a Steam launch-context error before reaching network
  activity.
- The project already knows the game's Steam App ID is `1063730`.
- So the next practical archived attempt should be:
  - ensure Steam is running and logged in
  - ensure `steam_appid.txt` containing `1063730` exists next to the archived
    `NewWorld.exe`
  - then retry the Frida spawn path
- This is still lower-risk than going back to the live EAC client.
- `tools/client-hooks/frida_capture.py` now recreates `steam_appid.txt` automatically on
  every spawn attempt so this no longer has to be done by hand.

### 2. Archived / non-EAC-friendly binary + SSLKEYLOGFILE capture

Status: worth trying once the client can run without EAC interference

Why:
- the live client did not emit usable key logs
- a different runtime/build may still honor `SSLKEYLOGFILE`

What changed to support this:
- `tools/capture_session.py` now accepts:
  - `--name`
  - `--game-log`

Suggested usage:

```powershell
python tools\capture_session.py --name archived_keylog --game-log "X:\Path\To\Game.log"
```

Then launch the archived client with the environment inherited from that shell.

Success criteria:
- `capture/<session>/keys/sslkeys.log` is non-empty
- Wireshark/OpenSSL can decrypt the DTLS capture with those secrets

### 3. Local DTLS MITM against a non-EAC target

Status: only useful after trust is solved on a non-EAC target

Why:
- `tools/dtls_proxy.py` and `tools/udp_redirect.py` already form a viable
  decrypted-capture architecture if the client accepts our cert or can be
  patched in-memory without anti-cheat interference

Success criteria:
- client completes DTLS handshake with the proxy
- proxy logs decrypted application-data payloads

## Decision rule

Try routes in this order:

1. **Frida on archived/non-EAC target**
2. **SSLKEYLOGFILE on archived/non-EAC target**
3. **DTLS MITM on archived/non-EAC target**

Do not spend more time on the live Steam/EAC client until one of those routes
is available.

## Immediate practical target

As soon as any route produces decrypted DTLS bytes, focus analysis on the first
server REP registration window we already isolated offline:

- first server app-data: seq `1`, len `48`
- second: seq `2`, len `42`
- third: seq `3`, len `139`

That window is the shortest path from "we have decrypted bytes" to "we can map
the registration response and bootstrap message structure."
