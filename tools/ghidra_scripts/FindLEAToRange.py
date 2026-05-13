# -*- coding: utf-8 -*-
# FindLEAToRange.py - find every LEA / MOV instruction whose computed
# memory operand falls within a given address range. Useful when
# Ghidra's xref database missed RIP-relative loads of a runtime-
# accessed table base.
#
# args[0] = range start (hex)
# args[1] = range end (hex, inclusive)
# args[2] = optional output path
#
# @category Analysis.New_World
# @runtime Jython

import sys

args = list(getScriptArgs())  # noqa: F821
if len(args) < 2:
    print("FindLEAToRange: need <start-hex> <end-hex> [out_path]")
    sys.exit(1)

range_start = int(args[0], 16)
range_end = int(args[1], 16)
out_path = args[2] if len(args) > 2 else None

prog = currentProgram  # noqa: F821
listing = prog.getListing()
fm = prog.getFunctionManager()

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# scanning for LEA/MOV instructions targeting [0x%x, 0x%x]" %
     (range_start, range_end))
emit("")

instrs = listing.getInstructions(True)
hits_by_func = {}
total = 0

while instrs.hasNext():
    ins = instrs.next()
    mnemonic = ins.getMnemonicString()
    # Look at LEA, MOV, CMP — main address-loading and table-lookup ops
    if mnemonic not in ("LEA", "MOV", "MOVSXD", "CMP", "MOVZX"):
        continue
    # Walk operand references for any that target our range
    refs = ins.getReferencesFrom()
    target_in_range = False
    target_addr = None
    for ref in refs:
        addr = ref.getToAddress()
        if addr is None:
            continue
        offs = addr.getOffset()
        if range_start <= offs <= range_end:
            target_in_range = True
            target_addr = offs
            break
    if not target_in_range:
        continue
    total += 1
    func = fm.getFunctionContaining(ins.getAddress())
    fname = func.getName() if func else "?"
    fentry = func.getEntryPoint() if func else None
    key = (fname, str(fentry))
    if key not in hits_by_func:
        hits_by_func[key] = []
    hits_by_func[key].append((ins.getAddress(), mnemonic, target_addr,
                              ins.toString()))

emit("# %d hits across %d unique functions" % (total, len(hits_by_func)))
emit("")

for (fname, fentry), hits in sorted(hits_by_func.items(),
                                     key=lambda kv: kv[0][1] or ""):
    emit("## %s @ %s (%d hits)" % (fname, fentry, len(hits)))
    for addr, mnem, target, insn in hits[:20]:
        emit("  %s  %s  -> 0x%x   %s" % (addr, mnem, target, insn))
    if len(hits) > 20:
        emit("  ... (%d more)" % (len(hits) - 20))
    emit("")

emit("# end")

text = "\n".join(lines)

if out_path:
    with open(out_path, "w") as f:
        f.write(text)
    print("FindLEAToRange: wrote %s" % out_path)
