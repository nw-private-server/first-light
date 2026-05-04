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
import time
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
    # New informed guesses based on RE'd RegistrationResponseMsg in-memory struct.
    # GridMate uses BE byte order (kCarrierEndian = EndianType::BigEndian).
    # DefaultHandshake's OnInitiate writes just `m_version` (= 5 per captures),
    # but NewWorld uses a custom V3 handshake with additional fields. The
    # in-memory RegistrationResponseMsg has error_code at +0x08 (must be 0)
    # and an EOS flag at +0x5b (must be 0). These variants attempt minimal
    # serializations of the response struct.
    #
    # 9-byte: version + error_code (no session string, no status bytes)
    "v3_min":  b"\x00\x00\x00\x05" b"\x00\x00\x00\x00" b"\x02",
    # 14-byte: version + error_code + str_len(0) + 3 status bytes + eos_flag + msgId
    "v3_full": b"\x00\x00\x00\x05" b"\x00\x00\x00\x00" b"\x00\x00" b"\x00\x00\x00" b"\x00" b"\x02",
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
        # Per-channel outbound sequence + reliable-sequence counters. GridMate
        # increments these per outgoing record on each channel.
        self.out_msg_seq = [0, 0, 0, 0]
        self.out_rel_seq = [0, 0, 0, 0]
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
        # Process start-time anchor so SM_CLOCK_SYNC values are monotonic and
        # within u32 range. GridMate's SyncTime is typically a uint32 of
        # milliseconds since some local epoch (matches the BE u32 we saw the
        # SM_CLOCK_SYNC sender FUN_140f80440 byte-swap before writing).
        self.start_ms = time.monotonic_ns() // 1_000_000

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

    def wrap_envelope_echo(self, body: bytes, echo_seq: int) -> bytes:
        # 2026-05-04: Mixed Nuts noted "you're not handling the sequence
        # number 80 01 0000". Strong reading: our envelope seq should track
        # / acknowledge the client's incoming seq, not start at 0 and walk
        # independently. This variant echoes the client's seq for the
        # datagram we're replying to.
        return ENVELOPE_HEAD + struct.pack(">H", echo_seq & 0xFFFF) + body

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
        # 2026-05-04: Track the latest inbound envelope seq so we can echo
        # it on the reply (Mixed Nuts: "you're not handling the sequence
        # number 80 01 0000"). Strong hypothesis is the server's reply seq
        # should mirror the client's, not walk independently.
        self.last_inbound_env_seq = env.sequence
        # Track the inbound env_seq range so the piggyback ACK record can
        # acknowledge the right span (matches demo: "Last To ACK", "First
        # To ACK"). First-seen seq is the lower bound; latest seq is upper.
        if not hasattr(self, "_inbound_env_first") or self._inbound_env_first is None:
            self._inbound_env_first = env.sequence
        self._inbound_env_last = env.sequence
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

        # 2026-05-04: detect data-channel records (the V3 RegistrationRequest).
        # Per analysis/v3_request/HEADER_DECODE.md, the V3 request lands as a
        # single record with flags & MF_NO_LENGTH (0x40). Log it loud + handle.
        for m in result.messages:
            if m.flags & 0x40:
                self._handle_v3_data_record(m)
                break

    def _handle_v3_data_record(self, m) -> None:
        """Log + reply to an inbound V3 RegistrationRequest record."""
        from javelin.v3_response import V3RegistrationResponse, encode
        # Save a copy to disk so we can RE without needing another live run
        self.v3_request_count = getattr(self, "v3_request_count", 0) + 1
        try:
            outdir = Path(self.log.handlers[0].baseFilename).parent / (
                Path(self.log.handlers[0].baseFilename).stem + "_v3"
            )
            outdir.mkdir(exist_ok=True)
            (outdir / f"v3_req_{self.v3_request_count:03d}.bin").write_bytes(m.payload)
        except Exception as e:
            self.log.debug(f"v3 dump failed: {e}")
        self.log.info(
            f"!! V3 RegistrationRequest #{self.v3_request_count} received: "
            f"ch={m.channel} flags=0x{m.flags:02x} seq={m.sequence} "
            f"rel_seq={m.reliable_sequence} payload_len={len(m.payload)}"
        )

        # Don't spam — only respond to the first one (later retries should
        # stop once the client accepts our reply, but in case it doesn't,
        # rate-limit to one response per second).
        now_ms = time.monotonic_ns() // 1_000_000
        last_sent = getattr(self, "_v3_response_last_ms", 0)
        if now_ms - last_sent < 1000 and last_sent != 0:
            return
        self._v3_response_last_ms = now_ms

        # Build a stub RegistrationResponseMsg. GUESSED FIELDS — likely needs
        # iteration. The 0x60-byte in-memory layout requires error_code=0
        # at +0x08 and eos_flag=0 at +0x5b for the success path. See
        # javelin/v3_response.py for the field-by-field guesses.
        resp = V3RegistrationResponse(session_token=f"sess-{self.v3_request_count:08x}")
        resp_body = encode(resp)

        # Wrap in a data-channel record matching the MF_NO_LENGTH format the
        # client uses (per analysis/v3_request/HEADER_DECODE.md). 3-byte
        # opaque sub-header (we write zeros — semantics unknown), then
        # channel/seq/rel_seq, then the response body extending to end.
        # Mirror the request's channel (the data channel the V3 came in on).
        out_seq = self.v3_request_count - 1  # GUESS: simple counter on this channel
        flags = 0x60  # MF_NO_LENGTH | MF_DATA_CHANNEL (no MF_CONNECTING — past handshake)
        record = (
            bytes([flags]) +
            b"\x00\x00\x00" +  # GUESS: opaque sub-header (client uses 20 00 02)
            bytes([m.channel & 0xFF]) +
            struct.pack(">H", out_seq & 0xFFFF) +
            struct.pack(">H", 0xFFFF) +  # rel_seq sentinel
            resp_body
        )
        if getattr(self, "last_inbound_env_seq", None) is not None:
            datagram = self.wrap_envelope_echo(record, self.last_inbound_env_seq)
        else:
            datagram = self.wrap_envelope(record)
        self.send_app(datagram)
        self.log.info(
            f">> V3RegistrationResponse stub session={resp.session_token!r} "
            f"resp_body_len={len(resp_body)} datagram_len={len(datagram)}"
        )
        self.drain_outbound()

    def _next_seq(self, channel: int, reliable: bool) -> tuple[int, int]:
        """Allocate (seq, rel_seq) for a new outbound record on `channel`."""
        seq = self.out_msg_seq[channel]
        self.out_msg_seq[channel] = (seq + 1) & 0xFFFF
        if reliable:
            rel = self.out_rel_seq[channel]
            self.out_rel_seq[channel] = (rel + 1) & 0xFFFF
        else:
            # Sentinel matches what the captured client sends for non-reliable
            # records (relSeq = 0xFFFF when it doesn't apply).
            rel = 0xFFFF
        return seq, rel

    def send_connect_ack(self) -> None:
        # 2026-05-04: rewritten to match Mixed Nuts' Wireshark dissector
        # capture (analysis docs in the repo). Server reply to client's
        # SM_CONNECT_REQUEST is a SINGLE Carrier datagram with TWO records:
        #
        #   1. SM_CONNECT_ACK on channel 3 — flag 0x21 (MF_RELIABLE +
        #      MF_DATA_CHANNEL), len=5, seq=0, rel_seq=0, payload
        #      `00 00 00 05 02` (4-byte version echo + msgid 0x02).
        #
        #   2. Piggyback SM_CT_ACKS on channel 3 — flag 0x18
        #      (MF_SEQUENTIAL_ID + MF_SEQUENTIAL_REL_ID; channel inherits),
        #      len=6, payload `40 [Last_BE_u16] [First_BE_u16] 06` where
        #      Last/First mark the inbound env_seq range we are acknowledging.
        #
        # Neither MF_CONNECTING nor SM_CLOCK_SYNC. (The previous SM_CLOCK_SYNC
        # we were sending was a guess; the canonical reply is just these two.)
        # Envelope sequence echoes the client's incoming env_seq.
        ack_payload = b"\x00\x00\x00\x05\x02"  # 4-byte version echo + msgid

        connect_ack = MessageRecord(
            channel=3,
            payload=ack_payload,
            sequence=0,
            reliable_sequence=0,
            reliable=True,
            connecting=False,
            num_chunks=1,
            flags_override=0x21,  # MF_RELIABLE | MF_DATA_CHANNEL
        )
        # Build the inline ACK record, range First..Last of inbound env_seqs.
        # Inbound seqs we've seen so far: track via _inbound_env_first /
        # _inbound_env_last. If we haven't seen any (shouldn't happen in
        # this code path), fall back to (current, current).
        first = getattr(self, "_inbound_env_first", self.last_inbound_env_seq)
        last = getattr(self, "_inbound_env_last", self.last_inbound_env_seq)
        ack_inline_payload = (
            b"\x40" + struct.pack(">H", last & 0xFFFF) +
            struct.pack(">H", first & 0xFFFF) + b"\x06"
        )
        ack_inline = MessageRecord(
            channel=3,
            payload=ack_inline_payload,
            sequence=1,
            reliable_sequence=0,
            reliable=False,
            connecting=False,
            num_chunks=1,
            # 0x18 = MF_SEQUENTIAL_ID | MF_SEQUENTIAL_REL_ID. Forces the
            # writer to skip both the seq AND rel_seq u16 fields (they'll
            # be inherited from the previous record on this channel).
            flags_override=0x18,
        )

        body = marshal_datagram([connect_ack, ack_inline])
        if getattr(self, "last_inbound_env_seq", None) is not None:
            datagram = self.wrap_envelope_echo(body, self.last_inbound_env_seq)
        else:
            datagram = self.wrap_envelope(body)
        self.send_app(datagram)
        self.connect_ack_count += 1
        self.log.info(
            f">> SM_CONNECT_ACK+ACK #{self.connect_ack_count} "
            f"first={first} last={last} datagram={datagram.hex()}"
        )
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
