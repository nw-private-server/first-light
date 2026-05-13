# -*- coding: utf-8 -*-
# FindAlignedDataConstant.py - find every occurrence of a 32-bit constant
# in DATA sections at a specific byte alignment. Useful for locating
# entries in a packed table where the constant is the table key.
#
# args[0] = constant in hex (e.g. 0x40a)
# args[1] = alignment in decimal (e.g. 8 for 8-byte aligned table entries)
# args[2] = optional output path
#
# @category Analysis.New_World
# @runtime Jython

import sys
import jarray  # noqa: F821

args = list(getScriptArgs())  # noqa: F821
if len(args) < 2:
    print("FindAlignedDataConstant: need <const-hex> <alignment> [out_path]")
    sys.exit(1)

const_val = int(args[0], 0) & 0xffffffff
alignment = int(args[1])
out_path = args[2] if len(args) > 2 else None

prog = currentProgram  # noqa: F821
mem = prog.getMemory()
fm = prog.getFunctionManager()

# Build LE byte pattern
pattern = []
v = const_val
for _ in range(4):
    pattern.append(v & 0xff)
    v >>= 8
jb = jarray.array(
    [b if b < 128 else b - 256 for b in pattern],
    "b",
)

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# searching for 0x%x in DATA sections at %d-byte alignment" %
     (const_val, alignment))
emit("")

hits = []
for block in mem.getBlocks():
    if not block.isInitialized():
        continue
    name = block.getName()
    # Filter to data-shaped blocks. Common names: .data, .rdata
    if name not in (".data", ".rdata", ".pdata"):
        continue
    start = block.getStart()
    end = block.getEnd()
    cur = start
    while cur is not None:
        cur = mem.findBytes(cur, end, jb, None, True, None)
        if cur is None:
            break
        offset_in_binary = cur.getOffset()
        if offset_in_binary % alignment == 0:
            hits.append((cur, name))
        nxt = cur.add(1)
        if nxt.compareTo(end) > 0:
            break
        cur = nxt
        if len(hits) >= 200:
            break

emit("found %d aligned hits" % len(hits))
emit("")

for addr, blk in hits[:50]:
    # Show 32 bytes of context
    try:
        before = mem.getBytes(addr.subtract(0x10), 0x30)
        ctx = " ".join("%02x" % (b & 0xff) for b in before)
    except Exception:
        ctx = "(ctx fail)"
    fn = fm.getFunctionContaining(addr)
    emit("  %s  block=%s  ctx=%s" % (addr, blk, ctx))

if len(hits) > 50:
    emit("  ... (%d more)" % (len(hits) - 50))

emit("")
emit("# end")

text = "\n".join(lines)

if out_path:
    with open(out_path, "w") as f:
        f.write(text)
    print("FindAlignedDataConstant: wrote %s" % out_path)
