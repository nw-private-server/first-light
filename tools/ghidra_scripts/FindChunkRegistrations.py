# FindChunkRegistrations.py
# Ghidra Python (Jython) script.
#
# Finds all Javelin ReplicaChunk descriptor initializer functions by
# looking for the canonical pattern:
#
#   1. Function writes a string pointer to [arg2_deref + 0x30]
#   2. Function calls a hash/ClassId function with that string
#
# Since each chunk has its own (near-identical) init function due to
# template instantiation, we can't use xref of a single register()
# call. Instead we look for the string-assignment pattern itself.
#
# Output:
#   analysis/ghidra_chunks.txt  -- one line per chunk: address | name
#
# @category Analysis.New_World
# @menupath Tools.Find Chunk Registrations
# @runtime Jython

import json
from ghidra.program.model.listing import CodeUnit  # type: ignore
from ghidra.program.model.scalar import Scalar  # type: ignore

OUTPUT_PATH = r"C:\Users\<username>\Programs\NewWorldPrivate\analysis\ghidra_chunks.txt"

prog = currentProgram  # noqa: F821
listing = prog.getListing()
mem = prog.getMemory()
fm = prog.getFunctionManager()
ref_mgr = prog.getReferenceManager()

# Find all defined strings that end in "Chunk"
print("[*] Scanning defined strings for *Chunk names...")
chunk_strings = {}  # address -> name

data_iter = listing.getDefinedData(True)
count = 0
for data in data_iter:
    count += 1
    if count > 5000000:
        break
    dt = data.getDataType().getName()
    if "string" not in dt.lower() and "char" not in dt.lower():
        continue
    try:
        val = data.getValue()
    except:  # noqa: E722
        continue
    if val is None:
        continue
    try:
        if isinstance(val, unicode):  # noqa: F821 (Jython-only)
            s = val.encode("utf-8", errors="replace")
        else:
            s = str(val)
    except:  # noqa: E722
        continue
    if (8 <= len(s) <= 100 and s.endswith("Chunk")
            and s[0].isupper() and all(c.isalnum() or c == '_' for c in s)):
        chunk_strings[data.getAddress()] = s

print("[+] Found {} candidate chunk name strings".format(len(chunk_strings)))

# For each chunk name string, find xrefs and look for the init-function pattern.
# A chunk init function is a function where an xref to the chunk-name string
# comes from an instruction that writes that string pointer to an offset +0x30
# of some object. We approximate this by: any function containing a code-type
# xref to the string is a candidate.

print("[*] Walking xrefs for each chunk name string...")
chunks = []
for addr, name in chunk_strings.items():
    refs = ref_mgr.getReferencesTo(addr)
    for ref in refs:
        from_addr = ref.getFromAddress()
        fn = fm.getFunctionContaining(from_addr)
        if fn is None:
            continue
        # Only consider code references
        rtype = str(ref.getReferenceType())
        if "DATA" in rtype and "READ" not in rtype:
            # DATA refs from pure vtables; skip unless we have no better
            continue
        chunks.append({
            "name": name,
            "string_addr": str(addr),
            "ref_addr": str(from_addr),
            "ref_type": rtype,
            "init_function": fn.getName(),
            "init_entry": str(fn.getEntryPoint()),
        })

# Deduplicate by init_entry (each function once)
seen = set()
unique = []
for c in chunks:
    if c["init_entry"] in seen:
        continue
    seen.add(c["init_entry"])
    unique.append(c)

print("[+] Found {} unique chunk initializer functions".format(len(unique)))

# Write output
with open(OUTPUT_PATH, "w") as f:
    f.write("# Javelin chunk descriptor initializers\n")
    f.write("# Format: init_function_address | chunk_name | string_address\n\n")
    for c in sorted(unique, key=lambda x: x["name"]):
        f.write("{entry}  {name:50s}  {sa}\n".format(
            entry=c["init_entry"],
            name=c["name"],
            sa=c["string_addr"],
        ))

print("[+] Wrote {}".format(OUTPUT_PATH))
print("")
print("First 20 chunks found:")
for c in sorted(unique, key=lambda x: x["name"])[:20]:
    print("  {:50s}  init_fn={}  str={}".format(
        c["name"], c["init_entry"], c["string_addr"]))
