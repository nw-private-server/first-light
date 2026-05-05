"""
Validates that every community capture in info/ parses without errors.

Automatically discovers all messages-redacted.txt files so any new capture
submitted via PR is tested without any manual test-registration step.

Run with:
    pytest server/test_captures.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from server.javelin.replay_store import ReplayStore

_INFO_DIR = Path(__file__).parents[1] / "info"
_DUMPS = sorted(_INFO_DIR.glob("*/messages-redacted.txt"))


@pytest.mark.skipif(not _DUMPS, reason="no captures found in info/")
@pytest.mark.parametrize("dump_path", _DUMPS, ids=lambda p: p.parent.name)
def test_capture_parses(dump_path: Path) -> None:
    store = ReplayStore(dump_path)
    assert len(store.messages) > 0, f"{dump_path}: parsed 0 messages"
    # Validation warnings are non-fatal: captures may have partial redaction
    # that corrupts the R-direction type-marker bytes. Surface them in output
    # so contributors can investigate, but don't fail the suite.
    for w in store.validation_warnings:
        print(f"\n  [capture warning] {dump_path.parent.name}: {w}")
