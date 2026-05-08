# Parallels Desktop pivot — proposal

> **Status: proposal awaiting maintainer decision.** Companion to
> [vm_setup_steps.md](vm_setup_steps.md) and [vm_setup_faq.md](vm_setup_faq.md).
> The UTM setup works for everything except actually launching the
> game; this doc proposes Parallels Desktop as the alternate VM
> backend that should clear the GPU virtualization issue.

## Why pivot

Wake 47 / 48 traced the smoke test's silent abort to a virtual-call
dispatch inside `FUN_1470d11a0` (NewWorld.exe RVA `0x70d11a0`):

```c
void FUN_1470d11a0(longlong *param_1, ..., ..., ...) {
    (**(code **)(*param_1 + 8))(param_1, ...);  // crash at +0x15
}
```

`param_1` is a null/invalid pointer at the moment of the call. This
is a downstream consequence of UTM's `virtio-gpu` exposing
`VendorId = DeviceId = 0` to DXGI: the engine's GPU subsystem
half-initializes some object, then a different subsystem (audio /
scene-graph / asset-stream — nailing the caller is the next yak)
tries to dispatch through that object's vtable and crashes.

The path to fixing this with Frida hooks alone is a long tail:

| Wake | Hypothesis | Reality |
|---|---|---|
| 45 | `MessageBoxW(MB_DEFBUTTON2)` is the gate | Auto-OK was already happening |
| 46 | `FUN_147143960` returns 0 because of MB cancel | Returns 1 naturally |
| 47 | `FUN_147143960` returns 0 because render init fails | Returns 1 — different exit path |
| 48 | The crash is in `FUN_1410d1120` (decompiled wrong addr) | Actual addr is `FUN_1470d11a0` (4-instruction thunk) |
| 49+ | Hook `FUN_1470d11a0` to skip the call | Then the next subsystem crashes ... |

Each iteration narrowed the target but the underlying issue (no real
GPU) has cascading effects all over the engine. Estimate to reach
network init via Frida bypass: 3-6 more wakes, no guarantee of
success, and any successes are fragile (release-version-specific RVAs).

## What Parallels gives us

From `vm_setup_faq.md`:

> "Game starts and reaches network init under UTM": 40-60%
> "Game starts and reaches network init under Parallels": 80%+

Parallels Desktop has substantially better Direct3D virtualization
than UTM's `virtio-gpu`. DXGI returns real-looking adapter info
(non-zero VendorId/DeviceId, working `GetDesc` callback), the engine
GPU init succeeds, and all the cascading null-pointer dispatches
disappear.

Importantly, **everything else we built tonight is reusable**:

- **SCP push of the 71 GB game directory** — works the same to a
  Parallels VM
- **SSH into the VM** — works the same; only the Mac-side IP and
  default routes differ
- **`tools/serve_for_vm.sh` Mac-side servers** — works the same
- **`tools/setup_vm_portproxy.ps1` VM-side portproxy** — works the
  same (Windows VM is Windows VM)
- **`tools/setup_hosts.py` redirects** — works the same
- **CA install via `certutil`** — works the same
- **Frida 17 + the trust patch + main hook + GPU-spoof hook** —
  all work the same; we just won't NEED the GPU-spoof if Parallels'
  D3D works. Trust patch is still needed.

The only delta is: which VM backend hosts the Windows install.

## Cost

| Item | Cost |
|---|---|
| Parallels Desktop trial | Free (14 days) |
| Parallels Desktop personal license | $99.99/yr standalone, $59.99/yr if you have a Pro Mac |
| Wall-clock to set up | ~30 min (skip Phase B-D using existing Win11-ARM64.iso, install Parallels Tools, install Steam etc., or import an existing UTM image) |
| Wall-clock for game launch / smoke test | ~5 min for first run + ~5 min for first-launch shader compile |

The trial is fully featured for 14 days — easily long enough to
validate that Parallels gets us to network init. If yes, decide
whether to subscribe; if no, we're back to where we are now and
can pursue physical Windows host or AWS Windows VM.

## Setup walkthrough

### 1. Install Parallels Desktop trial

Download from `https://www.parallels.com/products/desktop/trial/`.
Standard installer, ~5 min.

> The first launch asks for an Apple ID-style sign-in to start the
> trial. It DOES work without entering a license key — choose
> "Continue Trial" / "Use Without Activation" depending on the UI.

### 2. Create a Windows 11 ARM64 VM

The fastest path: when Parallels first launches, click "Get Windows
11 from Microsoft" — Parallels handles the ISO download and VM
provisioning automatically (Microsoft has a partnership with
Parallels for this). ~10 min unattended.

Alternatively, point Parallels at the existing
`~/Downloads/Win11_25H2_English_Arm64_v2.iso` from the UTM setup.

VM resources: same as UTM — 8 GB RAM minimum (16 GB recommended),
4 CPU cores, **120 GB disk** (NOT 100; UTM's recovery-partition
caveat applies the same way).

### 3. Configure VM

After Windows install:
- Install Parallels Tools (one-click in Parallels menu)
- Settings → Hardware → Graphics: enable "Resource Use" =
  "More resources for graphics" if available; this trades CPU for
  better D3D fidelity.
- Settings → Network: default Shared Network mode (matches UTM's
  default; the Mac will be reachable on `10.211.55.2` instead of
  UTM's `192.168.64.1`).

### 4. Adapt host IP detection

`tools/show_vm_host_ip.sh` currently looks for UTM's `bridge100`
interface. Parallels uses `vnic0`/`vnic1` and a different bridge
device (`bridge0` historically). The script should be extended:

```bash
# Parallels detection: vnicNNN with 10.211.55.x range
ip=$(ifconfig | awk '
    /^vnic[0-9]+:/ { iface=$1; next }
    /^bridge[0-9]+:/ { iface=$1; next }
    /^[a-z]/ { iface="" }
    iface != "" && /inet 10\.211\.55/ { print $2; exit }
    iface != "" && /inet 192\.168/ { print $2; exit }
')
```

Or just override at launch time: `tools/serve_for_vm.sh` already
falls back to `192.168.64.1`; add a fallback to `10.211.55.2` for
Parallels.

### 5. Reuse the rest

Once networking shows the right IP, the entire VM client-side
sequence works as-is:

```powershell
# In the Parallels VM, Administrator PowerShell:
git clone https://github.com/nw-private-server/first-light.git C:\first-light
git -C C:\first-light checkout claude/vacation-2026-05-06
certutil -addstore -f "ROOT" C:\path\to\newworld_ca.crt
cd C:\first-light
python tools\setup_hosts.py --apply --target 127.0.0.1
.\tools\setup_vm_portproxy.ps1 -MacIp 10.211.55.2

# Push game directory from Mac:
scp -r ~/SteamLibrary/NewWorld/* juni@<parallels-vm-ip>:'C:\NewWorldArchive\'

# Then on Mac:
tools/serve_for_vm.sh

# Then in VM:
python tools\client-hooks\frida_capture.py `
    --exe C:\NewWorldArchive\Bin64\NewWorld.exe `
    --name parallels_smoke_001
# (no --gpu-spoof needed if Parallels' D3D works)
```

If Parallels' D3D really works, we should see `[steam] SteamAPI_Init -> 0`
followed by the game proceeding past where it dies under UTM, and
eventually `[ws2] WSASend(...)` events as the client reaches out
to our auth_mock.

## Decision matrix

| Path | Time to network init | Probability of success | Cost |
|---|---|---|---|
| Continue UTM + Frida bypass | 3-6 wakes, fragile | <30% | $0 |
| Parallels Desktop trial | 1-2 wakes | 80%+ | $0 (trial) |
| Parallels Desktop subscription | same | 80%+ | $99.99/yr |
| Physical Windows host | 1 wake | ~95% | hardware + setup |
| AWS Windows-Gaming VM | 1 wake | ~95% | $1-2/hr |

## What I can / can't do autonomously

I can't install Parallels itself — it's a Mac GUI app with a
licensed trial registration that needs an Apple ID confirmation
loop and a one-time install permission grant. That step needs the
maintainer's keyboard for ~5 min.

After Parallels is installed, I CAN:
- Drive the Windows install + tooling setup via SSH (if SSH is
  enabled the same way it was for the UTM VM)
- SCP the game files
- Update host IP detection scripts
- Run the smoke tests

So the maintainer's interactive step is bounded to: install
Parallels (5 min), boot the Windows VM into the desktop (10-30
min unattended), enable SSH server with the same admin
authorized_keys quirk we used for UTM, then ping me with the new
VM's IP. From there I drive.

## Open questions for maintainer

1. **Trial vs commit:** Comfortable using the 14-day Parallels
   trial as a yes/no test, or want to wait until you've decided
   whether you'd subscribe?
2. **VM disk reuse:** Parallels can import UTM `.utm` packages with
   moderate friction. Worth trying that to skip the Windows
   reinstall, OR just create a fresh Parallels VM since the only
   things in the UTM VM are Steam (login required) and game files
   (SCP-pushed in ~12 min)?
3. **If Parallels also fails:** physical Windows host or AWS GPU
   VM as the next fallback? The latter costs $1-2/hr but no
   hardware required.

Filing this as a proposal, not a commitment. Awaiting input.
