"""Unit tests for `server.javelin.replay_substitution`.

Verifies the SubstitutionContext.apply() length-preservation invariant
and per-field-class substitution behavior using synthetic ReplayMessages.
"""

from __future__ import annotations

import uuid

from server.javelin.replay_store import ReplayMessage
from server.javelin.replay_substitution import (
    LENGTH_DEFAULT,
    SubstitutionContext,
    _persona_uuid_text_from_persona_id,
    _stub_character_uuid_from_persona,
)
from server.javelin.v3_request import V3RegistrationRequest


_FIXTURE_PERSONA_UUID = "11111111-2222-3333-4444-555566667777"
_FIXTURE_SESSION_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeffff0000"
_FIXTURE_PERSONA_ID = f"amzn1.developerPersonaId.{_FIXTURE_PERSONA_UUID}"


def _ctx(**overrides) -> SubstitutionContext:
    req = V3RegistrationRequest(
        persona_id=_FIXTURE_PERSONA_ID,
        session_uuid=_FIXTURE_SESSION_UUID,
    )
    kwargs = {
        "req": req,
        "session_token": b"f" * 32,
    }
    kwargs.update(overrides)
    return SubstitutionContext.from_v3_and_session(**kwargs)


def _msg(body: bytes, spans: list[tuple[int, int]], seq: int = 0x25) -> ReplayMessage:
    return ReplayMessage(
        seq=seq,
        type_id=0x8,
        direction="R",
        body=body,
        has_redaction=bool(spans),
        redacted_spans=spans,
    )


def test_persona_uuid_text_extraction():
    assert _persona_uuid_text_from_persona_id(_FIXTURE_PERSONA_ID) == _FIXTURE_PERSONA_UUID
    assert _persona_uuid_text_from_persona_id("") == ""
    assert _persona_uuid_text_from_persona_id("not-a-persona") == ""


def test_stub_character_uuid_is_deterministic():
    a = _stub_character_uuid_from_persona(_FIXTURE_PERSONA_ID)
    b = _stub_character_uuid_from_persona(_FIXTURE_PERSONA_ID)
    assert a == b
    different = _stub_character_uuid_from_persona("amzn1.developerPersonaId.other")
    assert a != different


def test_context_built_from_v3_populates_fields():
    ctx = _ctx()
    assert ctx.persona_id_text == _FIXTURE_PERSONA_ID
    assert ctx.persona_uuid_text == _FIXTURE_PERSONA_UUID
    assert ctx.persona_uuid_bytes == uuid.UUID(_FIXTURE_PERSONA_UUID).bytes
    assert ctx.session_uuid_text == _FIXTURE_SESSION_UUID
    assert ctx.session_uuid_bytes == uuid.UUID(_FIXTURE_SESSION_UUID).bytes
    assert len(ctx.session_token) == 32
    assert len(ctx.character_uuid_bytes) == 16
    assert len(ctx.character_uuid_text) == 36


def test_apply_passes_through_clean_messages():
    ctx = _ctx()
    body = bytes(range(32))
    m = _msg(body, [])
    assert ctx.apply(m) == body


def test_apply_preserves_length_for_every_class():
    ctx = _ctx()
    # One span per known length class, in the order the LENGTH_DEFAULT
    # dispatch supports. Total body covers each length back-to-back.
    classes = sorted(LENGTH_DEFAULT.keys())
    body = bytearray()
    spans = []
    for ln in classes:
        spans.append((len(body), ln))
        body.extend(b"\x00" * ln)
    m = _msg(bytes(body), spans)

    out = ctx.apply(m)
    assert len(out) == len(m.body)


def test_apply_substitutes_persona_uuid_for_16_byte_span():
    ctx = _ctx()
    body = bytearray(b"\x00" * 16)
    m = _msg(bytes(body), [(0, 16)])
    out = ctx.apply(m)
    assert out == ctx.persona_uuid_bytes


def test_apply_substitutes_session_uuid_text_for_36_byte_span():
    ctx = _ctx()
    body = bytearray(b"\x00" * 36)
    m = _msg(bytes(body), [(0, 36)])
    out = ctx.apply(m)
    assert out == ctx.session_uuid_text.encode("ascii")


def test_apply_substitutes_persona_id_for_61_byte_span():
    ctx = _ctx()
    body = bytearray(b"\x00" * 61)
    m = _msg(bytes(body), [(0, 61)])
    out = ctx.apply(m)
    assert out == _FIXTURE_PERSONA_ID.encode("ascii")
    assert len(out) == 61


def test_apply_zero_fills_8_byte_azcore_hash():
    ctx = _ctx()
    # AzCore hash spans are zero-filled in v1 (design risk #1).
    body = bytearray(b"\xff" * 8)
    m = _msg(bytes(body), [(0, 8)])
    out = ctx.apply(m)
    assert out == b"\x00" * 8


def test_apply_pads_display_name_to_target_length():
    ctx = _ctx(character_display_name="abc")
    for length in (18, 19, 20):
        body = bytearray(b"\x00" * length)
        m = _msg(bytes(body), [(0, length)])
        out = ctx.apply(m)
        assert len(out) == length
        assert out.startswith(b"abc")


def test_apply_truncates_display_name_too_long():
    long_name = "x" * 50
    ctx = _ctx(character_display_name=long_name)
    body = bytearray(b"\x00" * 18)
    m = _msg(bytes(body), [(0, 18)])
    out = ctx.apply(m)
    assert out == b"x" * 18


def test_apply_warns_on_unknown_length():
    ctx = _ctx()
    # 7-byte span isn't in LENGTH_DEFAULT.
    body = bytearray(b"\x00" * 7)
    m = _msg(bytes(body), [(0, 7)])
    out = ctx.apply(m)
    assert len(out) == 7
    assert any("len=7" in w for w in ctx.warnings)


def test_apply_handles_multiple_spans_in_order():
    ctx = _ctx()
    # Layout: [16 persona-uuid][8 hash][36 session-uuid-text]
    body = bytearray(b"\x00" * (16 + 8 + 36))
    spans = [(0, 16), (16, 8), (24, 36)]
    m = _msg(bytes(body), spans)
    out = ctx.apply(m)

    assert out[:16] == ctx.persona_uuid_bytes
    assert out[16:24] == b"\x00" * 8
    assert out[24:60] == ctx.session_uuid_text.encode("ascii")


def test_warnings_accumulate_across_calls():
    ctx = _ctx()
    body = bytearray(b"\x00" * 7)
    m = _msg(bytes(body), [(0, 7)])
    before = len(ctx.warnings)
    ctx.apply(m)
    ctx.apply(m)
    assert len(ctx.warnings) >= before + 2
