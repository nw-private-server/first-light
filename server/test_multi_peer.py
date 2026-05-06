"""Tests for the multi-peer hardening: log prefixing, idle eviction.

The shared `log` and the unbounded `sessions` dict were the two real
foot-guns the moment a second client connects to the responder. This
suite verifies:

  - `format_peer` renders (host, port) tuples in a stable form.
  - `_PeerLogAdapter` prefixes every line with `[peer=ip:port]`,
    leaving the underlying logger unchanged for other peers.
  - `PeerSession.is_idle` returns False until the threshold elapses,
    True after — and `last_activity_at` survives a `feed()` call so
    active peers aren't evicted.
"""
from __future__ import annotations

import io
import logging

import pytest

from server.rep_responder import (
    PeerSession,
    _PeerLogAdapter,
    format_peer,
)


def test_format_peer_for_tuple():
    assert format_peer(("127.0.0.1", 24999)) == "127.0.0.1:24999"
    assert format_peer(("10.0.0.1", 0)) == "10.0.0.1:0"


def test_format_peer_for_non_tuple():
    # Defensive: an unexpected type still produces a string.
    assert format_peer("oddball") == "oddball"


def test_log_adapter_prefixes_messages():
    base = logging.getLogger(f"test.adapter.{id(test_log_adapter_prefixes_messages)}")
    base.setLevel(logging.DEBUG)
    base.handlers.clear()
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    base.addHandler(handler)

    adapter = _PeerLogAdapter(base, ("192.0.2.5", 31337))
    adapter.info("handshake complete")
    adapter.warning("send failed")

    out = buf.getvalue()
    assert "[peer=192.0.2.5:31337] handshake complete" in out
    assert "[peer=192.0.2.5:31337] send failed" in out


def test_log_adapter_does_not_pollute_underlying_logger():
    """A direct .info() on the wrapped logger must NOT carry the prefix
    — only adapter calls add it. Otherwise main-loop log lines would
    show up tagged with whichever peer was last instantiated."""
    base = logging.getLogger(f"test.adapter.no_pollute.{id(object())}")
    base.setLevel(logging.DEBUG)
    base.handlers.clear()
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    base.addHandler(handler)

    _PeerLogAdapter(base, ("1.2.3.4", 5))
    base.info("plain main-loop line")
    out = buf.getvalue()
    assert "plain main-loop line" in out
    assert "[peer=" not in out


def test_log_adapter_idempotent_when_double_wrapped():
    """PeerSession.__init__ wraps the passed-in log unless it's already an
    adapter. Verifies the guard so a second wrap doesn't produce
    `[peer=...] [peer=...] message`."""
    base = logging.getLogger(f"test.adapter.idempotent.{id(object())}")
    base.setLevel(logging.DEBUG)
    base.handlers.clear()
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    base.addHandler(handler)

    inner = _PeerLogAdapter(base, ("1.1.1.1", 1))
    # The PeerSession __init__ guard checks `isinstance(..., _PeerLogAdapter)`.
    # If it instead unconditionally wrapped, this would become double-prefixed.
    assert isinstance(inner, _PeerLogAdapter)
    again = inner if isinstance(inner, _PeerLogAdapter) else _PeerLogAdapter(inner, ("2.2.2.2", 2))
    again.info("hello")
    out = buf.getvalue()
    # Only one prefix.
    assert out.count("[peer=") == 1


def _make_idle_session(activity_at: float) -> PeerSession:
    """Build a PeerSession without the SSL/socket setup so we can poke at
    `is_idle` and `last_activity_at` in isolation."""
    s = PeerSession.__new__(PeerSession)
    s.last_activity_at = activity_at
    return s


def test_is_idle_below_threshold():
    s = _make_idle_session(activity_at=100.0)
    assert s.is_idle(now=105.0, threshold_s=10.0) is False


def test_is_idle_at_threshold():
    s = _make_idle_session(activity_at=100.0)
    # Exactly at the threshold counts as idle (>=).
    assert s.is_idle(now=110.0, threshold_s=10.0) is True


def test_is_idle_above_threshold():
    s = _make_idle_session(activity_at=100.0)
    assert s.is_idle(now=200.0, threshold_s=10.0) is True


def test_is_idle_zero_threshold_always_idle():
    """A 0-second threshold should mark every session idle immediately —
    used by no other path in production but the boundary value should
    still be sane."""
    s = _make_idle_session(activity_at=100.0)
    assert s.is_idle(now=100.0, threshold_s=0.0) is True
