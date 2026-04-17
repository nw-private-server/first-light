"""
Minimum-viable Javelin stub server — Option 5.

What this does:
  1. Listens on UDP at 0.0.0.0:<port>
  2. Presents our self-signed cert (CN=New World, OU=Amazon Game Studios)
     with the exact cipher the game uses: ECDHE-RSA-AES256-GCM-SHA384
  3. Completes DTLS 1.2 handshake (cookie exchange via PyDTLS' DTLSv1_listen)
  4. For every decrypted datagram, runs it through server.javelin.parse_datagram
     and logs every MessageRecord.
  5. If it sees a channel-3 connecting packet, replies with an SM_CONNECT_ACK
     to prove round-trip marshaling works on the wire.

What this does NOT do (yet):
  - Any gameplay replication. No chunks, no replica state.
  - OmniSDK auth mock. (That lives in the HTTPS gateway, not DTLS.)
  - Ack tracking. (The peer will complain after a few seconds.)

Known issue (2026-04-17):
  python3-dtls's SSLConnection server-mode `listen()` fails to process
  incoming datagrams on Python 3.13 — the demuxer returns None forever
  even when real ClientHellos arrive. The DTLS transport layer will
  need a different library (OpenSSL via ctypes, or swap to a subprocess
  `openssl s_server` that pipes plaintext over a local UDP pair).
  For now, the Javelin-layer logic is validated via server/test_loopback.py.

Usage (Administrator not required; WinDivert is only for tap mode):
    python -m server.stub_server --port 23971

Then point a client at 127.0.0.1:<port>. Easiest test is our own
capture replayer, or openssl s_client for DTLS smoke.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    from dtls.sslconnection import (
        SSLConnection,
        PROTOCOL_DTLSv1_2,
        CERT_NONE,
    )
except ImportError:
    print("[!] python3-dtls not installed. Run: pip install python3-dtls")
    sys.exit(1)

from server.javelin import (
    MessageFlags,
    MessageRecord,
    SystemMessageId,
    marshal_datagram,
    parse_datagram,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent
CERTS_DIR = PROJECT_DIR / "server" / "certs"
DEFAULT_CERT = CERTS_DIR / "server.crt"
DEFAULT_KEY = CERTS_DIR / "server.key"

# The cipher the game's SecureSocketDriver installs.
JAVELIN_CIPHER = "ECDHE-RSA-AES256-GCM-SHA384"


# ---------------------------------------------------------------------------
#  Connection handler
# ---------------------------------------------------------------------------

class Connection:
    """Per-client state carried across datagrams on the same DTLS session."""

    def __init__(self, conn: "SSLConnection", peer: tuple[str, int]):
        self.conn = conn
        self.peer = peer
        self.sent_connect_ack = False

    def log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] [{self.peer[0]}:{self.peer[1]}] {msg}")

    # -- send helpers --

    def send_datagram(self, records: list[MessageRecord]) -> None:
        data = marshal_datagram(records)
        self.log(f">> send {len(records)} message(s), {len(data)} bytes")
        for i, rec in enumerate(records):
            self.log(
                f"     #{i} ch={rec.channel} seq={rec.sequence} "
                f"rel={rec.reliable} conn={rec.connecting} "
                f"size={rec.size}"
            )
        self.conn.write(data)

    def send_connect_ack(self) -> None:
        """Reply to the client's SM_CONNECT_REQUEST with an ACK.

        GridMate's SM_CONNECT_ACK payload has a small header followed by
        the msgId byte at the end. We send the minimum: a 4-byte welcome
        data blob (zeros) + msgId=2.
        """
        payload = b"\x00" * 4 + bytes([SystemMessageId.SM_CONNECT_ACK])
        ack = MessageRecord(
            channel=3,              # system channel
            payload=payload,
            sequence=0,
            reliable_sequence=0,
            reliable=True,
            connecting=True,
            num_chunks=1,
        )
        self.send_datagram([ack])
        self.sent_connect_ack = True

    # -- receive handler --

    def on_datagram(self, data: bytes) -> None:
        self.log(f"<< recv {len(data)} bytes (DTLS-decrypted)")
        result = parse_datagram(data)
        if result.error:
            self.log(f"   [parse-error] {result.error}")
            return
        self.log(f"   parsed {len(result.messages)} message(s), "
                 f"{result.trailing_bits} trailing bits")

        for i, rec in enumerate(result.messages):
            summary = (
                f"#{i} ch={rec.channel} seq={rec.sequence} "
                f"rel={rec.reliable} conn={rec.connecting} "
                f"size={rec.size} flags=0x{rec.flags:02x}"
            )
            if rec.is_system:
                mid = rec.system_msg_id
                try:
                    name = SystemMessageId(mid).name if mid is not None else "?"
                except ValueError:
                    name = f"unknown({mid})"
                summary += f" SYS={name}"
            self.log(f"   {summary}")

            # Handle known system-channel messages.
            if rec.is_system and rec.system_msg_id == SystemMessageId.SM_CONNECT_REQUEST:
                if not self.sent_connect_ack:
                    self.log("   -> replying with SM_CONNECT_ACK")
                    self.send_connect_ack()


def _serve_connection(conn: "SSLConnection", peer: tuple[str, int]) -> None:
    """Handle one DTLS client in its own thread."""
    c = Connection(conn, peer)
    c.log("+ DTLS handshake complete, serving")

    try:
        while True:
            try:
                data = conn.read(65535)
            except socket.timeout:
                continue
            except Exception as e:
                msg = str(e).lower()
                if "timed out" in msg or "timeout" in msg:
                    continue
                if "reset" in msg or "eof" in msg or "shutdown" in msg:
                    c.log(f"- peer closed: {e}")
                    break
                c.log(f"! read error: {e}")
                break
            if not data:
                c.log("- peer closed (empty read)")
                break
            c.on_datagram(data)
    finally:
        try:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
        except Exception:
            pass
        c.log("- connection closed")


# ---------------------------------------------------------------------------
#  Listener
# ---------------------------------------------------------------------------

def run_server(host: str, port: int, cert: str, key: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] [*] Javelin stub server starting")
    print(f"    Listen:  {host}:{port}/udp")
    print(f"    Cert:    {cert}")
    print(f"    Cipher:  {JAVELIN_CIPHER}")
    print()

    raw = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    raw.bind((host, port))
    # Non-zero timeout is required — PyDTLS' listen() blocks on recv
    # otherwise, and we want the loop to stay responsive to Ctrl+C.
    raw.settimeout(1.0)

    server = SSLConnection(
        raw,
        keyfile=key,
        certfile=cert,
        server_side=True,
        ssl_version=PROTOCOL_DTLSv1_2,
        cert_reqs=CERT_NONE,           # client sends empty cert (per our pcap)
        ciphers=JAVELIN_CIPHER,
        do_handshake_on_connect=False,
    )

    print(f"[+] Ready. Waiting for DTLS ClientHello...")
    print()

    idle_ticks = 0
    try:
        while True:
            try:
                # listen() runs the cookie exchange for a new peer.
                peer = server.listen()
                idle_ticks += 1
                if idle_ticks % 5 == 0:
                    ts = datetime.now().strftime("%H:%M:%S")
                    print(f"[{ts}] (idle tick {idle_ticks}, listen returned {peer!r})",
                          flush=True)
                if not peer:
                    continue
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"[{ts}] [+] Cookie exchange done, accept()ing {peer}")

                conn, addr = server.accept()
                print(f"[{ts}] [+] Accepted full DTLS handshake from {addr}")

                t = threading.Thread(
                    target=_serve_connection, args=(conn, addr), daemon=True
                )
                t.start()
                idle_ticks = 0
            except socket.timeout:
                idle_ticks += 1
                continue
            except Exception as e:
                msg = str(e).lower()
                if "timed out" in msg or "timeout" in msg:
                    idle_ticks += 1
                    continue
                print(f"[!] listen/accept error: {e}")
                import traceback
                traceback.print_exc()
    except KeyboardInterrupt:
        print("\n[*] Stopping.")
    finally:
        try:
            server.close()
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Javelin stub DTLS server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=23971)
    ap.add_argument("--cert", default=str(DEFAULT_CERT))
    ap.add_argument("--key", default=str(DEFAULT_KEY))
    args = ap.parse_args()

    if not Path(args.cert).exists() or not Path(args.key).exists():
        print("[!] Missing server cert/key. Run: python tools/generate_cert.py")
        sys.exit(1)

    run_server(args.host, args.port, args.cert, args.key)


if __name__ == "__main__":
    main()
