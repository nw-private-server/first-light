# -*- coding: utf-8 -*-
# FindOffsetReferences.py
# Broader scan than FindOffsetWrites: catches ANY instruction whose
# operand has memory access at the target displacement, regardless of
# operation (MOV, MOVZX, CMP, AND, etc.). Useful when the writer is
# register-based or the field is read more than written.
#
# args[0] = displacement (hex, e.g. 0x252)
# args[1] = optional output path
# args[2] = optional address-range filter prefix (e.g. "145a" to limit
#           hits to the wrapper class neighborhood at 0x145axxxxx)
#
# @category Analysis.New_World
# @runtime Jython

import sys
from ghidra.program.model.scalar import Scalar  # type: ignore

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("FindOffsetReferences: need <offset> [out_path] [addr_prefix]")
    sys.exit(1)

OFFSET = int(args[0], 0)
out_path = args[1] if len(args) > 1 else None
addr_prefix = args[2] if len(args) > 2 else None

prog = currentProgram  # noqa: F821
listing = prog.getListing()
fm = prog.getFunctionManager()

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# offset-reference scan: any instruction with operand displacement 0x%x" % OFFSET)
if addr_prefix:
    emit("# filtered to function entries starting with: %s" % addr_prefix)
emit("")

inst_iter = listing.getInstructions(True)
scanned = 0
matches = []

for inst in inst_iter:
    scanned += 1
    n_ops = inst.getNumOperands()
    if n_ops == 0:
        continue

    has_target_disp = False
    for op_idx in range(n_ops):
        op_objs = inst.getOpObjects(op_idx)
        for o in op_objs:
            if isinstance(o, Scalar):
                try:
                    if o.getValue() == OFFSET:
                        has_target_disp = True
                        break
                except Exception:
                    pass
        if has_target_disp:
            break

    if not has_target_disp:
        continue

    func = fm.getFunctionContaining(inst.getAddress())
    fname = func.getName() if func else "?"
    fentry = func.getEntryPoint().toString() if func else "?"

    if addr_prefix and not fentry.startswith(addr_prefix):
        continue

    matches.append((inst.getAddress().toString(), fname, fentry, inst.toString()))

emit("scanned %d instructions, %d hits" % (scanned, len(matches)))
emit("")

# Group by enclosing function
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
        print("FindOffsetReferences: wrote %s" % out_path)
    except Exception as e:
        print("FindOffsetReferences: write failed: %s" % e)
        sys.exit(1)
