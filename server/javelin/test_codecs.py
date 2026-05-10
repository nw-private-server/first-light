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
# SessionClockBeacon (type 0x14f)
# ---------------------------------------------------------------------------

from .session_clock_beacon import (  # noqa: E402
    SessionClockBeacon,
    encode as encode_clock,
    decode as decode_clock,
    TYPED_BODY_SIZE as CLOCK_TYPED_BODY_SIZE,
    TYPE_HEADER as CLOCK_TYPE_HEADER,
)


_CAPTURED_CLOCK = bytes.fromhex("00018f05" "0b888d68" "7b13001a")


def test_clock_decode_captured_first_message():
    msg = decode_clock(_CAPTURED_CLOCK)
    assert msg.session_clock == 0x0b888d68
    assert msg.nonce == 0x7b13001a


def test_clock_round_trip():
    msg = decode_clock(_CAPTURED_CLOCK)
    assert encode_clock(msg) == _CAPTURED_CLOCK


def test_clock_encode_size_12():
    blob = encode_clock(SessionClockBeacon(session_clock=0, nonce=0))
    assert len(blob) == CLOCK_TYPED_BODY_SIZE == 12
    assert blob[:4] == CLOCK_TYPE_HEADER


def test_clock_validates_u32_range():
    with pytest.raises(ValueError, match="session_clock"):
        SessionClockBeacon(session_clock=2**32, nonce=0)
    with pytest.raises(ValueError, match="nonce"):
        SessionClockBeacon(session_clock=0, nonce=2**32)


def test_clock_decode_wrong_size_rejects():
    with pytest.raises(ValueError, match="12 bytes"):
        decode_clock(_CAPTURED_CLOCK + b"\x00")


def test_clock_decode_wrong_type_header():
    bad = b"\x00\x01\x99\x99" + _CAPTURED_CLOCK[4:]
    with pytest.raises(ValueError, match="type header"):
        decode_clock(bad)


def test_clock_replay_session_clock_progression():
    """The 4 captured copies of 0x14f should decode with session_clock
    values [0x0b888d68, 0x0b888d68, 0x0b888d69, 0x0b888d69] — the value
    transitions between seqs 0x27 and 0x3c. This confirms the wake-66
    finding that 0x14f's payload bytes 0..3 are a slow-incrementing
    per-session timer."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msgs = sorted(
        (m for m in store.messages if m.type_id == 0x14f),
        key=lambda m: m.seq,
    )
    clocks = [decode_clock(m.body).session_clock for m in msgs]
    assert clocks == [0x0b888d68, 0x0b888d68, 0x0b888d69, 0x0b888d69]


def test_clock_replay_nonces_all_different():
    """The 4 captured 0x14f nonces should all be distinct — each
    message carries a fresh nonce."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msgs = [m for m in store.messages if m.type_id == 0x14f]
    nonces = [decode_clock(m.body).nonce for m in msgs]
    assert len(set(nonces)) == len(nonces)


# ---------------------------------------------------------------------------
# mystery8 decomposition (V3 response field +0x07..+0x0e)
# ---------------------------------------------------------------------------

from .v3_response import (  # noqa: E402
    DEFAULT_MYSTERY8,
    DEFAULT_MYSTERY8_SESSION_CLOCK,
    DEFAULT_MYSTERY8_NONCE,
    make_mystery8,
    parse_mystery8,
)


def test_mystery8_default_unchanged():
    """Backward compat: the default 8-byte value must equal the
    captured bytes that v3_response.py shipped with."""
    assert DEFAULT_MYSTERY8.hex() == "0b888d68706c415b"


def test_mystery8_make_then_parse_roundtrip():
    blob = make_mystery8(0x0b888d68, 0x706c415b)
    assert blob == DEFAULT_MYSTERY8
    clock, nonce = parse_mystery8(blob)
    assert clock == DEFAULT_MYSTERY8_SESSION_CLOCK == 0x0b888d68
    assert nonce == DEFAULT_MYSTERY8_NONCE == 0x706c415b


def test_mystery8_make_validates_u32():
    with pytest.raises(ValueError, match="session_clock"):
        make_mystery8(2**32, 0)
    with pytest.raises(ValueError, match="nonce"):
        make_mystery8(0, 2**32)


def test_mystery8_parse_validates_length():
    with pytest.raises(ValueError, match="8 bytes"):
        parse_mystery8(b"\x00" * 7)


def test_mystery8_session_clock_matches_clock_beacon():
    """Cross-codec invariant: the V3 response's mystery8 session_clock
    is the same value 0x14f's first capture carries. This is the
    wake-66 finding made testable."""
    from .session_clock_beacon import decode as decode_clock_local
    captured_clock_msg = bytes.fromhex("00018f05" "0b888d68" "7b13001a")
    clock_msg = decode_clock_local(captured_clock_msg)
    mystery8_clock, _ = parse_mystery8(DEFAULT_MYSTERY8)
    assert clock_msg.session_clock == mystery8_clock == 0x0b888d68


# ---------------------------------------------------------------------------
# Heartbeat 0x15d (R ping + W ack pair)
# ---------------------------------------------------------------------------

from .heartbeat_15d import (  # noqa: E402
    HeartbeatPing15D,
    HeartbeatAck15D,
    encode_ping as encode_15d_ping,
    decode_ping as decode_15d_ping,
    encode_ack as encode_15d_ack,
    decode_ack as decode_15d_ack,
    PING_TYPED_BODY_SIZE,
    ACK_TYPED_BODY_SIZE,
)


def test_15d_ping_round_trip():
    captured = bytes.fromhex("00019d05" "00036ef6" "af912d74")
    msg = decode_15d_ping(captured)
    assert msg.counter == 0x36ef6
    assert msg.nonce == 0xaf912d74
    assert encode_15d_ping(msg) == captured


def test_15d_ping_validates_u32():
    with pytest.raises(ValueError, match="counter"):
        HeartbeatPing15D(counter=2**32, nonce=0)
    with pytest.raises(ValueError, match="nonce"):
        HeartbeatPing15D(counter=0, nonce=2**32)


def test_15d_ping_decode_wrong_type_header():
    bad = b"\x00\x01\x99\x99" + b"\x00" * 8
    with pytest.raises(ValueError, match="type header"):
        decode_15d_ping(bad)


def test_15d_ack_round_trip():
    captured = bytes.fromhex(
        "65c50b2b"
        "0000001c"
        + "00" * 16
        + "00019d05"
        "00036ef6"
        "af912d74"
    )
    msg = decode_15d_ack(captured)
    assert msg.client_hash.hex() == "65c50b2b"
    assert msg.echoed_ping.counter == 0x36ef6
    assert msg.echoed_ping.nonce == 0xaf912d74
    assert encode_15d_ack(msg) == captured


def test_15d_ack_rejects_wrong_remaining_length():
    bad = (
        b"\x65\xc5\x0b\x2b"
        + b"\x00\x00\x00\x99"  # length = 0x99 instead of 0x1c
        + b"\x00" * 16
        + b"\x00\x01\x9d\x05" b"\x00\x03\x6e\xf6" b"\xaf\x91\x2d\x74"
    )
    with pytest.raises(ValueError, match="remaining-length"):
        decode_15d_ack(bad)


def test_15d_ack_rejects_nonzero_padding():
    captured = bytes.fromhex(
        "65c50b2b"
        "0000001c"
        + "00" * 15 + "ff"  # one non-zero padding byte
        + "00019d05"
        "00036ef6"
        "af912d74"
    )
    with pytest.raises(ValueError, match="padding non-zero"):
        decode_15d_ack(captured)


def test_15d_ack_validates_client_hash_length():
    with pytest.raises(ValueError, match="client_hash"):
        HeartbeatAck15D(
            client_hash=b"\x00\x00\x00",  # 3 bytes
            echoed_ping=HeartbeatPing15D(counter=0, nonce=0),
        )


def test_15d_replay_pings_and_acks_paired():
    """All 10 R pings should pair 1:1 with the 10 W acks; the W's
    echoed_ping body must equal the R's body."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    pings = sorted(
        (m for m in store.messages if m.type_id == 0x15d and m.direction == "R"),
        key=lambda m: m.seq,
    )
    acks = sorted(
        (m for m in store.messages if m.type_id == 0x15d and m.direction == "W"),
        key=lambda m: m.seq,
    )
    assert len(pings) == len(acks) == 10
    for ping_msg, ack_msg in zip(pings, acks):
        # The W ack should follow the R ping in seq
        assert ack_msg.seq > ping_msg.seq
        ping = decode_15d_ping(ping_msg.body)
        ack = decode_15d_ack(ack_msg.body)
        assert ack.echoed_ping.counter == ping.counter
        assert ack.echoed_ping.nonce == ping.nonce


# ---------------------------------------------------------------------------
# LevelDescriptor 0x663
# ---------------------------------------------------------------------------

from .level_descriptor_663 import (  # noqa: E402
    LevelDescriptor663,
    encode as encode_663,
    decode as decode_663,
    TYPED_BODY_SIZE as LD663_TYPED_BODY_SIZE,
    DEFAULT_BUILD_VERSION as LD663_DEFAULT_BUILD_VERSION,
)


_CAPTURED_663 = bytes.fromhex(
    "0001a319"
    "14"
    + "4e6577576f726c645f5669746165457465726e61"
    + "1e"
    + "636f61746c696375652f4e6577576f726c645f5669746165457465726e61"
    + "45000000" "41800000" "463fc000" "46202800"
    + "00" * 8
    + "01010000"
    + "9cfa58617814 69f2".replace(" ", "")
    + "65030000"
    + "000001010100000000c17f9be48f"
)


def test_663_decode_captured_bytes():
    msg = decode_663(_CAPTURED_663)
    assert msg.level_name == "NewWorld_VitaeEterna"
    assert msg.level_path == "coatlicue/NewWorld_VitaeEterna"
    assert msg.geometry == (2048.0, 16.0, 12272.0, 10250.0)
    assert msg.second_id.hex() == "9cfa58617814" + "69f2"
    assert msg.flags == 0x00000101
    assert msg.build_version == LD663_DEFAULT_BUILD_VERSION  # 0x365


def test_663_round_trip():
    msg = decode_663(_CAPTURED_663)
    assert encode_663(msg) == _CAPTURED_663


def test_663_size_is_110():
    assert len(_CAPTURED_663) == LD663_TYPED_BODY_SIZE == 110


def test_663_validates_string_lengths_sum_to_50():
    """The fixed total wire size requires level_name + level_path == 50 bytes."""
    with pytest.raises(ValueError, match="must sum to 50"):
        LevelDescriptor663(
            level_name="too short",  # 9 bytes
            level_path="also short",  # 10 bytes
            geometry=(0.0, 0.0, 0.0, 0.0),
            second_id=bytes(8),
        )


def test_663_validates_geometry_arity():
    with pytest.raises(ValueError, match="must have 4 floats"):
        LevelDescriptor663(
            level_name="x" * 20,
            level_path="y" * 30,
            geometry=(1.0, 2.0, 3.0),  # only 3
            second_id=bytes(8),
        )


def test_663_decode_wrong_size_rejects():
    with pytest.raises(ValueError, match="110"):
        decode_663(_CAPTURED_663 + b"\x00")


def test_663_both_replay_copies_decode_identically():
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msgs = [m for m in store.messages if m.type_id == 0x663]
    assert len(msgs) == 2
    decoded = [decode_663(m.body) for m in msgs]
    assert decoded[0] == decoded[1]
    assert decoded[0].level_name == "NewWorld_VitaeEterna"


def test_663_metadata_block_matches_18a6():
    """Cross-codec invariant: 0x663's `flags`, `second_id`, and
    `build_version` are the same metadata footer that 0x18a6 carries.
    Verify by decoding one capture of each and comparing the fields."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)

    msg_663 = decode_663(
        next(m for m in store.messages if m.type_id == 0x663).body
    )
    msg_18a6 = decode_18a6(
        next(m for m in store.messages if m.type_id == 0x18a6).body
    )
    assert msg_663.flags == msg_18a6.flags == 0x00000101
    assert msg_663.second_id == msg_18a6.second_id
    assert msg_663.build_version == msg_18a6.build_version


# ---------------------------------------------------------------------------
# SessionSubkeyBeacon 0x1a59 (W direction)
# ---------------------------------------------------------------------------

from .session_subkey_1a59 import (  # noqa: E402
    SessionSubkeyBeacon1A59,
    encode as encode_1a59,
    decode as decode_1a59,
    TOTAL_WIRE_SIZE as SSB_TOTAL_WIRE_SIZE,
)

_CAPTURED_1A59_SEQ_69 = bytes.fromhex(
    "ea7d8adf"
    "00000025"
    "1a954abc4b3185bfbe37c3d8592618e0"
    "00019969"
    "f8cbed57c68b18f4bf85314bbc4a951a"
    "02"
)


def test_1a59_round_trip():
    msg = decode_1a59(_CAPTURED_1A59_SEQ_69)
    assert encode_1a59(msg) == _CAPTURED_1A59_SEQ_69


def test_1a59_size_is_45():
    assert SSB_TOTAL_WIRE_SIZE == 45
    assert len(_CAPTURED_1A59_SEQ_69) == 45


def test_1a59_decode_wrong_size_rejects():
    with pytest.raises(ValueError, match="45"):
        decode_1a59(_CAPTURED_1A59_SEQ_69 + b"\x00")


def test_1a59_decode_wrong_remaining_length_rejects():
    bad = bytearray(_CAPTURED_1A59_SEQ_69)
    bad[7] = 0x99  # corrupt the BE remaining_len
    with pytest.raises(ValueError, match="remaining-length"):
        decode_1a59(bytes(bad))


def test_1a59_decode_wrong_type_header_rejects():
    bad = bytearray(_CAPTURED_1A59_SEQ_69)
    bad[26] = 0xFF  # corrupt the type header
    with pytest.raises(ValueError, match="type_id mismatch|type header"):
        decode_1a59(bytes(bad))


def test_1a59_validates_lengths():
    with pytest.raises(ValueError, match="client_hash"):
        SessionSubkeyBeacon1A59(
            client_hash=b"\x00\x00\x00",  # 3 bytes
            session_uuid=b"\x00" * 16,
            subkey=b"\x00" * 16,
            counter=0,
        )
    with pytest.raises(ValueError, match="session_uuid"):
        SessionSubkeyBeacon1A59(
            client_hash=b"\x00\x00\x00\x00",
            session_uuid=b"\x00" * 8,  # wrong size
            subkey=b"\x00" * 16,
            counter=0,
        )
    with pytest.raises(ValueError, match="subkey"):
        SessionSubkeyBeacon1A59(
            client_hash=b"\x00\x00\x00\x00",
            session_uuid=b"\x00" * 16,
            subkey=b"\x00" * 8,  # wrong size
            counter=0,
        )
    with pytest.raises(ValueError, match="counter"):
        SessionSubkeyBeacon1A59(
            client_hash=b"\x00\x00\x00\x00",
            session_uuid=b"\x00" * 16,
            subkey=b"\x00" * 16,
            counter=256,  # >u8
        )


def test_1a59_all_replay_copies_round_trip():
    """All 3 captured 0x1a59 W messages should round-trip identically.
    Counters should be 2, 3, 4 (matching the 0x18a6 R-direction
    counter sequence)."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msgs = sorted(
        (m for m in store.messages if m.type_id == 0x1a59 and m.direction == "W"),
        key=lambda m: m.seq,
    )
    assert len(msgs) == 3
    decoded = [decode_1a59(m.body) for m in msgs]
    counters = [d.counter for d in decoded]
    assert counters == [2, 3, 4]
    # Subkey should be identical across all three (same session)
    subkeys = {d.subkey for d in decoded}
    assert len(subkeys) == 1, "subkey should be constant across 0x1a59 captures"
    # Each should round-trip
    for src, dec in zip(msgs, decoded):
        assert encode_1a59(dec) == src.body


def test_1a59_subkey_matches_18a6_first_16_bytes():
    """Cross-codec invariant: 0x1a59's 16-byte subkey is byte-identical
    to the first 16 bytes of 0x18a6's body (first_uuid_half +
    session_uuid_lower). Same session ⇒ same subkey."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    m_1a59 = decode_1a59(
        next(m for m in store.messages
             if m.type_id == 0x1a59 and m.direction == "W").body
    )
    m_18a6 = decode_18a6(
        next(m for m in store.messages if m.type_id == 0x18a6).body
    )
    # 0x18a6 stores it as first_uuid_half + session_uuid_lower
    assert m_1a59.subkey == m_18a6.first_uuid_half + m_18a6.session_uuid_lower


# ---------------------------------------------------------------------------
# IdentityFingerprintSet 0x5b2 (W direction)
# ---------------------------------------------------------------------------

from .identity_fingerprint_5b2 import (  # noqa: E402
    IdentityFingerprintSet5B2,
    encode as encode_5b2,
    decode as decode_5b2,
    MIN_TOTAL_WIRE_SIZE as IFS_MIN_TOTAL_WIRE_SIZE,
    FINGERPRINT_SIZE as IFS_FINGERPRINT_SIZE,
)

_CAPTURED_5B2_SMALL = bytes.fromhex(
    "f9b3ea55"
    "00000025"
    "1a954abc4b3185bfbe37c3d8592618e0"
    "0001b216"
    "180f8d4e573697c6"
    "bf85314bbc4a951a"
    "00"
)

_CAPTURED_5B2_LARGE = bytes.fromhex(
    "c468b848"
    "00000055"
    "1a954abc4b3185bfbe37c3d8592618e0"
    "0001b216"
    "180f8d4e573697c6"
    "bf85314bbc4a951a"
    "06"
    "1e4e63891491 99c8"
    "c44e4b804e09 a0fd"
    "ac4fe4f4cbb0 c2ff"
    "2644e72b17b4 794c"
    "e24816dee8a3 9546"
    "dd464d7541fa f5a5".replace(" ", "")
)


def test_5b2_small_round_trip():
    msg = decode_5b2(_CAPTURED_5B2_SMALL)
    assert len(msg.fingerprints) == 0
    assert encode_5b2(msg) == _CAPTURED_5B2_SMALL


def test_5b2_large_round_trip():
    msg = decode_5b2(_CAPTURED_5B2_LARGE)
    assert len(msg.fingerprints) == 6
    for fp in msg.fingerprints:
        assert len(fp) == IFS_FINGERPRINT_SIZE
    assert encode_5b2(msg) == _CAPTURED_5B2_LARGE


def test_5b2_min_size_is_45():
    assert IFS_MIN_TOTAL_WIRE_SIZE == 45
    assert len(_CAPTURED_5B2_SMALL) == IFS_MIN_TOTAL_WIRE_SIZE


def test_5b2_decode_too_short_rejects():
    with pytest.raises(ValueError, match="too short"):
        decode_5b2(_CAPTURED_5B2_SMALL[:-1])


def test_5b2_decode_count_size_mismatch_rejects():
    """Tamper with the count byte without adding fingerprints — the size
    field then doesn't match the implied buffer length."""
    bad = bytearray(_CAPTURED_5B2_SMALL)
    bad[44] = 0x01  # claim 1 fingerprint without padding
    with pytest.raises(ValueError, match="size mismatch"):
        decode_5b2(bytes(bad))


def test_5b2_decode_wrong_type_header_rejects():
    bad = bytearray(_CAPTURED_5B2_SMALL)
    bad[26] = 0xFF
    with pytest.raises(ValueError, match="type header"):
        decode_5b2(bytes(bad))


def test_5b2_validates_fingerprint_size():
    with pytest.raises(ValueError, match="fingerprint"):
        IdentityFingerprintSet5B2(
            client_hash=b"\x00" * 4,
            session_uuid=b"\x00" * 16,
            second_id=b"\x00" * 8,
            session_uuid_lower=b"\x00" * 8,
            fingerprints=(b"\x00" * 7,),  # wrong size
        )


def test_5b2_three_small_replay_copies_are_identical():
    """The 3 small-variant 0x5b2 messages (seq 0x92, 0x99, 0x9b) are
    byte-identical including client_hash — strong evidence of
    reliable-delivery resends of the same logical message."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msgs = [
        m for m in store.messages
        if m.type_id == 0x5b2 and m.direction == "W" and len(m.body) == 45
    ]
    assert len(msgs) == 3
    bodies = {m.body for m in msgs}
    assert len(bodies) == 1, "the 3 small 0x5b2 messages should be identical bytes"


def test_5b2_all_replay_copies_round_trip():
    """All 4 captured 0x5b2 W messages should round-trip; share the
    same second_id and session_uuid (same session)."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msgs = [m for m in store.messages if m.type_id == 0x5b2 and m.direction == "W"]
    assert len(msgs) == 4
    decoded = [decode_5b2(m.body) for m in msgs]
    second_ids = {d.second_id for d in decoded}
    session_uuids = {d.session_uuid for d in decoded}
    assert len(second_ids) == 1
    assert len(session_uuids) == 1
    counts = sorted(len(d.fingerprints) for d in decoded)
    assert counts == [0, 0, 0, 6]
    for src, dec in zip(msgs, decoded):
        assert encode_5b2(dec) == src.body


# ---------------------------------------------------------------------------
# ActionHistory 0x635 (W direction)
# ---------------------------------------------------------------------------

from .action_history_635 import (  # noqa: E402
    ActionHistory635,
    encode as encode_635,
    decode as decode_635,
    MIN_TOTAL_WIRE_SIZE as AH_MIN_TOTAL_WIRE_SIZE,
    HISTORY_RECORD_SIZE as AH_HISTORY_RECORD_SIZE,
    DEFAULT_TRAILER as AH_DEFAULT_TRAILER,
)


def test_635_first_send_round_trip():
    """seq 0x6e — counter=1, first_send=True, no history records.
    Total 93 bytes."""
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
    msg = decode_635(seq6e)
    assert msg.counter == 1
    assert msg.first_send is True
    assert msg.history_counters == ()
    assert encode_635(msg) == seq6e


def test_635_largest_round_trip():
    """seq 0x72 — counter=5, 4 history records (4, 3, 2, 1).
    Total 153 bytes."""
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
    msg = decode_635(seq72)
    assert msg.counter == 5
    assert msg.first_send is False
    assert msg.history_counters == (4, 3, 2, 1)
    assert encode_635(msg) == seq72


def test_635_min_size_is_93():
    assert AH_MIN_TOTAL_WIRE_SIZE == 93
    assert AH_HISTORY_RECORD_SIZE == 15
    assert len(AH_DEFAULT_TRAILER) == 13


def test_635_decode_too_short_rejects():
    with pytest.raises(ValueError, match="too short"):
        decode_635(b"\x00" * 50)


def test_635_decode_unaligned_history_rejects():
    """Truncate one byte off a valid message — leaves a body that
    isn't a clean multiple of HISTORY_RECORD_SIZE."""
    seq6f = bytes.fromhex(
        "98404b17"
        "00000064"
        "1a954abc4b3185bfbe37c3d8592618e0"
        "0001b518"
        "fbde4b9a600d428f"
        "bf85314bbc4a951a"
        "00000000"
        "91020600"
        "000101000000000000000001"
        "2007194b"
        "000000ac0f01"
        "02" "01" "00000002"
        "c0802000808080800300000001"
        "00000000" "01" "00" "808080800300000001"
    )
    # Drop the last byte and patch remaining_len so we hit the alignment check
    # (rather than the remaining-length check).
    truncated = bytearray(seq6f[:-1])
    truncated[7] = seq6f[7] - 1  # decrement remaining_len BE byte
    with pytest.raises(ValueError, match="multiple of"):
        decode_635(bytes(truncated))


def test_635_decode_counter_mismatch_rejects():
    """If the u32 LE counter doesn't equal the u8 counter, decode rejects."""
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
        "01" "01" "00000002"   # u8=1, u32=2 — mismatch!
        "c0802000808080800300000001"
    )
    with pytest.raises(ValueError, match="counter u8/u32 mismatch"):
        decode_635(seq6e)


def test_635_encoder_default_history_for_counter_n():
    """When history_counters is empty and counter > 1, encoder should
    auto-generate (counter-1, ..., 1) — matching captured behavior."""
    msg = ActionHistory635(
        client_hash=b"\xb1\xc1\x02\x29",
        session_uuid=bytes.fromhex("1a954abc4b3185bfbe37c3d8592618e0"),
        second_id=bytes.fromhex("fbde4b9a600d428f"),
        session_uuid_lower=bytes.fromhex("bf85314bbc4a951a"),
        counter=5,
        first_send=False,
        history_counters=(),  # let the encoder fill this in
    )
    encoded = encode_635(msg)
    redecoded = decode_635(encoded)
    assert redecoded.history_counters == (4, 3, 2, 1)


def test_635_all_replay_copies_round_trip():
    """All 5 captured 0x635 W messages should round-trip and exhibit
    the expected counter / history pattern."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msgs = sorted(
        (m for m in store.messages if m.type_id == 0x635 and m.direction == "W"),
        key=lambda m: m.seq,
    )
    assert len(msgs) == 5
    decoded = [decode_635(m.body) for m in msgs]
    # Counters: 1..5
    assert [d.counter for d in decoded] == [1, 2, 3, 4, 5]
    # first_send only on the first message
    assert [d.first_send for d in decoded] == [True, False, False, False, False]
    # history grows monotonically: 0, 1, 2, 3, 4 records
    assert [len(d.history_counters) for d in decoded] == [0, 1, 2, 3, 4]
    # All messages share the same session_uuid + second_id
    assert len({d.session_uuid for d in decoded}) == 1
    assert len({d.second_id for d in decoded}) == 1
    # Round-trip
    for src, dec in zip(msgs, decoded):
        assert encode_635(dec) == src.body


def test_635_history_records_descend_from_n_minus_1_to_1():
    """Captured 0x635 history records always run counter-1, counter-2,
    ..., 1. Document this invariant."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    for m in store.messages:
        if m.type_id != 0x635 or m.direction != "W":
            continue
        d = decode_635(m.body)
        if d.counter > 1:
            expected = tuple(range(d.counter - 1, 0, -1))
            assert d.history_counters == expected, (
                f"seq 0x{m.seq:x}: counter={d.counter} but history={d.history_counters}"
            )


# ---------------------------------------------------------------------------
# AssetBlob 0x16a0 (R direction, small variant)
# ---------------------------------------------------------------------------

from .asset_blob_16a0 import (  # noqa: E402
    AssetBlob16A0Small,
    encode as encode_16a0,
    decode as decode_16a0,
    SMALL_TYPED_BODY_SIZE as AB_SMALL_TYPED_BODY_SIZE,
)


def test_16a0_round_trip_from_replay():
    """Round-trip the captured small 0x16a0 R message. Asset class
    should decode to "ItemPool". Cannot validate handler-side semantic
    fields because the asset-id span is redacted in the capture."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    candidates = [
        m for m in store.messages
        if m.type_id == 0x16a0 and m.direction == "R" and len(m.body) == 153
    ]
    assert len(candidates) == 1
    msg = decode_16a0(candidates[0].body)
    assert encode_16a0(msg) == candidates[0].body
    found = msg.find_asset_class()
    assert found is not None
    name, _offset = found
    assert name == "ItemPool"


def test_16a0_size_is_153():
    assert AB_SMALL_TYPED_BODY_SIZE == 153


def test_16a0_decode_wrong_size_rejects():
    with pytest.raises(ValueError, match="153"):
        decode_16a0(b"\x00" * 100)


def test_16a0_decode_wrong_type_header_rejects():
    bad = bytearray(b"\x00" * 153)
    bad[0:4] = b"\x00\x01\xff\xff"  # wrong type header
    with pytest.raises(ValueError, match="type header"):
        decode_16a0(bytes(bad))


def test_16a0_validates_field_sizes():
    with pytest.raises(ValueError, match="asset_uuid"):
        AssetBlob16A0Small(asset_uuid=b"\x00" * 8, payload_bytes=b"\x00" * 133)
    with pytest.raises(ValueError, match="payload_bytes"):
        AssetBlob16A0Small(asset_uuid=b"\x00" * 16, payload_bytes=b"\x00" * 100)


# ---------------------------------------------------------------------------
# HandshakeBlob76 — type 0x40a + type 0x1be (R direction, 76 bytes)
# ---------------------------------------------------------------------------

from .handshake_blob_76 import (  # noqa: E402
    HandshakeBlob76,
    encode as encode_hsb,
    decode as decode_hsb,
    TYPED_BODY_SIZE as HSB_TYPED_BODY_SIZE,
    DEFAULT_SUB_ID as HSB_DEFAULT_SUB_ID,
    DEFAULT_SHARED_TRAILER as HSB_DEFAULT_SHARED_TRAILER,
)


def test_hsb_size_is_76():
    assert HSB_TYPED_BODY_SIZE == 76
    assert len(HSB_DEFAULT_SUB_ID) == 4
    assert len(HSB_DEFAULT_SHARED_TRAILER) == 36


def test_hsb_decode_wrong_size_rejects():
    with pytest.raises(ValueError, match="76"):
        decode_hsb(b"\x00" * 50)


def test_hsb_decode_wrong_marker_rejects():
    bad = bytearray(b"\x00" * 76)
    bad[0:2] = b"\x99\x99"
    with pytest.raises(ValueError, match="marker"):
        decode_hsb(bytes(bad))


def test_hsb_validates_blob_size():
    with pytest.raises(ValueError, match="blob"):
        HandshakeBlob76(type_id=0x40a, blob=b"\x00" * 16)


def test_hsb_round_trip_both_singletons():
    """Both 76-byte singletons (0x40a and 0x1be) should round-trip.
    They share the same 4-byte sub_id and 36-byte trailer."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msgs = [
        m for m in store.messages
        if m.type_id in (0x40a, 0x1be) and m.direction == "R"
    ]
    assert len(msgs) == 2
    decoded = [(m.type_id, decode_hsb(m.body)) for m in msgs]
    type_ids = {tid for tid, _ in decoded}
    assert type_ids == {0x40a, 0x1be}
    # All decoded messages share the same sub_id and trailer
    sub_ids = {d.sub_id for _, d in decoded}
    trailers = {d.shared_trailer for _, d in decoded}
    assert len(sub_ids) == 1
    assert sub_ids.pop() == HSB_DEFAULT_SUB_ID
    assert len(trailers) == 1
    assert trailers.pop() == HSB_DEFAULT_SHARED_TRAILER
    # Round-trip
    for src, (_tid, dec) in zip(msgs, decoded):
        assert encode_hsb(dec) == src.body


def test_hsb_type_id_round_trip():
    """Encoding then decoding should preserve the type_id exactly,
    even for arbitrary in-range values."""
    for tid in (0x40a, 0x1be, 0x000, 0x123, 0x3fff):
        msg = HandshakeBlob76(type_id=tid, blob=b"\x42" * 32)
        assert decode_hsb(encode_hsb(msg)).type_id == tid


# ---------------------------------------------------------------------------
# VivoxConfig1067 (R direction, 86 bytes)
# ---------------------------------------------------------------------------

from .vivox_config_1067 import (  # noqa: E402
    VivoxConfig1067,
    encode as encode_vc1067,
    decode as decode_vc1067,
    CAPTURED_API_URL,
    CAPTURED_REALM,
    CAPTURED_ISSUER,
)


def test_1067_round_trip_from_replay():
    """Round-trip the captured 0x1067 R message. Should decode to
    the Amazon NA Vivox voice-chat config."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    candidates = [m for m in store.messages if m.type_id == 0x1067]
    assert len(candidates) == 1
    msg = decode_vc1067(candidates[0].body)
    assert msg.api_url == CAPTURED_API_URL
    assert msg.realm == CAPTURED_REALM
    assert msg.issuer == CAPTURED_ISSUER
    assert encode_vc1067(msg) == candidates[0].body


def test_1067_decode_wrong_type_header_rejects():
    bad = bytearray(b"\x00\x01\xff\xff" + b"\x00" * 80)
    with pytest.raises(ValueError, match="type header"):
        decode_vc1067(bytes(bad))


def test_1067_decode_string_overrun_rejects():
    """Length prefix claims more bytes than the buffer holds."""
    bad = (
        b"\x00\x01\xa7\x41"           # type header
        + b"\x00" * 16                # identity_uuid
        + b"\xff"                     # claim 255 bytes for first string
        + b"X" * 4                    # only 4 bytes available
    )
    with pytest.raises(ValueError, match="overruns"):
        decode_vc1067(bad)


def test_1067_decode_missing_terminator_rejects():
    """Drop the trailing 0x00 terminator."""
    encoded = encode_vc1067(
        VivoxConfig1067(
            identity_uuid=b"\x00" * 16,
            api_url="a",
            realm="b",
            issuer="c",
        )
    )
    bad = encoded[:-1]  # drop terminator
    with pytest.raises(ValueError, match="terminator|too short"):
        decode_vc1067(bad)


def test_1067_decode_wrong_terminator_rejects():
    encoded = encode_vc1067(
        VivoxConfig1067(
            identity_uuid=b"\x00" * 16,
            api_url="a",
            realm="b",
            issuer="c",
        )
    )
    bad = bytearray(encoded)
    bad[-1] = 0xFF  # corrupt terminator
    with pytest.raises(ValueError, match="terminator"):
        decode_vc1067(bytes(bad))


def test_1067_validates_identity_uuid_size():
    with pytest.raises(ValueError, match="identity_uuid"):
        VivoxConfig1067(
            identity_uuid=b"\x00" * 8,
            api_url="x",
            realm="y",
            issuer="z",
        )


def test_1067_round_trip_with_arbitrary_strings():
    msg = VivoxConfig1067(
        identity_uuid=bytes(range(16)),
        api_url="https://example.test/api/",
        realm="region-1",
        issuer="@example.test",
    )
    assert decode_vc1067(encode_vc1067(msg)) == msg


# ---------------------------------------------------------------------------
# IdentityBlob 0x8e6 (R direction, 42 bytes)
# ---------------------------------------------------------------------------

from .identity_blob_8e6 import (  # noqa: E402
    IdentityBlob8E6,
    encode as encode_8e6,
    decode as decode_8e6,
    TYPED_BODY_SIZE as IB8E6_TYPED_BODY_SIZE,
)


def test_8e6_round_trip_from_replay():
    """Round-trip the captured 0x8e6 R singleton."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    candidates = [m for m in store.messages if m.type_id == 0x8e6]
    assert len(candidates) == 1
    msg = decode_8e6(candidates[0].body)
    assert encode_8e6(msg) == candidates[0].body
    # The identity_uuid lower 8 bytes should match session_uuid_lower
    assert msg.identity_uuid[8:] == bytes.fromhex("bf85314bbc4a951a")


def test_8e6_size_is_42():
    assert IB8E6_TYPED_BODY_SIZE == 42


def test_8e6_decode_wrong_size_rejects():
    with pytest.raises(ValueError, match="42"):
        decode_8e6(b"\x00" * 40)


def test_8e6_decode_wrong_type_header_rejects():
    bad = bytearray(b"\x00" * 42)
    bad[0:4] = b"\x00\x01\xff\xff"
    with pytest.raises(ValueError, match="type header"):
        decode_8e6(bytes(bad))


def test_8e6_decode_nonzero_pad_rejects():
    """Nonzero byte in the trailing 6-byte pad span should reject."""
    msg = IdentityBlob8E6(
        identity_uuid=b"\x00" * 16, opaque_blob=b"\x00" * 16
    )
    encoded = bytearray(encode_8e6(msg))
    encoded[-1] = 0xFF  # corrupt last pad byte
    with pytest.raises(ValueError, match="pad"):
        decode_8e6(bytes(encoded))


def test_8e6_validates_field_sizes():
    with pytest.raises(ValueError, match="identity_uuid"):
        IdentityBlob8E6(identity_uuid=b"\x00" * 8, opaque_blob=b"\x00" * 16)
    with pytest.raises(ValueError, match="opaque_blob"):
        IdentityBlob8E6(identity_uuid=b"\x00" * 16, opaque_blob=b"\x00" * 8)


# ---------------------------------------------------------------------------
# AssetCountTable 0xca4 (R direction, variable size)
# ---------------------------------------------------------------------------

from .asset_count_table_ca4 import (  # noqa: E402
    AssetCountTableCA4,
    AssetCountRecord,
    encode as encode_ca4,
    decode as decode_ca4,
    MIN_TYPED_BODY_SIZE as ACT_MIN_TYPED_BODY_SIZE,
    DEFAULT_TRAILER as ACT_DEFAULT_TRAILER,
)


def test_ca4_round_trip_from_replay():
    """Round-trip the captured 0xca4 R singleton; verify 10 records
    and the asset quantities."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    candidates = [m for m in store.messages if m.type_id == 0xca4]
    assert len(candidates) == 1
    msg = decode_ca4(candidates[0].body)
    assert len(msg.records) == 10
    expected_values = [43, 6, 1, 226, 1304, 24, 16, 1713, 6090, 23]
    assert [r.value for r in msg.records] == expected_values
    assert msg.trailer == ACT_DEFAULT_TRAILER
    assert encode_ca4(msg) == candidates[0].body
    # identity_uuid lower 8 = session_uuid_lower
    assert msg.identity_uuid[8:] == bytes.fromhex("bf85314bbc4a951a")


def test_ca4_min_size_22_bytes():
    assert ACT_MIN_TYPED_BODY_SIZE == 22


def test_ca4_decode_too_short_rejects():
    with pytest.raises(ValueError, match="too short"):
        decode_ca4(b"\x00" * 10)


def test_ca4_decode_wrong_type_header_rejects():
    bad = bytearray(b"\x00\x01\xff\xff" + b"\x00" * 18)
    with pytest.raises(ValueError, match="type header"):
        decode_ca4(bytes(bad))


def test_ca4_decode_count_size_mismatch_rejects():
    """Tamper with the count byte without adjusting the buffer length."""
    msg = AssetCountTableCA4(
        identity_uuid=b"\x00" * 16,
        records=(),
    )
    encoded = bytearray(encode_ca4(msg))
    encoded[20] = 0x05  # claim 5 records in a 22-byte buffer
    with pytest.raises(ValueError, match="size mismatch"):
        decode_ca4(bytes(encoded))


def test_ca4_record_validates_hash_size():
    with pytest.raises(ValueError, match="hash_id"):
        AssetCountRecord(hash_id=b"\x00\x00", value=0)


def test_ca4_empty_records_round_trip():
    msg = AssetCountTableCA4(
        identity_uuid=b"\xff" * 16,
        records=(),
        trailer=0x42,
    )
    assert decode_ca4(encode_ca4(msg)) == msg


# ---------------------------------------------------------------------------
# ResultToken 0x136a (R direction, 28 bytes)
# ---------------------------------------------------------------------------

from .result_token_136a import (  # noqa: E402
    ResultToken136A,
    encode as encode_136a,
    decode as decode_136a,
    TYPED_BODY_SIZE as RT_TYPED_BODY_SIZE,
)


def test_136a_round_trip_from_replay():
    """Round-trip the captured 0x136a R singleton."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    candidates = [m for m in store.messages if m.type_id == 0x136a]
    assert len(candidates) == 1
    msg = decode_136a(candidates[0].body)
    assert msg.result == 1
    assert msg.identity_uuid[8:] == bytes.fromhex("bf85314bbc4a951a")
    assert encode_136a(msg) == candidates[0].body


def test_136a_size_is_28():
    assert RT_TYPED_BODY_SIZE == 28


def test_136a_decode_wrong_size_rejects():
    with pytest.raises(ValueError, match="28"):
        decode_136a(b"\x00" * 24)


def test_136a_decode_wrong_type_header_rejects():
    bad = bytearray(b"\x00" * 28)
    bad[0:4] = b"\x00\x01\xff\xff"
    with pytest.raises(ValueError, match="type header"):
        decode_136a(bytes(bad))


def test_136a_validates_uuid_size():
    with pytest.raises(ValueError, match="identity_uuid"):
        ResultToken136A(identity_uuid=b"\x00" * 8, result=0)


def test_136a_validates_result_range():
    with pytest.raises(ValueError, match="result"):
        ResultToken136A(identity_uuid=b"\x00" * 16, result=2**64)


def test_136a_round_trip_max_u64():
    msg = ResultToken136A(identity_uuid=b"\x42" * 16, result=2**64 - 1)
    assert decode_136a(encode_136a(msg)) == msg


# ---------------------------------------------------------------------------
# ResultToken 0x1097 (R direction, 24 bytes)
# ---------------------------------------------------------------------------

from .result_token_1097 import (  # noqa: E402
    ResultToken1097,
    encode as encode_1097,
    decode as decode_1097,
    TYPED_BODY_SIZE as RT1097_TYPED_BODY_SIZE,
)


def test_1097_round_trip_from_replay():
    """Round-trip the captured 0x1097 R singleton; verify it pairs
    with 0x1096 by sharing identity_uuid."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    candidates = [m for m in store.messages if m.type_id == 0x1097]
    assert len(candidates) == 1
    msg = decode_1097(candidates[0].body)
    assert msg.result == 2
    assert encode_1097(msg) == candidates[0].body
    # Should share the same 16-byte identity_uuid as 0x1096
    msg_1096 = next(m for m in store.messages if m.type_id == 0x1096)
    assert msg.identity_uuid == msg_1096.body[4:20]


def test_1097_size_is_24():
    assert RT1097_TYPED_BODY_SIZE == 24


def test_1097_decode_wrong_size_rejects():
    with pytest.raises(ValueError, match="24"):
        decode_1097(b"\x00" * 20)


def test_1097_decode_wrong_type_header_rejects():
    bad = bytearray(b"\x00" * 24)
    bad[0:4] = b"\x00\x01\xff\xff"
    with pytest.raises(ValueError, match="type header"):
        decode_1097(bytes(bad))


def test_1097_validates_result_range():
    with pytest.raises(ValueError, match="result"):
        ResultToken1097(identity_uuid=b"\x00" * 16, result=2**32)


def test_1097_round_trip_max_u32():
    msg = ResultToken1097(identity_uuid=b"\x42" * 16, result=2**32 - 1)
    assert decode_1097(encode_1097(msg)) == msg


# ---------------------------------------------------------------------------
# Generic SubkeyBeacon — covers 12 W-singleton types + 0x1a59
# ---------------------------------------------------------------------------

from .subkey_beacon import (  # noqa: E402
    SubkeyBeacon,
    encode as encode_subkey,
    decode as decode_subkey,
    KNOWN_FAMILY,
    BASE_WIRE_SIZE as SUBKEY_BASE_WIRE_SIZE,
    make_type_header as subkey_make_type_header,
    decode_type_id as subkey_decode_type_id,
    make_subkey_beacon,
)


def test_subkey_base_size_44():
    assert SUBKEY_BASE_WIRE_SIZE == 44


def test_subkey_known_family_has_14_types():
    """Spot-check: the family covers the 14 captured-replay types
    (13 W-singletons + 0x1a59 with 3 captures)."""
    assert len(KNOWN_FAMILY) == 14
    assert KNOWN_FAMILY[0x1a59] == 1
    assert KNOWN_FAMILY[0x09d3] == 4
    assert KNOWN_FAMILY[0x192c] == 10


def test_subkey_round_trip_zero_trailer():
    msg = SubkeyBeacon(
        type_id=0x102f,
        client_hash=b"\x4b\x45\x10\x1a",
        session_uuid=bytes(range(16)),
        subkey=bytes(range(16, 32)),
        trailer=b"",
    )
    encoded = encode_subkey(msg)
    assert len(encoded) == 44
    decoded = decode_subkey(encoded)
    assert decoded == msg


def test_subkey_round_trip_4_byte_trailer():
    msg = SubkeyBeacon(
        type_id=0x09d3,
        client_hash=b"\x3f\x0d\xea\x49",
        session_uuid=bytes(range(16)),
        subkey=bytes(range(16, 32)),
        trailer=b"\xde\xad\xbe\xef",
    )
    encoded = encode_subkey(msg)
    assert len(encoded) == 48
    decoded = decode_subkey(encoded)
    assert decoded == msg


def test_subkey_decode_validates_remaining_length():
    msg = SubkeyBeacon(
        type_id=0x1a59,
        client_hash=b"\x00" * 4,
        session_uuid=bytes(16),
        subkey=bytes(16),
        trailer=b"\x00",
    )
    encoded = bytearray(encode_subkey(msg))
    encoded[7] = 0x99  # corrupt remaining_len
    with pytest.raises(ValueError, match="remaining-length"):
        decode_subkey(bytes(encoded))


def test_subkey_decode_expected_type_id_mismatch_rejects():
    msg = SubkeyBeacon(
        type_id=0x1a59,
        client_hash=b"\x00" * 4,
        session_uuid=bytes(16),
        subkey=bytes(16),
        trailer=b"\x00",
    )
    encoded = encode_subkey(msg)
    with pytest.raises(ValueError, match="type_id mismatch"):
        decode_subkey(encoded, expected_type_id=0x102f)


def test_subkey_decode_expected_trailer_size_mismatch_rejects():
    msg = SubkeyBeacon(
        type_id=0x1a59,
        client_hash=b"\x00" * 4,
        session_uuid=bytes(16),
        subkey=bytes(16),
        trailer=b"\x00",
    )
    encoded = encode_subkey(msg)
    with pytest.raises(ValueError, match="trailer size"):
        decode_subkey(encoded, expected_trailer_size=4)


def test_subkey_make_type_header_round_trip():
    for tid in (0x40, 0x1a59, 0x3FFF, 0x102e):
        hdr = subkey_make_type_header(tid)
        assert subkey_decode_type_id(hdr) == tid


def test_subkey_make_type_header_rejects_low_types():
    """The 4-byte typed envelope is for type-IDs in [0x40, 0x3FFF].
    Lower types use the 3-byte form — see post-v3-sequence.md."""
    with pytest.raises(ValueError, match="0x3"):
        subkey_make_type_header(0x3)
    with pytest.raises(ValueError, match="0x3F"):
        subkey_make_type_header(0x3F)


def test_make_subkey_beacon_basic():
    """Helper builds a fully-formed SubkeyBeacon from sub-system parts."""
    msg = make_subkey_beacon(
        type_id=0x1a59,
        client_hash=b"\x01\x02\x03\x04",
        session_uuid=b"\xaa" * 8 + b"\xbb" * 8,
        subkey_upper_8=b"\xcc" * 8,
        session_uuid_lower_8=b"\xbb" * 8,
        trailer=b"\x07",
    )
    assert msg.type_id == 0x1a59
    assert msg.subkey == b"\xcc" * 8 + b"\xbb" * 8
    assert msg.trailer == b"\x07"
    # Round-trip through wire encoding
    encoded = encode_subkey(msg)
    assert len(encoded) == 45
    assert decode_subkey(encoded) == msg


def test_make_subkey_beacon_validates_lower_match():
    """The session_uuid_lower_8 must match session_uuid[8:]."""
    with pytest.raises(ValueError, match="lower 8"):
        make_subkey_beacon(
            type_id=0x1a59,
            client_hash=b"\x00" * 4,
            session_uuid=b"\xaa" * 8 + b"\xbb" * 8,
            subkey_upper_8=b"\xcc" * 8,
            session_uuid_lower_8=b"\xdd" * 8,  # mismatch
            trailer=b"\x00",
        )


def test_make_subkey_beacon_validates_field_sizes():
    with pytest.raises(ValueError, match="subkey_upper_8"):
        make_subkey_beacon(
            type_id=0x1a59,
            client_hash=b"\x00" * 4,
            session_uuid=bytes(16),
            subkey_upper_8=b"\x00" * 4,  # wrong size
            session_uuid_lower_8=bytes(8),
        )


def test_subkey_all_replay_types_round_trip():
    """Round-trip every W-direction replay message that fits the
    subkey-beacon family. Verifies the generic codec handles all
    13 captured types end-to-end."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    seen_types: set[int] = set()
    for m in store.messages:
        if m.type_id not in KNOWN_FAMILY or m.direction != "W":
            continue
        expected_trailer = KNOWN_FAMILY[m.type_id]
        decoded = decode_subkey(
            m.body,
            expected_type_id=m.type_id,
            expected_trailer_size=expected_trailer,
        )
        assert encode_subkey(decoded) == m.body
        seen_types.add(m.type_id)
    # The 0x1a59 has 3 captures, the rest are singletons → 13 total types.
    assert seen_types == set(KNOWN_FAMILY.keys())


# ---------------------------------------------------------------------------
# PermissionBitmap 0x0a95 (W direction, variable-size)
# ---------------------------------------------------------------------------

from .permission_bitmap_a95 import (  # noqa: E402
    PermissionBitmapA95,
    encode as encode_a95,
    decode as decode_a95,
    MIN_TOTAL_WIRE_SIZE as PB_MIN_WIRE_SIZE,
)


def test_a95_round_trip_from_replay():
    """Round-trip the captured 0x0a95 W singleton; verify 36 flags
    with one disabled at index 6."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    candidates = [m for m in store.messages if m.type_id == 0x0a95]
    assert len(candidates) == 1
    msg = decode_a95(candidates[0].body)
    assert len(msg.flags) == 36
    disabled = [i for i, f in enumerate(msg.flags) if f == 0]
    assert disabled == [6]
    assert encode_a95(msg) == candidates[0].body


def test_a95_min_size_45():
    assert PB_MIN_WIRE_SIZE == 45


def test_a95_decode_too_short_rejects():
    with pytest.raises(ValueError, match="too short"):
        decode_a95(b"\x00" * 30)


def test_a95_decode_count_size_mismatch_rejects():
    """Tamper with the flag-count without resizing the buffer."""
    msg = PermissionBitmapA95(
        client_hash=b"\x00" * 4,
        session_uuid=bytes(16),
        subkey=bytes(16),
        flags=b"",
    )
    encoded = bytearray(encode_a95(msg))
    encoded[44] = 0x05  # claim 5 flags but the buffer has none
    with pytest.raises(ValueError, match="size mismatch"):
        decode_a95(bytes(encoded))


def test_a95_round_trip_empty_flags():
    msg = PermissionBitmapA95(
        client_hash=b"\xff" * 4,
        session_uuid=bytes(range(16)),
        subkey=bytes(range(16, 32)),
        flags=b"",
    )
    assert decode_a95(encode_a95(msg)) == msg


def test_a95_subkey_upper_matches_5b2_second_id():
    """Cross-codec finding: the upper 8 bytes of 0x0a95's subkey
    match 0x5b2's second_id — same fingerprint-reporter sub-system
    identity."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msg_a95 = decode_a95(
        next(m for m in store.messages if m.type_id == 0x0a95).body
    )
    msg_5b2 = decode_5b2(
        next(m for m in store.messages if m.type_id == 0x5b2).body
    )
    assert msg_a95.subkey[:8] == msg_5b2.second_id


# ---------------------------------------------------------------------------
# KeybindingConfig 0x12f6 (W direction, variable size)
# ---------------------------------------------------------------------------

from .keybinding_config_12f6 import (  # noqa: E402
    KeybindingConfig12F6,
    encode as encode_12f6,
    decode as decode_12f6,
    DEFAULT_TRANSITION as KC_DEFAULT_TRANSITION,
    DEFAULT_TRAILER as KC_DEFAULT_TRAILER,
)


def test_12f6_round_trip_from_replay():
    """Round-trip the captured 0x12f6 W singleton; verify the 18
    captured keybindings (with 2 empty entries)."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    candidates = [m for m in store.messages if m.type_id == 0x12f6]
    assert len(candidates) == 1
    msg = decode_12f6(candidates[0].body)
    assert len(msg.keybindings) == 18
    # Spot-check several recognizable keybindings.
    assert "@cc_f3" in msg.keybindings
    assert "@cc_mouse2" in msg.keybindings
    assert "@cc_q" in msg.keybindings
    # Two empty bindings in the captured layout.
    assert msg.keybindings.count("") == 2
    # The trailing version blocks open with `{0.0.0.` and `{0.0.1.`
    assert msg.version_block_1.startswith(b"{0.0.0.")
    assert msg.version_block_2.startswith(b"{0.0.1.")
    assert encode_12f6(msg) == candidates[0].body


def test_12f6_subkey_upper_is_keybinding_config_id():
    """The subkey upper 8 bytes match the keybinding-config sub-system
    identity from the cross-codec identity-bundle map."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msg = decode_12f6(
        next(m for m in store.messages if m.type_id == 0x12f6).body
    )
    assert msg.subkey[:8] == bytes.fromhex("9e921a154971f6b7")
    # Lower 8 bytes are session_uuid_lower.
    assert msg.subkey[8:] == bytes.fromhex("bf85314bbc4a951a")


def test_12f6_decode_wrong_type_header_rejects():
    msg = KeybindingConfig12F6(
        client_hash=b"\x00" * 4,
        session_uuid=bytes(16),
        subkey=bytes(16),
        state_region=bytes(26),
        keybindings=("@cc_x",),
        version_block_1=b"x" * 55,
        version_block_2=b"y" * 55,
    )
    encoded = bytearray(encode_12f6(msg))
    encoded[26] = 0xFF  # corrupt the type header
    with pytest.raises(ValueError, match="type header"):
        decode_12f6(bytes(encoded))


def test_12f6_decode_wrong_version_block_prefix_rejects():
    msg = KeybindingConfig12F6(
        client_hash=b"\x00" * 4,
        session_uuid=bytes(16),
        subkey=bytes(16),
        state_region=bytes(26),
        keybindings=("@cc_x",),
        version_block_1=b"x" * 55,
        version_block_2=b"y" * 55,
    )
    encoded = bytearray(encode_12f6(msg))
    # Find vb1 length prefix and corrupt it.
    # transition (5) starts at offset suffix_start; vb1 prefix is at +5
    suffix_start = len(encoded) - 122
    encoded[suffix_start + 5] = 0xFF
    with pytest.raises(ValueError, match="version_block_1 length"):
        decode_12f6(bytes(encoded))


def test_12f6_validates_field_sizes():
    with pytest.raises(ValueError, match="state_region"):
        KeybindingConfig12F6(
            client_hash=b"\x00" * 4,
            session_uuid=bytes(16),
            subkey=bytes(16),
            state_region=bytes(20),  # wrong size
            keybindings=(),
            version_block_1=b"x" * 55,
            version_block_2=b"y" * 55,
        )
    with pytest.raises(ValueError, match="version_block_1"):
        KeybindingConfig12F6(
            client_hash=b"\x00" * 4,
            session_uuid=bytes(16),
            subkey=bytes(16),
            state_region=bytes(26),
            keybindings=(),
            version_block_1=b"x" * 50,  # wrong size
            version_block_2=b"y" * 55,
        )


def test_12f6_round_trip_arbitrary_keybindings():
    """Round-trip with a different number of keybindings than the capture."""
    msg = KeybindingConfig12F6(
        client_hash=b"\x42" * 4,
        session_uuid=bytes(range(16)),
        subkey=bytes(range(16, 32)),
        state_region=bytes(range(26)),
        keybindings=("@cc_a", "@cc_b", "@cc_c"),
        version_block_1=b"{1.2.3.45678901}.{" + b"\x00" * 36 + b"}",
        version_block_2=b"{9.8.7.65432101}.{" + b"\x00" * 36 + b"}",
    )
    encoded = encode_12f6(msg)
    decoded = decode_12f6(encoded)
    assert decoded == msg


def test_12f6_round_trip_empty_keybindings():
    msg = KeybindingConfig12F6(
        client_hash=b"\x00" * 4,
        session_uuid=bytes(16),
        subkey=bytes(16),
        state_region=bytes(26),
        keybindings=(),
        version_block_1=b"x" * 55,
        version_block_2=b"y" * 55,
    )
    assert decode_12f6(encode_12f6(msg)) == msg


# ---------------------------------------------------------------------------
# ReceiptHandshake 0x09fc (W direction, 102 bytes)
# ---------------------------------------------------------------------------

from .receipt_handshake_9fc import (  # noqa: E402
    ReceiptHandshake9FC,
    encode as encode_9fc,
    decode as decode_9fc,
    TYPED_BODY_SIZE as RH_TYPED_BODY_SIZE,
)


def test_9fc_round_trip_from_replay():
    """Round-trip the captured 0x09fc W singleton."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    candidates = [m for m in store.messages if m.type_id == 0x09fc]
    assert len(candidates) == 1
    msg = decode_9fc(candidates[0].body)
    # echoed_session_uuid duplicates the envelope session_uuid
    assert msg.echoed_session_uuid == msg.session_uuid
    assert encode_9fc(msg) == candidates[0].body


def test_9fc_size_is_102():
    assert RH_TYPED_BODY_SIZE == 102


def test_9fc_decode_wrong_size_rejects():
    with pytest.raises(ValueError, match="102"):
        decode_9fc(b"\x00" * 100)


def test_9fc_decode_wrong_remaining_length_rejects():
    bad = bytearray(b"\x00" * 102)
    bad[24:28] = b"\x00\x01\xbc\x27"  # set valid type header
    bad[7] = 0x99  # corrupt remaining_len
    with pytest.raises(ValueError, match="remaining-length"):
        decode_9fc(bytes(bad))


def test_9fc_validates_field_sizes():
    with pytest.raises(ValueError, match="state_block"):
        ReceiptHandshake9FC(
            client_hash=b"\x00" * 4,
            session_uuid=bytes(16),
            subkey=bytes(16),
            echoed_session_uuid=bytes(16),
            state_block=bytes(20),  # wrong size
            echoed_blob=bytes(16),
        )


def test_9fc_echoes_8e6_opaque_blob():
    """Cross-codec invariant (the load-bearing test): 0x09fc's
    echoed_blob is byte-identical to the paired 0x8e6's opaque_blob.
    Server-side replay must preserve this echo for client validation."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msg_8e6 = decode_8e6(
        next(m for m in store.messages if m.type_id == 0x8e6).body
    )
    msg_9fc = decode_9fc(
        next(m for m in store.messages
             if m.type_id == 0x9fc and m.direction == "W").body
    )
    assert msg_9fc.echoed_blob == msg_8e6.opaque_blob
    # And verify_8e6_echo helper agrees
    assert msg_9fc.verify_8e6_echo(msg_8e6.opaque_blob) is True
    # Mismatched blob must fail verification
    assert msg_9fc.verify_8e6_echo(b"\x00" * 16) is False


def test_9fc_subkey_upper_matches_8e6_identity_uuid_upper():
    """Cross-codec invariant: 0x09fc's subkey upper 8 = 0x8e6's
    identity_uuid upper 8 (receipt-handshake sub-system id)."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    msg_8e6 = decode_8e6(
        next(m for m in store.messages if m.type_id == 0x8e6).body
    )
    msg_9fc = decode_9fc(
        next(m for m in store.messages
             if m.type_id == 0x9fc and m.direction == "W").body
    )
    assert msg_9fc.subkey[:8] == msg_8e6.identity_uuid[:8]


# ---------------------------------------------------------------------------
# WorldDataBlob 0x065c (R direction, structural codec)
# ---------------------------------------------------------------------------

from .world_data_blob_65c import (  # noqa: E402
    WorldDataBlob65C,
    WorldDataRecord,
    encode as encode_65c,
    decode as decode_65c,
    RECORDS_OFFSET as WD_RECORDS_OFFSET,
)
from .handshake_blob_76 import (  # noqa: E402
    DEFAULT_SHARED_TRAILER as HSB_DEFAULT_SHARED_TRAILER_FOR_65C,
)


def test_65c_round_trip_from_replay():
    """Round-trip the captured 0x065c R singleton (12706 bytes)."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    candidates = [m for m in store.messages if m.type_id == 0x065c]
    assert len(candidates) == 1
    msg = decode_65c(candidates[0].body)
    # 42 records walked from the captured message.
    assert len(msg.records) == 42
    # First record: 42 bytes data + 80 FF padding (the leading section).
    assert len(msg.records[0].data) == 42
    assert msg.records[0].ff_padding_size == 80
    # Shared trailer must match handshake_blob_76's DEFAULT — load-bearing
    # cross-codec invariant.
    assert msg.shared_trailer == HSB_DEFAULT_SHARED_TRAILER_FOR_65C
    assert encode_65c(msg) == candidates[0].body


def test_65c_records_offset_is_93():
    assert WD_RECORDS_OFFSET == 93


def test_65c_decode_too_short_rejects():
    with pytest.raises(ValueError, match="too short"):
        decode_65c(b"\x00" * 50)


def test_65c_decode_wrong_sub_id_rejects():
    """Tamper with the sub_id field; codec should reject."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    body = bytearray(next(m for m in store.messages if m.type_id == 0x065c).body)
    body[21:25] = b"\xde\xad\xbe\xef"  # corrupt sub_id
    with pytest.raises(ValueError, match="sub_id mismatch"):
        decode_65c(bytes(body))


def test_65c_decode_wrong_shared_trailer_rejects():
    """The shared_trailer must match the handshake-family constant
    by default. Pass validate_shared_trailer=False to accept any."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)
    body = bytearray(next(m for m in store.messages if m.type_id == 0x065c).body)
    body[57] ^= 0xFF  # flip a byte in the shared_trailer
    with pytest.raises(ValueError, match="shared_trailer"):
        decode_65c(bytes(body))
    # With validation off, it should still decode
    msg = decode_65c(bytes(body), validate_shared_trailer=False)
    assert msg.shared_trailer != HSB_DEFAULT_SHARED_TRAILER_FOR_65C


def test_65c_record_validates_no_ff_in_data():
    with pytest.raises(ValueError, match="0xFF"):
        WorldDataRecord(data=b"\x01\xff\x02", ff_padding_size=0)


def test_65c_round_trip_synthetic():
    """Round-trip a synthetic 0x65c with a few small records."""
    msg = WorldDataBlob65C(
        count=2,
        redacted_id=b"\x00" * 16,
        ephemeral_block=b"\xab" * 32,
        records=(
            WorldDataRecord(data=b"\x01\x02\x03", ff_padding_size=5),
            WorldDataRecord(data=b"\x04\x05", ff_padding_size=3),
        ),
    )
    encoded = encode_65c(msg)
    decoded = decode_65c(encoded)
    assert decoded == msg


# ---------------------------------------------------------------------------
# Encoder-side convenience helpers
# ---------------------------------------------------------------------------

from .init_message_18a6 import make_init_message_18a6  # noqa: E402
from .heartbeat_15d import make_ack_for  # noqa: E402
from .session_clock_beacon import (  # noqa: E402
    make_session_clock_beacon,
    encode as encode_14f_helper,
    decode as decode_14f_helper,
)
from .session_identity_beacon import (  # noqa: E402
    make_session_identity_beacon,
    encode as encode_1b88_helper,
    decode as decode_1b88_helper,
)
from .session_message_a4 import (  # noqa: E402
    make_session_message_a4,
    encode as encode_a4_helper,
    decode as decode_a4_helper,
)
from .session_state import SessionState  # noqa: E402
from .init_message_18a6 import (  # noqa: E402
    DEFAULT_FLAGS as IM_DEFAULT_FLAGS,
    DEFAULT_BUILD_VERSION as IM_DEFAULT_BUILD_VERSION,
    encode as encode_18a6,
    decode as decode_18a6_helper,
)


def test_make_init_message_18a6_defaults():
    msg = make_init_message_18a6(
        counter=3,
        first_uuid_half=b"\xaa" * 8,
        session_uuid_lower=b"\xbb" * 8,
        second_id=b"\xcc" * 8,
    )
    assert msg.counter == 3
    assert msg.flags == IM_DEFAULT_FLAGS
    assert msg.build_version == IM_DEFAULT_BUILD_VERSION
    # Round-trip through wire encoding.
    decoded = decode_18a6_helper(encode_18a6(msg))
    assert decoded == msg


def test_make_init_message_18a6_overrides():
    msg = make_init_message_18a6(
        counter=42,
        first_uuid_half=b"\x00" * 8,
        session_uuid_lower=b"\x00" * 8,
        second_id=b"\x00" * 8,
        flags=0xDEADBEEF,
        build_version=0x999,
    )
    assert msg.counter == 42
    assert msg.flags == 0xDEADBEEF
    assert msg.build_version == 0x999


def test_make_ack_for_round_trip():
    """The ack body should wrap the ping body verbatim — server-side
    replay can use this helper to pre-compute expected acks."""
    ping = HeartbeatPing15D(counter=0xCAFE, nonce=0xBABE1234)
    ack = make_ack_for(ping, client_hash=b"\x01\x02\x03\x04")
    assert ack.client_hash == b"\x01\x02\x03\x04"
    assert ack.echoed_ping == ping
    # Encode and verify the ack body wraps the ping body at +0x18.
    encoded = encode_15d_ack(ack)
    assert len(encoded) == 36
    assert encoded[24:36] == encode_15d_ping(ping)


def test_make_ack_for_validates_client_hash():
    ping = HeartbeatPing15D(counter=1, nonce=2)
    with pytest.raises(ValueError, match="client_hash"):
        make_ack_for(ping, client_hash=b"\x00\x00\x00")  # 3 bytes


def test_make_session_clock_beacon_round_trip():
    msg = make_session_clock_beacon(
        session_clock=0x0b888d68,
        nonce=0x706c415b,
    )
    assert msg.session_clock == 0x0b888d68
    assert msg.nonce == 0x706c415b
    assert decode_14f_helper(encode_14f_helper(msg)) == msg


def test_make_session_identity_beacon_round_trip():
    uuid = bytes(range(16))
    msg = make_session_identity_beacon(uuid)
    assert msg.session_uuid == uuid
    encoded = encode_1b88_helper(msg)
    assert len(encoded) == 42
    assert decode_1b88_helper(encoded) == msg


def test_make_session_message_a4_round_trip():
    uuid = bytes.fromhex("1a954abc4b3185bfbe37c3d8592618e0")
    msg = make_session_message_a4(uuid)
    assert msg.session_uuid == uuid
    encoded = encode_a4_helper(msg)
    assert len(encoded) == 20
    assert decode_a4_helper(encoded) == msg


from .handshake_blob_76 import (  # noqa: E402
    make_handshake_blob_76,
    DEFAULT_SUB_ID as HSB_FACTORY_DEFAULT_SUB_ID,
    DEFAULT_SHARED_TRAILER as HSB_FACTORY_DEFAULT_TRAILER,
)
from .result_token_136a import make_result_token_136a  # noqa: E402
from .result_token_1097 import make_result_token_1097  # noqa: E402


def test_make_handshake_blob_76_defaults():
    """Factory uses the captured handshake-family sub_id + trailer
    by default — covers the canonical 0x40a / 0x1be construction."""
    msg = make_handshake_blob_76(
        type_id=0x40a,
        blob=b"\x42" * 32,
    )
    assert msg.type_id == 0x40a
    assert msg.sub_id == HSB_FACTORY_DEFAULT_SUB_ID
    assert msg.shared_trailer == HSB_FACTORY_DEFAULT_TRAILER
    assert msg.blob == b"\x42" * 32
    # Round-trip through wire encoding
    assert decode_hsb(encode_hsb(msg)) == msg


def test_make_handshake_blob_76_overrides():
    """Caller can override sub_id / trailer for non-handshake-family
    captures (e.g. a different signing scheme in a future session)."""
    custom_trailer = bytes(range(36))
    msg = make_handshake_blob_76(
        type_id=0x1be,
        blob=b"\x99" * 32,
        sub_id=b"\x00\x01\x02\x03",
        shared_trailer=custom_trailer,
    )
    assert msg.type_id == 0x1be
    assert msg.sub_id == b"\x00\x01\x02\x03"
    assert msg.shared_trailer == custom_trailer


def test_make_result_token_136a_default_result():
    """Default result=1 matches the captured value."""
    uuid = b"\xab" * 16
    msg = make_result_token_136a(uuid)
    assert msg.result == 1
    assert msg.identity_uuid == uuid
    assert decode_136a(encode_136a(msg)) == msg


def test_make_result_token_1097_default_result():
    """Default result=2 matches the captured value (companion to 0x1096)."""
    uuid = b"\xcd" * 16
    msg = make_result_token_1097(uuid)
    assert msg.result == 2
    assert msg.identity_uuid == uuid
    assert decode_1097(encode_1097(msg)) == msg


# ---------------------------------------------------------------------------
# SessionState (sketch — runtime-not-consumed structure)
# ---------------------------------------------------------------------------

def test_session_state_default_construction():
    """Default ctor yields a usable empty state."""
    s = SessionState()
    assert s.session_uuid == b""
    assert s.next_18a6_counter == 1
    assert s.extra == {}


def test_session_state_fresh_populates_session_uuid_and_nonce():
    s = SessionState.fresh()
    assert len(s.session_uuid) == 16
    assert 0 < s.session_nonce <= 0xFFFFFFFF
    # `extra` is per-instance (not shared across instances)
    s.extra["foo"] = 1
    assert SessionState.fresh().extra == {}


def test_session_state_can_drive_make_init_message_18a6():
    """Roundtrip: SessionState → make_init_message_18a6 → wire bytes."""
    s = SessionState.fresh()
    s.subkey_upper_8 = b"\xaa" * 8
    s.metadata_block_second_id = b"\xbb" * 8
    msg = make_init_message_18a6(
        counter=s.next_18a6_counter,
        first_uuid_half=s.subkey_upper_8,
        session_uuid_lower=s.session_uuid[8:],
        second_id=s.metadata_block_second_id,
    )
    assert msg.counter == 1
    encoded = encode_18a6(msg)
    assert decode_18a6_helper(encoded) == msg


# ---------------------------------------------------------------------------
# Library exports
# ---------------------------------------------------------------------------

def test_javelin_package_exports():
    """Spot-check that the top-level `server.javelin` namespace
    re-exports the most-used codec classes and helpers."""
    import server.javelin as j
    # Wire-framing primitives
    assert hasattr(j, "BitStream")
    assert hasattr(j, "MessageFlags")
    # Generic family + factories
    assert hasattr(j, "SubkeyBeacon")
    assert hasattr(j, "make_subkey_beacon")
    assert hasattr(j, "SUBKEY_FAMILY")
    # R + W codec classes
    assert hasattr(j, "InitMessage18A6")
    assert hasattr(j, "HeartbeatPing15D")
    assert hasattr(j, "ReceiptHandshake9FC")
    assert hasattr(j, "WorldDataBlob65C")
    # New encoder helpers
    assert hasattr(j, "make_init_message_18a6")
    assert hasattr(j, "make_ack_for")


# ---------------------------------------------------------------------------
# C→S framing CRC32 (wake 90 finding)
# ---------------------------------------------------------------------------

from .wire import (  # noqa: E402
    compute_cs_crc32,
    serialize_cs_envelope,
    parse_cs_envelope,
    fixup_cs_crc32,
    verify_cs_crc32,
)


def test_cs_crc32_matches_captured_w_messages():
    """Every captured W-direction message should have a CRC32 at offset 0
    that equals zlib.crc32(correlation_uuid + envelope), big-endian.

    Validated wake 90: 37 of 39 captured W messages match. The two
    exceptions (V3 request at seq 0, and 0x12f6 with 36-byte redacted
    spans) are documented and asserted below."""
    from pathlib import Path
    from .replay_store import ReplayStore
    p = Path(__file__).resolve().parents[2] / "info" / \
        "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        pytest.skip("replay file not present")
    store = ReplayStore(p)

    matches = 0
    mismatches = []
    for m in store.messages:
        if m.direction != "W" or len(m.body) < 24:
            continue
        if verify_cs_crc32(m.body):
            matches += 1
        else:
            mismatches.append((m.seq, m.type_id, m.has_redaction))

    # 37 of 39 captured W messages must match.
    assert matches == 37, f"expected 37 CRC matches, got {matches}"
    # The 2 known exceptions are V3 request (seq 0) and 0x12f6 (redacted)
    expected_exceptions = {(0, 0x13), (0x6b, 0x12f6)}
    actual_exceptions = {(seq, tid) for seq, tid, _ in mismatches}
    assert actual_exceptions == expected_exceptions, (
        f"unexpected CRC mismatches: {actual_exceptions}"
    )


def test_compute_cs_crc32_basic():
    """Direct CRC computation matches captured 0x5b2 message bytes."""
    correlation_uuid = bytes.fromhex("1a954abc4b3185bfbe37c3d8592618e0")
    envelope = bytes.fromhex(
        "0001b216"  # type header
        "180f8d4e573697c6"  # second_id
        "bf85314bbc4a951a"  # session_uuid_lower
        "00"  # count = 0
    )
    crc = compute_cs_crc32(correlation_uuid, envelope)
    assert crc == 0xf9b3ea55  # captured 0x5b2 small variant's CRC


def test_compute_cs_crc32_validates_correlation_uuid_length():
    with pytest.raises(ValueError, match="correlation_uuid"):
        compute_cs_crc32(b"\x00" * 8, b"some envelope")


def test_serialize_parse_cs_envelope_round_trip():
    """serialize_cs_envelope + parse_cs_envelope reverse cleanly."""
    correlation_uuid = bytes(range(16))
    envelope = b"\x00\x01\x99\x69" + b"\x42" * 17  # 0x1a59-shaped
    serialized = serialize_cs_envelope(correlation_uuid, envelope)
    crc, payload_size, parsed_uuid, parsed_env = parse_cs_envelope(serialized)
    assert parsed_uuid == correlation_uuid
    assert parsed_env == envelope
    assert payload_size == 16 + len(envelope)
    assert verify_cs_crc32(serialized)


def test_fixup_cs_crc32_repairs_zero_crc():
    """fixup_cs_crc32 replaces a zero/placeholder CRC with the correct value."""
    correlation_uuid = bytes(range(16))
    envelope = b"\x00\x01\x99\x69\x42" * 4  # synthetic envelope
    # Construct a bad message with CRC=0
    bad = (
        b"\x00\x00\x00\x00"  # crc32 placeholder
        + (16 + len(envelope)).to_bytes(4, "big")  # payload_size
        + correlation_uuid
        + envelope
    )
    assert not verify_cs_crc32(bad)
    fixed = fixup_cs_crc32(bad)
    assert verify_cs_crc32(fixed)
    # Idempotent
    assert fixup_cs_crc32(fixed) == fixed


def test_fixup_cs_crc32_works_with_existing_w_codec_output():
    """Encode any W codec normally (with arbitrary client_hash), then
    fixup_cs_crc32 to produce a wire-valid message — useful for
    server-side fresh emission code paths."""
    msg = SessionSubkeyBeacon1A59(
        client_hash=b"\x00" * 4,  # placeholder
        session_uuid=bytes.fromhex("1a954abc4b3185bfbe37c3d8592618e0"),
        subkey=bytes.fromhex("f8cbed57c68b18f4bf85314bbc4a951a"),
        counter=5,
    )
    encoded = encode_1a59(msg)
    assert not verify_cs_crc32(encoded)  # placeholder CRC
    fixed = fixup_cs_crc32(encoded)
    assert verify_cs_crc32(fixed)
    # The fixed bytes still decode as the same SessionSubkeyBeacon1A59
    # (fixup only touches the CRC field).
    redecoded = decode_1a59(fixed)
    # client_hash now holds the computed CRC, but other fields match
    assert redecoded.session_uuid == msg.session_uuid
    assert redecoded.subkey == msg.subkey
    assert redecoded.counter == msg.counter


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
