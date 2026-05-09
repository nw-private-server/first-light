"""
Subkey-beacon family — generic codec for W-direction "session-subkey
+ small trailer" messages.

A large family of W-direction messages share an identical wire shape:

  +0x00  u8x4    client_hash       per-message correlation hash
  +0x04  u32 BE  remaining_len     total - 8
  +0x08  u8x16   session_uuid      full session UUID
  +0x18  u8x4    type_header       per-type
  +0x1c  u8x16   subkey            16 bytes — typically
                                    [first_uuid_half:8][session_uuid_lower:8]
  +0x2c  u8x(T)  trailer           per-type trailer (T = 0/1/2/4 bytes)

The captured replay holds 12 distinct types fitting this pattern:

  Trailer 0 (44 bytes total) — types 0x066b, 0x102f, 0x1098
  Trailer 1 (45 bytes total) — types 0x0f7f, 0x101a, 0x101d, 0x10b0,
                                0x143d, 0x187c, 0x187f, 0x1a59
  Trailer 2 (46 bytes total) — type  0x102e
  Trailer 4 (48 bytes total) — type  0x09d3

The trailer field is treated as opaque bytes by this generic codec.
Different types use it for different things — the canonical 0x1a59
case uses it as a 1-byte counter; other types may use it as a flag,
result code, or sub-id.

Existing `session_subkey_1a59` ships its own typed dataclass that
**wraps** this generic codec; that wrapper preserves backward
compatibility for existing callers.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


SESSION_UUID_OFFSET = 8
SESSION_UUID_SIZE = 16
TYPE_HEADER_OFFSET = 24
SUBKEY_OFFSET = 28
SUBKEY_SIZE = 16
TRAILER_OFFSET = 44

# Body size before any trailer is added.
BASE_WIRE_SIZE = 44

# Set of (type_id, trailer_size) combinations characterized in the replay.
# Used by tests to spot-check the family map but not enforced by the codec.
KNOWN_FAMILY: dict[int, int] = {
    0x066b: 0,
    0x102f: 0,
    0x1098: 0,
    0x0f7f: 1,
    0x101a: 1,
    0x101d: 1,
    0x10b0: 1,
    0x143d: 1,
    0x187c: 1,
    0x187f: 1,
    0x1a59: 1,
    0x102e: 2,
    0x09d3: 4,
}


def make_type_header(type_id: int) -> bytes:
    """Build the 4-byte typed envelope header for a given type id."""
    if not 0x40 <= type_id <= 0x3FFF:
        raise ValueError(
            f"type_id 0x{type_id:x} outside the [0x40, 0x3FFF] range "
            f"that uses the 4-byte typed envelope"
        )
    return bytes((
        0x00,
        0x01,
        (type_id & 0x3F) | 0x80,
        (type_id >> 6) & 0xFF,
    ))


def decode_type_id(type_header: bytes) -> int:
    """Recover the type_id from a 4-byte typed envelope header."""
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
            f"type header byte 2 high bit must be set; "
            f"got 0x{type_header[2]:02x}"
        )
    type_lo = type_header[2] & 0x3F
    type_hi = type_header[3]
    return (type_hi << 6) | type_lo


@dataclass
class SubkeyBeacon:
    """Generic W-direction subkey-bearing message.

    The `trailer` field is opaque bytes — different types use it
    differently. Callers wanting type-specific semantics (e.g. the
    1-byte counter in 0x1a59) should wrap this with a typed dataclass."""

    type_id: int             # 0x40..0x3FFF
    client_hash: bytes       # 4 bytes
    session_uuid: bytes      # 16 bytes — full session UUID
    subkey: bytes            # 16 bytes
    trailer: bytes           # 0..N bytes — per-type opaque trailer

    def __post_init__(self) -> None:
        if not 0x40 <= self.type_id <= 0x3FFF:
            raise ValueError(
                f"type_id 0x{self.type_id:x} outside [0x40, 0x3FFF]"
            )
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
        # trailer length is per-type; no upper bound enforced here.

    @property
    def total_wire_size(self) -> int:
        return BASE_WIRE_SIZE + len(self.trailer)


def encode(msg: SubkeyBeacon) -> bytes:
    """Build the on-wire bytes for a generic subkey-beacon message."""
    remaining_len = msg.total_wire_size - 8
    return (
        msg.client_hash
        + struct.pack(">I", remaining_len)
        + msg.session_uuid
        + make_type_header(msg.type_id)
        + msg.subkey
        + msg.trailer
    )


def decode(buf: bytes, *, expected_type_id: int | None = None,
           expected_trailer_size: int | None = None) -> SubkeyBeacon:
    """Parse a generic subkey-beacon from on-wire bytes.

    Caller can optionally pin the expected `type_id` and/or
    `trailer_size`; if either is provided, the codec validates the
    parsed message matches. Otherwise the type-id is recovered from
    the header and the trailer is whatever follows the subkey.
    """
    if len(buf) < BASE_WIRE_SIZE:
        raise ValueError(
            f"buffer too short: need at least {BASE_WIRE_SIZE} bytes; "
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
    type_id = decode_type_id(buf[TYPE_HEADER_OFFSET:TYPE_HEADER_OFFSET + 4])
    if expected_type_id is not None and type_id != expected_type_id:
        raise ValueError(
            f"type_id mismatch: expected 0x{expected_type_id:x}, "
            f"got 0x{type_id:x}"
        )
    subkey = buf[SUBKEY_OFFSET:SUBKEY_OFFSET + SUBKEY_SIZE]
    trailer = buf[TRAILER_OFFSET:]
    if expected_trailer_size is not None and len(trailer) != expected_trailer_size:
        raise ValueError(
            f"trailer size mismatch: expected {expected_trailer_size}, "
            f"got {len(trailer)}"
        )
    return SubkeyBeacon(
        type_id=type_id,
        client_hash=client_hash,
        session_uuid=session_uuid,
        subkey=subkey,
        trailer=trailer,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Round-trip a 1-byte-trailer beacon (matches the 0x1a59 shape).
    captured = bytes.fromhex(
        "031e2fea"
        "00000025"
        "1a954abc4b3185bfbe37c3d8592618e0"
        "00019969"
        "f8cbed57c68b18f4bf85314bbc4a951a"
        "04"
    )
    msg = decode(captured)
    assert msg.type_id == 0x1a59
    assert msg.trailer == b"\x04"
    rebuilt = encode(msg)
    assert rebuilt == captured
    print(f"0x1a59 round-trip OK; trailer=0x{msg.trailer.hex()}")

    # Pin both type_id and trailer_size.
    msg2 = decode(captured, expected_type_id=0x1a59, expected_trailer_size=1)
    assert msg2 == msg
    print(f"validated decode OK")

    # Mismatched expected_type_id should raise.
    try:
        decode(captured, expected_type_id=0x102f)
    except ValueError as e:
        print(f"correctly rejected wrong type_id: {e}")
    else:
        raise AssertionError("expected ValueError on wrong type_id")
