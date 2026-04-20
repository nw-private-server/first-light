# d3d11 Proxy Patch

Runtime-only DLL proxy for New World.

Purpose:
- load as `d3d11.dll` from the game directory
- forward the common `d3d11` exports to the real system DLL
- patch the DTLS trust branch in memory from inside the process

This is the next step after Frida failed with:
- `VirtualAllocEx returned 0x00000005`

## What it patches

Target function:
- `FUN_145dce750`

Target VA:
- `0x145dce8b5`

Original bytes:
- `0F 84 19 01 00 00`

Patched bytes:
- `E9 19 01 00 00 90`

Meaning:
- turns the conditional jump into an unconditional jump
- forces the DTLS driver onto the permissive verify-callback path

## Files

- `d3d11_proxy.cpp`
- `d3d11_proxy.def`
- `build_proxy.bat`

## Build

Open a `x64 Native Tools Command Prompt for VS` and run:

```bat
cd C:\Users\charl\Programs\NewWorldPrivate\tools\d3d11_proxy
build_proxy.bat
```

Output:
- `build\d3d11.dll`

## Deploy

Copy:
- `build\d3d11.dll`

To:
- `H:\SteamLibrary\steamapps\common\New World\Bin64\d3d11.dll`

Do not overwrite the system DLL. This works via normal DLL search order.

## Notes

- This is still an anti-cheat-risky runtime modification.
- It does not modify `NewWorld.exe` on disk.
- The proxy only forwards the most common `d3d11` exports. If the game needs
  more, add them to the `.def` and wrapper file.
- Logging goes to:
  - `%TEMP%\nw_d3d11_proxy.log`
