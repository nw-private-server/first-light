"""
Init message — type 0x18a6 (40-byte variant).

Per the existing replay (4 occurrences, all identical except the
trailing 1-byte counter), this is a periodic init/handshake beacon
that carries the session UUID, build version, and a per-broadcast
counter. See `analysis/replay_message_inventory.md` for the
byte-level breakdown.

Wire layout (after the 4-byte typed envelope header `[00 01 a6 62]`):

  +0x00  u8x8   first_uuid_half       e.g. f8 cb ed 57 c6 8b 18 f4
  +0x08  u8x8   session_uuid_lower    same lower-half UUID as 0x1b88 / 0xa4
  +0x10  u32    flags                 0x00000101 in every captured msg
  +0x14  u8x8   second_id             e.g. 9c fa 58 61 78 14 69 f2
  +0x1c  u32 LE build_version         0x365 = 869 (matches "1.365.…")
  +0x20  u8x3   reserved              fixed `00 00 02` in every captured msg
  +0x23  u8     counter               1, 2, 3, 4 across the 4 captures

Total body (with type header): 40 bytes.

The `flags`, `reserved` bytes, and exact role of the two 8-byte ids
are unconfirmed; they are constants in the captured data. The
codec exposes them as fields so a maintainer can override if a
future capture shows variation.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


TYPED_BODY_SIZE = 40
PAYLOAD_SIZE = 36

# 4-byte typed envelope header for type 0x18a6:
#   marker [0x00, 0x01], then ((0x18a6 & 0x3f) | 0x80) = 0xa6,
#   then ((0x18a6 >> 6) & 0xff) = 0x62
TYPE_HEADER = bytes((0x00, 0x01, 0xa6, 0x62))

# Captured constant — flags u32 LE at payload +0x10 in every replay copy.
DEFAULT_FLAGS = 0x00000101

# Captured constant — fixed 3 bytes at payload +0x20 in every replay copy.
RESERVED_PREFIX = bytes((0x00, 0x00, 0x02))

# Captured build version (1.365.6031.6006993 → minor 365 = 0x365).
DEFAULT_BUILD_VERSION = 0x365


@dataclass
class InitMessage18A6:
    """Type 0x18a6 — periodic init beacon with build version + counter."""

    first_uuid_half: bytes        # 8 bytes; first half of a 16-byte id
    session_uuid_lower: bytes     # 8 bytes; matches lower half of 0x1b88 / 0xa4 UUIDs
    second_id: bytes              # 8 bytes; second 8-byte identifier
    counter: int = 1              # u8 — 1..255

    flags: int = DEFAULT_FLAGS
    build_version: int = DEFAULT_BUILD_VERSION

    def __post_init__(self) -> None:
        if len(self.first_uuid_half) != 8:
            raise ValueError(
                f"first_uuid_half must be exactly 8 bytes; got {len(self.first_uuid_half)}"
            )
        if len(self.session_uuid_lower) != 8:
            raise ValueError(
                f"session_uuid_lower must be exactly 8 bytes; got "
                f"{len(self.session_uuid_lower)}"
            )
        if len(self.second_id) != 8:
            raise ValueError(
                f"second_id must be exactly 8 bytes; got {len(self.second_id)}"
            )
        if not 0 <= self.counter <= 0xFF:
            raise ValueError(f"counter must fit in u8; got {self.counter}")
        if not 0 <= self.flags <= 0xFFFFFFFF:
            raise ValueError(f"flags must fit in u32; got {self.flags}")
        if not 0 <= self.build_version <= 0xFFFFFFFF:
            raise ValueError(
                f"build_version must fit in u32; got {self.build_version}"
            )


def encode(msg: InitMessage18A6) -> bytes:
    """Build the on-wire 0x18a6 body INCLUDING the type header.

    Returns 40 bytes total.
    """
    out = bytearray()
    out += TYPE_HEADER                                    # 4 bytes
    out += msg.first_uuid_half                            # +0x00, 8 bytes
    out += msg.session_uuid_lower                         # +0x08, 8 bytes
    out += struct.pack("<I", msg.flags)                   # +0x10, 4 bytes
    out += msg.second_id                                  # +0x14, 8 bytes
    out += struct.pack("<I", msg.build_version)           # +0x1c, 4 bytes
    out += RESERVED_PREFIX                                # +0x20, 3 bytes
    out += bytes((msg.counter & 0xFF,))                   # +0x23, 1 byte
    return bytes(out)


def decode(buf: bytes) -> InitMessage18A6:
    """Parse an on-wire 0x18a6 body.

    Inverse of `encode()`. Raises `ValueError` on size mismatch or
    type-header mismatch.

    Does NOT enforce that `flags` and `reserved` match the captured
    constants — if a future capture shows variation, the codec
    survives without changes.
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
    first_uuid_half = buf[4:12]
    session_uuid_lower = buf[12:20]
    (flags,) = struct.unpack_from("<I", buf, 20)
    second_id = buf[24:32]
    (build_version,) = struct.unpack_from("<I", buf, 32)
    # buf[36:39] is the reserved 3-byte prefix; we don't enforce
    # equality so future captures can be parsed even if it varies
    counter = buf[39]
    return InitMessage18A6(
        first_uuid_half=first_uuid_half,
        session_uuid_lower=session_uuid_lower,
        second_id=second_id,
        counter=counter,
        flags=flags,
        build_version=build_version,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "0001a662"
        "f8cbed57c68b18f4"
        "bf85314bbc4a951a"
        "01010000"
        "9cfa58617814 69f2".replace(" ", "")
        + "65030000"
        + "000002"
        + "01"
    )
    msg = decode(captured)
    print(f"decoded: session_uuid_lower={msg.session_uuid_lower.hex()}, "
          f"build_version=0x{msg.build_version:x}, counter={msg.counter}")
    rebuilt = encode(msg)
    assert rebuilt == captured, f"round-trip failed:\n  got: {rebuilt.hex()}\n  exp: {captured.hex()}"
    print(f"len={len(rebuilt)} bytes — round-trip OK")
