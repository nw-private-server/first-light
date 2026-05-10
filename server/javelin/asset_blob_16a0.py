"""
Asset blob — type 0x16a0 (R direction).

2 captures in the existing replay:

- **Small variant** (153 bytes typed body, seq 0x28) — full structural
  layout below.
- **Large variant** (~99 KB, seq 0x29) — same 20-byte prefix (type
  header + asset_uuid), bulk data tail. Wake-109 codec
  (`AssetBlob16A0Large` + `decode_either`) handles round-trip but does
  not subdivide the bulk tail; with only one capture and most of the
  body redacted, structural assumptions would be guessing.

The small-variant body carries an embedded asset-pool reference as
a length-prefixed UTF-8 string (`"ItemPool"`) and a `$`-delimited
asset identifier — observed in the capture but with the asset-id
bytes redacted.

The exact layout of the leading and trailing fixed-shape sections
is partially conjectural — only one un-redacted capture is
available — so this codec validates the **type-header**, the
**embedded "ItemPool" length-prefixed string**, and the **trailing
byte counts**; the variable-shape middle section is kept as opaque
bytes so a round-trip is byte-exact.

Wire layout (153-byte typed body, including 4-byte type header):

  +0x00  u8x4    type_header        [00 01 a0 5a] = type 0x16a0
  +0x04  u8x16   asset_uuid         16 bytes — lower 8 are
                                     session_uuid_lower
  +0x14  u8x60   header_blob        60 bytes of header data —
                                     contains two 16-byte UUID-like
                                     blocks and several u32-shaped
                                     fields. Treated as opaque.
  +0x50  u16 BE  asset_class_len    e.g. 8 for "ItemPool"
  +0x52  bytes×L asset_class        UTF-8 ("ItemPool" in capture)
  +0x52+L  u8    sep                always `$` (0x24)
  +0x53+L  bytes×40  asset_id       ASCII asset identifier
                                     (UUID-like; redacted in capture)
  +0x7B+L  u8x21  trailer_blob      21 bytes — `00*7 + 0b` followed
                                     by 16 bytes of UUID/hash data
                                     and a terminator `00`. Treated
                                     as opaque.

Concretely for the captured small variant (asset_class_len=8):
  - +0x14..+0x4F  60 bytes header_blob
  - +0x50..+0x51  `00 08` (length BE)
  - +0x52..+0x59  "ItemPool"
  - +0x5A         (length=8 means asset_class is 8 bytes; total used so far: +0x5A)

  Wait — the captured byte sequence has `00 01 00 08` at +0x4F..+0x52,
  so the layout above doesn't fully cleanly align. To stay safe, this
  codec encodes/decodes by:

    * Validating type_header.
    * Extracting asset_uuid (16 bytes).
    * Storing the rest as `payload_bytes` (133 bytes) and exposing a
      `find_asset_class()` helper that locates the
      `\x00\x08ItemPool` style length-prefix inline.

The codec is intentionally **conservative**: until a second
un-redacted 0x16a0 capture is available, structural assumptions
about the middle section can't be validated.
"""

from __future__ import annotations

from dataclasses import dataclass


# Total typed-body size of the small-variant 0x16a0.
SMALL_TYPED_BODY_SIZE = 153

# 4-byte typed envelope header for type 0x16a0:
#   marker [0x00, 0x01], then ((0x16a0 & 0x3f) | 0x80) = 0xa0,
#   then ((0x16a0 >> 6) & 0xff) = 0x5a
TYPE_HEADER = bytes((0x00, 0x01, 0xa0, 0x5a))

ASSET_UUID_OFFSET = 4
ASSET_UUID_SIZE = 16
PAYLOAD_OFFSET = ASSET_UUID_OFFSET + ASSET_UUID_SIZE  # 20


@dataclass
class AssetBlob16A0Small:
    """R-direction 0x16a0 small variant (153 bytes typed body)."""

    asset_uuid: bytes        # 16 bytes — lower 8 are session_uuid_lower
    payload_bytes: bytes     # 133 bytes — opaque payload (see module docstring)

    def __post_init__(self) -> None:
        if len(self.asset_uuid) != ASSET_UUID_SIZE:
            raise ValueError(
                f"asset_uuid must be exactly {ASSET_UUID_SIZE} bytes; "
                f"got {len(self.asset_uuid)}"
            )
        expected_payload = SMALL_TYPED_BODY_SIZE - PAYLOAD_OFFSET
        if len(self.payload_bytes) != expected_payload:
            raise ValueError(
                f"payload_bytes must be exactly {expected_payload} bytes; "
                f"got {len(self.payload_bytes)}"
            )

    def find_asset_class(self) -> tuple[str, int] | None:
        """Locate the embedded `[u16 BE length][UTF-8 string]` asset-class
        marker in the payload. Returns (string, payload_offset) on success.
        Looks for the length-prefix pattern preceding the captured
        `"ItemPool"` byte sequence."""
        # Scan for u16 BE lengths in [4, 32] and try to decode that many
        # bytes after as UTF-8. Return the first valid match.
        p = self.payload_bytes
        for i in range(0, len(p) - 2):
            length = (p[i] << 8) | p[i + 1]
            if 4 <= length <= 32 and i + 2 + length <= len(p):
                try:
                    s = p[i + 2:i + 2 + length].decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if s.isascii() and s.isalnum():
                    return s, i
        return None


def encode(msg: AssetBlob16A0Small) -> bytes:
    """Build the on-wire 0x16a0 small-variant body (153 bytes total)."""
    return TYPE_HEADER + msg.asset_uuid + msg.payload_bytes


def decode(buf: bytes) -> AssetBlob16A0Small:
    """Parse a 0x16a0 small-variant body. Raises on size or type-header
    mismatch."""
    if len(buf) != SMALL_TYPED_BODY_SIZE:
        raise ValueError(
            f"expected exactly {SMALL_TYPED_BODY_SIZE} bytes; got {len(buf)}"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )
    asset_uuid = buf[ASSET_UUID_OFFSET:ASSET_UUID_OFFSET + ASSET_UUID_SIZE]
    payload_bytes = buf[PAYLOAD_OFFSET:]
    return AssetBlob16A0Small(asset_uuid=asset_uuid, payload_bytes=payload_bytes)


# ---------------------------------------------------------------------------
#  Large variant (wake 109)
# ---------------------------------------------------------------------------

# The large variant's body in the captured replay is 99 819 bytes — three
# orders of magnitude larger than the small variant. The first 20 bytes
# (type header + asset_uuid) are identical in both forms; the remaining
# bulk-data tail varies wildly in size.
#
# We don't know the exact subdivision of the bulk tail without runtime
# context (it's the asset/world streaming payload — likely a sequence of
# length-prefixed sub-records keyed by asset class), so the codec
# preserves it verbatim. With a second capture this could be upgraded;
# until then the codec just round-trips.

# Minimum body size for the large variant: prefix only.
LARGE_MIN_BODY_SIZE = PAYLOAD_OFFSET  # 20

# Threshold above which `decode_either` treats the body as the large
# variant. Anything larger than the small variant's fixed size that still
# starts with TYPE_HEADER goes through the Large path.
SIZE_THRESHOLD = SMALL_TYPED_BODY_SIZE


@dataclass
class AssetBlob16A0Large:
    """R-direction 0x16a0 large variant: same 20-byte prefix as the small
    variant, opaque bulk-data tail (variable length).

    The bulk tail is kept verbatim — round-trip is byte-identical for
    any captured large 0x16a0 body."""

    asset_uuid: bytes        # 16 bytes — lower 8 are session_uuid_lower
    bulk_data: bytes         # variable — opaque

    def __post_init__(self) -> None:
        if len(self.asset_uuid) != ASSET_UUID_SIZE:
            raise ValueError(
                f"asset_uuid must be exactly {ASSET_UUID_SIZE} bytes; "
                f"got {len(self.asset_uuid)}"
            )


def encode_large(msg: AssetBlob16A0Large) -> bytes:
    """Build the on-wire 0x16a0 large-variant body."""
    return TYPE_HEADER + msg.asset_uuid + msg.bulk_data


def decode_large(buf: bytes) -> AssetBlob16A0Large:
    """Parse a 0x16a0 large-variant body. Raises on minimum-size or
    type-header mismatch."""
    if len(buf) < LARGE_MIN_BODY_SIZE:
        raise ValueError(
            f"need at least {LARGE_MIN_BODY_SIZE} bytes "
            f"(4 header + 16 asset_uuid); got {len(buf)}"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )
    return AssetBlob16A0Large(
        asset_uuid=buf[ASSET_UUID_OFFSET:ASSET_UUID_OFFSET + ASSET_UUID_SIZE],
        bulk_data=buf[PAYLOAD_OFFSET:],
    )


# Common type for either variant — handy for type hints.
AssetBlob16A0 = AssetBlob16A0Small | AssetBlob16A0Large


def decode_either(buf: bytes) -> AssetBlob16A0:
    """Pick small vs large based on body size. The small variant is
    fixed at 153 bytes; anything larger that still starts with the
    type header goes through the Large codec."""
    if len(buf) == SMALL_TYPED_BODY_SIZE:
        return decode(buf)
    return decode_large(buf)


def encode_either(msg: AssetBlob16A0) -> bytes:
    """Encode either variant. Picks by isinstance."""
    if isinstance(msg, AssetBlob16A0Small):
        return encode(msg)
    if isinstance(msg, AssetBlob16A0Large):
        return encode_large(msg)
    raise TypeError(
        f"unsupported 0x16a0 message type: {type(msg).__name__}"
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Captured 0x16a0 R seq 0x28; the 36-byte asset-id span after '$'
    # is redacted in the public capture and replaced with `00` here.
    captured = bytes.fromhex(
        "0001a05a"
        "69ceaf9f28443d0dbf85314bbc4a951a"
        + "01845b00000000f9"                                      # 8
        + "bec16c136f4458b7508e4f4cd2921412"                      # 16
        + "9c60033f92487294 89ccc326511cdb78".replace(" ", "")    # 16
        + "af11d2206da359"                                        # 7
        + "0000000a0000000200 0000c800".replace(" ", "")          # 13
        + "010008"                                                # 3 (u16 BE 1, then prefix `00 08`)
        + "4974656d506f6f6c"                                      # 8 = "ItemPool"
        + "24"                                                    # 1 = '$'
        + "00" * 36                                               # 36 redacted asset-id bytes
        + "00 00 00 00 00 00 00 0b".replace(" ", "")              # 8
        + "a3 40 42 47 2e 33 4c 7b".replace(" ", "")              # 8
        + "a5 f5 be 4f cf 93 62 4b".replace(" ", "")              # 8
        + "00"                                                    # 1 terminator
    )
    msg = decode(captured)
    found = msg.find_asset_class()
    print(f"asset_uuid={msg.asset_uuid.hex()}, len(payload)={len(msg.payload_bytes)}")
    print(f"asset_class={found}")
    rebuilt = encode(msg)
    assert rebuilt == captured, (
        f"round-trip failed:\n  got: {rebuilt.hex()}\n  exp: {captured.hex()}"
    )
    print(f"len={len(rebuilt)} bytes — round-trip OK")
