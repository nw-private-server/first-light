# Capture Guide

This guide explains how to capture New World network traffic and submit it so the community can use it to reconstruct the server protocol.

**Why this matters:** Once the official servers shut down, the only way to understand what the server sends is from captures made while it was still running. A capture you submit today may be the reason someone can implement Gate 3 or 4 next year.

---

## What to capture

### Priority 1 — Full login-to-world sessions

The most valuable capture is a complete session from the moment you click "Enter World" through the black-screen loading phase into the fully-rendered world. The critical window is the ~50 messages the server sends immediately after the V3 registration response (seq `0x1`), which we currently do not have in decoded form beyond `0x24`.

**Especially valuable:**
- A session that loads all the way into a running world (past the black screen)
- Sessions from different regions (eu-central-1, sa-east-1, etc.)
- Sessions with a character that has significant game state (inventory, quests, housing)

### Priority 2 — Extended in-world sessions

Once in the world, any traffic you can capture tells us about the ongoing message protocol: movement, combat, NPC interaction, zone transitions. Longer sessions covering more activities are more useful than many short ones.

### Priority 3 — Edge cases

- Character creation flow (before ever entering the world)
- Multiple logins in quick succession (captures the retry/variance behavior)
- Login failures (wrong region, full server queue)

---

## How to capture

### Option A — The `cap` tool (if you have it)

The `info/nw-login-safe-20260502-153840/` capture was made with a local `cap` tool that produces a per-message binary dump. If you have access to a capture tool that produces per-message files keyed by sequence number, use it and export with:

```
cap list                              # verify sequence range
cap export --range 0x0-0x<max> --redact
```

### Option B — Wireshark / pcapng

If you can capture at the UDP level before DTLS decryption, a `pcapng` file is useful even if the payload is encrypted. We can extract:
- DTLS handshake details (cipher, certificate, timing)
- Packet sizes and timing for each epoch-1 burst (lets us identify message boundaries)
- Correlation with game log timestamps

Capture filter: `udp and host <game-server-ip>`. The game server IP appears in your game log around `StartREPConnection`.

Save as `.pcapng` (not `.pcap`). Compress with gzip before submitting if large.

### Option C — Game log only

Even if you cannot capture network traffic, your game log (`Game.log` in the New World installation) contains:
- The exact server IP and port used each session
- Timestamps for every state transition (StartREPConnection, WaitingForREPConnection, WaitingForActorGameConnection, etc.)
- The server version string
- Error messages and disconnect reasons

A game log from a successful world-load session is useful on its own.

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
