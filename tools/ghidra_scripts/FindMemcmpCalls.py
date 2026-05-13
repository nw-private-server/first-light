# -*- coding: utf-8 -*-
# FindMemcmpCalls.py - find call sites where a small fixed-size memcmp
# is performed. Heuristic: locate `MOV R8D, <size>` (the 3rd MS-x64 arg
# = byte count) shortly before a CALL, where <size> matches the supplied
# value. Useful for finding fixed-size byte comparisons (e.g. trailer
# verifiers).
#
# args[0] = byte count to look for (decimal or hex)
# args[1] = optional output path
# args[2] = optional max distance from MOV to CALL in bytes (default 24)
#
# @category Analysis.New_World
# @runtime Jython

import sys

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("FindMemcmpCalls: need <byte-count> [out_path] [max_gap]")
    sys.exit(1)

target_size = int(args[0], 0)
out_path = args[1] if len(args) > 1 else None
max_gap = int(args[2]) if len(args) > 2 else 24

prog = currentProgram  # noqa: F821
listing = prog.getListing()
fm = prog.getFunctionManager()
mem = prog.getMemory()

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# scanning for `MOV R8/R8D, %d` followed within %d bytes by a CALL"
     % (target_size, max_gap))
emit("")

instrs = listing.getInstructions(True)
hits = 0

while instrs.hasNext():
    ins = instrs.next()
    mnemonic = ins.getMnemonicString()
    if mnemonic != "MOV":
        continue
    # Must be MOV to R8 or R8D from immediate
    op0 = ins.getDefaultOperandRepresentation(0)
    if op0 not in ("R8", "R8D", "r8", "r8d"):
        continue
    # 2nd operand: immediate value
    try:
        scalar = ins.getScalar(1)
    except Exception:
        continue
    if scalar is None:
        continue
    if scalar.getUnsignedValue() != target_size:
        continue
    # We have a MOV R8/R8D, <target>. Now look forward up to max_gap bytes
    # for a CALL.
    cur_addr = ins.getAddress()
    next_ins = ins.getNext()
    walked = 0
    found_call = None
    while next_ins is not None and walked < max_gap:
        if next_ins.getMnemonicString() == "CALL":
            found_call = next_ins
            break
        walked += next_ins.getLength()
        next_ins = next_ins.getNext()
    if found_call is None:
        continue
    hits += 1
    func = fm.getFunctionContaining(cur_addr)
    fname = func.getName() if func else "?"
    target = found_call.getDefaultOperandRepresentation(0)
    emit("## hit %d: MOV at %s in %s -> CALL %s at %s" % (
        hits, cur_addr, fname, target, found_call.getAddress(),
    ))

emit("")
emit("# total hits: %d" % hits)
emit("# end")

text = "\n".join(lines)

if out_path:
    with open(out_path, "w") as f:
        f.write(text)
    print("FindMemcmpCalls: wrote %s" % out_path)
