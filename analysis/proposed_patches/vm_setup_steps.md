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

### Where the shared folder shows up

UTM's SPICE WebDAV agent mounts a configured shared directory as
**Z:\\** in Windows (specifically `\\localhost@9843\DavWWWRoot`,
mapped automatically). It does **not** appear under `\\Mac\Home\...`
— that path comes from Parallels/VMware Fusion documentation and
does not apply to UTM.

So with Phase C step 5 pointing at `~/SteamLibrary/NewWorld/`, the
game directory contents show up at `Z:\Bin64\`, `Z:\assets\`, etc.

Verify before continuing:

```powershell
Test-Path Z:\Bin64\NewWorld.exe
# True
```

### ⚠️ SPICE WebDAV's 100 MB read-size cap

UTM's SPICE WebDAV (drive `Z:`) **silently fails reads on files
larger than ~100 MB** with `ERROR 223 (0x000000DF) — The file
size exceeds the limit allowed and cannot be saved.` This affects:

- `Z:\Bin64\NewWorld.exe` (171 MB) — robocopy skips it; Frida
  spawn fails with the same error code.
- 76 PAK files in `Z:\assets` (70.67 GB total).

**Implication:** "run direct from Z:" and "symlink assets to Z:"
both fail in practice. The game can't launch from Z:, and even
if it could, asset PAK loads would fail. You need a real local
copy of everything large.

### Option F-1: Full local copy via SCP push from the Mac

Once SSH-from-Mac-to-VM is available (see Phase E quirks for the
`administrators_authorized_keys` requirement), push the whole
tree directly:

```bash
# On the Mac:
scp -r -i ~/.ssh/id_ed25519 ~/SteamLibrary/NewWorld/* \
  juni@<VM-IP>:'C:\NewWorldArchive\'
```

Throughput on UTM Shared Network: ~95 MB/s in practice. 71 GB
takes ~12 minutes. SCP also bypasses Defender realtime scan
(set exclusions first: `Add-MpPreference -ExclusionPath
C:\NewWorldArchive`).

This is the recommended path if SSH access is set up.

### Option F-2: Robocopy from Z: (small files only)

Robocopy from `Z:` works for files **under 100 MB**. Use this for
the small DLLs and support files, then SCP-push the large ones:

```powershell
# Most of Bin64, EasyAntiCheat, _CommonRedist are <100 MB
robocopy "Z:\Bin64"         "C:\NewWorldArchive\Bin64"         /E /MT:8
robocopy "Z:\EasyAntiCheat" "C:\NewWorldArchive\EasyAntiCheat" /E /MT:8
robocopy "Z:\_CommonRedist" "C:\NewWorldArchive\_CommonRedist" /E /MT:8
robocopy "Z:\" "C:\NewWorldArchive\" /XD assets Bin64 EasyAntiCheat _CommonRedist /COPYALL
```

Then SCP-push only the files that were skipped (NewWorld.exe + the
77 large PAKs).

### Disk space caveat: extend C: to use the full disk

A fresh 100 GB Windows install ships with `C:` at ~99 GB and a
~750 MB recovery partition at the tail blocking extension. To
fit the 71 GB game directory + Windows + tools, drop the recovery
partition and extend C:

```powershell
# Administrator PowerShell:
Remove-Partition -DiskNumber 0 -PartitionNumber 4 -Confirm:$false
$max = (Get-PartitionSupportedSize -DriveLetter C).SizeMax
Resize-Partition -DriveLetter C -Size $max
```

(Recovery partition is fine to lose on a throwaway verification
VM — it's the partition Windows boots into for "Reset this PC,"
which we don't need.)

Total local disk used: ~430 MB instead of 71 GB.

### Option F-3: External drive

Faster if you have a USB 3+ drive AND enough VM disk. Copy
`~/SteamLibrary/NewWorld/` onto the drive on the Mac, mount it in
the VM, copy to `C:\NewWorldArchive\`. ~10 min. Same disk-space
caveat as F-1.

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

**One-shot launcher** (recommended) — defaults to unprivileged
mode (auth_mock on :4443, no sudo); runs both servers, Ctrl-C stops
both:

```bash
tools/serve_for_vm.sh
```

It prints a one-liner for the VM-side portproxy that pairs with
this. Use `--privileged` to fall back to port 443 + sudo (mostly
useful for direct-physical-Windows scenarios where there's no VM
to run a portproxy in).

**Or manually in two terminals**:

```bash
# Terminal 1: HTTPS auth mock on :4443 (unprivileged)
.venv/bin/python -m server.auth_mock \
  --port 4443 \
  --rep-host "$(tools/show_vm_host_ip.sh)" \
  --rep-port 24083

# Terminal 2: DTLS REP server on UDP/24083
.venv/bin/python -m server.rep_responder --bind-port 24083
```

`rep_responder` doesn't need admin and binds UDP/24083 directly —
the client connects to MAC_IP:24083 on its own (auth_mock's
`/login` response carries the rep address).

### Set up the VM client side

Three one-time steps inside the VM, all from an Administrator
PowerShell:

```powershell
# 1. Trust the auth_mock CA (path is wherever you SCP'd the
#    regenerated newworld_ca.crt; or use server\certs\newworld_ca.crt
#    if you committed it):
certutil -addstore -f "ROOT" C:\path\to\newworld_ca.crt

# 2. Redirect Amazon hostnames to localhost:
cd C:\first-light
python tools\setup_hosts.py --apply --target 127.0.0.1

# 3. Forward 127.0.0.1:443 -> MAC_IP:4443 (matches the Mac's
#    auth_mock unprivileged port):
.\tools\setup_vm_portproxy.ps1
```

Verify reachability after starting the Mac servers:

```powershell
Test-NetConnection 127.0.0.1 -Port 443         # should be True
Test-NetConnection 192.168.64.1 -Port 4443     # also True
```

(If you're using `--privileged` mode on the Mac, skip step 3 and
use `--target 192.168.64.1` in step 2.)

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

> **Important:** SPICE WebDAV (drive `Z:`) silently truncates
> reads on files larger than ~100 MB with `ERROR_FILE_TOO_LARGE`
> (0xDF). NewWorld.exe is 171 MB and many asset PAKs are over
> 1 GB, so the F-0 "run direct from Z:" approach was found
> non-viable in practice. Use Option F-2 (local copy via SCP-push;
> see Phase F above).

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
