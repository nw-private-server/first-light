"""
Empty-marker — type 0x651.

Single capture in the replay (R direction, 4 bytes total). The body
is **exactly the 4-byte typed envelope header for type 0x651, with
zero payload bytes following it**:

  0x651 & 0x3f       = 0x11
  (0x11 | 0x80)      = 0x91
  (0x651 >> 6) & 0xff = 0x19

so the type header is `00 01 91 19`, and the captured body is
literally those four bytes.

A zero-payload typed message is the protocol's way of saying "this
event happened, no parameters needed" — like a state nudge, a
session-readiness signal, or an empty completion notice. Without
runtime context (state-10 thread is open) we can't authoritatively
name it, but the format is unambiguous.

The codec is here so:
  1. test_codecs covers all 40 captured wire-types,
  2. a server replay would correctly identify the type even though
     the body carries no data,
  3. encoding side is trivially derivable from the type-id alone.
"""

from __future__ import annotations

from dataclasses import dataclass


TYPE_ID = 0x651

# 4-byte typed envelope header: marker [0x00, 0x01], then
# ((TYPE_ID & 0x3f) | 0x80), then ((TYPE_ID >> 6) & 0xff).
TYPE_HEADER = bytes((0x00, 0x01, 0x91, 0x19))

BODY_SIZE = 4  # exactly the type header; no payload


@dataclass(frozen=True)
class EmptyMarker651:
    """A 0x651 typed message with no payload.

    Frozen because there's nothing to vary — every instance is
    byte-identical on the wire. Constructable as `EmptyMarker651()`.
    """


def encode(_msg: EmptyMarker651 = EmptyMarker651()) -> bytes:
    """Build the 4-byte wire form. Always returns the same bytes."""
    return TYPE_HEADER


def decode(buf: bytes) -> EmptyMarker651:
    """Parse a 4-byte 0x651 message. Raises on size or header
    mismatch."""
    if len(buf) != BODY_SIZE:
        raise ValueError(
            f"expected exactly {BODY_SIZE} bytes; got {len(buf)}"
        )
    if buf != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf.hex()}"
        )
    return EmptyMarker651()


if __name__ == "__main__":
    captured = bytes.fromhex("00019119")
    msg = decode(captured)
    print(f"decoded: {msg!r}")
    assert encode(msg) == captured
    print("OK — empty-marker round-trips")
