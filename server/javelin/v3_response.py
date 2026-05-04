"""
RegistrationResponseMsg encoder.

REWRITTEN 2026-05-04 from a REAL successful login capture shared by Mixed
Nuts at docs/community/nw-login-safe/messages-redacted.txt seq 0x1.

The actual wire bytes for a server -> client RegistrationResponseMsg are
88 bytes. NO 16-byte type GUID prefix (the previous version of this file
guessed wrong about that). Instead the message starts with a 3-byte
preamble [0x00 0x01 type_byte], where type_byte = 0x03 for a
RegistrationResponseMsg.

Captured layout (with the 32-byte session-token span redacted by Mixed
Nuts before sharing):

  offset 0x00  00 01 03                          # preamble: marker + type=3
  offset 0x03  00 00 00 00                       # 4 zero bytes (likely error_code = 0)
  offset 0x07  0b 88 8d 68 70 6c 41 5b           # 8 bytes -- semantics unknown
  offset 0x0f  20                                # length-prefix = 32 (0x20)
  offset 0x10  XX * 32                           # 32-byte session token (REDACTED)
  offset 0x30  23                                # length-prefix = 35 (0x23)
  offset 0x31  "[RETAIL].Javelin.1.365.6031.6006993"   # 35-char server-version string
  offset 0x54  01 00 00 01                       # 4-byte trailer

Total: 88 bytes. Caller wraps in a Carrier data-channel record + envelope.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# Type code for RegistrationResponseMsg in the post-Carrier message stream.
RESPONSE_TYPE_BYTE = 0x03

# Default server-version string (length 35), captured verbatim from the
# real successful-login dump. Caller can override via constructor.
DEFAULT_SERVER_VERSION = "[RETAIL].Javelin.1.365.6031.6006993"

# 8-byte mystery field at offset 0x07 in Mixed Nuts' capture. We don't yet
# know what it encodes. Default to the captured bytes verbatim; caller can
# override if we learn what these mean (probably tied to session/clock).
DEFAULT_MYSTERY8 = bytes.fromhex("0b888d68706c415b")  # 0b 88 8d 68 70 6c 41 5b

# 4-byte trailer at offset 0x54 in Mixed Nuts' capture. Likely status flags
# or a fixed checksum. Captured verbatim.
DEFAULT_TRAILER = bytes.fromhex("01000001")  # 01 00 00 01


@dataclass
class V3RegistrationResponse:
    # The 32-byte session token at offset 0x10. Mixed Nuts redacted his —
    # default to a deterministic stub. Caller can supply real bytes once
    # we wire up a session-allocator.
    session_token: bytes = b"NWP-stub-session-token--3232bytes"  # 32 ASCII bytes

    # The 35-char server-version string at offset 0x31.
    server_version: str = DEFAULT_SERVER_VERSION

    # The 4-byte preamble immediately after the type byte. Captured shows
    # 4 zeros — interpreted as error_code/success-flag. Set to non-zero
    # for negative-test fuzzing.
    error_code: int = 0

    # 8-byte mystery field at offset 0x07. Default to captured bytes.
    mystery8: bytes = DEFAULT_MYSTERY8

    # 4-byte trailer at offset 0x54. Default to captured bytes.
    trailer: bytes = DEFAULT_TRAILER

    def __post_init__(self) -> None:
        if len(self.session_token) != 32:
            raise ValueError(
                f"session_token must be exactly 32 bytes; got {len(self.session_token)}"
            )
        if len(self.mystery8) != 8:
            raise ValueError(
                f"mystery8 must be exactly 8 bytes; got {len(self.mystery8)}"
            )
        if len(self.trailer) != 4:
            raise ValueError(
                f"trailer must be exactly 4 bytes; got {len(self.trailer)}"
            )
        ver_bytes = self.server_version.encode("utf-8")
        if len(ver_bytes) > 0xFF:
            raise ValueError(
                f"server_version length {len(ver_bytes)} too big for 1-byte prefix"
            )


def encode(resp: V3RegistrationResponse) -> bytes:
    """Build the on-wire RegistrationResponseMsg body.

    Returns exactly 88 bytes (or 53 + len(server_version) bytes if the
    server_version string isn't the default 35-char value).
    """
    out = bytearray()
    out += b"\x00\x01"                              # marker
    out.append(RESPONSE_TYPE_BYTE)                   # type = 0x03
    out += int(resp.error_code).to_bytes(4, "big", signed=True)  # 4 BE error_code
    out += resp.mystery8                             # 8 mystery bytes
    out.append(0x20)                                 # length-prefix = 32
    out += resp.session_token                        # 32-byte token
    ver_bytes = resp.server_version.encode("utf-8")
    out.append(len(ver_bytes))                       # length-prefix
    out += ver_bytes                                 # server-version string
    out += resp.trailer                              # 4-byte trailer
    return bytes(out)


def make_session_token() -> bytes:
    """Generate a fresh 32-byte session token suitable for the
    `session_token` field. ASCII-printable so it shows up legibly in logs
    (the real game token might be binary; if so we'll switch to os.urandom).
    """
    # 32 hex chars = 16 random bytes -> 32 ASCII chars
    return os.urandom(16).hex().encode("ascii")


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    resp = V3RegistrationResponse(session_token=make_session_token())
    blob = encode(resp)
    print(f"len={len(blob)} bytes (expected 88 for default server_version)")
    print(blob.hex())
    # Sanity: expected length is 3 + 4 + 8 + 1 + 32 + 1 + 35 + 4 = 88
    assert len(blob) == 88, f"expected 88, got {len(blob)}"
    print("OK")
