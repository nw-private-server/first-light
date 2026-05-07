# -*- coding: utf-8 -*-
# FindStringXrefs.py
# Locate every occurrence of a literal ASCII string in the binary, then
# dump xrefs to each occurrence. Useful for finding where a message name
# is registered as a handler key.
#
# args[0] = literal string to search for
# args[1] = optional output path
#
# @category Analysis.New_World
# @runtime Jython

import sys

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("FindStringXrefs: missing string arg")
    sys.exit(1)

needle = args[0]
out_path = args[1] if len(args) > 1 else None

prog = currentProgram  # noqa: F821
listing = prog.getListing()
memory = prog.getMemory()
fm = prog.getFunctionManager()
ref_mgr = prog.getReferenceManager()

# Encode as ASCII bytes with terminating null (typical C-string layout)
ascii_bytes = []
for ch in needle:
    ascii_bytes.append(ord(ch))
ascii_bytes.append(0)
needle_bytes = bytearray(ascii_bytes)
# Convert to a Java byte array via bytes-string for findBytes
pattern = "".join("%02x" % b for b in needle_bytes)

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# string xref hunt: %r" % needle)
emit("")

# Iterate defined strings first (faster than full scan when string is defined)
hits = []
data_iter = listing.getDefinedData(True)
for data in data_iter:
    dt_name = data.getDataType().getName()
    if "string" not in dt_name.lower() and "char" not in dt_name.lower():
        continue
    val = data.getValue()
    if val is None:
        continue
    try:
        s = unicode(val).encode("ascii", "replace")
    except Exception:
        try:
            s = repr(val)
        except Exception:
            continue
    if needle in s:
        hits.append((data.getAddress(), s))

emit("found %d defined-string hits" % len(hits))
emit("")

for str_addr, val in hits:
    emit("## string at %s: %r" % (str_addr, val[:120]))
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
        print("FindStringXrefs: wrote %s" % out_path)
    except Exception as e:
        print("FindStringXrefs: write failed: %s" % e)
        sys.exit(1)
