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
    categorize_wake_title,
    _enrich_families,
    load_findings,
    load_live_decoder_history,
    load_recent_wakes,
    load_live_decoder_coverage,
    _coverage_badge_color,
    CATEGORY_ORDER,
    CROSS_CHECK_MANIFEST,
    FINDINGS_CATEGORY_ORDER,
    LDTYPE_TO_TYPE_IDS,
    WAKE_CATEGORY_ORDER,
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


def test_load_recent_wakes_includes_stable_line_numbers():
    """Wake 170 added a `line` field so the front-end can deep-link
    each entry to `?plain=1#L<line>`. Pin: every entry has a
    positive int line number, and line numbers are monotonically
    decreasing across the newest-first list (newer wakes appear later
    in the file so their line number is higher)."""
    entries = load_recent_wakes(limit=6)
    lines = [e.get("line") for e in entries]
    for e in entries:
        ln = e.get("line")
        assert isinstance(ln, int) and ln > 0, (
            f"wake {e.get('wake')} line must be positive int; got {ln}"
        )
    assert lines == sorted(lines, reverse=True), (
        f"line numbers should decrease in newest-first order; got {lines}"
    )


def test_load_recent_wakes_respects_limit():
    assert len(load_recent_wakes(limit=1)) == 1
    assert len(load_recent_wakes(limit=3)) == 3


def test_live_decoder_coverage_shape_and_growth():
    """Wake 175 added the live-decoder coverage indicator. Pin
    invariants: covered ≤ total, percent in [0,100], uncovered is a
    list of hex strings, covered + len(uncovered) == total."""
    captured = [
        {"type_id_hex": "0x0003"},
        {"type_id_hex": "0x015d"},
        {"type_id_hex": "0x014f"},
        {"type_id_hex": "0x0651"},
        {"type_id_hex": "0x1a59"},  # in subkey family
    ]
    cov = load_live_decoder_coverage(captured)
    assert cov["total"] == 5
    assert 0 <= cov["covered"] <= cov["total"]
    assert 0.0 <= cov["percent"] <= 100.0
    assert isinstance(cov["uncovered"], list)
    assert cov["covered"] + len(cov["uncovered"]) == cov["total"]
    # 0x015d/0x014f/0x0651/0x1a59 should resolve as covered; 0x0003 not.
    assert "0x0003" in cov["uncovered"]
    assert "0x015d" not in cov["uncovered"]
    assert "0x014f" not in cov["uncovered"]
    assert "0x1a59" not in cov["uncovered"]


def test_findings_linkify_map_matches_build_site_coverage_map():
    """The JS-side `TYPE_ID_TO_LDTYPE` in `site/index.html` (wake 177,
    used to linkify wire-type mentions in Findings cards) and the
    Python-side `LDTYPE_TO_TYPE_IDS` in `tools/build_site.py` (wake
    178 promoted it to a module-level constant) encode the *same*
    relationship from opposite directions. If they drift — e.g. a
    new decoder is added to one map but not the other — the Findings
    linkify would point at the wrong decoder or fail to surface a
    link the coverage indicator counts as covered.

    Pin both directions:
      - Every (type_id → ldtype) entry in the JS map must have
        `type_id` in the Python map's value-set for that ldtype.
      - Every type_id in the Python map's union of values must
        have an entry in the JS map.
    """
    import re as _re
    repo = Path(__file__).resolve().parents[2]
    index_html = (repo / "site" / "index.html").read_text()

    # Parse the JS map block. Pattern: "0xNN": "ldtype",
    m = _re.search(
        r"const TYPE_ID_TO_LDTYPE\s*=\s*\{(.*?)\};",
        index_html,
        _re.DOTALL,
    )
    assert m, "couldn't locate TYPE_ID_TO_LDTYPE in site/index.html"
    js_map: dict[int, str] = {}
    for pair in _re.finditer(
        r'"0x([0-9a-fA-F]+)"\s*:\s*"([^"]+)"', m.group(1)
    ):
        js_map[int(pair.group(1), 16)] = pair.group(2)
    assert js_map, "TYPE_ID_TO_LDTYPE parsed empty"

    # Direction 1: every JS entry must have the type_id in the Python
    # map's value-set for that ldtype.
    for type_id, ldtype in js_map.items():
        assert ldtype in LDTYPE_TO_TYPE_IDS, (
            f"JS map references unknown ldtype {ldtype!r} for "
            f"type_id 0x{type_id:x}"
        )
        assert type_id in LDTYPE_TO_TYPE_IDS[ldtype], (
            f"JS map says 0x{type_id:x} → {ldtype!r}, but Python "
            f"map's {ldtype!r} set is {LDTYPE_TO_TYPE_IDS[ldtype]} "
            f"(missing 0x{type_id:x})"
        )

    # Direction 2: every type_id in the Python map's union must have
    # a JS entry. We tolerate ldtypes that don't appear in the JS map
    # (e.g. 15d_W's 0x15d is already covered by 15d_R's entry).
    py_union: set[int] = set()
    for ids in LDTYPE_TO_TYPE_IDS.values():
        py_union |= ids
    for type_id in py_union:
        assert type_id in js_map, (
            f"type_id 0x{type_id:x} in Python LDTYPE_TO_TYPE_IDS has no "
            f"entry in JS TYPE_ID_TO_LDTYPE — the Findings linkify will "
            f"silently skip this type"
        )


def test_coverage_badge_color_thresholds():
    """Wake 201 invariant. The wake-195 live-decoder shields badge
    uses 4 color steps tied to fixed percentage thresholds: ≥80%
    brightgreen, ≥60% blue, ≥40% yellow, else orange. A future tweak
    to the function body (e.g. a typo in the threshold or a
    different palette) would silently change the visual progression
    on the README badge. Pin the 4 thresholds explicitly so any
    such tweak fails here.

    Walks the percentage range with values that bracket each
    threshold from both sides — 0/39/40/41/59/60/61/79/80/81/100 —
    and asserts each falls in the expected bucket.
    """
    # Below the 40% threshold → orange.
    for pct in (0, 1, 25, 39, 39.99):
        assert _coverage_badge_color(pct) == "orange", f"{pct}% should be orange"
    # 40-59% → yellow.
    for pct in (40, 40.5, 50, 59, 59.99):
        assert _coverage_badge_color(pct) == "yellow", f"{pct}% should be yellow"
    # 60-79% → blue.
    for pct in (60, 65, 70, 79, 79.99):
        assert _coverage_badge_color(pct) == "blue", f"{pct}% should be blue"
    # 80% and above → brightgreen.
    for pct in (80, 85, 90, 99, 100):
        assert _coverage_badge_color(pct) == "brightgreen", f"{pct}% should be brightgreen"


def test_public_api_md_matches_render_output():
    """Wake 202 invariant. The wake-161 generator
    `tools/build_api_reference.py` produces `analysis/public_api.md`
    from the current source code. The doc must always match the
    `render()` output for the current code state — otherwise visitors
    landing on the API ref see stale class summaries or missing
    entries.

    Catches: a contributor adds an export to `__init__.py` or
    patches a class docstring, runs the test suite, but forgets to
    re-run `tools/build_api_reference.py`. The committed
    `public_api.md` would drift from the live code; the test fails
    with a precise pointer to re-run the generator.

    Idempotency is implicit: if `render()` output ever changes
    spontaneously between two calls (e.g. due to dict-ordering or
    timestamp), this test fails. The wake-161 generator is
    deterministic by design (sorted iteration, no timestamps).
    """
    from tools.build_api_reference import render
    repo = Path(__file__).resolve().parents[2]
    expected = render()
    actual = (repo / "analysis" / "public_api.md").read_text()
    assert actual == expected, (
        "analysis/public_api.md is stale. Re-run "
        "`tools/build_api_reference.py` to regenerate. "
        f"(rendered output is {len(expected)} bytes; current file is "
        f"{len(actual)} bytes)"
    )


def test_render_is_idempotent():
    """Wake 202 invariant. Two consecutive calls to `render()` must
    produce byte-identical output. Catches the regression: a future
    tweak to `build_api_reference.py` introduces dict-ordering noise
    or timestamp drift, which would make the generated doc churn
    in git on every rebuild.
    """
    from tools.build_api_reference import render
    out1 = render()
    out2 = render()
    assert out1 == out2, (
        f"render() is non-deterministic: outputs differ "
        f"({len(out1)} vs {len(out2)} bytes). Check for dict-iteration "
        f"or timestamp-based content."
    )


def test_current_coverage_badge_matches_data_json():
    """Wake 201: the live badge JSON (`site/badge-live-decoder.json`)
    must agree with the color the function picks for the *current*
    coverage percentage in `site/data.json`. Catches a forgotten
    rebuild (build_site not re-run after a coverage change) or a
    map drift that left the badge stale."""
    import json as _json
    repo = Path(__file__).resolve().parents[2]
    data = _json.loads((repo / "site" / "data.json").read_text())
    cov = data.get("live_decoder_coverage", {})
    cov_total = cov.get("total", 0)
    cov_covered = cov.get("covered", 0)
    cov_pct = (cov_covered / cov_total * 100.0) if cov_total else 0.0
    expected_color = _coverage_badge_color(cov_pct)
    badge = _json.loads((repo / "site" / "badge-live-decoder.json").read_text())
    assert badge.get("color") == expected_color, (
        f"badge-live-decoder.json color is {badge.get('color')!r} but "
        f"current coverage {cov_pct:.1f}% should produce {expected_color!r}. "
        f"Did you forget to run `tools/build_site.py` after a coverage "
        f"change?"
    )


def test_every_shadow_or_validate_helper_has_a_lockdown_test():
    """Wake 196 meta-invariant. The wake-157/158 + wake-187/188 arcs
    established a pattern: every helper named `_shadow_*` or
    `_validate_*` in `server/rep_responder.py` is a logging-only
    proof-of-safety step for some future dispatcher promotion, and
    each must have a lockdown test file (≥6 tests) before the
    promotion can proceed. Catch the regression: a contributor adds a
    new `_shadow_*` or `_validate_*` helper without a corresponding
    `test_<name>.py` file with ≥6 tests.

    The test scans `server/rep_responder.py` for `def _shadow_*` or
    `def _validate_*` definitions and confirms each one is referenced
    by ≥6 tests across `server/javelin/test_*.py` files.
    """
    import re as _re
    repo = Path(__file__).resolve().parents[2]
    src = (repo / "server" / "rep_responder.py").read_text()

    helpers = _re.findall(
        r"^\s+def (_(?:shadow|validate)_[A-Za-z0-9_]+)\(",
        src, _re.MULTILINE,
    )
    assert helpers, "no _shadow_*/ _validate_* helpers found — has the wake-157 pattern been removed?"

    # For each helper, find at least one test_*.py file that mentions
    # the helper name AND has ≥6 `def test_*` functions. The 6-test bar
    # mirrors wake-158 (9 shadow-decode tests) and wake-188 (8 heartbeat-
    # encode-validate tests).
    test_dir = repo / "server" / "javelin"
    test_files = list(test_dir.glob("test_*.py"))

    for helper in helpers:
        best_count = 0
        best_file = None
        for tf in test_files:
            text = tf.read_text()
            if helper not in text:
                continue
            count = len(_re.findall(r"^def test_\w+\(", text, _re.MULTILINE))
            if count > best_count:
                best_count = count
                best_file = tf.name
        assert best_count >= 6, (
            f"helper {helper!r} has no test_*.py file with ≥6 tests "
            f"that mentions it. Best match: {best_file!r} with {best_count} "
            f"tests. The wake-157/158 + wake-187/188 pattern requires a "
            f"lockdown file before any future emission/consumption "
            f"promotion. Add tests to a test_<helper-name-suffix>.py file."
        )


def test_howitworks_type_id_mentions_all_linkify():
    """Wake 184 added a DOM walker that linkifies `0xNNN` mentions in
    the static "How it works" walkthrough HTML. Pin the invariant:
    every type-id mentioned in the walkthrough's prose must be in
    `LDTYPE_TO_TYPE_IDS` (the source-of-truth Python map), so the
    DOM walker actually surfaces a clickable link rather than passing
    through as plain text.

    Catches the scenario: a future contributor adds a new wire-type
    walkthrough or mentions a type-id in the "How it works" prose
    but forgets to add the matching live-decoder entry."""
    import re as _re
    repo = Path(__file__).resolve().parents[2]
    html = (repo / "site" / "index.html").read_text()

    # Slice out the howitworks tab's section. Section tags don't nest
    # in our markup, so a non-greedy match is sufficient.
    m = _re.search(
        r'<section class="tab" data-tab="howitworks">(.*?)</section>',
        html, _re.DOTALL,
    )
    assert m, "couldn't locate howitworks section"
    walkthrough = m.group(1)

    # Find every 0xNNN mention. 1-2 hex-char mentions (e.g. `0x80`,
    # `0xa6`) typically refer to individual byte values in wire-format
    # explanations, not type-ids — restrict the invariant to 3+ hex
    # chars which is the common type-id shape. Edge case: 0xa4 is a
    # 2-char type-id we DO support; the wake-183 DOM linkifier would
    # surface it as a link if mentioned (the JS regex matches 2-char
    # hex), but the test stays conservative on the static-walkthrough
    # side.
    mentions = set()
    for w in _re.finditer(r"\b0x([0-9a-fA-F]{3,4})\b", walkthrough):
        mentions.add(int(w.group(1), 16))

    assert mentions, "walkthrough should mention at least one type-id"

    covered = set()
    for tids in LDTYPE_TO_TYPE_IDS.values():
        covered |= tids

    uncovered = sorted(mentions - covered)
    assert not uncovered, (
        f"How-it-works mentions type-ids that aren't in LDTYPE_TO_TYPE_IDS, "
        f"so the wake-184 DOM linkifier will leave them plain text: "
        f"{[hex(t) for t in uncovered]}. Add the type-id to "
        f"LDTYPE_TO_TYPE_IDS (and TYPE_ID_TO_LDTYPE) or stop mentioning it."
    )


def test_live_decoder_coverage_against_real_data():
    """Smoke test: the actual computed coverage against the captured
    set is non-trivial. Avoids hard-coding an exact number (which
    would force test updates whenever the coverage grows), but
    asserts at least half is covered as of wake 175."""
    # Read the captured types from data.json (already built).
    import json
    repo = Path(__file__).resolve().parents[2]
    with (repo / "site" / "data.json").open() as f:
        data = json.load(f)
    cov = load_live_decoder_coverage(data["captured_types"])
    assert cov["total"] == 40, f"expected 40 captured types; got {cov['total']}"
    assert cov["covered"] >= 20, (
        f"expected at least 20 covered as of wake 175; got {cov['covered']}"
    )


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


# ---------------------------------------------------------------------------
#  10th cross-check (wake 207) — every retrospective doc has a README link
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
#  categorize_wake_title — recent-activity strip pill (wake 210)
# ---------------------------------------------------------------------------


def test_categorize_wake_title_test_keywords():
    assert categorize_wake_title("10th cross-check: every retrospective doc must have a README link") == "test"
    assert categorize_wake_title("badge-color invariant (2 new tests)") == "test"
    assert categorize_wake_title("9-test lockdown of inbound shadow") == "test"


def test_categorize_wake_title_site_keywords():
    assert categorize_wake_title("Findings card for the phase-2D swap") == "site"
    assert categorize_wake_title("live decoder +0xca4 AssetCountTable → 34/40") == "site"
    assert categorize_wake_title("dashboard badge refresh") == "site"


def test_categorize_wake_title_code_keywords():
    assert categorize_wake_title("phase-2D: actual heartbeat emission swap") == "code"
    assert categorize_wake_title("counter-advance enhancement (phase-2D follow-up)") == "code"


def test_categorize_wake_title_docs_keywords():
    assert categorize_wake_title("update wake-197 retrospective with wake-204 swap") == "docs"
    assert categorize_wake_title("README refresh: add wake-197 retrospective link") == "docs"


def test_categorize_wake_title_unknown_returns_other():
    assert categorize_wake_title("free-form exploratory wake on something nobody saw coming") == "other"
    assert categorize_wake_title("") == "other"


def test_categorize_wake_title_precedence_test_beats_site():
    """A wake titled "cross-check test for the live decoder badge"
    matches both `test` (cross-check) and `site` (badge). Test
    should win because the wake's primary artifact is a test."""
    assert categorize_wake_title("cross-check for the live decoder badge") == "test"


def test_every_recent_wake_has_a_known_category():
    """12th cross-check (wake 210): every entry in `load_recent_wakes`
    must carry a `category` field that's a member of
    `WAKE_CATEGORY_ORDER`. Catches a future heuristic change that
    accidentally returns an unknown string."""
    for w in load_recent_wakes():
        assert "category" in w, f"wake {w.get('wake')} missing category field"
        assert w["category"] in WAKE_CATEGORY_ORDER, (
            f"wake {w['wake']} has unknown category {w['category']!r}; "
            f"expected one of {WAKE_CATEGORY_ORDER}"
        )


def test_phase2_arc_findings_card_pair_consistent():
    """11th cross-check (wake 209): the rep_responder ↔ dispatcher
    integration arc spans 5 wakes (157 inbound shadow, 158 inbound
    lockdown, 187 outbound probe, 188 outbound lockdown, 204
    emission swap). Two Findings cards narrate this arc:

      - Keyed to wake 188 — the *foundation* card. Tells the story
        as of wake 188 ("two-step shadow/validate proof... a future
        wake can flip the switch"). Narrates the first 4 steps.
      - Keyed to wake 204 — the *closure* card. Tells the story
        with the emission swap shipped. Narrates all 5 steps.

    Drift mode: someone edits one card to change a step number,
    add a step, or rename a wake, but forgets to update the other.
    Pin the consistency: both cards must reference every wake
    appropriate to their scope.

    Asymmetric design: the closure card MUST mention every wake the
    foundation card mentions (it's a superset narrative) plus its
    own closing wake. The foundation card need not mention the
    closure (that wake didn't exist when the foundation was
    written, narratively speaking)."""
    import re
    cards = {f["wake"]: f for f in load_findings()}
    foundation_arc = [157, 158, 187, 188]
    closure_arc = foundation_arc + [204]
    foundation = cards.get(188)
    closure = cards.get(204)
    assert foundation is not None, (
        "expected a Findings card keyed to wake 188 (phase-2 foundation)"
    )
    assert closure is not None, (
        "expected a Findings card keyed to wake 204 (phase-2 closure)"
    )
    # Case-insensitive "wake NNN" match. Catches both "Wake 157" and
    # "wake 157" forms used across the two summaries.
    for wake in foundation_arc:
        pattern = re.compile(rf"\b[Ww]ake {wake}\b")
        assert pattern.search(foundation["summary"]), (
            f"foundation card (wake 188) summary missing reference "
            f"to wake {wake} — phase-2 arc has drifted between cards"
        )
    for wake in closure_arc:
        pattern = re.compile(rf"\b[Ww]ake {wake}\b")
        assert pattern.search(closure["summary"]), (
            f"closure card (wake 204) summary missing reference "
            f"to wake {wake} — phase-2 arc has drifted between cards"
        )


def test_findings_meta_card_count_matches_manifest():
    """13th cross-check (wake 214) — self-referential. The wake-210
    Findings card narrates the cross-check graph as
    "N invariants" plus per-bucket counts. Those numbers are easy
    to leave behind when a new structural test ships: the
    maintainer adds the test to `test_build_tools.py`, updates
    `CROSS_CHECK_MANIFEST` in `build_site.py`, but forgets the
    Findings card prose. Pin the consistency.

    Asserts:
      - The card title contains "N invariants" where N is
        `sum(len(v) for v in CROSS_CHECK_MANIFEST.values())`.
      - The card summary opens with "N pytest tests" matching the
        same total.
      - Each bucket name appears in the card summary with its
        per-bucket count: e.g. "Code structure** (6 tests:".

    Why not assert the wake-numbers cited in the prose match the
    manifest's per-bucket lists too? That would double the
    surface area for cosmetic typos without proportionally
    raising the safety. The count claim is the most likely thing
    to drift; the per-wake citations are harder to mistype and
    easier to spot in review."""
    import re
    cards = {f["wake"]: f for f in load_findings()}
    card = cards.get(210)
    assert card is not None, (
        "expected the wake-210 cross-check meta-pattern card"
    )
    total = sum(len(v) for v in CROSS_CHECK_MANIFEST.values())
    # Title: "Cross-check test graph: N invariants pinning ..."
    title_match = re.search(rf"\b{total} invariants\b", card["title"])
    assert title_match, (
        f"wake-210 card title should claim {total} invariants "
        f"(matching CROSS_CHECK_MANIFEST); got: {card['title']!r}"
    )
    # Summary opening: "N pytest tests now form ..."
    open_match = re.search(
        rf"\b{total} pytest tests now form\b", card["summary"]
    )
    assert open_match, (
        f"wake-210 card summary should open with '{total} pytest "
        f"tests now form'; got: {card['summary'][:120]!r}..."
    )
    # Summary closing benefit line: "Benefit: N silent failure modes"
    benefit_match = re.search(
        rf"Benefit: {total} silent failure modes", card["summary"]
    )
    assert benefit_match, (
        f"wake-210 card benefit line should say "
        f"'Benefit: {total} silent failure modes'"
    )
    # Per-bucket counts: "Bucket Name** (N tests:"
    for bucket, wakes in CROSS_CHECK_MANIFEST.items():
        n = len(wakes)
        pattern = re.compile(rf"{re.escape(bucket)}\*\*\s*\({n} tests:")
        assert pattern.search(card["summary"]), (
            f"wake-210 card should claim {n} tests in bucket "
            f"{bucket!r} (matching manifest); summary excerpt: "
            f"{card['summary'][card['summary'].find(bucket):card['summary'].find(bucket)+80]!r}"
        )


def test_live_decoder_history_last_entry_matches_current_coverage():
    """16th cross-check (wake 224) — pins the wake-223 coverage
    progression chart's last entry to the live badge value.

    Drift mode: someone adds a new ldtype to LDTYPE_TO_TYPE_IDS
    (badge auto-recomputes to 37/40) but forgets to append a new
    milestone to load_live_decoder_history() (chart still ends at
    36/40). The dashboard's overview-tab chart would silently
    diverge from the badge across the top of the page.

    Asserts the last entry of `load_live_decoder_history()` matches
    the current `load_live_decoder_coverage()` result against the
    captured-types set in data.json. The chart can lag behind the
    badge only by one wake — the SAME commit that adds the codec
    must also append a milestone.

    Why not also pin the chart's earlier history entries against
    git-log-mined data? Those are historical and frozen; only the
    last entry can drift against current state. Pinning just the
    tail keeps the test cheap."""
    import json
    repo = Path(__file__).resolve().parents[2]
    with (repo / "site" / "data.json").open() as f:
        data = json.load(f)
    cov = load_live_decoder_coverage(data["captured_types"])
    hist = load_live_decoder_history()
    assert hist, "load_live_decoder_history() returned an empty list"
    last = hist[-1]
    assert last["covered"] == cov["covered"], (
        f"chart's last entry shows {last['covered']}/{last['total']} "
        f"but the badge computes {cov['covered']}/{cov['total']}. "
        f"If you just added a new ldtype to LDTYPE_TO_TYPE_IDS, "
        f"append a corresponding milestone to "
        f"load_live_decoder_history() in tools/build_site.py."
    )
    assert last["total"] == cov["total"], (
        f"chart's last entry total ({last['total']}) differs from "
        f"the live count of captured types ({cov['total']})"
    )
    # Percent should match too (recomputed deterministically).
    expected_percent = 100.0 * cov["covered"] / cov["total"]
    assert abs(last["percent"] - expected_percent) < 0.01, (
        f"chart's last entry percent ({last['percent']}) differs "
        f"from the recomputed value ({expected_percent:.1f}%)"
    )


def test_every_manifest_wake_has_a_referencing_test():
    """18th cross-check (wake 227) — closes the manifest-vs-tests
    loop on `CROSS_CHECK_MANIFEST`. The wake-214 test asserts the
    wake-210 card's count matches the manifest sum; the wake-218
    test asserts manifest wakes appear in the card; the wake-222
    test asserts manifest wakes are unique across buckets. But
    none of those catches the drift mode 'manifest entry added
    without writing the corresponding test'.

    Scans every `server/javelin/test_*.py` file for `wake N`
    references (case-insensitive, whitespace-tolerant — handles
    both 'wake 222' and the rare 'wake\\n222' that arises from
    line-wrapped docstrings). For each wake in
    `CROSS_CHECK_MANIFEST`, asserts it appears in at least one
    test file. The pattern is loose on purpose: older tests use
    varied phrasings ('Wake 201 invariant', '(wake 166):',
    'wake 178 promoted it to ...') and forcing a strict naming
    convention isn't worth the bulk-rename cost.

    Failure mode it catches: future maintainer adds wake 999 to
    CROSS_CHECK_MANIFEST, updates the wake-210 card claim, but
    forgets the test. No current cross-check catches it. This
    test fails with 'wake 999 missing from any test docstring'."""
    import re
    repo = Path(__file__).resolve().parents[2]
    text_blob = ""
    for test_file in sorted((repo / "server" / "javelin").glob("test_*.py")):
        text_blob += test_file.read_text(errors="replace")
    referenced = {
        int(m.group(1))
        for m in re.finditer(r"[Ww]ake\s+(\d+)", text_blob)
    }
    manifest_wakes = {
        w for bucket in CROSS_CHECK_MANIFEST.values() for w in bucket
    }
    missing = sorted(manifest_wakes - referenced)
    assert not missing, (
        f"CROSS_CHECK_MANIFEST entries without a test docstring "
        f"reference: {missing}. Either write the test (its docstring "
        f"should cite the wake number) or remove the manifest entry."
    )


def test_cross_check_manifest_wake_numbers_are_unique_across_buckets():
    """15th cross-check (wake 222) — defensive pin on the manifest
    itself. CROSS_CHECK_MANIFEST groups cross-check test wakes into
    three buckets (code structure / generated output integrity /
    doc-navigation drift). A wake naturally belongs to exactly one
    bucket — pinning structure isn't the same job as pinning a
    badge value. If a wake appeared in two buckets the wake-214
    count claim ('N invariants') would over-count the actual number
    of distinct tests, and the wake-218 citation pin would
    silently accept the duplicate.

    Asserts every wake number across all manifest values appears
    exactly once. Concrete failure message tells the maintainer
    which wake is duplicated and across which buckets.

    Why "manifest wake-numbers unique across buckets" rather than
    "manifest length matches distinct count"? Same end result,
    different framing: this phrasing makes the failure more
    actionable ('wake N is in both X and Y, pick one')."""
    from collections import Counter
    flat = [
        (wake, bucket)
        for bucket, wakes in CROSS_CHECK_MANIFEST.items()
        for wake in wakes
    ]
    counts = Counter(wake for wake, _ in flat)
    dupes = {w: n for w, n in counts.items() if n > 1}
    if dupes:
        # Find which buckets each duplicate appears in for the
        # diagnostic message.
        dupe_locations = {
            w: [b for ww, b in flat if ww == w]
            for w in dupes
        }
        raise AssertionError(
            f"CROSS_CHECK_MANIFEST has duplicate wake numbers across "
            f"buckets: {dupe_locations}. Each cross-check test "
            f"belongs to exactly one bucket — pick the one that "
            f"best describes the drift mode being pinned and remove "
            f"the duplicate."
        )


def test_findings_meta_card_cites_every_manifest_wake():
    """14th cross-check (wake 218) — extends wake-214 self-referential
    coverage. The wake-214 test pins the COUNT claims in the
    wake-210 card; this test pins the WAKE CITATIONS. Without it, a
    maintainer could swap one wake number for another in the card
    prose (e.g. change "wake 162" to "wake 152" by mistake), keep
    the total count at 14, and pass wake-214's test — but the
    citations would diverge from the manifest's list silently.

    Asserts that for every wake number in CROSS_CHECK_MANIFEST
    (across all three buckets), the summary of the wake-210 card
    contains a reference to that wake number (matched as a bare
    integer at word boundaries — robust to both "wake N" and
    bare-number forms used in the bucket prose).

    Distinct from wake-214 because that test answers "does the card
    claim the right TOTAL?"; this one answers "does the card cite
    the right WAKES?". Together they pin both axes of drift."""
    import re
    cards = {f["wake"]: f for f in load_findings()}
    card = cards.get(210)
    assert card is not None, (
        "expected the wake-210 cross-check meta-pattern card"
    )
    all_wakes = sorted(
        {w for bucket in CROSS_CHECK_MANIFEST.values() for w in bucket}
    )
    assert all_wakes, "expected CROSS_CHECK_MANIFEST to be non-empty"
    summary = card["summary"]
    missing = []
    for wake in all_wakes:
        # Match the wake number as a standalone integer with word
        # boundaries. Manifest wakes (162, 166, ...) don't collide
        # with the non-wake digits in the card body (14 invariants,
        # &lt;30 lines, ~320 lines, etc), so a bare \b{N}\b match
        # is unambiguous in this context.
        pattern = re.compile(rf"\b{wake}\b")
        if not pattern.search(summary):
            missing.append(wake)
    assert not missing, (
        f"wake-210 card summary missing references to manifest wakes: "
        f"{missing}. The wake-218 test pins citation-by-citation "
        f"consistency: every wake listed in CROSS_CHECK_MANIFEST must "
        f"appear in the card. Either fix the card prose to cite the "
        f"wake, or update the manifest if the wake was removed."
    )


def test_findings_card_analysis_doc_references_exist():
    """17th cross-check (wake 225) — bidirectional pin between
    Findings-card prose and `analysis/*.md` files.

    Drift mode: someone renames an analysis doc (e.g. wake 221's
    `decision_0x065c_live_decoder.md` → a shorter
    `decision_0x065c.md`) and updates the README + dashboard
    index links, but the wake-200 Findings card's summary also
    embeds the old path as a `see analysis/decision_*.md for ...`
    reference. The dashboard generation succeeds, the doc still
    exists under its new name, but a visitor clicking through
    the card hits a 404. The wake-221 pattern of citing analysis
    docs from card summaries is useful but creates this new
    drift mode: a card-prose dead link nothing else catches.

    Asserts: scans every Findings card's summary for paths of
    the form `analysis/<filename>.md` (regex requires the .md
    suffix — paths cited without it are deliberately not pinned,
    since they're ambiguous between file and directory
    references) and asserts each resolves to an actual file in
    the repo.

    Remediation on failure: either restore the missing file at
    its referenced path, or update the card prose in
    `tools/build_site.py` to reference the new name.

    Symmetric to wake-207's "every retrospective has a README
    link" — that one pins file → mention; this pins mention →
    file. Both directions together prevent both orphaning AND
    broken references."""
    import re
    repo = Path(__file__).resolve().parents[2]
    pattern = re.compile(r"analysis/[A-Za-z0-9_./-]+\.md")
    missing = []
    for f in load_findings():
        for match in pattern.finditer(f["summary"]):
            rel = match.group(0)
            if not (repo / rel).exists():
                missing.append((f["wake"], f["title"], rel))
    assert not missing, (
        f"Findings cards reference {len(missing)} non-existent "
        f"analysis paths: {missing}. Either restore the missing "
        f"file or update the card prose to drop the reference."
    )


def test_every_decision_doc_has_readme_entry():
    """19th cross-check (wake 231) — extends the wake-207
    retrospective-link pattern to decision documents.

    Drift mode: someone adds a new `analysis/decision_*.md` doc
    (e.g. "why we deferred X" or "why we chose Y") but forgets to
    surface it from README. The wake-228 Architecture-bucket
    Findings card lists decision docs as a discoverable category;
    the wake-225 cross-check requires referenced paths to exist;
    but nothing requires NEW decision docs to be linked from the
    repo root.

    Asserts every `analysis/decision_*.md` file's relative path
    appears in README.md. Symmetric counterpart to wake 207 for a
    different doc category — together they pin that both
    retrospective and decision docs survive as discoverable
    artifacts from the repo root."""
    repo = Path(__file__).resolve().parents[2]
    readme = (repo / "README.md").read_text()
    decisions = sorted((repo / "analysis").glob("decision_*.md"))
    assert decisions, (
        "expected at least one analysis/decision_*.md "
        "(the first is wake-221's 0x065c decision)"
    )
    missing = []
    for path in decisions:
        rel = f"analysis/{path.name}"
        if rel not in readme:
            missing.append(rel)
    assert not missing, (
        f"decision docs without a README link: {missing}. "
        "Add a one-liner under the 'Design decisions' section in "
        "README.md."
    )


def test_every_retrospective_doc_has_readme_entry():
    """Structural drift mode: someone writes a new
    `analysis/session_retrospective_*.md` but forgets to link it from
    `README.md`. The doc still gets indexed by `categorize_doc`
    (Retrospective bucket) and shows up on the dashboard, but a
    visitor landing on the repo root never sees it.

    Pin the invariant: every retrospective file on disk must be
    referenced by relative path in the README. Reverse direction
    isn't enforced (a README link to a future doc is allowed during
    a write-in-progress wake)."""
    repo = Path(__file__).resolve().parents[2]
    readme = (repo / "README.md").read_text()
    retros = sorted((repo / "analysis").glob("session_retrospective_*.md"))
    assert retros, "expected at least one session_retrospective_*.md"
    missing = []
    for path in retros:
        rel = f"analysis/{path.name}"
        if rel not in readme:
            missing.append(rel)
    assert not missing, (
        f"retrospective docs without a README link: {missing}. "
        "Add a one-liner under the Quick links in README.md."
    )
