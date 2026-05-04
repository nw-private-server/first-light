# CTD Investigation - 2026-05-04 character-select crashes

## Summary

Two reproducible CTDs at character-select today (and at least four total). All four crashes are **the same bug, same instruction, same exception code**.

| Time | PID (dec) | PID (hex) | Source |
|------|-----------|-----------|--------|
| 13:30:21 | 19216 | 0x4B10 | session.log + WER + .dmp |
| 14:35:26 | 15540 | 0x3CB4 | session.log + WER + .dmp |
| 14:36:48 | 37948 | 0x943C | WER + .dmp |
| 14:48:17 | 33376 | 0x8260 | WER + .dmp |

## Crash artifacts found

- **Minidumps** in `C:\Users\charl\AppData\Local\CrashDumps\`
  - `NewWorld.exe.19216.dmp` (96 MB, 13:30)
  - `NewWorld.exe.15540.dmp` (96 MB, 14:35)
  - `NewWorld.exe.37948.dmp`, `NewWorld.exe.33376.dmp` (today's other CTDs)
- **WER reports** in `C:\ProgramData\Microsoft\Windows\WER\ReportArchive\AppCrash_NewWorld.exe_*` (4 entries today)
- **Application Event Log** `Application Error` event id 1000 at 13:30:18 and 14:35:23 (and 14:36, 14:48). Verbatim from 13:30:

```
Faulting application name: NewWorld.exe, version: 1.400.6031.40375
Faulting module name:      NewWorld.exe, version: 1.400.6031.40375
Exception code:  0xc0000005   (access violation)
Fault offset:    0x0000000003007ec3
Faulting process id: 0x4B10  (= PID 19216, the 13:30 crash)
Faulting application path: G:\NewWorldArchive\GameClient\Bin64\NewWorld.exe
Bucket: 1843783487914520197 / 9c5bbc985b25fc5649966f503fe02e85
```

All four crashes share the **same WER bucket** (1843783487914520197) and **same Fault Offset 0x3007ec3** => deterministic same code site. NewWorld.exe ImageBase = 0x140000000, so absolute crash address = **0x143007EC3** (in NewWorld.exe `.text`, not in any third-party DLL).

## Loaded modules at crash time (relevant subset)

WER LoadedModule list shows the following **non-default** DLLs in-process at crash:

- `C:\Users\charl\AppData\Local\Medal\HookDLL\MedalHook_19216\medal-hook64.dll` (per-PID hook injected by Medal.tv)
- `C:\Program Files (x86)\RivaTuner Statistics Server\RTSSHooks64.dll`
- `C:\Program Files (x86)\Steam\gameoverlayrenderer64.dll`
- `C:\WINDOWS\system32\nvspcap64.dll` (NVIDIA ShadowPlay capture)
- `G:\NewWorldArchive\GameClient\Bin64\sl.interposer.dll` (NVIDIA Streamline / DLSS)
- `C:\Program Files\Bonjour\mdnsNSP.dll`
- `frida-agent.dll`
- `EOSSDK-Win64-Shipping.dll` (Easy Anti-Cheat / Epic Online)

`Get-Process medal*` confirms 8 Medal processes running including MedalEncoder. The medal-hook64.dll path embeds the target PID (`MedalHook_19216`, `MedalHook_15540`), proving Medal injects fresh per spawn.

## Last events before the 14:35 crash (T-3.4s)

```
14:35:22.908  ws2 ConnectEx(0x24f0) -> [::1]:443         (motd worlds JSON to local responder)
14:35:22.909  winhttp 200 OK ... worlds_STEAM_APP_ID.json
14:35:22.998  ui  CreateWindowExW class=medal_temp_d3d_window_4039785 title=Temp Window
14:35:26.384  Session detached: process-terminated
```

The **Medal "temp d3d window" creation** at T-3.4s is Medal's standard pattern when it (re)attaches its capture hook to the game's swapchain. The 13:30 session shows the same window creation (13:29:36, T-44s) followed by no further game-thread Frida hooks before the crash. The fault is inside NewWorld.exe code (not medal-hook64.dll), but the trigger window opens after Medal hooks the swapchain.

## Faulting module + exception

- **Faulting module:** NewWorld.exe (in-process, not a third-party DLL)
- **Exception:** 0xc0000005 access violation at NewWorld.exe+0x3007ec3 (abs 0x143007EC3)
- **Same instruction across all four crashes today** -> deterministic crash, not heap corruption noise

## Root-cause hypothesis

**Medal.tv's `medal-hook64.dll` swapchain hook is corrupting a D3D11/DXGI object that NewWorld dereferences at character-select.** The crash is in game code (consistent with a stale/garbled DXGI swap-chain or device-context vtable read inside the game), but the smoking-gun environmental cause is the per-PID Medal hook injecting after game launch (note: Medal HookDLL path contains the target PID, so the hook is built dynamically each spawn). The 14:35 session shows Medal's `medal_temp_d3d_window_*` CreateWindowExW immediately followed by the crash. RTSSHooks64.dll and nvspcap64.dll also hook the swapchain and contribute to the conflict pile, but Medal is the only one whose presence aligns with the recent crash regression.

## Remediation (in priority order)

1. **Kill Medal first** (highest signal). PowerShell as admin:
   ```powershell
   Get-Process Medal*, MedalEncoder | Stop-Process -Force
   ```
   Then relaunch NewWorld and re-run the Frida capture. If the 0x3007ec3 crash disappears, Medal is confirmed.
2. If still crashing, kill **RivaTuner Statistics Server** (`RTSS.exe`, `EncoderServer.exe`).
3. Then kill **NVIDIA ShadowPlay overlay**: `nvcontainer.exe` instances and disable in-game overlay in GeForce Experience.
4. Disable **Steam in-game overlay** for New World (Steam -> Library -> NW -> Properties -> uncheck "Enable Steam Overlay").
5. If a clean-environment run still hits 0x143007EC3 deterministically, the bug is real game code (likely tickled by our REP path landing the client somewhere it normally cannot reach). In that case open the dump in WinDbg/Visual Studio: `windbg -z C:\Users\charl\AppData\Local\CrashDumps\NewWorld.exe.19216.dmp` and run `!analyze -v` to get the function name at +0x3007ec3 - then we know whether to add a Frida bypass for that path.

The cheapest first try is step 1; do that before any code change.
