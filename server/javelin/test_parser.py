"""
Smoke tests for the Javelin parser & marshaler.

Covers:
  - BitStream read and write (aligned + unaligned)
  - Parse synthetic records
  - Marshal synthetic records
  - Round-trip: marshal -> parse should recover original values
  - System-channel msgId-at-end semantics
  - Sequential ID optimization on both sides

Run with:
    python -m server.javelin.test_parser
"""

from __future__ import annotations

from .bitstream import BitStream, BitStreamWriter
from .frame import (
    MessageFlags,
    MessageRecord,
    ParseResult,
    marshal_datagram,
    marshal_record,
    parse_datagram,
    MarshalState,
)


# ---------------------------------------------------------------------------
#  BitStream
# ---------------------------------------------------------------------------

def test_bitstream_byte_aligned():
    s = BitStream(b"\x12\x34\x56\x78")
    assert s.read_u8() == 0x12
    assert s.read_u16_be() == 0x3456
    assert s.read_u8() == 0x78
    print("[+] test_bitstream_byte_aligned")


def test_bitstream_unaligned():
    # Verified against decompiler shift/mask pattern: 0xAB, 0xCD, skip 4, read 8 -> 0xDA
    s = BitStream(b"\xAB\xCD")
    s.read_bits(4)
    b = s.read_bits(8)
    assert b[0] == 0xDA, f"expected 0xDA, got 0x{b[0]:02x}"
    print("[+] test_bitstream_unaligned")


def test_bitstream_writer_aligned():
    w = BitStreamWriter()
    w.write_u8(0x12)
    w.write_u16_be(0x3456)
    w.write_u8(0x78)
    assert w.to_bytes() == b"\x12\x34\x56\x78"
    print("[+] test_bitstream_writer_aligned")


def test_bitstream_writer_unaligned():
    # Write 4 bits, then 8 more — the 12 bits should read back the same.
    # Note: read_bits(n) returns ceil(n/8) bytes where only the low `n%8`
    # bits of the last byte are meaningful (matches the binary's behaviour).
    w = BitStreamWriter()
    w.write_bits(b"\x0B", 4)
    w.write_bits(b"\xDA", 8)
    data = w.to_bytes()
    s = BitStream(data)
    b4 = s.read_bits(4)
    assert b4[0] & 0x0F == 0x0B, f"first 4 bits: got 0x{b4[0] & 0x0F:x}"
    b8 = s.read_bits(8)
    assert b8[0] == 0xDA, f"next 8 bits: got 0x{b8[0]:02x}"
    print("[+] test_bitstream_writer_unaligned")


# ---------------------------------------------------------------------------
#  Parse (original tests)
# ---------------------------------------------------------------------------

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
    assert len(payload) == size
    out.extend(payload)
    return bytes(out)


def test_parse_single_minimal():
    payload = b"hello!"
    buf = _build_msg_bytes(
        flags=MessageFlags.MF_DATA_CHANNEL,
        size=len(payload),
        channel=1,
        sequence=42,
        rel_seq=0,
        payload=payload,
    )
    result = parse_datagram(buf)
    assert result.error is None
    assert len(result.messages) == 1
    m = result.messages[0]
    assert m.channel == 1
    assert m.sequence == 42
    assert m.payload == payload
    print("[+] test_parse_single_minimal")


def test_parse_system_message():
    payload = b"\x00\x01\x02\x06"
    buf = _build_msg_bytes(
        flags=MessageFlags.MF_DATA_CHANNEL,
        size=len(payload),
        channel=3,
        sequence=100,
        rel_seq=0,
        payload=payload,
    )
    result = parse_datagram(buf)
    assert result.error is None
    m = result.messages[0]
    assert m.is_system
    assert m.system_msg_id == 6
    print("[+] test_parse_system_message")


def test_parse_truncated():
    buf = bytes([
        MessageFlags.MF_DATA_CHANNEL, 0x00, 0x10, 0x00,
        0x00, 0x00, 0x00, 0x00,
    ]) + b"\x00" * 4
    result = parse_datagram(buf)
    assert result.error is not None
    print(f"[+] test_parse_truncated  (error: {result.error})")


# ---------------------------------------------------------------------------
#  Marshal
# ---------------------------------------------------------------------------

def test_marshal_single():
    rec = MessageRecord(
        channel=1,
        payload=b"hello!",
        sequence=42,
        reliable_sequence=0,
        reliable=False,
        connecting=False,
    )
    data = marshal_datagram([rec])
    # First message on this channel -> channel must be written (DATA_CHANNEL set),
    # seq must be written (not sequential since no prev). Non-reliable so relseq
    # can be skipped (SEQUENTIAL_REL_ID set).
    # Expected flags: MF_DATA_CHANNEL | MF_SEQUENTIAL_REL_ID = 0x20 | 0x10 = 0x30
    assert data[0] == 0x30, f"flag byte should be 0x30, got 0x{data[0]:02x}"
    # size = 6 big-endian
    assert data[1] == 0x00 and data[2] == 0x06
    # channel byte
    assert data[3] == 0x01
    # seq 42 big-endian
    assert data[4] == 0x00 and data[5] == 0x2A
    # payload
    assert data[6:12] == b"hello!"
    print("[+] test_marshal_single")


# ---------------------------------------------------------------------------
#  Round-trip
# ---------------------------------------------------------------------------

def _assert_records_equal(a: MessageRecord, b: MessageRecord):
    assert a.channel == b.channel, f"channel {a.channel} != {b.channel}"
    assert a.payload == b.payload, "payload mismatch"
    assert a.sequence == b.sequence, f"seq {a.sequence} != {b.sequence}"
    # Reliable sequence only matters when reliable=True (matches writer logic).
    if a.reliable:
        assert a.reliable_sequence == b.reliable_sequence
    assert a.reliable == b.reliable
    assert a.connecting == b.connecting
    assert a.num_chunks == b.num_chunks


def test_roundtrip_single_record():
    records = [MessageRecord(
        channel=2, payload=b"round-trip!",
        sequence=99, reliable_sequence=7,
        reliable=True, connecting=False, num_chunks=1,
    )]
    data = marshal_datagram(records)
    result = parse_datagram(data)
    assert result.error is None
    assert len(result.messages) == 1
    _assert_records_equal(records[0], result.messages[0])
    print("[+] test_roundtrip_single_record")


def test_roundtrip_multi_with_sequential():
    records = [
        MessageRecord(channel=0, payload=b"A", sequence=10, reliable=False),
        MessageRecord(channel=0, payload=b"B", sequence=11, reliable=False),  # sequential
        MessageRecord(channel=0, payload=b"C", sequence=12, reliable=False),  # sequential
        MessageRecord(channel=0, payload=b"D", sequence=100, reliable=False),  # NOT sequential
    ]
    data = marshal_datagram(records)
    result = parse_datagram(data)
    assert result.error is None
    assert len(result.messages) == 4
    for src, out in zip(records, result.messages):
        _assert_records_equal(src, out)

    # Also verify marshaler set MF_SEQUENTIAL_ID on records 2 and 3 but not 4.
    assert not (result.messages[0].flags & MessageFlags.MF_SEQUENTIAL_ID)
    assert result.messages[1].flags & MessageFlags.MF_SEQUENTIAL_ID
    assert result.messages[2].flags & MessageFlags.MF_SEQUENTIAL_ID
    assert not (result.messages[3].flags & MessageFlags.MF_SEQUENTIAL_ID)
    print("[+] test_roundtrip_multi_with_sequential")


def test_roundtrip_channel_switch():
    records = [
        MessageRecord(channel=0, payload=b"X", sequence=1, reliable=False),
        MessageRecord(channel=0, payload=b"Y", sequence=2, reliable=False),  # inherit channel
        MessageRecord(channel=2, payload=b"Z", sequence=1, reliable=False),  # switch channel
    ]
    data = marshal_datagram(records)
    result = parse_datagram(data)
    assert result.error is None
    assert [m.channel for m in result.messages] == [0, 0, 2]
    # First msg must have MF_DATA_CHANNEL, second must NOT, third must.
    assert result.messages[0].flags & MessageFlags.MF_DATA_CHANNEL
    assert not (result.messages[1].flags & MessageFlags.MF_DATA_CHANNEL)
    assert result.messages[2].flags & MessageFlags.MF_DATA_CHANNEL
    print("[+] test_roundtrip_channel_switch")


def test_roundtrip_chunks():
    records = [MessageRecord(
        channel=1, payload=b"big" * 100,
        sequence=5, reliable_sequence=0, reliable=False,
        num_chunks=5,
    )]
    data = marshal_datagram(records)
    result = parse_datagram(data)
    assert result.error is None
    assert result.messages[0].num_chunks == 5
    assert result.messages[0].flags & MessageFlags.MF_CHUNKS
    _assert_records_equal(records[0], result.messages[0])
    print("[+] test_roundtrip_chunks")


def test_roundtrip_connecting():
    records = [MessageRecord(
        channel=3, payload=b"\x00\x01",
        sequence=0, reliable=True, reliable_sequence=1,
        connecting=True,
    )]
    data = marshal_datagram(records)
    result = parse_datagram(data)
    assert result.error is None
    assert result.messages[0].connecting
    assert result.messages[0].flags & MessageFlags.MF_CONNECTING
    _assert_records_equal(records[0], result.messages[0])
    print("[+] test_roundtrip_connecting")


def test_roundtrip_reliable_with_sequential_relseq():
    records = [
        MessageRecord(channel=0, payload=b"R1", sequence=1, reliable=True, reliable_sequence=50),
        MessageRecord(channel=0, payload=b"R2", sequence=2, reliable=True, reliable_sequence=51),  # sequential rel too
    ]
    data = marshal_datagram(records)
    result = parse_datagram(data)
    assert result.error is None
    # Second record should have MF_SEQUENTIAL_REL_ID set because rel_seq=51 = 50+1
    assert result.messages[1].flags & MessageFlags.MF_SEQUENTIAL_REL_ID
    _assert_records_equal(records[0], result.messages[0])
    _assert_records_equal(records[1], result.messages[1])
    print("[+] test_roundtrip_reliable_with_sequential_relseq")


if __name__ == "__main__":
    test_bitstream_byte_aligned()
    test_bitstream_unaligned()
    test_bitstream_writer_aligned()
    test_bitstream_writer_unaligned()
    test_parse_single_minimal()
    test_parse_system_message()
    test_parse_truncated()
    test_marshal_single()
    test_roundtrip_single_record()
    test_roundtrip_multi_with_sequential()
    test_roundtrip_channel_switch()
    test_roundtrip_chunks()
    test_roundtrip_connecting()
    test_roundtrip_reliable_with_sequential_relseq()
    print("\nAll tests passed.")
