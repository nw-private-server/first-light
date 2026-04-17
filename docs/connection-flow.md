# New World Connection Flow (Extracted from Game.log 2025-12-27)

## Complete Login → World Entry Sequence

### Phase 1: Channel Config (t+0s)
Channel service config fetched from CloudFront:
- `https://d2c74t4zimux3r.cloudfront.net/STEAM_APP_ID.1063730.json`
- Returns list of regional Auth Stacks and Gateway Stacks

### Phase 2: Regional Endpoints Loaded
| Region | Auth Stack | Gateway Host | Gateway Stack (CloudFront) |
|--------|-----------|-------------|---------------------------|
| eu-central-1 | `2mfrik7h83.execute-api.us-east-1.amazonaws.com/Prod` | `u433g9r00c.execute-api.eu-central-1.amazonaws.com` | `d1w0bfy6smo4d1.cloudfront.net` |
| sa-east-1 | `kqqt5twsi7.execute-api.us-east-1.amazonaws.com/Prod` | `j4n6whncmi.execute-api.sa-east-1.amazonaws.com` | `d1cjlmzk0xrm0z.cloudfront.net` |
| us-east-1 | `eudbjx6mig.execute-api.us-east-1.amazonaws.com/Prod` | `0prplal5u1.execute-api.us-east-1.amazonaws.com` | `d2oeuvxi3kfsrw.cloudfront.net` |
| us-west-2 | `q8hqllbg6k.execute-api.us-east-1.amazonaws.com/Prod` | `v7irlu1nrl.execute-api.us-west-2.amazonaws.com` | `d3bj4csovi1fe8.cloudfront.net` |
| ap-southeast-2 | `hhf8nn71vb.execute-api.us-east-1.amazonaws.com/Prod` | `ep1m9qoir8.execute-api.ap-southeast-2.amazonaws.com` | `de4mfzk9wkelz.cloudfront.net` |

Note: ALL auth stacks route to us-east-1. Gateway hosts are regional.

### Phase 3: Steam + OmniSDK Auth (t+10s)
1. `[AuthManager] Initializing Steam Auth Manager`
2. `[SteamAuth] Omni metadata is present for this channel, using OMNI Authentication`
3. `[OmniAuthBackend] Initializing OmniSDK 1.6`
4. Auth Mode: `user`
5. Steam auth session ticket obtained (handle: 2)
6. OmniSDK CreateSession → persona ID: `amzn1.developerPersonaId.4ee4810f-da59-c553-4027-91e961054dce`
7. HTTP call: `https://d3bj4csovi1fe8.cloudfront.net/prod/credentials/omni`
8. Returns: gateway AWS credentials + persona AWS credentials (refresh ~55min)
9. `CGame::OnCampfireLoginComplete, login successful. ownership=permanent`

### Phase 4: Gateway Configuration (t+15s)
- Gateway Signing Host: `v7irlu1nrl.execute-api.us-west-2.amazonaws.com`
- Gateway Address: `d3bj4csovi1fe8.cloudfront.net`
- HTTP Gateway: `https://d3bj4csovi1fe8.cloudfront.net/prod`
- Gateway Mode: `gateway`
- ConfigureLogin MODE_GATEWAY

### Phase 5: Second Auth (for world server?) (t+15s)
- Gets a SECOND steam auth ticket (handle: 3)
- Repeats OmniSDK CreateSession
- Calls credentials/omni on us-east-1 stack this time
- Second gateway configured: `d2oeuvxi3kfsrw.cloudfront.net/prod` (us-east-1)

### Phase 6: World Selection + Login Queue (t+34s)
1. `ActorContainerConnect`
2. `GameConnectionWrapper::Connect: playerName = NoxJ`
3. State: `Disconnected → QueryGameUpdateCheck → QueueGameLogin → WaitingForQueuedLogin`
4. Login queued for character `500d3986-4b74-48d4-8ee3-8dafb5d9d780`

### Phase 7: Login Ticket + World Assignment (t+42s)
1. Received login ticket: `eacab29f-f0eb-43b4-84ed-91c4861aefc0_a1683238-3332-4128-8e78-f79ebb4abff0`
2. World ID: `eacab29f-f0eb-43b4-84ed-91c4861aefc0`
3. World Name: `live-2-02-1`

### Phase 8: Remote Config Fetch (t+45s)
Multiple S3 config layers fetched:
- `applications/public/configuration-sets/WorldId/{worldId}/versionless`
- `applications/public/configuration-sets/WorldId/{worldId}/6030;5950962`
- `applications/publicGameplay/configuration-sets/WorldId/{worldId}/versionless`
- `applications/publicGameplay/configuration-sets/WorldId/{worldId}/6030;5950962`

### Phase 9: REP Connection (Game Server) (t+46s)
1. **Direct TCP connection to game server: `35.71.190.194:25493`**
2. State: `StartREPConnection → WaitingForREPConnection`
3. "REP socket connection established, now waiting to register"
4. "received registration response from REP"
5. Server version: `[RETAIL].Javelin.1.365.6030.5950962`
6. "start actor game connection"

### Phase 10: World Entry (t+47s)
1. "actor game connection succeeds"
2. State: `WaitingForActorGameConnection → WaitingForSpawnPoint`
3. "spawn point found"
4. State: `WaitingForSpawnPoint → WaitingForPlayerSpawn`
5. Loading map: `NewWorld_VitaeEterna`
6. Processing 8 pending reliable messages
7. "player spawn succeeds, in game"
8. State: `WaitingForPlayerSpawn → InGame`
9. Vivox voice chat connects

### Phase 11: Disconnect (t+~2min)
1. `IAuthManager::GetInstance()->EndSession()`
2. `SteamAuth Omni EndSession`
3. `Disconnected from REP`
4. State: `InGame → Disconnected`

## Key Findings
- **NOT WebSocket** — the game server uses direct TCP ("REP" connection) on port 25493
- Auth IS HTTP/REST via AWS API Gateway + CloudFront
- Two separate auth sessions happen (two different regional gateways)
- OmniSDK 1.6 is Amazon's cross-platform auth SDK
- Game server IP: 35.71.190.194 (AWS Global Accelerator range)
- "REP" likely = Replication Protocol (O3DE terminology)
- Config is pulled from S3 via the gateway, versioned per-world
- CMS content (news, MOTD) from `d1hkbwzm1bktgo.cloudfront.net`
