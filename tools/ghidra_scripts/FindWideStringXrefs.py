# -*- coding: utf-8 -*-
# FindWideStringXrefs.py
# Like FindStringXrefs but searches for UTF-16LE (wide) strings —
# the format MessageBoxW and other unicode Win32 APIs use.
#
# args[0] = literal string to search for
# args[1] = optional output path
#
# @category Analysis.New_World
# @runtime Jython

import sys

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("FindWideStringXrefs: missing string arg")
    sys.exit(1)

needle = args[0]
out_path = args[1] if len(args) > 1 else None

prog = currentProgram  # noqa: F821
listing = prog.getListing()
memory = prog.getMemory()
fm = prog.getFunctionManager()
ref_mgr = prog.getReferenceManager()

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# wide-string xref hunt: %r" % needle)
emit("")

# Build UTF-16LE byte pattern (no NUL terminator since we're substring matching)
le_bytes = []
for ch in needle:
    cp = ord(ch)
    le_bytes.append(cp & 0xFF)
    le_bytes.append((cp >> 8) & 0xFF)

# Convert to a hex pattern as a Java byte[] via signed bytes
import jarray  # noqa: F821
jb = jarray.array([(b - 256) if b > 127 else b for b in le_bytes], "b")
mask = jarray.array([-1 for _ in le_bytes], "b")  # full match

# Iterate program memory finding all matches
addr_set = prog.getMemory().getLoadedAndInitializedAddressSet()
addr_iter = addr_set.getAddressRanges()

found_addrs = []
for r in addr_iter:
    start = r.getMinAddress()
    end = r.getMaxAddress()
    cur = start
    while cur is not None and cur.compareTo(end) <= 0:
        nxt = memory.findBytes(cur, end, jb, mask, True, monitor)  # noqa: F821
        if nxt is None:
            break
        found_addrs.append(nxt)
        cur = nxt.add(2)
        if monitor.isCancelled():  # noqa: F821
            break

emit("found %d wide-string hits" % len(found_addrs))
emit("")

for str_addr in found_addrs:
    # Read the surrounding wide string content for confirmation (stop at NUL or 256 chars)
    chars = []
    for i in range(256):
        try:
            b0 = memory.getByte(str_addr.add(i * 2)) & 0xFF
            b1 = memory.getByte(str_addr.add(i * 2 + 1)) & 0xFF
            if b0 == 0 and b1 == 0:
                break
            cp = b0 | (b1 << 8)
            if cp < 0x80:
                chars.append(chr(cp))
            else:
                chars.append("?")
        except Exception:
            break
    val = "".join(chars)

    emit("## wide-string at %s: %r" % (str_addr, val[:120]))
    refs = list(ref_mgr.getReferencesTo(str_addr))
    emit("  %d references" % len(refs))
    seen = set()
    for ref in refs:
        rt = ref.getReferenceType().getName()
        from_addr = ref.getFromAddress()
        cf = fm.getFunctionContaining(from_addr)
        cf_name = cf.getName() if cf else "?"
        cf_entry = cf.getEntryPoint().toString() if cf else "?"
        key = (rt, cf_entry)
        if key in seen:
            continue
        seen.add(key)
        emit("    %s from %s in %s @ %s" % (rt, from_addr, cf_name, cf_entry))
    emit("")

emit("# end")

if out_path:
    try:
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print("FindWideStringXrefs: wrote %s" % out_path)
    except Exception as e:
        print("FindWideStringXrefs: write failed: %s" % e)
        sys.exit(1)
