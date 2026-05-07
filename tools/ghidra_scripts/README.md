# Ghidra scripts for the New World binary

Reusable Jython scripts that drive headless Ghidra against the imported
NewWorld.exe. They're called either through the project's `tools/ghidra`
CLI wrapper or directly via Ghidra's Script Manager.

## Setup

These scripts live in `tools/ghidra_scripts/` and are auto-registered
on the Ghidra script path by the `tools/ghidra` wrapper (it passes
`-scriptPath` to `analyzeHeadless`). For interactive use in the Ghidra
GUI, add this directory under **Window → Script Manager → Manage
Script Directories**.

All scripts write coding declaration `# -*- coding: utf-8 -*-` and
target Ghidra 12.x with Jython 2.7.

## The CLI wrapper: `tools/ghidra`

A thin Python wrapper around `analyzeHeadless`. All commands operate
on the project at `analysis/ghidra_project/NewWorld`.

```
ghidra analyze <exe> [--detach] [--overwrite]
    Import + auto-analyze a binary. --detach runs in background.

ghidra decompile <addr> [--out FILE]
    Decompile the function containing <addr>. Backed by HeadlessDecompile.py.

ghidra script <name.py> [args...]
    Run a script from this directory against the imported binary.

ghidra status / ghidra logs [--follow] / ghidra kill
    Manage detached analyze runs.
```

Environment overrides: `GHIDRA_HOME` (Ghidra install dir),
`NW_GHIDRA_BIN` (imported binary name; default `NewWorld.exe`).

## Script index

| Script | Purpose | Args |
|---|---|---|
| [HeadlessDecompile.py](#headlessdecompile) | Decompile one function | `<addr> [out_path]` |
| [FindXrefs.py](#findxrefs) | All xrefs to an address, grouped by type | `<addr> [out_path]` |
| [FindStringXrefs.py](#findstringxrefs) | Locate a literal string + dump its xrefs | `<needle> [out_path]` |
| [FindConstant.py](#findconstant) | Find every occurrence of a 32-bit constant | `<value> [out_path]` |
| [FindOffsetWrites.py](#findoffsetwrites) | `MOV [reg+OFFSET], imm` immediate-store scan | `<offset> <value> [out_path]` |
| [FindOffsetReferences.py](#findoffsetreferences) | Any operand with target displacement (read or write) | `<offset> [out_path] [addr_prefix]` |
| [DumpDataWindow.py](#dumpdatawindow) | Qword data dump with xref + string interpretation | `<addr> [radius_hex] [out_path]` |
| [DumpInstructionsWindow.py](#dumpinstructionswindow) | Disassemble around an address (works when Ghidra hasn't auto-created the function) | `<addr> [out_path]` |
| [FindWrapperSubstateWriters.py](#findwrappersubstatewriters) | Specialized: find writers of `wrapper[+0xa0]` (state-10→11 gate) | `[out_path]` |
| [JavelinHunt.py](JavelinHunt.py) | Pre-existing: automates the hunt list from `analysis/ghidra_hunt_list.md` | (none) |
| [FindChunkRegistrations.py](FindChunkRegistrations.py) | Pre-existing: identifies Javelin ReplicaChunk init functions | (none) |

## Generic-purpose scripts

### HeadlessDecompile

Decompile one function. Used by `ghidra decompile` under the hood.

```
ghidra decompile 0x14644a070
ghidra decompile 0x14644a070 --out analysis/decomp_state_machine.txt
```

Direct: `ghidra script HeadlessDecompile <addr> [out_path]`. Address
can be hex with or without `0x` prefix. With no `out_path`, prints to
stdout. The function lookup uses `getFunctionContaining(addr)`, so
addresses inside a function body work, not just function entries.

### FindXrefs

Dump every reference to an address, grouped by reference type
(DATA, UNCONDITIONAL_CALL, CONDITIONAL_CALL, etc.) and deduplicated
by enclosing function.

```
ghidra script FindXrefs 0x145a87010 analysis/xrefs_handler.txt
```

Output: `total references: N`, then per reference type a list of
`from <addr> in <func_name> @ <func_entry>`. Enclosing function is
`?` if Ghidra didn't auto-create a function at that location — that
itself is a useful signal.

### FindStringXrefs

Find every defined string in the binary that contains a substring,
then list xrefs to each match.

```
ghidra script FindStringXrefs PlayerManagerSelfIdentification analysis/xrefs.txt
```

Useful for the "identify a handler by its log message" pattern: the
PlayerManagerSelfIdentification handler was found this way (its
first action is `FUN_141721c20("GameMessagePort", "PlayerManager...")`).

The Jython 2.7 `unicode()` quirk is handled — strings containing
non-ASCII bytes are encoded with `errors="replace"` rather than
crashing.

### FindConstant

Find every place in the binary where a 32-bit constant appears
(little-endian byte pattern).

```
ghidra script FindConstant 0xFE476177 analysis/find_constant.txt
```

For each hit, prints the address, enclosing function (if any), and
nearby defined ASCII strings within ±0x40 bytes. Useful for
identifying CRC/event-id constants by their context — though in
release builds where AZ::Crc32 source strings are stripped, the
context will often be empty.

### FindOffsetWrites

Specialized: scan all instructions for `MOV [reg + OFFSET], imm`
where `imm` matches a target value. Grouped by enclosing function.

```
ghidra script FindOffsetWrites 0xa0 0x2 analysis/find_writers.txt
ghidra script FindOffsetWrites 0xfd 0x1 analysis/find_destroy_flag_writer.txt
```

This is the workhorse that nailed three single-writer findings on
the New World binary in 2026-05-07: the wrapper substate=2 setter
(`onConnectionSuccess`), the destroy-flush flag writer (gated by
event `0xFE476177`), and the state-12 gate writer (the wrapper's
`markSpawnPointReady`).

Note: this only catches **immediate stores**. Register-based stores
(`MOV reg, imm; MOV [other+OFFSET], reg`) and memcpy patterns are
not detected — see `FindOffsetReferences` for a broader scan.

### FindOffsetReferences

Broader than `FindOffsetWrites`: catches **any** instruction whose
operand has a memory access with the target displacement (any opcode,
any value, read or write). Optional address-range filter by function
entry prefix.

```
ghidra script FindOffsetReferences 0x252 analysis/all_252.txt
ghidra script FindOffsetReferences 0x252 analysis/wrapper_only.txt 145a
```

Use when `FindOffsetWrites` returns nothing for a known-meaningful
offset — the writer may use a non-immediate store pattern. Filtering
to a known address range (e.g. the wrapper class neighborhood) makes
the noise tractable.

### DumpDataWindow

Print qword-aligned memory in a window, with cross-reference hints
and string interpretation when the qword looks like an address into
a defined string.

```
ghidra script DumpDataWindow 0x14abcc15c 0x100 analysis/dispatch_table.txt
ghidra script DumpDataWindow 0x1484f9ff0 0x80 analysis/state_names.txt
```

Useful for inspecting dispatch tables, vtables, and string-pool
arrays. The `[5xref]` annotation on common addresses helps spot
function-pointer entries that are reused across many table rows.

### DumpInstructionsWindow

Walk the instruction listing around an address, disassembling
forward and backward. Works even when Ghidra's auto-analysis didn't
create a function at that location.

```
ghidra script DumpInstructionsWindow 0x146454bf3 analysis/disasm.txt
```

This is what revealed the MSVC virtual-base `this`-adjustment thunk
pattern (`MOVSXD; SUB; JMP`) at the call site for the
PlayerManagerSelfIdentification handler — that 3-instruction sequence
isn't inside any auto-discovered function, so `HeadlessDecompile`
couldn't reach it.

## Specialized scripts

### FindWrapperSubstateWriters

A specific-purpose scan that combines two strategies for finding
writers of the `GameConnectionWrapper` substate at `+0xa0`:

1. Pattern scan for `MOV [reg + 0xa0], imm` grouped by `imm` value
   (`0/1/2/3/4/5` listed separately).
2. Xref scan of `FUN_1402a1750`, the `&substate` accessor — list
   callers in case any write through the returned pointer.

```
ghidra script FindWrapperSubstateWriters analysis/wrapper_writers.txt
```

The first time this ran, strategy 1 returned 549 hits across the
binary (most unrelated classes) and strategy 2 returned 3 callers
(none of which were writers — they used the address as an opaque
identity token). The breakthrough was filtering strategy 1's hits
to the wrapper's address neighborhood (`0x145a8xxxx`/`0x145a9xxxx`),
which left exactly one hit: `FUN_145a87010`, the
`onConnectionSuccess` handler. This is the script that found the
state-10→11 gate writer — see `analysis/state_machine_summary.md`.

`FindOffsetWrites` is the generalized version of this script. Kept
the specialized version for documentation / reproducibility of the
specific find.

## Output convention

All scripts that take an `out_path` argument write the same content
to both stdout (interleaved with Ghidra's `INFO` log) and the file.
Output paths can be absolute or relative to the directory where
`ghidra script` was invoked.

A `.gitignore` rule excludes `analysis/ghidra_project/`, but the
`.txt` outputs the scripts produce are tracked under `analysis/`
when committed. Naming conventions used so far:

- `decomp_<descriptor>.txt` — single-function decompiles
- `xrefs_<symbol>.txt` — xref dumps for a symbol or address
- `find_<purpose>.txt` — scan results
- `dump_<descriptor>.txt` — raw memory or instruction dumps

## Adding a new script

Drop a `.py` file in this directory. Required header:

```python
# -*- coding: utf-8 -*-
# YourScript.py
# One-line description.
#
# args[0] = ...
# args[1] = ... (optional out_path)
#
# @category Analysis.New_World
# @runtime Jython
```

The `@category` and `@runtime` tags let the GUI Script Manager
classify it correctly. Read script args via `getScriptArgs()` (a
Java `String[]`).

Keep scripts ASCII or declare the `coding: utf-8` header — Jython
2.7 chokes on unannotated non-ASCII source.
