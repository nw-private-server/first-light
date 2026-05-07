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


def test_apply_preserves_surrounding_bytes():
    """A span in the middle of a body must not perturb the bytes before
    or after it. Guards against off-by-one slicing in `_field_bytes`."""
    ctx = _ctx()
    prefix = b"\xaa\xbb\xcc\xdd"
    suffix = b"\x11\x22\x33\x44\x55"
    body = prefix + b"\x00" * 16 + suffix
    m = _msg(body, [(len(prefix), 16)])
    out = ctx.apply(m)
    assert out[:len(prefix)] == prefix
    assert out[len(prefix):len(prefix) + 16] == ctx.persona_uuid_bytes
    assert out[-len(suffix):] == suffix


def test_apply_zero_fills_when_persona_uuid_missing():
    """Empty persona_id → persona_uuid_bytes is b''. The 16-byte default
    rule must still produce a length-preserving zero-filled span instead
    of crashing or shrinking the body."""
    req = V3RegistrationRequest(persona_id="", session_uuid=_FIXTURE_SESSION_UUID)
    ctx = SubstitutionContext.from_v3_and_session(req=req, session_token=b"f" * 32)
    body = bytearray(b"\xff" * 16)
    m = _msg(bytes(body), [(0, 16)])
    out = ctx.apply(m)
    assert out == b"\x00" * 16
    assert any("persona" in w.lower() for w in ctx.warnings)


def test_apply_zero_fills_when_session_uuid_text_missing():
    """Empty session_uuid → session_uuid_text is "". The 36-byte default
    rule (session_uuid_text) zero-fills rather than emitting a short body."""
    req = V3RegistrationRequest(persona_id=_FIXTURE_PERSONA_ID, session_uuid="")
    ctx = SubstitutionContext.from_v3_and_session(req=req, session_token=b"f" * 32)
    body = bytearray(b"\xff" * 36)
    m = _msg(bytes(body), [(0, 36)])
    out = ctx.apply(m)
    assert out == b"\x00" * 36
    assert len(out) == 36


def test_apply_partial_fill_on_unknown_span_in_middle():
    """A body with [known, unknown, known] spans. The unknown one keeps
    its original bytes (per the "leaving zero-filled" warning path),
    while the known ones get substituted, and surrounding inter-span
    bytes are untouched."""
    ctx = _ctx()
    persona_span = b"\x00" * 16   # 16 → persona_uuid_bytes
    weird_span = b"\xde\xad\xbe\xef\x55\x66\x77"  # length 7 — no rule
    session_span = b"\x00" * 36
    pad = b"PAD!"
    body = persona_span + pad + weird_span + pad + session_span
    spans = [
        (0, 16),
        (16 + len(pad), 7),
        (16 + len(pad) + 7 + len(pad), 36),
    ]
    m = _msg(body, spans)
    out = ctx.apply(m)

    assert out[:16] == ctx.persona_uuid_bytes
    assert out[16:16 + len(pad)] == pad
    # Unknown span kept its original bytes (zero-filled per design;
    # weird_span supplies the source pattern in our test fixture).
    assert out[16 + len(pad):16 + len(pad) + 7] == weird_span
    assert out[16 + len(pad) + 7:16 + len(pad) + 7 + len(pad)] == pad
    assert out[-36:] == ctx.session_uuid_text.encode("ascii")
    assert any("len=7" in w for w in ctx.warnings)


def test_apply_handles_span_at_end_of_body():
    """Span at the absolute tail of the body — `out[offset:offset+length]`
    slicing must cover the final bytes inclusive."""
    ctx = _ctx()
    prefix = b"HEAD" + b"\xaa" * 10
    body = prefix + b"\x00" * 16
    m = _msg(body, [(len(prefix), 16)])
    out = ctx.apply(m)
    assert out[:len(prefix)] == prefix
    assert out[-16:] == ctx.persona_uuid_bytes
    assert len(out) == len(body)


def test_apply_handles_unordered_spans():
    """SPAN_RULES doesn't promise any ordering; current implementation
    iterates `redacted_spans` in list order. A capture's parser could
    in principle emit them out of file-offset order. Verify both spans
    end up substituted regardless of order."""
    ctx = _ctx()
    body = b"\x00" * 16 + b"GAP!" + b"\x00" * 36
    # Late span first.
    spans = [(20, 36), (0, 16)]
    m = _msg(body, spans)
    out = ctx.apply(m)
    assert out[:16] == ctx.persona_uuid_bytes
    assert out[16:20] == b"GAP!"
    assert out[20:] == ctx.session_uuid_text.encode("ascii")


def test_session_token_field_is_addressable():
    """`session_token` is in `_field_bytes` for forward-compat. Confirm
    that if SPAN_RULES routes a span to it, the bytes flow through.
    Emulated by calling _field_bytes directly (the dispatch path)."""
    token = b"\xab" * 32
    ctx = _ctx(session_token=token)
    out = ctx._field_bytes("session_token", 32)
    assert out == token
    # And the _fit fallback handles a wrong-length request.
    assert ctx._fit(out, 16) == token[:16]
    assert ctx._fit(out, 40) == token + b"\x00" * 8


def test_unknown_field_name_in_span_rules_zero_fills():
    """If a (seq, length) override in SPAN_RULES points at a field name
    not handled by `_field_bytes`, the fallback is zero-fill — not a
    KeyError. Exercises the trailing `return b"\\x00" * length` branch."""
    ctx = _ctx()
    # Direct call exercises the dispatch tail.
    out = ctx._field_bytes("not_a_real_field", 5)
    assert out == b"\x00" * 5


def test_apply_no_redaction_returns_same_object():
    """Optimization invariant: a clean message (`has_redaction=False`)
    short-circuits and returns the original body without copying."""
    ctx = _ctx()
    body = b"clean payload"
    m = _msg(body, [])
    out = ctx.apply(m)
    assert out is m.body  # same object, not just equal
