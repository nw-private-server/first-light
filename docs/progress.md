# New World Private Server — Progress & Findings

> Living document. Updated as we learn more.
> Last updated: 2026-04-23 (DTLS trust gate is cleanly bypassed on the archived non-EAC build via a runtime Frida onEnter hook on `FUN_145dce750` that nulls `verifyField` / `param_1[0x51]`. Client now completes the full DTLS 1.2 handshake against our self-signed cert and emits encrypted application data. Current blocker: `openssl s_server` was tearing the connection down immediately after the handshake; fix in place. Next step is reading the first decrypted Javelin record and beginning to speak REP.)

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
    - 2026-04-19 note: moving `C:\Users\charl\AppData\Roaming\AGS\New World\savedata` aside to a timestamped backup removed one pre-`getlogininfo` failure mode where the game died before ever requesting character-select data.

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
| Game client | `G:\NewWorldArchive\GameClient\` | 72 GB |
| Game logs & crash DB | `G:\NewWorldArchive\AppData_Local\` | 199 MB |
| Save data & settings | `G:\NewWorldArchive\AppData_Roaming\` | 121 MB |
| Live install | `H:\SteamLibrary\steamapps\common\New World\` | 72 GB |

### Source references (sparse clones)
| Repo | Where | Purpose |
|------|-------|---------|
| O3DE (AzNetworking + Multiplayer gem + RTTI) | `C:\Users\charl\Programs\o3de\` | Conceptual comparison doc only (not a wire-format match) |
| Lumberyard (GridMate) | `C:\Users\charl\Programs\lumberyard\` | **Primary protocol reference** — Javelin is a GridMate fork |

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

- Tried `tools/frida_capture.py --exe "G:\NewWorldArchive\GameClient\Bin64\NewWorld.exe" --name archived_frida`
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

- Added `steam_appid.txt` containing `1063730` next to `G:\NewWorldArchive\GameClient\Bin64\NewWorld.exe`
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

- A later archived run regressed to the old Steam blocker. Investigation showed `G:\NewWorldArchive\GameClient\Bin64\steam_appid.txt` was no longer present at run time.
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
  - `G:\NewWorldArchive\GameClient\Bin64\steam_appid.txt` was missing again at run time
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

- Ran `tools/list_pe_imports.py` against `G:\NewWorldArchive\GameClient\Bin64\NewWorld.exe`
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

## 2026-04-21 REP Start Helper / Readiness Gate Result

- Archived run `capture/20260421_150732_archived_frida` hit the new internal hooks and finally exposed the exact post-queue REP behavior.
- The REP object methods are reached in this order:
  - `rep.vtbl+0x08`
  - `rep.vtbl+0x10`
  - `rep.vtbl+0x18`
- Immediately after those calls, the internal start helper returns:
  - `start helper leave ret=0xffff`
- Important caveat:
  - `FUN_146425f20` decompiles as `void`
  - so the observed `ret=0xffff` is just the leftover `RAX` value at function exit, not a trusted helper error code
- After that, the state machine repeatedly polls:
  - `rep.vtbl+0xa8`
- That readiness method returns:
  - `0x0`
  - on every observed poll
- No outbound REP UDP datagram or DTLS `ClientHello` appears before or during that polling loop.
- This tightens the archived blocker to:
  - `FUN_146425f20` completes but returns `0xffff`
  - the REP object never transitions into the ready state reported by `vtbl+0xa8`
  - `GameConnectionWrapper` therefore remains stuck in the `WaitingForREPConnection` branch until the process exits
- Practical conclusion:
  - the next RE target is no longer generic transport startup
  - it is specifically the REP object method behind `vtbl+0xa8` (`NewWorld.exe+0x6b6df30`) and the helper path that returns `0xffff` right before polling begins

## 2026-04-21 REP Ready-Flag Mapping

- Raw archived code bytes around `NewWorld.exe+0x6b6df30` show the readiness method is tiny:
  - `movzx eax, byte ptr [rcx+0x601]`
  - `ret`
- So `rep.vtbl+0xa8` is not a complex network routine; it simply reads the REP-object ready flag at offset `+0x601`.
- Nearby archived transport functions clarify the lifecycle of that flag:
  - `FUN_146b6f190` sets:
    - `*(byte *)(param_1 + 0x601) = 1`
    - on the path that logs / handles `Client connection is authorized`
  - `FUN_146b6e7c0` checks `*(byte *)(param_1 + 0x601) != 0`, handles disconnect/error work, then clears:
    - `*(byte *)(param_1 + 0x601) = 0`
- This means the current archived failure is best described as:
  - the REP object is created
  - the ready flag at `+0x601` never flips to `1`
  - therefore `rep.vtbl+0xa8` keeps returning `0`
  - and `GameConnectionWrapper` stays stuck waiting for REP connection readiness
- Follow-up instrumentation added:
  - direct Frida hooks for:
    - `FUN_146b6f190` (`NewWorld.exe+0x6b6f190`) — ready-flag setter / authorized path
    - `FUN_146b6e7c0` (`NewWorld.exe+0x6b6e7c0`) — ready-flag reset / disconnect path

## 2026-04-21 REP Ready-Flag Hook Result

- Archived run `capture/20260421_152417_archived_frida` reached the same post-queue REP boundary again.
- The key new result is negative but decisive:
  - neither the ready-flag setter hook (`FUN_146b6f190`) nor the reset hook (`FUN_146b6e7c0`) fired at all on the failing path
- At the same time:
  - `FUN_146425f20` (`start helper`) still ran once
  - `rep.vtbl+0x08`, `+0x10`, and `+0x18` still ran
  - `rep.vtbl+0xa8` was polled repeatedly and kept returning `0`
- So the current archived failure is even tighter than before:
  - the transport never reaches the code path that sets `repObj+0x601 = 1`
  - and it never reaches the disconnect/reset path that clears that same flag either
  - the state machine is simply stuck polling the readiness byte while it remains `0`
- Practical implication:
  - the next RE target should shift from the ready-flag setter itself to the specific branch between:
    - `FUN_146425f20` / REP vtable `+0x08/+0x10/+0x18`
    - and `FUN_146b6f190`
  - that gap is now the most likely place where the archived path bails before marking REP authorized/ready
- Follow-up instrumentation added:
  - REP object state snapshots on:
    - `rep.vtbl+0x10`
    - `rep.vtbl+0x18`
    - `rep.vtbl+0xa8`
  - fields logged per call:
    - `+0x600`
    - `+0x601`
    - `+0x6f0`
    - `+0x6f1`
    - `+0x6f2`
    - pointers at `+0xd0` and `+0x118`
- Goal of the next run:
  - determine whether the REP object shows any precursor authorization/ready-state mutation at all before the `+0xa8` poll loop starts

## 2026-04-21 REP Object State Snapshot Result

- Archived run `capture/20260421_153259_archived_frida` produced the first useful REP-object state snapshot around the last internal methods before the poll loop.
- At `rep.vtbl+0x10` / `rep.vtbl+0x18` entry the object looked like:
  - `+0x600 = 0`
  - `+0x601 = 0`
  - `+0x6f0 = 1`
  - `+0x6f1 = 0`
  - `+0x6f2 = 0`
  - `+0xd0 = non-null`
  - `+0x118 = 0`
- After `rep.vtbl+0x18` returns, the object changes only in one obvious way:
  - `+0x118` becomes non-null
- Then, during the repeated `rep.vtbl+0xa8` readiness polls, the object remains stable:
  - `+0x600 = 0`
  - `+0x601 = 0`
  - `+0x6f0 = 1`
  - `+0x6f1 = 0`
  - `+0x6f2 = 0`
  - `+0xd0 = same non-null pointer`
  - `+0x118 = same non-null pointer`
- So the archived path is not failing because the REP object is uninitialized.
- Instead:
  - `vtbl+0x18` appears to populate/attach the object behind `+0x118`
  - but nothing ever flips the readiness byte `+0x601`
  - and the auxiliary state bytes `+0x6f1` / `+0x6f2` also never change from `0`
- Practical implication:
  - the next RE target should focus on how the object at `repObj + 0x118` is supposed to drive the transition into the authorized/ready path
  - that pointer now looks like the most plausible upstream dependency for why `FUN_146b6f190` never fires and `+0x601` never becomes `1`

### Current archived REP focus

- The latest archived Frida runs narrowed the post-queue failure to the object behind:
  - `repObj + 0x118`
- Ghidra confirms:
  - `rep.vtbl+0xa8` is just `return *(byte *)(this + 0x601);`
  - `FUN_146b6f190` is the setter that flips `+0x601 = 1`
  - `FUN_146b6e7c0` is a later reset/error path that can clear it back to `0`
- Runtime state from the last good archived REP-boundary run:
  - before `rep.vtbl+0x18`:
    - `+0x600 = 0`
    - `+0x601 = 0`
    - `+0x6f0 = 1`
    - `+0x6f1 = 0`
    - `+0x6f2 = 0`
    - `+0xd0 = non-null`
    - `+0x118 = 0`
  - after `rep.vtbl+0x18`:
    - `+0x118` becomes non-null and stays non-null during the poll loop
  - during repeated `rep.vtbl+0xa8` polls:
    - `+0x601` remains `0`
    - `+0x6f1` / `+0x6f2` remain `0`
    - setter/reset hooks never fire
- Transport ctor Ghidra review (`FUN_146b6a270`) shows the transport object itself has meaningful vtable activity at:
  - `+0x08`
  - `+0x20`
  - `+0x30`
  - `+0x48`
  - `+0x68`
  - `+0x80`
- New Frida instrumentation now hooks those exact transport-object methods and snapshots transport state fields:
  - pointers:
    - `+0x60`
    - `+0x68`
    - `+0x1b0`
  - integral state:
    - `+0x164`
    - `+0x168`
    - `+0x169`
    - `+0x16a`
- Immediate goal for the next archived run:
  - determine whether the transport object at `repObj+0x118` is actually active
  - and whether its callback/control fields (especially `+0x60`) ever become populated before the REP ready byte would be set

### Latest archived run

- The newest archived Frida run reached the same REP-ready poll loop, but from the player perspective it CTD'd before the usual connection-error dialog.
- Useful internal result:
  - the REP object still stayed in the same stalled state:
    - `+0x601 = 0`
    - `+0x118 = non-null`
  - transport-object hooks partially attached:
    - `transport.vtbl+0x20` -> success
    - `transport.vtbl+0x48` -> success
    - `transport.vtbl+0x68` -> success
  - but none of those hooked transport methods actually executed on the failing path
- One instrumentation issue was exposed:
  - `transport.vtbl+0x30` repeatedly failed Frida attach with:
    - `unable to intercept function at 0x...`
  - this was Frida-side noise from retrying the same failed attach, not a new game-side behavior
  - the hook now marks failed transport hooks as attempted so future runs do not spam that error
- Additional runtime observation:
  - there was at least one later `WSASend` on the process after the REP poll loop, but still no REP-ready transition and no observed outbound DTLS `ClientHello`
- Current interpretation:
  - the transport object behind `repObj+0x118` exists, but the expected transport-vtable path that should drive authorization/readiness is still not executing
  - the blocker remains between successful transport creation and the path that would eventually flip `repObj+0x601 = 1`

### Newest archived CTD run

- This run CTD'd from the player's perspective right after character creation, but the logs show it still reached the same deeper boundary:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - REP-ready poll loop on `rep.vtbl+0xa8`
- So this was not a regression back to the create path; it was the same post-queue REP stall followed by process termination.
- The transport-object pass still showed:
  - `transport.vtbl+0x20` / `+0x48` / `+0x68` are hookable
  - none of those successfully hooked transport methods executed before termination
- New side observation:
  - there were late `WSASend` / `WSARecv` calls after the REP poll loop
  - but previous logs did not include socket handles, so it was unclear whether those belonged to the REP UDP socket or unrelated TCP/WinHTTP traffic
- Next instrumentation pass now logs for `WSASend` / `WSARecv`:
  - socket handle
  - whether that handle is one of the known REP UDP sockets
  - first buffer length
- Immediate goal for the next run:
  - determine whether the late send/recv activity is on the REP UDP socket or only on unrelated sockets

### Socket-label follow-up

- The next archived run showed that `udpKnown=true` was not specific enough:
  - there is definitely send/recv activity on UDP sockets
  - but the old label only meant “some UDP socket created by the process,” not “the REP socket created right after `23971/27000` resolution”
- New instrumentation now opens a short REP-candidate window when the client resolves:
  - `127.0.0.1:23971`
  - `127.0.0.1:27000`
- Any UDP socket created during that window is now marked:
  - `repCandidate=true`
- `WSASend` / `WSARecv` logs now include both:
  - `udpKnown=...`
  - `repCandidate=...`
- Immediate goal for the next run:
  - determine whether any actual send/recv traffic belongs to the REP-candidate socket rather than unrelated UDP activity

### REP-candidate UDP traffic breakthrough

- The newest good archived run proved the REP-candidate socket is not inert.
- After:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - REP address resolution for `127.0.0.1:23971` / `127.0.0.1:27000`
- the session log now shows real traffic on `repCandidate=true` UDP sockets.
- Concrete examples from `capture/20260421_162305_archived_frida/session.log`:
  - `sock=0x18bc udpKnown=true repCandidate=true`
    - `WSASend` lengths: `194`, `93`, `3516`, `31`
    - `WSARecv` buffers: `4096`
  - `sock=0x230c udpKnown=true repCandidate=true`
    - `WSASend` lengths: `194`, `93`, `283`, `31`
  - `sock=0x2230 udpKnown=true repCandidate=true`
    - `WSASend` lengths: `228`, `126`, `1217`, `3118`, `31`
    - `WSARecv` buffers: `4096`, `16384`, `20480`
  - `sock=0x2244 udpKnown=true repCandidate=true`
    - `WSASend` lengths: `207`, `93`, `1176`, `31`
- At the same time, the REP state machine still stalls:
  - `repObj+0x118 = non-null`
  - `repObj+0x601 = 0`
  - `rep.vtbl+0xa8` keeps returning `0`
- This is the first strong proof that the archived path is exchanging UDP traffic on the REP-candidate socket even though the ready flag never flips.
- Next instrumentation pass:
  - dump a short hex prefix and classify likely DTLS/TLS records for `WSASend` / `WSARecv` when `repCandidate=true`
  - goal: determine whether the REP-candidate traffic is actually DTLS (`16 fe fd` / `17 fe fd` etc.) or some other pre-auth datagram protocol

### Confirmed good post-queue run after packet-classifier patch

- The next archived run after the packet-classifier patch was a confirmed good path:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- Internal REP state remained the same:
  - `FUN_146425f20` / start helper entered
  - returned `0xffff`
  - `rep.vtbl+0xa8` kept returning `0`
  - `repObj+0x601` never flipped to `1`
- A new REP candidate socket was created:
  - `REP candidate socket -> 0x2290`
- But on this run there were still **no** `WSASend` / `WSARecv` logs for that specific `repCandidate=true` handle before termination.
- So the latest evidence is:
  - the client definitely reaches REP handoff
  - it definitely allocates a REP-candidate UDP socket
  - but the active UDP traffic seen later may still belong to a different socket than the one currently tagged as the REP candidate
- Next instrumentation refinement:
  - log socket age relative to the REP address-resolution window for **all** UDP socket creations
  - goal: determine whether the actual active post-queue UDP socket is being created slightly before or after the current 5s REP-candidate tagging window

### Refined REP UDP correlation result

- The next confirmed good archived run (`OUTCOME REACHED_LOGIN_QUEUE_V2`) tightened the picture again.
- Good-path milestones:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - `start helper enter`
  - REP readiness poll loop on `rep.vtbl+0xa8`
- Internal state still did not change:
  - `repObj+0x601` stayed `0`
  - `repObj+0x118` stayed non-null
  - `rep.vtbl+0xa8` kept returning `0`
- The refined socket-timing instrumentation showed:
  - a REP address-resolution window opened at:
    - `getaddrinfo -> 127.0.0.1:23971`
    - `getaddrinfo -> 127.0.0.1:27000`
  - a REP candidate socket was immediately created:
    - `REP candidate socket -> 0xc30 ageMs=0 sinceRepWindowMs=0`
- But after that:
  - there were still **no** `WSASend` / `WSARecv` events on `sock=0xc30`
  - all later active UDP traffic belonged to sockets still labeled `repCandidate=false`
- Important implication:
  - the current REP-candidate heuristic is still not identifying the actual active post-queue UDP socket
  - the “real” active UDP socket is likely created outside the narrow current window or selected through a different internal object path than the one we are correlating today
- This is still progress because it rules out a simpler interpretation:
  - the candidate socket created immediately at REP handoff is not the one later carrying the visible UDP traffic in this run

### Next correlation refinement

- The next instrumentation pass stops relying only on timing.
- New goal:
  - when a known UDP socket hits `WSASend` / `WSARecv`, scan the current:
    - REP object
    - transport object (`repObj+0x118`)
  - and log whether that active socket handle is actually stored anywhere inside those objects
- This should answer the next concrete question:
  - which live UDP handle is the REP stack internally pointing at while the ready flag remains `0`

### Latest confirmed REP-handoff run

- Latest archived Frida run `20260421_172121_archived_frida` was another real post-queue run:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- Internal REP state remained unchanged:
  - `start helper` entered and returned `0xffff`
  - `transport ctor` entered and returned successfully
  - `secure init` entered and returned `0`
  - `repObj+0x118` stayed non-null
  - `repObj+0x601` stayed `0`
  - `rep.vtbl+0xa8` continued polling and returning `0`
- The REP window opened cleanly:
  - `getaddrinfo -> 127.0.0.1:23971`
  - `getaddrinfo -> 127.0.0.1:27000`
  - immediate REP candidate socket creation:
    - `0x1e64`
  - immediate UDP configuration:
    - `WSAIoctl(0x1e64, SIO_UDP_CONNRESET) ret=0`
- But there were still no `WSASend` / `WSARecv` events on that REP-candidate handle.
- Later visible UDP traffic again belonged to other sockets, all still `repCandidate=false`.
- So the current best conclusion is unchanged but reinforced:
  - the client reaches REP handoff cleanly
  - the immediate REP-candidate socket is still not the active visible UDP socket
  - the real post-queue active UDP handle is either:
    - created outside the current timing window, or
    - referenced through a different internal object path than the current candidate logic

### REP socket-correlation fix

- The first REP-object-side correlation pass had a flaw:
  - it memoized correlation attempts before any hits were found
  - so if a UDP handle was inserted into the REP/transport object later, subsequent scans for the same source/socket/object tuple would be skipped
- The hook was updated so that:
  - only positive correlation signatures are cached
  - misses are not cached anymore
- The REP socket scan was also widened beyond just the top-level objects:
  - `rep`
  - `transport`
  - `rep+0xd0`
  - `rep+0x118`
  - `transport+0x60`
  - `transport+0x68`
  - `transport+0x1b0`
- Goal of the next good post-queue archived run:
  - catch late attachment of the real active UDP handle into the REP object graph
  - instead of relying only on the timing-based `repCandidate` heuristic

### Socket handle-reuse fix

- A later archived run exposed a second correlation bug:
  - socket handle reuse
- Example:
  - handle `0x1e70` first appeared as `AF_INET6 SOCK_DGRAM proto=0`
  - later the same numeric handle was reused for `AF_INET SOCK_STREAM proto=6`
  - the old tracking logic still treated it as `udpKnown=true`, which polluted the post-queue UDP analysis
- The hook was updated so that:
  - new socket creations always refresh classification for that numeric handle
  - non-UDP socket creation clears any stale UDP/REP-candidate state for the reused handle
  - `closesocket`
  - `WSPCloseSocket`
  - `NtClose` on known UDP handles
    now clear the tracked socket state too
- Goal of the next confirmed post-queue run:
  - eliminate false `udpKnown=true` carryover from handle reuse
  - so any future active UDP handle near REP startup is classified cleanly

### First clean post-queue run after handle-reuse fix

- Archived Frida run `20260421_175345_archived_frida` was a confirmed good REP-handoff run:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- Internal REP behavior still did not change:
  - `start helper` entered
  - `transport ctor` entered and succeeded
  - `secure init` entered and returned `0`
  - `repObj+0x118` stayed non-null
  - `repObj+0x601` stayed `0`
  - `rep.vtbl+0xa8` kept returning `0`
- After the handle-reuse fix, the earlier false UDP positives disappeared:
  - no post-queue active sockets were misclassified as `udpKnown=true`
  - no `[rep-sock] correlate ...` hits were produced
  - later socket activity near failure was cleanly classified as non-REP/non-UDP or unrelated traffic
- Current best conclusion:
  - the archived client still reaches REP handoff cleanly
  - the immediate REP object/transport setup succeeds
  - but we still do not see the real active outbound REP socket become visible through current object correlation

### Transport-object diff tracking

- The current best upstream dependency is still the non-null object at:
  - `repObj + 0x118`
- Ghidra and prior Frida runs already showed:
  - `repObj+0x118` becomes non-null after `rep.vtbl+0x18`
  - `repObj+0x601` never flips to `1`
  - the ready setter/resetter paths never fire
- `tools/frida_dtls_hook.js` now keeps a per-transport snapshot cache and logs only actual field transitions for:
  - `+0x60`
  - `+0x68`
  - `+0x164`
  - `+0x168`
  - `+0x169`
  - `+0x16a`
  - `+0x1b0`
- The diff logging is emitted from:
  - REP vtable `+0x08/+0x10/+0x18/+0xa8`
  - transport ctor enter/leave
  - hooked transport vtable methods
  - initial transport-object hook install
- Goal of the next confirmed post-queue run:
  - identify which transport fields or nested pointers actually move between `rep.vtbl+0x18` and the endless readiness poll
  - and use those transitions to choose the next direct internal hook target above the stalled REP ready gate

### First transport diff result

- Archived run `20260421_182715_archived_frida` was a confirmed good post-queue run:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- The new transport diff logging fired successfully.
- At first sight of the transport object, before ctor work completed, these fields still looked like junk/uninitialized data:
  - `+0x60`
  - `+0x68`
  - `+0x164 = 2`
- During transport ctor completion, the first real transition was:
  - `+0x60: 0x7573222c303a2264 -> 0x1f043e0ade0`
  - `+0x68: 0x22646574726f7070 -> 0x1f043e0add0`
  - `+0x164: 2 -> 0`
- After that normalization:
  - no further transport-field transitions were observed before the REP ready poll stalled
  - the ready byte still stayed `repObj+0x601 = 0`
- Next step:
  - hook the nested sub-objects at `transport+0x60` and `transport+0x68`
  - because those are now the only clearly meaningful transport-side pointers that change during ctor before the stall

### First transport sub-object result

- Archived run `20260421_195314_archived_frida` was another confirmed good post-queue run:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- The transport diff result repeated cleanly:
  - `transport+0x60` normalized from junk to a stable pointer
  - `transport+0x68` normalized from junk to a stable pointer
  - `transport+0x164` flipped `2 -> 0`
- However, none of the first-pass nested sub-object hooks fired before the REP ready poll froze:
  - no `transport+0x60` `+0x08/+0x10/+0x18`
  - no `transport+0x68` `+0x08/+0x10/+0x18`
- Current conclusion:
  - the nested objects at `transport+0x60` and `transport+0x68` are real and stabilize during ctor
  - but the REP-ready failure is still happening before any of those first-pass vtable slots are invoked
- Next step:
  - widen the sub-object vtable coverage beyond `+0x08/+0x10/+0x18`
  - specifically add `+0x20/+0x28/+0x30/+0x48` for both nested sub-objects

### First widened sub-object result

- Archived run `20260421_204517_archived_frida` was another confirmed good post-queue run:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- The widened sub-object hooks finally produced a live nested-method signal:
  - `transport+0x68->vtbl+0x48` fired repeatedly during the REP-ready stall
  - no other widened `transport+0x60` / `transport+0x68` slots fired on that run
- The repeated return value was stable and pointer-like:
  - `ret=0x7b268f90c8`
- Also notable on this run:
  - `start helper leave ret=0x0`
  - but `repObj+0x601` still never flipped and `rep.vtbl+0xa8` still kept returning `0`
- Current best conclusion:
  - the readiness stall is no longer just “somewhere under transport”
  - it is now tightly associated with the repeatedly-called nested path:
    - `transport+0x68 -> vtbl+0x48`
- Next step:
  - hook the object returned by `transport+0x68->vtbl+0x48`
  - inspect whether methods on that returned object are the actual last internal gate before REP becomes ready

### Repeated `transport+0x68->vtbl+0x48` result

- Archived run `20260421_205113_archived_frida` was another confirmed post-queue run:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- The main repeated live signal stayed the same:
  - `transport+0x68->vtbl+0x48` fired over and over during the REP-ready stall
  - the return value stayed stable and pointer-like:
    - `ret=0x5bfdfd8d08`
- This run also reverted to:
  - `start helper leave ret=0xffff`
- What did **not** happen:
  - no `[rep-retobj] ...` calls fired from the current “returned object” hook pass
  - `repObj+0x601` still never flipped
  - `rep.vtbl+0xa8` still kept returning `0`
- Current best conclusion:
  - the most concrete live gate is now the repeatedly-called nested method:
    - `transport+0x68 -> vtbl+0x48`
  - the follow-on returned-object hook did not yet produce signal, so the next best move is to reverse that concrete method directly in Ghidra rather than keep widening generic Frida hooks blindly

### Ghidra result for `transport+0x68->vtbl+0x48`

- The concrete method behind the repeated live path was mapped in Ghidra:
  - runtime target: `0x7ff61ef8dc90`
  - archived RVA: `NewWorld.exe+0x46dc90`
  - Ghidra address: `0x14046dc90`
- Decompiled result:
  - `longlong Transport68_GetInnerPtr(longlong param_1) { return param_1 + 8; }`
- So the repeatedly-called nested method is only a trivial getter:
  - it returns `this + 8`
  - it is not itself doing the REP-ready work
- Ghidra was updated:
  - renamed to `Transport68_GetInnerPtr`
  - decompiler comment added documenting the REP-stall observation
- Next step:
  - capture a one-shot backtrace for the repeated `transport+0x68->vtbl+0x48` live call
  - then map that caller chain back into Ghidra, because the real gate is now above this trivial getter, not inside it

### Caller-chain result above the trivial getter

- Archived run `20260421_212756_archived_frida` produced a clean one-shot backtrace for the repeated live getter call:
  - `[rep-subobj] transport+0x68+0x48 bt ...`
- The most useful module-relative callers in that chain were:
  - `NewWorld.exe+0x64b2b73`
  - `NewWorld.exe+0x650144b`
  - `NewWorld.exe+0x6519860`
  - `NewWorld.exe+0x7158cbf`
  - `NewWorld.exe+0x6dbd146`
  - `NewWorld.exe+0x646cf35`
  - `NewWorld.exe+0x646d3c5`
- Ghidra follow-up:
  - `NewWorld.exe+0x46dc90` / `0x14046dc90` was confirmed as the repeated getter:
    - `Transport68_GetInnerPtr(this) { return this + 8; }`
  - `NewWorld.exe+0x5012f0` / `0x1405012f0` is now the strongest new target above that getter path.
- `FUN_1405012f0` behavior from Ghidra:
  - builds a `"%s::%s::Getter"` object via `FUN_140530930`
  - stores that object at `param_1 + 0x58`
  - checks it through vtable slots:
    - `+0x40`
    - `+0x50`
- Current conclusion:
  - the repeated `transport+0x68->vtbl+0x48` call is only feeding a higher-level `Getter` object path
  - the next useful runtime instrumentation target is that `Getter` object stored at `+0x58`, not the trivial getter itself
- Next step:
  - hook `FUN_1405012f0` directly
  - hook the object stored at `owner+0x58`
  - log its `vtbl+0x40` / `vtbl+0x50` calls on the next good post-queue archived run

### `FUN_1405012f0` broad-hook failure and narrowing

- Archived run `20260421_213756_archived_frida` did **not** reach the usual REP boundary. The game stalled on the first loading screen and the Frida output exploded.
- Root cause from `session.log`:
  - the new direct hook on `FUN_1405012f0` fired far too early and broadly during unrelated startup code
  - the first captured backtrace was clearly not REP-related; it was dominated by audio/renderer paths
  - example first backtrace:
    - `NewWorld.exe+0x48b623`
    - `NewWorld.exe+0x4f42444`
    - `NewWorld.exe+0x137a50e`
    - `NewWorld.exe+0x11c3fe2`
    - `NewWorld.exe+0x6edb1a`
- Side effect:
  - the hook created many unrelated `Getter` objects
  - `owner+0x58->vtbl+0x50` then spammed heavily during startup
  - `owner+0x58->vtbl+0x40` also repeatedly failed Frida attach at the same code address
- Current conclusion:
  - `FUN_1405012f0` is reused in multiple non-REP systems
  - it must be gated to the REP-start window, not hooked globally from process startup
- Fix applied:
  - only activate the `FUN_1405012f0` owner logging/handoff after `start helper` opens a short REP-start window
  - skip the unstable `owner+0x58->vtbl+0x40` hook for now
  - keep only the `owner+0x58->vtbl+0x50` hook during the REP window
- Next step:
  - rerun the archived flow with the gated hook
  - verify that `[rep-getter] ...` only appears on good post-queue runs near the REP stall

### Gated `Getter`-object result

- Archived run `20260421_214647_archived_frida` was a good post-queue run again:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - then the usual post-queue REP stall / CTD
- The REP-window gating worked:
  - the new `[rep-getter] ...` lines no longer appeared during first loading-screen startup
  - they only appeared after `start helper` entered on the REP path
- However, the remaining hook target:
  - `owner+0x58->vtbl+0x50`
  - is an extremely hot path once the REP window opens
  - so full per-call logging still produced too much output
- Important conclusion:
  - the hook is now in the right phase of execution
  - but the `+0x50` method must be treated as a hot path and logged in one-shot / capped form only
- Fix applied:
  - keep the REP-window gate
  - cap `owner+0x58->vtbl+0x50` enter/leave logs to a small number
  - add a one-shot backtrace for the first `+0x50` call
- Next step:
  - rerun the archived post-queue path
  - use the first `owner+0x58->vtbl+0x50` backtrace as the next concrete Ghidra target above the hot getter path

### Returned-object path result

- Archived run `20260421_220206_archived_frida` was a good post-queue run and the script captured the whole failure before process termination, even though the client was later closed manually.
- What the run proved:
  - the REP-window gate still worked
  - `start helper` entered and returned `0xffff`
  - the usual REP-ready stall still held:
    - `repObj+0x601 = 0`
    - `rep.vtbl+0xa8 -> 0`
- The new useful signal was not the gated `owner+0x58->vtbl+0x50` path.
  - Instead, the returned-object hooks under:
    - `transport+0x68->vtbl+0x48->ret+...`
    - were the dominant live post-queue path.
- Repeated returned-object slots observed:
  - `ret+0x08`
  - `ret+0x18`
  - `ret+0x20`
  - `ret+0x28`
- `ret+0x28` appears to be especially hot on this REP-stall path.
- Current conclusion:
  - the runtime focus has moved one step deeper again
  - the most promising next internal caller target is now the first `ret+0x28` path above the returned object
- Fix applied:
  - throttle returned-object logging
  - keep only capped enter/leave logs
  - add a one-shot backtrace for the first:
    - `transport+0x68->vtbl+0x48->ret+0x28`
- Next step:
  - rerun another good post-queue archived flow
  - use the first `ret+0x28` backtrace as the next Ghidra target

### First `ret+0x28` backtrace

- Archived run `20260421_222721_archived_frida` was another confirmed good post-queue run:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - then the usual REP-ready stall / error
- The throttled returned-object pass succeeded:
  - the first `transport+0x68->vtbl+0x48->ret+0x28` backtrace was captured cleanly
- Captured backtrace:
  - `NewWorld.exe+0x6c9f72f`
  - `NewWorld.exe+0x0c43461`
  - `NewWorld.exe+0x0d4bbc3`
  - `NewWorld.exe+0x0d92d99`
  - `NewWorld.exe+0x0ce4ed8`
  - `NewWorld.exe+0x143fe81`
  - `NewWorld.exe+0x13f9f30`
  - `NewWorld.exe+0x14a0539`
  - `NewWorld.exe+0x14b620f`
- The REP state itself stayed unchanged during that call:
  - `start helper leave ret=0xffff`
  - `repObj+0x601 = 0`
  - `rep.vtbl+0xa8 -> 0`
- Current conclusion:
  - we now have the next concrete internal caller chain above the hot returned-object path
  - the best next RE target is the `ret+0x28` backtrace chain, starting with `NewWorld.exe+0x6c9f72f`
- Next step:
  - map those RVAs in Ghidra
  - identify which one owns the REP-ready decision above the returned-object hot path

### REP state-machine resolution

- The noisy `0x646...` frames from the REP-window backtraces are not random renderer junk.
- Ghidra confirmed:
  - `FUN_14644a070` (`NewWorld.exe+0x644a070`) is the actual `GameConnection` REP state machine.
  - State `9` logs `GameConnectionWrapper: start REP connection ...`, calls `FUN_146425f20`, then advances to state `10`.
  - State `10` polls:
    - `(**(code **)(**(longlong **)(param_1 + 0x1000) + 0xa8))()`
    - which matches the already traced `repObj->vtbl+0xa8` readiness gate.
  - When that returns nonzero, the state machine starts actor game connection; on failing archived runs it never does.
- Ghidra also confirmed:
  - `FUN_14646d460` (`NewWorld.exe+0x646d460`) wraps `FUN_14644a070`
  - then, if `param_1+0x118` is non-null, it calls:
    - `(**(code **)(**(longlong **)(param_1 + 0x118) + 8))()`
- Current interpretation:
  - the post-queue REP stall is now bounded to the `FUN_14646d460` / `FUN_14644a070` tick path
  - `param_1+0x118->vtbl+8` is a cleaner next runtime target than the earlier hot getter/returned-object helpers
- Frida changes prepared for the next run:
  - added a direct hook for:
    - `FUN_14646d460` (`internal_gameconn_wrapper_tick`)
  - it only logs state `9` / `10`
  - it logs:
    - wrapper pointer
    - state
    - `repObj`
    - `wrapper+0x118`
  - it dynamically hooks:
    - `wrapper+0x118->vtbl+0x08`
  - the very hot `transport+0x68->vtbl+0x48` path is now capped harder to reduce log spam
- Next useful signal expected from the next good post-queue archived run:
  - `[rep-wrapper] tick ...`
  - `[rep-wrapper] wrapper+0x118+0x08 ...`
  - which should tell us what object is actually being serviced while REP remains stuck not-ready

### REP wrapper callback queue

- The latest confirmed good archived REP-handoff run is still:
  - `capture/20260421_224444_archived_frida`
  - `auth_mock` reached:
    - `validator`
    - `CreateCharacter`
    - `login/queue/v2`
    - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- That run confirmed the same deeper stall:
  - `FUN_146425f20` ran
  - `transport ctor` and `secure init` succeeded
  - `repObj+0x118` became non-null
  - `repObj+0x601` stayed `0`
  - `rep.vtbl+0xa8` kept returning `0`
- Ghidra resolution of the wrapper-tick object is now specific:
  - `wrapper+0x118->vtbl+0x08`
  - runtime target:
    - `0x7ff624f8d600`
  - archived RVA:
    - `NewWorld.exe+0x646d600`
  - Ghidra function:
    - `FUN_14646d600`
- `FUN_14646d600` is a callback-queue pump, not a transport/socket routine:
  - queue begin at `+0x38`
  - queue end at `+0x40`
  - queue capacity/end storage at `+0x48`
  - callback object pointer in each 0x40-byte entry at `entry+0x38`
  - callback invoke via callback-object vtable `+0x10`
  - callback destroy via callback-object vtable `+0x20`
- New Frida instrumentation is now in place for the next good post-queue run:
  - log `queueBegin`, `queueEnd`, and `queueCap` on `wrapper+0x118->vtbl+0x08` enter/leave
  - one-shot dump of up to 4 queued entries:
    - entry pointer
    - callback object pointer
    - callback object vtable
- Archived run `capture/20260421_225628_archived_frida` was the first good post-queue run with the queue instrumentation active:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- It answered the queue question directly:
  - `wrapper+0x118->vtbl+0x08` repeatedly logged:
    - `queueBegin=0x0`
    - `queueEnd=0x0`
    - `queueCap=0x0`
  - enter/leave both stayed zero during the entire state-10 REP stall
  - no queued callback entries existed at all
- This rules out the “stuck queued callback in FUN_14646d600” theory.
- Current tighter boundary:
  - REP transport construction succeeds
  - secure init succeeds
  - `repObj+0x118` becomes non-null
  - the wrapper queue pump object at `wrapper+0x118` exists but its callback queue is empty
  - `repObj+0x601` stays `0`
  - `rep.vtbl+0xa8` keeps returning `0`
- New conclusion:
  - the missing REP-ready transition is not waiting in the wrapper callback queue
  - the remaining gate is upstream of queue delivery, in the internal path that should either:
    - set `repObj+0x601 = 1`, or
    - enqueue work into the empty `FUN_14646d600` callback queue

### Returned-object path after empty queue result

- The same good post-queue run also reaffirmed that the only hot internal transport-side method during the stall is:
  - `transport+0x68->vtbl+0x48`
- That method's archived target remains:
  - `NewWorld.exe+0x46dc90`
  - and earlier Ghidra resolution showed it is just a trivial getter returning `this + 8`
- The first caller-chain above that getter remains:
  - `NewWorld.exe+0x64b2b73`
  - `NewWorld.exe+0x650144b`
  - `NewWorld.exe+0x6519860`
  - `NewWorld.exe+0x7158cbf`
  - `NewWorld.exe+0x6dbd146`
  - `NewWorld.exe+0x646cf35`
- Existing returned-object hooks (`ret+0x08/+0x18/+0x20/+0x28`) have not produced useful follow-on calls.
- New runtime pass added for the next good archived REP-handoff run:
  - one-shot raw snapshot of the returned object from:
    - `transport+0x68->vtbl+0x48`
  - logs:
    - returned object pointer
    - vtable pointer
    - vtable slots `+0x08/+0x18/+0x20/+0x28`
    - qword fields at:
      - `+0x08`
      - `+0x10`
      - `+0x18`
      - `+0x20`
      - `+0x28`
      - `+0x30`
      - `+0x38`
- Purpose:
  - determine whether the returned object is actually a meaningful polymorphic object, a thin façade, or mostly a data carrier
  - avoid blind hook widening if the object is not dispatching the slots we previously assumed

### Latest archived REP returned-object snapshot

- Archived run `20260421_230736_archived_frida` was another confirmed post-queue run:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- Internal REP state stayed unchanged during the stall:
  - `start helper leave ret=0xffff`
  - `repObj+0x118` non-null
  - `repObj+0x601` stayed `0`
  - `rep.vtbl+0xa8` kept returning `0`
  - `wrapper+0x118->vtbl+0x08` callback queue stayed empty
- The new raw snapshot proved the hot returned-object path is a real polymorphic object, not junk:
  - `transport+0x68->vtbl+0x48 snapshot obj=0x1edeec4c468 vtbl=0x7ff6270d76f0`
  - live returned-object slot targets:
    - `ret+0x08 = 0x7ff61f1e6a00`
    - `ret+0x18 = 0x7ff61edc1da0`
    - `ret+0x20 = 0x7ff61f1e5990`
    - `ret+0x28 = 0x7ff61f1ecf20`
- The returned-object methods that actually executed on the failing path were:
  - `ret+0x08`
  - `ret+0x18`
  - `ret+0x20`
  - `ret+0x28`
- Observed behavior:
  - `ret+0x08` returned stable pointer-like values
  - `ret+0x18` returned `0` for some `this` values and non-null pointers for others
  - `ret+0x20` was especially hot and returned stable pointer-like values
  - `ret+0x28` produced the first clean caller-chain above the returned-object path:
    - `NewWorld.exe+0x6c9f72f`
    - `NewWorld.exe+0x0c43461`
    - `NewWorld.exe+0x0d4bbc3`
    - `NewWorld.exe+0x0d92d99`
    - `NewWorld.exe+0x0ce4ed8`
    - `NewWorld.exe+0x143fe81`
    - `NewWorld.exe+0x13f9f30`
    - `NewWorld.exe+0x14a0539`
    - `NewWorld.exe+0x14b620f`
- New conclusion:
  - the next useful RE targets are the concrete returned-object methods:
    - `NewWorld.exe+0x1e6a00` (`ret+0x08`)
    - `NewWorld.exe+0x0dc1da0` (`ret+0x18`)
    - `NewWorld.exe+0x1e5990` (`ret+0x20`)
    - `NewWorld.exe+0x1ecf20` (`ret+0x28`)
  - the next runtime pass should capture one-shot backtraces on `ret+0x08/+0x18/+0x20` as cleanly as it already does for `ret+0x28`.

### Follow-up good run after returned-object method backtrace pass

- Archived run `20260421_231626_archived_frida` was another confirmed post-queue run:
  - `validator`
  - `CreateCharacter`
  - `login/queue/v2`
  - `OUTCOME REACHED_LOGIN_QUEUE_V2`
- Internal REP state was still unchanged:
  - `start helper leave ret=0xffff`
  - `repObj+0x118` non-null
  - `repObj+0x601` stayed `0`
  - `rep.vtbl+0xa8` kept returning `0`
  - wrapper callback queue stayed empty
- The new pass did **not** produce any `ret+0x08/+0x18/+0x20/+0x28` method-call logs on this run.
- Only the raw returned-object snapshot appeared:
  - `transport+0x68->vtbl+0x48 snapshot obj=0x9b139e91f8 ...`
- Useful conclusion:
  - the returned object is still present on the failing path
  - but this latest run did not execute any of the concrete returned-object vtable methods we hooked
  - so the boundary is now:
    - after the returned object exists
    - before any of the hooked `ret+0x08/+0x18/+0x20/+0x28` methods are invoked on this specific stall path

### Static re-check of returned-object slot targets

- After the latest runtime boundary, the captured returned-object slot targets were checked again in Ghidra instead of assuming they were all meaningful live methods.
- Result:
  - `NewWorld.exe+0x1e6a00` decompiles to `FUN_1401e6a00`, a tiny init-style helper that sets a global byte via `FUN_1461a95c0(...)`
  - `NewWorld.exe+0x1ecf20` lands inside `FUN_1401ecee0`, another startup/init-style allocator-lock setup helper
  - `NewWorld.exe+0x0dc1da0` is inside `FUN_140dc1cf0`, a generic callback/dispatch-style routine, not an obvious REP transport method
  - `NewWorld.exe+0x1e5990` also lands in an init-style region near `FUN_1401e58f0`
- New conclusion:
  - the raw returned-object slot values are not reliable enough to keep treating as clean REP vtable methods
  - the better next runtime signal is field mutation on the returned object itself, not more blind method-hook expansion on those slot addresses
- New runtime pass:
  - keep the first raw returned-object snapshot
  - then diff the returned-object fields over time:
    - `vtbl`
    - `slot08/18/20/28`
    - `q08`
    - `q10`
    - `q18`
    - `q20`
    - `q28`
    - `q30`
    - `q38`
  - purpose: detect whether the returned object is being populated later on the failing REP stall path even when none of the hooked returned-object methods fire

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

---

## 2026-04-23: DTLS trust gate bypassed, first full handshake

### Headline

The archived non-EAC build (`G:\NewWorldArchive\GameClient\Bin64\NewWorld.exe`) now completes a full DTLS 1.2 handshake against our self-signed cert at `127.0.0.1:23971`. No `unknown ca` alert. Client accepts `CN=New World` server cert, finishes key exchange, writes `Finished`, and immediately sends application data (the first Javelin record). The 4-month cert-trust wall is down.

### What works

- **Trust bypass via Frida onEnter hook** on `FUN_145dce750` (`Javelin_SecureSocketDriver_Initialize`), RVA `0x5dce750`. Hook nulls `param_1[0x51]` (the 8-byte `verifyField` pointer at `ctx+0x288`) before the function body runs. The function's own `JZ` at `0x145dce8b5` then naturally takes the permissive branch, which calls `SSL_CTX_set_verify(..., FUN_1402a1a70)` — the always-return-1 callback. No byte rewrite, no code-flow change, SSL_CTX ends up cleanly configured.
- **Frida spawn-attach on the archived build** with the patch + capture hook both loaded while the process is still suspended. EAC blocks this on live Steam, so only the archived build is usable.
- **Full DTLS 1.2 handshake reaches `write finished` on both sides.** Captured in `capture/dtls_probe_20260423_151655.log`.
- **REP state machine transitions state 9 → state 10** for the first time in any session (`capture/20260423_152727_archived_probe_running/session.log`). State 10 is post-secure-init, waiting on server-sent Javelin messages.

### Why the initial byte-patch attempt broke the client

The first version of the trust patch (`frida_dtls_trust_patch.js` pre-rewrite) replaced the `JZ +0x119` at `0x145dce8b5` with `JMP +0x119` + NOP — forcing the permissive branch unconditionally. **Symptom:** client created the REP UDP socket but never emitted a single datagram; 2.68 s later the process died silently. **Root cause:** with `verifyField` still non-null, forcing the JMP past the strict branch skipped its CA-list setup, leaving the SSL_CTX half-wired. The DTLS state machine couldn't start the handshake. Replacing the byte patch with a data-level `onEnter` hook (null the field and let the function's own branch logic run) fixed it cleanly.

### Why the probe saw bytes, then stopped seeing bytes

Two separate issues:

1. **`-quiet` + `stdin=DEVNULL`** causes `openssl s_server` to send `close_notify` the instant its stdin reaches EOF (immediately after the handshake). Client retries indefinitely, each handshake succeeds, each gets torn down before any app data can be decrypted. Captured repeatedly in `dtls_probe_20260423_151655.log`.
2. **Switching `stdin` to `subprocess.PIPE`** (my first fix attempt) hung `s_server` on Windows: its POSIX-style `select()` event loop can't multiplex a blocking pipe-read with the UDP socket, so the accept loop never services incoming datagrams. Empty probe log, silent client failure.

Final fix: `stdin=subprocess.DEVNULL` + `-ign_eof` flag. `-ign_eof` tells `s_server` to not shut down on stdin EOF; works with DTLS (`-rev` does not).

### State of the tooling

- `tools/frida_dtls_trust_patch.js` — onEnter hook form. Installs `Interceptor.attach` on `FUN_145dce750`, zeros `ctx+0x288` before entry. Emits a `[trust-bypass] zeroed verifyField ctx=... was=0x...` line each call.
- `tools/frida_capture.py` — spawn flow loads the trust-patch script *first* (while process is still suspended), then the main hook script. `--no-patch-trust` disables it. Both scripts load in order, both hooks install before `device.resume(pid)`.
- `tools/dtls_probe.py` — `openssl s_server -dtls1_2 ... -ign_eof` wrapper. Binds `0.0.0.0:23971`, stays alive past handshake, logs everything via `-msg -debug -state`.
- `server/certs/server.crt` + `server.key` — self-signed cert matching `CN=New World, OU=Amazon Game Studios`. Client accepts this once trust bypass is active.

### Where we are, exactly

The probe at `151655` **captured a complete encrypted Javelin record** post-handshake at line 405:
```
17 fe fd 00 01 00 00 00 00 00 01 00 3b  [59 bytes of encrypted app data]
```
— but openssl was shutting down, so those bytes never got decrypted. With `-ign_eof` in place, the next probe run should decrypt and dump the record, giving us our first real Javelin message to parse.

### Next action

1. Re-run the three-terminal flow with the fixed probe:
   ```
   python -m server.auth_mock --port 443
   python tools\dtls_probe.py
   python tools\frida_capture.py --exe "G:\NewWorldArchive\GameClient\Bin64\NewWorld.exe" --name archived_probe_running
   ```
2. Character-create → enter world. Let it run 15–20 s.
3. In the probe log, look for `SSL_accept:SSLv3/TLS write finished` followed by **decrypted application-data hex blocks** (no `close notify` in between).
4. The first decrypted block is the client's first Javelin message. Feed its bytes into `server/javelin/frame.py:parse_datagram()` to identify the message type and fields.
5. From the parsed record, build the minimum server-side response the client expects (probably the auth/welcome message handled by `FUN_146b6f190` — that handler sets `repObj+0x601 = 1` when the right message arrives, per prior RE notes).
6. Start a new module `server/rep_responder.py` that terminates DTLS (self-signed cert) and speaks Javelin to the client. Initially just echoes the parsed bytes; iteratively add the handshake/auth response.

## 2026-04-23 (later): First decrypted Javelin records, Carrier envelope decoded

Major progress: the DTLS probe now captures clean post-handshake plaintext, the Javelin parser was patched to handle the real on-wire envelope, and we identified exactly what the client is asking for (and not getting).

### What worked

- **Probe wrapper rebuilt.** `tools/dtls_probe.py` now spawns `openssl s_server` with `stdin=None` (inherits parent console handle from PowerShell). DEVNULL/synthetic-pipe stdins all triggered immediate `s_server` exit on Git-for-Windows openssl 1.1 — confirmed it requires a real console handle. `-ign_eof` did not help. Captured stdout via `subprocess.PIPE` to preserve raw bytes; PowerShell's `*>` redirect was destroying ~half the bytes by re-encoding them through the OEM codepage.
- **Plaintext extracted.** `tools/extract_probe_plaintext.py` finds every decrypted application_data record in the log. `s_server -msg` does NOT fire `content_type=23` callbacks — instead it writes decrypted bytes raw to stdout between debug lines. The extractor walks the file, locates record-header callbacks, and slices the bytes immediately following each one. 149 plaintext chunks recovered from a single 30-second session.
- **Carrier envelope decoded.** Decompiled `Javelin_Carrier_ParseMessages @ 0x140f77eb0` and its caller `FUN_140f898e0`. Each post-DTLS datagram has a 4-byte Carrier envelope before the inner record stream:
  ```
  type   : u8       0x80 = plaintext records, 0x81 = encrypted/compressed
                    (high bit set, bits 1-6 must be 0)
  proto  : u8       must be 0x01
  seq    : u16 BE   per-datagram sequence
  ```
  Bit 0 of `type` (i.e. `type == 0x81`) routes the body through `param_1[5]` (cipher/compressor); `0x80` passes the body straight to `parse_datagram()`. Added `parse_envelope()` to `server/javelin/frame.py`.
- **Inner record parser confirmed correct.** With the envelope stripped, `parse_datagram()` parses **all 149 captured datagrams with zero trailing bits.** The original parser was right about the per-record encoding (8-bit flags, BE u16 size in bytes, conditional channel/numChunks/sequence/relSeq, then size bytes of payload). Just nobody had ever fed it real wire bytes.
- **Identified the message the client wants.** Every datagram is on channel 3 (system) with `MF_CONNECTING`. Each datagram is `1..N × SM_CONNECT_REQUEST` (msgId=1) followed by `1 × SM_CT_ACKS` (msgId=6). The client is sending these on a tight retry loop, waiting for an `SM_CONNECT_ACK` (msgId=2) we never reply with. SM_CONNECT_REQUEST body is `00 00 00 05 01` on first send, growing by one `01` byte per retry. SM_CT_ACKS body is constant `20 06`. After ~3 seconds of unanswered retries the REP state machine (state 10 with `repObj+0x601 = 0`) gives up and the client process terminates — same CTD pattern as before.

### Where we are right now

REP state 10 stalls. The handshake-then-CTD cycle is fully understood. The blocker is **we have no way to send back into the DTLS connection** — `openssl s_server` is a sink, not a server we can drive. The next step is to replace it with something we control end-to-end.

### Next action

1. **Build `server/rep_responder.py`.** A real DTLS server in Python. Three reasonable paths:
   - **A.** Pure-Python with `pyOpenSSL` or the `Dtls` PyPI package. Most flexibility, longest setup. Requires verifying DTLS 1.2 server mode actually works on Windows.
   - **B.** Wrap `s_server` with bidirectional pipes. Spawn it from Python with `stdin=PIPE` and write replies into stdin (s_server encrypts and sends). Read decrypted client bytes from stdout. Hacky but reuses the working crypto.
   - **C.** Frida-side test: inject a synthesized SM_CONNECT_ACK directly into the client's receive path to validate the message contents before committing to a real server.
2. **Identify SM_CONNECT_ACK contents.** The client's connect-handshake state machine handler is unidentified; search downstream of `FUN_140f66430` (the queue dispatcher called by ParseMessages for msgId<6) or look for the SM_CONNECT_REQUEST builder/serializer to mirror its structure. A blank ACK body might suffice; if not, we'll need the binary's expected fields.
3. **Wire envelope on send.** Marshal records via existing `marshal_datagram()`, prepend `b'\x80\x01' + struct.pack('>H', seq_out)`. Per-datagram sequence is independent of inner record sequences.

### Important notes

- `tools/dtls_probe.py` capture file: `capture/dtls_probe_20260423_164554.log` is the canonical "all 149 records" snapshot. Keep it for offline parser/responder development — no need to re-run the game on every iteration.
- PowerShell redirect (`*>`/`>`) is byte-destructive for raw streams. Always either let Python capture via `subprocess.PIPE` or wrap commands in `cmd /c "... > file 2>&1"` (cmd.exe `>` is byte-faithful).
- The encrypted/compressed envelope path (`type == 0x81`) is unimplemented and currently un-triggered — the client doesn't seem to use it during connect. If it shows up later, we'll need to find which cipher/compressor the binary is using.

## 2026-04-23 (experiment B): force `repObj+0x601 = 1` to test for shortcut

Goal: before committing to building a real DTLS responder, sanity-check whether the wrapper state machine can be made to advance just by flipping the `0x601` ready flag in the rep object. If yes, the carrier handshake matters but isn't actually load-bearing for state advance and we have flexibility. If no, building the responder is unavoidable.

**Patch:** Added `EXPERIMENT_FORCE_REP_READY` flag to `tools/frida_dtls_hook.js`. When the wrapper tick fires with `state == 10` and reads `repObj+0x601 == 0`, write `1`. Otherwise pure observation.

**Result:** Carrier handshake is required. No shortcut.

- The force fired exactly once at 17:51:35.670 (then stayed set, no resets).
- `rep.vtbl+0xa8` immediately changed return value from `0` → `1` (so it WAS reading 0x601 directly as a sub-gate).
- A downstream sub-object event loop started: `transport+0x68+0x48` cycled through 9 vtables (`0xb07e6c57 → 0x26b4094a → 0xdcbb3429 → 0xea5cc214 → 0x1053ff77 → 0x27029ea9 → 0xdd0da3ca → 0xe382a943 → 0x198d9420 → 0xb07e6c57`) with `q08` ticking 0→1→2→3 in a tight loop. **22,341 vtable transitions** during the experiment window. Looks like an internal carrier-side state machine that was previously starved.
- **Wrapper state never left 10.** Only 9 and 10 ever appeared.
- Client sent **no new message types** over the wire — same 197 datagrams of `SM_CONNECT_REQUEST + SM_CT_ACKS` retries.
- Game lived **22.7 seconds** post-force vs ~3 seconds without. Then clean `process-terminated` (no `csdkerr`, no MessageBox, no abort, no TerminateProcess hit).

**Interpretation:** `0x601` is a status flag downstream of carrier connect — setting it manually unblocks one local check (`vtbl+0xa8` returns 1) and starts the internal ack-pump loop, but the wrapper state machine has its own check looking at actual carrier-handshake completion (presumably reads received SM_CONNECT_ACK or an internal "carrier connected" flag elsewhere). The 22-second timeout is a different watchdog than the original 3-second one. Eventually the client decides the connection is dead and process-exits cleanly.

**Good news:** the rest of the REP machinery is wired and ready — once we send a proper `SM_CONNECT_ACK`, things should cascade. This is now firmly a "build the responder" problem, not a "find more gates" problem.

**Patch left in place** (gated by `EXPERIMENT_FORCE_REP_READY = false`) for future re-testing if needed.

### Next: `server/rep_responder.py`

The responder must:
1. Terminate DTLS 1.2 with our self-signed `server/certs/server.crt`/`server.key` (replacing `openssl s_server`).
2. Parse incoming Javelin via `parse_envelope` + `parse_datagram`.
3. On receiving a `SM_CONNECT_REQUEST` (channel=3, msgId=1), reply with `SM_CONNECT_ACK` (msgId=2).
4. Wire each outbound datagram with the 4-byte Carrier envelope: `b'\x80\x01' + struct.pack('>H', out_seq)`.
5. Almost certainly need to ack received reliable messages via `SM_CT_ACKS` too.

**Open question that gates everything:** what's the SM_CONNECT_ACK payload format? Captured `SM_CONNECT_REQUEST` body is `00 00 00 05 01` (msgId at end → body = `00 00 00 05`). The corresponding ACK structure isn't known. Three ways to find out:
- RE the binary's connect-handshake state machine (search downstream of `FUN_140f66430` queue dispatcher for the channel-3, msgId-2 case).
- RE the SM_CONNECT_REQUEST builder (where `00 00 00 05` is constructed) — the symmetric ACK builder is usually nearby.
- Try empty payload (`02` only) first; if the client rejects, iterate.

**DTLS server library options for the responder:**
- **pyOpenSSL**: production-grade OpenSSL bindings. DTLS support exists but is sparsely documented. Best long-term choice if it works on Windows.
- **`Dtls` PyPI package**: thin OpenSSL wrapper specifically for DTLS. May be unmaintained.
- **Subprocess pipe to s_server**: spawn openssl with `stdin=PIPE` from Python and write our reply bytes to stdin (s_server encrypts and forwards). Read decrypted client bytes from stdout. Hacky but reuses already-validated handshake. Good for first iteration.

## 2026-04-23 (later): Sender hunt — six candidates, zero hits

After payload iteration exhausted itself (mirror/empty/echo/v0/dynamic all carrier-acked but app-rejected), pivoted to finding the SM_CONNECT_REQUEST builder via Frida hooks. Decompiled and hooked SIX candidate sender functions across multiple sessions:

- `FUN_140f805f0` — public msgId+bitstream sender (calls FUN_140f66850 with channel=3)
- `FUN_140f66850` — generic message-record queuer (8 callers per Ghidra xref)
- `FUN_140f80770` — inline ack sender (confirmed for msgIds 6 & 7 in Ghidra)
- `FUN_140f7fe50` — contains literal `0x05000000` constant (= byte-swapped BE form of `00 00 00 05`, the body bytes we observe)
- `FUN_140f802e0` — sister candidate
- `FUN_140f80440` — confirmed SM_CLOCK_SYNC sender (msgId=4)

**ALL SIX install correctly. NONE fire during the connect attempt.** Verified via runtime byte-prologue dump that the addresses point at the correct functions (matches Ghidra disassembly exactly). Even the SM_CLOCK_SYNC sender (which a normally-running client uses regularly) doesn't fire — consistent with the connection never advancing past the carrier-pre-connect state.

**Conclusion:** The SM_CONNECT_REQUEST builder is on a code path that doesn't intersect any of these obvious carrier-sender functions. Strongest hypothesis: the body lives in a shared buffer in the channel struct (FUN_140f7fe50 reads bitstream pointers from offsets +0x138/+0x140 and +0x160/+0x168), and some background tick mutates the buffer in place (one `0x01` byte appended per retry) while re-queueing the same MessageRecord. The MessageRecord allocation may happen ONCE during channel setup.

### Better next moves

The Frida-hook-everything approach has hit diminishing returns. Better paths from here:

1. **Hook `FUN_140f8ab70` (transmission tick) entry** — walk the channel send queue at +0x90/+0xa0 *at that moment*, dump pending MessageRecords. If SM_CONNECT_REQUEST records are visible, we know the queue offset and can hook memory writes to find the appender.
2. **Hook `FUN_140f8bfd0` (BitStream::WriteBits)** with a filter for writes containing the magic `00 00 00 05` bytes — catches whoever mutates the body buffer.
3. **Open Ghidra UI directly** — MCP can't see all unidentified-function regions in the binary. Manual inspection of the channel struct allocator and its callers may reveal the builder faster than more Frida iteration.

Per `feedback_character_select_unreliable` (~10 min wall-clock per attempt), the value-per-iteration calculus increasingly favors deeper static analysis over more runtime A/B/C cycles.

## 2026-04-23 (FINAL): Carrier path is bypassed; pivot needed

Hooked the absolute-final serializer `FUN_140f65b20` (Carrier_WriteMessages) at the entry point. EVERY outbound MessageRecord on a standard Javelin Carrier channel should pass through this. Run with character creation completed and 22 SM_CONNECT_REQUEST datagrams received by responder — `[carrier-write] enter` **never logged**.

This is the seventh carrier-layer function we've hooked that doesn't fire. RVA validator confirmed all addresses correct. The conclusion is final: **the REP DTLS connection's transmission path completely bypasses the standard Javelin Carrier code in this binary.** Whatever sends SM_CONNECT_REQUEST is either a REP-specific mini-carrier (embedded in the transport struct — possibly the `transport+0x68+0x48` subobject pattern we observe cycling vtables in our session logs) or direct byte-construction passed straight to SSL_write/BIO_write without going through the Carrier framework at all.

### Pivot — better attack vectors

The carrier-path search has run its course. Three productive directions:

1. **Hook `SSL_write` / `BIO_write` (currently `not_found` via export scan).** OpenSSL is statically linked. A signature-based search for the SSL_write prologue would let us hook every plaintext byte just before encryption — independent of what Carrier code is in use. Backtrace from the hook would name the actual sender.
2. **Hook the SM_CONNECT_ACK *receive* path instead of looking for the sender.** We know our ACK reaches the binary (the responder logs show carrier-level acks). Whatever processes inbound msgId=2 reads the body fields the connect handler expects. Finding that gives us the same answer (what fields SM_CONNECT_ACK needs) as finding the sender, from the opposite direction.
3. **Manual Ghidra UI exploration.** MCP can't see unidentified-function regions in the binary, and there are clearly many of them. Tracing forward from the REP transport ctor `FUN_146b6a270` and following the `transport+0x68+0x48` subobject cycling pattern (which we see actively running in every Frida session) is where the REP-specific code lives. Human-driven UI navigation will be much faster than continued MCP/Frida iteration.

Tonight's net: durable infrastructure is built (DTLS responder, parser, envelope, ack-iteration scaffold), and we've definitively ruled out 7 candidate functions. We know the search space is NOT the standard Carrier — the answer lies in REP-specific code or below the Carrier layer at the SSL boundary. That's a meaningful narrowing even if the gate isn't open yet.

## 2026-04-23 (truly final): ParseMessages also bypassed — REP has parallel implementation

Tried option 2 from above: hooked `FUN_140f77eb0` (Carrier_ParseMessages) — the supposed-only inbound parser, called only from FUN_140f898e0 per Ghidra xref. Run with character creation completed; responder shows `new peer` connection. ParseMessages **never fires**.

This makes EIGHT carrier-layer functions that don't fire during the REP connect. RVA validator confirmed all addresses correct. The conclusion is now unambiguous and high-confidence:

**The REP DTLS code uses an entirely separate parallel Javelin implementation.** All our successfully-firing hooks are in the 0x14[5-6]______ region (FUN_146b6a270, FUN_14646d460, FUN_146b6f190, FUN_14644a070, FUN_146425f20). All our silent hooks are in 0x140f______ (the standard Carrier code). Two completely different code regions. The Carrier code we've been studying is presumably for game-data channels or a different transport — NOT for the REP DTLS handshake.

Same wire format (envelope + records — we've confirmed parsing), different implementation. Likely the REP transport struct embeds its own miniature carrier; the `transport+0x68+0x48` subobject cycling we see active in every session is probably that mini-carrier's per-tick processing loop.

### Where to go from here

Manual Ghidra UI exploration of the REP region is the highest-leverage move. Specifically:
- Start at `FUN_146b6a270` (transport ctor) and follow xrefs forward
- Decompile the transport+0x60 and transport+0x68 vtable methods (we observed those cycling)
- Look for functions that construct `00 00 00 05` followed by msgId byte 0x01

Alternative: implement byte-pattern signature scanning for SSL_write (the static-linked OpenSSL has stripped names; current export+string-xref fallback fails). Hooking the SSL boundary would let us catch every plaintext bytestream and backtrace the sender, completely independent of what carrier code is in use.

The Frida iteration approach has run its course — eight functions ruled out is meaningful narrowing, but further blind-hooking is unlikely to hit the right address without static analysis input.

## 2026-04-23 (truly truly final): GridMate-Carrier breakthrough via string enumeration

Did one more pivot before stopping: enumerated strings in the binary looking for Connect/Register/Carrier/Javelin keywords. **Massive payoff** — the REP protocol is not what we thought:

**It's Amazon's GridMate-Carrier middleware**, not generic Javelin Carrier. Messages are identified by 16-byte GUIDs, with named types like:
- `RegistrationRequestV3Msg` (current variant — log line says "Client connection using authtoken V3 registration message type")
- `RegistrationRequestV2Msg`, `RegistrationRequestMsg` (older variants)
- `RegistrationResponseMsg`

The transport identifies as `"GridMate-Carrier"` (string at 0x147fbe7e8) and uses a state machine with labels like `CS_WAIT_FOR_STATEFUL_HANDSHAKE`, `CS_SSL_HANDSHAKE_ACCEPT`, `CS_SSL_HANDSHAKE_CONNECT`.

**This explains why all 8 Carrier hooks were silent:** the Javelin Carrier code at 0x140f______ is for a different subsystem entirely. The REP DTLS uses GridMate-Carrier.

**Concrete identifications:**
- `FUN_1464755e0` is the **RegistrationResponseMsg receive handler** — logs the "received registration response" line, then reads `(server_version, string)` from the response.
- `FUN_1407f2c50` and `FUN_1407f2e80` are static initializers for the V3-Request and Response message type info.
- `FUN_140235010` is a huge GUID lookup-table initializer parsing ~17 message-type GUIDs into consecutive 16-byte slots starting at `DAT_14a4357f0`. The msgId byte we observe in carrier records (0x01, 0x02, etc.) likely indexes into this table — the byte ISN'T a generic SystemMessageId; it's a per-table index into GridMate-Carrier's message type registry.

**Reinterpretation of captured wire bytes:**
The body `00 00 00 05 01` we've been treating as `[magic 5][msgId 0x01]` is more likely:
- `00 00 00 05` = some carrier-level field (length, version, or header)
- `01` = INDEX into GridMate-Carrier's message-type GUID table → identifies `RegistrationRequestV3Msg`

The growing-body pattern across retries (`00 00 00 05 01`, `00 00 00 05 01 01`...) might be retry counters or session/sequence info appended on each attempt.

**Bonus discovery:** GridMate is **open-source** — it's part of Amazon Lumberyard / Open 3D Engine. Public SDK reference implementations should exist. Future research can pull message format definitions from there directly instead of pure RE.

### Truly real next steps (next session)

1. **Read the actual GUID bytes** at 0x147f47ec0 (RegistrationResponseMsg), 0x147f48660 (V3 Request), 0x147f48528 (V2 Request) — those are the type identifiers we need.
2. **Look up GridMate source** in Open 3D Engine repo on GitHub. The `RegistrationRequestV3Msg` definition there is likely directly applicable.
3. **Decompile `FUN_146460240`** (event dispatcher called from FUN_14642d950 with various event codes — likely the trigger that schedules registration).
4. **Find xrefs to the parsed GUID slots** (e.g., DAT_14a435920) once we know which slot holds which type — that gives us all the use sites.

This is the unblocking thread. Stop tonight — fresh eyes for next session will move much faster with GridMate as the search keyword.

## 2026-04-23 (final-final-final): RegistrationResponseMsg in-memory struct decoded

Pushed further into the breakthrough. Extracted the 3 GUIDs:
- RegistrationResponseMsg: `104145a7-ff95-44f1-9468-21fb41c8ac2b`
- RegistrationRequestV2Msg: `DA4E5889-A65C-4480-8642-0278160125A7`
- RegistrationRequestV3Msg: `0B826B33-89F5-49E0-B8CB-FE4433427778`

Decompiled `FUN_146b6f190` — the function whose hook fires `repObj+0x601=1`. It's a **massive type-cascade message dispatcher**. When a RegistrationResponseMsg arrives via `param_2`, the success path:

```c
lVar20 = *param_2;                              // message data ptr
if (cVar8 != '\\0' /* IS RegistrationResponseMsg */) {
    if (param_1[0xc0] == 0) {                   // not yet authorized
        param_1[0xc0] = 1;
        if (*(int *)(lVar20 + 8) == 0) {        // error_code MUST be 0
            if (*(char *)(lVar20 + 0x5b) == 0) { // eos_flag MUST be 0
                // Extract session_token string from lVar20+0x18 (24-byte AZStd::string)
                // Copy lVar20+0x58/0x59/0x5a → param_1+0xde/0x6f1/0x6f2
                *(undefined1 *)((longlong)param_1 + 0x601) = 1;  // ← THE FLAG
                FUN_146b66e70(...);             // state advance
            }
        }
    }
}
```

**RegistrationResponseMsg in-memory layout:**
| Offset | Type | Field | Notes |
|---|---|---|---|
| 0x00 | void* | header | pointer |
| 0x08 | int32_t | error_code | **MUST be 0 for success** |
| 0x0c | int32_t | pad | |
| 0x10 | void* | string_buf_ptr | |
| 0x18 | AZStd::string | session_token | 24 bytes |
| 0x38..0x57 | bytes | (transport endpoints?) | |
| 0x58 | uint8_t | status_a | → param_1+0xde |
| 0x59 | uint8_t | status_b | → param_1+0x6f1 |
| 0x5a | uint8_t | status_c | → param_1+0x6f2 |
| 0x5b | uint8_t | eos_error_flag | **MUST be 0** |

This is the IN-MEMORY layout the binary CONSUMES after deserialization. The wire-format SERIALIZATION is the remaining unknown — likely lives in the type's vtable methods at `PTR_FUN_147f46910` (referenced by both `FUN_1407f2e80` and `FUN_1407cd200`).

**Key hooks already in place** that can verify our work:
- `internal_rep_ready_setter` hooks FUN_146b6f190 entry — we'll see this fire IF and ONLY IF our packet reaches the dispatcher with the right type ID.
- The setter hook reads `repObj+0x601` before/after — once a properly-formed packet arrives, we should see `readyAfter=1`.

Nine other type-cascade slots (FUN_1407f6a30/2370/1cc0/0940/ebec0/ec780/f72e0/ef9d0/ee830) handle other GridMate message types (player whitelist, target updates, etc.) we haven't identified yet. Not needed for connect — only RegistrationResponseMsg is.

### Yet-newer next steps

1. **Find the serializer**: vtable at `PTR_FUN_147f46910` is the type info vtable. Its methods include serialize/deserialize. Walk it and find the byte-layout writer.
2. **Trace the inbound dispatch chain**: 0x146b6ed39 (sole in-code caller of FUN_146b6f190) is the dispatcher. Its containing function is the message-routing layer that converts wire bytes → typed message → dispatcher call. Find it to learn the wire format.
3. **GridMate open source**: search GitHub for `RegistrationRequestV3Msg` or the GUID `0B826B33-89F5-49E0-B8CB-FE4433427778` — the definition gives us the wire format directly.

## 2026-04-23 (post-test): --GatewayMode=stubbed didn't change behavior

Tested `python tools\frida_capture.py --exe ... --exe-arg=--GatewayMode=stubbed`.
Spawn line confirmed the arg was passed at the OS level. **Same exact behavior**
as previous runs: rep-wrapper hit state 10 ~3603 times, `601=0` stuck, same
eventual `process-terminated`.

Two possible explanations:
1. **CLI flag syntax wrong**: FUN_14645b520 reads keys `"GatewayMode"`, `"GatewayAddr"`,
   `"HttpGatewayAddr"`, `"AuthMode"`, etc. — bare names without dashes. The CLI string
   format the binary's parser expects (--Name=value, /Name=value, -Name:value, etc.)
   isn't visible from the decompile alone. Our `--GatewayMode=stubbed` may have been
   silently dropped.
2. **STUBBED mode might not actually bypass REP DTLS** — re-reading the subagent's report,
   FUN_146425000 (ConfigureLogin) controls the HTTP gateway / signing / region setup.
   But state 10 is "WaitingForREPConnection" — the DTLS layer, not HTTP. MODE_STUBBED
   could bypass HTTP-gateway init while STILL initializing REP DTLS independently.

Three alternative ways to enable stubbed mode worth trying:
- Write `ClientOverride.json` in the assets path (logs "Using client config override
  file: %s" if found) with `{"client-connection":{"client-gateway":{"mode":"stubbed"}}}`
- Frida-hook the config-getter to always return "stubbed" for the mode key
- Decompile FUN_146425000 to verify whether it actually controls REP init scope

## 2026-04-23 (TRUE FINAL): STUBBED MODE BYPASS DISCOVERED

Subagent string-enumeration of NewWorld.exe found the explicit dev/test bypass for the entire REP gateway handshake.

**Function**: `FUN_146425000` (ConfigureLogin) at 0x146425000. Reads `client-connection.client-gateway.mode` config and three-way branches:
- `"dummy"` → skip everything, set dummy flag
- `"stubbed"` → builds stubbed gateway client (PTR_FUN_1484fdfa0), **bypasses REP signing + region setup entirely**
- `"gateway"` (default) → real REP/gateway client (FUN_146402cc0) — what we've been hitting all night

**MODE_STUBBED routes around the entire REP handshake we couldn't crack.**

**Two ways to enable** (no patching needed):
1. **CLI flag**: `--GatewayMode=stubbed` (parser at FUN_14645b520 writes it directly into the config key)
2. **Config file**: edit `@assets@/Client.json` or `@assets@/ClientOverride.json`

`tools/frida_capture.py` now supports `--exe-arg=...` passthrough to spawn args.

**Test command**:
```powershell
python tools\frida_capture.py --exe "G:\NewWorldArchive\GameClient\Bin64\NewWorld.exe" --name stubbed_test --exe-arg=--GatewayMode=stubbed
```

Other CLI flags worth knowing (each maps to a config key, all from FUN_14645b520):
- `--AuthMode=stubbed`, `--AuthBackend=...`
- `--GatewayAddr=host:port`, `--HttpGatewayAddr=host:port`
- `--GatewayRegion=us_west_2`, `--GatewaySigningHost=...`
- `--DeveloperLoginAssumeRole=...`

Fallback if CLI is silently ignored: Frida byte-patch `FUN_146b6df50` (or `FUN_146445f30`) — both are pure `IsClientGatewayStubbedOrDummy()` predicates — to `mov al, 1; ret` so all callers think we're in stubbed mode.

This is the unblock. Test it next.

## 2026-04-23 (extra-final): SM_CLOCK_SYNC + reliable ACK didn't help

Per Carrier.cpp: on receiving SM_CONNECT_REQUEST and validating, the server should `SendSyncTime()` then `SendSystemMessage(SM_CONNECT_ACK, wb, conn, SEND_RELIABLE)`. Implemented both in the responder — paired SM_CLOCK_SYNC + reliable SM_CONNECT_ACK in a single batched datagram. Tested with `--ack-variant mirror` (the body content that uniquely got carrier "simple-ack" treatment in earlier runs).

**Result: same dead end.** State doesn't advance past 10. Worse, adding the SM_CLOCK_SYNC + reliable flag pushed our message OUT of the "simple-ack" carrier-treatment that bare mirror alone uniquely got. We're now in the "extended-ack tracking" mode like all the other variants.

**Most informative observation tonight:** bare mirror alone (single record, non-reliable, 5-byte body) is the ONLY variant that matched what the carrier expects format-wise. Anything we add — extra records, reliable flag, more body bytes — breaks that match.

Yet bare mirror also doesn't unlock state. So the carrier validation passes for mirror, but **the client still rejects at a higher layer**.

The subagent dive into Lumberyard source confirmed:
- `RegistrationResponseMsg` is NOT the SM_CONNECT_ACK payload — it's a higher-layer Hub actor message dispatched AFTER carrier handshake completes
- `ContainerClientSDK::Handshake` subclass does NOT exist in the binary
- Public source has only `DefaultHandshake` (wire format = `wb.Write(m_version)`)

**Possibilities for what's wrong:**
1. The 4-byte `00 00 00 05` body isn't actually `m_version` — might be a request type/session ID and we're misinterpreting the entire wire format
2. The two SM_CONNECT_REQUESTs in the client's first datagram (4B body + 5B body) might be V1 + V3 version-negotiation, requiring per-version response selection
3. Some additional carrier-level state (clock sync inbound, connection-control message, etc.) is gating the application-level dispatcher

Future variant guessing without more static analysis input has very low expected value. Highest-leverage move from here is direct Ghidra UI work on:
- The unidentified function containing 0x146b6ed39 (sole caller of FUN_146b6f190 — the dispatcher)
- FUN_146b66e70 (called after auth-ready, state advance logic)
- FUN_146b6df50 (checks client-gateway.mode config against "stubbed" / "dummy" — possible debug-mode shortcut?)

## 2026-04-23 (FINAL × 5): GridMate DefaultHandshake source confirms wire format basics

Searched and pulled `aws/lumberyard` GitHub repo. Confirmed GridMate is the Amazon-internal name; the `ContainerClientSDK` strings in NewWorld.exe are Amazon's internal extensions on top.

**Key discovery from `Carrier.cpp`:**
```cpp
enum SystemMessageId {
    SM_CONNECT_REQUEST = 1,
    SM_CONNECT_ACK,         // = 2
    SM_DISCONNECT,          // = 3
    SM_CLOCK_SYNC,          // = 4
    SM_CT_FIRST,            // = 5
    SM_CT_ACKS,             // = 6
    SM_CT_CONN_CONTROL,     // = 7
    SM_CT_BANDWIDTH,        // = 8
};
```

So our original `SystemMessageId` interpretation was CORRECT all along — `msgId=1` = SM_CONNECT_REQUEST, `msgId=2` = SM_CONNECT_ACK, channel=3 (k_systemChannel), big-endian byte order (`kCarrierEndian = EndianType::BigEndian`).

The "RegistrationRequestV3Msg" we found is a HIGHER-LAYER concept — Amazon's REP application uses GridMate's SM_CONNECT_REQUEST to wrap their registration message. The architecture is:

```
DTLS (encryption)
  └─ Carrier envelope (4B: type 0x80|0x81 + proto 0x01 + seq u16 BE)
       └─ Carrier records (flags + size + channel + seq + relSeq + payload)
            └─ For ch=3: payload = [body bytes][SystemMessageId byte at end]
                 └─ For SM_CONNECT_REQUEST: body = whatever Handshake::OnInitiate writes
```

**Pulled `DefaultHandshake.cpp`:**
```cpp
// OnInitiate (builds SM_CONNECT_REQUEST body):
wb.Write(m_version);

// OnReceiveRequest (builds SM_CONNECT_ACK reply when receiving valid request):
VersionType version;
if (rb.Read(version) && version == m_version) {
    OnInitiate(id, wb);  // delegates: writes m_version back
    return HandshakeErrorCode::OK;
}
return HandshakeErrorCode::VERSION_MISMATCH;
```

**This means for pure DefaultHandshake:**
- SM_CONNECT_REQUEST body = `[VersionType m_version]`
- SM_CONNECT_ACK body = `[VersionType m_version]` (same)

Our captured client SM_CONNECT_REQUEST body is `00 00 00 05` = VersionType u32 BE = **5**. So if NewWorld used DefaultHandshake, our `mirror` variant (`00 00 00 05 02`) WOULD WORK.

**It doesn't, because NewWorld uses a custom V3 handshake** (string evidence: "Client connection using authtoken V3 registration message type"). The V3 handshake's `OnInitiate` writes additional fields beyond just version — that's why the request body GROWS by `0x01` per retry (extra V3-specific fields the custom impl writes).

The V3 handshake's `OnReceiveRequest` reads those additional fields and writes back a richer ACK. To craft a working SM_CONNECT_ACK, we need to mirror the V3 handshake's reply format.

**What the V3 ACK likely contains** (from our in-memory RegistrationResponseMsg decode):
- u32 BE: version (= 5, must match)
- u32 BE: error_code (= 0 for success)
- string: session_token (length-prefixed AZStd::string)
- 3 bytes: status flags (status_a/b/c)
- u8: eos_error_flag (= 0)
- ... possibly more

A reasonable next-attempt body (untested):
`00 00 00 05` (version) `00 00 00 00` (error=0) `00 00` (str_len=0) `00 00 00` (status flags) `00` (eos flag) `02` (msgId)

= 14 bytes. Add as a variant, run the responder, see if state advances.

Even shorter test — the EXACT mirror was 5 bytes; try a richer 9-byte version too: `00 00 00 05` (version) `00 00 00 00` (error=0) `02` (msgId) — minimum needed if there's no string field.

This is the actual next thing to try when starting fresh.

## 2026-04-23 (responder bring-up + payload iterations)

`server/rep_responder.py` shipped using pyOpenSSL `DTLS_SERVER_METHOD` with memory BIOs. First run: DTLS handshake passed, parsed inbound, sent SM_CONNECT_ACK with body `00 00 00 05 02` (mirror of client's `00 00 00 05 01`), client carrier-acked our outbound seq=0 explicitly, but never advanced state. Game lived 1m40s vs 3s baseline. Confirmed the responder is working at the carrier layer; the application-level connect-handler in the channel struct is rejecting our payload content.

Iterated four payload variants on `--ack-variant`:

| Variant | Body | Carrier ack reaction | State advanced? |
|---|---|---|---|
| `mirror`  | `00 00 00 05 02`       | simple ack `00000006` 3x then idle | no |
| `empty`   | `02`                   | extended ack `400001000006` (0x40 flag), client briefly skips SM_CONNECT_REQUEST in env_seq=7, then resumes | no |
| `echo`    | `00 00 00 05 00 02`    | identical to `empty` | no |
| `v0`      | `00 00 00 00 02`       | identical to `empty` | no |

Key observation: `empty`/`echo`/`v0` ALL produce identical client behavior, but DIFFER from `mirror`. The `mirror` body's `00 00 00 05` prefix appears to trigger a different parser path (perhaps "connect-ack with negotiation params" which then fails validation), while the others trigger "generic ack" with the full extended-ack tracking format. Either way: the application-level handler is unsatisfied.

The cheap-experiment loop has ~exhausted itself; further variant guessing without RE is unlikely to converge. Per `feedback_character_select_unreliable`: each end-to-end iteration is ~10 min wall-clock (game reaches character creation only ~1 in 6 launches), so we can't afford too many more A/B/C runs.

Added a `dynamic` variant that echoes the client's latest SM_CONNECT_REQUEST body byte-for-byte with msgId swapped (handles the per-retry growing body). Worth one run.

### Real next step: find the SM_CONNECT_REQUEST writer

Confirmed that `FUN_140f80770` (the system-message sender) is **only** ever called with `msgId=6` (SM_CT_ACKS) and `msgId=7` (SM_CT_CONN_CONTROL) — there's no caller passing `msgId=1`. So SM_CONNECT_REQUEST is constructed and queued via a different code path (probably the carrier's handler/strategy class at `param_1[2]` — its vtable `+0x80`/`+0x88` look like message-builder methods called from the transmission tick `FUN_140f8ab70`).

Locating that writer will reveal exactly what the `00 00 00 05` body bytes mean (likely a session/connection ID or protocol version number) and what fields SM_CONNECT_ACK needs to mirror or generate. That's the highest-leverage next move.

### Important responder log paths

- `capture/responder_<timestamp>.log` — every run writes here (no need to ask for terminal scrollback)
- `capture/<timestamp>_<name>/session.log` — Frida session log (existing convention)
- `capture/<timestamp>_<name>/hooks.log` — Frida hook resolution status

---

## 2026-04-26 (very late) — REP DTLS bypass via byte-patch (MODE_STUBBED / MODE_DUMMY)

**Headline:** the unsolvable REP DTLS state-10 wall is bypassable. ConfigureLogin (`FUN_146425000`, RVA `0x06425000`) has three branches selected by `client-connection.client-gateway.mode` — `gateway` (default), `stubbed`, `dummy`. Forcing either non-default branch via byte patch makes the binary skip REP DTLS entirely. Confirmed in two iterations by Game.log emitting `ConfigureLogin MODE_STUBBED` / `MODE_DUMMY` instead of `MODE_GATEWAY`, with zero `[rep-wrapper]` activity in the Frida session log afterward.

Both bypasses produced new failure modes downstream, **but neither is the same wall as state 10** — they're tractable problems further along the flow.

### Why the CLI flag and config file approach failed

- `--GatewayMode=stubbed` was silently ignored. CLI parser at `FUN_14645b520` reads bare keys (no `--` prefix) via a generic args registry; the actual CLI syntax for that registry is unknown.
- `@assets@/ClientOverride.json` is checked at startup but `@assets@` resolves through AZCore's pak-only namespace — placing a loose JSON at any disk location (`assets/`, `assets/pc/`, `Cache/Assets/pc/`, game root, Bin64) all failed; the FS only walks pak-file directories for that alias and short-circuits. No Win32 file APIs ever got hit for ClientOverride.json — confirmed by a Frida findoverride trace.
- Cleaner solution: byte patch.

### The byte patches (added to `tools/frida_dtls_hook.js`, default off)

Two flags, mutually exclusive, both default false now:

```js
var EXPERIMENT_FORCE_STUBBED_MODE = false;
var EXPERIMENT_FORCE_DUMMY_MODE   = false;
```

Patches applied when either flag is true:

| RVA | Original | Patched | Purpose |
|---|---|---|---|
| `0x06b6df50` | `48 89 5c` (prologue) | `B0 01 C3` (MOV AL,1; RET) | `FUN_146b6df50 IsClientGatewayStubbedOrDummy` → always true |
| `0x06445f30` | `48 89 5c` (prologue) | `B0 01 C3` | `FUN_146445f30 IsClientGatewayStubbedOrDummy` (other site) → always true |
| `0x06425357` | `0F 85 62 03 00 00` (JNZ rel32) | `90 90 90 90 90 90` | ConfigureLogin JNZ-to-gateway → NOP, forces STUBBED branch |
| `0x064252e9` | `75 20` (JNZ rel8) | `90 90` | ConfigureLogin JNZ-past-DUMMY → NOP, forces DUMMY branch (alternative to above) |

Patch applies in `hookInternalRepFunctions()` so it lands before any game code runs that reads the mode. Also installs an `Interceptor` on `FUN_146425000` to log which vtable was installed at `gameConn+0x118` (stub vtable = `PTR_FUN_1484fdfa0` at RVA `0x84fdfa0`).

### MODE_STUBBED outcome (capture `20260426_225029_force_stubbed_v6`)

ConfigureLogin took the stubbed branch — `gameConn+0x118` got the stub gateway vtable. **Zero state-10 wrapper activity.** REP DTLS was never attempted.

The stub gateway is essentially the **internal Amazon dev environment**: it talks to AWS services directly via AWS SDK (HTTPS+JSON/XML), not via the live REP gateway. Observed during character-select arrival:

- `dynamodb.<region>.amazonaws.com:80/ping` × 5 regions — succeed against real AWS
- `tokenservice.amazongames.com:443/games/new-world/tokens` — auth_mock 200 OK
- `d3bj4csovi1fe8.cloudfront.net:443/prod/credentials/omni` — auth_mock 200 OK
- `ags-javelin-remote-config.s3.amazonaws.com:443/...` × 12 config fetches — auth_mock 200 OK
- **`sts.us-east-1.amazonaws.com:443/` POST** — real AWS, **403 Forbidden** (rejects our credentials)
- `client.entitlementservice.amazongames.com:443/...` — auth_mock 200 OK
- **`kinesis.us-west-2.amazonaws.com:443/` POST** — real AWS, **400** (rejects malformed/unauthenticated request)

Then "Connection Failed: Login services are unavailable" auto-fired on character-select arrival.

The `:5999` in `ConfigureLogin MODE_STUBBED: endpoint=d3bj4csovi1fe8.cloudfront.net:5999` is just a **default port set by ConfigureLogin if the URL has no port** — the stub never connects to it. All actual traffic is HTTPS:443 plus a few HTTP:80 dynamodb pings.

### MODE_DUMMY outcome (capture `20260426_225941_force_dummy_test`)

DUMMY branch sets `gameConn+0x128 = 1` and jumps to cleanup without constructing any gateway client. `gameConn+0x118` stays `0x0`. No AWS calls, no STS, no Kinesis — totally clean HTTP layer (every response 200).

Same dialog auto-fires on character-select arrival. The state machine sees null gateway client and immediately fails — user cannot click "Create Character" or anything else; the dialog blocks interaction.

### What this changes

The strategic landscape is now clearer:

1. **REP DTLS is no longer the wall.** Byte patches give a clean bypass.
2. **The wall is the gameConn state machine's "is gateway healthy" check** — fires on character-select arrival regardless of mode, before the user can even click "Create Character".
3. **MODE_GATEWAY (default) is still the best baseline** for further work because auth_mock already supports the full character-create / name-reservation flow. The character-select screen's auto-failure in STUBBED/DUMMY shows the gateway client itself participates in early state transitions; replacing it (DUMMY) or swapping it for a non-functional one (STUBBED without AWS mocks) breaks the screen.

### Discarded paths

- ❌ Mock the AWS services (STS / Kinesis / DynamoDB) — significant work to emulate a large chunk of AWS, and the dev-env path is not a guarantee of better progress than the production REP path.
- ❌ MODE_DUMMY as long-term solution — too aggressive; character select itself fails.

### Next move (per user direction 2026-04-26)

Both flags reverted to false → back to MODE_GATEWAY baseline. Next session should focus on the **unanalyzed code at `0x146b6e190–0x146b6e7c0`** — specifically the call to `FUN_146b6df50` at `0x146b6e2ab` and what gates the wrapper's state-10 → state-11 transition. Per memory `project_gridmate_carrier_breakthrough.md`, this region is what actually validates the REP handshake, and Ghidra MCP can't see it without manual define-as-function in the UI.

### Side fixes shipped this session (still useful regardless of mode)

- `tools/frida_dtls_hook.js` `formatSockaddr` now handles AF_INET6 (was IPv4-only). All IPv6 connect targets in session.log now show `[ipv6addr]:port` instead of `unknown`.
- `server/auth_mock.py` is now dual-stack v4/v6 (binds `[::]` with `IPV6_V6ONLY=0`). Required because the stubbed gateway used AF_INET6 sockets and our hosts file now resolves to both 127.0.0.1 and ::1.
- `tools/setup_hosts.py` adds both v4 and v6 entries for every redirect host (default `--target=127.0.0.1`, additional `::1` block appended).
- `server/stub_tcp_probe.py` — small dual-stack TCP listener on port 5999 for capturing whatever the stub gateway sends. Stub never actually connected to 5999 in practice (it uses HTTPS:443), so the probe is unused; kept for future diagnostics.


## 2026-05-04 — REP_state10_dispatcher decoded; the captured `00 00 00 05 01` is a SystemMessage, not a registration request

### How we got here

Installed `akiselev/ghidra-cli` (Rust CLI bridge to Ghidra headless). Two patches applied to make it work with our Ghidra 11.3 install — see memory `feedback_ghidra_cli_setup.md`. Used it to **define-as-function** the gap entry at `0x146b6e190` (which Ghidra MCP could not see because it is only reached via vtable dispatch + tail-call thunk), then decompiled.

### What `REP_state10_dispatcher` actually does

```c
void REP_state10_dispatcher(wrapper) {
  if (gateway[0x160] == 0) {
    // BRANCH A — small SystemMessage, msgcode chosen by gateway[0x164]
    msgcode = (gateway[0x164]==1) ? 6
            : (gateway[0x164]==2) ? 7
            : (gateway[0x164]==3) ? 0xe
            :                       5;   // <-- DEFAULT FALLBACK
    FUN_146b6c500(wrapper, msgcode, 0, &emptyStr);
  } else {
    // BRANCH B — RegistrationRequest (V2 or V3)
    if (DAT_149f80d34==0 || stubbed_or_dummy()) {
      // Logs "Client connection using V2 registration message type"
      FUN_146b66a60(buf, ..., wrapper+0x27, +0x39, +0x3d, +0xa2, +0xb2);
    } else {
      // Logs "Client connection using authtoken V3 registration message type"
      FUN_146b67c70(wrapper+0xed, &cb);   // attach callback
      FUN_146b66820(buf, ..., wrapper+0x27, +0x39, +0x3d, +0x7e, +0xa2, +0xb2);
    }
    enqueue via wrapper.vtable[0x30];
    wrapper[0x600] = 0;   // clear send-pending
  }
}
```

### Three findings that change earlier conclusions

1. **The captured `00 00 00 05 01` body is BRANCH A, not a registration request.** The `5` is `msgcode 5` — the default fallback when `gateway[0x164]` is not 1/2/3. The trailing `01` is a 1-byte field appended by `FUN_146b6c500`’s enqueue path, not a `msgId`. **This invalidates the "magic value 5 = length prefix" hypothesis** in `project_gridmate_carrier_breakthrough.md`.

2. **Registration is gated on `gateway[0x160] != 0`.** While this byte stays 0, the dispatcher only ever sends BRANCH A SystemMessages. That explains why every RegistrationRequest builder we hooked over the past ten days was silent — they were never being called.

3. **`DAT_149f80d34` is the V2/V3 selector global** in normal mode. We did not previously know what chose between V2 and V3 registration.

### Newly-named symbols (saved into the Ghidra project)

| Address | Old | New | Purpose |
|---|---|---|---|
| `0x146b6e190` | (unanalyzed) | `REP_state10_dispatcher` | The gap function that gates state-10. Branches on `gateway[0x160]`. |
| `0x146b66820` | `FUN_146b66820` | (unrenamed) | RegistrationRequestV3Msg constructor — 0x470 bytes. |
| `0x146b66a60` | `FUN_146b66a60` | (unrenamed) | RegistrationRequestMsg (V2) constructor — 0x360 bytes. |
| `0x146b6c500` | `FUN_146b6c500` | (unrenamed) | SystemMessage sender — SRW-locked queue append at `wrapper[0xc4]`. Wraps `FUN_146b69e80` for serialization. |

Decompilations saved to `analysis/decomp_v3_builder.txt`, `decomp_v2_builder.txt`, `decomp_branchA_sender.txt`.

### Next move

Primary lead: **find what writes `gateway[0x160]`**. While that byte stays 0, registration never fires. Two angles:
- Static: search xrefs to `gateway+0x160` writes in Ghidra. Should be a small number of write sites; one of them is the "DTLS-handshake-success" path.
- Dynamic: hook the wrapper init in Frida and watch `gateway+0x160` byte writes during connect attempts.

Secondary lead: decompile `FUN_146b69e80` and `FUN_146b687e0` (called by `FUN_146b6c500`) to recover the SystemMessage wire format for codes 5/6/7/14 and confirm the `00 00 00 05 01` reading.

### Tooling shipped this session

- `ghidra-cli` (third-party) installed and patched at `C:\Tools\ghidra-cli`. Two patches: scripts_dir relocation (Bnd hidden-dir filter on `%APPDATA%`) and `handleCreateFunction` flow-analysis fallback. Daily-use commands documented in memory `feedback_ghidra_cli_setup.md`.
- Three decompile dumps under `analysis/decomp_*.txt`.


## 2026-05-04 (later) — Mixed Nuts wire fix landed; V3 RegistrationRequest captured

### What happened

Applied Mixed Nuts wire fixes (commit `5712ed1`): outgoing record flag `0xb0` -> `0x20`, drop `MF_CONNECTING`/`MF_SEQUENTIAL_REL_ID` auto-set, write `rel_seq` u16 explicitly, and echo client's inbound envelope seq onto the reply.

User ran the next attempt. Outcome:

- DTLS handshake completed.
- Client sent its usual `[ch=3 sysmsg=1 payload=0000000501..]` BRANCH-A SystemMessages (env_seq=2, 3).
- Our reply went out with the corrected `0x20` flag.
- **Client transitioned to BRANCH B** of `REP_state10_dispatcher` and sent `RegistrationRequestV3Msg` at `env_seq=4` — confirmed by visible AzCore strings in the body: JWT, Steam ticket, world UUID, persona ID, signature, gateway endpoint, build version `6031`, `[RETAIL]` tag, etc.
- Our parser couldn't decode the new data-channel record format (`flag=0xf0`/`0xe0`, reserved bit `0x40` set, `size` field reads as 800/8192 which exceeds available bytes).
- No reply -> client retried 10 times over ~10 seconds, then sent `SM_DISCONNECT` (`[ch=3 sysmsg=3 payload=0103]`, reason=0x01 = TIMEOUT).
- Game showed in-game "Connection Error - Unable to connect to the server".

### Why this is a breakthrough

For the past two weeks every Carrier sender hook we'd installed for the V3 builder stayed silent. Per `project_rep_state10_dispatcher_decoded.md`, that's because `gw[0x160]==0` kept the dispatcher in BRANCH A indefinitely. We later identified `FUN_146b713e0` as the setter (`project_gw160_setter_found.md`) but didn't know which message-type triggered it. **Mixed Nuts' fix accidentally answered the question by working** — our reply, with the correct `0x20` flag and explicit rel_seq, satisfies whatever predicate `FUN_146b713e0`'s `vtable[0x8]` invoked. So the missing trigger was never an exotic message-type we hadn't sent — it was just a malformed reply to one we already had.

### What we have on disk

- `analysis/v3_request/env_seq4_first_attempt.hex` — the very first V3 request bytes (848 bytes, 5-byte longer header than retries).
- `analysis/v3_request/all_v3_request_retries.hex` — 10 retries (one per line, 843 bytes each). Identical except for one byte at offset 6 (the inbound-ack counter).

Wire-record header for the data-channel format (different from sysmsg records):
- First-attempt: `f0 03 20 00 06 03 00 05 ff ff 40 00 03 00 02 06 [payload starts at offset 0x10]`
- Retry:        `e0 20 00 02 03 00 XX ff ff 20 06 [payload starts at offset 0x0b]`

Reserved bit `0x40` is set in both flag bytes — `frame.py` enum is wrong about it being unused; it has meaning, possibly a layout marker for non-system records.

### What unblocks next

1. **Decode the data-channel size encoding.** Once we can correctly parse the V3 record, we can extract its payload. Most likely: variable-length size, OR size in bits (varint?), OR completely different layout for non-system records.
2. **Send a `RegistrationResponseMsg`** in reply. Per `project_rep_state10_dispatcher_decoded.md` the response must validate `error_code==0` (msg+0x08) and `eos_flag==0` (msg+0x5b), include a session token (AZStd::string at +0x18), and have 3 status bytes (+0x58/+0x59/+0x5a). The on-wire size is 0x60 bytes per the typeregistry.
3. **Mixed Nuts may already have the parser + responder** in his refactored impl — best to ask before reinventing. The capture (full body hex) is a clean test vector for him.

### What this changes about prior conclusions

- The "magic value 5 length prefix" hypothesis (in `project_gridmate_carrier_breakthrough.md`) was wrong. Confirmed by `project_rep_state10_dispatcher_decoded.md` and now confirmed AGAIN by the actual wire bytes.
- The "we need to find a special message that flips gateway[0x160]" lead is resolved — wasn't a special message, just a malformed reply to the SystemMessage that was already there.
- The "ClientConnectionMsg unsolicited from server" hypothesis was wrong. Per `0x14a134910` C++ symbol it's client->server, and we now see the client never even sends it during this flow.


## 2026-05-04 (later still) - Two protocol dumps merged + V3 round-trip wired

### What landed since last entry

1. **Mixed Nuts (working server impl) shared a Wireshark trace** with custom dissector at `docs/handoff_state10_question.md` reply path. Decoded the canonical Connect ACK shape (flag 0x21 + 0x18 piggyback). Our reply now matches his demo BYTE-FOR-BYTE.
2. **A second reverser shared their full 22-phase post-registration roadmap** at `docs/community/community_state_machine_dump.txt`. Different code path from Mixed Nuts, includes wire-format gotchas, NW Protocol Wrapper for ch0/ch1, C->S after-handshake format, and binary patches needed for actual play.
3. **Two agents in parallel** decoded the V3 RegistrationRequest body (`server/javelin/v3_request.py` round-trips byte-perfect on all 10 captured retries) and drafted the response encoder (`server/javelin/v3_response.py`).
4. **Parser fix** for MF_NO_LENGTH (0x40) data-channel records and the 0x10 first-attempt connect form. `analysis/v3_request/HEADER_DECODE.md` has the layout.
5. **Compression confirmed LZ4 raw block** (verified by round-trip). Client accepts uncompressed (envelope 0x80) — no need to LZ4 our replies for now.
6. **rep_responder._handle_v3_data_record** now: (a) dumps raw V3 bytes to `capture/responder_*_v3/v3_req_NNN.bin`, (b) builds a stub V3RegistrationResponse with our encoder, (c) wraps in MF_NO_LENGTH data-channel record (flag 0x60), (d) sends via wrap_envelope_echo. Rate-limited to 1/sec.

### Key conflicting data point

The two reversers DISAGREE on Connect ACK shape:
- Mixed Nuts: flag `0x21`, relSeq=0 (real-server form)
- Other reverser: flag `0xa0`, relSeq=0xffff -- explicitly says `0x21/0` "instant-disconnects on our path"

We currently use Mixed Nuts's form because his fix made our client send the V3 request (proven progress). If the next attempt regresses, falling back to `0xa0/0xffff` is the obvious next experiment.

### Next milestone

User tests with the new responder. Three possible outcomes:

1. **Client accepts the stub response** (state-10 -> state-11): we have ~100ms to start pushing the 22-phase post-registration script. We are NOT ready for that yet -- it's 700KB of state and the binary needs two patches we don't have. Game will probably show a different error (loading-circle freeze or similar).
2. **Client SM_DISCONNECTs with a specific reason byte**: tells us exactly which response field is wrong. Iterate.
3. **Client just keeps retrying**: our response wasn't formatted correctly to be parsed. Compare against the V3 request format we just decoded.

Either way, this is the first time we'll see signal from the post-V3 layer.
