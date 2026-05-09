"""
Session subkey beacon — type 0x1a59 (W direction).

3 captures in the existing replay; **all three are 45 bytes** and
share the same payload shape, with only a 4-byte client hash and a
1-byte counter varying across messages.

This is a client-side beacon that pairs the session UUID with the
same 16-byte "session subkey" that appears at the start of `0x18a6`
(see `init_message_18a6.py`). The counter increments monotonically
across the captured copies (0x02 → 0x03 → 0x04), matching the
`0x18a6` counter pattern.

Wire layout (full 45-byte W-direction message):

  +0x00  u8x4    client_hash       per-message correlation/hash
  +0x04  u32 BE  remaining_len     0x25 = 37 = total - 8
  +0x08  u8x16   session_uuid      full session UUID (matches 0xa4)
  +0x18  u8x4    type_header       [00 01 99 69] = type 0x1a59
  +0x1c  u8x16   subkey            [first_uuid_half:8][session_uuid_lower:8]
                                    matches 0x18a6's first 16 payload bytes
  +0x2c  u8      counter           1-byte counter (matches 0x18a6 counter)

The 16-byte subkey is structurally identical to the first 16 bytes
of `init_message_18a6` body: the first 8 bytes are a "session
subkey upper" (`f8 cb ed 57 c6 8b 18 f4` in the captured session)
and the next 8 bytes are the lower half of the session UUID
(`bf 85 31 4b bc 4a 95 1a` — matches `session_message_a4` lower
half and `session_identity_beacon` UUID lower half).

So 0x1a59 is the W-direction "client confirms session subkey,
counter=N" beacon, paired with the R-direction `0x18a6` from the
server.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


# Total wire size of a full 0x1a59 W message.
TOTAL_WIRE_SIZE = 45

# Layout constants.
SESSION_UUID_OFFSET = 8
SESSION_UUID_SIZE = 16
TYPE_HEADER_OFFSET = 24
SUBKEY_OFFSET = 28
SUBKEY_SIZE = 16
COUNTER_OFFSET = 44

# 4-byte typed envelope header for type 0x1a59:
#   marker [0x00, 0x01], then ((0x1a59 & 0x3f) | 0x80) = 0x99,
#   then ((0x1a59 >> 6) & 0xff) = 0x69
TYPE_HEADER = bytes((0x00, 0x01, 0x99, 0x69))

# Value of the BE remaining-length field — total wire size minus
# the 8-byte header (client_hash + remaining_len).
REMAINING_LEN = TOTAL_WIRE_SIZE - 8  # 37 = 0x25


@dataclass
class SessionSubkeyBeacon1A59:
    """W-direction 0x1a59 session-subkey beacon (45 bytes total)."""

    client_hash: bytes      # 4 bytes
    session_uuid: bytes     # 16 bytes — full session UUID
    subkey: bytes           # 16 bytes — first_uuid_half + session_uuid_lower
    counter: int            # u8

    def __post_init__(self) -> None:
        if len(self.client_hash) != 4:
            raise ValueError(
                f"client_hash must be exactly 4 bytes; got {len(self.client_hash)}"
            )
        if len(self.session_uuid) != SESSION_UUID_SIZE:
            raise ValueError(
                f"session_uuid must be exactly {SESSION_UUID_SIZE} bytes; "
                f"got {len(self.session_uuid)}"
            )
        if len(self.subkey) != SUBKEY_SIZE:
            raise ValueError(
                f"subkey must be exactly {SUBKEY_SIZE} bytes; "
                f"got {len(self.subkey)}"
            )
        if not 0 <= self.counter <= 0xFF:
            raise ValueError(f"counter must fit in u8; got {self.counter}")


def encode(msg: SessionSubkeyBeacon1A59) -> bytes:
    """Build the on-wire 0x1a59 W message (45 bytes total)."""
    return (
        msg.client_hash
        + struct.pack(">I", REMAINING_LEN)
        + msg.session_uuid
        + TYPE_HEADER
        + msg.subkey
        + bytes((msg.counter,))
    )


def decode(buf: bytes) -> SessionSubkeyBeacon1A59:
    """Parse an on-wire 0x1a59 W message. Raises on size, length-field,
    or type-header mismatch."""
    if len(buf) != TOTAL_WIRE_SIZE:
        raise ValueError(
            f"expected exactly {TOTAL_WIRE_SIZE} bytes; got {len(buf)}"
        )
    client_hash = buf[0:4]
    (remaining,) = struct.unpack_from(">I", buf, 4)
    if remaining != REMAINING_LEN:
        raise ValueError(
            f"remaining-length field mismatch: expected 0x{REMAINING_LEN:x}, "
            f"got 0x{remaining:x}"
        )
    session_uuid = buf[SESSION_UUID_OFFSET:SESSION_UUID_OFFSET + SESSION_UUID_SIZE]
    type_header = buf[TYPE_HEADER_OFFSET:TYPE_HEADER_OFFSET + 4]
    if type_header != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {type_header.hex()}"
        )
    subkey = buf[SUBKEY_OFFSET:SUBKEY_OFFSET + SUBKEY_SIZE]
    counter = buf[COUNTER_OFFSET]
    return SessionSubkeyBeacon1A59(
        client_hash=client_hash,
        session_uuid=session_uuid,
        subkey=subkey,
        counter=counter,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "031e2fea"
        "00000025"
        "1a954abc4b3185bfbe37c3d8592618e0"
        "00019969"
        "f8cbed57c68b18f4bf85314bbc4a951a"
        "04"
    )
    msg = decode(captured)
    print(
        f"decoded: client_hash={msg.client_hash.hex()}, counter={msg.counter}, "
        f"subkey={msg.subkey.hex()}"
    )
    rebuilt = encode(msg)
    assert rebuilt == captured, (
        f"round-trip failed:\n  got: {rebuilt.hex()}\n  exp: {captured.hex()}"
    )
    print(f"len={len(rebuilt)} bytes — round-trip OK")
