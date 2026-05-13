# -*- coding: utf-8 -*-
# FindBytesAnywhere.py - find every offset in the loaded binary whose
# bytes match a given hex pattern. Searches all loaded memory blocks
# (code AND data), not just instruction-immediate operands.
#
# args[0] = hex pattern (any length, e.g. "58617814")
# args[1] = optional output path
#
# @category Analysis.New_World
# @runtime Jython

import sys
import jarray  # noqa: F821

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("FindBytesAnywhere: need <hex> [out_path]")
    sys.exit(1)

needle_hex = args[0]
out_path = args[1] if len(args) > 1 else None

if len(needle_hex) % 2 != 0:
    print("expected even number of hex chars")
    sys.exit(1)

def _signed(b):
    return b - 256 if b > 127 else b

needle = jarray.array(
    [_signed(int(needle_hex[i:i + 2], 16)) for i in range(0, len(needle_hex), 2)],
    "b",
)

prog = currentProgram  # noqa: F821
memory = prog.getMemory()
listing = prog.getListing()

lines = []
lines.append("# byte scan for %s (%d bytes) across all loaded blocks" %
             (needle_hex, len(needle_hex) // 2))

hits = []
for block in memory.getBlocks():
    if not block.isInitialized():
        continue
    start = block.getStart()
    end = block.getEnd()
    cur = memory.findBytes(start, end, needle, None, True, None)
    while cur is not None and len(hits) < 100:
        hits.append((cur, block.getName()))
        # advance past this hit
        next_addr = cur.add(1)
        if next_addr.compareTo(end) > 0:
            break
        cur = memory.findBytes(next_addr, end, needle, None, True, None)

lines.append("found %d hits" % len(hits))
lines.append("")

fm = prog.getFunctionManager()
for addr, blk in hits:
    fn = fm.getFunctionContaining(addr)
    fn_name = fn.getName() if fn else "(no function)"
    sym = prog.getSymbolTable().getPrimarySymbol(addr)
    sym_name = sym.getName() if sym else "(no sym)"
    lines.append("  %s  block=%s  fn=%s  sym=%s" % (
        addr, blk, fn_name, sym_name,
    ))

lines.append("")
lines.append("# end")

text = "\n".join(lines)
print(text)

if out_path:
    with open(out_path, "w") as f:
        f.write(text)
    print("FindBytesAnywhere: wrote %s" % out_path)
