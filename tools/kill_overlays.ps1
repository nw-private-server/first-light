# Kill third-party overlay/recorder processes that conflict with Frida instrumentation
# of NewWorld.exe. Run this BEFORE launching the game to avoid CTDs.
#
# Background: 4/4 NewWorld CTDs on 2026-05-04 were access violations at
# NewWorld.exe+0x3007ec3, with Medal, RTSS, ShadowPlay, Steam overlay, and
# NVIDIA Streamline all loaded. See analysis/ctd_investigation.md.
#
# Discord can stay running (its overlay didn't show in the crash dump module
# list). Disable in-game overlays for NW manually in Steam settings + NVIDIA
# App settings if you keep crashing.

$names = @(
    "Medal",                # Medal.tv main process
    "MedalEncoder",         # Medal capture encoder
    "RTSS",                 # RivaTuner Statistics Server (MSI Afterburner)
    "RTSSHooksLoader64",    # RTSS hook loader
    "ESDDiscord",           # third-party Discord enhancement
    "com.barraider.obstools" # Stream Deck OBS plugin
)

$killed = @()
foreach ($name in $names) {
    $procs = Get-Process -Name $name -ErrorAction SilentlyContinue
    if ($procs) {
        $procs | Stop-Process -Force -ErrorAction SilentlyContinue
        $killed += "$name ($($procs.Count))"
    }
}

if ($killed.Count -eq 0) {
    Write-Output "[ok] no overlay processes were running"
} else {
    Write-Output "[ok] killed: $($killed -join ', ')"
}

# Also warn if Discord is running with overlay potentially enabled
$discord = Get-Process -Name "Discord" -ErrorAction SilentlyContinue
if ($discord) {
    Write-Output "[warn] Discord ($($discord.Count) procs) still running. If you still get CTDs, disable Discord overlay in Settings -> Game Overlay."
}
