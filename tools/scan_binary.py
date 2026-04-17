r"""
Static scan of NewWorld.exe for AzNetworking / Multiplayer gem markers.

Doesn't need Ghidra. Just reads the PE file directly and greps for
strings + RTTI UUIDs from docs/aznetworking-reference.md. Tells us
before Ghidra finishes which O3DE pieces are present in the retail
binary vs stripped/replaced.

Usage:
    python tools/scan_binary.py
    python tools/scan_binary.py --exe <steam-library>\steamapps\common\New World\Bin64\NewWorld.exe
"""

import argparse
import struct
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

# Default: use the ARCHIVED copy so Steam updates can't invalidate our findings
DEFAULT_EXE = Path(r"<archive-root>\GameClient\Bin64\NewWorld.exe")

# From docs/aznetworking-reference.md section 7.1
RTTI_UUIDS = {
    "IPacket":                    "1B33BFE8-8A4B-44E3-8C8D-3B924093227C",
    "IPacketHeader":              "90A0EFE3-01A4-4F04-87CF-E98E94D49648",
    "UdpPacketHeader":            "21A11FF3-6829-4A59-9906-C06EF7F39AC1",
    "TcpPacketHeader":            "6D92B9BE-C5E4-4571-B0FA-8F29042BE93B",
    "INetworkInterface":          "ECDA6FA2-4AA0-435E-881F-214C4B179A31",
    "INetworking":                "6E47367B-3AA5-4CB8-A691-4910168F287A",
    "AzNetworkingModule":         "4118D37D-233D-4CD5-ACE7-747FBAF2615D",
    "IMultiplayer":               "90A001DD-AD31-46C7-9FBE-1059AFB7F5E9",
    "IMultiplayerSpawner":        "E5525317-A476-4209-BE45-477FB9D96083",
    "INetworkEntityManager":      "109759DE-9492-439C-A0B1-AE46E6FD029C",
    "INetworkTime":               "7D468063-255B-4FEE-86E1-6D750EEDD42A",
    "MultiplayerComponent":       "B7F5B743-CCD3-4981-8F1A-FC2B95CE22D7",
    "MultiplayerModule":          "497FF057-6CE1-43D5-9A9F-D2B7ABF6D3A7",
    "NetworkEntityUpdateMessage": "CFCA08F7-547B-4B89-9794-37A8679608DF",
    "NetworkEntityRpcMessage":    "3AA5E1A5-6383-46C1-9817-F1B8C2325178",
    "PrefabEntityId":             "EFD37465-CCAC-4E87-A825-41B4010A2C75",
    "NetworkSpawnable":           "780FC028-25D7-4F70-A93F-D697820B76F8",
    "NetEntityId":                "05E4C08B-3A1B-4390-8144-3767D8E56A81",
    "NetComponentId":             "8AF3B382-F187-4323-9014-B380638767E3",
    "PropertyIndex":              "F4460210-024D-4B3B-A10A-04B669C34230",
    "RpcIndex":                   "EBB1C475-FA03-4111-8C84-985377434B9B",
    "ClientInputId":              "35BF3504-CEC9-4406-A275-C633A17FBEFB",
    "HostFrameId":                "DF17F6F3-48C6-4B4A-BBD9-37DA03162864",
}

CVAR_NAMES = [
    "net_UdpUseEncryption", "net_UdpUseDtlsCookies", "net_UdpTimeoutConnections",
    "net_UdpDefaultTimeoutMs", "net_UdpMaxUnackedPacketCount",
    "net_UdpSendBufferSize", "net_UdpRecvBufferSize",
    "net_SslExternalCertificateFile", "net_SslInternalCertificateFile",
    "net_SslAllowSelfSigned", "net_SslEnablePinning", "net_SslValidateExpiry",
    "net_SslMaxCertDepth", "net_RotateCookieTimer",
    "net_validateSerializedTypes", "net_UdpCompressor", "net_TcpCompressor",
    "net_UdpFragmentTimeoutMs", "net_MaxReliablePacketsInWindow",
    "net_FragmentsAlwaysReliable",
]

LOG_MESSAGES = [
    "SSL handshake negotiation failed",
    "dtls handshake is completed",
    "An existing SSL socket was open during a call to connect",
    "Unacked packet count exceeded, sending client heartbeat",
    "Accepted new Udp Connection",
    "Registering packetId",
    "Processing time exceeded, discarding",
    "OpenSSL preverification failed",
    "net_SslAllowSelfSigned is",
    "Failed to decompress packet!",
    "New outgoing connection to remote address",
    "New incoming connection from remote address",
    "Multiplayer operating in",
    "Server did not provide a valid level to load",
    "No IMultiplayerSpawner was available",
    "Migrating to new server shard",
    "Total networked entities",
]

CLASS_NAMES = [
    "UdpPacketHeader", "UdpConnection", "UdpNetworkInterface",
    "UdpSocket", "DtlsSocket", "DtlsEndpoint",
    "NetworkInputSerializer", "NetworkOutputSerializer",
    "MultiplayerSystemComponent", "NetworkEntityManager",
    "NetworkEntityUpdateMessage", "NetworkEntityRpcMessage",
    "ClientToServerConnectionData", "ServerToClientConnectionData",
    "NetworkSpawnable", "ServerToClientReplicationWindow",
]

PACKET_CLASS_NAMES = [
    "CorePackets::InitiateConnectionPacket",
    "CorePackets::ConnectionHandshakePacket",
    "CorePackets::TerminateConnectionPacket",
    "CorePackets::HeartbeatPacket",
    "CorePackets::FragmentedPacket",
    "MultiplayerPackets::Connect",
    "MultiplayerPackets::Accept",
    "MultiplayerPackets::VersionMismatch",
    "MultiplayerPackets::ReadyForEntityUpdates",
    "MultiplayerPackets::EntityUpdates",
    "MultiplayerPackets::EntityRpcs",
    "MultiplayerPackets::ClientMigration",
]

FIELD_NAMES = [
    "PacketType", "LocalSequence", "RemoteSequence", "SequenceWindow",
    "IsReliable", "ReliableSequence", "PacketFlags", "EntityId",
    "TypeAndFlags", "PrefabEntityId", "RpcDeliveryType",
    "ComponentId", "RpcIndex",
]


def uuid_to_le_bytes(uuid_str: str) -> bytes:
    """Convert {AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE} to the Windows GUID
    byte layout: first three groups little-endian, last two as bytes."""
    s = uuid_str.replace("-", "").replace("{", "").replace("}", "")
    raw = bytes.fromhex(s)
    # raw[0:4] little-endian reversed, raw[4:6] LE, raw[6:8] LE, raw[8:] as-is
    return raw[0:4][::-1] + raw[4:6][::-1] + raw[6:8][::-1] + raw[8:]


def count_occurrences(data: bytes, needle: bytes, label: str) -> int:
    """Count non-overlapping occurrences of needle in data."""
    count = 0
    idx = 0
    first_at = -1
    while True:
        pos = data.find(needle, idx)
        if pos == -1:
            break
        if first_at == -1:
            first_at = pos
        count += 1
        idx = pos + 1
        if count > 10000:
            break
    return count, first_at


def scan(exe_path: Path):
    if not exe_path.exists():
        print(f"[!] Binary not found: {exe_path}")
        sys.exit(1)

    print(f"[*] Reading {exe_path}...")
    data = exe_path.read_bytes()
    print(f"[+] Loaded {len(data):,} bytes\n")

    # ---- RTTI UUIDs ----
    print("=" * 70)
    print("  RTTI / AZ_TYPE_INFO UUIDs")
    print("=" * 70)
    uuid_hits = 0
    for name, uuid_str in RTTI_UUIDS.items():
        needle = uuid_to_le_bytes(uuid_str)
        count, first_at = count_occurrences(data, needle, name)
        status = f"FOUND @0x{first_at:08x}" if count else "--"
        if count:
            uuid_hits += 1
        print(f"  {name:30s}  {count:>3d}  {status}")
    print(f"\n  {uuid_hits}/{len(RTTI_UUIDS)} RTTI UUIDs present\n")

    # ---- CVars ----
    print("=" * 70)
    print("  Network CVars")
    print("=" * 70)
    cvar_hits = 0
    for name in CVAR_NAMES:
        count, first_at = count_occurrences(data, name.encode("utf-8"), name)
        status = f"@0x{first_at:08x}" if count else "--"
        if count:
            cvar_hits += 1
        print(f"  {name:45s}  {count:>3d}  {status}")
    print(f"\n  {cvar_hits}/{len(CVAR_NAMES)} CVars present\n")

    # ---- Log messages ----
    print("=" * 70)
    print("  Distinctive log messages")
    print("=" * 70)
    log_hits = 0
    for msg in LOG_MESSAGES:
        count, first_at = count_occurrences(data, msg.encode("utf-8"), msg)
        status = f"@0x{first_at:08x}" if count else "--"
        if count:
            log_hits += 1
        print(f"  {msg[:50]:50s}  {count:>3d}  {status}")
    print(f"\n  {log_hits}/{len(LOG_MESSAGES)} log messages present\n")

    # ---- Class names ----
    print("=" * 70)
    print("  Class name strings")
    print("=" * 70)
    class_hits = 0
    for name in CLASS_NAMES:
        needle = name.encode("utf-8") + b"\x00"  # null-terminated
        count, first_at = count_occurrences(data, needle, name)
        status = f"@0x{first_at:08x}" if count else "--"
        if count:
            class_hits += 1
        print(f"  {name:45s}  {count:>3d}  {status}")
    print(f"\n  {class_hits}/{len(CLASS_NAMES)} class names present\n")

    # ---- Packet class names ----
    print("=" * 70)
    print("  Packet class names (namespaced)")
    print("=" * 70)
    packet_hits = 0
    for name in PACKET_CLASS_NAMES:
        count, first_at = count_occurrences(data, name.encode("utf-8"), name)
        status = f"@0x{first_at:08x}" if count else "--"
        if count:
            packet_hits += 1
        print(f"  {name:50s}  {count:>3d}  {status}")
    print(f"\n  {packet_hits}/{len(PACKET_CLASS_NAMES)} packet class names present\n")

    # ---- Serialization field names ----
    print("=" * 70)
    print("  Serialization field names")
    print("=" * 70)
    field_hits = 0
    for name in FIELD_NAMES:
        needle = name.encode("utf-8") + b"\x00"  # null-terminated
        count, first_at = count_occurrences(data, needle, name)
        status = f"@0x{first_at:08x}" if count else "--"
        if count:
            field_hits += 1
        print(f"  {name:30s}  {count:>3d}  {status}")
    print(f"\n  {field_hits}/{len(FIELD_NAMES)} field names present\n")

    # ---- Summary ----
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    total = len(RTTI_UUIDS) + len(CVAR_NAMES) + len(LOG_MESSAGES) + \
            len(CLASS_NAMES) + len(PACKET_CLASS_NAMES) + len(FIELD_NAMES)
    hits = uuid_hits + cvar_hits + log_hits + class_hits + packet_hits + field_hits
    print(f"  RTTI UUIDs:    {uuid_hits:>3d}/{len(RTTI_UUIDS):>3d}")
    print(f"  CVars:         {cvar_hits:>3d}/{len(CVAR_NAMES):>3d}")
    print(f"  Log messages:  {log_hits:>3d}/{len(LOG_MESSAGES):>3d}")
    print(f"  Class names:   {class_hits:>3d}/{len(CLASS_NAMES):>3d}")
    print(f"  Packet names:  {packet_hits:>3d}/{len(PACKET_CLASS_NAMES):>3d}")
    print(f"  Field names:   {field_hits:>3d}/{len(FIELD_NAMES):>3d}")
    print(f"  TOTAL:         {hits:>3d}/{total:>3d}  ({100*hits/total:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Scan NewWorld.exe for AzNetworking markers")
    parser.add_argument("--exe", type=str, default=str(DEFAULT_EXE),
                        help="Path to NewWorld.exe (default: archived copy)")
    args = parser.parse_args()
    scan(Path(args.exe))


if __name__ == "__main__":
    main()
