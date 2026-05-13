"""
Spawn-confirmation result token — type 0x1097 (R direction, singleton).

Single 24-byte capture (seq 0x76). Paired with `0x1096` (seq 0x75)
by a shared 16-byte `identity_uuid` — both messages reference the
same spawn entity. 0x1097 is the smaller "result / confirmation"
half of that pair.

Wire layout:

  +0x00  u8x4    type_header        [00 01 97 42] = type 0x1097
  +0x04  u8x16   identity_uuid      lower 8 = session_uuid_lower;
                                     upper 8 must equal the upper 8
                                     of the paired 0x1096's identity_uuid
  +0x14  u32 BE  result             0x00000002 in capture

Total: 24 bytes.

Structurally identical to `result_token_136a` modulo the result
field width (u32 BE here vs u64 BE in 0x136a). Both look like
"server response with numeric result code" messages from
different sub-systems / phases.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


TYPED_BODY_SIZE = 24

# 4-byte typed envelope header for type 0x1097:
#   marker [0x00, 0x01], then ((0x1097 & 0x3f) | 0x80) = 0x97,
#   then ((0x1097 >> 6) & 0xff) = 0x42
TYPE_HEADER = bytes((0x00, 0x01, 0x97, 0x42))

IDENTITY_UUID_OFFSET = 4
IDENTITY_UUID_SIZE = 16
RESULT_OFFSET = 20
RESULT_SIZE = 4


@dataclass
class ResultToken1097:
    """R-direction 0x1097 spawn-confirmation result token (24 bytes total)."""

    identity_uuid: bytes      # 16 bytes; lower 8 = session_uuid_lower;
                              # upper 8 pairs with 0x1096's identity_uuid
    result: int               # u32 BE — opaque numeric result

    def __post_init__(self) -> None:
        if len(self.identity_uuid) != IDENTITY_UUID_SIZE:
            raise ValueError(
                f"identity_uuid must be exactly {IDENTITY_UUID_SIZE} bytes; "
                f"got {len(self.identity_uuid)}"
            )
        if not 0 <= self.result <= 0xFFFFFFFF:
            raise ValueError(f"result must fit in u32; got {self.result}")


def make_result_token_1097(
    identity_uuid: bytes,
    result: int = 2,
) -> ResultToken1097:
    """Build a `ResultToken1097` (0x1097 R) from the identity_uuid and
    a u32 BE result.

    The captured value is `2` — companion to a 0x1096 spawn message
    (paired by shared identity_uuid). Server-side replay code mints
    these alongside the corresponding 0x1096 emission.
    """
    return ResultToken1097(identity_uuid=identity_uuid, result=result)


def encode(msg: ResultToken1097) -> bytes:
    """Build the on-wire 0x1097 body (24 bytes total)."""
    return (
        TYPE_HEADER
        + msg.identity_uuid
        + struct.pack(">I", msg.result)
    )


def decode(buf: bytes) -> ResultToken1097:
    """Parse a 0x1097 body. Raises on size or type-header mismatch."""
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
    (result,) = struct.unpack_from(">I", buf, RESULT_OFFSET)
    return ResultToken1097(identity_uuid=identity_uuid, result=result)


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "00019742"
        "93a3e477cb5fd51e bf85314bbc4a951a".replace(" ", "")
        + "00000002"
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
