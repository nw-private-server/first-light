"""
Permission bitmap — type 0x0a95 (W direction, singleton).

Single 81-byte capture (seq 0x3d). Body extends the standard
W-singleton subkey-beacon shape with a count-prefixed array of
small flag bytes.

Wire layout (full 81-byte W-direction message):

  +0x00  u8x4    client_hash
  +0x04  u32 BE  remaining_len     0x49 = 73
  +0x08  u8x16   session_uuid      full session UUID
  +0x18  u8x4    type_header       [00 01 95 2a] = type 0x0a95
  +0x1c  u8x16   subkey            [first_uuid_half:8][session_uuid_lower:8]
                                    upper 8 bytes match the
                                    `0x5b2` second_id
                                    (`18 0f 8d 4e 57 36 97 c6`) —
                                    same fingerprint-reporter
                                    sub-system identity.
  +0x2c  u8      flag_count        0x24 = 36 in capture
  +0x2d  u8x(N)  flags             N small u8 values

Total: 28 (envelope) + 16 (subkey) + 1 (count) + N (flags).
For N=36: 81 bytes ✓.

In the capture all 36 flags are `0x01` **except** index 6 which is
`0x00` — strongly suggests a **per-feature permission/enable
bitmap** with a single feature toggled off. Flag indexes are
likely sub-system features (chat, voice, market, mail, etc.) but
without static-RE on the handler we can't name them.

The upper 8 bytes of the subkey link this message to the
**fingerprint-reporter sub-system** (also seen in `0x5b2`'s
second_id), suggesting 0x0a95 is the client telling the server
"these are my enabled features for the current session."
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


# Layout constants
SESSION_UUID_OFFSET = 8
SESSION_UUID_SIZE = 16
TYPE_HEADER_OFFSET = 24
SUBKEY_OFFSET = 28
SUBKEY_SIZE = 16
COUNT_OFFSET = 44
FLAGS_OFFSET = 45

MIN_TOTAL_WIRE_SIZE = 45  # envelope + subkey + count, with 0 flags

# 4-byte typed envelope header for type 0x0a95:
#   marker [0x00, 0x01], then ((0x0a95 & 0x3f) | 0x80) = 0x95,
#   then ((0x0a95 >> 6) & 0xff) = 0x2a
TYPE_HEADER = bytes((0x00, 0x01, 0x95, 0x2a))


@dataclass
class PermissionBitmapA95:
    """W-direction 0x0a95 permission bitmap (variable size)."""

    client_hash: bytes              # 4 bytes
    session_uuid: bytes             # 16 bytes
    subkey: bytes                   # 16 bytes — second_id + session_uuid_lower
    flags: bytes                    # 0..N u8 flag bytes

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
        if len(self.flags) > 0xFF:
            raise ValueError(
                f"flag count {len(self.flags)} doesn't fit in u8"
            )


def encode(msg: PermissionBitmapA95) -> bytes:
    """Build the on-wire 0x0a95 W message."""
    body = (
        msg.subkey
        + bytes((len(msg.flags),))
        + msg.flags
    )
    remaining_len = SESSION_UUID_SIZE + 4 + len(body)
    return (
        msg.client_hash
        + struct.pack(">I", remaining_len)
        + msg.session_uuid
        + TYPE_HEADER
        + body
    )


def decode(buf: bytes) -> PermissionBitmapA95:
    """Parse an on-wire 0x0a95 W message."""
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
    if buf[TYPE_HEADER_OFFSET:TYPE_HEADER_OFFSET + 4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[TYPE_HEADER_OFFSET:TYPE_HEADER_OFFSET + 4].hex()}"
        )
    subkey = buf[SUBKEY_OFFSET:SUBKEY_OFFSET + SUBKEY_SIZE]
    count = buf[COUNT_OFFSET]
    expected_size = MIN_TOTAL_WIRE_SIZE + count
    if len(buf) != expected_size:
        raise ValueError(
            f"size mismatch: count={count} implies {expected_size} bytes, "
            f"got {len(buf)}"
        )
    flags = buf[FLAGS_OFFSET:FLAGS_OFFSET + count]
    return PermissionBitmapA95(
        client_hash=client_hash,
        session_uuid=session_uuid,
        subkey=subkey,
        flags=flags,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "b0700b03"
        "00000049"
        "1a954abc4b3185bfbe37c3d8592618e0"
        "0001952a"
        "180f8d4e573697c6 bf85314bbc4a951a".replace(" ", "")
        + "24"
        + "01" * 6 + "00" + "01" * 29
    )
    msg = decode(captured)
    print(f"flag_count={len(msg.flags)}")
    print(f"flags={msg.flags.hex()}")
    print(f"disabled at indexes: {[i for i, f in enumerate(msg.flags) if f == 0]}")
    rebuilt = encode(msg)
    assert rebuilt == captured, (
        f"round-trip failed:\n  got: {rebuilt.hex()}\n  exp: {captured.hex()}"
    )
    print(f"len={len(rebuilt)} bytes — round-trip OK")
