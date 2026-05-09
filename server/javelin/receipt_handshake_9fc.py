"""
Receipt-handshake echo — type 0x09fc (W direction, singleton).

Single 102-byte capture (seq 0x3b). The client-side reply
acknowledging receipt of the server's `0x8e6` identity blob.

**Cross-codec invariant**: the trailing 16 bytes of 0x9fc are
**byte-for-byte identical to the `opaque_blob` field in the
preceding `0x8e6` R message**, and the upper 8 bytes of 0x9fc's
subkey match the upper 8 bytes of 0x8e6's `identity_uuid`. So
0x9fc is the receipt-confirmation echo: "client to server: I
got your 0x8e6, here's the hash echoed back."

Wire layout (full 102-byte W message):

  +0x00  u8x4    client_hash       per-message correlation hash
  +0x04  u32 BE  remaining_len     0x5e = 94 = total - 8
  +0x08  u8x16   session_uuid      full session UUID
  +0x18  u8x4    type_header       [00 01 bc 27] = type 0x09fc
  +0x1c  u8x16   subkey            upper 8 = `4c 0c 0e d6 47 8a
                                                69 da` (matches
                                                0x8e6 identity_uuid
                                                upper 8 — receipt-
                                                handshake sub-system
                                                id)
                                     lower 8 = session_uuid_lower
  +0x2c  u8x16   echoed_session_uuid  full session UUID, identical to
                                     bytes +0x08..+0x17. Looks like
                                     the client's "I'm reflecting
                                     back the session-id you assigned
                                     me" pattern — not strictly
                                     necessary for routing since the
                                     outer envelope already carries
                                     it, but matches a "session-id-
                                     pair handshake" interpretation.
  +0x3c  u8x26   state_block       26 bytes of opaque state. Visible
                                     content: `00 00 00 00 00 00 00 01
                                     00 00 00 01 00 00 00 00 00 a0 10
                                     00 00 00 10 10 00 09`. Treated
                                     as opaque — too compressed to
                                     pin down per-byte semantics
                                     from one capture.
  +0x56  u8x16   echoed_blob       BYTE-IDENTICAL to the 16-byte
                                     `opaque_blob` field of the
                                     0x8e6 R message that this
                                     0x9fc acknowledges. The
                                     codec validates this echo
                                     when given the paired
                                     0x8e6 blob (helper
                                     `verify_8e6_echo`).

Total: 102 bytes.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


TYPED_BODY_SIZE = 102

# Layout offsets
SESSION_UUID_OFFSET = 8
SESSION_UUID_SIZE = 16
TYPE_HEADER_OFFSET = 24
SUBKEY_OFFSET = 28
SUBKEY_SIZE = 16
ECHOED_SESSION_UUID_OFFSET = 44
ECHOED_SESSION_UUID_SIZE = 16
STATE_BLOCK_OFFSET = 60
STATE_BLOCK_SIZE = 26
ECHOED_BLOB_OFFSET = 86
ECHOED_BLOB_SIZE = 16

# 4-byte typed envelope header for type 0x09fc:
#   marker [0x00, 0x01], then ((0x09fc & 0x3f) | 0x80) = 0xbc,
#   then ((0x09fc >> 6) & 0xff) = 0x27
TYPE_HEADER = bytes((0x00, 0x01, 0xbc, 0x27))


@dataclass
class ReceiptHandshake9FC:
    """W-direction 0x09fc receipt-handshake echo (102 bytes total)."""

    client_hash: bytes              # 4 bytes
    session_uuid: bytes             # 16 bytes (envelope)
    subkey: bytes                   # 16 bytes
    echoed_session_uuid: bytes      # 16 bytes (typically equals session_uuid)
    state_block: bytes              # 26 bytes — opaque
    echoed_blob: bytes              # 16 bytes — must match the paired
                                    # 0x8e6's opaque_blob

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
        if len(self.echoed_session_uuid) != ECHOED_SESSION_UUID_SIZE:
            raise ValueError(
                f"echoed_session_uuid must be exactly "
                f"{ECHOED_SESSION_UUID_SIZE} bytes; "
                f"got {len(self.echoed_session_uuid)}"
            )
        if len(self.state_block) != STATE_BLOCK_SIZE:
            raise ValueError(
                f"state_block must be exactly {STATE_BLOCK_SIZE} bytes; "
                f"got {len(self.state_block)}"
            )
        if len(self.echoed_blob) != ECHOED_BLOB_SIZE:
            raise ValueError(
                f"echoed_blob must be exactly {ECHOED_BLOB_SIZE} bytes; "
                f"got {len(self.echoed_blob)}"
            )

    def verify_8e6_echo(self, paired_8e6_opaque_blob: bytes) -> bool:
        """Verify the 16-byte echoed_blob matches the paired 0x8e6's
        opaque_blob byte-for-byte. Returns True if they match."""
        if len(paired_8e6_opaque_blob) != ECHOED_BLOB_SIZE:
            raise ValueError(
                f"paired blob must be exactly {ECHOED_BLOB_SIZE} bytes; "
                f"got {len(paired_8e6_opaque_blob)}"
            )
        return self.echoed_blob == paired_8e6_opaque_blob


def encode(msg: ReceiptHandshake9FC) -> bytes:
    """Build the on-wire 0x09fc W message (102 bytes total)."""
    body = (
        msg.subkey
        + msg.echoed_session_uuid
        + msg.state_block
        + msg.echoed_blob
    )
    remaining_len = SESSION_UUID_SIZE + 4 + len(body)
    return (
        msg.client_hash
        + struct.pack(">I", remaining_len)
        + msg.session_uuid
        + TYPE_HEADER
        + body
    )


def decode(buf: bytes) -> ReceiptHandshake9FC:
    """Parse a 0x09fc W message. Raises on size, length-field, or
    type-header mismatch."""
    if len(buf) != TYPED_BODY_SIZE:
        raise ValueError(
            f"expected exactly {TYPED_BODY_SIZE} bytes; got {len(buf)}"
        )
    client_hash = buf[0:4]
    (remaining,) = struct.unpack_from(">I", buf, 4)
    if remaining != TYPED_BODY_SIZE - 8:
        raise ValueError(
            f"remaining-length field mismatch: expected 0x{TYPED_BODY_SIZE - 8:x}, "
            f"got 0x{remaining:x}"
        )
    session_uuid = buf[SESSION_UUID_OFFSET:SESSION_UUID_OFFSET + SESSION_UUID_SIZE]
    if buf[TYPE_HEADER_OFFSET:TYPE_HEADER_OFFSET + 4] != TYPE_HEADER:
        raise ValueError(
            f"type header mismatch: expected {TYPE_HEADER.hex()}, "
            f"got {buf[TYPE_HEADER_OFFSET:TYPE_HEADER_OFFSET + 4].hex()}"
        )
    return ReceiptHandshake9FC(
        client_hash=client_hash,
        session_uuid=session_uuid,
        subkey=buf[SUBKEY_OFFSET:SUBKEY_OFFSET + SUBKEY_SIZE],
        echoed_session_uuid=buf[ECHOED_SESSION_UUID_OFFSET:
                                ECHOED_SESSION_UUID_OFFSET + ECHOED_SESSION_UUID_SIZE],
        state_block=buf[STATE_BLOCK_OFFSET:STATE_BLOCK_OFFSET + STATE_BLOCK_SIZE],
        echoed_blob=buf[ECHOED_BLOB_OFFSET:ECHOED_BLOB_OFFSET + ECHOED_BLOB_SIZE],
    )


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    captured = bytes.fromhex(
        "e7117bb9"
        "0000005e"
        "1a954abc4b3185bfbe37c3d8592618e0"
        "0001bc27"
        "4c0c0ed6478a69dabf85314bbc4a951a"
        "1a954abc4b3185bfbe37c3d8592618e0"
        "00000000000000010000000100000000000a01000000010100 09".replace(" ", "")
        + "e1634370307b4d06a72fd9df005cd942"
    )
    msg = decode(captured)
    print(f"echoed_blob={msg.echoed_blob.hex()}")
    print(f"echoed_session_uuid matches session_uuid: "
          f"{msg.echoed_session_uuid == msg.session_uuid}")
    rebuilt = encode(msg)
    assert rebuilt == captured, (
        f"round-trip failed:\n  got: {rebuilt.hex()}\n  exp: {captured.hex()}"
    )
    print(f"len={len(rebuilt)} bytes — round-trip OK")
