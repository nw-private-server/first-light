"""
Replay store for the redacted login dump at
info/nw-login-safe-20260502-153840/messages-redacted.txt.

Parses Mixed Nuts' xxd-style capture of a working login (177 messages) into
ReplayMessage records keyed by seq. Redacted spans (XX) are preserved as
0x00 bytes plus an explicit (offset, length) span list, so callers can decide
whether to skip a message or substitute their own bytes.

R-direction messages start with the typed-stream marker:
    [0x00 0x01] [(type & 0x3F) | 0x80] [(type >> 6) & 0xFF]
i.e. a 6-bit-continuation tagged encoding of the GridMate type id. W-direction
messages have a 24-byte client-only header before that marker, so we don't
enforce it there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReplayMessage:
    seq: int
    type_id: int
    direction: str
    body: bytes
    has_redaction: bool
    redacted_spans: list[tuple[int, int]] = field(default_factory=list)


_HEADER_RE = re.compile(
    r"^seq:\s*0x([0-9a-fA-F]+)\s*\((\d+)\)\s*$"
)
_TYPE_RE = re.compile(
    r"^type:\s*0x([0-9a-fA-F]+)\s*\((\d+)\)\s*$"
)
_DIR_RE = re.compile(r"^direction:\s*([WR])\s*$")
_SIZE_RE = re.compile(r"^size:\s*(\d+)\s*bytes\s*$")
_HEX_ROW_RE = re.compile(
    r"^([0-9a-fA-F]{8})\s+((?:[0-9a-fA-FxX]{2}\s+){1,16})\|"
)
_SEPARATOR = "=" * 16  # any line with >= 16 '=' chars marks a block boundary


def _parse_hex_row(line: str) -> tuple[int, list[str]] | None:
    m = _HEX_ROW_RE.match(line)
    if not m:
        return None
    offset = int(m.group(1), 16)
    tokens = m.group(2).split()
    return offset, tokens


def _decode_body(
    hex_rows: list[tuple[int, list[str]]],
) -> tuple[bytes, list[tuple[int, int]]]:
    body = bytearray()
    spans: list[tuple[int, int]] = []
    cur_span_start: int | None = None

    for offset, tokens in hex_rows:
        if offset != len(body):
            raise ValueError(
                f"hex row offset 0x{offset:x} does not match body length "
                f"0x{len(body):x} (rows out of order or gap)"
            )
        for tok in tokens:
            pos = len(body)
            if tok in ("XX", "xx"):
                body.append(0x00)
                if cur_span_start is None:
                    cur_span_start = pos
            else:
                if cur_span_start is not None:
                    spans.append((cur_span_start, pos - cur_span_start))
                    cur_span_start = None
                body.append(int(tok, 16))

    if cur_span_start is not None:
        spans.append((cur_span_start, len(body) - cur_span_start))

    return bytes(body), spans


class ReplayStore:
    def __init__(self, dump_path: Path):
        self._path = Path(dump_path)
        self._messages: list[ReplayMessage] = []
        self._by_seq: dict[int, ReplayMessage] = {}
        self.validation_warnings: list[str] = []
        self._parse()

    @property
    def messages(self) -> list[ReplayMessage]:
        return list(self._messages)

    def get(self, seq: int) -> ReplayMessage | None:
        return self._by_seq.get(seq)

    def messages_in_range(
        self,
        start_seq: int,
        end_seq: int,
        direction: str | None = None,
    ) -> list[ReplayMessage]:
        out = []
        for m in self._messages:
            if not (start_seq <= m.seq <= end_seq):
                continue
            if direction is not None and m.direction != direction:
                continue
            out.append(m)
        return out

    def replay_messages_after_v3(
        self, max_seq: int = 0x24, *, include_redacted: bool = False,
    ) -> list[ReplayMessage]:
        return [
            m
            for m in self._messages
            if 0x2 <= m.seq <= max_seq
            and m.direction == "R"
            and (include_redacted or not m.has_redaction)
        ]

    def _parse(self) -> None:
        text = self._path.read_text(encoding="utf-8", errors="strict")
        lines = text.splitlines()

        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            if line.startswith(_SEPARATOR) and set(line.strip()) == {"="}:
                i += 1
                i = self._parse_block(lines, i)
            else:
                i += 1

        self._messages.sort(key=lambda m: m.seq)

    def _parse_block(self, lines: list[str], i: int) -> int:
        n = len(lines)
        seq: int | None = None
        type_id: int | None = None
        direction: str | None = None
        size: int | None = None

        while i < n:
            line = lines[i]
            stripped = line.strip()
            if line.startswith(_SEPARATOR) and set(stripped) == {"="}:
                break
            if stripped == "raw:":
                i += 1
                break
            m = _HEADER_RE.match(stripped)
            if m:
                seq = int(m.group(1), 16)
                i += 1
                continue
            m = _TYPE_RE.match(stripped)
            if m:
                type_id = int(m.group(1), 16)
                i += 1
                continue
            m = _DIR_RE.match(stripped)
            if m:
                direction = m.group(1)
                i += 1
                continue
            m = _SIZE_RE.match(stripped)
            if m:
                size = int(m.group(1))
                i += 1
                continue
            i += 1

        hex_rows: list[tuple[int, list[str]]] = []
        while i < n:
            line = lines[i]
            stripped = line.strip()
            if line.startswith(_SEPARATOR) and set(stripped) == {"="}:
                break
            row = _parse_hex_row(line)
            if row is not None:
                hex_rows.append(row)
            i += 1

        if seq is None or type_id is None or direction is None or size is None:
            return i

        body, spans = _decode_body(hex_rows)

        if len(body) != size:
            raise ValueError(
                f"seq=0x{seq:x} type=0x{type_id:x} dir={direction}: "
                f"body length {len(body)} != header size {size}"
            )

        if direction == "R":
            expected = bytes([
                0x00,
                0x01,
                (type_id & 0x3F) | 0x80,
                (type_id >> 6) & 0xFF,
            ])
            if len(body) < 4 or body[:4] != expected:
                got = body[:4].hex() if len(body) >= 4 else body.hex()
                self.validation_warnings.append(
                    f"seq=0x{seq:x} type=0x{type_id:x} dir=R: marker "
                    f"mismatch (expected {expected.hex()}, got {got})"
                )

        msg = ReplayMessage(
            seq=seq,
            type_id=type_id,
            direction=direction,
            body=body,
            has_redaction=bool(spans),
            redacted_spans=spans,
        )
        self._messages.append(msg)
        self._by_seq[seq] = msg
        return i


if __name__ == "__main__":
    dump = (
        Path(__file__).resolve().parents[2]
        / "info"
        / "nw-login-safe-20260502-153840"
        / "messages-redacted.txt"
    )
    store = ReplayStore(dump)

    total = len(store.messages)
    by_dir: dict[str, int] = {}
    redacted_by_dir: dict[str, int] = {}
    clean_by_dir: dict[str, int] = {}
    redacted_total = 0

    for m in store.messages:
        by_dir[m.direction] = by_dir.get(m.direction, 0) + 1
        if m.has_redaction:
            redacted_total += 1
            redacted_by_dir[m.direction] = redacted_by_dir.get(m.direction, 0) + 1
        else:
            clean_by_dir[m.direction] = clean_by_dir.get(m.direction, 0) + 1

    print(f"total messages: {total}")
    for d in sorted(by_dir):
        print(
            f"  dir={d}: {by_dir[d]} "
            f"(redacted={redacted_by_dir.get(d, 0)}, "
            f"clean={clean_by_dir.get(d, 0)})"
        )
    print(f"redacted total: {redacted_total}")
    print(f"fully recoverable: {total - redacted_total}")

    replayable = store.replay_messages_after_v3()
    print(
        f"replay_messages_after_v3(max_seq=0x24): {len(replayable)} clean R-msgs"
    )
    for m in replayable:
        print(
            f"  seq=0x{m.seq:x} type=0x{m.type_id:x} size={len(m.body)}"
        )

    if store.validation_warnings:
        print(f"\nvalidation warnings ({len(store.validation_warnings)}):")
        for w in store.validation_warnings:
            print(f"  {w}")
    else:
        print("\nno validation warnings")
