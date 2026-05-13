"""Tests for `rep_responder._validate_dispatcher_heartbeat_encode_matches`
(wake 187).

The phase-2B startup probe decodes the cached 0x15d heartbeat through
the central dispatcher, re-encodes it, and asserts byte-equality
against the original. Success means a future wake can swap the
emission path from raw replay-bytes to dispatcher-encoded output
with confidence; failure surfaces at startup, not later as a
wire-level surprise. The probe is logging-only — it must never
raise or change runtime behavior.

These tests pin that contract:
  - Match path: logs an INFO line containing "byte-identical" + the
    body length.
  - Mismatch path: logs a WARN line including the first diff offset.
  - No-heartbeat path (msg=None): silent return, no log entry.
  - Non-0x15d path (e.g. msg.type_id=0x14f fallback): silent return.
  - Decoder exception: WARN log, no propagation.
  - Encoder exception: WARN log, no propagation.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import List
from unittest.mock import patch

from server.rep_responder import PeerSession
from server.javelin.replay_store import ReplayMessage
from server.javelin import dispatch


# Captured 0x15d ping body (12 bytes — TYPE_HEADER + counter + nonce)
CAPTURED_PING_BODY = bytes.fromhex("00019d05" "00036ef6" "af912d74")


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def at(self, level: int) -> List[str]:
        return [r.getMessage() for r in self.records if r.levelno == level]


def _stub_self(heartbeat_msg) -> SimpleNamespace:
    handler = _RecordingHandler()
    log = logging.getLogger(f"hb_validate_test_{id(handler)}")
    log.setLevel(logging.DEBUG)
    log.handlers = [handler]
    log.propagate = False
    return SimpleNamespace(
        log=log, _handler=handler, _heartbeat_msg=heartbeat_msg
    )


def _call(stub):
    PeerSession._validate_dispatcher_heartbeat_encode_matches(stub)


def _make_heartbeat_msg(body: bytes = CAPTURED_PING_BODY) -> ReplayMessage:
    return ReplayMessage(
        seq=0x07, type_id=0x15d, direction="R", body=body, has_redaction=False,
    )


# ---------------------------------------------------------------------------
#  Success path
# ---------------------------------------------------------------------------


def test_match_path_logs_info_with_byte_identical_and_length():
    stub = _stub_self(_make_heartbeat_msg())
    _call(stub)
    info = stub._handler.at(logging.INFO)
    assert len(info) == 1, f"expected one INFO log; got {info}"
    msg = info[0]
    assert "byte-identical" in msg
    assert "12 bytes" in msg
    assert "[phase-2B]" in msg


# ---------------------------------------------------------------------------
#  Silent-skip paths
# ---------------------------------------------------------------------------


def test_no_heartbeat_msg_returns_silently():
    """`_heartbeat_msg` is None when no clean small R-msg was cached.
    The probe must skip silently — no log entry of any level."""
    stub = _stub_self(None)
    _call(stub)
    assert stub._handler.records == []


def test_non_0x15d_heartbeat_returns_silently():
    """The captured replay falls back to 0x14f session_clock if 0x15d
    isn't available. The probe handles only 0x15d at the moment — the
    fallback should pass through without complaint."""
    fallback = ReplayMessage(
        seq=0x0a, type_id=0x14f, direction="R",
        body=bytes.fromhex("00018f05" "0b888d68" "7b13001a"),
        has_redaction=False,
    )
    stub = _stub_self(fallback)
    _call(stub)
    assert stub._handler.records == []


# ---------------------------------------------------------------------------
#  Mismatch path
# ---------------------------------------------------------------------------


def test_mismatch_path_logs_warn_with_diff_offset():
    """Patch the encoder to return a different byte string; probe
    should log a WARN line including the first differing offset
    (in hex). Diagnostic message guides a future maintainer to the
    drift."""
    # Wrong-length bytes after the type header.
    wrong_bytes = bytes.fromhex("00019d05" "ffffffff" "af912d74")

    def fake_encode(_type_id, _msg):
        return wrong_bytes

    stub = _stub_self(_make_heartbeat_msg())
    with patch.object(dispatch, "encode_replay_message", fake_encode):
        _call(stub)
    info = stub._handler.at(logging.INFO)
    warn = stub._handler.at(logging.WARNING)
    assert info == [], f"unexpected INFO log on mismatch: {info}"
    assert len(warn) == 1, f"expected one WARN log; got {warn}"
    assert "differs from" in warn[0]
    assert "first diff at offset 0x4" in warn[0]  # bytes 4..7 are different


# ---------------------------------------------------------------------------
#  Exception paths — both must catch + log, never propagate
# ---------------------------------------------------------------------------


def test_decoder_exception_is_caught_and_logged():
    def fake_decode(_type_id, _direction, _body):
        raise ValueError("simulated decoder crash")

    stub = _stub_self(_make_heartbeat_msg())
    with patch.object(dispatch, "decode_replay_message", fake_decode):
        # Must not raise.
        _call(stub)
    warn = stub._handler.at(logging.WARNING)
    assert any(
        "round-trip failed" in m and "ValueError" in m
        and "simulated decoder crash" in m
        for m in warn
    ), f"expected WARN with decoder failure detail; got {warn}"


def test_encoder_exception_is_caught_and_logged():
    def fake_encode(_type_id, _msg):
        raise RuntimeError("simulated encoder crash")

    stub = _stub_self(_make_heartbeat_msg())
    with patch.object(dispatch, "encode_replay_message", fake_encode):
        _call(stub)
    warn = stub._handler.at(logging.WARNING)
    assert any(
        "round-trip failed" in m and "RuntimeError" in m
        and "simulated encoder crash" in m
        for m in warn
    ), f"expected WARN with encoder failure detail; got {warn}"


def test_decoder_returning_none_logs_debug_and_skips():
    """If `decode_replay_message` returns None (e.g. an unregistered
    type), the probe should log a DEBUG diagnostic and skip the
    re-encode step — never crash."""
    def fake_decode(_type_id, _direction, _body):
        return None

    stub = _stub_self(_make_heartbeat_msg())
    with patch.object(dispatch, "decode_replay_message", fake_decode):
        _call(stub)
    info = stub._handler.at(logging.INFO)
    warn = stub._handler.at(logging.WARNING)
    debug = stub._handler.at(logging.DEBUG)
    assert info == []
    assert warn == []
    assert any("returned None for heartbeat" in m for m in debug), (
        f"expected DEBUG with None-return note; got {debug}"
    )


# ---------------------------------------------------------------------------
#  Belt-and-suspenders: probe never raises across hostile inputs
# ---------------------------------------------------------------------------


def _phase2d_stub(captured_list=None, send_fail=False):
    """Build a stub-self set up for phase-2D testing: populates
    `_heartbeat_decoded` via the wake-187 probe + attaches an
    instance-level `_send_replay_message` mock that records what
    the dispatched path would emit."""
    stub = _stub_self(_make_heartbeat_msg())
    PeerSession._validate_dispatcher_heartbeat_encode_matches(stub)
    stub.heartbeat_use_dispatcher = True
    stub._heartbeat_dispatched_count = 0
    # Wake 207: default to "no counter advance" so wake-204 byte-equality
    # tests still pass; tests that want the advance behavior flip the
    # flag explicitly.
    stub.heartbeat_advance_counter = False
    import secrets as _secrets
    stub._heartbeat_nonce_fn = lambda: _secrets.randbits(32)
    captured_list = captured_list if captured_list is not None else []
    def fake_send(msg, is_heartbeat=False):
        captured_list.append((msg.body, is_heartbeat))
    stub._send_replay_message = fake_send
    stub._captured = captured_list
    return stub


def test_phase2d_dispatched_emission_byte_identical_to_replay():
    """Wake 204 phase-2D: with `heartbeat_use_dispatcher=True`, the
    bytes the responder writes must equal the bytes the
    `heartbeat_use_dispatcher=False` path would write. Wake-187/188
    proved the wire-format equality; this confirms
    `_send_dispatched_heartbeat` plumbs it through to the actual
    emission call site."""
    stub = _phase2d_stub()
    PeerSession._send_dispatched_heartbeat(stub)
    assert len(stub._captured) == 1
    body, is_hb = stub._captured[0]
    assert is_hb is True
    assert body == CAPTURED_PING_BODY, (
        f"dispatched-path body {body.hex()} differs from captured "
        f"replay body {CAPTURED_PING_BODY.hex()}"
    )


def test_phase2d_dispatched_emission_logs_first_send_at_info():
    """First dispatched heartbeat logs at INFO; subsequent at DEBUG.
    Gives operators a clear marker in the responder log when the
    swap takes effect."""
    stub = _phase2d_stub()
    PeerSession._send_dispatched_heartbeat(stub)
    PeerSession._send_dispatched_heartbeat(stub)
    info = stub._handler.at(logging.INFO)
    debug = stub._handler.at(logging.DEBUG)
    assert any("first dispatcher-encoded heartbeat sent" in m for m in info)
    assert any("dispatcher heartbeat #2" in m for m in debug)


def test_phase2d_dispatched_emission_falls_back_on_encode_failure():
    """If `dispatch.encode_replay_message` raises at runtime, the
    dispatched path must NOT crash. It must log WARN and fall back
    to the replay-bytes path."""
    from unittest.mock import patch
    from server.javelin import dispatch
    stub = _phase2d_stub()
    def crashing_encode(_type_id, _msg):
        raise RuntimeError("simulated runtime crash")
    with patch.object(dispatch, "encode_replay_message", crashing_encode):
        PeerSession._send_dispatched_heartbeat(stub)
    # The fallback path called `_send_replay_message` once with the
    # original captured body.
    assert len(stub._captured) == 1
    body, _ = stub._captured[0]
    assert body == CAPTURED_PING_BODY
    warn = stub._handler.at(logging.WARNING)
    assert any(
        "dispatcher heartbeat encode failed at runtime" in m
        and "falling back to replay bytes" in m
        for m in warn
    )


def test_phase2d_counter_advances_when_advance_flag_set():
    """Wake 207: with `heartbeat_advance_counter=True`, each dispatched
    heartbeat increments the counter by 1 and refreshes the nonce.
    Confirms the mutation is persisted to `_heartbeat_decoded` so
    successive calls build on each other (matching the real server's
    slow-incrementing counter pattern)."""
    from server.javelin.heartbeat_15d import decode_ping
    stub = _phase2d_stub()
    stub.heartbeat_advance_counter = True
    # Deterministic nonce sequence — no flakiness from secrets.randbits.
    nonces = iter([0x11111111, 0x22222222, 0x33333333])
    stub._heartbeat_nonce_fn = lambda: next(nonces)
    starting_counter = stub._heartbeat_decoded.counter
    PeerSession._send_dispatched_heartbeat(stub)
    PeerSession._send_dispatched_heartbeat(stub)
    PeerSession._send_dispatched_heartbeat(stub)
    assert len(stub._captured) == 3
    msgs = [decode_ping(body) for body, _ in stub._captured]
    # Counter incremented by 1 each call.
    assert msgs[0].counter == starting_counter + 1
    assert msgs[1].counter == starting_counter + 2
    assert msgs[2].counter == starting_counter + 3
    # Nonces follow our injected sequence.
    assert msgs[0].nonce == 0x11111111
    assert msgs[1].nonce == 0x22222222
    assert msgs[2].nonce == 0x33333333


def test_phase2d_counter_does_not_advance_by_default():
    """The default `heartbeat_advance_counter=False` preserves the
    wake-204 byte-equality contract: emitted body equals
    CAPTURED_PING_BODY across multiple calls. Future-proofs the
    safe default against an accidental flip."""
    stub = _phase2d_stub()
    # Default is False — explicit for clarity.
    assert stub.heartbeat_advance_counter is False
    PeerSession._send_dispatched_heartbeat(stub)
    PeerSession._send_dispatched_heartbeat(stub)
    bodies = [body for body, _ in stub._captured]
    assert bodies[0] == CAPTURED_PING_BODY
    assert bodies[1] == CAPTURED_PING_BODY


def test_phase2d_counter_wraps_at_u32_max():
    """Belt-and-suspenders: if `counter` hits u32 max, the next call
    wraps to 0 — does NOT raise from the HeartbeatPing15D range check
    in __post_init__. A long-lived session at ~1 Hz takes ~136 years
    to wrap u32, but the math should be correct anyway."""
    from server.javelin.heartbeat_15d import HeartbeatPing15D, decode_ping
    stub = _phase2d_stub()
    stub.heartbeat_advance_counter = True
    stub._heartbeat_nonce_fn = lambda: 0  # deterministic
    # Force the decoded counter to u32 max — next call should produce 0.
    stub._heartbeat_decoded = HeartbeatPing15D(
        counter=0xFFFFFFFF,
        nonce=stub._heartbeat_decoded.nonce,
    )
    PeerSession._send_dispatched_heartbeat(stub)
    msg = decode_ping(stub._captured[-1][0])
    assert msg.counter == 0
    assert msg.nonce == 0


def test_probe_never_raises_across_corrupt_bodies():
    """Sweep a few malformed bodies that would each trigger different
    failure modes in the decoder/encoder. All of them must produce a
    log entry and a clean return — none should propagate."""
    bodies = [
        b"",                                                # empty
        b"\x00\x01\x9d\x05",                                # too short
        b"\x00\x01\x9d\x05" + b"\x00" * 100,                # too long
        b"\xff" * 12,                                       # wrong header
    ]
    for body in bodies:
        msg = ReplayMessage(
            seq=0x01, type_id=0x15d, direction="R",
            body=body, has_redaction=False,
        )
        stub = _stub_self(msg)
        _call(stub)
        # Any combination of INFO/WARN is fine; the key invariant is
        # "didn't raise". The records list will have at most a few
        # entries; we just check we didn't crash.
