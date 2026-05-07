# -*- coding: utf-8 -*-
# UuidAtAddress.py
# Read 16 bytes at the given address, format as a Microsoft-style GUID
# (first 4 bytes LE, next 2 LE, next 2 LE, last 8 raw), then look up
# in /tmp/uuid_to_name.json (built from info/typeregistry.json).
#
# args[0..N] = one or more hex addresses to read
#
# Output goes to stdout. Useful for resolving dispatch-table metadata
# pointers to their AZ::TypeId class names.
#
# @category Analysis.New_World
# @runtime Jython

import sys
import json

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("UuidAtAddress: need <addr> [more addrs]")
    sys.exit(1)

# Load lookup table
try:
    with open("/tmp/uuid_to_name.json", "r") as f:
        uuid_to_name = json.load(f)
except Exception as e:
    print("UuidAtAddress: could not load /tmp/uuid_to_name.json: %s" % e)
    sys.exit(1)

print("loaded %d named UUIDs" % len(uuid_to_name))

prog = currentProgram  # noqa: F821
mem = prog.getMemory()
af = prog.getAddressFactory()


def read_bytes(addr_str):
    addr = af.getAddress(addr_str)
    if addr is None:
        return None
    out = []
    for i in range(16):
        try:
            b = mem.getByte(addr.add(i)) & 0xff
            out.append(b)
        except Exception as e:
            return None
    return out


def format_uuid(b):
    # MS GUID: first 4 bytes LE, next 2 LE, next 2 LE, last 8 raw
    p1 = "%02X%02X%02X%02X" % (b[3], b[2], b[1], b[0])
    p2 = "%02X%02X" % (b[5], b[4])
    p3 = "%02X%02X" % (b[7], b[6])
    p4 = "%02X%02X" % (b[8], b[9])
    p5 = "%02X%02X%02X%02X%02X%02X" % (b[10], b[11], b[12], b[13], b[14], b[15])
    return "%s-%s-%s-%s-%s" % (p1, p2, p3, p4, p5)


for arg in args:
    print("")
    print("== %s ==" % arg)
    b = read_bytes(arg)
    if b is None:
        print("  could not read")
        continue
    raw = " ".join("%02x" % x for x in b)
    print("  bytes: %s" % raw)
    uuid = format_uuid(b)
    print("  uuid:  %s" % uuid)
    name = uuid_to_name.get(uuid.upper())
    if name:
        print("  name:  %s" % name)
    else:
        print("  name:  <not in registry>")
