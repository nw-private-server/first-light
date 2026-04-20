# New World Private Server — Progress & Findings

> Living document. Updated as we learn more.
> Last updated: 2026-04-20 (live Steam path reaches REP/DTLS but is blocked by certificate trust and EAC. Current highest-value work is offline DTLS/Javelin decoding from captures, not more live patch attempts.)

---

## Goal

Build a private server emulator that can accept the New World client, pass auth, and render a static world without crashing. No combat, NPCs, or persistence required for MVP.

---

## Roadmap

### Gate 1: Intercept the Auth Flow
**Status: COMPLETE (2026-04-18).** Auth mock carries the game from Steam login through OmniSDK session, credentials, entitlements, character-select render, Create Character UI flow (archetype / appearance / name), and finally the character-submit POSTs. The game fails at the next step — attempting a REP/DTLS connection to the fake game server — which is gate 2. All HTTP/JSON endpoints required for character creation are mocked and schema-correct.

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
- [x] ~~Capture the actual HTTP request/response bodies for `/prod/credentials/omni`~~ — hosts-file redirect + local HTTPS mock (`server/auth_mock.py`) intercepts all calls. SSLKEYLOGFILE / Frida not needed for this layer.
- [x] ~~Understand the OmniSDK `CreateSession` call~~ — POST `tokenservice.amazongames.com/games/new-world/tokens` returns `accessToken/fallbackToken/limitedUseToken/platformAccount/account`. Game confirms `CreateSession complete with result: 0`.
- [x] ~~Figure out the real `/prod/credentials/omni` response schema.~~ **Solved 2026-04-18.** Parser `FUN_145a955e0` (SteamAuth HTTP response handler) reads four **flat** top-level fields: `accessKeyId`, `secretAccessKey`, `sessionToken`, `expiration`. No wrapper. Our earlier `gatewayCredentials`/`personaCredentials` guess was invented. Fix shipped in `server/auth_mock.py::handle_credentials_omni`.
- [x] ~~Figure out `GetLoginInfoLists` response schema~~ (served at `/prod/game/getlogininfo/jwt/omni`). **Solved 2026-04-18** via a giant RPC schema table dump from `FUN_144f40780` plus a new PE-reader helper (`tools/resolve_strings.py`). Wrapper types: `RegionMetadata`, `WorldMetrics`, `WorldMetadata`, `FilterParam`, `WorldFilter`, `RecommendedWorld`, `WorldsInfo`, `CharacterMetadata`. WorldsInfo (the top-level response) has just `worlds` + `recommendedWorlds` — NOT the inherited entity fields (`personaId`, `region`, `channel`, `creationDate`, `modifiedDate`) which belong to CharacterMetadata's base class. See `tools/resolve_strings.py` output and `server/auth_mock.py::handle_get_login_info`.
- [ ] Determine if the returned AWS credentials use standard SigV4 or a custom signing scheme
- [ ] Understand what the channel config JSON contains (fetch it directly before shutdown)

### Gate 2: Capture the Game Server Protocol
**Status: ~80% complete**

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
- As of **2026-04-20**, our mock drives the client all the way through:
  - `/prod/game/getlogininfo/jwt/omni`
  - character-select render
  - `validator`
  - `CreateCharacter`
  - `/prod/game/login/queue/v2`
  - queue-ticket acceptance
  - remote-config fetch for the chosen world
  - `StartREPConnection`
  - **actual DTLS ClientHello / HelloVerifyRequest / ServerHello / Certificate / ServerKeyExchange / ServerHelloDone**
- The current failure is **not** queue polling anymore. The client now fails in `WaitingForREPConnection` with:
  - `ClientSDK: @mm_csdkerr_transport_security_error (2)`
  - OpenSSL probe shows the client sends a fatal alert:
    - `unknown ca`
  - Therefore the blocker is now **certificate trust / DTLS auth**, not ticket format.
- 2026-04-20 follow-up RE: `FUN_145dce750` (`Javelin_SecureSocketDriver_Initialize`) has two DTLS trust modes:
  - if the CA-bundle slot is null, it calls `SSL_CTX_set_verify(..., FUN_1402a1a70)` and `FUN_1402a1a70` simply returns `1` (accept any cert)
  - if the CA-bundle slot is non-null, it builds a CA list and calls `SSL_CTX_set_verify(..., 0)` (normal OpenSSL validation)
- 2026-04-20 follow-up RE: the gridmate-udp transport constructor carries an embedded PEM for the real self-signed `CN=New World` cert, strongly suggesting the client has bundled/pinned REP trust material.
- 2026-04-20 practical next step: runtime-only trust bypass, not more queue/auth JSON work. See `docs/dtls-trust-bypass.md` and `tools/frida_dtls_trust_patch.py`.
- 2026-04-20 follow-up: Frida attach against the live Steam process fails with `VirtualAllocEx returned 0x00000005`, so the next runtime path is an in-process proxy DLL rather than remote injection. Scaffold added under `tools/d3d11_proxy/`.
- 2026-04-20 follow-up: EAC rejects the proxy DLL too (`Untrusted system file ... Bin64\\d3d11.dll`). Combined with the earlier EXE patch rejection and Frida `ACCESS_DENIED`, the live Steam path is currently hostile to all straightforward local runtime patching.
- 2026-04-20 offline pivot: `tools/analyze_tap_capture.py` confirms the only non-empty tap session currently in repo (`capture/20260416_231434_tap_test/packets.jsonl`) contains only DTLS records, not plaintext pre-DTLS Javelin datagrams.
- 2026-04-20 offline pivot: `tools/extract_dtls_handshake.py` extracts handshake-level details from the tap capture. Current confirmed client offer:
  - DTLS version `0xfefd`
  - cipher suites: `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384` + `TLS_EMPTY_RENEGOTIATION_INFO_SCSV`
  - repeated retransmitted `ClientHello` with the same random and no cookie until `HelloVerifyRequest`
- 2026-04-20 tooling note: the offline DTLS analyzers are now reusable both as standalone scripts and importable helpers for follow-on parsing scripts.
- 2026-04-20 extractor improvement: `tools/extract_dtls_handshake.py --unique` now collapses retransmits into a clean handshake timeline. On the current tap capture, the unique timeline only reaches:
  - initial cookie-less `ClientHello`
  - cookie-bearing `ClientHello`
  - `HelloVerifyRequest`
  This capture does **not** include a clean post-cookie `ServerHello` / certificate flight, so it is only useful for the DTLS cookie-exchange baseline.
- 2026-04-20 offline breakthrough: `tools/analyze_pcapng_dtls.py` can now inspect the two stored `pcapng` captures without Wireshark/tshark. Both real captures (`20260416_221806_first_capture`, `20260416_222545_second_capture`) contain the **full DTLS server flight**:
  - `HelloVerifyRequest`
  - `ServerHello`
  - `Certificate`
  - `CertificateRequest`
  - `ServerKeyExchange`
  - `ServerHelloDone`
  - client `Certificate` / `ClientKeyExchange`
  - `ChangeCipherSpec`
  - large volumes of DTLS `application_data`
- 2026-04-20 offline implication: the in-repo `pcapng` files are now the primary artifact for post-handshake DTLS/Javelin work; the tap session is only needed for the packet-per-file UDP baseline.
- 2026-04-20 offline extractor: `tools/extract_pcapng_dtls_handshake.py` now reconstructs a real AWS-side DTLS handshake timeline from `pcapng`. The second capture cleanly shows:
  - client cookie-less `ClientHello`
  - server `HelloVerifyRequest`
  - client cookie-bearing `ClientHello`
  - server `ServerHello`
  - server `Certificate`
  - fragmented server `ServerKeyExchange`
  - server `CertificateRequest`
  - server `ServerHelloDone`
  - client `Certificate`
  - client `ClientKeyExchange`
  After that point, encrypted/fragmented records need deeper handling to distinguish Finished/application-data boundaries cleanly.
- 2026-04-20 offline extractor: `tools/extract_pcapng_dtls_timeline.py` now makes the post-handshake transition explicit. On the second capture:
  - client `ChangeCipherSpec` at epoch 0 / seq 3
  - client encrypted handshake record at epoch 1 / seq 0 (the client's Finished)
  - server `ChangeCipherSpec` at epoch 0 / seq 7
  - server encrypted handshake record at epoch 1 / seq 0 (the server's Finished)
  - then both sides switch to DTLS `application_data`
  - first server application-data record: epoch 1 / seq 1 / len 48
  This gives us an exact offline boundary between TLS handshake completion and opaque Javelin traffic.
- 2026-04-20 offline correlation: `tools/correlate_rep_timeline.py` now lines up the real DTLS milestones with `game_log_after.log` for the second capture. Current measured offsets:
  - first client `ClientHello`: `06:27:01.928644`
  - first server `ServerHello`: `06:27:02.193697`
  - client CCS: `06:27:02.195908`
  - first client application-data: `06:27:02.283648`
  - server CCS: `06:27:02.283475`
  - first server application-data: `06:27:02.403124`
  - `GameConnectionWrapper: REP socket connection established`: `06:27:02.404`
  - `received registration response from REP`: `06:27:02.577`
  This is the best offline anchor we currently have for "which encrypted application-data burst corresponds to REP registration".
- 2026-04-20 offline burst analysis: `tools/extract_registration_window.py` now isolates the earliest epoch-1 application-data exchange around REP registration. In the second real capture:
  - first server application-data record: seq `1`, len `48`, at `06:27:02.403124`
  - second server record: seq `2`, len `42`, at `06:27:02.504204`
  - third server record: seq `3`, len `139`, at `06:27:02.576602` — essentially coincident with the logged `received registration response from REP` at `06:27:02.577`
  - immediately after that, the server emits a dense burst at the same timestamp (`06:27:02.720833`) with lengths `41, 206, 164, 221, 261, 295, 250`
  - client-side epoch-1 traffic mirrors this: small records first, then a larger burst (`1141, 718, 480`) before the logged REP registration response, then steady smaller records
  This is now our best offline candidate window for the encrypted REP registration/actor-connection bootstrap payloads.
- 2026-04-20 cross-session comparison: the first and second real captures show the **same** early server registration-window lengths:
  - server seq `1..5` = `48, 42, 139, 63, 179`
  - then the same dense server burst = `41, 206, 164, 221, 261, 295, 250`
  - client early burst is also stable modulo tiny variance: `40, ~1140, ~720, ~480, 52, 75, 42...`
  This strongly suggests these are fixed protocol messages, not incidental transport fragmentation. It makes server seq `3` (`len 139`) the strongest candidate for the encrypted REP registration response payload.
- 2026-04-20 repository audit: there are no stored `sslkeys.log`, `CLIENT_RANDOM`, or other keylog/decrypted traffic artifacts in the repo. The old Frida/OpenSSL hook attempt (`capture/20260416_224201_dtls_test`) failed immediately because `SSL_read` was not found, so there is no forgotten decrypted capture to salvage.

**What we captured:**
- 60MB pcap from first session (HTTPS only, missed REP due to port filter)
- 7.5MB pcap from second session — **includes full DTLS handshake + encrypted game traffic**
- Full DTLS server certificate extracted and decoded
- Complete list of TLS SNI hostnames the client connects to (see connection-flow.md)

**What we still need:**
- [x] ~~Capture the REP stream~~ — done (second capture, DTLS over UDP)
- [x] ~~Determine if REP is encrypted~~ — yes, DTLS 1.2
- [x] ~~Drive the live client to our local REP/DTLS endpoint~~ — done (2026-04-20)
- [ ] Decrypt DTLS traffic — Frida hook on SSL_read/SSL_write, or extract session keys
- [ ] Determine if client sends a client certificate (Certificate Request seen in handshake)
- [ ] Make the client trust our DTLS endpoint (or patch/bypass trust validation) so the handshake completes past certificate verification
- [ ] Capture longer sessions with varied activities (combat, inventory, travel between zones)
- [ ] Understand the relationship between the HTTPS gateway traffic and the DTLS game traffic
- [x] Confirm the 2026-04-16 tap capture is all DTLS records (no plaintext pre-DTLS Javelin datagrams available there)

### Gate 3: Decode the Packet Format
**Status: ~55% — Javelin message framing layer fully decoded and implemented in Python**

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
- [x] ~~Clone O3DE source and study AzNetworking packet header format~~
- [x] Clone Lumberyard GridMate and produce protocol reference — `docs/gridmate-reference.md`
- [x] Ghidra auto-analysis
- [x] GhidraMCP live server
- [x] SecureSocketDriver::Initialize fully mapped (all 7 OpenSSL wrappers, state struct offsets)
- [x] Session → CarrierImpl → Carrier → ReplicaManager hierarchy
- [x] Pump functions defined and decompiled (`Javelin_CarrierThread_ThreadPump` @ `0x140f82340`)
- [x] **Complete DTLS state machine enumerated** (`Javelin_SecureSocketDriver_StateDispatch` @ `0x145dce4c0` — all 12 states with handler addresses)
- [x] `Javelin_CarrierThread_ReceiveLoop` @ `0x140f898e0` — ingress path + DTLS decrypt vtable offset (0x30)
- [x] `Javelin_CarrierThread_SendLoop` @ `0x140f8ab70` — egress path + DTLS encrypt vtable offset (0x28)
- [x] **`Javelin_Carrier_ParseMessages` @ `0x140f77eb0` — ReadMessageHeader fully decoded**
- [x] **`Javelin_Carrier_WriteMessages` @ `0x140f65b20` — WriteMessageHeader fully decoded**
- [x] `Javelin_BitStream_ReadBits` @ `0x140f7c420` — bit-level stream primitive
- [x] `Javelin_Carrier_HandleAckVector` / `BuildAckVector` — SM_CT_ACKS handler + builder
- [x] **KEY DISCOVERY: Javelin uses bit-streams, not byte streams** — all fields read/written via `ReadBits(n_bits)`. That's why the `0x42` byte-aligned scan failed.
- [x] **Working Python parser + marshaler** in `server/javelin/` — 14/14 round-trip tests passing
- [ ] Decompile DTLS state-handler functions (CS_CONNECT, CS_COOKIE_EXCHANGE, CS_SSL_HANDSHAKE_CONNECT, CS_ESTABLISHED) — tells the stub server how to drive the client through DTLS negotiation
- [ ] Parse the pre-DTLS `MF_CONNECTING` handshake packets from our captures (first few packets before DTLS is established are plaintext)
- [ ] Harvest full chunk catalog (auto-define strings first, then re-run FindChunkRegistrations.py)
- [ ] Find `Cmd_*` switch at the top of replica dispatch (§5.4 of GridMate ref) — gives per-chunk payload decoding

### Gate 4: Stub a Minimal Server
**Status: Auth mock partially operational — blocked on `/credentials/omni` response schema.**

**What we'll need to build:**
- Mock auth server (intercept via hosts file redirect) — **`server/auth_mock.py` exists; multi-host HTTPS listener with routing table**
  - [x] Serve the channel config JSON (`d2c74t4zimux3r.cloudfront.net/STEAM_APP_ID.1063730.json`) — game parses all 5 regional stacks successfully
  - [x] Accept OmniSDK `CreateSession` (`tokenservice.amazongames.com/games/new-world/tokens`) — game logs `result: 0`
  - [~] Return fake AWS credentials the client will accept — game fetches `/prod/credentials/omni`, consumes 200 response, then **silent CTD**. Wrapper field names wrong (see Gate 1).
  - [ ] Serve remote config S3 responses (world config, gameplay config)
- Mock REP game server
  - Accept TCP connection on a port
  - Handle registration handshake
  - Send "actor game connection" success
  - Send spawn point + player spawn packets
  - Send minimal world state so the client renders without crashing

---

## Key Discoveries

Things that differ from the initial Perplexity research or are otherwise surprising:

-1. **OmniSDK auth is SOLVED (2026-04-17).** `tokenservice.amazongames.com/games/new-world/tokens` returns `accessToken/fallbackToken/limitedUseToken/expiresIn/platformAccount/account`. Dropping null `suspension`/`conflictingAccount` keys was the last fix (game was tripping `0xCB` on nulls). Game logs `Omni CreateSession complete with result: 0` and advances to the credentials stage.

-2. **`/credentials/omni` schema is SOLVED (2026-04-18).** Parser `FUN_145a955e0` reads four flat top-level fields: `accessKeyId`, `secretAccessKey`, `sessionToken`, `expiration`. No wrapper. Yesterday's `gatewayCredentials`/`personaCredentials` guess was invented. With this fix the game progresses past the post-auth hang.

-3. **`GetLoginInfoLists` / `WorldsInfo` schema is SOLVED (2026-04-18).** Full RPC schema extracted from `FUN_144f40780` (the giant schema registration table in NewWorld.exe). Wrapper types: `RegionMetadata`, `WorldMetrics`, `WorldMetadata`, `FilterParam`, `WorldFilter`, `RecommendedWorld`, `WorldsInfo`, `CharacterMetadata`. Outer response (`WorldsInfo`) has just `worlds` + `recommendedWorlds`. `WorldMetadata` fields: `worldId, type, status, publicStatusCode, publicName, version, maxAccountCharacters, worldSet, worldMetrics{worldAgeDays,queueSize,queueWaitTimeSec,worldPopulationStatus}, transferToRegion, isFull, isRecommended`. Enum fields (`type`, `status`, `publicStatusCode`, `worldPopulationStatus`) are wire-format int32. `CharacterMetadata` inherits a base class with `name, personaId, worldId, region, channel, creationDate, modifiedDate` plus its own 21 fields — **these are NOT WorldsInfo top-level fields**; a bad guess putting them at response root caused a delayed CTD on the character-select render.

-4. **PE string resolver — `tools/resolve_strings.py`.** Given a list of virtual addresses (from Ghidra disassembly), maps each to a PE file offset using the section table and dumps the null-terminated string. Bypasses the ghidraMCP 5s timeout on `list_strings` for dozens of addresses at once. This is how we enumerated all 40+ GetLoginInfoLists field names in one pass. Reusable for any future schema extraction.

-5. **Game reaches Select Character screen (2026-04-18).** With a minimal 1-world payload (int enums = 0, no inherited base fields), the client renders the screen and even allows region switching. But: "Character Limit per Region = 0", no Create Character button. Those are gated by the entitlement response shape — our `{}` stub is stable on initial load but causes a CTD on region switch after the post-switch `POST /entitlements/sync`. Real entitlement schema needs extracting before we can hand back a non-`{}` response without crashing.

-7. **Complete HTTP character-creation flow (2026-04-18).** End-to-end path the user traversed through the UI:
    - Character-select loads (0/4 slots, 4 Create widgets)
    - Click Create Character → Standard world type picker
    - Intro cinematic (skippable)
    - Appearance + archetype + name input
    - Name check (any name accepted; we don't validate)
    - Region confirmation dialog → OK
    - Game POSTs `/prod/game/worlds/{worldId}/characters/validator/jwt/omni` with `{"ValidateCharacterBody":{"Name":"..."}}` (40B)
    - Game POSTs `/prod/game/worlds/{worldId}/characters/jwt/omni` with `{"CreateCharacterRequest":{"CharacterCreationParams":"<base64 zlib protobuf>"}}` (1.7KB)
    - Game then tries to REP-connect to the address we handed back in the login ticket (127.0.0.1:23971) — fails, "Connection Failed: Login malfunction" dialog. That's gate 2.
    - Key unlock for this whole flow was wrapping the getlogininfo response body in `{"LoginInfoList": {"Worlds": [...], "Characters": [...]}}`. The parser literally checks for that top-level envelope; without it the embedded parse block is zeroed and the downstream candidate vector never populates, leaving "No active worlds in your region."
    - 2026-04-19 follow-up: the auth mock is now stateful. `Ctx` persists `persona_id`, `world_id/world_name`, and created `Characters[]` entries so create -> reload flows stop contradicting themselves.
    - 2026-04-19 follow-up: `handle_login_queue()` now returns a ticket for the same world id handed out in `getlogininfo`, instead of an unrelated fallback world.
    - 2026-04-19 follow-up: persisted `Characters[]` entries were expanded toward the real PascalCase parser shape by adding the date / transfer / published / social placeholder fields the client expects.
    - 2026-04-20 follow-up: seeded-character mode plus the corrected queue/login envelopes now let the client consistently reach `/prod/game/login/queue/v2`, accept a login ticket, fetch world remote-config, and start the REP connection.
    - 2026-04-20 current end state: after `GameConnectionWrapper: start REP connection RepAddress = 127.0.0.1:23971`, the DTLS probe sees a real client handshake. The client rejects our local server certificate with fatal `unknown ca`, then surfaces `@mm_csdkerr_transport_security_error (2)` and returns to menu. Gate 2 is now a **DTLS certificate-trust** problem, not an auth-mock/queue-schema problem.
    - 2026-04-19 note: moving `C:\Users\<username>\AppData\Roaming\AGS\New World\savedata` aside to a timestamped backup removed one pre-`getlogininfo` failure mode where the game died before ever requesting character-select data.

-6. **Entitlement service schemas resolved via URL-first trace (2026-04-18).** Key pivot: instead of grepping for field-name strings, find the URL-builder function for the endpoint and follow the callback descriptor it passes to the shared HTTP helper.
    - `GET /players/{}/games/new-world/platforms/steam/entitlements`: URL builder is `FUN_1474caa10`, response parser is `FUN_1474c2420`. Shape is the generic paginated list wrapper `{hasMoreResults, lineItems[]}` — NOT `{entitlements, status}` as I guessed three times. Per-entry via `FUN_1474bde20` → `FUN_1474c4630`: `{acquisitionPersonaId, acquisitionType, amount (number), createdDate, productId, transactionId, type}`.
    - `POST /.../entitlements/sync`: URL builder is `FUN_1474d5100`, request writer is `FUN_1474d4d60` (writes `syncTypes` + optional `entitledPersonaId/event/platformSyncParameters`). **There is no response parser** — `FUN_1474d5100` inlines success/failure handling and reads zero JSON fields from the body. Our `{}` response is correct on this endpoint.
    - With real `/entitlements` shape shipped, the initial character-select load is stable for the first time. A region switch afterward still CTDs without logging anything — Game.log stops mid-`ConfigureLogin MODE_GATEWAY` for the new region, no Crashpad dump, no stack trace. Diagnostic dead end; next session try a different angle (click Create Character on initial region to see what endpoint it hits, or investigate whether the CTD is a DTLS auto-connect attempt to our missing REP server).

-7. **Create Character is a Javelin protobuf RPC, not an HTTP endpoint (2026-04-18).** Traced via Codex: RPC path `/Javelin.RPC.StubbedGatewayService/CreateCharacter` @ `0x1484bc4c8`, method name `CreateCharacter` @ `0x1483b74e0`, registered in the same `FUN_144f40780` schema table where `GetLoginInfoLists` lives. Request type `Javelin.RPC.CreateCharacterRequest = {world_id (string), character_creation_parameters: CharacterCreationParameters{name, +4 more fields likely appearance/gender/customization blob}}`. Response type `Javelin.RPC.CreateCharacterResult = {character_id (string)}` — failures surface via a separate `LoginError` callback, not rich result fields. Sibling `ValidateCharacter` RPC with request `{world_id, name}` probably precedes Create Character for name-availability preflight.
    - **Architectural implication:** Some RPCs (like `GetLoginInfoLists`) are exposed as JSON HTTP endpoints at `/prod/game/<method>/jwt/omni` — these we can mock with the existing HTTPS listener. Others (like `CreateCharacter`) appear to use the native Javelin RPC transport — either protobuf-over-HTTPS-POST on the gateway, or protobuf-over-DTLS on the REP port. Next session: find where `CreateCharacter` gets serialized and *which transport* it hits. If protobuf-over-HTTPS on the gateway, we add a new route to auth_mock.py that decodes the protobuf. If protobuf-over-DTLS, we need gate 2 (DTLS listener) operational before we can respond.

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
| `ghidra_findings.md` | Live findings from Ghidra-MCP sessions (DTLS stack, Session hierarchy, ReceiveLoop, SendLoop, ParseMessages/WriteMessages decompile notes, DTLS state machine) |
| `ghidra_findings.txt` | JSON output from JavelinHunt.py |
| `ghidra_chunks.txt` | Output from FindChunkRegistrations.py (empty — strings not defined as typed data) |
| `ghidra_project/` | Ghidra project database (gitignored) |

### Ghidra scripts (`tools/ghidra_scripts/`)
| File | Purpose |
|------|---------|
| `JavelinHunt.py` | Tier-1 anchor resolver. Resolves string anchors, collects xrefs, scans `.text` for 0x42 immediate (found: CryEngine false positives; ReadMessageHeader uses bit-stream reads instead). Outputs JSON. |
| `FindChunkRegistrations.py` | Walks defined strings ending in `*Chunk` and collects their xrefs. Needs `.rdata` auto-string-analysis run first. |

### Working protocol code (`server/javelin/`)
| File | Purpose |
|------|---------|
| `bitstream.py` | `BitStream` (read) + `BitStreamWriter` (write) — mirrors `Javelin_BitStream_ReadBits` @ `0x140f7c420` with aligned/unaligned bit paths. |
| `frame.py` | `MessageRecord`, `MessageFlags`, `SystemMessageId`, `parse_datagram()`, `marshal_datagram()` — inverses of `Javelin_Carrier_ParseMessages` / `Javelin_Carrier_WriteMessages`. |
| `test_parser.py` | 14 unit + round-trip tests, all passing. |

### Server mocks (`server/`)
| File | Purpose |
|------|---------|
| `auth_mock.py` | Multi-host HTTPS listener with routing table for channel service, tokenservice (OmniSDK), credentials/omni, login queue, S3 remote config, entitlements/catalog services. Reads `SNI` + `Host` header + path to dispatch. Logs every request to `capture/auth_mock_logs/YYYYMMDD.log`. Cert is in `server/certs/` (shared with hosts-file-redirected domains via self-signed CA). |

### Capture/diagnostic tools (`tools/`)
| File | Purpose |
|------|---------|
| `watch_connections.py` | Runs tshark with a tight filter (`SYN without ACK` + `DNS queries`) and prints/logs outbound TCP connection attempts + DNS lookups live. Used to confirm the game makes zero new network calls between `/credentials/omni` response and CTD — proving the crash is local (JSON parse) not network. Run in Admin PowerShell. |
| `resolve_strings.py` | Reads NewWorld.exe directly, parses the PE section table, and prints the null-terminated string at each of a list of virtual addresses. Built when ghidraMCP timed out on string-table scans — feed it VAs copied out of a large-function disassembly slice and it returns the field names verbatim. Used to extract the entire `GetLoginInfoLists` / WorldsInfo schema in one shot. |
| `analyze_tap_capture.py` | Summarizes a `packets.jsonl` tap capture: DTLS record counts, handshake message counts, alerts, and whether any non-DTLS datagrams exist. Used to prove the current repo capture set does not contain plaintext pre-DTLS Javelin traffic. |
| `extract_dtls_handshake.py` | Pulls a human-readable DTLS handshake transcript from `packets.jsonl` (ClientHello / HelloVerifyRequest / ServerHello details, cookies, cipher suites, retransmits). Used for offline DTLS/Javelin reverse-engineering now that live runtime patch paths are blocked by EAC. |
| `analyze_pcapng_dtls.py` | Dependency-free `pcapng` DTLS summarizer. Parses Ethernet/IPv4/UDP Enhanced Packet Blocks and reports DTLS content types, handshake message counts, endpoints, and sample payloads. Used to prove the stored Wireshark captures contain the full DTLS server flight and post-handshake application data. |
| `extract_pcapng_dtls_handshake.py` | Extracts a DTLS handshake timeline directly from `pcapng` captures, including the real AWS server flight (HelloVerifyRequest, ServerHello, Certificate, fragmented ServerKeyExchange, CertificateRequest, ServerHelloDone, then client Certificate/ClientKeyExchange). |
| `extract_pcapng_dtls_timeline.py` | Extracts record-level DTLS timelines from `pcapng` with content type, epoch, and sequence numbers. Used to mark the exact CCS → encrypted Finished → application-data transition on both client and server. |
| `correlate_rep_timeline.py` | Correlates `pcapng` DTLS milestones with `game_log_after.log` state transitions (StartREPConnection, REP established, registration response, actor connection, spawn). Used to anchor the first opaque application-data bursts to concrete game-side events. |
| `extract_registration_window.py` | Pulls the earliest epoch-1 server/client application-data burst around REP registration. Used to identify which encrypted records are the highest-value decryption target first. |
| `compare_registration_windows.py` | Compares the registration window across both real captures and surfaces which encrypted record sizes are stable session-to-session. |
| `assess_capture_routes.py` | Audits the repo's current DTLS/Javelin capture/decryption routes and ranks which ones are actually viable today. Used after EAC blocked the live trust-bypass paths so we can stop guessing and focus on realistic next steps. |

---

## 2026-04-20 Capture Route Audit

- Added `docs/capture-routes.md` and `tools/assess_capture_routes.py` so the current DTLS/Javelin capture options are documented as an explicit decision rather than more ad hoc experiments.
- Audit conclusion:
  - **best current route:** offline `pcapng` analysis of the existing real captures
  - **useful but metadata-only:** WinDivert / UDP probe transport capture
  - **blocked on the current live path:** SSLKEYLOGFILE, Frida/OpenSSL live hooks, and local DTLS MITM
- Evidence:
  - there are no non-empty `sslkeys.log`, `CLIENT_RANDOM`, or other keylog/decrypted artifacts anywhere under `capture/`
  - stored Frida hook attempt `capture/20260416_224201_dtls_test/hooks.log` failed immediately because `SSL_read` was not found
  - the live DTLS probe path reached a real handshake but aborted with fatal `unknown ca`
- Practical implication:
  - there is **no already-working non-EAC decryption route in the repo today**
  - the highest-value path is to keep narrowing the offline encrypted REP registration/bootstrap window while identifying a non-EAC source of session secrets or decrypted traffic

## 2026-04-20 Non-EAC Acquisition Plan

- Added `docs/non-eac-capture-plan.md` to turn the route audit into a concrete ordered acquisition plan.
- Updated the existing tools so they can actually target an archived or non-EAC-friendly client instead of assuming the live Steam install:
  - `tools/frida_capture.py` now supports `--process-name` in addition to `--exe`
  - `tools/capture_session.py` now uses `argparse` and supports `--name` and `--game-log`
- Ranked next attempts:
  1. Frida hook against archived/non-EAC-friendly binary
  2. SSLKEYLOGFILE capture against archived/non-EAC-friendly binary
  3. DTLS MITM only if trust can be solved on that non-EAC target
- Immediate focus once any route yields decrypted bytes:
  - use the already-isolated server REP registration window (`seq 1..3`, especially the stable `len 139` record) as the first decryption target

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

### Immediate (next session) — unblock character creation

1. **Extract the real entitlement-service schema.** Our `{}` stub for `GET /entitlements` and `POST /entitlements/sync` holds up on initial load but trips a CTD on region switch (right after the post-switch `POST /sync`). A guessed `BaseGame` entitlement caused a delayed CTD too. Route through Codex (ghidraMCP bridge handles wide string/xref work now):
   - Defined-strings search: `entitlements`, `entitlementId`, `productId`, `grantTime`, `syncType`, `syncResult`, `ownership`.
   - xref the camelCase `[READ]` hit that lives in a rapidjson-style reader (pattern: SSE load of field-name literal → call to `FindMember`/`HasMember`-style helper, same shape as the `/credentials/omni` parser `FUN_145a955e0`).
   - Decompile that reader. Enumerate top-level fields + per-entitlement-entry fields. Also find the `POST /sync` response reader — the body sent is `{"syncTypes":["FirstTimeLogin","PrimeGamingSync","CodeRedemptionSync","TwitchDropsSync","SteamRetailSync"]}`.
   - Update `handle_entitlements_list` + `handle_entitlements_sync` in `server/auth_mock.py`.
2. **Retry region switch** with the real schema. Expected: no CTD, per-region character cap actually non-zero, Create Character button stays visible.
3. **Follow the Create Character click.** Watch the auth-mock log for the new endpoint the game calls (probably `POST /prod/game/createcharacter` or similar). Extract the request/response schema the same way.
4. **Build the login-queue route** (`/prod/users/login_queue/*`) as the next blocker after character creation returns successfully.

### Protocol/DTLS work (parallel, as time allows)

4. **Find or produce a decryptable path** for post-handshake DTLS application data (session keys, SSL hooks on a non-EAC target, or alternative capture route). The repo contains no existing keylog/decrypted artifacts, so this likely requires a fresh non-EAC capture route or another source of session secrets.
5. **Use the registration window as the first decryption target** — server app-data seq `1..3`, especially the stable `len 139` record that aligns with the logged registration response.
6. **Harvest full chunk catalog** (auto-define strings first, then re-run FindChunkRegistrations.py).
7. **Find `Cmd_*` switch** at the top of replica dispatch — gives per-chunk payload decoding.
