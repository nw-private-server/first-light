# -*- coding: utf-8 -*-
# DumpInstructionsWindow.py
# Walk backward from a given address looking for a function prologue,
# then forward-disassemble until a return / unreachable. Useful for
# call sites where Ghidra's auto-analysis didn't create a function.
#
# args[0] = address of interest (hex)
# args[1] = optional output path
#
# @category Analysis.New_World
# @runtime Jython

import sys

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("DumpInstructionsWindow: missing address arg")
    sys.exit(1)

addr_str = args[0]
out_path = args[1] if len(args) > 1 else None

prog = currentProgram  # noqa: F821
listing = prog.getListing()
af = prog.getAddressFactory()

target = af.getAddress(addr_str)
if target is None:
    print("DumpInstructionsWindow: bad address")
    sys.exit(1)

lines = []


def emit(s):
    lines.append(s)
    print(s)


# Strategy: walk backward instruction-by-instruction up to 0x200 bytes,
# looking for the start of a function. If Ghidra has a defined instruction
# at the address, we walk via getInstructionBefore. If the chain breaks
# (no defined instruction), we stop and print what we have.

# First, find the nearest defined instruction at or before target.
inst = listing.getInstructionContaining(target)
if inst is None:
    inst = listing.getInstructionBefore(target)
if inst is None:
    emit("no defined instruction near %s" % addr_str)
    sys.exit(1)

emit("# starting from %s" % inst.getAddress())

# Walk backward, collecting up to 200 instructions
backward = []
cur = inst
for _ in range(200):
    prev = listing.getInstructionBefore(cur.getAddress())
    if prev is None:
        break
    # If prev's flow doesn't fall-through to cur, we've crossed a function boundary
    flow = prev.getFlowType()
    if flow.isTerminal() or flow.isJump() and not flow.isConditional():
        break
    backward.append(prev)
    cur = prev

# Reverse so we read top-to-bottom
backward.reverse()
context = backward + [inst]

# Walk forward from inst up to 200 instructions (or until terminator)
cur = inst
for _ in range(200):
    nxt = listing.getInstructionAfter(cur.getAddress())
    if nxt is None:
        break
    flow = cur.getFlowType()
    if flow.isTerminal():
        break
    context.append(nxt)
    cur = nxt

# Print
emit("# %d instructions in window" % len(context))
emit("")
for inst in context:
    addr = inst.getAddress()
    marker = "  <-- TARGET" if addr.getOffset() == target.getOffset() else ""
    emit("%s  %s%s" % (addr, inst.toString(), marker))

emit("")
emit("# end")

if out_path:
    try:
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print("DumpInstructionsWindow: wrote %s" % out_path)
    except Exception as e:
        print("DumpInstructionsWindow: write failed: %s" % e)
        sys.exit(1)
