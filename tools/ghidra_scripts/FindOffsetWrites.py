# -*- coding: utf-8 -*-
# FindOffsetWrites.py
# Generic version of FindWrapperSubstateWriters.
# Scan all instructions for `MOV [reg + OFFSET], imm` where imm matches a
# target small int. Group results by enclosing function.
#
# args[0] = offset (hex, e.g. 0xfd or 0xa0)
# args[1] = value (hex or int, e.g. 1, 2, 0)
# args[2] = output path (optional)
#
# @category Analysis.New_World
# @runtime Jython

import sys
from ghidra.program.model.scalar import Scalar  # type: ignore

args = list(getScriptArgs())  # noqa: F821
if len(args) < 2:
    print("FindOffsetWrites: need <offset> <value> [out_path]")
    sys.exit(1)

OFFSET = int(args[0], 0)
TARGET_VALUE = int(args[1], 0)
out_path = args[2] if len(args) > 2 else None

prog = currentProgram  # noqa: F821
listing = prog.getListing()
fm = prog.getFunctionManager()

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# offset-write scan: MOV [reg + 0x%x], 0x%x" % (OFFSET, TARGET_VALUE))
emit("")

inst_iter = listing.getInstructions(True)
scanned = 0
matches = []

for inst in inst_iter:
    scanned += 1
    if inst.getMnemonicString() != "MOV":
        continue
    if inst.getNumOperands() != 2:
        continue

    op0_objs = inst.getOpObjects(0)
    has_target_disp = False
    for o in op0_objs:
        if isinstance(o, Scalar):
            try:
                if o.getValue() == OFFSET:
                    has_target_disp = True
                    break
            except Exception:
                pass
    if not has_target_disp:
        continue

    op1_objs = inst.getOpObjects(1)
    imm_val = None
    for o in op1_objs:
        if isinstance(o, Scalar):
            try:
                imm_val = o.getValue()
            except Exception:
                pass
    if imm_val != TARGET_VALUE:
        continue

    func = fm.getFunctionContaining(inst.getAddress())
    fname = func.getName() if func else "?"
    fentry = func.getEntryPoint().toString() if func else "?"
    matches.append((inst.getAddress().toString(), fname, fentry, inst.toString()))

emit("scanned %d instructions, %d hits" % (scanned, len(matches)))
emit("")

# Group by enclosing function for easier review
by_func = {}
for ia, fn, fe, txt in matches:
    by_func.setdefault((fe, fn), []).append((ia, txt))

emit("## hits grouped by enclosing function (%d unique)" % len(by_func))
emit("")
for (fe, fn), hits in sorted(by_func.items()):
    emit("### %s @ %s  (%d hit%s)" % (fn, fe, len(hits), "" if len(hits) == 1 else "s"))
    for ia, txt in hits:
        emit("  %s  %s" % (ia, txt))
    emit("")

emit("# end")

if out_path:
    try:
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print("FindOffsetWrites: wrote %s" % out_path)
    except Exception as e:
        print("FindOffsetWrites: write failed: %s" % e)
        sys.exit(1)
