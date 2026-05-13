"""
Vivox voice-chat configuration — type 0x1067 (R direction, singleton).

Single 86-byte capture (seq 0x65). Carries the URL/realm/issuer
configuration the client needs to authenticate to Amazon's Vivox
voice service.

Wire layout (4-byte typed envelope + 82-byte body):

  +0x00  u8x4    type_header        [00 01 a7 41] = type 0x1067
  +0x04  u8x16   identity_uuid      [first_uuid_half:8][session_uuid_lower:8]
                                     lower 8 bytes match the
                                     `bf 85 31 4b bc 4a 95 1a` shared
                                     session UUID lower half.
  +0x14  u8      url_len            length of the API URL (32 in capture)
  +0x15  bytes×L api_url            UTF-8 URL, e.g.
                                     "https://nwxp.www.vivox.com/api2/"
  +...   u8      realm_len          length of the realm (15 in capture)
  +...   bytes×L realm              UTF-8 realm, e.g.
                                     "amazon9050-ne83"
  +...   u8      issuer_len         length of the issuer (15 in capture)
  +...   bytes×L issuer             UTF-8 issuer, e.g.
                                     "@nwxp.vivox.com"
  +...   u8      terminator         always 0x00

Total: 4 (envelope) + 16 (uuid) + 1+L1 + 1+L2 + 1+L3 + 1 (terminator)
     = 23 + L1 + L2 + L3 bytes.

For the captured values: 23 + 32 + 15 + 15 = 85... but the message
is 86 bytes. Let me check: the captured trailer terminator is `00`
and there's no extra byte. Re-examining the bytes shows that the
sequence is exactly 86 = 23 + 32 + 15 + 15 + ... wait, 23 + 32 +
15 + 15 = 85. There's one extra byte somewhere. Looking at the
raw capture:

  hdr (4) + identity (16) + 0x20 + 32 + 0x0f + 15 + 0x0f + 15 + 0x00
  = 4 + 16 + 1 + 32 + 1 + 15 + 1 + 15 + 1 = 86 ✓

The `0x00` at the very end IS the terminator that's already counted.
Total exactly 86. The codec validates this arithmetic precisely.

The three Pascal-style u8-prefixed strings are the standard
serialization for short identifier strings in this game's protocol
(also seen in `level_descriptor_663` for level_name + level_path).
"""

from __future__ import annotations

from dataclasses import dataclass


# 4-byte typed envelope header for type 0x1067:
#   marker [0x00, 0x01], then ((0x1067 & 0x3f) | 0x80) = 0xa7,
#   then ((0x1067 >> 6) & 0xff) = 0x41
TYPE_HEADER = bytes((0x00, 0x01, 0xa7, 0x41))

IDENTITY_UUID_OFFSET = 4
IDENTITY_UUID_SIZE = 16
STRINGS_OFFSET = 20
TERMINATOR = 0x00

# Constants for sanity checks on the captured singleton.
CAPTURED_API_URL = "https://nwxp.www.vivox.com/api2/"
CAPTURED_REALM = "amazon9050-ne83"
CAPTURED_ISSUER = "@nwxp.vivox.com"


@dataclass
class VivoxConfig1067:
    """R-direction 0x1067 Vivox voice-chat configuration."""

    identity_uuid: bytes      # 16 bytes; lower 8 = session_uuid_lower
    api_url: str              # voice-service API URL
    realm: str                # voice realm / region identifier
    issuer: str               # voice token issuer

    def __post_init__(self) -> None:
        if len(self.identity_uuid) != IDENTITY_UUID_SIZE:
            raise ValueError(
                f"identity_uuid must be exactly {IDENTITY_UUID_SIZE} bytes; "
                f"got {len(self.identity_uuid)}"
            )
        for name, s in (("api_url", self.api_url), ("realm", self.realm),
                         ("issuer", self.issuer)):
            encoded = s.encode("utf-8")
            if not 0 <= len(encoded) <= 0xFF:
                raise ValueError(
                    f"{name} length {len(encoded)} doesn't fit in u8"
                )


def encode(msg: VivoxConfig1067) -> bytes:
    """Build the on-wire 0x1067 body."""
    out = bytearray()
    out += TYPE_HEADER
    out += msg.identity_uuid
    for s in (msg.api_url, msg.realm, msg.issuer):
        encoded = s.encode("utf-8")
        out += bytes((len(encoded),))
        out += encoded
    out += bytes((TERMINATOR,))
    return bytes(out)


def decode(buf: bytes) -> VivoxConfig1067:
    """Parse a 0x1067 body. Raises on type-header mismatch, length-prefix
    overrun, missing terminator, or trailing bytes."""
    if len(buf) < STRINGS_OFFSET + 1:
        raise ValueError(
            f"buffer too short: need at least {STRINGS_OFFSET + 1} bytes; "
            f"got {len(buf)}"
        )
    if buf[:4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[:4].hex()}"
        )
    identity_uuid = buf[IDENTITY_UUID_OFFSET:IDENTITY_UUID_OFFSET + IDENTITY_UUID_SIZE]
    pos = STRINGS_OFFSET
    strings = []
    for _ in range(3):
        if pos >= len(buf):
            raise ValueError(f"unexpected end of buffer at offset {pos}")
        length = buf[pos]
        pos += 1
        if pos + length > len(buf):
            raise ValueError(
                f"string length {length} at offset {pos - 1} overruns buffer"
            )
        try:
            strings.append(buf[pos:pos + length].decode("utf-8"))
        except UnicodeDecodeError as e:
            raise ValueError(
                f"string at offset {pos - 1} is not valid UTF-8: {e}"
            ) from None
        pos += length
    if pos >= len(buf):
        raise ValueError(f"missing terminator at offset {pos}")
    if buf[pos] != TERMINATOR:
        raise ValueError(
            f"terminator mismatch at offset {pos}: expected 0x{TERMINATOR:02x}, "
            f"got 0x{buf[pos]:02x}"
        )
    pos += 1
    if pos != len(buf):
        raise ValueError(
            f"unexpected trailing {len(buf) - pos} bytes after terminator"
        )
    return VivoxConfig1067(
        identity_uuid=identity_uuid,
        api_url=strings[0],
        realm=strings[1],
        issuer=strings[2],
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "0001a741"
        "d8c9c8af5e7a353c bf85314bbc4a951a".replace(" ", "")
        + "20" + CAPTURED_API_URL.encode("utf-8").hex()
        + "0f" + CAPTURED_REALM.encode("utf-8").hex()
        + "0f" + CAPTURED_ISSUER.encode("utf-8").hex()
        + "00"
    )
    msg = decode(captured)
    print(f"api_url={msg.api_url!r}")
    print(f"realm={msg.realm!r}")
    print(f"issuer={msg.issuer!r}")
    rebuilt = encode(msg)
    assert rebuilt == captured, (
        f"round-trip failed:\n  got: {rebuilt.hex()}\n  exp: {captured.hex()}"
    )
    print(f"len={len(rebuilt)} bytes — round-trip OK")
