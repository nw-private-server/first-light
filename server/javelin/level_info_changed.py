"""
LevelInfoChangedMsg encoder.

See `analysis/clientmessagestrait_wire_formats.md` for the canonical
wire-format reference (kept in sync with this file by convention).
Wire format hypothesized from `analysis/clientmessagestrait_wire_formats.md`
(static-RE wakes 51, 53, 54, 57, 60). Field offsets and types come from
decompiling `FUN_146446800` (the handler) and `FUN_1464027b0` (the body
copy constructor). The full in-memory struct is 176 bytes (with a
runtime-only `is_initialized` byte at +0xB0 that the encoder does NOT
emit).

The serialized wire form follows the AzCore convention: fields in
declaration order, integers little-endian, `AZStd::string` as
`[u32 length_LE][raw bytes]`, `AZStd::unordered_*` as
`[u32 count_LE][elements...]`. Struct padding at +0xA4..+0xA7 is in-memory
alignment only and is NOT serialized.

Decoded layout:

  +0x00  AZStd::string  m_levelName              [u32 length][bytes]
  +0x28  AZStd::string  m_someOtherName          [u32 length][bytes]
  +0x50  u32 x 4        (Vec4/quat — purpose TBD)
  +0x60  u64
  +0x68  AZStd::unordered_*  m_extendedField     [u32 count][elements]
  +0xA0  u8 x 4         flags  (m_field_a0, m_levelIsLoading,
                                m_isInGameTransition, m_field_a3)
  +0xA8  u64            m_clientContextInstanceId  (server MUST change
                                                    this between calls
                                                    or the client de-dups)

Min wire size: 4 + 4 + 16 + 8 + 4 + 4 + 8 = 48 bytes (all-zeros / empty
strings / empty container).

CAVEAT: this is a hypothesized wire format derived from in-memory layout
and AzCore conventions. Without a captured LevelInfoChangedMsg from a
real session, we can't fully validate it. A mismatch would show up as
the client either ignoring the message or aborting.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Sequence


# Minimum wire-form size (all empty / zero):
MIN_WIRE_SIZE = 4 + 4 + 16 + 8 + 4 + 4 + 8


@dataclass
class LevelInfoChangedMsg:
    """AzCore-style typed message: signals a level / map transition.

    Encoded server → client when the world the player is loading
    changes. Carries the level name, a paired secondary name, a
    geometry quadruple, a level-loading flag, and an in-game-
    transition flag. The handler in the client uses these to
    advance the state machine past state 12 (WaitingForSpawnPoint),
    so server emission of this message is one path past that gate.
    """
    # m_levelName at struct +0x00. The level identifier the client uses
    # to locate config / asset bundles.
    level_name: str = ""

    # m_someOtherName at struct +0x28. Purpose unconfirmed; possibly
    # region/instance display name. The handler reads it (as part of
    # the body copy) but doesn't make decisions on it.
    other_name: str = ""

    # 4-tuple at struct +0x50. Looks like a Vec4/quat from the access
    # pattern (4 contiguous u32s). Default to all zero.
    quad: tuple[int, int, int, int] = (0, 0, 0, 0)

    # u64 at struct +0x60. Purpose unconfirmed.
    field_60: int = 0

    # m_extendedField at struct +0x68. AZStd::unordered_set / map; we
    # encode an empty container (count=0) by default. Element type T
    # is unknown without further RE.
    extended_count: int = 0

    # 4 byte flags at struct +0xA0..+0xA3. Defaults match what the
    # handler passes through:
    #   field_a0      — purpose unconfirmed
    #   level_is_loading (+0xA1)  — passed to FUN_1463e42b0 callback
    #                                dispatcher; gate is per-listener
    #                                (wake 57). 1 is the conventional value.
    #   is_in_game_transition (+0xA2) — gate for the state-14 → state-13
    #                                    transition; must be non-zero for
    #                                    that branch to fire.
    #   field_a3      — purpose unconfirmed
    field_a0: int = 0
    level_is_loading: int = 1
    is_in_game_transition: int = 1
    field_a3: int = 0

    # m_clientContextInstanceId at struct +0xA8. The handler de-dups by
    # comparing this u64 to its cached previous value (outer + 0x198).
    # Server MUST change this between consecutive LevelInfoChangedMsg
    # calls or the client treats them as redundant.
    client_context_instance_id: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.field_a0 <= 0xFF:
            raise ValueError(f"field_a0 must fit in u8; got {self.field_a0}")
        if not 0 <= self.level_is_loading <= 0xFF:
            raise ValueError(
                f"level_is_loading must fit in u8; got {self.level_is_loading}"
            )
        if not 0 <= self.is_in_game_transition <= 0xFF:
            raise ValueError(
                f"is_in_game_transition must fit in u8; got "
                f"{self.is_in_game_transition}"
            )
        if not 0 <= self.field_a3 <= 0xFF:
            raise ValueError(f"field_a3 must fit in u8; got {self.field_a3}")
        if not 0 <= self.client_context_instance_id <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError(
                "client_context_instance_id must fit in u64; got "
                f"{self.client_context_instance_id}"
            )
        if len(self.quad) != 4:
            raise ValueError(f"quad must have 4 elements; got {len(self.quad)}")
        for i, v in enumerate(self.quad):
            if not 0 <= v <= 0xFFFFFFFF:
                raise ValueError(
                    f"quad[{i}] must fit in u32; got {v}"
                )
        if not 0 <= self.field_60 <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError(f"field_60 must fit in u64; got {self.field_60}")
        if self.extended_count != 0:
            raise NotImplementedError(
                "non-empty m_extendedField encoding not yet supported "
                "(element type T not yet decoded; see "
                "analysis/clientmessagestrait_wire_formats.md)"
            )


def _encode_az_string(s: str) -> bytes:
    """AzCore wire form for AZStd::string: [u32 length_LE][raw bytes]."""
    raw = s.encode("utf-8")
    return struct.pack("<I", len(raw)) + raw


def encode(msg: LevelInfoChangedMsg) -> bytes:
    """Build the on-wire LevelInfoChangedMsg body.

    Returns the body only (no Carrier framing, no envelope, no preamble).
    Caller wraps as appropriate for the sequence stage.
    """
    out = bytearray()
    out += _encode_az_string(msg.level_name)
    out += _encode_az_string(msg.other_name)
    out += struct.pack("<IIII", *msg.quad)               # 4-tuple at +0x50
    out += struct.pack("<Q", msg.field_60)               # u64 at +0x60
    out += struct.pack("<I", msg.extended_count)         # unordered count
    # Note: when extended_count > 0, encoded elements would follow here
    out += bytes((
        msg.field_a0 & 0xFF,
        msg.level_is_loading & 0xFF,
        msg.is_in_game_transition & 0xFF,
        msg.field_a3 & 0xFF,
    ))
    out += struct.pack("<Q", msg.client_context_instance_id)
    return bytes(out)


def _decode_az_string(buf: bytes, offset: int) -> tuple[str, int]:
    """Read an AzCore-wire AZStd::string starting at offset. Returns
    (decoded_string, bytes_consumed)."""
    if offset + 4 > len(buf):
        raise ValueError(
            f"truncated string length prefix at offset {offset} "
            f"(buffer length {len(buf)})"
        )
    length = struct.unpack_from("<I", buf, offset)[0]
    end = offset + 4 + length
    if end > len(buf):
        raise ValueError(
            f"truncated string body at offset {offset}: declared length "
            f"{length} but only {len(buf) - offset - 4} bytes remain"
        )
    text = buf[offset + 4:end].decode("utf-8")
    return text, 4 + length


def decode(buf: bytes) -> LevelInfoChangedMsg:
    """Parse an on-wire LevelInfoChangedMsg body.

    Inverse of `encode()`. Raises `ValueError` on truncation, encoding
    errors, or trailing bytes after the expected end. Raises
    `NotImplementedError` if the buffer declares a non-empty
    `m_extendedField` (parsing the AZStd::unordered_* element layout
    is not yet supported — see the encoder's caveat).
    """
    pos = 0

    level_name, consumed = _decode_az_string(buf, pos)
    pos += consumed

    other_name, consumed = _decode_az_string(buf, pos)
    pos += consumed

    if pos + 16 > len(buf):
        raise ValueError(f"truncated quad at offset {pos}")
    quad = struct.unpack_from("<IIII", buf, pos)
    pos += 16

    if pos + 8 > len(buf):
        raise ValueError(f"truncated field_60 at offset {pos}")
    (field_60,) = struct.unpack_from("<Q", buf, pos)
    pos += 8

    if pos + 4 > len(buf):
        raise ValueError(f"truncated extended_count at offset {pos}")
    (extended_count,) = struct.unpack_from("<I", buf, pos)
    pos += 4

    if extended_count != 0:
        raise NotImplementedError(
            "non-empty m_extendedField decoding not yet supported "
            f"(declared count = {extended_count})"
        )

    if pos + 4 > len(buf):
        raise ValueError(f"truncated flag bytes at offset {pos}")
    field_a0, level_is_loading, is_in_game_transition, field_a3 = buf[pos:pos + 4]
    pos += 4

    if pos + 8 > len(buf):
        raise ValueError(f"truncated client_context_instance_id at offset {pos}")
    (client_context_instance_id,) = struct.unpack_from("<Q", buf, pos)
    pos += 8

    if pos != len(buf):
        raise ValueError(
            f"trailing {len(buf) - pos} unexpected bytes after expected end "
            f"(consumed {pos}, buffer is {len(buf)})"
        )

    return LevelInfoChangedMsg(
        level_name=level_name,
        other_name=other_name,
        quad=quad,
        field_60=field_60,
        extended_count=extended_count,
        field_a0=field_a0,
        level_is_loading=level_is_loading,
        is_in_game_transition=is_in_game_transition,
        field_a3=field_a3,
        client_context_instance_id=client_context_instance_id,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    msg = LevelInfoChangedMsg(
        level_name="NewWorld_Aeternum",
        other_name="ServerAlpha-EU",
        client_context_instance_id=0x1234,
    )
    blob = encode(msg)
    expected_min = MIN_WIRE_SIZE + len("NewWorld_Aeternum") + len("ServerAlpha-EU")
    print(f"len={len(blob)} bytes (expected={expected_min})")
    print(blob.hex())
    assert len(blob) == expected_min, f"expected {expected_min}, got {len(blob)}"
    print("OK")
