"""
Frame-config — type 0x1096.

Single capture in the replay (R direction, 80 bytes total). Body
layout below — derived from byte-pattern inspection only (one
capture, no symbolic reference). Field names describe **shape**,
not authoritative semantics. The codec validates the apparent
structural constraints (zero-padding pattern, repeated ratios)
so a second capture would either round-trip cleanly or break a
specific invariant in a useful, locatable way.

  +0x00  4 bytes   typed envelope header `00 01 96 42`
  +0x04  8 bytes   sub_system_id           (identity-bundle, wake 78)
  +0x0c  8 bytes   session_uuid_lower      (identity-bundle, wake 78)
  +0x14  4 bytes   f32 BE  f0              captured: 6.0
  +0x18  4 bytes   f32 BE  f1              captured: -1.0
  +0x1c  4 bytes   f32 BE  f2              captured: 4.69e-4 (small rate)
  +0x20  4 bytes   u32 BE  word0_value     captured: 21300
  +0x24  4 bytes   u32 BE  must be zero    captured: 0
  +0x28  4 bytes   u32 BE  word1_value     captured: 65100
  +0x2c  4 bytes   u32 BE  must be zero    captured: 0
  +0x30  4 bytes   u32 BE  secs_a          captured: 3600 (1 hour)
  +0x34  4 bytes   u32 BE  secs_b          captured: 1800 (30 min)
  +0x38  4 bytes   u32 BE  hash_a          captured: 0x0b879fb3
  +0x3c  4 bytes   u32 BE  hash_b          captured: 0x3482a0b7
  +0x40  4 bytes   f32 BE  ratio_lo        captured: 1/6 ≈ 0.16666
  +0x44  4 bytes   f32 BE  must equal +0x40 (ratio_lo repeated)
  +0x48  4 bytes   f32 BE  ratio_hi        captured: 5/6 ≈ 0.83333
  +0x4c  4 bytes   f32 BE  must equal +0x48 (ratio_hi repeated)

Structural invariants (validated on decode):
  * +0x24 == +0x2c == 0
  * +0x40 == +0x44      (ratio_lo doubled)
  * +0x48 == +0x4c      (ratio_hi doubled)
  * total length == 80 bytes
  * type header == `00 01 96 42`

The field names (`secs_*`, `hash_*`, `ratio_*`) reflect
plausible interpretations of the captured values (3600/1800
look like durations in seconds; 1/6 and 5/6 look like
normalized fractions of a range), but a second capture is
needed to confirm. Until then the codec treats them as raw
typed fields.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


TYPE_ID = 0x1096

# 4-byte typed envelope header for type 0x1096:
#   marker [0x00, 0x01], then ((0x1096 & 0x3f) | 0x80) = 0x96,
#   then ((0x1096 >> 6) & 0xff) = 0x42
TYPE_HEADER = bytes((0x00, 0x01, 0x96, 0x42))

BODY_SIZE = 80
IDENTITY_SIZE = 16  # sub_system_id (8) + session_uuid_lower (8)


@dataclass
class FrameConfig1096:
    """Structural representation of a captured 0x1096 message.

    Fields are named by shape, not authoritative semantics — see
    the module docstring for the byte layout."""

    sub_system_id: bytes        # 8 bytes
    session_uuid_lower: bytes   # 8 bytes
    f0: float                   # f32 BE at +0x14
    f1: float                   # f32 BE at +0x18
    f2: float                   # f32 BE at +0x1c
    word0_value: int            # u32 BE at +0x20 (followed by 4 zero bytes)
    word1_value: int            # u32 BE at +0x28 (followed by 4 zero bytes)
    secs_a: int                 # u32 BE at +0x30
    secs_b: int                 # u32 BE at +0x34
    hash_a: int                 # u32 BE at +0x38
    hash_b: int                 # u32 BE at +0x3c
    ratio_lo: float             # f32 BE at +0x40, repeated at +0x44
    ratio_hi: float             # f32 BE at +0x48, repeated at +0x4c

    def __post_init__(self) -> None:
        if len(self.sub_system_id) != 8:
            raise ValueError(
                f"sub_system_id must be exactly 8 bytes; "
                f"got {len(self.sub_system_id)}"
            )
        if len(self.session_uuid_lower) != 8:
            raise ValueError(
                f"session_uuid_lower must be exactly 8 bytes; "
                f"got {len(self.session_uuid_lower)}"
            )
        for name in ("word0_value", "word1_value", "secs_a",
                     "secs_b", "hash_a", "hash_b"):
            v = getattr(self, name)
            if not 0 <= v <= 0xFFFFFFFF:
                raise ValueError(f"{name} must fit in u32; got {v}")


def encode(msg: FrameConfig1096) -> bytes:
    """Build the 80-byte wire form."""
    return (
        TYPE_HEADER
        + msg.sub_system_id
        + msg.session_uuid_lower
        + struct.pack(
            ">fff"           # f0, f1, f2
            "I" "I"          # word0_value (then 4 zero bytes)
            "I" "I"          # word1_value (then 4 zero bytes)
            "II"             # secs_a, secs_b
            "II"             # hash_a, hash_b
            "f f f f",       # ratio_lo (x2), ratio_hi (x2)
            msg.f0, msg.f1, msg.f2,
            msg.word0_value, 0,
            msg.word1_value, 0,
            msg.secs_a, msg.secs_b,
            msg.hash_a, msg.hash_b,
            msg.ratio_lo, msg.ratio_lo,
            msg.ratio_hi, msg.ratio_hi,
        )
    )


def decode(buf: bytes) -> FrameConfig1096:
    """Parse an 80-byte 0x1096 message. Raises on any structural
    invariant violation (size, header, zero-pads, ratio repeats)."""
    if len(buf) != BODY_SIZE:
        raise ValueError(
            f"expected exactly {BODY_SIZE} bytes; got {len(buf)}"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )

    sub_system_id = buf[4:12]
    session_uuid_lower = buf[12:20]

    (f0, f1, f2,
     word0_value, zero_a,
     word1_value, zero_b,
     secs_a, secs_b,
     hash_a, hash_b,
     ratio_lo_1, ratio_lo_2,
     ratio_hi_1, ratio_hi_2) = struct.unpack(">fffIIIIIIIIffff", buf[20:80])

    if zero_a != 0:
        raise ValueError(
            f"+0x24 zero-pad violated: expected 0, got 0x{zero_a:08x}"
        )
    if zero_b != 0:
        raise ValueError(
            f"+0x2c zero-pad violated: expected 0, got 0x{zero_b:08x}"
        )
    if ratio_lo_1 != ratio_lo_2:
        raise ValueError(
            f"ratio_lo repeat violated: +0x40={ratio_lo_1!r} "
            f"vs +0x44={ratio_lo_2!r}"
        )
    if ratio_hi_1 != ratio_hi_2:
        raise ValueError(
            f"ratio_hi repeat violated: +0x48={ratio_hi_1!r} "
            f"vs +0x4c={ratio_hi_2!r}"
        )

    return FrameConfig1096(
        sub_system_id=sub_system_id,
        session_uuid_lower=session_uuid_lower,
        f0=f0, f1=f1, f2=f2,
        word0_value=word0_value,
        word1_value=word1_value,
        secs_a=secs_a, secs_b=secs_b,
        hash_a=hash_a, hash_b=hash_b,
        ratio_lo=ratio_lo_1,
        ratio_hi=ratio_hi_1,
    )


if __name__ == "__main__":
    captured = bytes.fromhex(
        "00019642"
        "93a3e477cb5fd51e"
        "bf85314bbc4a951a"
        "40c00000"
        "bf800000"
        "39f5f5b8"
        "00005334" "00000000"
        "0000fe4c" "00000000"
        "00000e10"
        "00000708"
        "0b879fb3"
        "3482a0b7"
        "3e2aaaab" "3e2aaaab"
        "3f555555" "3f555555"
    )
    msg = decode(captured)
    print(
        f"f0={msg.f0}, f1={msg.f1}, f2={msg.f2}, "
        f"secs_a={msg.secs_a}, secs_b={msg.secs_b}, "
        f"ratio_lo={msg.ratio_lo}, ratio_hi={msg.ratio_hi}"
    )
    assert encode(msg) == captured
    print("OK — frame_config_1096 round-trips")
