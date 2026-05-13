# Codec encoder audit — wake 135

Companion to `codec_test_audit.md` (decoder-side, wakes 125-126).
This audit asks: do all 27 codec modules with an `encode()`
function have a test that round-trips a **populated dataclass**
through encode → decode and asserts equality?

The earlier `test_dispatch_encode_decode_round_trip_full_replay`
test (wake 105) exercises every captured type's encoder path —
but only with the values that happen to appear in the bundled
replay. A populated-dataclass test exercises edge values, max
u32, all-zero fields, etc. that the replay may not cover.

## Method

For each codec module's `encode*()` functions:

1. Find all dataclasses the module exports (`^class \w+:`).
2. Search `test_codecs.py` for test functions whose name
   references the codec module (by module name, leading word,
   or class-name fragment).
3. Within each candidate test, check that the body contains
   both `encode` and `decode` plus an `assert` — a populated
   round-trip pattern.

The heuristic is keyword-based; a future refinement could parse
test ASTs to be more rigorous.

## Coverage table

| Module | Encoders | Populated round-trip |
|---|---:|---|
| `action_history_635` | 1 | ✓ (wake 135 added) |
| `asset_blob_16a0` | 3 | ✓ (wake 136 added — small + large variants) |
| `asset_count_table_ca4` | 1 | ✓ (wake 136 added) |
| `chunked_stream_08` | 3 | ✓ |
| `empty_marker_651` | 1 | ✓ |
| `frame_config_1096` | 1 | ✓ |
| `handshake_blob_76` | 1 | ✓ |
| `heartbeat_15d` | 2 | ✓ |
| `identity_blob_8e6` | 1 | ✓ |
| `identity_fingerprint_5b2` | 1 | ✓ |
| `init_message_18a6` | 1 | ✓ |
| `keybinding_config_12f6` | 1 | ✓ |
| `level_descriptor_663` | 1 | ✓ |
| `level_info_changed` | 1 | ✓ |
| `opaque_blob_1033` | 1 | ✓ |
| `permission_bitmap_a95` | 1 | ✓ (wake 135 added) |
| `receipt_handshake_9fc` | 1 | ✓ (wake 135 added) |
| `result_token_1097` | 1 | ✓ |
| `result_token_136a` | 1 | ✓ |
| `self_ident` | 3 | ✓ |
| `session_clock_beacon` | 1 | ✓ |
| `session_identity_beacon` | 1 | ✓ |
| `session_message_a4` | 1 | ✓ |
| `session_subkey_1a59` | 1 | ✓ |
| `subkey_beacon` | 1 | ✓ |
| `v3_response` | 1 | ✓ |
| `vivox_config_1067` | 1 | ✓ (wake 136 added) |
| `world_data_blob_65c` | 1 | ✓ (wake 136 added) |

`dispatch` and `wire` are routing/utility modules with `encode*`
helpers but no dataclass — out of scope for this audit.

## Wake-135 fix-ups

Added 3 populated round-trip tests for the lowest-effort gaps:

- `test_permission_bitmap_a95_populated_round_trip`
- `test_action_history_635_populated_round_trip`
- `test_receipt_handshake_9fc_populated_round_trip`

Each constructs a fully-populated dataclass with non-trivial
field values (subkey, session_uuid, hashes, etc.), encodes it,
decodes the wire bytes, and asserts the result equals the
original. **Gap count: 7 → 4.**

## Remaining 4 gaps — closed wake 136

Filled in wake 136 with 5 additional populated round-trip tests
(asset_blob has both small + large variants tested):

- **`asset_blob_16a0`** — small variant: 16-byte asset_uuid +
  133-byte payload. Large variant: 16-byte uuid + 1 KB
  varied bulk_data. Both via dedicated tests.
- **`asset_count_table_ca4`** — 8 `AssetCountRecord` items with
  varying hash_ids + values, identity_uuid populated, custom
  trailer byte.
- **`vivox_config_1067`** — realistic api_url, realm, issuer
  strings (matching the captured replay's shape).
- **`world_data_blob_65c`** — 5 `WorldDataRecord` items with
  varying data lengths + ff_padding; `decode(..., validate_shared_trailer=False)`
  since synthetic bytes don't match the captured handshake-
  trailer invariant.

**Gap count: 4 → 0**. Every encoder-bearing codec module now has
at least one populated round-trip test.

Final test count: **341 → 346 (+5 in wake 136)**.

## Limitations

- Keyword bucketing matches conservatively. Some tests
  legitimately exercising a codec may be miscategorized as
  "other" if they don't reference the codec by its module or
  class name in the function name.
- The audit doesn't verify the test actually exercises all
  fields of the dataclass — only that it round-trips at all.
  A more thorough audit would parse the test body for which
  fields are set.

Cap follow-up: codec_test_audit_v2.md after AST-based parsing
of `pytest.raises` and field-coverage. Not urgent.
