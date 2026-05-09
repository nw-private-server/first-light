"""
Asset count table — type 0xca4 (R direction, singleton).

Single 102-byte capture (seq 0x9). Body is a clean count-prefixed
table of 8-byte records, each carrying a 4-byte truncated hash
and a 4-byte u32 BE value. Plausibly an **asset / inventory
count table** the server sends early in the session — values
look like quantities (`43, 6, 1, 226, 1304, 24, 16, 1713, 6090,
23`) and the leading 4-byte fields look like 32-bit truncated
hashes of asset / pool / item identifiers.

Wire layout (4-byte typed envelope + 98-byte body):

  +0x00  u8x4    type_header        [00 01 a4 32] = type 0xca4
  +0x04  u8x16   identity_uuid      lower 8 = session_uuid_lower
  +0x14  u8      record_count       0x0a = 10 in capture
  +0x15  u8x(8*N)  records          per-record:
                                       u8x4   hash_id    truncated hash
                                       u32 BE value      u32 BE quantity
  +...   u8      trailer            constant 0x01 in capture

For the captured singleton: 4 + 16 + 1 + 80 + 1 = 102 bytes ✓.

The trailing `0x01` byte is conjectural — it could be a "more
records follow" flag, a version byte, or a structural padding
sentinel. The codec validates it equals the captured value
(default `0x01`) and offers a `trailer` field for callers that
need to override.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


# 4-byte typed envelope header for type 0xca4:
#   marker [0x00, 0x01], then ((0xca4 & 0x3f) | 0x80) = 0xa4,
#   then ((0xca4 >> 6) & 0xff) = 0x32
TYPE_HEADER = bytes((0x00, 0x01, 0xa4, 0x32))

IDENTITY_UUID_OFFSET = 4
IDENTITY_UUID_SIZE = 16
COUNT_OFFSET = 20
RECORDS_OFFSET = 21
RECORD_SIZE = 8
HASH_SIZE = 4

MIN_TYPED_BODY_SIZE = 22  # envelope + uuid + count + trailer (no records)
DEFAULT_TRAILER = 0x01


@dataclass(frozen=True)
class AssetCountRecord:
    """A single (hash_id, value) entry in the asset count table."""

    hash_id: bytes      # 4 bytes — truncated 32-bit hash
    value: int          # u32 BE — quantity / count

    def __post_init__(self) -> None:
        if len(self.hash_id) != HASH_SIZE:
            raise ValueError(
                f"hash_id must be exactly {HASH_SIZE} bytes; "
                f"got {len(self.hash_id)}"
            )
        if not 0 <= self.value <= 0xFFFFFFFF:
            raise ValueError(
                f"value must fit in u32; got {self.value}"
            )


@dataclass
class AssetCountTableCA4:
    """R-direction 0xca4 asset count table (variable size)."""

    identity_uuid: bytes                  # 16 bytes
    records: tuple[AssetCountRecord, ...] # 0..255 records
    trailer: int = DEFAULT_TRAILER        # u8

    def __post_init__(self) -> None:
        if len(self.identity_uuid) != IDENTITY_UUID_SIZE:
            raise ValueError(
                f"identity_uuid must be exactly {IDENTITY_UUID_SIZE} bytes; "
                f"got {len(self.identity_uuid)}"
            )
        if not 0 <= len(self.records) <= 0xFF:
            raise ValueError(
                f"record count {len(self.records)} doesn't fit in u8"
            )
        if not 0 <= self.trailer <= 0xFF:
            raise ValueError(
                f"trailer must fit in u8; got {self.trailer}"
            )


def encode(msg: AssetCountTableCA4) -> bytes:
    """Build the on-wire 0xca4 body."""
    out = bytearray()
    out += TYPE_HEADER
    out += msg.identity_uuid
    out += bytes((len(msg.records),))
    for r in msg.records:
        out += r.hash_id
        out += struct.pack(">I", r.value)
    out += bytes((msg.trailer,))
    return bytes(out)


def decode(buf: bytes) -> AssetCountTableCA4:
    """Parse a 0xca4 body. Raises on size, type-header, or
    record-count overrun."""
    if len(buf) < MIN_TYPED_BODY_SIZE:
        raise ValueError(
            f"buffer too short: need at least {MIN_TYPED_BODY_SIZE} bytes; "
            f"got {len(buf)}"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )
    identity_uuid = buf[IDENTITY_UUID_OFFSET:IDENTITY_UUID_OFFSET + IDENTITY_UUID_SIZE]
    count = buf[COUNT_OFFSET]
    expected_size = MIN_TYPED_BODY_SIZE + count * RECORD_SIZE
    if len(buf) != expected_size:
        raise ValueError(
            f"size mismatch: count={count} implies {expected_size} bytes, "
            f"got {len(buf)}"
        )
    records = []
    pos = RECORDS_OFFSET
    for _ in range(count):
        hash_id = buf[pos:pos + HASH_SIZE]
        pos += HASH_SIZE
        (value,) = struct.unpack_from(">I", buf, pos)
        pos += 4
        records.append(AssetCountRecord(hash_id=hash_id, value=value))
    trailer = buf[pos]
    return AssetCountTableCA4(
        identity_uuid=identity_uuid,
        records=tuple(records),
        trailer=trailer,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "0001a432"
        "a0b45ffbd9b3264b bf85314bbc4a951a".replace(" ", "")
        + "0a"  # count = 10
        + "f73ab7440000002b"
        + "23c4d7c200000006"
        + "0b2132dc00000001"
        + "4101344e000000e2"
        + "5e8b583100000518"
        + "e4bd0a9d00000018"
        + "c77f0b9e00000010"
        + "683169f8000006b1"
        + "6a0c5c7e000017ca"
        + "cbd637dc00000017"
        + "01"  # trailer
    )
    msg = decode(captured)
    print(f"identity_uuid={msg.identity_uuid.hex()}")
    print(f"trailer=0x{msg.trailer:02x}")
    print(f"records ({len(msg.records)}):")
    for r in msg.records:
        print(f"  hash={r.hash_id.hex()} value={r.value}")
    rebuilt = encode(msg)
    assert rebuilt == captured, (
        f"round-trip failed:\n  got: {rebuilt.hex()}\n  exp: {captured.hex()}"
    )
    print(f"len={len(rebuilt)} bytes — round-trip OK")
