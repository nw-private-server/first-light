"""Bare UDP listener for 127.0.0.1:23971 -- the REP port handed back in the
mock login ticket. Logs every datagram (src, length, first 64 bytes hex) to
console + capture/udp_probe_<ts>.log.

Purpose: test whether the region-switch CTD is driven by a failed DTLS
auto-connect. If the game sends anything to this port during a region
switch we'll see it; the first datagram of a DTLS handshake is a plaintext
ClientHello (record type 0x16 = Handshake, version 0xfefd = DTLS 1.2).

Run from an Administrator shell alongside the auth mock (Admin not strictly
required for loopback UDP, but matches the rest of the workflow):

    python tools/udp_probe.py

Ctrl-C when done.
"""

import socket
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT / "capture"
LOG_DIR.mkdir(exist_ok=True)

HOST = "127.0.0.1"
PORT = 23971
BUF = 2048


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"udp_probe_{stamp}.log"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((HOST, PORT))
    except OSError as e:
        sys.exit(f"[-] bind {HOST}:{PORT} failed: {e}")
    sock.settimeout(1.0)

    banner = [
        f"[+] listening on UDP {HOST}:{PORT}",
        f"[+] log: {log_path}",
        "[+] waiting for datagrams. Ctrl-C to stop.",
    ]
    for line in banner:
        print(line)
    with open(log_path, "w", encoding="utf-8") as fh:
        for line in banner:
            fh.write(line + "\n")
        fh.flush()

        try:
            while True:
                try:
                    data, addr = sock.recvfrom(BUF)
                except socket.timeout:
                    continue
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                head = data[:64].hex()
                # DTLS fingerprint: record type (1 byte), version (2 bytes).
                # 16 fefd = DTLS 1.2 handshake. 14 fefd = ChangeCipherSpec.
                fp = ""
                if len(data) >= 3:
                    rt = data[0]
                    ver = (data[1] << 8) | data[2]
                    if rt == 0x16 and ver == 0xFEFD:
                        fp = "  (DTLS 1.2 Handshake)"
                    elif rt == 0x17 and ver == 0xFEFD:
                        fp = "  (DTLS 1.2 ApplicationData)"
                    elif rt == 0x14 and ver == 0xFEFD:
                        fp = "  (DTLS 1.2 ChangeCipherSpec)"
                    elif rt == 0x15 and ver == 0xFEFD:
                        fp = "  (DTLS 1.2 Alert)"
                entry = (
                    f"[{ts}] from {addr[0]}:{addr[1]}  {len(data)}B{fp}\n"
                    f"            {head}"
                )
                print(entry)
                fh.write(entry + "\n")
                fh.flush()
        except KeyboardInterrupt:
            print("\n[+] stopped.")
        finally:
            sock.close()
    print(f"[+] log saved: {log_path}")


if __name__ == "__main__":
    main()
