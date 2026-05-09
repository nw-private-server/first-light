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
| `0x08` | R | 79 | 78–46423 | — | Continuous entity-state stream; 24 byte-identical 46407B snapshots are pure transport-layer resends |
| `0x13` | W | 1 | 2750 | — | V3 RegistrationRequest (the client side; envelope/body parser lives in `v3_request.py`) |
| `0xa4` | R | 2 | 20 | [`session_message_a4.py`](../server/javelin/session_message_a4.py) | Phase-5 SESSION small |
| `0x14f` | R | 4 | 12 | [`session_clock_beacon.py`](../server/javelin/session_clock_beacon.py) | Periodic; clock value matches V3 `mystery8` |
| `0x15d` | R+W | 20 | 12 / 36 | [`heartbeat_15d.py`](../server/javelin/heartbeat_15d.py) | Ping/ack pair; W body wraps ping verbatim |
| `0x1be` | R | 1 | 76 | [`handshake_blob_76.py`](../server/javelin/handshake_blob_76.py) | Handshake blob (paired with 0x40a) |
| `0x40a` | R | 1 | 76 | [`handshake_blob_76.py`](../server/javelin/handshake_blob_76.py) | Handshake blob (paired with 0x1be) |
| `0x5b2` | W | 4 | 45 / 93 | [`identity_fingerprint_5b2.py`](../server/javelin/identity_fingerprint_5b2.py) | Identity fingerprint set; 3 of 4 captures byte-identical (reliable resends) |
| `0x635` | W | 5 | 93–153 | [`action_history_635.py`](../server/javelin/action_history_635.py) | Action history queue; +15B per new message |
| `0x651` | R | 1 | 4 | — | 4-byte type-header-only signal (no payload) |
| `0x65c` | R | 1 | 12706 | — | Phase-4 WORLD DATA blob; 224-byte fixed-record skeleton documented in inventory |
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
| `0x1033` | R | 1 | 498 | — | Merkle-shape blob; offset-5/450 8-byte repeat documented |
| `0x1067` | R | 1 | 86 | [`vivox_config_1067.py`](../server/javelin/vivox_config_1067.py) | Vivox voice-chat config (api_url, realm, issuer) |
| `0x1096` | R | 1 | 80 | — | Spawn-position floats; paired with 0x1097 |
| `0x1097` | R | 1 | 24 | [`result_token_1097.py`](../server/javelin/result_token_1097.py) | Companion to 0x1096 (u32 BE result) |
| `0x1098` | W | 1 | 44 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=0) | |
| `0x10b0` | W | 1 | 45 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=1) | |
| `0x12f6` | W | 1 | 299 | [`keybinding_config_12f6.py`](../server/javelin/keybinding_config_12f6.py) | Client keybinding/control-config dump |
| `0x136a` | R | 1 | 28 | [`result_token_136a.py`](../server/javelin/result_token_136a.py) | Result token (u64 BE) |
| `0x143d` | W | 1 | 45 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=1) | |
| `0x16a0` | R | 2 | 153 / 99819 | [`asset_blob_16a0.py`](../server/javelin/asset_blob_16a0.py) (small only) | Small variant codec'd; large is chunked-replay |
| `0x187c` | W | 1 | 45 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=1) | |
| `0x187f` | W | 1 | 45 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=1) | |
| `0x18a6` | R | 4 | 40 | [`init_message_18a6.py`](../server/javelin/init_message_18a6.py) | Init beacon with counter; pairs with 0x1a59 |
| `0x192c` | W | 1 | 54 | [`subkey_beacon.py`](../server/javelin/subkey_beacon.py) (generic, trailer=10) | |
| `0x1a59` | W | 3 | 45 | [`session_subkey_1a59.py`](../server/javelin/session_subkey_1a59.py) (wraps `subkey_beacon`) | Counter-coupled with 0x18a6 |
| `0x1b88` | R | 23 | 42 | [`session_identity_beacon.py`](../server/javelin/session_identity_beacon.py) | Identical bytes across all 23 captures |

## Coverage summary

- **Total distinct type-IDs in capture**: 40
- **Codec'd**: 33 (20 dedicated + 13 via the generic `subkey_beacon` family)
- **Documented but no codec**: 7
  - `0x08` — entity-state TLV stream (would need handler-side static-RE for the inner format)
  - `0x13` — V3 RegistrationRequest (parser side; the V3 envelope handling lives in `v3_request.py` for the protocol-framing code path)
  - `0x651` — 4-byte type-header-only signal (no payload to codec)
  - `0x65c` — 12.7 KB Phase-4 WORLD DATA blob (224-byte fixed-record skeleton documented; codec deferred pending semantic info)
  - `0x1033` — 498-byte Merkle-shape blob
  - `0x1096` — spawn-position floats (no codec; paired companion 0x1097 is codec'd)
  - `0x16a0` large variant (~99 KB, chunked-replay; reassembly handled by `wire.py`)

The library covers the messages most likely to need server-side
**replay fidelity** (V3 response, identity beacons, counter pairs,
handshake-family signing trailer carriers, asset-count tables,
Vivox config, keybinding config). The remaining gaps are
content-stream / large-blob / chunked-replay cases that either
need handler-side static-RE or are large enough that a structural
codec wouldn't add real value vs preserving raw bytes.

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
