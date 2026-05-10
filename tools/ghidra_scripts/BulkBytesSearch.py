# -*- coding: utf-8 -*-
# BulkBytesSearch.py - search for many byte patterns in a single
# Ghidra session (avoids the per-script-startup overhead).
#
# args[0] = input TSV with `label\tpattern_hex` per line
# args[1] = output path
#
# @category Analysis.New_World
# @runtime Jython

import sys
import jarray  # noqa: F821

args = list(getScriptArgs())  # noqa: F821
if len(args) < 2:
    print("BulkBytesSearch: need <tsv-path> <out-path>")
    sys.exit(1)

tsv_path = args[0]
out_path = args[1]

prog = currentProgram  # noqa: F821
mem = prog.getMemory()
fm = prog.getFunctionManager()


def signed(b):
    return b - 256 if b > 127 else b


def find_first_match(needle_hex):
    pattern = [signed(int(needle_hex[i:i + 2], 16))
               for i in range(0, len(needle_hex), 2)]
    jb = jarray.array(pattern, "b")
    all_set = mem.getAllInitializedAddressSet()
    return mem.findBytes(all_set.getMinAddress(), jb, None, True, None)


def find_all_matches(needle_hex, max_hits=10):
    pattern = [signed(int(needle_hex[i:i + 2], 16))
               for i in range(0, len(needle_hex), 2)]
    jb = jarray.array(pattern, "b")
    all_set = mem.getAllInitializedAddressSet()
    cur = all_set.getMinAddress()
    end = all_set.getMaxAddress()
    out = []
    while cur is not None and len(out) < max_hits:
        match = mem.findBytes(cur, jb, None, True, None)
        if match is None:
            break
        out.append(match)
        cur = match.add(1)
        if cur.compareTo(end) > 0:
            break
    return out


lines_out = []


def emit(s):
    lines_out.append(s)
    print(s)


emit("# bulk-bytes-search\n")

with open(tsv_path) as f:
    pairs = []
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            pairs.append((parts[0], parts[1]))

emit("# %d patterns to search\n" % len(pairs))

hits_total = 0
hits_with_results = 0
for label, pattern in pairs:
    matches = find_all_matches(pattern, max_hits=5)
    if matches:
        hits_with_results += 1
        hits_total += len(matches)
        emit("HIT %s pattern=%s found=%d" % (label, pattern, len(matches)))
        for m in matches:
            block = mem.getBlock(m)
            block_name = block.getName() if block else "?"
            fn = fm.getFunctionContaining(m)
            fn_name = fn.getName() if fn else "(no fn)"
            emit("    %s  block=%s  fn=%s" % (m, block_name, fn_name))
    # else: silent for no-hit patterns

emit("")
emit("# %d patterns matched (out of %d), %d total hits" % (
    hits_with_results, len(pairs), hits_total
))
emit("# end")

with open(out_path, "w") as f:
    f.write("\n".join(lines_out))
print("BulkBytesSearch: wrote %s" % out_path)
