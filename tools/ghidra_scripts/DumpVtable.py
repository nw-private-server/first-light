# -*- coding: utf-8 -*-
# @runtime Jython
# DumpVtable.py - print N qwords starting at the given address
# args[0] = start address (hex)
# args[1] = count (decimal)
# args[2] = optional output path

import sys

args = list(getScriptArgs())  # noqa: F821
if len(args) < 2:
    print("usage: DumpVtable.py <addr-hex> <count-dec> [out-path]")
    sys.exit(1)

start = int(args[0], 16)
count = int(args[1])
out_path = args[2] if len(args) > 2 else None

prog = currentProgram  # noqa: F821
fm = prog.getFunctionManager()
memory = prog.getMemory()
factory = prog.getAddressFactory().getDefaultAddressSpace()

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# vtable dump at 0x%x (%d entries)" % (start, count))
emit("")

for i in range(count):
    addr = factory.getAddress(start + i * 8)
    try:
        b = []
        for j in range(8):
            b.append(memory.getByte(addr.add(j)) & 0xFF)
        v = 0
        for j in range(8):
            v |= b[j] << (j * 8)
        target_addr = factory.getAddress(v) if v < 0x10000000000 else None
        f = fm.getFunctionContaining(target_addr) if target_addr else None
        if f:
            emit("  [%2d] %s -> 0x%x  in %s @ %s" %
                 (i, addr, v, f.getName(), f.getEntryPoint()))
        else:
            emit("  [%2d] %s -> 0x%x" % (i, addr, v))
    except Exception as e:
        emit("  [%2d] %s -> READ_FAIL %s" % (i, addr, e))

emit("")
emit("# end")

if out_path:
    with open(out_path, "w") as fout:
        fout.write("\n".join(lines) + "\n")
    print("DumpVtable: wrote %s" % out_path)
