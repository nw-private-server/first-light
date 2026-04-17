"""
Javelin per-message framing — mirrors `Javelin_Carrier_ParseMessages`
(NewWorld.exe @ 0x140f77eb0).

Every datagram (after DTLS decrypt) is a stream of 1..N message records.
Each record is:

    flags  : u8  bit-packed  (see MessageFlags)
    size   : u16 big-endian  (payload size — units TBD, measured in...
                              probably bytes, possibly bits)
    channel: u8  (only if MF_DATA_CHANNEL set, else inherit previous)
    numChunks: u16 (only if MF_CHUNKS, else 1)
    sequence : u16 (only if !MF_SQUENTIAL_ID, else auto-increment)
    relSeq   : u16 (only if !MF_SQUENTIAL_REL_ID, else auto if reliable)
    payload  : size bytes

System messages (channel 3) place the msgId BYTE at the END of the
payload (not the start).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Iterator, List, Optional

from .bitstream import BitStream, BitStreamError


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
    SM_CT_FIRST = 5  # sentinel
    SM_CT_ACKS = 6
    SM_CT_CONN_CONTROL = 7
    SM_CT_BANDWIDTH = 8


@dataclass
class MessageRecord:
    """One parsed message record. Mirrors the 0x38-byte struct the
    binary builds inside Javelin_Carrier_ParseMessages."""

    flags: int
    channel: int
    size: int
    num_chunks: int
    sequence: int
    reliable_sequence: int
    reliable: bool
    connecting: bool
    payload: bytes

    @property
    def is_system(self) -> bool:
        return self.channel == 3

    @property
    def system_msg_id(self) -> Optional[int]:
        """For channel-3 messages, the msgId byte lives at the END of
        the payload."""
        if not self.is_system or not self.payload:
            return None
        return self.payload[-1]


@dataclass
class ParseResult:
    messages: List[MessageRecord] = field(default_factory=list)
    error: Optional[str] = None
    trailing_bits: int = 0  # bits left in stream at EOF


def parse_datagram(
    data: bytes,
    *,
    start_bit: int = 0,
    size_unit_bits: bool = False,
) -> ParseResult:
    """Parse a decrypted Javelin datagram payload.

    Args:
        data: The plaintext bytes (post-DTLS).
        start_bit: Where in the first byte the stream starts. 0 for normal
                   datagrams. Non-zero if the caller has already consumed
                   a flag byte and wants to continue from the next bit.
        size_unit_bits: If True, interpret the `size` field as bits.
                        Decompilation suggests size is in a unit where
                        payload advances via `cursor += size * 8` — so
                        `size` is expressed in bytes. Default False
                        matches that.

    Returns:
        ParseResult with parsed messages and any error state.
    """

    stream = BitStream(data, start_bit=start_bit)
    result = ParseResult()

    # Carry-over state between messages (inherit channel; auto-increment
    # sequence numbers when the flag-skipped optimization is used).
    prev_channel = 0
    per_channel_seq = [0, 0, 0, 0]
    per_channel_rel_seq = [0, 0, 0, 0]

    while stream.remaining() > 0:
        try:
            flags = stream.read_u8()
            size = stream.read_u16_be()  # payload size (bytes)

            reliable = bool(flags & MessageFlags.MF_RELIABLE)
            connecting = bool(flags & MessageFlags.MF_CONNECTING)

            # Channel
            if flags & MessageFlags.MF_DATA_CHANNEL:
                channel = stream.read_u8()
            else:
                channel = prev_channel
            if channel > 3:
                result.error = f"invalid channel {channel} (max 3)"
                return result
            prev_channel = channel

            # Chunks
            if flags & MessageFlags.MF_CHUNKS:
                num_chunks = stream.read_u16_be()
            else:
                num_chunks = 1

            # Sequence number
            if not (flags & MessageFlags.MF_SEQUENTIAL_ID):
                sequence = stream.read_u16_be()
                per_channel_seq[channel] = sequence
            else:
                per_channel_seq[channel] = (per_channel_seq[channel] + 1) & 0xFFFF
                sequence = per_channel_seq[channel]

            # Reliable sequence
            if not (flags & MessageFlags.MF_SEQUENTIAL_REL_ID):
                rel_seq = stream.read_u16_be()
                per_channel_rel_seq[channel] = rel_seq
            elif reliable:
                per_channel_rel_seq[channel] = (per_channel_rel_seq[channel] + 1) & 0xFFFF
                rel_seq = per_channel_rel_seq[channel]
            else:
                rel_seq = per_channel_rel_seq[channel]

            # Payload: size bytes (8 bits each)
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
                    size=size,
                    num_chunks=num_chunks,
                    sequence=sequence,
                    reliable_sequence=rel_seq,
                    reliable=reliable,
                    connecting=connecting,
                    payload=payload,
                )
            )

        except BitStreamError as e:
            result.error = str(e)
            break

    result.trailing_bits = stream.remaining()
    return result


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
                pass  # unknown system msg id
