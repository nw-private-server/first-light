# New World: First Light

[![Tests](https://github.com/nw-private-server/first-light/actions/workflows/tests.yml/badge.svg)](https://github.com/nw-private-server/first-light/actions/workflows/tests.yml)

A community effort to build a private server emulator for New World before Amazon shuts down the live service (~Dec 2026). The goal is to accept the real unmodified client binary, pass auth, and let a player enter a static world. No combat, NPCs, or persistence required for MVP.

The name *First Light* is the goal: be the first community server to come online before the official ones go dark.

---

## Why this exists

Once the official servers go down, all knowledge of the wire protocol becomes much harder to reconstruct without live traffic to sniff. **Captures made while the servers are still up are the single most durable thing a contributor can produce.** We have one full login-to-state=53 capture (`info/nw-login-safe-20260502-153840/`); we still need more from different regions, character states, and especially extended in-world traffic. See [docs/capture-guide.md](docs/capture-guide.md).

---

## Current status (2026-05-05)

| Gate | Description | Status |
|------|-------------|--------|
| 1 | Auth flow (HTTPS / OmniSDK / character creation) | **Complete** |
| 2 | Javelin REP — DTLS handshake + V3 registration | **V3 response accepted by client; `rep.ready` flips 0→1; client then re-sends V3 every ~500ms anyway and the session is destroyed after ~30s. That retry loop is the active blocker.** |
| 3 | World streaming (post-registration server messages) | Not started |
| 4 | Input / movement / actor replication | Not started |

For background, the running session log is in [docs/progress.md](docs/progress.md) and the latest blocker description is in [docs/next-session.md](docs/next-session.md). These are working notes for the maintainers' Claude Code sessions — read them for context, but don't worry about updating them.

---

## What the project needs most right now

1. **Reverse engineering — top priority.** `FUN_14644a070` (`gameconn_state`, RVA `0x0644a070`) drives the state-10→11 transition. Decompile it and find what condition advances state past 10 after the V3 response is accepted. Sibling target: `FUN_146b3c250 + 0x58f` — find what writes to `[R13+0xfd]`, the byte that fires the destroy loop.
2. **Captures with in-world traffic.** Our existing capture goes through `state=53` (past `WaitingForPlayerSpawn`) but stops before extended in-world activity. A session that loads into a running world AND captures movement/combat/zone-transition messages is the single most useful new capture. See [docs/capture-guide.md](docs/capture-guide.md) for the priority list.
3. **Python/server contributors.** Once RE identifies the post-V3 message sequence, `server/rep_responder.py` needs to send it. Independent of that: multi-peer support (currently single-peer), and a Carrier-level reliable ACK on the V3 request itself (a 5-line experiment that may be the entire fix).

---

## Repository layout

```
server/          Core server implementation
  auth_mock.py     HTTPS auth gateway mock (handles all client auth endpoints)
  rep_responder.py DTLS-terminating Javelin REP server (the game server stub)
  javelin/         Javelin protocol library
    frame.py         Message framing — parse_datagram / marshal_datagram
    bitstream.py     Bit-level I/O (aligned + unaligned)
    v3_request.py    RegistrationRequestV3Msg parser
    v3_response.py   RegistrationResponseMsg encoder
    replay_store.py  Loads captured message dumps for replay

tools/           Standalone utilities (capture, analysis, RE helpers)
  client-hooks/    Game-binary-interacting tools (Frida, d3d11 proxy) — kept separate from the server code
docs/            Protocol documentation and session notes
analysis/        Ghidra findings, decompilation artifacts, hex decode notes
capture/         Local session logs (not committed — see .gitignore)
info/            Community-shared captures and reference data
```

---

## Quick start

### Prerequisites

- Python 3.11 or 3.12 (python3-dtls is broken on 3.13)
- pyOpenSSL: `pip install pyopenssl`
- A non-EAC build of New World (archived/offline build)
- Frida 16+: `pip install frida-tools` (for trust bypass on the client)

### Run the mock stack

```powershell
# Terminal 1 — HTTPS auth mock (port 443, needs admin on Windows)
python -m server.auth_mock --port 443

# Terminal 2 — Javelin REP server
python -m server.rep_responder

# Terminal 3 — game client with Frida trust bypass
python tools\client-hooks\frida_capture.py --exe "path\to\NewWorld.exe" --name session1
```

Before starting the client, redirect auth hostnames to your loopback. Run `python tools\setup_hosts.py` (admin) — it appends every required host to `C:\Windows\System32\drivers\etc\hosts` and adds matching IPv6 entries.

### Run the tests

```bash
pip install pytest
pytest
```

CI runs the same suite on Python 3.11 and 3.12 for every push and PR (see `.github/workflows/tests.yml`). New captures dropped under `info/<name>/messages-redacted.txt` are auto-validated by `server/test_captures.py` — no test registration needed.

---

## Key protocol references

- [docs/connection-flow.md](docs/connection-flow.md) — Full login-to-world-entry sequence extracted from real game logs
- [docs/gridmate-reference.md](docs/gridmate-reference.md) — Deep-read of Lumberyard GridMate source; this is the Javelin wire-format reference
- [analysis/v3_request/BODY_DECODE.md](analysis/v3_request/BODY_DECODE.md) — Registration request body field map
- [docs/dtls-trust-bypass.md](docs/dtls-trust-bypass.md) — How to bypass the client's certificate pinning

---

## Mirrors and resilience

This repository is the primary home for the project, but the code should outlive any single hosting platform. If you want to keep a mirror:

**Codeberg** (EU non-profit, recommended):
```bash
git remote add codeberg https://codeberg.org/<your-org>/first-light.git
git push codeberg main
```

**Self-hosted Forgejo/Gitea:**
```bash
git remote add self https://<your-host>/first-light.git
git push self main
```

You can push to multiple remotes at once by adding them all to the `origin` push URL:
```bash
git remote set-url --add --push origin https://codeberg.org/<your-org>/first-light.git
```

If you maintain a mirror, please keep the `info/` captures synced — that data is the hardest to reconstruct after shutdown.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

- **Have a game capture?** → Follow [docs/capture-guide.md](docs/capture-guide.md) and open a PR or share in the community channel.
- **Have RE findings?** → Drop them in `analysis/` as a new `.md` or `.txt` file (look at existing entries for the format).
- **Writing code?** → One function at a time; keep changes testable. See CONTRIBUTING.md for style expectations.
