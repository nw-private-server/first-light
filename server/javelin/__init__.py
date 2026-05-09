"""Javelin protocol parser + marshaler — mirrors the binary's Carrier::ParseMessages and Carrier::WriteMessages.

Submodules:

- `bitstream`, `frame`        — low-level wire framing (datagrams, records, system messages)
- per-type codec modules      — wire-level dataclasses + encode/decode for each
                                  characterized type-id (see
                                  `analysis/codec_coverage.md` for the
                                  full type→module map)
- `subkey_beacon`             — generic codec covering 14 W-direction
                                  type-ids in the subkey-beacon family
                                  (see `KNOWN_FAMILY`)

Most-used codec classes are re-exported below for convenience; full
modules are also importable directly via `from server.javelin.X import Y`.
"""

from .bitstream import BitStream, BitStreamWriter
from .frame import (
    MessageFlags,
    MessageRecord,
    ParseResult,
    SystemMessageId,
    iter_system_messages,
    marshal_datagram,
    marshal_record,
    parse_datagram,
)

# Generic / family codecs
from .subkey_beacon import (
    SubkeyBeacon,
    KNOWN_FAMILY as SUBKEY_FAMILY,
    make_subkey_beacon,
)

# R-direction (server → client) message codecs
from .session_message_a4 import SessionMessageA4, make_session_message_a4
from .session_clock_beacon import SessionClockBeacon, make_session_clock_beacon
from .heartbeat_15d import HeartbeatPing15D, HeartbeatAck15D, make_ack_for
from .session_identity_beacon import (
    SessionIdentityBeacon,
    make_session_identity_beacon,
)
from .init_message_18a6 import InitMessage18A6, make_init_message_18a6
from .level_descriptor_663 import LevelDescriptor663
from .identity_blob_8e6 import IdentityBlob8E6
from .vivox_config_1067 import VivoxConfig1067
from .asset_count_table_ca4 import AssetCountTableCA4, AssetCountRecord
from .asset_blob_16a0 import AssetBlob16A0Small
from .result_token_136a import ResultToken136A, make_result_token_136a
from .result_token_1097 import ResultToken1097, make_result_token_1097
from .handshake_blob_76 import HandshakeBlob76, make_handshake_blob_76
from .world_data_blob_65c import WorldDataBlob65C, WorldDataRecord
from .v3_response import V3RegistrationResponse

# W-direction (client → server) message codecs
from .session_subkey_1a59 import SessionSubkeyBeacon1A59
from .identity_fingerprint_5b2 import IdentityFingerprintSet5B2
from .action_history_635 import ActionHistory635
from .permission_bitmap_a95 import PermissionBitmapA95
from .receipt_handshake_9fc import ReceiptHandshake9FC
from .keybinding_config_12f6 import KeybindingConfig12F6

# AzCore-style typed codecs
from .level_info_changed import LevelInfoChangedMsg
from .self_ident import PlayerManagerSelfIdentificationMsg

# Session-state scaffolding (sketch — not consumed by runtime today)
from .session_state import SessionState


__all__ = [
    # Low-level wire framing
    "BitStream",
    "BitStreamWriter",
    "MessageFlags",
    "MessageRecord",
    "ParseResult",
    "SystemMessageId",
    "iter_system_messages",
    "marshal_datagram",
    "marshal_record",
    "parse_datagram",
    # Generic / family codecs
    "SubkeyBeacon",
    "SUBKEY_FAMILY",
    "make_subkey_beacon",
    # R-direction codecs
    "SessionMessageA4",
    "make_session_message_a4",
    "SessionClockBeacon",
    "make_session_clock_beacon",
    "HeartbeatPing15D",
    "HeartbeatAck15D",
    "make_ack_for",
    "SessionIdentityBeacon",
    "make_session_identity_beacon",
    "InitMessage18A6",
    "make_init_message_18a6",
    "LevelDescriptor663",
    "IdentityBlob8E6",
    "VivoxConfig1067",
    "AssetCountTableCA4",
    "AssetCountRecord",
    "AssetBlob16A0Small",
    "ResultToken136A",
    "make_result_token_136a",
    "ResultToken1097",
    "make_result_token_1097",
    "HandshakeBlob76",
    "make_handshake_blob_76",
    "WorldDataBlob65C",
    "WorldDataRecord",
    "V3RegistrationResponse",
    # W-direction codecs
    "SessionSubkeyBeacon1A59",
    "IdentityFingerprintSet5B2",
    "ActionHistory635",
    "PermissionBitmapA95",
    "ReceiptHandshake9FC",
    "KeybindingConfig12F6",
    # AzCore-style codecs
    "LevelInfoChangedMsg",
    "PlayerManagerSelfIdentificationMsg",
    # Session-state scaffolding
    "SessionState",
]
