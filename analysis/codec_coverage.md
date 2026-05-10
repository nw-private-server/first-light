# Codec coverage map

> Maps every captured type-ID in
> `info/nw-login-safe-20260502-153840/messages-redacted.txt` to its
> Python codec module under `server/javelin/`. Generated/updated as
> codec work progresses; cross-check against
> `analysis/replay_message_inventory.md` for byte-level details.

## Type → codec table

| Type | Direction | Captures | Bytes | Codec module | Notes |
|------|-----------|---------:|------:|--------------|-------|
| `0x03` | R | 1 | 88 | [`v3_response.py`](../server/javelin/v3_response.py) | V3 RegistrationResponse (encoder) |
| `0x08` | R | 79 | 78–46423 | [`chunked_stream_08.py`](../server/javelin/chunked_stream_08.py) | Two forms: standard (78 captures, 11-byte anchor + opaque tail) + UUID-prefixed (1 capture, the 46 KB world-data dump). Wake 103. |
| `0x13` | W | 1 | 2750 | [`v3_request.py`](../server/javelin/v3_request.py) | V3 RegistrationRequest. Strict → retry (tagged) → lenient chain (wakes 106-108). |
| `0xa4` | R | 2 | 20 | [`session_message_a4.py`](../server/javelin/session_message_a4.py) | Phase-5 SESSION small |
| `0x14f` | R | 4 | 12 | [`session_clock_beacon.py`](../server/javelin/session_clock_beacon.py) | Periodic; clock value matches V3 `mystery8` |
| `0x15d` | R+W | 20 | 12 / 36 | [`heartbeat_15d.py`](../server/javelin/heartbeat_15d.py) | Ping/ack pair; W body wraps ping verbatim |
| `0x1be` | R | 1 | 76 | [`handshake_blob_76.py`](../server/javelin/handshake_blob_76.py) | Handshake blob (paired with 0x40a) |
| `0x40a` | R | 1 | 76 | [`handshake_blob_76.py`](../server/javelin/handshake_blob_76.py) | Handshake blob (paired with 0x1be) |
| `0x5b2` | W | 4 | 45 / 93 | [`identity_fingerprint_5b2.py`](../server/javelin/identity_fingerprint_5b2.py) | Identity fingerprint set; 3 of 4 captures byte-identical (reliable resends) |
| `0x635` | W | 5 | 93–153 | [`action_history_635.py`](../server/javelin/action_history_635.py) | Action history queue; +15B per new message |
| `0x651` | R | 1 | 4 | [`empty_marker_651.py`](../server/javelin/empty_marker_651.py) | 4-byte type-header-only signal (no payload). Wake 100. |
| `0x65c` | R | 1 | 12706 | [`world_data_blob_65c.py`](../server/javelin/world_data_blob_65c.py) | Phase-4 WORLD DATA blob; structural codec walks 224-byte-ish records as (data, ff_padding) |
| `0x663` | R | 2 | 110 | [`level_descriptor_663.py`](../server/javelin/level_descriptor_663.py) | Level descriptor |
| `0x66b` | W | 1 | 44 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=0) | |
| `0x8e6` | R | 1 | 42 | [`identity_blob_8e6.py`](../server/javelin/identity_blob_8e6.py) | Receipt-handshake half; paired with 0x9fc |
| `0x9d3` | W | 1 | 48 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=4) | |
| `0x9fc` | W | 1 | 102 | [`receipt_handshake_9fc.py`](../server/javelin/receipt_handshake_9fc.py) | Echoes 0x8e6's opaque_blob; cross-codec invariant test |
| `0xa95` | W | 1 | 81 | [`permission_bitmap_a95.py`](../server/javelin/permission_bitmap_a95.py) | 36-byte feature/permission flag array |
| `0xca4` | R | 1 | 102 | [`asset_count_table_ca4.py`](../server/javelin/asset_count_table_ca4.py) | Count-prefixed table of (hash, value) records |
| `0xf7f` | W | 1 | 45 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=1) | |
| `0x101a` | W | 1 | 45 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=1) | |
| `0x101d` | W | 1 | 45 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=1) | |
| `0x102e` | W | 1 | 46 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=2) | |
| `0x102f` | W | 1 | 44 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=0) | |
| `0x1033` | R | 1 | 498 | [`opaque_blob_1033.py`](../server/javelin/opaque_blob_1033.py) | Identity-bundle prefix + opaque tail (presumed encrypted; see `wire_type_0x1033.md`). Wake 102. |
| `0x1067` | R | 1 | 86 | [`vivox_config_1067.py`](../server/javelin/vivox_config_1067.py) | Vivox voice-chat config (api_url, realm, issuer) |
| `0x1096` | R | 1 | 80 | [`frame_config_1096.py`](../server/javelin/frame_config_1096.py) | Structural codec: 6 floats / 2 u32 zero-pad pairs / 2 durations / 2 hashes / 2 doubled ratios. Wake 101. |
| `0x1097` | R | 1 | 24 | [`result_token_1097.py`](../server/javelin/result_token_1097.py) | Companion to 0x1096 (u32 BE result) |
| `0x1098` | W | 1 | 44 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=0) | |
| `0x10b0` | W | 1 | 45 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=1) | |
| `0x12f6` | W | 1 | 299 | [`keybinding_config_12f6.py`](../server/javelin/keybinding_config_12f6.py) | Client keybinding/control-config dump |
| `0x136a` | R | 1 | 28 | [`result_token_136a.py`](../server/javelin/result_token_136a.py) | Result token (u64 BE) |
| `0x143d` | W | 1 | 45 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=1) | |
| `0x16a0` | R | 2 | 153 / 99819 | [`asset_blob_16a0.py`](../server/javelin/asset_blob_16a0.py) (small + large) | Two forms: small (153 B, structural) and large (99 KB, opaque bulk). Both round-trip byte-exact. Wake 109. |
| `0x187c` | W | 1 | 45 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=1) | |
| `0x187f` | W | 1 | 45 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=1) | |
| `0x18a6` | R | 4 | 40 | [`init_message_18a6.py`](../server/javelin/init_message_18a6.py) | Init beacon with counter; pairs with 0x1a59 |
| `0x192c` | W | 1 | 54 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=10) | |
| `0x1a59` | W | 3 | 45 | [`session_subkey_1a59.py`](../server/javelin/session_subkey_1a59.py) (wraps `subkey_beacon`) | Counter-coupled with 0x18a6 |
| `0x1b88` | R | 23 | 42 | [`session_identity_beacon.py`](../server/javelin/session_identity_beacon.py) | Identical bytes across all 23 captures |

## Coverage summary

- **Total distinct type-IDs in capture**: 40
- **Codec'd**: **40 / 40 (100%)** — every captured wire-type has a codec module as of wake 109.
- Coverage depth varies:
  - **Structural** (full field-by-field): heartbeat 0x15d, init 0x18a6, session-clock 0x14f, identity blobs 0x8e6/0x9fc, V3 strict 0x13 first-attempt, frame_config 0x1096, etc.
  - **Framing-only** (anchor + opaque tail): chunked_stream 0x08 (both forms), opaque_blob 0x1033, asset_blob 0x16a0 large variant. Body too varied or presumed encrypted; preserved verbatim.
  - **Family** (generic shared codec): 13 subkey-beacon type-ids via `subkey_beacon.KNOWN_FAMILY` — typed dispatch on `(type_id, trailer_size)`.

Both audits (decoder rejection + encoder round-trip) are at **0
gaps** as of wake 136 — see
[`codec_test_audit.md`](codec_test_audit.md) and
[`codec_encoder_audit.md`](codec_encoder_audit.md).

The dispatcher (`server.javelin.dispatch`) routes 174+ captured
messages round-trip byte-identically; the only intentional decode
skip is `0x03` (V3 response — server-emit-only).

## When to add a new codec

Use the [cross-codec identity-bundle map in the inventory](replay_message_inventory.md#cross-codec-identity-bundle-map)
to check whether a new candidate type fits an existing
sub-system family. If it does, the codec can either:

1. Wrap `subkey_beacon` (for fixed-shape `[envelope + subkey +
   trailer]` messages) — see `session_subkey_1a59.py` for the
   pattern.
2. Add a typed `(type_id, trailer_size)` entry to
   `subkey_beacon.KNOWN_FAMILY` (for trailer-only variants).
3. Author a dedicated codec following the conventions in
   any of the existing modules — see the worklog
   (`autonomous_worklog.md`) wakes 66-80 for the patterns.

For any new codec:
- Put the wire layout in the module docstring with byte offsets.
- Round-trip the captured bytes byte-exact in a `test_codecs.py`
  test using `ReplayStore`.
- Add cross-codec invariant tests if the type shares fields with
  others (e.g. matching `second_id`, hash echoes, counter pairs).

## Library health snapshot (wake 146)

- **36 Python modules** in `server/javelin/` (codec + dispatch +
  framing + replay infra; see
  [`codec_library_overview.md`](codec_library_overview.md))
- **346 tests passing** (+1 skipped) in `test_codecs.py`
- **22 dedicated codecs** + **1 generic** (`subkey_beacon`,
  covering 14 W-direction types) + **1 SessionState sketch**
- **9 factory helpers** (`make_*`):
  `make_subkey_beacon`, `make_init_message_18a6`,
  `make_ack_for`, `make_session_clock_beacon`,
  `make_session_identity_beacon`, `make_session_message_a4`,
  `make_handshake_blob_76`, `make_result_token_136a`,
  `make_result_token_1097`
- **49 exports** from `server/javelin/__init__.py`
- **252 tests passing** in `test_codecs.py`
- **~35 of 40 captured type-IDs covered**

### Larger codec modules (≥ 200 lines)

| Module | Lines | Notes |
|---|---|---|
| `keybinding_config_12f6.py` | 303 | Most complex codec; walks variable-length string list |
| `subkey_beacon.py` | 283 | Generic family (14 types) |
| `level_info_changed.py` | 263 | AzCore-style with `AZStd::string` + `AZStd::vector` |
| `world_data_blob_65c.py` | 254 | Structural codec for the 12.7 KB WORLD DATA blob |
| `self_ident.py` | 228 | AzCore-style; not yet wired to runtime |
| `level_descriptor_663.py` | 220 | Pascal-style strings + level metadata |
| `receipt_handshake_9fc.py` | 209 | 0x8e6 echo invariant |
| `vivox_config_1067.py` | 178 | Three Pascal-prefixed strings |

### Smaller codec modules (< 200 lines)

Most simple message types fit in 100-170 lines including
docstrings, dataclass, validators, encode/decode, and self-test.
Generic shape: docstring + dataclass + encode/decode + an
optional `make_*` factory.

### Test density

`test_codecs.py` is **3149 lines** and contains 252 tests —
about ~12 lines per test on average. Most tests are
round-trip verifications against captured bytes, plus a few
cross-codec invariant tests (counter pairs, hash echoes,
identity-bundle uppers).

### Documentation footprint

- `analysis/replay_message_inventory.md` — byte-level structural
  reference for every type-ID
- `analysis/codec_coverage.md` — this file (type → module map)
- `analysis/integration_status.md` — codec ↔ server gap
- `analysis/queued_work.md` — themed todo list
- `analysis/static_re_handshake_signing.md` — RE note
- `analysis/static_re_1033_merkle.md` — RE note
- `docs/post-v3-sequence.md` — phase table with codec column
