"""RegistrationRequestV3Msg body parser.

Decodes the 832-byte AzCore-serialized body of a captured V3 registration
request (see ``analysis/v3_request/all_v3_request_retries.hex`` and
``analysis/v3_request/BODY_DECODE.md``).

The framing was only partially reverse-engineered. Every visible
``AZStd::string`` element is recovered (length-prefixed by ``u8``); the
inter-field framing bytes and the long Steam auth blob are kept verbatim
as ``Optional[bytes]`` so the body can be round-tripped byte-for-byte.

Nothing here is "guessed" -- if a region's encoding is unknown it is
preserved as raw bytes labelled ``unknown_*``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional  # noqa: F401 -- documents intent on `bytes` fields


# Region offsets into the 832-byte body (from BODY_DECODE.md).
PRELUDE_END = 0x21              # bytes [0x000..0x021] -- raw prelude / type-id
AUTH_BLOB_START = 0x15D         # bytes [0x15D..0x334] -- Steam ticket region
TRAILER_OFF = 0x334             # bytes [0x334..0x340] -- 12 B class-close + pad
TRAILER = bytes.fromhex("00430280" + "00" * 8)
EXPECTED_BODY_LEN = 832


@dataclass
class V3RegistrationRequest:
    """Decoded V3 RegistrationRequest body.

    String fields below are the AzCore length-prefixed elements visible in
    the capture. Every ``unknown_*`` field is opaque bytes preserved
    verbatim so we can re-emit the original payload.
    """

    # --- Opaque header / type-id region (0x000..0x021, 33 B) ---------------
    # Contains the wire-side type identity (likely `RegistrationRequestV3Msg`
    # GUID 0B826B33-89F5-49E0-B8CB-FE4433427778 in some byte order) plus
    # AzCore class metadata (CRC-shaped bytes near the end). Not decoded.
    prelude: bytes = b""

    # --- Visible AZStd::string fields, in wire order -----------------------
    # All length-prefixed by a single u8. See BODY_DECODE.md for offsets.
    build_version: str = ""              # "6031"
    unknown_400: str = ""                # "400" -- branch / region (?)
    sdk_name: str = ""                   # "Javelin"
    sdk_version: str = ""                # "600415" + a trailing 0x18 byte
    sdk_version_tail: int = 0            # the 0x18 byte after "600415"
    build_flavor: str = ""               # "[RETAIL]"
    client_signature: str = ""           # "sig:fb79c7c4-...-7a11e6e27eb8"
    client_endpoint: str = ""            # "127.0.0.1:23971"
    session_uuid: str = ""               # "4760baff-f4af-49ee-8875-3e0103c74b07"
    persona_id: str = ""                 # "amzn1.developerPersonaId.4ee4810f-..."
    platform_app_tag: str = ""           # "STEAM_APP_ID.1063730"
    platform_user_id: str = ""           # "76561198069524636" (SteamID64)
    platform_name_blob: str = ""         # captured as 8-byte field "steam|14"
                                         # (length prefix = 0x08, not 0x05)

    # --- Inter-field gap bytes, kept verbatim -------------------------------
    # gaps[i] is the bytes between string[i] and string[i+1] (post-length
    # byte of string[i] up to the length byte of string[i+1]).
    gaps: list[bytes] = field(default_factory=list)

    # The blob between the "127.0.0.1:23971" string and the session UUID is
    # special: it leads with the literal text `b1a00000-` (truncated worldId
    # candidate) followed by 11 B of binary. Tracked explicitly.
    unknown_worldid_region: bytes = b""

    # --- Steam auth blob (0x15D..0x334) ------------------------------------
    # Internal framing not yet RE'd. Contains the Steam auth ticket and
    # likely the JWT, hex-encoded with f0/f1/f2 + a2/88/91/a4/c4/af tag
    # bytes. Round-tripped verbatim.
    auth_blob: bytes = b""

    # --- Trailer (0x334..0x340, 12 B) --------------------------------------
    # Always `00 43 02 80` + 8 zero bytes. Defaulted; settable for fuzzing.
    trailer: bytes = TRAILER

    # --- Retry-format round-trip support (wake 108) ------------------------
    # When the body was decoded by `parse_v3_request_retry` (the tagged
    # 6-record format used by V3 retries with chunked replay payloads),
    # these three fields capture the parts the strict format doesn't have a
    # slot for. `retry_records` carries the (type_id, value) pairs in their
    # captured order; the encoder re-emits prelude + records (in this exact
    # order) + tail.
    #
    # Empty on strict-decoded messages — so the strict serializer ignores
    # them. Non-empty on retry-decoded messages — `serialize_v3_request_retry`
    # uses them to round-trip byte-for-byte.
    retry_prelude: bytes = b""
    retry_records: list[tuple[int, str]] = field(default_factory=list)
    retry_tail: bytes = b""


def _read_str(buf: bytes, off: int) -> tuple[str, int]:
    """Read [u8 length][length bytes ASCII] from buf at off; return (text, new_off)."""
    if off >= len(buf):
        raise ValueError(f"_read_str: offset {off:#x} past end")
    ln = buf[off]
    end = off + 1 + ln
    if end > len(buf):
        raise ValueError(
            f"_read_str: length {ln} at off {off:#x} overruns buffer "
            f"(len={len(buf)})"
        )
    return buf[off + 1:end].decode("latin-1"), end


def parse_v3_request(body: bytes) -> V3RegistrationRequest:
    """Walk the 832-byte body and return a populated dataclass.

    The walk uses fixed offsets where the framing is unknown (prelude,
    inter-field gaps, auth blob) and length-prefixed reads where we
    confirmed the AzCore string element format.
    """
    if len(body) != EXPECTED_BODY_LEN:
        raise ValueError(
            f"parse_v3_request: expected {EXPECTED_BODY_LEN} B body, got {len(body)}"
        )
    if not body.endswith(TRAILER):
        raise ValueError("parse_v3_request: missing standard 12 B trailer")

    msg = V3RegistrationRequest()
    msg.prelude = body[:PRELUDE_END]

    # (length-prefix offset, attribute-to-set). Read length from wire.
    schedule = [
        (0x021, "build_version"),
        (0x02a, "unknown_400"),
        (0x038, "sdk_name"),
        (0x044, "sdk_version_raw"),     # 6 visible + 1 tail byte (0x18)
        (0x050, "build_flavor"),
        (0x05a, "client_signature"),
        (0x083, "client_endpoint"),
        # 0x093..0x0a8 -- worldId-prefix region, captured opaque
        (0x0a8, "session_uuid"),
        (0x0cd, "persona_id"),
        (0x110, "platform_app_tag"),
        (0x144, "platform_user_id"),
        (0x157, "platform_name_blob"),  # length byte is 0x08; data = "steam|14"
    ]

    # Walk strings; bytes between consecutive length-prefix offsets become
    # gaps[i-1] (no gap before slot 0). Always append, even when empty, so
    # gaps[i-1] aligns 1:1 with strings[i] on re-serialize.
    cursor = PRELUDE_END
    for slot_idx, (off, attr) in enumerate(schedule):
        if slot_idx > 0:
            msg.gaps.append(body[cursor:off])
        text, cursor = _read_str(body, off)
        if attr == "sdk_version_raw":
            msg.sdk_version = text[:-1]
            msg.sdk_version_tail = ord(text[-1])
        else:
            setattr(msg, attr, text)

    # The worldId-prefix region (between client_endpoint and session_uuid)
    # is captured separately; clear its slot in gaps[] so it isn't
    # double-emitted on re-serialize.
    msg.unknown_worldid_region = body[0x93:0xa8]
    SESSION_UUID_GAP_IDX = 6
    if (SESSION_UUID_GAP_IDX < len(msg.gaps) and
            msg.gaps[SESSION_UUID_GAP_IDX] == body[0x93:0xa8]):
        msg.gaps[SESSION_UUID_GAP_IDX] = b""

    # Auth blob from end of platform_name_blob (cursor) to TRAILER_OFF.
    msg.auth_blob = body[cursor:TRAILER_OFF]

    msg.trailer = body[TRAILER_OFF:]
    return msg


def parse_v3_request_retry(body: bytes) -> V3RegistrationRequest | None:
    """Parse a V3 retry body whose format differs from the 832-byte
    first-attempt.

    Captured retries use a length-prefixed record format starting at
    offset +0x20 (after a 32-byte prelude). Each record is:

        +0  u32 BE  type_id  (in [0..7])
        +4  u8      length
        +5  bytes   string of `length` bytes

    The 6 record type-ids observed in the captured retry map to the
    same logical fields as the strict body:

        type 0 → build_flavor             "[RETAIL]"
        type 1 → sdk_name                 "Javelin"
        type 2 → unknown_sdk_field        "1"  (purpose unknown)
        type 3 → unknown_400              "400"
        type 4 → build_version            "6031"
        type 5 → unknown_sdk_blob         "6004151"

    After the 6 records, the remaining ~2.6 KB tail carries the
    Amazon `az_*` metadata blob and (in unredacted captures) the
    session_uuid, persona_id, client_signature, and other identity
    fields. We extract those via the lenient regex pass.

    Returns a partially-populated `V3RegistrationRequest` (without
    `prelude`, `gaps`, `auth_blob`, `trailer` — those round-tripping
    fields are strict-only). Returns `None` if the leading 6 records
    don't parse as the expected tagged format.
    """
    import struct

    PRELUDE_LEN = 32
    EXPECTED_RECORD_COUNT = 6

    if len(body) < PRELUDE_LEN + 5 * EXPECTED_RECORD_COUNT:
        return None

    msg = V3RegistrationRequest()
    msg.retry_prelude = body[:PRELUDE_LEN]
    off = PRELUDE_LEN
    records: list[tuple[int, str]] = []
    for _ in range(EXPECTED_RECORD_COUNT):
        if off + 5 > len(body):
            return None
        type_id = struct.unpack_from(">I", body, off)[0]
        if type_id > 0xFFFF:
            return None
        ln = body[off + 4]
        end = off + 5 + ln
        if end > len(body):
            return None
        text = body[off + 5:end].decode("latin-1", errors="replace")
        records.append((type_id, text))

        if type_id == 4:
            msg.build_version = text
        elif type_id == 3:
            msg.unknown_400 = text
        elif type_id == 1:
            msg.sdk_name = text
        elif type_id == 0:
            msg.build_flavor = text
        # types 2 and 5 carry values whose strict-mode mapping is not
        # confirmed; deliberately not assigned to avoid overwriting
        # strict semantics

        off = end

    # Sanity check the records look right (set, not order-strict).
    if {tid for tid, _ in records} != {0, 1, 2, 3, 4, 5}:
        return None

    msg.retry_records = records
    msg.retry_tail = body[off:]

    # Pull identity fields from the tail via the lenient regex pass.
    tail_extract = parse_v3_request_lenient(msg.retry_tail)
    if tail_extract is not None:
        msg.session_uuid = tail_extract.session_uuid or msg.session_uuid
        msg.persona_id = tail_extract.persona_id or msg.persona_id

    return msg


def serialize_v3_request_retry(msg: V3RegistrationRequest) -> bytes:
    """Re-emit a V3 retry body from a dataclass that was retry-decoded.

    Requires `retry_prelude`, `retry_records`, and `retry_tail` to be
    populated (they are after a successful `parse_v3_request_retry`).
    Records are emitted in their captured order, which is preserved by
    the parser. Round-trips byte-for-byte for any body where the parser
    succeeded.

    Raises `ValueError` if the dataclass wasn't retry-decoded (i.e. the
    retry-format fields are still at their defaults).
    """
    import struct
    if not msg.retry_records:
        raise ValueError(
            "serialize_v3_request_retry: dataclass has no retry_records; "
            "use parse_v3_request_retry to decode first, or call "
            "serialize_v3_request for strict-format bodies"
        )
    out = bytearray(msg.retry_prelude)
    for type_id, text in msg.retry_records:
        out.extend(struct.pack(">I", type_id))
        body_bytes = text.encode("latin-1")
        if len(body_bytes) > 0xFF:
            raise ValueError(
                f"retry record value too long for u8 length: "
                f"type={type_id} len={len(body_bytes)}"
            )
        out.append(len(body_bytes))
        out.extend(body_bytes)
    out.extend(msg.retry_tail)
    return bytes(out)


def parse_v3_request_lenient(body: bytes) -> V3RegistrationRequest | None:
    """Best-effort identity extraction from a V3 body that doesn't match
    the strict 832-byte form (e.g. retries with chunked replay payloads,
    or the 835-byte live first-attempt).

    Recovers `session_uuid` and `persona_id` by regex, since those two
    identity fields are the only ones the runtime needs from a retry.
    Returns a `V3RegistrationRequest` with just those fields populated,
    or `None` when neither field is recoverable.

    The parser does **not** populate `auth_blob`, `prelude`, `gaps`, or
    any other strict-mode field — pass the result back through
    `serialize_v3_request` only after re-populating those.

    Used by `dispatch.decode_replay_message` as the fallback when
    `parse_v3_request` rejects a body. Promoted from
    `rep_responder._lenient_v3_extract` (wake 106).
    """
    import re

    # session_uuid is a normal UUID preceded by a `$` (0x24) length byte
    # (0x24 == 36, the UUID's length).
    session_uuid = ""
    for u in re.finditer(
        rb'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-'
        rb'[0-9a-f]{4}-[0-9a-f]{12}',
        body,
    ):
        # Skip occurrences inside the auth signature blob ("sig:") or
        # inside `naId.<uuid>` runs.
        pre = body[max(0, u.start() - 8):u.start()].decode(
            "latin-1", errors="replace"
        )
        if "sig:" in pre or "naId." in pre:
            continue
        if u.start() > 0 and body[u.start() - 1] == 0x24:
            session_uuid = u.group(0).decode("ascii")
            break

    # persona_id is `amzn1.developerPersonaId.<uuid>` (61 chars).
    persona_id = ""
    m = re.search(
        rb'amzn1\.developerPersonaId\.[0-9a-f-]{36}',
        body,
    )
    if m:
        persona_id = m.group(0).decode("ascii")

    if not session_uuid and not persona_id:
        return None
    out = V3RegistrationRequest()
    out.session_uuid = session_uuid
    out.persona_id = persona_id
    return out


def parse_v3_request_or_lenient(body: bytes) -> V3RegistrationRequest:
    """Try the strict parser first; on failure fall back to retry-format
    (tagged records); on second failure fall back to lenient regex.

    Raises `ValueError` only when all three parsers fail (typical for a
    body with no recognizable identity material). The strict parser's
    full error is wrapped into the final-failure message for
    diagnostics.

    This is the entry point the dispatcher uses for type 0x13.
    """
    try:
        return parse_v3_request(body)
    except ValueError as strict_err:
        retry = parse_v3_request_retry(body)
        if retry is not None:
            return retry
        lenient = parse_v3_request_lenient(body)
        if lenient is not None:
            return lenient
        raise ValueError(
            f"v3 retry+lenient fallbacks also failed; "
            f"strict error: {strict_err}"
        )


def serialize_v3_request(msg: V3RegistrationRequest) -> bytes:
    """Re-emit a V3 body from a parsed dataclass.

    Pairs gaps and string-elements in declared order, splices the
    worldId-prefix region back into its slot, then appends the auth blob
    and trailer. Round-trips parse output exactly.
    """
    out = bytearray()
    out.extend(msg.prelude)

    string_attrs = [
        ("build_version", msg.build_version),
        ("unknown_400", msg.unknown_400),
        ("sdk_name", msg.sdk_name),
        ("sdk_version_raw", msg.sdk_version + chr(msg.sdk_version_tail)),
        ("build_flavor", msg.build_flavor),
        ("client_signature", msg.client_signature),
        ("client_endpoint", msg.client_endpoint),
        ("session_uuid", msg.session_uuid),
        ("persona_id", msg.persona_id),
        ("platform_app_tag", msg.platform_app_tag),
        ("platform_user_id", msg.platform_user_id),
        ("platform_name_blob", msg.platform_name_blob),
    ]

    for i, (attr, text) in enumerate(string_attrs):
        # gaps[k] sits BEFORE strings[k+1] (i.e., between strings[k] and
        # strings[k+1]). The first string follows directly from the prelude
        # with no separating gap. The session_uuid slot uses the opaque
        # worldId-prefix region in place of an ordinary gap.
        if i > 0:
            if attr == "session_uuid":
                out.extend(msg.unknown_worldid_region)
            else:
                gap_idx = i - 1
                gap = msg.gaps[gap_idx] if gap_idx < len(msg.gaps) else b""
                out.extend(gap)
        encoded = text.encode("latin-1")
        out.append(len(encoded))
        out.extend(encoded)

    out.extend(msg.auth_blob)
    out.extend(msg.trailer)
    return bytes(out)


# ---------------------------------------------------------------------------
#  Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import pprint

    here = os.path.dirname(__file__)
    hex_path = os.path.abspath(
        os.path.join(here, "..", "..", "analysis", "v3_request",
                     "all_v3_request_retries.hex")
    )
    with open(hex_path) as f:
        retry2 = bytes.fromhex(f.readlines()[1].strip())

    HEADER = 11
    body = retry2[HEADER:]
    print(f"body length = {len(body)} bytes")

    msg = parse_v3_request(body)
    pprint.pprint(msg, width=120)

    rebuilt = serialize_v3_request(msg)
    print(f"\nrebuilt length = {len(rebuilt)} bytes")

    if rebuilt == body:
        print("ROUND-TRIP: byte-for-byte identical")
    else:
        # Diff diagnostics
        diff_off = next(
            (i for i, (a, b) in enumerate(zip(rebuilt, body)) if a != b),
            min(len(rebuilt), len(body)),
        )
        accounted = sum(1 for a, b in zip(rebuilt, body) if a == b)
        print(f"ROUND-TRIP MISMATCH: first diff at offset {diff_off:#x}")
        print(f"  original[{diff_off:#x}:{diff_off+16:#x}] = "
              f"{body[diff_off:diff_off+16].hex(' ')}")
        print(f"  rebuilt [{diff_off:#x}:{diff_off+16:#x}] = "
              f"{rebuilt[diff_off:diff_off+16].hex(' ')}")
        print(f"  bytes that match: {accounted} / {len(body)} "
              f"({100*accounted//len(body)}%)")
