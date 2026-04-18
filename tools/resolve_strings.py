"""Resolve null-terminated strings at virtual addresses in NewWorld.exe.

Given a list of VAs (from Ghidra disassembly), map each to a file offset
using the PE section table and print the string. Used to dump the field
names of the GetLoginInfoLists RPC schema without having to navigate
every address in Ghidra manually.
"""

import struct
import sys
from pathlib import Path

EXE = Path(r"H:\SteamLibrary\steamapps\common\New World\Bin64\NewWorld.exe")

# Collected from the FUN_144f40780 disassembly slice. Organized by block.
BLOCKS = {
    "pre-name-header": [0x1483c0890, 0x1483516e0],
    "method-names": [0x1483c0878, 0x1483c08a8, 0x148367f40,
                     0x1483af750, 0x1483af788, 0x1483af7b0,
                     0x1483af7e8, 0x1483af7f8, 0x1483af838,
                     0x1483c0a58],
    "request-fields": [0x1483c08c0, 0x1483c08d0, 0x1483c08f0,
                       0x1483c0908, 0x147f773a4, 0x1483c0918,
                       0x1483c0928],
    "sub1-fields (LoginInfo top-level?)":
        [0x1483c0938, 0x1483c0948, 0x1483c0958, 0x1483c0970],
    "sub2-fields (world row?)":
        [0x148040d98, 0x147fa8034, 0x147fc22dc, 0x1483c0988,
         0x1483c09a0, 0x147ff1b90, 0x1483c09b0, 0x1483c09c8,
         0x1483c09d8, 0x1483c09e8, 0x1483c09fc, 0x1483c0a08],
    "sub3-fields (character row?)":
        [0x1483c0a70, 0x148040d68, 0x147f7a288, 0x148040d88,
         0x1483b6c00, 0x1481e7500, 0x1483c0a80, 0x148044b08,
         0x1483c0a90, 0x148044b18, 0x148044b28, 0x1483c0aa8,
         0x1483c0ab8, 0x1483c0ac8, 0x1483c0ad8, 0x1483c0ae8,
         0x1483c0b00, 0x1483c0b18, 0x1483c0b28, 0x1483c0b40,
         0x1483c0b50],
    "response-top-level":
        [0x148044b38, 0x1483c0c94, 0x147f798c0, 0x1483c0ca0,
         0x1483c0cb0, 0x1483c0cc0, 0x1483c0cd0, 0x1483bc7b0,
         0x1483c0ce8, 0x1483c0cf8, 0x1480254a0, 0x1481737f0,
         0x1483c0d10, 0x1483c0d28],
}


def parse_pe_sections(data: bytes):
    if data[:2] != b"MZ":
        sys.exit("[-] Not a PE file (MZ magic missing)")
    pe_off = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe_off:pe_off + 4] != b"PE\0\0":
        sys.exit("[-] Bad PE signature")
    coff = pe_off + 4
    num_sections = struct.unpack_from("<H", data, coff + 2)[0]
    size_opt_hdr = struct.unpack_from("<H", data, coff + 16)[0]
    opt_hdr = coff + 20
    # Magic: 0x10b = PE32, 0x20b = PE32+
    magic = struct.unpack_from("<H", data, opt_hdr)[0]
    if magic != 0x20b:
        sys.exit(f"[-] Not PE32+ (magic=0x{magic:x})")
    image_base = struct.unpack_from("<Q", data, opt_hdr + 24)[0]
    sections = []
    sect_tbl = opt_hdr + size_opt_hdr
    for i in range(num_sections):
        base = sect_tbl + i * 40
        name = data[base:base + 8].rstrip(b"\0").decode("ascii", errors="replace")
        virt_size = struct.unpack_from("<I", data, base + 8)[0]
        virt_addr = struct.unpack_from("<I", data, base + 12)[0]  # RVA
        raw_size = struct.unpack_from("<I", data, base + 16)[0]
        raw_ptr = struct.unpack_from("<I", data, base + 20)[0]
        sections.append({
            "name": name, "vs": virt_size, "va": virt_addr,
            "rs": raw_size, "rp": raw_ptr,
        })
    return image_base, sections


def va_to_file_offset(va: int, image_base: int, sections: list) -> int | None:
    rva = va - image_base
    for s in sections:
        if s["va"] <= rva < s["va"] + max(s["vs"], s["rs"]):
            return s["rp"] + (rva - s["va"])
    return None


def read_cstring(data: bytes, off: int, max_len: int = 256) -> str:
    end = data.find(b"\0", off, off + max_len)
    if end == -1:
        return data[off:off + max_len].decode("utf-8", errors="replace") + "..."
    return data[off:end].decode("utf-8", errors="replace")


def main():
    if not EXE.exists():
        sys.exit(f"[-] Not found: {EXE}")
    print(f"[+] Reading {EXE} ({EXE.stat().st_size / 1024 / 1024:.1f} MB)")
    data = EXE.read_bytes()
    image_base, sections = parse_pe_sections(data)
    print(f"[+] ImageBase: 0x{image_base:x}")
    print(f"[+] Sections:")
    for s in sections:
        print(f"      {s['name']:<10} VA=0x{image_base + s['va']:x} size=0x{s['vs']:x}")
    print()

    for label, addrs in BLOCKS.items():
        print(f"=== {label} ===")
        for va in addrs:
            off = va_to_file_offset(va, image_base, sections)
            if off is None:
                print(f"  0x{va:x}  <not in any section>")
                continue
            s = read_cstring(data, off)
            print(f"  0x{va:x}  {s!r}")
        print()


if __name__ == "__main__":
    main()
