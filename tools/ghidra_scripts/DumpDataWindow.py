# -*- coding: utf-8 -*-
# DumpDataWindow.py
# Print qword-aligned data and cross-references in a window around an
# address. Useful for inspecting dispatch-table-like structures where
# nearby entries should follow a fixed stride.
#
# args[0] = center address (hex)
# args[1] = window radius in bytes (default 0x80)
# args[2] = optional output path
#
# @category Analysis.New_World
# @runtime Jython

import sys

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("DumpDataWindow: missing address arg")
    sys.exit(1)

center_str = args[0]
radius = int(args[1], 0) if len(args) > 1 else 0x80
out_path = args[2] if len(args) > 2 else None

prog = currentProgram  # noqa: F821
mem = prog.getMemory()
fm = prog.getFunctionManager()
ref_mgr = prog.getReferenceManager()
sym_table = prog.getSymbolTable()

af = prog.getAddressFactory()
center = af.getAddress(center_str)
if center is None:
    print("DumpDataWindow: bad address %s" % center_str)
    sys.exit(1)

start = center.subtract(radius)
end = center.add(radius)

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# data window around %s (radius 0x%x)" % (center_str, radius))
emit("")
emit("addr               qword             interp")
emit("----               -----             ------")

addr = start
# round down to 8-byte alignment
off = addr.getOffset() & ~7
addr = af.getAddress("0x%x" % off)

end_off = end.getOffset()
while addr.getOffset() < end_off:
    try:
        qword = mem.getLong(addr) & 0xffffffffffffffff
    except Exception as e:
        emit("%s  <unreadable: %s>" % (addr, e))
        addr = addr.add(8)
        continue

    # Try to interpret the qword as an address into the program
    interp = ""
    try:
        target_addr = af.getAddress("0x%x" % qword)
        if mem.contains(target_addr):
            func = fm.getFunctionAt(target_addr)
            if func is not None:
                interp = "-> %s @ %s" % (func.getName(), target_addr)
            else:
                # Maybe it's a string?
                data = prog.getListing().getDataAt(target_addr)
                if data is not None and data.hasStringValue():
                    val = data.getValue()
                    try:
                        s = unicode(val).encode("ascii", "replace")
                        interp = "-> string %r" % s[:60]
                    except Exception:
                        interp = "-> string?"
                else:
                    interp = "-> in-image"
    except Exception:
        pass

    # Mark the center
    is_center = (addr.getOffset() <= center.getOffset() < addr.getOffset() + 8)
    marker = "  <-- CENTER" if is_center else ""

    # Refs to this address
    refs_to = list(ref_mgr.getReferencesTo(addr))
    ref_marker = " [%dxref]" % len(refs_to) if refs_to else ""

    emit("%s  %016x  %s%s%s" % (addr, qword, interp, ref_marker, marker))
    addr = addr.add(8)

emit("")
emit("# end")

if out_path:
    try:
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print("DumpDataWindow: wrote %s" % out_path)
    except Exception as e:
        print("DumpDataWindow: write failed: %s" % e)
        sys.exit(1)
