"""
Javelin per-message framing — mirrors `Javelin_Carrier_ParseMessages`
(read side, NewWorld.exe @ 0x140f77eb0) and `Javelin_Carrier_WriteMessages`
(write side, @ 0x140f65b20).

Each post-DTLS datagram has a 4-byte Carrier envelope:

    type   : u8       0x80 = plaintext records, 0x81 = encrypted/compressed
                      (bit 0 selects cipher/compressor path; bits 1-6 must be 0;
                       high bit must be set — verified at FUN_140f898e0+0x4a3)
    proto  : u8       must be 0x01 (verified at FUN_140f898e0+0x4f0)
    seq    : u16 BE   per-datagram sequence number

After the envelope (and after optional cipher/decompress) is a stream of
1..N MessageRecords. Each record is framed via a compact bit-packed header:

    flags    : u8  bit-packed  (see MessageFlags)
    size     : u16 big-endian  (payload size in bytes)
    channel  : u8  present only when MF_DATA_CHANNEL is set
    numChunks: u16 present only when MF_CHUNKS is set (implicit 1)
    sequence : u16 present only when MF_SEQUENTIAL_ID is CLEAR
                  (set ⇒ auto-increment per channel)
    relSeq   : u16 present only when MF_SEQUENTIAL_REL_ID is CLEAR
                  (set ⇒ auto-increment per channel when reliable)
    payload  : size bytes

System messages (channel 3) place the 1-byte msgId at the END of the
payload, not the start.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Iterator, List, Optional

from .bitstream import BitStream, BitStreamError, BitStreamWriter


class MessageFlags(enum.IntFlag):
    MF_RELIABLE = 0x01
    # 0x02 reserved / unused in Javelin
    MF_CHUNKS = 0x04
    MF_SEQUENTIAL_ID = 0x08
    MF_SEQUENTIAL_REL_ID = 0x10
    MF_DATA_CHANNEL = 0x20
    # 0x40 reserved / unused in Javelin
    MF_CONNECTING = 0x80


class SystemMessageId(enum.IntEnum):
    SM_CONNECT_REQUEST = 1
    SM_CONNECT_ACK = 2
    SM_DISCONNECT = 3
    SM_CLOCK_SYNC = 4
    SM_CT_FIRST = 5
    SM_CT_ACKS = 6
    SM_CT_CONN_CONTROL = 7
    SM_CT_BANDWIDTH = 8


@dataclass
class MessageRecord:
    """One parsed/marshaled message record. Mirrors the 0x38-byte
    in-memory struct the binary uses inside Carrier::Parse/WriteMessages."""

    channel: int
    payload: bytes
    sequence: int = 0
    reliable_sequence: int = 0
    reliable: bool = False
    connecting: bool = False
    num_chunks: int = 1
    # Filled by the parser; ignored by the writer.
    flags: int = 0

    @property
    def size(self) -> int:
        return len(self.payload)

    @property
    def is_system(self) -> bool:
        return self.channel == 3

    @property
    def system_msg_id(self) -> Optional[int]:
        """For channel-3 messages, msgId is the LAST byte of payload."""
        if not self.is_system or not self.payload:
            return None
        return self.payload[-1]


# ---------------------------------------------------------------------------
#  Parser (inverse of Javelin_Carrier_WriteMessages)
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    messages: List[MessageRecord] = field(default_factory=list)
    error: Optional[str] = None
    trailing_bits: int = 0


@dataclass
class CarrierEnvelope:
    type_byte: int
    proto: int
    sequence: int

    @property
    def is_encrypted(self) -> bool:
        return bool(self.type_byte & 1)


def parse_envelope(data: bytes) -> tuple[CarrierEnvelope, bytes]:
    """Strip and return the 4-byte Carrier envelope; returns (envelope, body).
    Raises ValueError if the envelope doesn't match the expected magic."""
    if len(data) < 4:
        raise ValueError(f"datagram too short ({len(data)} bytes) for envelope")
    type_byte = data[0]
    proto = data[1]
    if not (type_byte & 0x80) or (type_byte & 0x7e):
        raise ValueError(f"bad envelope type byte 0x{type_byte:02x}")
    if proto != 0x01:
        raise ValueError(f"bad envelope proto byte 0x{proto:02x} (expected 0x01)")
    seq = (data[2] << 8) | data[3]
    return CarrierEnvelope(type_byte=type_byte, proto=proto, sequence=seq), data[4:]


def parse_datagram(data: bytes, *, start_bit: int = 0) -> ParseResult:
    """Parse a decrypted Javelin datagram payload into MessageRecords.

    Note: pass the body AFTER `parse_envelope` has stripped the 4-byte
    Carrier header. This function only handles the inner record stream.
    """
    stream = BitStream(data, start_bit=start_bit)
    result = ParseResult()

    prev_channel = 0
    per_channel_seq = [0, 0, 0, 0]
    per_channel_rel_seq = [0, 0, 0, 0]

    while stream.remaining() > 0:
        try:
            flags = stream.read_u8()
            size = stream.read_u16_be()

            reliable = bool(flags & MessageFlags.MF_RELIABLE)
            connecting = bool(flags & MessageFlags.MF_CONNECTING)

            if flags & MessageFlags.MF_DATA_CHANNEL:
                channel = stream.read_u8()
            else:
                channel = prev_channel
            if channel > 3:
                result.error = f"invalid channel {channel} (max 3)"
                return result
            prev_channel = channel

            if flags & MessageFlags.MF_CHUNKS:
                num_chunks = stream.read_u16_be()
            else:
                num_chunks = 1

            if not (flags & MessageFlags.MF_SEQUENTIAL_ID):
                sequence = stream.read_u16_be()
                per_channel_seq[channel] = sequence
            else:
                per_channel_seq[channel] = (per_channel_seq[channel] + 1) & 0xFFFF
                sequence = per_channel_seq[channel]

            if not (flags & MessageFlags.MF_SEQUENTIAL_REL_ID):
                rel_seq = stream.read_u16_be()
                per_channel_rel_seq[channel] = rel_seq
            elif reliable:
                per_channel_rel_seq[channel] = (per_channel_rel_seq[channel] + 1) & 0xFFFF
                rel_seq = per_channel_rel_seq[channel]
            else:
                rel_seq = per_channel_rel_seq[channel]

            n_payload_bits = size * 8
            if n_payload_bits > stream.remaining():
                result.error = (
                    f"payload truncated: need {n_payload_bits} bits, "
                    f"have {stream.remaining()}"
                )
                return result

            payload = stream.read_bits(n_payload_bits)

            result.messages.append(
                MessageRecord(
                    flags=flags,
                    channel=channel,
                    sequence=sequence,
                    reliable_sequence=rel_seq,
                    reliable=reliable,
                    connecting=connecting,
                    num_chunks=num_chunks,
                    payload=payload,
                )
            )

        except BitStreamError as e:
            result.error = str(e)
            break

    result.trailing_bits = stream.remaining()
    return result


# ---------------------------------------------------------------------------
#  Marshaler (mirrors Javelin_Carrier_WriteMessages)
# ---------------------------------------------------------------------------

@dataclass
class MarshalState:
    """Per-datagram state carried across messages in the same datagram.

    Mirrors the cross-message state kept by Carrier::WriteMessages:
      - prev_channel:  last channel written (to decide if MF_DATA_CHANNEL is needed)
      - last_seq[c]:   last sequence number written on each channel (for MF_SEQUENTIAL_ID)
      - last_rel_seq[c]: same for reliable sequence
      - has_written[c]: whether any message has been written on this channel yet
                       (first message ever can't be "sequential")
    """
    prev_channel: int = -1  # -1 = never written
    last_seq: List[int] = field(default_factory=lambda: [0, 0, 0, 0])
    last_rel_seq: List[int] = field(default_factory=lambda: [0, 0, 0, 0])
    has_written: List[bool] = field(default_factory=lambda: [False] * 4)


def marshal_record(
    writer: BitStreamWriter,
    rec: MessageRecord,
    state: MarshalState,
) -> None:
    """Serialize one MessageRecord into `writer`, updating `state`.

    The flags byte is computed by comparing with the previous state. This
    is exactly what Carrier::WriteMessages does.
    """
    if rec.channel not in (0, 1, 2, 3):
        raise ValueError(f"invalid channel {rec.channel} (must be 0..3)")

    c = rec.channel

    # Compute "can we skip the sequence field?"
    # Writer optimization: if this msg's seq == last_seq + 1 (with u16 wrap),
    # mark it as sequential and omit the field.
    is_seq_sequential = (
        state.has_written[c]
        and ((state.last_seq[c] + 1) & 0xFFFF) == rec.sequence
    )
    is_relseq_sequential = (
        state.has_written[c]
        and rec.reliable
        and ((state.last_rel_seq[c] + 1) & 0xFFFF) == rec.reliable_sequence
    )
    # 2026-05-04: Mixed Nuts confirmed correct flag byte for our outgoing
    # post-DTLS records is 0x20 (MF_DATA_CHANNEL only). Previously we
    # auto-set MF_SEQUENTIAL_REL_ID for non-reliable records to save the
    # rel_seq u16. That made our flag byte 0xb0 (with MF_CONNECTING). The
    # canonical writer ALWAYS writes the rel_seq field, even for non-reliable
    # records (the reader ignores it when reliable=false). Remove the
    # bandwidth optimization so our flag matches the wire-correct 0x20.

    channel_changed = (state.prev_channel != c)

    # Build flag byte.
    flags = 0
    if rec.reliable:
        flags |= MessageFlags.MF_RELIABLE
    if rec.num_chunks > 1:
        flags |= MessageFlags.MF_CHUNKS
    if is_seq_sequential:
        flags |= MessageFlags.MF_SEQUENTIAL_ID
    if is_relseq_sequential:
        flags |= MessageFlags.MF_SEQUENTIAL_REL_ID
    if channel_changed:
        flags |= MessageFlags.MF_DATA_CHANNEL
    if rec.connecting:
        flags |= MessageFlags.MF_CONNECTING

    # Emit fields in the canonical order.
    writer.write_u8(flags)
    writer.write_u16_be(rec.size)
    if channel_changed:
        writer.write_u8(c)
    if rec.num_chunks > 1:
        writer.write_u16_be(rec.num_chunks)
    if not is_seq_sequential:
        writer.write_u16_be(rec.sequence & 0xFFFF)
    if not is_relseq_sequential:
        writer.write_u16_be(rec.reliable_sequence & 0xFFFF)
    writer.write_bits(rec.payload, rec.size * 8)

    # Update state.
    state.prev_channel = c
    state.last_seq[c] = rec.sequence & 0xFFFF
    if rec.reliable:
        state.last_rel_seq[c] = rec.reliable_sequence & 0xFFFF
    state.has_written[c] = True


def marshal_datagram(records: List[MessageRecord]) -> bytes:
    """Marshal a list of MessageRecords into a single datagram payload."""
    writer = BitStreamWriter()
    state = MarshalState()
    for rec in records:
        marshal_record(writer, rec, state)
    return writer.to_bytes()


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def iter_system_messages(result: ParseResult) -> Iterator[tuple[SystemMessageId, MessageRecord]]:
    """Yield (msg_id, record) pairs for system-channel messages."""
    for rec in result.messages:
        if rec.is_system:
            mid = rec.system_msg_id
            if mid is None:
                continue
            try:
                yield SystemMessageId(mid), rec
            except ValueError:
                pass
