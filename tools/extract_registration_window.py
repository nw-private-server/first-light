"""
Extract the earliest DTLS application-data window around REP registration.

This uses:
- the PCAPNG DTLS timeline
- the matching Game.log milestones

Goal:
- identify the first server-side epoch-1 application-data burst most likely to
  contain the REP registration response payloads
- quantify sizes, ordering, and timing without decrypting anything

Usage:
  python tools/extract_registration_window.py ^
    capture/20260416_222545_second_capture/pcaps/capture.pcapng ^
    capture/20260416_222545_second_capture/logs/game_log_after.log
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from analyze_pcapng_dtls import CONTENT_TYPES, iter_pcapng_udp_payloads, parse_dtls_record_header
    from correlate_rep_timeline import parse_log_milestones
except ModuleNotFoundError:
    from tools.analyze_pcapng_dtls import CONTENT_TYPES, iter_pcapng_udp_payloads, parse_dtls_record_header
    from tools.correlate_rep_timeline import parse_log_milestones


def collect_records(pcap_path: Path) -> list[dict]:
    rows = []
    for parsed in iter_pcapng_udp_payloads(pcap_path):
        payload = parsed["payload"]
        off = 0
        while True:
            hdr = parse_dtls_record_header(payload, off)
            if hdr is None:
                break
            rows.append(
                {
                    "timestamp": parsed["timestamp"],
                    "timestamp_iso_utc": parsed["timestamp_iso_utc"],
                    "src": f"{parsed['src_ip']}:{parsed['src_port']}",
                    "dst": f"{parsed['dst_ip']}:{parsed['dst_port']}",
                    "content_type": CONTENT_TYPES.get(hdr["content_type"], f"unknown_{hdr['content_type']}"),
                    "epoch": hdr["epoch"],
                    "sequence_number": hdr["sequence_number"],
                    "length": hdr["length"],
                }
            )
            off += hdr["total_len"]
    return rows


def extract_window(pcap_path: Path, log_path: Path, server_records: int, client_records: int) -> dict:
    log = parse_log_milestones(log_path)
    rows = collect_records(pcap_path)

    first_server_app = None
    for row in rows:
        if row["content_type"] == "application_data" and row["epoch"] == 1 and row["dst"].endswith(":27000"):
            first_server_app = row
            break

    if first_server_app is None:
        return {"error": "no server epoch-1 application-data record found"}

    server_window = []
    client_window = []
    started = False
    for row in rows:
        if row is first_server_app:
            started = True
        if not started:
            continue
        if row["content_type"] != "application_data" or row["epoch"] != 1:
            continue
        if row["dst"].endswith(":27000") and len(server_window) < server_records:
            server_window.append(row)
        elif row["src"].endswith(":27000") and len(client_window) < client_records:
            client_window.append(row)
        if len(server_window) >= server_records and len(client_window) >= client_records:
            break

    return {
        "pcap": str(pcap_path),
        "game_log": str(log_path),
        "log_milestones": log,
        "first_server_application_data": first_server_app,
        "server_window": server_window,
        "client_window": client_window,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcapng", type=Path)
    parser.add_argument("game_log", type=Path)
    parser.add_argument("--server-records", type=int, default=12)
    parser.add_argument("--client-records", type=int, default=12)
    args = parser.parse_args()
    print(json.dumps(extract_window(args.pcapng, args.game_log, args.server_records, args.client_records), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
