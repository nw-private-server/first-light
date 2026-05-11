# New World: First Light

[![Tests](https://github.com/nw-private-server/first-light/actions/workflows/tests.yml/badge.svg)](https://github.com/nw-private-server/first-light/actions/workflows/tests.yml) [![Pages](https://github.com/nw-private-server/first-light/actions/workflows/pages.yml/badge.svg)](https://nw-private-server.github.io/first-light/) [![Test count](https://img.shields.io/endpoint?url=https%3A%2F%2Fnw-private-server.github.io%2Ffirst-light%2Fbadge-tests-count.json)](https://nw-private-server.github.io/first-light/#overview) [![Codecs](https://img.shields.io/endpoint?url=https%3A%2F%2Fnw-private-server.github.io%2Ffirst-light%2Fbadge-codecs.json)](https://nw-private-server.github.io/first-light/#overview) [![Live decoder](https://img.shields.io/endpoint?url=https%3A%2F%2Fnw-private-server.github.io%2Ffirst-light%2Fbadge-live-decoder.json)](https://nw-private-server.github.io/first-light/#explore)

A community effort to build a private server emulator for New World before Amazon shuts down the live service (~Dec 2026). The goal is to accept the real unmodified client binary, pass auth, and let a player enter a static world. No combat, NPCs, or persistence required for MVP.
First Light is in reference to the territory "First Light" that was eventually removed from the game.

**Live dashboard:** [nw-private-server.github.io/first-light](https://nw-private-server.github.io/first-light/) — friendly project overview, captured-traffic charts, connection-state diagram, and the codec/decompile catalog. Mobile-friendly; auto-redeploys on push.

**Recent milestones:**
- [150-wake session retrospective](analysis/session_retrospective_150.md) — wakes 1-150: 40/40 codec coverage, central dispatcher, state-10 RE breakthrough, audit arcs, 100% decompile cross-link density.
- [Second-stretch retrospective (wakes 151-196)](analysis/session_retrospective_196.md) — rep_responder ↔ dispatcher integration foundation, live-decoder coverage at 80% (32/40 captured wire-types decodable from the Explore tab), 7-test cross-check graph. Frozen wake-196 snapshot.
- [Third-stretch retrospective (wakes 197-227)](analysis/session_retrospective_227.md) — live-decoder coverage push to 90.0% (36/40) with the wake-221 floor decision, phase-2 emission swap + counter-advance extension, and the cross-check graph grown from 9 to 18 with five self-referential pins.

**Design decisions:**
- [Why the live decoder stops at 90.0% (wake 221)](analysis/decision_0x065c_live_decoder.md) — 0x065c (12706-byte world-data-blob) deferred by explicit decision rather than reflexive shipping. Criteria + reversal conditions documented.


---

## Why this exists

Once the official servers go down, all knowledge of the wire protocol becomes much harder to reconstruct without live traffic to sniff. **Captures made while the servers are still up are the single most durable thing a contributor can produce.** We have one full login-to-state=53 capture (`info/nw-login-safe-20260502-153840/`); we still need more from different regions, character states, and especially extended in-world traffic. See [docs/capture-guide.md](docs/capture-guide.md).

---

## Current status (2026-05-11)

| Gate | Description | Status |
|------|-------------|--------|
| 1 | Auth flow (HTTPS / OmniSDK / character creation) | **Complete** |
| 2 | Javelin REP — DTLS handshake + V3 registration | **V3 response accepted by client; `rep.ready` flips 0→1; client then re-sends V3 every ~500ms anyway and the session is destroyed after ~30s. That retry loop is the active blocker.** Infrastructure for the next experiment landed since 2026-05-05: the rep_responder ↔ central-dispatcher integration arc is shipped behind two feature flags (`heartbeat_use_dispatcher` for emission swap, `heartbeat_advance_counter` for counter mutation), both default off and proven byte-equivalent to the captured replay path. Real-GPU validation will flip them and observe the retry loop. |
| 3 | World streaming (post-registration server messages) | Not started |
| 4 | Input / movement / actor replication | Not started |

For background, the running session log is in [docs/progress.md](docs/progress.md) and the latest blocker description is in [docs/next-session.md](docs/next-session.md). These are working notes for the maintainers' working sessions — read them for context, but don't worry about updating them.

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

- [docs/protocol-overview.md](docs/protocol-overview.md) — **Start here.** Master synthesis: state-machine map, layered protocol diagram, current open questions, file index.
- [docs/connection-flow.md](docs/connection-flow.md) — Full login-to-world-entry sequence extracted from real game logs
- [docs/post-v3-sequence.md](docs/post-v3-sequence.md) — 22-phase post-V3 server→client message reference
- [docs/gridmate-reference.md](docs/gridmate-reference.md) — Deep-read of Lumberyard GridMate source; the Javelin wire-format reference
- [analysis/state_machine_summary.md](analysis/state_machine_summary.md) — GameConnection state-machine map with handler addresses
- [analysis/message_inventory.md](analysis/message_inventory.md) — Catalog of 2,025 typed messages across 174 namespaces
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

See [CONTRIBUTING.md](CONTRIBUTING.md) — has a quick-start (clone → venv → pytest → `decode_message.py`) plus the reference doc list. The short version:

- **Have a game capture?** → Follow [docs/capture-guide.md](docs/capture-guide.md) and open a PR or share in the community channel.
- **Have RE findings?** → Drop them in `analysis/` as a new `.md` or `.txt` file (look at existing entries for the format).
- **Writing code?** → One function at a time; keep changes testable. See [analysis/codec_library_overview.md](analysis/codec_library_overview.md) for the codec library structure and "how to add a new codec" walkthrough.
