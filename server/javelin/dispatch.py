"""
Wire-type dispatch — central decode router.

Maps every captured wire-type-id observed in the replay to its codec
module's decode entry-point. Built on top of the per-type codecs that
landed across wakes 86-103. As of wake 104:

  * 40 captured wire-types in the replay
  * 40 covered by codecs (varying depth — some structural, some
    framing-only with documented opaque tails)

`decode_replay_message(type_id, direction, body)` is the single entry
point. It returns the codec's decoded dataclass, or `bytes` for types
where the codec is intentionally framing-only.

The dispatcher does **not** include `0x03` (V3RegistrationResponse) —
that codec is server-emit-only (we generate the response, never parse
it from a peer). If a future use-case needs a 0x03 decoder, add it
here.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from . import (
    chunked_stream_08,
    session_message_a4,
    heartbeat_15d,
    handshake_blob_76,
    identity_fingerprint_5b2,
    action_history_635,
    empty_marker_651,
    world_data_blob_65c,
    level_descriptor_663,
    subkey_beacon,
    identity_blob_8e6,
    receipt_handshake_9fc,
    permission_bitmap_a95,
    asset_count_table_ca4,
    opaque_blob_1033,
    vivox_config_1067,
    frame_config_1096,
    result_token_1097,
    keybinding_config_12f6,
    result_token_136a,
    asset_blob_16a0,
    init_message_18a6,
    session_subkey_1a59,
    session_identity_beacon,
    session_clock_beacon,
    v3_request,
    v3_response,
)


# The 13 type-ids that go through subkey_beacon's generic family decoder.
SUBKEY_FAMILY_TYPE_IDS = frozenset(subkey_beacon.KNOWN_FAMILY)


# Decoder signature: (body, direction) -> object. `direction` is "R" or
# "W". Most codecs ignore it; heartbeat is the one current case where
# direction selects between two decoders.
DecoderFn = Callable[[bytes, str], Any]


def _direction_agnostic(decode: Callable[[bytes], Any]) -> DecoderFn:
    """Wrap a single-arg decode so it conforms to the (body, direction)
    signature."""
    def _wrap(body: bytes, _direction: str) -> Any:
        return decode(body)
    return _wrap


def _heartbeat_15d(body: bytes, direction: str) -> Any:
    if direction == "R":
        return heartbeat_15d.decode_ping(body)
    if direction == "W":
        return heartbeat_15d.decode_ack(body)
    raise ValueError(f"heartbeat 0x15d: unknown direction {direction!r}")


def _subkey_beacon(type_id: int) -> DecoderFn:
    """Build a direction-agnostic decoder for a subkey_beacon type-id."""
    def _wrap(body: bytes, _direction: str) -> Any:
        return subkey_beacon.decode(body, expected_type_id=type_id)
    return _wrap


# Static table: type_id -> decoder
DECODERS: dict[int, DecoderFn] = {
    # 0x03: V3RegistrationResponse — server-emit-only, intentionally absent
    0x08: _direction_agnostic(chunked_stream_08.decode_either),
    0x13: _direction_agnostic(v3_request.parse_v3_request_or_lenient),
    0xa4: _direction_agnostic(session_message_a4.decode),
    0x14f: _direction_agnostic(session_clock_beacon.decode),
    0x15d: _heartbeat_15d,
    0x1be: _direction_agnostic(handshake_blob_76.decode),
    0x40a: _direction_agnostic(handshake_blob_76.decode),
    0x5b2: _direction_agnostic(identity_fingerprint_5b2.decode),
    0x635: _direction_agnostic(action_history_635.decode),
    0x651: _direction_agnostic(empty_marker_651.decode),
    0x65c: _direction_agnostic(world_data_blob_65c.decode),
    0x663: _direction_agnostic(level_descriptor_663.decode),
    0x8e6: _direction_agnostic(identity_blob_8e6.decode),
    0x9fc: _direction_agnostic(receipt_handshake_9fc.decode),
    0xa95: _direction_agnostic(permission_bitmap_a95.decode),
    0xca4: _direction_agnostic(asset_count_table_ca4.decode),
    0x1033: _direction_agnostic(opaque_blob_1033.decode),
    0x1067: _direction_agnostic(vivox_config_1067.decode),
    0x1096: _direction_agnostic(frame_config_1096.decode),
    0x1097: _direction_agnostic(result_token_1097.decode),
    0x12f6: _direction_agnostic(keybinding_config_12f6.decode),
    0x136a: _direction_agnostic(result_token_136a.decode),
    0x16a0: _direction_agnostic(asset_blob_16a0.decode),
    0x18a6: _direction_agnostic(init_message_18a6.decode),
    0x1a59: _direction_agnostic(session_subkey_1a59.decode),
    0x1b88: _direction_agnostic(session_identity_beacon.decode),
}


# Add subkey_beacon family entries
for _tid in SUBKEY_FAMILY_TYPE_IDS:
    DECODERS[_tid] = _subkey_beacon(_tid)


def decode_replay_message(
    type_id: int,
    direction: str,
    body: bytes,
) -> Optional[Any]:
    """Decode a captured replay message into its codec dataclass.

    Returns the decoded object, or `None` if `type_id` is not registered
    (e.g. 0x03 — server-emit-only — or any type not yet covered).

    The codec's own validation runs; ValueError propagates so that
    bytes that don't fit the codec's expected layout fail loudly.
    """
    decoder = DECODERS.get(type_id)
    if decoder is None:
        return None
    return decoder(body, direction)


def supported_type_ids() -> frozenset[int]:
    """The set of type-ids the dispatcher knows how to decode."""
    return frozenset(DECODERS)


# ---------------------------------------------------------------------------
#  Encode side (wake 105)
# ---------------------------------------------------------------------------

# Encoder signature: (msg) -> bytes. Encoders take the codec dataclass
# and return the wire bytes. Direction is not needed at the parameter
# level because for the one direction-split codec (heartbeat) the
# message dataclass type itself disambiguates ping vs ack.
EncoderFn = Callable[[Any], bytes]


def _heartbeat_15d_encode(msg: Any) -> bytes:
    """Pick ping vs ack by isinstance."""
    if isinstance(msg, heartbeat_15d.HeartbeatPing15D):
        return heartbeat_15d.encode_ping(msg)
    if isinstance(msg, heartbeat_15d.HeartbeatAck15D):
        return heartbeat_15d.encode_ack(msg)
    raise TypeError(
        f"heartbeat 0x15d: unsupported msg type {type(msg).__name__}; "
        f"expected HeartbeatPing15D or HeartbeatAck15D"
    )


ENCODERS: dict[int, EncoderFn] = {
    0x03: v3_response.encode,
    0x08: chunked_stream_08.encode_either,
    0x13: v3_request.serialize_v3_request,
    0xa4: session_message_a4.encode,
    0x14f: session_clock_beacon.encode,
    0x15d: _heartbeat_15d_encode,
    0x1be: handshake_blob_76.encode,
    0x40a: handshake_blob_76.encode,
    0x5b2: identity_fingerprint_5b2.encode,
    0x635: action_history_635.encode,
    0x651: empty_marker_651.encode,
    0x65c: world_data_blob_65c.encode,
    0x663: level_descriptor_663.encode,
    0x8e6: identity_blob_8e6.encode,
    0x9fc: receipt_handshake_9fc.encode,
    0xa95: permission_bitmap_a95.encode,
    0xca4: asset_count_table_ca4.encode,
    0x1033: opaque_blob_1033.encode,
    0x1067: vivox_config_1067.encode,
    0x1096: frame_config_1096.encode,
    0x1097: result_token_1097.encode,
    0x12f6: keybinding_config_12f6.encode,
    0x136a: result_token_136a.encode,
    0x16a0: asset_blob_16a0.encode,
    0x18a6: init_message_18a6.encode,
    0x1a59: session_subkey_1a59.encode,
    0x1b88: session_identity_beacon.encode,
}

# Subkey-beacon family: every type-id in KNOWN_FAMILY shares the same
# encoder; the type_id is carried inside the SubkeyBeacon dataclass.
for _tid in SUBKEY_FAMILY_TYPE_IDS:
    ENCODERS[_tid] = subkey_beacon.encode


def encode_replay_message(type_id: int, msg: Any) -> bytes:
    """Encode a codec dataclass back into wire bytes.

    Returns the wire body (typed envelope header + payload as the
    codec produces it). Raises `KeyError` if `type_id` has no
    registered encoder, or `TypeError` from the encoder if `msg` is
    the wrong dataclass for the type.
    """
    encoder = ENCODERS.get(type_id)
    if encoder is None:
        raise KeyError(
            f"no encoder registered for type 0x{type_id:x}"
        )
    return encoder(msg)


def encodable_type_ids() -> frozenset[int]:
    """The set of type-ids the dispatcher knows how to encode."""
    return frozenset(ENCODERS)
