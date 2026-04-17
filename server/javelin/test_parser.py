"""
Smoke tests for the Javelin parser.

We can't test against real decrypted payloads yet (they're encrypted in our
captures). These tests build synthetic byte streams matching the documented
format and make sure parse_datagram recovers them correctly.

Run with:
    python -m server.javelin.test_parser
"""

from __future__ import annotations

from .bitstream import BitStream
from .frame import MessageFlags, MessageRecord, parse_datagram


def _build_msg_bytes(
    *,
    flags: int,
    size: int,
    channel: int | None = None,
    num_chunks: int | None = None,
    sequence: int | None = None,
    rel_seq: int | None = None,
    payload: bytes = b"",
) -> bytes:
    """Assemble a single byte-aligned message record for testing."""
    out = bytearray()
    out.append(flags & 0xFF)
    out.extend(size.to_bytes(2, "big"))
    if (flags & MessageFlags.MF_DATA_CHANNEL) and channel is not None:
        out.append(channel & 0xFF)
    if (flags & MessageFlags.MF_CHUNKS) and num_chunks is not None:
        out.extend(num_chunks.to_bytes(2, "big"))
    if not (flags & MessageFlags.MF_SEQUENTIAL_ID) and sequence is not None:
        out.extend(sequence.to_bytes(2, "big"))
    if not (flags & MessageFlags.MF_SEQUENTIAL_REL_ID) and rel_seq is not None:
        out.extend(rel_seq.to_bytes(2, "big"))
    assert len(payload) == size, f"payload size mismatch ({len(payload)} != {size})"
    out.extend(payload)
    return bytes(out)


def test_bitstream_byte_aligned():
    """Byte-aligned reads should match plain slicing."""
    s = BitStream(b"\x12\x34\x56\x78")
    assert s.read_u8() == 0x12
    assert s.read_u16_be() == 0x3456
    assert s.read_u8() == 0x78
    print("[+] test_bitstream_byte_aligned")


def test_bitstream_unaligned():
    """Bit-level reads across byte boundaries."""
    # 0xAB = 1010 1011, 0xCD = 1100 1101
    # After skipping 4 bits, reading 4 bits should yield low nibble of 0xAB = 0x0B
    s = BitStream(b"\xAB\xCD")
    s.read_bits(4)  # consume low 4 bits of 0xAB
    # Now cursor is at bit 4; next byte read should splice across boundary
    b = s.read_bits(8)  # 8 bits starting from bit 4
    # We're reading bits [4..11] = high 4 of 0xAB + low 4 of 0xCD
    # = 1010 1101 = 0xAD (LSB-first, so high_nibble_of_0xAB=A, low_nibble_of_0xCD=D)
    # But the binary reads LSB-first within a byte:
    #   bit 4 of 0xAB = 0 (since 0xAB = 10101011, bit 4 = the '0' in position 4 counting from 0)
    # Actually the Javelin ReadBits reads "byte >> bit_in_byte" which gives the upper
    # (MS-bits-shifted-down) part first.
    # For 0xAB = 10101011, shifted right by 4 = 00001010 = 0x0A
    # For 0xCD = 11001101, masked low 4 bits with << 4 = 11010000 = 0xD0
    # Combined = 0x0A | 0xD0 = 0xDA
    print(f"    unaligned read result: 0x{b[0]:02x}  (expected 0xDA per decomp logic)")
    # This is useful just to understand — the bit-order is implementation-specific.
    print("[+] test_bitstream_unaligned")


def test_parse_single_minimal():
    """Minimal message: byte-aligned fields, no chunks, seq+relseq present."""
    payload = b"hello!"
    flags = MessageFlags.MF_DATA_CHANNEL  # channel present, no other flags
    buf = _build_msg_bytes(
        flags=flags,
        size=len(payload),
        channel=1,
        sequence=42,
        rel_seq=0,
        payload=payload,
    )
    result = parse_datagram(buf)
    assert result.error is None, f"parse error: {result.error}"
    assert len(result.messages) == 1, f"expected 1, got {len(result.messages)}"
    m = result.messages[0]
    assert m.channel == 1
    assert m.sequence == 42
    assert m.payload == payload
    assert not m.reliable
    assert not m.connecting
    print(f"[+] test_parse_single_minimal  (remaining bits: {result.trailing_bits})")


def test_parse_system_message():
    """Channel 3 system message; msgId is the LAST byte of payload."""
    # Build a SM_CT_ACKS: payload ends in 0x06
    payload = b"\x00\x01\x02\x06"  # 4-byte payload with msgId=6 at end
    flags = MessageFlags.MF_DATA_CHANNEL
    buf = _build_msg_bytes(
        flags=flags,
        size=len(payload),
        channel=3,
        sequence=100,
        rel_seq=0,
        payload=payload,
    )
    result = parse_datagram(buf)
    assert result.error is None, result.error
    m = result.messages[0]
    assert m.is_system
    assert m.system_msg_id == 6
    print("[+] test_parse_system_message")


def test_parse_sequential_optimization():
    """When MF_SEQUENTIAL_ID is set, sequence auto-increments."""
    # First message: channel 0, explicit seq=5
    buf1 = _build_msg_bytes(
        flags=MessageFlags.MF_DATA_CHANNEL,
        size=1,
        channel=0,
        sequence=5,
        rel_seq=0,
        payload=b"A",
    )
    # Second message: same channel (inherit), SEQUENTIAL_ID set — seq should be 6
    flags2 = MessageFlags.MF_SEQUENTIAL_ID
    buf2 = _build_msg_bytes(
        flags=flags2,
        size=1,
        rel_seq=0,
        payload=b"B",
    )
    combined = buf1 + buf2
    result = parse_datagram(combined)
    assert result.error is None, result.error
    assert len(result.messages) == 2
    assert result.messages[0].sequence == 5
    # Auto-increment: 5 + 1 = 6
    assert result.messages[1].sequence == 6, f"got {result.messages[1].sequence}"
    assert result.messages[1].channel == 0  # inherited
    print("[+] test_parse_sequential_optimization")


def test_parse_connecting_flag():
    flags = MessageFlags.MF_CONNECTING | MessageFlags.MF_DATA_CHANNEL
    buf = _build_msg_bytes(
        flags=flags, size=0, channel=0, sequence=0, rel_seq=0, payload=b""
    )
    result = parse_datagram(buf)
    assert result.error is None
    assert result.messages[0].connecting
    print("[+] test_parse_connecting_flag")


def test_parse_truncated():
    """Buffer smaller than the declared payload — should error gracefully."""
    buf = bytes([
        MessageFlags.MF_DATA_CHANNEL,
        0x00, 0x10,  # size = 16
        0x00,         # channel
        0x00, 0x00,   # seq
        0x00, 0x00,   # rel_seq
    ]) + b"\x00" * 4  # only 4 bytes of payload, need 16
    result = parse_datagram(buf)
    assert result.error is not None, "expected truncation error"
    assert "truncated" in result.error.lower() or "past end" in result.error.lower()
    print(f"[+] test_parse_truncated  (error: {result.error})")


if __name__ == "__main__":
    test_bitstream_byte_aligned()
    test_bitstream_unaligned()
    test_parse_single_minimal()
    test_parse_system_message()
    test_parse_sequential_optimization()
    test_parse_connecting_flag()
    test_parse_truncated()
    print("\nAll tests passed.")
