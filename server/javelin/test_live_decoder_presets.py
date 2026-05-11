"""Cross-check: every live-decoder preset hex on the dashboard
must round-trip through the matching Python codec.

Wake-152/154/171 added six preset buttons to `site/index.html`'s
"Live decoder" panel. Each button carries `data-ldtype` (the type
key the JS uses to pick a decoder) and `data-ldhex` (the hex string
that populates the textarea). The JS DECODERS port the Python
codecs byte-for-byte — which means if a preset's hex decodes
through Python, it'll decode through JS too. This test pins the
"presets decode" invariant at the Python side so a future preset
addition with a typo is caught immediately.
"""

from __future__ import annotations

import re
from pathlib import Path

from server.javelin import (
    heartbeat_15d,
    session_clock_beacon,
    empty_marker_651,
    init_message_18a6,
    session_identity_beacon,
    subkey_beacon,
    result_token_1097,
    result_token_136a,
    frame_config_1096,
    self_ident,
    identity_blob_8e6,
    handshake_blob_76,
    receipt_handshake_9fc,
)


REPO = Path(__file__).resolve().parents[2]
INDEX_HTML = REPO / "site" / "index.html"


def _decode_self_ident(buf: bytes):
    """Accept either the 4-byte trigger or the 25+-byte structured form.

    The JS decoder handles both forms; mirror that for the cross-check
    test. Trigger form is just the TYPE_HEADER with no body — confirm
    the header bytes match, return a sentinel."""
    if len(buf) == 4:
        if buf != self_ident.TYPE_HEADER:
            raise ValueError(
                f"trigger form must equal TYPE_HEADER {self_ident.TYPE_HEADER.hex()}; "
                f"got {buf.hex()}"
            )
        return "trigger"
    return self_ident.decode_typed(buf)


# `data-ldtype` → callable that takes raw bytes and returns the
# decoded dataclass. Mirrors `DECODERS` in `site/index.html`.
PYTHON_DECODERS = {
    "15d_R": heartbeat_15d.decode_ping,
    "15d_W": heartbeat_15d.decode_ack,
    "14f":   session_clock_beacon.decode,
    "651":   empty_marker_651.decode,
    "18a6":  init_message_18a6.decode,
    "1b88":  session_identity_beacon.decode,
    "subkey": subkey_beacon.decode,
    "1097":  result_token_1097.decode,
    "136a":  result_token_136a.decode,
    "1096":  frame_config_1096.decode,
    "5d1":   _decode_self_ident,
    "8e6":   identity_blob_8e6.decode,
    "76":    handshake_blob_76.decode,
    "9fc":   receipt_handshake_9fc.decode,
}


PRESET_RE = re.compile(
    r'data-ldtype="([^"]+)"\s+data-ldhex="([^"]+)"',
)


def _load_presets() -> list[tuple[str, bytes]]:
    """Return [(ldtype, raw_bytes), ...] for every preset button in
    `site/index.html`'s Live-decoder panel."""
    text = INDEX_HTML.read_text()
    out = []
    for m in PRESET_RE.finditer(text):
        ldtype = m.group(1)
        cleaned = m.group(2).replace(" ", "").replace("\n", "")
        raw = bytes.fromhex(cleaned)
        out.append((ldtype, raw))
    return out


def test_index_html_has_at_least_six_presets():
    """Sanity: the wake-152/154/171 work shipped 6 presets. If a
    future edit accidentally drops one, this catches it."""
    presets = _load_presets()
    assert len(presets) >= 6, (
        f"expected at least 6 live-decoder presets; found {len(presets)}"
    )


def test_every_preset_has_a_matching_python_decoder():
    """Every preset's `data-ldtype` must map to a Python decoder in
    `PYTHON_DECODERS`. A new live-decoder type that doesn't update
    the test mapping triggers this — the test then drives the
    contributor to extend the JS DECODERS table and the Python-side
    mapping at the same time."""
    for ldtype, _ in _load_presets():
        assert ldtype in PYTHON_DECODERS, (
            f"preset type {ldtype!r} has no Python decoder mapping in test"
        )


def test_every_preset_hex_round_trips_through_python_codec():
    """The actual cross-check: each preset's hex decodes through the
    matching Python codec without raising. This catches the most
    likely future regression — a typo in a hand-written hex
    string that the JS DECODERS would also reject but only at
    runtime when a visitor clicks the preset."""
    for ldtype, raw in _load_presets():
        decoder = PYTHON_DECODERS[ldtype]
        try:
            decoded = decoder(raw)
        except Exception as e:  # noqa: BLE001
            raise AssertionError(
                f"preset {ldtype!r} hex ({raw.hex()}) failed to decode "
                f"through Python codec: {type(e).__name__}: {e}"
            ) from e
        assert decoded is not None, (
            f"preset {ldtype!r} decoded to None"
        )
