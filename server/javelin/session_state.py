"""
Session-state scaffolding for codec-driven emission.

This is a **structure-only sketch** — it captures the runtime fields
a future server-side path needs to drive the codec library when
emulating fresh sessions (rather than replaying a captured one).
Today's `server/rep_responder.py` uses captured-bytes + redaction
substitution and does not consume this; see
`analysis/integration_status.md` for the design rationale.

When the project graduates to multi-session emulation, the
integration shape would be:

  state = SessionState.fresh()
  ...
  msg = make_init_message_18a6(
      counter=state.advance_18a6_counter(),
      first_uuid_half=state.subkey_upper_8,
      session_uuid_lower=state.session_uuid[8:],
      second_id=state.metadata_block_second_id,
  )
  send(encode(msg))

The dataclass below carries the **raw fields** required for that
emission. Methods (`advance_*`, `mint_session_clock`, etc.) are
intentionally not added yet — they're a layer of policy that
should be agreed on with the maintainer before being committed.

For now this serves as **documentation of the runtime state
the integration will need**, organized by sub-system.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class SessionState:
    """Runtime state for a single client session.

    All fields default to "unset" (zeros / empty bytes) so a fresh
    `SessionState()` is valid; populate them via the appropriate
    handshake step (V3 RegistrationRequest parse → session_uuid,
    persona_id, etc.).
    """

    # ---- core identity (from V3 handshake) ----

    session_uuid: bytes = b""           # 16 bytes, assigned at registration
    persona_id: int = 0                  # u32 from V3 request
    build_version: int = 0               # u32, from server-side config

    # ---- session clock + nonce baseline ----
    #
    # Embedded in V3 RegistrationResponse mystery8[0..4] AND broadcast
    # periodically as type 0x14f (session_clock_beacon). Both must
    # share the same value at session start; the clock can advance
    # within the session (captured replay shows 0x0b888d68 → 0x0b888d69
    # across the 4 captured 0x14f beacons).

    session_clock: int = 0               # u32 BE — slow-incrementing
    session_nonce: int = 0               # u32 BE — set at registration;
                                         # nonce field of mystery8

    # ---- sub-system identity bundles ----
    #
    # Each captured session has a fixed 8-byte "second_id" or
    # "first_uuid_half" per major sub-system, shared across all messages
    # in that family. See cross-codec identity-bundle map in
    # `analysis/replay_message_inventory.md` for the convention.
    # In the captured session the lower 8 bytes are session_uuid[8:]
    # and the upper 8 vary per sub-system.

    # Session-manager subkey upper (used by 0x18a6 + 0x1a59 family)
    subkey_upper_8: bytes = b""          # 8 bytes

    # Metadata-block "second_id" (used by 0x18a6 + 0x663)
    metadata_block_second_id: bytes = b""  # 8 bytes

    # Action-queue identity (used by 0x635)
    action_queue_second_id: bytes = b""  # 8 bytes

    # Fingerprint-reporter identity (used by 0x5b2 + 0x0a95)
    fingerprint_reporter_second_id: bytes = b""  # 8 bytes

    # Receipt-handshake identity (used by 0x8e6 + 0x9fc)
    receipt_handshake_id_upper: bytes = b""  # 8 bytes

    # ---- per-family message counters ----
    #
    # Tracked per direction. Server emits 0x18a6 with monotonic counters
    # and bumps after observing the matching 0x1a59 ack; ditto other
    # counter-coupled pairs.

    next_18a6_counter: int = 1           # 0x18a6 R counter (1..255)
    next_635_counter: int = 1            # 0x635 W counter (client-tracked, but server validates)
    next_15d_ping_counter: int = 0       # 0x15d ping counter (slow-incrementing)

    # ---- 0x8e6 ↔ 0x9fc receipt-handshake state ----
    #
    # Server emits 0x8e6 with a 16-byte opaque_blob; client replies
    # 0x9fc echoing that blob byte-for-byte. The blob is per-session
    # state that the server picks once and references in both messages.

    receipt_blob: bytes = b""            # 16 bytes — server-chosen, echoed by client

    # ---- captured-blob constants (fixed per session) ----
    #
    # Some captured fields are server-policy values that don't change
    # within a session but vary across deployments (e.g. Vivox config
    # for a private-server install).

    vivox_api_url: str = ""              # e.g. "https://server.example/api2/"
    vivox_realm: str = ""                # e.g. "amazon9050-ne83"
    vivox_issuer: str = ""               # e.g. "@server.example"

    # ---- ad-hoc state (extension point) ----

    extra: dict = field(default_factory=dict)

    @classmethod
    def fresh(cls) -> "SessionState":
        """Build a fresh session state with random session_uuid + nonce.

        Use this at session start, then populate the sub-system
        identity bundles from server-side policy / config.
        """
        return cls(
            session_uuid=os.urandom(16),
            session_nonce=int.from_bytes(os.urandom(4), "big"),
        )
