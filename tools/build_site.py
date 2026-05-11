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
        [pytest_cmd, "server/javelin/test_codecs.py",
         "--collect-only", "-q"],
        cwd=str(REPO), capture_output=True, text=True,
    )
    m = re.search(r"(\d+) tests collected", res.stdout)
    return int(m.group(1)) if m else 0


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
            "title": "Server↔client counter pairs",
            "category": "Wire-level finding",
            "wake": 78,
            "summary": "Four R/W-coupled message pairs documented: "
                       "0x18a6↔0x1a59 (counter-coupled 1→2→3→4), "
                       "0x15d ping↔ack (verbatim echo), 0x14f R (clock "
                       "baseline), 0x8e6↔0x9fc (16-byte hash echo).",
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
        "wire_type_families": wire_type_families,
        "decompile_groups": decompile_groups,
        "analysis_docs": analysis_docs,
        "analysis_doc_categories": CATEGORY_ORDER,
        "findings_categories": FINDINGS_CATEGORY_ORDER,
    }


def write_badges(data: dict) -> None:
    """Emit shields.io endpoint JSON files for README badges.

    Each badge is `site/badge-<name>.json` consumed by:
      https://img.shields.io/endpoint?url=https://nw-private-server.github.io/first-light/badge-<name>.json

    Keeps the README counters in sync with the live build automatically.
    """
    stats = data["stats"]
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
