"""Wake 95: bulk-extract type names from InstallRegistrationHook<T>
typeinfo strings, anchored by named registry entries.

Inputs:
  - info/typeregistry.json (registry: 3487 entries with index, typeIndex, name)
  - analysis/installhook_strings_by_addr.txt (3482 (addr, mangled) pairs)

Output:
  - analysis/typename_mapping.csv (typeIndex, name, source)
"""
import json
import re
import sys
from pathlib import Path


def parse_mangled(mangled):
    """Extract the C++ namespace path from a mangled InstallRegistrationHook
    name. The MSVC encoding is class@namespace1@namespace2@... reading
    inside-out, so we reverse the path components for canonical "::" form.

    Example: 'State@ClientActorRoutingAuthorizationTrait' →
             'ClientActorRoutingAuthorizationTrait::State'
    """
    parts = mangled.split("@")
    return "::".join(reversed(parts))


def main():
    repo = Path(__file__).resolve().parent.parent / "Programs" / "NewWorldFirstLight"
    if not repo.exists():
        repo = Path("/Users/junichi/Programs/NewWorldFirstLight")

    # Load registry
    with open(repo / "info" / "typeregistry.json") as f:
        data = json.load(f)
    registry = []  # list of (index, typeIndex, name)
    for entry in data["data"]["m_list"]:
        if isinstance(entry, list) and len(entry) >= 2:
            d = entry[1]
            idx = d.get("index")
            ti = d.get("typeIndex")
            nm = d.get("name", "") or ""
            if idx is not None and ti is not None:
                registry.append((idx, ti, nm))
    registry.sort()

    # Load strings
    strings = []  # list of (addr, full_path_name, raw_mangled)
    with open(repo / "analysis" / "installhook_strings_by_addr.txt") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            addr_hex, mangled = line.split("\t", 1)
            addr = int(addr_hex, 16)
            full = parse_mangled(mangled)
            strings.append((addr, full, mangled))
    strings.sort()  # sort by address ascending

    print(f"# {len(registry)} registry entries; {len(strings)} typeinfo strings")

    # Step 1: match named registry entries against strings using
    # namespace-aware tail matching.
    named_entries = [(i, ti, n) for i, ti, n in registry if n]
    print(f"# {len(named_entries)} named registry entries")

    # Build candidate index: bare-name (last :: component) → list of
    # (idx_in_strings, full_name)
    bare_to_idxs = {}
    for i, (addr, full, mangled) in enumerate(strings):
        bare = full.split("::")[-1]
        bare_to_idxs.setdefault(bare, []).append(i)

    matches = []  # (registry_idx, registry_ti, registry_name, strings_idx, addr)
    ambiguous = []
    unmatched = []

    for r_idx, r_ti, r_name in named_entries:
        # Try exact full-name match first
        full_match = [(i, addr) for i, (addr, full, _) in enumerate(strings)
                      if full == r_name]
        if len(full_match) == 1:
            matches.append((r_idx, r_ti, r_name, full_match[0][0], full_match[0][1]))
            continue
        # Try bare-name match (last component of registry name)
        registry_bare = r_name.split("::")[-1]
        candidates = bare_to_idxs.get(registry_bare, [])
        # Also filter to strings whose full path ENDS with registry_name
        if "::" in r_name:
            # registry name like "ClientActorRoutingAuthorizationTrait::State"
            # should match strings whose full ends with this
            candidates = [c for c in candidates
                          if strings[c][1].endswith(r_name)]
        if len(candidates) == 1:
            i = candidates[0]
            matches.append((r_idx, r_ti, r_name, i, strings[i][0]))
        elif len(candidates) > 1:
            ambiguous.append((r_idx, r_ti, r_name, candidates))
        else:
            unmatched.append((r_idx, r_ti, r_name))

    print(f"# matched: {len(matches)}; ambiguous: {len(ambiguous)}; unmatched: {len(unmatched)}")

    # For ambiguous cases: pick the one with the closest neighbor anchor.
    # Build a sorted list of (registry_idx, addr) anchors so far.
    anchors = sorted([(r_idx, addr) for r_idx, _, _, _, addr in matches])

    def predict_addr(r_idx):
        """Given a registry index, predict its expected address based on
        anchors. Use linear interpolation between bracketing anchors."""
        if not anchors:
            return None
        # Find bracketing anchors
        for i in range(len(anchors) - 1):
            if anchors[i][0] <= r_idx <= anchors[i + 1][0]:
                # Linear interpolate
                low_i, low_a = anchors[i]
                hi_i, hi_a = anchors[i + 1]
                if hi_i == low_i:
                    return low_a
                frac = (r_idx - low_i) / (hi_i - low_i)
                return int(low_a + frac * (hi_a - low_a))
        # Outside anchor range: use nearest
        if r_idx < anchors[0][0]:
            return anchors[0][1]
        return anchors[-1][1]

    resolved_ambiguous = []
    for r_idx, r_ti, r_name, candidates in ambiguous:
        predicted = predict_addr(r_idx)
        if predicted is None:
            unmatched.append((r_idx, r_ti, r_name))
            continue
        # Pick the candidate with closest address
        best = min(candidates,
                   key=lambda c: abs(strings[c][0] - predicted))
        resolved_ambiguous.append(
            (r_idx, r_ti, r_name, best, strings[best][0])
        )
    matches.extend(resolved_ambiguous)
    matches.sort()

    print(f"# after ambiguous resolution: {len(matches)} matched")
    print(f"# remaining unmatched: {len(unmatched)}")

    # Step 2: interpolate unmatched indices using anchors.
    # For each unmatched (or unnamed) registry entry, find the bracketing
    # anchors and assign the string at the interpolated position.
    # Use REVERSE within-TU pattern: as registry_index increases by 1,
    # address typically decreases.

    # Build index → (addr, full_name) map for matched
    matched_by_idx = {m[0]: (m[3], m[4]) for m in matches}  # idx → (str_idx, addr)

    # Build set of strings already claimed
    claimed = set(m[3] for m in matches)
    available = [(addr, full, i) for i, (addr, full, _) in enumerate(strings)
                 if i not in claimed]

    # For each unnamed registry entry, find a string for it using
    # nearest-neighbor in the anchor map, walking strings in
    # registration-index order
    final_mapping = {}  # registry_index → (typeIndex, name, source)
    for r_idx, r_ti, r_name in registry:
        if r_idx in matched_by_idx:
            str_idx, addr = matched_by_idx[r_idx]
            full = strings[str_idx][1]
            final_mapping[r_idx] = (r_ti, full, "matched")
        elif r_name:
            # named but unmatched (shouldn't happen but record)
            final_mapping[r_idx] = (r_ti, r_name, "registry-only")
        else:
            # unnamed registry entry — try to interpolate
            # For now, mark as unknown but record anchors nearby
            predicted = predict_addr(r_idx)
            # Find closest available string to predicted addr
            if predicted is not None and available:
                best_match = min(available,
                                 key=lambda x: abs(x[0] - predicted))
                # Heuristic guard: only assign if reasonably close
                # (within some distance threshold proportional to local density)
                # Actually for now just assign and accept some noise
                final_mapping[r_idx] = (r_ti, best_match[1], "interpolated")
                # Don't actually consume — many indices may interpolate
                # to overlapping strings and that's an honest signal
            else:
                final_mapping[r_idx] = (r_ti, "(unknown)", "no-anchor")

    # Output CSV: typeIndex,name,source
    out_path = repo / "analysis" / "typename_mapping.csv"
    with open(out_path, "w") as f:
        f.write("typeIndex,name,source\n")
        # Sort by typeIndex for easy lookup
        rows = sorted(
            [(ti, name, src) for r_idx, (ti, name, src) in final_mapping.items()],
            key=lambda r: r[0],
        )
        # Deduplicate by typeIndex (keep first)
        seen = set()
        for ti, name, src in rows:
            if ti in seen:
                continue
            seen.add(ti)
            # Quote name if it has a comma (shouldn't, but safety)
            if "," in name:
                name = f'"{name}"'
            f.write(f"{ti},{name},{src}\n")

    print(f"\n# Wrote {out_path}")
    print(f"# Total unique typeIndex entries: {len(seen)}")

    # Show captured wire-types specifically
    captured_ids = [0x3, 0x8, 0x13, 0xa4, 0x14f, 0x15d, 0x1be, 0x40a,
                    0x5b2, 0x635, 0x651, 0x65c, 0x663, 0x66b, 0x8e6,
                    0x9d3, 0x9fc, 0xa95, 0xca4, 0xf7f, 0x101a, 0x101d,
                    0x102e, 0x102f, 0x1033, 0x1067, 0x1096, 0x1097,
                    0x1098, 0x10b0, 0x12f6, 0x136a, 0x143d, 0x16a0,
                    0x187c, 0x187f, 0x18a6, 0x192c, 0x1a59, 0x1b88]

    by_ti = {}
    for r_idx, (ti, name, src) in final_mapping.items():
        if ti not in by_ti:
            by_ti[ti] = (name, src)

    print("\n# Captured wire-types with names:")
    print("typeIndex\twire\tname\tsource")
    for tid in captured_ids:
        if tid in by_ti:
            name, src = by_ti[tid]
            # Trim long names
            short = name if len(name) < 80 else name[:77] + "..."
            print(f"  {tid}\t0x{tid:04x}\t{short}\t{src}")
        else:
            print(f"  {tid}\t0x{tid:04x}\t(missing)\t-")


if __name__ == "__main__":
    main()
