"""
Attach to a running NewWorld.exe and apply the in-memory DTLS trust patch.

Usage:
    python tools/frida_dtls_trust_patch.py
    python tools/frida_dtls_trust_patch.py --pid 12345

Recommended workflow:
1. Launch the game normally.
2. Wait until EAC/startup is finished and the game is at character select.
3. Run this script.
4. Click Play / continue into REP.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

try:
    import frida
except ImportError:
    print("[!] frida not installed. Run: pip install frida-tools")
    raise SystemExit(1)


PROJECT_DIR = Path(__file__).resolve().parent.parent
HOOK_PATH = PROJECT_DIR / "tools" / "frida_dtls_trust_patch.js"


def find_pid_by_name(name: str = "NewWorld.exe") -> int | None:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None

    for line in result.stdout.strip().splitlines():
        parts = line.strip('"').split('","')
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            try:
                return int(parts[1])
            except ValueError:
                return None
    return None


def on_message(message, data):
    if message["type"] == "send":
        payload = message["payload"]
        kind = payload.get("type")
        if kind == "log":
            print(f"[*] {payload.get('text', '')}")
        elif kind == "status":
            prefix = "[+]" if payload.get("ok") else "[!]"
            print(f"{prefix} {payload.get('text', '')}")
        else:
            print(f"[*] {payload}")
    elif message["type"] == "error":
        print("[!] Frida error:")
        print(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, help="Attach to this PID instead of auto-discovering NewWorld.exe")
    args = parser.parse_args()

    pid = args.pid or find_pid_by_name()
    if not pid:
        print("[!] Could not find a running NewWorld.exe")
        return 1

    print(f"[*] Attaching to PID {pid}")
    session = frida.attach(pid)
    script = session.create_script(HOOK_PATH.read_text(encoding="utf-8"))
    script.on("message", on_message)
    script.load()

    print("[*] Patch script loaded. Waiting briefly for status...")
    time.sleep(2)
    session.detach()
    print("[*] Detached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
