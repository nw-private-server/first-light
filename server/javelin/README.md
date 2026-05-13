# `server/javelin/` — codec library

This directory contains the wire-protocol codec library: per-type
encoders / decoders for every wire-type observed in the captured
DTLS replay, plus framing primitives and the central dispatcher.

For the architectural walkthrough — layered structure, coverage
depth glossary, "how to add a new codec" — see
[`analysis/codec_library_overview.md`](../../analysis/codec_library_overview.md).
This file is the directory-level TOC.

## Entry point

For most callers:

```python
from server.javelin import dispatch

msg = dispatch.decode_replay_message(type_id, direction, body)
wire = dispatch.encode_replay_message(type_id, msg)
```

`dispatch.py` knows every captured wire-type plus `0x5d1` (the
SelfIdentification trigger that's not in the captured replay but
which the server will need to emit — see
[`analysis/state_10_unblock_synthesis.md`](../../analysis/state_10_unblock_synthesis.md)).

## Module index

### Wire-framing primitives

| Module | Purpose |
|---|---|
| [`bitstream.py`](bitstream.py) | Bit-level reader/writer matching `Javelin_BitStream_ReadBits`. |
| [`frame.py`](frame.py) | Datagram, record, and system-message framing — mirrors `Javelin_Carrier_ParseMessages`. |
| [`wire.py`](wire.py) | C→S CRC32 framing helpers (`compute_cs_crc32`, `serialize_cs_envelope`, `fixup_cs_crc32`, etc). |

### Per-type codecs (alphabetical)

| Module | Wire type | Direction |
|---|---|---|
| [`action_history_635.py`](action_history_635.py) | `0x635` | W |
| [`asset_blob_16a0.py`](asset_blob_16a0.py) | `0x16a0` | R (small + large variants) |
| [`asset_count_table_ca4.py`](asset_count_table_ca4.py) | `0xca4` | R |
| [`chunked_stream_08.py`](chunked_stream_08.py) | `0x08` | R (standard + UUID-prefixed) |
| [`empty_marker_651.py`](empty_marker_651.py) | `0x651` | R (zero-payload trigger) |
| [`frame_config_1096.py`](frame_config_1096.py) | `0x1096` | R |
| [`handshake_blob_76.py`](handshake_blob_76.py) | `0x40a` / `0x1be` | R (shared 76-byte family) |
| [`heartbeat_15d.py`](heartbeat_15d.py) | `0x15d` | R + W (ping / ack pair) |
| [`identity_blob_8e6.py`](identity_blob_8e6.py) | `0x8e6` | R |
| [`identity_fingerprint_5b2.py`](identity_fingerprint_5b2.py) | `0x5b2` | W |
| [`init_message_18a6.py`](init_message_18a6.py) | `0x18a6` | W |
| [`keybinding_config_12f6.py`](keybinding_config_12f6.py) | `0x12f6` | W |
| [`level_descriptor_663.py`](level_descriptor_663.py) | `0x663` | R |
| [`level_info_changed.py`](level_info_changed.py) | (AzCore-style) | R |
| [`opaque_blob_1033.py`](opaque_blob_1033.py) | `0x1033` | R (framing-only — body presumed encrypted) |
| [`permission_bitmap_a95.py`](permission_bitmap_a95.py) | `0xa95` | W |
| [`receipt_handshake_9fc.py`](receipt_handshake_9fc.py) | `0x9fc` | W |
| [`result_token_1097.py`](result_token_1097.py) | `0x1097` | R |
| [`result_token_136a.py`](result_token_136a.py) | `0x136a` | R |
| [`self_ident.py`](self_ident.py) | `0x5d1` | (synthetic — state-10 unblock trigger) |
| [`session_clock_beacon.py`](session_clock_beacon.py) | `0x14f` | R |
| [`session_identity_beacon.py`](session_identity_beacon.py) | `0x1b88` | R |
| [`session_message_a4.py`](session_message_a4.py) | `0xa4` | R |
| [`session_subkey_1a59.py`](session_subkey_1a59.py) | `0x1a59` | W |
| [`v3_request.py`](v3_request.py) | `0x13` | W (strict + retry-tagged + lenient parsers) |
| [`v3_response.py`](v3_response.py) | `0x03` | R (encode-only — server-emitted) |
| [`vivox_config_1067.py`](vivox_config_1067.py) | `0x1067` | R |
| [`world_data_blob_65c.py`](world_data_blob_65c.py) | `0x65c` | R |

### Family / generic codecs

| Module | Coverage |
|---|---|
| [`subkey_beacon.py`](subkey_beacon.py) | 13 type-ids in the W-direction subkey-beacon family (see `KNOWN_FAMILY` constant). |

### Dispatcher and supporting

| Module | Purpose |
|---|---|
| [`dispatch.py`](dispatch.py) | Central type-id → codec router (decode + encode). |
| [`replay_store.py`](replay_store.py) | Parses the captured DTLS replay file into `Message` records. |
| [`replay_substitution.py`](replay_substitution.py) | Fills redacted spans in captured replays with live-session identity. |
| [`session_state.py`](session_state.py) | Per-peer session-state scaffolding (not yet plumbed into the runtime). |

### Tests

`test_codecs.py` — single test file, ~3700+ lines as of wake 117.
Includes round-trip coverage, captured-replay byte-identity,
structural rejection, and dispatcher coverage tests.

```sh
.venv/bin/pytest server/javelin/test_codecs.py
# 320+ passing as of wake 117
```

## Hand-debug a single message

```sh
.venv/bin/python3 ../../tools/decode_message.py --type 0x15d --replay-index 0 --direction R
```

Prints the decoded codec dataclass for the first captured 0x15d
ping. See
[`tools/decode_message.py`](../../tools/decode_message.py)
for the full CLI options.
