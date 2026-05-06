"""
Quick host-side import probe for the archived NewWorld.exe.

This is a companion to the Frida hook work: it confirms, from disk, which
named imports exist in the archived binary before we attempt to resolve them
manually in-process.

Usage:
    python tools/import_table_probe.py
"""

import os
from pathlib import Path
from tools.list_pe_imports import parse_imports


EXE = Path(os.environ.get(
    "NW_ARCHIVE_EXE",
    r"C:\NewWorldArchive\GameClient\Bin64\NewWorld.exe",
))
TARGETS = {
    "steam_api64.dll": {"SteamAPI_Init", "SteamInternal_ContextInit"},
    "WINHTTP.dll": {"WinHttpConnect", "WinHttpOpenRequest", "WinHttpSendRequest"},
    "WS2_32.dll": {"WSAConnect", "WSASend", "WSARecv", "WSARecvFrom", "GetAddrInfoW", "getaddrinfo"},
}


def main() -> int:
    data = EXE.read_bytes()
    imports = {dll.lower(): set(symbols) for dll, symbols in parse_imports(data)}
    print(f"[+] probing {EXE}")
    for dll, wanted in TARGETS.items():
        present = imports.get(dll.lower(), set())
        print(f"\n{dll}")
        for name in sorted(wanted):
            print(f"  {'YES' if name in present else 'NO ':>3}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
