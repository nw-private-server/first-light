#!/bin/bash
# show_vm_host_ip.sh
#
# Prints the Mac's IP as seen from a Mac VM (UTM or Parallels) using
# the VM's default Shared Network / NAT mode. This is the IP that
# auth_mock should advertise via --rep-host and that setup_hosts.py
# inside the VM should redirect Amazon hostnames to.
#
# Usage:
#   tools/show_vm_host_ip.sh
#
# Tested with:
#   - UTM (Shared Network):     bridge100 with host at 192.168.64.1
#   - Parallels (Shared NAT):   bridge100 with host at 10.211.55.2
#
# Both backends use the same bridge interface name; only the IP
# range differs. We accept both 192.168.x.x and 10.x.x.x ranges.

set -euo pipefail

# Find any interface named bridgeNNN with an IP in either
#   192.168.0.0/16  (UTM default)
#   10.0.0.0/8      (Parallels default 10.211.55.x)
ip=$(ifconfig | awk '
    /^bridge[0-9]+:/ { iface=$1; next }
    /^[a-z]/ { iface="" }
    iface != "" && (/inet 192\.168/ || /inet 10\./) { print $2; exit }
')

if [ -z "$ip" ]; then
    echo "error: no UTM bridge interface with a 192.168.x.y address found" >&2
    echo "  - is a UTM VM running with Shared Network mode?" >&2
    echo "  - check 'ifconfig | grep bridge' manually" >&2
    exit 1
fi

echo "$ip"
