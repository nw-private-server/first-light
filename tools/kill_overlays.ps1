# Kill third-party overlay/recorder processes that hook into NewWorld.exe.
#
# IMPORTANT (2026-05-04): the deterministic CTD at NewWorld.exe+0x3007ec3 was
# NOT caused by these overlays — it was caused by auth_mock not emitting an
# ETag response header (the game strlens it on every CMS HTTP load). Fixed
# in auth_mock._respond. See analysis/decomp_crash_site.txt.
#
# This helper is now an OPTIONAL "if you still see crashes after the ETag
# fix, try killing third-party hooks too" fallback. Cross-session analysis
# in analysis/ctd_correlations.md shows Medal in BOTH CTD and successful
# sessions, so it's not the primary culprit — but Medal/RTSS/ShadowPlay
# all hook the D3D pipeline and CAN cause indirect issues.

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
