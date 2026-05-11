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
from server.javelin import dispatch as _dispatch  # noqa: E402
from server.javelin.replay_store import ReplayStore, ReplayMessage  # noqa: E402
from server.javelin.v3_request import V3RegistrationRequest  # noqa: E402
from server.javelin.wire import (  # noqa: E402
    chunk_replay_payload as _chunk_replay_payload,
    encode_vlq32 as _encode_vlq32,
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
                 log: logging.Logger, ack_payload: bytes, ack_form: str = "mn",
                 v3_resp_flag: int = 0x21, v3_resp_channel=None,
                 v3_resp_subheader: str = "000000",
                 v3_piggyback_ack: bool = True,
                 replay_store: ReplayStore | None = None,
                 replay_max_seq: int = 0x24,
                 replay_interval_ms: int = 50):
        self.peer = peer
        self.sock = sock
        self.log = log
        self.ack_payload = ack_payload
        # Connect-ACK form selector. "mn" = Mixed Nuts (flag 0x21, rel_seq=0,
        # real-server form). "alt" = community dump's form (flag 0xa0,
        # rel_seq=0xFFFF). See project_22_phase_post_registration.md.
        self.ack_form = ack_form
        # V3 RegistrationResponse wrap parameters. Settable via CLI for
        # rapid iteration without code changes.
        self.v3_resp_flag = v3_resp_flag
        self.v3_resp_channel = v3_resp_channel
        # 3-byte hex string for the data-channel sub-header (only used
        # when the V3 response flag has MF_NO_LENGTH set). Client uses
        # "200002" for V3 retries — mirroring may help.
        self.v3_resp_subheader = v3_resp_subheader
        # Bundle a Carrier-level piggyback ACK record alongside the V3
        # RegistrationResponse in the same envelope. Mixed Nuts' working
        # server sends `20 00 00 06 03 00 03 00 00 40 00 0c 00 02 06`
        # (flag 0x20 ch=3 sysmsg ACK) bundled with the V3 reply. We don't
        # currently — testing whether this is what makes the client stop
        # retrying V3 (per docs/next-session.md "cheapest first action").
        self.v3_piggyback_ack = v3_piggyback_ack
        # Replay-substitution: a SubstitutionContext built from the first V3
        # request, used to fill XX placeholders in captured replay messages
        # at seq >= 0x25. None until V3 fields are parseable.
        self.substitution_ctx = None
        self.character_display_name = "NWPrivateTester01"
        self.replay_include_redacted = False
        # Default chunk-payload size for MF_CHUNKS replay. Matches the
        # ~1115 B per-chunk size the real server uses for WORLD DATA per
        # docs/community/community_state_machine_dump.txt.
        self.replay_chunk_size = 1100
        # Threshold above which we switch to MF_CHUNKS. Set just under the
        # DTLS 1.2 plaintext cap of 16 384 (SSL3_RT_MAX_PLAIN_LENGTH) so
        # a single replay record + record header fits a single DTLS frame.
        self.replay_single_record_limit = 14000
        # Post-replay heartbeat: after the replay queue drains, re-send a
        # captured small message every N ms to keep the client from cleanly
        # disconnecting (`SM_DISCONNECT reason=0`) when the server falls
        # silent post-load. 0 disables. Captured 0x15d (12 B) is the
        # default heartbeat candidate (most frequent small R-msg in the
        # dump). See project_render_destroy_was_normal_teardown.md.
        self.post_replay_heartbeat_ms = 500
        self._heartbeat_msg: ReplayMessage | None = None
        self._next_heartbeat_at: float = 0.0
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
        # 2026-05-04: Post-V3 replay state. After our V3 RegistrationResponse
        # is sent and the deserializer accepts it (Frida-confirmed), we replay
        # the captured 0x2..max_seq R-direction messages from Mixed Nuts'
        # working login dump. Tests the hypothesis that the use-after-free at
        # NewWorld+0x61ae9b5 is downstream of "client stuck waiting for the
        # post-registration init burst".
        self.replay_store = replay_store
        self.replay_max_seq = replay_max_seq
        self.replay_interval_s = replay_interval_ms / 1000.0
        self.replay_queue: list[ReplayMessage] = []
        self.replay_started = False
        self._next_replay_at: float = 0.0

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
        # Suppress repeated bare keepalive-ACK datagrams: when the only
        # message is sysmsg=6 (SM_CT_ACKS) and the payload matches the
        # last bare-ack we logged, downgrade to debug level. Anything else
        # — multi-msg datagrams, sysmsg != 6, payload changes — logs at
        # info level normally. Helps reduce noise with heartbeats running.
        is_bare_ack = (
            len(result.messages) == 1
            and result.messages[0].channel == 3
            and result.messages[0].system_msg_id == 6
        )
        msg_summary = " ".join(
            f"[ch={m.channel} sysmsg={m.system_msg_id} payload={m.payload.hex()}]"
            for m in result.messages
        )
        line = f"<< env_seq={env.sequence} msgs={len(result.messages)} {msg_summary}"
        if is_bare_ack and getattr(self, "_last_bare_ack_summary", None) == msg_summary:
            self._suppressed_bare_acks = getattr(self, "_suppressed_bare_acks", 0) + 1
            self.log.debug(line)
        else:
            suppressed = getattr(self, "_suppressed_bare_acks", 0)
            if suppressed:
                self.log.info(f"<< (... {suppressed} repeated bare ACKs suppressed)")
                self._suppressed_bare_acks = 0
            self.log.info(line)
            self._last_bare_ack_summary = msg_summary if is_bare_ack else None
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

        # Wake 157: parallel shadow-decode through the central dispatcher.
        # No behavior change — for each inbound record, try to sniff a
        # typed-envelope header and call `dispatch.decode_replay_message`,
        # logging success/failure. This validates the dispatcher against
        # live traffic before any later wake routes the responder through
        # it for real.
        for m in result.messages:
            self._shadow_decode_record(m)

    def _shadow_decode_record(self, m: MessageRecord) -> None:
        """Try to decode an inbound record through the central dispatcher.

        Sniffs the typed-envelope header (`[0x00, 0x01, (id & 0x3f) | 0x80,
        id >> 6]`) at the start of `m.payload`. If present, calls
        `dispatch.decode_replay_message(type_id, "R", payload)` and logs
        the outcome at debug level. Never raises; never affects runtime
        behavior. Records without a typed-envelope prefix (system msgs,
        V3 request, etc.) are silently skipped.
        """
        payload = m.payload
        if len(payload) < 4 or payload[0] != 0x00 or payload[1] != 0x01:
            return
        # Decode the type_id from bytes [2,3]: low 6 bits | high bits << 6
        b2, b3 = payload[2], payload[3]
        if not (b2 & 0x80):
            return
        type_id = (b2 & 0x3f) | (b3 << 6)
        if type_id not in _dispatch.DECODERS:
            self.log.debug(
                f"[shadow] type_id=0x{type_id:x} not in dispatcher "
                f"(len={len(payload)})"
            )
            return
        try:
            decoded = _dispatch.decode_replay_message(type_id, "R", payload)
        except Exception as e:  # noqa: BLE001 — log-only, no rethrow
            self.log.debug(
                f"[shadow] type_id=0x{type_id:x} decode failed: "
                f"{type(e).__name__}: {e}"
            )
            return
        self.log.debug(
            f"[shadow] type_id=0x{type_id:x} -> "
            f"{type(decoded).__name__ if decoded is not None else 'None'}"
        )

    def _validate_dispatcher_heartbeat_encode_matches(self) -> None:
        """Wake 187 phase-2B foundation: confirm the central dispatcher's
        encoder produces byte-identical output to the captured heartbeat
        message we're about to replay. Logging-only; never raises.

        The path that would replace `_send_replay_message(msg)` for the
        heartbeat case is:
            decoded = _dispatch.decode_replay_message(0x15d, "R", body)
            new_body = _dispatch.encode_replay_message(0x15d, decoded)
            ... wrap new_body in the Carrier envelope and send ...

        This validation runs that decode → encode round-trip against the
        cached `_heartbeat_msg.body` and asserts byte-equality. If
        equality holds, a future wake can swap the emission path with
        confidence. If it fails, the failure surfaces here at startup
        with the diff bytes, not later as a wire-level surprise.
        """
        msg = self._heartbeat_msg
        if msg is None or msg.type_id != 0x15d:
            return
        try:
            decoded = _dispatch.decode_replay_message(0x15d, "R", msg.body)
            if decoded is None:
                self.log.debug(
                    "[phase-2B] dispatcher returned None for heartbeat 0x15d; "
                    "expected HeartbeatPing15D"
                )
                return
            roundtripped = _dispatch.encode_replay_message(0x15d, decoded)
        except Exception as e:  # noqa: BLE001 — log-only, never raise
            self.log.warning(
                f"[phase-2B] dispatcher heartbeat round-trip failed: "
                f"{type(e).__name__}: {e}"
            )
            return
        if roundtripped == msg.body:
            self.log.info(
                "[phase-2B] dispatcher encoder produces byte-identical "
                f"heartbeat ({len(roundtripped)} bytes) — emission-path swap "
                f"would be safe."
            )
        else:
            # Diff the first differing offset for diagnosis.
            diff_at = next(
                (i for i, (a, b) in enumerate(zip(msg.body, roundtripped))
                 if a != b),
                min(len(msg.body), len(roundtripped)),
            )
            self.log.warning(
                f"[phase-2B] dispatcher heartbeat encode differs from "
                f"captured: lens {len(msg.body)} vs {len(roundtripped)}, "
                f"first diff at offset 0x{diff_at:x}. NOT safe to swap."
            )

    def _handle_v3_data_record(self, m) -> None:
        """Log + reply to an inbound V3 RegistrationRequest record."""
        try:
            self._handle_v3_data_record_inner(m)
        except Exception:
            import traceback
            self.log.error(
                "V3 handler crashed:\n" + traceback.format_exc()
            )
            raise

    def _handle_v3_data_record_inner(self, m) -> None:
        from server.javelin.v3_response import V3RegistrationResponse, encode
        from server.javelin.v3_request import parse_v3_request
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
        # Decode and log the visible fields so we can compare against
        # what the game sends each retry. Only log on the first retry
        # to keep noise down.
        if self.v3_request_count == 1:
            try:
                req = parse_v3_request(m.payload)  # noqa: F811
                # Print just the readable string fields (skip large bytes blobs)
                summary = {
                    f.name: getattr(req, f.name)
                    for f in req.__dataclass_fields__.values()
                    if isinstance(getattr(req, f.name), str)
                }
                self.log.info(f"   V3 fields: {summary}")
            except Exception as e:
                self.log.warning(f"   V3 decode failed: {e!r}")

        # Don't spam — only respond to the first one (later retries should
        # stop once the client accepts our reply, but in case it doesn't,
        # rate-limit to one response per second).
        now_ms = time.monotonic_ns() // 1_000_000
        last_sent = getattr(self, "_v3_response_last_ms", 0)
        if now_ms - last_sent < 1000 and last_sent != 0:
            return
        self._v3_response_last_ms = now_ms

        # 2026-05-04: Build the RegistrationResponseMsg using bytes captured
        # from a real successful login (Mixed Nuts shared docs/community/
        # nw-login-safe/messages-redacted.txt seq 0x1). 88-byte body:
        #   00 01 03 [4B error] [8B mystery] 20 [32B session] 23 [35B ver] 01 00 00 01
        # See javelin/v3_response.py for the exact template.
        from server.javelin.v3_response import make_session_token
        # Try echoing the request's session_uuid (after stripping dashes) as
        # the response session_token. Both are 32 hex chars = 32 bytes.
        # If not echoable from request, fall back to random.
        token = make_session_token()
        req: V3RegistrationRequest | None = None
        try:
            req = parse_v3_request(m.payload)
            sess_uuid_no_dashes = req.session_uuid.replace("-", "")
            if len(sess_uuid_no_dashes) == 32:
                token = sess_uuid_no_dashes.encode("ascii")
        except Exception as e:
            self.log.debug(f"v3 session_uuid strict-parse failed: {e!r}")
            # Lenient fallback: scan the body for the session UUID + persona-id.
            # The strict parser fails when body length diverges from 832 B
            # (live first-attempt is 835 B, retries are 829-838 B), but the
            # identity fields are still recoverable by regex.
            from server.javelin.v3_request import parse_v3_request_lenient
            req = parse_v3_request_lenient(m.payload)
            if req and req.session_uuid:
                sess_uuid_no_dashes = req.session_uuid.replace("-", "")
                if len(sess_uuid_no_dashes) == 32:
                    token = sess_uuid_no_dashes.encode("ascii")
                    self.log.info(
                        f"   V3 lenient-extracted session_uuid={req.session_uuid}"
                    )
        resp = V3RegistrationResponse(session_token=token)
        resp_body = encode(resp)

        # Build the replay-substitution context once per session, the first
        # time we successfully parse identity fields from the V3 request.
        # Subsequent V3 retries (the 0xfc replay-bounce form) won't overwrite
        # it. Spans in the captured replay messages get filled with these
        # live values so the post-V3 replay can extend past seq 0x24 without
        # leaking the captured player's real identity.
        if req is not None and getattr(self, "substitution_ctx", None) is None:
            try:
                from server.javelin.replay_substitution import (
                    SubstitutionContext, _digest_for_diagnostics,
                )
                self.substitution_ctx = SubstitutionContext.from_v3_and_session(
                    req=req,
                    session_token=token,
                    character_display_name=self.character_display_name,
                )
                self.log.info(
                    f"   substitution_ctx armed: "
                    f"{_digest_for_diagnostics(self.substitution_ctx)}"
                )
                for w in self.substitution_ctx.warnings:
                    self.log.debug(f"   substitution warning: {w}")
            except Exception as e:
                self.log.warning(f"   substitution_ctx build failed: {e!r}")
                self.substitution_ctx = None

        # 2026-05-04 round 3: response wrap iteration via --v3-resp-flag /
        # --v3-resp-channel CLI flags. Empirical results so far:
        #   - flag 0x21 + ch=3 + length-field: 15 retries -> TIMEOUT (0x00)
        #   - flag 0xe0 + ch=3 + no-length:    immediate BAD_PACKETS (0x02)
        # Flag 0x21 is the default (less bad). Untried options to iterate
        # via CLI: 0x60 (MF_NO_LENGTH alone, no CONNECTING), 0xa0
        # (CONNECTING + DATA_CHANNEL with length field), channel 0/1/2.
        # 2026-05-04 Mixed Nuts confirmed S->C format:
        #   [Carrier record header][message_size:VLQ32][typed_envelope...]
        # Channel is 0 (data), NOT 3 (system). Without the VLQ32 size
        # prefix, the client mis-dispatched the message and silently
        # ignored it. Prepend the VLQ32 size byte and put the record on
        # channel 0 by default.
        out_seq = getattr(self, "_v3_response_seq", 0)
        self._v3_response_seq = (out_seq + 1) & 0xFFFF
        flags = self.v3_resp_flag
        ch = self.v3_resp_channel if self.v3_resp_channel is not None else 0
        # VLQ32: 1-5 byte little-endian variable-length integer. For < 128
        # values (our 88-byte body) it's a single byte with the top bit
        # clear. resp_body length is always 88 for the default response.
        msg_size = len(resp_body)
        vlq32 = _encode_vlq32(msg_size)
        envelope_body = vlq32 + resp_body
        no_length = bool(flags & 0x40)
        if no_length:
            # MF_NO_LENGTH form: 3-byte sub-header, no length u16, payload
            # extends to end of datagram.
            sub = bytes.fromhex(self.v3_resp_subheader.replace("0x", ""))
            assert len(sub) == 3, f"v3-resp-subheader must be 3 bytes, got {len(sub)}"
            record = (
                bytes([flags]) +
                sub +
                bytes([ch & 0xFF]) +
                struct.pack(">H", out_seq & 0xFFFF) +
                struct.pack(">H", 0xFFFF) +     # rel_seq sentinel like client
                envelope_body
            )
        else:
            # Standard form: u16 length right after flag. Length covers
            # the VLQ32 prefix + typed envelope (Mixed Nuts sample
            # `21 00 59 ...` = size 89 = 1B VLQ + 88B body).
            record = (
                bytes([flags]) +
                struct.pack(">H", len(envelope_body)) +
                bytes([ch & 0xFF]) +
                struct.pack(">H", out_seq & 0xFFFF) +
                struct.pack(">H", 0) +          # rel_seq starts at 0 for reliable
                envelope_body
            )
        # Optionally append a Carrier-level piggyback ACK record (flag 0x20
        # ch=3 sysmsg) acknowledging the inbound env_seq range we've seen.
        # Mirrors Mixed Nuts' working bundle byte-for-byte:
        #   20 00 06 03 [seq] [rel_seq=0] 40 [last_env_be] [first_env_be] 06
        # The 0x40 marker is AckRange, msgid 0x06 is SM_CT_ACKS. Goal:
        # confirm to the client that we received its V3 RegistrationRequest
        # at the carrier layer so it stops retrying every ~500ms.
        ack_record_bytes = b""
        ack_log = ""
        if self.v3_piggyback_ack:
            first_env = getattr(self, "_inbound_env_first",
                                getattr(self, "last_inbound_env_seq", 0))
            last_env = getattr(self, "_inbound_env_last",
                               getattr(self, "last_inbound_env_seq", 0))
            ack_seq = self.out_msg_seq[3]
            self.out_msg_seq[3] = (ack_seq + 1) & 0xFFFF
            ack_inline_payload = (
                b"\x40" + struct.pack(">H", last_env & 0xFFFF) +
                struct.pack(">H", first_env & 0xFFFF) + b"\x06"
            )
            ack_record_bytes = (
                bytes([0x20]) +                                  # MF_DATA_CHANNEL
                struct.pack(">H", len(ack_inline_payload)) +     # size = 6
                bytes([3]) +                                     # channel 3
                struct.pack(">H", ack_seq & 0xFFFF) +
                struct.pack(">H", 0) +                           # rel_seq = 0
                ack_inline_payload
            )
            ack_log = (
                f" piggyback_ack=[seq={ack_seq} ack_range=({first_env}..{last_env})]"
            )
        record = record + ack_record_bytes

        if getattr(self, "last_inbound_env_seq", None) is not None:
            datagram = self.wrap_envelope_echo(record, self.last_inbound_env_seq)
        else:
            datagram = self.wrap_envelope(record)
        self.send_app(datagram)
        self.log.info(
            f">> V3RegistrationResponse #{self.v3_request_count} "
            f"session={resp.session_token!r} "
            f"resp_body_len={len(resp_body)} datagram_len={len(datagram)}"
            f"{ack_log} "
            f"datagram_first48={datagram[:48].hex()}"
        )
        self.drain_outbound()
        self._start_replay()

    def _start_replay(self) -> None:
        """Queue post-V3 captured messages for paced replay."""
        if self.replay_started or self.replay_store is None:
            return
        self.replay_started = True
        self.replay_queue = self.replay_store.replay_messages_after_v3(
            self.replay_max_seq,
            include_redacted=self.replay_include_redacted,
        )
        # Cache a small captured R-msg as the post-replay heartbeat
        # template. type 0x15d (PingMsg) is the most frequent small R-msg
        # in the dump and ships clean. Falls back to 0x14f if not present.
        if self.post_replay_heartbeat_ms > 0:
            self._heartbeat_msg = (
                self.replay_store.get(0x2)
                or next(
                    (
                        m for m in self.replay_store.messages
                        if m.direction == "R" and m.type_id in (0x15d, 0x14f)
                        and not m.has_redaction
                    ),
                    None,
                )
            )
            if self._heartbeat_msg is None:
                self.log.warning(
                    "post-replay heartbeat enabled but no clean small R-msg "
                    "found in dump; disabling heartbeat"
                )
                self.post_replay_heartbeat_ms = 0
            else:
                # Wake 187 phase-2B foundation: validate that the central
                # dispatcher's encoder produces byte-identical output to
                # the captured heartbeat. Future wakes can swap the
                # emission path from `_send_replay_message(msg)` (raw
                # captured bytes) to a dispatcher-encoded fresh body —
                # this assertion proves the swap is safe BEFORE actually
                # performing it, in the spirit of the wake-157 shadow
                # pattern. Currently logs only; no behavior change.
                self._validate_dispatcher_heartbeat_encode_matches()
        # The V3 response sent on ch=0 with seq=0/rel_seq=0 doesn't go through
        # _next_seq, so the per-channel counters are still at 0. Bump them so
        # replay records get seq=1/rel_seq=1 onward instead of colliding with
        # the V3 response and getting deduped client-side.
        self.out_msg_seq[0] = 1
        self.out_rel_seq[0] = 1
        self._next_replay_at = time.monotonic()
        self.log.info(
            f">> replay queue armed: {len(self.replay_queue)} R-msgs "
            f"(seq 0x2..0x{self.replay_max_seq:x}), "
            f"interval={int(self.replay_interval_s * 1000)}ms, "
            f"ch0 counters bumped to seq=1 rel_seq=1"
        )

    def _pump_replay(self) -> None:
        """Send the next queued replay message if its delay has elapsed.

        After the queue drains, switch to periodic heartbeat sends if
        post_replay_heartbeat_ms > 0. This stops the client from cleanly
        timing out (`SM_DISCONNECT reason=0`) ~9s after the init burst.
        """
        now = time.monotonic()
        if self.replay_queue:
            if now < self._next_replay_at:
                return
            msg = self.replay_queue.pop(0)
            self._send_replay_message(msg)
            self._next_replay_at = now + self.replay_interval_s
            # Arm the first heartbeat for one full interval after the
            # last replay message ships (so we don't double up).
            if not self.replay_queue and self.post_replay_heartbeat_ms > 0:
                self._next_heartbeat_at = now + (
                    self.post_replay_heartbeat_ms / 1000.0
                )
            return

        # Queue is empty: heartbeat path
        if self.post_replay_heartbeat_ms <= 0 or self._heartbeat_msg is None:
            return
        if now < self._next_heartbeat_at:
            return
        self._send_replay_message(self._heartbeat_msg, is_heartbeat=True)
        self._next_heartbeat_at = now + (self.post_replay_heartbeat_ms / 1000.0)

    def _send_replay_message(self, msg: ReplayMessage, is_heartbeat: bool = False) -> None:
        """Wrap a captured typed-stream body in a Carrier record + envelope.

        Mirrors the V3 RegistrationResponse wrap (ch=0, flag=0x21, VLQ32
        length-prefixed body) which we know the deserializer accepts. The
        replay body already contains the [00 01 <type-encoded>] preamble
        from the dump, so we forward it verbatim.

        `is_heartbeat=True` downgrades the success log line to DEBUG and
        emits a periodic summary instead, so the post-replay heartbeat
        loop doesn't flood the console.
        """
        ch = 0
        flags = 0x21  # MF_RELIABLE | MF_DATA_CHANNEL
        out_seq, rel_seq = self._next_seq(ch, reliable=True)

        # If the captured message has redacted spans, substitute live-session
        # values via SubstitutionContext. Skip if the context isn't ready yet
        # (drops the message rather than emitting captured XX zero-fills).
        if msg.has_redaction:
            ctx = getattr(self, "substitution_ctx", None)
            if ctx is None:
                self.log.warning(
                    f"replay seq=0x{msg.seq:x} has redaction but no "
                    f"substitution_ctx; dropping"
                )
                return
            body_bytes = ctx.apply(msg)
            assert len(body_bytes) == len(msg.body), (
                f"replay-substitute changed body length: "
                f"{len(msg.body)} -> {len(body_bytes)}"
            )
        else:
            body_bytes = msg.body

        msg_size = len(body_bytes)
        vlq32 = _encode_vlq32(msg_size)
        envelope_body = vlq32 + body_bytes

        # DTLS 1.2 caps plaintext records at SSL3_RT_MAX_PLAIN_LENGTH = 16 384 B
        # (RFC 5246 §6.2.1). With AES-GCM cipher + record + envelope overhead,
        # plaintext bodies above ~14 000 B start failing inside OpenSSL with
        # "dtls message too big" and never reach UDP. Empirical evidence
        # (capture/responder_20260505_202651.log line 98): 12 706 B replay
        # body went through; 46 423 B body got dropped at the SSL layer
        # before MF_CHUNKS would have triggered. So the chunking threshold
        # is the DTLS plaintext cap, not the Carrier u16 record-size cap
        # (which is 65 535 and irrelevant here).
        if len(envelope_body) <= self.replay_single_record_limit:
            # Single-record path
            record = (
                bytes([flags]) +
                struct.pack(">H", len(envelope_body)) +
                bytes([ch & 0xFF]) +
                struct.pack(">H", out_seq & 0xFFFF) +
                struct.pack(">H", rel_seq & 0xFFFF) +
                envelope_body
            )
            datagram = self.wrap_envelope(record)
            self.send_app(datagram)
            line = (
                f">> replay seq=0x{msg.seq:x} type=0x{msg.type_id:x} "
                f"body_len={len(msg.body)} dgram_len={len(datagram)} "
                f"remaining={len(self.replay_queue)}"
            )
            if is_heartbeat:
                self._heartbeat_count = getattr(self, "_heartbeat_count", 0) + 1
                # First heartbeat at INFO so it's visible; subsequent
                # at DEBUG; periodic summary at INFO every N heartbeats.
                if self._heartbeat_count == 1:
                    self.log.info(f"{line} [HEARTBEAT START]")
                elif self._heartbeat_count % 60 == 0:
                    self.log.info(
                        f">> heartbeat alive: count={self._heartbeat_count} "
                        f"(every ~{self.post_replay_heartbeat_ms}ms)"
                    )
                else:
                    self.log.debug(line)
            else:
                self.log.info(line)
            self.drain_outbound()
            return

        # Chunked path: MF_CHUNKS (0x04) splits the message across N records
        # on the same channel. numChunks is a countdown — first record has
        # the total count, subsequent records decrement to 1. The first
        # chunk carries the VLQ32 size prefix (= total_size); subsequent
        # chunks ship just their slice. See analysis/replay_chunking_design.md.
        chunked_flags = flags | 0x04  # add MF_CHUNKS
        chunks = _chunk_replay_payload(envelope_body, self.replay_chunk_size)
        # The first chunk's seq/rel_seq are out_seq/rel_seq (already
        # allocated above). Subsequent chunks get fresh allocations.
        first_seq, first_rel = out_seq, rel_seq
        for i, (remaining, payload_slice) in enumerate(chunks):
            if i == 0:
                c_seq, c_rel = first_seq, first_rel
            else:
                c_seq, c_rel = self._next_seq(ch, reliable=True)
            record = (
                bytes([chunked_flags]) +
                struct.pack(">H", len(payload_slice)) +
                bytes([ch & 0xFF]) +
                struct.pack(">H", remaining & 0xFFFF) +
                struct.pack(">H", c_seq & 0xFFFF) +
                struct.pack(">H", c_rel & 0xFFFF) +
                payload_slice
            )
            datagram = self.wrap_envelope(record)
            self.send_app(datagram)
            self.drain_outbound()
        self.log.info(
            f">> replay seq=0x{msg.seq:x} type=0x{msg.type_id:x} "
            f"body_len={len(msg.body)} CHUNKED chunks={len(chunks)} "
            f"chunk_size={self.replay_chunk_size} "
            f"remaining={len(self.replay_queue)}"
        )

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
        # 2026-05-04: two known-working forms for the Connect ACK record:
        #   - "mn" (Mixed Nuts): flag 0x21 (MF_RELIABLE | MF_DATA_CHANNEL),
        #     seq=0, rel_seq=0. Real-server form. Confirmed byte-identical to
        #     Mixed Nuts' Wireshark dissector capture.
        #   - "alt" (community dump): flag 0xa0 (MF_CONNECTING | MF_DATA_CHANNEL),
        #     seq=current, rel_seq=0xFFFF. Other reverser explicitly says the
        #     0x21/0 form instant-disconnects on their path.
        # Both forms ship the SAME piggyback ACK record (flag 0x18) afterwards.
        # Selectable via --ack-form CLI flag.
        ack_payload = b"\x00\x00\x00\x05\x02"  # 4-byte version echo + msgid

        if self.ack_form == "alt":
            # Other reverser's form
            connect_ack = MessageRecord(
                channel=3,
                payload=ack_payload,
                sequence=self.out_msg_seq[3],
                reliable_sequence=0xFFFF,
                reliable=False,
                connecting=True,
                num_chunks=1,
                flags_override=0xa0,  # MF_CONNECTING | MF_DATA_CHANNEL
            )
            self.out_msg_seq[3] = (self.out_msg_seq[3] + 1) & 0xFFFF
        else:
            # Mixed Nuts' form (default)
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
                    help="which SM_CONNECT_ACK payload to send (legacy)")
    ap.add_argument("--ack-form", default="mn", choices=("mn", "alt"),
                    help="Connect ACK record form. 'mn' = Mixed Nuts shape "
                         "(flag 0x21, rel_seq=0, real-server form). 'alt' = "
                         "community fallback (flag 0xa0, rel_seq=0xFFFF). "
                         "Try 'mn' first; fall back to 'alt' if the client "
                         "instant-disconnects after Connect ACK.")
    ap.add_argument("--v3-resp-flag", default="0x21",
                    help="V3 RegistrationResponse Carrier record flag (hex). "
                         "0x21=MF_RELIABLE|MF_DATA_CHANNEL (length field). "
                         "0x60=MF_NO_LENGTH|MF_DATA_CHANNEL. "
                         "0xa0=MF_CONNECTING|MF_DATA_CHANNEL. "
                         "0xe0=MF_CONNECTING|MF_NO_LENGTH|MF_DATA_CHANNEL.")
    ap.add_argument("--v3-resp-channel", type=int, default=None,
                    help="Carrier channel for V3 response (0-4). Default: "
                         "mirror request's channel (typically 3).")
    ap.add_argument("--v3-resp-subheader", default="000000",
                    help="3-byte hex sub-header for MF_NO_LENGTH V3 response "
                         "(only used when --v3-resp-flag has 0x40 set). "
                         "Client uses '200002' for V3 retries; try that to "
                         "mirror.")
    ap.add_argument("--no-v3-piggyback-ack", action="store_true",
                    help="Disable bundling a Carrier-level ACK (flag 0x20 "
                         "ch=3 SM_CT_ACKS) alongside the V3 response in the "
                         "same envelope. Default: bundled (matches Mixed Nuts' "
                         "working server). Disable to A/B-test whether the "
                         "piggyback ACK is what stops the V3 retry loop.")
    ap.add_argument("--replay-include-redacted", action="store_true",
                    help="Include captured replay messages with XX-redacted "
                         "spans in the queue. Spans are filled at send-time "
                         "via SubstitutionContext (built from the live V3 "
                         "RegistrationRequest fields). Required to push "
                         "replay past seq 0x24 into the StateBundle range.")
    ap.add_argument("--character-display-name", default="NWPrivateTester01",
                    help="Display-name string used to fill display-name "
                         "spans in redacted replay messages. The captured "
                         "spans are 21-23 chars; this is padded/truncated "
                         "to fit each.")
    ap.add_argument("--replay-chunk-size", type=int, default=1100,
                    help="Per-chunk payload size for MF_CHUNKS replay. "
                         "Default 1100 matches the real server's WORLD "
                         "DATA segment size. Range 1..65000.")
    ap.add_argument("--replay-single-record-limit", type=int, default=14000,
                    help="Replay bodies up to this size ship as a single "
                         "Carrier record; bodies above it are chunked via "
                         "MF_CHUNKS. Default 14000 leaves headroom under "
                         "the DTLS 1.2 plaintext cap (SSL3_RT_MAX_PLAIN_"
                         "LENGTH = 16384). Lower if you see 'dtls message "
                         "too big' SSL errors.")
    ap.add_argument("--post-replay-heartbeat-ms", type=int, default=500,
                    help="After replay queue drains, re-send the captured "
                         "0x15d (or 0x14f) heartbeat every N ms to stop "
                         "the client from cleanly disconnecting (SM_DISCON"
                         "NECT reason=0) when the server falls silent. "
                         "Default 500 (matches community-state-machine-"
                         "dump phase 21). 0 disables.")
    ap.add_argument("--replay-after-v3", action="store_true",
                    help="After V3 response is sent, replay the captured "
                         "post-registration R-direction messages from the "
                         "Mixed Nuts dump. Tests whether post-V3 silence "
                         "is what causes the use-after-free CTD downstream.")
    ap.add_argument("--replay-dump",
                    default=str(PROJECT / "info" /
                                "nw-login-safe-20260502-153840" /
                                "messages-redacted.txt"),
                    help="Path to the redacted login dump for replay mode.")
    ap.add_argument("--replay-max-seq", default="0x24",
                    help="Highest captured seq to replay (hex). Defaults to "
                         "0x24 - covers the early ping/control burst before "
                         "the first big StateBundle at 0x25.")
    ap.add_argument("--replay-interval-ms", type=int, default=50,
                    help="Delay between replay messages in milliseconds. "
                         "Real captures fire close together - start small, "
                         "increase if the client struggles to keep up.")
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
    log.info(f"ack form: {args.ack_form} (mn=0x21/rel_seq=0, alt=0xa0/rel_seq=0xFFFF)")
    log.info(f"V3 response wrap: flag={args.v3_resp_flag} channel={args.v3_resp_channel or 'mirror-request'}")
    log.info(f"V3 piggyback ACK: {'disabled' if args.no_v3_piggyback_ack else 'enabled (flag 0x20 ch=3)'}")
    log.info(f"replay redacted: {'INCLUDED (substitution active)' if args.replay_include_redacted else 'filtered out'}")
    log.info(f"post-replay heartbeat: "
             f"{'disabled' if args.post_replay_heartbeat_ms <= 0 else f'every {args.post_replay_heartbeat_ms}ms'}")

    replay_store: ReplayStore | None = None
    if args.replay_after_v3:
        dump_path = Path(args.replay_dump)
        if not dump_path.is_file():
            log.error(f"replay dump not found: {dump_path}")
            return 1
        replay_store = ReplayStore(dump_path)
        log.info(
            f"replay armed: dump={dump_path.name} "
            f"max_seq={args.replay_max_seq} "
            f"interval={args.replay_interval_ms}ms "
            f"({len(replay_store.replay_messages_after_v3(int(args.replay_max_seq, 16)))} clean R-msgs queued)"
        )

    sessions: dict[tuple, PeerSession] = {}

    try:
      while True:
        try:
            try:
                data, peer = sock.recvfrom(65535)
            except socket.timeout:
                # Drive periodic work for every active session.
                for sess in list(sessions.values()):
                    sess._pump_replay()
                    sess.drain_outbound()
                continue
            except OSError as e:
                log.warning(f"recvfrom failed: {e}")
                continue

            sess = sessions.get(peer)
            if sess is None:
                log.info(f"new peer {peer}")
                sess = PeerSession(ctx, peer, sock, log, ack_payload,
                                   ack_form=args.ack_form,
                                   v3_resp_flag=int(args.v3_resp_flag, 16),
                                   v3_resp_channel=args.v3_resp_channel,
                                   v3_resp_subheader=args.v3_resp_subheader,
                                   v3_piggyback_ack=not args.no_v3_piggyback_ack,
                                   replay_store=replay_store,
                                   replay_max_seq=int(args.replay_max_seq, 16),
                                   replay_interval_ms=args.replay_interval_ms)
                sess.replay_include_redacted = args.replay_include_redacted
                sess.character_display_name = args.character_display_name
                sess.replay_chunk_size = args.replay_chunk_size
                sess.replay_single_record_limit = args.replay_single_record_limit
                sess.post_replay_heartbeat_ms = args.post_replay_heartbeat_ms
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
            raise
        except Exception:
            import traceback
            log.error("main loop iteration crashed:\n" + traceback.format_exc())
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
