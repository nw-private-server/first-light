"""
Heartbeat ping/ack — type 0x15d.

20 captures in the existing replay split into two distinct shapes
that come in matched pairs:

- **R direction, 12 bytes** — the server's ping. Carries a slow-
  incrementing counter (similar pattern to the 0x14f session_clock)
  and a per-message nonce.
- **W direction, 36 bytes** — the client's ack. Wraps the server's
  ping body in an envelope with a 4-byte client hash and a length
  field.

The two shapes appear in seq pairs (server emits 0x15d R at seq N,
client replies 0x15d W at seq N+1), and the W body's last 12 bytes
are byte-identical to the R body. So this is a heartbeat protocol
with explicit echo for liveness/sequence verification.

Wire layout (after the 4-byte typed envelope header `[00 01 9d 05]`):

  R direction (`HeartbeatPing15D`, 12 bytes total):
    +0x00  u32 BE  counter      slowly increments across the session
    +0x04  u32     nonce        per-message random

  W direction (`HeartbeatAck15D`, 36 bytes total — type header is
  NOT at the start; the wrapper field is. The echoed ping body
  (with its own type header) lives at the END):
    +0x00  u8x4   client_hash   per-message hash/correlation-id
    +0x04  u32 BE remaining_len = 0x1c (28 bytes — matches +0x08..+0x23)
    +0x08  u8x16  padding       all zero in every captured copy
    +0x18  u8x12  echoed_ping   the full 12-byte server ping incl. its
                                 4-byte type header (`[00 01 9d 05]
                                 [u32 BE counter][u32 nonce]`)

The W message does NOT carry the typed envelope header at the very
start — `client_hash` is at byte 0. The "type 0x15d W" identification
comes from the wrapped echoed_ping at +0x18.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


# ---------------------------------------------------------------------------
#  Shared
# ---------------------------------------------------------------------------

# 4-byte typed envelope header for type 0x15d:
#   marker [0x00, 0x01], then ((0x15d & 0x3f) | 0x80) = 0x9d,
#   then ((0x15d >> 6) & 0xff) = 0x05
TYPE_HEADER = bytes((0x00, 0x01, 0x9d, 0x05))

PING_TYPED_BODY_SIZE = 12  # R direction
ACK_TYPED_BODY_SIZE = 36   # W direction
ACK_REMAINING_LEN = 0x1c   # value of the BE length field in W messages
ACK_PADDING = bytes(16)    # 16 zero bytes at +0x08..+0x17 in every captured ack


# ---------------------------------------------------------------------------
#  Ping (R direction, 12 bytes)
# ---------------------------------------------------------------------------


@dataclass
class HeartbeatPing15D:
    """Server-side 0x15d ping (12 bytes total)."""

    counter: int   # u32 BE — slow-incrementing per-session counter
    nonce: int     # u32 BE — per-message random

    def __post_init__(self) -> None:
        if not 0 <= self.counter <= 0xFFFFFFFF:
            raise ValueError(f"counter must fit in u32; got {self.counter}")
        if not 0 <= self.nonce <= 0xFFFFFFFF:
            raise ValueError(f"nonce must fit in u32; got {self.nonce}")


def encode_ping(msg: HeartbeatPing15D) -> bytes:
    """Build the R-direction 12-byte ping (with type header)."""
    return (
        TYPE_HEADER
        + msg.counter.to_bytes(4, "big")
        + msg.nonce.to_bytes(4, "big")
    )


def decode_ping(buf: bytes) -> HeartbeatPing15D:
    """Parse the R-direction 12-byte ping. Raises on size or type-header
    mismatch."""
    if len(buf) != PING_TYPED_BODY_SIZE:
        raise ValueError(
            f"expected exactly {PING_TYPED_BODY_SIZE} bytes; got {len(buf)}"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )
    return HeartbeatPing15D(
        counter=int.from_bytes(buf[4:8], "big"),
        nonce=int.from_bytes(buf[8:12], "big"),
    )


# ---------------------------------------------------------------------------
#  Ack (W direction, 36 bytes — wraps the ping)
# ---------------------------------------------------------------------------


@dataclass
class HeartbeatAck15D:
    """Client-side 0x15d ack (36 bytes total). Wraps the server's
    ping body."""

    client_hash: bytes               # 4 bytes
    echoed_ping: HeartbeatPing15D    # the server's ping that this acks

    def __post_init__(self) -> None:
        if len(self.client_hash) != 4:
            raise ValueError(
                f"client_hash must be exactly 4 bytes; got {len(self.client_hash)}"
            )


def encode_ack(msg: HeartbeatAck15D) -> bytes:
    """Build the W-direction 36-byte ack."""
    return (
        msg.client_hash
        + struct.pack(">I", ACK_REMAINING_LEN)
        + ACK_PADDING
        + encode_ping(msg.echoed_ping)
    )


def decode_ack(buf: bytes) -> HeartbeatAck15D:
    """Parse the W-direction 36-byte ack. Raises on size, length-field,
    padding, or wrapped-ping errors."""
    if len(buf) != ACK_TYPED_BODY_SIZE:
        raise ValueError(
            f"expected exactly {ACK_TYPED_BODY_SIZE} bytes; got {len(buf)}"
        )
    client_hash = buf[0:4]
    (remaining,) = struct.unpack_from(">I", buf, 4)
    if remaining != ACK_REMAINING_LEN:
        raise ValueError(
            f"remaining-length field mismatch: expected 0x{ACK_REMAINING_LEN:x}, "
            f"got 0x{remaining:x}"
        )
    padding = buf[8:24]
    if padding != ACK_PADDING:
        raise ValueError(
            f"padding non-zero: {padding.hex()}"
        )
    echoed_ping = decode_ping(buf[24:36])
    return HeartbeatAck15D(client_hash=client_hash, echoed_ping=echoed_ping)


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured_ping = bytes.fromhex("00019d05" "00036ef6" "af912d74")
    ping = decode_ping(captured_ping)
    print(f"ping: counter=0x{ping.counter:x}, nonce=0x{ping.nonce:x}")
    assert encode_ping(ping) == captured_ping

    captured_ack = bytes.fromhex(
        "65c50b2b"
        "0000001c"
        + "00" * 16
        + "00019d05"
        "00036ef6"
        "af912d74"
    )
    ack = decode_ack(captured_ack)
    print(
        f"ack: client_hash={ack.client_hash.hex()}, "
        f"echoed_ping.counter=0x{ack.echoed_ping.counter:x}"
    )
    assert encode_ack(ack) == captured_ack
    print("OK — both ping/ack round-trip")
