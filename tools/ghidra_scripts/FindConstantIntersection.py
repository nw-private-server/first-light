# -*- coding: utf-8 -*-
# FindConstantIntersection.py - find functions that reference EVERY one of
# a given list of 32-bit constants. Useful for locating switch-statement
# dispatchers that match against multiple type-IDs (where each type-ID
# appears as a CMP immediate within the dispatcher).
#
# args[0] = comma-separated hex constants (e.g. "0x40a,0x1be,0x65c")
# args[1] = optional output path
# args[2] = optional per-constant hit cap (default 1000)
#
# @category Analysis.New_World
# @runtime Jython

import sys
import jarray  # noqa: F821

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("FindConstantIntersection: need <c1,c2,c3,...> [out_path] [hit_cap]")
    sys.exit(1)

const_strs = args[0].split(",")
out_path = args[1] if len(args) > 1 else None
hit_cap = int(args[2]) if len(args) > 2 else 1000

const_vals = [int(s, 0) & 0xffffffff for s in const_strs]

prog = currentProgram  # noqa: F821
mem = prog.getMemory()
fm = prog.getFunctionManager()

lines = []


def emit(s):
    lines.append(s)
    print(s)


def le_bytes(value):
    out = []
    v = value
    for _ in range(4):
        out.append(v & 0xff)
        v >>= 8
    return out


def find_all(value):
    """Return a set of function entry-points that contain the constant."""
    pattern = le_bytes(value)
    jb = jarray.array(
        [b if b < 128 else b - 256 for b in pattern],
        "b",
    )
    funcs = set()
    raw_hits = []
    all_set = mem.getAllInitializedAddressSet()
    start = all_set.getMinAddress()
    n = 0
    while start is not None and n < hit_cap:
        found = mem.findBytes(start, jb, None, True, None)
        if found is None:
            break
        n += 1
        func = fm.getFunctionContaining(found)
        if func is not None:
            funcs.add(func.getEntryPoint())
        raw_hits.append((found, func.getName() if func else None))
        start = found.add(1)
    return funcs, raw_hits, n


emit("# searching for intersection of: %s" % ", ".join(
    "0x%x" % v for v in const_vals
))
emit("# (per-constant hit cap: %d)" % hit_cap)
emit("")

per_const_funcs = []
for v in const_vals:
    funcs, _, n = find_all(v)
    emit("# 0x%x: %d total hits, %d unique enclosing funcs" % (v, n, len(funcs)))
    per_const_funcs.append(funcs)

# Intersection of all sets
intersection = per_const_funcs[0]
for s in per_const_funcs[1:]:
    intersection = intersection & s

emit("")
emit("## intersection: %d functions reference ALL %d constants" % (
    len(intersection), len(const_vals)
))

for fn_addr in sorted(intersection, key=lambda a: a.getOffset()):
    fn = fm.getFunctionAt(fn_addr)
    fn_name = fn.getName() if fn else "(no name)"
    emit("  %s  %s" % (fn_addr, fn_name))

emit("")
emit("# end")

text = "\n".join(lines)

if out_path:
    with open(out_path, "w") as f:
        f.write(text)
    print("FindConstantIntersection: wrote %s" % out_path)
