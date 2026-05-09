"""
Result token — type 0x136a (R direction, singleton).

Single 28-byte capture (seq 0x26). Simple fixed-shape: 4-byte
envelope + 16-byte identity_uuid + 8-byte u64 BE result token
(= 1 in capture).

Wire layout:

  +0x00  u8x4    type_header        [00 01 aa 4d] = type 0x136a
  +0x04  u8x16   identity_uuid      lower 8 = session_uuid_lower
  +0x14  u64 BE  result             8-byte big-endian unsigned

Total: 28 bytes.

The 8-byte result is structurally similar to the 4-byte u32 BE
trailer in `0x1097` (paired with `0x1096`), suggesting both are
generic "small response with a numeric result" messages. Without
more captures we can't pin the semantics — could be a server
acknowledgement code, a session cookie, or a result-type
discriminator.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


TYPED_BODY_SIZE = 28

# 4-byte typed envelope header for type 0x136a:
#   marker [0x00, 0x01], then ((0x136a & 0x3f) | 0x80) = 0xaa,
#   then ((0x136a >> 6) & 0xff) = 0x4d
TYPE_HEADER = bytes((0x00, 0x01, 0xaa, 0x4d))

IDENTITY_UUID_OFFSET = 4
IDENTITY_UUID_SIZE = 16
RESULT_OFFSET = 20
RESULT_SIZE = 8


@dataclass
class ResultToken136A:
    """R-direction 0x136a result-token message (28 bytes total)."""

    identity_uuid: bytes      # 16 bytes; lower 8 = session_uuid_lower
    result: int               # u64 BE — opaque numeric result

    def __post_init__(self) -> None:
        if len(self.identity_uuid) != IDENTITY_UUID_SIZE:
            raise ValueError(
                f"identity_uuid must be exactly {IDENTITY_UUID_SIZE} bytes; "
                f"got {len(self.identity_uuid)}"
            )
        if not 0 <= self.result <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError(f"result must fit in u64; got {self.result}")


def encode(msg: ResultToken136A) -> bytes:
    """Build the on-wire 0x136a body (28 bytes total)."""
    return (
        TYPE_HEADER
        + msg.identity_uuid
        + struct.pack(">Q", msg.result)
    )


def decode(buf: bytes) -> ResultToken136A:
    """Parse a 0x136a body. Raises on size or type-header mismatch."""
    if len(buf) != TYPED_BODY_SIZE:
        raise ValueError(
            f"expected exactly {TYPED_BODY_SIZE} bytes; got {len(buf)}"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )
    identity_uuid = buf[IDENTITY_UUID_OFFSET:IDENTITY_UUID_OFFSET + IDENTITY_UUID_SIZE]
    (result,) = struct.unpack_from(">Q", buf, RESULT_OFFSET)
    return ResultToken136A(identity_uuid=identity_uuid, result=result)


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "0001aa4d"
        "4d6b64a4c7da53fa bf85314bbc4a951a".replace(" ", "")
        + "0000000000000001"
    )
    msg = decode(captured)
    print(
        f"identity_uuid={msg.identity_uuid.hex()}, result={msg.result}"
    )
    rebuilt = encode(msg)
    assert rebuilt == captured, (
        f"round-trip failed:\n  got: {rebuilt.hex()}\n  exp: {captured.hex()}"
    )
    print(f"len={len(rebuilt)} bytes — round-trip OK")
