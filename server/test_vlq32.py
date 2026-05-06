"""Unit tests for `_encode_vlq32` in `server.rep_responder`.

Verifies the canonical-shortest-form encoding at boundary values that
matter for the replay path: small bodies (V3 response = 88 B) up through
the seq 0x25 StateBundle (~46 KB) which now needs 3-byte encoding.
"""

from __future__ import annotations

import pytest

from server.rep_responder import _encode_vlq32


def _decode_vlq32(buf: bytes) -> tuple[int, int]:
    """Inverse of _encode_vlq32; returns (value, bytes_consumed)."""
    value = 0
    shift = 0
    for i, b in enumerate(buf):
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, i + 1
        shift += 7
    raise ValueError("VLQ32 buffer truncated")


def test_zero():
    assert _encode_vlq32(0) == b"\x00"


def test_one_byte_max():
    assert _encode_vlq32(0x7F) == b"\x7f"
    assert len(_encode_vlq32(127)) == 1


def test_two_byte_min():
    assert _encode_vlq32(0x80) == b"\x80\x01"
    assert len(_encode_vlq32(128)) == 2


def test_v3_response_size_is_one_byte():
    # The V3 RegistrationResponse body is 88 B.
    assert _encode_vlq32(88) == b"\x58"


def test_two_byte_max():
    assert _encode_vlq32(0x3FFF) == b"\xff\x7f"
    assert len(_encode_vlq32(16383)) == 2


def test_three_byte_min():
    assert _encode_vlq32(0x4000) == b"\x80\x80\x01"
    assert len(_encode_vlq32(16384)) == 3


def test_seq_0x25_size_is_three_bytes():
    # StateBundle seq 0x25 is ~46 KB — exceeds the old 2-byte ceiling.
    size = 46423
    enc = _encode_vlq32(size)
    assert len(enc) == 3
    assert _decode_vlq32(enc) == (size, 3)


def test_three_byte_max():
    assert _encode_vlq32(0x1FFFFF) == b"\xff\xff\x7f"
    assert len(_encode_vlq32(0x1FFFFF)) == 3


def test_seq_0x29_size_is_three_bytes():
    # 99 KB (the largest replay message) still fits in 3 bytes.
    size = 99819
    enc = _encode_vlq32(size)
    assert len(enc) == 3
    assert _decode_vlq32(enc) == (size, 3)


def test_four_byte_boundary():
    assert _encode_vlq32(0x200000) == b"\x80\x80\x80\x01"
    assert len(_encode_vlq32(0x200000)) == 4
    assert len(_encode_vlq32(0xFFFFFFF)) == 4


def test_max_u32():
    # 2**32 - 1 takes 5 bytes.
    enc = _encode_vlq32(0xFFFFFFFF)
    assert len(enc) == 5
    assert _decode_vlq32(enc) == (0xFFFFFFFF, 5)


def test_roundtrip_random_sample():
    import random
    rng = random.Random(0xCAFEBABE)
    for _ in range(200):
        v = rng.randint(0, 0xFFFFFFFF)
        enc = _encode_vlq32(v)
        decoded, consumed = _decode_vlq32(enc)
        assert decoded == v
        assert consumed == len(enc)


def test_negative_rejected():
    with pytest.raises(ValueError):
        _encode_vlq32(-1)


def test_oversize_rejected():
    with pytest.raises(ValueError):
        _encode_vlq32(0x1_0000_0000)
