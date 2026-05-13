"""Tests for `rep_responder._shadow_decode_record` (wake 157).

The shadow-decode path runs every inbound MessageRecord payload through
the central dispatcher and logs the outcome, *without* affecting any
runtime behavior. These tests pin that wiring:

  - Typed-envelope payloads route through `dispatch.decode_replay_message`
    and the log records the decoded class name.
  - Non-typed payloads (system messages, V3 request, etc.) are silently
    skipped — no log entry, no exception.
  - Unsupported type-ids log "not in dispatcher" but don't raise.
  - Codec failures (corrupt payloads) log the exception but don't raise.

The tests exercise the method directly with a stub `self` carrying a
captured-log adapter. No SSL setup; no socket; no PeerSession
construction (it requires a live SSL connection).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import List

from server.rep_responder import PeerSession
from server.javelin.frame import MessageRecord


class _RecordingHandler(logging.Handler):
    """Capture log records for assertion without touching stdout."""

    def __init__(self) -> None:
        super().__init__()
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def messages(self) -> List[str]:
        return [r.getMessage() for r in self.records]


def _stub_self() -> SimpleNamespace:
    """Minimum object satisfying `_shadow_decode_record`'s `self.log` access."""
    handler = _RecordingHandler()
    log = logging.getLogger(f"shadow_test_{id(handler)}")
    log.setLevel(logging.DEBUG)
    log.handlers = [handler]
    log.propagate = False
    return SimpleNamespace(log=log, _handler=handler)


def _call_shadow(stub: SimpleNamespace, payload: bytes) -> List[str]:
    """Run `_shadow_decode_record` against a stub-self with the given payload.
    Returns captured log messages."""
    record = MessageRecord(channel=0, payload=payload)
    PeerSession._shadow_decode_record(stub, record)
    return stub._handler.messages()


# ---------------------------------------------------------------------------
#  Typed-envelope payloads route through the dispatcher
# ---------------------------------------------------------------------------


def test_shadow_decodes_0x15d_heartbeat_ping():
    # Captured 0x15d ping (12 bytes): TYPE_HEADER + counter + nonce.
    payload = bytes.fromhex("00019d05" "00036ef6" "af912d74")
    stub = _stub_self()
    msgs = _call_shadow(stub, payload)
    assert len(msgs) == 1
    assert "type_id=0x15d" in msgs[0]
    assert "HeartbeatPing15D" in msgs[0]


def test_shadow_decodes_0x14f_clock_beacon():
    # Captured 0x14f session_clock (12 bytes).
    payload = bytes.fromhex("00018f05" "0b888d68" "7b13001a")
    stub = _stub_self()
    msgs = _call_shadow(stub, payload)
    assert len(msgs) == 1
    assert "type_id=0x14f" in msgs[0]
    assert "SessionClockBeacon" in msgs[0]


def test_shadow_decodes_0x651_empty_marker():
    # Captured 0x651 empty marker (4 bytes — just the type header).
    payload = bytes.fromhex("00019119")
    stub = _stub_self()
    msgs = _call_shadow(stub, payload)
    assert len(msgs) == 1
    assert "type_id=0x651" in msgs[0]
    assert "EmptyMarker651" in msgs[0]


# ---------------------------------------------------------------------------
#  Non-typed payloads are silently skipped
# ---------------------------------------------------------------------------


def test_shadow_skips_short_payload():
    """Payloads under 4 bytes can't be typed — skip without logging."""
    stub = _stub_self()
    msgs = _call_shadow(stub, b"\x00\x01\x9d")
    assert msgs == []


def test_shadow_skips_wrong_envelope_prefix():
    """Payloads not starting with `00 01` are non-typed — skip without
    logging. Covers V3 system messages and anything else routed by
    the responder outside the typed-envelope wire format."""
    stub = _stub_self()
    msgs = _call_shadow(stub, b"\x42\x42\x9d\x05\xff\xff")
    assert msgs == []


def test_shadow_skips_envelope_byte2_missing_marker_bit():
    """Even with the `00 01` prefix, byte 2 must have the high bit set
    (encodes `(type_id & 0x3f) | 0x80`). Without that, the payload
    isn't a valid typed envelope — skip."""
    stub = _stub_self()
    # 0x05 in byte 2: no high bit set, so this is not a typed envelope.
    msgs = _call_shadow(stub, b"\x00\x01\x05\x05\xff\xff")
    assert msgs == []


# ---------------------------------------------------------------------------
#  Type-id known to envelope but unsupported by the dispatcher
# ---------------------------------------------------------------------------


def test_shadow_logs_unsupported_type_id():
    """A type-id that decodes from the envelope but isn't in the
    DECODERS table logs at debug level."""
    # Pick a type-id that's unlikely to ever be registered. 0x3fff
    # encodes as (0x3f | 0x80) = 0xbf, (0x3fff >> 6) = 0xff.
    payload = b"\x00\x01\xbf\xff" + b"\x00" * 8
    stub = _stub_self()
    msgs = _call_shadow(stub, payload)
    assert len(msgs) == 1
    assert "type_id=0x3fff" in msgs[0]
    assert "not in dispatcher" in msgs[0]


# ---------------------------------------------------------------------------
#  Codec failure is logged but never raised
# ---------------------------------------------------------------------------


def test_shadow_logs_decode_failure_without_raising():
    """When the type-id matches a known codec but the body is the wrong
    size, the codec raises ValueError. The shadow path catches and logs
    at debug level — it must not propagate."""
    # 0x15d header with wrong-sized body (5 bytes total instead of 12).
    bad_payload = b"\x00\x01\x9d\x05\xff"
    stub = _stub_self()
    msgs = _call_shadow(stub, bad_payload)
    assert len(msgs) == 1
    assert "type_id=0x15d" in msgs[0]
    assert "decode failed" in msgs[0]
    # The exception name should appear in the log message
    assert "ValueError" in msgs[0]


def test_shadow_does_not_raise_on_decoder_exception():
    """Belt-and-suspenders: even a malformed payload that triggers a
    deeper crash must not propagate from `_shadow_decode_record`."""
    stub = _stub_self()
    # Try a few payloads that are individually invalid
    bad_payloads = [
        b"\x00\x01\x9d\x05",                              # 0x15d, too short
        b"\x00\x01\x8f\x05" + b"\x00" * 100,              # 0x14f, too long
        b"\x00\x01\x91\x19" + b"\x42\x42",                # 0x651, extra bytes
    ]
    for p in bad_payloads:
        # If any of these raises, the test will fail naturally
        _call_shadow(stub, p)
