"""Unit tests for `chunk_replay_payload` in `server.javelin.wire`.

Verifies the MF_CHUNKS countdown convention, length-preservation across
chunks, and boundary cases that matter for the captured replay (e.g.
the ~99 KB seq 0x29 message split into ~91 chunks at 1100 B each).
"""

from __future__ import annotations

import pytest

from server.javelin.wire import chunk_replay_payload as _chunk_replay_payload


def test_empty_body():
    chunks = _chunk_replay_payload(b"", chunk_size=1100)
    assert chunks == [(1, b"")]


def test_single_chunk_smaller_than_chunk_size():
    body = b"hello"
    chunks = _chunk_replay_payload(body, chunk_size=100)
    assert chunks == [(1, b"hello")]


def test_single_chunk_exact_size():
    body = b"x" * 1100
    chunks = _chunk_replay_payload(body, chunk_size=1100)
    assert len(chunks) == 1
    assert chunks[0] == (1, body)


def test_two_chunks_exact_split():
    body = b"x" * 2200
    chunks = _chunk_replay_payload(body, chunk_size=1100)
    assert len(chunks) == 2
    assert chunks[0] == (2, b"x" * 1100)
    assert chunks[1] == (1, b"x" * 1100)


def test_two_chunks_with_short_tail():
    body = b"x" * 1500
    chunks = _chunk_replay_payload(body, chunk_size=1100)
    assert len(chunks) == 2
    assert chunks[0] == (2, b"x" * 1100)
    assert chunks[1] == (1, b"x" * 400)


def test_countdown_decrements_correctly():
    body = b"x" * 5000
    chunks = _chunk_replay_payload(body, chunk_size=1100)
    counts = [c[0] for c in chunks]
    assert counts == [5, 4, 3, 2, 1]


def test_concatenation_reconstructs_body():
    body = bytes(range(256)) * 400  # 102 400 B distinctive payload
    chunks = _chunk_replay_payload(body, chunk_size=1100)
    reassembled = b"".join(slice for _, slice in chunks)
    assert reassembled == body


def test_seq_0x29_size_chunks_to_91():
    # The real seq 0x29 (init StateBundle) is 99 819 B.
    # 99 819 / 1100 = 90.74 -> 91 chunks
    body = b"\x00" * 99819
    chunks = _chunk_replay_payload(body, chunk_size=1100)
    assert len(chunks) == 91
    assert chunks[0][0] == 91
    assert chunks[-1][0] == 1
    assert chunks[-1][1] == b"\x00" * (99819 - 1100 * 90)


def test_chunk_size_larger_than_body():
    body = b"abc"
    chunks = _chunk_replay_payload(body, chunk_size=10000)
    assert chunks == [(1, b"abc")]


def test_chunk_size_one():
    body = b"abc"
    chunks = _chunk_replay_payload(body, chunk_size=1)
    assert len(chunks) == 3
    assert chunks == [(3, b"a"), (2, b"b"), (1, b"c")]


def test_chunk_size_zero_rejected():
    with pytest.raises(ValueError):
        _chunk_replay_payload(b"abc", chunk_size=0)


def test_negative_chunk_size_rejected():
    with pytest.raises(ValueError):
        _chunk_replay_payload(b"abc", chunk_size=-1)
