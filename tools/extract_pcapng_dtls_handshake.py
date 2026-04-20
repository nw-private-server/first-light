"""
Extract a DTLS handshake timeline from a PCAPNG capture without external deps.

This focuses on the real Wireshark captures in `capture/*/pcaps/capture.pcapng`,
which contain a fuller server flight than the tap session.

Usage:
  python tools/extract_pcapng_dtls_handshake.py capture/20260416_222545_second_capture/pcaps/capture.pcapng --unique
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from analyze_pcapng_dtls import HANDSHAKE_TYPES, iter_dtls_records, parse_udp_payload, read_u32
except ModuleNotFoundError:
    from tools.analyze_pcapng_dtls import HANDSHAKE_TYPES, iter_dtls_records, parse_udp_payload, read_u32

import struct


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
    sid_len = payload[off]
    off += 1
    out["session_id"] = payload[off:off + sid_len].hex()
    off += sid_len
    cookie_len = payload[off]
    off += 1
    out["cookie"] = payload[off:off + cookie_len].hex()
    off += cookie_len
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
        event["src"],
        event["dst"],
        event["handshake_type"],
        event["message_seq"],
        event["message_len"],
        event["fragment_offset"],
        event["fragment_len"],
        details.get("cookie", ""),
        details.get("cipher_suite", ""),
        tuple(details.get("cipher_suites", [])),
    )


def iter_handshake_events(path: Path):
    data = path.read_bytes()
    off = 0
    endian = "<"
    linktype = None
    while off + 12 <= len(data):
        block_type_le = struct.unpack_from("<I", data, off)[0]
        block_len = struct.unpack_from(endian + "I", data, off + 4)[0]
        if block_type_le == 0x0A0D0D0A:
            bom = data[off + 8:off + 12]
            if bom == b"\x4d\x3c\x2b\x1a":
                endian = "<"
            elif bom == b"\x1a\x2b\x3c\x4d":
                endian = ">"
            block_len = read_u32(data, off + 4, endian)
        if block_len < 12 or off + block_len > len(data):
            break
        body = data[off + 8:off + block_len - 4]
        if block_type_le == 0x00000001 and len(body) >= 8:
            linktype = struct.unpack_from(endian + "H", body, 0)[0]
        elif block_type_le == 0x00000006 and linktype == 1 and len(body) >= 20:
            cap_len = struct.unpack_from(endian + "I", body, 12)[0]
            pkt = body[20:20 + cap_len]
            parsed = parse_udp_payload(pkt)
            if parsed is not None:
                payload = parsed["payload"]
                for ctype, rec_payload in iter_dtls_records(payload):
                    if ctype != 22 or len(rec_payload) < 12:
                        continue
                    htype = rec_payload[0]
                    msg_len = int.from_bytes(rec_payload[1:4], "big")
                    msg_seq = int.from_bytes(rec_payload[4:6], "big")
                    frag_off = int.from_bytes(rec_payload[6:9], "big")
                    frag_len = int.from_bytes(rec_payload[9:12], "big")
                    body2 = rec_payload[12:12 + frag_len]
                    yield {
                        "src": f"{parsed['src_ip']}:{parsed['src_port']}",
                        "dst": f"{parsed['dst_ip']}:{parsed['dst_port']}",
                        "record_version": f"{payload[1]:02x}{payload[2]:02x}",
                        "handshake_type": HANDSHAKE_TYPES.get(htype, f"unknown_{htype}"),
                        "message_seq": msg_seq,
                        "message_len": msg_len,
                        "fragment_offset": frag_off,
                        "fragment_len": frag_len,
                        "details": parse_handshake_message(htype, body2),
                    }
        off += block_len


def extract(path: Path, unique: bool, limit: int) -> list[dict]:
    items = []
    seen: set[tuple] = set()
    for event in iter_handshake_events(path):
        if unique:
            key = event_key(event)
            if key in seen:
                continue
            seen.add(key)
        items.append(event)
        if len(items) >= limit:
            break
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcapng", type=Path)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--unique", action="store_true")
    args = parser.parse_args()
    print(json.dumps(extract(args.pcapng, args.unique, args.limit), indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
