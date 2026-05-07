# -*- coding: utf-8 -*-
# FindConstant.py
# Search the binary for a 32-bit constant value (treating as little-endian
# bytes). For each hit, print its location, the enclosing function (if
# any), and ASCII strings within +/- 0x40 bytes — useful when looking for
# a CRC32 constant near its source string literal.
#
# args[0] = constant in hex (e.g. 0xFE476177)
# args[1] = optional output path
#
# @category Analysis.New_World
# @runtime Jython

import sys

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("FindConstant: missing constant arg")
    sys.exit(1)

const_val = int(args[0], 0) & 0xffffffff
out_path = args[1] if len(args) > 1 else None

prog = currentProgram  # noqa: F821
mem = prog.getMemory()
listing = prog.getListing()
fm = prog.getFunctionManager()

# Build little-endian byte pattern: low byte first
pattern_bytes = []
v = const_val
for _ in range(4):
    pattern_bytes.append(v & 0xff)
    v >>= 8

# Convert to Java byte array via Python bytearray + jbyte cast
from array import array
java_bytes = array("b", [b if b < 128 else b - 256 for b in pattern_bytes])
# findBytes wants a byte[]
import jarray  # type: ignore
jb = jarray.array(list(java_bytes), "b")

lines = []


def emit(s):
    lines.append(s)
    print(s)


emit("# searching for constant 0x%08x (LE bytes: %s)" %
     (const_val, " ".join("%02x" % b for b in pattern_bytes)))
emit("")

# Iterate memory blocks; findBytes scans within initialized blocks
all_set = mem.getAllInitializedAddressSet()
start = all_set.getMinAddress()
hits = 0
limit = 50  # safety: cap at 50 hits

while start is not None and hits < limit:
    found = mem.findBytes(start, jb, None, True, None)
    if found is None:
        break
    hits += 1
    func = fm.getFunctionContaining(found)
    fname = func.getName() if func else "?"
    emit("## hit %d: %s  in %s" % (hits, found, fname))

    # Dump 0x80 bytes of context as ASCII (printable only)
    try:
        before = mem.getBytes(found.subtract(0x40), 0x80)
        ascii_chars = []
        for byte in before:
            b = byte & 0xff
            if 0x20 <= b < 0x7f:
                ascii_chars.append(chr(b))
            else:
                ascii_chars.append(".")
        emit("  context: %r" % "".join(ascii_chars))
    except Exception as e:
        emit("  (context fetch failed: %s)" % e)

    # Look for ASCII strings within +/- 0x40 bytes
    nearby_strings = []
    for delta in range(-0x40, 0x40, 1):
        try:
            ad = found.add(delta)
            data = listing.getDataAt(ad)
            if data is not None and data.hasStringValue():
                val = data.getValue()
                try:
                    s = unicode(val).encode("ascii", "replace")
                    if len(s) >= 3:
                        nearby_strings.append("%s: %r" % (ad, s[:80]))
                except Exception:
                    pass
        except Exception:
            pass
    if nearby_strings:
        emit("  nearby defined strings:")
        for ns in nearby_strings[:8]:
            emit("    %s" % ns)
    emit("")

    start = found.add(1)

emit("# total hits: %d" % hits)
emit("# end")

if out_path:
    try:
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print("FindConstant: wrote %s" % out_path)
    except Exception as e:
        print("FindConstant: write failed: %s" % e)
        sys.exit(1)
