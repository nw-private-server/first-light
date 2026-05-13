"""
Identity fingerprint set — type 0x5b2 (W direction).

4 captures in the existing replay split into two shapes:

- **3 byte-identical 45-byte messages** (seq 0x92, 0x99, 0x9b) —
  the small variant with zero fingerprints. Notably even the
  4-byte client_hash is the same across all three (`f9 b3 ea 55`),
  which suggests this is **the same logical message resent at the
  wire level** (reliable-delivery retransmission, or a periodic
  "no fingerprints to report" beacon).
- **1 distinct 93-byte message** (seq 0x9f) — the large variant
  carrying 6 fingerprints of 8 bytes each.

Each fingerprint is an opaque 8-byte value (likely a content hash,
asset ID, or input digest). The count is a u8 immediately after
the second_id + session_uuid_lower block.

Wire layout (full W-direction message; total = 45 + 8*count bytes):

  +0x00  u8x4    client_hash       per-message correlation/hash
                                    (constant across reliable resends)
  +0x04  u32 BE  remaining_len     total - 8
  +0x08  u8x16   session_uuid      full session UUID (matches 0xa4)
  +0x18  u8x4    type_header       [00 01 b2 16] = type 0x5b2
  +0x1c  u8x8    second_id         e.g. `18 0f 8d 4e 57 36 97 c6`
                                    in the captured session
  +0x24  u8x8    session_uuid_lower  matches lower 8 of session_uuid
  +0x2c  u8      count             number of 8-byte fingerprints
  +0x2d  u8x(8*count)  fingerprints  opaque 8-byte values

The `second_id` in the captured 0x5b2 messages is **distinct** from
the `second_id` carried by `0x18a6` and `0x635`. So this message
references a different identity surface than those types — perhaps
a "fingerprint-bundle origin" or a sub-system instance ID.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


# Layout constants.
SESSION_UUID_OFFSET = 8
SESSION_UUID_SIZE = 16
TYPE_HEADER_OFFSET = 24
SECOND_ID_OFFSET = 28
SECOND_ID_SIZE = 8
SESSION_UUID_LOWER_OFFSET = 36
SESSION_UUID_LOWER_SIZE = 8
COUNT_OFFSET = 44
FINGERPRINTS_OFFSET = 45
FINGERPRINT_SIZE = 8

MIN_TOTAL_WIRE_SIZE = 45  # count == 0

# 4-byte typed envelope header for type 0x5b2:
#   marker [0x00, 0x01], then ((0x5b2 & 0x3f) | 0x80) = 0xb2,
#   then ((0x5b2 >> 6) & 0xff) = 0x16
TYPE_HEADER = bytes((0x00, 0x01, 0xb2, 0x16))


@dataclass
class IdentityFingerprintSet5B2:
    """W-direction 0x5b2 identity-fingerprint set (variable size)."""

    client_hash: bytes              # 4 bytes
    session_uuid: bytes             # 16 bytes — full session UUID
    second_id: bytes                # 8 bytes — fingerprint-bundle origin
    session_uuid_lower: bytes       # 8 bytes — lower half of session UUID
    fingerprints: tuple[bytes, ...] # 0..N entries of 8 bytes each

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
        if len(self.second_id) != SECOND_ID_SIZE:
            raise ValueError(
                f"second_id must be exactly {SECOND_ID_SIZE} bytes; "
                f"got {len(self.second_id)}"
            )
        if len(self.session_uuid_lower) != SESSION_UUID_LOWER_SIZE:
            raise ValueError(
                f"session_uuid_lower must be exactly {SESSION_UUID_LOWER_SIZE} "
                f"bytes; got {len(self.session_uuid_lower)}"
            )
        if len(self.fingerprints) > 0xFF:
            raise ValueError(
                f"fingerprint count {len(self.fingerprints)} doesn't fit in u8"
            )
        for i, fp in enumerate(self.fingerprints):
            if len(fp) != FINGERPRINT_SIZE:
                raise ValueError(
                    f"fingerprint[{i}] must be exactly {FINGERPRINT_SIZE} "
                    f"bytes; got {len(fp)}"
                )


def encode(msg: IdentityFingerprintSet5B2) -> bytes:
    """Build the on-wire 0x5b2 W message."""
    body = (
        msg.second_id
        + msg.session_uuid_lower
        + bytes((len(msg.fingerprints),))
        + b"".join(msg.fingerprints)
    )
    remaining_len = SESSION_UUID_SIZE + 4 + len(body)  # uuid + type_hdr + body
    return (
        msg.client_hash
        + struct.pack(">I", remaining_len)
        + msg.session_uuid
        + TYPE_HEADER
        + body
    )


def decode(buf: bytes) -> IdentityFingerprintSet5B2:
    """Parse an on-wire 0x5b2 W message. Raises on size, length-field,
    type-header mismatch, or fingerprint-count overrun."""
    if len(buf) < MIN_TOTAL_WIRE_SIZE:
        raise ValueError(
            f"buffer too short: need at least {MIN_TOTAL_WIRE_SIZE} bytes; "
            f"got {len(buf)}"
        )
    client_hash = buf[0:4]
    (remaining,) = struct.unpack_from(">I", buf, 4)
    expected_remaining = len(buf) - 8
    if remaining != expected_remaining:
        raise ValueError(
            f"remaining-length field mismatch: expected 0x{expected_remaining:x}, "
            f"got 0x{remaining:x}"
        )
    session_uuid = buf[SESSION_UUID_OFFSET:SESSION_UUID_OFFSET + SESSION_UUID_SIZE]
    type_header = buf[TYPE_HEADER_OFFSET:TYPE_HEADER_OFFSET + 4]
    if type_header != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {type_header.hex()}"
        )
    second_id = buf[SECOND_ID_OFFSET:SECOND_ID_OFFSET + SECOND_ID_SIZE]
    session_uuid_lower = buf[
        SESSION_UUID_LOWER_OFFSET:SESSION_UUID_LOWER_OFFSET + SESSION_UUID_LOWER_SIZE
    ]
    count = buf[COUNT_OFFSET]
    expected_size = MIN_TOTAL_WIRE_SIZE + count * FINGERPRINT_SIZE
    if len(buf) != expected_size:
        raise ValueError(
            f"size mismatch: count={count} implies {expected_size} bytes, "
            f"got {len(buf)}"
        )
    fingerprints = tuple(
        buf[FINGERPRINTS_OFFSET + i * FINGERPRINT_SIZE:
            FINGERPRINTS_OFFSET + (i + 1) * FINGERPRINT_SIZE]
        for i in range(count)
    )
    return IdentityFingerprintSet5B2(
        client_hash=client_hash,
        session_uuid=session_uuid,
        second_id=second_id,
        session_uuid_lower=session_uuid_lower,
        fingerprints=fingerprints,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Small variant — count=0
    small = bytes.fromhex(
        "f9b3ea55"
        "00000025"
        "1a954abc4b3185bfbe37c3d8592618e0"
        "0001b216"
        "180f8d4e573697c6"
        "bf85314bbc4a951a"
        "00"
    )
    msg = decode(small)
    print(f"small: count={len(msg.fingerprints)}")
    assert encode(msg) == small, "small round-trip failed"

    # Large variant — count=6
    large = bytes.fromhex(
        "c468b848"
        "00000055"
        "1a954abc4b3185bfbe37c3d8592618e0"
        "0001b216"
        "180f8d4e573697c6"
        "bf85314bbc4a951a"
        "06"
        "1e4e63891491 99c8"
        "c44e4b804e09 a0fd"
        "ac4fe4f4cbb0 c2ff"
        "2644e72b17b4 794c"
        "e24816dee8a3 9546"
        "dd464d7541fa f5a5".replace(" ", "")
    )
    msg = decode(large)
    print(f"large: count={len(msg.fingerprints)}")
    assert encode(msg) == large, "large round-trip failed"

    print(f"OK — both variants round-trip")
