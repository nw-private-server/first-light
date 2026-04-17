# New World Private Server — Progress & Findings

> Living document. Updated as we learn more.
> Last updated: 2026-04-17 (static scan reveals bespoke "Javelin" networking)

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
**Status: ~15% — major pivot from static scan**

**Critical finding (2026-04-17):** New World does **NOT** use stock O3DE AzNetworking. Static scan of NewWorld.exe against the full list of AzNetworking class names, RTTI UUIDs, CVars, and log messages from O3DE source returned **0 hits out of 101 checks**. Instead, the binary uses a **bespoke networking library named "Javelin"** in the `Javelin::` namespace. This aligns with the server version string we captured earlier: `[RETAIL].Javelin.1.365.6031.6004151`.

**What the static scan revealed:**
- `Javelin::` appears 5001 times; namespace contains 730 unique class names (see `analysis/javelin_classes.txt`)
- `GridMate` references present (30×) — Lumberyard's older networking lib; Javelin is likely forked from or inspired by it, predating O3DE's AzNetworking
- `AzFramework` (152×) and `AzCore` (13×) confirm some Amazon engine core is still present
- No AzNetworking class names, CVars, log strings, or RTTI UUIDs — everything networking was replaced by Javelin
- OpenSSL (24×) and SSL_CTX (24×) confirm standard DTLS via statically-linked OpenSSL

**Javelin architecture (inferred from class names):**
- `*ComponentClientFacet` / `*ComponentServerFacet` — replicated state holders per component
- `*ComponentClientMessages` / `*ComponentServerMessages` — RPC message groups per component
- `HandleReplicatedState` — function that processes incoming replication updates
- `ReplicationDataManager` — central replication system
- `I*RemoteMessages` / `I*ClientMessages` — RPC interface groups (IPlayerRemoteMessages, etc.)
- Component-oriented architecture, similar to GridMate's Replica pattern but with bespoke naming

**What this means for our stub server:**
- The O3DE AzNetworking reference (`docs/aznetworking-reference.md`) is still useful as a *conceptual map* but won't map 1:1
- We're doing bottom-up reverse engineering from the binary — no known protocol spec to cross-reference
- Wire format (packet header layout, opcode scheme, serialization primitives) all TBD from Ghidra

**What we still need:**
- [x] ~~Clone O3DE source and study AzNetworking packet header format~~ (done, but less relevant than expected)
- [ ] Ghidra auto-analysis (in progress — 1-4 hours)
- [ ] Enable GhidraMCP plugin after analysis completes
- [ ] Find `Javelin::` packet/serializer/replication classes in Ghidra
- [ ] Reverse-engineer the Javelin UDP packet header layout
- [ ] Cross-reference with our 38,845 captured DTLS records
- [ ] Build opcode catalog from discovered packet structures

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

0. **"Javelin", not AzNetworking.** The retail binary contains zero AzNetworking/Multiplayer-gem markers (0/101 on static scan). New World has its own networking library called **Javelin** (730 unique `Javelin::*` classes), likely forked from Lumberyard's GridMate before O3DE open-sourced AzNetworking. All packet, replication, and RPC code is bespoke and must be reversed from the binary.

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
- Python 3.13 — for capture scripts and future stub server
- tshark (Wireshark 4.6.4) — packet capture and analysis
- mitmproxy 12.2.2 — HTTPS interception proxy
- frida-tools 14.8.1 — runtime hooking for TLS decryption
- Node.js — available if needed

### Archived
| What | Where | Size |
|------|-------|------|
| Game client | `<archive-root>\GameClient\` | 72 GB |
| Game logs & crash DB | `<archive-root>\AppData_Local\` | 199 MB |
| Save data & settings | `<archive-root>\AppData_Roaming\` | 121 MB |
| Live install | `<steam-library>\steamapps\common\New World\` | 72 GB |

### Capture Sessions
| Date | Directory | Notes |
|------|-----------|-------|
| 2026-04-16 | `capture/20260416_221806_first_capture/` | 60MB pcap (HTTPS only, missed REP stream). Full game log captured. |
| 2026-04-16 | `capture/20260416_222545_second_capture/` | 7.5MB pcap — **has DTLS handshake + game traffic to 52.223.16.88:58068**. Server cert extracted. |
| 2026-04-16 | `capture/20260416_231434_tap_test/` | **38,845 packets (7.1MB)** via WinDivert tap. Full DTLS session with gameplay. 90.6% ApplicationData, 8.6% Handshake. |

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

1. **Run a second capture** with the fixed filter to get the REP TCP stream
2. **Fetch the channel config JSON** directly (`https://d2c74t4zimux3r.cloudfront.net/STEAM_APP_ID.1063730.json`) — this is public and documents all endpoints
3. **Build a Frida script** to hook TLS and capture decrypted auth HTTP bodies
4. **Clone O3DE source** and study AzNetworking packet format
5. **Start Ghidra analysis** of NewWorld.exe for packet structures
