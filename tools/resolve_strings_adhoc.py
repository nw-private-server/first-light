"""Grep NewWorld.exe for enum-value string prefixes matching the fields
we need (WorldStatus, PublicStatusCode, WorldPopulationStatus). Javelin's
convention is ePascalCase_Value. Report each hit with address + value."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from resolve_strings import parse_pe_sections, read_cstring, EXE

PREFIXES = [
    "eWorldType_",
    "eWorldStatus_",
    "ePublicStatusCode_",
    "eWorldPopulationStatus_",
    "ePopulationStatus_",
    "eStatus_",
    "eTransferReason_",  # known, sanity check
]


def find_string_va(data, pattern_bytes, image_base, sections):
    hits = []
    pos = 0
    while True:
        idx = data.find(pattern_bytes, pos)
        if idx < 0:
            break
        # Map file offset -> RVA -> VA via sections
        va = None
        for s in sections:
            if s["rp"] <= idx < s["rp"] + s["rs"]:
                va = image_base + s["va"] + (idx - s["rp"])
                break
        if va is not None:
            hits.append((va, idx))
        pos = idx + 1
    return hits


def main():
    data = EXE.read_bytes()
    image_base, sections = parse_pe_sections(data)

    for prefix in PREFIXES:
        pattern = prefix.encode("ascii")
        hits = find_string_va(data, pattern, image_base, sections)
        print(f"=== {prefix} ({len(hits)} hit(s)) ===")
        seen_values = set()
        # Loosen: print even if not at string start (to catch substrings of
        # longer enum names), so we don't silently drop values.
        for va, off in hits:
            is_start = off == 0 or data[off - 1] == 0
            s = read_cstring(data, off, 128)
            if s in seen_values:
                continue
            seen_values.add(s)
            marker = "" if is_start else "  (substr)"
            print(f"  0x{va:x}  {s!r}{marker}")
        print()


if __name__ == "__main__":
    main()
