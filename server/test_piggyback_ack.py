"""Tests for the Carrier-level piggyback SM_CT_ACKS record builder.

Exercises both the pure helper (`build_sm_ct_acks_record`) and the
PeerSession-level cursor advancement (`_emit_piggyback_ack`). The pure
helper validates byte-for-byte against the Mixed Nuts working bundle
shape; the integration test confirms the cursor advances and only fresh
inbound seqs trigger a fresh ACK.
"""
from __future__ import annotations

import struct

import pytest

from server.rep_responder import build_sm_ct_acks_record


def test_returns_none_when_no_inbound_seen():
    assert build_sm_ct_acks_record(seq=0, last_inbound_seq=None,
                                   acked_through_seq=None) is None


def test_returns_none_when_already_acked_through_latest():
    assert build_sm_ct_acks_record(seq=0, last_inbound_seq=10,
                                   acked_through_seq=10) is None
    assert build_sm_ct_acks_record(seq=0, last_inbound_seq=5,
                                   acked_through_seq=10) is None


def test_first_ack_uses_last_inbound_as_first_to_ack():
    # No prior cursor → both endpoints of the ACK range are last_inbound.
    rec = build_sm_ct_acks_record(seq=0x42, last_inbound_seq=0x1234,
                                  acked_through_seq=None)
    assert rec is not None
    # Layout: 20 [size:u16] 03 [seq:u16] [rel:u16] 40 [last:u16] [first:u16] 06
    assert rec[0] == 0x20                               # MF_DATA_CHANNEL only
    assert struct.unpack(">H", rec[1:3])[0] == 6        # inline size
    assert rec[3] == 0x03                               # channel 3
    assert struct.unpack(">H", rec[4:6])[0] == 0x42     # record seq
    assert struct.unpack(">H", rec[6:8])[0] == 0        # rel_seq always 0
    assert rec[8] == 0x40                               # AHF_CONTINUOUS_ACK
    assert struct.unpack(">H", rec[9:11])[0] == 0x1234  # lastToAck
    assert struct.unpack(">H", rec[11:13])[0] == 0x1234 # firstToAck = last
    assert rec[13] == 0x06                              # SM_CT_ACKS msgid


def test_subsequent_ack_advances_first_to_ack():
    rec = build_sm_ct_acks_record(seq=7, last_inbound_seq=20,
                                  acked_through_seq=10)
    assert rec is not None
    # firstToAck = acked_through + 1 = 11; lastToAck = 20
    assert struct.unpack(">H", rec[9:11])[0] == 20
    assert struct.unpack(">H", rec[11:13])[0] == 11


def test_record_seq_wraps_at_u16():
    rec = build_sm_ct_acks_record(seq=0x1FFFF, last_inbound_seq=1,
                                  acked_through_seq=None)
    assert rec is not None
    assert struct.unpack(">H", rec[4:6])[0] == 0xFFFF


def test_last_inbound_wraps_at_u16():
    rec = build_sm_ct_acks_record(seq=0, last_inbound_seq=0x10000,
                                  acked_through_seq=None)
    assert rec is not None
    assert struct.unpack(">H", rec[9:11])[0] == 0


def test_record_size_is_constant_14_bytes():
    rec = build_sm_ct_acks_record(seq=1, last_inbound_seq=99,
                                  acked_through_seq=0)
    assert rec is not None
    # 1 flag + 2 size + 1 ch + 2 seq + 2 rel_seq + 6 inline = 14
    assert len(rec) == 14


def test_acked_through_zero_treated_as_real_cursor_not_none():
    # Edge case: cursor was advanced to seq 0 (rare but valid). Ensure the
    # check distinguishes None from 0; firstToAck should be 1, not 5.
    rec = build_sm_ct_acks_record(seq=0, last_inbound_seq=5,
                                  acked_through_seq=0)
    assert rec is not None
    assert struct.unpack(">H", rec[11:13])[0] == 1


def _make_session():
    """Construct a minimal PeerSession-like object that exercises only the
    cursor + ACK emission path. We avoid the real __init__ (which builds
    a DTLS context) by short-circuiting via type.__call__."""
    from server.rep_responder import PeerSession
    s = PeerSession.__new__(PeerSession)
    s.v3_piggyback_ack = True
    s.last_inbound_env_seq = None
    s._acked_through_seq = None
    s.out_msg_seq = [0, 0, 0, 0]
    return s


def test_emit_returns_empty_when_no_inbound():
    s = _make_session()
    rec, log = s._emit_piggyback_ack()
    assert rec == b""
    assert log == ""
    assert s.out_msg_seq[3] == 0  # no seq consumed


def test_emit_advances_cursor_and_seq():
    s = _make_session()
    s.last_inbound_env_seq = 100
    rec, log = s._emit_piggyback_ack()
    assert rec != b""
    assert "ack_range=(100..100)" in log
    assert s._acked_through_seq == 100
    assert s.out_msg_seq[3] == 1


def test_emit_skips_when_no_new_inbound_since_last_ack():
    s = _make_session()
    s.last_inbound_env_seq = 100
    s._emit_piggyback_ack()
    # Same inbound seq — second emit should be a no-op (no duplicate ACK,
    # no seq consumption).
    rec2, log2 = s._emit_piggyback_ack()
    assert rec2 == b""
    assert log2 == ""
    assert s.out_msg_seq[3] == 1


def test_emit_emits_again_when_new_inbound_arrives():
    s = _make_session()
    s.last_inbound_env_seq = 100
    s._emit_piggyback_ack()
    # New inbound datagram arrived → fresh ACK covering 101..150.
    s.last_inbound_env_seq = 150
    rec, log = s._emit_piggyback_ack()
    assert rec != b""
    assert "ack_range=(101..150)" in log
    assert s._acked_through_seq == 150
    assert s.out_msg_seq[3] == 2


def test_emit_disabled_returns_empty_even_with_inbound():
    s = _make_session()
    s.v3_piggyback_ack = False
    s.last_inbound_env_seq = 100
    rec, log = s._emit_piggyback_ack()
    assert rec == b""
    assert log == ""
    assert s._acked_through_seq is None
