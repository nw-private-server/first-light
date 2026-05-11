"""Regenerate the static site under `site/` from current repo data.

Inputs:
  - info/typeregistry.json
  - info/nw-login-safe-20260502-153840/messages-redacted.txt (replay)
  - analysis/typename_mapping.csv
  - analysis/decomp_*.txt
  - server/javelin/*.py (codec inventory)

Outputs:
  - site/data.json (consumed by site/index.html)
  - site/decomp/<addr>.txt (per-function decompile previews, linked from UI)

Run from repo root: `.venv/bin/python3 tools/build_site.py`

The HTML/CSS/JS in site/ is hand-written and committed alongside data.json.
"""
import json
import re
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
SITE.mkdir(exist_ok=True)
(SITE / "decomp").mkdir(exist_ok=True)


def load_registry():
    with open(REPO / "info" / "typeregistry.json") as f:
        data = json.load(f)
    by_typeindex = {}
    for entry in data["data"]["m_list"]:
        if isinstance(entry, list) and len(entry) >= 2:
            d = entry[1]
            ti = d.get("typeIndex")
            if ti is None:
                continue
            by_typeindex[ti] = {
                "uuid": entry[0],
                "name": d.get("name", "") or "",
                "index": d.get("index"),
                "baseVtable": d.get("baseVtable"),
            }
    return by_typeindex


def load_typename_mapping():
    """Load high-confidence names from typename_mapping.csv."""
    out = {}
    csv_path = REPO / "analysis" / "typename_mapping.csv"
    if not csv_path.exists():
        return out
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ti = int(row["typeIndex"])
            out[ti] = (row["name"], row["confidence"])
    return out


def load_captured_messages():
    """Parse replay_store-style data from messages-redacted.txt."""
    import sys
    sys.path.insert(0, str(REPO))
    from server.javelin.replay_store import ReplayStore
    p = REPO / "info" / "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        return []
    store = ReplayStore(p)
    return store.messages


def load_codec_modules():
    """Survey server/javelin/*.py for codec modules + size."""
    out = []
    for py in sorted((REPO / "server" / "javelin").glob("*.py")):
        if py.name.startswith("test_") or py.name == "__init__.py":
            continue
        text = py.read_text()
        # Pull first paragraph of module docstring as description
        m = re.search(r'^"""(.*?)"""', text, re.DOTALL)
        desc = ""
        if m:
            doc = m.group(1).strip()
            # First non-empty line
            first_para = doc.split("\n\n")[0]
            desc = first_para.replace("\n", " ").strip()
        out.append({
            "module": py.name,
            "lines": len(text.splitlines()),
            "description": desc[:300],
        })
    return out


def load_decompiles():
    """List all analysis/decomp_*.txt with first-line preview + size.

    Some files are raw Ghidra JSON exports (`[{"address":..., "code":"..."}]`).
    Detect those and unpack the `code` field so previews are readable.
    """
    out = []
    for txt in sorted((REPO / "analysis").glob("decomp_*.txt")):
        raw = txt.read_text()
        # Strip BOM if present
        if raw.startswith("﻿"):
            raw = raw[1:]

        fn_name = txt.stem
        addr = ""
        body = raw

        # Try JSON-wrapped form first
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                first = parsed[0]
                if "code" in first:
                    body = first["code"]
                if "address" in first:
                    addr = str(first["address"])
                if "name" in first:
                    fn_name = first["name"]
        except (json.JSONDecodeError, ValueError):
            # Plain text — try to parse a leading "// FUN_xxx @ addr" header
            head = body.splitlines()[0] if body else ""
            m = re.match(r"//\s*(\S+)\s*@\s*([0-9a-f]+)", head)
            if m:
                fn_name = m.group(1)
                addr = m.group(2)

        # Normalize line endings for readable preview
        body = body.replace("\r\n", "\n").replace("\r", "\n")
        lines = body.splitlines()

        # Pull a representative function signature from early lines
        sig = ""
        for line in lines[:30]:
            stripped = line.strip()
            if (stripped.startswith(("void ", "int ", "longlong ", "ulonglong ",
                                      "uint ", "char ", "bool ", "undefined",
                                      "size_t ")) and "FUN_" in stripped):
                sig = stripped[:200]
                break

        preview_path = SITE / "decomp" / f"{txt.stem}.txt"
        preview_path.write_text(body[:50000])  # cap at 50KB per file
        out.append({
            "name": fn_name,
            "addr": addr,
            "stem": txt.stem,
            "lines": len(lines),
            "size_bytes": len(body),
            "signature": sig,
        })
    return out


CATEGORY_ORDER = ["Retrospective", "Overview", "RE Finding", "Decompile", "Audit"]


def categorize_doc(filename: str) -> str:
    """Bucket an analysis/*.md filename into a Findings-tab category."""
    name = filename[:-3] if filename.endswith(".md") else filename
    if "retrospect" in name or name in ("cross_link_arc", "MORNING_BRIEF"):
        return "Retrospective"
    if "_audit" in name or name == "ghidra_hunt_list":
        return "Audit"
    if "_decompiles" in name or name == "ghidra_findings":
        return "Decompile"
    if name in {
        "codec_library_overview", "codec_coverage",
        "replay_message_inventory", "message_inventory",
        "integration_status", "queued_work", "state_machine_summary",
        "public_api",
    }:
        return "Overview"
    return "RE Finding"


def load_analysis_docs():
    """Index of `analysis/*.md` writeups for the dashboard.

    For each doc: extract its first heading as the title, the first
    paragraph after the title as a summary, the filename, and a
    category (one of `CATEGORY_ORDER`). Excludes noisy bookkeeping
    docs (worklog) and per-decomp text dumps.
    """
    EXCLUDED = {
        "autonomous_worklog.md",
        "autonomous_worklog_through_253.md",  # wake-261 archive split
    }
    out = []
    for md in sorted((REPO / "analysis").glob("*.md")):
        if md.name in EXCLUDED:
            continue
        try:
            text = md.read_text(errors="replace")
        except Exception:
            continue
        lines = text.splitlines()
        title = md.stem.replace("_", " ")
        summary = ""
        # Title from first '# ' heading
        for ln in lines[:5]:
            if ln.startswith("# "):
                title = ln[2:].strip()
                break
        # Summary from first non-empty, non-heading, non-blockquote
        # paragraph after the title
        in_para = False
        para_lines = []
        for ln in lines[1:]:
            stripped = ln.strip()
            if not stripped:
                if in_para:
                    break
                continue
            if stripped.startswith(("#", ">", "```", "|", "-", "*")):
                if in_para:
                    break
                continue
            in_para = True
            para_lines.append(stripped)
            if len(" ".join(para_lines)) > 220:
                break
        summary = " ".join(para_lines)
        if len(summary) > 220:
            summary = summary[:217] + "…"
        out.append({
            "filename": md.name,
            "title": title,
            "summary": summary,
            "bytes": len(text),
            "category": categorize_doc(md.name),
        })
    return out


def load_decompile_annotations():
    """For each decomp stem, find analysis/*.md docs that reference it
    by name. Excludes the noisy bookkeeping docs (autonomous_worklog,
    codec_test_audit) so the per-row "related" list stays informative.
    Returns: stem → list of {filename, label} dicts.
    """
    EXCLUDED = {
        "autonomous_worklog.md",
        "autonomous_worklog_through_253.md",  # wake-261 archive split
        "codec_test_audit.md",
    }
    stems = [p.stem.replace("decomp_", "")
             for p in (REPO / "analysis").glob("decomp_*.txt")]
    refs: dict[str, list[dict]] = {}
    for md in sorted((REPO / "analysis").glob("*.md")):
        if md.name in EXCLUDED:
            continue
        try:
            text = md.read_text(errors="replace")
        except Exception:
            continue
        for stem in stems:
            if stem in text:
                refs.setdefault(stem, []).append({
                    "filename": md.name,
                    # Friendly label: strip extension, replace underscores
                    "label": md.stem.replace("_", " "),
                })
    return refs


def load_test_count():
    """Collect-only pytest to get the test count without running them.

    Scans the full `server/javelin/` test directory (wake 164) so the
    badge reflects every test the project ships, not just the codec
    suite. That includes the wake-157 shadow-decode tests and the
    wake-162 build-tools tests.

    Uses `.venv/bin/pytest` locally if present, else `pytest` on PATH.
    The CI runner installs pytest globally (no .venv), so the fallback
    matters there.
    """
    import subprocess
    import shutil
    venv_pytest = REPO / ".venv" / "bin" / "pytest"
    pytest_cmd = (
        str(venv_pytest)
        if venv_pytest.exists()
        else shutil.which("pytest")
    )
    if pytest_cmd is None:
        return 0
    res = subprocess.run(
        [pytest_cmd, "server/javelin/", "--collect-only", "-q"],
        cwd=str(REPO), capture_output=True, text=True,
    )
    m = re.search(r"(\d+) tests collected", res.stdout)
    return int(m.group(1)) if m else 0


# Maps each live-decoder `data-ldtype` value to the set of wire-type
# ids it can decode. Family decoders (currently just `subkey`) cover
# multiple type ids — those mirror `KNOWN_FAMILY` in
# `server/javelin/subkey_beacon.py`. Future family decoders need a
# one-line update here. The wake-178 test pins this against the JS-
# side `TYPE_ID_TO_LDTYPE` in `site/index.html`.
LDTYPE_TO_TYPE_IDS: dict[str, set[int]] = {
    "15d_R": {0x15d},
    "15d_W": {0x15d},     # same wire-type, different direction
    "14f":   {0x14f},
    "651":   {0x651},
    "18a6":  {0x18a6},
    "1b88":  {0x1b88},
    "1097":  {0x1097},
    "136a":  {0x136a},
    "1096":  {0x1096},
    "8e6":   {0x8e6},
    # Type 76 is a generic codec used for both 0x40a and 0x1be (same wire shape).
    "76":    {0x40a, 0x1be},
    "9fc":   {0x9fc},
    "a4":    {0xa4},
    "1033":  {0x1033},
    "5b2":   {0x5b2},
    "a95":   {0xa95},
    "1067":  {0x1067},
    "663":   {0x663},
    "16a0":  {0x16a0},
    "ca4":   {0xca4},
    "635":   {0x635},
    "12f6":  {0x12f6},
    # 0x5d1 is NOT in the captured replay (server synthesizes it for
    # the state-10 → 11 transition). Included here for completeness
    # — the coverage join against captured_types naturally drops it.
    "5d1":   {0x5d1},
    # The subkey family decoder covers 14 wire-types — mirrors
    # KNOWN_FAMILY in server/javelin/subkey_beacon.py.
    "subkey": {
        0x066b, 0x102f, 0x1098,
        0x0f7f, 0x101a, 0x101d, 0x10b0, 0x143d,
        0x187c, 0x187f, 0x1a59,
        0x102e,
        0x09d3,
        0x192c,
    },
}


def load_live_decoder_coverage(captured_types: list) -> dict:
    """Compute live-decoder coverage against the captured set.

    Scans `site/index.html` for the `<option value="...">` entries on
    the live-decoder type-id dropdown, maps each `data-ldtype` value
    to one or more wire-type-ids, and joins against the captured-
    types list. Returns `{covered, total, percent, uncovered}` where
    `covered` is the number of distinct captured type_ids the
    decoder can render, `uncovered` is the sorted list of
    `0xNNNN`-form strings the decoder doesn't cover.

    Family decoders (currently just `subkey`) cover multiple type
    ids — the mapping below mirrors `KNOWN_FAMILY` in
    `server/javelin/subkey_beacon.py`. Future family decoders need
    a one-line update here.
    """
    index_html = REPO / "site" / "index.html"
    try:
        text = index_html.read_text()
    except OSError:
        return {"covered": 0, "total": len(captured_types), "percent": 0.0, "uncovered": []}

    # Parse <select id="ld-type"> options to find current ldtypes.
    import re as _re
    m = _re.search(r'<select id="ld-type">(.*?)</select>', text, _re.DOTALL)
    if not m:
        return {"covered": 0, "total": len(captured_types), "percent": 0.0, "uncovered": []}
    ldtypes = _re.findall(r'<option value="([^"]+)"', m.group(1))

    covered_ids: set[int] = set()
    for ld in ldtypes:
        covered_ids.update(LDTYPE_TO_TYPE_IDS.get(ld, set()))

    captured_ids = {int(c["type_id_hex"], 16) for c in captured_types}
    covered_captured = covered_ids & captured_ids
    uncovered_captured = sorted(captured_ids - covered_ids)
    total = len(captured_ids)
    covered = len(covered_captured)
    return {
        "covered": covered,
        "total": total,
        "percent": (covered / total * 100.0) if total else 0.0,
        "uncovered": [f"0x{tid:04x}" for tid in uncovered_captured],
    }


WAKE_CATEGORY_ORDER = ["test", "site", "code", "docs", "other"]


def categorize_wake_title(title: str) -> str:
    """Bucket a worklog wake title into a recent-activity category
    (wake 210). Used to color a pill on the Overview tab strip so a
    visitor scanning recent work can pick out structural-test wakes
    vs feature-code wakes at a glance.

    Heuristic precedence: test → docs → site → code → other. The
    order matters because some titles match multiple keywords:
      - "10th cross-check ..." also mentions retrospective — `test`
        wins because the wake's artifact is a test.
      - "update wake-197 retrospective with wake-204 swap" hits both
        docs and code — `docs` wins because the artifact is doc text.
      - "Findings card for the phase-2D swap" hits site and code —
        `site` wins because the artifact is the dashboard card."""
    t = title.lower()
    # Test: cross-checks, invariants, lockdown tests.
    if any(k in t for k in ("cross-check", "invariant", "lockdown")):
        return "test"
    # Docs: retrospective, README, worklog, checkpoint.
    if any(k in t for k in ("retrospective", "readme", "worklog", "checkpoint", "documentation")):
        return "docs"
    # Site: Findings cards, decoder coverage, dashboard, badges.
    if any(k in t for k in ("findings card", "live decoder", "dashboard", "badge", "category pill")):
        return "site"
    # Code: phase-2 work, heartbeat changes, rep_responder, codecs.
    if any(k in t for k in ("phase-", "heartbeat", "rep_responder", "swap", "codec", "emission", "counter-advance")):
        return "code"
    return "other"


def load_recent_wakes(limit: int = 6):
    """Tail the autonomous worklog and return the most recent N wake
    headlines as a list of `{wake, title, line}` dicts (newest first).

    The "Recent activity" strip on the Overview tab consumes this.
    Re-runs cheaply (regex over the worklog, no git calls), and stays
    in sync automatically — every commit that appends a new wake
    entry refreshes this list on the next build_site run.

    The `line` field (added wake 170) lets the front-end deep-link
    each entry to the corresponding `?plain=1#L<line>` raw-view on
    GitHub. Line numbers stay stable across commits because the
    worklog is append-only.
    """
    worklog = REPO / "analysis" / "autonomous_worklog.md"
    try:
        text = worklog.read_text(errors="replace")
    except OSError:
        return []
    # Match: `## Wake 167 — title goes here`. Capture line numbers
    # alongside via finditer + manual position-to-line conversion.
    pattern = re.compile(
        r"^##\s+Wake\s+(\d+)\s+[—-]\s+(.+?)\s*$",
        flags=re.MULTILINE,
    )
    # Pre-compute line offsets so we can convert each match position
    # to a 1-based line number cheaply.
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)
    import bisect
    headers = []
    for m in pattern.finditer(text):
        line_no = bisect.bisect_right(line_starts, m.start())
        headers.append((int(m.group(1)), m.group(2), line_no))
    if not headers:
        return []
    # Newest-first means *last in the file*. Take the tail.
    tail = headers[-limit:]
    tail.reverse()
    return [
        {"wake": w, "title": t, "line": ln, "category": categorize_wake_title(t)}
        for w, t, ln in tail
    ]


def load_live_decoder_history() -> list[dict]:
    """Hardcoded coverage milestones for the live-decoder progression
    chart (wake 223). Updated by hand at each milestone wake — there
    are few enough of these (~7) that automating extraction from git
    log isn't worth the maintenance. The wake-185 preset coverage
    test + the wake-222 manifest uniqueness test together prevent
    the more critical drift modes; an out-of-date entry here just
    means a slightly stale chart, not a code bug."""
    return [
        {"wake": 152, "covered": 6,  "total": 40, "percent": 15.0,
         "note": "Initial live-decoder shipping with 6 simple codecs"},
        {"wake": 178, "covered": 23, "total": 40, "percent": 57.5,
         "note": "+1097, 136a, 1096, subkey family (14 types via one decoder)"},
        {"wake": 192, "covered": 32, "total": 40, "percent": 80.0,
         "note": "First 80% milestone: +1067 VivoxConfig, +663 LevelDescriptor"},
        {"wake": 199, "covered": 34, "total": 40, "percent": 85.0,
         "note": "+16a0 AssetBlob Small (153 bytes), +ca4 AssetCountTable"},
        {"wake": 213, "covered": 35, "total": 40, "percent": 87.5,
         "note": "+0x635 ActionHistory (variable 15-byte history records)"},
        {"wake": 217, "covered": 36, "total": 40, "percent": 90.0,
         "note": "+0x12f6 KeybindingConfig (UTF-8 binding walk + 2 version blocks)"},
        {"wake": 221, "covered": 36, "total": 40, "percent": 90.0,
         "note": "Decision: 0x065c stays out — 90.0% is the floor by design"},
    ]


def load_test_count_history():
    """Mine git log for the test_count history of site/data.json.

    For each commit that touched site/data.json, extract the recorded
    `stats.test_count` and pair it with a wake number parsed from the
    commit message ("wake 109" form). Returns a list of
    {wake, test_count, commit, subject} ordered by commit date
    (oldest first, so a line chart reads left→right naturally).
    """
    import subprocess
    import re
    res = subprocess.run(
        ["git", "log", "--reverse", "--format=%H|||%s",
         "--", "site/data.json"],
        cwd=str(REPO), capture_output=True, text=True,
    )
    if res.returncode != 0:
        return []
    out = []
    for line in res.stdout.strip().splitlines():
        if "|||" not in line:
            continue
        sha, subject = line.split("|||", 1)
        # Pull the test_count out of the data.json at that commit
        blob = subprocess.run(
            ["git", "show", f"{sha}:site/data.json"],
            cwd=str(REPO), capture_output=True, text=True,
        )
        if blob.returncode != 0:
            continue
        try:
            data = json.loads(blob.stdout)
        except Exception:
            continue
        tc = data.get("stats", {}).get("test_count")
        if tc is None or tc == 0:
            continue
        m = re.search(r"\bwake (\d+)\b", subject)
        wake = int(m.group(1)) if m else None
        out.append({
            "wake": wake,
            "test_count": tc,
            "commit": sha[:7],
            "subject": subject[:120],
        })
    return out


def load_replay_timeline():
    """Per-message timeline data for the session-flow scatter chart.

    Walks the captured replay in seq order and returns a compact
    record per message — enough for a Chart.js scatter:
    x=seq, y=type-id, color=direction, tooltip shows the rest.
    """
    import sys
    sys.path.insert(0, str(REPO))
    from server.javelin.replay_store import ReplayStore
    p = REPO / "info" / "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        return []
    store = ReplayStore(p)
    return [
        {
            "seq": m.seq,
            "type_id": m.type_id,
            "type_id_hex": f"0x{m.type_id:04x}",
            "direction": m.direction,
            "size": len(m.body),
        }
        for m in store.messages
    ]


# How many hex chars of bytes to keep inline in any single bytes field
# of a decoded message (1024 chars = 512 bytes).
_BYTES_HEX_CAP = 1024
# How many hex chars of the raw message body to ship inline (so the
# browser can render a small hex preview alongside the decoded fields).
_BODY_HEX_CAP = 1024


def _to_jsonable(obj, depth: int = 0):
    """Recursively convert a decoded codec dataclass to a JSON-friendly
    structure. Bytes become {hex, len, truncated?}; large blobs are
    truncated so a single "ship the whole replay" pass stays under
    a few hundred KB.
    """
    import dataclasses
    if depth > 6:
        return repr(obj)[:200]
    if isinstance(obj, (bytes, bytearray)):
        h = obj.hex()
        if len(h) > _BYTES_HEX_CAP:
            return {
                "__bytes__": True,
                "hex": h[:_BYTES_HEX_CAP],
                "len": len(obj),
                "truncated": True,
            }
        return {"__bytes__": True, "hex": h, "len": len(obj)}
    if dataclasses.is_dataclass(obj):
        return {
            f.name: _to_jsonable(getattr(obj, f.name), depth + 1)
            for f in dataclasses.fields(obj)
        }
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x, depth + 1) for x in obj]
    if isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    return repr(obj)[:200]


def load_replay_decoded():
    """Pre-decode every captured message via dispatch.decode_replay_message
    so the site can render a click-to-inspect view without server-side
    decoding. Truncates large bytes blobs so the inline JSON payload
    stays small.
    """
    import sys
    sys.path.insert(0, str(REPO))
    from server.javelin.replay_store import ReplayStore
    from server.javelin.dispatch import decode_replay_message
    p = REPO / "info" / "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    if not p.exists():
        return []
    store = ReplayStore(p)
    out = []
    for m in store.messages:
        body_hex = m.body.hex()
        body_truncated = len(body_hex) > _BODY_HEX_CAP
        rec = {
            "seq": m.seq,
            "type_id_hex": f"0x{m.type_id:04x}",
            "direction": m.direction,
            "body_size": len(m.body),
            "body_hex": body_hex[:_BODY_HEX_CAP],
            "body_truncated": body_truncated,
            "has_redaction": m.has_redaction,
            "redacted_spans": m.redacted_spans,
        }
        try:
            decoded = decode_replay_message(m.type_id, m.direction, m.body)
        except Exception as e:
            rec["decode_status"] = "error"
            rec["error"] = f"{type(e).__name__}: {e}"[:300]
            out.append(rec)
            continue
        if decoded is None:
            rec["decode_status"] = "no-codec"
            out.append(rec)
            continue
        rec["decode_status"] = "ok"
        rec["kind"] = type(decoded).__name__
        if isinstance(decoded, (bytes, bytearray)):
            # Framing-only codecs return raw bytes — surface as a single
            # implicit field so the UI can still render something useful.
            rec["fields"] = {"body": _to_jsonable(decoded)}
        else:
            rec["fields"] = _to_jsonable(decoded)
        out.append(rec)
    return out


def load_decompile_groups():
    """Hand-curated grouping of the 39 decompile files by purpose.
    Stems that aren't listed here fall into the "Misc" group at render
    time. Highlights surface the 1-2 most-useful decompiles in each
    group for non-technical visitors."""
    return [
        {
            "label": "State machine (the connection-state blocker)",
            "highlight": "state_advance_predicate",
            "highlight_note": "The *(int*)(wrapper+0xa0)==2 predicate that gates "
                              "the state-10→11 transition. See "
                              "analysis/state_10_unblock_synthesis.md.",
            "stems": [
                "state_advance_predicate",
                "state11_dispatcher",
                "state12_gate_setter_caller",
                "state13_writer_a",
                "state13_writer_b",
                "state13_writer_c",
                "substate_writers",
                "wrapper_state10_entry",
                "wrapper_state10_setup",
                "wrapper_state12_gate",
                "wrapper_state12_gate_writer",
                "wrapper_state13_gate",
                "wrapper_substate_setter_candidate",
                "wrapper_substate_xref_caller_1",
                "wrapper_substate_xref_caller_2",
                "wrapper_switchD8_check",
            ],
        },
        {
            "label": "Connection lifecycle (success / fail / destroy)",
            "highlight": "javelin_game_on_connection_succeed",
            "highlight_note": "The success-path handler invoked when a "
                              "connection completes. Mirror with `_fail` for "
                              "the destroy-path equivalent.",
            "stems": [
                "javelin_game_on_connection_succeed",
                "javelin_game_on_connection_fail",
                "connection_success_caller",
                "destroy_dispatcher",
                "destroy_function",
                "destroy_flag_writer",
                "wrapper_destroy_arg",
            ],
        },
        {
            "label": "V3 RegistrationRequest / Response handlers",
            "highlight": "response_unmarshal",
            "highlight_note": "Where the captured V3 response body is parsed "
                              "by the client. The V3 retry tagged-format "
                              "parser in `server/javelin/v3_request.py` was "
                              "informed by this file.",
            "stems": [
                "v2_builder",
                "v3_builder",
                "response_typeinfo",
                "response_unmarshal",
                "clientconnectionmsg_sender",
                "clientconnectionmsg_typeinfo",
            ],
        },
        {
            "label": "Wrapper setters (the +0xa0 / +0xfa* writers)",
            "highlight": "wrapper_setter_fa10",
            "highlight_note": "One of three wrapper-state setters at "
                              "+0xfa10 / +0xfa30 / +0xfa80 — together they "
                              "implement the wake-3 substate writer pattern.",
            "stems": [
                "wrapper_setter_fa10",
                "wrapper_setter_fa30",
                "wrapper_setter_fa80",
                "gw160_setter",
                "branchA_sender",
            ],
        },
        {
            "label": "Misc / context",
            "highlight": "crash_site",
            "highlight_note": "The destroy-on-error crash site that the "
                              "rep_responder is currently hitting. Useful "
                              "when reading any decompile that ends in a "
                              "throw or _CxxThrowException.",
            "stems": [
                "FUN_146240d70",
                "FUN_1462419c0",
                "FUN_1462426b0",
                "crash_site",
                "loadcontext_no_selfid",
            ],
        },
    ]


def _enrich_families(families: list, captured_types: list) -> list:
    """Attach per-member metadata to each family entry.

    For each `wire_types` hex string in a family, look up the matching
    entry in `captured_types` and attach `name`, `count`, `directions`,
    `codec`. Members that don't match keep just the hex. Front-end
    uses these to render the expandable detail panel on the Overview
    tab's family cards.
    """
    by_id = {}
    for c in captured_types:
        # type_id_hex looks like "0x0003" — normalize to int for matching.
        try:
            by_id[int(c["type_id_hex"], 16)] = c
        except (KeyError, ValueError):
            continue

    enriched = []
    for fam in families:
        members = []
        for hex_id in fam["wire_types"]:
            tid = int(hex_id, 16)
            meta = by_id.get(tid, {})
            members.append({
                "hex": hex_id,
                "name": meta.get("name") or "",
                "count": meta.get("count") or 0,
                "directions": meta.get("directions") or "",
                "codec": meta.get("codec") or "",
            })
        out = dict(fam)
        out["members"] = members
        enriched.append(out)
    return enriched


def load_wire_type_families():
    """Cross-correlated sub_system_id → wire-type groupings from
    `analysis/identity_bundle_correlation.md` (wake 121). Hand-curated:
    the wake-121 analysis ran an offline extraction; surfacing the
    result here lets the dashboard render the relationships visitors
    can't see from raw type-ids alone.

    Each entry groups wire-types that share an 8-byte sub_system_id
    in their identity bundle, meaning they belong to the same in-
    session sub-system family.
    """
    return [
        {
            "sub_system_id": "ce81136a2b7ad33e",
            "wire_types": ["0x102e", "0x1033", "0x192c"],
            "label": "3-way correlation",
            "note": "0x1033 is the wake-102 opaque blob (presumed encrypted). "
                    "0x102e and 0x192c are subkey-beacon family. Shared "
                    "sub_system_id implies the opaque blob's bulk content "
                    "is part of a session-state-bundle whose pieces are "
                    "fragmented across three message types.",
        },
        {
            "sub_system_id": "f8cbed57c68b18f4",
            "wire_types": ["0x18a6", "0x1a59"],
            "label": "Counter-coupled init pair",
            "note": "Init beacon ↔ session subkey beacon. Validated by "
                    "wake-78's counter-coupling finding (counter increments "
                    "0x02→0x03→0x04 across captured copies).",
        },
        {
            "sub_system_id": "93a3e477cb5fd51e",
            "wire_types": ["0x1096", "0x1097"],
            "label": "Spawn-config + token",
            "note": "Frame-config (durations, ratios) and the spawn-"
                    "confirmation result token share a sub_system_id. New "
                    "finding: wake-78's pair list didn't include this; the "
                    "shared identity puts them together.",
        },
        {
            "sub_system_id": "4c0c0ed6478a69da",
            "wire_types": ["0x8e6", "0x9fc"],
            "label": "Identity blob + receipt echo",
            "note": "Already paired by 16-byte hash echo per wake 78; the "
                    "shared sub_system_id confirms.",
        },
        {
            "sub_system_id": "180f8d4e573697c6",
            "wire_types": ["0x5b2", "0xa95"],
            "label": "Fingerprint + permission",
            "note": "Identity-fingerprint set + permission-bitmap. Both "
                    "W-direction client→server.",
        },
        {
            "sub_system_id": "16009918b041c1f9",
            "wire_types": ["0x187c", "0x187f"],
            "label": "Subkey-beacon variant pair",
            "note": "Two subkey-beacon family entries with adjacent type-ids.",
        },
        {
            "sub_system_id": "9e921a154971f6b7",
            "wire_types": ["0xf7f", "0x143d"],
            "label": "Subkey-beacon variant pair",
            "note": "Another subkey-beacon family pair, type-ids non-adjacent.",
        },
    ]


FINDINGS_CATEGORY_ORDER = [
    "RE breakthrough",
    "Wire-level finding",
    "Research closure",
    "Architecture",
]


# Canonical manifest of the dashboard cross-check test graph. The
# wake-210 meta-pattern Findings card narrates this list as
# "N invariants" + per-bucket counts; the wake-214 self-referential
# test asserts the card's claims match this manifest, so a new test
# added to the manifest that forgets to update the card prose fails
# loudly. Bucket names match the card prose verbatim.
CROSS_CHECK_MANIFEST: dict[str, list[int]] = {
    "Code structure":              [162, 166, 178, 184, 185, 196, 222, 227],
    "Generated output integrity":  [172, 201, 202, 224],
    "Doc/navigation drift":        [207, 209, 210, 214, 218, 225, 231],
}


def load_findings():
    """Pull a curated list of major findings from the worklog (the last
    few wake entries' headlines).

    Each entry carries a `category` tag for grouping on the Findings
    tab (wake 163). Categories must be one of
    `FINDINGS_CATEGORY_ORDER`.
    """
    return [
        {
            "title": "sub_system_id deterministic-hash hypothesis ruled out",
            "category": "Research closure",
            "wake": 155,
            "summary": "13 hash families × 9,470 byte-inputs × 2 byte-"
                       "orderings = 246,220 hash invocations checked → 0 "
                       "matches. xxh3_64, xxh64, mmh3 ×3, CRC-64-ECMA all "
                       "tested on top of the wake-122 FNV/SHA/MD5/CRC32 "
                       "set. The 11 captured sub_system_ids are not "
                       "deterministic hashes of any registry name or UUID. "
                       "Session-scoped allocation is now the strongly-"
                       "favored remaining hypothesis.",
        },
        {
            "title": "State-10 gate predicate + trigger identified",
            "category": "RE breakthrough",
            "wake": 112,
            "summary": "The state-10 → 11 transition is gated by "
                       "*(int*)(wrapper+0xa0) == 2 (corrected from the "
                       "earlier +0x130 hypothesis). The trigger is wire "
                       "type 0x5d1 (PlayerManagerSelfIdentificationMsg) — "
                       "not in the captured replay, so the server must "
                       "synthesize it. Codec is wire-bound; ready for "
                       "runtime testing.",
        },
        {
            "title": "State-12 → 13 second writer identified (LevelInfoChanged is the primary)",
            "category": "RE breakthrough",
            "wake": 232,
            "summary": "The state 12 → 13 transition is gated by "
                       "**wrapper[+0xbc8] != 0** (per the state-machine "
                       "summary predicate table). The primary path is "
                       "**LevelInfoChangedMsg**'s handler "
                       "(FUN_146446800) which **directly forces state "
                       "to 13**. A separate scan (`FindOffsetWrites "
                       "0xbc8 0x1`) found that there is also a **soft "
                       "writer** of the gate byte that sets "
                       "wrapper[+0xbc8] = 1 without force-advancing: "
                       "FUN_145a9fa00 (one-line setter, exactly one "
                       "xref). The state machine then advances 12 → 13 "
                       "on its next tick via the normal predicate. The "
                       "writer's single caller is FUN_14645c660 — "
                       "itself a ClientMessagesTrait dispatch-table "
                       "entry (at 0x14abcc45c, 0x300 bytes from "
                       "PlayerManagerSelfIdentification's entry). So a "
                       "**second trait message** (name TBD) provides an "
                       "alternative path to advance state past 12 "
                       "without sending the full LevelInfoChanged "
                       "payload. Static-RE can't recover the message "
                       "name because that dispatch row's metadata "
                       "column points into a different `.rdata` "
                       "segment with no log-strings or RTTI tag near "
                       "the entry. Candidates are the 3 unmapped "
                       "ClientMessagesTrait classes "
                       "(PlayerManagerRejectedMsg, RemoteConfigChangedMsg, "
                       "DebugCommandResponseMsg); definitive ID needs "
                       "a runtime Frida trace hooking FUN_14645c660 to "
                       "log the incoming RTTI tag. Finding originated "
                       "at autonomous-loop wake 13 (2026-05-07) and "
                       "was surfaced into "
                       "`analysis/state_machine_summary.md` § 4½ at "
                       "wake 232 (with a wake-234 correction — the "
                       "wake-232 prose mistakenly framed this as the "
                       "11→12 gate; 11→12 is actually a re-check on "
                       "wrapper[+0xa0] that auto-fires once 10→11 "
                       "lands). State 13 → 14 (entering InGame) "
                       "remains TBD — wrapper[+0x252] is its gate but "
                       "no clean single-writer was found.",
        },
        {
            "title": "Post-V3 state-spawn ladder: 4 transitions mapped (1 writer still open)",
            "category": "RE breakthrough",
            "wake": 240,
            "summary": "Static-RE has mapped the post-V3 state-spawn "
                       "ladder end-to-end. States 10 → 14 form the "
                       "spawn sequence (10=WaitingForREPConnection, "
                       "11=WaitingForActorGameConnection, "
                       "12=WaitingForSpawnPoint, "
                       "13=WaitingForPlayerSpawn, 14=InGame — names "
                       "recovered from the table at 0x1484f9ff0). "
                       "Each transition reads a different field on "
                       "the `GameConnectionWrapper` sub-object at "
                       "`gc + 0x130`: "
                       "**10→11** `*(int)(wrapper+0xa0) == 2`, written "
                       "by `FUN_145a87010` (onConnectionSuccess) "
                       "called from `FUN_146454c00` "
                       "(PlayerManagerSelfIdentification handler); "
                       "wire trigger 0x5d1 (wake 112). "
                       "**11→12** `*(int)(wrapper+0xa0) != 0` — "
                       "inverted check on the same field, auto-fires "
                       "once 10→11 lands. "
                       "**12→13** `*(u8)(wrapper+0xbc8) != 0` — "
                       "primary path: LevelInfoChangedMsg's handler "
                       "(`FUN_146446800`) directly forces state to 13; "
                       "secondary path: `FUN_14645c660` (another "
                       "ClientMessagesTrait dispatch entry, message "
                       "TBD) sets the gate byte via `FUN_145a9fa00` "
                       "(wake 232/234). "
                       "**13→14** `*(u8)(wrapper+0x252) != 0` — "
                       "**writer + trigger chain identified (wakes "
                       "247, 249)**. Writer is `FUN_142ffbc50` in "
                       "the 0x142ff connection-namespace; walks a "
                       "0x70-stride collection at "
                       "`wrapper[+0x1b8..+0x1c0]`, sets the gate to "
                       "1 if any entry matches `param_2` via two "
                       "predicates, emits a notification callback. "
                       "Wake-249 decompiled all 5 caller xrefs — "
                       "they're local state-update functions, not "
                       "message handlers. The most informative caller "
                       "(`FUN_142ff8940`) explicitly **copies a "
                       "0x70-stride collection from an upstream "
                       "container at `param_2[+0x7d0]` INTO "
                       "`wrapper[+0x1b8]`** then re-evaluates the "
                       "gate. So the trigger chain is: **server "
                       "replica-creation message (likely GridMate "
                       "`NewProxy`) → client replica system "
                       "populates `param_2[+0x7d0]` → caller fires, "
                       "copies into wrapper → writer matches "
                       "predicate, sets gate → state advances**. "
                       "**MVP server-side estimate (revised)**: "
                       "**3 messages minimum** — SelfIdent + "
                       "LevelInfoChanged + a replica-creation "
                       "message. The wake-241 alt hypothesis "
                       "(\"only 2 messages needed\") was "
                       "directionally right (local-system-driven) "
                       "but quantitatively off (the local system "
                       "is driven by a server message, just not a "
                       "`ClientMessagesTrait` one). See "
                       "`analysis/state_machine_summary.md` § 1 for "
                       "the predicate table, § 4½ for the wake-232 "
                       "12→13 writer details, and "
                       "`analysis/state_13_14_writer_investigation.md` "
                       "for the full wake-241 → 247 → 249 RE arc. "
                       "The wake-112 + wake-232 individual cards "
                       "capture earlier breakthroughs; this "
                       "synthesis card surfaces the complete "
                       "4-transition picture + the closed-at-"
                       "static-RE-level state.",
        },
        {
            "title": "W-direction CRC32 confirmed",
            "category": "Wire-level finding",
            "wake": 90,
            "summary": "The 4-byte field at offset 0 of every captured "
                       "W-direction message is standard zlib CRC32 over "
                       "(correlation_uuid + envelope), big-endian. Validated "
                       "37 of 39 captured W messages.",
        },
        {
            "title": "Wire-type-id == typeIndex from runtime registry",
            "category": "Wire-level finding",
            "wake": 90,
            "summary": "info/typeregistry.json (3487 entries) maps each "
                       "registered type's typeIndex to (uuid, handler, "
                       "baseVtable). Verified: typeIndex == wire-format "
                       "type-id. 6 captured types now have authoritative names.",
        },
        {
            "title": "Type-id catalog tables are Unicode case-folding",
            "category": "Research closure",
            "wake": 88,
            "summary": "An earlier candidate dispatch table at 0x149f41880 "
                       "turned out to be the binary's Unicode case-folding "
                       "lookup, NOT a protocol type-id catalog. The 16960-"
                       "entry size and the 0x40A→0x45A (Cyrillic Tshe → "
                       "tshe) mappings gave it away.",
        },
        {
            "title": "Cross-codec identity-bundle map (11 sub-systems)",
            "category": "Wire-level finding",
            "wake": 78,
            "summary": "Every captured type's 16-byte identity field "
                       "decomposes as [sub_system_id:8][session_uuid_lower:8]. "
                       "11 distinct sub_system_id values surfaced across "
                       "the codec library, each tied to a specific message "
                       "family.",
        },
        {
            "title": "Sub-system families: 7 of 11 IDs span multiple wire-types",
            "category": "Wire-level finding",
            "wake": 121,
            "summary": "Cross-correlation of the 11 sub_system_ids "
                       "across captured wire-types: 7 of 11 are shared "
                       "by multiple message kinds, surfacing in-session "
                       "sub-system groupings. Notable correlations: "
                       "0x18a6↔0x1a59 (counter-coupled init pair, shared "
                       "ID f8cbed57c68b18f4), 0x8e6↔0x9fc (identity "
                       "blob + receipt echo), 0x1096↔0x1097 (frame "
                       "config + spawn-confirmation token), and the "
                       "3-way 0x102e+0x1033+0x192c (sub_system_id "
                       "ce81136a2b7ad33e — opaque-blob fragmented "
                       "across three message types). All 7 cards "
                       "drilldown from the Overview tab's family panel.",
        },
        {
            "title": "Counter-advance: phase-2D realism extension behind a second flag",
            "category": "Research closure",
            "wake": 208,
            "summary": "The wake-204 dispatched-heartbeat path cached "
                       "the decoded 0x15d once and re-encoded it on "
                       "every emission — bytes were identical to the "
                       "captured replay forever. Real servers slow-"
                       "increment a counter (~1 Hz) and randomize a "
                       "nonce per ping. Wake 208 adds optional "
                       "per-call mutation via a second feature flag "
                       "`heartbeat_advance_counter` (default off — "
                       "preserves wake-204 byte-equality contract). "
                       "When flipped alongside `heartbeat_use_dispatcher`, "
                       "each call mutates `_heartbeat_decoded`: "
                       "`counter += 1` (mod u32, wraps cleanly at "
                       "`0xFFFFFFFF + 1 → 0`) and `nonce = "
                       "_heartbeat_nonce_fn()` (default "
                       "`secrets.randbits(32)`, pluggable for tests). "
                       "Mutation persists across calls so the counter "
                       "genuinely advances. Three new lockdown tests "
                       "pin the advance-when-set, no-advance-default "
                       "(safe-default guarantee), and u32 wraparound "
                       "behaviors. Distinct from the integration arc "
                       "(wakes 157-204) — that arc proves the "
                       "dispatcher CAN emit safely; counter-advance "
                       "extends the emission to match real server "
                       "behavior. The two flags compose: default off/"
                       "off = captured replay; on/off = byte-identical "
                       "dispatcher emission; on/on = genuinely-"
                       "advancing dispatcher emission ready for "
                       "real-GPU validation.",
        },
        {
            "title": "Cross-check test graph: 19 invariants pinning dashboard + workflow drift",
            "category": "Research closure",
            "wake": 210,
            "summary": "19 pytest tests now form a structural drift "
                       "safety net for the dashboard + workflow. Each "
                       "pins a discrete failure mode that wouldn't "
                       "surface as a product bug — silent prose drift, "
                       "stale generated assets, broken category "
                       "heuristics — but would degrade contributor "
                       "experience or documentation legibility. The "
                       "graph splits into three buckets: "
                       "**Code structure** (8 tests: wake 162 "
                       "`parse_sections`, 166 parser coverage, 178 "
                       "JS↔Python LDTYPE map sync, 184 linkify map ↔ "
                       "coverage map, 185 preset coverage, 196 "
                       "shadow/validate-helper lockdown parity, 222 "
                       "manifest wake-numbers unique across "
                       "buckets, **227 every manifest wake has a "
                       "referencing test function**); "
                       "**Generated output integrity** "
                       "(4 tests: 172 preset hex round-trip, 201 "
                       "badge color thresholds, 202 api-ref "
                       "idempotency + on-disk consistency, "
                       "**224 coverage-chart last-entry matches "
                       "badge**); "
                       "**Doc/navigation drift** "
                       "(7 tests: 207 retrospective ↔ README link, "
                       "209 Findings-card pair consistency, 210 "
                       "recent-wake category membership, 214 "
                       "self-referential card-count ↔ manifest "
                       "consistency, 218 wake-number citations "
                       "match manifest, 225 every analysis-doc "
                       "path cited in a Findings card exists on "
                       "disk, **231 every decision doc has a "
                       "README link**). Each test "
                       "is &lt;30 lines and self-documents the drift "
                       "mode in its docstring, including a pointer "
                       "to where the maintainer should fix the "
                       "regression. Test cost: ~420 lines total. "
                       "Benefit: 19 silent failure modes converted "
                       "to loud pytest failures with precise "
                       "remediation hints. Pattern is extensible — "
                       "any future structural invariant becomes test "
                       "20; wakes 214 and 218 together enforce "
                       "that both the count claim AND the wake-number "
                       "citations here match `CROSS_CHECK_MANIFEST` "
                       "in `tools/build_site.py`; wake 222 pins the "
                       "manifest itself against bucket-cross-"
                       "contamination; wake 224 closes the loop on "
                       "the wake-223 coverage chart; wake 225 "
                       "prevents card prose from referencing "
                       "renamed or deleted analysis files; wake 227 "
                       "closes the manifest-vs-tests loop; wake 231 "
                       "extends the wake-207 retrospective-link "
                       "pattern to decision docs. **Stable at 19 "
                       "since wake 231** — no obvious structural "
                       "drift mode remains unpinned in the current "
                       "dashboard surface area; further cross-check "
                       "additions would be incremental over-pinning "
                       "without proportional value. The graph is "
                       "now treated as essentially complete; future "
                       "additions are expected only when a new "
                       "structural surface (e.g. a new doc genre or "
                       "a new generated-asset format) emerges.",
        },
        {
            "title": "Static-RE candidate-triage pattern proven (state-13→14 case study)",
            "category": "Research closure",
            "wake": 251,
            "summary": "The state-13 → 14 writer question was "
                       "deferred for ~10 wakes after the wake-13 "
                       "FindOffsetWrites scan came up empty. Wake "
                       "241 broke the deferral cycle by **shipping a "
                       "candidate-triage investigation log** instead "
                       "of trying to find the writer in one wake — "
                       "the log enumerated all 18+ candidates from "
                       "the offset-scan, ranked them into 4 tiers, "
                       "named the most-likely (`FUN_146c60830` as "
                       "tier-A), and listed 5 concrete next-step "
                       "Ghidra actions. **Wake 247 Ghidra session** "
                       "decompiled both top candidates: tier-A turned "
                       "out to be a false-positive constructor (zeros "
                       "the byte, doesn't set it), but tier-B "
                       "`FUN_142ffbc50` was the writer. **Wake 249 "
                       "Ghidra session** decompiled all 5 caller "
                       "xrefs and identified the trigger chain: "
                       "local replica-system handlers fire when an "
                       "upstream container at `param_2[+0x7d0]` "
                       "changes; they copy 0x70-stride entries into "
                       "the wrapper and re-evaluate the predicate. "
                       "Reusable pattern: when static-RE on a "
                       "specific question keeps deferring across "
                       "wakes, **ship the candidate-triage log first** "
                       "— it converts \"I keep deferring this\" into "
                       "\"the next person with Ghidra access has a "
                       "30-minute path to a finding\". Tier-A being "
                       "a false-positive doesn't invalidate the "
                       "pattern; it validates triaging multiple "
                       "candidates rather than betting on one. The "
                       "wake-241 → 247 → 249 arc spans 3 wakes and "
                       "produced one writer + one trigger chain — a "
                       "rate the deferral-cycle had been blocking. "
                       "See "
                       "`analysis/state_13_14_writer_investigation.md` "
                       "for the full log preserving the wake-241 "
                       "investigation, wake-247 writer-found, and "
                       "wake-249 caller-analysis sections.",
        },
        {
            "title": "Static-RE wall: indirect-vtable termination (NewProxy upstream case study)",
            "category": "Research closure",
            "wake": 252,
            "summary": "Static-RE has natural termination points "
                       "where further progress requires runtime data. "
                       "The state-13 → 14 RE arc (closed wakes 247 + "
                       "249) traced the writer + 5-caller trigger "
                       "chain, but the **upstream** of the trigger "
                       "chain hits a wall: the most-informative "
                       "caller (`FUN_142ff8940`) has 0 unconditional "
                       "call xrefs and 4 data references, all to a "
                       "single vtable entry at `0x14816cec0`. The "
                       "function is invoked indirectly through that "
                       "vtable, so static-RE can't trace the caller "
                       "chain further without finding what dispatches "
                       "through the vtable — and that dispatcher is "
                       "itself indirect, recursively. Identifying the "
                       "specific server message that triggers the "
                       "gate-set (likely GridMate `NewProxy` per "
                       "`ghidra_hunt_list.md` § 2C) is now genuinely "
                       "**runtime-dependent**. A Frida hook on any of "
                       "the 5 callers catches the stack frame at "
                       "call-time and resolves the question "
                       "immediately. This is documented as the **4th "
                       "RE artifact genre — \"wall\"** — distinct "
                       "from finding (writer identified), decision "
                       "(question closed with criteria, e.g. 0x065c "
                       "at wake 221), and investigation (search log "
                       "with candidate triage, e.g. wake 241). The "
                       "4-genre typology is now established in the "
                       "wake-228 skeleton card. Walls aren't "
                       "failures — they're explicit handoff points "
                       "to a different research method (here: "
                       "runtime trace). Without a documented wall, "
                       "future contributors might assume more "
                       "static-RE could close the question; the "
                       "wall card prevents wasted effort. See "
                       "`analysis/state_13_14_writer_investigation.md` "
                       "for the wake-252 wall section.",
        },
        {
            "title": "Server↔client counter pairs",
            "category": "Wire-level finding",
            "wake": 78,
            "summary": "Four R/W-coupled message pairs documented: "
                       "0x18a6↔0x1a59 (counter-coupled 1→2→3→4), "
                       "0x15d ping↔ack (verbatim echo), 0x14f R (clock "
                       "baseline), 0x8e6↔0x9fc (16-byte hash echo).",
        },
        {
            "title": "Phase-2D shipped: heartbeat emission swap behind a feature flag",
            "category": "Research closure",
            "wake": 204,
            "summary": "The 5-step rep_responder ↔ dispatcher "
                       "integration arc is complete: wake 157 inbound "
                       "shadow decode, wake 158 9-test lockdown, "
                       "wake 187 outbound encode-validation probe, "
                       "wake 188 8-test lockdown, **wake 204 actual "
                       "emission swap behind `heartbeat_use_dispatcher` "
                       "(default off)**. Flipping the flag routes "
                       "outbound 0x15d heartbeats through "
                       "`dispatch.encode_replay_message` instead of "
                       "captured replay bytes; the wake-187 startup "
                       "probe + wake-188 lockdown prove byte-equality, "
                       "and a runtime-failure fallback in the "
                       "dispatched path keeps the heartbeat stream "
                       "alive even if the dispatcher raises. Three "
                       "additional lockdown tests pin the dispatched "
                       "path (byte-identical to replay, log-level "
                       "progression, fallback safety net). The "
                       "captured-replay path remains the safe default "
                       "until a real-GPU host validates the swap end-"
                       "to-end. Pattern is now reusable: any future "
                       "dispatcher-emission promotion follows shadow → "
                       "lockdown → validate → lockdown → swap, with "
                       "each step staying logging-only or feature-"
                       "flagged-off until the next gets ≥6 tests.",
        },
        {
            "title": "rep_responder ↔ dispatcher integration foundation proven safe",
            "category": "Research closure",
            "wake": 188,
            "summary": "Two-step shadow/validate proof that the central "
                       "dispatcher can drive the rep_responder's wire "
                       "output safely. Wake 157 added an inbound shadow-"
                       "decode path (every received record routes through "
                       "the dispatcher at debug-log level, no behavior "
                       "change); wake 158 locked it down with 9 tests. "
                       "Wake 187 added an outbound encode-validation "
                       "probe (at startup, decode + re-encode the cached "
                       "0x15d heartbeat through the dispatcher, assert "
                       "byte-equality against the captured body); wake "
                       "188 locked that down with 8 tests across the "
                       "success / mismatch / decoder-exception / "
                       "encoder-exception branches. The startup probe "
                       "currently logs 'dispatcher encoder produces "
                       "byte-identical heartbeat — emission-path swap "
                       "would be safe.' A future wake can flip the "
                       "switch and have the responder emit dispatcher-"
                       "encoded fresh bytes instead of captured replay "
                       "bytes, with the wake-105 round-trip tests + the "
                       "two lockdowns catching any regression. The "
                       "incremental approach (shadow → lockdown → "
                       "validate → lockdown → swap) is now a repeatable "
                       "pattern for every future dispatcher-emission "
                       "promotion.",
        },
        {
            "title": "Remaining 4 uncovered wire-types: structural reasons",
            "category": "Research closure",
            "wake": 200,
            "summary": "Live-decoder coverage at 36/40 (90.0%) — the "
                       "remaining 4 captured wire-types are uncovered "
                       "for cause, not for lack of effort. **Three "
                       "are structurally unable to add**: 0x0003 "
                       "(REPClient registration response — server-"
                       "emitted only, no captured-side decode path), "
                       "0x0008 (chunked_stream — meta-codec for "
                       "framing, not a single message), 0x0013 (V3 "
                       "request — encoder-only path; we don't "
                       "reply-decode our own V3 sends). **The fourth "
                       "is a deliberate decision**: 0x065c "
                       "(world_data_blob — 12706 bytes / 42 variable-"
                       "size records with ff_padding trailers) was "
                       "deferred at wake 221 — the 12-kbyte blob "
                       "shape fails the \"single-screen JS rendering "
                       "useful to a visitor\" bar the other 36 "
                       "covered types meet. See "
                       "`analysis/decision_0x065c_live_decoder.md` "
                       "for criteria, reversal conditions, and the "
                       "120-150-line cost estimate behind the call. "
                       "For complexity reference: wake 213's 0x0635 "
                       "shipped at ~70 lines, wake 217's 0x12f6 at "
                       "~85 lines — those mark the upper-end "
                       "complexity points already covered; 0x065c "
                       "would push well past both. **90.0% is the "
                       "floor by design, not by accident.**",
        },
        {
            "title": "Live decoder addresses 90% of captured wire-types",
            "category": "Research closure",
            "wake": 192,
            "summary": "36 of 40 captured wire-types (90.0%) are now "
                       "decodable directly from the dashboard's "
                       "Explore tab — no clone, no CLI, no Python "
                       "required. The visitor pastes a hex body, "
                       "picks the type, and sees field-aligned output. "
                       "Captured-string rendering surfaces "
                       "production identifiers inline: 0x1067 "
                       "VivoxConfig exposes the production Vivox API "
                       "URL + realm + issuer; 0x663 LevelDescriptor "
                       "shows the level name and path "
                       "(e.g. \"NewWorld_VitaeEterna\"). Wake 213's "
                       "0x0635 ActionHistory introduced the "
                       "variable-length-record decoder pattern "
                       "(15-byte history records); wake 217's 0x12f6 "
                       "KeybindingConfig extended it with u8-prefixed "
                       "UTF-8 string walks — those mark the upper-end "
                       "complexity shapes covered to date. A typo in "
                       "any preset hex or a drift between the JS and "
                       "Python type-id maps fails loudly at pytest "
                       "with a precise pointer at the broken row "
                       "(see the wake-210 cross-check meta-pattern "
                       "card for the full graph).",
        },
        {
            "title": "Codec audit arcs both closed at 0 gaps",
            "category": "Research closure",
            "wake": 136,
            "summary": "Two complete audits of the 40-codec library, "
                       "both closing at 0 gaps. The decoder-rejection "
                       "audit (wakes 125-126) added structural-rejection "
                       "tests for every codec — corrupt or wrong-sized "
                       "input must raise a precise error, not silently "
                       "decode garbage. The encoder round-trip audit "
                       "(wakes 135-136) added populated round-trip tests "
                       "for every codec — encode(decode(captured)) must "
                       "equal the original bytes. Together: every codec "
                       "has both halves of the wire-format contract "
                       "pinned. 0 captured wire-types lack either test "
                       "as of this writing. See cross_link_arc.md for "
                       "the scaffold-wedge-close pattern that closed "
                       "both arcs in 2-3 wakes each.",
        },
        {
            "title": "Four-retrospective session-arc skeleton",
            "category": "Architecture",
            "wake": 228,
            "summary": "The autonomous-session work is now narrated "
                       "across four frozen retrospective documents, "
                       "each covering a coherent multi-wake arc: "
                       "wakes 1-150 "
                       "(`analysis/session_retrospective_150.md`) — "
                       "codec library + dispatcher + initial "
                       "dashboard, ending at 40/40 captured-codec "
                       "coverage and the wake-112 state-10 RE "
                       "breakthrough; wakes 151-196 "
                       "(`analysis/session_retrospective_196.md`) — "
                       "navigable dashboard, live decoder at 80%, "
                       "rep_responder ↔ dispatcher integration "
                       "foundation; wakes 197-227 "
                       "(`analysis/session_retrospective_227.md`) — "
                       "live decoder push to 90.0% (with the wake-221 "
                       "floor decision), phase-2 emission swap + "
                       "counter-advance realism extension, and the "
                       "cross-check graph (see the wake-210 "
                       "meta-pattern card for current count, with "
                       "five self-referential pins on the meta-card "
                       "itself); **wakes "
                       "228-253 "
                       "(`analysis/session_retrospective_253.md`) — "
                       "state-machine RE closure arc, all 4 post-V3 "
                       "state-spawn transitions now have writers + "
                       "trigger chains identified at static-RE level, "
                       "with the wake-252 indirect-vtable wall marking "
                       "the static-RE limit (further progress on "
                       "NewProxy wire-type ID is runtime-dependent)**. "
                       "Each doc is a frozen snapshot of its arc + a "
                       "forward pointer to the next. The wake-207 "
                       "cross-check "
                       "pins each doc to a README link; the wake-225 "
                       "cross-check pins each path cited in this "
                       "card to actually exist; wake 231 added an "
                       "analogous pin for decision-doc README links. "
                       "Future arcs follow the same pattern: ~25-50 "
                       "wakes per retrospective, snapshot + 3-5 phases "
                       "+ open-items + forward pointer. The wake-253 "
                       "retro covers 26 wakes — slightly below the "
                       "previous-arc range, but the state-machine "
                       "closure provided a natural narrative anchor. "
                       "Four artifact genres now coexist on the "
                       "Findings tab: **retrospectives** (frozen "
                       "snapshots — 4 docs, this is their card); "
                       "**decision docs** (closed questions with "
                       "reversal criteria — wake 221's 0x065c, cited "
                       "from the wake-200 Findings card); "
                       "**investigation logs** (search-in-progress "
                       "with candidate triage — wake 241's "
                       "state-13→14 search, surfaced via the "
                       "wake-251 methodology card); **walls** "
                       "(documented static-RE limit, runtime handoff "
                       "necessary — wake 252's indirect-vtable "
                       "termination, surfaced via the wake-257 "
                       "wall card). Each genre has at least one "
                       "exemplar Findings card on the dashboard, "
                       "completing the 4-genre coverage as of wake "
                       "257.",
        },
        {
            "title": "VM-on-Apple-Silicon ruled out for runtime testing",
            "category": "Architecture",
            "wake": 70,
            "summary": "Both UTM and Parallels Desktop fail at GPU "
                       "detection: paravirtualized GPU presents "
                       "VendorId=DeviceId=0 to DXGI; the renderer-init "
                       "rejects. Real-GPU host (AWS g4dn.xlarge or "
                       "physical Windows) is the next step.",
        },
        {
            "title": "Type-name extraction limit + unblock spec",
            "category": "RE breakthrough",
            "wake": 97,
            "summary": "Static-only methodology recovered 5 confirmed "
                       "captured-type names (REPClient::*, etc.) and 297 of "
                       "312 named registry entries. Pushing past 5 captured "
                       "names needs runtime data — see "
                       "analysis/typename_unblock_spec.md.",
        },
    ]


def build_data():
    registry = load_registry()
    captured_msgs = load_captured_messages()
    typename_map = load_typename_mapping()
    codecs = load_codec_modules()
    decompiles = load_decompiles()
    test_count = load_test_count()
    findings = load_findings()
    replay_timeline = load_replay_timeline()
    replay_decoded = load_replay_decoded()
    test_count_history = load_test_count_history()
    live_decoder_history = load_live_decoder_history()
    wire_type_families = load_wire_type_families()
    decompile_groups = load_decompile_groups()
    decompile_annotations = load_decompile_annotations()
    analysis_docs = load_analysis_docs()

    # Merge annotations into decompiles (key match: txt.stem is
    # "decomp_<name>", annotations are keyed by "<name>"). Empty list
    # when nothing references the decomp.
    for d in decompiles:
        bare_stem = d["stem"].replace("decomp_", "", 1)
        d["related"] = decompile_annotations.get(bare_stem, [])

    # Build captured-types list
    captured_by_id = {}
    for m in captured_msgs:
        d = captured_by_id.setdefault(m.type_id, {
            "type_id": m.type_id,
            "type_id_hex": f"0x{m.type_id:04x}",
            "directions": set(),
            "sizes": set(),
            "count": 0,
        })
        d["directions"].add(m.direction)
        d["sizes"].add(len(m.body))
        d["count"] += 1

    # Codec module map for captured types
    codec_for_type = {
        0x03: "v3_response.py",
        0x08: "chunked_stream_08.py",
        0x13: "v3_request.py",
        0xa4: "session_message_a4.py",
        0x651: "empty_marker_651.py",
        0x14f: "session_clock_beacon.py",
        0x15d: "heartbeat_15d.py",
        0x1be: "handshake_blob_76.py",
        0x40a: "handshake_blob_76.py",
        0x5b2: "identity_fingerprint_5b2.py",
        0x635: "action_history_635.py",
        0x65c: "world_data_blob_65c.py",
        0x663: "level_descriptor_663.py",
        0x8e6: "identity_blob_8e6.py",
        0x9fc: "receipt_handshake_9fc.py",
        0xa95: "permission_bitmap_a95.py",
        0xca4: "asset_count_table_ca4.py",
        0x1067: "vivox_config_1067.py",
        0x1096: "frame_config_1096.py",
        0x1097: "result_token_1097.py",
        0x12f6: "keybinding_config_12f6.py",
        0x1033: "opaque_blob_1033.py",
        0x136a: "result_token_136a.py",
        0x16a0: "asset_blob_16a0.py",
        0x18a6: "init_message_18a6.py",
        0x1a59: "session_subkey_1a59.py",
        0x1b88: "session_identity_beacon.py",
        # subkey_beacon family:
        **{tid: "subkey_beacon.py (generic)" for tid in
           [0x66b, 0x9d3, 0xf7f, 0x101a, 0x101d, 0x102e, 0x102f,
            0x10b0, 0x143d, 0x187c, 0x187f, 0x192c, 0x1098]},
    }

    captured_list = []
    for tid in sorted(captured_by_id):
        d = captured_by_id[tid]
        reg = registry.get(tid, {})
        name_info = typename_map.get(tid)
        registry_name = reg.get("name", "")
        confidence = "registry-direct" if registry_name else "no-name"
        if name_info:
            full_name, conf = name_info
            if conf == "direct":
                display_name = full_name
                confidence = "binary-confirmed"
            elif conf in ("hi", "med"):
                display_name = full_name + f" ({conf})"
                confidence = conf
            elif conf == "registry-only":
                display_name = registry_name or "(unnamed)"
                confidence = "registry-only"
            else:
                display_name = "(unclaimed)"
                confidence = "unclaimed"
        else:
            display_name = registry_name or "(unnamed)"

        captured_list.append({
            "type_id": tid,
            "type_id_hex": f"0x{tid:04x}",
            "count": d["count"],
            "directions": "".join(sorted(d["directions"])),
            "sizes": sorted(d["sizes"]),
            "name": display_name,
            "uuid": reg.get("uuid", ""),
            "registry_index": reg.get("index"),
            "confidence": confidence,
            "codec": codec_for_type.get(tid, ""),
        })

    # ---- summaries for charts + landing ----

    # Total replay-message counts by direction
    direction_counts = {"R": 0, "W": 0}
    for c in captured_list:
        for d in c["directions"]:
            direction_counts[d] = direction_counts.get(d, 0) + c["count"]

    # Top-15 types by raw message count (for the volume bar chart)
    volume_top = sorted(
        captured_list, key=lambda c: -c["count"]
    )[:15]
    volume_top_short = [
        {
            "type_id_hex": c["type_id_hex"],
            "count": c["count"],
            "name": c["name"][:40],
            "codec": c["codec"],
        }
        for c in volume_top
    ]

    # Coverage breakdown for the doughnut
    coverage_buckets = {
        "Confirmed name (binary or registry)": 0,
        "Structural codec": 0,
        "Framing-only / opaque": 0,
    }
    framing_only_codecs = {
        "opaque_blob_1033.py", "chunked_stream_08.py",
    }
    for c in captured_list:
        if c["confidence"] in ("binary-confirmed", "registry-direct"):
            coverage_buckets["Confirmed name (binary or registry)"] += 1
        elif c["codec"] in framing_only_codecs:
            coverage_buckets["Framing-only / opaque"] += 1
        elif c["codec"]:
            coverage_buckets["Structural codec"] += 1
        else:
            coverage_buckets["Framing-only / opaque"] += 1

    # The 13-state connection-handshake diagram. State numbering follows
    # the binary's internal state machine; descriptions are plain-English
    # interpretations from wakes 60-80.
    state_machine = [
        {"n": 1, "name": "Init", "desc": "Client object built; nothing on the wire yet."},
        {"n": 2, "name": "DTLS handshake", "desc": "TLS-over-UDP setup. Server cert, key exchange, cipher agreed."},
        {"n": 3, "name": "Connect request", "desc": "Carrier system message asking the server to register the client."},
        {"n": 4, "name": "Connect ack", "desc": "Server acknowledges the connect, opens the data channel."},
        {"n": 5, "name": "V3 registration", "desc": "Client sends its identity (Steam ID, persona, sdk version)."},
        {"n": 6, "name": "Registration response", "desc": "Server returns a session token; client validates."},
        {"n": 7, "name": "Heartbeat exchange", "desc": "Ping/ack pair — both sides confirm the session is alive."},
        {"n": 8, "name": "Identity beacons", "desc": "Sub-system identity fingerprints exchanged."},
        {"n": 9, "name": "Asset count + key tables", "desc": "Server tells the client what world data to expect."},
        {"n": 10, "name": "World data streaming", "desc": "Bulk world / level data over the chunked stream (0x08)."},
        {"n": 11, "name": "Substate setup", "desc": "Open thread — the gate from 10 to 11 is the current blocker."},
        {"n": 12, "name": "World ready", "desc": "Game can render the world; player can move."},
        {"n": 13, "name": "Steady state", "desc": "Heartbeats + world updates only; normal play."},
    ]
    BLOCKER_STATE = 11  # 10→11 transition is the current open thread

    # FAQ — plain-English answers
    faq = [
        {
            "q": "What is this project?",
            "a": "A reverse-engineering effort to understand New World's network protocol "
                 "well enough to build a private server. Right now it's static-analysis "
                 "work: pulling apart the game binary and a captured login session to "
                 "figure out how each message on the wire is structured.",
        },
        {
            "q": "Can I play on it?",
            "a": "Not yet. The codec library can read and re-emit every captured message "
                 "byte-for-byte, but the runtime side (an actual server you'd point your "
                 "game at) still needs significant work — at minimum, the connection "
                 "state machine has an open blocker at the 10→11 transition.",
        },
        {
            "q": "Why is it stuck on \"state 10\"?",
            "a": "The game runs through a sequence of internal states from \"client just "
                 "started\" to \"steady gameplay.\" Our captured replay drives the server "
                 "through state 10 cleanly, but the predicate that lets state 10 advance "
                 "to state 11 reads runtime data that the captured replay alone doesn't "
                 "supply. Cracking that needs a real-GPU host running the game.",
        },
        {
            "q": "Is this affiliated with Amazon Games?",
            "a": "No. This is an independent reverse-engineering project for "
                 "research and hobby purposes.",
        },
        {
            "q": "Why are some messages \"opaque\" but others fully decoded?",
            "a": "Most captured message types have observable structure (numeric "
                 "values, known field shapes, repeated patterns) and got full structural "
                 "codecs. A few (`0x1033`, the largest `0x08`) look like encrypted or "
                 "signed material — without runtime context we can't subdivide their "
                 "bodies meaningfully, so the codec just treats them as opaque payloads.",
        },
    ]

    # Project milestone timeline. Hand-curated rather than auto-extracted
    # because the value lives in the framing, not in raw wake numbers.
    timeline = [
        {"label": "Codec scaffolding starts",
         "wake": "wake 1-30",
         "desc": "First passes at the wire framing — datagram + record layers, system "
                 "messages, the V3 registration request format."},
        {"label": "First captured-type codecs ship",
         "wake": "wake 30-60",
         "desc": "Per-type codecs for the heartbeat, init message, identity beacons, "
                 "and the subkey-beacon family. Tests grow past 100."},
        {"label": "Replay round-trip works",
         "wake": "wake 60-80",
         "desc": "Full captured DTLS replay parses cleanly. State machine reverse-"
                 "engineered from binary decompiles; state-10 blocker identified."},
        {"label": "Type registry + 5 confirmed names",
         "wake": "wake 90-97",
         "desc": "3487-entry runtime type registry mapped against MSVC RTTI strings. "
                 "5 captured wire-types confirmed by direct binary match (REPClient::"
                 "RegistrationResponseMsg, TimeSynchMsg, PingMsg, etc)."},
        {"label": "Visualization site shipped",
         "wake": "wake 98",
         "desc": "This site! Generated from the codec library + analysis files; "
                 "deployed to GitHub Pages."},
        {"label": "Codec coverage hits 40/40",
         "wake": "wake 100-103",
         "desc": "Every captured wire-type in the replay now has a codec — "
                 "including the empty-marker (0x651), the 80-byte frame-config "
                 "(0x1096), the opaque blob (0x1033), and the chunked stream (0x08, "
                 "the high-volume world-data type)."},
        {"label": "Central dispatcher",
         "wake": "wake 104-107",
         "desc": "Single decode/encode router for every captured type. 174 captured "
                 "messages round-trip byte-identically through the dispatcher; only "
                 "documented-edge-case failures remain."},
        {"label": "Test coverage audits closed",
         "wake": "wake 125-126, 135-136",
         "desc": "Heuristic-based audits of decoder rejection + encoder round-trip "
                 "tests. Both arcs followed scaffold → wedge → close in 2 wakes each. "
                 "Tests 320 → 346. Final gap counts: 0 + 0. See "
                 "analysis/cross_link_arc.md for the retrospective."},
        {"label": "Dashboard polish + auto-updating badges",
         "wake": "wake 137-140",
         "desc": "Shields.io endpoint JSON regenerated each build so README test/codec "
                 "counters stay live. Decompiles tab cross-link density 100%. "
                 "\"How it works\" tab with a guided codec-pipeline walkthrough. "
                 "Audit-gap stat card on Overview."},
    ]

    # Enrich wire-type families with per-member metadata so the
    # Overview-tab cards can render a detail panel inline.
    wire_type_families = _enrich_families(wire_type_families, captured_list)

    # Compute live-decoder coverage so the Explore tab can show a
    # progress badge.
    live_decoder_coverage = load_live_decoder_coverage(captured_list)

    return {
        "generated_at": "auto-generated by tools/build_site.py",
        "stats": {
            "test_count": test_count,
            "codec_module_count": len(codecs),
            "captured_type_count": len(captured_list),
            "registry_entry_count": len(registry),
            "decompile_count": len(decompiles),
            "named_captured_types": sum(
                1 for c in captured_list
                if c["confidence"] in ("binary-confirmed", "registry-direct")
            ),
        },
        "captured_types": captured_list,
        "codecs": codecs,
        "decompiles": decompiles,
        "findings": findings,
        "direction_counts": direction_counts,
        "volume_top": volume_top_short,
        "coverage_buckets": coverage_buckets,
        "state_machine": state_machine,
        "blocker_state": BLOCKER_STATE,
        "faq": faq,
        "timeline": timeline,
        "replay_timeline": replay_timeline,
        "replay_decoded": replay_decoded,
        "test_count_history": test_count_history,
        "live_decoder_history": live_decoder_history,
        "wire_type_families": wire_type_families,
        "decompile_groups": decompile_groups,
        "analysis_docs": analysis_docs,
        "analysis_doc_categories": CATEGORY_ORDER,
        "findings_categories": FINDINGS_CATEGORY_ORDER,
        "recent_wakes": load_recent_wakes(limit=6),
        "live_decoder_coverage": live_decoder_coverage,
    }


def _coverage_badge_color(pct: float) -> str:
    """Map a coverage percentage to a shields.io badge color.

    The visual progression is intentional: a future contributor's
    +1-decoder push that crosses a threshold (40, 60, 80) bumps the
    badge color visibly. Wake-201 invariant test pins these
    thresholds so a future tweak to the function body fails loudly.

    Thresholds:
      - ≥80% → brightgreen
      - ≥60% → blue
      - ≥40% → yellow
      - below 40% → orange
    """
    if pct >= 80:
        return "brightgreen"
    if pct >= 60:
        return "blue"
    if pct >= 40:
        return "yellow"
    return "orange"


def write_badges(data: dict) -> None:
    """Emit shields.io endpoint JSON files for README badges.

    Each badge is `site/badge-<name>.json` consumed by:
      https://img.shields.io/endpoint?url=https://nw-private-server.github.io/first-light/badge-<name>.json

    Keeps the README counters in sync with the live build automatically.
    """
    stats = data["stats"]
    cov = data.get("live_decoder_coverage", {})
    cov_covered = cov.get("covered", 0)
    cov_total = cov.get("total", 0)
    cov_pct = (cov_covered / cov_total * 100.0) if cov_total else 0.0
    cov_color = _coverage_badge_color(cov_pct)
    badges = {
        "tests": {
            "schemaVersion": 1,
            "label": "tests",
            "message": f"{stats['test_count']} passing",
            "color": "brightgreen",
        },
        "codecs": {
            "schemaVersion": 1,
            "label": "captured types covered",
            "message": f"{stats['captured_type_count']}/40",
            "color": "brightgreen" if stats["captured_type_count"] == 40 else "yellow",
        },
        "tests-count": {
            "schemaVersion": 1,
            "label": "tests",
            "message": str(stats["test_count"]),
            "color": "brightgreen",
        },
        # Wake 195: live-decoder coverage. "X/40 in live decoder" links to
        # the Explore tab on the live dashboard. Color steps with %-thresholds.
        "live-decoder": {
            "schemaVersion": 1,
            "label": "live decoder",
            "message": f"{cov_covered}/{cov_total}" if cov_total else "0/?",
            "color": cov_color,
        },
    }
    for name, payload in badges.items():
        (SITE / f"badge-{name}.json").write_text(json.dumps(payload))


def main():
    data = build_data()
    out = SITE / "data.json"
    with open(out, "w") as f:
        json.dump(data, f, indent=2, default=str)
    write_badges(data)
    print(f"wrote {out} ({len(json.dumps(data))} bytes)")
    print(f"  test_count: {data['stats']['test_count']}")
    print(f"  captured_types: {data['stats']['captured_type_count']}")
    print(f"  codecs: {data['stats']['codec_module_count']}")
    print(f"  decompiles: {data['stats']['decompile_count']}")
    print(f"  named_captured: {data['stats']['named_captured_types']}")
    print(f"  replay_decoded: {len(data['replay_decoded'])}")


if __name__ == "__main__":
    main()
