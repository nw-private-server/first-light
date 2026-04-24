"""Minimal DTLS-terminating Javelin REP responder.

Replaces `openssl s_server` for the post-DTLS bring-up. Listens on UDP,
terminates DTLS 1.2 with our self-signed cert, parses inbound Javelin
datagrams, and replies with the carrier-handshake messages the client
needs to leave state 10.

Currently implemented:
    - DTLS 1.2 server termination via pyOpenSSL memory BIOs
    - Per-peer SSL connection state (single peer expected for bring-up)
    - Inbound parse via parse_envelope + parse_datagram
    - Outbound: SM_CONNECT_ACK (msgId=2) on receipt of SM_CONNECT_REQUEST,
      mirroring the client's `00 00 00 05` prefix as a first guess.
      Iterate this once we observe the client's reaction.

NOT YET implemented:
    - SM_CT_ACKS replies (acknowledging received reliable messages)
    - Encrypted/compressed envelope (type=0x81) — client doesn't use it
      during connect, will revisit if observed
    - Multi-peer (we currently track exactly one peer)

Run from Admin PowerShell (UDP bind requires it on Windows):
    python -m server.rep_responder
"""

from __future__ import annotations

import argparse
import logging
import socket
import struct
import sys
from datetime import datetime
from pathlib import Path

from OpenSSL import SSL

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from server.javelin.frame import (  # noqa: E402
    CarrierEnvelope,
    MessageRecord,
    parse_envelope,
    parse_datagram,
    marshal_datagram,
)


CERT_PATH = PROJECT / "server" / "certs" / "server.crt"
KEY_PATH = PROJECT / "server" / "certs" / "server.key"

DEFAULT_BIND = ("0.0.0.0", 23971)

# Constant Carrier envelope head: 0x80 (plaintext) + 0x01 (proto). The
# remaining 2 bytes are a per-datagram BE u16 sequence we increment on send.
ENVELOPE_HEAD = b"\x80\x01"


# Cipher we know the client negotiates from prior captures.
JAVELIN_CIPHER = "ECDHE-RSA-AES256-GCM-SHA384"


# SM_CONNECT_ACK payload variants to iterate on. Last byte is msgId=0x02
# (the channel-3 system msgId convention).
#
# Result tracking (2026-04-23):
#   "mirror"  -> 00 00 00 05 02       — carrier-acked simple-format, app-rejected
#   "empty"   -> 02                   — carrier-acked extended-format (0x40 flag),
#                                       client briefly stops retrying then resumes
#   "echo"    -> 00 00 00 05 00 02    — same as empty
#   "v0"      -> 00 00 00 00 02       — same as empty
#   "dynamic" -> echoes the client's latest SM_CONNECT_REQUEST body with msgId
#                swapped to 0x02 (handles the per-retry growing body)
ACK_VARIANTS: dict[str, bytes] = {
    "mirror": b"\x00\x00\x00\x05\x02",
    "empty":  b"\x02",
    "echo":   b"\x00\x00\x00\x05\x00\x02",
    "v0":     b"\x00\x00\x00\x00\x02",
    "dynamic": b"",  # marker — actual payload built per send from last request
}


def make_ssl_context() -> SSL.Context:
    ctx = SSL.Context(SSL.DTLS_SERVER_METHOD)
    ctx.use_certificate_file(str(CERT_PATH))
    ctx.use_privatekey_file(str(KEY_PATH))
    ctx.check_privatekey()
    ctx.set_cipher_list(JAVELIN_CIPHER.encode())
    # No client cert verification — game accepts our self-signed cert because
    # the Frida trust-bypass nulls verifyField.
    ctx.set_verify(SSL.VERIFY_NONE, lambda *_: True)
    return ctx


class PeerSession:
    """Per-peer DTLS+Javelin state."""

    def __init__(self, ctx: SSL.Context, peer: tuple, sock: socket.socket,
                 log: logging.Logger, ack_payload: bytes):
        self.peer = peer
        self.sock = sock
        self.log = log
        self.ack_payload = ack_payload
        self.handshake_done = False
        self.out_seq = 0  # outbound Carrier-envelope sequence number
        self.conn = SSL.Connection(ctx, None)
        self.conn.set_accept_state()
        # Counts how many SM_CONNECT_ACK datagrams we've sent. Don't gate
        # at one — if the client rejects our first ACK, it'll keep retrying
        # SM_CONNECT_REQUEST and we should keep ACKing so the iteration loop
        # converges as we tweak the payload.
        self.connect_ack_count = 0
        # For the "dynamic" variant: track the latest SM_CONNECT_REQUEST body
        # we've seen. The body grows by one 0x01 per retry; we mirror it back.
        self.last_request_body: bytes = b""

    # ---------- BIO bridging ----------

    def feed(self, datagram: bytes) -> None:
        """Push a UDP datagram from the wire into the SSL state machine."""
        try:
            self.conn.bio_write(datagram)
        except SSL.Error as e:
            self.log.warning(f"bio_write failed: {e}")

    def drain_outbound(self) -> None:
        """Send any encrypted bytes the SSL state machine wants to emit."""
        while True:
            try:
                chunk = self.conn.bio_read(65535)
            except SSL.WantReadError:
                return
            except SSL.Error as e:
                self.log.warning(f"bio_read failed: {e}")
                return
            if not chunk:
                return
            try:
                self.sock.sendto(chunk, self.peer)
            except OSError as e:
                self.log.warning(f"sendto failed: {e}")
                return

    # ---------- handshake ----------

    def try_handshake(self) -> None:
        if self.handshake_done:
            return
        try:
            self.conn.do_handshake()
            self.handshake_done = True
            self.log.info(f"handshake complete cipher={self.conn.get_cipher_name()}")
        except SSL.WantReadError:
            pass
        except SSL.Error as e:
            self.log.error(f"handshake error: {e}")

    # ---------- application data ----------

    def read_app(self) -> bytes:
        """Read any decrypted application data the SSL state machine has buffered."""
        try:
            return self.conn.recv(65535)
        except SSL.WantReadError:
            return b""
        except SSL.ZeroReturnError:
            return b""

    def send_app(self, data: bytes) -> None:
        """Encrypt and queue application data for transmission."""
        try:
            self.conn.send(data)
        except SSL.Error as e:
            self.log.warning(f"send failed: {e}")

    # ---------- Javelin layer ----------

    def wrap_envelope(self, body: bytes) -> bytes:
        seq = self.out_seq & 0xFFFF
        self.out_seq = (self.out_seq + 1) & 0xFFFF
        return ENVELOPE_HEAD + struct.pack(">H", seq) + body

    def handle_decrypted_datagram(self, raw: bytes) -> None:
        try:
            env, body = parse_envelope(raw)
        except ValueError as e:
            self.log.warning(f"bad envelope: {e} raw={raw.hex()}")
            return
        result = parse_datagram(body)
        if result.error:
            self.log.warning(f"parse error: {result.error} body={body.hex()}")
            return
        self.log.info(
            f"<< env_seq={env.sequence} msgs={len(result.messages)} "
            + " ".join(
                f"[ch={m.channel} sysmsg={m.system_msg_id} payload={m.payload.hex()}]"
                for m in result.messages
            )
        )
        # ACK every SM_CONNECT_REQUEST we see. While we're iterating on the
        # payload, the client keeps retrying because it hasn't accepted our
        # ACK yet — so we should keep sending too.
        for m in result.messages:
            if m.is_system and m.system_msg_id == 1:
                # Strip the trailing msgId byte; the body is everything before it.
                self.last_request_body = m.payload[:-1]
                self.send_connect_ack()
                break

    def send_connect_ack(self) -> None:
        # SM_CONNECT_ACK payload chosen by --ack-variant flag. The msgId
        # (0x02) goes LAST per the channel-3 system-message convention.
        # The "dynamic" variant mirrors the latest SM_CONNECT_REQUEST body
        # byte-for-byte and substitutes the msgId.
        if self.ack_payload == b"":  # dynamic mode marker
            payload = self.last_request_body + b"\x02"
        else:
            payload = self.ack_payload
        rec = MessageRecord(
            channel=3,
            payload=payload,
            sequence=0,
            reliable_sequence=0xFFFF,
            reliable=False,
            connecting=True,
            num_chunks=1,
        )
        body = marshal_datagram([rec])
        datagram = self.wrap_envelope(body)
        self.send_app(datagram)
        self.connect_ack_count += 1
        self.log.info(f">> SM_CONNECT_ACK #{self.connect_ack_count} datagram={datagram.hex()}")
        self.drain_outbound()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind-host", default=DEFAULT_BIND[0])
    ap.add_argument("--bind-port", type=int, default=DEFAULT_BIND[1])
    ap.add_argument("--verbose", "-v", action="count", default=0)
    ap.add_argument("--ack-variant", default="mirror", choices=sorted(ACK_VARIANTS),
                    help="which SM_CONNECT_ACK payload to send")
    args = ap.parse_args()
    ack_payload = ACK_VARIANTS[args.ack_variant]

    log_dir = PROJECT / "capture"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"responder_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("rep_responder")
    log.setLevel(logging.DEBUG if args.verbose >= 2 else logging.INFO)
    file_h = logging.FileHandler(log_path, encoding="utf-8")
    file_h.setFormatter(fmt)
    log.addHandler(file_h)
    stream_h = logging.StreamHandler(sys.stdout)
    stream_h.setFormatter(fmt)
    log.addHandler(stream_h)
    log.info(f"log file: {log_path}")

    if not CERT_PATH.is_file() or not KEY_PATH.is_file():
        log.error(f"cert/key missing: {CERT_PATH} / {KEY_PATH}")
        return 1

    ctx = make_ssl_context()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind_host, args.bind_port))
    sock.settimeout(0.1)
    log.info(f"listening DTLS 1.2 on udp/{args.bind_host}:{args.bind_port}")
    log.info(f"cert: {CERT_PATH}")
    log.info(f"ack variant: {args.ack_variant} payload={ack_payload.hex()}")

    sessions: dict[tuple, PeerSession] = {}

    try:
        while True:
            try:
                data, peer = sock.recvfrom(65535)
            except socket.timeout:
                # Drive periodic work for every active session.
                for sess in list(sessions.values()):
                    sess.drain_outbound()
                continue
            except OSError as e:
                log.warning(f"recvfrom failed: {e}")
                continue

            sess = sessions.get(peer)
            if sess is None:
                log.info(f"new peer {peer}")
                sess = PeerSession(ctx, peer, sock, log, ack_payload)
                sessions[peer] = sess

            sess.feed(data)
            sess.try_handshake()
            sess.drain_outbound()

            if sess.handshake_done:
                while True:
                    plaintext = sess.read_app()
                    if not plaintext:
                        break
                    sess.handle_decrypted_datagram(plaintext)
                sess.drain_outbound()
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
