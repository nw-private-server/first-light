"""
Compare REP registration windows across multiple real captures.

Usage:
  python tools/compare_registration_windows.py
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    from extract_registration_window import extract_window
except ModuleNotFoundError:
    from tools.extract_registration_window import extract_window


PAIRS = [
    (
        Path("capture/20260416_221806_first_capture/pcaps/capture.pcapng"),
        Path("capture/20260416_221806_first_capture/logs/game_log_after.log"),
    ),
    (
        Path("capture/20260416_222545_second_capture/pcaps/capture.pcapng"),
        Path("capture/20260416_222545_second_capture/logs/game_log_after.log"),
    ),
]


def main() -> int:
    rows = []
    for pcap, log in PAIRS:
        data = extract_window(pcap, log, 12, 12)
        rows.append(
            {
                "pcap": str(pcap),
                "first_server_application_data": data["first_server_application_data"],
                "server_lengths": [r["length"] for r in data["server_window"]],
                "client_lengths": [r["length"] for r in data["client_window"]],
                "registration_response": data["log_milestones"].get("registration_response"),
            }
        )
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
