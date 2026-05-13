# -*- coding: utf-8 -*-
# @runtime Jython
# FindByteLiteralXrefs.py - find every code/data location whose 4 bytes
# at offset N match the given hex pattern. Useful for tracking 4-byte
# RVA references where Ghidra's pointer xref tracker doesn't catch them
# (e.g., packed RVA tables with 4-byte function-pointer halves).
#
# args[0] = 4-byte hex pattern, MSB-first ASCII (e.g. "06454bec" for the
#           function at RVA 0x6454bec; the script handles little-endian
#           byte ordering internally)
# args[1] = optional output path

import sys
import jarray  # noqa: F821

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("FindByteLiteralXrefs: need <hex8> [out_path]")
    sys.exit(1)

needle_hex = args[0]
out_path = args[1] if len(args) > 1 else None

if len(needle_hex) != 8:
    print("expected 8 hex chars (4 bytes)")
    sys.exit(1)

# Reverse byte order (MSB-first input -> LE bytes for x64 immediate form).
le_bytes = []
for i in range(0, 8, 2):
    le_bytes.append(int(needle_hex[6 - i:8 - i], 16))

prog = currentProgram  # noqa: F821
listing = prog.getListing()
fm = prog.getFunctionManager()
memory = prog.getMemory()

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# byte-literal scan for %s (LE bytes: %s)" %
     (needle_hex, " ".join("%02x" % b for b in le_bytes)))
emit("")

# Build Java byte array (signed)
jb = jarray.array([(b - 256) if b > 127 else b for b in le_bytes], "b")
mask = jarray.array([-1 for _ in le_bytes], "b")

addr_set = memory.getLoadedAndInitializedAddressSet()
addr_iter = addr_set.getAddressRanges()

found = []
for r in addr_iter:
    start = r.getMinAddress()
    end = r.getMaxAddress()
    cur = start
    while cur is not None and cur.compareTo(end) <= 0:
        nxt = memory.findBytes(cur, end, jb, mask, True, monitor)  # noqa: F821
        if nxt is None:
            break
        found.append(nxt)
        cur = nxt.add(1)
        if monitor.isCancelled():  # noqa: F821
            break

emit("found %d hits" % len(found))
emit("")

# For each hit, classify: code (in a function?), data, etc.
for addr in found:
    func = fm.getFunctionContaining(addr)
    inst = listing.getInstructionContaining(addr)
    if func is not None:
        suffix = " (in func %s @ %s)" % (func.getName(), func.getEntryPoint())
        if inst is not None:
            suffix += " inst=%s" % inst.toString()
    else:
        # Likely data or padding
        suffix = " (no enclosing function)"
    emit("  %s%s" % (addr, suffix))

emit("")
emit("# end")

if out_path:
    try:
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print("FindByteLiteralXrefs: wrote %s" % out_path)
    except Exception as e:
        print("FindByteLiteralXrefs: write failed: %s" % e)
        sys.exit(1)
