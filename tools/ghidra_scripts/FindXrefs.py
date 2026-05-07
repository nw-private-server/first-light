# -*- coding: utf-8 -*-
# FindXrefs.py
# Given a function address (args[0]) and an output path (args[1] optional),
# dumps every reference to that address grouped by reference type and
# enclosing function.
#
# Useful for "who calls this" hunts during the wrapper-substate / connection
# lifecycle investigation.
#
# @category Analysis.New_World
# @runtime Jython

import sys

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("FindXrefs: missing address arg")
    sys.exit(1)

addr_str = args[0]
out_path = args[1] if len(args) > 1 else None

prog = currentProgram  # noqa: F821
fm = prog.getFunctionManager()
ref_mgr = prog.getReferenceManager()
addr = prog.getAddressFactory().getAddress(addr_str)
if addr is None:
    print("FindXrefs: could not parse address %s" % addr_str)
    sys.exit(1)

target_func = fm.getFunctionAt(addr)
target_name = target_func.getName() if target_func else "?"

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# xrefs to %s @ %s" % (target_name, addr_str))
emit("")

groups = {}  # reftype -> list of (from_addr, in_func_name, in_func_entry)
total = 0
for ref in ref_mgr.getReferencesTo(addr):
    rt = ref.getReferenceType().getName()
    from_addr = ref.getFromAddress()
    cf = fm.getFunctionContaining(from_addr)
    cf_name = cf.getName() if cf else "?"
    cf_entry = cf.getEntryPoint().toString() if cf else "?"
    groups.setdefault(rt, []).append((from_addr.toString(), cf_name, cf_entry))
    total += 1

emit("total references: %d" % total)
emit("")
for rt in sorted(groups.keys()):
    refs = groups[rt]
    emit("## %s (%d)" % (rt, len(refs)))
    seen_funcs = set()
    for from_addr, cf_name, cf_entry in sorted(refs):
        key = cf_entry
        if key in seen_funcs:
            continue
        seen_funcs.add(key)
        emit("  from %s in %s @ %s" % (from_addr, cf_name, cf_entry))
    emit("")

emit("# end")

if out_path:
    try:
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print("FindXrefs: wrote %s" % out_path)
    except Exception as e:
        print("FindXrefs: write failed: %s" % e)
        sys.exit(1)
