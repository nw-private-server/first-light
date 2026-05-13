<#
.SYNOPSIS
    Set up a Windows portproxy so the game's HTTPS traffic to 127.0.0.1:443
    is forwarded to the Mac host's auth_mock listening on a non-privileged
    port (4443 by default).

.DESCRIPTION
    The Phase G design when auth_mock runs unprivileged on the Mac:
      - tools/setup_hosts.py redirects all auth hostnames to 127.0.0.1.
      - This script forwards 127.0.0.1:443 (in the VM) to MAC_IP:4443.
      - rep_responder still talks UDP/24083 directly (no proxy needed).

    Run once as Administrator inside the VM. Idempotent: removes any
    existing proxy on the same listen port before adding the new one.

.PARAMETER MacIp
    The Mac's IP as reachable from the VM. Defaults to 192.168.64.1
    (UTM Shared Network bridge default).

.PARAMETER AuthPort
    Mac-side auth_mock port. Defaults to 4443 (matches serve_for_vm.sh).

.PARAMETER ListenPort
    VM-side listen port. Defaults to 443 (the port the game expects).

.PARAMETER Revert
    Remove the proxy instead of adding it.

.EXAMPLE
    PS> .\setup_vm_portproxy.ps1
    Listening 127.0.0.1:443 -> 192.168.64.1:4443

.EXAMPLE
    PS> .\setup_vm_portproxy.ps1 -Revert
    Removes the proxy.
#>

param(
    [string]$MacIp = "192.168.64.1",
    [int]$AuthPort = 4443,
    [int]$ListenPort = 443,
    [switch]$Revert
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "This script must be run from an Administrator PowerShell."
    exit 1
}

# Always remove any existing proxy on the listen port first (idempotency)
Write-Host "Removing any existing proxy on 127.0.0.1:${ListenPort}..."
$existing = netsh interface portproxy show all | Select-String "127.0.0.1\s+${ListenPort}\s"
if ($existing) {
    netsh interface portproxy delete v4tov4 `
        listenport=$ListenPort listenaddress=127.0.0.1 | Out-Null
}

if ($Revert) {
    Write-Host "Reverted. Current proxies:"
    netsh interface portproxy show all
    exit 0
}

Write-Host "Adding proxy: 127.0.0.1:${ListenPort} -> ${MacIp}:${AuthPort}"
netsh interface portproxy add v4tov4 `
    listenport=$ListenPort `
    listenaddress=127.0.0.1 `
    connectport=$AuthPort `
    connectaddress=$MacIp

Write-Host
Write-Host "Current proxies:"
netsh interface portproxy show all

Write-Host
Write-Host "Verify: in another shell, run:"
Write-Host "  Test-NetConnection 127.0.0.1 -Port ${ListenPort}"
Write-Host "(Should show 'TcpTestSucceeded : True' once auth_mock is running on the Mac.)"
