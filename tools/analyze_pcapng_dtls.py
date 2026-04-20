"""
Minimal dependency-free PCAPNG DTLS summarizer.

Purpose:
- inspect .pcapng captures in-repo without tshark/scapy
- count DTLS UDP payloads by content type
- surface whether a capture contains server-side DTLS flights beyond HelloVerifyRequest

This parser currently handles the common case used by our captures:
- Section Header Block
- Interface Description Block
- Enhanced Packet Block
- Ethernet + IPv4 + UDP frames

Usage:
  python tools/analyze_pcapng_dtls.py capture/20260416_222545_second_capture/pcaps/capture.pcapng
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
from collections import Counter
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


def read_u32(data: bytes, offset: int, endian: str) -> int:
    return struct.unpack_from(endian + "I", data, offset)[0]


def parse_udp_payload(pkt: bytes) -> dict | None:
    if len(pkt) < 14:
        return None
    eth_type = struct.unpack_from("!H", pkt, 12)[0]
    if eth_type != 0x0800:
        return None
    ip = pkt[14:]
    if len(ip) < 20:
        return None
    version_ihl = ip[0]
    version = version_ihl >> 4
    ihl = (version_ihl & 0x0F) * 4
    if version != 4 or len(ip) < ihl + 8:
        return None
    if ip[9] != 17:
        return None
    total_len = struct.unpack_from("!H", ip, 2)[0]
    src_ip = socket.inet_ntoa(ip[12:16])
    dst_ip = socket.inet_ntoa(ip[16:20])
    udp = ip[ihl:]
    src_port, dst_port, udp_len = struct.unpack_from("!HHH", udp, 0)
    payload = udp[8:8 + max(0, udp_len - 8)]
    if total_len and len(ip) > total_len:
        payload = ip[ihl + 8:total_len]
    return {
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "src_port": src_port,
        "dst_port": dst_port,
        "payload": payload,
    }


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


def summarize_pcapng(path: Path) -> dict:
    data = path.read_bytes()
    off = 0
    endian = "<"
    linktype = None

    packet_count = 0
    udp_count = 0
    dtls_packet_count = 0
    content_counts = Counter()
    handshake_counts = Counter()
    endpoints = Counter()
    examples = []

    while off + 12 <= len(data):
        block_type_le = struct.unpack_from("<I", data, off)[0]
        block_len_le = struct.unpack_from("<I", data, off + 4)[0]
        if block_len_le < 12 or off + block_len_le > len(data):
            break

        if block_type_le == 0x0A0D0D0A:
            bom = data[off + 8:off + 12]
            if bom == b"\x4d\x3c\x2b\x1a":
                endian = "<"
            elif bom == b"\x1a\x2b\x3c\x4d":
                endian = ">"
            block_len = read_u32(data, off + 4, endian)
        else:
            block_len = read_u32(data, off + 4, endian)

        body = data[off + 8:off + block_len - 4]

        if block_type_le == 0x00000001 and len(body) >= 8:
            linktype = struct.unpack_from(endian + "H", body, 0)[0]
        elif block_type_le == 0x00000006 and linktype == 1 and len(body) >= 20:
            packet_count += 1
            cap_len = struct.unpack_from(endian + "I", body, 12)[0]
            pkt = body[20:20 + cap_len]
            parsed = parse_udp_payload(pkt)
            if parsed is not None:
                udp_count += 1
                endpoints[(parsed["src_ip"], parsed["src_port"], parsed["dst_ip"], parsed["dst_port"])] += 1
                payload = parsed["payload"]
                found_dtls = False
                for ctype, rec_payload in iter_dtls_records(payload):
                    found_dtls = True
                    content_counts[CONTENT_TYPES[ctype]] += 1
                    if ctype == 22 and rec_payload:
                        handshake_counts[HANDSHAKE_TYPES.get(rec_payload[0], f"unknown_{rec_payload[0]}")] += 1
                if found_dtls:
                    dtls_packet_count += 1
                    if len(examples) < 20:
                        examples.append(
                            {
                                "src": f"{parsed['src_ip']}:{parsed['src_port']}",
                                "dst": f"{parsed['dst_ip']}:{parsed['dst_port']}",
                                "payload_head": payload[:64].hex(),
                            }
                        )

        off += block_len

    top_endpoints = [
        {"src": f"{s[0]}:{s[1]}", "dst": f"{s[2]}:{s[3]}", "count": c}
        for s, c in endpoints.most_common(10)
    ]

    return {
        "path": str(path),
        "linktype": linktype,
        "packet_count": packet_count,
        "udp_packet_count": udp_count,
        "dtls_packet_count": dtls_packet_count,
        "content_type_counts": dict(content_counts),
        "handshake_counts": dict(handshake_counts),
        "top_endpoints": top_endpoints,
        "examples": examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcapng", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize_pcapng(args.pcapng), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
