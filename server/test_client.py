"""
Test client for the stub server. Uses PyDTLS to do a DTLS 1.2 handshake
against 127.0.0.1:<port>, then sends a minimal SM_CONNECT_REQUEST
message via our Javelin marshaler.

Usage:
    python -m server.test_client --port 24999
"""

from __future__ import annotations

import argparse
import socket
import ssl
import sys
import time
from datetime import datetime

try:
    from dtls.sslconnection import (
        SSLConnection,
        PROTOCOL_DTLSv1_2,
        CERT_NONE,
    )
except ImportError:
    print("[!] python3-dtls not installed")
    sys.exit(1)

from server.javelin import (
    MessageRecord,
    SystemMessageId,
    marshal_datagram,
    parse_datagram,
)

JAVELIN_CIPHER = "ECDHE-RSA-AES256-GCM-SHA384"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=24999)
    args = ap.parse_args()

    log(f"[*] Connecting to {args.host}:{args.port}")

    raw = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    raw.settimeout(5.0)

    client = SSLConnection(
        raw,
        server_side=False,
        ssl_version=PROTOCOL_DTLSv1_2,
        cert_reqs=CERT_NONE,            # don't verify server cert
        ciphers=JAVELIN_CIPHER,
        do_handshake_on_connect=False,
    )

    log("[*] Calling connect()...")
    client.connect((args.host, args.port))
    log("[+] connect() returned")

    log("[*] do_handshake()...")
    client.do_handshake()
    log("[+] DTLS handshake complete")

    # Send a minimal SM_CONNECT_REQUEST.
    #   - channel 3 (system)
    #   - connecting flag set
    #   - reliable
    #   - payload: 4-byte "welcome" zeros + msgId (1 = SM_CONNECT_REQUEST)
    payload = b"\x00\x00\x00\x00" + bytes([SystemMessageId.SM_CONNECT_REQUEST])
    req = MessageRecord(
        channel=3,
        payload=payload,
        sequence=0,
        reliable_sequence=0,
        reliable=True,
        connecting=True,
        num_chunks=1,
    )
    data = marshal_datagram([req])
    log(f"[*] Sending {len(data)} bytes (SM_CONNECT_REQUEST): {data.hex()}")
    client.write(data)

    # Wait for reply (SM_CONNECT_ACK).
    log("[*] Waiting for server reply...")
    try:
        resp = client.read(65535)
    except Exception as e:
        log(f"[!] read failed: {e}")
        return
    log(f"[+] Got {len(resp)} bytes: {resp.hex()}")

    result = parse_datagram(resp)
    if result.error:
        log(f"[!] parse error: {result.error}")
        return
    for i, rec in enumerate(result.messages):
        summary = (
            f"   #{i} ch={rec.channel} seq={rec.sequence} "
            f"conn={rec.connecting} rel={rec.reliable} size={rec.size}"
        )
        if rec.is_system:
            try:
                name = SystemMessageId(rec.system_msg_id).name
            except (ValueError, TypeError):
                name = f"unknown({rec.system_msg_id})"
            summary += f" SYS={name}"
        log(summary)

    log("[*] Success. Closing.")
    try:
        client.shutdown(socket.SHUT_RDWR)
        client.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
