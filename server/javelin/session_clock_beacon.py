"""
Session-clock beacon — type 0x14f.

12-byte beacon the server emits periodically. The 4 occurrences in
the existing replay carry a u32 BE session clock (which slowly
increments across the session) plus a u32 nonce (different in each
capture).

The session clock matches the V3 response's `mystery8` first 4
bytes — see `analysis/replay_message_inventory.md`. So when the
server emits a 0x14f beacon, the embedded `session_clock` is the
same logical value that's at offset +0x07..+0x0a of the V3
response.

Wire layout (after the 4-byte typed envelope header `[00 01 8f 05]`):

  +0x00  u32 BE  session_clock     0x0b888d68 in the first capture
  +0x04  u32 BE  nonce             different in each capture

Total body (with type header): 12 bytes.

The 4 captured copies of this message have session_clock values
[0x0b888d68, 0x0b888d68, 0x0b888d69, 0x0b888d69] across seqs
[0xa, 0x27, 0x3c, 0x54] — the value transitions between seqs
0x27 and 0x3c.
"""

from __future__ import annotations

from dataclasses import dataclass


TYPED_BODY_SIZE = 12
PAYLOAD_SIZE = 8

# 4-byte typed envelope header for type 0x14f:
#   marker [0x00, 0x01], then ((0x14f & 0x3f) | 0x80) = 0x8f,
#   then ((0x14f >> 6) & 0xff) = 0x05
TYPE_HEADER = bytes((0x00, 0x01, 0x8f, 0x05))


@dataclass
class SessionClockBeacon:
    """Type 0x14f — periodic session-clock beacon."""

    session_clock: int  # u32 BE — slow-incrementing per-session timer
    nonce: int          # u32 BE — per-message nonce

    def __post_init__(self) -> None:
        if not 0 <= self.session_clock <= 0xFFFFFFFF:
            raise ValueError(
                f"session_clock must fit in u32; got {self.session_clock}"
            )
        if not 0 <= self.nonce <= 0xFFFFFFFF:
            raise ValueError(f"nonce must fit in u32; got {self.nonce}")


def make_session_clock_beacon(
    session_clock: int,
    nonce: int,
) -> SessionClockBeacon:
    """Build a `SessionClockBeacon` from session-state values.

    Server-side replay code can call this to mint a fresh 0x14f with
    the live session_clock + a per-message nonce (e.g. `os.urandom(4)`
    folded to u32). The 4-byte session_clock is the same field
    embedded in the V3 RegistrationResponse's `mystery8[0..4]` —
    server-side code should keep both in sync (a single
    `session_clock` u32 used by both emission paths).
    """
    return SessionClockBeacon(session_clock=session_clock, nonce=nonce)


def encode(msg: SessionClockBeacon) -> bytes:
    """Build the on-wire 0x14f body INCLUDING the type header.

    Returns 12 bytes total.
    """
    return (
        TYPE_HEADER
        + msg.session_clock.to_bytes(4, "big")
        + msg.nonce.to_bytes(4, "big")
    )


def decode(buf: bytes) -> SessionClockBeacon:
    """Parse an on-wire 0x14f body.

    Inverse of `encode()`. Raises `ValueError` on size mismatch or
    type-header mismatch.
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
    session_clock = int.from_bytes(buf[4:8], "big")
    nonce = int.from_bytes(buf[8:12], "big")
    return SessionClockBeacon(session_clock=session_clock, nonce=nonce)


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex("00018f05" "0b888d68" "7b13001a")
    msg = decode(captured)
    print(f"decoded: session_clock=0x{msg.session_clock:x}, nonce=0x{msg.nonce:x}")
    rebuilt = encode(msg)
    assert rebuilt == captured, "round-trip failed"
    print(f"len={len(rebuilt)} bytes — round-trip OK")
