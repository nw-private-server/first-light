"""
DTLS transport bridge using `openssl s_server` as a subprocess.

Why: python3-dtls doesn't work on Python 3.13 — its SSLConnection server
mode fails to process incoming datagrams. Rather than chase that library
bug, we outsource the DTLS termination to the well-tested `openssl`
binary and pipe plaintext to/from our Python stub.

Architecture:

    Game client                           Python (this module)
        |                                         |
        | UDP:23971 (DTLS)                        |
        v                                         |
    openssl s_server -dtls1_2 -accept 23971       |
        stdin (encrypt)  <---- outbound plaintext | (marshal via
        stdout (decrypt) ----> inbound plaintext  |  server.javelin)
                                                  v
                                        Javelin parser / marshaler

Usage:
    python -m server.dtls_bridge --port 23971

Caveats:
- openssl s_server in stdin/stdout mode handles ONE client at a time.
  For a single-player private server, that's fine.
- We parse each line from stdout as a separate datagram, which is
  only correct when the client sends text-based newline-delimited
  frames. For true binary DTLS payloads we need -quiet + read raw
  bytes. That's what this implementation does: bytes, not lines.

Status (2026-04-17): SKELETON / WIP.
  Standalone `openssl s_server -dtls1_2` + `openssl s_client` handshake
  works (verified — certs accepted, version negotiated). However, when
  wrapping s_server in subprocess.Popen with stdin=PIPE on Windows, the
  handshake does not complete — stdin piping seems to interact badly
  with s_server's event loop. Likely fixes to try later:
    - stdin=DEVNULL (read-only bridge, useful for recv-only testing)
    - Use pty on Linux / ConPTY on Windows instead of pipes
    - Write our own ctypes OpenSSL wrapper
  For now, this file captures the intended architecture and will be
  picked back up once we have end-to-end auth (task #16 blocker).
"""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from server.javelin import (
    MessageRecord,
    SystemMessageId,
    marshal_datagram,
    parse_datagram,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent
CERTS_DIR = PROJECT_DIR / "server" / "certs"
DEFAULT_CERT = CERTS_DIR / "server.crt"
DEFAULT_KEY = CERTS_DIR / "server.key"
JAVELIN_CIPHER = "ECDHE-RSA-AES256-GCM-SHA384"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(tag: str, msg: str) -> None:
    print(f"[{_ts()}] [{tag}] {msg}", flush=True)


# ---------------------------------------------------------------------------
#  openssl s_server wrapper
# ---------------------------------------------------------------------------


class DtlsServer:
    """Wraps `openssl s_server -dtls1_2` as a plaintext stdio transport.

    The subprocess listens on UDP, terminates DTLS, and exposes plaintext
    as stdin/stdout. This class owns the subprocess lifecycle + two
    bridge threads (stdout->queue, stdin<-writes).
    """

    def __init__(
        self,
        port: int,
        cert: Path,
        key: Path,
        cipher: str = JAVELIN_CIPHER,
        openssl_bin: str | None = None,
    ):
        self.port = port
        self.cert = cert
        self.key = key
        self.cipher = cipher
        self.openssl_bin = openssl_bin or shutil.which("openssl")
        if not self.openssl_bin:
            raise RuntimeError("openssl not found in PATH")

        self.proc: subprocess.Popen | None = None
        self._stop_event = threading.Event()
        self._on_datagram = None  # callable(bytes) set by caller

    def start(self, on_datagram) -> None:
        """Spawn openssl s_server. `on_datagram(bytes)` is called from a
        reader thread for every plaintext payload received."""
        self._on_datagram = on_datagram

        cmd = [
            self.openssl_bin, "s_server",
            "-dtls1_2",
            "-accept", str(self.port),
            "-cert", str(self.cert),
            "-key", str(self.key),
            "-cipher", self.cipher,
            "-quiet",            # suppress banner and session info
            "-no_ticket",        # simpler handshake
            # NOTE: intentionally no -Verify / -verify — the client in our
            # pcap sends an empty certificate and uppercase -Verify would
            # require one. Default s_server behavior is to not request.
        ]
        log("dtls", "launching: " + " ".join(cmd))

        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,           # unbuffered binary I/O
        )
        log("dtls", f"subprocess pid={self.proc.pid}, waiting for client...")

        # Reader thread: drain stdout as plaintext datagrams.
        t_out = threading.Thread(target=self._read_stdout, daemon=True)
        t_out.start()

        # Reader thread: mirror stderr to our log.
        t_err = threading.Thread(target=self._read_stderr, daemon=True)
        t_err.start()

    def _read_stdout(self) -> None:
        """openssl s_server -quiet writes the DECRYPTED datagram payload
        to stdout. Each read should correspond to one datagram (but UDP
        boundaries aren't guaranteed via a pipe)."""
        assert self.proc and self.proc.stdout
        while not self._stop_event.is_set():
            try:
                chunk = self.proc.stdout.read(65535)
            except Exception as e:
                log("dtls", f"stdout read error: {e}")
                break
            if not chunk:
                log("dtls", "stdout closed (peer disconnected or process exited)")
                break
            try:
                if self._on_datagram:
                    self._on_datagram(chunk)
            except Exception as e:
                log("dtls", f"handler error: {e}")

    def _read_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        while not self._stop_event.is_set():
            try:
                line = self.proc.stderr.readline()
            except Exception:
                break
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                log("openssl", text)

    def send(self, data: bytes) -> None:
        """Send a plaintext datagram to the client (openssl will encrypt)."""
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("server not running")
        try:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except Exception as e:
            log("dtls", f"stdin write error: {e}")

    def stop(self) -> None:
        self._stop_event.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ---------------------------------------------------------------------------
#  Javelin dispatcher (same logic as stub_server.py, but wired to dtls_bridge)
# ---------------------------------------------------------------------------


class JavelinServer:
    """Plugs the DtlsServer plaintext stream into our Javelin parser."""

    def __init__(self, dtls: DtlsServer):
        self.dtls = dtls
        self.sent_connect_ack = False
        self.packet_count = 0

    def on_datagram(self, data: bytes) -> None:
        self.packet_count += 1
        log("jav", f"<- recv datagram {self.packet_count}, {len(data)} bytes: "
            f"{data[:32].hex()}...")

        result = parse_datagram(data)
        if result.error:
            log("jav", f"   parse error: {result.error}")
            return

        log("jav", f"   parsed {len(result.messages)} record(s), "
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
            log("jav", f"   {summary}")

            if (rec.is_system
                    and rec.system_msg_id == SystemMessageId.SM_CONNECT_REQUEST
                    and not self.sent_connect_ack):
                self.reply_connect_ack()

    def reply_connect_ack(self) -> None:
        payload = b"\x00\x00\x00\x00" + bytes([SystemMessageId.SM_CONNECT_ACK])
        ack = MessageRecord(
            channel=3,
            payload=payload,
            sequence=0,
            reliable_sequence=0,
            reliable=True,
            connecting=True,
        )
        data = marshal_datagram([ack])
        log("jav", f"-> sending SM_CONNECT_ACK, {len(data)} bytes: {data.hex()}")
        self.dtls.send(data)
        self.sent_connect_ack = True


# ---------------------------------------------------------------------------
#  Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=23971)
    ap.add_argument("--cert", default=str(DEFAULT_CERT))
    ap.add_argument("--key", default=str(DEFAULT_KEY))
    ap.add_argument("--openssl", default=None, help="openssl binary path")
    args = ap.parse_args()

    cert = Path(args.cert)
    key = Path(args.key)
    if not cert.exists() or not key.exists():
        print("[!] Missing server cert/key. Run: python tools/generate_cert.py")
        sys.exit(1)

    log("main", "Javelin DTLS bridge starting")
    log("main", f"    port={args.port} cert={cert}")
    log("main", f"    cipher={JAVELIN_CIPHER}")
    log("main", "")

    dtls = DtlsServer(args.port, cert, key, openssl_bin=args.openssl)
    server = JavelinServer(dtls)

    try:
        dtls.start(server.on_datagram)
        # Main thread: keep alive until Ctrl+C or subprocess exits.
        while True:
            if dtls.proc and dtls.proc.poll() is not None:
                log("main", f"openssl subprocess exited with code {dtls.proc.returncode}")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        log("main", "Ctrl+C, stopping.")
    finally:
        dtls.stop()
        log("main", f"{server.packet_count} datagrams processed")


if __name__ == "__main__":
    main()
