"""
DTLS 1.2 MITM Proxy for New World

Terminates the game client's DTLS connection, logs decrypted packets,
and optionally forwards to the real game server.

Usage:
    # Standalone (listen only, no forwarding)
    python dtls_proxy.py --port 23971

    # With forwarding to real server
    python dtls_proxy.py --port 23971 --forward 52.223.16.88:58068
"""

import argparse
import json
import os
import socket
import ssl
import struct
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# PyDTLS — use SSLConnection directly (do_patch is broken on Python 3.12+)
try:
    from dtls.sslconnection import SSLConnection, PROTOCOL_DTLSv1_2
    from dtls.sslconnection import CERT_NONE
except ImportError:
    print("[!] python3-dtls not installed. Run: pip install python3-dtls")
    sys.exit(1)

PROJECT_DIR = Path(__file__).resolve().parent.parent
CAPTURE_DIR = PROJECT_DIR / "capture"
CERTS_DIR = PROJECT_DIR / "server" / "certs"


class PacketLogger:
    """Logs decrypted packets to disk in the same format as frida_capture.py."""

    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.packets_dir = session_dir / "packets"
        self.packets_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = session_dir / "packets.jsonl"
        self.log_path = session_dir / "session.log"
        self._jsonl = open(self.jsonl_path, "w", encoding="utf-8")
        self._log = open(self.log_path, "w", encoding="utf-8")
        self.seq = 0
        self.stats = {}  # "protocol:direction" -> count
        self.total_bytes = 0
        self._write_log(f"Session started: {datetime.now().isoformat()}")

    def _write_log(self, text: str):
        line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {text}"
        self._log.write(line + "\n")
        self._log.flush()
        print(line)

    def log(self, text: str):
        self._write_log(text)

    def write_packet(self, data: bytes, direction: str, protocol: str = "dtls"):
        seq = self.seq
        self.seq += 1

        filename = f"{seq:06d}_{direction}_{protocol}.bin"
        bin_path = self.packets_dir / filename
        bin_path.write_bytes(data)

        hex_head = data[:256].hex()
        entry = {
            "seq": seq,
            "ts": datetime.now().isoformat(),
            "direction": direction,
            "protocol": protocol,
            "len": len(data),
            "file": filename,
            "hexHead": hex_head,
        }
        self._jsonl.write(json.dumps(entry) + "\n")
        self._jsonl.flush()

        key = f"{protocol}:{direction}"
        self.stats[key] = self.stats.get(key, 0) + 1
        self.total_bytes += len(data)

        arrow = "<-" if direction == "read" else "->"
        print(f"  [DTLS] {arrow} #{seq:06d}  {len(data):>8d} bytes  {hex_head[:64]}...")

    def close(self):
        self._jsonl.close()
        self._log.close()

    def print_summary(self):
        print(f"\n  Packets: {self.seq}  |  Bytes: {self.total_bytes:,}")
        for key in sorted(self.stats):
            print(f"    {key:>20s}: {self.stats[key]:>6d}")


def create_dtls_server(host: str, port: int, cert_path: str, key_path: str):
    """Create a DTLS server using PyDTLS's SSLConnection directly."""

    # Create the underlying UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))

    # Wrap with DTLS SSLConnection (server mode)
    dtls_conn = SSLConnection(
        sock,
        keyfile=key_path,
        certfile=cert_path,
        server_side=True,
        ssl_version=PROTOCOL_DTLSv1_2,
        cert_reqs=CERT_NONE,  # Don't require client cert
        do_handshake_on_connect=False,
    )

    return dtls_conn


def handle_client(conn, addr, logger: PacketLogger, forward_addr=None):
    """Handle a single DTLS client connection."""
    logger.log(f"[+] Client connected from {addr[0]}:{addr[1]}")

    # Complete DTLS handshake
    try:
        conn.do_handshake()
        logger.log(f"[+] DTLS handshake complete with {addr[0]}:{addr[1]}")
    except Exception as e:
        logger.log(f"[!] DTLS handshake failed: {e}")
        return

    # Optional: connect to real server for forwarding
    forward_sock = None
    if forward_addr:
        try:
            forward_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            logger.log(f"[*] Forwarding enabled to {forward_addr}")
        except Exception as e:
            logger.log(f"[!] Forward connection failed: {e}")
            forward_sock = None

    # Read loop
    try:
        while True:
            try:
                data = conn.read(65535)
                if not data:
                    break
                logger.write_packet(data, "read")

                if forward_sock and forward_addr:
                    forward_sock.sendto(data, forward_addr)

            except Exception as e:
                err_str = str(e).lower()
                if "timed out" in err_str or "timeout" in err_str:
                    continue
                if "reset" in err_str or "connection" in err_str:
                    logger.log(f"[-] Client {addr[0]}:{addr[1]} disconnected")
                    break
                logger.log(f"[!] Read error: {e}")
                break
    finally:
        try:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
        except Exception:
            pass
        if forward_sock:
            forward_sock.close()
        logger.log(f"[-] Connection closed: {addr[0]}:{addr[1]}")


def run_proxy(host: str, port: int, cert_path: str, key_path: str,
              logger: PacketLogger, forward_addr=None):
    """Main proxy loop."""

    logger.log(f"[*] Starting DTLS proxy on {host}:{port}")
    logger.log(f"[*] Certificate: {cert_path}")
    logger.log(f"[*] Key: {key_path}")
    if forward_addr:
        logger.log(f"[*] Forwarding to: {forward_addr[0]}:{forward_addr[1]}")

    try:
        dtls_server = create_dtls_server(host, port, cert_path, key_path)
    except Exception as e:
        logger.log(f"[!] Failed to create DTLS socket: {e}")
        import traceback
        traceback.print_exc()
        return

    logger.log(f"[+] DTLS proxy listening on {host}:{port}")
    logger.log(f"[*] Waiting for game client connection...")

    try:
        while True:
            try:
                # listen() handles cookie exchange, blocks until a peer arrives
                peer_address = dtls_server.listen()
                if peer_address:
                    logger.log(f"[*] New peer from {peer_address}, accepting...")
                    # accept() completes the DTLS handshake
                    conn, addr = dtls_server.accept()
                    logger.log(f"[+] Accepted connection from {addr}")
                    t = threading.Thread(
                        target=handle_client,
                        args=(conn, addr, logger, forward_addr),
                        daemon=True,
                    )
                    t.start()
            except socket.timeout:
                continue
            except Exception as e:
                err_str = str(e).lower()
                if "timed out" in err_str or "timeout" in err_str:
                    continue
                logger.log(f"[!] Listen/Accept error: {e}")
                import traceback
                traceback.print_exc()
    except KeyboardInterrupt:
        logger.log("[*] Shutting down proxy...")
    finally:
        dtls_server.close()


def main():
    parser = argparse.ArgumentParser(description="DTLS MITM Proxy for New World")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=23971, help="Listen port")
    parser.add_argument("--cert", default=str(CERTS_DIR / "server.crt"), help="Server certificate")
    parser.add_argument("--key", default=str(CERTS_DIR / "server.key"), help="Server private key")
    parser.add_argument("--forward", default=None, help="Forward to real server (ip:port)")
    parser.add_argument("--name", default="dtls_proxy", help="Session name")
    args = parser.parse_args()

    # Verify cert/key exist
    if not Path(args.cert).exists():
        print(f"[!] Certificate not found: {args.cert}")
        print(f"    Run: python tools/generate_cert.py")
        sys.exit(1)
    if not Path(args.key).exists():
        print(f"[!] Key not found: {args.key}")
        sys.exit(1)

    # Parse forward address
    forward_addr = None
    if args.forward:
        parts = args.forward.split(":")
        forward_addr = (parts[0], int(parts[1]))

    # Setup session
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = CAPTURE_DIR / f"{timestamp}_{args.name}"
    logger = PacketLogger(session_dir)

    print()
    print("=" * 64)
    print("  New World DTLS Proxy")
    print("=" * 64)
    print(f"  Listen:  {args.host}:{args.port}")
    print(f"  Cert:    {args.cert}")
    print(f"  Output:  {session_dir}")
    if forward_addr:
        print(f"  Forward: {forward_addr[0]}:{forward_addr[1]}")
    print("=" * 64)
    print()

    try:
        run_proxy(args.host, args.port, args.cert, args.key, logger, forward_addr)
    finally:
        logger.print_summary()
        logger.close()
        print(f"\n  Session: {session_dir}")


if __name__ == "__main__":
    main()
