"""Diff observed wire types in a capture against info/typeregistry.json.

Usage:
    python tools/typeregistry_diff.py [<capture_dir>] [--registry <path>]

`<capture_dir>` defaults to info/nw-login-safe-20260502-153840/ and must contain
a `messages-redacted.txt` file in the format produced by the capture tooling
(blocks of `seq: 0xNN (N)` / `direction: R|W` / `type: 0xNN (N)` / `size: N`).

Prints, in order:
  1. summary counts (records, distinct types, named/anonymous split)
  2. per-direction breakdown of every observed type (named first)
  3. named types in the registry that are NOT in the capture, grouped by
     coarse name-pattern category — useful to spot what the in-world phase
     would add (movement, actor, combat, ...).
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys


CAP_RE = re.compile(
    r"^seq: (0x[0-9a-fA-F]+) \((\d+)\)\s*\n"
    r"direction: ([RW])\s*\n"
    r"type: (0x[0-9a-fA-F]+) \((\d+)\)\s*\n"
    r"size: (\d+)",
    re.MULTILINE,
)


def load_registry(path: pathlib.Path) -> dict[int, str]:
    data = json.loads(path.read_text())
    out: dict[int, str] = {}
    for _uuid, body in data["data"]["m_list"]:
        ti = body.get("typeIndex")
        name = body.get("name") or ""
        if ti is None or not name:
            continue
        out.setdefault(ti, name)
    return out


def parse_capture(path: pathlib.Path):
    text = path.read_text()
    records = []
    for m in CAP_RE.finditer(text):
        records.append({
            "seq": int(m.group(2)),
            "dir": m.group(3),
            "type": int(m.group(5)),
            "size": int(m.group(6)),
        })
    return records


def categorize(name: str) -> str:
    n = name.lower()
    rules = [
        ("world/actor", ("spawn", "actor")),
        ("movement", ("movement", "transform", "position")),
        ("combat", ("combat", "damage", "attack", "ability")),
        ("inventory", ("inventory", "item", "equipment", "loot")),
        ("chat/persistence", ("chat", "persistence", "customizeddata")),
        ("territory/zone", ("territory", "zone", "region", "world", "crossworld")),
        ("quest", ("quest", "task", "objective")),
        ("social", ("group", "party", "guild", "company")),
        ("economy", ("auction", "trade", "shop", "market")),
        ("auth/session", ("login", "register", "auth", "session", "fragmentaccess")),
        ("keepalive", ("ping", "timesync", "sendclock", "heartbeat", "timeout")),
    ]
    for cat, kws in rules:
        if any(k in n for k in kws):
            return cat
    if "rpc" in n or "request" in n or "response" in n:
        return "rpc"
    if "msg" in n:
        return "misc-msg"
    return "other"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("capture_dir", nargs="?",
                   default="info/nw-login-safe-20260502-153840")
    p.add_argument("--registry", default="info/typeregistry.json")
    args = p.parse_args(argv)

    cap_path = pathlib.Path(args.capture_dir) / "messages-redacted.txt"
    reg_path = pathlib.Path(args.registry)

    if not cap_path.exists():
        print(f"capture not found: {cap_path}", file=sys.stderr)
        return 2
    if not reg_path.exists():
        print(f"registry not found: {reg_path}", file=sys.stderr)
        return 2

    ti_to_name = load_registry(reg_path)
    records = parse_capture(cap_path)

    by_type = collections.defaultdict(lambda: {"R": 0, "W": 0, "sizes": []})
    for r in records:
        bt = by_type[r["type"]]
        bt[r["dir"]] += 1
        bt["sizes"].append(r["size"])

    observed = set(by_type)
    named = set(ti_to_name)

    print(f"Capture: {cap_path}")
    print(f"Registry: {reg_path}")
    print(f"Records: {len(records)}  (R={sum(1 for r in records if r['dir']=='R')}"
          f"  W={sum(1 for r in records if r['dir']=='W')})")
    print(f"Distinct types observed: {len(observed)}")
    print(f"  named in registry:     {len(observed & named)}")
    print(f"  anonymous in registry: {len(observed - named)}")
    print(f"Named types in registry: {len(named)}  "
          f"(observed: {len(observed & named)}, unobserved: {len(named - observed)})")
    print()

    print("=== Observed types (named first, then anonymous, by total count) ===")
    items = sorted(by_type.items(),
                   key=lambda kv: (kv[0] not in named, -(kv[1]["R"] + kv[1]["W"])))
    for t, info in items:
        sizes = info["sizes"]
        median = sorted(sizes)[len(sizes) // 2]
        flag = "named" if t in named else "anon "
        name = ti_to_name.get(t, "")
        print(f"  [{flag}] 0x{t:04x} ({t:5d})  R={info['R']:3d} W={info['W']:3d}"
              f"  min={min(sizes):5d} max={max(sizes):6d} med={median:5d}  {name}")
    print()

    print("=== Named types NOT observed (potential in-world / RPC gaps) ===")
    unobs = sorted(named - observed)
    bycat: dict[str, list[tuple[int, str]]] = collections.defaultdict(list)
    for t in unobs:
        bycat[categorize(ti_to_name[t])].append((t, ti_to_name[t]))
    for cat, lst in sorted(bycat.items()):
        print(f"\n--- {cat}  ({len(lst)} types) ---")
        for t, n in sorted(lst):
            print(f"  0x{t:04x} ({t:5d})  {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
