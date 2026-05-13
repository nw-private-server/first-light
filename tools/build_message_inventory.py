#!/usr/bin/env python3
"""Build analysis/message_inventory.md from binary RE outputs.

Inputs:
  - A ``FindStringXrefs InstallRegistrationHook ...`` output file
    (the script in tools/ghidra_scripts/). Defaults to
    ``/tmp/all_install_hooks.txt``.
  - ``info/typeregistry.json`` — runtime-extracted type registry.

Output: ``analysis/message_inventory.md`` — a comprehensive catalog of
every ``InstallRegistrationHook<T>`` template instantiation in the
binary, grouped by namespace and topically bucketed, cross-referenced
with the typeregistry where coverage exists.

Run after refreshing either input. Intended as the single source of
truth for "what messages does this binary know about?" — far broader
than the older ``analysis/javelin_chunks.txt`` (2 components) and
``analysis/chunk_names.txt`` (17 chunk names).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Topical buckets for the index. Order of namespaces within each bucket
# matters for readability; ordering of buckets is roughly priority for
# this project (connection/lifecycle first, then gameplay etc.).
BUCKETS = {
    "Connection / lifecycle (project-relevant)": [
        "Javelin::ClientMessagesTrait",
        "Aoi::PlayerManagerTrait",
        "Amazon::Hub",
        "Amazon::Hub::HubLifecyclePeeringTrait",
        "Amazon::Hub::HubLifecycleStateListenerTrait",
        "Amazon::Hub::HubEndpointSharingTrait",
        "Amazon::Hub::HubLifecycleStateRequestTrait",
        "Amazon::Hub::HubReconnectListener",
        "Amazon::Hub::HubIdDebugTrait",
        "Aoi::PhasingGridCoordinatorTrait",
    ],
    "Component facets (gameplay messages — bulk of catalog)": [
        "Javelin::ClientMessages",
    ],
    "Replicated state": [
        "MB",
        "MB::ServerContext",
    ],
    "Movement / physics": [
        "ActorMover",
        "Aoi::PhysicsTrait",
    ],
    "World / dungeons / events": [
        "Javelin::DungeonMasterTrait",
        "Javelin::WorldEventCoordinatorTrait",
        "Aoi::BaseQueryTrait",
        "Aoi::GhostExTrait",
        "OrchestrationTrait",
    ],
    "Chat / character / players": [
        "ChatBroker",
        "Javelin::CharacterServiceProxyTrait",
        "Javelin::PlayerPresenceTrackingTrait",
    ],
    "IPC / infrastructure": [
        "Amazon::IPC",
    ],
    "Other (Javelin top-level)": [
        "Javelin",
    ],
}

MANGLED_PATTERN = re.compile(r"InstallRegistrationHook@V(\w+)@([\w@]+?)@@")


def parse_install_hook_strings(src: str) -> dict[str, list[str]]:
    """Return {namespace: [type, ...]} from FindStringXrefs raw output."""
    by_ns: dict[str, list[str]] = defaultdict(list)
    for type_name, ns_chain in MANGLED_PATTERN.findall(src):
        # MSVC reverse-mangles namespaces: A@B@C@@ means C::B::A
        parts = [p for p in ns_chain.split("@") if p]
        canonical = "::".join(reversed(parts))
        by_ns[canonical].append(type_name)
    for ns in by_ns:
        by_ns[ns] = sorted(set(by_ns[ns]))
    return dict(by_ns)


def load_typeregistry_names(path: Path) -> set[str]:
    """Return the set of named types from info/typeregistry.json."""
    data = json.loads(path.read_text())
    names: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            n = node.get("name")
            if isinstance(n, str) and n:
                names.add(n)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return names


def emit(by_ns: dict[str, list[str]], known_typeids: set[str], out: Path):
    total_msgs = sum(len(v) for v in by_ns.values())
    total_in_reg = sum(
        1 for ns in by_ns for t in by_ns[ns] if t in known_typeids
    )
    pct = 100 * total_in_reg // total_msgs if total_msgs else 0

    with out.open("w") as f:
        f.write("# Javelin Message Inventory\n\n")
        f.write(
            "> Comprehensive catalog of all `InstallRegistrationHook<T>` template\n"
            "> instantiations recovered from the binary by static-RE. Each entry\n"
            "> represents a typed message class registered with the dispatch\n"
            "> system. Sourced from `tools/ghidra_scripts/FindStringXrefs.py`\n"
            f"> against the `\"InstallRegistrationHook\"` literal — total {total_msgs}\n"
            f"> unique (namespace, type) pairs across {len(by_ns)} namespaces.\n"
            ">\n"
            "> Cross-referenced where possible with `info/typeregistry.json` (a\n"
            "> runtime-extracted type registry; 312 named types with handler\n"
            "> data). Types marked **(R)** appear in typeregistry — useful when\n"
            "> looking up serialization metadata.\n"
            ">\n"
            "> The project's pre-existing `analysis/javelin_chunks.txt` cataloged\n"
            "> 2 components and `analysis/chunk_names.txt` cataloged 17 chunk\n"
            "> names. This inventory is two orders of magnitude broader.\n\n"
        )

        f.write("## Index by topical bucket\n\n")
        for bucket, namespaces in BUCKETS.items():
            f.write(f"### {bucket}\n\n")
            for ns in namespaces:
                types = by_ns.get(ns, [])
                if not types:
                    continue
                in_reg = sum(1 for t in types if t in known_typeids)
                f.write(
                    f"- **{ns}** — {len(types)} messages  "
                    f"({in_reg} in typeregistry)\n"
                )
            f.write("\n")

        f.write("---\n\n")
        f.write("## Full namespace listing\n\n")
        f.write(
            "Sorted by message count, descending. Type names are the C++ class\n"
            "names as recovered from the mangled `InstallRegistrationHook<T>` RTTI.\n"
            "A type name marked **(R)** has full handler metadata in\n"
            "`info/typeregistry.json`.\n\n"
        )

        for ns, types in sorted(
            by_ns.items(), key=lambda kv: (-len(kv[1]), kv[0])
        ):
            in_reg = sum(1 for t in types if t in known_typeids)
            f.write(
                f"### `{ns}` — {len(types)} messages  "
                f"({in_reg} in typeregistry)\n\n"
            )
            for t in types:
                marker = " **(R)**" if t in known_typeids else ""
                f.write(f"- `{t}`{marker}\n")
            f.write("\n")

        f.write("---\n\n")
        f.write(f"**Total:** {total_msgs} messages across {len(by_ns)} namespaces.\n")
        f.write(
            f"**typeregistry coverage:** {total_in_reg} of {total_msgs} ({pct}%).\n\n"
        )
        f.write(
            "Generated by `tools/build_message_inventory.py`. To regenerate:\n\n"
            "```bash\n"
            "ghidra script FindStringXrefs InstallRegistrationHook /tmp/all_install_hooks.txt\n"
            "python3 tools/build_message_inventory.py\n"
            "```\n"
        )


def main() -> int:
    here = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser()
    p.add_argument(
        "--hooks",
        type=Path,
        default=Path("/tmp/all_install_hooks.txt"),
        help="FindStringXrefs InstallRegistrationHook output file",
    )
    p.add_argument(
        "--typeregistry",
        type=Path,
        default=here / "info" / "typeregistry.json",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=here / "analysis" / "message_inventory.md",
    )
    args = p.parse_args()

    if not args.hooks.exists():
        print(f"missing {args.hooks}", file=sys.stderr)
        print(
            "regenerate with: ghidra script FindStringXrefs InstallRegistrationHook /tmp/all_install_hooks.txt",
            file=sys.stderr,
        )
        return 1

    by_ns = parse_install_hook_strings(args.hooks.read_text())
    known = load_typeregistry_names(args.typeregistry)
    emit(by_ns, known, args.out)
    print(f"wrote {args.out} ({sum(len(v) for v in by_ns.values())} messages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
