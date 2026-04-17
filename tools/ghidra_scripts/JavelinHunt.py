# JavelinHunt.py
# Ghidra Python (Jython) script -- run from Script Manager or headlessly.
# Automates the GridMate/Javelin hunt list from analysis/ghidra_hunt_list.md.
#
# Ghidra Script Manager setup:
#   1. File > Configure > Script Directories > add this file's folder
#   2. Script Manager > find JavelinHunt > Run
#
# Outputs go to:
#   - Ghidra's Console (for quick review)
#   - C:\Users\charl\Programs\NewWorldPrivate\analysis\ghidra_findings.txt
#
# @category Analysis.New_World
# @menupath Tools.Javelin Hunt
# @runtime Jython

import json
from ghidra.program.model.listing import CodeUnit  # type: ignore
from ghidra.program.model.symbol import RefType  # type: ignore
from ghidra.program.model.scalar import Scalar  # type: ignore

# Output file
OUTPUT_PATH = r"C:\Users\charl\Programs\NewWorldPrivate\analysis\ghidra_findings.txt"

findings = {
    "anchors": {},
    "xrefs": {},
    "bit_pattern_hits": {},
    "chunk_names": [],
}


def log(msg):
    print(msg)


def find_string_address(needle):
    """Find the defined data address of a string literal."""
    listing = currentProgram.getListing()  # noqa: F821
    memory = currentProgram.getMemory()  # noqa: F821
    addr_set = memory.getAllInitializedAddressSet()
    found = findBytes(addr_set.getMinAddress(), needle, 1)  # noqa: F821
    if found is None or len(found) == 0:
        return None
    return found[0] if not isinstance(found, (list, tuple)) else found[0]


def find_all_string_addresses(needle):
    """Return all addresses that contain this exact byte pattern."""
    memory = currentProgram.getMemory()  # noqa: F821
    addr_set = memory.getAllInitializedAddressSet()
    results = []
    start = addr_set.getMinAddress()
    while start is not None:
        found = findBytes(start, needle, 1)  # noqa: F821
        if found is None:
            break
        if isinstance(found, (list, tuple)):
            if len(found) == 0:
                break
            addr = found[0]
        else:
            addr = found
        results.append(addr)
        start = addr.add(1)
        # Safety cap
        if len(results) > 200:
            break
    return results


def xrefs_to(addr):
    """Get functions that reference addr."""
    rm = currentProgram.getReferenceManager()  # noqa: F821
    refs = rm.getReferencesTo(addr)
    funcs = []
    fm = currentProgram.getFunctionManager()  # noqa: F821
    for ref in refs:
        fn = fm.getFunctionContaining(ref.getFromAddress())
        funcs.append({
            "from": str(ref.getFromAddress()),
            "type": str(ref.getReferenceType()),
            "function": fn.getName() if fn else "<none>",
            "function_entry": str(fn.getEntryPoint()) if fn else None,
        })
    return funcs


# -----------------------------------------------------------------------------
# Step 1: String anchors
# -----------------------------------------------------------------------------

log("=" * 70)
log("  JavelinHunt: Tier-1 string anchors")
log("=" * 70)

ANCHORS = [
    ("cipher",         "ECDHE-RSA-AES256-GCM-SHA384"),
    ("carrier_thread", "GridMate-Carrier Packet Send Thread"),
    ("allocator",      "GridMateAllocatorMP"),
    ("transform_chunk", "TransformReplicaChunk"),
    ("cs_disconnected", "CS_DISCONNECTED"),
    ("cs_ssl_error",    "CS_SSL_ERROR"),
    ("conn_datasend",   "conn.dataSend = "),
]

for key, needle in ANCHORS:
    addr = find_string_address(needle)
    if addr is None:
        log("  [--] %-20s  %-50s  NOT FOUND" % (key, needle[:50]))
        findings["anchors"][key] = None
        continue
    findings["anchors"][key] = str(addr)
    log("  [OK] %-20s  %-50s  %s" % (key, needle[:50], addr))

    # Collect xrefs
    refs = xrefs_to(addr)
    findings["xrefs"][key] = refs
    log("       %d xref(s):" % len(refs))
    for r in refs[:5]:
        log("         from %s  in %s @ %s" % (r["from"], r["function"],
                                                r["function_entry"]))
    if len(refs) > 5:
        log("         ...+ %d more" % (len(refs) - 5))


# -----------------------------------------------------------------------------
# Step 2: 0x42 scalar search (ReadMessageHeader fingerprint)
# -----------------------------------------------------------------------------

log("")
log("=" * 70)
log("  JavelinHunt: 0x42 bit-mask scalar hits (ReadMessageHeader)")
log("=" * 70)

# We want instructions that AND a register with 0x42. Simplest way: scan
# decompiled output of functions containing scalar 0x42. But quick
# approach first: iterate instructions in .text, check operands.

prog = currentProgram  # noqa: F821
listing = prog.getListing()
memory = prog.getMemory()
text = memory.getBlock(".text")

hits_0x42 = []
if text is not None:
    start = text.getStart()
    end = text.getEnd()
    instrs = listing.getInstructions(start, True)
    count = 0
    for ins in instrs:
        count += 1
        if count > 10_000_000:
            log("  [!] Stopped scanning after 10M instructions (set cap lower if slow)")
            break
        num_ops = ins.getNumOperands()
        for i in range(num_ops):
            obj_list = ins.getOpObjects(i)
            for obj in obj_list:
                if isinstance(obj, Scalar):
                    if obj.getUnsignedValue() == 0x42:
                        mnem = ins.getMnemonicString().lower()
                        # AND, TEST are the interesting ones
                        if mnem in ("and", "test"):
                            fm = prog.getFunctionManager()
                            fn = fm.getFunctionContaining(ins.getAddress())
                            hits_0x42.append({
                                "address": str(ins.getAddress()),
                                "mnem": mnem,
                                "operands": ins.toString(),
                                "function": fn.getName() if fn else "<none>",
                                "function_entry": str(fn.getEntryPoint()) if fn else None,
                            })

log("  Found %d AND/TEST-with-0x42 instructions in .text" % len(hits_0x42))
for h in hits_0x42[:20]:
    log("    %s  %s  in %s" % (h["address"], h["operands"], h["function"]))
if len(hits_0x42) > 20:
    log("    ... +%d more (see findings file)" % (len(hits_0x42) - 20))

findings["bit_pattern_hits"]["0x42_and_test"] = hits_0x42


# -----------------------------------------------------------------------------
# Step 3: Harvest all strings ending in "Chunk" or "Messages" or "Facet"
# -----------------------------------------------------------------------------

log("")
log("=" * 70)
log("  JavelinHunt: Javelin class string harvest")
log("=" * 70)

# Ghidra has a defined strings table. Iterate and filter.
data_iter = listing.getDefinedData(True)
seen = set()
count = 0
javelin_total = 0

for data in data_iter:
    count += 1
    if count > 2_000_000:
        break
    dt = data.getDataType().getName()
    if "string" not in dt.lower():
        continue
    try:
        val = data.getValue()
    except:  # noqa: E722
        continue
    if val is None:
        continue
    s = str(val)
    if "Javelin::" in s and len(s) < 200:
        if s not in seen:
            seen.add(s)
            javelin_total += 1

log("  Found %d unique strings containing 'Javelin::' in defined data" % javelin_total)
log("  (already mirrored in analysis/javelin_classes.txt)")
findings["javelin_string_count"] = javelin_total


# -----------------------------------------------------------------------------
# Step 4: Save findings
# -----------------------------------------------------------------------------

log("")
log("=" * 70)
log("  Writing findings to: %s" % OUTPUT_PATH)
log("=" * 70)

try:
    with open(OUTPUT_PATH, "w") as f:
        f.write(json.dumps(findings, indent=2))
    log("  [OK] Findings saved.")
except Exception as e:
    log("  [!] Failed to save: %s" % e)

log("")
log("Done. Next step: use analysis/ghidra_findings.txt to drive further queries.")
log("The cipher-string xref (findings.xrefs.cipher) points to the")
log("SecureSocketDriver root function; walk its vtable from there.")
