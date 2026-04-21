"""
List imported DLLs and symbols from a PE32+ binary.

Useful for quickly checking which networking / Steam APIs a New World build
actually imports before designing Frida hooks.

Usage:
    python tools/list_pe_imports.py --exe "G:\\NewWorldArchive\\GameClient\\Bin64\\NewWorld.exe"
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


def u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def u64(data: bytes, off: int) -> int:
    return struct.unpack_from("<Q", data, off)[0]


def parse_sections(data: bytes):
    if data[:2] != b"MZ":
        raise ValueError("Not a PE file")
    pe_off = u32(data, 0x3C)
    if data[pe_off:pe_off + 4] != b"PE\0\0":
        raise ValueError("Bad PE signature")

    coff = pe_off + 4
    num_sections = u16(data, coff + 2)
    size_opt_hdr = u16(data, coff + 16)
    opt = coff + 20
    magic = u16(data, opt)
    if magic != 0x20B:
        raise ValueError(f"Expected PE32+, got 0x{magic:x}")

    image_base = u64(data, opt + 24)
    import_rva = u32(data, opt + 0x78)
    import_size = u32(data, opt + 0x7C)

    sections = []
    sect = opt + size_opt_hdr
    for i in range(num_sections):
        base = sect + i * 40
        name = data[base:base + 8].rstrip(b"\0").decode("ascii", errors="replace")
        virt_size = u32(data, base + 8)
        virt_addr = u32(data, base + 12)
        raw_size = u32(data, base + 16)
        raw_ptr = u32(data, base + 20)
        sections.append({
            "name": name,
            "va": virt_addr,
            "vs": virt_size,
            "rs": raw_size,
            "rp": raw_ptr,
        })
    return image_base, import_rva, import_size, sections


def rva_to_off(rva: int, sections: list[dict]) -> int | None:
    for s in sections:
        size = max(s["vs"], s["rs"])
        if s["va"] <= rva < s["va"] + size:
            return s["rp"] + (rva - s["va"])
    return None


def read_cstr(data: bytes, off: int) -> str:
    end = data.find(b"\0", off)
    if end == -1:
        end = off
    return data[off:end].decode("ascii", errors="replace")


def parse_imports(data: bytes):
    _, import_rva, _, sections = parse_sections(data)
    off = rva_to_off(import_rva, sections)
    if off is None:
        return []

    imports = []
    while True:
        original_first_thunk = u32(data, off + 0x00)
        time_date_stamp = u32(data, off + 0x04)
        forwarder_chain = u32(data, off + 0x08)
        name_rva = u32(data, off + 0x0C)
        first_thunk = u32(data, off + 0x10)
        if (original_first_thunk, time_date_stamp, forwarder_chain, name_rva, first_thunk) == (0, 0, 0, 0, 0):
            break

        name_off = rva_to_off(name_rva, sections)
        dll_name = read_cstr(data, name_off) if name_off is not None else f"<bad-rva:0x{name_rva:x}>"

        thunk_rva = original_first_thunk or first_thunk
        thunk_off = rva_to_off(thunk_rva, sections)
        symbols: list[str] = []
        if thunk_off is not None:
            cur = thunk_off
            while True:
                entry = u64(data, cur)
                if entry == 0:
                    break
                if entry >> 63:
                    ordinal = entry & 0xFFFF
                    symbols.append(f"ordinal:{ordinal}")
                else:
                    ibn_off = rva_to_off(entry & 0x7FFFFFFF_FFFFFFFF, sections)
                    if ibn_off is None:
                        symbols.append(f"<bad-ibn:0x{entry:x}>")
                    else:
                        hint = u16(data, ibn_off)
                        name = read_cstr(data, ibn_off + 2)
                        symbols.append(name if name else f"hint:{hint}")
                cur += 8

        imports.append((dll_name, symbols))
        off += 20
    return imports


def main() -> int:
    parser = argparse.ArgumentParser(description="List imported DLLs and symbols from a PE32+ binary")
    parser.add_argument("--exe", required=True, help="Path to the PE file")
    parser.add_argument("--filter", default="", help="Case-insensitive substring filter for DLL or symbol names")
    args = parser.parse_args()

    exe = Path(args.exe)
    data = exe.read_bytes()
    filt = args.filter.lower()

    print(f"[+] Imports for {exe}")
    for dll, symbols in parse_imports(data):
        if filt and filt not in dll.lower() and not any(filt in sym.lower() for sym in symbols):
            continue
        print(f"\n{dll} ({len(symbols)} symbols)")
        for sym in symbols:
            if not filt or filt in dll.lower() or filt in sym.lower():
                print(f"  {sym}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
