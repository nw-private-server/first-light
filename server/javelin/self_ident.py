"""
PlayerManagerSelfIdentificationMsg encoder.

Wire format hypothesized from `analysis/clientmessagestrait_wire_formats.md`
(static-RE wakes 51, 53, 60). Field offsets and types come from
decompiling `FUN_146454c00` (the handler) and `FUN_1402d13a0`
(the AZStd::vector<u32> copy used at body+0x08). The handler reads
exactly five fields from the message body before any conditional
branch, so the offsets are stable.

Decoded in-memory layout:

  +0x00  uint32_t              m_field0
  +0x04  (4 bytes alignment)
  +0x08  AZStd::vector<u32>    m_field08    (32-byte container in-memory)
  +0x28  uint8_t               m_debugFlag
  +0x29  (3 bytes padding)
  +0x2C  uint64_t              m_field2C    (UNALIGNED 8-byte read)
  +0x34  uint32_t              m_field34
  +0x38  end (min 56 bytes)

Wire form (AzCore convention):

  [u32 LE: m_field0]
  [u32 LE: m_field08 length][u32 LE × length: elements]
  [u8: m_debugFlag]
  [u64 LE: m_field2C]                 (no in-memory padding on the wire)
  [u32 LE: m_field34]

Min wire size with empty vector: 4 + 4 + 1 + 8 + 4 = **21 bytes**.

CAVEAT: as with `level_info_changed.py`, this is a hypothesized wire
format. AzCore vector wire convention is `[u32 count][elements]`;
that's what we assume. The in-memory u64 at +0x2C is unaligned —
the wire form drops the in-memory alignment padding (we don't emit
the 3-byte +0x29..+0x2B padding). A mismatch would manifest as the
client either ignoring the message or hitting the sender-validation
gate (the handler short-circuits when param_5's UUID-shaped struct
doesn't match the expected sender).

Field semantic notes (from the static-RE work):

  - m_field0:    u32 — purpose unconfirmed (sequence? persona-id-half?)
  - m_field08:   u32 vector — purpose unconfirmed (character IDs?
                              channel IDs? shader-set IDs?)
  - m_debugFlag: when true, triggers a debug-only branch in the handler
                 that reads CVars `g_debugPlayerPosition` /
                 `g_debugPlayerRotation`. Production servers should
                 send 0.
  - m_field2C:   u64 — possibly a session id or timestamp.
  - m_field34:   u32 — maybe a flags field.

The handler also forwards three identity-tuple inputs (param_3/4/7 in
the dispatcher's call) into the wrapper sub-object setters. Those are
NOT part of the wire body; they're side-channel inputs the dispatcher
framework provides.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Sequence


# Minimum wire-form size (all empty / zero):
MIN_WIRE_SIZE = 4 + 4 + 1 + 8 + 4  # 21


@dataclass
class PlayerManagerSelfIdentificationMsg:
    # u32 at struct +0x00. Purpose unconfirmed.
    field_0: int = 0

    # u32 vector at struct +0x08. Purpose unconfirmed.
    # Defaults to empty.
    field_08: tuple[int, ...] = ()

    # u8 at struct +0x28. Production servers MUST set this to 0
    # (1 triggers a debug-only branch that reads CVars).
    debug_flag: int = 0

    # u64 at struct +0x2C. Purpose unconfirmed.
    field_2c: int = 0

    # u32 at struct +0x34. Purpose unconfirmed.
    field_34: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.field_0 <= 0xFFFFFFFF:
            raise ValueError(f"field_0 must fit in u32; got {self.field_0}")
        if not 0 <= self.debug_flag <= 0xFF:
            raise ValueError(
                f"debug_flag must fit in u8; got {self.debug_flag}"
            )
        if not 0 <= self.field_2c <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError(f"field_2c must fit in u64; got {self.field_2c}")
        if not 0 <= self.field_34 <= 0xFFFFFFFF:
            raise ValueError(f"field_34 must fit in u32; got {self.field_34}")
        if not isinstance(self.field_08, tuple):
            # Allow list/sequence inputs but normalize to tuple for
            # immutability + cleaner equality.
            self.field_08 = tuple(self.field_08)
        for i, v in enumerate(self.field_08):
            if not 0 <= v <= 0xFFFFFFFF:
                raise ValueError(
                    f"field_08[{i}] must fit in u32; got {v}"
                )
        if len(self.field_08) > 0xFFFFFFFF:
            raise ValueError(
                f"field_08 length {len(self.field_08)} exceeds u32"
            )


def encode(msg: PlayerManagerSelfIdentificationMsg) -> bytes:
    """Build the on-wire PlayerManagerSelfIdentificationMsg body.

    Returns the body only (no Carrier framing, no envelope, no preamble).
    Caller wraps as appropriate.
    """
    out = bytearray()
    out += struct.pack("<I", msg.field_0)                       # +0x00
    out += struct.pack("<I", len(msg.field_08))                 # vector length
    for v in msg.field_08:
        out += struct.pack("<I", v)                             # u32 elements
    out += bytes((msg.debug_flag & 0xFF,))                      # u8
    out += struct.pack("<Q", msg.field_2c)                      # u64
    out += struct.pack("<I", msg.field_34)                      # u32
    return bytes(out)


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    msg = PlayerManagerSelfIdentificationMsg(
        field_0=0x11223344,
        field_08=(0xa, 0xb, 0xc),
        debug_flag=0,
        field_2c=0xCAFEBABEDEADBEEF,
        field_34=0x55667788,
    )
    blob = encode(msg)
    expected = MIN_WIRE_SIZE + 4 * len(msg.field_08)
    print(f"len={len(blob)} bytes (expected={expected})")
    print(blob.hex())
    assert len(blob) == expected, f"expected {expected}, got {len(blob)}"
    print("OK")
