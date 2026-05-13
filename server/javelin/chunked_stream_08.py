"""
Chunked stream — type 0x08.

The highest-volume captured wire-type: **79 R-direction captures**
in the replay, with 47 distinct body sizes from 78 B up to 46 423 B.

The bodies fall into two forms:

## Standard form (78/79 captures)

```
+0x00  4 bytes   prefix  `00 01 08 01`     fixed across all 78
+0x04  1 byte    subtype                   varies (54 distinct values;
                                            0x01 dominates with 24 captures)
+0x05  6 bytes   constant `01 01 01 01 00 00`
+0x0b  ...       opaque tail               variable length
```

The 11-byte anchor (4 prefix + 1 subtype + 6 constant) is invariant
across all 78 standard captures. Beyond +0x0b the layout depends on
the subtype byte and is not yet structurally characterized.

The body sometimes contains the recurring 8-byte correlation marker
`03 65 f2 69 14 78 61 58` (ASCII tail "xaX") — but **not** as a
chunk separator: 30 of 30 large messages (5K-50K bytes) have zero
markers, while the small/mid messages (200-1000 B) average 2.5
markers each. The marker is treated here as inline data, not
structural.

## UUID-prefixed form (1/79 captures — seq 0x25)

The single outlier is the largest 0x08 in the replay (46 423 bytes,
opens the session). It does **not** start with the standard prefix;
the first 16 bytes look like a UUID/digest:

```
+0x00  16 bytes  uuid                      `03 87 94 2a 66 1f 85 43
                                            1d 45 8b 40 d2 1f 3b 26`
+0x10  ...       opaque tail               46 407 bytes
```

This is consistent with a "world-data dump" that bundles the session
identity at the start. We expose this as a separate dataclass rather
than try to unify the layouts.

## Codec scope

`ChunkedStream08Standard` covers the 78 standard captures with the
confirmed 11-byte anchor + opaque tail. `ChunkedStream08UuidPrefixed`
covers the single outlier with a 16-byte UUID + opaque tail.
`decode_either(buf)` dispatches by sniffing the leading 4 bytes.

The codec preserves bytes round-trip but does not interpret the
opaque tail. A second session capture (or runtime trace of the
emitting function) would let us subdivide the tail by subtype.

See `analysis/wire_type_0x08.md` for the full investigation and the
per-subtype byte distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


TYPE_ID = 0x08

# Standard-form anchor: 4-byte prefix + 1 subtype byte + 6 constant bytes
STANDARD_PREFIX = bytes((0x00, 0x01, 0x08, 0x01))
STANDARD_CONSTANT = bytes((0x01, 0x01, 0x01, 0x01, 0x00, 0x00))
STANDARD_HEADER_SIZE = 4 + 1 + 6  # 11

# UUID-prefixed form (single outlier; bundle identity at +0x00..+0x0f)
UUID_PREFIX_SIZE = 16


@dataclass
class ChunkedStream08Standard:
    """Standard-form 0x08 message: 11-byte anchor + opaque tail."""

    subtype: int       # 1 byte; varies across captures
    opaque: bytes      # tail bytes after the 11-byte anchor

    def __post_init__(self) -> None:
        if not 0 <= self.subtype <= 0xFF:
            raise ValueError(f"subtype must fit in u8; got {self.subtype}")


@dataclass
class ChunkedStream08UuidPrefixed:
    """Outlier-form 0x08 message: 16-byte UUID + opaque tail."""

    uuid: bytes        # 16 bytes
    opaque: bytes      # tail bytes after the UUID

    def __post_init__(self) -> None:
        if len(self.uuid) != UUID_PREFIX_SIZE:
            raise ValueError(
                f"uuid must be exactly {UUID_PREFIX_SIZE} bytes; "
                f"got {len(self.uuid)}"
            )


ChunkedStream08 = Union[ChunkedStream08Standard, ChunkedStream08UuidPrefixed]


def encode_standard(msg: ChunkedStream08Standard) -> bytes:
    """Build the standard-form wire bytes."""
    return (
        STANDARD_PREFIX
        + bytes([msg.subtype])
        + STANDARD_CONSTANT
        + msg.opaque
    )


def encode_uuid_prefixed(msg: ChunkedStream08UuidPrefixed) -> bytes:
    """Build the UUID-prefixed wire bytes."""
    return msg.uuid + msg.opaque


def decode_standard(buf: bytes) -> ChunkedStream08Standard:
    """Parse a standard-form 0x08 message. Raises on prefix or
    constant-region mismatch."""
    if len(buf) < STANDARD_HEADER_SIZE:
        raise ValueError(
            f"need at least {STANDARD_HEADER_SIZE} bytes; got {len(buf)}"
        )
    if buf[:4] != STANDARD_PREFIX:
        raise ValueError(
            f"standard prefix mismatch: expected {STANDARD_PREFIX.hex()}, "
            f"got {buf[:4].hex()}"
        )
    if buf[5:11] != STANDARD_CONSTANT:
        raise ValueError(
            f"constant region at +0x05..+0x0a mismatch: expected "
            f"{STANDARD_CONSTANT.hex()}, got {buf[5:11].hex()}"
        )
    return ChunkedStream08Standard(
        subtype=buf[4],
        opaque=buf[11:],
    )


def decode_uuid_prefixed(buf: bytes) -> ChunkedStream08UuidPrefixed:
    """Parse a UUID-prefixed 0x08 message. Raises on minimum-size."""
    if len(buf) < UUID_PREFIX_SIZE:
        raise ValueError(
            f"need at least {UUID_PREFIX_SIZE} bytes; got {len(buf)}"
        )
    return ChunkedStream08UuidPrefixed(
        uuid=buf[:UUID_PREFIX_SIZE],
        opaque=buf[UUID_PREFIX_SIZE:],
    )


def decode_either(buf: bytes) -> ChunkedStream08:
    """Dispatch to standard or UUID-prefixed by sniffing the first 4 bytes."""
    if len(buf) >= 4 and buf[:4] == STANDARD_PREFIX:
        return decode_standard(buf)
    return decode_uuid_prefixed(buf)


def encode_either(msg: ChunkedStream08) -> bytes:
    """Encode either form. Dispatches by dataclass type."""
    if isinstance(msg, ChunkedStream08Standard):
        return encode_standard(msg)
    if isinstance(msg, ChunkedStream08UuidPrefixed):
        return encode_uuid_prefixed(msg)
    raise TypeError(f"unsupported 0x08 form: {type(msg).__name__}")


if __name__ == "__main__":
    smallest = bytes.fromhex(
        "00010801"   # prefix
        "30"         # subtype
        "010101010000"  # constant region
        + "00" * 67   # placeholder opaque (78 - 11 = 67)
    )
    msg = decode_standard(smallest)
    print(f"standard: subtype=0x{msg.subtype:02x}, opaque_len={len(msg.opaque)}")
    assert encode_standard(msg) == smallest

    # Outlier: just confirm the dispatch and round-trip work
    outlier = bytes.fromhex("0387942a661f85431d458b40d21f3b26") + b"\xab" * 100
    omsg = decode_either(outlier)
    assert isinstance(omsg, ChunkedStream08UuidPrefixed)
    print(f"uuid-prefixed: uuid={omsg.uuid.hex()}, opaque_len={len(omsg.opaque)}")
    assert encode_either(omsg) == outlier
    print("OK — chunked_stream_08 both forms round-trip")
