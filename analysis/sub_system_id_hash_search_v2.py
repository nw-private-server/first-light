"""Wake 155 — extended sub_system_id hash hunt (v2).

Re-run of the wake-122 search with xxhash + mmh3 + a CRC-64-ECMA
variant added on top of the wake-122 set (FNV-1a-64, SHA-1, SHA-
256, MD5, double-CRC32). Goal: produce a definitive yes/no on
whether any of the named registry entries hashes to any of the
11 captured sub_system_ids under any of the standard 64-bit
hash families.

Run from repo root with the project venv:
    .venv/bin/python3 analysis/sub_system_id_hash_search_v2.py
"""

from __future__ import annotations

import json
import hashlib
import zlib
import sys
from pathlib import Path

try:
    import xxhash
    import mmh3
except ImportError as e:
    print(f"missing dep: {e}; run `pip install xxhash mmh3`", file=sys.stderr)
    sys.exit(1)


REPO = Path(__file__).resolve().parents[1]


# 11 captured sub_system_ids from wake 121
TARGETS = {
    bytes.fromhex(h)
    for h in [
        "16009918b041c1f9",
        "180f8d4e573697c6",
        "288c27b1a6be71cc",
        "4c0c0ed6478a69da",
        "93a3e477cb5fd51e",
        "95a5a80aa54288d1",
        "9e921a154971f6b7",
        "ce81136a2b7ad33e",
        "d1a94ccc870660b0",
        "db84a5d631d9b33a",
        "f8cbed57c68b18f4",
        "fbde4b9a600d428f",
    ]
}


# CRC-64-ECMA polynomial 0xc96c5795d7870f42 (reversed of standard
# 0x42f0e1eba9ea3693). Standard table-based implementation; simplest
# AzCore-flavored 64-bit hash without pulling in a CRC dependency.
CRC64_POLY = 0xc96c5795d7870f42


def _crc64_table():
    table = []
    for byte in range(256):
        c = byte
        for _ in range(8):
            c = (c >> 1) ^ (CRC64_POLY if (c & 1) else 0)
        table.append(c)
    return table


_CRC64_TABLE = _crc64_table()


def crc64_ecma(buf: bytes) -> int:
    crc = 0xFFFFFFFFFFFFFFFF
    for b in buf:
        crc = (crc >> 8) ^ _CRC64_TABLE[(crc ^ b) & 0xFF]
    return (crc ^ 0xFFFFFFFFFFFFFFFF) & 0xFFFFFFFFFFFFFFFF


def hash_variants(s: bytes) -> dict:
    """Compute every 64-bit hash variant for one byte-input."""
    out = {}
    # FNV-1a-64
    fnv = 0xcbf29ce484222325
    for b in s:
        fnv = ((fnv ^ b) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    out["fnv1a64"] = fnv.to_bytes(8, "big")
    # SHA / MD5 (wake-122 set; included for replay)
    h_sha1 = hashlib.sha1(s).digest()
    out["sha1_first8"] = h_sha1[:8]
    out["sha1_last8"] = h_sha1[-8:]
    out["sha256_first8"] = hashlib.sha256(s).digest()[:8]
    out["md5_first8"] = hashlib.md5(s).digest()[:8]
    out["md5_last8"] = hashlib.md5(s).digest()[-8:]
    # double-CRC32 (forward, reversed)
    fwd = zlib.crc32(s) & 0xFFFFFFFF
    rev = zlib.crc32(s[::-1]) & 0xFFFFFFFF
    out["crc32_dbl"] = (fwd << 32 | rev).to_bytes(8, "big")
    # ---- v2 additions ----
    out["xxh3_64"] = xxhash.xxh3_64(s).digest()
    out["xxh64"] = xxhash.xxh64(s).digest()
    mh = mmh3.hash64(s)  # returns (low, high), each signed 64-bit
    out["mmh3_64_lo"] = (mh[0] & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "big")
    out["mmh3_64_hi"] = (mh[1] & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "big")
    out["mmh3_128_first8"] = mmh3.hash_bytes(s)[:8]
    out["crc64_ecma"] = crc64_ecma(s).to_bytes(8, "big")
    return out


def permutations(name: str) -> list[bytes]:
    """8 string-encoding permutations to try per name."""
    leaf = name.rsplit("::", 1)[-1]
    nows = name.replace(" ", "").replace("\t", "")
    return [
        name.encode(),
        name.lower().encode(),
        name.upper().encode(),
        leaf.encode(),
        leaf.lower().encode(),
        nows.lower().encode(),
        ("Javelin::" + leaf).encode(),
        ("Javelin::ClientMessagesTrait::" + leaf).encode(),
    ]


def main() -> int:
    reg_path = REPO / "info" / "typeregistry.json"
    with reg_path.open() as f:
        reg = json.load(f)

    data = reg.get("data", reg)
    names = []
    uuids = []
    for pair in data.get("m_list", []):
        if not (isinstance(pair, list) and len(pair) == 2):
            continue
        u, entry = pair
        if isinstance(entry, dict) and entry.get("name"):
            names.append(entry["name"])
        if isinstance(u, str):
            uuids.append(u)
    # Also include the m_vector UUID list (3487 entries, often
    # broader than m_list which holds the populated entries).
    for u in data.get("m_vector", []):
        if isinstance(u, str):
            uuids.append(u)
    # De-dupe while preserving order
    seen = set()
    uuids = [u for u in uuids if not (u in seen or seen.add(u))]

    print(f"loaded {len(names)} named entries, {len(uuids)} uuids")

    # Build byte-input set: all 8 permutations of every name +
    # raw bytes of every uuid (as ASCII string and as parsed bytes).
    inputs = []
    for n in names:
        for p in permutations(n):
            inputs.append((f"name[{n}]:{p[:30]!r}", p))
    for u in uuids:
        u_clean = u.replace("-", "").replace("{", "").replace("}", "")
        try:
            inputs.append((f"uuid[{u}]:bytes", bytes.fromhex(u_clean)))
        except ValueError:
            pass
        inputs.append((f"uuid[{u}]:str", u.encode()))

    print(f"trying {len(inputs)} byte-inputs × 13 hashes × 2 byte-orders")

    matches = []
    checked = 0
    for label, b in inputs:
        variants = hash_variants(b)
        for vname, hbytes in variants.items():
            for order in ("BE", "LE"):
                v = hbytes if order == "BE" else hbytes[::-1]
                checked += 1
                if v in TARGETS:
                    matches.append((label, vname, order, v.hex()))
        # short-circuit print every 100k
        if checked % 200000 == 0:
            print(f"  … checked {checked:,} hashes, {len(matches)} matches so far")

    print(f"\ntotal hash invocations checked: {checked:,}")
    print(f"matches: {len(matches)}")
    if matches:
        print("---")
        for m in matches[:50]:
            print("  match:", m)
    return 0 if not matches else 0


if __name__ == "__main__":
    sys.exit(main())
