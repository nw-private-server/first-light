"""
Action history beacon — type 0x635 (W direction).

5 captures in the existing replay (seq 0x6e..0x72), all sharing the
same session UUID, second_id, and constant prefix; differing only
in counter and the trailing list of "history records".

Structurally this looks like a **client input/action queue** — each
new message increments a u8 counter and appends another 15-byte
record at the tail, while keeping the older records intact. So the
client is re-broadcasting unacknowledged actions until the server
acks them.

Across the 5 captures:
- seq 0x6e: counter=1, 0 history records  → 93 bytes total
- seq 0x6f: counter=2, 1 history record   → 108 bytes
- seq 0x70: counter=3, 2 history records  → 123 bytes
- seq 0x71: counter=4, 3 history records  → 138 bytes
- seq 0x72: counter=5, 4 history records  → 153 bytes

Each new message adds exactly **15 bytes** at the tail.

Wire layout (full W-direction message; total = 93 + 15*history_count):

  +0x00  u8x4    client_hash       per-message correlation/hash
  +0x04  u32 BE  remaining_len     total - 8
  +0x08  u8x16   session_uuid      full session UUID
  +0x18  u8x4    type_header       [00 01 b5 18] = type 0x635
  +0x1c  u8x8    second_id         e.g. `fb de 4b 9a 60 0d 42 8f`
                                    in the captured session
  +0x24  u8x8    session_uuid_lower  matches lower 8 of session_uuid
  +0x2c  u8x4    first_send_flag   `00 01 00 00` only on the first
                                    message of this type-stream;
                                    `00 00 00 00` thereafter
  +0x30  u8x4    const_a           `91 02 06 00`
  +0x34  u8x12   const_b           `00 01 01 00 00 00 00 00 00 00 00 01`
  +0x40  u8x4    second_id_b       `20 07 19 4b` (constant in this
                                    capture; possibly another sub-id)
  +0x44  u8x6    const_c           `00 00 00 ac 0f 01`
  +0x4a  u8      counter_u8        1, 2, 3, ...
  +0x4b  u8      const_d           `01`
  +0x4c  u32 BE  counter_u32       always equals counter_u8
  +0x50  u8x13   trailer           `c0 80 20 00 80 80 80 80
                                     03 00 00 00 01`
                                    (constant in all 5 captures —
                                    "fixed footer" or "current state")
  +0x5d  N x 15-byte history       0..N records in DESCENDING
          records                    counter order. Each record:
                                       u8x4    `00 00 00 00`
                                       u8      record_counter (u8)
                                       u8      `00`
                                       u8x4    `80 80 80 80`
                                       u8x5    `03 00 00 00 01`
                                    (4+1+1+4+5 = 15 bytes)

The history record values are derivable from the counter: a message
with counter=N carries records for counters N-1, N-2, ..., 1 (each
in the same fixed shape, only the `record_counter` u8 differs).

This codec models the **structure** but does NOT attempt to interpret
the action / state payloads — the constant blocks could carry input
flags, ability cooldowns, etc., that we'd need handler-side static-RE
or live captures to disambiguate. The trailer `c0 80 20 00 ...` and
the per-record `80 80 80 80 03 00 00 00 01` patterns are clearly
NOT random noise — they look like serialized state values — but
without semantic context we treat them as constants the captured
session happened to use.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


# Sizes
SECOND_ID_SIZE = 8
SESSION_UUID_SIZE = 16
SESSION_UUID_LOWER_SIZE = 8
HEADER_AREA_SIZE = 28  # client_hash + remaining_len + session_uuid + type_hdr
FIXED_BODY_SIZE = 65   # body up to and including the 13-byte trailer
HISTORY_RECORD_SIZE = 15
MIN_TOTAL_WIRE_SIZE = HEADER_AREA_SIZE + FIXED_BODY_SIZE  # 93

# 4-byte typed envelope header for type 0x635:
#   marker [0x00, 0x01], then ((0x635 & 0x3f) | 0x80) = 0xb5,
#   then ((0x635 >> 6) & 0xff) = 0x18
TYPE_HEADER = bytes((0x00, 0x01, 0xb5, 0x18))

# Captured constants (see module docstring for offsets).
DEFAULT_CONST_A = bytes.fromhex("91020600")
DEFAULT_CONST_B = bytes.fromhex("000101000000000000000001")
DEFAULT_SECOND_ID_B = bytes.fromhex("2007194b")
DEFAULT_CONST_C = bytes.fromhex("000000ac0f01")
DEFAULT_CONST_D = 0x01
DEFAULT_TRAILER = bytes.fromhex("c08020008080808003000000 01".replace(" ", ""))
assert len(DEFAULT_TRAILER) == 13, f"trailer is {len(DEFAULT_TRAILER)} bytes"

# Fixed shape of a 15-byte history record:
#   [00 00 00 00][record_counter:u8][00][80 80 80 80][03 00 00 00 01]
HISTORY_RECORD_PREFIX = bytes.fromhex("00000000")  # 4 bytes
HISTORY_RECORD_INFIX = bytes.fromhex("00")          # 1 byte
HISTORY_RECORD_TAIL = bytes.fromhex("80808080" "0300000001")  # 9 bytes


def _pack_history_record(record_counter: int) -> bytes:
    if not 0 <= record_counter <= 0xFF:
        raise ValueError(
            f"history record_counter must fit in u8; got {record_counter}"
        )
    return (
        HISTORY_RECORD_PREFIX
        + bytes((record_counter,))
        + HISTORY_RECORD_INFIX
        + HISTORY_RECORD_TAIL
    )


def _unpack_history_record(buf: bytes) -> int:
    """Return the record_counter from a 15-byte history record buffer.
    Raises if any constant slot doesn't match its captured value."""
    if len(buf) != HISTORY_RECORD_SIZE:
        raise ValueError(
            f"history record must be exactly {HISTORY_RECORD_SIZE} bytes; "
            f"got {len(buf)}"
        )
    if buf[0:4] != HISTORY_RECORD_PREFIX:
        raise ValueError(
            f"history record prefix mismatch: expected "
            f"{HISTORY_RECORD_PREFIX.hex()}, got {buf[0:4].hex()}"
        )
    record_counter = buf[4]
    if buf[5:6] != HISTORY_RECORD_INFIX:
        raise ValueError(
            f"history record infix mismatch: expected "
            f"{HISTORY_RECORD_INFIX.hex()}, got {buf[5:6].hex()}"
        )
    if buf[6:15] != HISTORY_RECORD_TAIL:
        raise ValueError(
            f"history record tail mismatch: expected "
            f"{HISTORY_RECORD_TAIL.hex()}, got {buf[6:15].hex()}"
        )
    return record_counter


@dataclass
class ActionHistory635:
    """W-direction 0x635 action-history beacon (variable size)."""

    client_hash: bytes              # 4 bytes
    session_uuid: bytes             # 16 bytes — full session UUID
    second_id: bytes                # 8 bytes — first identity
    session_uuid_lower: bytes       # 8 bytes — lower half of session UUID
    counter: int                    # u8 (also written as u32 LE)
    first_send: bool = False        # if True, sets the +0x2c flag word
    history_counters: tuple[int, ...] = ()  # descending counters; default is
                                            # (counter-1, counter-2, ..., 1)
    const_a: bytes = DEFAULT_CONST_A
    const_b: bytes = DEFAULT_CONST_B
    second_id_b: bytes = DEFAULT_SECOND_ID_B
    const_c: bytes = DEFAULT_CONST_C
    const_d: int = DEFAULT_CONST_D
    trailer: bytes = DEFAULT_TRAILER

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
        if len(self.second_id) != SECOND_ID_SIZE:
            raise ValueError(
                f"second_id must be exactly {SECOND_ID_SIZE} bytes; "
                f"got {len(self.second_id)}"
            )
        if len(self.session_uuid_lower) != SESSION_UUID_LOWER_SIZE:
            raise ValueError(
                f"session_uuid_lower must be exactly "
                f"{SESSION_UUID_LOWER_SIZE} bytes; got "
                f"{len(self.session_uuid_lower)}"
            )
        if not 0 <= self.counter <= 0xFF:
            raise ValueError(f"counter must fit in u8; got {self.counter}")
        if len(self.const_a) != 4:
            raise ValueError(f"const_a must be 4 bytes; got {len(self.const_a)}")
        if len(self.const_b) != 12:
            raise ValueError(f"const_b must be 12 bytes; got {len(self.const_b)}")
        if len(self.second_id_b) != 4:
            raise ValueError(
                f"second_id_b must be 4 bytes; got {len(self.second_id_b)}"
            )
        if len(self.const_c) != 6:
            raise ValueError(f"const_c must be 6 bytes; got {len(self.const_c)}")
        if not 0 <= self.const_d <= 0xFF:
            raise ValueError(
                f"const_d must fit in u8; got {self.const_d}"
            )
        if len(self.trailer) != 13:
            raise ValueError(
                f"trailer must be 13 bytes; got {len(self.trailer)}"
            )
        for i, c in enumerate(self.history_counters):
            if not 0 <= c <= 0xFF:
                raise ValueError(
                    f"history_counters[{i}] must fit in u8; got {c}"
                )


def encode(msg: ActionHistory635) -> bytes:
    """Build the on-wire 0x635 W message. If `history_counters` is empty
    AND counter > 1, encodes the implicit default (counter-1, ..., 1)."""
    if not msg.history_counters and msg.counter > 1:
        history = tuple(range(msg.counter - 1, 0, -1))
    else:
        history = msg.history_counters

    body = (
        msg.second_id
        + msg.session_uuid_lower
        + (b"\x00\x01\x00\x00" if msg.first_send else b"\x00\x00\x00\x00")
        + msg.const_a
        + msg.const_b
        + msg.second_id_b
        + msg.const_c
        + bytes((msg.counter,))
        + bytes((msg.const_d,))
        + struct.pack(">I", msg.counter)
        + msg.trailer
        + b"".join(_pack_history_record(c) for c in history)
    )
    remaining_len = SESSION_UUID_SIZE + 4 + len(body)
    return (
        msg.client_hash
        + struct.pack(">I", remaining_len)
        + msg.session_uuid
        + TYPE_HEADER
        + body
    )


def decode(buf: bytes) -> ActionHistory635:
    """Parse an on-wire 0x635 W message."""
    if len(buf) < MIN_TOTAL_WIRE_SIZE:
        raise ValueError(
            f"buffer too short: need at least {MIN_TOTAL_WIRE_SIZE} bytes; "
            f"got {len(buf)}"
        )
    client_hash = buf[0:4]
    (remaining,) = struct.unpack_from(">I", buf, 4)
    expected_remaining = len(buf) - 8
    if remaining != expected_remaining:
        raise ValueError(
            f"remaining-length field mismatch: expected 0x{expected_remaining:x}, "
            f"got 0x{remaining:x}"
        )
    session_uuid = buf[8:24]
    if buf[24:28] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[24:28].hex()}"
        )
    body = buf[28:]
    if len(body) < FIXED_BODY_SIZE:
        raise ValueError(
            f"body too short: need at least {FIXED_BODY_SIZE} bytes after "
            f"type header; got {len(body)}"
        )
    if (len(body) - FIXED_BODY_SIZE) % HISTORY_RECORD_SIZE != 0:
        raise ValueError(
            f"body trailing length {len(body) - FIXED_BODY_SIZE} is not "
            f"a multiple of {HISTORY_RECORD_SIZE}"
        )

    second_id = body[0:8]
    session_uuid_lower = body[8:16]
    flag_word = body[16:20]
    if flag_word == b"\x00\x01\x00\x00":
        first_send = True
    elif flag_word == b"\x00\x00\x00\x00":
        first_send = False
    else:
        raise ValueError(
            f"first_send flag word unexpected: {flag_word.hex()}"
        )
    const_a = body[20:24]
    const_b = body[24:36]
    second_id_b = body[36:40]
    const_c = body[40:46]
    counter_u8 = body[46]
    const_d = body[47]
    (counter_u32,) = struct.unpack_from(">I", body, 48)
    if counter_u8 != counter_u32:
        raise ValueError(
            f"counter u8/u32 mismatch: u8={counter_u8}, u32={counter_u32}"
        )
    trailer = body[52:65]
    history = []
    pos = FIXED_BODY_SIZE
    while pos < len(body):
        history.append(_unpack_history_record(body[pos:pos + HISTORY_RECORD_SIZE]))
        pos += HISTORY_RECORD_SIZE

    return ActionHistory635(
        client_hash=client_hash,
        session_uuid=session_uuid,
        second_id=second_id,
        session_uuid_lower=session_uuid_lower,
        counter=counter_u8,
        first_send=first_send,
        history_counters=tuple(history),
        const_a=const_a,
        const_b=const_b,
        second_id_b=second_id_b,
        const_c=const_c,
        const_d=const_d,
        trailer=trailer,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # First-send variant (counter=1, no history)
    seq6e = bytes.fromhex(
        "a24e2975"
        "00000055"
        "1a954abc4b3185bfbe37c3d8592618e0"
        "0001b518"
        "fbde4b9a600d428f"
        "bf85314bbc4a951a"
        "00010000"
        "91020600"
        "000101000000000000000001"
        "2007194b"
        "000000ac0f01"
        "01" "01" "00000001"
        "c0802000808080800300000001"
    )
    msg = decode(seq6e)
    print(f"seq 0x6e: counter={msg.counter}, first_send={msg.first_send}, "
          f"history={msg.history_counters}")
    assert encode(msg) == seq6e, "seq 0x6e round-trip failed"

    # Largest variant (counter=5, 4 history records)
    seq72 = bytes.fromhex(
        "b1c10229"
        "00000091"
        "1a954abc4b3185bfbe37c3d8592618e0"
        "0001b518"
        "fbde4b9a600d428f"
        "bf85314bbc4a951a"
        "00000000"
        "91020600"
        "000101000000000000000001"
        "2007194b"
        "000000ac0f01"
        "05" "01" "00000005"
        "c0802000808080800300000001"
        "00000000" "04" "00" "808080800300000001"
        "00000000" "03" "00" "808080800300000001"
        "00000000" "02" "00" "808080800300000001"
        "00000000" "01" "00" "808080800300000001"
    )
    msg = decode(seq72)
    print(f"seq 0x72: counter={msg.counter}, first_send={msg.first_send}, "
          f"history={msg.history_counters}")
    assert encode(msg) == seq72, "seq 0x72 round-trip failed"

    print("OK — both variants round-trip")
