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
    # 2026-05-04: Originally thought reserved/unused. Per the captured V3
    # RegistrationRequest record (analysis/v3_request/HEADER_DECODE.md), bit
    # 0x40 means "no message-length field — payload extends to end of
    # datagram". Set on the V3 data-channel record (flag=0xe0/0xf0).
    MF_NO_LENGTH = 0x40
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
    # Optional: override the writer's computed flag byte with this value.
    # Use only when the canonical wire flag differs from what the auto-computer
    # would derive (e.g. piggyback ACK records that need MF_SEQUENTIAL_REL_ID
    # set even for non-reliable).
    flags_override: Optional[int] = None

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
    """Outcome of parsing a Javelin datagram body.

    `messages` is the list of decoded records (empty if parsing
    aborted). `error` is a short string describing the failure
    when parsing fails partway through; `None` on success.
    `trailing_bits` is the count of bits left over in the bitstream
    after the last record — a healthy datagram has 0 trailing bits.
    """
    messages: List[MessageRecord] = field(default_factory=list)
    error: Optional[str] = None
    trailing_bits: int = 0


@dataclass
class CarrierEnvelope:
    # Per Mixed Nuts' Wireshark dissector: byte 0 is the "Compression Flag".
    # Bit 7 (0x80) is the always-on Carrier protocol marker. Bit 0 (0x01)
    # signals the body is LZ4-compressed. (We previously assumed bit 0 was
    # an encryption marker — wrong; encryption is implicit DTLS-layer.)
    type_byte: int
    proto: int
    sequence: int

    @property
    def is_compressed(self) -> bool:
        return bool(self.type_byte & 1)

    # Back-compat alias so existing callers don't break. The semantic is wrong
    # (it's compression, not encryption) but the wire bit is the same.
    @property
    def is_encrypted(self) -> bool:
        return self.is_compressed


def parse_envelope(data: bytes) -> tuple[CarrierEnvelope, bytes]:
    """Strip and return the 4-byte Carrier envelope; returns (envelope, body).
    Raises ValueError if the envelope doesn't match the expected magic.

    Envelope (4 bytes):
      byte 0: Compression Flag — 0x80 (uncompressed) or 0x81 (LZ4 compressed)
      byte 1: Protocol ID — always 0x01
      bytes 2-3: Datagram Sequence (BE u16)
    """
    if len(data) < 4:
        raise ValueError(f"datagram too short ({len(data)} bytes) for envelope")
    type_byte = data[0]
    proto = data[1]
    # Bit 7 always set; only bit 0 (compression) varies. Other bits unused.
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
            # 2026-05-04: MF_NO_LENGTH (0x40) records use a different layout:
            #   [flags][3-byte sub-header][channel][seq][rel_seq][payload..end]
            # When the 0x10 bit is ALSO set (first-attempt connect form, flag
            # 0xf0), the sub-header is 4 bytes and there is an extra 5-byte
            # CONNECT-INIT blob between rel_seq and the payload. Per
            # analysis/v3_request/HEADER_DECODE.md.
            size = stream.read_u16_be()
            no_length = bool(flags & MessageFlags.MF_NO_LENGTH)
            first_attempt = no_length and bool(flags & MessageFlags.MF_SEQUENTIAL_REL_ID)
            if no_length:
                # 3-byte sub-header normally, 4-byte for first-attempt form.
                stream.read_u8()
                if first_attempt:
                    stream.read_u8()

            reliable = bool(flags & MessageFlags.MF_RELIABLE)
            connecting = bool(flags & MessageFlags.MF_CONNECTING)

            if flags & MessageFlags.MF_DATA_CHANNEL:
                channel = stream.read_u8()
            else:
                channel = prev_channel
            if channel > 4:
                # Per community dump: per-channel counters for ch0/1/3/4
                # documented (no 2). Max 4. Was max 3 — bumped 2026-05-04
                # because we may need to send V3 response on ch=4.
                result.error = f"invalid channel {channel} (max 4)"
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

            if no_length:
                # MF_NO_LENGTH: payload runs to end of datagram. Single
                # such record per datagram in practice.
                n_payload_bits = stream.remaining()
            else:
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

    # Build flag byte (or honour an explicit override).
    if rec.flags_override is not None:
        flags = rec.flags_override
        # Re-derive the booleans from the override so emit decisions stay
        # consistent with the actual flag value on the wire.
        is_seq_sequential = bool(flags & MessageFlags.MF_SEQUENTIAL_ID)
        is_relseq_sequential = bool(flags & MessageFlags.MF_SEQUENTIAL_REL_ID)
        channel_changed = bool(flags & MessageFlags.MF_DATA_CHANNEL)
    else:
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
