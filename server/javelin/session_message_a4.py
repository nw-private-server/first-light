"""
Session message — type 0xa4 (small variant).

Per `docs/post-v3-sequence.md`, type `0xa4` appears at Phase 5
("INIT 0x91(0x19) + small 0xa4") and Phase 6 ("SESSION 0xa4 large").
The 2 occurrences in the existing capture are both the small
20-byte variant — just the 4-byte typed envelope header followed by
a 16-byte session UUID (no flags, no padding, no counter).

Wire layout (after the 4-byte typed envelope header `[00 01 a4 02]`):

  +0x00  u8x16  session_uuid

Total body (with type header): 20 bytes.

The session UUID's lower 8 bytes are shared with the `0x1b88`
(`session_identity_beacon`) and `0x18a6` payloads in the same
capture — see `analysis/replay_message_inventory.md`.

The "large" 0xa4 variant (Phase 6, ~75 bytes retail / 195 bytes
test-39) is a different layout and is NOT covered by this codec.
A future capture covering Phase 6 would let us add a separate
LargeSessionMessageA4 codec.
"""

from __future__ import annotations

from dataclasses import dataclass


TYPED_BODY_SIZE = 20
PAYLOAD_SIZE = 16

# 4-byte typed envelope header for type 0xa4:
#   marker [0x00, 0x01], then ((0xa4 & 0x3f) | 0x80) = 0xa4,
#   then ((0xa4 >> 6) & 0xff) = 0x02
TYPE_HEADER = bytes((0x00, 0x01, 0xa4, 0x02))


@dataclass
class SessionMessageA4:
    """Type 0xa4 small variant — session-UUID handshake beacon."""

    session_uuid: bytes  # 16 raw UUID bytes

    def __post_init__(self) -> None:
        if len(self.session_uuid) != 16:
            raise ValueError(
                f"session_uuid must be exactly 16 bytes; got {len(self.session_uuid)}"
            )


def make_session_message_a4(session_uuid: bytes) -> SessionMessageA4:
    """Build a `SessionMessageA4` (0xa4 small) from the live session UUID.

    Phase-5 SESSION small per `docs/post-v3-sequence.md`. The body is
    just the 16-byte session UUID; this helper exists for symmetry
    with the other `make_*` factories so server-side code can build
    all session-bringup messages from a single `session_uuid` value.
    """
    return SessionMessageA4(session_uuid=session_uuid)


def encode(msg: SessionMessageA4) -> bytes:
    """Build the on-wire 0xa4 small body INCLUDING the type header.

    Returns 20 bytes total.
    """
    return TYPE_HEADER + msg.session_uuid


def decode(buf: bytes) -> SessionMessageA4:
    """Parse an on-wire 0xa4 small body.

    Inverse of `encode()`. Raises `ValueError` on size mismatch or
    type-header mismatch. Note: this codec only handles the SMALL
    20-byte variant — Phase 6's 0xa4 large is a different layout
    not yet characterized.
    """
    if len(buf) != TYPED_BODY_SIZE:
        raise ValueError(
            f"expected exactly {TYPED_BODY_SIZE} bytes for 0xa4 small "
            f"variant; got {len(buf)} (large variant is unsupported)"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )
    return SessionMessageA4(session_uuid=buf[4:20])


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "0001a402"
        "1a954abc4b3185bfbe37c3d8592618e0"
    )
    msg = decode(captured)
    print(f"decoded: session_uuid={msg.session_uuid.hex()}")
    rebuilt = encode(msg)
    assert rebuilt == captured, "round-trip failed"
    print(f"len={len(rebuilt)} bytes — round-trip OK")
