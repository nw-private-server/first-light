"""
Handshake-shaped 76-byte messages — type 0x40a + type 0x1be (R direction).

Two singletons in the existing replay (seq 0x4 and 0x5) — both 76
bytes, R direction, sent at the very start of the connection. They
share a common wire shape and a constant 36-byte trailer:

  +0x00  u8x4    type_header        type-dependent
  +0x04  u8x4    sub_id             `58 61 78 14` — bytes 2..5 of the
                                     `9c fa 58 61 78 14 69 f2`
                                     metadata-block second_id seen in
                                     0x18a6 / 0x663. Constant in both
                                     singletons.
  +0x08  u8x32   blob               32 bytes of variable per-message
                                     content — looks like a public
                                     key + nonce or a cipher block.
                                     Different for each type.
  +0x28  u8x36   shared_trailer     `cb d4 a1 8a 40 42 c7 ee
                                      a4 62 98 c7 49 9b a8 26
                                      ef 53 39 aa 29 70 e2 83
                                      fc f3 4b 6f 8f 07 86 d6
                                      8b f3 ae 45`
                                     **Byte-identical** between the two
                                     singletons — almost certainly a
                                     hash, MAC, or signature over a
                                     fixed-shape header/cert.

Total: 4 + 4 + 32 + 36 = 76 bytes.

Sequence position (seq 0x4 + seq 0x5 — the two messages **right
after** the V3 registration response and before any session beacons)
strongly suggests this is a **two-step handshake / key-exchange**
between the server and client at session bring-up:

  - 0x40a R (seq 0x4): server → client first half
  - 0x1be R (seq 0x5): server → client second half

The constant `sub_id` and the shared 36-byte trailer support the
"fixed-cert + per-message ephemeral material" interpretation: the
trailer is the cert/MAC, the 32-byte blob is the ephemeral half.

We model both types with a single `HandshakeBlob76` dataclass
parameterized by `type_id` since the wire shape is identical.
"""

from __future__ import annotations

from dataclasses import dataclass


TYPED_BODY_SIZE = 76
SUB_ID_OFFSET = 4
SUB_ID_SIZE = 4
BLOB_OFFSET = 8
BLOB_SIZE = 32
TRAILER_OFFSET = 40
TRAILER_SIZE = 36

# Constant 4-byte sub-id observed in both singletons — bytes 2..5 of
# the 0x18a6/0x663 metadata-block second_id.
DEFAULT_SUB_ID = bytes((0x58, 0x61, 0x78, 0x14))

# Byte-identical 36-byte trailer in both singletons.
DEFAULT_SHARED_TRAILER = bytes.fromhex(
    "cbd4a18a4042c7ee"
    "a46298c7499ba826"
    "ef5339aa2970e283"
    "fcf34b6f8f0786d6"
    "8bf3ae45"
)
assert len(DEFAULT_SHARED_TRAILER) == TRAILER_SIZE


def _type_header(type_id: int) -> bytes:
    """Build the 4-byte typed envelope header for a given type id."""
    if not 0 <= type_id <= 0xFFFF:
        raise ValueError(f"type_id must fit in u16; got {type_id}")
    return bytes((
        0x00,
        0x01,
        (type_id & 0x3F) | 0x80,
        (type_id >> 6) & 0xFF,
    ))


def _decode_type_id(type_header: bytes) -> int:
    """Inverse of _type_header — recover the type_id from a 4-byte
    typed envelope header. Raises if the header doesn't fit the
    `[0x00, 0x01, type_lo|0x80, type_hi]` pattern."""
    if len(type_header) != 4:
        raise ValueError(
            f"type_header must be exactly 4 bytes; got {len(type_header)}"
        )
    if type_header[0:2] != b"\x00\x01":
        raise ValueError(
            f"type header marker mismatch: expected '00 01', "
            f"got {type_header[0:2].hex()}"
        )
    if (type_header[2] & 0x80) == 0:
        raise ValueError(
            f"type header byte 2 high bit must be set; got 0x{type_header[2]:02x}"
        )
    type_lo = type_header[2] & 0x3F
    type_hi = type_header[3]
    return (type_hi << 6) | type_lo


@dataclass
class HandshakeBlob76:
    """76-byte handshake-shaped message body. Used for both type 0x40a
    and type 0x1be (the two captured singletons share a wire shape)."""

    type_id: int            # 0x40a or 0x1be
    blob: bytes             # 32 bytes — per-message ephemeral content
    sub_id: bytes = DEFAULT_SUB_ID
    shared_trailer: bytes = DEFAULT_SHARED_TRAILER

    def __post_init__(self) -> None:
        if not 0 <= self.type_id <= 0xFFFF:
            raise ValueError(f"type_id must fit in u16; got {self.type_id}")
        if len(self.sub_id) != SUB_ID_SIZE:
            raise ValueError(
                f"sub_id must be exactly {SUB_ID_SIZE} bytes; got {len(self.sub_id)}"
            )
        if len(self.blob) != BLOB_SIZE:
            raise ValueError(
                f"blob must be exactly {BLOB_SIZE} bytes; got {len(self.blob)}"
            )
        if len(self.shared_trailer) != TRAILER_SIZE:
            raise ValueError(
                f"shared_trailer must be exactly {TRAILER_SIZE} bytes; "
                f"got {len(self.shared_trailer)}"
            )


def make_handshake_blob_76(
    type_id: int,
    blob: bytes,
    *,
    sub_id: bytes = DEFAULT_SUB_ID,
    shared_trailer: bytes = DEFAULT_SHARED_TRAILER,
) -> HandshakeBlob76:
    """Build a `HandshakeBlob76` for the given type-id (0x40a or 0x1be).

    The 4-byte `sub_id` and 36-byte `shared_trailer` default to the
    handshake-family constants observed across the captured 0x40a +
    0x1be messages (see `analysis/replay_message_inventory.md`
    "Cross-codec identity-bundle map"). Server-side replay code can
    override either when targeting a different signing scheme — but
    for the captured Amazon retail session the defaults are correct.

    The 32-byte `blob` is the per-message ephemeral content; this
    differs between 0x40a and 0x1be in the capture. Server-side
    code typically generates fresh ephemeral material for each
    handshake message of the pair.
    """
    return HandshakeBlob76(
        type_id=type_id,
        blob=blob,
        sub_id=sub_id,
        shared_trailer=shared_trailer,
    )


def encode(msg: HandshakeBlob76) -> bytes:
    """Build the on-wire 76-byte handshake body."""
    return (
        _type_header(msg.type_id)
        + msg.sub_id
        + msg.blob
        + msg.shared_trailer
    )


def decode(buf: bytes) -> HandshakeBlob76:
    """Parse a 76-byte handshake body. Raises on size or type-header
    mismatch."""
    if len(buf) != TYPED_BODY_SIZE:
        raise ValueError(
            f"expected exactly {TYPED_BODY_SIZE} bytes; got {len(buf)}"
        )
    type_id = _decode_type_id(buf[0:4])
    sub_id = buf[SUB_ID_OFFSET:SUB_ID_OFFSET + SUB_ID_SIZE]
    blob = buf[BLOB_OFFSET:BLOB_OFFSET + BLOB_SIZE]
    shared_trailer = buf[TRAILER_OFFSET:TRAILER_OFFSET + TRAILER_SIZE]
    return HandshakeBlob76(
        type_id=type_id,
        sub_id=sub_id,
        blob=blob,
        shared_trailer=shared_trailer,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured_40a = bytes.fromhex(
        "00018a10"
        "58617814"
        "c20daee38238a1d140d1878a7a25f147"
        "912907e277204e2d80818aa27c952bc9"
        "cbd4a18a4042c7ee"
        "a46298c7499ba826"
        "ef5339aa2970e283"
        "fcf34b6f8f0786d6"
        "8bf3ae45"
    )
    msg = decode(captured_40a)
    print(f"0x40a: type_id=0x{msg.type_id:x}, blob[0:8]={msg.blob[:8].hex()}")
    assert msg.type_id == 0x40a
    assert encode(msg) == captured_40a

    captured_1be = bytes.fromhex(
        "0001be06"
        "58617814"
        "1c56024e9b798cf2b7aadfc1a567c5a6"
        "826dfb5c061e438d89a297fe582d944c"
        "cbd4a18a4042c7ee"
        "a46298c7499ba826"
        "ef5339aa2970e283"
        "fcf34b6f8f0786d6"
        "8bf3ae45"
    )
    msg = decode(captured_1be)
    print(f"0x1be: type_id=0x{msg.type_id:x}, blob[0:8]={msg.blob[:8].hex()}")
    assert msg.type_id == 0x1be
    assert encode(msg) == captured_1be

    # Cross-sanity: shared_trailer must be byte-identical
    a = decode(captured_40a)
    b = decode(captured_1be)
    assert a.shared_trailer == b.shared_trailer
    assert a.sub_id == b.sub_id
    print("OK — both 76-byte handshake variants round-trip; trailer + sub_id shared")
