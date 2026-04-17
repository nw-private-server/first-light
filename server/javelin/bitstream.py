"""
BitStream implementation matching Javelin's `Javelin_BitStream_ReadBits`
(NewWorld.exe @ 0x140f7c420) and the inline write pattern used by
Javelin_Carrier_WriteMessages (@ 0x140f65b20).

Semantics verified from decompilation:
- Bit-level cursor over a byte buffer.
- ReadBits(n) either memcpy's aligned bytes or shifts byte-by-byte for
  non-aligned reads.
- WriteBits(n) has the inverse behavior: aligned fast path, then a
  per-byte splice for unaligned writes.
- When the caller passes a multi-byte integer big-endian, it byte-swaps
  the value BEFORE calling write_bits (same as ReadMessageHeader does
  on the read side). This is controlled by a flag on the stream at
  `stream[+0x20]` ("byteswap needed") — zero means "yes swap".

Struct layout observed in the binary (40 bytes on wire):
  +0x00  u64  m_basePtr         base address of the backing buffer
  +0x08  u64  m_startBitOffset  how many bits into m_basePtr the window starts
  +0x10  u64  m_cursorBits      current bit offset from start of window
  +0x18  u64  m_endBits         end (in bits) of the window
  +0x20  u8   m_errorFlag
"""

from __future__ import annotations

from dataclasses import dataclass, field


class BitStreamError(Exception):
    """Raised when a BitStream read/write goes past the end."""


# ---------------------------------------------------------------------------
#  Reader
# ---------------------------------------------------------------------------

@dataclass
class BitStream:
    """Read-only bit-level view over a fixed buffer."""

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

        The order-within-byte follows what the decompiled
        Javelin_BitStream_ReadBits does: lower bits of each source byte
        map to lower bits of each output byte.
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
            out[:] = self.data[byte_off:byte_off + out_len]
        else:
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


# ---------------------------------------------------------------------------
#  Writer
# ---------------------------------------------------------------------------

@dataclass
class BitStreamWriter:
    """Grow-able bit-level writer. Mirrors the virtual WriteBits method
    called from Javelin_Carrier_WriteMessages and WriteSystemMessage.

    The buffer grows as needed. Final bytes are retrieved via `to_bytes()`
    which pads the last byte with zeros to byte-align the output.
    """

    buf: bytearray = field(default_factory=bytearray)
    cursor_bit: int = 0

    def write_bits(self, data: bytes, n_bits: int) -> None:
        """Write n_bits bits from `data`. `data` must be at least
        ceil(n_bits/8) bytes long."""
        if n_bits == 0:
            return
        if len(data) * 8 < n_bits:
            raise BitStreamError(
                f"write_bits: data has {len(data) * 8} bits but asked to write {n_bits}"
            )

        # Ensure buffer is large enough.
        needed_bytes = (self.cursor_bit + n_bits + 7) // 8
        if needed_bytes > len(self.buf):
            self.buf.extend(b"\x00" * (needed_bytes - len(self.buf)))

        cursor_byte = self.cursor_bit >> 3
        bit_in_byte = self.cursor_bit & 7

        if bit_in_byte == 0:
            # Byte-aligned fast path.
            full_bytes = n_bits // 8
            tail_bits = n_bits % 8
            if full_bytes:
                self.buf[cursor_byte:cursor_byte + full_bytes] = data[:full_bytes]
            if tail_bits:
                mask = (1 << tail_bits) - 1
                self.buf[cursor_byte + full_bytes] = data[full_bytes] & mask
        else:
            # Splice per-byte, matching the shift/mask inverse of read.
            written = 0
            while written < n_bits:
                src_byte = data[written // 8]
                remaining = n_bits - written
                abs_bit = self.cursor_bit + written
                dst_byte_off = abs_bit >> 3
                dst_bit_in_byte = abs_bit & 7

                # Clear destination bits we're about to overwrite.
                # In this byte we can fit (8 - dst_bit_in_byte) bits.
                space_lo = 8 - dst_bit_in_byte
                take = min(8, remaining)

                lo_bits = min(space_lo, take)
                lo_mask = ((1 << lo_bits) - 1)
                self.buf[dst_byte_off] &= ~(lo_mask << dst_bit_in_byte) & 0xFF
                self.buf[dst_byte_off] |= (src_byte & lo_mask) << dst_bit_in_byte
                self.buf[dst_byte_off] &= 0xFF

                if take > lo_bits:
                    # Spill into next byte.
                    hi_bits = take - lo_bits
                    hi_mask = (1 << hi_bits) - 1
                    hi_source = (src_byte >> lo_bits) & hi_mask
                    if dst_byte_off + 1 >= len(self.buf):
                        self.buf.append(0)
                    self.buf[dst_byte_off + 1] &= ~hi_mask & 0xFF
                    self.buf[dst_byte_off + 1] |= hi_source
                    self.buf[dst_byte_off + 1] &= 0xFF

                written += take

        self.cursor_bit += n_bits

    def write_u8(self, value: int) -> None:
        self.write_bits(bytes([value & 0xFF]), 8)

    def write_u16_be(self, value: int) -> None:
        self.write_bits((value & 0xFFFF).to_bytes(2, "big"), 16)

    def write_u16_le(self, value: int) -> None:
        self.write_bits((value & 0xFFFF).to_bytes(2, "little"), 16)

    def write_u32_be(self, value: int) -> None:
        self.write_bits((value & 0xFFFFFFFF).to_bytes(4, "big"), 32)

    def align_to_byte(self) -> None:
        """Round the cursor up to the next byte boundary (zero-pads).

        Matches the `if (cursor & 7 != 0) cursor = round_up + 8` pattern
        from Javelin_Carrier_WriteSystemMessage.
        """
        if self.cursor_bit & 7:
            pad = 8 - (self.cursor_bit & 7)
            self.write_bits(b"\x00", pad)

    def to_bytes(self) -> bytes:
        return bytes(self.buf[: (self.cursor_bit + 7) // 8])
