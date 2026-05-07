# -*- coding: utf-8 -*-
# FindWrapperSubstateWriters.py
# Locate code that writes the GameConnectionWrapper substate at +0xa0.
#
# Two strategies:
#  1. Instruction pattern scan: any MOV [reg + 0xa0], imm where imm is a
#     small int (we list 0/1/2/3/4 separately).
#  2. Xref scan of FUN_1402a1750 (returns &substate) - callers may write
#     through the returned pointer.
#
# Output written to the path passed as args[0]. If absent, prints to console.
#
# @category Analysis.New_World
# @runtime Jython

import sys
from ghidra.program.model.scalar import Scalar  # type: ignore
from ghidra.program.model.symbol import RefType  # type: ignore

OFFSET = 0xa0
INTERESTING_VALUES = {0, 1, 2, 3, 4, 5}
ACCESSOR_ADDR_HEX = "0x1402a1750"

args = list(getScriptArgs())  # noqa: F821
out_path = args[0] if args else None

prog = currentProgram  # noqa: F821
listing = prog.getListing()
fm = prog.getFunctionManager()
ref_mgr = prog.getReferenceManager()

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# wrapper-substate writer hunt")
emit("# pattern: MOV [reg + 0x%x], <imm in %s>" % (OFFSET, sorted(INTERESTING_VALUES)))
emit("")

# ---- Strategy 1: instruction pattern scan ---------------------------------

emit("## Pattern matches (MOV [reg + 0x%x], imm)" % OFFSET)
emit("")

inst_iter = listing.getInstructions(True)
scanned = 0
matches_by_value = {v: [] for v in INTERESTING_VALUES}
other_matches = []

for inst in inst_iter:
    scanned += 1
    if inst.getMnemonicString() != "MOV":
        continue
    if inst.getNumOperands() != 2:
        continue

    # Operand 0 must be a memory access with displacement OFFSET.
    op0_objs = inst.getOpObjects(0)
    has_target_disp = False
    for o in op0_objs:
        if isinstance(o, Scalar):
            try:
                v = o.getValue()
                if v == OFFSET:
                    has_target_disp = True
                    break
            except Exception:
                pass
    if not has_target_disp:
        continue

    # Operand 1 must be an immediate scalar.
    op1_objs = inst.getOpObjects(1)
    imm_val = None
    for o in op1_objs:
        if isinstance(o, Scalar):
            try:
                imm_val = o.getValue()
            except Exception:
                pass
    if imm_val is None:
        continue

    func = fm.getFunctionContaining(inst.getAddress())
    fname = func.getName() if func else "?"
    rec = "  %s  %s  %s" % (inst.getAddress().toString(), fname, inst.toString())
    if imm_val in INTERESTING_VALUES:
        matches_by_value[imm_val].append(rec)
    else:
        other_matches.append((imm_val, rec))

emit("scanned %d instructions" % scanned)
emit("")
for v in sorted(INTERESTING_VALUES):
    recs = matches_by_value[v]
    emit("### imm = %d (%d hits)" % (v, len(recs)))
    if recs:
        for r in recs:
            emit(r)
    else:
        emit("  (none)")
    emit("")

emit("### imm = other small const (%d hits, capped at 30)" % len(other_matches))
for imm_val, r in other_matches[:30]:
    emit("  imm=%d %s" % (imm_val, r.lstrip()))
emit("")

# ---- Strategy 2: xrefs of the &substate accessor -------------------------

emit("## Callers of FUN_1402a1750 (returns &wrapper.substate)")
emit("")

addr = prog.getAddressFactory().getAddress(ACCESSOR_ADDR_HEX)
func = fm.getFunctionAt(addr)
if func is None:
    emit("  ERROR: no function at %s" % ACCESSOR_ADDR_HEX)
else:
    callers = set()
    for ref in ref_mgr.getReferencesTo(addr):
        if not ref.getReferenceType().isCall():
            continue
        from_addr = ref.getFromAddress()
        cf = fm.getFunctionContaining(from_addr)
        cf_name = cf.getName() if cf else "?"
        cf_entry = cf.getEntryPoint().toString() if cf else "?"
        callers.add((cf_entry, cf_name, from_addr.toString()))
    emit("found %d call sites" % len(callers))
    for cf_entry, cf_name, from_addr in sorted(callers):
        emit("  call from %s in %s @ %s" % (from_addr, cf_name, cf_entry))
emit("")

emit("# end")

if out_path:
    try:
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print("FindWrapperSubstateWriters: wrote %s" % out_path)
    except Exception as e:
        print("FindWrapperSubstateWriters: write failed: %s" % e)
        sys.exit(1)
