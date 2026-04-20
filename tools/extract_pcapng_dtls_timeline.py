"""
Extract a DTLS record-level timeline from a PCAPNG capture.

Purpose:
- make the handshake -> CCS -> encrypted-data transition explicit
- show epochs and sequence numbers on each side
- identify the first encrypted records after CCS without external tooling

Usage:
  python tools/extract_pcapng_dtls_timeline.py capture/20260416_222545_second_capture/pcaps/capture.pcapng --limit 40
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from analyze_pcapng_dtls import CONTENT_TYPES, HANDSHAKE_TYPES, iter_pcapng_udp_payloads, parse_dtls_record_header
except ModuleNotFoundError:
    from tools.analyze_pcapng_dtls import CONTENT_TYPES, HANDSHAKE_TYPES, iter_pcapng_udp_payloads, parse_dtls_record_header


def extract(path: Path, limit: int, after_ccs_only: bool) -> list[dict]:
    rows = []
    seen_ccs = set()

    for parsed in iter_pcapng_udp_payloads(path):
        payload = parsed["payload"]
        off = 0
        while True:
            hdr = parse_dtls_record_header(payload, off)
            if hdr is None:
                break

            body_start = off + hdr["header_len"]
            body_end = off + hdr["total_len"]
            body = payload[body_start:body_end]
            direction = f"{parsed['src_ip']}:{parsed['src_port']} -> {parsed['dst_ip']}:{parsed['dst_port']}"
            ctype_name = CONTENT_TYPES.get(hdr["content_type"], f"unknown_{hdr['content_type']}")

            if hdr["content_type"] == 20:
                seen_ccs.add(direction)

            if not after_ccs_only or direction in seen_ccs:
                row = {
                    "direction": direction,
                    "content_type": ctype_name,
                    "record_version": hdr["record_version"],
                    "epoch": hdr["epoch"],
                    "sequence_number": hdr["sequence_number"],
                    "length": hdr["length"],
                }
                if hdr["content_type"] == 22 and body:
                    row["handshake_type"] = HANDSHAKE_TYPES.get(body[0], f"unknown_{body[0]}")
                rows.append(row)
                if len(rows) >= limit:
                    return rows

            off += hdr["total_len"]

    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcapng", type=Path)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--after-ccs-only", action="store_true", help="Only show records after each side's first ChangeCipherSpec")
    args = parser.parse_args()
    print(json.dumps(extract(args.pcapng, args.limit, args.after_ccs_only), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
