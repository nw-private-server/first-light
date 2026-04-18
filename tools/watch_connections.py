"""
Watch outbound TCP SYNs and DNS queries live via tshark.

Purpose: between the auth mock's /credentials/omni response and the silent CTD,
the game is doing *something* on the network. This captures only connection
initiations (SYN without ACK) and DNS queries (UDP 53, qry not response), so
the output stays narrow and readable while the game runs.

Run in Administrator PowerShell alongside the auth mock:
    python tools\watch_connections.py

Output is printed live and also written to capture\watch_connections_<ts>.log.
Ctrl-C when the CTD happens.
"""

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT / "capture"
LOG_DIR.mkdir(exist_ok=True)


def find_tshark() -> str:
    for cand in (shutil.which("tshark"), r"C:\Program Files\Wireshark\tshark.exe"):
        if cand and Path(cand).is_file():
            return cand
    sys.exit("[-] tshark not found. Install Wireshark (include TShark).")


def active_interfaces(tshark: str) -> list[str]:
    out = subprocess.run([tshark, "-D"], capture_output=True, text=True, timeout=10).stdout
    ifaces = []
    for line in out.splitlines():
        if "Loopback" in line or "etwdump" in line or "Npcap" not in line and "USBPcap" in line:
            continue
        m = re.match(r"\s*(\d+)\.", line)
        if m:
            ifaces.append(m.group(1))
    return ifaces or ["1"]


def main():
    tshark = find_tshark()
    ifaces = active_interfaces(tshark)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"watch_connections_{stamp}.log"

    # SYN without ACK = outbound TCP connection initiations.
    # DNS query (not response) = hostname lookups.
    capture_filter = (
        "(tcp[tcpflags] & tcp-syn != 0 and tcp[tcpflags] & tcp-ack == 0) "
        "or (udp port 53)"
    )

    iface_args = []
    for i in ifaces:
        iface_args += ["-i", i]

    cmd = [
        tshark,
        *iface_args,
        "-f", capture_filter,
        "-l",  # line-buffered
        "-n",  # don't resolve IPs/ports (faster, and we want raw destinations)
        "-T", "fields",
        "-e", "frame.time",
        "-e", "ip.src",
        "-e", "ip.dst",
        "-e", "tcp.dstport",
        "-e", "dns.qry.name",
        "-E", "separator=|",
    ]

    print(f"[+] tshark: {tshark}")
    print(f"[+] interfaces: {','.join(ifaces)}")
    print(f"[+] log: {log_path}")
    print(f"[+] filter: SYN(no-ACK) or DNS")
    print("=" * 60)
    print("Launch the game now. Ctrl-C after the CTD.")
    print("=" * 60)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        with open(log_path, "w", encoding="utf-8") as fh:
            for raw in proc.stdout:
                parts = raw.rstrip("\n").split("|")
                if len(parts) < 5:
                    continue
                ts, src, dst, dport, qry = parts[0], parts[1], parts[2], parts[3], parts[4]
                # Extract HH:MM:SS.ffff from tshark's long timestamp format.
                m = re.search(r"(\d{2}:\d{2}:\d{2}\.\d+)", ts)
                short_ts = m.group(1)[:12] if m else ts[:12]
                if qry:
                    line = f"[{short_ts}] DNS query: {qry}"
                elif dport:
                    line = f"[{short_ts}] SYN -> {dst}:{dport}  (from {src})"
                else:
                    continue
                print(line)
                fh.write(line + "\n")
                fh.flush()
    except KeyboardInterrupt:
        print("\n[+] Stopped.")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    print(f"[+] Log saved: {log_path}")


if __name__ == "__main__":
    main()
