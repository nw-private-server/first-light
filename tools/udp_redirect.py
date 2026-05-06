"""
WinDivert-based UDP redirector for New World.

Intercepts UDP packets to game server IPs and rewrites them to point
at the local DTLS proxy. Also rewrites return packets so the game
thinks they're coming from the real server.

Must be run as Administrator (WinDivert requires it).

Usage:
    python udp_redirect.py --proxy-port 23971
    python udp_redirect.py --proxy-port 23971 --server-ip 52.223.16.88 --server-port 58068
    python udp_redirect.py --proxy-port 23971 --auto  (reads game log for server IP)
"""

import argparse
import os
import re
import signal
import sys
import time
from pathlib import Path

try:
    import pydivert
except ImportError:
    print("[!] pydivert not installed. Run: pip install pydivert")
    sys.exit(1)

# AWS Global Accelerator IP ranges commonly used by New World
# These are the /16 or /10 ranges we've seen game servers in
AWS_GA_PREFIXES = [
    "35.71.",      # 35.71.190.194
    "52.223.",     # 52.223.16.88
]

GAME_LOG = Path(os.environ.get(
    "NW_GAME_LOG",
    str(Path.home() / "AppData" / "Local" / "AGS" / "New World" / "Game.log"),
))


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


def is_game_server_ip(ip: str) -> bool:
    """Check if an IP belongs to known AWS Global Accelerator ranges."""
    for prefix in AWS_GA_PREFIXES:
        if ip.startswith(prefix):
            return True
    return False


def run_redirect(proxy_host: str, proxy_port: int,
                 server_ip: str | None, server_port: int | None,
                 auto_detect: bool):
    """Main redirect loop using WinDivert."""

    # Build filter
    if server_ip and server_port:
        # Specific server — only capture packets we'll modify
        filt = (
            f"udp and "
            f"((outbound and ip.DstAddr == {server_ip} and udp.DstPort == {server_port}) or "
            f"(inbound and ip.SrcAddr == 127.0.0.1 and udp.SrcPort == {proxy_port}))"
        )
        print(f"[*] Redirecting {server_ip}:{server_port} -> 127.0.0.1:{proxy_port}")
    else:
        # Wait for the game log to tell us the server IP:port
        print(f"[*] Waiting for game to connect -- monitoring game log for REP Address...")
        while not server_ip:
            detected = detect_server_from_log()
            if detected:
                server_ip, server_port = detected
                print(f"[+] Detected from game log: {server_ip}:{server_port}")
            else:
                time.sleep(1)
                sys.stdout.write(".")
                sys.stdout.flush()
        # Now build a precise filter
        filt = (
            f"udp and ("
            f"(outbound and ip.DstAddr == {server_ip} and udp.DstPort == {server_port}) or "
            f"(inbound and ip.SrcAddr == 127.0.0.1 and udp.SrcPort == {proxy_port})"
            f")"
        )
        print(f"[*] Redirecting {server_ip}:{server_port} -> 127.0.0.1:{proxy_port}")

    # Track active redirects: original (ip, port) -> True
    active_server = None
    if server_ip and server_port:
        active_server = (server_ip, server_port)

    # State for NAT: maps local_src_port -> (original_dst_ip, original_dst_port)
    nat_table = {}

    print(f"[*] Opening WinDivert handle...")
    print(f"[*] Filter: {filt[:100]}...")

    try:
        w = pydivert.WinDivert(filt)
        w.open()
    except Exception as e:
        if "access" in str(e).lower() or "denied" in str(e).lower():
            print(f"[!] Permission denied. Run as Administrator.")
        else:
            print(f"[!] WinDivert error: {e}")
        sys.exit(1)

    print(f"[+] WinDivert active. Intercepting packets...")
    print(f"[*] Press Ctrl+C to stop\n")

    packet_count = 0
    redirected_count = 0

    try:
        while True:
            try:
                packet = w.recv()
            except Exception as e:
                if "interrupted" in str(e).lower():
                    break
                raise

            if packet.is_outbound:
                dst_ip = packet.dst_addr
                dst_port = packet.dst_port
                src_port = packet.src_port

                # In auto-detect mode, the filter already limits to AWS GA ranges
                if not active_server:
                    active_server = (dst_ip, dst_port)
                    print(f"[+] Detected game server: {dst_ip}:{dst_port}")
                    # Reopen with a precise bidirectional filter
                    w.close()
                    precise_filt = (
                        f"udp and ("
                        f"(outbound and ip.DstAddr == {dst_ip} and udp.DstPort == {dst_port}) or "
                        f"(inbound and ip.SrcAddr == 127.0.0.1 and udp.SrcPort == {proxy_port})"
                        f")"
                    )
                    print(f"[*] Reopening with precise filter for {dst_ip}:{dst_port}")
                    w = pydivert.WinDivert(precise_filt)
                    w.open()
                    # The packet we just read is lost, but the game will retransmit
                    continue

                # Redirect outbound to proxy
                nat_table[src_port] = (dst_ip, dst_port)
                packet.dst_addr = "127.0.0.1"
                packet.dst_port = proxy_port
                redirected_count += 1

                if redirected_count <= 5 or redirected_count % 500 == 0:
                    print(f"  -> Redirect #{redirected_count}: {dst_ip}:{dst_port} -> 127.0.0.1:{proxy_port} ({len(packet.payload)} bytes)")

            elif packet.is_inbound:
                dst_port = packet.dst_port

                # Restore original server address on proxy responses
                if dst_port in nat_table:
                    orig_ip, orig_port = nat_table[dst_port]
                    packet.src_addr = orig_ip
                    packet.src_port = orig_port

                    if redirected_count <= 5:
                        print(f"  <- Restore: 127.0.0.1:{proxy_port} -> {orig_ip}:{orig_port}")

            # Re-inject the packet
            try:
                w.send(packet)
            except OSError as e:
                # Some packets can't be re-injected (e.g., loopback issues)
                if redirected_count <= 5:
                    print(f"  [!] Send failed: {e}")
                continue
            packet_count += 1

    except KeyboardInterrupt:
        print(f"\n[*] Stopping...")
    finally:
        w.close()
        print(f"\n[+] WinDivert closed")
        print(f"    Total packets: {packet_count}")
        print(f"    Redirected: {redirected_count}")
        if active_server:
            print(f"    Server: {active_server[0]}:{active_server[1]}")


def main():
    parser = argparse.ArgumentParser(description="UDP redirector for New World DTLS proxy")
    parser.add_argument("--proxy-host", default="127.0.0.1", help="Proxy listen address")
    parser.add_argument("--proxy-port", type=int, default=23971, help="Proxy listen port")
    parser.add_argument("--server-ip", default=None, help="Game server IP to intercept")
    parser.add_argument("--server-port", type=int, default=None, help="Game server port")
    parser.add_argument("--auto", action="store_true", help="Auto-detect from game log or traffic")
    args = parser.parse_args()

    print()
    print("=" * 64)
    print("  New World UDP Redirector (WinDivert)")
    print("=" * 64)

    server_ip = args.server_ip
    server_port = args.server_port

    # Try auto-detect from game log
    if args.auto or (not server_ip):
        detected = detect_server_from_log()
        if detected:
            server_ip, server_port = detected
            print(f"  Detected from game log: {server_ip}:{server_port}")
        else:
            print(f"  No server detected in game log -- will auto-detect from traffic")

    print(f"  Proxy: {args.proxy_host}:{args.proxy_port}")
    if server_ip:
        print(f"  Server: {server_ip}:{server_port}")
    else:
        print(f"  Server: auto-detect (AWS Global Accelerator ranges)")
    print("=" * 64)
    print()

    run_redirect(args.proxy_host, args.proxy_port, server_ip, server_port, args.auto)


if __name__ == "__main__":
    main()
