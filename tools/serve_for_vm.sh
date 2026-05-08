#!/bin/bash
# serve_for_vm.sh
#
# One-shot launcher for the auth-mock + rep-responder pair, configured
# for a UTM Windows VM client. Auto-detects the Mac's IP from the VM's
# perspective and threads it into auth_mock's --rep-host flag so the
# client connects back to the host instead of looping to localhost.
#
# Usage:
#   tools/serve_for_vm.sh               # foreground, both servers, ctrl-C exits
#   tools/serve_for_vm.sh --no-auth     # only run rep_responder
#   tools/serve_for_vm.sh --rep-port 24083 --auth-port 443
#
# Logs:
#   capture/auth_mock_logs/YYYYMMDD.log     (auth_mock's own log path)
#   capture/responder_<timestamp>.log       (rep_responder's log path)
#
# Requires:
#   - .venv set up (see docs/protocol-overview.md § Local verification)
#   - sudo access for auth_mock (binds port 443)
#   - UTM running with default Shared Network (auto-detected via
#     tools/show_vm_host_ip.sh)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# --- args -----------------------------------------------------------

AUTH_PORT=443
REP_PORT=24083
RUN_AUTH=1
RUN_REP=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-auth)   RUN_AUTH=0; shift;;
        --no-rep)    RUN_REP=0;  shift;;
        --auth-port) AUTH_PORT="$2"; shift 2;;
        --rep-port)  REP_PORT="$2";  shift 2;;
        -h|--help)
            grep -E "^# (Usage|  )" "$0" | sed 's/^# //'
            exit 0
            ;;
        *) echo "unknown arg: $1" >&2; exit 1;;
    esac
done

# --- detect VM-side IP ----------------------------------------------

if ! VM_HOST_IP="$(tools/show_vm_host_ip.sh 2>/dev/null)"; then
    echo "warning: tools/show_vm_host_ip.sh failed; falling back to 192.168.64.1" >&2
    VM_HOST_IP="192.168.64.1"
fi

# --- venv check -----------------------------------------------------

if [[ ! -x ".venv/bin/python" ]]; then
    echo "error: .venv not found. Set up first:" >&2
    echo "  python3.12 -m venv .venv" >&2
    echo "  .venv/bin/pip install -q pyOpenSSL pytest pytest-timeout" >&2
    exit 1
fi

# --- launch ---------------------------------------------------------

pids=()

cleanup() {
    echo
    echo "[serve_for_vm] shutting down..."
    for pid in "${pids[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo "[serve_for_vm] all servers stopped"
}
trap cleanup INT TERM EXIT

if [[ $RUN_AUTH -eq 1 ]]; then
    echo "[serve_for_vm] starting auth_mock on :${AUTH_PORT} with --rep-host ${VM_HOST_IP}"
    sudo -E .venv/bin/python -m server.auth_mock \
        --port "${AUTH_PORT}" \
        --rep-host "${VM_HOST_IP}" \
        --rep-port "${REP_PORT}" &
    pids+=($!)
fi

if [[ $RUN_REP -eq 1 ]]; then
    echo "[serve_for_vm] starting rep_responder on :${REP_PORT}"
    .venv/bin/python -m server.rep_responder \
        --bind-host 0.0.0.0 \
        --bind-port "${REP_PORT}" &
    pids+=($!)
fi

if [[ ${#pids[@]} -eq 0 ]]; then
    echo "[serve_for_vm] nothing to run (--no-auth and --no-rep both set?)"
    exit 1
fi

echo
echo "[serve_for_vm] running. host IP for VM: ${VM_HOST_IP}"
echo "[serve_for_vm] press Ctrl-C to stop"
echo "[serve_for_vm] PIDs: ${pids[*]}"
echo
wait
