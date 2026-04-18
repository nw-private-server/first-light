# OmniSDK Research Notes

Working notes from trying to get the game client past OmniSDK's
`CreateSession` call. Current state: **blocked at error 203**.

## What we know

**OmniSDK source path**: `C:\JenkinsBuilds\OmniSDK\sdk\source\gateway\ags_fed_acc_token_serv_gateway.cpp`

Version string: `v1.6.7`

**Endpoint**: `POST https://tokenservice.amazongames.com/games/{game}/tokens`

**Request body** (captured live):
```json
{
  "platformIdentityType": "steam",
  "platformAuth": { "ticket": "<steam session ticket hex>" },
  "fallbackToken": "<JWT signed by Amazon's key, cached from prior successful login>"
}
```

**Discovered response fields** (strings at VA 0x1495d7ea0..0x1495d9a0):

| Field | Type | Notes |
|-------|------|-------|
| `fallbackToken` | string (JWT) | Amazon-signed JWT for future refreshes |
| `limitedUseToken` | string (JWT) | Short-lived bearer |
| `platformAccount` | object | `{ identityId, identityType }` |
| `conflictingAccount` | object or null | |
| `suspension` | object or null | reason/duration |
| `isNewAccount` | boolean | |
| `agsAccount` | object (likely) | `{ identityId, accountType }` |

**Error codes emitted as strings** (VA 0x1495d7c20..):
`INVALID_AGS_AUTH_TOKEN`, `INVALID_PLATFORM_AUTH`, `PLATFORM_AUTH_SERVICE_NOT_RESPONDING`,
`PLAYER_IS_BANNED`, `INVALID_GAME`, `AGS_IDENTITY_MERGE_CONFLICT`,
`UNSUPPORTED_REGION`, `INVALID_GAME_VARIANT_FOR_PLATFORM`,
`ERROR_PARSING_REQUEST`, `INVALID_PLATFORM_IDENTITY`,
`INVALID_FALLBACK_TOKEN`, `AGS_IDENTITY_NOT_SUPPORTED`,
`AGS_IDENTITY_REQUIRED`, etc.

## What we tried (all returned error 203)

| Attempt | Result |
|---------|--------|
| Kitchen-sink response (personaId, sub, id, session_id, token, etc.) | 203, empty id |
| Plus RS256-signed JWT with our own keypair + jwks.json handler | 203, empty id |
| Echo fallbackToken from request as our response token | 203, empty id |
| Canonical schema (platformAccount + fallbackToken + suspension null) | 203, empty id |

## Why 203

Found in Ghidra at `FUN_1479c9f00` (the CreateToken function):

```c
cVar8 = FUN_1426a8f10(local_78);  // check JSON parse flag
if (cVar8 == '\0') {
    // parse failed — log "Failed to parse create token response as JSON"
    if (local_2f8[0] == 0) {
        local_2f8[0] = 0xcb;  // 203 decimal
    }
    // report error upward
}
```

So **203 = JSON parse FAILED** at the outermost level. But our JSON passes Python's
json.loads — so either:
- aws-sdk-cpp's JSON parser is stricter than Python's (e.g., requires lowercase
  `true`/`false`, no unicode chars, Content-Type must match exactly, etc.)
- Or 203 propagates from a deeper validation step that we haven't traced yet

The log line `"Omni CreateSession complete with result: %d, id: %s"` shows the
id field is always empty when the result is 203 — because the parser never
populated it.

## Where the 203 shows up in the game log

```
[OmniAuthBackend] Omni CreateSession complete with result: 203, id: 
[SteamAuth] Failed to create session for Omni, result code: 203
[Game] CGame::OnCampfireLoginFailed with error: @mm_authresult_Error_Persona
```

## Paths forward

1. **Binary patch the 203 check** — find `FUN_1479c9f00` @ `0x1479c9f00` (in
   the game's statically linked OmniSDK), NOP out the `if (cVar8 == '\0')`
   branch, force success with our payload. We can do this via Ghidra MCP.
   Risk: downstream code may reject because our fallbackToken echo doesn't
   validate against Amazon's hardcoded public key in OmniSDK's verifier.

2. **Intercept the live response** — if we can capture ONE real OmniSDK
   response (from a real login to Amazon's servers), we can replay its shape.
   Blocked by HTTPS/DTLS encryption — WinHTTP+SChannel doesn't honor
   SSLKEYLOGFILE, mitmproxy needs cert-pinning bypass, Frida is blocked by EAC.

3. **Pivot to other work** — Gate 3 reverse engineering (chunk catalog),
   Gate 4 DTLS stub server (needs a working DTLS library first, task #15),
   or dig deeper into the binary for OmniSDK internals.

## What we built anyway

- `server/auth_mock.py` — working HTTPS mock with 10 handlers, routes by Host,
  full request/response logging
- `tools/generate_auth_certs.py` — root CA + server cert with 34 hostname SANs
- `tools/setup_hosts.py` — safe apply/revert of hosts-file redirects
- `server/certs/jwt_signing.*` — keypair for signing JWTs with `jku`
  verification path

The auth mock is reusable — if we find a way around OmniSDK, every other
endpoint (credentials/omni, login_queue, remote config, etc.) is already
stubbed and waiting.

## Referenced binary addresses

| Symbol | VA |
|--------|-----|
| `FUN_1479c9f00` | CreateToken HTTP response parser — error 203 lives here |
| `FUN_1426a8f10` | JSON parse-success boolean check |
| `FUN_1479d5a70` | JSON parse invocation |
| VA `0x14844b188` | Format string `"Omni CreateSession%s complete with result: %d%s%s"` |
| VA `0x1495d7ea0+` | Response field-name strings cluster |
| VA `0x1495d7c20+` | Error code name strings cluster |
