"""Javelin protocol parser + marshaler — mirrors the binary's Carrier::ParseMessages and Carrier::WriteMessages."""

from .bitstream import BitStream, BitStreamWriter
from .frame import (
    MessageFlags,
    MessageRecord,
    ParseResult,
    SystemMessageId,
    iter_system_messages,
    marshal_datagram,
    marshal_record,
    parse_datagram,
)

__all__ = [
    "BitStream",
    "BitStreamWriter",
    "MessageFlags",
    "MessageRecord",
    "ParseResult",
    "SystemMessageId",
    "iter_system_messages",
    "marshal_datagram",
    "marshal_record",
    "parse_datagram",
]
