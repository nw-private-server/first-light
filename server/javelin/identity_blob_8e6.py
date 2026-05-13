"""
Identity blob — type 0x8e6 (R direction, singleton).

Single 42-byte capture (seq 0x43). Clean fixed-shape body with two
16-byte UUID-like fields and a 6-byte zero-padded tail.

Wire layout (4-byte typed envelope + 38-byte body):

  +0x00  u8x4    type_header        [00 01 a6 23] = type 0x8e6
  +0x04  u8x16   identity_uuid      `4c 0c 0e d6 47 8a 69 da
                                      bf 85 31 4b bc 4a 95 1a`
                                     lower 8 bytes match the
                                     `bf 85 31 4b bc 4a 95 1a`
                                     shared session_uuid_lower —
                                     same identity-bundle convention
                                     as 0x18a6, 0x1b88, 0xa4, etc.
  +0x14  u8x16   opaque_blob        `e1 63 43 70 30 7b 4d 06
                                      a7 2f d9 df 00 5c d9 42`
                                     16 bytes of UUID-like or
                                     hash-like content. No
                                     internal structure visible
                                     from one capture.
  +0x24  u8x6    zero_padding       all 0x00 in capture

Total: 42 bytes.

The 16-byte `opaque_blob` could be:
- A second UUID (no shared bytes with session_uuid_lower)
- A 16-byte session-derived hash or MAC
- An asset/entity ID

Without more captures or handler-side static-RE we can't
disambiguate. The codec validates structure, exposes the obvious
fields, and rejects non-zero padding bytes (so future captures
that turn out to use that span for something else will surface as
decode errors rather than silent acceptance).
"""

from __future__ import annotations

from dataclasses import dataclass


TYPED_BODY_SIZE = 42

# 4-byte typed envelope header for type 0x8e6:
#   marker [0x00, 0x01], then ((0x8e6 & 0x3f) | 0x80) = 0xa6,
#   then ((0x8e6 >> 6) & 0xff) = 0x23
TYPE_HEADER = bytes((0x00, 0x01, 0xa6, 0x23))

IDENTITY_UUID_OFFSET = 4
IDENTITY_UUID_SIZE = 16
OPAQUE_BLOB_OFFSET = 20
OPAQUE_BLOB_SIZE = 16
ZERO_PAD_OFFSET = 36
ZERO_PAD_SIZE = 6


@dataclass
class IdentityBlob8E6:
    """R-direction 0x8e6 identity blob (42 bytes total)."""

    identity_uuid: bytes      # 16 bytes; lower 8 = session_uuid_lower
    opaque_blob: bytes        # 16 bytes; semantics unknown

    def __post_init__(self) -> None:
        if len(self.identity_uuid) != IDENTITY_UUID_SIZE:
            raise ValueError(
                f"identity_uuid must be exactly {IDENTITY_UUID_SIZE} bytes; "
                f"got {len(self.identity_uuid)}"
            )
        if len(self.opaque_blob) != OPAQUE_BLOB_SIZE:
            raise ValueError(
                f"opaque_blob must be exactly {OPAQUE_BLOB_SIZE} bytes; "
                f"got {len(self.opaque_blob)}"
            )


def encode(msg: IdentityBlob8E6) -> bytes:
    """Build the on-wire 0x8e6 body (42 bytes total)."""
    return (
        TYPE_HEADER
        + msg.identity_uuid
        + msg.opaque_blob
        + bytes(ZERO_PAD_SIZE)
    )


def decode(buf: bytes) -> IdentityBlob8E6:
    """Parse a 0x8e6 body. Raises on size, type-header, or zero-padding
    mismatch."""
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
    opaque_blob = buf[OPAQUE_BLOB_OFFSET:OPAQUE_BLOB_OFFSET + OPAQUE_BLOB_SIZE]
    zero_pad = buf[ZERO_PAD_OFFSET:ZERO_PAD_OFFSET + ZERO_PAD_SIZE]
    if zero_pad != bytes(ZERO_PAD_SIZE):
        raise ValueError(
            f"trailing pad non-zero at offset {ZERO_PAD_OFFSET}: {zero_pad.hex()}"
        )
    return IdentityBlob8E6(
        identity_uuid=identity_uuid,
        opaque_blob=opaque_blob,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "0001a623"
        "4c0c0ed6478a69da bf85314bbc4a951a".replace(" ", "")
        + "e163437030 7b4d06a72fd9df005cd942".replace(" ", "")
        + "00" * 6
    )
    msg = decode(captured)
    print(
        f"identity_uuid={msg.identity_uuid.hex()}\n"
        f"opaque_blob={msg.opaque_blob.hex()}"
    )
    rebuilt = encode(msg)
    assert rebuilt == captured, (
        f"round-trip failed:\n  got: {rebuilt.hex()}\n  exp: {captured.hex()}"
    )
    print(f"len={len(rebuilt)} bytes — round-trip OK")
