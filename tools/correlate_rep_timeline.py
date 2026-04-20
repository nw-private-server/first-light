"""
Correlate REP/DTLS capture milestones with Game.log milestones.

Inputs:
- a real DTLS pcapng capture
- the matching game_log_after.log

Outputs:
- the key GameConnection state-transition times
- the key DTLS milestones
- relative offsets from StartREPConnection

Usage:
  python tools/correlate_rep_timeline.py ^
    capture/20260416_222545_second_capture/pcaps/capture.pcapng ^
    capture/20260416_222545_second_capture/logs/game_log_after.log
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

try:
    from analyze_pcapng_dtls import iter_pcapng_udp_payloads, parse_dtls_record_header, CONTENT_TYPES, HANDSHAKE_TYPES
except ModuleNotFoundError:
    from tools.analyze_pcapng_dtls import iter_pcapng_udp_payloads, parse_dtls_record_header, CONTENT_TYPES, HANDSHAKE_TYPES


LOG_PATTERNS = {
    "start_rep": "GameConnectionWrapper: start REP connection",
    "rep_established": "REP socket connection established",
    "registration_response": "received registration response from REP",
    "start_actor_connection": "start actor game connection",
    "actor_connection_succeeds": "actor game connection succeeds",
    "spawn_point_found": "spawn point found",
    "player_spawn_succeeds": "player spawn succeeds, in game",
}


LOG_RE = re.compile(r"<(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2}\.\d{3})>:")


def parse_log_milestones(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LOG_RE.search(line)
        if not m:
            continue
        ts = f"{m.group('date')}T{m.group('time')}"
        for key, needle in LOG_PATTERNS.items():
            if key not in out and needle in line:
                out[key] = ts
    return out


def parse_pcap_milestones(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
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
            key = None
            row = {
                "timestamp_iso_utc": parsed["timestamp_iso_utc"],
                "timestamp": parsed["timestamp"],
                "src": f"{parsed['src_ip']}:{parsed['src_port']}",
                "dst": f"{parsed['dst_ip']}:{parsed['dst_port']}",
                "content_type": CONTENT_TYPES.get(hdr["content_type"], f"unknown_{hdr['content_type']}"),
                "epoch": hdr["epoch"],
                "sequence_number": hdr["sequence_number"],
                "length": hdr["length"],
            }
            if hdr["content_type"] == 22 and body:
                htype = HANDSHAKE_TYPES.get(body[0], f"unknown_{body[0]}")
                row["handshake_type"] = htype
                if htype == "client_hello" and "first_client_hello" not in out:
                    key = "first_client_hello"
                elif htype == "server_hello" and "first_server_hello" not in out:
                    key = "first_server_hello"
            elif hdr["content_type"] == 20:
                if parsed["src_port"] == 27000 and "client_ccs" not in out:
                    key = "client_ccs"
                elif parsed["dst_port"] == 27000 and "server_ccs" not in out:
                    key = "server_ccs"
            elif hdr["content_type"] == 23:
                if parsed["src_port"] == 27000 and "first_client_appdata" not in out:
                    key = "first_client_appdata"
                elif parsed["dst_port"] == 27000 and "first_server_appdata" not in out:
                    key = "first_server_appdata"
            if key is not None:
                out[key] = row
            off += hdr["total_len"]
    return out


def correlate(pcap_path: Path, log_path: Path) -> dict:
    log = parse_log_milestones(log_path)
    pcap = parse_pcap_milestones(pcap_path)
    return {
        "pcap": str(pcap_path),
        "game_log": str(log_path),
        "log_milestones": log,
        "pcap_milestones": pcap,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcapng", type=Path)
    parser.add_argument("game_log", type=Path)
    args = parser.parse_args()
    print(json.dumps(correlate(args.pcapng, args.game_log), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
