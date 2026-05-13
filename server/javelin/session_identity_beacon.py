"""
Session identity beacon — type 0x1b88.

Captured in the existing replay 23 times with identical bytes.
See `analysis/replay_message_inventory.md` for the byte-level
analysis. Hypothesis: this is a periodic "I'm still here" beacon
the server emits with the connection's session UUID.

Wire layout (after the 4-byte typed envelope header
`[00 01 88 6e]`):

  +0x00  u8x16  session_uuid (16 raw bytes — UUID-shaped)
  +0x10  u8x22  zero padding

Total payload: 38 bytes. Total body (with type header): 42 bytes.

The session UUID's lower 8 bytes match the lower 8 of `0xa4` and
`0x18a6`'s session-id fields, suggesting a shared "connection
family" identifier. See `analysis/replay_message_inventory.md` for
the cross-type breakdown.
"""

from __future__ import annotations

from dataclasses import dataclass


# Total wire-form size INCLUDING the 4-byte typed envelope header
TYPED_BODY_SIZE = 42

# Just the payload (without the 4-byte header)
PAYLOAD_SIZE = 38

# The 4-byte typed-envelope header for type 0x1b88:
#   marker bytes [0x00, 0x01], then ((0x1b88 & 0x3f) | 0x80) = 0x88,
#   then ((0x1b88 >> 6) & 0xff) = 0x6e
TYPE_HEADER = bytes((0x00, 0x01, 0x88, 0x6e))

PADDING = bytes(22)  # 22 zero bytes that follow the UUID in every captured msg


@dataclass
class SessionIdentityBeacon:
    """Type 0x1b88 — periodic session-identity broadcast."""

    # 16 raw UUID bytes. Same value across all 23 captures (it's the
    # session UUID for that specific recorded session).
    session_uuid: bytes

    def __post_init__(self) -> None:
        if len(self.session_uuid) != 16:
            raise ValueError(
                f"session_uuid must be exactly 16 bytes; got {len(self.session_uuid)}"
            )


def make_session_identity_beacon(session_uuid: bytes) -> SessionIdentityBeacon:
    """Build a `SessionIdentityBeacon` (0x1b88) from the live session UUID.

    Captures showed 23 byte-identical 42-byte messages — this beacon
    is rebroadcast periodically with the same payload. Server-side
    code emits a single instance and re-sends at the
    captured cadence.
    """
    return SessionIdentityBeacon(session_uuid=session_uuid)


def encode(msg: SessionIdentityBeacon) -> bytes:
    """Build the on-wire SessionIdentityBeacon body INCLUDING the
    4-byte typed envelope header.

    Returns 42 bytes total. The fixed-zero padding at +0x10..+0x25
    is emitted automatically — every captured copy of this message
    had the same 22 zeros there.
    """
    return TYPE_HEADER + msg.session_uuid + PADDING


def decode(buf: bytes) -> SessionIdentityBeacon:
    """Parse an on-wire SessionIdentityBeacon body (with type header).

    Inverse of `encode()`. Raises `ValueError` on size mismatch,
    type-header mismatch, or non-zero padding.
    """
    if len(buf) != TYPED_BODY_SIZE:
        raise ValueError(
            f"expected exactly {TYPED_BODY_SIZE} bytes; got {len(buf)}"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )
    session_uuid = buf[4:20]
    padding = buf[20:42]
    if padding != PADDING:
        raise ValueError(
            f"trailing padding non-zero: {padding.hex()} (expected 22 zero bytes)"
        )
    return SessionIdentityBeacon(session_uuid=session_uuid)


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Capture a real example from the replay store:
    #   00 01 88 6e   e2 64 0b 7c e5 40 80 36 bf 85 31 4b bc 4a 95 1a   ...22 zeros...
    captured = bytes.fromhex(
        "0001886e"
        "e2640b7ce5408036bf85314bbc4a951a"
        + "00" * 22
    )
    msg = decode(captured)
    print(f"decoded: session_uuid={msg.session_uuid.hex()}")
    rebuilt = encode(msg)
    assert rebuilt == captured, "round-trip failed"
    print(f"len={len(rebuilt)} bytes — round-trip OK")
