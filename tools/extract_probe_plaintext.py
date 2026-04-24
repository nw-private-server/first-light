"""Extract decrypted Javelin plaintext records from a `dtls_probe.py` log.

The probe captures `openssl s_server -msg -debug -state` output verbatim. After
the DTLS handshake completes, every encrypted application_data record from the
client triggers two distinct outputs:

  1. A debug header callback printed as ASCII text:
        <<< Not TLS data or unknown version (version=65277, content_type=256)
        [length 000d]
            17 fe fd 00 01 00 00 00 00 00 NN 00 LL

  2. The decrypted plaintext written as raw bytes to s_server's stdout.

s_server does NOT fire a content_type=23 callback for application_data, so the
raw plaintext appears as a binary chunk between the end of the header
hex-dump line and the next debug line (typically `read from 0x...`).

This script extracts those plaintext chunks, attempts to parse each via
`server.javelin.frame.parse_datagram`, and prints a summary.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from server.javelin.frame import parse_datagram, parse_envelope, MessageFlags  # noqa: E402


HEADER_TAG = b"<<< Not TLS data or unknown version"
NEXT_DBG_TAGS = (b"read from", b"write to", b"<<<", b">>>", b"SSL_", b"DONE", b"-----")


def find_plaintext_chunks(blob: bytes) -> list[tuple[int, bytes]]:
    """Return a list of (offset, plaintext_bytes) for each decrypted record."""
    out: list[tuple[int, bytes]] = []
    pos = 0
    while True:
        idx = blob.find(HEADER_TAG, pos)
        if idx < 0:
            break
        # Read the rest of the line to extract the length
        eol = blob.find(b"\n", idx)
        line = blob[idx:eol]
        m = re.search(rb"length ([0-9a-fA-F]+)", line)
        if not m:
            pos = eol
            continue
        rec_len = int(m.group(1), 16)
        # Skip past the hex dump of the header (4 hex chars + space per byte,
        # 16 bytes per line). For a 13-byte record header it's just one line.
        # Find the line that starts with raw hex (4-space indent + bytes).
        # The simpler heuristic: skip past the next blank or non-hex line.
        cursor = eol + 1
        # Skip the first line of indented hex content (the header itself)
        # which is "    XX XX XX..." up to a CRLF.
        while cursor < len(blob):
            line_end = blob.find(b"\n", cursor)
            if line_end < 0:
                line_end = len(blob)
            line = blob[cursor:line_end]
            stripped = line.strip()
            if not stripped:
                cursor = line_end + 1
                continue
            # Hex dump of header bytes — looks like "XX XX XX ..." all hex+space.
            # Once we leave the hex dump region, we hit raw plaintext OR a debug tag.
            if all(c in b" 0123456789abcdefABCDEF\r\t" for c in stripped):
                # Still inside the header hex dump
                cursor = line_end + 1
                continue
            break

        # Now `cursor` points at the first byte after the header hex dump.
        # Everything from here until the next debug tag is plaintext.
        next_idx = len(blob)
        for tag in NEXT_DBG_TAGS:
            i = blob.find(tag, cursor)
            if i >= 0 and i < next_idx:
                next_idx = i
        plaintext = blob[cursor:next_idx]
        # Strip leading/trailing CRLF whitespace
        plaintext = plaintext.strip(b"\r\n\t ")
        # Filter to records of the expected size only:
        # ciphertext = 8-byte explicit nonce + plaintext + 16-byte GCM tag
        # so plaintext_len = rec_len - 24
        expected = rec_len - 24
        if expected > 0 and len(plaintext) >= expected:
            plaintext = plaintext[:expected]
        out.append((idx, plaintext))
        pos = next_idx
    return out


def fmt_record(rec) -> str:
    flag_names = []
    for f in MessageFlags:
        if rec.flags & f:
            flag_names.append(f.name)
    flags_str = "|".join(flag_names) or "0"
    extras = []
    if rec.is_system:
        sid = rec.system_msg_id
        extras.append(f"sysmsg={sid}")
    return (
        f"ch={rec.channel} seq={rec.sequence} relSeq={rec.reliable_sequence} "
        f"size={rec.size} flags={flags_str} "
        + (" ".join(extras) if extras else "")
        + f" payload={rec.payload.hex()}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log", type=Path)
    ap.add_argument("--limit", type=int, default=20, help="how many records to dump")
    args = ap.parse_args()

    blob = args.log.read_bytes()
    chunks = find_plaintext_chunks(blob)
    print(f"[+] {args.log}")
    print(f"[+] found {len(chunks)} plaintext chunks")
    print()

    for n, (offset, pt) in enumerate(chunks[: args.limit]):
        if len(pt) == 0:
            continue
        print(f"--- record #{n} @ log offset 0x{offset:x}, len={len(pt)} ---")
        print(f"  hex: {pt.hex()}")
        try:
            env, body = parse_envelope(pt)
        except ValueError as e:
            print(f"  envelope error: {e}")
            print()
            continue
        print(f"  envelope: type=0x{env.type_byte:02x} proto=0x{env.proto:02x} "
              f"seq={env.sequence}{' [encrypted]' if env.is_encrypted else ''}")
        result = parse_datagram(body)
        if result.error:
            print(f"  parse error: {result.error}")
        print(f"  trailing_bits: {result.trailing_bits}")
        for i, rec in enumerate(result.messages):
            print(f"  msg{i}: {fmt_record(rec)}")
        print()

    if len(chunks) > args.limit:
        print(f"... and {len(chunks) - args.limit} more")


if __name__ == "__main__":
    main()
