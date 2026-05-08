"""
Tests for v3_response encoder, v3_request codec, and replay_store parser.

Run with:
    pytest server/javelin/test_codecs.py
    python -m server.javelin.test_codecs
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

from .v3_response import V3RegistrationResponse, encode, make_session_token
from .v3_request import parse_v3_request, serialize_v3_request, TRAILER, EXPECTED_BODY_LEN
from .replay_store import ReplayStore


# ---------------------------------------------------------------------------
# V3RegistrationResponse / encode
# ---------------------------------------------------------------------------

def test_encode_default_length():
    assert len(encode(V3RegistrationResponse())) == 88


def test_encode_preamble_and_type():
    assert encode(V3RegistrationResponse())[:3] == b"\x00\x01\x03"


def test_encode_error_code_zero():
    assert encode(V3RegistrationResponse())[3:7] == b"\x00\x00\x00\x00"


def test_encode_session_token_length_prefix():
    assert encode(V3RegistrationResponse())[0x0F] == 0x20  # 32 decimal


def test_encode_session_token_position():
    token = b"A" * 32
    blob = encode(V3RegistrationResponse(session_token=token))
    assert blob[0x10:0x30] == token


def test_encode_server_version_present():
    assert b"Javelin" in encode(V3RegistrationResponse())


def test_encode_nonzero_error_code():
    blob = encode(V3RegistrationResponse(error_code=1))
    assert int.from_bytes(blob[3:7], "big", signed=True) == 1


def test_encode_length_scales_with_server_version():
    # "X" is 1 byte; default is 35 bytes → difference is 34
    short = encode(V3RegistrationResponse(server_version="X"))
    default = encode(V3RegistrationResponse())
    assert len(default) - len(short) == 34


def test_validation_session_token_too_short():
    with pytest.raises(ValueError, match="session_token"):
        V3RegistrationResponse(session_token=b"tooshort")


def test_validation_session_token_too_long():
    with pytest.raises(ValueError, match="session_token"):
        V3RegistrationResponse(session_token=b"X" * 33)


def test_validation_mystery8_wrong_length():
    with pytest.raises(ValueError, match="mystery8"):
        V3RegistrationResponse(session_token=b"A" * 32, mystery8=b"\x00" * 7)


def test_validation_trailer_wrong_length():
    with pytest.raises(ValueError, match="trailer"):
        V3RegistrationResponse(session_token=b"A" * 32, trailer=b"\x00" * 3)


def test_validation_server_version_too_long():
    with pytest.raises(ValueError, match="server_version"):
        V3RegistrationResponse(session_token=b"A" * 32, server_version="X" * 256)


def test_make_session_token_length():
    assert len(make_session_token()) == 32


def test_make_session_token_ascii():
    assert make_session_token().isascii()


def test_make_session_token_unique():
    assert make_session_token() != make_session_token()


# ---------------------------------------------------------------------------
# LevelInfoChangedMsg
# ---------------------------------------------------------------------------

from .level_info_changed import (  # noqa: E402
    LevelInfoChangedMsg,
    encode as encode_level_info,
    MIN_WIRE_SIZE as LIC_MIN_WIRE_SIZE,
)
import struct as _struct  # noqa: E402


def test_level_info_empty_min_size():
    blob = encode_level_info(LevelInfoChangedMsg())
    assert len(blob) == LIC_MIN_WIRE_SIZE == 48


def test_level_info_empty_strings_are_zero_length():
    blob = encode_level_info(LevelInfoChangedMsg())
    # First u32 is length of m_levelName, second u32 is length of m_someOtherName
    assert blob[0:4] == b"\x00\x00\x00\x00"
    assert blob[4:8] == b"\x00\x00\x00\x00"


def test_level_info_string_length_prefix_and_payload():
    msg = LevelInfoChangedMsg(level_name="alpha", other_name="bravo_x")
    blob = encode_level_info(msg)
    # m_levelName: 4-byte LE length then bytes
    assert blob[0:4] == _struct.pack("<I", 5)
    assert blob[4:9] == b"alpha"
    # m_someOtherName follows immediately
    assert blob[9:13] == _struct.pack("<I", 7)
    assert blob[13:20] == b"bravo_x"


def test_level_info_quad_at_correct_offset_after_strings():
    msg = LevelInfoChangedMsg(level_name="ab", other_name="cd",
                              quad=(1, 2, 3, 4))
    blob = encode_level_info(msg)
    # 4 (len_a) + 2 (a) + 4 (len_b) + 2 (b) = 12 bytes before the quad
    assert blob[12:28] == _struct.pack("<IIII", 1, 2, 3, 4)


def test_level_info_field_60_at_correct_offset():
    msg = LevelInfoChangedMsg(field_60=0xCAFEBABE_DEADBEEF)
    blob = encode_level_info(msg)
    # 4 + 4 + 16 = 24 bytes before field_60
    assert blob[24:32] == _struct.pack("<Q", 0xCAFEBABE_DEADBEEF)


def test_level_info_extended_count_at_correct_offset():
    blob = encode_level_info(LevelInfoChangedMsg())
    # 4 + 4 + 16 + 8 = 32 bytes before extended_count u32
    assert blob[32:36] == b"\x00\x00\x00\x00"


def test_level_info_flag_bytes_at_correct_offset():
    msg = LevelInfoChangedMsg(field_a0=0x11, level_is_loading=0x22,
                              is_in_game_transition=0x33, field_a3=0x44)
    blob = encode_level_info(msg)
    # 4 + 4 + 16 + 8 + 4 = 36 bytes before the 4 flag bytes
    assert blob[36:40] == bytes((0x11, 0x22, 0x33, 0x44))


def test_level_info_client_context_id_at_correct_offset():
    msg = LevelInfoChangedMsg(client_context_instance_id=0x9876543210)
    blob = encode_level_info(msg)
    # 4 + 4 + 16 + 8 + 4 + 4 = 40 bytes before m_clientContextInstanceId
    assert blob[40:48] == _struct.pack("<Q", 0x9876543210)


def test_level_info_full_size_with_strings():
    msg = LevelInfoChangedMsg(level_name="hello", other_name="world!",
                              client_context_instance_id=42)
    blob = encode_level_info(msg)
    # Min + len("hello") + len("world!")
    assert len(blob) == LIC_MIN_WIRE_SIZE + 5 + 6


def test_level_info_validates_quad_length():
    with pytest.raises(ValueError, match="quad must have 4 elements"):
        LevelInfoChangedMsg(quad=(1, 2, 3))  # type: ignore[arg-type]


def test_level_info_validates_u8_flags():
    with pytest.raises(ValueError, match="must fit in u8"):
        LevelInfoChangedMsg(level_is_loading=0x100)


def test_level_info_validates_u32_quad():
    with pytest.raises(ValueError, match="must fit in u32"):
        LevelInfoChangedMsg(quad=(1, 2, 3, 0x1_0000_0000))


def test_level_info_validates_u64_field_60():
    with pytest.raises(ValueError, match="must fit in u64"):
        LevelInfoChangedMsg(field_60=2 ** 64)


def test_level_info_extended_count_nonzero_not_supported():
    with pytest.raises(NotImplementedError, match="m_extendedField"):
        LevelInfoChangedMsg(extended_count=1)


def test_level_info_default_flags_match_handler_recipe():
    # The handler convention is level_is_loading=1 and
    # is_in_game_transition=1; verify our defaults match.
    msg = LevelInfoChangedMsg()
    assert msg.level_is_loading == 1
    assert msg.is_in_game_transition == 1
    assert msg.field_a0 == 0
    assert msg.field_a3 == 0


# ---------------------------------------------------------------------------
# v3_request — error paths (no capture file needed)
# ---------------------------------------------------------------------------

def test_parse_v3_request_wrong_length():
    with pytest.raises(ValueError, match=str(EXPECTED_BODY_LEN)):
        parse_v3_request(b"\x00" * 100)


def test_parse_v3_request_wrong_trailer():
    body = b"\x00" * (EXPECTED_BODY_LEN - len(TRAILER)) + b"\xFF" * len(TRAILER)
    with pytest.raises(ValueError, match="trailer"):
        parse_v3_request(body)


# ---------------------------------------------------------------------------
# v3_request — round-trip from real capture (skipped if file is absent)
# ---------------------------------------------------------------------------

_HEX_PATH = (
    Path(__file__).resolve().parents[2]
    / "analysis" / "v3_request" / "all_v3_request_retries.hex"
)


@pytest.mark.skipif(
    not _HEX_PATH.exists(),
    reason="analysis/v3_request/all_v3_request_retries.hex not present",
)
def test_v3_request_roundtrip():
    lines = _HEX_PATH.read_text().splitlines()
    body = bytes.fromhex(lines[1].strip())[11:]  # strip 11-byte Javelin header
    msg = parse_v3_request(body)
    assert msg.sdk_name == "Javelin"
    assert serialize_v3_request(msg) == body


# ---------------------------------------------------------------------------
# ReplayStore
# ---------------------------------------------------------------------------

# R-direction type-marker bytes for type_id=0x3:
#   byte2 = (0x3 & 0x3F) | 0x80 = 0x83,  byte3 = (0x3 >> 6) = 0x00
# W-direction markers are not validated, so any bytes work there.
_DUMP = """\
================================================================================
seq: 0x1 (1)
type: 0x3 (3)
direction: R
size: 4 bytes
raw:
00000000  00 01 83 00                                       |....|
================================================================================
seq: 0x2 (2)
type: 0x13 (19)
direction: W
size: 6 bytes
raw:
00000000  00 01 93 00 XX 00                                 |....X.|
================================================================================
"""


def _store(text: str) -> ReplayStore:
    """Build a ReplayStore from an in-memory string without a permanent file."""
    fd, path_str = tempfile.mkstemp(suffix=".txt")
    path = Path(path_str)
    try:
        os.write(fd, text.encode("utf-8"))
        os.close(fd)
        return ReplayStore(path)
    finally:
        path.unlink(missing_ok=True)


def test_store_message_count():
    assert len(_store(_DUMP).messages) == 2


def test_store_get_by_seq():
    msg = _store(_DUMP).get(0x1)
    assert msg is not None
    assert msg.type_id == 0x3
    assert msg.direction == "R"


def test_store_body_bytes():
    assert _store(_DUMP).get(0x1).body == bytes([0x00, 0x01, 0x83, 0x00])


def test_store_clean_message_no_redaction():
    assert not _store(_DUMP).get(0x1).has_redaction


def test_store_redacted_message_tracked():
    msg = _store(_DUMP).get(0x2)
    assert msg.has_redaction
    assert msg.redacted_spans == [(4, 1)]


def test_store_messages_sorted_by_seq():
    reversed_dump = """\
================================================================================
seq: 0x5 (5)
type: 0x3 (3)
direction: R
size: 4 bytes
raw:
00000000  00 01 83 00                                       |....|
================================================================================
seq: 0x2 (2)
type: 0x3 (3)
direction: R
size: 4 bytes
raw:
00000000  00 01 83 00                                       |....|
================================================================================
"""
    seqs = [m.seq for m in _store(reversed_dump).messages]
    assert seqs == sorted(seqs)


def test_store_messages_in_range():
    r_only = _store(_DUMP).messages_in_range(0x1, 0x2, direction="R")
    assert len(r_only) == 1
    assert r_only[0].seq == 0x1


def test_store_r_direction_marker_mismatch_warns():
    bad = """\
================================================================================
seq: 0x1 (1)
type: 0x3 (3)
direction: R
size: 4 bytes
raw:
00000000  FF FF FF FF                                       |....|
================================================================================
"""
    store = _store(bad)
    assert len(store.validation_warnings) == 1
    assert "marker mismatch" in store.validation_warnings[0]


def test_store_body_length_mismatch_raises():
    bad = """\
================================================================================
seq: 0x1 (1)
type: 0x3 (3)
direction: R
size: 8 bytes
raw:
00000000  00 01 83 00                                       |....|
================================================================================
"""
    with pytest.raises(ValueError, match="body length"):
        _store(bad)


def test_replay_messages_after_v3_filters_correctly():
    # type 0x15d R marker: byte2=(0x1d|0x80)=0x9d, byte3=(0x15d>>6)=0x05
    dump = """\
================================================================================
seq: 0x2 (2)
type: 0x15d (349)
direction: R
size: 4 bytes
raw:
00000000  00 01 9d 05                                       |....|
================================================================================
seq: 0x3 (3)
type: 0x15d (349)
direction: W
size: 4 bytes
raw:
00000000  00 01 9d 05                                       |....|
================================================================================
seq: 0x4 (4)
type: 0x15d (349)
direction: R
size: 5 bytes
raw:
00000000  00 01 9d 05 XX                                    |....X|
================================================================================
"""
    replayable = _store(dump).replay_messages_after_v3()
    # Only seq 0x2: R, clean, in range 0x2..0x24
    assert len(replayable) == 1
    assert replayable[0].seq == 0x2


# ---------------------------------------------------------------------------
# Direct-run shim
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    failures = 0
    skip_roundtrip = not _HEX_PATH.exists()
    for name, fn in list(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        if name == "test_v3_request_roundtrip" and skip_roundtrip:
            print(f"[skip] {name}  (capture file absent)")
            continue
        try:
            fn()
            print(f"[+] {name}")
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    if failures:
        sys.exit(failures)
    print("\nAll codec tests passed.")
