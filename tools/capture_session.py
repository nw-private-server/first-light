"""
New World Traffic Capture Script
Run BEFORE launching the game. Captures:
1. The game log in real-time (auth flow, endpoints, state transitions)
2. Network traffic via tshark (if installed)
3. TLS keys via SSLKEYLOGFILE (if the game respects it)

Usage:
    python capture_session.py [session_name]
"""

import os
import sys
import shutil
import subprocess
import time
import signal
from pathlib import Path
from datetime import datetime

# Paths
PROJECT_DIR = Path(r"C:\Users\charl\Programs\NewWorldPrivate")
CAPTURE_DIR = PROJECT_DIR / "capture"
GAME_LOG = Path(r"C:\Users\charl\AppData\Local\AGS\New World\Game.log")
GAME_EXE = Path(r"C:\Program Files (x86)\Steam\steamapps\common\New World\NewWorld.exe")

def setup_session(name: str) -> Path:
    """Create a timestamped capture session directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = CAPTURE_DIR / f"{timestamp}_{name}"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "logs").mkdir(exist_ok=True)
    (session_dir / "pcaps").mkdir(exist_ok=True)
    (session_dir / "keys").mkdir(exist_ok=True)
    return session_dir


def backup_current_log(session_dir: Path):
    """Copy the current game log as a 'before' snapshot."""
    if GAME_LOG.exists():
        shutil.copy2(GAME_LOG, session_dir / "logs" / "game_log_before.log")
        print(f"[+] Backed up existing game log ({GAME_LOG.stat().st_size} bytes)")


def set_sslkeylog(session_dir: Path) -> str:
    """Set SSLKEYLOGFILE env var and return the path."""
    keylog_path = str(session_dir / "keys" / "sslkeys.log")
    os.environ["SSLKEYLOGFILE"] = keylog_path
    print(f"[+] SSLKEYLOGFILE set to: {keylog_path}")
    return keylog_path


def start_tshark(session_dir: Path) -> subprocess.Popen | None:
    """Start tshark capture if available."""
    tshark = shutil.which("tshark")
    # Wireshark default install path on Windows
    if not tshark:
        default = r"C:\Program Files\Wireshark\tshark.exe"
        if os.path.isfile(default):
            tshark = default
    if not tshark:
        print("[-] tshark not found. Install Wireshark for packet capture.")
        print("    Download: https://www.wireshark.org/download.html")
        print("    (CLI-only: select 'TShark' during install)")
        return None

    pcap_path = str(session_dir / "pcaps" / "capture.pcapng")
    # Capture all TCP traffic - REP port is dynamic (seen 25493, 23971)
    # so we can't filter by port. Filter to known server IP ranges instead.
    # AWS IP ranges used by New World: 35.71.x.x, 18.x.x.x, 52.x.x.x, etc.
    # Safest: capture everything and filter in post-analysis.
    capture_filter = "tcp"

    # On Windows, "-i any" doesn't work. Find active non-loopback interfaces.
    # Use multiple -i flags to capture on all real interfaces.
    interface_args = []
    try:
        result = subprocess.run([tshark, "-D"], capture_output=True, text=True, timeout=10)
        for line in result.stdout.splitlines():
            # Skip loopback and ETW
            if "Loopback" in line or "etwdump" in line:
                continue
            # Extract interface number
            parts = line.split(".", 1)
            if parts[0].strip().isdigit():
                iface_num = parts[0].strip()
                interface_args.extend(["-i", iface_num])
    except Exception:
        # Fallback: just try interface 1
        interface_args = ["-i", "1"]

    if not interface_args:
        interface_args = ["-i", "1"]

    cmd = [
        tshark,
        *interface_args,
        "-f", capture_filter,
        "-w", pcap_path,
        "-q",               # quiet mode
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"[+] tshark capturing to: {pcap_path}")
        print(f"    Filter: {capture_filter}")
        return proc
    except Exception as e:
        print(f"[-] Failed to start tshark: {e}")
        return None


def tail_game_log(session_dir: Path):
    """Monitor the game log for new entries and save them."""
    output_path = session_dir / "logs" / "game_log_session.log"

    if not GAME_LOG.exists():
        print(f"[-] Game log not found at {GAME_LOG}")
        print("    Launch the game first, then restart this script.")
        return

    # Get current file size to only capture new entries
    initial_size = GAME_LOG.stat().st_size
    print(f"[+] Monitoring game log from offset {initial_size}")
    print(f"    New entries will be saved to: {output_path}")
    print()
    print("=" * 60)
    print("Launch New World now. Press Ctrl+C when done playing.")
    print("=" * 60)
    print()

    try:
        with open(output_path, "w", encoding="utf-8") as out:
            last_size = initial_size
            while True:
                current_size = GAME_LOG.stat().st_size
                if current_size > last_size:
                    with open(GAME_LOG, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_size)
                        new_data = f.read(current_size - last_size)
                        out.write(new_data)
                        out.flush()

                        # Print interesting lines to console
                        for line in new_data.splitlines():
                            if any(kw in line.lower() for kw in [
                                "auth", "login", "connect", "gateway",
                                "credential", "session", "ticket", "rep ",
                                "spawn", "world", "error", "warning",
                                "disconnect", "socket", "state"
                            ]):
                                print(f"  {line.strip()}")

                    last_size = current_size
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[+] Stopped monitoring.")

    # Also save final full log
    if GAME_LOG.exists():
        shutil.copy2(GAME_LOG, session_dir / "logs" / "game_log_after.log")
        print(f"[+] Saved final game log")


def main():
    session_name = sys.argv[1] if len(sys.argv) > 1 else "session"

    print("=" * 60)
    print("  New World Traffic Capture")
    print("=" * 60)
    print()

    # Setup
    session_dir = setup_session(session_name)
    print(f"[+] Session directory: {session_dir}")

    backup_current_log(session_dir)
    keylog_path = set_sslkeylog(session_dir)

    # Start packet capture
    tshark_proc = start_tshark(session_dir)

    # Monitor game log
    try:
        tail_game_log(session_dir)
    finally:
        # Cleanup
        if tshark_proc:
            tshark_proc.terminate()
            tshark_proc.wait(timeout=5)
            print("[+] tshark stopped")

        # Summary
        print()
        print("=" * 60)
        print("  Capture Summary")
        print("=" * 60)
        for f in sorted(session_dir.rglob("*")):
            if f.is_file():
                size = f.stat().st_size
                print(f"  {f.relative_to(session_dir)} ({size:,} bytes)")

        keylog = Path(keylog_path)
        if keylog.exists() and keylog.stat().st_size > 0:
            print()
            print("[!!!] SSLKEYLOGFILE has data! TLS decryption is possible!")
        elif keylog.exists():
            print()
            print("[-] SSLKEYLOGFILE exists but is empty — game doesn't dump keys.")
            print("    Will need Frida hooks for TLS decryption.")


if __name__ == "__main__":
    main()
