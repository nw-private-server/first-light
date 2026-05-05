# NWPrivateServer

A community effort to build a private server emulator for New World before Amazon shuts down the live service (~Dec 2026). The goal is to accept the real unmodified client binary, pass auth, and let a player enter a static world. No combat, NPCs, or persistence required for MVP.

---

## Why this exists

Once the official servers go down, all knowledge of the wire protocol becomes much harder to reconstruct without live traffic to sniff. **Capturing and cataloging as many request/response pairs as possible while the servers are still up is the single most valuable thing a contributor can do right now.** See [docs/capture-guide.md](docs/capture-guide.md).

---

## Current status

| Gate | Description | Status |
|------|-------------|--------|
| 1 | Auth flow (HTTPS / OmniSDK / character creation) | **Complete** |
| 2 | Javelin REP — DTLS handshake + V3 registration | **~80%** — V3 response accepted, client stalls at world-load |
| 3 | World streaming (post-registration server messages) | Not started |
| 4 | Input / movement / actor replication | Not started |

See [docs/progress.md](docs/progress.md) for the detailed running history and [docs/next-session.md](docs/next-session.md) for the current exact blocker.

---

## What the project needs most right now

1. **Captures** — Especially post-login world-load traffic from different players/sessions. See [docs/capture-guide.md](docs/capture-guide.md) for exactly what to capture and how to submit it.
2. **Reverse engineering** — `FUN_14644a070` (`gameconn_state`, RVA `0x0644a070`) drives the state-10→11 transition. Decompiling it in Ghidra is the current unblocking task.
3. **Python/server contributors** — The REP responder (`server/rep_responder.py`) needs the post-V3 message sequence implemented once we know what to send.

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
python tools\frida_capture.py --exe "path\to\NewWorld.exe" --name session1
```

Edit your `hosts` file to redirect auth hostnames to 127.0.0.1. See [docs/capture-routes.md](docs/capture-routes.md) for the full list.

### Run the tests

```bash
python -m server.javelin.test_parser
python -m server.test_loopback
```

---

## Key protocol references

- [docs/connection-flow.md](docs/connection-flow.md) — Full login-to-world-entry sequence extracted from real game logs
- [docs/gridmate-reference.md](docs/gridmate-reference.md) — Deep-read of Lumberyard GridMate source; this is the Javelin wire-format reference
- [analysis/v3_request/BODY_DECODE.md](analysis/v3_request/BODY_DECODE.md) — Registration request body field map
- [docs/dtls-trust-bypass.md](docs/dtls-trust-bypass.md) — How to bypass the client's certificate pinning

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

- **Have a game capture?** → Follow [docs/capture-guide.md](docs/capture-guide.md) and open a PR or share in the community channel.
- **Have RE findings?** → Add a dated entry to [docs/progress.md](docs/progress.md) or a new file in `analysis/`.
- **Writing code?** → One function at a time; keep changes testable. See CONTRIBUTING.md for style expectations.
