# HeadlessDecompile.py
# Auto-generated helper used by `ghidra decompile <addr>`.
# Decompiles the function containing the address in args[0] and writes C to
# args[1] (or stdout if args[1] absent).
#
# @category Analysis.New_World
# @runtime Jython

import sys
from ghidra.app.decompiler import DecompInterface  # type: ignore
from ghidra.util.task import ConsoleTaskMonitor  # type: ignore

args = list(getScriptArgs())  # noqa: F821
if not args:
    print("HeadlessDecompile: missing address arg")
    sys.exit(1)

addr_str = args[0]
out_path = args[1] if len(args) > 1 else None

addr = currentProgram.getAddressFactory().getAddress(addr_str)  # noqa: F821
if addr is None:
    print("HeadlessDecompile: could not parse address %s" % addr_str)
    sys.exit(1)

func = currentProgram.getFunctionManager().getFunctionContaining(addr)  # noqa: F821
if func is None:
    print("HeadlessDecompile: no function contains %s" % addr_str)
    sys.exit(1)

dec = DecompInterface()
dec.openProgram(currentProgram)  # noqa: F821
res = dec.decompileFunction(func, 120, ConsoleTaskMonitor())
if not res.decompileCompleted():
    print("HeadlessDecompile: decompile failed: %s" % res.getErrorMessage())
    sys.exit(1)

text = "// %s @ %s\n%s" % (func.getName(), func.getEntryPoint(), res.getDecompiledFunction().getC())

if out_path:
    with open(out_path, "w") as f:
        f.write(text)
    print("HeadlessDecompile: wrote %s" % out_path)
else:
    print(text)
