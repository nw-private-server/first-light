"""
Integrated DTLS proxy capture for New World.

Launches the DTLS proxy and UDP redirector together, monitors the game
log for REP Address, and coordinates everything in one script.

Usage:
    python proxy_capture.py --name my_session

Must be run as Administrator (WinDivert requires kernel access).
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_DIR / "tools"
CAPTURE_DIR = PROJECT_DIR / "capture"
CERTS_DIR = PROJECT_DIR / "server" / "certs"
GAME_LOG = Path(os.environ.get(
    "NW_GAME_LOG",
    str(Path.home() / "AppData" / "Local" / "AGS" / "New World" / "Game.log"),
))


def check_prereqs():
    """Verify everything is in place before starting."""
    errors = []

    cert = CERTS_DIR / "server.crt"
    key = CERTS_DIR / "server.key"
    if not cert.exists() or not key.exists():
        errors.append(f"Certificate not found. Run: python tools/generate_cert.py")

    try:
        import pydivert
    except ImportError:
        errors.append("pydivert not installed. Run: pip install pydivert")

    try:
        from dtls import do_patch
    except ImportError:
        errors.append("python3-dtls not installed. Run: pip install python3-dtls")

    if errors:
        print("[!] Prerequisites missing:")
        for e in errors:
            print(f"    - {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Integrated DTLS proxy capture")
    parser.add_argument("--name", default="proxy_capture", help="Session name")
    parser.add_argument("--port", type=int, default=23971, help="Proxy listen port")
    parser.add_argument("--server-ip", default=None, help="Game server IP (auto-detect from log if not set)")
    parser.add_argument("--server-port", type=int, default=None, help="Game server port")
    args = parser.parse_args()

    # Auto-detect server from game log if not provided
    if not args.server_ip and GAME_LOG.exists():
        import re
        pattern = re.compile(r"REP Address: (\d+\.\d+\.\d+\.\d+):(\d+)")
        with open(GAME_LOG, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = pattern.search(line)
                if m:
                    args.server_ip = m.group(1)
                    args.server_port = int(m.group(2))
        if args.server_ip:
            print(f"[+] Detected server from game log: {args.server_ip}:{args.server_port}")
            print(f"    (If the server IP changes, pass --server-ip and --server-port manually)")
        else:
            print("[!] No REP Address found in game log. Run the game once first,"
                  " or pass --server-ip and --server-port manually.")
            sys.exit(1)

    check_prereqs()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = f"{timestamp}_{args.name}"
    session_dir = CAPTURE_DIR / session_name

    print()
    print("=" * 64)
    print("  New World DTLS Proxy Capture")
    print("=" * 64)
    print(f"  Session:  {session_name}")
    print(f"  Server:   {args.server_ip}:{args.server_port}")
    print(f"  Proxy:    127.0.0.1:{args.port}")
    print(f"  Output:   {session_dir}")
    print("=" * 64)
    print()

    # Copy game log snapshot
    session_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = session_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    if GAME_LOG.exists():
        shutil.copy2(GAME_LOG, logs_dir / "game_log_before.log")

    python = sys.executable
    # Force UTF-8 output in child processes to avoid cp1252 encoding errors
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"

    # Start DTLS proxy
    print("[*] Starting DTLS proxy...")
    proxy_proc = subprocess.Popen(
        [python, str(TOOLS_DIR / "dtls_proxy.py"),
         "--port", str(args.port),
         "--name", f"{session_name}_dtls"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=child_env,
    )

    # Give proxy a moment to bind
    time.sleep(1)

    # Start UDP redirector with known server IP
    print(f"[*] Starting UDP redirector for {args.server_ip}:{args.server_port}...")
    redirect_proc = subprocess.Popen(
        [python, str(TOOLS_DIR / "udp_redirect.py"),
         "--proxy-port", str(args.port),
         "--server-ip", args.server_ip,
         "--server-port", str(args.server_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=child_env,
    )

    # Stream output from both processes
    def stream_output(proc, prefix):
        for line in iter(proc.stdout.readline, b""):
            try:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    print(f"[{prefix}] {text}")
            except Exception:
                pass

    t1 = threading.Thread(target=stream_output, args=(proxy_proc, "PROXY"), daemon=True)
    t2 = threading.Thread(target=stream_output, args=(redirect_proc, "REDIR"), daemon=True)
    t1.start()
    t2.start()

    print()
    print("=" * 64)
    print("  Both services running. Launch New World through Steam now.")
    print("  Press Ctrl+C to stop everything.")
    print("=" * 64)
    print()

    try:
        while True:
            # Check if either process died
            if proxy_proc.poll() is not None:
                print(f"[!] Proxy exited with code {proxy_proc.returncode}")
                break
            if redirect_proc.poll() is not None:
                print(f"[!] Redirector exited with code {redirect_proc.returncode}")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Stopping...")

    # Cleanup
    for proc, name in [(proxy_proc, "Proxy"), (redirect_proc, "Redirector")]:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            print(f"[+] {name} stopped")

    # Save final game log
    if GAME_LOG.exists():
        shutil.copy2(GAME_LOG, logs_dir / "game_log_after.log")

    print()
    print("=" * 64)
    print("  Capture Complete")
    print("=" * 64)
    print(f"  Session: {session_dir}")
    print("=" * 64)


if __name__ == "__main__":
    main()
