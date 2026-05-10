# Project Dashboard

> One-page status of the New World private-server RE work.
> Optimized for mobile viewing on github.com. Last updated wake 90 (2026-05-09).

## TL;DR

- **Codec library**: 22 dedicated codecs + 1 generic + 9 factories + `SessionState`. **252 tests passing.** ~35 of 40 captured wire-types covered.
- **Two major findings (wake 90)**: W-direction CRC32 confirmed; wire-type-id == typeIndex from `info/typeregistry.json` (3487 entries; 6 captured types now authoritatively named).
- **Runtime blocker**: real-GPU host needed (UTM and Parallels both fail at GPU detection on Apple Silicon). AWS `g4dn.xlarge` is the recommended path.
- **State 10 → 11 transition**: handler is `FUN_146454c00` (`PlayerManagerSelfIdentificationMsg`, typeIndex 0x5d1). Predicate `*(int *)(wrapper + 0xa0) == 2`. **Captured replay lacks Phase 9b** — needs runtime trace or static-RE on the deserializer.

## Library status

| Layer | Components | Tests |
|---|---|---|
| Wire framing | `frame.py`, `bitstream.py`, `wire.py` | included in 252 |
| V3 RegistrationRequest/Response | `v3_request.py`, `v3_response.py` | included |
| Per-type codecs | 22 dedicated modules + `subkey_beacon` (14 types) | 252 round-trip + invariant |
| Factory helpers (9) | `make_subkey_beacon`, `make_init_message_18a6`, `make_ack_for`, `make_session_clock_beacon`, `make_session_identity_beacon`, `make_session_message_a4`, `make_handshake_blob_76`, `make_result_token_136a`, `make_result_token_1097` | included |
| Session-state scaffolding | `SessionState` dataclass (structure-only sketch) | smoke tested |

**Test command**: `.venv/bin/pytest server/javelin/test_codecs.py -q`

## Captured wire-types (40 total)

Full table — wire-type → registry name → codec module:

| Wire | N | Dir | Bytes | Registry Name | UUID | Codec |
|---|---:|---|---:|---|---|---|
| `0x0003` | 1 | R | 88 | RegistrationResponseMsg | 104145A7... | `v3_response.py` |
| `0x0008` | 79 | R | 78,106,126... | _(unnamed)_ | 8A40AEC2... | `—` |
| `0x0013` | 1 | W | 2750 | RegistrationRequestV3Msg | 0B826B33... | `—` |
| `0x00a4` | 2 | R | 20 | **ClientAddEntryMsg** | E3578B38... | `session_message_a4.py` |
| `0x014f` | 4 | R | 12 | **TimeSynchMsg** | 038CD847... | `session_clock_beacon.py` |
| `0x015d` | 20 | RW | 12,36 | **PingMsg** | 6A379FB8... | `heartbeat_15d.py` |
| `0x01be` | 1 | R | 76 | _(unnamed)_ | 1E718638... | `handshake_blob_76.py` |
| `0x040a` | 1 | R | 76 | _(unnamed)_ | 979E13FB... | `handshake_blob_76.py` |
| `0x05b2` | 4 | W | 45,93 | _(unnamed)_ | 298436A9... | `identity_fingerprint_5b2.py` |
| `0x0635` | 5 | W | 93,108,123... | _(unnamed)_ | 01346CCD... | `action_history_635.py` |
| `0x0651` | 1 | R | 4 | _(unnamed)_ | 21207525... | `—` |
| `0x065c` | 1 | R | 12706 | _(unnamed)_ | 169443E0... | `world_data_blob_65c.py` |
| `0x0663` | 2 | R | 110 | _(unnamed)_ | 45918D03... | `level_descriptor_663.py` |
| `0x066b` | 1 | W | 44 | _(unnamed)_ | 1505D3B1... | `subkey_beacon (generic)` |
| `0x08e6` | 1 | R | 42 | _(unnamed)_ | 8C39E814... | `identity_blob_8e6.py` |
| `0x09d3` | 1 | W | 48 | _(unnamed)_ | C3AB71F9... | `subkey_beacon (generic)` |
| `0x09fc` | 1 | W | 102 | _(unnamed)_ | D61428C7... | `receipt_handshake_9fc.py` |
| `0x0a95` | 1 | W | 81 | _(unnamed)_ | CB4BA5E5... | `permission_bitmap_a95.py` |
| `0x0ca4` | 1 | R | 102 | _(unnamed)_ | F725B229... | `asset_count_table_ca4.py` |
| `0x0f7f` | 1 | W | 45 | _(unnamed)_ | 8950B8C3... | `subkey_beacon (generic)` |
| `0x101a` | 1 | W | 45 | _(unnamed)_ | 702F8589... | `subkey_beacon (generic)` |
| `0x101d` | 1 | W | 45 | _(unnamed)_ | E3262DD9... | `subkey_beacon (generic)` |
| `0x102e` | 1 | W | 46 | _(unnamed)_ | 5D87AA99... | `subkey_beacon (generic)` |
| `0x102f` | 1 | W | 44 | _(unnamed)_ | 81EAD9F2... | `subkey_beacon (generic)` |
| `0x1033` | 1 | R | 498 | _(unnamed)_ | 8FA38DAE... | `—` |
| `0x1067` | 1 | R | 86 | _(unnamed)_ | 09FF1758... | `vivox_config_1067.py` |
| `0x1096` | 1 | R | 80 | _(unnamed)_ | 49A52E21... | `—` |
| `0x1097` | 1 | R | 24 | _(unnamed)_ | DEEBDC36... | `result_token_1097.py` |
| `0x1098` | 1 | W | 44 | _(unnamed)_ | 5AFEA411... | `subkey_beacon (generic)` |
| `0x10b0` | 1 | W | 45 | _(unnamed)_ | 6E9C33D1... | `subkey_beacon (generic)` |
| `0x12f6` | 1 | W | 299 | _(unnamed)_ | 6E2A29B1... | `keybinding_config_12f6.py` |
| `0x136a` | 1 | R | 28 | _(unnamed)_ | F8B391FF... | `result_token_136a.py` |
| `0x143d` | 1 | W | 45 | _(unnamed)_ | 971DDBB2... | `subkey_beacon (generic)` |
| `0x16a0` | 2 | R | 153,99819 | _(unnamed)_ | 0E1245B4... | `asset_blob_16a0.py` |
| `0x187c` | 1 | W | 45 | _(unnamed)_ | CC6E0819... | `subkey_beacon (generic)` |
| `0x187f` | 1 | W | 45 | _(unnamed)_ | F56E3380... | `subkey_beacon (generic)` |
| `0x18a6` | 4 | R | 40 | _(unnamed)_ | D33230C8... | `init_message_18a6.py` |
| `0x192c` | 1 | W | 54 | _(unnamed)_ | 9FF57F0B... | `subkey_beacon (generic)` |
| `0x1a59` | 3 | W | 45 | _(unnamed)_ | B42B3E49... | `session_subkey_1a59.py` |
| `0x1b88` | 23 | R | 42 | _(unnamed)_ | AA0A0B64... | `session_identity_beacon.py` |

**Bold** = type names recovered from `info/typeregistry.json` (wake 90).

## State 10 → 11 status

| Item | Detail |
|---|---|
| Trigger handler | `FUN_146454c00` (`PlayerManagerSelfIdentificationMsg`) |
| State predicate | `*(int *)(wrapper + 0xa0) == 2` |
| Wire trigger type-ID | `0x5d1` (= 1489 = typeIndex from registry) |
| Registry UUID | `60A51DFC-8745-4276-976D-8808EF52CD77` |
| In-binary CreateInstance stub | `0x1414e9ad0` |
| Captured replay | **Phase 9b missing** (no `0x91(0x17)` byte sequence) |
| Encoder | `server/javelin/self_ident.py` (not yet wired) |

**To unblock state 10**: need either a captured Phase 9b SelfIdentification body, or static-RE on `FUN_146454c00`'s deserializer to determine the exact wire body shape (current docs say 4-byte body but in-memory struct is 56 bytes — gap unresolved).

## Major protocol findings

### Wake 90: CRC32 confirmed (W-direction framing)

The 4-byte field at offset 0 of every captured W-direction message is **standard zlib CRC32 (IEEE 802.3) over `(correlation_uuid + envelope)`, big-endian**. Verified: 37 of 39 captured W messages match exactly (the 2 exceptions are V3 request and the redacted 0x12f6).

```
C → S framing: [crc32:4 BE][payload_size:4 BE][correlation_uuid:16][envelope]
```

Helpers in `server/javelin/wire.py`: `compute_cs_crc32()`, `serialize_cs_envelope()`, `parse_cs_envelope()`.

### Wake 90: typeregistry maps wire-type-id

`info/typeregistry.json` (a runtime memory dump of the AZ type registry, 3487 entries) provides:
- UUID per type
- name (often empty for un-RTTI'd types)
- handler function fingerprints
- **typeIndex == wire-format type-id**

6 captured types now have authoritative names from the registry; the remaining 34 are unnamed but UUIDs are recorded.

Additional named types of interest (NOT captured in this replay):
- `RegistrationRequestMsg` typeIndex=1
- `RegistrationRequestV2Msg` typeIndex=2
- `REPConnectionListener::State` typeIndex=368 (= 0x170)
- `RegistryClient::State` typeIndex=328 (= 0x148)
- `PlayerManagerSelfIdentificationMsg` typeIndex=1489 (= 0x5d1)

### Earlier wakes

| Wake | Finding |
|---|---|
| 70 | Both UTM and Parallels Desktop on Apple Silicon fail GPU detection → real-GPU host (AWS / physical) needed |
| 71 | 0x18a6 ↔ 0x1a59 counter pair: 0x1a59's subkey is byte-identical to 0x18a6's first 16 payload bytes |
| 75 | 0x65c carries the same 36-byte signing trailer as 0x40a/0x1be (same handshake-family) |
| 77 | 0x09fc's tail 16 bytes are byte-identical to 0x8e6's `opaque_blob` (receipt-handshake echo) |
| 80 | Codec coverage map: 33 of 40 captured types codec'd at that point |
| 86-89 | Static-RE confirmed all "expected constants" (handshake trailer, sub_id, 0x1033 chunks) are 100% runtime-derived, not in the binary as immediates or data |

## Cross-codec invariants (validated by tests)

| Invariant | R type | W type | Test |
|---|---|---|---|
| Counter monotonic 1→2→3→4 (subkey byte-equal) | 0x18a6 | 0x1a59 | `test_1a59_subkey_matches_18a6_first_16_bytes` |
| Echoed ping body verbatim at +0x18 | 0x15d ping | 0x15d ack | `test_15d_replay_pings_and_acks_paired` |
| Hash echo at tail (16B byte-equal) | 0x8e6 | 0x9fc | `test_9fc_echoes_8e6_opaque_blob` |
| 36-byte signing trailer shared | 0x40a, 0x1be, 0x65c | — | `test_hsb_round_trip_both_singletons` |

## Runtime / VM status

| Path | Status | Notes |
|---|---|---|
| UTM Win11 ARM64 | ❌ | Game terminates at GPU detect (virtio-gpu) |
| Parallels Desktop Win11 ARM64 | ❌ | Same as UTM (paravirtualized GPU) |
| **AWS EC2 g4dn.xlarge** | ⏳ | Recommended next step. Real Tesla T4 GPU; ~$0.75/hr including Windows Server license |
| Physical Windows host (Bootcamp / spare PC) | ⏳ | Alternative; no recurring cost |
| Shadow PC | ❌ | ToS likely prohibits Frida-style injection; streaming-first client breaks the SSH-driven automation |

When a real-GPU path lands, the SSH-driven infrastructure (cert install, hosts redirects, portproxy, SCP push of game directory, Frida hook orchestration) transfers verbatim from the UTM/Parallels work.

## Repository layout

```
server/javelin/        # codec library (35 .py files, ~10000 lines, 252 tests)
server/rep_responder.py   # runtime DTLS responder (replay-bytes + substitution)
analysis/                 # docs, RE notes, codec inventory
docs/                     # protocol overviews + post-V3 sequence reference
tools/ghidra_scripts/     # 13 Ghidra Jython scripts (5 added in wakes 86-89)
info/                     # captures + community drops
```

## Key documents

| Doc | Purpose |
|---|---|
| [`analysis/replay_message_inventory.md`](analysis/replay_message_inventory.md) | Byte-level reference for every captured type |
| [`analysis/codec_coverage.md`](analysis/codec_coverage.md) | Type → codec module map + library health snapshot |
| [`analysis/integration_status.md`](analysis/integration_status.md) | Codec ↔ server gap survey |
| [`analysis/queued_work.md`](analysis/queued_work.md) | Themed todo / deferred-items list |
| [`analysis/state_machine_summary.md`](analysis/state_machine_summary.md) | GameConnection state machine (incl. state 10 detail) |
| [`docs/post-v3-sequence.md`](docs/post-v3-sequence.md) | 22-phase post-V3 sequence with codec column |
| [`analysis/static_re_handshake_signing.md`](analysis/static_re_handshake_signing.md) | Static-RE note on the 36-byte handshake-family trailer |
| [`analysis/static_re_1033_merkle.md`](analysis/static_re_1033_merkle.md) | Static-RE note on 0x1033 chunk pool |
| [`analysis/autonomous_worklog.md`](analysis/autonomous_worklog.md) | Detailed wake-by-wake history (90+ entries) |

## Branch + commit

- **Branch**: `claude/vacation-2026-05-06`
- **Commits this session**: ~90 wake-log commits since 2026-05-06; the head commit at any time is the latest wake's writeup
- **Push status**: all commits pushed to origin
