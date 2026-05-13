# -*- coding: utf-8 -*-
# ExtractTypeNames.py - given a list of (type_id, fingerprint_hex) pairs,
# locate each fingerprint in the binary, find data references to it,
# then scan nearby bytes for printable ASCII strings (class names) and
# UUIDs (in canonical {hhhhhhhh-hhhh-...-hhhh} or hhhhhhhhhhhh form).
#
# args[0] = path to a TSV file with `type_id\tfingerprint_hex` per line
#           (type_id in hex like 0x18a6; fingerprint as hex bytes)
# args[1] = output path
#
# @category Analysis.New_World
# @runtime Jython

import sys
import jarray  # noqa: F821

args = list(getScriptArgs())  # noqa: F821
if len(args) < 2:
    print("ExtractTypeNames: need <tsv-path> <out-path>")
    sys.exit(1)

tsv_path = args[0]
out_path = args[1]

prog = currentProgram  # noqa: F821
mem = prog.getMemory()
listing = prog.getListing()
fm = prog.getFunctionManager()


def signed(b):
    return b - 256 if b > 127 else b


def find_first_byte_match(needle_hex):
    pattern = [signed(int(needle_hex[i:i + 2], 16))
               for i in range(0, len(needle_hex), 2)]
    jb = jarray.array(pattern, "b")
    all_set = mem.getAllInitializedAddressSet()
    return mem.findBytes(all_set.getMinAddress(), jb, None, True, None)


def find_xrefs_to(addr):
    """Return list of source addresses that reference `addr`."""
    refs = prog.getReferenceManager().getReferencesTo(addr)
    sources = []
    for r in refs:
        sources.append(r.getFromAddress())
    return sources


def scan_nearby_strings(center_addr, radius=0x100):
    """Walk the data listing near `center_addr` looking for ASCII strings
    and UUID-like sequences. Returns list of (addr, kind, value)."""
    findings = []
    base = center_addr.getOffset() - radius
    end = center_addr.getOffset() + radius
    cur = mem.getMinAddress().getNewAddress(base)
    end_addr = mem.getMinAddress().getNewAddress(end)
    # Walk byte-by-byte, identifying runs of printable ASCII >=4 chars.
    pos = base
    run_start = None
    run_chars = []
    while pos < end:
        try:
            b = mem.getByte(mem.getMinAddress().getNewAddress(pos)) & 0xff
        except Exception:
            pos += 1
            continue
        if 0x20 <= b < 0x7f:
            if run_start is None:
                run_start = pos
            run_chars.append(chr(b))
        else:
            # End of run — emit if long enough
            if run_start is not None and len(run_chars) >= 6:
                s = "".join(run_chars)
                # Heuristic: UUID strings start with "{" and contain dashes
                if s.startswith("{") and "-" in s:
                    kind = "uuid"
                else:
                    kind = "string"
                findings.append((run_start, kind, s))
            run_start = None
            run_chars = []
        pos += 1
    if run_start is not None and len(run_chars) >= 6:
        s = "".join(run_chars)
        kind = "uuid" if s.startswith("{") and "-" in s else "string"
        findings.append((run_start, kind, s))
    return findings


lines_out = []


def emit(s):
    lines_out.append(s)
    print(s)


emit("# type-name extraction via fingerprint search\n")

with open(tsv_path) as f:
    pairs = []
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            pairs.append((parts[0], parts[1]))

emit("# %d (type_id, fingerprint) pairs to process\n" % len(pairs))

for type_id_str, fingerprint_hex in pairs:
    emit("## type %s  fingerprint=%s" % (type_id_str, fingerprint_hex))
    stub = find_first_byte_match(fingerprint_hex)
    if stub is None:
        emit("  no stub found")
        emit("")
        continue
    emit("  stub at: %s" % stub)
    sources = find_xrefs_to(stub)
    emit("  xref sources: %d" % len(sources))
    if not sources:
        emit("")
        continue
    # Pick first source (usually the only one) and scan nearby
    src = sources[0]
    emit("  xref source: %s" % src)
    findings = scan_nearby_strings(src, radius=0x80)
    # Filter to short strings that look like class names (no `{` for non-UUID)
    candidates = [
        (a, k, v) for a, k, v in findings
        if (k == "uuid") or (
            len(v) >= 6 and len(v) <= 80 and
            (v[0].isalpha() or v[0] == "_") and
            ("Msg" in v or "Trait" in v or "::" in v or v.endswith("State") or
             v.endswith("Settings") or v.endswith("Data") or
             v.endswith("Info") or v.endswith("Listener"))
        )
    ]
    for addr, kind, val in candidates:
        emit("  candidate [%s @ 0x%x]: %r" % (kind, addr, val))
    emit("")

emit("# end")

with open(out_path, "w") as f:
    f.write("\n".join(lines_out))
print("ExtractTypeNames: wrote %s" % out_path)
