"""
RegistrationResponseMsg encoder.

The wire format is a best-effort guess based on:
  * the in-memory layout of the response object (decoded from
    FUN_146b6f190 in analysis/decomp_v3_builder.txt-adjacent files
    and `project_rep_state10_dispatcher_decoded.md`),
  * the captured V3 RegistrationRequest body
    (analysis/v3_request/all_v3_request_retries.hex,
    analysis/v3_request/HEADER_DECODE.md), and
  * AzCore SerializeContext conventions inferred from that capture
    (1-byte string length prefix, element-close marker `00 43 02 80`,
    8-byte trailing alignment pad).

MUST be revised once we observe a real successful response on the wire.
Anything labelled `# GUESS:` is a placeholder we picked because we had to
pick something — flag those for revisit when we see real server traffic
or finish the AzCore SerializeContext RE.

Caller responsibilities (NOT done here):
  * Compression (LZ4) — done by the Carrier envelope writer when it sets
    bit 0 of the type byte.
  * DTLS encryption — handled by the SSL layer downstream.
  * Wrapping in a Carrier MessageRecord and datagram envelope — see
    `frame.marshal_record` / `frame.marshal_datagram`. The bytes returned
    here go INSIDE a data-channel record's payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
#  Type identity
# ---------------------------------------------------------------------------
#
# RegistrationResponseMsg GUID per typeregistry: 104145A7-FF95-44F1-9468-21FB41C8AC2B.
# CreateInstance opcode encodes `MOV ECX, 0x60` (96 bytes in-memory size).
#
# GUID byte order on the wire — UNVERIFIED. We default to the dashed-form
# raw byte order (network order across all 16 bytes), which matches the
# instruction in the task spec. MSVC's UuidToString convention would split
# the first three groups as little-endian; if/when we observe a real
# wire-side GUID for any AzCore message, switch by setting GUID_USE_MSVC_LE
# below to True.
#
# Dashed form bytes:  10 41 45 a7  ff 95  44 f1  94 68  21 fb 41 c8 ac 2b
RESPONSE_GUID_HEX = "104145A7FF9544F1946821FB41C8AC2B"
GUID_USE_MSVC_LE = False  # GUESS: flip to True if first attempt is rejected.


def _guid_bytes() -> bytes:
    raw = bytes.fromhex(RESPONSE_GUID_HEX)
    if not GUID_USE_MSVC_LE:
        return raw
    # MSVC layout: {DWORD LE}{WORD LE}{WORD LE}{8 raw BE}
    d1 = raw[0:4][::-1]
    d2 = raw[4:6][::-1]
    d3 = raw[6:8][::-1]
    d4 = raw[8:16]
    return d1 + d2 + d3 + d4


# ---------------------------------------------------------------------------
#  AzCore SerializeContext primitives (best-effort)
# ---------------------------------------------------------------------------

def _az_string(s: str) -> bytes:
    """AzCore length-prefixed string.

    Captured V3 request shows uniformly 1-byte length prefixes for all
    visible strings (including the 40-char `sig:...` blob). We assume the
    same for the response. For len >= 256 we don't have an observed
    encoding; we raise rather than guess wrong.
    """
    encoded = s.encode("utf-8")
    if len(encoded) >= 256:
        # GUESS-territory: V3 capture's longest single-byte-prefixed string
        # was 40 chars. The Steam JWT used a `\xc4\xc3` 2-byte prefix —
        # interpretation unclear. Refuse rather than emit wrong bytes.
        raise ValueError(
            f"_az_string: length {len(encoded)} >= 256 not supported; "
            "AzCore long-string prefix encoding not yet RE'd."
        )
    return bytes([len(encoded)]) + encoded


def _az_class_close() -> bytes:
    """AzCore element-close + 8-byte alignment pad.

    Captured V3 request trailer is exactly:
        00 43 02 80 00 00 00 00 00 00 00 00     (1 + 3 + 8 bytes)
    Per HEADER_DECODE.md: `00` = element terminator, `43 02 80` =
    class-close marker (`0x80` = AzCore end-of-element high-bit tag),
    then 8 bytes of zero padding to reach 8-byte alignment. We always
    emit a fixed 8 trailing zero bytes. When we have a finer-grained
    AzCore RE we may need to compute the pad size from current offset.
    """
    return b"\x00\x43\x02\x80" + b"\x00" * 8


# ---------------------------------------------------------------------------
#  Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class V3RegistrationResponse:
    # +0x08 int32_t — MUST be 0 for the success path inside FUN_146b6f190.
    error_code: int = 0

    # +0x5b uint8_t — MUST be 0; non-zero means EOS auth failed and the
    # client tears down. Kept as a settable field for negative-test fuzzing.
    eos_flag: int = 0

    # +0x18 AZStd::string — copied into the wrapper as the active session
    # token. Stub value is fine for first contact; the client just stores
    # it for later replay.
    session_token: str = "session-stub-0001"

    # +0x58/+0x59/+0x5a — copied into wrapper[0xde], wrapper[0x6f1],
    # wrapper[0x6f2]. Semantics unknown; we send all-zero which is the
    # least likely to trigger a sub-state branch we don't understand.
    status_a: int = 0
    status_b: int = 0
    status_c: int = 0

    # GUESS: there are bytes 0x38..0x57 (32 bytes) between session_token
    # and the status triple. Likely 1-2 more AZStd::strings (transport
    # endpoints? a refresh token?). We expose a list of additional
    # strings caller can supply; default is two empty strings, which on
    # the wire becomes two `00` length bytes — the cheapest legal
    # placeholder if AzCore tolerates empty strings.
    extra_strings: List[str] = field(default_factory=lambda: ["", ""])


# ---------------------------------------------------------------------------
#  Encoder
# ---------------------------------------------------------------------------

def encode(resp: V3RegistrationResponse) -> bytes:
    """Encode the message body that goes inside a data-channel record.

    Layout (best-effort GUESS):

        [16-byte type GUID]
        [4-byte error_code, big-endian]   # AzCore int32 — Carrier endian is BE
        [AzCore string  : session_token]
        [AzCore string  : extra_strings[0]]   # GUESS placeholder
        [AzCore string  : extra_strings[1]]   # GUESS placeholder
        [1 byte         : status_a]
        [1 byte         : status_b]
        [1 byte         : status_c]
        [1 byte         : eos_flag]
        [class-close + 8-byte pad]

    The caller wraps this in a MessageRecord on a data channel
    (channel 0, 1, or 2 — NOT the system channel 3) with the
    MF_NO_LENGTH (0x40) data-channel flag bit set, mirroring the
    request format we observed.
    """
    parts: List[bytes] = []

    # Wire-side type identity. AzCore's polymorphic deserializer reads
    # this 16-byte GUID first and uses it to look up the type info that
    # tells it how many fields to read.
    parts.append(_guid_bytes())

    # error_code is int32; Carrier endian is documented BigEndian. GUESS:
    # AzCore SerializeContext respects Carrier endian for raw scalars.
    parts.append(int(resp.error_code).to_bytes(4, "big", signed=True))

    # session_token at +0x18 in-memory — first AZStd::string field after
    # the int32 + padding.
    parts.append(_az_string(resp.session_token))

    # GUESS: the +0x38..+0x57 region is two AZStd::string fields. Emit
    # whatever the caller supplied; pad to 2 entries with empty strings
    # to keep the wire shape stable.
    extras = list(resp.extra_strings)
    while len(extras) < 2:
        extras.append("")
    for s in extras[:2]:
        parts.append(_az_string(s))

    # Three status bytes copied to wrapper[0xde], [0x6f1], [0x6f2].
    parts.append(bytes([resp.status_a & 0xFF]))
    parts.append(bytes([resp.status_b & 0xFF]))
    parts.append(bytes([resp.status_c & 0xFF]))

    # eos_flag — must be 0 for success. Last scalar before the close.
    parts.append(bytes([resp.eos_flag & 0xFF]))

    # AzCore element-close + 8-byte trailing pad, mirroring the request
    # trailer at end of every captured retry.
    parts.append(_az_class_close())

    return b"".join(parts)


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    blob = encode(V3RegistrationResponse())
    # Avoid Unicode in print() per Windows-encoding feedback memory.
    print(f"len={len(blob)} bytes")
    print(blob.hex())
