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

## 2026-04-20 Archived Frida Attempt

- Tried `tools/frida_capture.py --exe "<archive-root>\GameClient\Bin64\NewWorld.exe" --name archived_frida`
- Important result: Frida spawn/attach **worked** on the archived binary. This is materially better than the live EAC path, where attach failed with `VirtualAllocEx` `ACCESS_DENIED`.
- Immediate blocker on that archived run:
  - the client surfaced `Steam must be running to play this game`
  - so the archived target still needs proper Steam launch context before it can reach network activity
- Hook result from that run:
  - OpenSSL symbols were still not found (`SSL_read`, `SSL_write`, `_ex` variants)
  - the previous winsock fallback also failed because the script used a bad static `Module.findExportByName(...)` call in this runtime
- Follow-up change:
  - fixed `tools/frida_dtls_hook.js` winsock fallback to use proper `ws2_32.dll` export lookups and added `connect`, `sendto`, `recvfrom`, `send`, and `recv` logging
- Next archived-binary attempt should add Steam context first:
  - Steam running and logged in
  - `steam_appid.txt` containing `1063730` next to the archived `NewWorld.exe`

## 2026-04-20 Archived Frida Attempt #2

- Added `steam_appid.txt` containing `1063730` next to `<archive-root>\GameClient\Bin64\NewWorld.exe`
- Result:
  - the old `Steam must be running` blocker disappeared
  - the archived binary now gets farther, but exits with a generic `Unable to connect to New World: Aeternum servers` error
- The Frida capture from `capture/20260420_221749_archived_frida/` shows:
  - Frida spawn/attach still works
  - SSL hooks still do not resolve (`SSL_read`, `SSL_write`, `_ex` variants all `not_found`)
  - `packets.jsonl` is still empty
  - process terminates shortly after hook installation
- Interpretation:
  - this archived target is now viable enough to continue instrumenting
  - but the current hook was still too narrow to prove whether the binary reaches plain network APIs before failing
- Follow-up change:
  - widened `tools/frida_dtls_hook.js` again so it now:
    - records explicit `not_found` / `success` states for Winsock exports
    - hooks `connect`, `sendto`, `recvfrom`, `send`, `recv`
    - also hooks WinHTTP (`WinHttpConnect`, `WinHttpOpenRequest`, `WinHttpSendRequest`)
    - and WinINet (`InternetConnectW`, `HttpOpenRequestW`)
- Next value check:
  - rerun the archived Frida path and inspect whether the process reaches **any** plain network API before termination

## 2026-04-20 Archived Frida Attempt #3

- A later archived run regressed to the old Steam blocker. Investigation showed `<archive-root>\GameClient\Bin64\steam_appid.txt` was no longer present at run time.
- The session at `capture/20260420_222214_archived_frida/` confirms the archived process terminated even earlier than the previous run:
  - only `SSL_read` reached `not_found`
  - the process detached before the rest of the hook installation completed
- Practical implication:
  - the old hook order was still too slow for very early startup failures
- Follow-up changes:
  - restored `steam_appid.txt` with `1063730`
  - changed `tools/frida_dtls_hook.js` to install **Winsock / WinHTTP / WinINet hooks before** the slower SSL symbol scans
- Next archived rerun should now answer the right question:
  - does the archived binary touch any plain network API at all before it dies?

## 2026-04-20 Archived Frida Attempt #4 Prep

- The next archived run still reached the generic `Unable to connect to New World: Aeternum servers` error, but the Frida log showed every plain network hook as `not_found` immediately at startup:
  - Winsock (`connect`, `sendto`, `recvfrom`, `send`, `recv`)
  - WinHTTP (`WinHttpConnect`, `WinHttpOpenRequest`, `WinHttpSendRequest`)
  - WinINet (`InternetConnectW`, `HttpOpenRequestW`)
- Most likely cause:
  - those DLLs are simply not loaded yet when the script checks at process start, so the old one-shot lookup was racing process initialization
- Follow-up change:
  - `tools/frida_dtls_hook.js` now:
    - hooks `LoadLibraryA/W` and `LoadLibraryExA/W`
    - retries Winsock / WinHTTP / WinINet hook installation for 30 seconds after startup
    - keeps the early-hook ordering from the prior patch
- Expected value from the next run:
  - either we finally see plain network API activity before termination
  - or we prove this archived binary dies before loading the common Windows networking stacks at all

## 2026-04-20 Archived Frida Attempt #5 Prep

- Another archived rerun regressed to the old Steam blocker again.
- Root cause check:
  - `<archive-root>\GameClient\Bin64\steam_appid.txt` was missing again at run time
- Follow-up change:
  - `tools/frida_capture.py` now recreates `steam_appid.txt` with `1063730` automatically before every spawn attempt
- Practical implication:
  - future archived spawn tests no longer depend on the file surviving from a previous manual setup step

## 2026-04-20 Archived Frida Attempt #6 Prep

- Even with the self-healing `steam_appid.txt` path, the archived process still reaches only the generic `Unable to connect to New World: Aeternum servers` error.
- The latest Frida session still showed only startup-time `not_found` results and no packet or API activity before termination.
- Next highest-value move:
  - stop guessing which Windows networking exports this archived build should touch
  - inspect the archived binary's actual import table first
- Added `tools/list_pe_imports.py` for exactly that purpose so we can target the right API surface for the next hook iteration.

## 2026-04-20 Archived Import Audit

- Ran `tools/list_pe_imports.py` against `<archive-root>\GameClient\Bin64\NewWorld.exe`
- Important result: the archived binary really does import the Windows and Steam APIs we care about, but not necessarily the specific plain-socket names we first guessed.
- Relevant imports confirmed:
  - `steam_api64.dll`
    - `SteamAPI_Init`
    - `SteamInternal_ContextInit`
    - related Steam callback/context exports
  - `WINHTTP.dll`
    - `WinHttpOpen`
    - `WinHttpConnect`
    - `WinHttpOpenRequest`
    - `WinHttpSendRequest`
    - `WinHttpReceiveResponse`
    - `WinHttpReadData`
    - `WinHttpWriteData`
  - `WS2_32.dll`
    - `WSAConnect`
    - `WSASend`
    - `WSARecv`
    - `WSARecvFrom`
    - `GetAddrInfoW`
    - `getaddrinfo`
    - plus socket/event/ioctl support
- Follow-up change:
  - retargeted `tools/frida_dtls_hook.js` to hook the imported API surface that actually exists in this archived build:
    - Steam: `SteamAPI_Init`, `SteamInternal_ContextInit`
    - Winsock: `WSAConnect`, `WSASend`, `WSARecv`, `WSARecvFrom`, `GetAddrInfoW`, `getaddrinfo`
    - kept the older plain-socket and WinHTTP/WinINet probes as secondary coverage
- Expected value from the next archived rerun:
  - if this binary reaches real startup/network paths before failing, we should finally see concrete Steam or WSA/WinHTTP activity instead of a wall of `not_found`

## 2026-04-20 Archived Import-Hook Adjustment

- The next archived rerun still produced a wall of `not_found`, including for functions that the import-table audit had already proven are imported by `NewWorld.exe`.
- That strongly suggests the previous Frida strategy was still looking in the wrong place:
  - asking the runtime for DLL exports
  - instead of hooking the already-resolved import thunks in `NewWorld.exe`
- Follow-up change:
  - `tools/frida_dtls_hook.js` now first resolves candidate hook targets from the **main module import table** via `Module.enumerateImportsSync(getMainModule().name)`
  - only falls back to `Module.getExportByName(...)` if no imported function thunk is present
- Expected value:
  - the next archived rerun should tell us whether the process actually calls imported Steam / WSA / WinHTTP APIs before it dies, instead of failing at target discovery time

## 2026-04-20 Archived Import-Hook Result

- The import-thunk lookup rerun still produced `not_found` for all targeted Steam / WSA / WinHTTP hooks, even though the archived binary's on-disk import table proves those symbols exist.
- That rules out simple export-name mismatch as the main issue.
- Practical conclusion:
  - the next hook iteration needs to stop relying on Frida's high-level module/import lookup for this target
  - and instead resolve the main module's import table manually in memory, then hook the resulting thunk addresses directly
- Added `tools/import_table_probe.py` as a tiny host-side sanity check for the exact imported symbols we care about while preparing that next hook step.

## 2026-04-20 Archived Manual IAT Hook Prep

- Implemented a manual PE import-table walker inside `tools/frida_dtls_hook.js`
- New behavior:
  - `findImportedFunction(name)` now first walks the main module's PE headers in memory
  - resolves the import descriptor table
  - walks the thunk/IAT pairs
  - and returns the imported function thunk address directly
  - only after that does it fall back to Frida's `Module.enumerateImportsSync(...)`
- Why this matters:
  - the archived target has already proven that Frida's high-level import visibility is unreliable here
  - manual IAT resolution is the cleanest next escalation before abandoning this archived build

## 2026-04-20 Archived Manual IAT Bugfix

- The first run with the manual IAT path still failed before producing signal.
- The session log finally revealed why:
  - `manual import walk failed: TypeError: not a function`
- Root cause:
  - the first implementation relied on 64-bit helper methods (`shr`, `compare`, etc.) that are not available in this Frida runtime
- Fix:
  - rewrote the thunk walk to use plain 32-bit reads (`entryLow`, `entryHigh`) and an explicit high-bit ordinal check
- Expected result:
  - the next archived rerun should actually exercise the manual import-table resolution instead of failing inside the resolver itself

## 2026-04-20 Archived Manual IAT Result

- The next archived Frida run finally produced the first real hook breakthrough.
- Session: `capture/20260420_224946_archived_frida/`
- Hook install results:
  - `success`
    - `WSAConnect`
    - `WSASend`
    - `WSARecv`
    - `WSARecvFrom`
    - `GetAddrInfoW`
    - `getaddrinfo`
    - `WinHttpConnect`
    - `SteamAPI_Init`
    - `SteamInternal_ContextInit`
  - still `not_found`
    - plain `connect/send/recv/sendto/recvfrom`
    - WinINet (`InternetConnectW`, `HttpOpenRequestW`)
  - one Frida-specific issue remains:
    - `winhttp` secondary hook path errored with `unable to intercept function at 00007FF761CAA7F8`
- Important interpretation:
  - the manual IAT resolver is now working
  - the archived binary **does** expose the expected imported Steam / WSA / WinHTTP surface in-process
  - but there were still **no actual API call logs** before process termination
  - so the process appears to die before invoking those hooked networking functions or before the current log points on those functions are reached
- Practical conclusion:
  - this archived build is no longer blocked on hook discovery
  - the next value is not more target-discovery work, but capturing *earlier process behavior* (e.g. Steam init return, module load sequence, or startup failure path before network calls)

## 2026-04-20 Archived Startup/Termination Pivot

- Since the manual IAT path now yields real `success` hooks but still no actual network-call logs, the problem is no longer target discovery.
- New working hypothesis:
  - the archived process is dying before it reaches the current network log points
  - so the next useful instrumentation is startup/termination behavior rather than more network-surface expansion
- Follow-up change:
  - extended `tools/frida_dtls_hook.js` with:
    - process-lifecycle hooks:
      - `ExitProcess`
      - `TerminateProcess`
      - `RtlExitUserProcess`
      - `RaiseFailFastException`
      - `abort`
    - early UI hooks:
      - `CreateWindowExW`
      - `CreateWindowExA`
      - `ShowWindow`
      - `MessageBoxW`
- Goal of the next archived rerun:
  - determine whether the process creates UI and which exit path it takes before it dies

## 2026-04-20 Archived Startup/Termination Result

- Session: `capture/20260420_225722_archived_frida/`
- This run ended almost immediately after startup instrumentation finished:
  - process detached at `22:57:24.549`
  - roughly 1.5 seconds after the hook installation phase
- Hook install results improved again:
  - `success`
    - `WSAConnect`
    - `WSASend`
    - `WSARecv`
    - `WSARecvFrom`
    - `GetAddrInfoW`
    - `getaddrinfo`
    - `WinHttpConnect`
    - `SteamAPI_Init`
    - `SteamInternal_ContextInit`
    - `CreateWindowExW`
    - `CreateWindowExA`
    - `ShowWindow`
  - some secondary lifecycle/UI hooks still error when Frida tries to intercept the specific target address:
    - `process_lifecycle`
    - `user32_startup`
- Important result:
  - despite those hooks installing successfully, there were still **no actual `[steam]`, `[ws2]`, `[winhttp]`, `[ui]`, or `[proc]` event logs**
  - so the archived process is terminating before it reaches the current hooked call sites, not because hook discovery is still failing
- Practical implication:
  - the next highest-value path is likely outside the current Frida surface:
    - either hook an even earlier failure/reporting path
    - or stop treating this archived build as the best non-EAC candidate if it cannot even reach basic startup calls before dying

## 2026-04-20 Archived Import-Hook False Positive

- We found the reason the archived Frida runs were reporting import-hook `success` without any runtime events:
  - the manual import walker was returning the **IAT slot address**
  - not the **resolved function pointer stored in that slot**
- That means `Interceptor.attach(...)` was landing on import-table data cells instead of the actual target code.
- This explains the contradiction we saw:
  - the archived build visibly created UI and reached the generic connection-error dialog
  - but none of the supposedly successful `WSA*`, `WinHttp*`, `SteamAPI_*`, or `CreateWindowEx*` hooks ever logged a call
- `tools/frida_dtls_hook.js` now dereferences each IAT entry with `iat.readPointer()` and attaches to the resolved target address.
- Expected effect of the next archived rerun:
  - either we finally get real `[steam]`, `[ws2]`, `[winhttp]`, and/or `[ui]` runtime events
  - or we can rule out the imported-API surface with much higher confidence

## 2026-04-20 Archived Runtime Signal Breakthrough

- After fixing the imported-target hook path, the archived Frida run finally produced real runtime events.
- Confirmed startup sequence:
  - `SteamAPI_Init -> 1` early in startup
  - main game UI window created:
    - `CreateWindowExW class=GameWindowClass title=New World`
  - additional helper/UI windows appear later
  - `ShowWindow cmd=1`
- Confirmed network surface:
  - repeated WinHTTP requests to:
    - `d2c74t4zimux3r.cloudfront.net:443`
    - `GET /STEAM_APP_ID.1063730.json`
- The process still ends in the generic connection-error dialog, but this is no longer a black box.
- Practical implication:
  - the next highest-value instrumentation is **WinHTTP response/error status**
  - we need to know whether those CloudFront requests are succeeding, failing, or returning an unexpected payload/status before the game throws the generic dialog

## 2026-04-20 Archived HTTP Failure Shape

- The next archived Frida run showed the generic connection error still happens after startup, but with one more concrete signal:
  - the archived process eventually calls:
    - `TerminateProcess(handle=0xffffffffffffffff, code=0)`
  - so it is self-terminating cleanly after its startup HTTP path, not crashing via an obvious fail-fast or exception path
- Before self-termination, the visible startup/network sequence is:
  - `SteamAPI_Init -> 1`
  - main window creation (`GameWindowClass`, `New World`)
  - repeated `WinHttpConnect/OpenRequest/SendRequest`
    - host: `d2c74t4zimux3r.cloudfront.net:443`
    - path: `GET /STEAM_APP_ID.1063730.json`
- We still did **not** see:
  - `WinHttpReceiveResponse`
  - `WinHttpQueryHeaders`
  - `WinHttpReadData`
- Practical implication:
  - the next highest-value hook point is the **WinHTTP async status callback path**
  - the game is likely learning about request failure through `WinHttpSetStatusCallback` rather than the synchronous response/read APIs we were watching

## 2026-04-20 Archived Hosts Redirect Cause

- The archived Frida callback run clarified the startup failure:
  - the client repeatedly requests:
    - `https://d2c74t4zimux3r.cloudfront.net/STEAM_APP_ID.1063730.json`
  - our local machine currently resolves that hostname to `127.0.0.1`
  - because the global `hosts` file still contains the NewWorldPrivate auth-mock redirects
- Direct host-side verification:
  - `Resolve-DnsName d2c74t4zimux3r.cloudfront.net` returned `127.0.0.1`
  - direct `Invoke-WebRequest` to that URL from the host failed with:
    - `Unable to connect to the remote server`
- Practical implication:
  - the archived build is no longer failing because of Steam-only startup context
  - it is failing because it is being redirected into the local mock topology
  - therefore, standalone archived Frida runs **must either**:
    - run with `auth_mock` active
    - or temporarily remove/disable the hosts redirect block
- Highest-value next archived test:
  - leave Frida instrumentation as-is
  - start `auth_mock`
  - rerun the archived build so the redirected CloudFront/API traffic has a real local responder

## 2026-04-20 Archived Create-Flow CTD With auth_mock

- Running the archived build with both `auth_mock` and Frida active got much farther:
  - startup channel config succeeded
  - validator succeeded
  - `getlogininfo` refresh succeeded
  - CMS `motd/worlds_*.json` succeeded
- The archived run still CTD'd after name entry, but **before** any `CreateCharacter` request was sent.
- Frida + auth-mock correlation showed:
  - `POST /prod/game/worlds/.../characters/validator/jwt/omni` -> `200`
  - immediate `GET /prod/game/getlogininfo/jwt/omni` -> `200`
  - no subsequent `/characters/jwt/omni` create call before termination
- There are repeated side-channel `POST /` requests returning `400`, but those are to:
  - `sts.us-east-1.amazonaws.com`
  - `kinesis.us-west-2.amazonaws.com`
  and they occur alongside successful mainline gateway flow, so they are likely noise / telemetry / AWS SDK background traffic rather than the primary create-flow blocker.
- Highest-value mock hypothesis from this run:
  - after a successful validator round-trip, the client re-reads `LoginInfoList`
  - `LoginInfoList.NameReservations` was still always `[]`
  - that makes `NameReservations` the best candidate for the post-validator crash before customization/create

## 2026-04-20 NameReservations Mock Patch

- Ghidra trace:
  - top-level parser key: `NameReservations`
  - entry parser: `FUN_1474e7090`
  - transformed model builder: `FUN_1464291e0`
- The parser recognizes a real structured PascalCase object including fields such as:
  - `Channel`
  - `CreatedDate`
  - `DeletedDate`
  - `DisplayName`
  - `IsLatent`
  - `IsTrialOwner`
  - `ModifiedDate`
  - `NameLatentDate`
  - `Namespace`
  - `NormalizedName`
  - `OwnerState`
  - `OwningResourceId`
  - `PersonaId`
  - `Region`
  - `Service`
  - `State`
  - `WorldId`
- `server/auth_mock.py` now:
  - persists validated names in `Ctx.name_reservations`
  - records them in `handle_validate_character`
  - returns them in `LoginInfoList.NameReservations`
- Current minimal reservation object emitted after validator:
  - `Channel = "STEAM_APP_ID.1063730"`
  - `DisplayName = <validated name>`
  - `NormalizedName = <uppercased name>`
  - `State = "Reserved"`
  - `PersonaId = ctx.persona_id`
  - `WorldId = ctx.world_id`
  - plus timestamp/string fields populated with safe defaults

## 2026-04-21 Archived Flow Breakthrough To REP Setup

- With `auth_mock` running, the archived build can now get beyond character select and into the post-create/login path under Frida.
- New observed sequence from `capture/20260421_114737_archived_frida/session.log`:
  - remote-config GET succeeded with `200` and tiny `{}`-style bodies
  - the client then resolved:
    - `127.0.0.1:23971`
    - `127.0.0.1:27000`
  - this is the first archived-run proof that it is consuming the mocked login/REP addressing and preparing local socket setup
- After that, the archived run still ends in the generic connection error / relaunch behavior.
- There is still a repeated side-channel `POST /` returning `400`, but at this stage it is happening **after** remote config and REP-address resolution, so it is weaker as the primary blocker than before.
- Practical implication:
  - the archived path is no longer blocked at character select alone
  - it is now reaching the local REP setup boundary
  - next highest-value work should focus on correlating this archived failure with the live DTLS/REP path rather than continuing to treat it as a pure auth/create problem

## 2026-04-21 Archived Run Reaches Create + Queue + Local REP Resolution

- Latest paired evidence from:
  - `capture/auth_mock_logs/20260421.log`
  - `capture/20260421_115623_archived_frida/session.log`
- The archived client now definitely completes the mocked happy path through:
  - `POST /prod/game/worlds/.../characters/validator/jwt/omni` -> `200`
  - post-validator `GET /prod/game/getlogininfo/jwt/omni` -> `200`
  - `POST /prod/game/worlds/.../characters/jwt/omni` -> `200`
  - `POST /prod/game/login/queue/v2/jwt/omni` -> `200`
  - world remote-config fetches -> `200`
- The mocked create response was accepted:
  - auth mock logged persisted character count increasing to `2`
  - client accepted the top-level PascalCase `{"Character": {...}}` payload
- The mocked queue response was also accepted:
  - auth mock logged issued ticket `22a363e1-23c9-43cd-a9b7-b0e2d6199af4`
  - client continued into remote-config + local-address resolution instead of failing at queue parsing
- Frida then showed the archived client resolving the local REP-related endpoints:
  - `127.0.0.1:23971`
  - `127.0.0.1:27000`
- Important current gap:
  - no actual socket connect/sendto to `23971` was observed yet
  - instead, after address resolution, the client still performs one or more `WinHTTP POST /` calls that return `400`
  - from the user’s point of view this still surfaces as the same generic server connection error
- Interpretation:
  - auth/create/login-queue parsing is now good enough on the archived path
  - the next blocker is downstream of queue admission and overlaps the REP startup boundary
  - the remaining useful instrumentation work is:
    - attribute those anonymous `POST / -> 400` calls to their exact host/handle
    - watch for actual socket creation / UDP path startup after `23971` resolution

## 2026-04-21 Archived `POST / -> 400` Is Kinesis, Not The REP Blocker

- Latest archived Frida run:
  - `capture/20260421_121413_archived_frida/session.log`
- New WinHTTP handle tracking proved the previously anonymous `POST / -> 400` requests are:
  - `POST https://kinesis.us-west-2.amazonaws.com:443/`
- This happened both before and after create/queue, and the client still continued past:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - world remote-config fetches
- So the recurring `400` is background telemetry/noise, not the primary blocker.
- More important signal from the same run:
  - immediately after queue admission and world remote-config, the client resolved:
    - `127.0.0.1:23971`
    - `127.0.0.1:27000`
  - and then created:
    - `WSASocketW -> AF_INET SOCK_DGRAM proto=17`
- That is the strongest archived proof so far that the client is crossing into the REP/UDP startup path.
- Current remaining gap:
  - no actual UDP send/connect event to `23971` has been observed yet
  - no DTLS bytes captured yet on the archived path
- Next instrumentation priority is therefore the UDP path, not WinHTTP:
  - `WSASendTo`
  - `bind`
  - `WSAIoctl`
  - any subsequent datagram activity after the `23971` / `27000` resolution point

## 2026-04-21 Archived Client Now Creates And Configures The REP UDP Socket

- Latest archived run:
  - `capture/20260421_121953_archived_frida/session.log`
  - auth side confirms the same run reached:
    - `validator`
    - `CreateCharacter`
    - `login/queue/v2`
    - world remote-config
- After queue admission, the archived client again resolved:
  - `127.0.0.1:23971`
  - `127.0.0.1:27000`
- New useful signal from the added UDP hooks:
  - it creates a dedicated UDP socket exactly at that point:
    - `WSASocketW -> AF_INET SOCK_DGRAM proto=17`
  - then immediately configures it with:
    - `WSAIoctl(..., 0x9800000c) ret=0`
- This is the strongest archived proof so far that the client has crossed from the queue/remote-config flow into REP UDP initialization.
- Important negative result:
  - there is still **no** observed:
    - `WSAConnect()` to `127.0.0.1:23971`
    - `sendto()` / `WSASendTo()`
    - `bind()`
    - DTLS traffic on the archived path
- The recurring `POST https://kinesis.us-west-2.amazonaws.com/ -> 400` continues after this point and remains background telemetry, not the primary blocker.
- Current blocker has narrowed again:
  - the archived client resolves REP endpoints
  - allocates and configures the UDP socket
  - but dies before the first outbound datagram / DTLS ClientHello is emitted
- Highest-value next instrumentation target is now the code path between:
  - UDP socket creation / `WSAIoctl(0x9800000c)`
  - and the missing first datagram send

## 2026-04-21 Next UDP Instrumentation Pass

- Added more REP-startup socket instrumentation to `tools/frida_dtls_hook.js`:
  - `WSASendMsg`
  - `WSAEventSelect`
  - improved `WSAIoctl` decoding
- Known ioctl mappings now logged symbolically:
  - `0x9800000c` -> `SIO_UDP_CONNRESET`
  - `0xc8000006` -> `SIO_GET_EXTENSION_FUNCTION_POINTER`
  - `0x98000011` -> `SIO_KEEPALIVE_VALS`
  - `0xc8000019` -> `SIO_LOOPBACK_FAST_PATH`
  - `0x48000016` -> `SIO_TCP_INFO`
- Purpose of this pass:
  - determine whether the archived client switches to extension/event-driven socket APIs between UDP socket setup and the missing first outbound datagram
  - distinguish “socket created but never used” from “socket used through a different Winsock path than `sendto` / `WSAConnect`”

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

## 2026-04-21 Archived Post-Queue State Is Stable; Send Path Still Missing

- Latest archived run (`capture/20260421_123139_archived_frida`) again reached:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - world-scoped remote-config fetches
- `auth_mock` confirmed this as:
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- Frida confirms the same internal REP boundary every good run:
  - `getaddrinfo -> 127.0.0.1:23971`
  - `getaddrinfo -> 127.0.0.1:27000`
  - `WSASocketW -> AF_INET SOCK_DGRAM proto=17`
  - `WSAIoctl(..., SIO_UDP_CONNRESET) ret=0`
- The recurring `POST / -> 400` noise is fully attributed to:
  - `POST https://kinesis.us-west-2.amazonaws.com:443/`
  and remains unrelated telemetry.
- Important negative result remains unchanged:
  - no `WSAConnect()` to `23971`
  - no `sendto()` / `WSASendTo()`
  - no DTLS packets
- Current blocker is now very tight:
  - after REP UDP socket creation/configuration, before first outbound datagram

## 2026-04-21 Winsock Extension Hooking Pass

- Updated `tools/frida_dtls_hook.js` so `WSAIoctl(SIO_GET_EXTENSION_FUNCTION_POINTER)` now:
  - decodes the input GUID as a real GUID string
  - maps known extension GUIDs symbolically where possible:
    - `ConnectEx`
    - `DisconnectEx`
    - `AcceptEx`
    - `GetAcceptExSockaddrs`
    - `TransmitFile`
    - `TransmitPackets`
    - `WSARecvMsg`
    - `WSASendMsg`
  - reads the returned function pointer from the output buffer
  - auto-hooks those extension functions in-process
- Purpose:
  - determine whether the missing first REP/DTLS datagram is sent through an extension path instead of normal `sendto` / `WSAConnect`
  - especially verify whether the client transitions into `WSASendMsg`, `ConnectEx`, or another provider-specific path right after UDP socket setup

## 2026-04-21 Extension GUID Decode Result

- The extension-function pass is working:
  - `SIO_GET_EXTENSION_FUNCTION_POINTER` now resolves concrete Winsock extensions instead of logging raw buffers
  - current archived runs successfully auto-hook:
    - `ConnectEx`
    - `DisconnectEx`
- Important result:
  - on the latest archived attempts, the observed extension usage is still only on the normal TCP/HTTPS side
  - example:
    - `ConnectEx(...) -> 127.0.0.1:443`
    - `ConnectEx(...) -> 34.223.45.127:443`
- No REP-specific extension send path has been observed yet:
  - no `WSASendMsg`
  - no UDP-side `ConnectEx`
  - no first datagram to `127.0.0.1:23971`
- One of the latest attempts (`capture/20260421_125553_archived_frida`) did **not** reach the REP boundary at all:
  - auth mock only reached `getlogininfo`
  - no validator/create/login-queue on that run
- So the extension-hooking pass is validated, but it has not yet shown a hidden REP send path.

## 2026-04-21 Good Archived Post-Queue Run Under Extension Hooks

- Archived run `capture/20260421_134015_archived_frida` reached the full mocked handoff again:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - world remote-config
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- After queue admission, Frida again shows:
  - `getaddrinfo -> 127.0.0.1:23971`
  - `getaddrinfo -> 127.0.0.1:27000`
  - `WSASocketW -> AF_INET SOCK_DGRAM proto=17`
  - `WSAIoctl(..., SIO_UDP_CONNRESET) ret=0`
- Critical negative result:
  - even on a true post-queue run, there is still no:
    - UDP-side `ConnectEx`
    - `WSASendMsg`
    - `WSASendTo`
    - `sendto`
    - DTLS packet to `127.0.0.1:23971`
- The new extension hooks only caught the already-known TCP/HTTPS path:
  - repeated `ConnectEx(... -> 127.0.0.1:443)`
  - repeated `ConnectEx(... -> 34.223.45.86:443)`
- Process still exits cleanly via:
  - `TerminateProcess(handle=0xffffffffffffffff, code=0)`
- Current conclusion:
  - the archived client definitely reaches REP UDP socket initialization
  - but the first outbound REP datagram is still gated before any observable Winsock send path we currently hook

## 2026-04-21 IOCP / Socket Infra Instrumentation Pass

- Added another archived Frida pass focused on the gap after REP UDP socket creation and before the missing first outbound datagram.
- `tools/frida_dtls_hook.js` now also hooks:
  - `CreateIoCompletionPort`
  - `GetQueuedCompletionStatus`
  - `PostQueuedCompletionStatus`
  - `setsockopt`
  - `ioctlsocket`
- Goal of this pass:
  - determine whether the archived client associates the REP UDP socket with an IO completion port
  - capture any lower-level socket configuration immediately before the missing first DTLS/UDP send

## 2026-04-21 Low-Level NTDLL Socket Pass

- Added a deeper archived Frida pass for the exact REP UDP gap after `WSASocketW(AF_INET, SOCK_DGRAM, 17)`.
- `tools/frida_dtls_hook.js` now tracks known datagram socket handles and hooks:
  - `NtDeviceIoControlFile`
  - `NtClose`
- These hooks are filtered to known UDP socket handles only.
- Goal:
  - determine whether the first REP datagram path bypasses normal Winsock send APIs and drops directly into AFD / `NtDeviceIoControlFile`
  - confirm whether the REP UDP socket is immediately closed without ever sending

## 2026-04-21 Winsock Provider SPI Pass

- Added another archived Frida pass to catch REP traffic if it bypasses normal Winsock exports entirely.
- `tools/frida_dtls_hook.js` now attempts to hook `WSPStartup` and, on success, auto-hooks selected provider procedure table entries:
  - `WSPSocket`
  - `WSPConnect`
  - `WSPIoctl`
  - `WSPSendTo`
  - `WSPCloseSocket`
- Goal:
  - determine whether the REP UDP socket uses Winsock SPI provider callbacks instead of `WSAConnect` / `WSASendTo` / `sendto`
  - catch provider-level UDP send or close behavior immediately after queue admission and REP address resolution

## 2026-04-21 Provider SPI Pass Result

- Archived run `capture/20260421_142133_archived_frida` reached the same REP UDP boundary again:
  - `getaddrinfo -> 127.0.0.1:23971`
  - `getaddrinfo -> 127.0.0.1:27000`
  - `WSASocketW -> AF_INET SOCK_DGRAM proto=17`
  - `WSAIoctl(..., SIO_UDP_CONNRESET) ret=0`
- The new Winsock SPI pass did **not** expose a hidden provider-level REP send path:
  - `WSPStartup` was `not_found`
  - therefore no `WSPSendTo` / `WSPIoctl` / `WSPConnect` / `WSPCloseSocket` hooks were installed
- The low-level NTDLL pass also remained unavailable on this archived build/runtime:
  - `NtDeviceIoControlFile` was `not_found`
  - `NtClose` was `not_found`
- Result:
  - even after exhausting normal Winsock exports, IOCP, extension functions, NTDLL, and provider SPI, the archived client still shows no observable outbound REP UDP datagram
  - the current blocker remains precisely: after REP UDP socket creation/configuration, before any first send that reaches a hookable OS networking surface

## 2026-04-21 Internal REP Function Hook Pass

- Added direct internal archived hooks for the two known REP transport RVAs from earlier Ghidra work:
  - `FUN_146b6a270` (`RVA 0x06b6a270`) — gridmate-udp / REP transport constructor path
  - `FUN_145dce750` (`RVA 0x05dce750`) — `Javelin_SecureSocketDriver_Initialize`
- Goal:
  - determine whether the archived client ever reaches internal REP transport construction and DTLS driver initialization on the failing post-queue path
  - stop relying purely on OS socket APIs and instead instrument the game-side REP setup one layer earlier

## 2026-04-21 Internal REP Hook Result

- Archived run `capture/20260421_143357_archived_frida` reached the same REP UDP boundary again and, for the first time, also hit the new internal REP hooks:
  - `[rep-int] transport ctor enter ...`
  - `[rep-int] secure init enter ctx=... verifyField=0x200fb1a7800 modeField=0`
  - `WSASocketW -> AF_INET SOCK_DGRAM proto=17`
  - `WSAIoctl(..., SIO_UDP_CONNRESET) ret=0`
  - `[rep-int] secure init leave ret=0x0`
  - `[rep-int] transport ctor leave ret=...`
- Important result:
  - the archived client definitely reaches both:
    - REP transport construction (`FUN_146b6a270`)
    - secure socket / DTLS driver initialization (`FUN_145dce750`)
  - both return successfully on the failing post-queue path
- This moves the blocker again:
  - no longer “before transport construction”
  - no longer “inside secure init”
  - now specifically after successful REP transport creation + secure init, but still before any observable outbound REP UDP datagram or DTLS ClientHello
- Follow-up instrumentation added after this result:
  - one-shot Frida backtraces on the transport-constructor hook and secure-init hook
  - goal is to identify the internal caller chain immediately above successful REP transport setup on the failing archived path

## 2026-04-21 Internal REP Backtrace Result

- Archived run `capture/20260421_144129_archived_frida` confirmed the new one-shot backtrace hooks fire on the failing post-queue path:
  - `[rep-int] transport ctor bt ...`
  - `[rep-int] secure init bt ...`
- The backtraces were useful in one respect:
  - they confirmed the hooks are firing at the exact REP boundary where address resolution and UDP socket creation happen
- But the symbol names in the archived runtime are too noisy / misleading for direct interpretation.
- Follow-up change:
  - Frida backtrace logging now includes raw module-relative offsets (`NewWorld.exe+0x...`) so the next archived run produces addresses that can be matched back to Ghidra directly.

## 2026-04-21 Internal REP Backtrace RVAs

- Archived run `capture/20260421_144726_archived_frida` produced clean module-relative caller-chain RVAs for the two internal REP hooks.
- Transport constructor backtrace included:
  - `NewWorld.exe+0x6b6d734`
  - `NewWorld.exe+0x6b6d5e8`
  - `NewWorld.exe+0x6426391`
  - `NewWorld.exe+0x644a66f`
  - `NewWorld.exe+0x646d4af`
  - `NewWorld.exe+0x646cbe5`
  - `NewWorld.exe+0x646d3c5`
  - `NewWorld.exe+0x1044d82`
  - `NewWorld.exe+0x720bae0`
  - `NewWorld.exe+0x72181dd`
  - `NewWorld.exe+0x7aa729e`
- Secure-init backtrace included:
  - `NewWorld.exe+0x0f693c0`
  - `NewWorld.exe+0x5dbb662`
  - `NewWorld.exe+0x5dbae0d`
  - `NewWorld.exe+0x5dc8be4`
  - `NewWorld.exe+0x6b36f03`
  - `NewWorld.exe+0x6b27e9d`
  - `NewWorld.exe+0x6b6a8be`
  - `NewWorld.exe+0x6b6d734`
  - `NewWorld.exe+0x6b6d5e8`
  - `NewWorld.exe+0x6426391`
  - `NewWorld.exe+0x644a66f`
  - `NewWorld.exe+0x646d4af`
- These runs still end the same way:
  - transport constructor enters
  - secure init enters and returns `0`
  - UDP socket is created and `SIO_UDP_CONNRESET` is set
  - no observable outbound REP datagram appears
  - process exits via `TerminateProcess(handle=-1, code=0)`
- Result:
  - we now have concrete RVAs for the caller chain immediately above successful REP transport creation and secure init
  - the next RE step should target those RVAs directly in Ghidra instead of expanding OS-level hooks further

## 2026-04-21 Ghidra REP State-Machine Mapping

- Mapped the important backtrace RVAs in Ghidra on the archived binary:
  - `NewWorld.exe+0x644a070` -> `FUN_14644a070`
  - `NewWorld.exe+0x6425f20` -> `FUN_146425f20`
  - `NewWorld.exe+0x646d460` -> `FUN_14646d460`
- `FUN_14644a070` is the `GameConnectionWrapper` state machine.
  - In the `StartREPConnection` branch it logs the REP address, calls `FUN_146425f20(param_1, param_2)`, and transitions into `WaitingForREPConnection`.
  - In the next wait branch it checks a virtual method on `*(param_1 + 0x1000)` at vtable offset `+0xa8`; if that reports ready, it advances to `start actor game connection`.
- `FUN_146425f20` is the REP/bootstrap helper directly called from that state machine branch.
  - It works against the REP-side object at `param_1 + 0x1000`.
  - It invokes multiple virtual methods on that object (`+0x08`, `+0x10`, `+0x18`) while setting up the REP side.
- This means the archived failure is now tightly bounded to:
  - after successful transport construction / secure init
  - inside or immediately after the `StartREPConnection` -> `FUN_146425f20` path
  - before the `*(repObj->vtbl + 0xa8)` readiness gate ever transitions the state machine forward
- Follow-up instrumentation added to the Frida archived hook:
  - direct hooks for `FUN_146425f20` and `FUN_14644a070`
  - dynamic hooks for REP object vtable slots:
    - `+0x08`
    - `+0x10`
    - `+0x18`
    - `+0xa8`
- Goal of the next archived run:
  - determine whether the REP object methods are actually called
  - and whether the readiness method at `+0xa8` is returning a stable false / error path before any outbound datagram is sent

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
