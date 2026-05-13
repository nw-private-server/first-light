"""
Level descriptor — type 0x663.

Both captured copies (seq 0x10 and 0x4d) are byte-identical 110-byte
messages carrying:

- A level name string (`"NewWorld_VitaeEterna"`, 20 bytes)
- A level-path string (`"coatlicue/NewWorld_VitaeEterna"`, 30 bytes)
- 4 IEEE-754 BE floats (likely a Vec4 — coordinates / scale / region
  bounds; values 2048.0, 16.0, 12272.0, 10250.0 in the captures)
- 8 zero bytes
- A "session metadata" block re-used from `0x18a6`:
    * 4 bytes flags (`01 01 00 00`)
    * 8 bytes second_id (`9c fa 58 61 78 14 69 f2`)
    * 4 bytes build_version (`0x365` LE)
- A 14-byte trailer

The strings use a **1-byte length prefix** ("Pascal-style"), NOT the
4-byte LE length of `AZStd::string` used by the LevelInfoChangedMsg
codec. This is a different serialization convention used by some
older / specialized message types.

Wire layout (after the 4-byte typed envelope header `[00 01 a3 19]`):

  +0x00  u8       len_a              0x14 = 20
  +0x01  bytes×20 level_name         "NewWorld_VitaeEterna"
  +0x15  u8       len_b              0x1e = 30
  +0x16  bytes×30 level_path         "coatlicue/NewWorld_VitaeEterna"
  +0x34  f32 BE   ×4                 4 floats
  +0x44  u8x8     zero padding
  +0x4c  u32 LE   flags              0x00000101
  +0x50  u8x8     second_id
  +0x58  u32 LE   build_version      0x365
  +0x5c  u8x14    trailer            captured constant

Total body (with type header): 110 bytes.

The shared `flags`, `second_id`, `build_version` block is the same
metadata footer that `0x18a6` carries — see the `init_message_18a6`
codec.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


TYPED_BODY_SIZE = 110

# 4-byte typed envelope header for type 0x663:
#   marker [0x00, 0x01], then ((0x663 & 0x3f) | 0x80) = 0xa3,
#   then ((0x663 >> 6) & 0xff) = 0x19
TYPE_HEADER = bytes((0x00, 0x01, 0xa3, 0x19))

# Same metadata-block constants as init_message_18a6:
DEFAULT_FLAGS = 0x00000101
DEFAULT_BUILD_VERSION = 0x365

# Captured trailer (14 bytes; constant in both replay copies)
DEFAULT_TRAILER = bytes.fromhex("000001010100000000c17f9be48f")
assert len(DEFAULT_TRAILER) == 14, f"trailer is {len(DEFAULT_TRAILER)} bytes"


@dataclass
class LevelDescriptor663:
    """Type 0x663 — level descriptor with name, path, geometry, and
    session-metadata block."""

    level_name: str          # short name, e.g. "NewWorld_VitaeEterna"
    level_path: str          # path-like, e.g. "coatlicue/NewWorld_VitaeEterna"
    geometry: tuple[float, float, float, float]  # 4 IEEE-754 BE floats
    second_id: bytes         # 8 bytes — same role as 0x18a6's second_id
    flags: int = DEFAULT_FLAGS
    build_version: int = DEFAULT_BUILD_VERSION
    trailer: bytes = DEFAULT_TRAILER

    def __post_init__(self) -> None:
        a = self.level_name.encode("utf-8")
        if not 0 <= len(a) <= 0xFF:
            raise ValueError(
                f"level_name length {len(a)} doesn't fit in u8"
            )
        b = self.level_path.encode("utf-8")
        if not 0 <= len(b) <= 0xFF:
            raise ValueError(
                f"level_path length {len(b)} doesn't fit in u8"
            )
        # The total body size is fixed at TYPED_BODY_SIZE, so the strings
        # together must occupy exactly the right number of bytes. We could
        # support arbitrary strings by relaxing this — if a future capture
        # shows a different total size, revisit.
        # 4 (header) + 1 + a + 1 + b + 16 + 8 + 4 + 8 + 4 + 14 == TYPED_BODY_SIZE
        # → a + b == TYPED_BODY_SIZE - 60 == 50
        expected = TYPED_BODY_SIZE - (4 + 1 + 1 + 16 + 8 + 4 + 8 + 4 + 14)
        if len(a) + len(b) != expected:
            raise ValueError(
                f"level_name ({len(a)}) + level_path ({len(b)}) must sum to "
                f"{expected} for the fixed {TYPED_BODY_SIZE}-byte wire size; got "
                f"{len(a) + len(b)}"
            )
        if len(self.geometry) != 4:
            raise ValueError(
                f"geometry must have 4 floats; got {len(self.geometry)}"
            )
        if len(self.second_id) != 8:
            raise ValueError(
                f"second_id must be exactly 8 bytes; got {len(self.second_id)}"
            )
        if not 0 <= self.flags <= 0xFFFFFFFF:
            raise ValueError(f"flags must fit in u32; got {self.flags}")
        if not 0 <= self.build_version <= 0xFFFFFFFF:
            raise ValueError(
                f"build_version must fit in u32; got {self.build_version}"
            )
        if len(self.trailer) != 14:
            raise ValueError(
                f"trailer must be exactly 14 bytes; got {len(self.trailer)}"
            )


def encode(msg: LevelDescriptor663) -> bytes:
    """Build the on-wire 0x663 body (with type header, 110 bytes)."""
    a = msg.level_name.encode("utf-8")
    b = msg.level_path.encode("utf-8")
    out = bytearray()
    out += TYPE_HEADER
    out += bytes((len(a),))
    out += a
    out += bytes((len(b),))
    out += b
    out += struct.pack(">ffff", *msg.geometry)
    out += bytes(8)                                  # zero padding
    out += struct.pack("<I", msg.flags)              # u32 LE flags
    out += msg.second_id
    out += struct.pack("<I", msg.build_version)      # u32 LE build_version
    out += msg.trailer
    return bytes(out)


def decode(buf: bytes) -> LevelDescriptor663:
    """Parse an on-wire 0x663 body. Raises on size or type-header
    mismatch, length-prefix overrun, or non-zero padding."""
    if len(buf) != TYPED_BODY_SIZE:
        raise ValueError(
            f"expected exactly {TYPED_BODY_SIZE} bytes; got {len(buf)}"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )
    pos = 4
    len_a = buf[pos]
    pos += 1
    if pos + len_a > len(buf):
        raise ValueError(f"level_name length {len_a} overruns buffer")
    level_name = buf[pos:pos + len_a].decode("utf-8")
    pos += len_a
    len_b = buf[pos]
    pos += 1
    if pos + len_b > len(buf):
        raise ValueError(f"level_path length {len_b} overruns buffer")
    level_path = buf[pos:pos + len_b].decode("utf-8")
    pos += len_b
    geometry = struct.unpack_from(">ffff", buf, pos)
    pos += 16
    if buf[pos:pos + 8] != bytes(8):
        raise ValueError(
            f"zero-padding non-zero at offset {pos}: {buf[pos:pos + 8].hex()}"
        )
    pos += 8
    (flags,) = struct.unpack_from("<I", buf, pos)
    pos += 4
    second_id = buf[pos:pos + 8]
    pos += 8
    (build_version,) = struct.unpack_from("<I", buf, pos)
    pos += 4
    trailer = buf[pos:pos + 14]
    pos += 14
    if pos != len(buf):
        raise ValueError(
            f"unexpected trailing {len(buf) - pos} bytes after trailer"
        )
    return LevelDescriptor663(
        level_name=level_name,
        level_path=level_path,
        geometry=geometry,
        second_id=second_id,
        flags=flags,
        build_version=build_version,
        trailer=trailer,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "0001a319"
        "14"
        + "4e6577576f726c645f5669746165457465726e61"
        + "1e"
        + "636f61746c696375652f4e6577576f726c645f5669746165457465726e61"
        + "45000000" "41800000" "463fc000" "46202800"
        + "00" * 8
        + "01010000"
        + "9cfa58617814 69f2".replace(" ", "")
        + "65030000"
        + "000001010100000000c17f9be48f"
    )
    msg = decode(captured)
    print(f"decoded: name={msg.level_name!r}, path={msg.level_path!r}")
    print(f"  geometry={msg.geometry}")
    print(f"  second_id={msg.second_id.hex()}, build=0x{msg.build_version:x}")
    rebuilt = encode(msg)
    assert rebuilt == captured, f"round-trip failed:\n  got: {rebuilt.hex()}\n  exp: {captured.hex()}"
    print(f"len={len(rebuilt)} bytes — round-trip OK")
