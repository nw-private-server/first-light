# VM Setup Steps for Local Client-Side Verification

> **Status: Phase A done (UTM already installed). Phases B–F documented
> below for the maintainer to walk through.** Once complete, the VM
> runs the same flow as the existing home setup
> (`tools/client-hooks/frida_capture.py --exe ...`) — just on a
> Windows VM instead of a physical Windows host.

## Why this is now tractable

Per worklog wake 36: the "non-EAC archive" the existing setup uses is
**not a special build**. It's the same `NewWorld.exe` from any source,
launched directly via Frida (`frida.spawn(GAME_EXE)`) instead of
through `NewWorldLauncher.exe`. EAC is wrapper-based; skipping the
wrapper skips EAC entirely. So we already have the bytes we need at
`~/SteamLibrary/NewWorld/` (downloaded via SteamCMD on day 1, ~71 GB).

## Phase A: UTM ✅ DONE

UTM 4.7.5 already installed at `/Applications/UTM.app`. Existing
Linux VM in the data directory; this guide adds a Windows VM
alongside it.

## Phase B: Get Windows 11 ARM64 ISO

Microsoft's free download:
**https://www.microsoft.com/software-download/windows11arm64**

This page uses a session-based download token, so it needs to be
done in a browser (not scriptable). ~5–7 GB, 10–30 min depending
on connection.

Save the `.iso` somewhere accessible — recommend `~/Downloads/`.

License: Microsoft permits using the ISO unactivated for evaluation.
Watermark in the corner is the only visible cost. For our purpose
(running NewWorld.exe long enough to see state advance) activation
isn't needed.

## Phase C: Create the Windows VM in UTM

1. Open UTM → **Create a New Virtual Machine** → **Virtualize**
2. Select **Windows** → check **Install Windows 10 or higher**
3. Click **Browse** for the ISO and pick the file from Phase B
4. Resources:
   - **RAM:** 8192 MB (8 GB) is the floor; 16 GB if you have it
   - **CPU cores:** 4 (or `#cores - 2`, whichever is larger)
   - **Storage:** 100 GB minimum (Windows + Steam + game = ~75 GB)
5. Shared directory (optional but recommended): point at
   `~/SteamLibrary/NewWorld/`. UTM will mount this read-only inside
   the VM.
6. Save the VM. Default name is fine.

## Phase D: Install Windows in the VM

1. Boot the VM. Windows installer starts.
2. Skip product key (link "I don't have a product key" at the
   bottom of the activation screen).
3. Edition: **Windows 11 Pro** (any edition works; Pro has fewer
   bloatware choices).
4. Network setup: skip / "I don't have internet" (Win11 will let
   you make a local account this way; otherwise you're forced to
   sign in with a Microsoft account, which we don't need).
5. Keep clicking through. Default partitioning is fine.
6. Once at the desktop, install **UTM Tools** for the VM (UTM
   menu → Insert UTM Tools ISO, then run the installer inside
   Windows). Improves clipboard sharing and shared-folder support.

This phase is interactive — about 30 min wall-clock with breaks
between screens. Most of it is unattended waiting for installers.

## Phase E: Install dependencies in the VM

Inside Windows:

1. **Steam**: download from steampowered.com, install, log in.
   *This is the maintainer's Steam login step.* Steam Guard code
   from your phone — same flow as SteamCMD on day 1.
2. **Python 3.11**: `winget install Python.Python.3.11` from PowerShell, OR
   download from python.org. Verify: `python --version` shows 3.11.x.
3. **Frida 16+**: `pip install frida-tools` (~10 sec).
4. **Git for Windows** (optional, only if you want to clone the
   project inside the VM): `winget install Git.Git`.

## Phase F: Bring the project + game directory into the VM

Two options:

### Option F-1: Shared folder (recommended)

If you set up a shared directory in Phase C step 5, the game
directory at `~/SteamLibrary/NewWorld/` shows up under
`\\Mac\Home\SteamLibrary\NewWorld\` in Windows. Copy it locally:

```powershell
robocopy "\\Mac\Home\SteamLibrary\NewWorld" "C:\NewWorldArchive" /E /MT:8
```

`/MT:8` runs 8 threads in parallel. ~71 GB transfer over UTM's
shared-folder layer is slow (USB-2 speeds, plan for 30–60 min).

### Option F-2: External drive

Faster if you have a USB 3+ drive. Copy `~/SteamLibrary/NewWorld/`
onto the drive on the Mac, mount it in the VM, copy to
`C:\NewWorldArchive\`. ~10 min.

### Project repo

The autonomous-loop branch is at
`https://github.com/nw-private-server/first-light.git`.
Clone inside the VM (or share the host folder):

```powershell
git clone https://github.com/nw-private-server/first-light.git C:\first-light
git -C C:\first-light fetch origin
git -C C:\first-light checkout claude/vacation-2026-05-06
```

## Phase G: Networking (VM ↔ Host)

The servers run on the Mac; the game runs in the VM. Both server
binaries already bind to `0.0.0.0` by default
(`server/rep_responder.py:60` and `server/auth_mock.py:--host '::'`),
so they're reachable from the VM's network without code changes.

### Find the Mac's IP from the VM's perspective

UTM's default Shared Network mode bridges the VM to the host on
the `192.168.64.0/24` subnet, with the Mac at **`192.168.64.1`**
(verified in this environment).

To confirm or auto-detect, run on the Mac:

```bash
tools/show_vm_host_ip.sh
# 192.168.64.1
```

The script auto-detects the right bridge interface in case UTM's
naming changes between versions. Use this output as
`MAC_IP_FROM_VM` in the steps below.

If you'd rather verify from inside Windows, the default gateway
IS the Mac:

```powershell
ipconfig | Select-String "Default Gateway"
```

### Run the servers on the Mac

```bash
# Terminal 1: HTTPS auth mock with rep address pointing at the Mac
sudo python -m server.auth_mock \
  --port 443 \
  --rep-host MAC_IP_FROM_VM \
  --rep-port 24083

# Terminal 2: DTLS REP server bound to all interfaces
python -m server.rep_responder --port 24083
```

`auth_mock` needs admin (port 443). `rep_responder` doesn't but
will need its UDP port reachable from the VM — UTM's default NAT
should pass UDP fine.

### Redirect hostnames in the VM

Inside Windows, from an Administrator PowerShell:

```powershell
cd C:\first-light
python tools\setup_hosts.py --apply --target-ip MAC_IP_FROM_VM
```

Verify by trying to resolve one of the hostnames:

```powershell
nslookup d3bj4csovi1fe8.cloudfront.net
# Should return MAC_IP_FROM_VM
```

## Phase H: Run NewWorld through the existing setup

Once networking is wired:

```powershell
# Make sure Steam is running + logged in (Phase E step 1)
# Then launch NewWorld via Frida:
cd C:\first-light
python tools\client-hooks\frida_capture.py `
  --exe "C:\NewWorldArchive\Bin64\NewWorld.exe" `
  --name vm_test
```

If you ALSO want the SelfIdent diagnostic hook (worth running first
time to resolve the V3-retry hypothesis tree):

```powershell
# In a second VM PowerShell, after frida_capture.py spawns the game:
frida -p $(Get-Process NewWorld | Select-Object -ExpandProperty Id) `
      -l C:\first-light\tools\client-hooks\frida_self_ident_hook.js
```

Or add the script to `frida_capture.py`'s script-load list so it
attaches at spawn time.

## Expected outcome

If everything works: the game launches under Frida, the trust-patch
takes effect, the game's DTLS connection is redirected to the
Mac-hosted server stub, and the Frida hooks log captured packets to
`capture/<timestamp>_vm_test/packets.jsonl`. State machine advances
through the post-V3 sequence to whatever phase the current server
stub supports.

Performance caveat: Windows ARM64 + x64 emulation via Microsoft Prism
+ UTM hypervisor means the game runs at low FPS (5–15 FPS expected).
For state-machine verification this is fine; for actual play it
isn't.

## Failure modes and fallbacks

- **VM detection by something OTHER than EAC**: unlikely since EAC
  isn't running, but the game may have its own anti-VM checks. If
  so: try CPUID hypervisor-flag spoofing in UTM's QEMU args, or
  switch to a physical Windows host.
- **Frida 16 incompatibility with Windows ARM64**: if Frida fails
  to attach, the project also has a d3d11_proxy DLL approach in
  `tools/client-hooks/d3d11_proxy/` that injects from inside the
  process — different injection mechanism, same end-state.
- **Game refuses to launch with `steam_appid.txt` only**:
  `frida_capture.py` already creates this file automatically, but
  if it still fails, Steam needs to be RUNNING (not just installed).

## What this enables

Once running, the Frida hook from
`tools/client-hooks/frida_self_ident_hook.js` (staged earlier in
the loop) becomes runnable. That resolves the three V3-retry
hypotheses in one observation:

- `FUN_146454c00` fires + `FUN_145a87010` fires → state 10→11
  advancing → V3-retry was correlation-echo (already resolved by
  patch).
- Fires + onConnSuccess doesn't → identity mismatch in replay
  (hypothesis 3).
- Never fires → capture genuinely lacks SelfIdent (hypothesis 2).

Plus the wire-format byte layouts for the seven SelfIdent in-args
get captured in one go, resolving multiple of the project's
remaining "runtime-needed" questions.
