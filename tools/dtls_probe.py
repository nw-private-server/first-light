"""Run `openssl s_server -dtls1_2` bound to 127.0.0.1:23971 (the REP port
the mock login ticket points at). Logs the full handshake + any application
data bytes the game sends after the handshake completes.

Purpose: validate that the game client's DTLS handshake succeeds against
our self-signed `server.crt`. If it does, the next step is wiring plaintext
bytes through to a Javelin protocol parser. If it doesn't, we'll see the
specific TLS alert the client sends (cert rejection, version mismatch,
cipher mismatch, etc.) and know what to fix.

Usage (Administrator PowerShell recommended so the UDP bind is clean):
    python tools/dtls_probe.py

Notes:
- openssl s_server DTLS mode processes one client at a time. That's fine
  for a single-player bring-up.
- We pass -quiet so openssl doesn't write prompts into the stream; -msg
  gives us TLS record dumps; -debug adds raw byte hex.
- Any bytes the game sends AFTER the handshake completes land in
  openssl's stdout (because s_server echoes decrypted application data
  by default). We capture those raw.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
CERTS = PROJECT / "server" / "certs"
LOGS = PROJECT / "capture"
LOGS.mkdir(exist_ok=True)

DEFAULT_CERT = CERTS / "server.crt"
DEFAULT_KEY = CERTS / "server.key"

# Amazon client negotiates ECDHE-RSA-AES256-GCM-SHA384 per the Apr 2026
# capture. Pin it so we reproduce their selection.
JAVELIN_CIPHER = "ECDHE-RSA-AES256-GCM-SHA384"


def find_openssl() -> str:
    cand = shutil.which("openssl")
    if cand:
        return cand
    for p in (r"C:\Program Files\Git\mingw64\bin\openssl.exe",
              r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe"):
        if Path(p).is_file():
            return p
    sys.exit("[-] openssl not found on PATH")


def main() -> None:
    ap = argparse.ArgumentParser(description="DTLS handshake probe")
    ap.add_argument("--port", type=int, default=23971)
    ap.add_argument("--cert", default=str(DEFAULT_CERT))
    ap.add_argument("--key", default=str(DEFAULT_KEY))
    ap.add_argument("--cipher", default=JAVELIN_CIPHER)
    args = ap.parse_args()

    openssl = find_openssl()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS / f"dtls_probe_{stamp}.log"

    cmd = [
        openssl, "s_server",
        "-dtls1_2",
        "-accept", str(args.port),
        "-cert", args.cert,
        "-key", args.key,
        "-cipher", args.cipher,
        "-msg",
        "-debug",
        "-state",
        # -ign_eof: don't tear down the DTLS connection when our stdin
        # reaches EOF (which it does immediately, since stdin is DEVNULL).
        # Without this, s_server writes close_notify the moment the
        # handshake finishes. Valid with DTLS; -rev is TLS-only.
        "-ign_eof",
    ]

    print(f"[+] openssl: {openssl}")
    print(f"[+] listening DTLS 1.2 on 0.0.0.0:{args.port}")
    print(f"[+] cert:  {args.cert}")
    print(f"[+] cipher: {args.cipher}")
    print(f"[+] log: {log_path}")
    print(f"[+] cmd: {' '.join(cmd)}")
    print("=" * 60)
    print("Launch New World, finish character creation, click OK.")
    print("Watch for 'SSL_accept' / 'Ciphers' / raw bytes after handshake.")
    print("Ctrl-C when done.")
    print("=" * 60)

    # s_server exits the instant it sees stdin EOF. DEVNULL EOFs immediately
    # and a synthetic Python pipe (even one held open by a sleeper subprocess)
    # also gets treated as EOF by Git-for-Windows openssl 1.1 — it likely
    # checks _isatty(0) and bails when stdin isn't a console. The flag
    # -ign_eof doesn't help. Manual `openssl s_server` runs from a PowerShell
    # window work because the PS terminal hands openssl a real console
    # handle, so we mimic that by inheriting the parent's stdin (which IS
    # a console when this script is launched from PowerShell/cmd).
    #
    # We still capture stdout via PIPE so we can write raw bytes — using a
    # PowerShell `*>` redirect would re-encode via the OEM codepage and
    # replace every byte >=0x80 with literal '?', destroying ciphertext
    # AND the plaintext openssl echoes after decrypting.
    with open(log_path, "wb") as fh:
        proc = subprocess.Popen(
            cmd,
            stdin=None,  # inherit parent's console handle
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        try:
            assert proc.stdout is not None
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                fh.write(chunk)
                fh.flush()
                try:
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.flush()
                except Exception:
                    pass
        except KeyboardInterrupt:
            print("\n[+] stopping.")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    print(f"[+] log saved: {log_path}")


if __name__ == "__main__":
    main()
