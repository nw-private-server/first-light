"""
Combined DTLS interceptor for New World.

Uses WinDivert to capture game server UDP packets and feeds them to a
local DTLS proxy. Instead of rewriting packet destinations (which can't
reach loopback), this captures outbound packets, drops them, and relays
the raw UDP payload through a local socket pair to the DTLS server.

Must be run as Administrator.

Usage:
    python dtls_intercept.py
    python dtls_intercept.py --server-ip 52.223.16.88 --server-port 58068
    python dtls_intercept.py --name my_session
"""

import argparse
import json
import os
import re
import signal
import socket
import struct
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import pydivert
except ImportError:
    print("[!] pydivert not installed. Run: pip install pydivert")
    sys.exit(1)

PROJECT_DIR = Path(__file__).resolve().parent.parent
CAPTURE_DIR = PROJECT_DIR / "capture"
CERTS_DIR = PROJECT_DIR / "server" / "certs"
GAME_LOG = Path(os.environ.get(
    "NW_GAME_LOG",
    str(Path.home() / "AppData" / "Local" / "AGS" / "New World" / "Game.log"),
))


class PacketLogger:
    """Logs intercepted packets to disk."""

    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.packets_dir = session_dir / "packets"
        self.packets_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = session_dir / "packets.jsonl"
        self.log_path = session_dir / "session.log"
        self._jsonl = open(self.jsonl_path, "w", encoding="utf-8")
        self._log = open(self.log_path, "w", encoding="utf-8")
        self.seq = 0
        self.stats = {}
        self.total_bytes = 0
        self._write_log(f"Session started: {datetime.now().isoformat()}")

    def _write_log(self, text: str):
        line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {text}"
        self._log.write(line + "\n")
        self._log.flush()
        print(line)

    def log(self, text: str):
        self._write_log(text)

    def write_packet(self, data: bytes, direction: str, protocol: str = "raw_udp"):
        seq = self.seq
        self.seq += 1
        filename = f"{seq:06d}_{direction}_{protocol}.bin"
        (self.packets_dir / filename).write_bytes(data)

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

        arrow = "<-" if direction == "recv" else "->"
        print(f"  [{protocol.upper():>7s}] {arrow} #{seq:06d}  {len(data):>6d} bytes  {hex_head[:80]}")

    def close(self):
        self._jsonl.close()
        self._log.close()

    def print_summary(self):
        print(f"\n  Packets: {self.seq}  |  Bytes: {self.total_bytes:,}")
        for key in sorted(self.stats):
            print(f"    {key:>25s}: {self.stats[key]:>6d}")


def detect_server_from_log() -> tuple[str, int] | None:
    """Parse the game log for the most recent REP Address."""
    if not GAME_LOG.exists():
        return None
    pattern = re.compile(r"REP Address: (\d+\.\d+\.\d+\.\d+):(\d+)")
    last_match = None
    with open(GAME_LOG, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                last_match = (m.group(1), int(m.group(2)))
    return last_match


def run_intercept(server_ip: str, server_port: int, logger: PacketLogger):
    """
    Main intercept loop.

    Strategy:
    - WinDivert captures outbound UDP to server_ip:server_port
    - Instead of re-injecting, we DROP those packets (don't call w.send())
    - We forward the UDP payload to the real server via our own socket
    - Responses from the real server come back to our socket
    - We inject response packets back to the game using WinDivert

    This gives us plaintext access to the UDP payloads before DTLS.
    Note: This captures the raw DTLS records, not decrypted data.
    But it proves the interception works and we can see the handshake.
    """

    filt = (
        f"outbound and udp and "
        f"ip.DstAddr == {server_ip} and udp.DstPort == {server_port}"
    )

    logger.log(f"[*] Intercepting UDP to {server_ip}:{server_port}")
    logger.log(f"[*] Filter: {filt}")

    try:
        w = pydivert.WinDivert(filt)
        w.open()
    except Exception as e:
        if "access" in str(e).lower() or "denied" in str(e).lower():
            logger.log("[!] Permission denied. Run as Administrator.")
        else:
            logger.log(f"[!] WinDivert error: {e}")
        return

    logger.log("[+] WinDivert active")

    # Create a UDP socket to forward to the real server
    relay_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    relay_sock.settimeout(0.1)

    # Track the game's source address for injecting responses
    game_src_addr = None  # (ip, port)
    packet_count = 0

    # Thread to receive responses from real server and inject back to game
    running = True

    def recv_responses():
        nonlocal packet_count
        while running:
            try:
                data, addr = relay_sock.recvfrom(65535)
                if data and game_src_addr:
                    logger.write_packet(data, "recv")
                    # Build a UDP response packet and inject via WinDivert
                    # We need to craft the packet at IP level
                    # For now, just log it - injecting raw packets is complex
                    packet_count += 1
            except socket.timeout:
                continue
            except Exception as e:
                if running:
                    logger.log(f"[!] Recv error: {e}")
                break

    recv_thread = threading.Thread(target=recv_responses, daemon=True)
    recv_thread.start()

    logger.log("[*] Waiting for game packets... Launch New World and hit Play.")
    logger.log("[*] Press Ctrl+C to stop")

    try:
        while True:
            try:
                packet = w.recv()
            except Exception as e:
                if "interrupted" in str(e).lower():
                    break
                raise

            # Extract UDP payload
            payload = packet.payload
            src_ip = packet.src_addr
            src_port = packet.src_port

            if game_src_addr is None:
                game_src_addr = (src_ip, src_port)
                logger.log(f"[+] Game source: {src_ip}:{src_port}")

            # Log the outbound packet
            logger.write_packet(payload, "send")

            # Forward to real server
            try:
                relay_sock.sendto(payload, (server_ip, server_port))
            except Exception as e:
                logger.log(f"[!] Forward error: {e}")

            # DON'T re-inject the original packet (we forwarded it ourselves)
            # But we need to let it through or the game will hang...
            # Actually, let's re-inject it AND forward it (tee mode)
            try:
                w.send(packet)
            except OSError:
                pass

            packet_count += 1

    except KeyboardInterrupt:
        logger.log("[*] Stopping...")
    finally:
        running = False
        relay_sock.close()
        w.close()
        logger.log(f"[+] Intercepted {packet_count} packets")


def main():
    parser = argparse.ArgumentParser(description="New World DTLS interceptor")
    parser.add_argument("--server-ip", default=None, help="Game server IP")
    parser.add_argument("--server-port", type=int, default=None, help="Game server port")
    parser.add_argument("--name", default="intercept", help="Session name")
    args = parser.parse_args()

    # Auto-detect from game log
    if not args.server_ip:
        detected = detect_server_from_log()
        if detected:
            args.server_ip, args.server_port = detected
            print(f"[+] Detected from game log: {args.server_ip}:{args.server_port}")
        else:
            print("[!] No server found in game log. Pass --server-ip and --server-port")
            sys.exit(1)

    # Check cert exists
    cert = CERTS_DIR / "server.crt"
    key = CERTS_DIR / "server.key"
    if not cert.exists() or not key.exists():
        print("[!] Certificates not found. Run: python tools/generate_cert.py")
        sys.exit(1)

    # Setup session
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = CAPTURE_DIR / f"{timestamp}_{args.name}"
    logger = PacketLogger(session_dir)

    print()
    print("=" * 64)
    print("  New World DTLS Interceptor")
    print("=" * 64)
    print(f"  Server:  {args.server_ip}:{args.server_port}")
    print(f"  Output:  {session_dir}")
    print("=" * 64)
    print()

    try:
        run_intercept(args.server_ip, args.server_port, logger)
    finally:
        logger.print_summary()
        logger.close()


if __name__ == "__main__":
    main()
