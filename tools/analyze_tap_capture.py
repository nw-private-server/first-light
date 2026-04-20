"""
Summarize a New World tap capture produced by our packet hooks.

Input:
  capture/<session>/packets.jsonl

Purpose:
- classify DTLS record types
- count handshake message types
- confirm whether a session contains any plaintext non-DTLS datagrams
- give a quick offline summary before deeper parser work

Usage:
  python tools/analyze_tap_capture.py capture/20260416_231434_tap_test/packets.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


CONTENT_TYPES = {
    20: "change_cipher_spec",
    21: "alert",
    22: "handshake",
    23: "application_data",
    24: "heartbeat",
}

HANDSHAKE_TYPES = {
    0: "hello_request",
    1: "client_hello",
    2: "server_hello",
    3: "hello_verify_request",
    11: "certificate",
    12: "server_key_exchange",
    13: "certificate_request",
    14: "server_hello_done",
    15: "certificate_verify",
    16: "client_key_exchange",
    20: "finished",
}


def is_dtls_record(buf: bytes) -> bool:
    return len(buf) >= 13 and buf[0] in CONTENT_TYPES and buf[1] == 0xFE and buf[2] in (0xFD, 0xFF)


def iter_dtls_records(buf: bytes):
    off = 0
    while off + 13 <= len(buf):
        ctype = buf[off]
        ver1 = buf[off + 1]
        ver2 = buf[off + 2]
        if ctype not in CONTENT_TYPES or ver1 != 0xFE or ver2 not in (0xFD, 0xFF):
            break
        length = int.from_bytes(buf[off + 11:off + 13], "big")
        total = 13 + length
        if off + total > len(buf):
            break
        yield ctype, buf[off + 13:off + total]
        off += total


def summarize(path: Path) -> dict:
    total_packets = 0
    dtls_packets = 0
    non_dtls_packets = 0
    total_bytes = 0

    direction_counts = Counter()
    content_type_counts = Counter()
    handshake_counts = Counter()
    alert_counts = Counter()
    non_dtls_examples = []
    per_direction_ct = defaultdict(Counter)

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            total_packets += 1
            direction = obj.get("direction", "unknown")
            direction_counts[direction] += 1
            hh = obj.get("hexHead", "")
            if not hh:
                continue
            buf = bytes.fromhex(hh)
            total_bytes += obj.get("len", len(buf))

            if not is_dtls_record(buf):
                non_dtls_packets += 1
                if len(non_dtls_examples) < 20:
                    non_dtls_examples.append(
                        {
                            "seq": obj.get("seq"),
                            "direction": direction,
                            "len": obj.get("len"),
                            "hexHead": hh[:160],
                        }
                    )
                continue

            dtls_packets += 1
            for ctype, payload in iter_dtls_records(buf):
                name = CONTENT_TYPES.get(ctype, f"unknown_{ctype}")
                content_type_counts[name] += 1
                per_direction_ct[direction][name] += 1
                if ctype == 22 and payload:
                    htype = payload[0]
                    handshake_counts[HANDSHAKE_TYPES.get(htype, f"unknown_{htype}")] += 1
                elif ctype == 21 and len(payload) >= 2:
                    alert_counts[f"{payload[0]}/{payload[1]}"] += 1

    return {
        "path": str(path),
        "total_packets": total_packets,
        "total_bytes": total_bytes,
        "dtls_packets": dtls_packets,
        "non_dtls_packets": non_dtls_packets,
        "direction_counts": dict(direction_counts),
        "content_type_counts": dict(content_type_counts),
        "handshake_counts": dict(handshake_counts),
        "alert_counts": dict(alert_counts),
        "per_direction_ct": {k: dict(v) for k, v in per_direction_ct.items()},
        "non_dtls_examples": non_dtls_examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path, help="Path to packets.jsonl")
    args = parser.parse_args()

    summary = summarize(args.jsonl)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
