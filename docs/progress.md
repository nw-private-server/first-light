# New World Private Server — Progress & Findings

> Living document. Updated as we learn more.
> Last updated: 2026-04-17 (GridMate reference added; AzNetworking ref demoted)

---

## Goal

Build a private server emulator that can accept the New World client, pass auth, and render a static world without crashing. No combat, NPCs, or persistence required for MVP.

---

## Roadmap

### Gate 1: Intercept the Auth Flow
**Status: ~70% complete**

We have the full auth sequence documented from two separate game sessions (Dec 2025, Apr 2026). No traffic interception needed — the game logs it all in plaintext.

**What we know:**
- Auth uses **Amazon OmniSDK 1.6**, not a simple REST POST as initially assumed
- Flow: Steam ticket → OmniSDK `CreateSession` → persona ID → `/prod/credentials/omni` → AWS SigV4 credentials
- The client receives two sets of AWS credentials: "gateway" and "persona"
- Credentials refresh on ~55 minute intervals
- Two separate auth sessions happen per login (one per-region for gameplay, one for us-east-1)
- Channel config (list of all regional endpoints) is fetched from a single CloudFront URL

**Auth endpoints documented:**

| Region | Auth Stack (API Gateway) | Gateway (CloudFront) |
|--------|--------------------------|----------------------|
| eu-central-1 | `2mfrik7h83.execute-api.us-east-1.amazonaws.com/Prod` | `d1w0bfy6smo4d1.cloudfront.net/prod` |
| sa-east-1 | `kqqt5twsi7.execute-api.us-east-1.amazonaws.com/Prod` | `d1cjlmzk0xrm0z.cloudfront.net/prod` |
| us-east-1 | `eudbjx6mig.execute-api.us-east-1.amazonaws.com/Prod` | `d2oeuvxi3kfsrw.cloudfront.net/prod` |
| us-west-2 | `q8hqllbg6k.execute-api.us-east-1.amazonaws.com/Prod` | `d3bj4csovi1fe8.cloudfront.net/prod` |
| ap-southeast-2 | `hhf8nn71vb.execute-api.us-east-1.amazonaws.com/Prod` | `de4mfzk9wkelz.cloudfront.net/prod` |

**What we still need:**
- [ ] Capture the actual HTTP request/response bodies for `/prod/credentials/omni` (need Frida or mitmproxy — SSLKEYLOGFILE doesn't work)
- [ ] Understand the OmniSDK `CreateSession` call — what does it send, what does it return?
- [ ] Determine if the returned AWS credentials use standard SigV4 or a custom signing scheme
- [ ] Understand what the channel config JSON contains (fetch it directly before shutdown)

### Gate 2: Capture the Game Server Protocol
**Status: ~60% complete**

**Key corrections from second capture session (2026-04-16):**
- NOT WebSocket (as Perplexity said)
- NOT plain TCP (as first log analysis suggested)
- It's **DTLS 1.2** (Datagram TLS) — encrypted UDP

**What we know:**
- Game server uses **UDP with DTLS 1.2 encryption**, not TCP
- The game log says "REP socket connection" but the actual transport is UDP+DTLS
- Server IPs are AWS Global Accelerator: `35.71.190.194`, `52.223.16.88`
- Port is **dynamic** — observed `25493`, `23971`, `58068` across sessions
- The server IP + port are provided in the login ticket response, not hardcoded
- DTLS handshake includes mutual authentication (server sends Certificate Request)
- Server certificate: `CN=New World, O=Amazon, OU=Amazon Game Studios, Email=ags-nw@amazon.com`
- Certificate validity: 2025-08-04 to 2027-01-06
- Connection flow after DTLS: register → registration response → actor game connection → spawn point → player spawn → in game
- Server version: `[RETAIL].Javelin.1.365.6031.6004151`
- Voice chat is separate (Vivox, SIP-based, `nwxp.vivox.com`)
- Typical game session: ~2800 UDP packets to game server over ~30s of gameplay

**What we captured:**
- 60MB pcap from first session (HTTPS only, missed REP due to port filter)
- 7.5MB pcap from second session — **includes full DTLS handshake + encrypted game traffic**
- Full DTLS server certificate extracted and decoded
- Complete list of TLS SNI hostnames the client connects to (see connection-flow.md)

**What we still need:**
- [x] ~~Capture the REP stream~~ — done (second capture, DTLS over UDP)
- [x] ~~Determine if REP is encrypted~~ — yes, DTLS 1.2
- [ ] Decrypt DTLS traffic — Frida hook on SSL_read/SSL_write, or extract session keys
- [ ] Determine if client sends a client certificate (Certificate Request seen in handshake)
- [ ] Capture longer sessions with varied activities (combat, inventory, travel between zones)
- [ ] Understand the relationship between the HTTPS gateway traffic and the DTLS game traffic

### Gate 3: Decode the Packet Format
**Status: ~25% — protocol reference built from Lumberyard GridMate**

**Critical finding (2026-04-17):** New World does **NOT** use stock O3DE AzNetworking. Static scan of NewWorld.exe found **0 hits / 101 checks** on AzNetworking markers but **5001 hits** on `Javelin::` classes. The binary uses a **bespoke networking library named "Javelin"** — almost certainly forked from Lumberyard's older **GridMate** (pre-O3DE, ~2017 era), because:
- `"GridMate"` appears as a string 30× in the binary (log tags likely preserved)
- `"Lumberyard"` appears 7×
- The Javelin class patterns (`*ComponentClientFacet` / `*ComponentServerFacet`, `*ComponentClientMessages` / `*ComponentServerMessages`) match GridMate's `ReplicaChunk` model with a NW-specific split into data-facet + message-facet
- Server version string: `[RETAIL].Javelin.1.365.6031.6004151`

**Primary protocol reference: `docs/gridmate-reference.md`** — a 500+ line deep-read of Lumberyard GridMate source (Carrier header, channel/message framing, reliability/ack vector, DTLS integration, replica system, RPC wire format, handshake layers, type GUIDs, and a predicted GridMate→Javelin class mapping). This is our Ghidra hunt map.

**Secondary reference (demoted): `docs/aznetworking-reference.md`** — originally produced as our protocol map, but the static scan proved Javelin is NOT AzNetworking-derived. Retained only as a *conceptual comparison* document showing how Amazon later re-imagined the same problem for O3DE. Do not use it for wire-format predictions.

**What the static scan revealed:**
- `Javelin::` appears 5001 times; namespace contains 730 unique class names (see `analysis/javelin_classes.txt`)
- `AzFramework` (152×) and `AzCore` (13×) confirm Amazon engine core still present
- OpenSSL (24×) + SSL_CTX (24×) confirm DTLS via statically-linked OpenSSL — matches GridMate's `SecureSocketDriver` using `DTLSv1_2_method()` + cipher `ECDHE-RSA-AES256-GCM-SHA384`

**What we still need:**
- [x] ~~Clone O3DE source and study AzNetworking packet header format~~ (done, but orthogonal)
- [x] Clone Lumberyard GridMate and produce protocol reference — done, see `docs/gridmate-reference.md`
- [ ] Ghidra auto-analysis (in progress — 1-4 hours)
- [ ] Enable GhidraMCP plugin after analysis completes
- [ ] Find cipher string `ECDHE-RSA-AES256-GCM-SHA384` xref → roots the whole network stack (§9.1 of GridMate ref)
- [ ] Find `ReadMessageHeader` equivalent (bit-mask fingerprint `flags & 0x42 == 0`, reads u16 size)
- [ ] Find `Cmd_*` switch at the top of replica dispatch (§5.4 of GridMate ref)
- [ ] Harvest Javelin chunk-name strings from `.rdata` — each maps to one replicated component
- [ ] Cross-reference with our 38,845 captured DTLS records

### Gate 4: Stub a Minimal Server
**Status: Not started**

**What we'll need to build:**
- Mock auth server (intercept via hosts file redirect)
  - Serve the channel config JSON
  - Accept OmniSDK CreateSession (or bypass it)
  - Return fake AWS credentials the client will accept
  - Serve remote config S3 responses (world config, gameplay config)
- Mock REP game server
  - Accept TCP connection on a port
  - Handle registration handshake
  - Send "actor game connection" success
  - Send spawn point + player spawn packets
  - Send minimal world state so the client renders without crashing

---

## Key Discoveries

Things that differ from the initial Perplexity research or are otherwise surprising:

0. **"Javelin" is a GridMate fork, not AzNetworking.** The retail binary contains zero AzNetworking/Multiplayer-gem markers (0/101 on static scan) but 5001 `Javelin::` class hits and 30 `"GridMate"` string hits. Javelin is almost certainly Amazon's rebranded/forked Lumberyard GridMate — a pre-O3DE networking library from ~2017. See `docs/gridmate-reference.md` for the full protocol map we expect to match in the binary. Key differences vs AzNetworking: tiny 2-byte datagram header, per-message flags byte, out-of-band ack vector, DTLS runs sequentially before Carrier handshake (not interleaved), and bit-packed bools on the wire.

1. **Not WebSocket, not TCP — it's DTLS over UDP.** The Perplexity research said WebSocket. First log analysis suggested TCP. Packet capture proves it's **DTLS 1.2 (encrypted UDP)**. The game log misleadingly says "REP socket connection" but the transport is UDP.

2. **Mutual TLS authentication.** The DTLS handshake includes a Certificate Request from the server, meaning the client likely sends a client certificate too. This is a stronger auth model than just server-side TLS.

3. **Self-signed Amazon certificate.** The server cert is `CN=New World, OU=Amazon Game Studios`, self-signed (not from a public CA). Valid 2025-08-04 to 2027-01-06. Our stub server will need to present a cert the client trusts — likely need to patch the client's cert validation or use the same cert.

4. **OmniSDK, not simple REST.** Auth goes through Amazon's OmniSDK 1.6: Steam ticket → persona ID → AWS credentials. Not a straightforward POST.

5. **Dynamic REP port.** Game server port changes every session (25493, 23971, 58068). Assigned by login queue. Our stub can use any port.

6. **Two auth sessions per login.** Client authenticates twice — once for the gameplay region (us-west-2) and once for us-east-1. Unclear why.

7. **S3-based remote config.** World config pulled from S3 via gateway, versioned per world ID and build number.

8. **SSLKEYLOGFILE doesn't work.** Game doesn't honor this env var. Frida hooks needed for TLS/DTLS decryption.

9. **The game logs everything.** Auth endpoints, tickets, persona IDs, server IPs, state transitions — all in plaintext in `Game.log`.

10. **All external services identified from TLS SNI.** Full list of hostnames the client contacts: Amazon auth, CloudFront gateways, S3 config, Vivox voice, EAC anti-cheat, Steam API, Kinesis telemetry, Datadog logging, Epic (EAC), and more.

---

## Infrastructure & Tools

### Installed
- Python 3.13 — capture scripts and stub server
- Node.js — available if needed
- tshark / Wireshark 4.6.4 — packet capture and analysis
- mitmproxy 12.2.2 — HTTPS interception proxy
- frida-tools 14.8.1 — runtime hooking (blocked by EAC; kept for auth-flow work)
- pydivert / WinDivert — kernel-level UDP packet tap (working)
- python3-dtls 1.3.0 — DTLS server for future stub
- **Eclipse Temurin JDK 21** (at `C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot\`) — required by Ghidra
- **Ghidra 11.3** (at `C:\Tools\ghidra\ghidra_11.3_PUBLIC\`) — static analysis; launch via `tools/launch_ghidra.bat`
- **GhidraMCP 1.4** — plugin lets Claude Code query Ghidra over MCP; registered in `.mcp.json`. Bridge script at `C:\Tools\ghidra_scripts\GhidraMCP-release-1-4\bridge_mcp_ghidra.py`

### Archived
| What | Where | Size |
|------|-------|------|
| Game client | `<archive-root>\GameClient\` | 72 GB |
| Game logs & crash DB | `<archive-root>\AppData_Local\` | 199 MB |
| Save data & settings | `<archive-root>\AppData_Roaming\` | 121 MB |
| Live install | `<steam-library>\steamapps\common\New World\` | 72 GB |

### Source references (sparse clones)
| Repo | Where | Purpose |
|------|-------|---------|
| O3DE (AzNetworking + Multiplayer gem + RTTI) | `C:\Users\<username>\Programs\o3de\` | Conceptual comparison doc only (not a wire-format match) |
| Lumberyard (GridMate) | `C:\Users\<username>\Programs\lumberyard\` | **Primary protocol reference** — Javelin is a GridMate fork |

### Capture Sessions
| Date | Directory | Notes |
|------|-----------|-------|
| 2026-04-16 | `capture/20260416_221806_first_capture/` | 60MB pcap (HTTPS only, missed REP stream). Full game log captured. |
| 2026-04-16 | `capture/20260416_222545_second_capture/` | 7.5MB pcap — **has DTLS handshake + game traffic to 52.223.16.88:58068**. Server cert extracted. |
| 2026-04-16 | `capture/20260416_231434_tap_test/` | **38,845 packets (7.1MB)** via WinDivert tap. Full DTLS session with gameplay. 90.6% ApplicationData, 8.6% Handshake. |

### Analysis artifacts (`analysis/`)
| File | Contents |
|------|----------|
| `javelin_classes.txt` | All 730 `Javelin::*` class names in the binary |
| `javelin_chunks.txt` | 10+ components with visible Facet/Messages strings (Guilds, PlayerTutorials, Warboard, Inventories, HouseData, etc.) |
| `chunk_names.txt` | 17 `*Chunk` type strings (3 networking: `TransformReplicaChunk`, `ScriptComponentReplicaChunk`, `NetBindingComponentChunk`; rest CryEngine terrain) |
| `ghidra_hunt_list.md` | Consolidated anchor VAs + bit-pattern fingerprints for post-analysis Ghidra work |
| `ghidra_project/` | Ghidra project database (gitignored) |

### Ghidra scripts (`tools/ghidra_scripts/`)
| File | Purpose |
|------|---------|
| `JavelinHunt.py` | Jython script. Resolves all Tier-1 string anchors, collects xrefs, scans `.text` for `AND/TEST 0x42` (ReadMessageHeader fingerprint), dumps findings JSON. Run from Script Manager once auto-analysis finishes. |

---

## Connection State Machine

Documented from game logs. This is the exact sequence our stub server must replicate:

```
Disconnected
  → QueryGameUpdateCheck
  → QueueGameLogin
  → WaitingForQueuedLogin          ← client waits for login ticket
  → QueryForRemoteConfigClass      ← 4 sequential S3 config fetches
  → WaitingForRemoteConfigClass
  → (repeat above 3 more times)
  → ObtainREPRequirements
  → StartREPConnection             ← TCP connect to game server IP:port
  → WaitingForREPConnection        ← TCP handshake + registration
  → WaitingForActorGameConnection  ← game-level handshake
  → WaitingForSpawnPoint           ← server sends spawn coordinates
  → WaitingForPlayerSpawn          ← level loads (e.g., NewWorld_VitaeEterna)
  → InGame                         ← success
```

---

## Next Steps (Priority Order)

1. **Wait for Ghidra auto-analysis** to complete (1-4 hours, in progress).
2. **Enable GhidraMCP plugin** (`File > Configure > Miscellaneous`), restart Ghidra — MCP server auto-starts on `http://127.0.0.1:8080/`.
3. **Run `JavelinHunt.py`** from Script Manager. It produces `analysis/ghidra_findings.txt` with all anchor xrefs and the `ReadMessageHeader` candidates.
4. **Walk the vtable from the cipher-string xref** to map `SecureSocketDriver` equivalent → every DTLS connection-state function.
5. **Harvest chunk names** by xref'ing `TransformReplicaChunk` at VA `0x1484ee539` to its `RegisterChunkType` call site, then enumerate sibling callers — each registers one chunk.
6. **Map Carrier receive path** from `GridMate-Carrier Packet Send Thread` string xref → thread function → message dispatch loop.

### Once we have a chunk/opcode catalog
7. **Write a GridMate protocol parser** (Python) using `docs/gridmate-reference.md` as spec. Test against our 38,845 captured packets' handshake portion (plaintext DTLS). ApplicationData packets remain encrypted until we extract session keys.
8. **Stub server design.** Start with DTLS handshake + Carrier `SM_CONNECT_REQUEST`/`SM_CONNECT_ACK`. Build up to NewProxy/Update for minimum viable world render.
4. **Build a Frida script** to hook TLS and capture decrypted auth HTTP bodies (still pending).
5. **Fetch the channel config JSON** directly (`https://d2c74t4zimux3r.cloudfront.net/STEAM_APP_ID.1063730.json`) — public, documents all regional endpoints.
6. **Decrypt the DTLS captures** (Frida hook on `SSL_read`/`SSL_write` in NewWorld.exe) and validate GridMate wire format assumptions against plaintext.
