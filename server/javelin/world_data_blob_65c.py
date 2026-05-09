"""
World-data blob — type 0x065c (R direction, singleton).

Single 12706-byte capture (seq 0x6, Phase 4 WORLD DATA — sent
right after the V3 RegistrationResponse and before the
0x40a/0x1be handshake pair). Heavily padded with literal `0xFF`
bytes; only 32 bytes are redacted (two 16-byte spans at offsets
5 and 12690).

This codec is **structural**: it preserves byte-exact round-trips
without trying to decode per-record semantics. The body
decomposes into:

  +0x00  u8x4    type_header        [00 01 9c 19] = type 0x065c
  +0x04  u8      count              0x05 in capture (u8)
  +0x05  u8x16   redacted_id        16 bytes redacted in capture
                                     (ReplayStore stores them as
                                     0x00; decoder accepts any bytes)
  +0x15  u8x4    sub_id             `58 61 78 14` — same sub_id
                                     used by `handshake_blob_76`
                                     (0x40a + 0x1be) for the
                                     handshake-family signing scheme
  +0x19  u8x32   ephemeral_block    32 bytes of per-message ephemeral
                                     content (varies per session)
  +0x39  u8x36   shared_trailer     **byte-identical to
                                     `handshake_blob_76`'s
                                     `DEFAULT_SHARED_TRAILER`**
                                     in the captured session — the
                                     handshake-family signing trailer.
                                     Codec validates this against the
                                     known constant on decode.
  +0x5d  records×N                  per-record:
                                       data: bytes (variable, all
                                             non-`FF` content for
                                             that slot)
                                       ff_padding_size: int
                                             (number of trailing
                                             0xFF bytes)

Total fixed header (the prefix before the records): 93 bytes.

The records section is **not strictly fixed-size** — most records
in the capture are 224 bytes (e.g. 80 data + 144 FF), but several
deviate (240, 232, etc.). The codec tolerates arbitrary record
sizes by walking alternating non-FF/FF spans.

In the captured 0x65c the 42 records sum to 12613 bytes and split
roughly:

  - record 0: 42 data + 80 FF (122 bytes total) — leading
    section that's mostly zeros with a 3-byte `38 80 31` marker
  - records 1..39: mostly 80-data + 144-FF (= 224 bytes total),
    with some 88/96/104-byte data variants
  - record 40: 112 data + 3632 FF (3744 bytes) — large gap
  - record 41: 27 data + 0 FF — trailing tail with the second
    16-byte redaction span at offsets 12690..12705
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterable

from .handshake_blob_76 import (
    DEFAULT_SHARED_TRAILER as HANDSHAKE_TRAILER,
    DEFAULT_SUB_ID as HANDSHAKE_SUB_ID,
)


# 4-byte typed envelope header for type 0x065c:
#   marker [0x00, 0x01], then ((0x65c & 0x3f) | 0x80) = 0x9c,
#   then ((0x65c >> 6) & 0xff) = 0x19
TYPE_HEADER = bytes((0x00, 0x01, 0x9c, 0x19))

COUNT_OFFSET = 4
REDACTED_ID_OFFSET = 5
REDACTED_ID_SIZE = 16
SUB_ID_OFFSET = 21
SUB_ID_SIZE = 4
EPHEMERAL_BLOCK_OFFSET = 25
EPHEMERAL_BLOCK_SIZE = 32
SHARED_TRAILER_OFFSET = 57
SHARED_TRAILER_SIZE = 36
RECORDS_OFFSET = 93  # fixed header is the first 93 bytes


@dataclass(frozen=True)
class WorldDataRecord:
    """One record in the variable-size records section: a data span
    followed by `ff_padding_size` trailing 0xFF bytes."""

    data: bytes
    ff_padding_size: int

    def __post_init__(self) -> None:
        if self.ff_padding_size < 0:
            raise ValueError(
                f"ff_padding_size must be non-negative; got {self.ff_padding_size}"
            )
        if 0xFF in self.data:
            raise ValueError(
                "data must not contain 0xFF bytes (those are reserved for "
                "the FF padding section)"
            )

    @property
    def total_size(self) -> int:
        return len(self.data) + self.ff_padding_size


@dataclass
class WorldDataBlob65C:
    """R-direction 0x065c WORLD DATA blob (variable size, structural)."""

    count: int                         # u8 at +0x04 (= 5 in capture)
    redacted_id: bytes                 # 16 bytes at +0x05
    ephemeral_block: bytes             # 32 bytes at +0x19
    records: tuple[WorldDataRecord, ...]
    sub_id: bytes = HANDSHAKE_SUB_ID
    shared_trailer: bytes = HANDSHAKE_TRAILER

    def __post_init__(self) -> None:
        if not 0 <= self.count <= 0xFF:
            raise ValueError(f"count must fit in u8; got {self.count}")
        if len(self.redacted_id) != REDACTED_ID_SIZE:
            raise ValueError(
                f"redacted_id must be exactly {REDACTED_ID_SIZE} bytes; "
                f"got {len(self.redacted_id)}"
            )
        if len(self.sub_id) != SUB_ID_SIZE:
            raise ValueError(
                f"sub_id must be exactly {SUB_ID_SIZE} bytes; got {len(self.sub_id)}"
            )
        if len(self.ephemeral_block) != EPHEMERAL_BLOCK_SIZE:
            raise ValueError(
                f"ephemeral_block must be exactly {EPHEMERAL_BLOCK_SIZE} bytes; "
                f"got {len(self.ephemeral_block)}"
            )
        if len(self.shared_trailer) != SHARED_TRAILER_SIZE:
            raise ValueError(
                f"shared_trailer must be exactly {SHARED_TRAILER_SIZE} bytes; "
                f"got {len(self.shared_trailer)}"
            )

    @property
    def total_records_size(self) -> int:
        return sum(r.total_size for r in self.records)


def _records_to_bytes(records: Iterable[WorldDataRecord]) -> bytes:
    out = bytearray()
    for r in records:
        out += r.data
        out += b"\xff" * r.ff_padding_size
    return bytes(out)


def _records_from_bytes(buf: bytes) -> tuple[WorldDataRecord, ...]:
    """Walk alternating non-FF / FF spans from `buf`. Each pair becomes
    one record. The last record may have ff_padding_size=0 if the buffer
    ends on a non-FF byte."""
    records: list[WorldDataRecord] = []
    pos = 0
    while pos < len(buf):
        # data span: until first 0xFF
        d_start = pos
        while pos < len(buf) and buf[pos] != 0xFF:
            pos += 1
        data = buf[d_start:pos]
        # ff span: until first non-FF
        f_start = pos
        while pos < len(buf) and buf[pos] == 0xFF:
            pos += 1
        ff_padding_size = pos - f_start
        records.append(WorldDataRecord(data=data, ff_padding_size=ff_padding_size))
    return tuple(records)


def encode(msg: WorldDataBlob65C) -> bytes:
    """Build the on-wire 0x065c body."""
    out = bytearray()
    out += TYPE_HEADER
    out += bytes((msg.count,))
    out += msg.redacted_id
    out += msg.sub_id
    out += msg.ephemeral_block
    out += msg.shared_trailer
    out += _records_to_bytes(msg.records)
    return bytes(out)


def decode(buf: bytes, *, validate_shared_trailer: bool = True) -> WorldDataBlob65C:
    """Parse a 0x065c body. Validates type header, sub_id, and (by
    default) the shared_trailer against the handshake-family
    constant. Pass `validate_shared_trailer=False` to accept any
    36-byte trailer (useful for future captures from sessions with
    a different signing scheme)."""
    if len(buf) < RECORDS_OFFSET:
        raise ValueError(
            f"buffer too short: need at least {RECORDS_OFFSET} bytes; got {len(buf)}"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )
    count = buf[COUNT_OFFSET]
    redacted_id = buf[REDACTED_ID_OFFSET:REDACTED_ID_OFFSET + REDACTED_ID_SIZE]
    sub_id = buf[SUB_ID_OFFSET:SUB_ID_OFFSET + SUB_ID_SIZE]
    if sub_id != HANDSHAKE_SUB_ID:
        raise ValueError(
            f"sub_id mismatch: expected {HANDSHAKE_SUB_ID.hex()} "
            f"(handshake_blob_76 family), got {sub_id.hex()}"
        )
    ephemeral_block = buf[EPHEMERAL_BLOCK_OFFSET:
                          EPHEMERAL_BLOCK_OFFSET + EPHEMERAL_BLOCK_SIZE]
    shared_trailer = buf[SHARED_TRAILER_OFFSET:
                         SHARED_TRAILER_OFFSET + SHARED_TRAILER_SIZE]
    if validate_shared_trailer and shared_trailer != HANDSHAKE_TRAILER:
        raise ValueError(
            f"shared_trailer doesn't match handshake-family constant"
        )
    records = _records_from_bytes(buf[RECORDS_OFFSET:])
    return WorldDataBlob65C(
        count=count,
        redacted_id=redacted_id,
        sub_id=sub_id,
        ephemeral_block=ephemeral_block,
        shared_trailer=shared_trailer,
        records=records,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    store = ReplayStore(p)
    m = next(m for m in store.messages if m.type_id == 0x065c)
    msg = decode(m.body)
    print(f"count={msg.count}, len(records)={len(msg.records)}")
    print(f"shared_trailer matches handshake family: "
          f"{msg.shared_trailer == HANDSHAKE_TRAILER}")
    sample_sizes = [(len(r.data), r.ff_padding_size) for r in msg.records[:5]]
    print(f"first 5 record (data, ff): {sample_sizes}")
    rebuilt = encode(msg)
    assert rebuilt == m.body, "round-trip failed"
    print(f"len={len(rebuilt)} bytes — round-trip OK")
