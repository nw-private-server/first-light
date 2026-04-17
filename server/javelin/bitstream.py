"""
BitStream implementation matching Javelin's `Javelin_BitStream_ReadBits`
(NewWorld.exe @ 0x140f7c420).

Semantics verified from decompilation:
- Bit-level cursor over a byte buffer.
- ReadBits(n) either memcpy's aligned bytes or shifts byte-by-byte for
  non-aligned reads.
- Big-endian byte-swap is applied AFTER reading (by the caller) when the
  byteswap flag at `stream[+0x24]` is zero (default).

Struct layout (40 bytes on wire):
  +0x00  u64  m_basePtr
  +0x08  u64  m_startBitOffset
  +0x10  u64  m_cursorBits
  +0x18  u64  m_endBits
  +0x20  u8   m_errorFlag
"""

from __future__ import annotations

from dataclasses import dataclass


class BitStreamError(Exception):
    """Raised when a BitStream read goes past the end."""


@dataclass
class BitStream:
    data: bytes
    start_bit: int = 0
    cursor_bit: int = 0
    end_bit: int = -1
    error: bool = False

    def __post_init__(self):
        if self.end_bit < 0:
            self.end_bit = len(self.data) * 8 - self.start_bit

    def remaining(self) -> int:
        return self.end_bit - self.cursor_bit

    def read_bits(self, n_bits: int) -> bytes:
        """Read n_bits bits, returned as ceil(n_bits/8) bytes.

        Bytes are returned in the same order as read from the stream.
        The caller is responsible for byte-swapping if the field is a
        big-endian multi-byte integer (same as the binary).
        """
        if self.error:
            raise BitStreamError("stream already in error state")
        if n_bits > self.remaining():
            self.error = True
            raise BitStreamError(
                f"read_bits({n_bits}) past end "
                f"(cursor={self.cursor_bit}, end={self.end_bit})"
            )

        out_len = (n_bits + 7) // 8
        out = bytearray(out_len)

        abs_bit = self.start_bit + self.cursor_bit
        byte_off = abs_bit >> 3
        bit_in_byte = abs_bit & 7

        if bit_in_byte == 0:
            # Fast-path: byte-aligned.
            out[:] = self.data[byte_off:byte_off + out_len]
        else:
            # Slow-path: shift-and-mask, matches the inner loop in
            # 0x140f7c420.
            written = 0
            while written < n_bits:
                abs_bit = self.start_bit + self.cursor_bit + written
                byte_off = abs_bit >> 3
                bit_in_byte = abs_bit & 7

                lo = self.data[byte_off] >> bit_in_byte
                hi_mask = (1 << bit_in_byte) - 1
                if byte_off + 1 < len(self.data) and bit_in_byte:
                    hi = (self.data[byte_off + 1] & hi_mask) << (8 - bit_in_byte)
                else:
                    hi = 0
                out[written // 8] = (hi | lo) & 0xFF
                written += 8

        self.cursor_bit += n_bits
        return bytes(out)

    def read_u8(self) -> int:
        return self.read_bits(8)[0]

    def read_u16_be(self) -> int:
        b = self.read_bits(16)
        return int.from_bytes(b, "big")

    def read_u16_le(self) -> int:
        b = self.read_bits(16)
        return int.from_bytes(b, "little")

    def read_u32_be(self) -> int:
        b = self.read_bits(32)
        return int.from_bytes(b, "big")
