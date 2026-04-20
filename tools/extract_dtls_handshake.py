"""
Extract a human-readable DTLS handshake transcript from a packets.jsonl capture.

This is intentionally lightweight: it decodes record headers and enough handshake
payload fields to answer practical reverse-engineering questions like:
- which side sent ClientHello / HelloVerifyRequest / ServerHello
- cookie values
- cipher suites offered / chosen
- whether the capture reached certificate / key exchange / finished

Usage:
  python tools/extract_dtls_handshake.py capture/20260416_231434_tap_test/packets.jsonl
  python tools/extract_dtls_handshake.py capture/20260416_231434_tap_test/packets.jsonl --unique
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from analyze_tap_capture import CONTENT_TYPES, HANDSHAKE_TYPES, iter_dtls_records
except ModuleNotFoundError:
    from tools.analyze_tap_capture import CONTENT_TYPES, HANDSHAKE_TYPES, iter_dtls_records


CIPHER_SUITES = {
    0xC030: "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
    0x00FF: "TLS_EMPTY_RENEGOTIATION_INFO_SCSV",
}


def parse_client_hello(payload: bytes) -> dict:
    out: dict[str, object] = {}
    if len(payload) < 34:
        return out
    out["client_version"] = f"{payload[0]:02x}{payload[1]:02x}"
    out["random"] = payload[2:34].hex()
    off = 34
    if off >= len(payload):
        return out
    sid_len = payload[off]
    off += 1
    out["session_id"] = payload[off:off + sid_len].hex()
    off += sid_len
    if off >= len(payload):
        return out
    cookie_len = payload[off]
    off += 1
    out["cookie"] = payload[off:off + cookie_len].hex()
    off += cookie_len
    if off + 2 > len(payload):
        return out
    cs_len = int.from_bytes(payload[off:off + 2], "big")
    off += 2
    suites = []
    for i in range(0, cs_len, 2):
        if off + i + 2 > len(payload):
            break
        suite = int.from_bytes(payload[off + i:off + i + 2], "big")
        suites.append(CIPHER_SUITES.get(suite, f"0x{suite:04x}"))
    out["cipher_suites"] = suites
    return out


def parse_server_hello(payload: bytes) -> dict:
    out: dict[str, object] = {}
    if len(payload) < 38:
        return out
    out["server_version"] = f"{payload[0]:02x}{payload[1]:02x}"
    out["random"] = payload[2:34].hex()
    off = 34
    sid_len = payload[off]
    off += 1
    out["session_id"] = payload[off:off + sid_len].hex()
    off += sid_len
    if off + 2 <= len(payload):
        suite = int.from_bytes(payload[off:off + 2], "big")
        out["cipher_suite"] = CIPHER_SUITES.get(suite, f"0x{suite:04x}")
    return out


def parse_hello_verify(payload: bytes) -> dict:
    if len(payload) < 3:
        return {}
    cookie_len = payload[2]
    return {
        "server_version": f"{payload[0]:02x}{payload[1]:02x}",
        "cookie": payload[3:3 + cookie_len].hex(),
    }


def parse_handshake_message(htype: int, body: bytes) -> dict:
    if htype == 1:
        return parse_client_hello(body)
    if htype == 2:
        return parse_server_hello(body)
    if htype == 3:
        return parse_hello_verify(body)
    return {}


def event_key(event: dict) -> tuple:
    details = event.get("details", {})
    return (
        event["direction"],
        event["handshake_type"],
        event["message_seq"],
        event["message_len"],
        event["fragment_offset"],
        event["fragment_len"],
        details.get("cookie", ""),
        details.get("cipher_suite", ""),
        tuple(details.get("cipher_suites", [])),
    )


def extract(path: Path, limit: int) -> list[dict]:
    events: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            hh = obj.get("hexHead", "")
            if not hh:
                continue
            buf = bytes.fromhex(hh)
            for ctype, payload in iter_dtls_records(buf):
                if ctype != 22 or len(payload) < 12:
                    continue
                htype = payload[0]
                msg_len = int.from_bytes(payload[1:4], "big")
                msg_seq = int.from_bytes(payload[4:6], "big")
                frag_off = int.from_bytes(payload[6:9], "big")
                frag_len = int.from_bytes(payload[9:12], "big")
                body = payload[12:12 + frag_len]
                events.append(
                    {
                        "seq": obj.get("seq"),
                        "ts": obj.get("ts"),
                        "direction": obj.get("direction"),
                        "record_version": f"{buf[1]:02x}{buf[2]:02x}",
                        "handshake_type": HANDSHAKE_TYPES.get(htype, f"unknown_{htype}"),
                        "message_seq": msg_seq,
                        "message_len": msg_len,
                        "fragment_offset": frag_off,
                        "fragment_len": frag_len,
                        "details": parse_handshake_message(htype, body),
                    }
                )
                if len(events) >= limit:
                    return events
    return events


def collapse_retransmits(events: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen: set[tuple] = set()
    for event in events:
        key = event_key(event)
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path, help="Path to packets.jsonl")
    parser.add_argument("--limit", type=int, default=40, help="Max handshake events to print")
    parser.add_argument("--unique", action="store_true", help="Collapse retransmits into a unique handshake timeline")
    args = parser.parse_args()
    events = extract(args.jsonl, args.limit * 50 if args.unique else args.limit)
    if args.unique:
        events = collapse_retransmits(events)[:args.limit]
    else:
        events = events[:args.limit]
    print(json.dumps(events, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
