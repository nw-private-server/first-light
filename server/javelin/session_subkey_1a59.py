"""
Session subkey beacon — type 0x1a59 (W direction).

3 captures in the existing replay; **all three are 45 bytes** and
share the same payload shape, with only a 4-byte client hash and a
1-byte counter varying across messages.

This is a client-side beacon that pairs the session UUID with the
same 16-byte "session subkey" that appears at the start of `0x18a6`
(see `init_message_18a6.py`). The counter increments monotonically
across the captured copies (0x02 → 0x03 → 0x04), matching the
`0x18a6` counter pattern.

This module is now a **thin wrapper** over `subkey_beacon` — the
generic codec handles 12 W-singleton types fitting the same shape
(see `subkey_beacon.KNOWN_FAMILY`); 0x1a59 is the canonical
1-byte-trailer case where the trailer is interpreted as a u8
counter.

The 16-byte subkey is structurally identical to the first 16 bytes
of `init_message_18a6` body: the first 8 bytes are a "session
subkey upper" (`f8 cb ed 57 c6 8b 18 f4` in the captured session)
and the next 8 bytes are the lower half of the session UUID
(`bf 85 31 4b bc 4a 95 1a` — matches `session_message_a4` lower
half and `session_identity_beacon` UUID lower half).

So 0x1a59 is the W-direction "client confirms session subkey,
counter=N" beacon, paired with the R-direction `0x18a6` from the
server.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import subkey_beacon as _generic


# Canonical type-id and total wire size — public constants for callers.
TYPE_ID = 0x1a59
TOTAL_WIRE_SIZE = 45  # base 44 + 1-byte counter trailer
TRAILER_SIZE = 1

# Layout constants (preserved for backward compatibility with prior callers).
SESSION_UUID_OFFSET = _generic.SESSION_UUID_OFFSET
SESSION_UUID_SIZE = _generic.SESSION_UUID_SIZE
TYPE_HEADER_OFFSET = _generic.TYPE_HEADER_OFFSET
SUBKEY_OFFSET = _generic.SUBKEY_OFFSET
SUBKEY_SIZE = _generic.SUBKEY_SIZE
COUNTER_OFFSET = _generic.TRAILER_OFFSET

# 4-byte typed envelope header for type 0x1a59.
TYPE_HEADER = _generic.make_type_header(TYPE_ID)

# Value of the BE remaining-length field for a 45-byte 0x1a59 message.
REMAINING_LEN = TOTAL_WIRE_SIZE - 8  # 37 = 0x25


@dataclass
class SessionSubkeyBeacon1A59:
    """W-direction 0x1a59 session-subkey beacon (45 bytes total)."""

    client_hash: bytes      # 4 bytes
    session_uuid: bytes     # 16 bytes — full session UUID
    subkey: bytes           # 16 bytes — first_uuid_half + session_uuid_lower
    counter: int            # u8

    def __post_init__(self) -> None:
        if len(self.client_hash) != 4:
            raise ValueError(
                f"client_hash must be exactly 4 bytes; got {len(self.client_hash)}"
            )
        if len(self.session_uuid) != SESSION_UUID_SIZE:
            raise ValueError(
                f"session_uuid must be exactly {SESSION_UUID_SIZE} bytes; "
                f"got {len(self.session_uuid)}"
            )
        if len(self.subkey) != SUBKEY_SIZE:
            raise ValueError(
                f"subkey must be exactly {SUBKEY_SIZE} bytes; "
                f"got {len(self.subkey)}"
            )
        if not 0 <= self.counter <= 0xFF:
            raise ValueError(f"counter must fit in u8; got {self.counter}")


def encode(msg: SessionSubkeyBeacon1A59) -> bytes:
    """Build the on-wire 0x1a59 W message (45 bytes total)."""
    return _generic.encode(_generic.SubkeyBeacon(
        type_id=TYPE_ID,
        client_hash=msg.client_hash,
        session_uuid=msg.session_uuid,
        subkey=msg.subkey,
        trailer=bytes((msg.counter,)),
    ))


def decode(buf: bytes) -> SessionSubkeyBeacon1A59:
    """Parse an on-wire 0x1a59 W message. Raises on size, length-field,
    or type-header mismatch."""
    if len(buf) != TOTAL_WIRE_SIZE:
        raise ValueError(
            f"expected exactly {TOTAL_WIRE_SIZE} bytes; got {len(buf)}"
        )
    generic = _generic.decode(
        buf,
        expected_type_id=TYPE_ID,
        expected_trailer_size=TRAILER_SIZE,
    )
    return SessionSubkeyBeacon1A59(
        client_hash=generic.client_hash,
        session_uuid=generic.session_uuid,
        subkey=generic.subkey,
        counter=generic.trailer[0],
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "031e2fea"
        "00000025"
        "1a954abc4b3185bfbe37c3d8592618e0"
        "00019969"
        "f8cbed57c68b18f4bf85314bbc4a951a"
        "04"
    )
    msg = decode(captured)
    print(
        f"decoded: client_hash={msg.client_hash.hex()}, counter={msg.counter}, "
        f"subkey={msg.subkey.hex()}"
    )
    rebuilt = encode(msg)
    assert rebuilt == captured, (
        f"round-trip failed:\n  got: {rebuilt.hex()}\n  exp: {captured.hex()}"
    )
    print(f"len={len(rebuilt)} bytes — round-trip OK")
