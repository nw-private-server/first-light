"""Pure-Python wire-encoding helpers used by the REP responder.

Kept out of `server.rep_responder` so unit tests can exercise them
without pulling in the pyOpenSSL DTLS dependency.

  - `encode_vlq32(n)`  -> 1..5 byte canonical-shortest-form VLQ32
  - `chunk_replay_payload(body, chunk_size)` -> [(remaining, slice), ...]
    for MF_CHUNKS reassembly, with a chunks-countdown convention
  - `compute_cs_crc32(correlation_uuid, envelope)` -> u32
  - `serialize_cs_envelope(correlation_uuid, envelope)` -> bytes
    Build the full C→S framed message including CRC32 prefix.
"""

from __future__ import annotations

import struct
import zlib


def encode_vlq32(value: int) -> bytes:
    """AzCore VLQ32: 7 bits per byte, top bit set means more bytes follow.

    Handles values 0..2**32-1 in 1..5 bytes. The decoder in the binary
    accepts the canonical (shortest) form for any given value.
    """
    if value < 0:
        raise ValueError(f"VLQ32 cannot encode negative value {value}")
    if value > 0xFFFFFFFF:
        raise ValueError(f"VLQ32 cannot encode value > 2**32-1: {value}")
    out = bytearray()
    remaining = value
    while True:
        chunk = remaining & 0x7F
        remaining >>= 7
        if remaining:
            out.append(chunk | 0x80)
        else:
            out.append(chunk)
            return bytes(out)


def chunk_replay_payload(
    body: bytes, chunk_size: int = 1100,
) -> list[tuple[int, bytes]]:
    """Split a body into chunks for MF_CHUNKS transmission.

    Returns a list of (remaining, slice) tuples where the first
    `remaining` is the total chunk count and each subsequent value
    decrements to 1 (the countdown convention used by the binary's
    chunk-reassembly path). Single-chunk fallthrough returns
    [(1, body)] so the caller can decide whether to even set MF_CHUNKS.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if not body:
        return [(1, b"")]
    n = (len(body) + chunk_size - 1) // chunk_size
    return [
        (n - i, body[i * chunk_size:(i + 1) * chunk_size])
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# C→S framing layer (Mixed Nuts spec)
#
# Per `docs/post-v3-sequence.md` and confirmed empirically (wake 90):
# every captured W-direction message has the layout
#
#   [crc32:4 BE][payload_size:4 BE][correlation_uuid:16][typed_envelope...]
#
# where crc32 = standard zlib CRC32 (IEEE 802.3 polynomial 0xEDB88320,
# reflected) computed over (correlation_uuid + typed_envelope), written
# in big-endian byte order. The payload_size field equals
# 16 + len(typed_envelope).
#
# Validated against 37 of 39 captured W-direction messages. The 2
# exceptions are: (a) the V3 RegistrationRequest at seq 0 (pre-session
# framing differs), and (b) the 0x12f6 keybinding-config message which
# has 36-byte redacted spans in the public capture that break the CRC.


def compute_cs_crc32(correlation_uuid: bytes, envelope: bytes) -> int:
    """Compute the CRC32 used in the C→S framing layer.

    Standard zlib CRC32 (IEEE 802.3 polynomial, reflected) over
    `correlation_uuid + envelope`. Result is a u32 the caller can
    serialize as 4 big-endian bytes.

    Validated against captured replay W-direction messages — see
    `test_codecs.py::test_cs_crc32_matches_captured_w_messages`.
    """
    if len(correlation_uuid) != 16:
        raise ValueError(
            f"correlation_uuid must be exactly 16 bytes; "
            f"got {len(correlation_uuid)}"
        )
    return zlib.crc32(correlation_uuid + envelope) & 0xFFFFFFFF


def serialize_cs_envelope(correlation_uuid: bytes, envelope: bytes) -> bytes:
    """Build the full C→S framed message:
        [crc32:4 BE][payload_size:4 BE][correlation_uuid:16][envelope...]

    The CRC is computed automatically from `correlation_uuid + envelope`.
    `payload_size` = 16 + len(envelope).
    """
    crc = compute_cs_crc32(correlation_uuid, envelope)
    payload_size = 16 + len(envelope)
    return (
        struct.pack(">I", crc)
        + struct.pack(">I", payload_size)
        + correlation_uuid
        + envelope
    )


def parse_cs_envelope(buf: bytes) -> tuple[int, int, bytes, bytes]:
    """Inverse of `serialize_cs_envelope`. Returns
    `(crc32, payload_size, correlation_uuid, envelope)`.

    Does NOT validate the CRC — caller decides how to handle CRC
    mismatches (some test scenarios use captured-byte fields with
    redactions that break the CRC; see wake 90 notes)."""
    if len(buf) < 24:
        raise ValueError(
            f"buffer too short for C→S envelope: need at least 24 bytes; "
            f"got {len(buf)}"
        )
    (crc32,) = struct.unpack_from(">I", buf, 0)
    (payload_size,) = struct.unpack_from(">I", buf, 4)
    correlation_uuid = buf[8:24]
    envelope = buf[24:]
    return crc32, payload_size, correlation_uuid, envelope
