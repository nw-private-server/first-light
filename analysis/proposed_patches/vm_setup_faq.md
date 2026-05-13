# VM Setup FAQ

> Calibrated answers to questions about running New World in a Windows
> VM on Apple Silicon for protocol verification. Companion to
> [vm_setup_steps.md](vm_setup_steps.md).

## Q: Will Microsoft Prism actually run NewWorld.exe?

**Probably yes, with two real risk areas.**

The translation chain on Apple Silicon:

```
Apple Silicon CPU (ARM64)
  ↓ Apple Hypervisor.framework — native ARM64 virtualization, ~free
Windows 11 ARM64 guest
  ↓ Microsoft Prism — x64 → ARM64 translation
NewWorld.exe (x64)
```

Only Prism is doing actual translation. Hypervisor.framework runs
Windows ARM64 natively. Prism is Microsoft's modern x64 emulator,
mainstream since Windows 11 24H2; it supports AVX/AVX2 (older
versions didn't, which broke many games).

**Real risks:**

1. **GPU virtualization quality.** UTM uses `virtio-gpu` which is
   weaker than Parallels' D3D virtualization. New World needs D3D11;
   if it's strict about GPU capability detection, it may refuse to
   start under UTM specifically. Parallels Desktop ($100/yr) has
   substantially better D3D virtualization and is the obvious
   fallback if UTM fails at D3D init.
2. **Performance.** Even when running, expect 3–10 FPS via Prism +
   virtual GPU. For state-machine verification at low FPS this is
   fine; for actual gameplay it isn't.

**Probability estimates:**
- "Game starts and reaches network init under UTM": 40–60%
- "Game starts and reaches network init under Parallels": 80%+
- "Game runs at playable framerate anywhere on this Mac": low

## Q: Why not just use Windows x64 in the VM instead of Windows ARM64?

**On Apple Silicon, Windows x64 isn't viable.**

`Apple Hypervisor.framework` only virtualizes ARM64 guests. There's
no hardware acceleration path for x86_64. To run Windows x64 on
Apple Silicon, you'd need full software CPU emulation (typically
QEMU TCG mode), which is **30–100× slower than native**. NewWorld
.exe might take an hour to reach login screen, if it doesn't time
out and crash first.

The viable path is Windows ARM64 + Microsoft Prism for x64 apps:

```
Windows ARM64 + Prism:                  Windows x64 emulated:
  Hypervisor.framework: native ARM64      QEMU TCG: software emulation
  Prism: ~30–50% overhead                 Direct execution but on emulated CPU
  RESULT: usable                          RESULT: 30–100× slowdown, unusable
```

On Intel Macs the answer flips — Intel Macs ran Windows x64 at
near-native speed. Apple Silicon broke that.

## Q: How does the project's "non-EAC" trick actually work?

**It skips the EAC launcher chain entirely.**

EAC integration is wrapper-based. Normal launch flow:

```
NewWorldLauncher.exe → EasyAntiCheat_Launcher.exe → NewWorld.exe
                       ↑ EAC bootstraps here
```

The project's `tools/client-hooks/frida_capture.py:251` does
`frida.spawn(NewWorld.exe)` directly. EAC never starts because its
wrapper never runs. The game's own launch-context checks are
satisfied by:
- `steam_appid.txt = 1063730` next to `NewWorld.exe`
  (frida_capture.py creates this on every spawn)
- A running Steam process (logged in)

There's no patched binary, no cracked version, no community-sourced
alternate build. The "archive" the project's docs reference is
just a copy of the game directory pointed at by `--exe` flag.

## Q: Will EAC detect the VM and refuse to launch the game?

**No — EAC never runs in this flow, so it never gets a chance to
detect anything.**

EAC's anti-VM and anti-tamper detection happens during EAC's own
initialization. Skipping the launcher means EAC isn't initialized.
The game's own checks are network-level (Steam launch context,
appid match) and don't involve VM detection.

This is the same reason Phase G works on the project's existing
Windows hosts — the home setup also uses `frida.spawn()` to skip
the launcher. The VM scenario is the same playbook on a different
host.

## Q: What if UTM doesn't work?

**Parallels Desktop is the obvious commercial fallback.** Better D3D
virtualization, mature Windows-on-Mac support, $100/yr. If New
World refuses to start under UTM due to GPU detection, Parallels is
probably still feasible.

**VMware Fusion** is now free for personal use but its GPU support
on Apple Silicon is between UTM and Parallels.

**Physical Windows host** is the always-works fallback — a Bootcamp
partition (Intel Mac only, this Mac is Apple Silicon so no
Bootcamp), a separate Windows PC, or a cloud Windows VM with GPU
passthrough (e.g. AWS/Azure Windows-Gaming images, ~$1–2/hr).

## Q: Why 71 GB to copy into the VM? Can we avoid that?

The full game directory is ~71 GB; that includes all assets,
shader caches, voice packs. Most of it is the asset PAK files;
NewWorld.exe itself is 171 MB.

For our purpose (boot far enough to fire the SelfIdent handler):
**we may not need the full 71 GB.** Worth experimenting:
- **Minimum**: `Bin64/`, `EasyAntiCheat/` (likely not needed
  since we skip it but the game might load DLLs from there),
  `bootstrap.cfg`, `engine.json`, `installscript.vdf`, plus
  whatever PAK files are referenced for the main menu.
- **First-attempt minimum**: copy `Bin64/` + small support files
  (~500 MB), see if the game starts; iterate by checking what it
  complains about missing.

This is a follow-up if the full 71 GB transfer is too painful.
For first attempt, copy everything; UTM's shared folder is slow
but not catastrophic.

## Q: How long should the full setup take?

**Wall-clock estimate, with normal pauses:**

| Phase | Active time | Wait time |
|---|---|---|
| A. UTM install | ✅ done | — |
| B. Windows ISO download | ~5 min | 10–30 min download |
| C. Create UTM VM | ~5 min | — |
| D. Install Windows | ~10 min clicking | ~20–30 min unattended |
| E. Steam + Python + Frida | ~10 min | — |
| F. Copy game dir | ~5 min start | 30–60 min transfer |
| G. Networking config | ~5 min | — |
| H. Launch NewWorld via Frida | ~2 min | first-launch shader compile |
| **Total** | **~45 min** | **~60–120 min** |

Roughly a 2–3 hour session end-to-end, mostly waiting on
unattended steps. The maintainer's keyboard time is the active
~45 min spread across the whole window.

## Q: What if Frida can't attach on Windows ARM64?

The project's `tools/client-hooks/d3d11_proxy/` is the documented
fallback. It's a DLL proxy that injects from inside the process
when Frida fails (the README cites
`VirtualAllocEx returned 0x00000005` as the failure mode).

The trust-patch JS hook (`frida_dtls_trust_patch.js`) gets
applied via the DLL proxy mechanism instead of via Frida's spawn
flow. Same end-state: cert pinning bypassed, our local server
accepted.

If both Frida and d3d11_proxy fail on Windows ARM64, the next
fallback is a physical Windows host or Parallels (better Frida
support).

## Q: Is doing this even worth it given the perf cost?

**For our use case, yes.** What we need is:
1. The game launches.
2. Reaches network init.
3. Sends V3 RegistrationRequest.
4. Frida hooks fire.
5. We capture the SelfIdent handler args at runtime.

Steps 1–4 don't need playable framerate. Step 5 is the unlock —
one live observation resolves the three V3-retry hypotheses
(correlation echo / missing SelfIdent / character_uuid mismatch)
AND captures wire-format byte layouts for the seven SelfIdent
in-args.

**Multiple "runtime-needed" project questions collapse to a
single live session.** That alone justifies the setup cost.

If the project's path to in-game (state 14) gets blocked at a
later phase that needs full graphical / input / movement testing,
*then* the VM setup hits real limits and a physical host becomes
necessary. But for the immediate state-10 → state-11 unlock,
low-FPS verification is fine.
