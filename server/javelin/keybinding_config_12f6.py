"""
Keybinding configuration — type 0x12f6 (W direction, singleton).

Single 299-byte capture (seq 0x6b). Body carries the client's
keyboard/mouse binding configuration: an array of u8-prefixed
UTF-8 binding tokens (e.g. `@cc_f3`, `@cc_mouse2`, `@cc_q`)
followed by two trailing version-block strings.

Wire layout (full 299-byte W message):

  +0x000  u8x4    client_hash       per-message correlation hash
  +0x004  u32 BE  remaining_len     0x123 = 291 = total - 8
  +0x008  u8x16   session_uuid      full session UUID
  +0x018  u8x4    type_header       [00 01 b6 4b] = type 0x12f6
  +0x01c  u8x16   subkey            upper 8 = `9e 92 1a 15 49 71
                                                f6 b7` (keybinding-
                                                config sub-system id)
                                     lower 8 = session_uuid_lower
  +0x02c  u8x26   state_region      26 bytes — looks like a fixed
                                     "key state" block:
                                       flags (16): `01 00 01 01 01 00
                                                    01 00 01 00 00 00
                                                    01 05 00 03`
                                       modifiers (10): `00 03 03 03 03
                                                        03 03 03 03 03`
                                     Treated as opaque by this codec
                                     (no semantic per-byte decoding
                                     attempted from a single capture).
  +0x046  u8x(N)  keybindings       N u8-prefixed UTF-8 strings of
                                     keybinding tokens:
                                       @cc_f3, @cc_e, @cc_tab, "",
                                       @cc_c, "", @cc_e, @cc_mouse2,
                                       @cc_f3, @cc_y, @cc_3, @cc_4,
                                       @cc_5, @cc_6, @cc_q, @cc_r,
                                       @cc_f, @cc_m
                                     (18 entries, 2 of which empty)
  +...    u8x5    transition        `01 00 00 00 00` (constant in
                                     capture; opaque)
  +...    u8x56   version_block_1   length-byte 0x37 (= 55) +
                                     55-byte content
                                     `{0.0.0.00000000}.{<36 nulls>}`
  +...    u8x56   version_block_2   `{0.0.1.00000000}.{<36 nulls>}`
  +...    u8x5    trailer           `00 00 00 00 00`

Total: 28 + 16 + 26 + (string-list-bytes) + 5 + 56 + 56 + 5
For the captured 18-binding case the keybinding region is 107 bytes
and total is 299.

This codec pins the prefix (envelope + subkey + state_region) and
the trailing structure (5-byte transition + 2 × 56-byte version
blocks + 5-byte trailer). The middle keybinding region is parsed
as a list of u8-prefixed UTF-8 strings.

The codec is **conservative** — the per-byte semantics of the
state_region and the transition/trailer slots aren't fully decoded.
Round-trips byte-exact for the captured message and for arbitrary
binding lists.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


# Layout offsets (within the full wire message)
SESSION_UUID_OFFSET = 8
SESSION_UUID_SIZE = 16
TYPE_HEADER_OFFSET = 24
SUBKEY_OFFSET = 28
SUBKEY_SIZE = 16
STATE_REGION_OFFSET = 44
STATE_REGION_SIZE = 26
KEYBINDINGS_OFFSET = STATE_REGION_OFFSET + STATE_REGION_SIZE  # 70

TRANSITION_SIZE = 5
VERSION_BLOCK_SIZE = 56          # 1 length byte + 55-byte content
VERSION_BLOCK_CONTENT_LEN = 55
VERSION_BLOCK_LENGTH_PREFIX = 0x37
NUM_VERSION_BLOCKS = 2
TRAILER_SIZE = 5

# Fixed-size suffix after the keybindings list:
# transition (5) + 2 × version_block (56) + trailer (5) = 122 bytes
SUFFIX_SIZE = TRANSITION_SIZE + NUM_VERSION_BLOCKS * VERSION_BLOCK_SIZE + TRAILER_SIZE  # 122

# Captured constants for the "transition" and "trailer" slots
DEFAULT_TRANSITION = bytes((0x01, 0x00, 0x00, 0x00, 0x00))
DEFAULT_TRAILER = bytes(5)  # all zeros

# 4-byte typed envelope header for type 0x12f6:
#   marker [0x00, 0x01], then ((0x12f6 & 0x3f) | 0x80) = 0xb6,
#   then ((0x12f6 >> 6) & 0xff) = 0x4b
TYPE_HEADER = bytes((0x00, 0x01, 0xb6, 0x4b))


@dataclass
class KeybindingConfig12F6:
    """W-direction 0x12f6 keybinding configuration (variable size)."""

    client_hash: bytes              # 4 bytes
    session_uuid: bytes             # 16 bytes
    subkey: bytes                   # 16 bytes
    state_region: bytes             # 26 bytes — opaque key-state block
    keybindings: tuple[str, ...]    # u8-prefixed UTF-8 binding tokens
    version_block_1: bytes          # 55-byte content (without length prefix)
    version_block_2: bytes          # 55-byte content (without length prefix)
    transition: bytes = DEFAULT_TRANSITION
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
        if len(self.subkey) != SUBKEY_SIZE:
            raise ValueError(
                f"subkey must be exactly {SUBKEY_SIZE} bytes; "
                f"got {len(self.subkey)}"
            )
        if len(self.state_region) != STATE_REGION_SIZE:
            raise ValueError(
                f"state_region must be exactly {STATE_REGION_SIZE} bytes; "
                f"got {len(self.state_region)}"
            )
        for i, kb in enumerate(self.keybindings):
            encoded = kb.encode("utf-8")
            if len(encoded) > 0xFF:
                raise ValueError(
                    f"keybindings[{i}] length {len(encoded)} doesn't fit in u8"
                )
        if len(self.version_block_1) != VERSION_BLOCK_CONTENT_LEN:
            raise ValueError(
                f"version_block_1 must be exactly {VERSION_BLOCK_CONTENT_LEN} bytes; "
                f"got {len(self.version_block_1)}"
            )
        if len(self.version_block_2) != VERSION_BLOCK_CONTENT_LEN:
            raise ValueError(
                f"version_block_2 must be exactly {VERSION_BLOCK_CONTENT_LEN} bytes; "
                f"got {len(self.version_block_2)}"
            )
        if len(self.transition) != TRANSITION_SIZE:
            raise ValueError(
                f"transition must be exactly {TRANSITION_SIZE} bytes; "
                f"got {len(self.transition)}"
            )
        if len(self.trailer) != TRAILER_SIZE:
            raise ValueError(
                f"trailer must be exactly {TRAILER_SIZE} bytes; "
                f"got {len(self.trailer)}"
            )


def _encode_keybindings(keybindings: tuple[str, ...]) -> bytes:
    out = bytearray()
    for kb in keybindings:
        encoded = kb.encode("utf-8")
        out += bytes((len(encoded),))
        out += encoded
    return bytes(out)


def encode(msg: KeybindingConfig12F6) -> bytes:
    """Build the on-wire 0x12f6 W message."""
    keybindings_bytes = _encode_keybindings(msg.keybindings)
    body = (
        msg.subkey
        + msg.state_region
        + keybindings_bytes
        + msg.transition
        + bytes((VERSION_BLOCK_LENGTH_PREFIX,))
        + msg.version_block_1
        + bytes((VERSION_BLOCK_LENGTH_PREFIX,))
        + msg.version_block_2
        + msg.trailer
    )
    remaining_len = SESSION_UUID_SIZE + 4 + len(body)
    return (
        msg.client_hash
        + struct.pack(">I", remaining_len)
        + msg.session_uuid
        + TYPE_HEADER
        + body
    )


def decode(buf: bytes) -> KeybindingConfig12F6:
    """Parse a 0x12f6 W message. Walks the keybinding string list
    until it has consumed exactly `total - SUFFIX_SIZE` bytes; rejects
    if the walk doesn't land cleanly on the suffix boundary."""
    min_size = KEYBINDINGS_OFFSET + SUFFIX_SIZE
    if len(buf) < min_size:
        raise ValueError(
            f"buffer too short: need at least {min_size} bytes; got {len(buf)}"
        )
    client_hash = buf[0:4]
    (remaining,) = struct.unpack_from(">I", buf, 4)
    expected_remaining = len(buf) - 8
    if remaining != expected_remaining:
        raise ValueError(
            f"remaining-length field mismatch: expected 0x{expected_remaining:x}, "
            f"got 0x{remaining:x}"
        )
    session_uuid = buf[SESSION_UUID_OFFSET:SESSION_UUID_OFFSET + SESSION_UUID_SIZE]
    if buf[TYPE_HEADER_OFFSET:TYPE_HEADER_OFFSET + 4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[TYPE_HEADER_OFFSET:TYPE_HEADER_OFFSET + 4].hex()}"
        )
    subkey = buf[SUBKEY_OFFSET:SUBKEY_OFFSET + SUBKEY_SIZE]
    state_region = buf[STATE_REGION_OFFSET:STATE_REGION_OFFSET + STATE_REGION_SIZE]

    # Keybindings region runs from KEYBINDINGS_OFFSET to (len - SUFFIX_SIZE).
    suffix_start = len(buf) - SUFFIX_SIZE
    if suffix_start < KEYBINDINGS_OFFSET:
        raise ValueError(
            f"buffer leaves no room for keybindings region: "
            f"suffix_start={suffix_start}, KEYBINDINGS_OFFSET={KEYBINDINGS_OFFSET}"
        )
    keybindings: list[str] = []
    pos = KEYBINDINGS_OFFSET
    while pos < suffix_start:
        L = buf[pos]
        pos += 1
        if pos + L > suffix_start:
            raise ValueError(
                f"keybinding length {L} at offset {pos - 1} overruns the "
                f"keybindings region (suffix_start={suffix_start})"
            )
        try:
            keybindings.append(buf[pos:pos + L].decode("utf-8"))
        except UnicodeDecodeError as e:
            raise ValueError(
                f"keybinding at offset {pos - 1} not valid UTF-8: {e}"
            ) from None
        pos += L
    if pos != suffix_start:
        raise ValueError(
            f"keybinding walk landed at offset {pos}; expected {suffix_start}"
        )

    transition = buf[suffix_start:suffix_start + TRANSITION_SIZE]
    pos = suffix_start + TRANSITION_SIZE
    # Version block 1
    if buf[pos] != VERSION_BLOCK_LENGTH_PREFIX:
        raise ValueError(
            f"version_block_1 length prefix mismatch at offset {pos}: "
            f"expected 0x{VERSION_BLOCK_LENGTH_PREFIX:02x}, got 0x{buf[pos]:02x}"
        )
    pos += 1
    version_block_1 = buf[pos:pos + VERSION_BLOCK_CONTENT_LEN]
    pos += VERSION_BLOCK_CONTENT_LEN
    # Version block 2
    if buf[pos] != VERSION_BLOCK_LENGTH_PREFIX:
        raise ValueError(
            f"version_block_2 length prefix mismatch at offset {pos}: "
            f"expected 0x{VERSION_BLOCK_LENGTH_PREFIX:02x}, got 0x{buf[pos]:02x}"
        )
    pos += 1
    version_block_2 = buf[pos:pos + VERSION_BLOCK_CONTENT_LEN]
    pos += VERSION_BLOCK_CONTENT_LEN
    trailer = buf[pos:pos + TRAILER_SIZE]
    pos += TRAILER_SIZE
    if pos != len(buf):
        raise ValueError(
            f"unexpected trailing {len(buf) - pos} bytes after parse"
        )
    return KeybindingConfig12F6(
        client_hash=client_hash,
        session_uuid=session_uuid,
        subkey=subkey,
        state_region=state_region,
        keybindings=tuple(keybindings),
        version_block_1=version_block_1,
        version_block_2=version_block_2,
        transition=transition,
        trailer=trailer,
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    store = ReplayStore(p)
    m = next(m for m in store.messages if m.type_id == 0x12f6)
    msg = decode(m.body)
    print(f"keybindings ({len(msg.keybindings)}):")
    for kb in msg.keybindings:
        print(f"  {kb!r}")
    rebuilt = encode(msg)
    assert rebuilt == m.body, "round-trip failed"
    print(f"len={len(rebuilt)} bytes — round-trip OK")
