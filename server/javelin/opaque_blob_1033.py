"""
Opaque blob — type 0x1033.

Single capture in the replay (R direction, 498 bytes total). The
body's first 20 bytes follow the project's standard layout:

  +0x00  4 bytes   typed envelope header `00 01 b3 40`
  +0x04  8 bytes   sub_system_id           (identity-bundle)
  +0x0c  8 bytes   session_uuid_lower      (identity-bundle)
  +0x14  478 bytes opaque payload          high-entropy

Beyond +0x14 the payload is high-entropy with no clean 4-byte or
8-byte grid (498 mod 4 == 2, 498 mod 8 == 2, 498 mod 16 == 2). A
visual scan of the bytes shows no obvious floats, durations,
zero-pads, or structured records — characteristics that worked
for the wake-101 codec on `0x1096` are absent here.

The most plausible interpretation is encrypted or signed material
(the identity-bundle is followed by a single opaque blob). Without
either a second capture (to find structural commonalities) or
runtime context (to interpret the blob), a structural codec
beyond "opaque tail" would be guessing.

This codec covers what we *can* assert:
  * the type header is exactly `00 01 b3 40`,
  * the identity-bundle layout (sub_system_id[8] +
    session_uuid_lower[8]) is at +0x04..+0x13,
  * the remaining 478 bytes are an opaque tail.

The captured body round-trips through this codec byte-identically.
A second capture, when available, will let us either confirm the
opaque tail is per-session-random (encrypted) or extract recurring
structural fields (in which case the codec gets an upgrade).

See `analysis/wire_type_0x1033.md` for the full structural
investigation.
"""

from __future__ import annotations

from dataclasses import dataclass


TYPE_ID = 0x1033

# 4-byte typed envelope header for type 0x1033:
#   marker [0x00, 0x01], then ((0x1033 & 0x3f) | 0x80) = 0xb3,
#   then ((0x1033 >> 6) & 0xff) = 0x40
TYPE_HEADER = bytes((0x00, 0x01, 0xb3, 0x40))

# Captured body length is fixed at 498. We don't enforce that in the
# codec because we have only one capture; a future capture might be
# a different length while still following the same layout. Instead
# we enforce a *minimum* (header + identity).
MIN_BODY_SIZE = 20  # 4-byte header + 16-byte identity bundle
IDENTITY_SIZE = 16


@dataclass
class OpaqueBlob1033:
    """0x1033 message: typed header + identity bundle + opaque tail.

    The opaque-tail bytes are exposed verbatim; the codec makes no
    claims about their internal structure (see module docstring)."""

    sub_system_id: bytes        # 8 bytes
    session_uuid_lower: bytes   # 8 bytes
    opaque: bytes               # variable length

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


def encode(msg: OpaqueBlob1033) -> bytes:
    """Build the wire form."""
    return (
        TYPE_HEADER
        + msg.sub_system_id
        + msg.session_uuid_lower
        + msg.opaque
    )


def decode(buf: bytes) -> OpaqueBlob1033:
    """Parse a 0x1033 message. Raises on minimum-size or header
    mismatch."""
    if len(buf) < MIN_BODY_SIZE:
        raise ValueError(
            f"need at least {MIN_BODY_SIZE} bytes "
            f"(4 header + 16 identity); got {len(buf)}"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )
    return OpaqueBlob1033(
        sub_system_id=buf[4:12],
        session_uuid_lower=buf[12:20],
        opaque=buf[20:],
    )


if __name__ == "__main__":
    captured = bytes.fromhex(
        "0001b340"
        "ce81136a2b7ad33e"
        "bf85314bbc4a951a"
    ) + bytes(478)  # placeholder opaque tail for self-test
    msg = decode(captured)
    print(f"sub_system_id={msg.sub_system_id.hex()}")
    print(f"session_uuid_lower={msg.session_uuid_lower.hex()}")
    print(f"opaque len={len(msg.opaque)}")
    assert encode(msg) == captured
    print("OK — opaque_blob_1033 round-trips")
