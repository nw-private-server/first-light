"""Bulk-extract type names from InstallRegistrationHook<T> typeinfo
strings, anchored by named registry entries.

Wake 95 v1: 297/312 named entries matched. Interpolation was too
aggressive — produced duplicates.

Wake 96 v2: tighter algorithm:
  1. Detect TU boundaries by address gaps in the typeinfo string list.
  2. Within each TU, walk strings in reverse-address order matching
     consecutive registry indices.
  3. Claim each string at most once.
  4. Mark each output entry with a confidence flag:
       direct       — exact name match between registry and a string
       hi          — interpolated within ≤5 indices of an anchor (both sides)
       med         — interpolated within ≤50 indices of an anchor
       lo          — outside that window
       unclaimed   — no string available for this index

Inputs:
  - info/typeregistry.json
  - analysis/installhook_strings_by_addr.txt

Output:
  - analysis/typename_mapping.csv (typeIndex, name, confidence)
"""
import json
from pathlib import Path

REPO = Path("/Users/junichi/Programs/NewWorldFirstLight")

# Address gap that we treat as a TU boundary (typeinfos within a TU are
# typically packed at ~0x80 bytes apart; a gap >= this threshold is
# treated as a new TU).
TU_GAP_THRESHOLD = 0x200


def parse_mangled(mangled):
    parts = mangled.split("@")
    return "::".join(reversed(parts))


def main():
    # 1. Load registry, sorted by index
    with open(REPO / "info" / "typeregistry.json") as f:
        data = json.load(f)
    registry = []
    for entry in data["data"]["m_list"]:
        if isinstance(entry, list) and len(entry) >= 2:
            d = entry[1]
            idx = d.get("index")
            ti = d.get("typeIndex")
            nm = d.get("name", "") or ""
            if idx is not None and ti is not None:
                registry.append((idx, ti, nm))
    registry.sort()
    idx_count = len(registry)

    # 2. Load strings, sorted by address
    strings = []
    with open(REPO / "analysis" / "installhook_strings_by_addr.txt") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            addr_hex, mangled = line.split("\t", 1)
            addr = int(addr_hex, 16)
            full = parse_mangled(mangled)
            strings.append((addr, full))
    strings.sort()
    str_count = len(strings)
    print(f"# {idx_count} registry entries; {str_count} typeinfo strings")

    # 3. Detect TU boundaries from address gaps
    tus = []
    cur = []
    for i, (addr, _) in enumerate(strings):
        if not cur:
            cur.append(i)
            continue
        prev_addr = strings[cur[-1]][0]
        gap = addr - prev_addr
        if gap >= TU_GAP_THRESHOLD:
            tus.append(cur)
            cur = [i]
        else:
            cur.append(i)
    if cur:
        tus.append(cur)
    print(f"# detected {len(tus)} TUs (gap threshold = 0x{TU_GAP_THRESHOLD:x})")

    # 4. Direct match: 1:1 by full name OR namespace-aware tail match
    str_full_to_indices = {}
    for i, (addr, full) in enumerate(strings):
        str_full_to_indices.setdefault(full, []).append(i)

    bare_to_indices = {}
    for i, (addr, full) in enumerate(strings):
        bare = full.split("::")[-1]
        bare_to_indices.setdefault(bare, []).append(i)

    matches = {}  # registry_idx -> (str_idx, name, "direct"/"hi"/"med"/"lo")
    ambiguous = []
    for r_idx, r_ti, r_name in registry:
        if not r_name:
            continue
        if r_name in str_full_to_indices and len(str_full_to_indices[r_name]) == 1:
            matches[r_idx] = (str_full_to_indices[r_name][0], r_name, "direct")
            continue
        bare = r_name.split("::")[-1]
        cands = bare_to_indices.get(bare, [])
        if "::" in r_name:
            cands = [c for c in cands if strings[c][1].endswith(r_name)]
        if len(cands) == 1:
            matches[r_idx] = (cands[0], strings[cands[0]][1], "direct")
        elif len(cands) > 1:
            ambiguous.append((r_idx, r_ti, r_name, cands))

    # 5. Resolve ambiguous via nearest-anchor address
    anchor_pairs = sorted(
        [(r_idx, strings[m[0]][0]) for r_idx, m in matches.items()]
    )

    def predict_addr_for_idx(r_idx):
        if not anchor_pairs:
            return None
        if r_idx <= anchor_pairs[0][0]:
            return anchor_pairs[0][1]
        if r_idx >= anchor_pairs[-1][0]:
            return anchor_pairs[-1][1]
        for i in range(len(anchor_pairs) - 1):
            lo, hi = anchor_pairs[i], anchor_pairs[i + 1]
            if lo[0] <= r_idx <= hi[0]:
                if hi[0] == lo[0]:
                    return lo[1]
                frac = (r_idx - lo[0]) / (hi[0] - lo[0])
                return int(lo[1] + frac * (hi[1] - lo[1]))
        return None

    for r_idx, r_ti, r_name, cands in ambiguous:
        predicted = predict_addr_for_idx(r_idx)
        if predicted is None:
            continue
        best = min(cands, key=lambda c: abs(strings[c][0] - predicted))
        matches[r_idx] = (best, strings[best][1], "direct")

    print(f"# direct matches: {len(matches)}")

    # 6. Re-anchor with all direct matches
    anchor_pairs = sorted(
        [(r_idx, strings[m[0]][0]) for r_idx, m in matches.items()]
    )

    # 7. Per-TU interpolation
    string_to_tu = {}
    for tu_id, str_indices in enumerate(tus):
        for si in str_indices:
            string_to_tu[si] = tu_id

    addr_to_str_idx = {strings[i][0]: i for i in range(len(strings))}
    claimed_strings = set(m[0] for m in matches.values())

    interp_added = 0
    interp_failed = 0
    for i in range(len(anchor_pairs) - 1):
        lo_idx, lo_addr = anchor_pairs[i]
        hi_idx, hi_addr = anchor_pairs[i + 1]
        if hi_idx - lo_idx <= 1:
            continue
        # Within-TU pattern: lo_addr > hi_addr (reverse order)
        if lo_addr <= hi_addr:
            interp_failed += 1
            continue
        lo_str_idx = addr_to_str_idx.get(lo_addr)
        hi_str_idx = addr_to_str_idx.get(hi_addr)
        if lo_str_idx is None or hi_str_idx is None:
            interp_failed += 1
            continue
        between = list(range(hi_str_idx + 1, lo_str_idx))
        if not between:
            continue
        tu_ids = set(string_to_tu[si] for si in between)
        if len(tu_ids) != 1:
            interp_failed += 1
            continue
        anchor_tu_lo = string_to_tu.get(lo_str_idx)
        anchor_tu_hi = string_to_tu.get(hi_str_idx)
        if anchor_tu_lo != anchor_tu_hi or anchor_tu_lo not in tu_ids:
            interp_failed += 1
            continue
        idx_gap = hi_idx - lo_idx - 1
        if idx_gap != len(between):
            interp_failed += 1
            continue
        # Reverse-walk: strings sorted by addr descending
        between.sort(key=lambda si: strings[si][0], reverse=True)
        for offset, si in enumerate(between):
            assigned_idx = lo_idx + offset + 1
            if si in claimed_strings or assigned_idx in matches:
                continue
            claimed_strings.add(si)
            dist = min(offset + 1, idx_gap - offset)
            if dist <= 5:
                conf = "hi"
            elif dist <= 50:
                conf = "med"
            else:
                conf = "lo"
            matches[assigned_idx] = (si, strings[si][1], conf)
            interp_added += 1

    print(f"# interpolation added {interp_added} indices; "
          f"{interp_failed} anchor pairs skipped (TU mismatch / count mismatch)")

    # 8. Build typeIndex → (name, conf)
    rows = []
    for r_idx, r_ti, r_name in registry:
        if r_idx in matches:
            _, name, conf = matches[r_idx]
            rows.append((r_ti, name, conf))
        elif r_name:
            rows.append((r_ti, r_name, "registry-only"))
        else:
            rows.append((r_ti, "(unclaimed)", "unclaimed"))
    rows.sort()
    seen = set()
    out_path = REPO / "analysis" / "typename_mapping.csv"
    with open(out_path, "w") as f:
        f.write("typeIndex,name,confidence\n")
        for ti, name, conf in rows:
            if ti in seen:
                continue
            seen.add(ti)
            if "," in name:
                name = f'"{name}"'
            f.write(f"{ti},{name},{conf}\n")
    print(f"# wrote {out_path} with {len(seen)} unique typeIndex rows")

    direct = sum(1 for m in matches.values() if m[2] == "direct")
    hi = sum(1 for m in matches.values() if m[2] == "hi")
    med = sum(1 for m in matches.values() if m[2] == "med")
    lo = sum(1 for m in matches.values() if m[2] == "lo")
    print(f"# all-types breakdown: direct={direct}, hi={hi}, med={med}, lo={lo}")

    # 9. Captured wire-types result
    captured_ids = [0x3, 0x8, 0x13, 0xa4, 0x14f, 0x15d, 0x1be, 0x40a,
                    0x5b2, 0x635, 0x651, 0x65c, 0x663, 0x66b, 0x8e6,
                    0x9d3, 0x9fc, 0xa95, 0xca4, 0xf7f, 0x101a, 0x101d,
                    0x102e, 0x102f, 0x1033, 0x1067, 0x1096, 0x1097,
                    0x1098, 0x10b0, 0x12f6, 0x136a, 0x143d, 0x16a0,
                    0x187c, 0x187f, 0x18a6, 0x192c, 0x1a59, 0x1b88]
    by_ti = {}
    for ti, name, conf in rows:
        if ti not in by_ti:
            by_ti[ti] = (name, conf)

    print("\n# captured wire-types result:")
    counters = {"direct": 0, "hi": 0, "med": 0, "lo": 0,
                "registry-only": 0, "unclaimed": 0, "missing": 0}
    for tid in captured_ids:
        info = by_ti.get(tid, ("(missing)", "missing"))
        name, conf = info
        short = name if len(name) < 75 else name[:72] + "..."
        print(f"  0x{tid:04x}  [{conf:>13}]  {short}")
        counters[conf] = counters.get(conf, 0) + 1
    print()
    for k, v in counters.items():
        if v:
            print(f"  captured {k}: {v}")


if __name__ == "__main__":
    main()
