"""Tests for the pure helpers in `tools/build_site.py` and
`tools/build_api_reference.py`.

These pin the small bits of logic that drive dashboard rendering
(category bucketing on the Findings tab, per-member enrichment on
Overview-tab family cards) and the API-reference generator (section
parsing, docstring-paragraph extraction).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.build_site import (  # noqa: E402
    categorize_doc,
    _enrich_families,
    load_findings,
    load_recent_wakes,
    CATEGORY_ORDER,
    FINDINGS_CATEGORY_ORDER,
)
from tools.build_api_reference import (  # noqa: E402
    parse_sections,
    first_paragraph,
)


# ---------------------------------------------------------------------------
#  categorize_doc — pins the Findings-tab grouping (wake 151)
# ---------------------------------------------------------------------------


def test_categorize_doc_retrospective_session():
    assert categorize_doc("session_retrospective_150.md") == "Retrospective"


def test_categorize_doc_retrospective_cross_link_arc():
    assert categorize_doc("cross_link_arc.md") == "Retrospective"


def test_categorize_doc_retrospective_morning_brief():
    # MORNING_BRIEF is in the explicit Retrospective allow-list (wake 153).
    assert categorize_doc("MORNING_BRIEF.md") == "Retrospective"


def test_categorize_doc_audit_codec_test():
    assert categorize_doc("codec_test_audit.md") == "Audit"


def test_categorize_doc_audit_ghidra_hunt_list():
    # The explicit allow-list catches a hunt-list as an Audit.
    assert categorize_doc("ghidra_hunt_list.md") == "Audit"


def test_categorize_doc_decompile_connection_lifecycle():
    assert categorize_doc("connection_lifecycle_decompiles.md") == "Decompile"


def test_categorize_doc_decompile_ghidra_findings():
    # ghidra_findings is the canonical decompile-overview doc.
    assert categorize_doc("ghidra_findings.md") == "Decompile"


def test_categorize_doc_overview_codec_library():
    assert categorize_doc("codec_library_overview.md") == "Overview"


def test_categorize_doc_overview_public_api():
    # Added wake 161 alongside the generated API reference doc.
    assert categorize_doc("public_api.md") == "Overview"


def test_categorize_doc_re_finding_fallback():
    assert categorize_doc("state_10_unblock_synthesis.md") == "RE Finding"


def test_categorize_doc_accepts_name_without_md_suffix():
    # The function should tolerate either form.
    assert categorize_doc("cross_link_arc") == "Retrospective"


def test_categorize_doc_returns_known_category_member():
    # Every output must be in the CATEGORY_ORDER list so the front-end
    # renders the right group header.
    for name in [
        "session_retrospective_150.md",
        "codec_test_audit.md",
        "connection_lifecycle_decompiles.md",
        "codec_library_overview.md",
        "state_10_unblock_synthesis.md",
        "random_unknown_doc.md",
    ]:
        assert categorize_doc(name) in CATEGORY_ORDER


# ---------------------------------------------------------------------------
#  _enrich_families — pins the Overview-tab drill-down join (wake 159)
# ---------------------------------------------------------------------------


def test_enrich_families_attaches_metadata_for_known_wire_type():
    families = [{"wire_types": ["0x15d"], "label": "test"}]
    captured = [{
        "type_id_hex": "0x015d",
        "name": "Heartbeat",
        "count": 12,
        "directions": "R",
        "codec": "heartbeat_15d.py",
    }]
    out = _enrich_families(families, captured)
    assert len(out) == 1
    members = out[0]["members"]
    assert len(members) == 1
    assert members[0]["hex"] == "0x15d"
    assert members[0]["name"] == "Heartbeat"
    assert members[0]["count"] == 12
    assert members[0]["directions"] == "R"
    assert members[0]["codec"] == "heartbeat_15d.py"


def test_enrich_families_unknown_wire_type_keeps_hex_with_zero_count():
    families = [{"wire_types": ["0xdead"]}]
    out = _enrich_families(families, captured_types=[])
    members = out[0]["members"]
    assert members == [
        {"hex": "0xdead", "name": "", "count": 0,
         "directions": "", "codec": ""}
    ]


def test_enrich_families_handles_empty_input():
    assert _enrich_families([], []) == []


def test_enrich_families_normalizes_hex_form_for_lookup():
    """A family hex like `0x15d` should match a captured_types entry
    keyed by `0x015d`. Both encode the same int."""
    families = [{"wire_types": ["0x15d"]}]
    captured = [{"type_id_hex": "0x015d", "name": "X", "count": 1,
                 "directions": "R", "codec": "x.py"}]
    out = _enrich_families(families, captured)
    assert out[0]["members"][0]["name"] == "X"


def test_enrich_families_skips_captured_entries_missing_type_id_hex():
    """Malformed captured_types entries (no type_id_hex) shouldn't
    crash the enricher — the enricher just skips them when building
    the lookup."""
    families = [{"wire_types": ["0x15d"]}]
    captured = [
        {"bogus": "no type id"},
        {"type_id_hex": "0x015d", "name": "Heartbeat", "count": 1,
         "directions": "R", "codec": "heartbeat_15d.py"},
    ]
    out = _enrich_families(families, captured)
    assert out[0]["members"][0]["name"] == "Heartbeat"


def test_enrich_families_preserves_original_fields():
    """The enricher should attach `members` without dropping existing
    keys (the front-end still uses `label`, `sub_system_id`, `note`)."""
    families = [{
        "wire_types": ["0x15d"],
        "label": "Heartbeat family",
        "sub_system_id": "abcdef0123456789",
        "note": "important context",
    }]
    out = _enrich_families(families, [])
    assert out[0]["label"] == "Heartbeat family"
    assert out[0]["sub_system_id"] == "abcdef0123456789"
    assert out[0]["note"] == "important context"


# ---------------------------------------------------------------------------
#  build_api_reference helpers (wake 161)
# ---------------------------------------------------------------------------


def test_first_paragraph_collapses_single_paragraph():
    text = "This is a\nmulti-line single\nparagraph."
    assert first_paragraph(text) == "This is a multi-line single paragraph."


def test_first_paragraph_returns_only_first():
    text = "First para.\n\nSecond para should be dropped."
    assert first_paragraph(text) == "First para."


def test_first_paragraph_handles_empty():
    assert first_paragraph("") == ""


def test_first_paragraph_handles_leading_whitespace():
    assert first_paragraph("\n\n  Lead spaces.  \n\nNope.") == "Lead spaces."


def test_parse_sections_returns_expected_headings():
    """`parse_sections()` reads `server/javelin/__init__.py` and
    recovers the section headings from the `# ...` comment markers
    above each `__all__` group. The exact set may evolve, but the
    function should return at least the well-known headings."""
    sections = parse_sections()
    headings = [h for h, _ in sections]
    # Spot-check a few headings that have shipped for many wakes.
    for expected in (
        "Low-level wire framing",
        "Generic / family codecs",
        "R-direction codecs",
        "W-direction codecs",
    ):
        assert expected in headings, (
            f"missing expected heading {expected!r}; got {headings}"
        )


def test_parse_sections_populates_member_names():
    """Each section returned by `parse_sections` should have at least
    one member name extracted from a `"Foo"` line."""
    sections = parse_sections()
    for heading, names in sections:
        assert names, f"section {heading!r} has no member names"
        # Names must be valid Python identifier-ish strings (no quotes
        # carried in).
        for n in names:
            assert '"' not in n, f"member name {n!r} carries quote in {heading!r}"


def test_parse_sections_covers_every_shipped_export():
    """Stricter invariant (wake 166): every name in
    `server.javelin.__all__` must surface in some section parsed
    out of `__init__.py`. Catches a regression where a `# heading`
    comment marker gets accidentally removed (the entries below it
    would be silently dropped from the parsed output, and the
    generated public_api.md would lose a whole section)."""
    import server.javelin as javelin
    sections = parse_sections()
    parsed_names = {n for _, names in sections for n in names}
    for export in javelin.__all__:
        assert export in parsed_names, (
            f"export {export!r} is in __all__ but missing from "
            f"parse_sections() output — section marker likely dropped"
        )


# ---------------------------------------------------------------------------
#  load_findings + FINDINGS_CATEGORY_ORDER (wake 163)
# ---------------------------------------------------------------------------


def test_every_finding_has_a_known_category():
    """Each curated finding must be tagged with a category that's in
    FINDINGS_CATEGORY_ORDER so the front-end groups it correctly. A
    typo or accidentally-dropped tag would silently dump the card
    under a fallback bucket on the dashboard."""
    for f in load_findings():
        assert "category" in f, f"finding {f['title']!r} has no category"
        assert f["category"] in FINDINGS_CATEGORY_ORDER, (
            f"finding {f['title']!r} has unknown category {f['category']!r}"
        )


def test_load_recent_wakes_returns_newest_first():
    """The Recent-activity strip on the Overview tab depends on
    `load_recent_wakes()` returning the latest worklog entries with
    wake number descending. Pin that contract."""
    entries = load_recent_wakes(limit=6)
    assert len(entries) <= 6
    assert len(entries) > 0, "worklog should have at least one wake entry"
    wakes = [e["wake"] for e in entries]
    assert wakes == sorted(wakes, reverse=True), (
        f"recent wakes must be newest-first; got {wakes}"
    )
    for e in entries:
        assert "wake" in e and isinstance(e["wake"], int)
        assert "title" in e and e["title"], (
            f"wake {e.get('wake')} has empty title"
        )


def test_load_recent_wakes_respects_limit():
    assert len(load_recent_wakes(limit=1)) == 1
    assert len(load_recent_wakes(limit=3)) == 3


def test_every_finding_has_required_render_fields():
    """The front-end renders `title`, `wake`, `summary` for each card.
    Pin the shape so a refactor can't drop one silently."""
    for f in load_findings():
        for key in ("title", "wake", "summary"):
            assert key in f, f"finding {f.get('title', '?')!r} missing {key!r}"
        assert isinstance(f["wake"], int), (
            f"finding {f['title']!r} wake must be int; got {type(f['wake'])}"
        )
        assert f["summary"], f"finding {f['title']!r} has empty summary"
