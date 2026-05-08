# Morning brief — autonomous overnight session 2026-05-07/08

> One-page summary of what got done overnight. Branch:
> `claude/vacation-2026-05-06`. Read this first; everything else
> linked from here.

## TL;DR

- **The whole infrastructure works.** SSH-driven VM control, SCP push
  of the 71 GB game directory, Mac-side servers (`auth_mock` + `rep_responder`)
  reachable from VM via portproxy, Frida 17 + trust-patch + main hook
  + 25+ internal hooks all installing successfully against
  `NewWorld.exe` under Microsoft Prism.
- **The game still won't reach network init under UTM.** Root cause:
  UTM's `virtio-gpu` returns `VendorId = DeviceId = 0` to DXGI, which
  cascades through CryEngine renderer init leaving hundreds of vtable
  slots null. The first vtable dispatch through a null slot crashes
  the process with `STATUS_ACCESS_VIOLATION` (`CONTEXT.Rip = 0x0`).
- **Frida bypass is exhausted as a path.** Cascade has too many sites
  (200+ `FUN_1470d11a0` dispatches before crash; each "fix" pushes
  the crash to the next null slot).
- **Recommendation: Parallels Desktop.** FAQ-estimated 80%+ probability
  of reaching network init under Parallels' real D3D virtualization.
  All infrastructure built tonight transfers as-is.

## Decision needed

Pick one path, then ping me. I drive the rest:

| Path | Time-to-network-init | Probability | Cost | Maintainer keyboard time |
|---|---|---|---|---|
| Continue UTM + Frida bypass | 3-6+ wakes | <30% | $0 | 0 |
| **Parallels Desktop trial** ★ | 1-2 wakes | 80%+ | $0 (14-day trial) | ~5 min (install + Apple ID consent) |
| Parallels subscription | same | 80%+ | $99.99/yr | ~5 min |
| Physical Windows host | 1 wake | ~95% | hardware | varies |
| AWS Windows-Gaming VM | 1 wake | ~95% | ~$1-2/hr | ~5 min cloud setup |

★ = my recommendation

Full proposal: [`analysis/proposed_patches/parallels_setup.md`](proposed_patches/parallels_setup.md)

## What works (don't redo)

| Component | Status | File |
|---|---|---|
| SSH into Windows VM as admin | ✅ | `ssh -i ~/.ssh/id_ed25519 juni@192.168.64.5` |
| 71 GB game-dir SCP push (~12 min) | ✅ | `scp -r ~/SteamLibrary/NewWorld/* juni@VM:'C:\NewWorldArchive\'` |
| Mac servers (auth_mock + rep_responder) | ✅ | `tools/serve_for_vm.sh` (unprivileged port 4443 default) |
| VM portproxy 127.0.0.1:443 → MAC:4443 | ✅ | `tools/setup_vm_portproxy.ps1` |
| VM hosts file redirects | ✅ | `python tools\setup_hosts.py --apply --target 127.0.0.1` |
| CA trust install in VM | ✅ | `certutil -addstore -f ROOT newworld_ca.crt` |
| Frida 17 spawn + attach + 25+ hooks | ✅ | `frida_capture.py` |
| DTLS trust patch RVA matches binary | ✅ | `frida_dtls_trust_patch.js` |

## What's blocked (don't poke)

- **Game launch under UTM.** Crashes during CryEngine renderer init.
  Diagnostic ceiling reached; further Frida hooks won't help.
- **GPU spoof hook (`frida_gpu_spoof.js`).** Built and works
  (`MessageBoxW` interception confirmed firing) but doesn't address
  the cascade.

## What got built tonight

New files:

- `analysis/proposed_patches/parallels_setup.md` — pivot proposal
- `analysis/proposed_patches/vm_setup_steps.md` (substantial rewrite)
- `analysis/MORNING_BRIEF.md` — this file
- `tools/serve_for_vm.sh` (unprivileged mode added)
- `tools/setup_vm_portproxy.ps1` (new)
- `tools/show_vm_host_ip.sh` (new)
- `tools/client-hooks/frida_gpu_spoof.js` (new)
- `tools/client-hooks/frida_exit_trap.js` (new)
- `tools/ghidra_scripts/FindWideStringXrefs.py` (new)
- `tools/client-hooks/frida_capture.py` (added `--gpu-spoof`,
  `--exit-trap` flags)

Roughly 11 commits this session, ~68 commits on the branch.

## Where the diagnostics live

For deep-dive, the worklog wakes 45-49 cover the full
investigation:

- Wake 45: First E2E smoke — game terminates at GPU
- Wake 46: GPU dialog isn't the gate (auto-IDOK already)
- Wake 47: Initial silent-abort root-cause (had RVA arithmetic error)
- Wake 48: Caught the arithmetic error; identified correct function
- Wake 49: Confirmed cascade is fundamental (CryEngine renderer init)

Worklog: [`analysis/autonomous_worklog.md`](autonomous_worklog.md) (entries appended at the bottom)

VM-side capture artifacts: `C:\first-light\capture\20260507_*_vm_smoke_*\`
(session.log + hooks.log per run; packets.jsonl is empty in all
runs since the game didn't reach network init).

## When you decide

Reply with one of:

1. **"parallels"** — I'll write a step-by-step setup script and
   walk you through the ~5 min interactive part.
2. **"frida"** — I'll resume the bypass investigation with the
   corrected entry-hook RVA and capture more diagnostic data.
3. **"physical"** or **"aws"** — I'll write the corresponding
   setup proposal.
4. **"pause"** — stop iterating, I'll wait until you ping.

If you don't reply, the loop will polish docs and stop iterating
after another 1-2 wakes. No more smoke tests until you decide.
