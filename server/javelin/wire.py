"""Pure-Python wire-encoding helpers used by the REP responder.

Kept out of `server.rep_responder` so unit tests can exercise them
without pulling in the pyOpenSSL DTLS dependency.

  - `encode_vlq32(n)`  -> 1..5 byte canonical-shortest-form VLQ32
  - `chunk_replay_payload(body, chunk_size)` -> [(remaining, slice), ...]
    for MF_CHUNKS reassembly, with a chunks-countdown convention
"""

from __future__ import annotations


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
