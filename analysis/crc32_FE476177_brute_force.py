"""Brute-force CRC32 reversal for 0xFE476177 and related event-family hashes.

History:
- Wake 9: 65 hand-picked names against zlib CRC32 (raw + lowercased). No match.
- Wake 277: 187 additional candidates × 7 variants. No match.
- Wake 278: Expanded target set from 1 hash to 19 hashes (entire event
  family discovered in FUN_146b621c0); 87 GridMate-focused candidates
  × 2 variants against the full set. No match.

Total: ~404 unique candidate strings × multiple variants × multiple target
hashes. Confirms hand-curated wordlists are too sparse without external
corpus access.

The wake-278 event family (all dispatched by FUN_146b621c0 + FUN_140fb3560
in the same handler structure — confirmed to be GridMate Carrier
connection-lifecycle events):
- 0xFE476177 — destroy-flag event (sets [+0xfd] in FUN_140fb3560,
  [+0xda] in FUN_146b621c0)
- 0xF2D0BB74 — co-occurring event (FUN_140fb3560 sub-key, FUN_146b621c0 branch)
- 0xF36721F9 — outer dispatch key (possibly EBus name itself)
- 0x53E4E683, 0xDECE4567, 0xAD273586, 0x8E281F3D — sibling branches
- 0x7FABBDE8, 0xBF83FB18, 0xB2B878F9 — shared AZ::Name namespace/type IDs
- 0x578A1F75, 0x20EDCD6C — shared sub-action hashes
- 0x9CCD4435, 0xF3B2D8C3, 0xFAF3C240, 0x671C7858, 0x82219416, 0x6606A5ED,
  0x08495DFC — branch-specific sub-names

If a future contributor matches ANY ONE of these to a known O3DE event
name, the EBus domain is identified and the other hashes constrain to
the same event class — a single match unlocks the family.

Next step (requires external corpus access, not loop-tractable):
1. Clone O3DE public source (github.com/o3de/o3de).
2. Grep all AZ_CRC, AZ_CRC_CE, Crc32(...) callsites.
3. Compute the CRC of each (algorithm verified below).
4. Check for 0xFE476177.

Alternative static thread (not yet attempted): AZ::Name in O3DE uses an
internal hash -> string table for runtime lookup. If the binary preserves
any of it, 0xFE476177 might be reachable through that table. The wake-9
notes mention `PTR_LAB_147ef8d50` as a suspected AZ::Name vtable — finding
the consumers of that vtable might surface the table.

Confirmed: AzCore's Crc32 uses the standard polynomial 0xEDB88320 (same
as zlib). The wake-9 attempt's algorithm was correct.
"""

from __future__ import annotations
import zlib

TARGET = 0xFE476177


def variants(s: str) -> dict[str, int]:
    """All CRC32 variants we've considered."""
    bs = s.encode()
    return {
        "raw": zlib.crc32(bs),
        "raw+null": zlib.crc32(bs + b"\x00"),
        "lower": zlib.crc32(s.lower().encode()),
        "lower+null": zlib.crc32(s.lower().encode() + b"\x00"),
        "upper": zlib.crc32(s.upper().encode()),
        "raw_inv": zlib.crc32(bs) ^ 0xFFFFFFFF,
        "lower_inv": zlib.crc32(s.lower().encode()) ^ 0xFFFFFFFF,
    }


def check(candidates: list[str]) -> list[tuple[str, str, str]]:
    """Returns (name, variant, hex_hash) tuples for any matches."""
    found = []
    for name in candidates:
        for vname, h in variants(name).items():
            if h == TARGET:
                found.append((name, vname, f"0x{h:08X}"))
    return found


if __name__ == "__main__":
    # Combined wordlists from wake 9 + wake 277.
    candidates = [
        # GridMate Carrier connection lifecycle (wake 277)
        "OnDisconnect", "OnConnectionLost", "OnTimeout", "OnDestroy",
        "OnDestroyed", "OnDisconnected", "OnConnectionTimeout",
        "DisconnectReason", "CarrierDisconnect", "CarrierTimeout",
        "CarrierDestroy", "ForceDisconnect", "GracefulDisconnect",
        "ConnectionDestroy", "ConnectionTimeout", "ConnectionDropped",
        "Reconnect", "ReconnectTimeout", "RetryTimeout",
        "FlushTimeout", "FlushQueue", "DrainQueue", "PurgeQueue",
        "SessionEnd", "SessionEnded", "SessionTimeout", "SessionExpired",
        "OnSessionEnd", "OnSessionEnded", "OnSessionTimeout",
        "OnSessionDelete", "OnSessionDeleted",
        "SkipTimeoutAndFlush", "SkipTimeout", "FlushAndDisconnect",
        "ImmediateDisconnect", "FastDisconnect",
        # GridMate Replica
        "OnReplicaDeactivated", "OnReplicaDestroyed", "ReplicaDeactivate",
        "ReplicaDestroy", "ReplicaTimeout", "ReplicaLost",
        "RemoveReplica", "ReplicaDisconnect",
        # REPClient / Hub / Javelin
        "OnRegistrationFailed", "RegistrationTimeout", "RegistrationLost",
        "RejectRegistration", "RejectClient", "RejectConnection",
        "DropConnection", "DropClient", "DisconnectClient",
        "TerminateConnection", "TerminateSession",
        # AzNetworking / generic
        "Shutdown", "Stop", "Quit", "Exit", "Cancel", "Abort",
        "ForceShutdown", "GracefulShutdown",
        "OnShutdown", "OnStop", "OnExit", "OnQuit", "OnAbort",
        "OnSystemTick", "OnTick", "OnUpdate", "PreShutdown", "PostShutdown",
        "SystemShutdown", "AppShutdown", "EngineShutdown",
        "EndOfSession", "EndSession", "FinishSession", "CloseSession",
        "ResetSession", "ExpireSession", "InvalidateSession",
        "OnReset", "OnInvalidate", "OnExpire",
        "NetClose", "NetDisconnect", "NetTimeout", "NetDestroy",
        "NetReset", "NetAbort",
        "OnPlayerDisconnect", "OnPlayerLeave", "OnPlayerExit",
        "PlayerDisconnect", "PlayerLeave", "PlayerExit",
        "ClientDisconnect", "ClientLeave", "ClientExit",
        "HubDisconnect", "HubLeave",
        # Carrier internal events (second pass)
        "ConnectionGood", "ConnectionBad", "ConnectionPing",
        "ReplicaActivate", "ReplicaRelease",
        "OnReplicaDeactivate", "OnReplicaRelease", "OnReplicaActivate",
        "ReplicaUpdate", "DataSetUpdate", "RpcCall",
        "SystemMessage", "AppMessage", "RegularMessage",
        "InternalEvent", "InternalMessage",
        "SessionTimeoutEvent", "PacketTimeout", "ProcessTimeout",
        "TimeoutEvent", "ExpireEvent",
        "OnPreDisconnect", "OnPostDisconnect", "OnGracefulDisconnect",
        "PreDestroy", "PostDestroy",
        "BeginShutdown", "EndShutdown", "FinishShutdown",
        "GridSession", "GridSessionEnd", "GridSessionDestroy",
        "OnGridSession", "OnSessionDestroy",
        "MultiplayerSession", "OnMultiplayerSessionEnd",
        "TickBus", "SystemTickBus", "EntityBus",
        "GameSessionEnd", "GameSessionTimeout", "GameDestroy",
        "JavelinDisconnect", "JavelinShutdown", "JavelinSessionEnd",
        "RepClientDestroy", "REPClientDestroy", "REPClientShutdown",
        "HubShutdown", "HubSessionEnd",
        "OnPreShutdownSequence", "OnShutdownComplete",
        "ComponentShutdown", "ComponentDeactivate",
        "Disconnect", "Destroy", "Cleanup", "End", "Finish",
        "Close", "Drop", "Kill", "Tear", "Tearing", "TearDown",
        "Disable", "Disabling", "Deactivate", "Detach",
        "Tick", "Update", "Reset", "Init", "Start", "Run",
    ]
    hits = check(candidates)
    print(f"{len(candidates)} candidates × 7 variants tried")
    if hits:
        for h in hits:
            print(f"  MATCH: {h}")
    else:
        print("  No match")
