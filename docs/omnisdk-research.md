# OmniSDK Auth Research (2026-04-17)

## Scope
- Investigated via live Ghidra bridge (`http://127.0.0.1:8080`) and local source/docs.
- No runtime code changes.
- Smoke-tested `server/auth_mock.py` behavior with `curl -k --resolve`.

## 1) What Actually Causes Error 203 (`0xCB`)

### Confirmed in `CreateToken`
- `FUN_1479c9f00` (`0x1479c9f00`) still does the expected top-level parse check:
  - `FUN_1479d5a70(...)` parse response JSON.
  - `FUN_1426a8f10(...)` reads parse-ok flag byte at `+0x10`.
  - If parse flag is false, branch logs parse failure and sets `0xCB` when result code is 0.

### Critical new finding: `0xCB` is also set in deeper model validation
- Even when top-level JSON parse succeeds, `FUN_1479b6d00` (`ags_fed_acc_token.cpp`) can set `0xCB` in multiple branches.
- Disassembly in this function shows several immediate `0xCB` assignments (`0x1479b741f`, `0x1479b7883`, `0x1479b7a11`, `0x1479b7d82`, `0x1479b7f31`).
- Nearby Omni functions in the same family also set `0xCB` (`0x1479c4a80`, `0x1479c6720`, `0x1479c7900`, `0x1479ca3e0`, `0x1479cb880`, `0x1479cc820`, `0x1479d22a0`).

### Implication
- `203` is not only "JSON parser rejected body". It is also "JSON parsed, but required schema/model checks failed".

## 2) `FUN_1479d5a70`, `FUN_1479d68b0`, `FUN_1479d6f30` Findings

### `FUN_1479d5a70` (`0x1479d5a70`)
- Calls `FUN_1479d58d0`, which uses `cJSON_ParseWithLengthOpts(...)`.
- On parse failure, parse flag is set false and error text is stored.

### `FUN_1479d58d0` (`0x1479d58d0`)
- No response `Content-Type` check found here.
- No explicit encoding gate found beyond cJSON parse.
- `FUN_1479d6860` (used later for field existence) first checks `cJSON_IsObject`, so `null`/`[]` will fail object-level checks.

### `FUN_1479d68b0` + `FUN_1479d6f30`
- These are generic JSON object-handle copy + JSON string serializer (`cJSON_PrintUnformatted`).
- They are used before request send in `FUN_1479c9f00`, so yes: effectively request serialization path.
- They do not indicate that response schema must mirror request; they are utility wrappers used in both directions.

## 3) Minimum Viable Response Shape You Have Not Tried (high-confidence)

Current mock response (per `server/auth_mock.py`) is missing fields that `FUN_1479b6d00` expects for success path.

### Required top-level keys for success (`resultCode == 0` path)
From `FUN_1479b6d00`:
- `accessToken` (required)
- `fallbackToken` (required for non-merge path)
- `platformAccount` (required object)
- `account` (required object; if absent sets code `0x133` in one branch, then still fails flow)
- `expiresIn` (read as numeric)

`limitedUseToken` is read optionally in this path, not the core required gate.

### Required nested fields (confirmed via live Ghidra 2026-04-17)
- `platformAccount` required-keys vector (`PTR_s_identityType_1495d94c8..1495d94e8`):
  - `identityType`, `identityId`, `personaId`, `ageGroup`
  - Optional: `platform`, `errorCode`
- `account` required-keys vector (`PTR_s_identityId_1495d93b0..1495d93d0`):
  - `identityId`, `personaId`, `type`, `ageGroup`
  - `type` is lowercased and compared to `"shadow"` (use `"full"` for non-shadow)
- Required-keys vector for top-level (`PTR_s_accessToken_1495d7bf8..1495d7c10`):
  - `accessToken`, `fallbackToken`, `platformAccount`

### Why your current payload likely hits 203
- You currently return `fallbackToken`, `limitedUseToken`, `platformAccount{identityId,identityType}`, `agsAccount`, etc.
- Missing `accessToken`, `account`, `expiresIn`, and likely missing required nested keys in `platformAccount`.
- This matches the deeper `0xCB` assignment behavior exactly.

## 4) Smoke Tests on `auth_mock.py` (curl)

Ran local mock on `127.0.0.1:8443` and posted bodies `{}`, `null`, `[]`, raw JWT-like text.

Observed:
- Server always returned HTTP 200 with JSON object payload.
- For `null`, `[]`, and raw text request body, mock logs showed fallback-token parse errors but still emitted full JSON response.

Interpretation:
- Mock emission behavior is consistent with current code.
- These tests only validate mock output shape under varied request bodies; they do not validate OmniSDK acceptance without running the client.

## 5) Deeper `203` Paths and Patch Viability

### Patch point A: top-level parse gate in `FUN_1479c9f00`
- Current branch:
  - `0x1479ca21d`: call `FUN_1426a8f10`
  - `0x1479ca222`: `TEST AL,AL`
  - `0x1479ca224`: conditional jump to success path
- Patching this alone is low value, because `FUN_1479b6d00` still sets `0xCB` on missing/invalid schema.

### Patch point B: `0xCB` assignments in `FUN_1479b6d00`
- Multiple sites set `local_288[0] = 0xCB`.
- Patching all of them is possible but brittle: you then risk propagating half-populated token/account structs downstream.

### Practical assessment
- Binary-patching only the parse-failed branch is unlikely to unblock auth.
- Binary-patching all validation failures may advance state but with high crash/logic-regression risk later (persona/account getters, token expiry, etc.).

## 6) `kid` / Public Key Question

### `FUN_1426a8f10` clarification
- It is only: `return *(byte*)(param + 0x10);` on the JSON wrapper.
- It is not JWT `kid` logic.

### Can full RSA public key be reconstructed from observed `kid`?
- Based on observed `kid` length/pattern, no reliable way to reconstruct a full 2048-bit modulus from that string alone.
- `AQAB` prefix corresponds to exponent `65537`, but that does not provide modulus.

### Hardcoded Amazon key search status
- I did not find definitive hardcoded key material in the functions inspected in this pass.
- Given time-box and Ghidra bridge performance limits on broad data scans, this remains open.

## 7) Bottom Line: Are We Stuck?

- **Not stuck yet.** The strongest blocker appears to be response schema mismatch, not necessarily cryptographic signature rejection.
- Highest-value next step is to make tokenservice response match `FUN_1479b6d00` success schema exactly (especially `accessToken`, `account`, `expiresIn`, and required nested fields), then re-test.
- If that still fails with `203`, then move to targeted patching of `FUN_1479b6d00` validation branches (not just parse flag branch).
