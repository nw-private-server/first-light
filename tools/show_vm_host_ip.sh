#!/bin/bash
# show_vm_host_ip.sh
#
# Prints the Mac's IP as seen from a UTM virtual machine using
# UTM's default Shared Network (NAT) mode. This is the IP that
# auth_mock should advertise via --rep-host and that setup_hosts.py
# inside the VM should redirect Amazon hostnames to.
#
# Usage:
#   tools/show_vm_host_ip.sh
#
# UTM's bridge interface is typically bridge100, with the host
# at 192.168.64.1 and the VM getting 192.168.64.x via DHCP.
# This script auto-detects in case UTM's interface naming changes.

set -euo pipefail

# Find any interface named bridgeNNN with an IP in the 192.168.0.0/16
# RFC1918 range (UTM uses 192.168.64.0/24 by default).
ip=$(ifconfig | awk '
    /^bridge[0-9]+:/ { iface=$1; next }
    /^[a-z]/ { iface="" }
    iface != "" && /inet 192\.168/ { print $2; exit }
')

if [ -z "$ip" ]; then
    echo "error: no UTM bridge interface with a 192.168.x.y address found" >&2
    echo "  - is a UTM VM running with Shared Network mode?" >&2
    echo "  - check 'ifconfig | grep bridge' manually" >&2
    exit 1
fi

echo "$ip"
