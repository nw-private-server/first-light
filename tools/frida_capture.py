"""
Frida-based TLS/DTLS Packet Capture for New World

Spawns or attaches to NewWorld.exe, loads frida_dtls_hook.js, and writes
decrypted packet data to timestamped session directories.

Usage:
    # Spawn game and hook immediately (best for catching early TLS traffic)
    python frida_capture.py

    # Attach to an already-running process (use after game is past EAC init)
    python frida_capture.py --attach

    # Attach by PID
    python frida_capture.py --attach --pid 12345

    # Custom session name
    python frida_capture.py --name dtls_combat_test

Output structure:
    capture/<timestamp>_<name>/
        packets/          -- individual binary packet files
        packets.jsonl     -- one JSON object per packet (metadata)
        session.log       -- human-readable log of all events
        hooks.log         -- hook installation status
"""

import argparse
import json
import os
import signal
import struct
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import frida
except ImportError:
    print("[!] frida not installed. Run: pip install frida-tools")
    sys.exit(1)

# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(r"C:\Users\charl\Programs\NewWorldPrivate")
CAPTURE_DIR = PROJECT_DIR / "capture"
TOOLS_DIR = PROJECT_DIR / "tools"
HOOK_SCRIPT = TOOLS_DIR / "frida_dtls_hook.js"
GAME_EXE = Path(r"H:\SteamLibrary\steamapps\common\New World\Bin64\NewWorld.exe")
DEFAULT_STEAM_APP_ID = "1063730"

# ---------------------------------------------------------------------------
#  Session setup
# ---------------------------------------------------------------------------

def setup_session(name: str) -> Path:
    """Create a timestamped session directory matching the project convention."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = CAPTURE_DIR / f"{timestamp}_{name}"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "packets").mkdir(exist_ok=True)
    return session_dir


class SessionWriter:
    """Manages all output files for a capture session."""

    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.packets_dir = session_dir / "packets"
        self.jsonl_path = session_dir / "packets.jsonl"
        self.log_path = session_dir / "session.log"
        self.hooks_path = session_dir / "hooks.log"
        self.packet_count = 0

        # Open persistent file handles
        self._jsonl = open(self.jsonl_path, "w", encoding="utf-8")
        self._log = open(self.log_path, "w", encoding="utf-8")
        self._hooks = open(self.hooks_path, "w", encoding="utf-8")

        self._write_log(f"Session started: {datetime.now().isoformat()}")
        self._write_log(f"Directory: {session_dir}")

    def close(self):
        for f in (self._jsonl, self._log, self._hooks):
            try:
                f.close()
            except Exception:
                pass

    # -- Logging --

    def _write_log(self, text: str):
        line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {text}"
        self._log.write(line + "\n")
        self._log.flush()
        print(line)

    def log(self, text: str):
        self._write_log(text)

    def log_hook(self, name: str, status: str, detail: str = ""):
        line = f"{name:30s}  {status:12s}  {detail}"
        self._hooks.write(line + "\n")
        self._hooks.flush()
        status_icon = {"success": "+", "not_found": "-", "error": "!"}
        icon = status_icon.get(status, "?")
        self._write_log(f"[{icon}] Hook {name}: {status}" + (f" ({detail})" if detail else ""))

    # -- Packet writing --

    def write_packet(self, meta: dict, raw_data: bytes | None):
        """Write a packet to disk.

        Creates:
          - packets/<seqNo>_<direction>_<protocol>.bin  (raw bytes)
          - One line in packets.jsonl (metadata + filename)
        """
        seq = meta.get("seqNo", self.packet_count)
        direction = meta.get("direction", "unknown")
        protocol = meta.get("protocol", "unknown")
        data_len = meta.get("len", 0)

        # Binary file
        filename = f"{seq:06d}_{direction}_{protocol}.bin"
        bin_path = self.packets_dir / filename

        if raw_data is not None:
            bin_path.write_bytes(raw_data)

        # JSONL entry (metadata only, hex head included for quick inspection)
        entry = {
            "seq": seq,
            "ts": meta.get("ts", datetime.now().isoformat()),
            "direction": direction,
            "protocol": protocol,
            "len": data_len,
            "file": filename,
            "hookName": meta.get("hookName", ""),
            "sslPtr": meta.get("sslPtr", ""),
            "hexHead": meta.get("hexHead", ""),
        }
        self._jsonl.write(json.dumps(entry) + "\n")
        self._jsonl.flush()

        self.packet_count += 1

        # Console summary (compact)
        arrow = "<-" if direction == "read" else "->"
        proto_tag = f"[{protocol.upper():>4s}]"
        print(f"  {proto_tag} {arrow} #{seq:06d}  {data_len:>8d} bytes  {filename}")

        return filename


# ---------------------------------------------------------------------------
#  Frida message handler
# ---------------------------------------------------------------------------

def make_on_message(writer: SessionWriter):
    """Return a closure that handles Frida send() messages."""

    def on_message(message, data):
        if message["type"] == "send":
            payload = message["payload"]
            msg_type = payload.get("type", "")

            if msg_type == "packet":
                writer.write_packet(payload, data)

            elif msg_type == "log":
                writer.log(payload.get("text", ""))

            elif msg_type == "hook_status":
                writer.log_hook(
                    payload.get("name", "?"),
                    payload.get("status", "?"),
                    payload.get("detail", ""),
                )

            else:
                writer.log(f"[frida] Unknown message type: {msg_type}")

        elif message["type"] == "error":
            writer.log(f"[frida:error] {message.get('description', message)}")
            stack = message.get("stack", "")
            if stack:
                writer.log(f"  Stack: {stack}")

        else:
            writer.log(f"[frida] {message}")

    return on_message


# ---------------------------------------------------------------------------
#  Process management
# ---------------------------------------------------------------------------

def find_pid_by_name(name: str = "NewWorld.exe") -> int | None:
    """Find the PID of a running process by name using tasklist."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            parts = line.strip('"').split('","')
            if len(parts) >= 2 and parts[0].lower() == name.lower():
                return int(parts[1])
    except Exception:
        pass
    return None


def spawn_and_attach(writer: SessionWriter) -> tuple:
    """Spawn NewWorld.exe suspended, attach Frida, then resume.

    Returns (session, script, pid).
    """
    if not GAME_EXE.exists():
        writer.log(f"[!] Game executable not found: {GAME_EXE}")
        writer.log("    Update GAME_EXE path in this script.")
        sys.exit(1)

    # Archived / non-EAC targets can regress to Steam launch-context errors if
    # steam_appid.txt is missing. Recreate it on every spawn attempt so the
    # run is self-contained instead of relying on the file to persist.
    steam_appid = GAME_EXE.parent / "steam_appid.txt"
    try:
        steam_appid.write_text(DEFAULT_STEAM_APP_ID, encoding="ascii")
        writer.log(f"[*] Ensured steam_appid.txt at {steam_appid} = {DEFAULT_STEAM_APP_ID}")
    except Exception as e:
        writer.log(f"[!] Failed to write steam_appid.txt: {e}")

    writer.log(f"[*] Spawning: {GAME_EXE}")
    device = frida.get_local_device()
    pid = device.spawn([str(GAME_EXE)])
    writer.log(f"[+] Spawned PID: {pid} (suspended)")

    session = device.attach(pid)
    writer.log(f"[+] Attached to PID {pid}")

    script_source = HOOK_SCRIPT.read_text(encoding="utf-8")
    script = session.create_script(script_source)
    script.on("message", make_on_message(writer))
    script.load()
    writer.log("[+] Hook script loaded")

    writer.log("[*] Resuming process...")
    device.resume(pid)
    writer.log("[+] Process resumed -- game is starting")

    return session, script, pid


def attach_to_running(writer: SessionWriter, pid: int | None = None,
                      process_name: str = "NewWorld.exe") -> tuple:
    """Attach to an already-running NewWorld.exe.

    Returns (session, script, pid).
    """
    if pid is None:
        pid = find_pid_by_name(process_name)
        if pid is None:
            writer.log(f"[!] {process_name} not found running. Launch the game first or use spawn mode.")
            sys.exit(1)

    writer.log(f"[*] Attaching to PID: {pid}")
    device = frida.get_local_device()
    session = device.attach(pid)
    writer.log(f"[+] Attached to PID {pid}")

    script_source = HOOK_SCRIPT.read_text(encoding="utf-8")
    script = session.create_script(script_source)
    script.on("message", make_on_message(writer))
    script.load()
    writer.log("[+] Hook script loaded into running process")

    return session, script, pid


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Capture decrypted TLS/DTLS traffic from New World via Frida"
    )
    parser.add_argument(
        "--attach", action="store_true",
        help="Attach to a running NewWorld.exe instead of spawning it"
    )
    parser.add_argument(
        "--pid", type=int, default=None,
        help="PID to attach to (implies --attach)"
    )
    parser.add_argument(
        "--name", type=str, default="frida_capture",
        help="Session name (used in directory name)"
    )
    parser.add_argument(
        "--exe", type=str, default=None,
        help="Override game executable path"
    )
    parser.add_argument(
        "--process-name", type=str, default="NewWorld.exe",
        help="Process name to search for in attach mode"
    )
    args = parser.parse_args()

    global GAME_EXE
    if args.exe:
        GAME_EXE = Path(args.exe)

    if args.pid is not None:
        args.attach = True

    # Setup session
    session_dir = setup_session(args.name)
    writer = SessionWriter(session_dir)

    print()
    print("=" * 64)
    print("  New World -- Frida TLS/DTLS Capture")
    print("=" * 64)
    print(f"  Session:   {session_dir.name}")
    print(f"  Output:    {session_dir}")
    print(f"  Mode:      {'attach' if args.attach else 'spawn'}")
    print("=" * 64)
    print()

    # Attach or spawn
    try:
        if args.attach:
            session, script, pid = attach_to_running(writer, args.pid, args.process_name)
        else:
            session, script, pid = spawn_and_attach(writer)
    except frida.ProcessNotFoundError:
        writer.log("[!] Process not found. Is the game running?")
        writer.close()
        sys.exit(1)
    except frida.PermissionDeniedError:
        writer.log("[!] Permission denied. Try running as Administrator.")
        writer.close()
        sys.exit(1)
    except Exception as e:
        writer.log(f"[!] Failed to attach: {e}")
        writer.close()
        sys.exit(1)

    writer.log(f"[*] Capturing packets. Press Ctrl+C to stop.")
    writer.log(f"[*] Packets are written to: {session_dir / 'packets'}")
    print()

    # Handle detach gracefully
    session_detached = [False]

    def on_detached(reason):
        session_detached[0] = True
        writer.log(f"[!] Session detached: {reason}")

    session.on("detached", on_detached)

    # Wait for Ctrl+C or process exit
    try:
        while not session_detached[0]:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()
        writer.log("[*] Ctrl+C received, stopping capture...")

    # Cleanup
    try:
        script.unload()
    except Exception:
        pass

    try:
        session.detach()
    except Exception:
        pass

    # Summary
    print()
    print("=" * 64)
    print("  Capture Summary")
    print("=" * 64)
    print(f"  Packets captured:  {writer.packet_count}")
    print(f"  Session directory: {session_dir}")

    # Count by protocol/direction
    if writer.packet_count > 0:
        try:
            counts = {}
            with open(session_dir / "packets.jsonl", "r") as f:
                for line in f:
                    entry = json.loads(line)
                    key = f"{entry['protocol']}:{entry['direction']}"
                    counts[key] = counts.get(key, 0) + 1
            print()
            for key in sorted(counts.keys()):
                print(f"    {key:>20s}: {counts[key]:>6d}")
        except Exception:
            pass

    # File sizes
    total_bytes = 0
    file_count = 0
    for f in (session_dir / "packets").iterdir():
        if f.is_file():
            total_bytes += f.stat().st_size
            file_count += 1
    print(f"\n  Packet files:      {file_count} ({total_bytes:,} bytes)")

    print()
    print("  Output files:")
    for f in sorted(session_dir.iterdir()):
        if f.is_file():
            print(f"    {f.name:30s}  {f.stat().st_size:>10,} bytes")
    print("=" * 64)

    writer.close()


if __name__ == "__main__":
    main()
