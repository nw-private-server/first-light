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


def load_test_count():
    import subprocess
    res = subprocess.run(
        [".venv/bin/pytest", "server/javelin/test_codecs.py",
         "--collect-only", "-q"],
        cwd=str(REPO), capture_output=True, text=True,
    )
    m = re.search(r"(\d+) tests collected", res.stdout)
    return int(m.group(1)) if m else 0


def load_findings():
    """Pull a curated list of major findings from the worklog (the last
    few wake entries' headlines)."""
    return [
        {
            "title": "W-direction CRC32 confirmed",
            "wake": 90,
            "summary": "The 4-byte field at offset 0 of every captured "
                       "W-direction message is standard zlib CRC32 over "
                       "(correlation_uuid + envelope), big-endian. Validated "
                       "37 of 39 captured W messages.",
        },
        {
            "title": "Wire-type-id == typeIndex from runtime registry",
            "wake": 90,
            "summary": "info/typeregistry.json (3487 entries) maps each "
                       "registered type's typeIndex to (uuid, handler, "
                       "baseVtable). Verified: typeIndex == wire-format "
                       "type-id. 6 captured types now have authoritative names.",
        },
        {
            "title": "Type-id catalog tables are Unicode case-folding",
            "wake": 88,
            "summary": "An earlier candidate dispatch table at 0x149f41880 "
                       "turned out to be the binary's Unicode case-folding "
                       "lookup, NOT a protocol type-id catalog. The 16960-"
                       "entry size and the 0x40A→0x45A (Cyrillic Tshe → "
                       "tshe) mappings gave it away.",
        },
        {
            "title": "Cross-codec identity-bundle map (11 sub-systems)",
            "wake": 78,
            "summary": "Every captured type's 16-byte identity field "
                       "decomposes as [sub_system_id:8][session_uuid_lower:8]. "
                       "11 distinct sub_system_id values surfaced across "
                       "the codec library, each tied to a specific message "
                       "family.",
        },
        {
            "title": "Server↔client counter pairs",
            "wake": 78,
            "summary": "Four R/W-coupled message pairs documented: "
                       "0x18a6↔0x1a59 (counter-coupled 1→2→3→4), "
                       "0x15d ping↔ack (verbatim echo), 0x14f R (clock "
                       "baseline), 0x8e6↔0x9fc (16-byte hash echo).",
        },
        {
            "title": "VM-on-Apple-Silicon ruled out for runtime testing",
            "wake": 70,
            "summary": "Both UTM and Parallels Desktop fail at GPU "
                       "detection: paravirtualized GPU presents "
                       "VendorId=DeviceId=0 to DXGI; the renderer-init "
                       "rejects. Real-GPU host (AWS g4dn.xlarge or "
                       "physical Windows) is the next step.",
        },
        {
            "title": "Type-name extraction limit + unblock spec",
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
        0xa4: "session_message_a4.py",
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
        0x1097: "result_token_1097.py",
        0x12f6: "keybinding_config_12f6.py",
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
    }


def main():
    data = build_data()
    out = SITE / "data.json"
    with open(out, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"wrote {out} ({len(json.dumps(data))} bytes)")
    print(f"  test_count: {data['stats']['test_count']}")
    print(f"  captured_types: {data['stats']['captured_type_count']}")
    print(f"  codecs: {data['stats']['codec_module_count']}")
    print(f"  decompiles: {data['stats']['decompile_count']}")
    print(f"  named_captured: {data['stats']['named_captured_types']}")


if __name__ == "__main__":
    main()
