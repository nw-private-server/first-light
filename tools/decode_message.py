"""Decode a wire-type message body and pretty-print the result.

Surfaces `server.javelin.dispatch` as a developer CLI. Useful for
hand-checking a captured body, sanity-checking a generator's output,
or eyeballing what the codec library makes of an unknown blob.

Usage:

  # Hex on the command line
  tools/decode_message.py --type 0x15d --direction R --hex '00019d050003af9100000001'

  # Body in a file (raw bytes)
  tools/decode_message.py --type 0x65c --direction R --file /tmp/body.bin

  # Body on stdin (raw bytes)
  cat body.bin | tools/decode_message.py --type 0x18a6 --direction W --stdin

  # Pluck the Nth body of a type from the captured replay
  tools/decode_message.py --type 0x15d --direction R --replay-index 0

The default direction is R; pass `--direction W` for client-side bodies.
The output is the codec dataclass formatted with `pprint`.
"""

from __future__ import annotations

import argparse
import sys
import pprint
from pathlib import Path

# Make `server.*` importable when running from the repo root.
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from server.javelin import dispatch  # noqa: E402


def _parse_type_id(raw: str) -> int:
    """Accept '0x15d', '15d', '349' (decimal)."""
    if raw.lower().startswith("0x"):
        return int(raw, 16)
    # Allow bare hex if non-decimal chars present
    if any(c in raw.lower() for c in "abcdef"):
        return int(raw, 16)
    return int(raw, 10)


def _read_body(args: argparse.Namespace) -> bytes:
    sources_set = sum(
        1 for x in (
            args.hex, args.file, args.stdin,
            args.replay_index is not None,
            args.seq is not None,
        ) if x
    )
    if sources_set != 1:
        raise SystemExit(
            "exactly one of --hex / --file / --stdin / --replay-index / --seq required"
        )
    if args.hex:
        return bytes.fromhex(args.hex.replace(" ", ""))
    if args.file:
        return Path(args.file).read_bytes()
    if args.stdin:
        return sys.stdin.buffer.read()
    if args.replay_index is not None:
        from server.javelin.replay_store import ReplayStore
        replay_path = REPO / "info" / "nw-login-safe-20260502-153840" / "messages-redacted.txt"
        if not replay_path.exists():
            raise SystemExit(f"replay file not found at {replay_path}")
        store = ReplayStore(replay_path)
        matching = [
            m for m in store.messages
            if m.type_id == args.type_id and m.direction == args.direction
        ]
        if not matching:
            raise SystemExit(
                f"no captured messages for type=0x{args.type_id:x} dir={args.direction}"
            )
        if args.replay_index >= len(matching):
            raise SystemExit(
                f"--replay-index {args.replay_index} out of range "
                f"(0..{len(matching) - 1})"
            )
        return matching[args.replay_index].body
    if args.seq is not None:
        from server.javelin.replay_store import ReplayStore
        replay_path = REPO / "info" / "nw-login-safe-20260502-153840" / "messages-redacted.txt"
        if not replay_path.exists():
            raise SystemExit(f"replay file not found at {replay_path}")
        store = ReplayStore(replay_path)
        # Match by seq alone; verify the type+direction agree with the
        # message at that seq (otherwise the user has a wrong --type).
        match = next((m for m in store.messages if m.seq == args.seq), None)
        if match is None:
            raise SystemExit(f"no captured message at seq=0x{args.seq:x}")
        if match.type_id != args.type_id:
            raise SystemExit(
                f"seq=0x{args.seq:x} is type=0x{match.type_id:x} "
                f"(not the --type 0x{args.type_id:x} you specified)"
            )
        if match.direction != args.direction:
            raise SystemExit(
                f"seq=0x{args.seq:x} direction is {match.direction!r} "
                f"(not the --direction {args.direction!r} you specified)"
            )
        return match.body
    raise AssertionError("unreachable")


def _list_wire_types() -> int:
    """Print every captured wire-type the dispatcher knows about.

    Cross-references the bundled captured replay (count + directions per
    type-id) with the dispatcher's coverage. Useful as a "what can I
    decode?" lookup before constructing a body source.
    """
    from server.javelin.replay_store import ReplayStore
    replay_path = REPO / "info" / "nw-login-safe-20260502-153840" / "messages-redacted.txt"
    captured: dict[int, dict] = {}
    if replay_path.exists():
        store = ReplayStore(replay_path)
        for m in store.messages:
            d = captured.setdefault(m.type_id, {"count": 0, "dirs": set()})
            d["count"] += 1
            d["dirs"].add(m.direction)

    supported = sorted(dispatch.supported_type_ids())
    print(f"# {len(supported)} wire-types known to the dispatcher")
    print(f"# {'type':>6}  {'count':>5}  {'dirs':>4}  decoder")
    for tid in supported:
        info = captured.get(tid, {"count": 0, "dirs": set()})
        dirs = "".join(sorted(info["dirs"])) or "—"
        decoder = dispatch.DECODERS.get(tid)
        # Best-effort decoder identifier
        name = getattr(decoder, "__name__", "<closure>")
        print(f"  0x{tid:04x}  {info['count']:>5}  {dirs:>4}  {name}")
    # Also flag any captured types without a registered decoder (only 0x03
    # in the current state; serves as a self-check).
    missing = sorted(set(captured) - set(supported))
    if missing:
        print()
        print(f"# {len(missing)} captured type(s) not in dispatcher (intentional skips):")
        for tid in missing:
            info = captured[tid]
            dirs = "".join(sorted(info["dirs"]))
            print(f"  0x{tid:04x}  {info['count']:>5}  {dirs:>4}  (no decoder — server-emit-only or unmapped)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="decode_message",
        description="Decode a wire-type message via server.javelin.dispatch",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List every captured wire-type the dispatcher knows about and exit",
    )
    parser.add_argument(
        "-t", "--type", default=None,
        help="Wire type-id (0x15d, 15d, or 349). Required unless --list.",
    )
    parser.add_argument(
        "-d", "--direction", default="R", choices=["R", "W"],
        help="R = server→client (default), W = client→server",
    )
    src = parser.add_argument_group("body source (pick one)")
    src.add_argument("--hex", help="Body as hex string (whitespace ignored)")
    src.add_argument("--file", help="Path to a file containing raw body bytes")
    src.add_argument("--stdin", action="store_true", help="Read body bytes from stdin")
    src.add_argument(
        "--replay-index", type=int, default=None, metavar="N",
        help="Pick the Nth captured message of this type+direction "
             "from the bundled replay (0-indexed)",
    )
    src.add_argument(
        "--seq", type=lambda s: int(s, 0), default=None, metavar="SEQ",
        help="Pick the captured message at this seq number "
             "(decimal or 0xHEX). Validates --type/--direction "
             "match the message at that seq.",
    )
    parser.add_argument(
        "--width", type=int, default=120,
        help="pprint output width (default 120)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit the decoded structure as JSON (machine-readable). "
             "Bytes fields render as hex strings; tuples/dataclasses as "
             "objects. Comment lines (`# ...`) go to stderr so stdout is "
             "clean JSON for piping.",
    )
    args = parser.parse_args(argv)

    if args.list:
        return _list_wire_types()

    if args.type is None:
        parser.error("--type/-t is required (or pass --list to enumerate types)")
    args.type_id = _parse_type_id(args.type)

    body = _read_body(args)

    header = f"# type=0x{args.type_id:x}  direction={args.direction}  len={len(body)} B"
    # When --json is set, comments go to stderr so stdout is parseable.
    print(header, file=sys.stderr if args.json else sys.stdout)

    decoded = dispatch.decode_replay_message(args.type_id, args.direction, body)
    if decoded is None:
        print(
            f"# no decoder registered for type 0x{args.type_id:x} "
            f"(intentionally skipped: 0x03 V3 response is server-emit-only, "
            f"or this type isn't in the dispatcher map)",
            file=sys.stderr,
        )
        return 1

    if args.json:
        import json
        json.dump(_to_jsonable(decoded), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        pprint.pp(decoded, width=args.width)
    return 0


def _to_jsonable(obj):
    """Recursively convert a codec dataclass to JSON-friendly types.
    Mirrors `tools/build_site.py::_to_jsonable`'s shape (bytes→hex,
    dataclass→dict)."""
    import dataclasses
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: _to_jsonable(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
        }
    if isinstance(obj, (bytes, bytearray)):
        return obj.hex()
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    return repr(obj)


if __name__ == "__main__":
    raise SystemExit(main())
