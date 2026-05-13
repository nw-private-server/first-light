# Morning brief — autonomous overnight session 2026-05-07/08

> One-page summary of what got done overnight. Branch:
> `claude/vacation-2026-05-06`. Read this first; everything else
> linked from here.

> **Historical-snapshot note (added wake 238)**: this doc was a
> one-shot briefing from wake 70 (2026-05-08) asking the
> maintainer to pick a runtime path after Parallels Desktop
> failed the same way UTM did. The decision was implicitly made
> by the loop continuing on the static-RE path; runtime testing
> remains blocked on a real-GPU Windows host. The codec/test
> counts cited below are wake-70-era and now far out of date
> (current state: 40/40 captured-codec coverage, 456 tests, see
> the [wake-227 third-stretch retrospective](session_retrospective_227.md)).
> Keeping this doc frozen as the wake-70 snapshot rather than
> refreshing in place — its purpose was point-in-time decision
> support, not a rolling status page.

## TL;DR (updated 2026-05-08)

- **Parallels Desktop test = failed.** Set up end-to-end while you
  slept (Windows 11 ARM64 VM, Steam, Python x64, Frida, repo, certs,
  hosts redirects, portproxy, full 71 GB game push, VC++ + DirectX
  runtimes). Smoke test reached the same exit cascade as UTM:
  AZoth "Unsupported video card" dialog → `FUN_147143960` returns 1
  naturally → game calls `TerminateProcess(self, 1)` explicitly.
- **Both VM backends fail the same way.** Apple Silicon's
  paravirtualized GPU (UTM virtio-gpu and Parallels' D3D
  virtualization) presents `VendorId = DeviceId = 0` to DXGI; the
  game's renderer-init checks reject any guest without a real GPU.
- **Diff vs UTM:** Parallels exits cleanly via explicit
  `TerminateProcess` instead of UTM's silent
  `STATUS_ACCESS_VIOLATION`. The new `exit_trap` hooks (wake 47/48)
  caught both `NtTerminateProcess` AND `ZwTerminateProcess` this
  time. Otherwise identical.
- **All non-runtime work is healthy.** 8 javelin codecs, 182
  passing tests, replay-mining inventory, infrastructure
  (SSH-driven setup, SCP, Mac-side servers) all production-ready.

## Decision needed (revised)

The VM-on-Apple-Silicon path is exhausted. Pick one of:

| Path | Time-to-network-init | Probability | Cost | Maintainer keyboard time |
|---|---|---|---|---|
| Physical Windows host (Bootcamp / spare PC) | 1 wake | ~95% | hardware on hand | install game + my pubkey |
| **AWS Windows-Gaming GPU VM** ★ | 1 wake | ~95% | ~$1-2/hr on-demand | ~10 min cloud setup |
| Continue VM-only Frida bypass | 4-8+ wakes | <20% | $0 | 0 |
| Pause runtime work, keep static RE going | indefinite | n/a | $0 | 0 |

★ = my recommendation. Spin up only when you want to test; tear down
when done. The infrastructure built for UTM/Parallels transfers
verbatim — only the VM creation step changes.

Full FAQ: [`analysis/proposed_patches/vm_setup_faq.md`](proposed_patches/vm_setup_faq.md)

## What works (don't redo)

| Component | Status | File |
|---|---|---|
| SSH into Windows VM (UTM or Parallels) | ✅ | `ssh -i ~/.ssh/id_ed25519 juni@<vm-ip>` |
| 71 GB game-dir SCP push (~10-12 min) | ✅ | `scp -r ~/SteamLibrary/NewWorld/* juni@VM:'C:\NewWorldArchive\'` |
| Mac servers (auth_mock + rep_responder) | ✅ | `tools/serve_for_vm.sh` |
| VM portproxy 127.0.0.1:443 → MAC:4443 | ✅ | `tools/setup_vm_portproxy.ps1` |
| VM hosts file redirects | ✅ | `python tools\setup_hosts.py --apply --target 127.0.0.1` |
| CA trust install in VM | ✅ | `certutil -addstore -f ROOT newworld_ca.crt` |
| Frida 17 spawn + attach + 25+ hooks | ✅ | `frida_capture.py` |
| DTLS trust patch RVA matches binary | ✅ | `frida_dtls_trust_patch.js` |
| `tools/show_vm_host_ip.sh` handles UTM **and** Parallels | ✅ | bridge100 192.168/10. ranges |
| Required runtimes (must install on fresh VM) | ✅ | VC++ 2022 x64+x86, DirectX June 2010 |

## What's blocked (don't poke)

- **Game launch under any Apple-Silicon-hosted VM.** Both UTM and
  Parallels confirmed today to fail at GPU validation. The game's
  D3D11 vendor/device ID check is strict; paravirtualized GPUs
  don't satisfy it.

## What got done overnight (2026-05-07/08)

Wake 70 (Parallels):

- New: nothing repo-side beyond an extra `show_vm_host_ip.sh`
  regex (commit `a827d6e`).
- VM-side: full Parallels Win11 ARM64 environment, Steam logged
  in, repo + certs + hosts + portproxy + 71 GB game push, VC++
  and DirectX runtimes installed, two smoke tests run.
- Result: same cascade as UTM. See `autonomous_worklog.md`
  wake-70 entry for the detailed event log.

Earlier wakes (replay-mining + codec library) — unrelated to VM:

- 8 dedicated codecs (`level_info_changed`, `self_ident`,
  `session_identity_beacon` 0x1b88, `session_message_a4` 0xa4,
  `init_message_18a6` 0x18a6, `session_clock_beacon` 0x14f,
  `heartbeat_15d` 0x15d R/W, `level_descriptor_663` 0x663)
- 182 round-trip + cross-replay tests passing
- `analysis/replay_message_inventory.md` — frequency table +
  per-type byte analysis

## Where the diagnostics live

The worklog wakes 45-49 + 70 cover the full VM/runtime
investigation:

- Wake 45: First E2E smoke — game terminates at GPU (UTM)
- Wake 46: GPU dialog isn't the gate (auto-IDOK already)
- Wake 47: Initial silent-abort root-cause (RVA arithmetic error)
- Wake 48: Caught the arithmetic error; identified correct function
- Wake 49: Confirmed cascade is fundamental (CryEngine renderer init)
- **Wake 70: Parallels reproduces the same cascade** —
  paravirtualized GPU on Apple Silicon doesn't pass the game's
  hardware checks regardless of hypervisor

Worklog: [`analysis/autonomous_worklog.md`](autonomous_worklog.md)

Capture artifacts (Parallels VM):
`C:\first-light\capture\20260508_231955_parallels_smoke_001\`

## When you decide

Reply with one of:

1. **"physical"** — write up Bootcamp / spare PC setup proposal
2. **"aws"** — write up AWS Windows-Gaming setup proposal
3. **"static"** — pause runtime entirely; keep static RE +
   replay-codec mining only (this is what the loop is doing now)
4. **"pause"** — stop iterating; I'll wait until you ping

If you don't reply, the loop continues mining replay codecs and
documenting protocol details from the static-RE side. There's
genuine remaining work there (5-10 message types in the inventory
worth characterizing) — no further smoke tests until you choose
a runtime path.
