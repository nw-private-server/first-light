# New World Private Server — Progress & Findings

> Living document. Updated as we learn more.
> Last updated: 2026-04-16

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
**Status: ~30% complete**

**Key correction:** The Perplexity research said WebSocket. It's actually **direct TCP** — the game calls it "REP" (Replication Protocol), which is O3DE/Lumberyard terminology.

**What we know:**
- Game server connection is plain TCP to an AWS Global Accelerator IP (`35.71.190.194`)
- Port is **dynamic** — observed `25493` (Dec 2025) and `23971` (Apr 2026)
- The server IP + port are provided in the login ticket response, not hardcoded
- Connection flow after TCP established: socket connect → register → registration response → actor game connection → spawn point → player spawn → in game
- Server identifies itself with a version string: `[RETAIL].Javelin.1.365.6031.6004151`
- Voice chat is separate (Vivox, SIP-based, `nwxp.vivox.com`)

**What we captured:**
- 60MB pcap from first session (mostly HTTPS on port 443 — TLS encrypted)
- The REP TCP stream was **missed** in first capture due to hardcoded port filter (now fixed)

**What we still need:**
- [ ] Capture the REP TCP stream (run updated capture script — filter is now `tcp` not port-specific)
- [ ] Determine if REP connection is encrypted (TLS) or plaintext
- [ ] If encrypted, use Frida to hook SSL_read/SSL_write and dump decrypted payloads
- [ ] Capture multiple sessions doing different activities (login, walk around, open inventory, etc.)

### Gate 3: Decode the Packet Format
**Status: Not started**

**What we know so far (from O3DE open source):**
- O3DE's AzNetworking uses a serialization format with AZ_RTTI-reflected types (each packet has a UUID)
- `NetworkInputSerializer` / `NetworkOutputSerializer` for byte stream serialization
- New World extended the base O3DE packet types with custom game packets
- Ghidra + the archived NewWorld.exe (72GB client archived to `<archive-root>\`) will be the primary RE tool

**What we still need:**
- [ ] Clone O3DE source and study AzNetworking packet header format
- [ ] Load NewWorld.exe into Ghidra, find IPacket subclasses and serialization methods
- [ ] Build opcode catalog: opcode → struct definition → game action
- [ ] Cross-reference captured REP traffic against discovered packet structures

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

1. **Not WebSocket — it's direct TCP.** The game server uses O3DE's REP (Replication Protocol) over plain TCP, not WebSocket framing. This is actually simpler to work with.

2. **OmniSDK, not simple REST.** Auth isn't a straightforward POST to a login endpoint. It goes through Amazon's OmniSDK 1.6, which handles the Steam ticket → persona ID → AWS credentials pipeline. The REST calls happen, but they're wrapped in OmniSDK.

3. **Dynamic REP port.** The game server port changes every session. It's assigned by the login queue system, not hardcoded. Our stub server can use any port.

4. **Two auth sessions per login.** The client authenticates twice — once for the gameplay region (e.g., us-west-2) and once for us-east-1. Unclear why yet.

5. **S3-based remote config.** World-specific configuration is pulled from S3 via the gateway, versioned per world ID and build number. We'll need to serve this from our stub.

6. **SSLKEYLOGFILE doesn't work.** The game doesn't use a TLS library that honors this env var. Frida hooks will be needed for HTTPS decryption.

7. **The game logs everything.** Even without verbose logging enabled, the game writes auth endpoints, tickets, persona IDs, server IPs, state transitions, and more to `Game.log`. This is our best source of protocol documentation.

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
