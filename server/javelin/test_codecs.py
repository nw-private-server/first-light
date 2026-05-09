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
    decode as decode_level_info,
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
# PlayerManagerSelfIdentificationMsg
# ---------------------------------------------------------------------------

from .self_ident import (  # noqa: E402
    PlayerManagerSelfIdentificationMsg,
    encode as encode_self_ident,
    decode as decode_self_ident,
    MIN_WIRE_SIZE as SI_MIN_WIRE_SIZE,
)


def test_self_ident_empty_min_size():
    blob = encode_self_ident(PlayerManagerSelfIdentificationMsg())
    assert len(blob) == SI_MIN_WIRE_SIZE == 21


def test_self_ident_field_0_position():
    msg = PlayerManagerSelfIdentificationMsg(field_0=0xDEADBEEF)
    blob = encode_self_ident(msg)
    assert blob[0:4] == _struct.pack("<I", 0xDEADBEEF)


def test_self_ident_empty_vector_length_prefix_zero():
    blob = encode_self_ident(PlayerManagerSelfIdentificationMsg())
    # offset 0..3 = field_0, offset 4..7 = vector length
    assert blob[4:8] == b"\x00\x00\x00\x00"


def test_self_ident_vector_length_prefix_and_elements():
    msg = PlayerManagerSelfIdentificationMsg(field_08=(1, 2, 3))
    blob = encode_self_ident(msg)
    assert blob[4:8] == _struct.pack("<I", 3)
    assert blob[8:12] == _struct.pack("<I", 1)
    assert blob[12:16] == _struct.pack("<I", 2)
    assert blob[16:20] == _struct.pack("<I", 3)


def test_self_ident_debug_flag_offset_after_vector():
    msg = PlayerManagerSelfIdentificationMsg(field_08=(0xa, 0xb), debug_flag=1)
    blob = encode_self_ident(msg)
    # 4 (field_0) + 4 (length) + 4*2 (two u32s) = 16 bytes before debug_flag
    assert blob[16:17] == bytes((1,))


def test_self_ident_field_2c_after_debug_flag():
    msg = PlayerManagerSelfIdentificationMsg(field_2c=0x1122334455667788)
    blob = encode_self_ident(msg)
    # 4 + 4 + 0 + 1 = 9 bytes before field_2c (no padding on the wire)
    assert blob[9:17] == _struct.pack("<Q", 0x1122334455667788)


def test_self_ident_field_34_at_end():
    msg = PlayerManagerSelfIdentificationMsg(field_34=0xAABBCCDD)
    blob = encode_self_ident(msg)
    # 4 + 4 + 0 + 1 + 8 = 17 bytes before field_34
    assert blob[17:21] == _struct.pack("<I", 0xAABBCCDD)


def test_self_ident_full_size_with_vector():
    msg = PlayerManagerSelfIdentificationMsg(field_08=(0,) * 5)
    blob = encode_self_ident(msg)
    assert len(blob) == SI_MIN_WIRE_SIZE + 4 * 5


def test_self_ident_validates_u32_field_0():
    with pytest.raises(ValueError, match="field_0 must fit in u32"):
        PlayerManagerSelfIdentificationMsg(field_0=2 ** 32)


def test_self_ident_validates_u8_debug_flag():
    with pytest.raises(ValueError, match="debug_flag must fit in u8"):
        PlayerManagerSelfIdentificationMsg(debug_flag=256)


def test_self_ident_validates_u64_field_2c():
    with pytest.raises(ValueError, match="field_2c must fit in u64"):
        PlayerManagerSelfIdentificationMsg(field_2c=2 ** 64)


def test_self_ident_validates_vector_element_range():
    with pytest.raises(ValueError, match=r"field_08\[1\] must fit in u32"):
        PlayerManagerSelfIdentificationMsg(field_08=(0, 2 ** 32))


def test_self_ident_default_debug_flag_is_zero():
    # Production servers must send debug_flag=0; verify default.
    assert PlayerManagerSelfIdentificationMsg().debug_flag == 0


def test_self_ident_accepts_list_for_field_08():
    # __post_init__ normalizes list -> tuple
    msg = PlayerManagerSelfIdentificationMsg(field_08=[10, 20, 30])
    assert msg.field_08 == (10, 20, 30)


# ---------------------------------------------------------------------------
# Round-trip / decoder tests
# ---------------------------------------------------------------------------


def test_level_info_roundtrip_default():
    msg = LevelInfoChangedMsg()
    assert decode_level_info(encode_level_info(msg)) == msg


def test_level_info_roundtrip_with_strings_and_quad():
    msg = LevelInfoChangedMsg(
        level_name="NewWorld_Aeternum",
        other_name="ServerAlpha-EU",
        quad=(1, 2, 3, 4),
        field_60=0x1122334455667788,
        field_a0=0x10, level_is_loading=0x20,
        is_in_game_transition=0x30, field_a3=0x40,
        client_context_instance_id=0x9876543210,
    )
    assert decode_level_info(encode_level_info(msg)) == msg


def test_level_info_roundtrip_unicode_strings():
    msg = LevelInfoChangedMsg(level_name="日本語", other_name="emoji-🦄-allowed")
    assert decode_level_info(encode_level_info(msg)) == msg


def test_level_info_decode_truncated_levelname_prefix():
    with pytest.raises(ValueError, match="truncated string length prefix"):
        decode_level_info(b"\x00\x00")


def test_level_info_decode_truncated_levelname_body():
    # Declares 100-byte string but only provides 5
    bad = _struct.pack("<I", 100) + b"hello"
    with pytest.raises(ValueError, match="truncated string body"):
        decode_level_info(bad)


def test_level_info_decode_trailing_bytes_rejected():
    blob = encode_level_info(LevelInfoChangedMsg()) + b"\xFF"
    with pytest.raises(ValueError, match="trailing"):
        decode_level_info(blob)


def test_level_info_decode_nonzero_extended_count_raises():
    # Build a buffer that decodes through up to extended_count = 5 then errors
    parts = [
        _struct.pack("<I", 0),     # m_levelName: empty
        _struct.pack("<I", 0),     # m_someOtherName: empty
        _struct.pack("<IIII", 0, 0, 0, 0),
        _struct.pack("<Q", 0),
        _struct.pack("<I", 5),     # extended_count = 5 → not yet supported
        bytes(4),
        _struct.pack("<Q", 0),
    ]
    with pytest.raises(NotImplementedError, match="non-empty m_extendedField"):
        decode_level_info(b"".join(parts))


def test_self_ident_roundtrip_default():
    msg = PlayerManagerSelfIdentificationMsg()
    assert decode_self_ident(encode_self_ident(msg)) == msg


def test_self_ident_roundtrip_with_vector():
    msg = PlayerManagerSelfIdentificationMsg(
        field_0=0xAABBCCDD,
        field_08=(1, 2, 3, 4, 5),
        debug_flag=0,
        field_2c=0xCAFEBABEDEADBEEF,
        field_34=0x12345678,
    )
    assert decode_self_ident(encode_self_ident(msg)) == msg


def test_self_ident_decode_too_short():
    with pytest.raises(ValueError, match="buffer too short"):
        decode_self_ident(b"\x00" * 10)


def test_self_ident_decode_truncated_vector():
    # Pad to MIN_WIRE_SIZE so the upfront size check passes, then
    # trigger the targeted vector-body-truncation error: vec_len = 100
    # claims 400 bytes of u32 elements but the buffer's body is much smaller.
    bad = _struct.pack("<I", 0) + _struct.pack("<I", 100) + b"\x00" * (
        SI_MIN_WIRE_SIZE - 8
    )
    with pytest.raises(ValueError, match="truncated vector body"):
        decode_self_ident(bad)


def test_self_ident_decode_trailing_bytes_rejected():
    blob = encode_self_ident(PlayerManagerSelfIdentificationMsg()) + b"\xFF\xFF"
    with pytest.raises(ValueError, match="trailing"):
        decode_self_ident(blob)


def test_self_ident_decode_preserves_vector_as_tuple():
    blob = encode_self_ident(PlayerManagerSelfIdentificationMsg(field_08=(7, 8, 9)))
    decoded = decode_self_ident(blob)
    assert decoded.field_08 == (7, 8, 9)
    assert isinstance(decoded.field_08, tuple)


# ---------------------------------------------------------------------------
# Integration: SelfIdent + LevelInfoChanged combined
# ---------------------------------------------------------------------------
# Constructs a server-emit-ready bundle of both ClientMessagesTrait bodies,
# verifies sizes + delimiting offsets, exercises both encoders together.
# Does NOT modify rep_responder (the live emission path is replay-based and
# wiring fresh encoders in requires runtime validation of an unresolved
# wire-vs-in-memory size conflict — see post-v3-sequence.md note ¹ and the
# "SECONDARY CAVEAT" in self_ident.py).


def test_combined_sequence_well_formed():
    """Build a SelfIdent then LevelInfoChanged body bundle. Verify the two
    bodies concatenate cleanly with the expected offsets — i.e. the byte
    stream a Carrier framer would consume after wrapping each body in its
    own typed envelope."""
    si_body = encode_self_ident(PlayerManagerSelfIdentificationMsg(
        field_0=0x12345678,
        field_08=(0xa, 0xb, 0xc),
        debug_flag=0,
        field_2c=0xCAFEBABEDEADBEEF,
        field_34=0x44332211,
    ))
    lic_body = encode_level_info(LevelInfoChangedMsg(
        level_name="NewWorld_Aeternum",
        other_name="ServerAlpha-EU",
        client_context_instance_id=0x4242,
    ))

    # Each body is independently parseable. Concatenation is just appending.
    bundle = si_body + lic_body

    # SelfIdent expected size: min + 3 vector elements
    assert len(si_body) == SI_MIN_WIRE_SIZE + 3 * 4

    # LevelInfoChanged expected size: min + len("NewWorld_Aeternum") +
    # len("ServerAlpha-EU")
    assert len(lic_body) == LIC_MIN_WIRE_SIZE + 17 + 14

    # Bundle is the sum
    assert len(bundle) == len(si_body) + len(lic_body)

    # SelfIdent's first 4 bytes are field_0; verify still positioned correctly
    # in the bundle
    assert bundle[0:4] == _struct.pack("<I", 0x12345678)

    # LevelInfoChanged's first 4 bytes (= u32 length of m_levelName) appear
    # right after SelfIdent's full body
    assert bundle[len(si_body):len(si_body) + 4] == _struct.pack("<I", 17)
    # And the level_name bytes follow
    assert bundle[len(si_body) + 4:len(si_body) + 4 + 17] == b"NewWorld_Aeternum"


def test_combined_sequence_production_safe_defaults():
    """Both encoders' defaults match the 'production server' recipe:
    SelfIdent.debug_flag = 0 (skips the debug branch); LevelInfoChanged
    flags include level_is_loading = 1 and is_in_game_transition = 1
    (allows the state-14 → 13 transition to fire)."""
    si = PlayerManagerSelfIdentificationMsg()
    assert si.debug_flag == 0

    lic = LevelInfoChangedMsg()
    assert lic.level_is_loading == 1
    assert lic.is_in_game_transition == 1


def test_combined_sequence_min_total_size():
    """Empty / default both encoders. Verify the minimum combined wire size
    is exactly SI_MIN + LIC_MIN — the floor a server must allocate for the
    two bodies before adding any actual content."""
    si_body = encode_self_ident(PlayerManagerSelfIdentificationMsg())
    lic_body = encode_level_info(LevelInfoChangedMsg())
    assert len(si_body) + len(lic_body) == SI_MIN_WIRE_SIZE + LIC_MIN_WIRE_SIZE
    assert SI_MIN_WIRE_SIZE + LIC_MIN_WIRE_SIZE == 21 + 48


# ---------------------------------------------------------------------------
# SessionIdentityBeacon (type 0x1b88)
# ---------------------------------------------------------------------------

from .session_identity_beacon import (  # noqa: E402
    SessionIdentityBeacon,
    encode as encode_sib,
    decode as decode_sib,
    TYPED_BODY_SIZE as SIB_TYPED_BODY_SIZE,
    TYPE_HEADER as SIB_TYPE_HEADER,
)


_CAPTURED_SIB = bytes.fromhex(
    "0001886e"
    "e2640b7ce5408036bf85314bbc4a951a"
    + "00" * 22
)


def test_sib_decode_captured_bytes():
    """The 23 identical captures in the replay all decode to the same UUID."""
    msg = decode_sib(_CAPTURED_SIB)
    assert msg.session_uuid.hex() == "e2640b7ce5408036bf85314bbc4a951a"


def test_sib_round_trip():
    msg = decode_sib(_CAPTURED_SIB)
    assert encode_sib(msg) == _CAPTURED_SIB


def test_sib_encode_default_size_42():
    uuid = bytes(range(16))
    blob = encode_sib(SessionIdentityBeacon(session_uuid=uuid))
    assert len(blob) == SIB_TYPED_BODY_SIZE == 42
    assert blob[:4] == SIB_TYPE_HEADER
    assert blob[4:20] == uuid
    assert blob[20:42] == bytes(22)


def test_sib_validates_uuid_length():
    with pytest.raises(ValueError, match="session_uuid"):
        SessionIdentityBeacon(session_uuid=b"\x00" * 15)
    with pytest.raises(ValueError, match="session_uuid"):
        SessionIdentityBeacon(session_uuid=b"\x00" * 17)


def test_sib_decode_wrong_size():
    with pytest.raises(ValueError, match="expected exactly 42"):
        decode_sib(_CAPTURED_SIB + b"\xFF")


def test_sib_decode_wrong_type_header():
    bad = b"\x00\x01\x99\x99" + _CAPTURED_SIB[4:]
    with pytest.raises(ValueError, match="type header mismatch"):
        decode_sib(bad)


def test_sib_decode_nonzero_padding():
    bad = _CAPTURED_SIB[:41] + b"\xFF"
    with pytest.raises(ValueError, match="padding non-zero"):
        decode_sib(bad)


def test_sib_decode_all_23_replay_copies_identical():
    """All 23 captures of this type in the replay are byte-identical;
    decoding any of them must give the same UUID."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    sibs = [m for m in store.messages if m.type_id == 0x1b88]
    assert len(sibs) > 0
    uuids = {decode_sib(m.body).session_uuid for m in sibs}
    assert len(uuids) == 1, f"expected 1 unique UUID, got {len(uuids)}"


# ---------------------------------------------------------------------------
# SessionMessageA4 (type 0xa4 small variant)
# ---------------------------------------------------------------------------

from .session_message_a4 import (  # noqa: E402
    SessionMessageA4,
    encode as encode_a4,
    decode as decode_a4,
    TYPED_BODY_SIZE as A4_TYPED_BODY_SIZE,
    TYPE_HEADER as A4_TYPE_HEADER,
)

_CAPTURED_A4 = bytes.fromhex(
    "0001a402"
    "1a954abc4b3185bfbe37c3d8592618e0"
)


def test_a4_decode_captured_bytes():
    msg = decode_a4(_CAPTURED_A4)
    assert msg.session_uuid.hex() == "1a954abc4b3185bfbe37c3d8592618e0"


def test_a4_round_trip():
    msg = decode_a4(_CAPTURED_A4)
    assert encode_a4(msg) == _CAPTURED_A4


def test_a4_encode_size_20():
    blob = encode_a4(SessionMessageA4(session_uuid=bytes(range(16))))
    assert len(blob) == A4_TYPED_BODY_SIZE == 20
    assert blob[:4] == A4_TYPE_HEADER
    assert blob[4:20] == bytes(range(16))


def test_a4_validates_uuid_length():
    with pytest.raises(ValueError, match="session_uuid"):
        SessionMessageA4(session_uuid=b"\x00" * 15)


def test_a4_decode_wrong_size_rejects():
    with pytest.raises(ValueError, match="20 bytes"):
        decode_a4(_CAPTURED_A4 + b"\xFF")


def test_a4_decode_wrong_type_header():
    bad = b"\x00\x01\x99\x99" + _CAPTURED_A4[4:]
    with pytest.raises(ValueError, match="type header"):
        decode_a4(bad)


def test_a4_both_replay_copies_decode_to_same_uuid():
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    a4s = [m for m in store.messages if m.type_id == 0xa4]
    assert len(a4s) == 2
    uuids = {decode_a4(m.body).session_uuid for m in a4s}
    assert len(uuids) == 1


# ---------------------------------------------------------------------------
# InitMessage18A6 (type 0x18a6)
# ---------------------------------------------------------------------------

from .init_message_18a6 import (  # noqa: E402
    InitMessage18A6,
    encode as encode_18a6,
    decode as decode_18a6,
    TYPED_BODY_SIZE as I18A6_TYPED_BODY_SIZE,
    TYPE_HEADER as I18A6_TYPE_HEADER,
    DEFAULT_BUILD_VERSION as I18A6_DEFAULT_BUILD_VERSION,
    DEFAULT_FLAGS as I18A6_DEFAULT_FLAGS,
)

_CAPTURED_18A6_C1 = bytes.fromhex(
    "0001a662"
    "f8cbed57c68b18f4"
    "bf85314bbc4a951a"
    "01010000"
    "9cfa58617814 69f2".replace(" ", "")
    + "65030000"
    + "000002"
    + "01"
)


def test_18a6_decode_captured_bytes():
    msg = decode_18a6(_CAPTURED_18A6_C1)
    assert msg.first_uuid_half.hex() == "f8cbed57c68b18f4"
    assert msg.session_uuid_lower.hex() == "bf85314bbc4a951a"
    assert msg.second_id.hex() == "9cfa58617814 69f2".replace(" ", "")
    assert msg.flags == I18A6_DEFAULT_FLAGS
    assert msg.build_version == I18A6_DEFAULT_BUILD_VERSION  # 0x365 = 869
    assert msg.counter == 1


def test_18a6_round_trip():
    msg = decode_18a6(_CAPTURED_18A6_C1)
    assert encode_18a6(msg) == _CAPTURED_18A6_C1


def test_18a6_encode_size_40():
    blob = encode_18a6(InitMessage18A6(
        first_uuid_half=bytes(8),
        session_uuid_lower=bytes(8),
        second_id=bytes(8),
        counter=1,
    ))
    assert len(blob) == I18A6_TYPED_BODY_SIZE == 40
    assert blob[:4] == I18A6_TYPE_HEADER


def test_18a6_counter_increments_in_replay():
    """The 4 captured copies have counters 1, 2, 3, 4 — verify the
    decoder reads them correctly."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msgs = [m for m in store.messages if m.type_id == 0x18a6]
    counters = [decode_18a6(m.body).counter for m in msgs]
    assert counters == [1, 2, 3, 4]


def test_18a6_validates_field_widths():
    with pytest.raises(ValueError, match="first_uuid_half"):
        InitMessage18A6(
            first_uuid_half=bytes(7),
            session_uuid_lower=bytes(8),
            second_id=bytes(8),
        )
    with pytest.raises(ValueError, match="session_uuid_lower"):
        InitMessage18A6(
            first_uuid_half=bytes(8),
            session_uuid_lower=bytes(9),
            second_id=bytes(8),
        )
    with pytest.raises(ValueError, match="second_id"):
        InitMessage18A6(
            first_uuid_half=bytes(8),
            session_uuid_lower=bytes(8),
            second_id=bytes(7),
        )


def test_18a6_validates_counter_fits_u8():
    with pytest.raises(ValueError, match="counter"):
        InitMessage18A6(
            first_uuid_half=bytes(8),
            session_uuid_lower=bytes(8),
            second_id=bytes(8),
            counter=256,
        )


def test_18a6_decode_wrong_size_rejects():
    with pytest.raises(ValueError, match="40"):
        decode_18a6(_CAPTURED_18A6_C1 + b"\xFF")


def test_18a6_decode_wrong_type_header():
    bad = b"\x00\x01\x99\x99" + _CAPTURED_18A6_C1[4:]
    with pytest.raises(ValueError, match="type header"):
        decode_18a6(bad)


def test_18a6_session_uuid_lower_matches_a4_lower_half():
    """Cross-codec invariant: 0x18a6's session_uuid_lower (bytes
    +0x08..+0x0F of payload) must match the lower 8 bytes of
    0xa4's session_uuid in the same capture. This is the
    "shared session-family identifier" finding from
    analysis/replay_message_inventory.md."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    a4 = next(m for m in store.messages if m.type_id == 0xa4)
    i18a6 = next(m for m in store.messages if m.type_id == 0x18a6)

    a4_msg = decode_a4(a4.body)
    i18a6_msg = decode_18a6(i18a6.body)

    # The 0xa4 session_uuid is 16 bytes laid out [upper8][lower8].
    # The 0x18a6 session_uuid_lower is the same lower 8 bytes.
    # Per the captures: 0xa4 session_uuid =
    #   1a954abc4b3185bf  be37c3d8592618e0
    # 0x18a6 session_uuid_lower = bf85314bbc4a951a
    # That's the FIRST 8 bytes of 0xa4's UUID, BYTE-REVERSED:
    #   1a954abc4b3185bf -> bf85314bbc4a951a
    # i.e. the session UUID stored in 0xa4 in big-endian / mixed-endian
    # form is reversed in the 0x18a6 payload (or vice versa).
    a4_first8 = a4_msg.session_uuid[:8]
    assert a4_first8 == bytes(reversed(i18a6_msg.session_uuid_lower)), (
        f"expected 0x18a6 session_uuid_lower ({i18a6_msg.session_uuid_lower.hex()}) "
        f"to be byte-reversal of 0xa4's first 8 bytes ({a4_first8.hex()})"
    )


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
