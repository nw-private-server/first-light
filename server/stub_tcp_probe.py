"""
Tiny TCP listener that accepts connections on port 5999 (dual-stack v4/v6),
logs the peer address, reads & hex-dumps the first chunk the client sends,
then keeps the socket open. Used to verify the stubbed-mode gateway client
is actually reaching us, and to capture whatever protocol it speaks first.

Run as Administrator.

Usage:
    python server/stub_tcp_probe.py
    python server/stub_tcp_probe.py --port 5999 --bind ::
"""

from __future__ import annotations

import argparse
import datetime
import socket
import sys
import threading


def hex_dump(data: bytes, width: int = 16) -> str:
    out = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hex_part = " ".join("{:02x}".format(b) for b in chunk)
        ascii_part = "".join((chr(b) if 32 <= b < 127 else ".") for b in chunk)
        out.append("{:08x}  {:<{w}}  {}".format(i, hex_part, ascii_part,
                                                w=width * 3 - 1))
    return "\n".join(out)


def now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def serve_one(conn: socket.socket, peer):
    print(f"[{now()}] [+] accepted conn from {peer}", flush=True)
    try:
        conn.settimeout(5.0)
        try:
            data = conn.recv(4096)
        except socket.timeout:
            print(f"[{now()}] [{peer}] no bytes after 5s, closing", flush=True)
            return
        if not data:
            print(f"[{now()}] [{peer}] EOF immediately", flush=True)
            return
        print(f"[{now()}] [{peer}] received {len(data)} bytes:", flush=True)
        print(hex_dump(data), flush=True)
        # Keep socket open for a bit; some protocols expect a server greeting
        # first. We just hold it open without responding.
        try:
            data2 = conn.recv(4096)
            if data2:
                print(f"[{now()}] [{peer}] +{len(data2)} bytes:", flush=True)
                print(hex_dump(data2), flush=True)
        except socket.timeout:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5999)
    ap.add_argument("--bind", default="::",
                    help="Bind address; '::' gives dual-stack v4+v6 on Windows")
    args = ap.parse_args()

    # Dual-stack: bind on IPv6 and disable IPV6_V6ONLY so it accepts v4 too.
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except OSError as e:
        print(f"[!] couldn't disable IPV6_V6ONLY: {e}", flush=True)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((args.bind, args.port))
    except OSError as e:
        print(f"[!] bind {args.bind}:{args.port} failed: {e}", flush=True)
        return 1
    sock.listen(64)
    print(f"[{now()}] [*] listening TCP on {args.bind}:{args.port} (dual-stack)",
          flush=True)
    print(f"[{now()}] [*] accepting connections; ^C to quit", flush=True)

    try:
        while True:
            conn, peer = sock.accept()
            t = threading.Thread(target=serve_one, args=(conn, peer), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print(f"\n[{now()}] [*] shutting down", flush=True)
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
