# Capture Guide

This guide explains how to capture New World network traffic and submit it so the community can use it to reconstruct the server protocol.

**Why this matters:** Once the official servers shut down, the only way to understand what the server sends is from captures made while it was still running. A capture you submit today may be the reason someone can implement Gate 3 or 4 next year.

---

## What we already have

`info/nw-login-safe-20260502-153840/` is a complete login-to-spawn capture: 177 messages spanning seq `0x0..0xb0`, ending after the StateBundle that takes the client to `state=53` (well past `WaitingForPlayerSpawn`). The byte stream is intact for every message; we have `replay_store.py` parsing it and `rep_responder.py` replaying it. What we don't yet have is full *format decode* for every type past seq `0x24`, plus anything beyond `0xb0`.

## What to capture

### Priority 1 — Extended in-world sessions

Once in the world, any traffic you can capture tells us about the ongoing message protocol: movement, combat, NPC interaction, zone transitions, inventory use. **Our existing capture stops shortly after spawn — anything past seq `0xb0` is brand-new ground.** A 30-minute capture covering varied in-world activity is more valuable than five short ones.

### Priority 2 — Variety on the login path

Cross-validation against the baseline `info/nw-login-safe-20260502-153840/` capture. Especially valuable:
- Sessions from different regions (eu-central-1, sa-east-1, ap-southeast-2, etc.)
- Sessions with a character that has significant game state (inventory, quests, housing) — the StateBundle bursts (`0x25..0x6c` are ~46 KB each in the baseline) will differ
- Different account / persona ID — confirms which fields are session-specific vs. account-specific

### Priority 3 — Edge cases

- Character creation flow (before ever entering the world)
- Multiple logins in quick succession (captures retry/variance behavior)
- Login failures (wrong region, full server queue)
- Mid-session disconnects (graceful and abrupt)

---

## How to capture

Pick the path that matches what you have:

| You have... | Use this |
|---|---|
| A non-EAC New World binary you can launch | **Recommended:** Frida + this project's capture stack — produces decrypted Javelin messages directly. See "A: Frida capture (recommended)" below. |
| The live Steam build only | Frida won't attach (EAC). You can still capture pcap-level traffic + your game log. See "B: pcap + game log". |
| Just the game log | Submit it on its own. See "C: game log only". |

### A — Frida capture (recommended)

This is the primary path the project uses, and it's the source of
`info/nw-login-safe-20260502-153840/`. It produces **decrypted
Javelin packets** in a structured `capture/<timestamp>/` directory.

**Quick command (assumes you've set up the stack once):**

```powershell
# Three terminals from the repo root with the venv activated:

# Terminal A — auth mock (admin PowerShell, binds 443)
python -m server.auth_mock --port 443

# Terminal B — DTLS REP server
python -m server.rep_responder

# Terminal C — the game itself, spawned under Frida
python tools\client-hooks\frida_capture.py `
    --exe "C:\path\to\NewWorld\Bin64\NewWorld.exe" `
    --name session_descriptor
```

**The full walkthrough** — venv setup, cert generation,
`certutil -addstore` for the CA, `setup_hosts.py`, what `success`
looks like, and common gotchas — is in
[../tools/client-hooks/README.md](../tools/client-hooks/README.md).
Read that the first time you set this up; come back here when you
have a `capture/<timestamp>/` directory and want to know what to
redact before sharing.

When the session ends:

- `capture/<timestamp>_<name>/packets/` has one `.bin` file per packet
- `packets.jsonl` has one JSON object per packet (direction, type,
  size, hookName, hexHead, filename)
- `session.log` is the human-readable event timeline
- `hooks.log` shows which Frida hooks installed (success / not_found
  / error)

The `messages-redacted.txt` format the project uses for
community-shared captures is built from this directory — see
"Submission format" below.

### B — pcap + game log (for live-EAC builds)

If your only access is the live Steam build, Frida runtime
instrumentation won't attach. You can still produce useful
captures:

- **`pcapng`** at the UDP level. Even though the payload is
  encrypted, we extract from it: DTLS handshake details (cipher,
  certificate, timing), packet sizes and timing for each
  epoch-1 burst (this lets us identify message boundaries), and
  correlation with game-log timestamps.
  - Capture filter: `udp and host <game-server-ip>`
  - The game server IP appears in your `Game.log` around
    `StartREPConnection`
  - Save as `.pcapng` (not `.pcap`); gzip if large.
- **Game log** (see C below) alongside the pcap so the timeline
  can be aligned.

### C — Game log only

Even if you cannot capture network traffic at all, your game log
(`Game.log` in the New World installation) is useful on its own:

- Exact server IP and port for the session
- Timestamps for every state transition
  (`StartREPConnection`, `WaitingForREPConnection`,
  `WaitingForActorGameConnection`, …)
- Server version string
- Error messages and disconnect reasons

A `Game.log` from a session that successfully reached an
in-world state is informative even without any network capture.

---

## Redacting sensitive data before submitting

**You must redact before submitting.** The raw Javelin stream contains your Steam auth ticket, persona ID, session token, and platform user ID. These are sensitive and should never be committed to the repo.

What to redact (replace bytes with `XX` in hex dumps):
- Steam auth ticket (a large binary blob, typically 512–1024 bytes in the V3 registration request)
- Session token (32 bytes in the V3 registration response)
- Persona ID strings (look like `amzn1.developerPersonaId.xxxxxxxx-...`)
- Steam ID 64 (17-digit decimal, e.g. `76561198069524636`)
- Any UUID that appears only in your session and not in the protocol structure

What is **not** sensitive and should be kept:
- Type IDs, sequence numbers, size fields
- Fixed protocol framing bytes
- Server version string (`[RETAIL].Javelin.1.365.xxxx.xxxxxxx`)
- Timestamp structure
- StateBundle data that doesn't contain account identifiers

When in doubt, redact it. A dump with more redactions is more useful than no dump at all.

---

## Submission format

Follow the structure of `info/nw-login-safe-20260502-153840/`:

```
info/<your-capture-name>/
  README.md               # required — see template below
  messages-redacted.txt   # xxd-style dump with XX for redacted spans
  capture-index.tsv       # seq, direction, type, size index (optional but helpful)
  redaction-report.txt    # summary of what was redacted (optional)
```

### messages-redacted.txt format

Use the format from `info/nw-login-safe-20260502-153840/messages-redacted.txt` — one block per message, separated by `================` lines:

```
================================================================================
file: 0x1_T0x3_R.bin
seq: 0x1 (1)
direction: R
type: 0x3 (3)
size: 88 bytes
raw:
00000000  00 01 03 00 00 00 00 0b  88 8d 68 70 6c 41 5b 20  |..........hplA[ |
00000010  XX XX XX XX XX XX XX XX  XX XX XX XX XX XX XX XX  |XXXXXXXXXXXXXXXX|
...
```

- `W` = client to server (what you sent)
- `R` = server to client (what the server sent — this is the valuable part)
- `type` = the GridMate/Javelin type ID (hex)
- `XX` = redacted byte

### README.md template

```markdown
# <Capture name>

- date: YYYY-MM-DD
- game version: (found in game log, e.g. `6031`)
- server version: (e.g. `[RETAIL].Javelin.1.365.6031.6006993`)
- region: (e.g. `us-west-2`)
- character state: (e.g. "fresh character, never entered world" or "existing character, ~10h playtime")
- sequence range: 0x0 through 0xXX
- messages exported: N
- did the session reach an in-world state: yes/no

## Notes

Any observations about what happened during the session, unusual messages,
or context that might help decode specific messages.

## Redaction summary

What spans were redacted and why.
```

---

## Naming your capture

Use: `<game-version>-<YYYYMMDD>-<brief-description>`

Examples:
- `6031-20260518-world-load-uswest2`
- `6031-20260520-character-create-only`
- `6031-20260525-in-world-30min-combat`

---

## Submitting

Open a pull request adding your `info/<capture-name>/` directory. The PR description should include what game state was captured and whether the session reached an in-world state.

If you cannot open a PR, share the files in the community channel — someone will add them.

---

## What happens with your capture

Once in the repo, the capture is loaded by `server/javelin/replay_store.py` and replayed to real clients by `server/rep_responder.py` (with `--replay-after-v3`). This lets us test whether replaying your server messages to a different client drives it toward a loaded world state.

Captures are also used for manual protocol analysis — comparing message shapes across multiple sessions helps identify which fields are fixed (protocol structure) vs. variable (session-specific data).

---

## Questions about a specific message

If you have a capture and want help understanding what a particular message type means, open an issue or ask in the community channel with:
1. The type ID (hex)
2. The size in bytes
3. A hex dump of the first 64 bytes (redacted if needed)

Cross-referencing against the type registry in `info/typeregistry.json` is a good first step.
