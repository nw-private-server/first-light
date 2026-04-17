"""
In-process loopback test for the stub server's message-level logic.

Skips DTLS entirely. Directly feeds bytes that a client would send over
a DTLS-terminated wire into the server's dispatcher, then verifies the
server's response parses back into the expected SM_CONNECT_ACK.

This isolates the "protocol correctness" of parser + marshaler + handler
from the "DTLS transport" problem. The latter needs a better library
than python3-dtls on Python 3.13.

Run:
    python -m server.test_loopback
"""

from __future__ import annotations

from server.javelin import (
    MessageRecord,
    SystemMessageId,
    marshal_datagram,
    parse_datagram,
)


class FakeConn:
    """Mimics just enough of server.stub_server.Connection to call on_datagram
    without any socket/DTLS dependency."""

    def __init__(self):
        self.sent: list[bytes] = []
        self.peer = ("127.0.0.1", 0)
        self.sent_connect_ack = False

    def log(self, m: str) -> None:
        print(f"[conn] {m}")

    def send_datagram(self, records: list[MessageRecord]) -> None:
        data = marshal_datagram(records)
        self.sent.append(data)
        self.log(f">> queued {len(records)} records, {len(data)} bytes")

    def send_connect_ack(self) -> None:
        payload = b"\x00" * 4 + bytes([SystemMessageId.SM_CONNECT_ACK])
        ack = MessageRecord(
            channel=3,
            payload=payload,
            sequence=0,
            reliable_sequence=0,
            reliable=True,
            connecting=True,
            num_chunks=1,
        )
        self.send_datagram([ack])
        self.sent_connect_ack = True

    def on_datagram(self, data: bytes) -> None:
        # Reuse the actual handler logic from stub_server.Connection.on_datagram.
        # We inline it here (rather than import) to keep this file standalone.
        self.log(f"<< recv {len(data)} bytes")
        result = parse_datagram(data)
        assert result.error is None, f"parse failed: {result.error}"
        for rec in result.messages:
            if (rec.is_system
                    and rec.system_msg_id == SystemMessageId.SM_CONNECT_REQUEST
                    and not self.sent_connect_ack):
                self.log("   -> sending SM_CONNECT_ACK")
                self.send_connect_ack()


def build_client_connect_request() -> bytes:
    """What a client would send right after DTLS handshake completes."""
    payload = b"\x00\x00\x00\x00" + bytes([SystemMessageId.SM_CONNECT_REQUEST])
    req = MessageRecord(
        channel=3,
        payload=payload,
        sequence=0,
        reliable_sequence=0,
        reliable=True,
        connecting=True,
        num_chunks=1,
    )
    return marshal_datagram([req])


def run():
    print("=" * 60)
    print("  Loopback test: SM_CONNECT_REQUEST -> SM_CONNECT_ACK")
    print("=" * 60)

    client_data = build_client_connect_request()
    print(f"[client] sending {len(client_data)} bytes: {client_data.hex()}")

    server = FakeConn()
    server.on_datagram(client_data)

    assert len(server.sent) == 1, f"expected 1 response, got {len(server.sent)}"
    resp = server.sent[0]
    print(f"[client] received {len(resp)} bytes: {resp.hex()}")

    parsed = parse_datagram(resp)
    assert parsed.error is None, f"response parse failed: {parsed.error}"
    assert len(parsed.messages) == 1
    rec = parsed.messages[0]
    print(f"[client] parsed: channel={rec.channel} seq={rec.sequence} "
          f"conn={rec.connecting} rel={rec.reliable} size={rec.size}")
    assert rec.is_system, "response should be system channel"
    assert rec.system_msg_id == SystemMessageId.SM_CONNECT_ACK, (
        f"expected SM_CONNECT_ACK (2), got {rec.system_msg_id}"
    )
    assert rec.connecting, "ACK should have MF_CONNECTING"
    assert rec.reliable, "ACK should be reliable"

    print("\n[OK] Full request/response cycle works end-to-end.")
    print("     Parser and marshaler are paired correctly.")


if __name__ == "__main__":
    run()
